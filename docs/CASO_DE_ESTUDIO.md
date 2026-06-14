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

## Resultados (medidos sobre mi golden set de 16 preguntas)
<!-- Pega aquí la captura de eval/reports/report.html -->
| Métrica | Valor |
|---|---|
| Fidelidad media | **0,96** |
| Citación en respuestas | **100%** |
| Abstención correcta (trampas) | **100%** |
| Alucinaciones de dosis de alta severidad | **0** |
| Tasa de respuesta (reales) | **83% (10/12; 2 abstenciones honestas)** |
| Latencia media | **44 847 ms** (reranker en CPU) |

> Cómo lo logré: corpus curado + Contextual Retrieval + búsqueda híbrida + reranking +
> guardarraíl de dosis. _(Si comparo modelos/configs, pongo la tabla antes/después.)_

## Limitaciones honestas (lo que NO hace)
- No reemplaza a un ingeniero agrónomo; es herramienta de **apoyo**.
- El diagnóstico por foto sería una pista, no un veredicto (no implementado en esta versión).
- La equivalencia de unidades de dosis (kg↔g) es una mejora pendiente del guardarraíl.
- Cobertura limitada al corpus curado; fuera de él, se abstiene a propósito.

## Stack
Python 3.12 · FastAPI · SQLAlchemy + **pgvector** · Ollama/Claude · RAGAS · ruff/mypy/pytest · CI.

## Qué aprendí
- Diseñar un RAG **de producción** (no un demo): evaluación, guardarraíles, observabilidad.
- Que el valor está en el **contenido curado y los guardarraíles**, no en el modelo.
- A medir calidad con números propios y a comunicar límites con honestidad.

## Enlaces
- Repo: **https://github.com/EazyHood/avorag**  · Demo (Loom): <!-- URL -->  · Dashboard de evaluación: <!-- captura -->
