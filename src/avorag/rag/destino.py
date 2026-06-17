"""Guardarraíl de autorización por PAÍS DE DESTINO de exportación.

Resuelve la objeción #1 del comprador exportador: "si tu app me hace aplicar un producto que en mi
mercado de destino (UE/EE.UU./…) no está autorizado, pierdo el contenedor por LMR". El guardarraíl de
prohibidos existente (`guardrails.banned_ingredients_in_answer`) mira el país de PRODUCCIÓN (registro
ICA en Colombia); este mira el país de DESTINO.

Funciona como un mínimo de seguridad: si la respuesta menciona un ingrediente activo NO APROBADO en el
mercado de destino configurado, se fuerza ROJO (no recomendable para exportar allí). Los activos con
LMR muy estricto generan un AVISO (amarillo), no un bloqueo.

Datos en `data/destinos/destino_<mercado>.json`. El mercado se configura en `.env` (EXPORT_MARKET=ue);
vacío = guardarraíl apagado. Los archivos son SEMILLAS incompletas (ver su campo `_AVISO`): la ausencia
de un activo NO implica que esté autorizado. Para producción, completar contra la base oficial del destino.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

from avorag.agro_terms import commercial_actives_in
from avorag.config import get_settings
from avorag.logging import get_logger

log = get_logger(__name__)

_DESTINOS_DIR = Path(__file__).resolve().parents[3] / "data" / "destinos"


def _norm(text: str) -> str:
    """Minúsculas sin acentos, para comparar nombres de activos de forma robusta."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@lru_cache
def _load_market(market: str) -> dict:
    """Carga el JSON del mercado de destino (cacheado). {} si no existe o falla."""
    if not market:
        return {}
    path = _DESTINOS_DIR / f"destino_{market.lower()}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.warning("destino_market_unknown", market=market, path=str(path))
        return {}
    except Exception as exc:  # noqa: BLE001 — datos malformados no deben tumbar el RAG
        log.warning("destino_market_load_failed", market=market, error=str(exc))
        return {}


def available_markets() -> list[str]:
    """Mercados de destino con archivo de datos disponible."""
    if not _DESTINOS_DIR.exists():
        return []
    return sorted(p.stem.removeprefix("destino_") for p in _DESTINOS_DIR.glob("destino_*.json"))


def _matches(text: str, items: list[dict]) -> list[dict]:
    """Casa por nombre QUÍMICO (subcadena) o por MARCA comercial resuelta a su i.a. (Lorsban→
    clorpirifos, Movento→spirotetramat…), para que un producto citado por su marca no evada el destino."""
    low = _norm(text)
    brand_actives = {_norm(a) for a in commercial_actives_in(text)}
    out: list[dict] = []
    for it in items:
        ia = _norm(str(it.get("ingrediente_activo", "")))
        if ia and (ia in low or ia in brand_actives):
            out.append(it)
    return out


def _resolve_market(market: str | None) -> str:
    return (market if market is not None else get_settings().export_market).lower()


def unauthorized_for_destination(text: str, market: str | None = None) -> list[str]:
    """Activos NO APROBADOS en el mercado de destino mencionados en `text` (→ ROJO).

    `market` None ⇒ usa EXPORT_MARKET del .env; si está vacío, devuelve [] (guardarraíl apagado).
    """
    m = _resolve_market(market)
    data = _load_market(m)
    if not data:
        return []
    nombre = data.get("nombre", m.upper())
    hits = _matches(text, data.get("no_autorizados", []))
    return [
        f"{it['ingrediente_activo']} (no autorizado en {nombre}: {it.get('motivo', '')})"
        for it in hits
    ][:3]


def strict_lmr_for_destination(text: str, market: str | None = None) -> list[str]:
    """Activos con LMR muy estricto en el destino (→ AVISO amarillo, no bloqueo)."""
    m = _resolve_market(market)
    data = _load_market(m)
    if not data:
        return []
    nombre = data.get("nombre", m.upper())
    hits = _matches(text, data.get("lmr_estricto", []))
    return [f"{it['ingrediente_activo']} (LMR estricto en {nombre}): {it.get('nota', '')}" for it in hits][:3]


def market_name(market: str | None = None) -> str:
    m = _resolve_market(market)
    return _load_market(m).get("nombre", m.upper()) if m else ""
