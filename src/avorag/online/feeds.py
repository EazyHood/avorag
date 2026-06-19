"""Servicio de FEEDS EN VIVO del modo ONLINE — el superpoder que cierra los huecos regulatorios.

Cada feed (ICA/SimplifICA, IDEAM, LMR UE, tolerancias 40 CFR 180, precios) se obtiene por un
PROVEEDOR intercambiable, se NORMALIZA a un esquema canónico, se SELLA con sha256 y se persiste como
un `FeedSnapshot` versionado (migración 0005). La frescura (P-5) la evalúa `avorag.rag.freshness`;
este módulo aporta el FETCH + la NORMALIZACIÓN + el LOOKUP que el guardarraíl consume para forzar
ROJO con dato vivo.

Diseño (testeable sin red ni BD):
- La cadena fetch→normalizar→sha256→lookup es PURA y determinista (`now` inyectable).
- El acceso a BD son funciones finas que reciben una `Session`.
- Aún SIN red real: hay proveedores `fake` deterministas (demo/tests) y los reales son STUBS marcados
  (`NotImplementedError`) para no acoplar a APIs externas inestables. Activar por `.env` cuando existan.

Colisión: módulo NUEVO bajo `online/`. NO toca el núcleo compartido (guardrails/pipeline/models/config).
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from avorag.db.models_online import FeedSnapshot
from avorag.logging import get_logger
from avorag.rag.freshness import (
    DEFAULT_TTL_SECONDS,
    FeedName,
    FeedSnapshotView,
    strip_accents,
)

log = get_logger(__name__)


# ── Tipos ───────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FeedFetch:
    """Resultado normalizado de consultar un feed (antes de persistir)."""

    feed_name: str
    as_of: datetime  # fecha-de-dato declarada por la fuente
    ttl_seconds: int  # SLA de frescura del feed
    payload: dict  # contenido canónico (esquema por feed, ver más abajo)
    source_url: str | None = None

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.payload)


def canonical_sha256(payload: dict) -> str:
    """Hash determinista e independiente del orden de claves del payload canónico (integridad/dedup)."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(UTC)


# ── Proveedores ───────────────────────────────────────────────────────────────────────────────
class FeedProvider(ABC):
    """Obtiene un feed y lo devuelve NORMALIZADO. Intercambiable por `.env` (igual que los LLM)."""

    feed: FeedName
    name: str = "desconocido"

    @property
    def default_ttl_seconds(self) -> int:
        return DEFAULT_TTL_SECONDS.get(self.feed, 24 * 3600)

    @abstractmethod
    def fetch(self, *, now: datetime | None = None) -> FeedFetch: ...


# --- Proveedores FAKE deterministas (demo/tests; sin red) ---------------------------------------
class FakeIcaProvider(FeedProvider):
    """Registros ICA simulados: estado de vigencia por ingrediente activo (canónico)."""

    feed = FeedName.ICA
    name = "fake-ica"

    def fetch(self, *, now: datetime | None = None) -> FeedFetch:
        payload = {
            "registros": [
                {
                    "ingrediente_activo": "clorpirifos",
                    "registro_ica": "0001",
                    "estado": "cancelado",
                    "cultivo": "varios",
                },
                {
                    "ingrediente_activo": "abamectina",
                    "registro_ica": "1234",
                    "estado": "vigente",
                    "cultivo": "hass",
                },
                {
                    "ingrediente_activo": "spinetoram",
                    "registro_ica": "5678",
                    "estado": "vigente",
                    "cultivo": "hass",
                },
            ]
        }
        return FeedFetch(
            self.feed.value, _now(now), self.default_ttl_seconds, payload, "fake://ica"
        )


class FakeLmrUeProvider(FeedProvider):
    """LMR UE simulados (mg/kg) + lista de no aprobados (canónico)."""

    feed = FeedName.LMR_UE
    name = "fake-lmr-ue"

    def fetch(self, *, now: datetime | None = None) -> FeedFetch:
        payload = {
            "lmr_mg_kg": {"abamectina": 0.01, "spinetoram": 0.03},
            "no_aprobados": ["clorpirifos"],
        }
        return FeedFetch(
            self.feed.value, _now(now), self.default_ttl_seconds, payload, "fake://lmr-ue"
        )


