# 🥑 AvoRAG — Asesor Hass

Asistente agronómico conversacional (RAG) en español de finca, **comercialmente neutral** y
curado por un ingeniero agrónomo, especializado en **aguacate Hass de exportación**. Responde
**citando la fuente oficial** (Agrosavia, ICA, Corpohass…), **se abstiene cuando no sabe** y
**marca en rojo (semáforo) las dosis no respaldadas por una fuente citada** y —cuando el
fragmento de respaldo trae registro ICA— exige que sea válido y vigente.

## 📊 Resultados (medición real · n=64 · `RERANK_PROVIDER=local` · qwen2.5:7b · prompt v8 · corpus 2026-06-15.3)

| Groundedness¹ | Soporte de cita | Abstención (trampas) | Peligrosas manejadas² | Latencia | Gate |
|:--:|:--:|:--:|:--:|:--:|:--:|
| **0.79** | **0.95** | **1.00** | **0.90** | **~17 s** | **✓ PASA** |

¹ **Groundedness** = cada afirmación está respaldada por el fragmento citado; juzgada por LLM
(qwen-7b autoevaluándose, conservador). **NO** es exactitud agronómica ni vigencia de la fuente.
² De 10 preguntas adversarias (mezcla, prohibido, fitotoxicidad, dosis-trampa), **9 quedaron en
rojo/amarillo y 1 se coló en verde** — lo reportamos en vez de ocultarlo (IC95 amplio por n=10:
0.60–0.98). Aparte, las 10 trampas de abstención se abstuvieron **correctamente (1.00)** y la tasa
de rojo global es **4,7%**. El reporte trae IC95 de Wilson por métrica.

> **Honestidad (0.96 → 0.79):** no es regresión, es honestidad. El 0.96 era sobre **n=16 fáciles**
> con un juez laxo; esto es **n=64** con preguntas adversarias, métricas más estrictas y el mismo
> qwen-7b local autoevaluándose. Subió respecto a una medición previa (0.73) al pasar a **prompt v8 +
> corpus ampliado**, y esta corrida **pasa el gate** de no-regresión. Con un modelo más fuerte
> (Claude) + validación humana sube más; los objetivos son ~0.85. Para una afirmación comercial:
> **≥200** preguntas curadas + segundo evaluador humano. El corpus se reconstruye desde fuentes
> públicas con [`scripts/build_corpus.py`](scripts/build_corpus.py).

## 🔬 Simulación a escala (500 preguntas) y la métrica correcta
Se generaron **500 preguntas** (plagas, fertilidad/suelos, fisiología, insumos, otros) y se midió
el sistema completo en 7B con el corpus ampliado (~1.832 chunks). En vez de perseguir un "% verde"
alto, se reportan los KPIs de un **asesor de seguridad** (n=189, IC95 Wilson):

| Respuestas peligrosas | Respaldo (cita en lo que responde) | Bloqueo de inseguros (rojo) | Cobertura confiable (verde) | Deferencia honesta |
|:--:|:--:|:--:|:--:|:--:|
| **0%** | **89%** | **4%** | **44%** | **51%** |

**Conclusión ([ADR 0005](docs/adr/0005-metrica-de-asesor-de-seguridad.md)):** sobre preguntas
**arbitrarias**, un objetivo de "≥80% verde" no es alcanzable ni deseable — forzarlo solo se logra
relajando el semáforo (afirmar con confianza sin respaldo). El valor de la herramienta es el
**0% de respuestas peligrosas** + responder citado en su dominio y deferir con honestidad fuera de
él. La simulación encontró y arregló falsos positivos del guardarraíl (dosis de fertilizante/riego
tratadas como plaguicida) y guió la **ampliación del corpus** con 8 fuentes oficiales nuevas
(Agrosavia, MinAgricultura, ICESI, UNAD).

> **Velocidad (trade-off de hardware):** en una GPU de 8 GB el modelo 7B tarda ~1–2 min/pregunta;
> el default interactivo es **3B (~7–22 s)**, que con el mismo corpus sigue citando y aplicando los
> guardarraíles. Para máxima calidad puntual se cambia `LLM_MODEL` a 7B (`.env`).

