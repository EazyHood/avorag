"""Engine y sesiones de SQLAlchemy (síncrono, psycopg3).

El engine se construye de forma PEREZOSA (`get_engine`, cacheado): importar este módulo no
abre conexiones ni lee la BD. Así el dominio puede importarse sin tocar infraestructura, y
los tests unitarios no necesitan una base de datos. Por compatibilidad, `engine` y
`SessionLocal` siguen accesibles como atributos del módulo (se materializan al primer uso).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from avorag.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Devuelve el engine (cacheado). Se construye en la primera llamada, no al importar."""
    settings = get_settings()
    # Keepalives TCP: en Postgres gestionado serverless (Neon) el proxy corta conexiones que
    # quedan ociosas. Los keepalives mantienen viva la conexión y detectan cortes pronto.
    # Solo aplican a psycopg (Postgres); SQLite u otros backends los ignoran.
    connect_args: dict[str, Any] = {}
    if settings.database_url.startswith(("postgresql", "postgres")):
        connect_args = {
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        }
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,  # evita conexiones muertas (importante con Postgres gestionado)
        pool_recycle=300,  # recicla conexiones de >5 min (Neon corta las viejas)
        connect_args=connect_args,
        future=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Devuelve la fábrica de sesiones (cacheada), ligada al engine perezoso."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False, class_=Session)


@contextmanager
def get_session() -> Iterator[Session]:
    """Context manager de sesión con commit/rollback automático."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def __getattr__(name: str) -> Any:
    # Compatibilidad: `engine` y `SessionLocal` se materializan perezosamente al accederlos,
    # sin construir nada al importar el módulo.
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
