"""Autenticación por API key, rate-limiting y minimización de datos en auditoría."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from avorag.api import auth
from avorag.config import Settings
from avorag.rag.pipeline import _audit_text


def _req(host: str = "1.2.3.4") -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host))


def test_dev_mode_allows_default_tenant() -> None:
    # Sin api_keys configuradas -> modo abierto.
    assert auth.require_api_key(None) == "demo"


def test_authenticated_mode_requires_valid_key(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(api_keys={"secreta": "finca1"}))
    assert auth.require_api_key("secreta") == "finca1"
    with pytest.raises(HTTPException) as exc:
        auth.require_api_key("mala")
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException):
        auth.require_api_key(None)


def test_rate_limit_blocks_after_threshold(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(rate_limit_per_minute=2))
    auth._reset_rate_limit()
    auth.rate_limit(_req(), x_api_key="k1")
    auth.rate_limit(_req(), x_api_key="k1")
    with pytest.raises(HTTPException) as exc:
        auth.rate_limit(_req(), x_api_key="k1")
    assert exc.value.status_code == 429
    # Otra clave tiene su propio bucket.
    auth.rate_limit(_req(), x_api_key="k2")


def test_rate_limit_disabled_when_zero(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(rate_limit_per_minute=0))
    auth._reset_rate_limit()
    for _ in range(100):
        auth.rate_limit(_req(), x_api_key="k")


def test_audit_text_hashes_when_minimized() -> None:
    assert _audit_text("hola", True) == "hola"
    h = _audit_text("hola", False)
    assert h.startswith("<sha256:") and "hola" not in h


def test_prod_env_requires_auth() -> None:
    # En producción, config sin API_KEYS no debe instanciarse.
    with pytest.raises(ValidationError):
        Settings(avorag_env="prod", api_keys={})
    s = Settings(avorag_env="prod", api_keys={"k": "t"})
    assert s.avorag_env == "prod"
