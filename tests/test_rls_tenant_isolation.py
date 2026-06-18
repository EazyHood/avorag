"""Aislamiento multi-tenant: `get_session` exige tenant (fail-closed) y la migración 0004 endurece RLS.

Regresión del hallazgo "RLS fail-open": una sesión sin `app.current_tenant` veía TODOS los tenants.
Ahora la política RLS es estricta y la capa de app obliga a declarar el tenant (o `system=True`).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from avorag.db import get_session


def test_get_session_requires_tenant_or_system():
    # Sin tenant ni system → ValueError ANTES de abrir la sesión (no hay fail-open silencioso).
    with pytest.raises(ValueError, match="tenant"), get_session():
        pass


def _load_migration_0004():
    path = (
        Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0004_rls_fail_closed.py"
    )
    spec = importlib.util.spec_from_file_location("mig0004", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0004_policy_is_fail_closed():
    mod = _load_migration_0004()
    assert mod.down_revision == "0003"
    # La política estricta NO lleva el "IS NULL OR" permisivo que causaba el fail-open.
    assert "IS NULL OR" not in mod._STRICT
    assert "tenant = current_setting('app.current_tenant', true)" in mod._STRICT
    # El permisivo se conserva SOLO para el downgrade (volver a 0003).
    assert "IS NULL OR" in mod._PERMISSIVE
