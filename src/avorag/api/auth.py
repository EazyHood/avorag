"""Autenticación por API key y rate-limiting.

En modo dev (sin `api_keys`) la API queda abierta; en prod exige key válida y deriva el
tenant del token. Rate-limiter en memoria; sustituir por Redis en multi-worker.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request, status

from avorag.config import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Valida el API key y devuelve el tenant asociado."""
    settings = get_settings()
    keys = settings.api_keys
    if not keys:
        return settings.default_tenant  # modo dev: sin autenticación
    if not x_api_key or x_api_key not in keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o ausente.",
        )
    return keys[x_api_key]


_HITS: dict[str, deque[float]] = defaultdict(deque)  # ventana deslizante de 60 s


def _bucket_key(request: Request, x_api_key: str | None) -> str:
    if x_api_key:
        return f"key:{x_api_key}"
    client = request.client.host if request.client else "anon"
    return f"ip:{client}"


def rate_limit(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Limita las solicitudes por API key (o IP) en una ventana de 60 s. 429 si se excede."""
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    key = _bucket_key(request, x_api_key)
    now = time.time()
    dq = _HITS[key]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas solicitudes. Intenta de nuevo en un minuto.",
        )
    dq.append(now)


def _reset_rate_limit() -> None:
    """Solo para tests."""
    _HITS.clear()
