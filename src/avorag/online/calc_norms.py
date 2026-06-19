"""Enriquecimiento de las CALCULADORAS con normas versionadas de `norm_tables` (modo online).

Cierra el lazo "umbrales hardcodeados" SIN romper la pureza ni la paridad offline: `agro_calc.py`
sigue siendo puro (las calculadoras Dart offline usan sus defaults/bundle). El servidor ONLINE, si
se activa `AVORAG_ONLINE_NORMS=1`, RESUELVE los umbrales desde `norm_tables` (vía `online.norms`) y
los PASA a las funciones de `agro_calc` que ya aceptan ese parámetro, estampando `norm_version`.

Gated y con fallback: si está apagado o la BD no tiene la norma, devuelve (None, None) y la ruta usa
su comportamiento actual (idéntico al offline). Colisión-safe: módulo NUEVO bajo `online/`.
"""

from __future__ import annotations

import os

from avorag.online.norms import get_norm

_HASS = {"cultivo": "hass"}


def online_norms_enabled() -> bool:
    """True si las calculadoras online deben resolver umbrales desde `norm_tables`."""
    return os.getenv("AVORAG_ONLINE_NORMS", "").lower() in ("1", "true", "yes", "on")


# --- Mapeo PURO (params de la norma → valor) — testeable sin BD --------------------------------
def ms_umbral_from_params(params: dict, objetivo: str | None) -> float | None:
    v = params.get((objetivo or "exportacion").strip().lower())
    return float(v) if v is not None else None


def ce_umbral_from_params(params: dict, portainjerto: str | None) -> float | None:
    key = (portainjerto or "").strip().lower()
    v = params.get(key) if key else None
    v = v if v is not None else params.get("_default")
    return float(v) if v is not None else None


def _norm_params(norm_key: str, scope: dict | None) -> tuple[dict, str | None]:
    """(params, norm_version) de la norma vigente; ({}, None) si no se puede leer."""
    try:
        from avorag.db import get_session

        with get_session(system=True) as session:
            n = get_norm(session, norm_key, scope=scope or _HASS)
        return n["params"], n["norm_version"]
    except Exception:  # noqa: BLE001 — sin BD/seed ⇒ que la ruta use su default
        return {}, None


def resolve_ms_umbral(
    objetivo: str | None, *, scope: dict | None = None
) -> tuple[float | None, str | None]:
    """(umbral_pct, norm_version) desde `ms_objetivo`, o (None, None) si apagado/no disponible."""
    if not online_norms_enabled():
        return None, None
    params, ver = _norm_params("ms_objetivo", scope)
    return ms_umbral_from_params(params, objetivo), ver


def resolve_ce_umbral(
    portainjerto: str | None, *, scope: dict | None = None
) -> tuple[float | None, str | None]:
    """(CEe umbral dS/m, norm_version) desde `ce_umbral_portainjerto`, o (None, None)."""
    if not online_norms_enabled() or not portainjerto:
        return None, None
    params, ver = _norm_params("ce_umbral_portainjerto", scope)
    return ce_umbral_from_params(params, portainjerto), ver
