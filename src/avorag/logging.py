"""Configuración de logging estructurado (structlog)."""

from __future__ import annotations

import contextlib
import logging
import sys

import structlog

from avorag.config import get_settings

_CONFIGURED = False


def _ensure_utf8_streams() -> None:
    """En Windows la consola usa cp1252 y rompe con ✓/emojis/…; forzamos UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8", errors="replace")


def configure_logging() -> None:
    """Inicializa structlog. Idempotente (seguro llamarlo varias veces)."""
    global _CONFIGURED
    _ensure_utf8_streams()
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if settings.log_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Devuelve un logger estructurado."""
    configure_logging()
    return structlog.get_logger(name)
