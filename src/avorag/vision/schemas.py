"""Esquemas del módulo de visión.

Frontera de diseño: la visión SOLO identifica (madurez o patología) a partir de una foto.
NO recomienda dosis ni tratamiento — eso lo hace el motor RAG (`avorag.rag.answer`) con sus
guardarraíles (semáforo, control de dosis, citación a fuente). Ver `docs/VISION.md`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class VisionKind(StrEnum):
    """Qué tipo de cosa identifica el modelo."""

    MADUREZ = "madurez"  # punto de maduración del fruto
    PATOLOGIA = "patologia"  # plaga o enfermedad (hoja/fruto)
    DESCONOCIDO = "desconocido"  # el modelo no está seguro / clase no mapeada


class VisionPrediction(BaseModel):
    """Una clase candidata con su probabilidad."""

    label: str  # clave canónica (p.ej. "trips", "madurez_maduro_2")
    label_es: str  # nombre legible en español
    kind: VisionKind = VisionKind.DESCONOCIDO
    confidence: float = Field(..., ge=0.0, le=1.0)


class VisionResult(BaseModel):
    """Salida del clasificador. Es una IDENTIFICACIÓN, no un diagnóstico ni una recomendación."""

    kind: VisionKind = VisionKind.DESCONOCIDO
    top: VisionPrediction | None = None  # mejor candidata (None si nada supera el umbral)
    predictions: list[VisionPrediction] = Field(default_factory=list)  # top-k ordenado desc
    requires_review: bool = False  # baja confianza → pedir mejor foto / revisar con agrónomo
    model_version: str = ""  # trazabilidad del modelo que produjo esto
    suggested_question: str | None = None  # pregunta agronómica derivada para el RAG
    disclaimer: str = (
        "Identificación visual asistida por IA: es una ayuda, NO un diagnóstico definitivo. "
        "Confírmalo con tu agrónomo antes de actuar."
    )


class VisionDiagnosis(BaseModel):
    """Resultado combinado: lo que la foto identificó + la respuesta citada del motor RAG."""

    vision: VisionResult
    # `answer` es un avorag.rag.schemas.Answer; se anida como dict para no acoplar capas aquí.
    answer: dict | None = None
