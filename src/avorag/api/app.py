"""Aplicación FastAPI. El mismo motor que luego usará el webhook de WhatsApp."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from avorag import __version__
from avorag.api.routes_chat import router as chat_router
from avorag.api.routes_health import router as health_router
from avorag.config import get_settings
from avorag.logging import configure_logging, get_logger

log = get_logger(__name__)
_STATIC_DIR = Path(__file__).parent / "static"


def _warm_models() -> None:
    """Precarga el reranker (y el embedder) al arrancar, para que la PRIMERA consulta no pague
    la carga del modelo (~varios s). Tolerante a fallo: si algo no está listo, no rompe el arranque."""
    from avorag.providers import (
        get_embedding_provider,
        get_llm_provider,
        get_rerank_provider,
    )

    s = get_settings()
    try:
        if s.rerank_provider.lower() == "local":
            get_rerank_provider().rerank("warmup", ["warmup"], 1)
        get_embedding_provider().embed_query("hola")
        get_llm_provider().complete("Responde solo: ok", "ok", max_tokens=1)
        log.info("models_warmed", rerank=s.rerank_provider, llm=s.llm_provider)
    except Exception as exc:  # noqa: BLE001
        log.warning("model_warmup_failed", error=str(exc))


def _prewarm_defaults() -> None:
    """Sirve al instante las preguntas por defecto: carga del disco lo válido y recalcula en un
    hilo de fondo lo que falte (sin bloquear el arranque)."""
    import threading

    from avorag.rag import prewarm

    try:
        prewarm.load_from_disk()
        threading.Thread(target=prewarm.refresh, name="prewarm", daemon=True).start()
    except Exception as exc:  # noqa: BLE001
        log.warning("prewarm_setup_failed", error=str(exc))


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _warm_models()
    _prewarm_defaults()
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="AvoRAG — Asesor Hass",
        version=__version__,
        description="Asistente agronómico RAG en español con citación a fuente.",
        lifespan=_lifespan,
    )

    settings = get_settings()
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    app.include_router(health_router)
    app.include_router(chat_router)
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    log.info("app_created", version=__version__)
    return app


app = create_app()
