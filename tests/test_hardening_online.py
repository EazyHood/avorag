"""Production hardening: rate-limit conmutable, verificación JWT HS256, spans de observabilidad."""

from __future__ import annotations

import pytest

from avorag.online import jwt_auth, observability, ratelimit


# ── Rate limiter ─────────────────────────────────────────────────────────────────────────────────
def test_memory_rate_limiter_ventana_fija():
    rl = ratelimit.MemoryRateLimiter()
    t = 1000.0
    assert all(rl.allow("k", limit=3, window_s=60, now=t) for _ in range(3))
    assert rl.allow("k", limit=3, window_s=60, now=t) is False  # 4º excede
    assert rl.allow("k", limit=3, window_s=60, now=t + 61) is True  # ventana nueva


def test_get_rate_limiter_memoria_sin_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    ratelimit._SINGLETON = None
    assert isinstance(ratelimit.get_rate_limiter(), ratelimit.MemoryRateLimiter)


# ── JWT HS256 ──────────────────────────────────────────────────────────────────────────────────
def test_jwt_roundtrip_y_tenant():
    tok = jwt_auth.encode_hs256({"tenant": "acme", "exp": 9_999_999_999}, "secret")
    assert jwt_auth.verify_hs256(tok, "secret")["tenant"] == "acme"
    assert jwt_auth.tenant_from_token(tok, secret="secret") == "acme"


def test_jwt_firma_invalida():
    tok = jwt_auth.encode_hs256({"tenant": "acme"}, "secret")
    with pytest.raises(ValueError, match="Firma"):
        jwt_auth.verify_hs256(tok, "otro-secreto")


def test_jwt_expirado():
    tok = jwt_auth.encode_hs256({"tenant": "acme", "exp": 1000}, "secret")
    with pytest.raises(ValueError, match="expirado"):
        jwt_auth.verify_hs256(tok, "secret", now=2000)


def test_jwt_sin_secreto_devuelve_none(monkeypatch):
    monkeypatch.delenv("AVORAG_JWT_SECRET", raising=False)
    tok = jwt_auth.encode_hs256({"tenant": "acme"}, "secret")
    assert jwt_auth.tenant_from_token(tok) is None


# ── Observabilidad ───────────────────────────────────────────────────────────────────────────────
def test_span_ok_y_propaga_excepcion():
    with observability.span("t", k="v"):
        pass
    with pytest.raises(ValueError), observability.span("t"):
        raise ValueError("x")
