"""Proveedor REAL de feed por HTTP-JSON + selección por URL configurada."""

from __future__ import annotations

from avorag.online import feeds
from avorag.rag.freshness import FeedName


def test_http_provider_fetch_usa_payload_y_as_of(monkeypatch):
    payload = {
        "registros": [{"ingrediente_activo": "x", "estado": "vigente"}],
        "as_of": "2026-06-10T00:00:00+00:00",
    }
    monkeypatch.setattr(feeds, "_http_get_json", lambda url, **k: payload)
    f = feeds.HttpJsonProvider(FeedName.ICA, "http://feed.local/ica").fetch()
    assert f.payload == payload and f.feed_name == FeedName.ICA.value
    assert f.as_of.isoformat().startswith("2026-06-10")
    assert f.source_url == "http://feed.local/ica"


def test_get_provider_real_usa_http_si_hay_url(monkeypatch):
    monkeypatch.setenv("AVORAG_FEED_ICA_URL", "http://feed.local/ica")
    p = feeds.get_provider(FeedName.ICA, mode="real")
    assert isinstance(p, feeds.HttpJsonProvider)


def test_get_provider_real_cae_al_stub_sin_url(monkeypatch):
    monkeypatch.delenv("AVORAG_FEED_ICA_URL", raising=False)
    p = feeds.get_provider(FeedName.ICA, mode="real")
    assert p.name == "ica-simplifica"  # stub específico
