"""Servicio HITL (P-2): cola de revisión + decisión firmada del agrónomo."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from avorag.online import hitl
from avorag.online.hitl import HitlReview
from avorag.rag.schemas import Semaforo

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


class _FakeSession:
    def __init__(self, *, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = scalars or []
        self.added: list = []

    def scalar(self, _stmt):
        return self._scalar

    def scalars(self, _stmt):
        return self._scalars

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def _query(**kw):
    base = {
        "id": uuid.uuid4(),
        "tenant": "demo",
        "question": "q",
        "answer": "a",
        "semaforo": "rojo",
        "review_status": "none",
        "reviewer_id": None,
        "corpus_version": "2026-06-17.1",
        "created_at": NOW,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── needs_hitl ────────────────────────────────────────────────────────────────────────────────────
def test_needs_hitl_solo_rojo():
    assert hitl.needs_hitl(Semaforo.ROJO) is True
    assert hitl.needs_hitl(Semaforo.AMARILLO) is False
    assert hitl.needs_hitl("verde") is False


# ── firma ───────────────────────────────────────────────────────────────────────────────────────
def test_firma_determinista_y_sensible():
    qid = uuid.uuid4()
    a = hitl.decision_signature(qid, "approved", "agro1", None)
    assert a == hitl.decision_signature(qid, "approved", "agro1", None)
    assert a != hitl.decision_signature(qid, "rejected", "agro1", None)


# ── cola ────────────────────────────────────────────────────────────────────────────────────────
def test_pending_devuelve_la_cola():
    rows = [_query(), _query()]
    out = hitl.pending_for_review(_FakeSession(scalars=rows), "demo")
    assert out == rows


def test_review_summary_expone_metadatos():
    s = hitl.review_summary(_query(question="¿clorpirifos?"))
    assert s["semaforo"] == "rojo" and s["question"] == "¿clorpirifos?" and "query_id" in s


# ── decisión ──────────────────────────────────────────────────────────────────────────────────────
def test_submit_decision_crea_review_y_actualiza_query():
    q = _query()
    s = _FakeSession(scalar=q)
    review = hitl.submit_decision(
        s, query_id=q.id, reviewer_id="agro1", decision="approved", now=NOW
    )
    assert isinstance(review, HitlReview)
    assert review.decision == "approved" and review.signature
    assert q.review_status == "approved" and q.reviewer_id == "agro1"
    assert len(s.added) == 1


def test_submit_decision_invalida_lanza_valueerror():
    q = _query()
    with pytest.raises(ValueError, match="Decisión inválida"):
        hitl.submit_decision(_FakeSession(scalar=q), query_id=q.id, reviewer_id="a", decision="meh")


def test_submit_decision_query_inexistente_lanza_lookuperror():
    with pytest.raises(LookupError):
        hitl.submit_decision(
            _FakeSession(scalar=None), query_id=uuid.uuid4(), reviewer_id="a", decision="approved"
        )
