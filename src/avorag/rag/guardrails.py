"""Guardarraíles de seguridad: dosis rastreable, categoría toxicológica, juez de
fidelidad, clasificación de intención y decisión de semáforo. El objetivo es
minimizar errores de alta severidad (NO se garantiza cero — por eso existe el HITL)."""

from __future__ import annotations

import json
import re
import unicodedata

from avorag.logging import get_logger
from avorag.providers import get_llm_provider
from avorag.rag.schemas import AbstentionType, Semaforo
from avorag.retrieval import ScoredChunk

log = get_logger(__name__)

# Unidades agronómicas típicas de dosis.
_UNITS = r"(?:%|ppm|cc\s?/\s?l|cc|ml|l\s?/\s?ha|kg\s?/\s?ha|g\s?/\s?l|g\s?/\s?ha|kg|gr|g|l|litros|cm3|mm)"
_DOSE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s?" + _UNITS + r"\b", re.IGNORECASE)


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


def extract_dose_numbers(text: str) -> list[str]:
    """Devuelve los valores numéricos (normalizados, con punto decimal) de cada dosis."""
    return [m.group(1).replace(",", ".") for m in _DOSE_RE.finditer(text)]


# Normalización de unidades para comparar dosis EQUIVALENTES (5 kg/ha == 5000 g/ha).
_DOSE_PAIR_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s?(" + _UNITS + r")\b", re.IGNORECASE)
_UNIT_FACTORS: dict[str, tuple[str, float]] = {
    "%": ("pct", 1.0), "ppm": ("ppm", 1.0), "mm": ("mm", 1.0),
    "g": ("mass", 1.0), "gr": ("mass", 1.0), "kg": ("mass", 1000.0),
    "ml": ("vol", 1.0), "cc": ("vol", 1.0), "cm3": ("vol", 1.0),
    "l": ("vol", 1000.0), "litros": ("vol", 1000.0),
    "g/ha": ("mass_ha", 1.0), "kg/ha": ("mass_ha", 1000.0),
    "l/ha": ("vol_ha", 1000.0),
    "g/l": ("conc_g_l", 1.0), "cc/l": ("conc_ml_l", 1.0),
}


def _canonical_doses(text: str) -> set[tuple[str, float]]:
    """Extrae dosis como (dimensión, valor en unidad base), normalizando equivalencias."""
    out: set[tuple[str, float]] = set()
    for m in _DOSE_PAIR_RE.finditer(text):
        value = float(m.group(1).replace(",", "."))
        unit = re.sub(r"\s+", "", m.group(2).lower())
        dim, factor = _UNIT_FACTORS.get(unit, (unit, 1.0))
        out.add((dim, round(value * factor, 6)))
    return out


def doses_grounded(answer_text: str, contexts_text: str) -> tuple[bool, list[str]]:
    """Cada dosis de la respuesta debe estar respaldada por una dosis EQUIVALENTE en el
    contexto (misma cantidad física aunque cambie la unidad: 5 kg/ha == 5000 g/ha). Un
    número suelto en el contexto (p.ej. '100 hectáreas') no respalda una dosis."""
    ctx = _canonical_doses(contexts_text)
    unsupported: list[str] = []
    for m in _DOSE_PAIR_RE.finditer(answer_text):
        value = float(m.group(1).replace(",", "."))
        unit = re.sub(r"\s+", "", m.group(2).lower())
        dim, factor = _UNIT_FACTORS.get(unit, (unit, 1.0))
        if (dim, round(value * factor, 6)) not in ctx:
            unsupported.append(m.group(1).replace(",", "."))
    return (len(unsupported) == 0, unsupported)


def cited_categoria_toxicologica(chunks: list[ScoredChunk]) -> set[str]:
    """Categorías toxicológicas presentes en los fragmentos usados."""
    return {str(sc.chunk.meta.get("categoria_toxicologica", "N/A")).upper() for sc in chunks}


