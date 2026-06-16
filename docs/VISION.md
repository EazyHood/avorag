# Módulo de visión de AvoRAG

Identifica **madurez** o **patología** del aguacate Hass a partir de una **foto** y conecta esa
identificación con el motor RAG, que responde **citando fuentes** y con sus guardarraíles
(semáforo, control de dosis). Datos de licencias/versiones **verificados a junio de 2026**.

## Frontera de seguridad (importante)

La visión **solo identifica**. **No** recomienda dosis ni tratamiento. El consejo agronómico lo
da siempre `avorag.rag.answer()`, que aplica el semáforo 🟢🟡🔴, el guardarraíl de dosis, la
citación a fuente oficial y la abstención honesta. Así, una mala identificación nunca produce una
recomendación peligrosa: el RAG cita o se abstiene igual que con una pregunta de texto.

```
foto → [clasificador] → etiqueta (p.ej. "trips") → pregunta agronómica → answer() → respuesta citada + semáforo
```

## Arquitectura

`src/avorag/vision/`
- `schemas.py` — `VisionResult` / `VisionPrediction` / `VisionDiagnosis` (identificación, no diagnóstico).
- `labels.py` — taxonomía: cada clase → nombre en español + tipo + **pregunta** para el RAG.
- `base.py` — interfaz `VisionClassifier` (+ `DisabledVisionClassifier`).
- `fakes.py` — `FakeVisionClassifier` determinista (demo/tests, sin torch).
- `classifier.py` — `LocalVisionClassifier`: carga un **TorchScript** `.pt` + `labels.json`, GPU/CPU.
- `registry.py` — fábrica por `.env` (`none | fake | local`), igual que los proveedores de LLM.
- `bridge.py` — `classify_image()` y `diagnose()` (puente al RAG, sin reescribir el motor).

API (`src/avorag/api/routes_vision.py`):
- `POST /api/vision/classify` — solo identifica (devuelve `VisionResult`).
- `POST /api/vision/diagnose` — identifica + respuesta citada del RAG (`VisionDiagnosis`).

CLI: `avorag vision classify <foto>` · `avorag vision diagnose <foto> [-q "pregunta"]`.

## Configuración (`.env`)

```
VISION_PROVIDER=none          # none | fake | local
VISION_MODEL_PATH=models/vision/model.pt
VISION_LABELS_PATH=           # vacío = labels.json junto al modelo
VISION_DEVICE=auto            # auto | cpu | cuda
VISION_MIN_CONFIDENCE=0.55    # bajo esto → requires_review (pedir mejor foto)
VISION_IMAGE_MAX_BYTES=8000000
```

Demo sin modelo (todo el flujo funciona con identificación determinista):
```
VISION_PROVIDER=fake uv run avorag serve
```

## Decisión de licencia: torchvision (BSD), NO Ultralytics YOLO (AGPL)

El repo de referencia `aguacatia` usaba **Ultralytics YOLO**, cuya licencia open-source es
**AGPL-3.0** (verificado: `ultralytics` 8.4.x, PyPI, "AGPLv3+"). Implicación **legal real**:

- **AGPL-3.0 §13 (interacción en red)** cierra el "hueco SaaS": servir el modelo por una API/web
  obliga a **publicar todo el código fuente** del producto a los usuarios remotos.
- Ultralytics lo declara explícitamente: *"SaaS platforms, APIs, or cloud systems that use YOLO
  behind the scenes"* requieren su **Enterprise License** (precio no público, cotización a medida;
  referencia comunitaria no oficial ~5.000 USD/año — sin confirmar).

Para AvoRAG (un asistente que se sirve por API/WhatsApp) eso es un **riesgo legal directo** si algún
día es comercial y cerrado. Por eso el clasificador usa **torchvision** (código **BSD-3-Clause**,
permisivo, apto para producto comercial cerrado). Un clasificador (etiquetar la imagen completa) es
además **la herramienta correcta** aquí — no necesitamos un detector con cajas como YOLO — y
**MobileNetV3 / EfficientNet-B0** son backbones ligeros, ideales para CPU/edge.