## 📷 Visión: diagnóstico de madurez por foto (multimodal)
El productor sube una **foto** del fruto → un clasificador (MobileNetV3, licencia permisiva BSD —
**sin YOLO/AGPL**) identifica la **etapa de madurez** → la etiqueta entra al motor RAG, que responde
**citando la fuente** con su semáforo. La visión **solo identifica; nunca aconseja dosis por sí sola**.

| Métrica (held-out: 71 frutos NO vistos · n=2.304) | Valor |
|:--|:--:|
| Exacto (5 etapas) | **82%** |
| **Dentro de ±1 etapa** | **99.4%** |
| Calibración (confianza acierto vs fallo) | 0.82 vs 0.69 |

La UI muestra una **banda ±1** ("etapa 3–4: maduro → óptimo") en vez de forzar 1 de 5 — honesto con la
incertidumbre real (las etapas oscuras son visualmente continuas). **Honestidad:** madurez entrenable
hoy (dataset Mendeley **CC BY 4.0**); patología es un slot **preparado** (sin dataset limpio aún). El
color indica *maduración*; el punto de corte de **exportación se decide por materia seca, no por
color**. Detalle: [`docs/VISION.md`](docs/VISION.md).

## 🎯 Qué demuestra
RAG con **prácticas de producción** (recuperación híbrida + reranking + evaluación con gate,
guardarraíles, auditoría, observabilidad), **criterio de producto** (guardarraíl de dosis
determinista, abstención honesta, semáforo de riesgo) y **dominio agronómico codificado** — el
perfil híbrido agrónomo + IA que escasea en agtech. La **autenticación, el rate-limiting y el
aislamiento multi-tenant por RLS** están implementados pero deben **activarse deliberadamente**
para la exposición pública (ver [`docs/DEUDA_TECNICA.md`](docs/DEUDA_TECNICA.md)).
Caso de estudio: [Español](docs/CASO_DE_ESTUDIO.md) · [English](docs/CASE_STUDY.md).

> **Probado, no solo afirmado:** la seguridad es un **contrato ejecutable** — invariantes del
> semáforo verificadas sobre **>4000 combinaciones** (VERDE solo desde estado sano), un
> **catálogo red-team versionado** ([`data/redteam/failure_modes.jsonl`](data/redteam/failure_modes.jsonl))
> donde cada modo de fallo (dosis a producto equivocado, carencia inventada, prohibido, off-label…)
> se prueba que termina en ROJO/abstención, y un **e2e del pipeline con proveedores fake** que
> corre en CI sin Ollama ni BD. Toda cifra de evaluación lleva su procedencia (git sha +
> corpus_version + prompt_version).

