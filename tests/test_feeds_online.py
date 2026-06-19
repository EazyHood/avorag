"""Servicio de feeds en vivo (modo online): normalización, sha256, lookups y upsert idempotente."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from avorag.online import feeds
from avorag.rag.freshness import FeedName, FeedSnapshotView

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


# ── sha256 canónico ──────────────────────────────────────────────────────────────────────────────
def test_sha256_es_determinista_e_independiente_del_orden():
    a = {"x": 1, "y": [3, 2]}
    b = {"y": [3, 2], "x": 1}
    assert feeds.canonical_sha256(a) == feeds.canonical_sha256(b)
    assert feeds.canonical_sha256(a) != feeds.canonical_sha256({"x": 2, "y": [3, 2]})


def test_sha256_del_fetch_no_depende_de_la_hora():
    p = feeds.FakeIcaProvider()
    f1 = p.fetch(now=NOW)
    f2 = p.fetch(now=NOW + timedelta(days=10))
    assert f1.as_of != f2.as_of  # la fecha-de-dato cambia…
    assert f1.sha256 == f2.sha256  # …pero el hash es del CONTENIDO (dedup correcto)


# ── Proveedores ──────────────────────────────────────────────────────────────────────────────────
def test_fake_providers_devuelven_fetch_valido():
    for feed in (FeedName.ICA, FeedName.LMR_UE, FeedName.TOL_EEUU):
        p = feeds.get_provider(feed, mode="fake")
        f = p.fetch(now=NOW)
        assert f.feed_name == feed.value
        assert f.ttl_seconds > 0 and f.as_of == NOW and isinstance(f.payload, dict)


def test_proveedor_real_es_stub_que_avisa():
    p = feeds.get_provider(FeedName.ICA, mode="real")
    with pytest.raises(NotImplementedError):
        p.fetch(now=NOW)


# ── Lookups canónicos (lo que el guardarraíl consume) ─────────────────────────────────────────────
def test_ica_status():
    payload = feeds.FakeIcaProvider().fetch(now=NOW).payload
    assert feeds.ica_status(payload, "clorpirifos") == "cancelado"
    assert feeds.ica_status(payload, "abamectina") == "vigente"
    assert feeds.ica_status(payload, "molecula_inexistente") == "desconocido"


def test_ue_lmr():
    payload = feeds.FakeLmrUeProvider().fetch(now=NOW).payload
    assert feeds.ue_lmr(payload, "clorpirifos") == ("no_aprobado", None)
    estado, val = feeds.ue_lmr(payload, "abamectina")
    assert estado == "aprobado" and val == 0.01
    assert feeds.ue_lmr(payload, "otra")[0] == "desconocido"


def test_eeuu_tolerance():
    payload = feeds.FakeTolEeuuProvider().fetch(now=NOW).payload
    # paraquat y azoxystrobin SÍ tienen tolerancia en aguacate (la doctrina 40 CFR 180).
    assert feeds.eeuu_tolerance(payload, "paraquat") == (True, 0.05)
    # clorpirifos sin tolerancia ⇒ residuo violatorio.
    assert feeds.eeuu_tolerance(payload, "clorpirifos") == (False, None)
    # ausencia ≠ autorizado.
    assert feeds.eeuu_tolerance(payload, "desconocida") == (False, None)


# ── Persistencia (sesión fake, sin BD) ────────────────────────────────────────────────────────────
class _FakeSession:
    def __init__(self, existing=None):
        self._existing = existing
        self.added: list = []

    def scalar(self, _stmt):
        return self._existing

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def test_upsert_inserta_si_no_existe():
    s = _FakeSession(existing=None)
    f = feeds.FakeIcaProvider().fetch(now=NOW)
    snap = feeds.upsert_snapshot(s, f)
    assert len(s.added) == 1
    assert snap.feed_name == FeedName.ICA.value and snap.sha256 == f.sha256


def test_upsert_es_idempotente_si_ya_existe():
    sentinel = object()
    s = _FakeSession(existing=sentinel)
    snap = feeds.upsert_snapshot(s, feeds.FakeIcaProvider().fetch(now=NOW))
    assert snap is sentinel and s.added == []  # no re-inserta


def test_latest_view_envuelve_el_snapshot():
    f = feeds.FakeIcaProvider().fetch(now=NOW)
    snap = feeds.FeedSnapshot(
        feed_name=f.feed_name,
        as_of=f.as_of,
        ttl_seconds=f.ttl_seconds,
        sha256=f.sha256,
        payload=f.payload,
    )
    view = feeds.latest_view(_FakeSession(existing=snap), FeedName.ICA)
    assert isinstance(view, FeedSnapshotView)
    assert view.feed_name == FeedName.ICA.value and view.as_of == NOW


def test_latest_view_none_si_no_hay_snapshot():
    assert feeds.latest_view(_FakeSession(existing=None), FeedName.ICA) is None
