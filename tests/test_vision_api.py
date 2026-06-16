"""Tests de la API de visión (`/api/vision/*`) con TestClient y proveedores fake.

No requiere GPU, modelo entrenado, Ollama ni DB: se monkeypatchea el clasificador (fake) y, para
`/diagnose`, el puente al RAG. TestClient se usa SIN context manager para no disparar el lifespan
(warmup de modelos). Cubre: 503 deshabilitado, 200 con fake, validación 415/400/413 y forma de /diagnose.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from avorag.api import routes_vision as RV
from avorag.api.app import create_app
from avorag.config import Settings
from avorag.vision.base import DisabledVisionClassifier
from avorag.vision.fakes import FakeVisionClassifier
from avorag.vision.schemas import VisionDiagnosis, VisionKind, VisionPrediction, VisionResult

_IMG = b"\x89PNG\r\n\x1a\n" + b"0" * 64  # bytes cualquiera; el fake no decodifica la imagen


def _client() -> TestClient:
    return TestClient(create_app())  # sin `with`: no corre lifespan (no warmup de modelos)


def _enable_fake(monkeypatch) -> None:
    fake = FakeVisionClassifier()
    # `_ensure_enabled` usa get_vision_classifier; el endpoint /classify usa classify_image (que por
    # dentro va al registro real). Parcheamos ambos para que usen el fake de forma consistente.
    monkeypatch.setattr(RV, "get_vision_classifier", lambda: fake)
    monkeypatch.setattr(RV, "classify_image", lambda data, top_k=3: fake.classify(data, top_k=top_k))


def test_classify_503_cuando_deshabilitado(monkeypatch) -> None:
    monkeypatch.setattr(RV, "get_vision_classifier", lambda: DisabledVisionClassifier())
    r = _client().post("/api/vision/classify", files={"file": ("f.jpg", _IMG, "image/jpeg")})
    assert r.status_code == 503
    assert "visión" in r.json()["detail"].lower()


def test_classify_200_con_fake(monkeypatch) -> None:
    _enable_fake(monkeypatch)
    r = _client().post(
        "/api/vision/classify",
        files={"file": ("f.jpg", _IMG, "image/jpeg")},
        data={"top_k": "3"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["model_version"] == "fake-v1"
    assert j["top"] and len(j["predictions"]) == 3
    assert j["disclaimer"]  # siempre lleva el aviso "no es diagnóstico"


def test_classify_415_formato_no_soportado(monkeypatch) -> None:
    # La ruta acepta cualquier image/* (incl. HEIC); 415 es para NO-imágenes (PDF, texto, etc.).
    _enable_fake(monkeypatch)
    r = _client().post("/api/vision/classify", files={"file": ("f.pdf", _IMG, "application/pdf")})
    assert r.status_code == 415


def test_classify_400_imagen_vacia(monkeypatch) -> None:
    _enable_fake(monkeypatch)
    r = _client().post("/api/vision/classify", files={"file": ("f.jpg", b"", "image/jpeg")})
    assert r.status_code == 400


def test_classify_413_demasiado_grande(monkeypatch) -> None:
    _enable_fake(monkeypatch)
    monkeypatch.setattr(RV, "get_settings", lambda: Settings(vision_image_max_bytes=8))
    r = _client().post("/api/vision/classify", files={"file": ("f.jpg", _IMG, "image/jpeg")})
    assert r.status_code == 413


def test_diagnose_200_combina_vision_y_rag(monkeypatch) -> None:
    _enable_fake(monkeypatch)
    top = VisionPrediction(label="trips", label_es="Trips (Thrips)", kind=VisionKind.PATOLOGIA, confidence=0.8)
    canned = VisionDiagnosis(
        vision=VisionResult(kind=VisionKind.PATOLOGIA, top=top, predictions=[top], model_version="fake-v1"),
        answer={"text": "Manejo integrado del trips [1].", "semaforo": "verde"},
    )
    captured: dict = {}

    def _fake_diag(image, **kwargs):
        captured.update(kwargs)
        return canned

    monkeypatch.setattr(RV, "diagnose", _fake_diag)
    r = _client().post(
        "/api/vision/diagnose",
        files={"file": ("f.jpg", _IMG, "image/jpeg")},
        data={"question": "¿qué hago con esto?", "soil_type": "arcilloso"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["vision"]["top"]["label"] == "trips"
    assert j["answer"]["semaforo"] == "verde"
    # el endpoint reenvía la pregunta y el contexto de finca al puente RAG
    assert captured["question"] == "¿qué hago con esto?"
    assert captured["soil_type"] == "arcilloso"