> ⚠️ **Pesos preentrenados (zona gris transversal):** los pesos por defecto de torchvision *y* de
> YOLO se entrenan sobre **ImageNet** (liberado "solo para investigación no comercial"). Para un
> producto 100% limpio: afina sobre tu propio dataset (transfer learning) **y declara el origen**,
> o entrena desde cero con `--no-pretrained`. El código (BSD/Apache) no es el problema; los pesos sí
> conviene declararlos.

## Datasets

### Madurez — listo y con licencia comercial ✅

**'Hass' Avocado Ripening Photographic Dataset** (Mendeley Data).
- DOI: **10.17632/3xd9n945v8.1** (V1) · 14.710 imágenes, 800×800 px, `.jpg`.
- 5 etapas: *Underripe / Breaking / Ripe First Stage / Ripe Second Stage / Overripe* (478 frutos,
  3 condiciones de almacenamiento, 2 fotos/día).
- **Licencia: CC BY 4.0 → uso comercial PERMITIDO con atribución.**
- **Atribución obligatoria** (incluir en README y app):
  > Xavier, P.; Rodrigues, P.; Silva, C. L. M. (2024). *'Hass' Avocado Ripening Photographic
  > Dataset*. Mendeley Data, V1. doi:10.17632/3xd9n945v8.1. (Artículo asociado: *Foods* 2024,
  > 13(8), 1150, doi:10.3390/foods13081150 — CC BY.)

⚠️ El dataset **no viene en carpetas por clase**: son imágenes sueltas + una **planilla** (Excel)
que asigna a cada foto su etapa (Índice de Maduración 1-5). `scripts/prepare_maturity_dataset.py`
la organiza en `data/vision/madurez/<clave>/` con este mapeo verificado:
`1 Underripe→madurez_verde`, `2 Breaking→madurez_pinton`, `3 Ripe First Stage→madurez_maduro_inicial`,
`4 Ripe Second Stage→madurez_maduro_optimo`, `5 Overripe→madurez_sobremaduro`.

### Patologías — **hay que curar dataset propio** (= tu foso) ⚠️

Conclusión **honesta y verificada**: **no existe** un dataset único, grande y bien licenciado que
cubra las plagas del Hass de exportación. Lo que hay (con sus banderas):

| Fuente | Cubre | Imágenes | Licencia | Bandera |
|---|---|---|---|---|
| Roboflow `suraj-azuiz/avocado-leaf-disease` | ácaro Persea, mildiu, mancha algal | ~95 | **CC BY 4.0** | usable pero diminuto |
| Mendeley `6zy6wxhf2v` (K‑Kotagiri) | sano/enfermo (difuso) | 435 | **CC BY 4.0** | clases poco definidas, origen India |
| Dataset Trips (Perú, Huamán‑Ampuero 2024) | **trips** vs sana | 3.000 | **A VERIFICAR** | el artículo es **CC BY‑NC‑ND** → si el dataset hereda eso, **prohibido uso comercial y derivados** |
| GitHub `Camposfe1208` (fruto) | roña/scab, antracnosis | 569 | **SIN licencia** | no reutilizable (todos los derechos reservados); dataset fuera del repo |
| Monalonion, Heilipus | — | — | — | **no hay dataset público** |

Por eso el slot de patología queda **preparado pero inactivo**: el código está listo (mismo
`LocalVisionClassifier`), y se activa cuando tengas un modelo entrenado con un dataset **limpio**.
La vía recomendada para un producto comercial es **curar imágenes propias en campo** (con permiso de
los productores) → derechos limpios + cobertura de TUS plagas prioritarias. Eso es justamente el
activo que solo tú (agrónomo con acceso a finca) puedes construir. Ver `data/vision/DATASETS.md`.

## Entrenar e instalar (RTX 5060 / Blackwell)

