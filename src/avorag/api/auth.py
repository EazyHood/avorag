"""Autenticación por API key y rate-limiting de la API.

Cierra #33: la ruta de consulta se vendía como 'de producción' sin control de acceso ni
límite de uso. En modo desarrollo (sin `api_keys`) sigue abierta; en producción exige una
key válida y deriva el tenant del token (no del body, ver #32). El rate-limiter es en memoria
(por proceso); para multi-worker se sustituye por Redis.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request, status

from avorag.config import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Devuelve el tenant asociado al API key. Sin `api_keys` configuradas (dev), deja pasar
    como el tenant por defecto. Con `api_keys`, exige una key válida."""
    settings = get_settings()
    keys = settings.api_keys
    if not keys:
        return settings.default_tenant  # modo abierto: solo desarrollo / mismo origen
    if not x_api_key or x_api_key not in keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida o ausente.",
        )
    return keys[x_api_key]


# Marcas de tiempo de las últimas peticiones por clave (ventana deslizante de 60 s).
_HITS: dict[str, deque[float]] = defaultdict(deque)


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
