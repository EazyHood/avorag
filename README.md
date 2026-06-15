# 🥑 AvoRAG — Asesor Hass

Asistente agronómico conversacional (RAG) en español de finca, **comercialmente neutral** y
curado por un ingeniero agrónomo, especializado en **aguacate Hass de exportación**. Responde
**citando la fuente oficial** (Agrosavia, ICA, Corpohass…), **se abstiene cuando no sabe** y
**marca en rojo (semáforo) las dosis no respaldadas por una fuente citada** y —cuando el
fragmento de respaldo trae registro ICA— exige que sea válido y vigente.

## 📊 Resultados (medición real · n=64 · `RERANK_PROVIDER=local` · qwen2.5:7b · corpus 2026-06-14)

| Groundedness¹ | Soporte de cita | Abstención (trampas) | Peligrosas manejadas² | Latencia | Gate |
|:--:|:--:|:--:|:--:|:--:|:--:|
| **0.73** | **0.89** | **0.90** | **1.00** | **35 s** | **✓ PASA** |

¹ **Groundedness** = cada afirmación está respaldada por el fragmento citado; juzgada por LLM
(qwen-7b autoevaluándose, conservador). **NO** es exactitud agronómica ni vigencia de la fuente.
² Las 10 preguntas adversarias (mezcla, prohibido, fitotoxicidad, dosis-trampa) quedaron en
rojo/amarillo, **ninguna en verde**. El reporte trae IC95 de Wilson por métrica.

> **Honestidad (0.96 → 0.73):** no es regresión, es honestidad. El 0.96 era sobre **n=16 fáciles**
> con un juez laxo; esto es **n=64** con preguntas adversarias, métricas más estrictas y el mismo
> qwen-7b local autoevaluándose. Con un modelo más fuerte (Claude) + validación humana sube; los
> objetivos son ~0.85. El **gate** es un piso de no-regresión calibrado sobre esta medición. Para
> una afirmación comercial: **≥200** preguntas curadas + segundo evaluador humano. El corpus se
> reconstruye desde fuentes públicas con [`scripts/build_corpus.py`](scripts/build_corpus.py).

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
ollama pull qwen2.5:7b-instruct

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
- [`docs/DEUDA_TECNICA.md`](docs/DEUDA_TECNICA.md) — corregido en v0.1 + diferidos a Ruta 🅱️.

La evaluación genera un **dashboard HTML** en `eval/reports/report.html` (captúralo para el portafolio).

## Licencia
**Código: MIT** (ver [`LICENSE`](LICENSE)) — libre de reutilizar, incluso comercialmente.
El **corpus** NO está cubierto por MIT: se rige por la licencia de cada fuente (varias de Agrosavia
son CC BY-NC = no comercial). Para vender el asistente, sustituir/licenciar el corpus aparte
(ver [`docs/SOURCES.md`](docs/SOURCES.md)).
