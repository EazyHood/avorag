# Plan de resolución de lo NO-código

Hay límites de AvoRAG que **no se arreglan tecleando código** (un feed en vivo, una licencia comercial,
un laboratorio, un corpus de otro país, un segundo evaluador humano). Negarlo sería deshonesto; dejarlos
como "imposibles" sería rendirse. Este documento **resuelve cada uno correctamente**: deja el camino
**concreto, con fuentes reales, responsable y esfuerzo**, y ejecuta las partes que sí están a mano.

Convención: **Responsable** = quién lo hace (👤 Jhona/agrónomo · 💻 dev · ⚖️ legal/negocio · 🤝 cliente).
**Estado**: ✅ resuelto · 🟡 listo-para-ejecutar (plan + interfaz) · ⏳ requiere recurso externo.

---

## 1. Datos en vivo (vigencia ICA, LMR de destino, clima, precios)
**Problema:** el sistema cita un PQUA de mar-2022 y no consulta el estado vivo; los LMR/registros cambian.

**Resolución correcta (🟡 plan + interfaz):** no se inventa el dato, se **conecta la fuente oficial**:
- **Vigencia/registro ICA →** portal **SimplifICA** (consulta de registros de plaguicidas) y la base
  **Plaguicidas Químicos de Uso Agrícola (PQUA)** del ICA. No hay API pública estable; el camino real
  es un **scraper/descarga programada mensual** del PQUA + diff contra el corpus, que marque `caducado`
  los registros que desaparezcan. **Responsable:** 💻 dev (job mensual) + 👤 validación. **Esfuerzo:** 2-3 días.
- **LMR UE →** **EU Pesticides Database** (`ec.europa.eu/food/plant/pesticides/eu-pesticides-database`):
  tiene descarga de datos; cablear una sincronización por par activo-cultivo. **LMR/tolerancia EE.UU. →**
  **40 CFR Parte 180** vía **eCFR** (`ecfr.gov`, hay API JSON) — codificar las tolerancias por "avocado".
- **Clima →** **IDEAM** (Colombia) o una API meteo (Open-Meteo es gratis y sin clave) para alimentar el
  **Kc/ETo** de la calculadora de riego y las ventanas de Stenoma. **Precios →** boletines SIPSA (DANE).
- **Interfaz a dejar lista (💻, 1 día):** un proveedor `LiveDataProvider` con default `none` (hoy) y
  método `vigencia(registro)`, `lmr(activo, mercado)`, `clima(lat,lon)`; cuando exista el feed, se
  enchufa sin tocar el resto. Mientras tanto, el sistema **avisa "verifica en SimplifICA"** (ya lo hace).

> Honesto: en una app **offline** el dato en vivo es imposible en el teléfono; vive en el build del
> bundle (se regenera al sincronizar) o en la versión web/servidor.

## 2. OCR de la Resolución ICA 1507/2016 (PDF escaneado)
**Estado: ✅ resuelto por otra vía** (mejor que OCR a ciegas): se ingirió una **síntesis del texto
oficial** (`data/corpus_curado/ica_1507_2016_cuarentenarias.md`) con las cuarentenarias y el régimen.
- Si además quieres el OCR del PDF original: instala **Tesseract** (`winget install UB-Mannheim.TesseractOCR`)
  + `uv sync --extra ocr`, y `uv run avorag ingest data/corpus/ica_resolucion_1507_2016.pdf --ocr`.
  **Responsable:** 👤 (instalar el binario) + 💻. **Esfuerzo:** 1 hora.

## 3. Licencia del corpus (CC-BY-NC → uso comercial)
**Problema:** el núcleo curado (Agrosavia) es **CC-BY-NC**: prohíbe uso comercial sin permiso escrito.

**Resolución correcta (⚖️ negocio):**
1. **Auditoría por fuente** (`data/corpus_manifest.json` → campo `licencia`): separa lo usable
   comercialmente de lo que no. Hoy: público-ICA/MinAgricultura = **OK comercial** (obra pública);
   Agrosavia = **CC-BY-NC** (no comercial); académicas = revisar caso a caso.
2. **Dos caminos para lo CC-BY-NC:**
   - **Permiso:** solicitar autorización escrita a la **editorial de Agrosavia** (editorial@agrosavia.co)
     para uso comercial — es el mecanismo estándar de CC-BY-NC. **Esfuerzo:** correo + negociación.
   - **Sustitución:** reemplazar el contenido por **fuentes oficiales de dominio público** (ICA,
     MinAgricultura, FAO, CODEX) que cubran lo mismo, para que la versión de pago **no dependa** de
     CC-BY-NC. **Responsable:** 👤 agrónomo (curar equivalentes) + 💻 (reingerir).
