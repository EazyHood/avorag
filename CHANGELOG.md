# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).
Estado del proyecto: **v0.1 — prueba de concepto** (sin rodaje en producción ni validación
con usuarios reales; los números publicados son de una evaluación interna).

## [No publicado] — Licencia propietaria (2026-06-17)
- **Cambio de licencia: de MIT a PROPIETARIO.** © 2026 Jhonatan del Rio, **todos los derechos
  reservados**. El código se publica visible **solo para revisión/evaluación** (portafolio); su uso,
  copia, modificación, distribución o uso comercial requiere **autorización escrita del titular**.
  Actualizados `LICENSE`, `pyproject.toml`, `README`, `TERMINOS_DE_USO`, `LIMITACIONES`,
  `PLAN_NO_CODIGO`, `SOBERANIA_DE_DATOS` y `VISION`. (El corpus sigue rigiéndose por la licencia de
  cada fuente, aparte.) Los documentos de revisión crítica conservan las menciones históricas a MIT
  como registro de su fecha.

## [No publicado] — Amplificación de las 40 fortalezas (2026-06-15)
Tras resolver los 40 problemas, se llevaron al máximo las 40 FORTALEZAS reconocidas: de
"afirmación" a **contrato ejecutable y medible**. **122 tests verdes, ruff+mypy limpios.**
- **Seguridad demostrable:** invariantes fail-safe del semáforo probadas sobre **>4000
  combinaciones** (VERDE solo desde estado sano); **catálogo red-team versionado**
  (`data/redteam/failure_modes.jsonl`) con 9 modos de fallo, cada uno probado end-to-end →
  semáforo+razón esperados, con `failure_mode_coverage = 100%`; propiedades de unidades de dosis
  (kg↔g, captura de `%`); disclaimer probado en todas las ramas.
- **Evaluación rigurosa:** golden set como contrato (categorías cerradas, cobertura mínima por
  eje de riesgo); `must_cite_mode` (all/any) bloqueante; `over_abstention_rate`; `PROMPT_VERSION`
  + contrato del prompt; `run_meta` (git sha + corpus_version + prompt_version) en cada reporte.
- **e2e sin Ollama:** proveedores **fake** deterministas → `answer()` completo testeado en el CI
  puro; reranker y búsqueda léxica **tolerantes a fallo** (degradan, no rompen); comando
  `avorag audit` (la auditoría guarda la justificación: por qué cada semáforo).
- **Procedencia y gobernanza:** citas con **autoridad + licencia** visibles y **quote dirigida a
  la cifra**; contrato de capas estático (AST); gobernanza del corpus como check; validador de
  invariantes de producción (`AVORAG_ENV=prod` exige auth y prohíbe CORS comodín).

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
