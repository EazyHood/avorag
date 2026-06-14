# ADR 0004 — Dimensión de embeddings fija y re-indexado

**Estado:** aceptado · **Fecha:** 2026-06-14

## Contexto
La columna `chunks.embedding` es `vector(EMBEDDING_DIM)`. Cada modelo de embeddings
produce una dimensión fija (bge-m3 = 1024, text-embedding-3-small = 1536).

## Decisión
- `EMBEDDING_DIM` se define en `.env` (default 1024 para bge-m3) y lo usan tanto el
  modelo ORM como la migración inicial.
- Cambiar de modelo de embeddings implica: ajustar `EMBEDDING_DIM`, recrear el índice
  vectorial y **re-embeber el corpus**. Esto se hace con el reindexado **blue-green**
  (construir el nuevo índice en paralelo, validar contra el golden set, y promover).

## Consecuencias
- (+) Sin sorpresas: el cambio de modelo es una operación documentada, no un bug.
- (−) Re-embeber tiene costo (tiempo/tokens); por eso el corpus se mantiene compacto.
