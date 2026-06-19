"""Verificación de JWT (HS256) para auth tipo OAuth2/OIDC de clave simétrica — sin dependencias.

Cierra la parte de código de "OAuth2/OIDC": verifica un Bearer JWT firmado HS256 contra un secreto
configurado (`AVORAG_JWT_SECRET`), comprueba `exp`/`nbf` y extrae el claim `tenant`. Esto cubre IdPs
de clave compartida; para IdPs RS256/JWKS (Auth0, Keycloak con clave pública) se necesita el paquete
`pyjwt[crypto]` y la URL del JWKS — documentado como activación de dependencia.

Integración (documentada): en `api/auth.py`, una dependencia que, si llega `Authorization: Bearer …`
y `AVORAG_JWT_SECRET` está configurado, use `verify_hs256(...)` y tome el tenant del token (en vez de
la API-key). Lógica PURA y testeable. Colisión-safe: módulo NUEVO bajo `online/`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time


def _b64url_decode(seg: str) -> bytes:
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def encode_hs256(claims: dict, secret: str) -> str:
    """Firma un JWT HS256 (sobre todo para tests/integración local)."""
    header = _b64url_encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    payload = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(sig)}"


def verify_hs256(token: str, secret: str, *, now: float | None = None, leeway: float = 0.0) -> dict:
    """Verifica firma HS256 + exp/nbf y devuelve los claims. Lanza ValueError si es inválido."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("JWT malformado (se esperan 3 segmentos).")
    header_b, payload_b, sig_b = parts
    try:
        header = json.loads(_b64url_decode(header_b))
        claims = json.loads(_b64url_decode(payload_b))
        actual_sig = _b64url_decode(sig_b)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("JWT no decodificable.") from exc
    if header.get("alg") != "HS256":
        raise ValueError(f"alg no soportado: {header.get('alg')} (solo HS256).")
    expected = hmac.new(
        secret.encode(), f"{header_b}.{payload_b}".encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected, actual_sig):
        raise ValueError("Firma JWT inválida.")
    t = now if now is not None else time.time()
    exp = claims.get("exp")
    if exp is not None and t > float(exp) + leeway:
        raise ValueError("Token expirado.")
    nbf = claims.get("nbf")
    if nbf is not None and t + leeway < float(nbf):
        raise ValueError("Token aún no válido (nbf).")
    return claims


def tenant_from_token(
    token: str, *, secret: str | None = None, claim: str = "tenant"
) -> str | None:
    """Verifica el token con el secreto (o `AVORAG_JWT_SECRET`) y devuelve el claim de tenant, o None."""
    secret = secret if secret is not None else os.getenv("AVORAG_JWT_SECRET", "")
    if not secret:
        return None
    return verify_hs256(token, secret).get(claim)
