# AvoRAG offline en el móvil — guía de construcción (exacta)

Cómo llevar AvoRAG a una **app móvil que funcione sin internet**. Pensado para que, cuando construyas
la app, **no haya sorpresas**: el punto que más rompe (el preprocesamiento de la imagen) está
especificado al detalle.

## Arquitectura offline (por qué así)
En un teléfono sin internet **no** caben ni un VLM pesado ni un LLM de 3B ni una API en la nube. La
vía correcta —y ya probada con el modelo de madurez— es:

```
foto → clasificador on-device (ONNX, ~17 MB) → CLASE → lookup en knowledge_bundle.json → manejo citado
```

- **Visión = clasificador entrenado** (MobileNetV3 → ONNX). Diminuto, rápido, 100% offline. NO un VLM.
- **Conocimiento = bundle precalculado**. El RAG corre UNA vez en tu PC (`build_knowledge_bundle.py`)
  y deja un JSON con el manejo + citas por clase. En el móvil es un simple lookup: **sin LLM, sin red**.
- El VLM→RAG (`describe.py`) es para la fase **escritorio/web**; en el móvil no se usa (sí sirve para
  pre-etiquetar fotos al crear el dataset).

## Los 3 archivos que la app empaqueta
Generados por los scripts de este repo (todos offline en el móvil):

| Archivo | Lo genera | Qué es |
|---|---|---|
| `model.onnx` | `scripts/export_onnx.py` | el clasificador (madurez y/o patología) |
| `labels.json` | `scripts/train_vision.py` (se copia junto al `.onnx`) | orden de clases + **preprocesamiento** (input_size, mean, std) |
| `knowledge_bundle.json` | `scripts/build_knowledge_bundle.py` | manejo + citas por clase (offline) |

## ⚠️ Preprocesamiento EXACTO (la causa #1 de errores silenciosos)
La app DEBE preprocesar la foto **idéntico** al entrenamiento, o el modelo acertará en el PC y fallará
en el móvil sin avisar. Los parámetros viven en `labels.json` (`input_size`, `mean`, `std`) — léelos de
ahí, no los hardcodees. El procedimiento (igual que `src/avorag/vision/classifier.py::_preprocess_np`):

1. **Decodificar** la foto a RGB. Aplicar la **orientación EXIF** (las fotos de móvil vienen giradas;
   si no la aplicas, el modelo ve la imagen de lado y falla).
2. **Resize del lado corto** a `input_size` (224), manteniendo proporción:
   `escala = input_size / min(ancho, alto)` → nuevo tamaño `(round(ancho·escala), round(alto·escala))`.
3. **Center-crop** cuadrado de `input_size × input_size` (recorta el centro).
4. **Normalizar**: `pixel/255.0`, luego `(valor − mean) / std` por canal, con
   `mean = [0.485, 0.456, 0.406]`, `std = [0.229, 0.224, 0.225]` (ImageNet; vienen en `labels.json`).
5. **Forma del tensor**: `NCHW` = `[1, 3, input_size, input_size]`, `float32`, canales en orden **RGB**.
6. **Inferencia**: `logits = sesión.run(model.onnx, {"input": tensor})[0]` → forma `[1, num_clases]`.
7. **Softmax** sobre los logits → probabilidades. `idx = argmax`. `clase = labels.json["classes"][idx]`
   (¡ese orden es el del modelo, no lo reordenes!). `confianza = prob[idx]`.
8. **Umbral**: si `confianza < 0.55` → marca *“revisar / toma otra foto”* (no muestres un resultado
   fiable). Ese 0.55 es `VISION_MIN_CONFIDENCE`.
9. **Mostrar**: busca `knowledge_bundle.json["clases"][clase]` → enseña `manejo` + `citas` + el
   `disclaimer`. Para madurez, además puedes mostrar la **banda ±1** (etapa N–M) si las dos clases más
   probables son adyacentes.

> Errores típicos que esto evita: BGR en vez de RGB, normalización omitida o con otros mean/std, resize
> que deforma (sin center-crop), saltarse la orientación EXIF, leer las clases en otro orden.

