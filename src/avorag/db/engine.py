"""Engine y sesiones de SQLAlchemy (síncrono, psycopg3). Construcción perezosa."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from avorag.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Devuelve el engine (cacheado)."""
    settings = get_settings()
    # Keepalives TCP para Postgres gestionado (Neon corta conexiones ociosas).
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
        pool_pre_ping=True,
        pool_recycle=300,  # Neon corta conexiones viejas
        connect_args=connect_args,
        future=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Devuelve la fábrica de sesiones (cacheada)."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False, class_=Session)


@contextmanager
def get_session(tenant: str | None = None, *, system: bool = False) -> Iterator[Session]:
    """Context manager de sesión con commit/rollback automático.

    En PostgreSQL el aislamiento multi-tenant es por RLS con políticas **fail-closed** (migración
    0004): una sesión SOLO ve/inserta filas de su `tenant`. Por eso el acceso a datos requiere
    tenant EXPLÍCITO:

    - ``get_session(tenant="acme")`` → fija ``app.current_tenant`` y acota la sesión a ese tenant.
    - ``get_session(system=True)`` → sesión administrativa explícita (tablas SIN RLS: ``tenants``,
      health checks). Por diseño NO ve filas de tablas con RLS (fail-closed).
    - ``get_session()`` sin ``tenant`` ni ``system`` → **ValueError**: evita el bug silencioso de
      operar sin tenant. Antes (políticas permisivas) ese caso veía TODOS los tenants (fail-open).

    En SQLite (tests) no hay RLS: `tenant` se valida pero no se aplica.
    """
    if tenant is None and not system:
        raise ValueError(
            "get_session requiere tenant=... (o system=True para operaciones administrativas sobre "
            "tablas sin RLS). Una sesión sin tenant no accede a datos con RLS: fail-closed."
        )
    session = get_session_factory()()
    try:
        if (
            tenant is not None
            and session.bind is not None
            and session.bind.dialect.name == "postgresql"
        ):
            session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant}
            )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def __getattr__(name: str) -> Any:
    # Compatibilidad hacia atrás: engine y SessionLocal se materializan al accederlos.
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
