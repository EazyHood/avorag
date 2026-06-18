"""Orquestación del guardarraíl online (freshness + regulatorio) sobre un Answer."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from avorag.online import feeds, integration
from avorag.online.feeds import FakeIcaProvider, FeedSnapshot
from avorag.rag.freshness import FeedName, FeedSnapshotView
from avorag.rag.schemas import Answer, Semaforo

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


def _answer(text: str, sem: Semaforo = Semaforo.VERDE, *, abstained: bool = False) -> Answer:
    return Answer(question="q", text=text, semaforo=sem, abstained=abstained, warnings=[])


@pytest.fixture
def fresh_ica(monkeypatch):
    """ICA fresco con clorpirifos CANCELADO (monkeypatch del acceso a BD)."""
    f = FakeIcaProvider().fetch(now=NOW)
    snap = FeedSnapshot(
        feed_name=f.feed_name,
        as_of=NOW,
        ttl_seconds=7 * 24 * 3600,
        sha256=f.sha256,
        payload=f.payload,
    )

    def latest(_s, feed):
        return snap if FeedName.ICA.value in str(getattr(feed, "value", feed)) else None

    monkeypatch.setattr(feeds, "latest_snapshot", latest)
    monkeypatch.setattr(
        feeds,
        "latest_view",
        lambda _s, feed: (
            FeedSnapshotView(snap.feed_name, snap.as_of, snap.ttl_seconds)
            if FeedName.ICA.value in str(getattr(feed, "value", feed))
            else None
        ),
    )


# ── núcleo apply_online_safety ────────────────────────────────────────────────────────────────────
def test_clorpirifos_verde_pasa_a_rojo(fresh_ica):
    ans = _answer("Aplica clorpirifos 1 L/ha para la plaga.")
    integration.apply_online_safety(None, ans, now=NOW)
    assert ans.semaforo is Semaforo.ROJO and ans.warnings


def test_abstencion_no_se_toca(fresh_ica):
    ans = _answer("clorpirifos", abstained=True)
    integration.apply_online_safety(None, ans, now=NOW)
    assert ans.semaforo is Semaforo.VERDE  # intacto


def test_respuesta_no_fitosanitaria_no_se_toca(fresh_ica):
    ans = _answer("El aguacate Hass florece en dicogamia protogínica.")
    integration.apply_online_safety(None, ans, now=NOW)
    assert ans.semaforo is Semaforo.VERDE and ans.warnings == []


# ── flag ──────────────────────────────────────────────────────────────────────────────────────────
def test_flag_off_por_defecto(monkeypatch):
    monkeypatch.delenv("AVORAG_ONLINE_FEEDS", raising=False)
    assert integration.online_safety_enabled() is False


def test_flag_on(monkeypatch):
    monkeypatch.setenv("AVORAG_ONLINE_FEEDS", "1")
    assert integration.online_safety_enabled() is True


# ── apply_online_safety_for_tenant (entrada del pipeline) ─────────────────────────────────────────
def test_for_tenant_noop_si_flag_off(monkeypatch, fresh_ica):
    monkeypatch.delenv("AVORAG_ONLINE_FEEDS", raising=False)
    ans = _answer("clorpirifos 1 L/ha")
    integration.apply_online_safety_for_tenant("demo", ans, now=NOW)
    assert ans.semaforo is Semaforo.VERDE  # no se activó


def test_for_tenant_aplica_si_flag_on(monkeypatch, fresh_ica):
    monkeypatch.setenv("AVORAG_ONLINE_FEEDS", "1")

    @contextmanager
    def fake_session(tenant=None, **kw):
        yield object()

    monkeypatch.setattr("avorag.db.get_session", fake_session)
    ans = _answer("clorpirifos 1 L/ha")
    integration.apply_online_safety_for_tenant("demo", ans, now=NOW)
    assert ans.semaforo is Semaforo.ROJO


def test_for_tenant_failsafe_degrada_verde_a_amarillo(monkeypatch):
    monkeypatch.setenv("AVORAG_ONLINE_FEEDS", "1")

    def boom(*a, **k):
        raise RuntimeError("BD caída")

    monkeypatch.setattr("avorag.db.get_session", boom)
    ans = _answer("clorpirifos 1 L/ha")  # fitosanitaria → entra al try
    integration.apply_online_safety_for_tenant("demo", ans, now=NOW)
    # No rompe; degrada un verde no verificado a amarillo (Modo 2).
    assert ans.semaforo is Semaforo.AMARILLO and ans.warnings