## Runtime on-device recomendado: **ONNX Runtime Mobile**
- Android/iOS, maduro y estable; el `.onnx` exportado aquí (opset 17, eje batch dinámico) ya es
  compatible. Paquetes: `onnxruntime` (Android/iOS), o `onnxruntime_genai`/wrappers de Flutter
  (`onnxruntime` pub) / React Native (`onnxruntime-react-native`).
- **TFLite (opcional, NO recomendado de entrada):** PyTorch→TFLite es frágil (vía `onnx2tf`/`onnx-tf`
  o `ai-edge-torch`, con choques de operadores). Úsalo solo si necesitas el delegado NNAPI/CoreML y
  tras verificar paridad de salidas. ONNX cubre Android+iOS sin ese dolor.

## Pasos para AÑADIR la identificación de PLAGAS (lo que falta: el dataset = tu foso)
El clasificador de madurez ya existe y exporta a ONNX. Para plagas/enfermedades, **el único requisito
es el dataset** (no hay atajo offline). Pasos exactos:

1. **Recolecta y etiqueta** fotos en carpetas-por-clase (las clases salen de
   `src/avorag/vision/labels.py`, sección patología):
   ```
   data/vision/patologia/
       trips/            antracnosis/     rona/         acaros/
       monalonion/       marceno/         minador_hoja/ mancha_foliar/
       deficiencia_magnesio/    sano/
   ```
   - **≥100–300 fotos por clase** (con transfer learning basta para empezar; más = mejor).
   - Incluye SIEMPRE la clase `sano` (hojas/frutos sin síntomas) para que el modelo aprenda a decir
     “no hay problema”.
   - Foto **cercana y enfocada** de la zona afectada, con buena luz, fondo simple.
   - **Evita fuga:** no metas muchas fotos casi idénticas del MISMO espécimen; si lo haces, que
     compartan un prefijo de nombre y sepáralas tú entre train/val (el split por defecto es por imagen).
   - Puedes **pre-etiquetar** con el VLM→RAG de escritorio (`/api/vision/health`) y luego validar a mano.
2. **Entrena** (reusa el pipeline de madurez, sirve para cualquier carpeta-por-clase):
   ```
   uv sync --extra vision
   uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128   # GPU Blackwell
   uv run python scripts/train_vision.py --data-dir data/vision/patologia --out models/vision_pat --epochs 15
   ```
3. **Exporta a ONNX:**
   ```
   uv run python scripts/export_onnx.py --model models/vision_pat/model.pt
   ```
4. **Regenera el bundle** (ya cubre madurez y patología):
   ```
   uv run python scripts/build_knowledge_bundle.py
   ```
5. **Empaqueta** `models/vision_pat/model.onnx` + `labels.json` + `knowledge_bundle.json` en la app y
   sigue el preprocesamiento de arriba.

> Mide la calidad honestamente (como en madurez): val_acc **por grupo/espécimen** + acierto **±1** si
> defines una escala de severidad. Reporta candidatos, no veredicto; deriva al agrónomo.

## Stack de app sugerido (todo offline)
- **Flutter** (`onnxruntime` + `image` para decode/EXIF/resize) o **React Native**
  (`onnxruntime-react-native`). Empaqueta los 3 archivos como assets.
- Madurez: el modelo y el bundle ya están listos hoy. Patología: tras recolectar el dataset.
- El corpus/knowledge bundle se regenera cuando amplíes fuentes; versiona su `prompt_version` +
  `corpus_version` (van dentro del JSON) para saber con qué se construyó.

## Honestidad (lo de siempre)
- Es **apoyo de triage citado**, NO diagnóstico de laboratorio. Da candidatos y deriva al agrónomo.
- La cobertura del bundle depende del corpus (hoy varias plagas tienen poca cita → se mejora ampliando
  fuentes ICA/Agrosavia). El pipeline ya está; subir calidad = más datos (imágenes) + más corpus.
