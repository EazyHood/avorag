# Deuda técnica y diferidos a Ruta 🅱️

> Esta lista existe para que **nada quede omitido en silencio**. Surge de una auditoría
> adversarial del scaffold (4 revisores + verificación de cada hallazgo). Lo que era barato
> y correcto se arregló en v0.1 (abajo); el resto son decisiones legítimas de fase 🅱️
> (producción / multi-tenant / WhatsApp), no olvidos.

## ✅ Corregido en v0.1 (tras la auditoría)
- **Guardarraíl de dosis:** eliminado el falso positivo de número-suelto (un número del
  contexto sin unidad de dosis ya no "respalda" una dosis). Tests añadidos.
- **Juez de fidelidad fail-safe:** si el juez falla devuelve `None` (no 1.0) → semáforo
  AMARILLO, nunca un VERDE falso.
- **Sin citas → AMARILLO:** una respuesta no-abstenida sin citas ya no sale VERDE.
- **Abstención etiquetada:** se usan `OUT_OF_COLLECTION` (cultivo ajeno, corta antes de
  gastar LLM) y `OUT_OF_CONTEXT` (sin señal agronómica), no solo `OUT_OF_CONTENT`.
- **/ready** ya no filtra la traza/URL de la excepción al cliente.
- **Validación de entrada** en `AskRequest` (`tenant` patrón, `country` 2 letras).
- **Búsqueda léxica tolerante a fallos** (una query FTS malformada cae al lado denso).
- **Gate de evaluación** solo exige citación si hubo respuestas reales contestadas.
- **CLI:** valida que exista `migrations/`; `ingest` acepta `--pais`/`--cultivo`.
- **Ingesta** reporta `contextual_failures` (no más pérdida silenciosa de contexto).
- **CORS** configurable (restrictivo por defecto).
- **Ollama**: acceso a respuestas por atributo (`.embeddings`, `.message.content`).

## ⏳ Diferido a Ruta 🅱️ (con su disparador)
| Tema | Por qué se difiere | Disparador para implementarlo |
|---|---|---|
| **Autenticación de API** (OAuth2/JWT) + tenant desde token | Ruta 🅰️ es demo de 1 tenant | Primer tenant real / exponer la API |
| **Aislamiento de tenant en BD** (tabla `tenants` + FK / RLS) | Hoy el filtro es a nivel de app | Multi-tenant real |
| **Rate limiting** (slowapi) | No hay exposición pública aún | API pública o piloto |
| **Auditoría con cola + reintentos** (Redis) | Commit síncrono es tolerable en 🅰️ | WhatsApp / volumen / SLA |
| **Re-embedding blue-green** (CLI) al cambiar `EMBEDDING_DIM` | Cambiar de modelo es raro y manual hoy | Cambio de modelo de embeddings (ver ADR 0004) |
| **Automatización de vigencia ICA** (job + fuente ICA) | El filtro por `vigencia` ya existe; marcar es manual | Acceso a datos del ICA |
| **Health checks profundos** (Ollama, índices) + monitoreo/alerting/on-call | Innecesario en local | Despliegue en servidor |
| **Normalización de unidades de dosis** (kg↔g, cc↔ml) | v1 compara número con unidad presente | Falsos negativos por equivalencia en el piloto |
| **Validación de coherencia país en ingesta** + geofiltro por-tenant | 1 país/1 tenant en 🅰️ | Multi-país (fase España/UE) |
| **Hardening anti prompt-injection** (sanitización del input) | El LLM-judge + geofiltro mitigan parte | WhatsApp abierto al productor |
| **Contrato Answer documentado** para consumidores externos | FastAPI ya expone `/docs` y `/openapi.json` | Integración del webhook WhatsApp |

## Notas de seguridad operativa
- **Nunca** `LOG_LEVEL=DEBUG` en producción: los SDKs podrían registrar cabeceras.
- `docker-compose.yml` trae credenciales de DEV (`avorag:avorag`); en prod usa secretos.
