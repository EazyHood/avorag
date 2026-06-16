# Datasets de visión — referencia verificada (jun 2026)

> Las imágenes y los pesos `.pt`/`.onnx` **no se versionan** (peso + licencia). Descárgalos aquí
> localmente. Atribución obligatoria de CC BY 4.0 en el README y la app. Ver `docs/VISION.md`.
> Licencias **verificadas con verificación cruzada** (workflow jun-2026). Lo no confirmable de fuente
> primaria se marca como ⚠️ NO verificado.

## Madurez (RECOMENDADO — listo y comercial) ✅

- **'Hass' Avocado Ripening Photographic Dataset** — Mendeley Data.
  - DOI `10.17632/3xd9n945v8.1` (V1) · 14.710 img · 800×800 `.jpg` · 5 etapas.
  - Licencia **CC BY 4.0** → comercial OK **con atribución**.
  - Cita: Xavier, P.; Rodrigues, P.; Silva, C. L. M. (2024). Mendeley Data, V1.
    doi:10.17632/3xd9n945v8.1. Artículo: *Foods* 2024, 13(8), 1150, doi:10.3390/foods13081150.
  - Fuente: https://data.mendeley.com/datasets/3xd9n945v8/1

## Patologías — NO hay dataset limpio para las plagas clave → curar propio ⚠️

**Conclusión verificada:** no existe ningún dataset público, etiquetado y con licencia clara dedicado
a las plagas clave del Hass de exportación (**trips, antracnosis, roña/scab, ácaros, monalonion**).
Lo usable es binario o diminuto; lo que cubre las patologías está bloqueado por licencia.

| Fuente | Imágenes | Clases | Licencia | ¿Comercial? | Nota |
|---|---|---|---|---|---|
| Mendeley `6zy6wxhf2v` **K‑Kotagiri** | 435 (216 enf./219 sanas) | binaria sano/enfermo | **CC BY 4.0** ✅ *confirmado en ficha* | **SÍ** con atribución | no distingue patologías; solo sano/enfermo |
| Roboflow **`suraj-azuiz/avocado-leaf-disease`** | 95 | 4 (mancha algal, ácaro Persea, daño de plaga, mildiu) | **CC BY 4.0** ⚠️ *no leído de fuente primaria (Cloudflare 403)* | SÍ **si se confirma** | único etiquetado por patología de hoja; diminuto; sin trips/antracnosis/roña |
| HuggingFace **`enalis/LeafNet`** | ~186.000 | 97 clases, 22 cultivos | **CC BY 4.0** ✅ | SÍ | **NO incluye aguacate** (confirmado) → descartar para Hass |
| **Trips palta Hass** (UNAMBA, Huamán‑Ampuero 2024) | ~3.000 | trips / sana | **CC BY‑NC‑ND 4.0** (artículo) | **NO** ⛔ | ver veredicto abajo |
| GitHub **`Camposfe1208`** (fruto) | 569 / 3.983 aum. | scab(roña), antracnosis, sano | **SIN licencia** (`license:null`) ⛔ | **NO** | el más relevante para fruto, pero no reutilizable sin permiso |
| Monalonion / Heilipus lauri | — | — | — | — | sin dataset público de imágenes |

### Veredicto del dataset de TRIPS — NO usar ⛔
- **NO está en Mendeley** (no hay DOI `10.17632/…` ni ficha). Las imágenes solo se "publican" como un
  **enlace de búsqueda** de Google Drive (`drive.google.com/drive/search?q=palta`), que ni da acceso real.
- El artículo (revista Micaela, UNAMBA, DOI `10.57166/micaela.v5.n1.2024.135`) es **CC BY‑NC‑ND 4.0**:
  **NC** prohíbe uso comercial, **ND** prohíbe distribuir derivados (un modelo entrenado lo es).
- La autora pide **"consultar con el propietario de las imágenes"**.
- → **No incorporar a producto comercial.** Única vía legal: permiso escrito de la autora
  (`161146@unamba.edu.pe`). (Hits de buscador que lo daban como "Mendeley, 300‑343/clase, sur de Asia"
  son **contaminación alucinada de otros datasets** — ignorar.)

## Plan de adquisición de datos (clasificador de patologías)

