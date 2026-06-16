"""Precálculo de las preguntas por defecto (los chips de la UI) para servirlas al instante.

Se calculan una vez, se fijan en memoria (`pipeline._PINNED`, sin expiración) y se persisten en
disco. Al arrancar se cargan del disco (instantáneo); si la firma —modelo + versión de prompt +
versión de corpus— cambió, se recalculan en segundo plano. Mantener `DEFAULT_QUESTIONS` en
sincronía con los chips de `api/static/index.html`.
"""

from __future__ import annotations

import json
from pathlib import Path

from avorag.config import get_settings
from avorag.logging import get_logger
from avorag.rag import pipeline
from avorag.rag.prompt import PROMPT_VERSION
from avorag.rag.schemas import Answer

log = get_logger(__name__)

# Deben coincidir EXACTAMENTE con los chips de la UI. Se omite el saludo ("Hola"), que es
# conversacional y ya responde al instante sin pasar por el RAG.
DEFAULT_QUESTIONS = [
    "¿Cómo manejo los trips en aguacate Hass?",
    "¿Cuánto potasio aplicar en Hass durante el llenado del fruto?",
    "¿Puedo usar clorpirifos para exportar a la UE?",
    "¿Cómo siembro arroz?",
]

_STORE = Path(__file__).resolve().parents[3] / "data" / "cache" / "default_answers.json"
# Banco de las 500 preguntas de evaluación, precalculadas para servirse al instante.
_BANK = Path(__file__).resolve().parents[3] / "data" / "cache" / "answer_bank.jsonl"

# Súbelo al cambiar la lógica de guardarraíles/formato de respuesta, para invalidar la caché en disco.
_LOGIC_VERSION = "5"


def _signature() -> str:
    s = get_settings()
    return f"{s.llm_model}|{PROMPT_VERSION}|{pipeline._corpus_version()}|{_LOGIC_VERSION}"


def _key(question: str) -> str:
    s = get_settings()
    return pipeline._cache_key(question, s.default_tenant, s.country, None, None)


def load_from_disk() -> int:
    """Carga a la caché fijada las respuestas del disco cuya firma coincide con la actual.
    Instantáneo. Devuelve cuántas cargó (0 si no hay archivo o la firma cambió)."""
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if data.get("signature") != _signature():
        return 0
    n = 0
    for q, dump in data.get("entries", {}).items():
        try:
            pipeline.pin_answer(q, Answer.model_validate(dump))
            n += 1
        except Exception:  # noqa: BLE001
            continue
    if n:
        log.info("prewarm_loaded", count=n)
    return n


def load_answer_bank() -> int:
    """Fija el banco de respuestas de las 500 preguntas (solo las de firma vigente). Instantáneo.
    Sirve para que esas preguntas (y sus variantes exactas) respondan al instante."""
    if not _BANK.exists():
        return 0
    sig = _signature()
    n = 0
    for line in _BANK.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if rec.get("firma") != sig or "answer" not in rec:
                continue
            pipeline.pin_answer(rec["pregunta"], Answer.model_validate(rec["answer"]))
            n += 1
        except Exception:  # noqa: BLE001
            continue
    if n:
        log.info("answer_bank_loaded", count=n)
    return n


def _persist() -> None:
    with pipeline._CACHE_LOCK:
        answers = {
            q: pipeline._PINNED[_key(q)] for q in DEFAULT_QUESTIONS if _key(q) in pipeline._PINNED
        }
    if not answers:
        return
    try:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "signature": _signature(),
            "entries": {q: a.model_dump(mode="json") for q, a in answers.items()},
        }
        _STORE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("prewarm_persist_failed", error=str(exc))


def refresh(force: bool = False) -> None:
    """Calcula vía el pipeline las preguntas por defecto que falten, las fija y persiste. Pensado
    para correr en un hilo de fondo al arrancar. Idempotente y tolerante a fallo."""
    computed = False
    for q in DEFAULT_QUESTIONS:
        if not force and _key(q) in pipeline._PINNED:
            continue
        try:
            pipeline.pin_answer(q, pipeline.answer(q))
            computed = True
            log.info("prewarmed", question=q)
        except Exception as exc:  # noqa: BLE001
            log.warning("prewarm_failed", question=q, error=str(exc))
    if computed:
        _persist()
