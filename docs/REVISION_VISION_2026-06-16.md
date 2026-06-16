# Revisión de calidad — Módulo de visión (2026-06-16)

> Revisión read-only multi-agente (4 dimensiones + verificación adversarial) hecha por la **Cuenta 1**
> sobre el módulo de visión commiteado (#3/#4). 18 hallazgos confirmados, 1 incierto, 1 falso positivo
> descartado. **Reparto:** la Cuenta 1 ya arregló los 4 de UI (`index.html`); el resto es lane de la
> **Cuenta 2** (impl). Cada ítem tiene file:línea y fix sugerido.

## Resumen
- **1 ALTA** (A1, DoS por tamaño de cuerpo en el upload). El resto media/baja. Módulo sano en general.
- ✅ = ya arreglado por Cuenta 1 (UI). ⬜ = pendiente, lane Cuenta 2 (impl).

## 🔴 ALTA
- ⬜ **A1 — El tope de imagen no limita el cuerpo recibido (DoS).** `routes_vision.py:_read_image` lee
  `file.read(max+1)` PERO Starlette ya materializó el multipart (derrame a `%TEMP%`). No hay tope global
  de cuerpo. **Fix:** middleware ASGI que rechace por `content-length`/conteo en `receive()` antes de
  tocar el body; opcional `--limit-max-requests`/proxy. Lane: Cuenta 2 (`routes_vision.py`/`app.py`).

## 🟡 MEDIA (lane Cuenta 2 salvo donde diga)
- ⬜ **M1 — ZeroDivisionError en `train_vision.py`** si el split deja train vacío (`:118` y `:191`
  `running/len(...)`). Fix: abortar si `len(group_ids)<2`; `n_val_groups=min(.., len-1)`; `max(1, len)` en :191.
- ⬜ **M2 — Split por fruto no estratifica por clase** (`:112-123`): una clase rara puede quedar 0 en
  train o val. Fix: estratificar por clase mayoritaria del grupo o validar cobertura de clases tras el split.
- ⬜ **M3 — Form de `/diagnose` sin `max_length`/`pattern`** (`routes_vision.py:65-90`) vs AskRequest.
  Fix: `question` max ~2000, `country` `^[A-Z]{2}$`, `soil_type` 64, `region` 80 → 422.
- ⬜ **M4 — Fuga de detalle interno en error del stream** (`routes_chat.py:74-75` reenvía `str(exc)` →
  puede filtrar el DSN de Postgres). Fix: loguear server-side, mensaje genérico al cliente (detalle solo en dev).
- ⬜ **M5 — Skew resize train/inferencia** (`classifier.py:_preprocess_np` usa BICUBIC default; `train`
  usa BILINEAR). Fix: `img.resize(..., resample=Image.BILINEAR)`.
- ⬜ **M6 — `prepare_maturity_dataset.py` no valida `fn_col != st_col`** (`:113-115`). Fix: abortar si
  coinciden; excluir fn_col al elegir st_col; preferir match exacto; imprimir muestra del mapeo.
- ⬜ **M7 — `vision classify --top-k 0/neg` crashea con el fake** (`fakes.py:32,42`). Fix: clampar en
  `bridge.classify_image` `top_k=max(1,min(top_k,5))` (compartido CLI+HTTP) o guarda en el fake.
- ⬜ **M8 — Modelo/labels corruptos → HTTP 500 feo** (rutas solo capturan `ValueError`; `available`
  solo mira `.exists()`). Fix: capturar `(FileNotFoundError, json.JSONDecodeError, KeyError, RuntimeError)`
  → 503 claro; idealmente `available` valida labels.json y/o precargar en el lifespan.
- ✅ **M9 — XSS por esquema en `c.url`** (`index.html`). **HECHO** (Cuenta 1): se valida
  `^https?://` antes de pintar el `<a>`. *Defensa en profundidad (validador Pydantic en ingesta + CSP)
  = lane Cuenta 2, opcional.*
- ✅ **M10 — UI no envía `X-Api-Key` (401 en prod) + errores poco claros** (`index.html`). **HECHO**
  (Cuenta 1): `httpErrMsg` mapea 401/429 a mensajes claros en foto y chat. *Decisión de fondo (inyectar
  key / no servir UI en prod con auth) pendiente de producto.*

## 🟢 BAJA
- ⬜ **B1 — Colisión de basename pierde datos en `prepare_maturity_dataset.py`** (`:123-126`, `:147-151`);
  además `counts[key]` sobre-cuenta. Fix: detectar colisión, desambiguar destino, contar tras materializar.
- ⬜ **B2 — `best_acc >=` reescribe el modelo en empates** (`train_vision.py:192`). Fix: `>` (init `-1.0`)
  o `acc > best or not best_path.exists()`.
- ⬜ **B3 — Log "Split por fruto (sin fuga)" miente** si no hay patrón Mendeley (`:54-57`,`:124-128`).
  Fix: detectar `len(group_ids)==len(samples)` y avisar "split por imagen"; texto condicional; `--group-regex`.
- ⬜ **B4 — No se valida nº de clases del modelo vs labels.json** (`classifier.py`). Fix: comparar
  `len(probs)`/`get_outputs()[-1]` con `len(classes)`; `log.warning` si difieren.
- ✅ **B5 — 4xx/429 mostrados como error genérico** (`index.html`). **HECHO** (Cuenta 1): se parsea el
  `detail` del backend.
- ✅ **B6 — ObjectURL de la miniatura nunca se revoca** (`index.html`). **HECHO** (Cuenta 1):
  `revokeObjectURL` al cargar la imagen.

## ❔ Incierto (revisar a mano)
- **U1 — `_ensure_loaded` sin lock** (`classifier.py`). La carrera descrita NO se da hoy (no es `Depends`,
  corre en serie en el event loop); solo importaría con `run_in_threadpool` futuro. Fix defensivo opcional:
  `threading.Lock` o precargar en el lifespan. Lane Cuenta 2 si se decide.

## Descartado
- **XSS vía `c.doi`** (`index.html`): FALSO, el href tiene `https://doi.org/` hardcodeado.

---
*Hallazgos verificados contra el código real; los duplicados (B1≡by_name, B2≡best_acc) se consolidaron.*
