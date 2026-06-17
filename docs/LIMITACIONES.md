# Límites y alcance honesto (para quien evalúa adoptar AvoRAG)

Este documento existe para que un **decisor** (exportadora, agrónomo, comprador) sepa **exactamente
qué hace y qué NO hace** AvoRAG hoy, sin sorpresas. La honestidad es parte del producto: preferimos
perder una venta a que alguien tome una decisión cara confiando de más.

> Responde punto por punto a la [revisión crítica](REVISION_CRITICA_AGRONOMO_Y_DUENO.md) de dos
> perfiles exigentes (ingeniero agrónomo de Hass de exportación + dueño de exportadora). Lo que era
> arreglable se arregló (PRs #13–#16); lo estructural se documenta aquí en vez de esconderse.

## Qué es (y qué NO es)
- **Es:** un *bibliotecario citador* + una *red de seguridad fitosanitaria determinista* + unas
  *calculadoras* agronómicas. Responde citando la fuente, se abstiene cuando no sabe, y bloquea en
  ROJO lo inseguro.
- **NO es:** el *cerebro de decisión* agronómica, ni firma recetas, ni sustituye al agrónomo
  colegiado ni al análisis de tu laboratorio. La decisión y la responsabilidad son del profesional.

## Límites estructurales (estado honesto)

| Límite (planteado en la revisión) | Estado real hoy | Mitigación / camino |
|---|---|---|
| **LMR y registro ICA en vivo** | No hay feed en vivo. | El guardarraíl exige que el registro ICA esté **citado** y no caducado, avisa "verifica vigencia en **SimplifICA**", y manda a ROJO los prohibidos/restringidos. Un activo **no autorizado en el destino** → ROJO si configuras `EXPORT_MARKET` (lista **de mínimos**, no exhaustiva). **Verifica el LMR del país de destino en la analítica de residuos**: una carencia correcta en Colombia no garantiza pasar en Róterdam. |
| **Clima en vivo** | No integrado; **imposible** en el objetivo móvil offline. | Da el *qué* y el *porqué* (umbrales, ventanas), no el *cuándo* de tu lote. El "cuándo" lo pone tu monitoreo + tu técnico. |
| **Licencia del corpus (uso comercial)** | Parte del contenido público (p. ej. Agrosavia) puede tener **términos no comerciales**. | Cada fuente lleva su `licencia_uso` en `data/corpus_manifest.json`: **verifícala antes de cualquier uso comercial** y re-licencia o sustituye lo que aplique. El código es **propietario** (© Jhonatan del Rio, todos los derechos reservados); el corpus es aparte. |
| **Cobertura del corpus** | ~**44%** de cobertura confiable (verde) en preguntas arbitrarias; **menor en insumos/dosis exactas** (defiere a propósito). | Es deferencia honesta, no fallo. Se sube **ampliando fuentes** oficiales (ICA/Agrosavia) — el pipeline ya está. |
| **Multipaís** | Corpus centrado en **Colombia** (17/18 fuentes). | México/Perú/España requieren su **propio corpus** + geofiltro por-tenant (fase 🅱️). No uses las cifras CO para otras fincas. |
| **Juez de fidelidad** | Por defecto el **mismo** LLM se autoevalúa (autocorrelación; mide respaldo de cita, **no** exactitud agronómica). | **Configurable independiente** con `JUDGE_LLM_PROVIDER`/`JUDGE_LLM_MODEL`; `provider_info.judge` reporta si es independiente. Para una afirmación seria, juez ≠ generador + validación humana. |
| **Rigor de la evaluación** | Groundedness n=**64**; KPIs de seguridad n=**189**; corrección agronómica sobre pocas preguntas. | Una afirmación **comercial** exige **≥200** preguntas curadas + **segundo evaluador humano**. El "0% peligrosas" es sobre la muestra (IC95 Wilson en el reporte), **no** una garantía absoluta. |
| **Foto de plaga/enfermedad** | **Slot preparado, sin dataset** limpio aún. Hoy solo **madurez** (82% exacto, 99,4% ±1). | Requiere recolectar/etiquetar imágenes (el "foso" del agrónomo). Pipeline listo: entrenar → ONNX → bundle (ver [MOBILE.md](MOBILE.md)). |
| **Cobertura de enfermedades** (revisión: "antracnosis quiescente, lenticelosis, sunblotch, daño por frío, calibres ausentes") | **Medido contra la BD:** la mayoría **sí estaba** (lenticelosis 8, antracnosis 27, calibres 32, *Phytophthora* 54, daño por frío 4, cuarentenarias 85 chunks; ICA 1507 con 4, no "0"). Solo 2 vacíos reales: **sunblotch/ASBVd** y el matiz de **antracnosis quiescente** (0 chunks). | **Cerrados** con una síntesis curada y citada (UC IPM, PaDIL, Frontiers 2025) — ver `data/corpus_curado/`. El resto era recuperación, no ausencia. |
| **Producto comercial vs i.a. + unidad por matriz** | La normalización de unidades (conc vs /ha, kg↔g) ya está; falta el **sentido agronómico** de la unidad por matriz (foliar/suelo/drench). | Diferido a recomendación sitio-específica (ver [DEUDA_TECNICA.md](DEUDA_TECNICA.md)). Mientras tanto, el guardarraíl prefiere abstenerse/avisar antes que arriesgar. |
| **Integraciones (ERP, GlobalGAP, WhatsApp)** | **No existen** hoy. WhatsApp es canal **futuro** (Ruta 🅱️), no software actual. | El núcleo `rag.answer()` está desacoplado del canal: añadirlas es trabajo **aditivo**, no reescritura. |
| **Madurez / soporte (bus factor, SLA)** | **v0.1**, autor único, **sin SLA**. | No apto para operación crítica sin un acuerdo de soporte. Es un producto en construcción + portafolio. |
| **Responsabilidad legal (licencia propietaria + disclaimer)** | El disclaimer deja la decisión en el usuario. | Por diseño: es **apoyo citado**, no asesoría que sustituya a un profesional colegiado. Úsalo con **agrónomo-en-el-bucle**. El código es propietario (© Jhonatan del Rio); usarlo requiere licencia del autor. |

## Lo que SÍ aporta hoy (para equilibrar)
- **Red de seguridad determinista:** prohibidos/restringidos → ROJO **siempre** (incluso si el modelo
  duda); premisas inseguras ("duplicar la dosis", "sin carencia", "cualquier producto") no refutadas
  → ROJO **por construcción**; dosis de fertilizante inverosímil → AMARILLO. Cubierto por tests.
- **Calculadoras** deterministas (materia seca, encalado por Al, relaciones foliares) — ver
  [CALCULADORAS.md](CALCULADORAS.md).
- **Trazabilidad:** cada respuesta cita su fuente y queda auditada (con minimización de datos).
- **Honestidad operativa:** se abstiene fuera de dominio y reporta sus propias métricas con IC95.

> En una frase: úsalo como **bibliotecario citador y red de seguridad**, con el agrónomo en el bucle.
> No como cerebro de decisión ni para firmar una receta. Ahí coincidimos con la crítica.

---

## Segunda revisión (80 hallazgos con anclas a `file:line`)

Una revisión técnica profunda (agrónomo de exportación + dueño de exportadora) listó 80 puntos. Lo
**arreglable se arregló** (PRs #19–#22, con tests); lo **estructural** se documenta aquí en vez de
fingirse. Resumen honesto:

### ✅ Arreglado en esta ronda (con tests)
- **Guardarraíles:** se cerró el *bypass del refutador* (una respuesta que avalaba "duplicar la dosis"
  y mencionaba "resistencia" apagaba el ROJO — ya no); premisas nuevas (encharcar/saturar el suelo,
  asperjar insecticida en floración, cobre+aceite, escalado parafraseado); **marcas comerciales**
  (Gramoxone→paraquat, Furadan→carbofurán…) ahora disparan prohibidos/destino.
- **Calculadoras:** foliar con **B, Zn, Cl, Na** y **niveles absolutos** (un árbol famélico con buena
  proporción ya no sale "óptimo"); **materia seca con muestreo** (media/n/CV/mínimo; un fruto avisa);
  **encalado con densidad/andisol**; nuevas de **riego (ETc)** y **salinidad (fracción de lavado + SAR)**.
- **Regulatorio/honestidad:** privacidad por defecto (`audit_store_text=False`); aviso **siempre** de
  verificar vigencia ICA al recomendar plaguicida; **+18 moléculas modernas** en destino UE/EE.UU.;
  riesgo **FRAC 11/7 (monositio) vs multisitio**; nudge **MIP/biocontrol** primero; daño por frío (~2-5 °C).
- **Cobertura/herramientas nuevas:** síntesis citada de la **Res. ICA 1507/2016** (cuarentenarias) +
  **aviso de tolerancia-cero** cuando se menciona Stenoma/Heilipus; calculadoras de **grados-día**
  (marco fenológico), **calibre** y **umbral de acción MIP**.

### 🔴 Estructural — NO se "arregla" con código (es lo que es en un v0.1)
| Tema (puntos de la revisión) | Por qué es estructural | Postura honesta |
|---|---|---|
| **Datos en vivo:** vigencia ICA, LMR/tolerancias (UE/EE.UU. 40 CFR 180), clima (IDEAM), precios | No hay feeds; el PQUA es extracto **mar-2022** | El sistema **avisa "verifica en SimplifICA"** y marca LMR de destino, pero **no consulta el estado vivo**. Es una foto, no un servicio regulatorio en tiempo real. |
| **ICA Res. 1507/2016** (plagas de control oficial) | El PDF original es **escaneado → 0 chunks sin OCR** (y no hay tesseract) | **Parcial:** se ingirió una **síntesis del texto oficial** (Heilipus/Stenoma + tolerancia cero). El **OCR del PDF original** sigue pendiente. |
| **Cuarentenarias tolerancia-cero** (Stenoma) | El protocolo completo (área libre, sistemas de mitigación) lo define el ICA | **Parcial:** ahora **AVISA** del régimen de tolerancia cero + reporte al ICA al mencionarse Stenoma/Heilipus; el protocolo operativo completo no está modelado. |
| **Fenología / ventana de cosecha** (%MS vs días de cuaje) | La **curva** %MS-vs-tiempo-térmico es calibrada y local | **Parcial:** hay una calculadora de **grados-día** (marco fenológico) y de progreso vs objetivo; **no predice** el corte — tú calibras y confirmas con materia seca. |
| **Umbrales/monitoreo MIP y calibre** | Los **umbrales** por plaga son del agrónomo/protocolo; vida verde necesita curva de firmeza | **Parcial:** calculadoras de **umbral de acción MIP** (tú pones el umbral) y de **calibre/count size**. **Vida verde** (firmeza/peso en tránsito) sigue sin herramienta. |
| **Diagnóstico molecular** (qPCR antracnosis, RT-PCR de sunblotch) | Es un ensayo de **laboratorio** | La app explica la biología y cita, pero **no diagnostica** ni acerca el ensayo. |
| **Foto-patología** (llava:7b débil; Claude rompe offline/soberanía) | Trade-off real modelo-local vs nube | El VLM local es flojo en lesiones sutiles; la vía precisa (Claude) **sale a internet y factura**. Hoy lo único portable offline es **madurez**. |
| **Historial de aplicaciones** (anti-resistencia real) | Requiere integrar tu cuaderno de campo | El aviso IRAC/FRAC es **genérico**: no sabe qué aplicaste la semana pasada. |
| **Unidad por matriz** (foliar/suelo/drench) | El sentido agronómico de la unidad está diferido | El guardarraíl normaliza kg↔g pero **no distingue** foliar de drench: puede dar por "rastreable" una dosis correcta para foliar aplicada a drench. |
| **Multipaís** (corpus 17/18 CO; `COUNTRY=ES` sin corpus) | Cada jurisdicción necesita su corpus regulatorio | Fuera de Colombia, registro/carencia/prohibidos **no aplican**. El bundle offline congela conocimiento **CO**. |
| **Multi-tenant / RLS fail-open / auth por API-key** | Implementado pero **sin activar ni probar en carga**; RLS permisiva si una sesión no fija el tenant | Hoy **1 tenant**; no separa fincas/clientes ni usuarios. No desplegar multiusuario sin activar y probar RLS (fail-closed). |
| **Integraciones** (ERP, packing, GlobalGAP, lab, WhatsApp) | No existen; WhatsApp es Ruta 🅱️ | La recomendación **no baja a tu traza**; el canal de campo está por construir. |
| **Métricas:** tabla n=64 **pre-fix**, juez **autoevaluándose**, corrección sobre **3** preguntas, config medida (rerank `local`) ≠ default (`none`) | Falta re-correr el eval y un 2º evaluador humano | El groundedness 0.79 mide **respaldo de cita, no exactitud agronómica**. Para afirmación comercial: ≥200 preguntas + juez independiente + humano. La fuga "1 en verde" está cerrada **por construcción** (test), aunque la **tabla** aún es previa. |
| **Madurez/soporte** (v0.1, autor único, sin SLA, bus factor 1) | Es un PoC/portafolio | No apto para operación crítica sin acuerdo de soporte. |

> Nada de lo anterior se esconde: cada punto tiene su ancla en el repo. La honestidad es el producto.
