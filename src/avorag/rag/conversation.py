"""Capa conversacional: saludos, agradecimientos y meta-preguntas reciben una respuesta
cercana, sin pasar por recuperación ni guardarraíles."""

from __future__ import annotations

import re

from avorag.providers import get_llm_provider
from avorag.rag.guardrails import _strip_accents, has_agronomic_signal

_GREETING = re.compile(
    r"\b(hola|holi|buenas|buenos dias|buenas tardes|buenas noches|hey|que tal|saludos|"
    r"que mas|quiubo|epa|holaa+)\b"
)
_THANKS = re.compile(r"\b(gracias|te agradezco|genial|perfecto|excelente|de una|listo)\b")
_META = re.compile(
    r"(que (puedes|sabes) hacer|para que sirves|quien eres|que eres|como funcionas|"
    r"en que (me )?puedes ayudar|^ayuda$|que haces|como te llamas|tu nombre)"
)
_SMALLTALK = re.compile(r"(como estas|como te va|todo bien|que cuentas|como vas|que onda)")
_BYE = re.compile(r"\b(adios|chao|hasta luego|nos vemos|bye|hasta pronto)\b")

# Orden de prioridad al clasificar.
_PATTERNS = [
    ("meta", _META),
    ("smalltalk", _SMALLTALK),
    ("thanks", _THANKS),
    ("bye", _BYE),
    ("greeting", _GREETING),
]
_STOP = {
    "de",
    "la",
    "el",
    "un",
    "una",
    "y",
    "o",
    "por",
    "con",
    "me",
    "te",
    "mi",
    "tu",
    "si",
    "es",
    "las",
    "los",
    "que",
    "a",
    "en",
    "al",
    "del",
    "lo",
    "su",
}


def classify_conversational(text: str) -> str | None:
    """Devuelve el tipo de mensaje conversacional, o None si es una consulta técnica.

    Conservador: solo clasifica como charla si, tras quitar las frases de cortesía, casi no queda
    contenido. Así 'hola, ¿cómo controlo la antracnosis?' va al RAG, pero 'hola' no.
    """
    if has_agronomic_signal(text):
        return None
    t = _strip_accents(text)
    if len(t) > 200:
        return None
    matched: str | None = None
    remainder = t
    for name, pat in _PATTERNS:
        if pat.search(remainder):
            matched = matched or name
            remainder = pat.sub(" ", remainder)
    if matched is None:
        return None
    leftover = [w for w in re.sub(r"[^\w\s]", " ", remainder).split() if w not in _STOP]
    return matched if len(leftover) <= 1 else None


_CONV_SYSTEM = (
    "Eres AvoRAG, un asistente cordial y cercano especializado en el cultivo del aguacate Hass de "
    "exportación. Responde BREVE (1 a 3 frases), cálido y natural, en español, al mensaje del "
    "usuario. Si saluda, saluda de vuelta y preséntate en una frase. Si pregunta qué puedes hacer, "
    "menciona que ayudas con plagas, enfermedades, fertilización, dosis, carencia y manejo del "
    "aguacate Hass, citando fuentes oficiales (ICA, Agrosavia). Invita con naturalidad a hacer una "
    "consulta. NUNCA des datos técnicos, dosis ni cifras aquí: esto es solo conversación."
)

_FALLBACK = {
    "greeting": (
        "¡Hola! 👋 Soy AvoRAG, tu asistente para el aguacate Hass. ¿En qué te ayudo hoy? Puedo "
        "orientarte sobre plagas, enfermedades, fertilización o dosis, siempre citando fuentes oficiales."
    ),
    "meta": (
        "Soy AvoRAG, un asistente para el cultivo de aguacate Hass de exportación. Te ayudo con "
        "plagas, enfermedades, fertilización, dosis y periodos de carencia, citando fuentes oficiales "
        "(ICA, Agrosavia) y avisándote cuando algo necesita a un agrónomo. ¿Sobre qué quieres preguntar?"
    ),
    "thanks": "¡Con gusto! Si te surge otra duda sobre tu cultivo de aguacate, aquí estoy. 🌱",
    "smalltalk": (
        "¡Todo bien por aquí, gracias! 🌱 Soy AvoRAG, listo para ayudarte con tu aguacate Hass. "
        "¿En qué te echo una mano?"
    ),
    "bye": "¡Hasta pronto! Cualquier duda sobre tu cultivo de aguacate, aquí estaré. 🥑",
}


def conversational_reply(text: str, conv_type: str) -> str:
    """Respuesta conversacional natural (LLM con persona cálida); cae a una plantilla si falla."""
    try:
        out = (
            get_llm_provider().complete(_CONV_SYSTEM, text, temperature=0.7, max_tokens=160).strip()
        )
        if out:
            return out
    except Exception:
        pass
    return _FALLBACK.get(conv_type, _FALLBACK["greeting"])
