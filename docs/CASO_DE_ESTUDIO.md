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

## Resultados (medición real · n=64 · `RERANK_PROVIDER=local` · qwen2.5:7b · prompt v8 · corpus_version 2026-06-15.3)
<!-- Pega aquí la captura de eval/reports/report.html -->
| Métrica | Valor (IC95 Wilson) | Qué mide (y qué NO) |
|---|---|---|
| **Groundedness** | **0,79** | Cada afirmación está respaldada por el fragmento citado. **NO** es exactitud agronómica ni vigencia. Juez LLM (qwen-7b autoevaluándose, conservador). |
| Soporte de cita | **0,95** (0,84–0,99) | La cifra citada `[n]` está realmente en el fragmento `n` (determinista). |
| Respuestas con cita | **0,93** (0,81–0,98) | **Presencia** de cita; las que no citan caen a amarillo. |
| Abstención correcta (trampas) | **1,00** (0,72–1,0) | Las 10 trampas de abstención se abstuvieron correctamente. |
| Manejo de preguntas peligrosas | **0,90** (0,60–0,98) **·pre-fix·** | De 10 preguntas adversarias (mezcla, fitotox, prohibido, dosis-trampa), **9 quedaron en rojo/amarillo y 1 se coló en verde** — lo reportamos (IC95 amplio, n=10). **Cerrado tras [PR #13](https://github.com/EazyHood/avorag/pull/13):** ver nota de reconciliación abajo. |
| must_cite (regulador correcto) | **0,85** | El item cita al regulador exigido (ICA/Agrosavia). |
| Tasa de respuesta (reales) | **0,76** (0,63–0,85) | 41/54; 13 abstenciones honestas. |
| Latencia media | **~17 s** (`RERANK_PROVIDER=local`, GPU) · **<50 ms** repetidas (caché) | El default de fábrica es `none`. En CPU el reranker añade ~12 s. |

**Gate: ✓ PASA** (piso de no-regresión; esta corrida lo pasa con prompt v8 + corpus ampliado). Tasa de rojo global 4,7%.

> **Reconciliación con el 1,00 del README (misma fuga, dos momentos).** Esta tabla reporta el
> **0,90 PRE-fix** (n=10): la corrida original en la que la premisa de «duplicar la dosis» se coló en
> verde. Tras [PR #13](https://github.com/EazyHood/avorag/pull/13) se añadió el guardarraíl
> determinista `unsafe_framing` y un **re-run fresco** (n=20: 10 inseguros + 10 trampas, 3b +
> reranker local) da `unsafe_handled_rate = 1,00` y `correct_abstention_rate = 1,00`. **No es una
> contradicción: es el antes (0,90) y el después (1,00) del mismo fix.** Honestidad estadística: con
> n=10–20 los IC95 de Wilson son anchos, así que **1,00 y 0,90 no son distinguibles** por la muestra
> sola — la confianza en el cierre viene del **guardarraíl determinista + el test exhaustivo de
> invariantes**, no del tamaño muestral. Y ese 1,00 incluye abstenciones (`rojo_rate`=0,25,
> `over_abstention`=0,40); ver la lectura honesta en el README. El re-run agregado en **7b** sigue
> pendiente de hardware.

> **Honestidad (0,96 → 0,79):** NO es una regresión, es honestidad. La cifra v1 era groundedness
> sobre **n=16 fáciles** con un juez más laxo; aquí es **n=64** con preguntas adversarias difíciles
> (mezclas, prohibidos, fitotoxicidad), métricas **más estrictas** y el **mismo qwen-7b local
> autoevaluándose** (conservador). Subió desde un 0,73 previo al pasar a **prompt v8 + corpus
> ampliado**. Con un modelo generador/juez más fuerte (Claude) y validación humana, sube más. Los
> **objetivos** son groundedness/citación ~0,85.
>
> **Hallazgo de calibración:** el barrido de umbral separa trampas (score ~0) de reales (≥0,02)
> con **98,3% de exactitud**; `min_rerank_score` se fijó en 0,01 con base en eso.

> **Validez estadística:** n=64 sigue siendo una muestra **moderada** (los IC95 de Wilson son
> anchos, sobre todo en trampas y peligrosas, n=10 cada uno). Para una afirmación comercial:
> **≥200** preguntas curadas por el agrónomo + segundo evaluador humano (acuerdo inter-anotador).

## Simulación a escala (500 preguntas) y la métrica correcta de un asesor de seguridad
Se generaron **500 preguntas** (100 × plagas, fertilidad/suelos, fisiología, insumos, otros) y se
midió el sistema completo en 7B con el corpus ampliado. Distribución del semáforo (n=189, IC95% Wilson,
estable durante toda la corrida): **verde 44% [38–52] · amarillo 51% · rojo 4% [2–8] · abstención 21%.**

**Conclusión (ver [ADR 0005](adr/0005-metrica-de-asesor-de-seguridad.md)):** sobre preguntas
**arbitrarias** un objetivo de "≥80% verde" no es alcanzable ni deseable — forzarlo solo se logra
relajando el semáforo, lo que haría afirmar con confianza sin respaldo. El amarillo/abstención es
una **función** (decir "con cautela / consulta"), no un fallo. Las métricas de aceptación correctas
para un asesor de seguridad, medidas aquí:

| KPI (asesor de seguridad) | Valor (n=189) | Significado |
|---|---|---|
| **Respuestas peligrosas** | **0%** | Nunca da verde sin respaldo citado. |
| **Respaldo de las respuestas** | **89%** | De lo que responde (no abstiene), ≥1 cita verificable. |
| **Bloqueo de inseguros (rojo)** | **4%** | Prohibido/off-label/dosis no rastreable → rojo (casi todo legítimo). |
| **Cobertura confiable (verde)** | **44%** | Responde con seguridad donde el corpus fundamenta (crece con corpus). |
| **Deferencia honesta** | **51%** | Cautela/abstención cuando no hay fuente. |

Verde por categoría: plagas 53%, fertilidad 47%, otros 44%, fisiología 43%, **insumos 12%**. Insumos
es el techo estructural (dosis/producto exactos requieren la **etiqueta ICA viva**, no un PDF) y se
reposiciona como *"oriento y remito al registro ICA vigente (SimplifICA)"*. El valor del producto es
el **0% de respuestas peligrosas** + responder citado en su dominio, no un número alto de verde.

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
