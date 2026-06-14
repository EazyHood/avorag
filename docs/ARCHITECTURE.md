# Arquitectura de AvoRAG

> Diseño pensado para que la **Ruta 🅰️ (portafolio web)** y la **Ruta 🅱️ (producto:
> WhatsApp + HITL + multi-tenant)** compartan el mismo motor. Nada se reescribe al crecer.

## Visión de capas

```
                         ┌──────────────────────────────────────┐
  Canales                │  Web UI (/)        WhatsApp (Ruta 🅱️) │
  (entrada)              └───────────────┬──────────────────────┘
                                         │  POST /api/ask
                         ┌───────────────▼──────────────────────┐
  API (FastAPI)          │  routes_chat → rag.answer()           │
                         └───────────────┬──────────────────────┘
                                         │
        ┌────────────────────────────────▼─────────────────────────────┐
        │                     NÚCLEO RAG (rag/pipeline.py)              │
        │                                                               │
        │  1. embed_query  ── providers.embeddings                      │
        │  2. hybrid_search ─ retrieval.hybrid (denso pgvector + FTS)   │
        │  3. rerank ──────── retrieval.rerank (none/cohere/local)      │
        │  4. prompt ──────── rag.prompt (evidence-first + abstención)  │
        │  5. generate ────── providers.llm (ollama/anthropic/openai)   │
        │  6. guardrails ──── rag.guardrails (dosis, cat I/II, juez)    │
        │  7. semáforo + citas + persistir auditoría (db.QueryLog)      │
        └───────────────┬───────────────────────────┬──────────────────┘
                        │                           │
              ┌─────────▼─────────┐       ┌─────────▼──────────┐
              │ Postgres+pgvector │       │  Proveedores (API   │
              │ documents/chunks/ │       │  o local en GPU)    │
              │ queries (audit)   │       └────────────────────┘
              └───────────────────┘
```

## Decisiones clave (resumen; detalle en `docs/adr/`)
- **Proveedores abstractos** (`providers/base.py`): LLM, embeddings y reranker son
  intercambiables por `.env`. El default es **100% local y gratis** (Ollama + GPU).
- **Recuperación híbrida** (denso + léxico) fusionada con **RRF**: lo denso da
  significado; lo léxico acierta en SKUs, registros ICA y dosis exactas.
- **Contextual Retrieval** (Anthropic) en ingesta: antepone contexto a cada chunk.
- **Guardarraíl de dosis**: ninguna cifra de dosis sin respaldo textual en una fuente.
- **Semáforo 🟢🟡🔴**: rojo = categoría I/II o dosis no rastreable → HITL (Ruta 🅱️).
- **Multi-tenant desde el esquema** (columna `tenant`) aunque la Ruta 🅰️ use uno solo.
- **Auditoría** (`queries`) de cada consulta: exigida por la due diligence B2B.

## Flujo de una consulta
Ver `rag/pipeline.py::answer()`. Cada paso registra latencia, citas, chunks
recuperados, fidelidad y semáforo en la tabla `queries`.

## Frontera Ruta 🅰️ → 🅱️ (qué se añade, sin reescribir)
| Pieza | Ruta 🅰️ (hoy) | Ruta 🅱️ (después) |
|---|---|---|
| Canal | Web UI | + Webhook WhatsApp (BSP) llamando a `rag.answer()` |
| Revisión | — | + Consola HITL sobre `queries` (reviewer_id, review_status) |
| Tenants | 1 (`demo`) | N (la columna `tenant` ya existe) |
| Generación | Ollama local | Claude (cambia `LLM_PROVIDER`) |
| Infra | local/Neon | Postgres gestionado + colas Redis + monitoreo |
