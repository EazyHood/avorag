"""Normas VERSIONADAS de las calculadoras (modo online) — saca los umbrales hardcodeados a datos.

Cierra la crítica recurrente de las revisiones: los rangos de suficiencia foliar, el umbral CEe por
portainjerto, la T_base, los objetivos de %MS y los factores de encalado eran CONSTANTES en
`agro_calc.py`. Aquí pasan a ser filas **versionadas y citables** en `norm_tables` (migración 0005),
con un `norm_version` que se estampa en la respuesta.

Resiliente: `get_norm()` prefiere la norma vigente de la BD (actualizable sin desplegar) pero cae al
DEFAULT del código si la BD no está sembrada o no está disponible → funciona igual offline y antes
del seed. Idempotente: `seed_norms()` no duplica.

Colisión-safe: módulo NUEVO bajo `online/`. NO edita `agro_calc.py` (consumir estas normas desde las
calculadoras es un paso de núcleo que se hará avisando). Los DEFAULT son un MIRROR de los valores
actuales de `agro_calc.py` (norm_version 2026-06-17): la migración del criterio es de datos, no de cifras.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from avorag.db.models_online import NormTable
from avorag.logging import get_logger

log = get_logger(__name__)

NORM_VERSION = "2026-06-17"

# Mirror de los defaults de agro_calc.py (v1). El valor migra aquí; las calculadoras los leerán luego.
DEFAULT_NORMS: list[dict[str, Any]] = [
    {
        "norm_key": "foliar_suficiencia",
        "norm_version": NORM_VERSION,
        "scope": {"cultivo": "hass"},
        "params": {
            "n": [1.6, 2.4, "%"],
            "p": [0.08, 0.25, "%"],
            "k": [0.75, 2.0, "%"],
            "ca": [1.0, 3.0, "%"],
            "mg": [0.25, 0.8, "%"],
            "s": [0.2, 0.6, "%"],
            "b": [40, 100, "ppm"],
            "zn": [30, 150, "ppm"],
            "fe": [50, 200, "ppm"],
            "mn": [30, 500, "ppm"],
            "cu": [5, 25, "ppm"],
        },
        "fuente": "Rangos de suficiencia foliar orientativos para Hass (hoja madura).",
    },
    {
        "norm_key": "ms_objetivo",
        "norm_version": NORM_VERSION,
        "scope": {"cultivo": "hass"},
        "params": {"minimo_legal": 20.8, "exportacion": 23.0, "premium": 25.0},
        "fuente": "Mínimo de madurez (CODEX/California) + exigencia comercial habitual/premium.",
    },
    {
        "norm_key": "ce_umbral_portainjerto",
        "norm_version": NORM_VERSION,
        "scope": {"cultivo": "hass"},
        "params": {"mexicano": 1.0, "guatemalteco": 1.3, "antillano": 1.8, "_default": 1.3},
        "fuente": "Tolerancia a salinidad (CEe, dS/m) por raza de portainjerto (orientativo).",
    },
    {
        "norm_key": "gdd_t_base",
        "norm_version": NORM_VERSION,
        "scope": {"cultivo": "hass"},
        "params": {"t_base": 10.0},
        "fuente": "Temperatura base orientativa del aguacate (calibrar por zona/cultivar).",
    },
    {
        "norm_key": "encalado",
        "norm_version": NORM_VERSION,
        "scope": {"cultivo": "hass"},
        "params": {"psa_objetivo_pct": 15.0, "lime_field_factor": 1.5},
        "fuente": "Saturación de Al objetivo + factor de campo orientativos (ajustar por suelo).",
    },
]

_DEFAULT_BY_KEY = {d["norm_key"]: d for d in DEFAULT_NORMS}


def _scope_is_subset(row_scope: dict | None, requested: dict) -> bool:
    """True si cada clave del scope de la fila coincide con lo pedido (scope vacío ⇒ aplica siempre)."""
    return all(requested.get(k) == v for k, v in (row_scope or {}).items())


def _best_match(rows: list[NormTable], requested: dict) -> NormTable | None:
    """De las filas vigentes, la de scope más específico que sea subconjunto de lo pedido."""
    candidates = [r for r in rows if _scope_is_subset(r.scope, requested)]
    candidates.sort(key=lambda r: len(r.scope or {}), reverse=True)
    return candidates[0] if candidates else None


def get_norm(
    session: Session | None, norm_key: str, *, scope: dict | None = None
) -> dict[str, Any]:
    """Norma vigente de `norm_key` para el `scope` dado, con FALLBACK al default del código.

    Devuelve {params, norm_version, fuente, source: 'db'|'default'}. Nunca lanza por BD: si la BD
    falla o no está sembrada, usa el default (que es el comportamiento actual de las calculadoras).
    """
    scope = scope or {}
    rows: list[NormTable] = []
    if session is not None:
        try:
            rows = list(
                session.scalars(
                    select(NormTable)
                    .where(NormTable.norm_key == norm_key, NormTable.vigente)
                    .order_by(NormTable.created_at.desc())
                )
            )
        except Exception as exc:  # noqa: BLE001 — BD no disponible ⇒ fallback al default
            log.warning("norm_db_read_failed", norm_key=norm_key, error=str(exc))
    best = _best_match(rows, scope)
    if best is not None:
        return {
            "params": best.params,
            "norm_version": best.norm_version,
            "fuente": best.fuente,
            "source": "db",
        }
    default = _DEFAULT_BY_KEY.get(norm_key)
    if default is None:
        raise KeyError(f"Norma desconocida: «{norm_key}».")
    return {
        "params": default["params"],
        "norm_version": default["norm_version"],
        "fuente": default["fuente"],
        "source": "default",
    }


def seed_norms(session: Session, *, now: datetime | None = None) -> int:
    """Siembra los DEFAULT en `norm_tables` (idempotente por norm_key+norm_version). Devuelve nº insertadas."""
    inserted = 0
    for spec in DEFAULT_NORMS:
        exists = session.scalar(
            select(NormTable).where(
                NormTable.norm_key == spec["norm_key"],
                NormTable.norm_version == spec["norm_version"],
            )
        )
        if exists is not None:
            continue
        session.add(
            NormTable(
                norm_key=spec["norm_key"],
                norm_version=spec["norm_version"],
                scope=spec["scope"],
                params=spec["params"],
                fuente=spec["fuente"],
                as_of=now,
                vigente=True,
            )
        )
        inserted += 1
    session.flush()
    log.info("norms_seeded", inserted=inserted, total=len(DEFAULT_NORMS))
    return inserted
