"""Observabilidad del modo online: spans cronometrados sobre el logger estructurado (sin dependencias).

Da timing y estado por operación AHORA (recuperación, rerank, generación, guardarraíles, feeds) en
los logs estructurados. La integración OpenTelemetry COMPLETA (trazas distribuidas con OTLP) se
activa instalando el SDK (`opentelemetry-sdk`, `opentelemetry-exporter-otlp`) y envolviendo este
`span()` con un tracer real — documentado como activación de dependencia/infra.

Colisión-safe: módulo NUEVO bajo `online/`.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from avorag.logging import get_logger

log = get_logger(__name__)


@contextmanager
def span(name: str, **fields) -> Iterator[None]:
    """Cronometra un bloque y emite `span_start`/`span_end` (con ms y estado) al log estructurado."""
    t0 = time.perf_counter()
    log.info("span_start", span=name, **fields)
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        log.info(
            "span_end",
            span=name,
            status=status,
            ms=int((time.perf_counter() - t0) * 1000),
            **fields,
        )
