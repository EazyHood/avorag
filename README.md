# 🥑 AvoRAG — Asesor Hass

Asistente agronómico conversacional (RAG) en español de finca, **comercialmente neutral** y
curado por un ingeniero agrónomo, especializado en **aguacate Hass de exportación**. Responde
**citando la fuente oficial** (Agrosavia, ICA, Corpohass…), **se abstiene cuando no sabe** y
**bloquea recomendaciones de dosis no rastreables a una etiqueta registrada**.

## 📊 Resultados (golden set de 16 preguntas · corpus oficial ICA/Agrosavia, ~460 fragmentos)

| Fidelidad media | Citación | Abstención correcta (trampas) | Errores de dosis | Gate |
|:--:|:--:|:--:|:--:|:--:|
| **0.96** | **100%** | **100%** | **0** | **✓ PASA** |

Probado **end-to-end en vivo**: Postgres + pgvector en la nube (Neon) + modelos locales en GPU
(Ollama). El **dashboard reproducible** se genera en `eval/reports/report.html`.

## 🎯 Qué demuestra
RAG **de producción** (recuperación híbrida + reranking + evaluación con gate de CI), **criterio
de producto** (guardarraíl de dosis, abstención honesta, semáforo de riesgo, auditoría de cada
consulta, multi-tenant) y **dominio agronómico codificado** — el perfil híbrido agrónomo + IA que
escasea en agtech. Caso de estudio: [Español](docs/CASO_DE_ESTUDIO.md) · [English](docs/CASE_STUDY.md).

> Arquitectura pensada para crecer a producto (WhatsApp + HITL + multi-tenant) **sin reescritura** —
> ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) y [`docs/adr/`](docs/adr/).

## Requisitos
- **Python 3.12** (lo gestiona `uv`; tu sistema puede tener otra versión).
- **[uv](https://docs.astral.sh/uv/)** (gestor de entorno y dependencias).
- **Postgres 16 + pgvector** vía `DATABASE_URL` — usa **Neon/Supabase gratis** (sin Docker) o el
  `docker-compose.yml` incluido.
- **[Ollama](https://ollama.com)** para el camino 100% local y gratis (embeddings + generación).

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
Propietario. El corpus se rige por las licencias de cada fuente (ver `docs/SOURCES.md`).