class FakeTolEeuuProvider(FeedProvider):
    """Tolerancias EE.UU. (40 CFR 180) simuladas: tolerancia por par activo-AGUACATE (canónico)."""

    feed = FeedName.TOL_EEUU
    name = "fake-tol-eeuu"

    def fetch(self, *, now: datetime | None = None) -> FeedFetch:
        payload = {
            "avocado_tolerances_ppm": {"paraquat": 0.05, "azoxystrobin": 1.0, "abamectina": 0.02},
            "sin_tolerancia": ["clorpirifos", "metamidofos"],
        }
        return FeedFetch(
            self.feed.value, _now(now), self.default_ttl_seconds, payload, "fake://40cfr180"
        )


# --- Proveedores REALES (stubs marcados; activar cuando exista el conector) ----------------------
class _RealStub(FeedProvider):
    name = "real-stub"

    def fetch(self, *, now: datetime | None = None) -> FeedFetch:
        raise NotImplementedError(
            f"Conector real de '{self.feed.value}' pendiente. Configura la fuente/credenciales o usa "
            "el proveedor 'fake'. Ver docs/ARQUITECTURA_ONLINE.md (Parte 5: conectores de datos en vivo)."
        )


class IcaSimplificaProvider(_RealStub):
    feed = FeedName.ICA
    name = "ica-simplifica"


class IdeamProvider(_RealStub):
    feed = FeedName.IDEAM
    name = "ideam"


class LmrUeProvider(_RealStub):
    feed = FeedName.LMR_UE
    name = "lmr-ue"


class Tol40CFRProvider(_RealStub):
    feed = FeedName.TOL_EEUU
    name = "tol-eeuu-40cfr180"


