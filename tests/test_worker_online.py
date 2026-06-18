"""Worker de refresco de feeds: upsert idempotente + resiliencia ante proveedores no conectados."""

from __future__ import annotations

from avorag.online import worker
from avorag.rag.freshness import FeedName


class _FakeSession:
    def __init__(self):
        self.added: list = []

    def scalar(self, _stmt):
        return None  # nada existe → upsert inserta

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def test_registered_feeds():
    assert set(worker.registered_feeds("fake")) == {
        FeedName.ICA,
        FeedName.LMR_UE,
        FeedName.TOL_EEUU,
    }
    assert FeedName.IDEAM in worker.registered_feeds("real")


def test_refresh_fake_upserta_los_3_feeds():
    s = _FakeSession()
    snaps = worker.refresh_all_feeds(s, mode="fake")
    assert len(snaps) == 3 and len(s.added) == 3


def test_refresh_real_resiliente_si_proveedores_no_conectados():
    # Proveedores reales son stubs (NotImplementedError): se saltan, no rompen el ciclo.
    s = _FakeSession()
    snaps = worker.refresh_all_feeds(s, mode="real")
    assert snaps == [] and s.added == []
