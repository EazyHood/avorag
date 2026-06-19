"""Feedback del usuario: comentario por HASH (P-4), validación de motivo."""

from __future__ import annotations

import uuid

import pytest

from avorag.online.feedback import submit_feedback


class _FakeSession:
    def __init__(self):
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def test_comentario_se_guarda_hasheado():
    s = _FakeSession()
    fb = submit_feedback(
        s,
        tenant="demo",
        response_id=uuid.uuid4(),
        util=False,
        motivo="peligrosa",
        comentario="texto sensible",
    )
    assert fb.comentario_sha256 and fb.comentario_sha256 != "texto sensible"
    assert len(fb.comentario_sha256) == 64 and fb.util is False
    assert len(s.added) == 1


def test_sin_comentario_hash_none():
    fb = submit_feedback(_FakeSession(), tenant="demo", response_id=uuid.uuid4(), util=True)
    assert fb.comentario_sha256 is None


def test_motivo_invalido_lanza():
    with pytest.raises(ValueError, match="Motivo inválido"):
        submit_feedback(
            _FakeSession(), tenant="d", response_id=uuid.uuid4(), util=True, motivo="meh"
        )
