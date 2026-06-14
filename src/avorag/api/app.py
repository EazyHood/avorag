"""Aplicación FastAPI. El mismo motor que luego usará el webhook de WhatsApp."""

from __future__ import annotations

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


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="AvoRAG — Asesor Hass",
        version=__version__,
        description="Asistente agronómico RAG en español con citación a fuente.",
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
