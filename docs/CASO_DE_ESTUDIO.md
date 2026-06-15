# Caso de estudio — AvoRAG (Asesor Hass)

> **Asistente agronómico conversacional (RAG) en español, neutral y con citación a fuente,
> especializado en aguacate Hass de exportación.**
> _Construido por un ingeniero agrónomo para demostrar IA aplicada con criterio de dominio._

> ℹ️ **Plantilla:** reemplaza los marcadores `{{...}}` con tus números reales tras correr
> `uv run avorag eval` (sale en `eval/reports/report.html`). No uses cifras de terceros.

## El problema
En Colombia, el aguacate Hass de exportación enfrenta dos presiones a la vez:
- **Brecha de extensión:** pocas manos técnicas para cientos de fincas proveedoras; las
  recomendaciones de manejo llegan tarde o inconsistentes.
- **Rechazos en destino:** una plaga mal manejada o un residuo químico fuera del LMR puede
  costar un **contenedor entero** en la UE/EE.UU.

Los asistentes genéricos de IA **alucinan dosis** y no citan fuente — inaceptable cuando una
dosis equivocada arruina un cultivo o una certificación.

## La solución
AvoRAG responde dudas de manejo del Hass **solo desde un corpus oficial curado**
(Agrosavia, ICA, Corpohass), **citando la fuente de cada afirmación**, **bloqueando dosis
no rastreables a una etiqueta registrada** y **abstiéndose cuando no sabe** en vez de inventar.

## Por qué yo
La parte difícil no es el LLM (eso lo hace la IA sola): es **codificar el criterio
agronómico** — qué fuentes son autoritativas, qué umbrales de dosis son válidos, qué va
siempre a revisión de un profesional. Ese es mi aporte como agrónomo, y el foso del producto.

## Decisiones de diseño clave
- **Neutralidad comercial:** no vende ningún insumo; su única lealtad es la fuente oficial.
- **Citación a nivel de fuente** (nombre + página): trazabilidad que un comprador exige.
- **Guardarraíl de dosis:** una cifra de dosis solo se acepta si aparece, con unidad, en una
  fuente citada; si no, semáforo 🔴 → revisión humana.
- **Abstención honesta** como feature: distingue "no hay info", "fuera de dominio" y "otro
  cultivo".
- **Semáforo 🟢🟡🔴** + **agrónomo-en-el-bucle** para lo de alto riesgo (categoría I/II).
- **Evaluación como gate:** un golden set verificado mide la calidad y bloquea regresiones.

