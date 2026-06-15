"""Configuración de pytest. Los tests unitarios no requieren DB ni LLM."""

import os

# Evita que un .env real altere los tests; usa defaults deterministas.
os.environ.setdefault("AVORAG_ENV", "test")
os.environ.setdefault("EMBEDDING_DIM", "1024")
# Evita heredar la URL real (Neon) del .env: un test no debe poder tocar producción.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://avorag:avorag@localhost:5432/avorag_test"
)