3. **Mientras tanto:** la **ruta 🅰️ (portafolio/empleo) es uso NO comercial** → CC-BY-NC es válida hoy.
   El bloqueo solo aplica a la **ruta 🅱️ (producto de pago)**.

## 4. Cobertura multipaís (México / Perú / España-UE)
**Problema:** el corpus es 100% Colombia (ICA); en otra jurisdicción el registro/carencia no aplica.

**Resolución correcta (🟡 plan + estructura):** el código **ya** filtra por `country` y por tenant; falta
el **corpus por país**. Checklist de fuentes oficiales por país (lo que sustituye al ICA/PQUA):
- **México 🇲🇽:** registro de plaguicidas **RSCO** (COFEPRIS/Salud + SENASICA/SADER + SEMARNAT);
  para aguacate, **APEAM**. LMR de destino igual (UE/EE.UU.).
- **Perú 🇵🇪:** **SENASA** — Registro de Plaguicidas de Uso Agrícola.
- **España/UE 🇪🇸:** **MAPA** (Registro de Productos Fitosanitarios) + **EU Pesticides Database** (LMR).
- **Pasos por país:** (1) descargar el registro oficial → (2) `avorag ingest ... --pais MX` →
  (3) cargar sus prohibidos/destinos en `data/` → (4) validar con un agrónomo local. **Responsable:**
  👤 agrónomo del país + 💻. **Esfuerzo:** ~1-2 semanas por país (la mayor parte es curaduría).

## 5. Diagnóstico de laboratorio (qPCR antracnosis, RT-PCR sunblotch)
**Problema:** la detección fiable de infección latente (antracnosis) y del viroide (ASBVd) es **de
laboratorio**; la app describe y cita, no diagnostica.

**Resolución correcta (👤 + 🤝 flujo de trabajo, no código):** definir el **flujo triage→laboratorio**:
1. La app/agrónomo hace el **triage** (síntomas, riesgo, historial) → decide qué lotes muestrear.
2. **Envío a laboratorio** de fitopatología molecular: **laboratorios del ICA**, **Agrosavia**, y
   **universidades** con diagnóstico molecular (p. ej. Nacional, Caldas, Antioquia). Empaquetar un
   **protocolo de muestreo** (cuántos frutos/árboles, transporte en frío, cadena de custodia).
3. La app **registra el resultado** del lab y ajusta la recomendación. **Esfuerzo:** redactar el
   protocolo (1 día) + acuerdo con un laboratorio (👤). La app NO sustituye el ensayo; lo **orquesta**.

## 6. Rigor del eval (≥200 preguntas + juez independiente + 2º evaluador humano)
**Problema:** la corrección agronómica se midió sobre pocas preguntas y el juez por defecto se autoevalúa.

**Resolución correcta (💻 + 👤, parcialmente EJECUTADA):**
- **Juez independiente (✅ ya soportado):** `JUDGE_LLM_PROVIDER`/`JUDGE_LLM_MODEL` (p. ej. Claude o un
  modelo distinto) elimina la autocorrelación; `provider_info.judge` reporta si es independiente.
- **Golden ≥200 (🟡 en curso):** ampliar `data/golden/hass_v1.jsonl` con preguntas curadas y
  `expected_facts` (la corrección agronómica se calcula solo con ≥8 de esas) — ver `docs/GOLDEN_SET.md`.
  Hoy se añadió un lote; meta 200 con 👤 agrónomo revisando.
