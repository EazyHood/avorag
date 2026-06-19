"""La migración 0005 (capa de datos online) es coherente y fail-closed.

Verifica sin BD (introspección del módulo): encadena tras 0004, crea las tablas del online y
aplica RLS ESTRICTA (sin la cláusula permisiva `IS NULL OR`) a las tablas tenant-scoped.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations" / "versions" / "0005_online_feeds_norms_hitl.py"
    )
    spec = importlib.util.spec_from_file_location("mig0005", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_0005_chains_after_0004():
    mod = _load()
    assert mod.revision == "0005"
    assert mod.down_revision == "0004"


def test_0005_creates_online_tables():
    mod = _load()
    blob = "\n".join(mod._UPGRADE)
    for table in ("feed_snapshots", "norm_tables", "hitl_reviews", "feedback"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in blob, table
    # Trazabilidad y idempotencia en queries (P-3/P-6).
    for col in ("response_id", "prompt_version", "model_version", "norm_version",
                "feed_versions", "idempotency_key"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in blob, col


def test_0005_rls_is_fail_closed():
    mod = _load()
    # Las tablas con datos de tenant llevan RLS.
    assert set(mod._RLS_TABLES) == {"hitl_reviews", "feedback"}
    # Política estricta: NO contiene la cláusula permisiva que causaba el fail-open.
    assert "IS NULL OR" not in mod._STRICT
    assert "tenant = current_setting('app.current_tenant', true)" in mod._STRICT
