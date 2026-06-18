"""Los modelos ORM del online concuerdan con la migración 0005 (paridad nombre/columnas)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from avorag.db.models import Base
from avorag.db.models_online import Feedback, FeedSnapshot, HitlReview, NormTable

MODELS = [FeedSnapshot, NormTable, HitlReview, Feedback]


def _migration_sql() -> str:
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations" / "versions" / "0005_online_feeds_norms_hitl.py"
    )
    spec = importlib.util.spec_from_file_location("mig0005", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return "\n".join(mod._UPGRADE)


def test_modelos_registrados_en_el_mismo_metadata():
    # Comparten metadata con el núcleo (mismo Base) → una sola fuente de verdad del esquema.
    for m in MODELS:
        assert m.__tablename__ in Base.metadata.tables


def test_tablas_existen_en_la_migracion():
    sql = _migration_sql()
    for m in MODELS:
        assert f"CREATE TABLE IF NOT EXISTS {m.__tablename__}" in sql, m.__tablename__


def test_columnas_orm_existen_en_la_migracion():
    sql = _migration_sql()
    for m in MODELS:
        # Bloque CREATE TABLE de esta tabla.
        block = re.search(
            rf"CREATE TABLE IF NOT EXISTS {m.__tablename__}\s*\((.*?)\)\s*\"\"\"",
            sql, flags=re.DOTALL,
        )
        # Fallback: el bloque hasta el cierre de paréntesis de nivel superior.
        haystack = block.group(1) if block else sql
        for col in [c.name for c in m.__table__.columns]:
            assert col in haystack, f"{m.__tablename__}.{col} no aparece en la migración 0005"
