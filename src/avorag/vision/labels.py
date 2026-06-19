"""Taxonomía de etiquetas y su traducción a una pregunta agronómica para el motor RAG.

Cada clase del clasificador (madurez o patología) se mapea aquí a:
  - un nombre legible en español,
  - el tipo (madurez / patología),
  - la pregunta que se le hará al RAG para que responda CITANDO fuentes.

IMPORTANTE: las clases REALES las define el archivo `labels.json` que acompaña a cada modelo
entrenado (orden de salida del modelo). Este diccionario solo da el significado/legibilidad de
las claves canónicas. Añadir una clase = añadir su entrada aquí + en el `labels.json` del modelo;
no hace falta tocar el resto del código.

Las clases de patología son una TAXONOMÍA DE REFERENCIA (basada en plagas/enfermedades relevantes
del Hass de exportación). El modelo de patología se entrena con un dataset curado (ver
`docs/VISION.md`); mientras no exista, el slot queda preparado pero inactivo.
"""

from __future__ import annotations

from dataclasses import dataclass

from avorag.vision.schemas import VisionKind


@dataclass(frozen=True)
class LabelInfo:
    es: str  # nombre legible en español
    kind: VisionKind
    question: str  # pregunta agronómica para el RAG (que responde con fuentes + guardarraíles)


# --- Madurez del fruto (escala de 5 etapas, estilo dataset abierto de maduración Hass) ---
# Las claves siguen el orden verde → sobremaduro. El punto de corte de exportación lo decide el
# RAG citando los índices de madurez oficiales; aquí solo se nombra el estado observado.
_MADUREZ: dict[str, LabelInfo] = {
    "madurez_verde": LabelInfo(
        "Verde (sin madurar)",
        VisionKind.MADUREZ,
        "El fruto de aguacate Hass se ve verde/sin madurar. ¿Qué indican los índices de madurez "
        "y cuándo es el punto de corte de cosecha para exportación?",
    ),
    "madurez_pinton": LabelInfo(
        "Pintón (en transición)",
        VisionKind.MADUREZ,
        "El fruto de aguacate Hass se ve en transición de color (pintón). ¿Qué dicen los índices "
        "de madurez sobre el punto de corte para cosecha y exportación?",
    ),
    "madurez_maduro_inicial": LabelInfo(
        "Maduro inicial",
        VisionKind.MADUREZ,
        "El fruto de aguacate Hass se ve en maduración inicial. ¿Cuál es el punto de corte de "
        "cosecha para exportación según los índices de madurez del Hass?",
    ),
    "madurez_maduro_optimo": LabelInfo(
        "Maduro óptimo (listo)",
        VisionKind.MADUREZ,
        "El fruto de aguacate Hass se ve maduro/listo para consumo. ¿Qué implica esto para el "
        "punto de corte de cosecha y la ventana de exportación?",
    ),
    "madurez_sobremaduro": LabelInfo(
        "Sobremaduro",
        VisionKind.MADUREZ,
        "El fruto de aguacate Hass se ve sobremaduro. ¿Qué dice el manejo de poscosecha del Hass "
        "sobre el sobremadurado y el punto de corte para evitar pérdidas en exportación?",
    ),
}

# --- Patologías (taxonomía de referencia para Hass de exportación) ---
# El RAG aplica el guardarraíl de dosis y el semáforo sobre cualquier recomendación de manejo.
_PATOLOGIA: dict[str, LabelInfo] = {
    "sano": LabelInfo(
        "Sano (sin síntomas)",
        VisionKind.PATOLOGIA,
        "El tejido de aguacate Hass se ve sano. ¿Qué prácticas preventivas recomiendan las "
        "fuentes para mantener la sanidad del cultivo de cara a la exportación?",
    ),
    "trips": LabelInfo(
        "Trips (Thrips)",
        VisionKind.PATOLOGIA,
        "¿Cómo es el manejo integrado del trips (Thrips) en aguacate Hass, qué daño causa y por "
        "qué es crítico para la exportación?",
    ),
    "antracnosis": LabelInfo(
        "Antracnosis (Colletotrichum)",
        VisionKind.PATOLOGIA,
        "¿Cómo se maneja la antracnosis (Colletotrichum) en aguacate Hass y qué efecto tiene en "
        "la calidad de fruto para exportación?",
    ),
    "rona": LabelInfo(
        "Roña (Sphaceloma perseae)",
        VisionKind.PATOLOGIA,
        "¿Cómo se identifica y maneja la roña (Sphaceloma perseae) del aguacate Hass y cómo "
        "afecta la exportación del fruto?",
    ),
    "acaros": LabelInfo(
        "Ácaros",
        VisionKind.PATOLOGIA,
        "¿Cuál es el manejo integrado de ácaros en aguacate Hass y qué daño foliar/del fruto "
        "causan?",
    ),
    "monalonion": LabelInfo(
        "Monalonion (chinche del aguacate)",
        VisionKind.PATOLOGIA,
        "¿Cómo se maneja el Monalonion (chinche) en aguacate Hass y qué daño causa en el fruto "
        "para exportación?",
    ),
    "marceno": LabelInfo(
        "Cucarrón marceño",
        VisionKind.PATOLOGIA,
        "¿Cómo se maneja el cucarrón marceño en aguacate Hass y en qué época aparece?",
    ),
    "deficiencia_magnesio": LabelInfo(
        "Deficiencia de magnesio",
        VisionKind.PATOLOGIA,
        "Las hojas de aguacate Hass muestran síntomas compatibles con deficiencia de magnesio. "
        "¿Cómo se corrige la nutrición de magnesio según las fuentes?",
    ),
    "minador_hoja": LabelInfo(
        "Minador de la hoja",
        VisionKind.PATOLOGIA,
        "¿Cómo se maneja el minador de la hoja en aguacate Hass y qué umbral de daño es relevante?",
    ),
    "mancha_foliar": LabelInfo(
        "Mancha foliar",
        VisionKind.PATOLOGIA,
        "Las hojas de aguacate Hass presentan manchas foliares. ¿Qué causas posibles y qué "
        "manejo recomiendan las fuentes?",
    ),
}

LABELS: dict[str, LabelInfo] = {**_MADUREZ, **_PATOLOGIA}


def info_for(label: str) -> LabelInfo | None:
    """Metadatos de una clave canónica, o None si no está mapeada."""
    return LABELS.get(label)


def question_for(label: str) -> str | None:
    """Pregunta agronómica asociada a una clase (la que se le hará al RAG)."""
    li = LABELS.get(label)
    return li.question if li else None


def display_for(label: str) -> str:
    """Nombre legible en español; cae a la propia clave si no está mapeada."""
    li = LABELS.get(label)
    return li.es if li else label


def kind_for(label: str) -> VisionKind:
    """Tipo (madurez/patología) de una clase; DESCONOCIDO si no está mapeada."""
    li = LABELS.get(label)
    return li.kind if li else VisionKind.DESCONOCIDO
