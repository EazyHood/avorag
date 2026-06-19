"""Gate de rol para HITL: allowlist de revisores por entorno."""

from __future__ import annotations

from avorag.online import roles


def test_sin_allowlist_permite(monkeypatch):
    monkeypatch.delenv("AVORAG_HITL_REVIEWERS", raising=False)
    assert roles.is_reviewer("cualquiera") is True
    assert roles.reviewers() == set()


def test_con_allowlist_restringe(monkeypatch):
    monkeypatch.setenv("AVORAG_HITL_REVIEWERS", " agro1 , agro2 ")
    assert roles.reviewers() == {"agro1", "agro2"}
    assert roles.is_reviewer("agro1") is True
    assert roles.is_reviewer("intruso") is False
