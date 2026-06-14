"""Tests del prompt: contexto de finca (suelo/región) y regla de suelo (puro)."""

from avorag.rag.prompt import build_system_prompt, build_user_prompt


def test_user_prompt_includes_farm_context():
    p = build_user_prompt("¿Cómo fertilizo?", [], farm_context="suelo arcilloso, región Quindío")
    assert "CONTEXTO DE LA FINCA: suelo arcilloso, región Quindío" in p


def test_user_prompt_without_farm_context():
    p = build_user_prompt("¿Cómo fertilizo?", [])
    assert "CONTEXTO DE LA FINCA" not in p


def test_system_prompt_has_soil_rule():
    s = build_system_prompt("CO")
    assert "TIPO DE SUELO" in s
    assert "arenoso" in s
