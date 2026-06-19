"""Rate-limiting con backend conmutable: Redis (multi-worker) o memoria (por proceso).

Cierra la parte de código del "rate-limit distribuido": si hay `REDIS_URL` y el cliente `redis`
disponible, se usa un contador en Redis (válido entre workers); si no, cae a un limitador en memoria
(por proceso, el comportamiento actual). Ventana fija, `now` inyectable (tests deterministas).

Activación: `REDIS_URL=redis://…` + sustituir el limitador de `api/auth.py` por `get_rate_limiter()`
(un cambio de una línea; documentado). Colisión-safe: módulo NUEVO bajo `online/`.
"""

from __future__ import annotations

import os
import threading
import time
from abc import ABC, abstractmethod


def _now(now: float | None) -> float:
    return now if now is not None else time.time()


class RateLimiter(ABC):
    @abstractmethod
    def allow(self, key: str, *, limit: int, window_s: int, now: float | None = None) -> bool:
        """True si la petición `key` cabe dentro de `limit` por `window_s`; la cuenta y decide."""


class MemoryRateLimiter(RateLimiter):
    """Ventana fija por proceso (como el actual). No comparte estado entre workers."""

    def __init__(self) -> None:
        self._hits: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_s: int, now: float | None = None) -> bool:
        t = _now(now)
        with self._lock:
            count, start = self._hits.get(key, (0, t))
            if t - start >= window_s:
                count, start = 0, t
            count += 1
            self._hits[key] = (count, start)
            return count <= limit


class RedisRateLimiter(RateLimiter):
    """Contador atómico en Redis (INCR + EXPIRE): válido entre múltiples workers/instancias."""

    def __init__(self, client) -> None:
        self._r = client

    def allow(self, key: str, *, limit: int, window_s: int, now: float | None = None) -> bool:
        rk = f"rl:{key}:{int(_now(now) // window_s)}"  # bucket de ventana
        count = self._r.incr(rk)
        if count == 1:
            self._r.expire(rk, window_s)
        return int(count) <= limit


def _try_redis():
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis  # dependencia opcional

        client = redis.Redis.from_url(url)
        client.ping()
        return client
    except Exception:  # noqa: BLE001 — sin redis/url ⇒ fallback a memoria
        return None


_SINGLETON: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Limitador del proceso: Redis si está configurado y disponible; si no, memoria."""
    global _SINGLETON
    if _SINGLETON is None:
        client = _try_redis()
        _SINGLETON = RedisRateLimiter(client) if client is not None else MemoryRateLimiter()
    return _SINGLETON
