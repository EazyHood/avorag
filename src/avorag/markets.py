"""Normalización canónica del MERCADO de destino de exportación (una sola fuente de verdad).

Antes cada guardarraíl resolvía `export_market` a su manera y podían DIVERGIR en el mismo request:
- el guardarraíl de destino (offline, `rag/destino.py`) buscaba `data/destinos/destino_<market>.json`
  con el texto crudo en minúsculas → 'us'/'usa'/'estados_unidos' NO encontraban `destino_eeuu.json`
  y el guardarraíl quedaba apagado en silencio;
- el cruce online (`online/regulatory.py`, `rag/freshness.py`) aceptaba {'ue','eeuu','us','usa'}.

Aquí se centraliza el alias→clave canónica. La clave canónica coincide con el sufijo de los archivos
`destino_<clave>.json` y con los mercados de los feeds online. Módulo sin dependencias de `avorag`
(lo importan destino/integration/regulatory/freshness sin riesgo de ciclo).
"""

from __future__ import annotations

# Clave canónica por alias. Las claves canónicas ('ue','eeuu') se mapean a sí mismas. Un mercado
# DESCONOCIDO se devuelve tal cual (así un `destino_<nuevo>.json` futuro funciona sin tocar esto).
_MARKET_ALIASES: dict[str, str] = {
    "ue": "ue",
    "union europea": "ue",
    "eu": "ue",
    "europa": "ue",
    "eeuu": "eeuu",
    "ee uu": "eeuu",
    "us": "eeuu",
    "usa": "eeuu",
    "estados unidos": "eeuu",
}


def normalize_market(market: str | None) -> str | None:
    """Clave canónica del mercado ('ue' | 'eeuu' | …) o None si vacío.

    Insensible a mayúsculas/acentos-de-puntuación: colapsa espacios, trata '_' '-' '.' como separador y
    aplica los alias (us/usa/estados_unidos/EE.UU. → 'eeuu'). Un mercado no mapeado se devuelve
    normalizado (minúsculas, espacios colapsados) para que case con su `destino_<clave>.json`.

    OJO: esta función NO rechaza grafías desconocidas (las pasa tal cual, para que un
    `destino_<nuevo>.json` futuro funcione sin tocar el módulo). El rechazo de un destino SIN cobertura
    de datos vive en los BORDES (validador de `config.export_market`, validador de la API) y en el
    fail-closed del guardarraíl online; todos contra `SUPPORTED_MARKETS` / `is_supported_market`.
    """
    if not market:
        return None
    raw = str(market).strip().lower()
    for sep in ("_", "-", ".", ","):
        raw = raw.replace(sep, " ")
    raw = " ".join(raw.split())
    if not raw:
        return None
    return _MARKET_ALIASES.get(raw, raw)


# Mercados de destino con COBERTURA COMPLETA de datos: archivo `data/destinos/destino_<clave>.json`
# (guardarraíl OFFLINE) + feed de residuo en vivo (UE→LMR, EE.UU.→40 CFR 180; guardarraíl ONLINE). Es
# la ÚNICA fuente de verdad del "conjunto soportado": la consumen la validación de `config.export_market`,
# el borde de la API (`routes_chat`) y el fail-closed de `online/integration`. Añadir un destino nuevo =
# crear su `destino_<clave>.json` + feed y sumar su clave aquí (cambio DELIBERADO, no un alias silencioso).
# OJO: el mapeo feed↔mercado está acoplado a mano en `online/regulatory.py` y `rag/freshness.py` (ramas
# `market == "ue"` / `== "eeuu"`); un mercado nuevo obliga a añadir también allí su rama de feed (si no,
# el fail-closed de integration lo degradará a AMARILLO, pero su cobertura de residuo quedaría muda).
SUPPORTED_MARKETS: frozenset[str] = frozenset({"ue", "eeuu"})


def is_supported_market(market: str | None) -> bool:
    """True si `market` (en cualquier grafía/alias) normaliza a un mercado con cobertura completa."""
    return normalize_market(market) in SUPPORTED_MARKETS
