"""Puente visión → RAG.

Clasifica la foto y, con la etiqueta, le hace una pregunta al motor RAG existente para que
RESPONDA CITANDO fuentes y aplicando sus guardarraíles (semáforo, control de dosis). La capa de
visión nunca recomienda manejo por sí misma; solo identifica y formula la pregunta.
"""

from __future__ import annotations

from avorag.vision.labels import question_for
from avorag.vision.registry import get_vision_classifier
from avorag.vision.schemas import HealthDiagnosis, VisionDiagnosis, VisionResult


def classify_image(image: bytes, *, top_k: int = 3) -> VisionResult:
    """Solo identifica (sin pasar por el RAG)."""
    return get_vision_classifier().classify(image, top_k=top_k)


def _build_question(result: VisionResult, user_question: str | None) -> str | None:
    """Construye la pregunta agronómica que se le hará al RAG a partir de la identificación."""
    top = result.top
    if user_question and user_question.strip():
        uq = user_question.strip()
        if top and not result.requires_review:
            conf = round(top.confidence * 100)
            return (
                f"{uq}\n\n[Contexto visual: la foto sugiere «{top.label_es}» "
                f"({top.kind.value}, confianza {conf}%).]"
            )
        return uq  # identificación poco fiable → respondemos la pregunta libre, sin sesgar
    # Sin pregunta del usuario: solo formulamos algo si la identificación es fiable.
    if top and not result.requires_review:
        return question_for(top.label)
    return None  # identificación dudosa y sin pregunta → no inventar


def diagnose(
    image: bytes,
    *,
    question: str | None = None,
    tenant: str | None = None,
    country: str | None = None,
    soil_type: str | None = None,
    region: str | None = None,
    top_k: int = 3,
    run_rag: bool = True,
) -> VisionDiagnosis:
    """Identifica la foto y (si procede) obtiene la respuesta citada del RAG."""
    result = classify_image(image, top_k=top_k)

    built = _build_question(result, question)
    result.suggested_question = built

    # Sin nada que preguntar (identificación dudosa y sin pregunta del usuario): solo identificación.
    if not run_rag or built is None:
        return VisionDiagnosis(vision=result, answer=None)

    from avorag.rag import answer  # import perezoso (no acoplar avorag.db al importar visión)

    ans = answer(
        built,
        tenant=tenant,
        country=country,
        soil_type=soil_type,
        region=region,
    )
    return VisionDiagnosis(vision=result, answer=ans.model_dump())


def diagnose_health(
    image: bytes,
    *,
    tenant: str | None = None,
    country: str | None = None,
    soil_type: str | None = None,
    region: str | None = None,
    run_rag: bool = True,
) -> HealthDiagnosis:
    """Describe los síntomas de la foto con un VLM y, si hay algo, obtiene del RAG los candidatos de
    plaga/enfermedad y su manejo CITANDO la fuente. La visión SOLO describe; el RAG diagnostica."""
    from avorag.vision.describe import build_health_query
    from avorag.vision.registry import get_vision_describer

    report = get_vision_describer().describe(image)
    query = build_health_query(report)
    report.suggested_query = query
    if not run_rag or query is None:
        return HealthDiagnosis(report=report, answer=None)

    from avorag.rag import answer  # import perezoso (no acoplar avorag.db al importar visión)

    ans = answer(query, tenant=tenant, country=country, soil_type=soil_type, region=region)
    return HealthDiagnosis(report=report, answer=ans.model_dump())
