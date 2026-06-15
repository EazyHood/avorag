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

## Resultados (medición real · n=64 · `RERANK_PROVIDER=local` · qwen2.5:7b · corpus_version 2026-06-14)
<!-- Pega aquí la captura de eval/reports/report.html -->
| Métrica | Valor (IC95 Wilson) | Qué mide (y qué NO) |
|---|---|---|
| **Groundedness** | **0,73** | Cada afirmación está respaldada por el fragmento citado. **NO** es exactitud agronómica ni vigencia. Juez LLM (qwen-7b autoevaluándose, conservador). |
| Soporte de cita | **0,89** (0,76–0,95) | La cifra citada `[n]` está realmente en el fragmento `n` (determinista). |
| Respuestas con cita | **0,73** (0,58–0,84) | **Presencia** de cita; las que no citan caen a amarillo. |
| Abstención correcta (trampas) | **0,90** (0,60–0,98) | 9/10 trampas abstenidas. |
| Manejo de preguntas peligrosas | **1,00** | Las 10 preguntas adversarias (mezcla, fitotox, prohibido, dosis-trampa) quedaron en rojo/amarillo, **ninguna en verde**. |
| must_cite (regulador correcto) | **0,89** | El item cita al regulador exigido (ICA/Agrosavia). |
| Tasa de respuesta (reales) | **0,81** | 44/54; 10 abstenciones honestas. |
| Latencia media | **35 s** (`RERANK_PROVIDER=local`, CPU) · **<50 ms** repetidas (caché) | El default de fábrica es `none`. GPU lo baja a segundos. |

**Gate: ✓ PASA** (piso de no-regresión calibrado sobre esta medición).

> **Honestidad sobre la caída vs la v1 (0,96 → 0,73):** NO es una regresión, es honestidad. La
> cifra v1 era groundedness sobre **n=16 fáciles** con un juez más laxo; aquí es **n=64** con
> preguntas adversarias difíciles (mezclas, prohibidos, fitotoxicidad), métricas **más estrictas**
> y el **mismo qwen-7b local autoevaluándose** (conservador). Con un modelo generador/juez más
> fuerte (Claude) y validación humana, sube. Los **objetivos** son groundedness/citación ~0,85.
>
> **Hallazgo de calibración:** el barrido de umbral separa trampas (score ~0) de reales (≥0,02)
> con **98,3% de exactitud**; `min_rerank_score` se fijó en 0,01 con base en eso.

> **Validez estadística:** n=64 sigue siendo una muestra **moderada** (los IC95 de Wilson son
> anchos, sobre todo en trampas y peligrosas, n=10 cada uno). Para una afirmación comercial:
> **≥200** preguntas curadas por el agrónomo + segundo evaluador humano (acuerdo inter-anotador).

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