# --- Clasificación de intención (etiqueta la abstención; backstop del retrieval/LLM) ---
_HASS_TERMS = {"aguacate", "hass", "palta", "palto"}
_OTHER_CROPS = {
    "tomate",
    "papa",
    "patata",
    "maiz",
    "arroz",
    "cafe",
    "cacao",
    "cana",
    "banano",
    "platano",
    "fresa",
    "cebolla",
    "frijol",
    "trigo",
    "soya",
    "soja",
    "mango",
    "citrico",
    "naranja",
    "pina",
    "yuca",
    "sorgo",
    "algodon",
    "uva",
    "lechuga",
}
_AGRO_SIGNAL = {
    "cultivo",
    "planta",
    "arbol",
    "hoja",
    "fruto",
    "flor",
    "raiz",
    "plaga",
    "enfermedad",
    "hongo",
    "riego",
    "agua",
    "fertiliz",
    "abono",
    "nutricion",
    "suelo",
    "dosis",
    "aplicar",
    "fumig",
    "poda",
    "cosecha",
    "siembra",
    "semilla",
    "trips",
    "acaro",
    "mancha",
    "pudricion",
    "carencia",
    "ica",
    "pesticida",
    "fitosanitario",
    "rendimiento",
    "produccion",
    "finca",
}


def is_other_crop(question: str) -> bool:
    """True si la pregunta es claramente sobre OTRO cultivo y no menciona aguacate Hass."""
    q = _strip_accents(question)
    if any(h in q for h in _HASS_TERMS):
        return False
    return any(re.search(rf"\b{c}", q) for c in _OTHER_CROPS)


def has_agronomic_signal(question: str) -> bool:
    """True si la pregunta contiene alguna señal agronómica reconocible."""
    q = _strip_accents(question)
    return any(t in q for t in (_AGRO_SIGNAL | _HASS_TERMS | _OTHER_CROPS))


def classify_intent(question: str) -> AbstentionType | None:
    """Pre-clasificación barata. OUT_OF_COLLECTION corta antes de recuperar (cultivo ajeno).
    Devuelve None si se debe proceder con la recuperación normal."""
    if is_other_crop(question):
        return AbstentionType.OUT_OF_COLLECTION
    return None


_JUDGE_SYSTEM = (
    "Eres un evaluador estricto de fidelidad. Dado un CONTEXTO y una RESPUESTA, "
    "determinas si TODA afirmación de la respuesta está respaldada por el contexto. "
    'Devuelves SOLO un JSON: {"faithful": true|false, "score": 0.0-1.0, '
    '"unsupported": ["..."]}.'
)


def faithfulness_judge(
    question: str, answer: str, contexts_text: str
) -> tuple[float | None, list[str]]:
    """LLM-as-judge de fidelidad. Devuelve (score 0..1, no-respaldadas).
    Si el juez FALLA, devuelve (None, []) — el pipeline lo trata como AMARILLO,
    NUNCA como fidelidad perfecta (fail-safe, no fail-open)."""
    try:
        llm = get_llm_provider()
        raw = llm.complete(
            _JUDGE_SYSTEM,
            f"CONTEXTO:\n{contexts_text}\n\nPREGUNTA:\n{question}\n\nRESPUESTA:\n{answer}\n\nJSON:",
            temperature=0.0,
            max_tokens=300,
        )
        data = _extract_json(raw)
        if not data:
            return None, []
        score = float(data.get("score", 1.0 if data.get("faithful") else 0.0))
        return max(0.0, min(1.0, score)), list(data.get("unsupported", []))
    except Exception as exc:
        log.warning("faithfulness_judge_failed", error=str(exc))
        return None, []


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def decide_semaforo(
    *,
    doses_ok: bool,
    cat_tox: set[str],
    faithfulness: float | None,
    has_citations: bool = True,
    judge_failed: bool = False,
    faithfulness_threshold: float = 0.6,
) -> tuple[Semaforo, str]:
    """Combina las señales en un semáforo con su razón. Orden: rojo > amarillo > verde."""
    if not doses_ok:
        return (
            Semaforo.ROJO,
            "Dosis no rastreable a una etiqueta citada: requiere validación de un agrónomo.",
        )
    if {"I", "II"} & cat_tox:
        return (
            Semaforo.ROJO,
            "Producto de categoría toxicológica I/II: requiere receta firmada por profesional.",
        )
    if judge_failed:
        return Semaforo.AMARILLO, "No se pudo verificar la fidelidad (juez no disponible): revisar."
    if faithfulness is not None and faithfulness < faithfulness_threshold:
        return Semaforo.AMARILLO, "Fidelidad por debajo del umbral: revisar antes de actuar."
    if not has_citations:
        return Semaforo.AMARILLO, "Respuesta sin citas de fuente: requiere verificación."
    return Semaforo.VERDE, "Respuesta respaldada por las fuentes citadas."
