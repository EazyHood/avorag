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
| **Licencia del corpus (uso comercial)** | Parte del contenido público (p. ej. Agrosavia) puede tener **términos no comerciales**. | Cada fuente lleva su `licencia_uso` en `data/corpus_manifest.json`: **verifícala antes de cualquier uso comercial** y re-licencia o sustituye lo que aplique. El código es MIT; el corpus es aparte. |
| **Cobertura del corpus** | ~**44%** de cobertura confiable (verde) en preguntas arbitrarias; **menor en insumos/dosis exactas** (defiere a propósito). | Es deferencia honesta, no fallo. Se sube **ampliando fuentes** oficiales (ICA/Agrosavia) — el pipeline ya está. |
| **Multipaís** | Corpus centrado en **Colombia** (17/18 fuentes). | México/Perú/España requieren su **propio corpus** + geofiltro por-tenant (fase 🅱️). No uses las cifras CO para otras fincas. |
| **Juez de fidelidad** | Por defecto el **mismo** LLM se autoevalúa (autocorrelación; mide respaldo de cita, **no** exactitud agronómica). | **Configurable independiente** con `JUDGE_LLM_PROVIDER`/`JUDGE_LLM_MODEL`; `provider_info.judge` reporta si es independiente. Para una afirmación seria, juez ≠ generador + validación humana. |
| **Rigor de la evaluación** | Groundedness n=**64**; KPIs de seguridad n=**189**; corrección agronómica sobre pocas preguntas. | Una afirmación **comercial** exige **≥200** preguntas curadas + **segundo evaluador humano**. El "0% peligrosas" es sobre la muestra (IC95 Wilson en el reporte), **no** una garantía absoluta. |
| **Foto de plaga/enfermedad** | **Slot preparado, sin dataset** limpio aún. Hoy solo **madurez** (82% exacto, 99,4% ±1). | Requiere recolectar/etiquetar imágenes (el "foso" del agrónomo). Pipeline listo: entrenar → ONNX → bundle (ver [MOBILE.md](MOBILE.md)). |
| **Cobertura de enfermedades** (revisión: "antracnosis quiescente, lenticelosis, sunblotch, daño por frío, calibres ausentes") | **Medido contra la BD:** la mayoría **sí estaba** (lenticelosis 8, antracnosis 27, calibres 32, *Phytophthora* 54, daño por frío 4, cuarentenarias 85 chunks; ICA 1507 con 4, no "0"). Solo 2 vacíos reales: **sunblotch/ASBVd** y el matiz de **antracnosis quiescente** (0 chunks). | **Cerrados** con una síntesis curada y citada (UC IPM, PaDIL, Frontiers 2025) — ver `data/corpus_curado/`. El resto era recuperación, no ausencia. |
| **Producto comercial vs i.a. + unidad por matriz** | La normalización de unidades (conc vs /ha, kg↔g) ya está; falta el **sentido agronómico** de la unidad por matriz (foliar/suelo/drench). | Diferido a recomendación sitio-específica (ver [DEUDA_TECNICA.md](DEUDA_TECNICA.md)). Mientras tanto, el guardarraíl prefiere abstenerse/avisar antes que arriesgar. |
| **Integraciones (ERP, GlobalGAP, WhatsApp)** | **No existen** hoy. WhatsApp es canal **futuro** (Ruta 🅱️), no software actual. | El núcleo `rag.answer()` está desacoplado del canal: añadirlas es trabajo **aditivo**, no reescritura. |
| **Madurez / soporte (bus factor, SLA)** | **v0.1**, autor único, **sin SLA**. | No apto para operación crítica sin un acuerdo de soporte. Es un producto en construcción + portafolio. |
| **Responsabilidad legal (MIT + disclaimer)** | El disclaimer deja la decisión en el usuario. | Por diseño: es **apoyo citado**, no asesoría que sustituya a un profesional colegiado. Úsalo con **agrónomo-en-el-bucle**. |

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
