"""Conocimiento de dominio agronómico, libre de infraestructura.

Vive en la raíz del paquete (sin dependencias de BD ni proveedores) para que lo compartan
tanto la INGESTA (`ingestion.metadata`) como el DOMINIO de seguridad (`rag.guardrails`) sin
acoplarlos entre sí ni a `avorag.db` (ver `tests/test_decoupling.py`).
"""

from __future__ import annotations

# Ingredientes activos conocidos en aguacate (no exhaustivo; amplía con el registro PQUA).
# Sirve para detectar el i.a. en texto libre y para asociar dosis↔producto de forma
# determinista. Incluye insecticidas, acaricidas, fungicidas y biológicos comunes.
ACTIVE_INGREDIENTS: tuple[str, ...] = (
    "abamectina",
    "spinetoram",
    "spinosad",
    "imidacloprid",
    "thiamethoxam",
    "acetamiprid",
    "spirotetramat",
    "clorantraniliprol",
    "clorpirifos",
    "lambda-cialotrina",
    "lambdacialotrina",
    "cipermetrina",
    "deltametrina",
    "buprofezin",
    "pyriproxyfen",
    "piriproxifen",
    "azadiractina",
    "bacillus thuringiensis",
    "beauveria bassiana",
    "metarhizium",
    "trichoderma",
    "azufre",
    "aceite agricola",
    "fosetil",
    "fosetil-aluminio",
    "metalaxil",
    "mancozeb",
    "oxicloruro de cobre",
    "hidroxido de cobre",
    "propiconazol",
    "difenoconazol",
    "azoxistrobina",
    "fosfito",
)


def extract_active_ingredient(text: str) -> str | None:
    """Primer ingrediente activo conocido que aparece en el texto (o None)."""
    low = text.lower()
    return next((ia for ia in ACTIVE_INGREDIENTS if ia in low), None)


def active_ingredients_in(text: str) -> set[str]:
    """Todos los ingredientes activos conocidos presentes en el texto."""
    low = text.lower()
    return {ia for ia in ACTIVE_INGREDIENTS if ia in low}
