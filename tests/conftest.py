"""Configuración de pytest. Los tests unitarios no requieren DB ni LLM."""

import os

# Evita que un .env real altere los tests; usa defaults deterministas.
os.environ.setdefault("AVORAG_ENV", "test")
os.environ.setdefault("EMBEDDING_DIM", "1024")