### Usar YA, solo para un PROTOTIPO de portafolio (CC BY verificado)
- **K‑Kotagiri** (435, CC BY 4.0): clasificador **binario sano/enfermo** de hoja. Único 100% verificado.
- **Roboflow `suraj`** (95, 4 clases): semilla para **ácaro Persea / daño de plaga**, *condicionado* a
  **abrir la ficha en un navegador y confirmar que dice "CC BY 4.0"** + guardar captura como evidencia.
- Es una **demo honesta**, NO un producto (cobertura y volumen insuficientes).

### Para el PRODUCTO comercial → curar dataset propio (= tu foso)
Razones verificadas: cobertura inexistente con licencia limpia; volumen insuficiente (~530 img total);
**sesgo de fondo** de los datasets de laboratorio (PlantVillage: modelo con 8 px de fondo logra 49% vs
2,6% azar; 99% en lab → 33‑40% en campo); y control legal total.

**Cuántas imágenes** (Shahinfar et al. 2020): la curva se aplana en **150–500 img/clase**.
30–50 = piloto que arranca · 100–200 = usable · **150–200 reales/clase = objetivo** · >500 = rinde poco.
El transfer learning (MobileNetV3/EfficientNet) es lo que permite estos números bajos.

**Clases candidatas:** antracnosis, roña/sarna (*Sphaceloma perseae*), mancha foliar por alga,
cercospora (*Pseudocercospora purpurea*), oídio/mildiu, daño por ácaro (perseamite), trips, monalonion,
**+ "hoja sana" robusta**.

**Captura (clave: combatir el sesgo de fondo):** fondos **reales y variados** (NO cartulina), luz de día
difusa (evitar sol duro), lesión centrada/nítida (haz y envés), **muchas muestras distintas** (no muchas
fotos del mismo individuo), distintos estadios. Metadatos: finca, fecha, variedad, diagnóstico.

**Splits sin fuga de datos:** (1) dividir train/val/test **antes** de augmentar y aumentar **solo** train;
(2) **split por grupo** (todas las fotos de un árbol/finca en el mismo conjunto, nunca repartidas).

**Etiquetado:** por agrónomo, con **doble verificación** y guía de criterios por enfermedad. Herramientas:
**carpetas por clase** (las lee `ImageFolder` directamente) o **Label Studio** (self‑host); CVAT para una
fase 2 de detección.

**Licencia del dataset resultante:** **privado** (producto comercial, recomendado) · **CC BY 4.0**
(portafolio/visibilidad) · CC0 (renuncias a crédito).

### Permisos a firmar ANTES de salir a campo (plantilla 1 página; ⚠️ borrador, valida con abogado)
1. **Permiso del productor (property release):** autoriza entrar, fotografiar el cultivo y **usar/licenciar
   las imágenes, incluido uso comercial y redistribución como dataset** (un dataset que se entrena/distribuye
   **no** es "uso editorial").
2. **Cesión de derechos del fotógrafo:** el autor de la foto es quien la toma; si no es Jhona, cesión escrita
   (work‑for‑hire) al proyecto.
3. **Consentimiento informado de datos:** qué se captura, para qué, con quién se comparte y bajo qué licencia
   (la ubicación de la finca puede ser **dato personal sensible**).
4. **Sin personas en cuadro:** encuadrar solo hoja/fruto/rama evita necesitar *model release*.

## Fuentes de verificación
- Madurez: https://data.mendeley.com/datasets/3xd9n945v8/1
- K‑Kotagiri (CC BY 4.0): https://data.mendeley.com/datasets/6zy6wxhf2v/1
- Roboflow `suraj` (verificar en navegador): https://universe.roboflow.com/suraj-azuiz/avocado-leaf-disease
- LeafNet (CC BY, sin aguacate): https://huggingface.co/datasets/enalis/LeafNet
- Trips (CC BY‑NC‑ND): https://revistas.unamba.edu.pe/index.php/micaela/article/view/134 · doi:10.57166/micaela.v5.n1.2024.135
- Fruto sin licencia: https://github.com/Camposfe1208/Avocado-fruit-diseases-classification
- Sesgo de fondo PlantVillage: https://arxiv.org/abs/2206.04374 · Cuántas imágenes: Shahinfar et al. 2020 (Ecological Informatics)
