"""Tests de clasificación de intención (puro, sin DB ni LLM)."""

from avorag.rag.guardrails import classify_intent, has_agronomic_signal, is_other_crop
from avorag.rag.schemas import AbstentionType


def test_other_crop_detected():
    assert is_other_crop("¿Cómo siembro arroz en zona inundable?") is True
    assert is_other_crop("¿Y el manejo del cacao en mi finca?") is True


def test_hass_question_is_not_other_crop():
    assert is_other_crop("¿Cómo manejo los trips en aguacate Hass?") is False
    # Aunque mencione otro cultivo, si compara con Hass no se descarta.
    assert is_other_crop("¿El Hass se asocia bien con café?") is False


def test_classify_intent_other_crop_is_out_of_collection():
    assert classify_intent("¿Cómo cultivo tomate?") == AbstentionType.OUT_OF_COLLECTION


def test_classify_intent_hass_proceeds():
    assert classify_intent("¿Qué hago con la mancha negra del aguacate?") is None


def test_agronomic_signal():
    assert has_agronomic_signal("¿Cómo controlo una plaga en el cultivo?") is True
    assert has_agronomic_signal("¿Qué equipo ganó el partido ayer?") is False


def test_accent_insensitive():
    # Sin tildes debe funcionar igual.
    assert is_other_crop("como cultivo platano") is True
