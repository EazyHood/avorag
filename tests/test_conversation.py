"""La capa conversacional detecta charla y deja pasar las consultas técnicas al RAG."""

from __future__ import annotations

import pytest

from avorag.rag.conversation import classify_conversational


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hola", "greeting"),
        ("Buenas tardes!", "greeting"),
        ("hey, qué tal", "greeting"),
        ("muchas gracias", "thanks"),
        ("¿qué puedes hacer?", "meta"),
        ("¿quién eres?", "meta"),
        ("¿cómo estás?", "smalltalk"),
        ("adiós", "bye"),
    ],
)
def test_detects_conversational(text: str, expected: str) -> None:
    assert classify_conversational(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "¿cómo manejo el trips en aguacate Hass?",
        "¿qué dosis de abamectina uso?",
        "hola, ¿cómo controlo la antracnosis?",
        "buenas, necesito un plan de fertilización",
    ],
)
def test_technical_questions_are_not_conversational(text: str) -> None:
    assert classify_conversational(text) is None