- **2º evaluador humano (protocolo, no código):** muestreo ciego de N respuestas, **rúbrica** (correcto /
  parcial / incorrecto / peligroso) por un agrónomo distinto al autor, y **acuerdo inter-evaluador**
  (Cohen's κ). Plantilla y pasos en `docs/GOLDEN_SET.md` §"Evaluación humana".
- **Re-corrida del eval (⏳ corriendo):** con 7b + reranker local sobre el corpus actual, para publicar
  números **post-fix** en el README (cierra "la tabla es pre-fix").

## 7. Multi-tenant / RLS fail-closed / usuarios (no solo API-key)
**Estado: 🟡 en curso (otra rama).** El aislamiento RLS fail-closed, el test de aislamiento y la
auth se están implementando aparte. **Plan correcto:** activar RLS **solo** tras verificar que cada
sesión fija `app.current_tenant` (ingesta, jobs, scripts); migrar de API-key a **usuarios+roles**
(agrónomo/capataz/gerente) con JWT; escribir `reviewer_id`/`review_status` en la auditoría (hoy columnas
sin uso). **Responsable:** 💻. **Disparador:** primer despliegue multi-cliente real.

## 8. Integraciones (ERP, packing, GlobalGAP, cuaderno de campo, WhatsApp)
**Problema:** la recomendación no baja a la trazabilidad del lote ni llega por el canal del capataz.

**Resolución correcta (💻 specs + data-contract, listas para construir):**
- **Cuaderno de campo / trazabilidad:** definir un **registro exportable** `{lote, fecha, producto,
  i.a., dosis, carencia, reingreso, responsable, semáforo, citas}` (CSV/JSON) que un ERP/cuaderno
  ingiera; añadir un endpoint `POST /api/aplicacion` que lo persista. Cierra la no-conformidad GlobalGAP.
- **WhatsApp (Ruta 🅱️):** webhook BSP → verificación de firma → mapeo número→tenant/finca →
  saneamiento anti-inyección → `rag.answer()` (el núcleo ya está desacoplado). **Esfuerzo:** 1-2 semanas.
- **ERP/packing/GlobalGAP:** conectores por API del ERP del cliente (caso a caso). **Responsable:** 💻 + 🤝.

## 9. Visión: dataset de plagas (el foso) + trade-off modelo local/nube
**Problema:** la foto-patología necesita un dataset que no existe; llava-7b es flojo y Claude rompe el offline.

**Resolución correcta (👤 recolección + decisión de arquitectura):**
- **Dataset (👤, el foso):** protocolo en `docs/MOBILE.md` — ≥100-300 fotos/clase (trips, antracnosis,
  monalonion, roña, ácaros…) + clase `sano`, foto cercana/enfocada, buena luz, etiquetado por agrónomo.
  Es **tu ventaja competitiva** (acceso a finca). Pre-etiquetar con el VLM y validar a mano.
- **Arquitectura (✅ decidida):** on-device = **clasificador entrenado (ONNX)**, NO un VLM; el VLM→RAG
  (Claude) queda para escritorio/pre-etiquetado, donde el envío a la nube es aceptable y consentido. Así
  el móvil es **soberano/offline** y la precisión de patología llega cuando exista el dataset.

## 10. Calibración de campo (curva %MS-vs-grados-día, vida verde, historial de resistencia)
**Resolución correcta (👤 protocolos de datos):** la calculadora de **grados-día** ya da el marco; falta
**tu** curva local. Protocolos a ejecutar en finca:
- **%MS-vs-GDD:** registrar, por lote, fecha de cuaje + Tmax/Tmin diarias + %MS muestreada cada 1-2
  semanas; tras 1-2 campañas se ajusta la curva y el GDD objetivo de TU zona/cultivar.
- **Vida verde:** medir firmeza/peso en poscosecha a lo largo del tránsito simulado → curva de pérdida.
- **Historial de resistencia:** llevar el **cuaderno de aplicaciones** (grupo IRAC/FRAC por ciclo);
  con eso el recordatorio anti-resistencia podrá cruzar el historial (hoy es genérico). **Responsable:** 👤.

## 11. Negocio: bus factor / SLA, ROI honesto, responsabilidad legal
**Resolución correcta (⚖️ negocio, no código):**
- **Bus factor / SLA:** documentar el **runbook de mantenimiento** (actualización mensual del PQUA,
  reingesta, re-eval) — ya en `docs/RUNBOOK.md`; sumar un **plan de sucesión** (2º mantenedor o contrato
  de soporte) antes de vender SLA. **Disparador:** primer cliente de pago.
- **ROI honesto:** no se vende como "reemplazo del agrónomo" (lo niega el propio producto), sino como
  **ahorro de horas del agrónomo + red de seguridad** (menos rechazos por LMR/madurez). Medir horas
  ahorradas en un **piloto** antes de afirmar cifras.
- **Responsabilidad legal:** licencia **propietaria** (© Jhonatan del Rio) + disclaimer + **agrónomo-en-el-bucle que firma** la receta; para la
  UE, considerar la Directiva 2024/2853 de responsabilidad por producto. **Responsable:** ⚖️/👤.

---

## Cómo leer este plan
Cada ítem tiene un **camino ejecutable**, no una excusa. Lo ✅ ya está; lo 🟡 tiene el plan + la interfaz
lista para enchufar; lo ⏳ depende de un recurso externo (un feed, un permiso, un laboratorio, un dato de
campo) cuya adquisición está **especificada**. La honestidad es el producto: se dice qué falta, quién lo
hace y cuánto cuesta — no se finge que ya está.
