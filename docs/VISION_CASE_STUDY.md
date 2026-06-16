# Caso de estudio — Capa de visión multimodal para AvoRAG

> Addendum de portafolio del módulo de visión. Se puede integrar luego en `CASO_DE_ESTUDIO.md` /
> `CASE_STUDY.md`. El modelo de madurez ya está **entrenado** (val_acc ≈ 0.83); el módulo, la API,
> la UI, los tests y los datos están construidos y verificados.

**En una frase:** convertí un asistente RAG agronómico **solo-texto** en uno **multimodal** — el
productor fotografía una hoja o un fruto, un clasificador lo identifica, y el motor RAG existente
responde **citando la fuente oficial** y con sus guardarraíles de seguridad.

## El problema

El aguacate Hass de exportación se rechaza por defectos visuales (trips, antracnosis, lenticelosis,
punto de madurez). El productor en campo **no sabe nombrar** la plaga, pero **sí puede fotografiarla**.
AvoRAG, al ser solo-texto, tenía un punto ciego estructural: el conocimiento de plagas vive en las
**figuras** de las guías, no en su texto.

## La solución

```
foto → [clasificador de visión] → etiqueta → pregunta agronómica → answer() → respuesta citada + semáforo 🟢🟡🔴
```

Un microservicio de clasificación se enchufa al pipeline RAG **sin reescribirlo**: la etiqueta
detectada se transforma en una pregunta que entra al `answer()` ya existente (igual que hoy se
enriquece con suelo/región).

## Decisiones de ingeniería destacadas

1. **Licencia como decisión de arquitectura.** El repo de referencia usaba **Ultralytics YOLO
   (AGPL-3.0)**, cuya cláusula de red obliga a abrir todo el código en un SaaS (o pagar licencia
   Enterprise). Para un asistente que se sirve por API/WhatsApp eso es un riesgo legal directo. Elegí
   **torchvision (BSD-3)** con un backbone ligero (MobileNetV3/EfficientNet): permisivo, apto para
   producto comercial cerrado, y **un clasificador es la herramienta correcta** (etiquetar la imagen
   completa) — no hace falta un detector con cajas.
2. **Frontera de seguridad explícita.** La visión **solo identifica**; **nunca** recomienda dosis ni
   tratamiento. El consejo lo da el RAG con su semáforo, guardarraíl de dosis, citación a fuente y
   abstención honesta. Así, **una mala identificación no puede producir una recomendación peligrosa**.
3. **Modelo-agnóstico y portable.** El clasificador carga un **TorchScript** `.pt` + `labels.json`
   (clases data-driven), con GPU/CPU automático y fallback a CPU. Añadir una clase = editar datos, no
   código. Vía de mejora documentada: export a ONNX para portabilidad multivendor.
4. **Proveedor intercambiable** (`none | fake | local`), igual que los proveedores de LLM/embeddings:
   un `FakeVisionClassifier` determinista permite probar todo el flujo (API, UI, tests) sin GPU.

## Rigor de datos y legalidad (verificado)

- **Madurez:** dataset **CC BY 4.0** ('Hass' Avocado Ripening, Mendeley `10.17632/3xd9n945v8.1`,
  14.710 imágenes) → uso comercial con atribución. Atribución incluida.
- **Patologías:** due diligence con verificación cruzada → **no existe** dataset limpio para las plagas
  clave del Hass; el de trips se **descartó** (CC BY-NC-ND + imágenes sin licencia abierta). Conclusión:
  hay que **curar dataset propio en campo** (con permisos firmados) — documentado como plan de
  adquisición. La debilidad pública es, de hecho, la **ventaja defensible** del proyecto.
- Principio aplicado en todo: **no usar datos sin licencia clara ni con licencia no comercial**.

## Verificación y calidad

- **159 tests** (unitarios del clasificador/etiquetas/puente + 6 de la API), **ruff + mypy** limpios.
- **Pipeline de entrenamiento validado end-to-end en GPU** (RTX 5060 / CUDA 12.8): entrenó → exportó
  TorchScript → el proveedor `local` lo cargó y clasificó correctamente.
- **UI** verificada (botón de foto + tarjeta de identificación con barras de confianza + respuesta
  citada), con degradación amable cuando aún no hay modelo.

## Estado y próximos pasos

- ✅ Módulo, API (`/api/vision/classify`, `/api/vision/diagnose`), CLI, UI, tests y docs.
- ✅ **Modelo de madurez entrenado** (5 etapas, MobileNetV3, dataset CC BY 4.0) — **val_acc ≈ 0.83**.
  Falta activarlo (`VISION_PROVIDER=local`) y una prueba end-to-end con foto real.
- ✅ **Export e inferencia ONNX** implementados y verificados (`scripts/export_onnx.py` + proveedor
  `onnx` con providers explícitos) — **paridad numérica con TorchScript** (Δconfianza ~1e-8).
- ⏭️ Clasificador de **patologías** con dataset propio curado (plan listo).

## Stack

Python 3.12 · FastAPI · torch/torchvision (BSD) · TorchScript · Pillow · pytest/ruff/mypy.
Frontera limpia con el motor RAG (pgvector híbrido + RRF + reranker + guardarraíles).