## Arquitectura (resumen)
Recuperación **híbrida** (denso `pgvector` + léxico FTS español) → fusión **RRF** →
**reranking** → prompt _evidence-first_ → LLM → **guardarraíles** → semáforo → auditoría.
Proveedores intercambiables por configuración (local gratis con Ollama, o Claude para el
demo). Detalle en [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Resultados (línea base v1 · n=16 · `RERANK_PROVIDER=local` · corpus_version 2026-06-14)
<!-- Pega aquí la captura de eval/reports/report.html -->
| Métrica | Valor | Qué mide (y qué NO) |
|---|---|---|
| **Groundedness** | **0,96** | Cada afirmación está respaldada por el fragmento citado. **NO** es exactitud agronómica ni vigencia de la fuente. Juez LLM. |
| Respuestas con cita | **100%** | **Presencia** de cita, no que el fragmento sostenga la afirmación (eso es `citation_support_rate`). |
| Abstención correcta (trampas) | **100%** | Sobre 4 trampas (IC95 amplio). |
| Dosis sin respaldo | **0** | Calculado por el guardarraíl de dosis (ahora determinista y atado al producto correcto). |
| Tasa de respuesta (reales) | **83% (10/12; 2 abstenciones honestas)** | |
| Latencia (primer hit) | **44 847 ms** con `RERANK_PROVIDER=local` en CPU · **<50 ms** repetidas (caché) | El default de fábrica es `none`. |

> Cómo lo logré: corpus curado + Contextual Retrieval + búsqueda híbrida + reranking +
> guardarraíl de dosis determinista + caché de respuestas.
>
> **El juez de groundedness es un LLM** (en la ruta local, `qwen2.5:7b` se autoevalúa: cifra
> indicativa, sin validación humana ni segundo modelo). Para una afirmación comercial: juez
> independiente (`JUDGE_LLM_PROVIDER`) + acuerdo inter-anotador humano (n≥200).

> **Validez estadística (honesto):** estos números son de la **v1 con n=16** preguntas — una
> muestra **pequeña**, suficiente para una prueba de concepto pero **no** para afirmar tasas
> poblacionales con intervalos estrechos (el reporte muestra IC95 de Wilson). El golden set se
> amplió a **n=64** (`data/golden/hass_v1.jsonl`, con dosis, carencia/PHI, categoría toxicológica,
> mezclas, prohibidos y trampas adversarias); la re-medición sobre n=64 con las métricas nuevas
> (correctness vs hechos esperados, citation_support) es el siguiente hito. Para una afirmación
> comercial: **≥200** preguntas curadas por el agrónomo + segundo evaluador humano (acuerdo inter-anotador).

## Limitaciones honestas (lo que NO hace)
- No reemplaza a un ingeniero agrónomo; es herramienta de **apoyo**.
- **Es texto-only:** NO identifica plaga/enfermedad por foto (la guía visual aporta sus *pies de
  figura* al índice, no la imagen). El diagnóstico por imagen sería trabajo futuro.
- El contexto de finca (suelo/región) afina cualitativamente vía prompt y recuperación; **no**
  interpreta análisis foliar/suelo ni calcula dosis por balance de nutrientes, y la evidencia de
  lixiviación por textura proviene de fuentes no-colombianas (se transfieren principios, no dosis).
- Cobertura limitada al corpus curado; fuera de él, se abstiene a propósito.
- El registro PQUA del ICA es de **mar-2022**; el estado vivo de cada producto está en SimplifICA
  (la respuesta lleva ese aviso cuando cita un registro).
- **Estado v0.1 (prueba de concepto):** sin rodaje en producción ni validación con usuarios reales.

## Guardarraíles de seguridad (qué verifica antes de mostrar una dosis)
- **Dosis con fuente:** toda cifra de dosis debe estar respaldada por el contexto (con equivalencia kg↔g); si no, **ROJO**.
- **Asociación producto–plaga–dosis–carencia:** un juez verifica que la dosis correcta vaya con el **producto y la plaga correctos** (no una dosis válida pegada al producto equivocado).
- **Periodo de carencia (PHI)/reingreso:** si el texto afirma una carencia que no está en la fuente, **ROJO** (riesgo de LMR en exportación).
- **Categoría toxicológica I/II:** se extrae del registro en la ingesta; si el producto recomendado es cat. I/II, **ROJO** con advertencia.
- Estos guardarraíles están cubiertos por **tests unitarios en el CI**.

## Stack
Python 3.11+ · FastAPI · SQLAlchemy + **pgvector** · Ollama/Claude · evaluación con **juez LLM
propio + golden set con gate** · ruff/mypy/pytest · CI.
_(Nota: RAGAS figura como dependencia opcional pero la evaluación NO la usa; se retiró de esta
lista para no sobre-declarar el stack.)_

## Qué aprendí
- Diseñar un RAG con **prácticas de producción** (no un demo): evaluación, guardarraíles, observabilidad.
- Que el valor está en el **contenido curado y los guardarraíles**, no en el modelo.
- A medir calidad con números propios y a comunicar límites con honestidad.

## Enlaces
- Repo: **https://github.com/EazyHood/avorag**  · Demo (Loom): <!-- URL -->  · Dashboard de evaluación: <!-- captura -->
