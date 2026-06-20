"""Orquestación del guardarraíl ONLINE en vivo (freshness + cruce regulatorio) sobre un Answer.

Punto único que el pipeline (núcleo) invoca con UNA línea. Toda la lógica vive aquí (colisión-safe):
componer `freshness.apply_freshness_gate` + `regulatory.apply_regulatory_findings` sobre el semáforo
YA decidido, respetando la invariante de NO-escalado.

Activación: flag de entorno `AVORAG_ONLINE_FEEDS` (off por defecto → no-op total, NO cambia el modo
offline ni el comportamiento actual). El `export_market` se toma de la config (igual que el
guardarraíl de destino existente), así no hay que cambiar firmas del núcleo.

Fail-safe ("0 errores"): si la verificación en vivo falla (BD/feed caído), NUNCA rompe la respuesta;
degrada un VERDE a AMARILLO (Modo 2: no servir un verde sin verificación en vivo) y avisa.
"""

from __future__ import annotations

import os
from datetime import datetime

from avorag.config import get_settings
from avorag.logging import get_logger
from avorag.markets import SUPPORTED_MARKETS, normalize_market
from avorag.online import feeds, regulatory
from avorag.rag.freshness import (
    apply_freshness_gate,
    regulatory_feeds_for,
    verde_permitido,
)
from avorag.rag.schemas import Answer, Semaforo

log = get_logger(__name__)

_TRUE = {"1", "true", "yes", "on", "si", "sí"}
# Destinos con feed de residuo en vivo (UE→LMR, EE.UU.→40 CFR 180): se reutiliza el conjunto canónico
# de `markets.SUPPORTED_MARKETS` (única fuente de verdad, DRY). Un destino FUERA de este conjunto no se
# puede verificar en vivo y NO debe servirse como VERDE confiable (fail-closed más abajo).


def online_safety_enabled() -> bool:
    """True si el guardarraíl de feeds en vivo está activado (`AVORAG_ONLINE_FEEDS`)."""
    return os.getenv("AVORAG_ONLINE_FEEDS", "").strip().lower() in _TRUE


def _resolve_market(export_market: str | None) -> str | None:
    """Clave canónica del mercado (request > .env), compartida con el guardarraíl de destino offline."""
    return normalize_market(export_market or get_settings().export_market)


def apply_online_safety(
    session,
    answer: Answer,
    *,
    export_market: str | None = None,
    now: datetime | None = None,
) -> None:
    """Compone freshness + cruce regulatorio en vivo sobre `answer` (muta semáforo/reason/warnings).

    No-op si la respuesta se abstuvo o no contiene recomendación fitosanitaria. `session` debe poder
    leer `feed_snapshots` (tabla global). PURO salvo esa lectura.
    """
    if answer.abstained:
        return
    market = _resolve_market(export_market)
    feeds_needed = regulatory_feeds_for(answer.text, export_market=market)
    if not feeds_needed:
        return  # respuesta sin i.a./dosis → nada regulatorio que cruzar

    views = feeds.freshness_views(session, feeds_needed)
    verde_ok, fresh_av = verde_permitido(depends_on_feeds=feeds_needed, snapshots=views, now=now)
    findings = regulatory.live_regulatory_findings(
        session, answer.text, export_market=market, now=now
    )

    sem, reason, _ = apply_freshness_gate(
        answer.semaforo, answer.reason or "", verde_ok=verde_ok, avisos=fresh_av
    )
    sem, reason, reg_av = regulatory.apply_regulatory_findings(sem, reason, findings)

    # Destino de exportación SIN feed de residuo mapeado (ni UE ni EE.UU.): no se puede confirmar la
    # admisibilidad del residuo → no es un VERDE confiable (fail-closed para destinos no soportados).
    dest_av: list[str] = []
    if market and market not in SUPPORTED_MARKETS:
        aviso = (
            f"No hay feed de residuos para el destino «{market}»: no se puede confirmar la "
            "admisibilidad del residuo en ese mercado. Verifica el LMR/tolerancia del país de destino."
        )
        dest_av.append(aviso)
        if sem is Semaforo.VERDE:
            sem = Semaforo.AMARILLO
            reason = f"Destino «{market}» sin verificación de residuo en vivo. {aviso}"

    answer.semaforo = sem
    answer.reason = reason
    for aviso in (*fresh_av, *reg_av, *dest_av):
        if aviso and aviso not in answer.warnings:
            answer.warnings.append(aviso)


def _degrade_unverified(answer: Answer, *, has_fitosanitario: bool) -> None:
    """Fail-safe: si NO se pudo verificar en vivo, no servir un dato sin confirmar (NO fail-open).

    - Con recomendación fitosanitaria presente (i.a./dosis): CIERRA a ROJO — un dato de seguridad no
      verificable sobre un fitosanitario no debe entregarse como consejo blando (AMARILLO).
    - Sin fitosanitario: un VERDE no confiable baja a AMARILLO.
    Nunca toca un ROJO ya decidido.
    """
    if answer.semaforo is Semaforo.ROJO:
        return
    if has_fitosanitario:
        answer.semaforo = Semaforo.ROJO
        answer.reason = (
            "Modo online: no se pudo verificar en vivo el dato regulatorio de una recomendación "
            "fitosanitaria; se bloquea por precaución hasta confirmar en la fuente oficial."
        )
        aviso = (
            "Verificación regulatoria en vivo NO disponible sobre un fitosanitario: trátalo como NO "
            "confirmado y verifica el registro/LMR en la fuente oficial antes de aplicar."
        )
    elif answer.semaforo is Semaforo.VERDE:
        answer.semaforo = Semaforo.AMARILLO
        answer.reason = "Modo online: no se pudo verificar el dato regulatorio en vivo; revísalo antes de actuar."
        aviso = "Verificación regulatoria en vivo no disponible: trata el dato como NO confirmado."
    else:
        return
    if aviso not in answer.warnings:
        answer.warnings.append(aviso)


def apply_online_safety_for_tenant(
    tenant: str,
    answer: Answer,
    *,
    export_market: str | None = None,
    now: datetime | None = None,
) -> None:
    """Entrada que invoca el pipeline (núcleo). Gated por flag; abre su propia sesión SOLO si aplica.

    Fail-safe: cualquier error de la verificación en vivo se registra y degrada (no rompe la respuesta).
    """
    if not online_safety_enabled() or answer.abstained:
        return
    market = _resolve_market(export_market)
    if not regulatory_feeds_for(answer.text, export_market=market):
        return  # pura: evita abrir sesión si no hay nada regulatorio que verificar
    try:
        from avorag.db import (
            get_session,  # import perezoso (evita coste/ciclos cuando el flag está off)
        )

        with get_session(tenant=tenant) as session:
            apply_online_safety(session, answer, export_market=market, now=now)
    except Exception as exc:  # noqa: BLE001 — la seguridad online NUNCA debe tumbar la respuesta
        # Solo se llega aquí con contexto fitosanitario (regulatory_feeds_for no vacío arriba): el
        # fail-safe debe CERRAR (ROJO), no fail-open a AMARILLO.
        log.warning("online_safety_failed", error=str(exc))
        _degrade_unverified(answer, has_fitosanitario=True)
