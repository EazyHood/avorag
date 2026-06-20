# Modo ONLINE del APK con un LLM **gratis** (backend AvoRAG)

Cómo hacer que la app móvil, **cuando hay internet**, responda mucho mejor — usando un LLM en la nube
**gratis** y los feeds regulatorios en vivo, **sin coste y sin clave dentro del APK**.

## Arquitectura (la clave: el APK NO lleva el modelo ni la clave)

```
APK (Flutter)
  ├── OFFLINE → modelo pequeño on-device (extractivo + guardarraíl base)
  └── ONLINE  → HTTPS a TU backend AvoRAG (FastAPI)  ──►  LLM gratis + feeds en vivo + "0 errores"
```

- El **backend AvoRAG** (este repo, con su `Dockerfile`) corre el RAG + los guardarraíles + el cruce
  regulatorio. Ahí vive el contrato **"0 errores"**.
- La clave del LLM vive **solo en el backend** (variable de entorno). El APK se autentica contra el
  backend con **su propio token** (`API_KEYS` del repo), nunca con la clave del LLM.
- "Online sirve mejor" = el backend usa un **modelo más grande** + **dato regulatorio fresco** que el
  modelo on-device.

> ⚠️ Nunca metas la clave del LLM en el APK: se descompila en minutos y te queman la cuota/te facturan.

## 1) LLM gratis vía `OPENAI_BASE_URL` (lo que se acaba de habilitar)

El provider `openai` ahora acepta un `base_url` opcional → apunta a **cualquier endpoint
OpenAI-compatible**. Eliges proveedor cambiando **solo el `.env`**, sin tocar código:

| Proveedor | `OPENAI_BASE_URL` | `OPENAI_LLM_MODEL` (ej.) | Dónde sacar la key |
|---|---|---|---|
| **Groq** ⚡ | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | console.groq.com (gratis) |
| **Google Gemini** 🇪🇸 | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.0-flash` | aistudio.google.com (gratis) |
| OpenRouter / Cerebras | su URL `/v1` | modelo abierto `:free` | su consola |
| Tu proxy **GLM** | la del proxy | el que exponga | ya lo tienes |

```bash
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
OPENAI_API_KEY=<tu_key>
OPENAI_LLM_MODEL=gemini-2.0-flash
```
> Verifica los **límites del free tier** (req/min, tokens/día) en cada consola — cambian seguido.

## 2) Embeddings (el detalle que NO se puede ignorar)

El embedding de **consulta** debe ser el **mismo** (proveedor + modelo + dimensión) con que se **ingirió
el corpus** — si no, la recuperación se rompe. Dos caminos:

- **A) Embeddings locales (CPU)** — mantienes `bge-m3` (con el que probablemente ingeriste):
  ```bash
  EMBEDDING_PROVIDER=local   # sentence-transformers (BAAI/bge-m3); requiere `uv sync --extra local`
  ```
  Pega: arrastra `torch` → imagen grande y RAM (~1.5–2 GB). Usa un host con margen (Fly.io / Oracle).
- **B) Embeddings en la nube (ligero, sin torch)** — re-ingiere el corpus con Gemini y consulta igual:
  ```bash
  EMBEDDING_PROVIDER=openai
  # usa el MISMO OPENAI_BASE_URL/KEY de arriba (Gemini)
  EMBEDDING_MODEL=text-embedding-004
  EMBEDDING_DIM=768
  ```
  Imagen pequeña → cabe en hosts de 512 MB (Render free). **Re-ingiere** el corpus con esta embedding
  antes (`uv run avorag ingest …`), porque cambia la dimensión.

`RERANK_PROVIDER=none` para el free tier (el reranker local es pesado en CPU; el repo ya lo soporta apagado).

## 3) Base de datos gratis (pgvector)

`DATABASE_URL` a un Postgres con pgvector en free tier:
- **Supabase** o **Neon** (ambos gratis, pgvector incluido). Luego `uv run avorag db upgrade`.

## 4) Hosting gratis del backend (usa el `Dockerfile` que ya está)

| Host | Notas |
|---|---|
| **Hugging Face Spaces** (Docker) | el más fácil para demo/portfolio; gratis |
| **Render** (free) | deploy del Dockerfile; 512 MB RAM → usa el camino **B** (embeddings nube) |
| **Fly.io** | más RAM en free; aguanta el camino **A** (bge-m3 local) |
| **Oracle Cloud Always Free** | VM ARM potente; el más capaz gratis |

El contenedor expone `:8000` y arranca `uvicorn avorag.api.app:app` (ya en el `Dockerfile`).

## 5) `.env` de ejemplo — backend gratis "todo nube ligero" (Gemini)

```bash
# LLM (generación) — Gemini gratis
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
OPENAI_API_KEY=AIza...                # clave de Google AI Studio (SOLO en el backend)
OPENAI_LLM_MODEL=gemini-2.0-flash
# Embeddings — Gemini (re-ingiere el corpus con esto)
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-004
EMBEDDING_DIM=768
RERANK_PROVIDER=none
# Datos
DATABASE_URL=postgresql+psycopg://...supabase-o-neon...
# Seguridad: el APK se autentica con uno de estos tokens (NO con la key del LLM)
API_KEYS={"token-del-apk":"finca-demo"}
# Modo online en vivo (feeds regulatorios)
AVORAG_ONLINE_FEEDS=1
EXPORT_MARKET=eeuu                     # o ue
```

## 6) El APK solo necesita
- La **URL** del backend (`https://tu-backend/api/chat`).
- Su **token** (`Authorization: Bearer token-del-apk`).
- Nada de claves de LLM. Si el usuario está offline, el APK usa el modelo on-device; si está online,
  pega al backend y recibe la respuesta **ya pasada por el "0 errores"**.

## Realidad
Free tier es perfecto para **portfolio/demo** y un piloto pequeño. Para un cliente real de pago
(privacidad de datos de finca, sin rate limits) querrás un tier pagado o self-hosting — pero **arrancas
gratis y migras sin tocar código** (solo el `.env`).
