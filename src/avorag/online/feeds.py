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

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from avorag.db.models_online import FeedSnapshot
from avorag.logging import get_logger
from avorag.rag.freshness import DEFAULT_TTL_SECONDS, FeedName, FeedSnapshotView

log = get_logger(__name__)


# ── Tipos ───────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FeedFetch:
    """Resultado normalizado de consultar un feed (antes de persistir)."""

    feed_name: str
    as_of: datetime              # fecha-de-dato declarada por la fuente
    ttl_seconds: int             # SLA de frescura del feed
    payload: dict                # contenido canónico (esquema por feed, ver más abajo)
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
                {"ingrediente_activo": "clorpirifos", "registro_ica": "0001", "estado": "cancelado", "cultivo": "varios"},
                {"ingrediente_activo": "abamectina", "registro_ica": "1234", "estado": "vigente", "cultivo": "hass"},
                {"ingrediente_activo": "spinetoram", "registro_ica": "5678", "estado": "vigente", "cultivo": "hass"},
            ]
        }
        return FeedFetch(self.feed.value, _now(now), self.default_ttl_seconds, payload, "fake://ica")


class FakeLmrUeProvider(FeedProvider):
    """LMR UE simulados (mg/kg) + lista de no aprobados (canónico)."""

    feed = FeedName.LMR_UE
    name = "fake-lmr-ue"

    def fetch(self, *, now: datetime | None = None) -> FeedFetch:
        payload = {
            "lmr_mg_kg": {"abamectina": 0.01, "spinetoram": 0.03},
            "no_aprobados": ["clorpirifos"],
        }
        return FeedFetch(self.feed.value, _now(now), self.default_ttl_seconds, payload, "fake://lmr-ue")


class FakeTolEeuuProvider(FeedProvider):
    """Tolerancias EE.UU. (40 CFR 180) simuladas: tolerancia por par activo-AGUACATE (canónico)."""

    feed = FeedName.TOL_EEUU
    name = "fake-tol-eeuu"

    def fetch(self, *, now: datetime | None = None) -> FeedFetch:
        payload = {
            "avocado_tolerances_ppm": {"paraquat": 0.05, "azoxystrobin": 1.0, "abamectina": 0.02},
            "sin_tolerancia": ["clorpirifos", "metamidofos"],
        }
        return FeedFetch(self.feed.value, _now(now), self.default_ttl_seconds, payload, "fake://40cfr180")


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
    """Fábrica de proveedores. `mode='fake'` (determinista, sin red) o `'real'` (stub hasta conectar)."""
    table = _FAKE_REGISTRY if mode == "fake" else _REAL_REGISTRY
    cls = table.get(feed)
    if cls is None:
        raise ValueError(f"No hay proveedor '{mode}' para el feed «{feed.value}».")
    return cls()


# ── Lookups canónicos (PUROS) — lo que el guardarraíl consume ──────────────────────────────────
def ica_status(payload: dict, ingrediente_activo: str) -> str:
    """Estado de vigencia del registro ICA de un i.a.: 'vigente' | 'cancelado' | 'desconocido'."""
    ia = (ingrediente_activo or "").strip().lower()
    for r in payload.get("registros", []):
        if str(r.get("ingrediente_activo", "")).lower() == ia:
            return str(r.get("estado", "desconocido")).lower()
    return "desconocido"


def ue_lmr(payload: dict, ingrediente_activo: str) -> tuple[str, float | None]:
    """LMR UE de un i.a.: ('no_aprobado'|'aprobado'|'desconocido', valor_mg_kg|None)."""
    ia = (ingrediente_activo or "").strip().lower()
    if ia in {x.lower() for x in payload.get("no_aprobados", [])}:
        return ("no_aprobado", None)
    lmr = {k.lower(): v for k, v in payload.get("lmr_mg_kg", {}).items()}
    if ia in lmr:
        return ("aprobado", float(lmr[ia]))
    return ("desconocido", None)


def eeuu_tolerance(payload: dict, ingrediente_activo: str) -> tuple[bool, float | None]:
    """Tolerancia EE.UU. (40 CFR 180) del par i.a.-AGUACATE: (tiene_tolerancia, ppm|None).

    La verdad vinculante es la tolerancia por par activo-aguacate: sin tolerancia ⇒ residuo violatorio.
    """
    ia = (ingrediente_activo or "").strip().lower()
    tols = {k.lower(): v for k, v in payload.get("avocado_tolerances_ppm", {}).items()}
    if ia in tols:
        return (True, float(tols[ia]))
    if ia in {x.lower() for x in payload.get("sin_tolerancia", [])}:
        return (False, None)
    return (False, None)  # ausencia ≠ autorizado: por defecto, sin tolerancia conocida


# ── Persistencia (migración 0005) ──────────────────────────────────────────────────────────────
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
    snap = FeedSnapshot(
        feed_name=fetch.feed_name,
        source_url=fetch.source_url,
        as_of=fetch.as_of,
        ttl_seconds=fetch.ttl_seconds,
        status="ok",
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
        select(FeedSnapshot).where(FeedSnapshot.feed_name == name).order_by(FeedSnapshot.as_of.desc()).limit(1)
    )


def latest_view(session: Session, feed: FeedName | str) -> FeedSnapshotView | None:
    """Vista de frescura del snapshot más reciente (puente a `avorag.rag.freshness`)."""
    snap = latest_snapshot(session, feed)
    if snap is None:
        return None
    return FeedSnapshotView(feed_name=snap.feed_name, as_of=snap.as_of, ttl_seconds=snap.ttl_seconds)


def freshness_views(session: Session, feeds: set[FeedName] | set[str]) -> dict[str, FeedSnapshotView]:
    """Mapa {feed_name: FeedSnapshotView} listo para `freshness.verde_permitido(...)`."""
    out: dict[str, FeedSnapshotView] = {}
    for f in feeds:
        name = f.value if isinstance(f, FeedName) else str(f)
        view = latest_view(session, name)
        if view is not None:
            out[name] = view
    return out


def refresh_feed(session: Session, provider: FeedProvider, *, now: datetime | None = None) -> FeedSnapshot:
    """Punto de entrada del worker: obtiene del proveedor y hace upsert idempotente del snapshot."""
    fetch = provider.fetch(now=now)
    snap = upsert_snapshot(session, fetch)
    log.info("feed_refreshed", feed=fetch.feed_name, sha256=fetch.sha256[:12], as_of=fetch.as_of.isoformat())
    return snap


# Esquemas canónicos por feed (documentación viva):
CANONICAL_SCHEMAS = {
    FeedName.ICA.value: "{'registros': [{'ingrediente_activo','registro_ica','estado','cultivo'}]}",
    FeedName.LMR_UE.value: "{'lmr_mg_kg': {ia: mg/kg}, 'no_aprobados': [ia]}",
    FeedName.TOL_EEUU.value: "{'avocado_tolerances_ppm': {ia: ppm}, 'sin_tolerancia': [ia]}",
}
