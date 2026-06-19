"""Cruce regulatorio en vivo: los feeds fuerzan ROJO/AMARILLO con dato fresco."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from avorag.online import feeds, regulatory
from avorag.online.feeds import (
    FakeIcaProvider,
    FakeLmrUeProvider,
    FakeTolEeuuProvider,
    FeedSnapshot,
)
from avorag.rag.freshness import FeedName, FeedSnapshotView
from avorag.rag.schemas import Semaforo

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
TTL = 7 * 24 * 3600


def _snap(provider, *, as_of=NOW):
    f = provider.fetch(now=NOW)
    return FeedSnapshot(
        feed_name=f.feed_name, as_of=as_of, ttl_seconds=TTL, sha256=f.sha256, payload=f.payload
    )


@pytest.fixture
def patch_feeds(monkeypatch):
    """Sustituye el acceso a BD por snapshots en memoria (frescos)."""
    snaps = {
        FeedName.ICA.value: _snap(FakeIcaProvider()),
        FeedName.LMR_UE.value: _snap(FakeLmrUeProvider()),
        FeedName.TOL_EEUU.value: _snap(FakeTolEeuuProvider()),
    }

    def fake_latest(_session, feed):
        name = feed.value if isinstance(feed, FeedName) else str(feed)
        return snaps.get(name)

    def fake_view(_session, feed):
        s = fake_latest(_session, feed)
        return None if s is None else FeedSnapshotView(s.feed_name, s.as_of, s.ttl_seconds)

    monkeypatch.setattr(feeds, "latest_snapshot", fake_latest)
    monkeypatch.setattr(feeds, "latest_view", fake_view)
    return snaps


def _sevs(findings, feed):
    return {f.severity for f in findings if f.feed == feed}


# ── Hallazgos en vivo ────────────────────────────────────────────────────────────────────────────
def test_clorpirifos_ica_cancelado_es_rojo(patch_feeds):
    fs = regulatory.live_regulatory_findings(None, "Aplica clorpirifos 1 L/ha.", now=NOW)
    assert Semaforo.ROJO in _sevs(fs, FeedName.ICA.value)


def test_clorpirifos_no_aprobado_ue_es_rojo(patch_feeds):
    fs = regulatory.live_regulatory_findings(
        None, "clorpirifos para exportar", export_market="ue", now=NOW
    )
    assert Semaforo.ROJO in _sevs(fs, FeedName.LMR_UE.value)


def test_clorpirifos_sin_tolerancia_eeuu_es_rojo(patch_feeds):
    fs = regulatory.live_regulatory_findings(None, "clorpirifos", export_market="eeuu", now=NOW)
    assert Semaforo.ROJO in _sevs(fs, FeedName.TOL_EEUU.value)


def test_abamectina_vigente_y_aprobada_no_da_rojo(patch_feeds):
    fs = regulatory.live_regulatory_findings(
        None, "abamectina 2,5 cc/L", export_market="ue", now=NOW
    )
    assert all(f.severity is not Semaforo.ROJO for f in fs)


def test_ica_stale_degrada_a_amarillo(monkeypatch):
    viejo = _snap(FakeIcaProvider(), as_of=NOW - timedelta(days=30))
    monkeypatch.setattr(
        feeds, "latest_snapshot", lambda s, f: viejo if FeedName.ICA.value in str(f) else None
    )
    monkeypatch.setattr(
        feeds,
        "latest_view",
        lambda s, f: (
            FeedSnapshotView(viejo.feed_name, viejo.as_of, viejo.ttl_seconds)
            if FeedName.ICA.value in str(f)
            else None
        ),
    )
    fs = regulatory.live_regulatory_findings(None, "abamectina 2,5 cc/L", now=NOW)
    assert any(x.severity is Semaforo.AMARILLO for x in fs)


def test_respuesta_sin_activos_no_da_hallazgos(patch_feeds):
    assert regulatory.live_regulatory_findings(None, "El Hass florece en dicogamia.", now=NOW) == []


# ── apply_regulatory_findings (invariante de no-escalado) ────────────────────────────────────────
def _rojo():
    return [
        regulatory.RegulatoryFinding(Semaforo.ROJO, "ica_simplifica", "clorpirifos", "cancelado")
    ]


def _amar():
    return [regulatory.RegulatoryFinding(Semaforo.AMARILLO, "lmr_ue", "x", "verificar")]


def test_apply_rojo_sube_verde_a_rojo():
    sem, reason, av = regulatory.apply_regulatory_findings(Semaforo.VERDE, "ok", _rojo())
    assert sem is Semaforo.ROJO and av


def test_apply_amarillo_sube_verde_a_amarillo():
    sem, _, _ = regulatory.apply_regulatory_findings(Semaforo.VERDE, "ok", _amar())
    assert sem is Semaforo.AMARILLO


def test_apply_no_degrada_rojo_existente():
    sem, _, _ = regulatory.apply_regulatory_findings(Semaforo.ROJO, "prohibido", _amar())
    assert sem is Semaforo.ROJO


def test_apply_no_sube_amarillo_a_verde():
    sem, _, _ = regulatory.apply_regulatory_findings(Semaforo.AMARILLO, "cautela", [])
    assert sem is Semaforo.AMARILLO


def test_apply_sin_hallazgos_no_cambia():
    sem, reason, av = regulatory.apply_regulatory_findings(Semaforo.VERDE, "ok", [])
    assert sem is Semaforo.VERDE and reason == "ok" and av == []
