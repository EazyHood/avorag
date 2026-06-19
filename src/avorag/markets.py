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
