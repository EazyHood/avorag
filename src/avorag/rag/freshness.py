"""Frescura de dato regulatorio en vivo — el guardarraíl P-5 del contrato "0 ERRORES" (modo ONLINE).

Online cruza todo dato REGULATORIO (registro ICA, LMR de la UE, tolerancia 40 CFR 180 de EE.UU.)
contra su feed en vivo. Un dato fuera de su SLA de frescura NO DEBE servirse como vigente: el
semáforo se degrada (VERDE prohibido → AMARILLO) y se emite un aviso con la fecha del dato. Esto
materializa el punto (3) del contrato "0 errores": *cero dato regulatorio caducado servido como
vigente*.

Diseño: lógica PURA y DETERMINISTA. `now` es inyectable (para tests reproducibles). NO toca BD ni
red: opera sobre vistas de snapshot que el pipeline obtiene de `feed_snapshots` (migración 0005).

Integración (NO invasiva — no edita `decide_semaforo`): el pipeline, tras calcular el semáforo,
llama a `apply_freshness_gate(...)` para degradar un VERDE que dependa de un feed no-fresco. Ver el
ejemplo al final del módulo.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from avorag.rag.schemas import Semaforo


class FeedName(StrEnum):
    ICA = "ica_simplifica"  # vigencia/cancelación de registros PQUA (SimplifICA)
    IDEAM = "ideam"  # clima (ETc/Kc/grados-día)
    LMR_UE = "lmr_ue"  # límites máximos de residuos UE (Reg. 396/2005)
    TOL_EEUU = "tol_eeuu_40cfr180"  # tolerancias EE.UU. (40 CFR Parte 180)
    PRECIOS = "precios"  # mercado


# Feeds cuyo dato es REGULATORIO/de-seguridad: si están no-frescos, VERDE queda PROHIBIDO.
# IDEAM (clima) y PRECIOS NO son regulatorios: su caducidad NO debe bloquear una recomendación
# fitosanitaria (sí degradar una de riego/precio, pero eso lo decide el dominio que los use).
REGULATORY_FEEDS: frozenset[FeedName] = frozenset(
    {FeedName.ICA, FeedName.LMR_UE, FeedName.TOL_EEUU}
)

# SLA de frescura por feed (segundos). Orientativo y configurable; debe coincidir con el
# `ttl_seconds` del snapshot cuando exista. Un dato más viejo que esto se considera STALE.
DEFAULT_TTL_SECONDS: dict[FeedName, int] = {
    FeedName.ICA: 7 * 24 * 3600,  # registros ICA: revisión semanal
    FeedName.LMR_UE: 7 * 24 * 3600,  # LMR UE: semanal
    FeedName.TOL_EEUU: 7 * 24 * 3600,  # tolerancias EE.UU.: semanal
    FeedName.IDEAM: 6 * 3600,  # clima: horas
    FeedName.PRECIOS: 24 * 3600,  # precios: diario
}

# Tolerancia de reloj para un `as_of` "del futuro". Hasta aquí lo achacamos a skew de reloj y lo
# tratamos como fresco; más allá es sospechoso (feed re-sellado / reloj adelantado / payload
# manipulado) y NO debe darse por vigente — si no, una fecha futura evade el gate STALE indefinidamente.
MAX_FUTURE_SKEW_SECONDS = 2 * 3600


class FreshnessState(StrEnum):
    OK = "ok"
    STALE = "stale"  # hay snapshot, pero más viejo que su SLA
    MISSING = "missing"  # no hay snapshot (feed nunca llegó o cayó sin caché)


@dataclass(frozen=True)
class FeedSnapshotView:
    """Vista mínima de un `feed_snapshots` (migración 0005) para evaluar frescura, sin acoplar al ORM."""

    feed_name: str
    as_of: datetime | None
    ttl_seconds: int | None = None


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(UTC)


def _ttl_for(feed: str, snapshot: FeedSnapshotView | None) -> int:
    if snapshot is not None and snapshot.ttl_seconds:
        return int(snapshot.ttl_seconds)
    try:
        return DEFAULT_TTL_SECONDS[FeedName(feed)]
    except ValueError:
        return 24 * 3600  # desconocido → 1 día por defecto, conservador


def freshness_state(
    snapshot: FeedSnapshotView | None, *, now: datetime | None = None
) -> FreshnessState:
    """Estado de frescura de un snapshot. MISSING si no hay dato; STALE si superó su SLA; OK si no."""
    if snapshot is None or snapshot.as_of is None:
        return FreshnessState.MISSING
    now = _now(now)
    as_of = snapshot.as_of if snapshot.as_of.tzinfo else snapshot.as_of.replace(tzinfo=UTC)
    edad_s = (now - as_of).total_seconds()
    if edad_s < 0:
        # Dato "del futuro": tolera solo un skew de reloj pequeño; más allá es sospechoso y NO
        # lo damos por fresco (si no, una fecha futura evadiría el gate STALE indefinidamente).
        return FreshnessState.OK if -edad_s <= MAX_FUTURE_SKEW_SECONDS else FreshnessState.STALE
    return (
        FreshnessState.OK
        if edad_s <= _ttl_for(snapshot.feed_name, snapshot)
        else FreshnessState.STALE
    )


# ── Detección de dependencia regulatoria de una respuesta (heurística, accent-insensitive) ──────
def _strip(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", (text or "").lower())
        if unicodedata.category(c) != "Mn"
    )


# Alias público: el cruce regulatorio y los lookups de feeds normalizan acentos con el MISMO criterio
# (evita el desajuste tildes feed↔diccionario que dejaba pasar 'clorpirifós' vs 'clorpirifos').
strip_accents = _strip


# Señales de que la respuesta APOYA una recomendación fitosanitaria (depende de la vigencia ICA).
_PESTICIDE_CTX = re.compile(
    r"\bregistro\b|\bica\b|simplifica|\bcarencia\b|periodo de seguridad|reingreso|"
    r"plaguicid|fitosanitari|insecticid|fungicid|acaricid|\bi\.?a\.?\b|ingrediente activo|"
    r"\bdosis\b|cc\s?/\s?l|l\s?/\s?ha|kg\s?/\s?ha|g\s?/\s?l",
    re.IGNORECASE,
)


def mentions_pesticide_context(answer_text: str) -> bool:
    """True si el texto APOYA una recomendación fitosanitaria (dosis/registro/carencia/i.a.)."""
    return bool(_PESTICIDE_CTX.search(_strip(answer_text)))


def regulatory_feeds_for(answer_text: str, *, export_market: str | None = None) -> set[FeedName]:
    """Qué feeds REGULATORIOS condicionan la validez de esta respuesta.

    - Si la respuesta apoya una recomendación fitosanitaria (dosis/registro/carencia/i.a.) → ICA
      (su validez depende de que el registro siga VIGENTE en SimplifICA).
    - Si además se exporta a un destino con `export_market`, su admisibilidad depende del feed del
      destino (UE → LMR_UE; EE.UU. → TOL_EEUU).
    """
    out: set[FeedName] = set()
    if _PESTICIDE_CTX.search(_strip(answer_text)):
        out.add(FeedName.ICA)
        m = (export_market or "").strip().lower()
        if m == "ue":
            out.add(FeedName.LMR_UE)
        elif m in ("eeuu", "us", "usa"):
            out.add(FeedName.TOL_EEUU)
    return out


def verde_permitido(
    *,
    depends_on_feeds: set[FeedName] | set[str],
    snapshots: dict[str, FeedSnapshotView] | None = None,
    now: datetime | None = None,
) -> tuple[bool, list[str]]:
    """¿Se permite VERDE dado el estado de frescura de los feeds de los que depende la respuesta?

    Devuelve (permitido, avisos). VERDE queda PROHIBIDO si algún feed REGULATORIO del que depende
    la respuesta está STALE o MISSING. Los avisos citan la fecha del dato (o su ausencia) y se
    adjuntan a `Answer.warnings`.
    """
    snapshots = snapshots or {}
    avisos: list[str] = []
    permitido = True
    for feed in depends_on_feeds:
        try:
            feed = FeedName(feed) if not isinstance(feed, FeedName) else feed
        except ValueError:
            continue
        if feed not in REGULATORY_FEEDS:
            continue
        estado = freshness_state(snapshots.get(str(feed)), now=now)
        if estado is FreshnessState.MISSING:
            permitido = False
            avisos.append(
                f"Dato regulatorio de «{feed.value}» NO verificado en vivo: no se confirma vigencia. "
                "Verifica en la fuente oficial antes de aplicar."
            )
        elif estado is FreshnessState.STALE:
            permitido = False
            snap = snapshots.get(str(feed))
            fecha = snap.as_of.date().isoformat() if snap and snap.as_of else "?"
            avisos.append(
                f"Dato regulatorio de «{feed.value}» fechado «{fecha}» fuera del plazo de frescura: "
                "puede haber cambiado. Verifica la vigencia en la fuente oficial."
            )
    return permitido, avisos


def apply_freshness_gate(
    semaforo: Semaforo,
    reason: str,
    *,
    verde_ok: bool,
    avisos: list[str],
) -> tuple[Semaforo, str, list[str]]:
    """Compone la frescura con el semáforo YA decidido, SIN escalarlo nunca (invariante de la
    arquitectura): solo degrada un VERDE a AMARILLO si la frescura no lo permite. NUNCA toca un
    ROJO ni convierte AMARILLO en VERDE. Pensado para llamarse en el pipeline tras `decide_semaforo`.
    """
    if semaforo is Semaforo.VERDE and not verde_ok:
        motivo = avisos[0] if avisos else "dato regulatorio no verificado en vivo"
        return (
            Semaforo.AMARILLO,
            f"Frescura regulatoria: {motivo} No es un VERDE confiable hasta verificar en la fuente.",
            avisos,
        )
    return semaforo, reason, avisos


# Ejemplo de integración en el pipeline (NO invasivo; pseudo):
#
#     sem, reason = decide_semaforo(...)                     # guardarraíl determinista existente
#     feeds = regulatory_feeds_for(ans.text, export_market=req.export_market)
#     ok, avisos = verde_permitido(depends_on_feeds=feeds, snapshots=feed_views_from_db())
#     sem, reason, avisos = apply_freshness_gate(sem, reason, verde_ok=ok, avisos=avisos)
#     ans.semaforo, ans.reason = sem, reason
#     ans.warnings.extend(avisos)
