"""Worker de REFRESCO de feeds en vivo (modo online).

Itera los proveedores configurados, obtiene el dato y hace upsert idempotente del snapshot
(migración 0005). Pensado para correr periódicamente (cron) vía `scripts/refresh_feeds.py`.

Resiliente: un feed que falla (proveedor real aún no conectado → NotImplementedError, o error de red)
NO interrumpe el resto; se registra y se continúa. Colisión-safe: módulo nuevo bajo `online/`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from avorag.logging import get_logger
from avorag.online import feeds
from avorag.rag.freshness import FeedName

log = get_logger(__name__)


def registered_feeds(mode: str = "fake") -> list[FeedName]:
    """Feeds con proveedor disponible en el modo dado ('fake' o 'real')."""
    table = feeds._FAKE_REGISTRY if mode == "fake" else feeds._REAL_REGISTRY
    return list(table.keys())


def refresh_all_feeds(
    session: Session, *, mode: str = "fake", now: datetime | None = None
) -> list[object]:
    """Refresca todos los feeds del modo dado; devuelve los snapshots upserted (los que pudieron)."""
    out: list[object] = []
    for feed in registered_feeds(mode):
        try:
            provider = feeds.get_provider(feed, mode=mode)
            out.append(feeds.refresh_feed(session, provider, now=now))
        except NotImplementedError as exc:
            log.warning("feed_provider_not_ready", feed=feed.value, error=str(exc))
        except Exception as exc:  # noqa: BLE001 — un feed no debe tumbar el ciclo
            log.warning("feed_refresh_failed", feed=feed.value, error=str(exc))
    log.info("feeds_refresh_cycle", mode=mode, ok=len(out))
    return out
