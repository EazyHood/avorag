"""Manifiesto de sincronización online↔offline: construcción firmada + versiones del servidor."""

from __future__ import annotations

from datetime import UTC, datetime

from avorag.online import sync

NOW = datetime(2026, 6, 18, tzinfo=UTC)


def test_manifest_firmado_y_verificable():
    m = sync.build_manifest(corpus_version="2026-06-17.1", norm_version="2026-06-17", now=NOW)
    assert m["signature"] and len(m["signature"]) == 64
    assert {"corpus", "normas"} <= {a["name"] for a in m["artifacts"]}
    # La firma cubre todo menos el propio campo signature: re-firmar da lo mismo.
    assert sync._sign_manifest(m) == m["signature"]


def test_manifest_acepta_artefactos_offline():
    extra = [{"name": "vision_model", "version": "1", "sha256": "a", "url": "u", "bytes": 1}]
    m = sync.build_manifest(corpus_version="c", norm_version="n", now=NOW, artifacts_extra=extra)
    assert any(a["name"] == "vision_model" for a in m["artifacts"])


def test_current_manifest_smoke():
    m = sync.current_manifest(now=NOW)
    assert m["offline_contract_version"] == "1" and "signature" in m
    assert m["generated_at"] == NOW.isoformat()
