"""Conocimiento de dominio agronómico, sin dependencias de infraestructura."""

from __future__ import annotations

# i.a. registrados en aguacate (no exhaustivo; ampliar con PQUA).
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
