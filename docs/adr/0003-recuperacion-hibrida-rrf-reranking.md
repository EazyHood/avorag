# ADR 0003 — Recuperación híbrida + RRF + reranking

**Estado:** aceptado · **Fecha:** 2026-06-14

## Contexto
En agronomía conviven preguntas semánticas ("¿por qué se me manchan las hojas?") con
términos exactos críticos: SKUs, números de registro ICA, dosis. Solo-denso falla en
exactos; solo-léxico falla en sinónimos.

## Decisión
- **Híbrido:** búsqueda densa (pgvector, distancia coseno, índice HNSW) +
  léxica (Postgres FTS con diccionario `spanish`, índice GIN sobre columna generada).
- **Fusión:** Reciprocal Rank Fusion (`RRF_K=60`).
- **Reranking:** cross-encoder opcional (Cohere o local) como mayor salto de calidad.
- **Chunking:** recursivo, ~480 tokens con 15% de solape; chunks pequeños para hechos
  (dosis), grandes para preguntas analíticas.
- **Contextual Retrieval** (Anthropic) en ingesta para reducir fallos de recuperación.

## Consecuencias
- (+) Robusto a consultas mixtas, lo que importa en este dominio.
- Nota: cambiar el **modelo de embeddings** cambia `EMBEDDING_DIM` → re-indexar el corpus
  (re-embed). Es esperado, no es reproceso de código. Ver ADR 0004.
