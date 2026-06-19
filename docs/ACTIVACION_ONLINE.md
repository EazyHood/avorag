# Activación de las capacidades del modo ONLINE

Qué quedó implementado (código + tests) y **cómo se activa** cada cosa. Lo que está implementado
funciona en cuanto pones su variable de entorno; lo marcado **(residual)** necesita una dependencia
o decisión de infraestructura tuya. Todo está **apagado por defecto** ⇒ no cambia el modo offline.

## 1. Guardarraíl en vivo + feeds
```bash
AVORAG_ONLINE_FEEDS=1          # activa el cruce freshness+regulatorio en el pipeline
```
Refrescar feeds (cron):
```bash
python scripts/refresh_feeds.py --mode fake     # demo determinista
python scripts/refresh_feeds.py --mode real     # usa conectores reales (abajo)
```
Conectores **reales** por feed (sin scraping frágil; el operador alimenta el dato oficial):
```bash
AVORAG_FEED_ICA_FILE=/datos/ica.csv             # CSV oficial → normalizado a canónico
AVORAG_FEED_LMR_UE_URL=https://tu-host/lmr.json # o JSON ya canónico (HttpJsonProvider)
# Variables por feed: ICA, IDEAM, LMR_UE, TOL_EEUU  (AVORAG_FEED_<FEED>_FILE / _URL)
```
Columnas CSV esperadas (por defecto, configurables): ICA `ingrediente_activo,registro_ica,estado,cultivo`;
LMR_UE `ingrediente_activo,lmr_mg_kg,aprobado`; TOL_EEUU `ingrediente_activo,tolerancia_ppm,tiene_tolerancia`.
**(residual)** Scrapers específicos de portales que no exponen export (Power BI de SimplifICA, etc.):
hay que escribir el parser de ESE formato, o exponerlo como CSV/JSON.

## 2. Normas versionadas de las calculadoras
```bash
python scripts/seed_norms.py                    # siembra los defaults en norm_tables (idempotente)
AVORAG_ONLINE_NORMS=1                            # las calc online resuelven umbrales desde norm_tables
```
Hoy cableado a materia-seca (objetivo→umbral) y salinidad (portainjerto→CEe), estampando `norm_version`.
**(coordinar con offline)** Cablear el resto (foliar, encalado, GDD) exige hacer opcionales esos
parámetros en `agro_calc.py` (núcleo compartido con el calc Dart) → coordinar para no romper la paridad.

## 3. HITL — control de rol
```bash
AVORAG_HITL_REVIEWERS=agro1,agro2               # solo estos reviewer_id firman decisiones (vacío = dev abierto)
```

## 4. Rate-limit distribuido (multi-worker)
```bash
REDIS_URL=redis://localhost:6379/0              # usa Redis si está; si no, memoria por proceso
```
El backend (`online/ratelimit.get_rate_limiter()`) ya elige Redis o memoria. **(activación)** Sustituir
el limitador en `api/auth.py` por `get_rate_limiter()` es un cambio de una línea (núcleo: avisar).

## 5. Auth OAuth2/OIDC (JWT)
```bash
AVORAG_JWT_SECRET=...                            # verifica Bearer JWT HS256 (clave simétrica) → tenant del token
```
`online/jwt_auth.verify_hs256` ya valida firma/exp/nbf. **(residual)** IdPs RS256/JWKS (Auth0, Keycloak con
clave pública): instalar `pyjwt[crypto]` y la URL del JWKS del IdP.

## 6. Observabilidad
`online/observability.span(...)` cronometra y emite `span_start/span_end` al log estructurado **ya**.
**(residual)** Trazas distribuidas OpenTelemetry: instalar `opentelemetry-sdk` + exportador OTLP y
envolver `span()` con el tracer; apuntar a tu backend (Tempo/Jaeger/Datadog).

## 7. Eval con juez independiente (rompe la autoevaluación)
**(necesita tu clave)** No se puede correr sin `ANTHROPIC_API_KEY`. Script listo:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/eval_independent_judge.py            # juez=Claude, generador=el local (ollama)
python scripts/eval_independent_judge.py --cloud    # generador y juez en Claude (modelos distintos)
```
Tras correr, `eval/reports/last_report.json` → `provider_info.judge` independiente; actualiza el README.

## 8. Sincronización offline
`GET /api/sync/manifest` ya devuelve `corpus_version` + `norm_version` firmados.
**(coordinar con offline)** Los artefactos `knowledge_bundle` y `vision_model` (ONNX) se añaden cuando
el lado offline publique su versión/hash/URL (es su dominio).
