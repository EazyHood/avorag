"""Tests del extractor de preguntas de seguimiento."""

from avorag.rag.pipeline import _split_followups


def test_split_followups_extracts():
    text = (
        "Respuesta detallada y explicativa.\n\n"
        "SEGUIMIENTO:\n- ¿Quieres saber la dosis por etapa?\n- ¿Te explico el riego en arenoso?"
    )
    body, fu = _split_followups(text)
    assert "SEGUIMIENTO" not in body
    assert body.strip() == "Respuesta detallada y explicativa."
    assert len(fu) == 2
    assert all(q.endswith("?") for q in fu)
    assert not fu[0].startswith("-")


def test_split_followups_none():
    body, fu = _split_followups("Solo una respuesta, sin sección de seguimiento.")
    assert fu == []
    assert body == "Solo una respuesta, sin sección de seguimiento."
