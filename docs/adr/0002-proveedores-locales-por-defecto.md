# ADR 0002 — Proveedores locales por defecto (Ollama + GPU)

**Estado:** aceptado · **Fecha:** 2026-06-14

## Contexto
El fundador tiene Ollama y una RTX 5060 (8 GB). La fase portafolio no debe costar
dinero en APIs, pero el demo de venta sí se beneficia de la calidad de Claude.

## Decisión
LLM, embeddings y reranker son **intercambiables por configuración** (`providers/`).
Defaults: `LLM_PROVIDER=ollama`, `EMBEDDING_PROVIDER=ollama` (bge-m3), `RERANK_PROVIDER=none`.
Para el demo/producción se cambia `LLM_PROVIDER=anthropic` con una sola variable.

## Consecuencias
- (+) Desarrollo gratis, offline y privado.
- (+) Cero reescritura para subir de calidad o de proveedor.
- (−) La calidad de un 7B local < Claude → se documenta y se mide en el golden set.
