# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).
Estado del proyecto: **v0.1 — prueba de concepto** (sin rodaje en producción ni validación
con usuarios reales; los números publicados son de una evaluación interna).

## [No publicado] — Auditoría de 40 problemas (2026-06-15)
Respuesta a una auditoría experta de 40 puntos. Resumen por olas:

### Seguridad agronómica (guardarraíl de dosis)
- Verificación **determinista** de dosis atada al fragmento de origen: la dosis debe co-ocurrir
  con el **producto correcto** en un mismo fragmento (antes bastaba que el número existiera).
- Exige **registro ICA vigente y oficial** para dosis de fitosanitarios; valida que la **cifra
  citada esté en el fragmento citado**; **denylist** de ingredientes prohibidos/restringidos;
  detección de **off-label** y de **conflicto entre fuentes**; aviso de **dato desactualizado**.
- Extracción **estructurada** de tablas de dosis en la ingesta (producto·plaga·dosis·carencia·
  registro·categoría); el troceado ya **no parte filas** de tabla.

### Honestidad de métricas y evaluación
- `groundedness` (respaldo en fuente) separado de **correctness** (vs hechos esperados) y de
  **citation_support** (la cifra citada está en el fragmento). IC95 de Wilson. **Juez LLM
  independiente** opcional (antes el modelo se autoevaluaba). Gate endurecido.
- Golden set ampliado a **n=64** con matriz de riesgo (mezclas, prohibidos, fitotoxicidad,
  resistencia, dosis-trampa) y métrica `unsafe_handled_rate`.

### Ingeniería y producción
- Frontera **dominio/infraestructura**: la lógica de seguridad ya no arrastra la BD (engine
  perezoso; blindado por test). Auditoría **tolerante a fallo** (savepoint) + minimización de
  datos (Habeas Data). **API key + rate-limit**; **RLS** multi-tenant (migración 0003).
- **Jueces LLM en paralelo** + caché de respuestas (latencia). Python **≥3.11** + matriz CI.
- Corpus **reproducible** (manifiesto con sha256 + `build_corpus.py --verify`); resumen de
  documento real para Contextual Retrieval; OCR opcional; pies de figura preservados.

### Documentación
- Recalibración de claims: "groundedness" (no "fidelidad/exactitud"), estado v0.1, trade-off
  del reranker, RAGAS marcado como no-cableado, licencia de **código MIT** (corpus aparte).

## [0.1.0] — 2026-06-14
- Primera versión: motor RAG (híbrido + RRF + reranker), guardarraíl de dosis, semáforo,
  evaluación con golden set y gate, UI de chat, citación con URL/DOI, conciencia de suelo/región.