# --- Proveedor REAL genérico por HTTP-JSON (para cualquier feed expuesto ya NORMALIZADO) ---------
def _http_get_json(url: str, *, timeout: float = 15.0) -> dict:
    """GET de una URL que devuelve el payload canónico en JSON (stdlib, sin dependencias)."""
    import urllib.request

    req = urllib.request.Request(  # noqa: S310 — URL de confianza configurada por el operador
        url, headers={"User-Agent": "AvoRAG-feeds/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("El feed HTTP no devolvió un objeto JSON (se espera el payload canónico).")
    return payload


class HttpJsonProvider(FeedProvider):
    """Trae el payload canónico de un feed desde una URL JSON (env `AVORAG_FEED_<FEED>_URL`).

    Útil cuando el operador expone el dato ya normalizado al esquema canónico (ver CANONICAL_SCHEMAS).
    Los conectores que exigen scraping/parseo específico (portal SimplifICA, EU Pesticides Database…)
    siguen como stubs hasta tener su formato exacto.
    """

    name = "http-json"

    def __init__(self, feed: FeedName, url: str) -> None:
        self.feed = feed
        self._url = url

    def fetch(self, *, now: datetime | None = None) -> FeedFetch:
        payload = _http_get_json(self._url)
        as_of = _now(now)
        raw = payload.get("as_of")
        if isinstance(raw, str):
            with contextlib.suppress(ValueError):
                as_of = datetime.fromisoformat(raw)
        return FeedFetch(self.feed.value, as_of, self.default_ttl_seconds, payload, self._url)


def _feed_url_env(feed: FeedName) -> str:
    return os.getenv(f"AVORAG_FEED_{feed.name}_URL", "").strip()


# --- Proveedor REAL por ARCHIVO CSV (vía realista: el operador descarga el export OFICIAL) ---------
# El operador deja periódicamente el export oficial (CSV) en una ruta y un NORMALIZADOR lo mapea al
# esquema canónico. Robusto y testeable (sin scraping frágil de portales). Mapeo de columnas
# configurable; los defaults asumen cabeceras con el nombre del campo canónico.
DEFAULT_CSV_MAPPING: dict[FeedName, dict[str, str]] = {
    FeedName.ICA: {
        "ia": "ingrediente_activo",
        "registro": "registro_ica",
        "estado": "estado",
        "cultivo": "cultivo",
    },
    FeedName.LMR_UE: {"ia": "ingrediente_activo", "lmr": "lmr_mg_kg", "aprobado": "aprobado"},
    FeedName.TOL_EEUU: {
        "ia": "ingrediente_activo",
        "ppm": "tolerancia_ppm",
        "tiene": "tiene_tolerancia",
    },
}
# Tokens que afirman INEQUÍVOCAMENTE aprobación/tolerancia. Cualquier OTRO valor NO afirmativo
# (negativo explícito, o texto libre como 'no renovado'/'revocado') se trata por el LADO SEGURO.
# La cadena VACÍA es "dato faltante" (desconocido), NO una afirmación negativa: NO está aquí ni se
# interpreta como 'no aprobado' (así una columna ausente no provoca un over-block masivo).
_APROBADO_TOKENS = {"si", "sí", "true", "1", "yes", "aprobado", "approved", "y", "t", "vigente"}
# Negativos explícitos de tolerancia EE.UU. (el ppm es la verdad vinculante; estos solo refuerzan).
_NO_TOL_TOKENS = {"no", "false", "n", "f", "0", "sin", "none", "no tiene", "sin tolerancia"}


def _read_csv(path: str) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _norm_ica(rows: list[dict], m: dict) -> dict:
    out = []
    for r in rows:
        ia = str(r.get(m["ia"], "")).strip().lower()
        if ia:
            out.append(
                {
                    "ingrediente_activo": ia,
                    "registro_ica": str(r.get(m.get("registro", ""), "")).strip(),
                    "estado": str(r.get(m["estado"], "")).strip().lower(),
                    "cultivo": str(r.get(m.get("cultivo", ""), "")).strip().lower(),
                }
            )
    return {"registros": out}


def _norm_lmr_ue(rows: list[dict], m: dict) -> dict:
    lmr: dict[str, float] = {}
    no_ap: list[str] = []
    for r in rows:
        ia = str(r.get(m["ia"], "")).strip().lower()
        if not ia:
            continue
        estado = strip_accents(str(r.get(m.get("aprobado", ""), "")).strip())
        if not estado:
            continue  # celda vacía = dato faltante ⇒ 'desconocido' (ni aprobado ni no_aprobado)
        if estado not in _APROBADO_TOKENS:
            # Negativo explícito o texto ambiguo ('no renovado','revocado','pendiente') ⇒ lado seguro.
            no_ap.append(ia)
            continue
        with contextlib.suppress(ValueError, TypeError):
            lmr[ia] = float(str(r.get(m.get("lmr", ""), "")).replace(",", "."))
    return {"lmr_mg_kg": lmr, "no_aprobados": no_ap}


def _norm_eeuu(rows: list[dict], m: dict) -> dict:
    tols: dict[str, float] = {}
    sin: list[str] = []
    for r in rows:
        ia = str(r.get(m["ia"], "")).strip().lower()
        if not ia:
            continue
        tiene = strip_accents(str(r.get(m.get("tiene", ""), "")).strip())
        ppm = str(r.get(m.get("ppm", ""), "")).strip()
        val: float | None = None
        if ppm:
            try:
                val = float(ppm.replace(",", "."))
            except (ValueError, TypeError):
                val = None
        # Afirma tolerancia SOLO con ppm numérico > 0 y sin negativo explícito. Lo demás (0 ppm, sin
        # ppm, 'no', vacío) ⇒ sin_tolerancia (40 CFR 180: ausencia o 0 ppm = residuo violatorio).
        if val is not None and val > 0 and tiene not in _NO_TOL_TOKENS:
            tols[ia] = val
        else:
            sin.append(ia)
    return {"avocado_tolerances_ppm": tols, "sin_tolerancia": sin}


_CSV_NORMALIZERS = {
    FeedName.ICA: _norm_ica,
    FeedName.LMR_UE: _norm_lmr_ue,
    FeedName.TOL_EEUU: _norm_eeuu,
}


class CsvFileProvider(FeedProvider):
    """Lee un export OFICIAL en CSV de una ruta y lo normaliza al esquema canónico (env AVORAG_FEED_<FEED>_FILE)."""

    name = "csv-file"

    def __init__(self, feed: FeedName, path: str, mapping: dict | None = None) -> None:
        if feed not in _CSV_NORMALIZERS:
            raise ValueError(f"No hay normalizador CSV para «{feed.value}».")
        self.feed = feed
        self._path = path
        self._mapping = mapping or DEFAULT_CSV_MAPPING[feed]

    def fetch(self, *, now: datetime | None = None) -> FeedFetch:
        rows = _read_csv(self._path)
        if rows:
            present = set(rows[0].keys())
            missing = [c for c in self._mapping.values() if c and c not in present]
            if missing:
                # Cabecera drifteada: avisa en vez de degradar columnas en silencio (over-block/under-block).
                log.warning(
                    "feed_csv_columns_missing",
                    feed=self.feed.value,
                    missing=missing,
                    path=self._path,
                )
        payload = _CSV_NORMALIZERS[self.feed](rows, self._mapping)
        return FeedFetch(
            self.feed.value, _now(now), self.default_ttl_seconds, payload, f"file://{self._path}"
        )


def _feed_file_env(feed: FeedName) -> str:
    return os.getenv(f"AVORAG_FEED_{feed.name}_FILE", "").strip()


_FAKE_REGISTRY: dict[FeedName, type[FeedProvider]] = {
    FeedName.ICA: FakeIcaProvider,
    FeedName.LMR_UE: FakeLmrUeProvider,
    FeedName.TOL_EEUU: FakeTolEeuuProvider,
}
_REAL_REGISTRY: dict[FeedName, type[FeedProvider]] = {
    FeedName.ICA: IcaSimplificaProvider,
    FeedName.IDEAM: IdeamProvider,
    FeedName.LMR_UE: LmrUeProvider,
    FeedName.TOL_EEUU: Tol40CFRProvider,
}


def get_provider(feed: FeedName, *, mode: str = "fake") -> FeedProvider:
    """Fábrica de proveedores. `mode='fake'` (determinista, sin red); `'real'` usa la URL HTTP-JSON
    configurada (`AVORAG_FEED_<FEED>_URL`) y, si no hay, el stub específico del feed."""
    if mode == "fake":
        cls = _FAKE_REGISTRY.get(feed)
        if cls is None:
            raise ValueError(f"No hay proveedor 'fake' para el feed «{feed.value}».")
        return cls()
    # real: archivo CSV oficial → URL HTTP-JSON → stub específico.
    path = _feed_file_env(feed)
    if path and feed in _CSV_NORMALIZERS:
        return CsvFileProvider(feed, path)
    url = _feed_url_env(feed)
    if url:
        return HttpJsonProvider(feed, url)
    cls = _REAL_REGISTRY.get(feed)
    if cls is None:
        raise ValueError(f"No hay proveedor 'real' para el feed «{feed.value}».")
    return cls()


# ── Lookups canónicos (PUROS) — lo que el guardarraíl consume ──────────────────────────────────
def ica_status(payload: dict, ingrediente_activo: str) -> str:
    """Estado de vigencia del registro ICA de un i.a.: 'vigente' | 'cancelado' | 'desconocido'.

    Compara SIN acentos (clorpirifós == clorpirifos) para no perder cruces por tildes feed↔lookup.
    """
    ia = strip_accents((ingrediente_activo or "").strip())
    for r in payload.get("registros", []):
        if strip_accents(str(r.get("ingrediente_activo", ""))) == ia:
            return str(r.get("estado", "desconocido")).strip().lower()
    return "desconocido"


def ue_lmr(payload: dict, ingrediente_activo: str) -> tuple[str, float | None]:
    """LMR UE de un i.a.: ('no_aprobado'|'aprobado'|'desconocido', valor_mg_kg|None). Sin acentos."""
    ia = strip_accents((ingrediente_activo or "").strip())
    if ia in {strip_accents(str(x)) for x in payload.get("no_aprobados", [])}:
        return ("no_aprobado", None)
    lmr = {strip_accents(str(k)): v for k, v in payload.get("lmr_mg_kg", {}).items()}
    if ia in lmr:
        try:
            return ("aprobado", float(lmr[ia]))
        except (TypeError, ValueError):
            return ("aprobado", None)
    return ("desconocido", None)


def eeuu_tolerance(payload: dict, ingrediente_activo: str) -> tuple[bool, float | None]:
    """Tolerancia EE.UU. (40 CFR 180) del par i.a.-AGUACATE: (tiene_tolerancia, ppm|None).

    La verdad vinculante es la tolerancia por par activo-aguacate: sin tolerancia ⇒ residuo violatorio.
    Una tolerancia de 0 ppm NO autoriza: en 40 CFR 180 significa que cualquier residuo detectable es
    violatorio (sin tolerancia efectiva). Compara sin acentos.
    """
    ia = strip_accents((ingrediente_activo or "").strip())
    tols = {strip_accents(str(k)): v for k, v in payload.get("avocado_tolerances_ppm", {}).items()}
    if ia in tols:
        try:
            val = float(tols[ia])
        except (TypeError, ValueError):
            return (False, None)
        return (val > 0, val if val > 0 else None)
    if ia in {strip_accents(str(x)) for x in payload.get("sin_tolerancia", [])}:
        return (False, None)
    return (False, None)  # ausencia ≠ autorizado: por defecto, sin tolerancia conocida


# ── Persistencia (migración 0005) ──────────────────────────────────────────────────────────────
# Claves mínimas del payload canónico por feed REGULATORIO. Un payload sin ellas (esquema drifteado,
# JSON/CSV roto) NO debe servirse como un feed "presente y fresco" con lookups vacíos: se marca
# inválido para que la frescura lo trate como MISSING y el gate degrade, en vez de afirmar vigencia.
_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    FeedName.ICA.value: ("registros",),
    FeedName.LMR_UE.value: ("lmr_mg_kg", "no_aprobados"),
    FeedName.TOL_EEUU.value: ("avocado_tolerances_ppm", "sin_tolerancia"),
}


def payload_status(feed_name: str, payload: dict) -> str:
    """'ok' si el payload trae el esquema canónico mínimo del feed; 'schema_invalid' si no.

    Los feeds no regulatorios (sin esquema requerido) se consideran 'ok' (no bloqueantes).
    """
    req = _REQUIRED_KEYS.get(feed_name)
    if req is None:
        return "ok"
    if not isinstance(payload, dict) or any(k not in payload for k in req):
        return "schema_invalid"
    return "ok"


def upsert_snapshot(session: Session, fetch: FeedFetch) -> FeedSnapshot:
    """Inserta el snapshot si su (feed_name, sha256) no existe; idempotente (P-6). Devuelve la fila."""
    existing = session.scalar(
        select(FeedSnapshot).where(
            FeedSnapshot.feed_name == fetch.feed_name,
            FeedSnapshot.sha256 == fetch.sha256,
        )
    )
    if existing is not None:
        return existing
    status = payload_status(fetch.feed_name, fetch.payload)
    if status != "ok":
        log.warning("feed_payload_schema_invalid", feed=fetch.feed_name, sha256=fetch.sha256[:12])
    snap = FeedSnapshot(
        feed_name=fetch.feed_name,
        source_url=fetch.source_url,
        as_of=fetch.as_of,
        ttl_seconds=fetch.ttl_seconds,
        status=status,
        sha256=fetch.sha256,
        payload=fetch.payload,
    )
    session.add(snap)
    session.flush()
    return snap


def latest_snapshot(session: Session, feed: FeedName | str) -> FeedSnapshot | None:
    """Snapshot más reciente (por `as_of`) de un feed, o None."""
    name = feed.value if isinstance(feed, FeedName) else str(feed)
    return session.scalar(
        select(FeedSnapshot)
        .where(FeedSnapshot.feed_name == name)
        .order_by(FeedSnapshot.as_of.desc())
        .limit(1)
    )


def latest_view(session: Session, feed: FeedName | str) -> FeedSnapshotView | None:
    """Vista de frescura del snapshot más reciente (puente a `avorag.rag.freshness`)."""
    snap = latest_snapshot(session, feed)
    if snap is None or (snap.status and snap.status != "ok"):
        return (
            None  # sin snapshot o esquema inválido ⇒ MISSING para la frescura (no afirma vigencia)
        )
    return FeedSnapshotView(
        feed_name=snap.feed_name, as_of=snap.as_of, ttl_seconds=snap.ttl_seconds
    )


def freshness_views(
    session: Session, feeds: set[FeedName] | set[str]
) -> dict[str, FeedSnapshotView]:
    """Mapa {feed_name: FeedSnapshotView} listo para `freshness.verde_permitido(...)`."""
    out: dict[str, FeedSnapshotView] = {}
    for f in feeds:
        name = f.value if isinstance(f, FeedName) else str(f)
        view = latest_view(session, name)
        if view is not None:
            out[name] = view
    return out


def refresh_feed(
    session: Session, provider: FeedProvider, *, now: datetime | None = None
) -> FeedSnapshot:
    """Punto de entrada del worker: obtiene del proveedor y hace upsert idempotente del snapshot."""
    fetch = provider.fetch(now=now)
    snap = upsert_snapshot(session, fetch)
    log.info(
        "feed_refreshed",
        feed=fetch.feed_name,
        sha256=fetch.sha256[:12],
        as_of=fetch.as_of.isoformat(),
    )
    return snap


# Esquemas canónicos por feed (documentación viva):
CANONICAL_SCHEMAS = {
    FeedName.ICA.value: "{'registros': [{'ingrediente_activo','registro_ica','estado','cultivo'}]}",
    FeedName.LMR_UE.value: "{'lmr_mg_kg': {ia: mg/kg}, 'no_aprobados': [ia]}",
    FeedName.TOL_EEUU.value: "{'avocado_tolerances_ppm': {ia: ppm}, 'sin_tolerancia': [ia]}",
}
