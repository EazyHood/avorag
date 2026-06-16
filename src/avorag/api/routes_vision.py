"""Endpoints de visión: identificar madurez/patología desde una foto y (opcional) responder con RAG.

Frontera de seguridad: estos endpoints SOLO identifican y, si se pide, reenvían la pregunta al
motor RAG (`/api/vision/diagnose`), que es quien aplica semáforo, control de dosis y citación.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from avorag.api.auth import rate_limit, require_api_key
from avorag.config import get_settings
from avorag.vision import VisionDiagnosis, VisionResult
from avorag.vision.bridge import classify_image, diagnose
from avorag.vision.registry import get_vision_classifier

router = APIRouter(prefix="/api/vision", tags=["vision"])

_ALLOWED = ("image/jpeg", "image/png", "image/webp")


async def _read_image(file: UploadFile) -> bytes:
    s = get_settings()
    if file.content_type not in _ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Formato no soportado ({file.content_type}). Usa JPEG, PNG o WebP.",
        )
    # Lee como máximo el límite + 1 byte: NUNCA bufferiza un cuerpo enorme en memoria.
    data = await file.read(s.vision_image_max_bytes + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Imagen vacía.")
    if len(data) > s.vision_image_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Imagen demasiado grande (máx {s.vision_image_max_bytes // 1024} KB).",
        )
    return data


def _ensure_enabled() -> None:
    if not getattr(get_vision_classifier(), "available", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El módulo de visión no está configurado o no tiene modelo cargado.",
        )


@router.post("/classify", response_model=VisionResult)
async def classify(
    file: UploadFile = File(..., description="Foto de hoja o fruto (JPEG/PNG/WebP)."),
    top_k: int = Form(3),
    _auth: str = Depends(require_api_key),
    _rl: None = Depends(rate_limit),
) -> VisionResult:
    """Solo identifica: devuelve las clases más probables (sin pasar por el RAG)."""
    _ensure_enabled()
    data = await _read_image(file)
    try:
        return classify_image(data, top_k=max(1, min(top_k, 5)))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


@router.post("/diagnose", response_model=VisionDiagnosis)
async def diagnose_route(
    file: UploadFile = File(..., description="Foto de hoja o fruto (JPEG/PNG/WebP)."),
    question: str | None = Form(None),
    country: str | None = Form(None),
    soil_type: str | None = Form(None),
    region: str | None = Form(None),
    top_k: int = Form(3),
    auth_tenant: str = Depends(require_api_key),
    _rl: None = Depends(rate_limit),
) -> VisionDiagnosis:
    """Identifica la foto y obtiene la respuesta CITADA del motor RAG (con sus guardarraíles)."""
    _ensure_enabled()
    data = await _read_image(file)
    try:
        return diagnose(
            data,
            question=question,
            tenant=auth_tenant,
            country=country,
            soil_type=soil_type,
            region=region,
            top_k=max(1, min(top_k, 5)),
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