```powershell
# 1) Instala el stack de visión (permisivo)
uv sync --extra vision
# 2) torch para Blackwell (sm_120), VERIFICADO jun-2026: usa CUDA 12.8 (cu128). cu130/CUDA 13
#    tiene problemas de compatibilidad con torch a jun-2026 → NO usar cu130.
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
#    Verifica: python -c "import torch; print(torch.cuda.get_device_capability())"  -> (12, 0)
# 3) Descarga el dataset de madurez (CC BY 4.0) de https://data.mendeley.com/datasets/3xd9n945v8/1
#    a una carpeta, p.ej. data/vision/_raw_madurez/  (imágenes sueltas + planilla de etapas).
# 4) Organízalo en carpetas-por-clase (el dataset NO viene así; lo exige ImageFolder):
uv run python scripts/prepare_maturity_dataset.py --src data/vision/_raw_madurez --out data/vision/madurez
# 5) Entrena (carpetas = clases con las claves de labels.py):
uv run python scripts/train_vision.py --data-dir data/vision/madurez --out models/vision --epochs 15
# 6) Activa en .env: VISION_PROVIDER=local, VISION_MODEL_PATH=models/vision/model.pt
```

Las *wheels* de PyTorch traen el runtime CUDA embebido: **no** hace falta instalar el CUDA Toolkit
aparte, solo un driver NVIDIA reciente.

## Formato del modelo: TorchScript hoy, ONNX para producción

- **TorchScript** (lo que usa este módulo): el camino más corto si todo el stack es PyTorch. Carga
  con `torch.jit.load`, sin necesitar la clase del modelo.
- **ONNX + ONNX Runtime** (mejora recomendada para producto): un solo `.onnx` corre en NVIDIA, CPU
  (muy optimizado), AMD, etc., y da el mejor **fallback a CPU** portable. Aviso: el fallback a CPU
  de ONNX Runtime está activo por defecto y puede degradar el rendimiento **en silencio** si un
  operador no está en el *execution provider* de GPU — fija los providers explícitamente.
- Inferencia en CPU (sin GPU): MobileNetV3‑Small / EfficientNet‑lite dan ~5–30 ms/imagen en CPU
  decente → perfectamente usable como respaldo.

## Resultados del modelo de madurez (medición honesta)

Transfer learning (MobileNetV3‑Large sobre ImageNet) → TorchScript.

| Métrica | Valor |
|---|---|
| **val_acc (split por FRUTO)** | **~0.82** |
| Clases | 5 (verde → sobremaduro) |
| Split | 478 frutos → 407 train / 71 val (validación sobre frutos NO vistos) |

> **Por qué el split es por fruto y no por imagen (honestidad de la cifra):** el dataset tiene ~478
> frutos físicos, cada uno fotografiado por sus 2 lados (a/b) durante varios días (~30 imágenes por
> fruto). Un split aleatorio **por imagen** metería el MISMO fruto en train y val → el modelo
> memorizaría el fruto y el val_acc saldría inflado. Aquí se parte **por fruto** (`_fruit_id` en
> `scripts/train_vision.py`): se valida contra frutos que el modelo nunca vio. El número honesto
> (~0.82) quedó casi igual que el del split por imagen (~0.83), lo que **confirma que el modelo
> aprendió la madurez, no la identidad del fruto**. Con solo 71 frutos de validación hay varianza
> entre épocas (0.65–0.82); para una afirmación firme conviene una validación mayor.

## Limitaciones honestas

- El modelo de **madurez** es entrenable hoy (dataset CC BY 4.0). El de **patología** necesita un
  dataset curado: hasta entonces, `VISION_PROVIDER=local` solo tiene sentido para madurez.
- La identificación es **una ayuda**, no un diagnóstico: por debajo de `VISION_MIN_CONFIDENCE` el
  resultado marca `requires_review` y no fuerza una pregunta al RAG.
- Confianza ≠ certeza: confírmalo siempre con el agrónomo (el `disclaimer` lo dice en cada salida).

## Resumen de licencias del stack

| Componente | Licencia | ¿Comercial cerrado? |
|---|---|---|
| Código AvoRAG | MIT | ✅ |
| torch / torchvision | BSD‑3 | ✅ |
| ONNX Runtime / ONNX | MIT / Apache‑2.0 | ✅ |
| Dataset madurez (Mendeley) | CC BY 4.0 | ✅ con atribución |
| Ultralytics YOLO | **AGPL‑3.0** | ❌ (requiere Enterprise) — **descartado** |
| Pesos ImageNet (torchvision) | no comercial en origen | ⚠️ afinar/declarar |