> **Estado:** v0.1, prueba de concepto. Sin rodaje en producción ni validación con usuarios
> reales; los números son de una evaluación interna. Arquitectura pensada para crecer a producto
> (WhatsApp + HITL + multi-tenant) sin reescritura — ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Requisitos
- **Python 3.11+** (lo gestiona `uv`; el dev usa 3.12 por las ruedas ML).
- **[uv](https://docs.astral.sh/uv/)** (gestor de entorno y dependencias).
- **Postgres 16 + pgvector** vía `DATABASE_URL` — usa **Neon/Supabase gratis** (sin Docker) o el
  `docker-compose.yml` incluido.
- **[Ollama](https://ollama.com)** para el camino 100% local y gratis (embeddings + generación).

> **Reranker (trade-off honesto):** el default de fábrica es `RERANK_PROVIDER=none` (rápido,
> pero sin reordenar, las portadas ganan la recuperación). Las métricas publicadas se midieron con
> `RERANK_PROVIDER=local` (cross-encoder). En **CPU** tarda ~12 s; en **GPU baja a ~0,02 s** (usa
> `fp16` automáticamente). Cohere reordena rápido pero es de pago. Las preguntas repetidas y los
> saludos responden al instante (caché / capa conversacional).

### Aceleración por GPU (NVIDIA)
El reranker local usa GPU si hay CUDA. Por defecto `torch` se instala en su versión CPU; para
acelerar (p.ej. RTX 40/50 — Blackwell `sm_120` necesita CUDA 12.8):
```powershell
uv pip install torch --index-url https://download.pytorch.org/whl/cu128   # ajusta cu121/cu124 según tu GPU
uv run python -c "import torch; print(torch.cuda.is_available())"          # debe imprimir True
```
La generación y los embeddings ya corren en GPU vía Ollama. Con esto, una consulta técnica baja
de ~35 s a unos pocos segundos.

## Arranque rápido (Ruta local, gratis)
```powershell
# 1) Dependencias (uv descarga Python 3.12 automáticamente)
uv sync

# 2) Modelos locales (una sola vez)
ollama pull bge-m3
ollama pull qwen2.5:3b-instruct     # interactivo, rápido (~7-22 s)
ollama pull qwen2.5:7b-instruct     # opcional: máxima calidad (más lento)

# 3) Configuración
Copy-Item .env.example .env      # y ajusta DATABASE_URL

# 4) Base de datos
uv run avorag db upgrade         # crea tablas + extensión pgvector

# 5) Ingesta de un PDF del corpus
uv run avorag ingest data/corpus/mi_documento.pdf --fuente "Agrosavia — Modelo Productivo Hass"

# 6) Servidor + UI de chat
uv run avorag serve              # http://127.0.0.1:8000

# 7) Evaluación (golden set como gate de calidad)
uv run avorag eval data/golden/golden_set.example.jsonl
```

## Comandos
| Comando | Qué hace |
|---|---|
| `uv run avorag db upgrade` | Aplica migraciones (tablas + pgvector) |
| `uv run avorag ingest <pdf> --fuente <nombre>` | Ingesta y vectoriza un documento |
| `uv run avorag ask "<pregunta>"` | Pregunta por CLI (respuesta citada) |
| `uv run avorag serve` | API FastAPI + UI web |
| `uv run avorag eval <golden.jsonl>` | Corre el golden set y reporta métricas |

## Reconstruir el corpus (reproducibilidad)
Los PDF no se versionan (licencia + peso). Para que un tercero reproduzca los números:
```powershell
python scripts/build_corpus.py --ingest   # descarga las fuentes públicas y vectoriza
```
Descarga lo descargable por HTTP, lista lo que requiere bajada manual (landings de repositorio /
extracción de páginas) y respeta `data/corpus_manifest.json` (fuentes, URLs y licencias).

## Documentación
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — componentes y flujo.
- [`docs/adr/`](docs/adr/) — decisiones de arquitectura (por qué de cada elección).
- [`docs/GOLDEN_SET.md`](docs/GOLDEN_SET.md) — cómo construir el golden set (tu activo de calidad).
- [`docs/CASO_DE_ESTUDIO.md`](docs/CASO_DE_ESTUDIO.md) · [`docs/CASE_STUDY.md`](docs/CASE_STUDY.md) — caso de estudio (ES/EN) para portafolio.
- [`docs/SOURCES.md`](docs/SOURCES.md) — corpus: fuentes legales y su licencia.
- [`docs/SECURITY.md`](docs/SECURITY.md) — datos, secretos, Habeas Data.
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — operación, backups, rollback.
- [`docs/VISION.md`](docs/VISION.md) — módulo de visión (foto → madurez → RAG): arquitectura, licencias y resultados honestos.
- [`docs/TERMINOS_DE_USO.md`](docs/TERMINOS_DE_USO.md) — términos de uso y aviso legal (borrador para revisión de un abogado).
- [`docs/DEUDA_TECNICA.md`](docs/DEUDA_TECNICA.md) — corregido en v0.1 + diferidos a Ruta 🅱️.

La evaluación genera un **dashboard HTML** en `eval/reports/report.html` (captúralo para el portafolio).

## Licencia
**Código: MIT** (ver [`LICENSE`](LICENSE)) — libre de reutilizar, incluso comercialmente.
El **corpus** NO está cubierto por MIT: se rige por la licencia de cada fuente (varias de Agrosavia
son CC BY-NC = no comercial). Para vender el asistente, sustituir/licenciar el corpus aparte
(ver [`docs/SOURCES.md`](docs/SOURCES.md)).
