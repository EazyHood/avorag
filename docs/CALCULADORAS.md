# Calculadoras agronómicas (cálculo determinista)

El RAG **cita**, no **calcula**. Algunas decisiones cuantitativas clave son aritmética exacta que no
debe pasar por un LLM (alucinaría cifras) y que el agrónomo necesita al pie del árbol. Estas
calculadoras las resuelven con fórmulas reconocidas, **sin red ni modelo** — por eso sirven igual
**offline** en la futura app móvil.

Motor: [`src/avorag/agro_calc.py`](../src/avorag/agro_calc.py) (puro, sin infra) ·
API: `POST /api/calc/*` ([`routes_calc.py`](../src/avorag/api/routes_calc.py)) ·
UI: botón **🧮 Calculadoras** en la barra superior.

## 1) Materia seca — el corte de exportación (con MUESTREO)
El Hass se corta por **materia seca**, no por color. La parte que de verdad falla es el **muestreo**:
la MS varía 3-5 puntos entre fruto de sol y de sombra, así que se promedian **10-20 frutos**.

- `POST /api/calc/materia-seca` → `{muestras: [%MS,…]}` (preferido) **o** `{peso_fresco_g, peso_seco_g}` (1 fruto) + `umbral_pct?`.
- Devuelve **media, n, CV y el mínimo**. Veredicto sensible al muestreo: un solo fruto **avisa** que
  es insuficiente; si la media supera el umbral **pero hay frutos por debajo** o el **CV > 8%** →
  `limítrofe` (parte del lote no llega). Umbral por defecto **23%** (mínimo de madurez legal ~20,8%).

## 2) Encalado por saturación de aluminio (con ANDISOLES)
Fórmula de saturación objetivo (Cochrane et al.): `req (cmol⁺/kg) = Al − (PSA_obj/100) · CICE`.

- `POST /api/calc/encalado` → `{al, ca, mg, k, na?, psa_objetivo_pct?, prnt_pct?, densidad_aparente?, profundidad_cm?}`.
- Si das **`densidad_aparente`**, la t/ha se recalcula desde primeros principios; y si es **< 1,0
  (andisol de ceniza volcánica)** se **ADVIERTE** que la fórmula de saturación no es fiable por el
  poder tampón (alófana) → es una cota inferior, haz una curva de incubación/tampón.
- Honestidad: profundidad, densidad y PRNT reales cambian la dosis; el PSA objetivo es orientativo.

## 3) Diagnóstico foliar — relaciones + NIVELES absolutos + estrés salino
No solo relaciones: ahora también el **nivel absoluto** de cada elemento y el estrés salino.

- `POST /api/calc/relaciones-foliares` → `{n?,p?,k?,ca?,mg?,s?, b?,zn?,fe?,mn?,cu?, cl?,na?}` (macros %, micros ppm).
- **Relaciones:** K/Ca, Ca/Mg, Mg/K, N/K, K/Mg (+ K/Cl, K/Na si hay sal).
- **Niveles absolutos:** cada elemento vs su rango de suficiencia → un árbol **famélico con buena
  proporción ya NO sale "óptimo"** (caza la doble deficiencia). Incluye **B y Zn** (cuajado/calibre).
- **Estrés salino:** Cl/Na altos → alerta de quemado marginal (preferir K₂SO₄ sobre KCl).
- Honestidad: rangos **orientativos** (varían por norma/laboratorio); no es un DRIS con normas locales.

## 4) Riego — requerimiento por ETc = ETo · Kc
- `POST /api/calc/riego` → `{eto_mm_dia, kc, precip_efectiva_mm_dia?, eficiencia?, area_ha?}`.
- ETc = ETo·Kc; lámina neta = ETc − lluvia efectiva; bruta = neta/eficiencia; volumen si das área
  (1 mm/ha = 10 m³). La ETo viene del clima del día y el Kc de la etapa — **son tus datos**, aquí va la aritmética.

## 5) Salinidad — fracción de lavado + SAR
El Hass es de los frutales **más sensibles** a Cl⁻/Na⁺ (umbral CEe ≈ 1,3 dS/m).

- `POST /api/calc/salinidad` → `{ce_agua_dsm, ce_umbral_suelo_dsm?, na_meq_l?, ca_meq_l?, mg_meq_l?}`.
- **Fracción de lavado** (Rhoades: LF = CEw/(5·CEe − CEw)) + **SAR** = Na/√((Ca+Mg)/2) (meq/L), con
  alertas si el agua es demasiado salina o sódica. Umbrales orientativos.

## 6) Grados-día (tiempo térmico) — marco de la ventana de cosecha
- `POST /api/calc/grados-dia` → `{temps: [[Tmax,Tmin],…], t_base?, t_tope?, objetivo_gdd?}`.
- Acumula GDD = Σ max(0, (Tmax+Tmin)/2 − T_base) desde cuaje. **No predice el corte** (eso exige una
  curva %MS-vs-GDD calibrada local): da el **marco fenológico** y, si das `objetivo_gdd`, el % de
  progreso. Calibra `t_base`/objetivo con tus registros y **confirma con materia seca**.

## 7) Calibre / count size
- `POST /api/calc/calibre` → `{peso_g, caja_kg?}`. Calibre UE = frutos por **caja de 4 kg**
  (calibre = caja_kg·1000/peso). Otros mercados usan otra caja → otro conteo. Orientativo.

## 8) Umbral de acción MIP (¿aplico o monitoreo?)
- `POST /api/calc/umbral-mip` → `{conteo_total, n_unidades, umbral, unidad?}`. Calcula la **media por
  unidad** (trampa/planta) y la compara con **tu** umbral de acción. El umbral lo define tu
  protocolo/agrónomo (la app **no lo inventa**); si interviene, recuerda **MIP**: biológico/cultural
  antes del químico.

## Por qué importa para el móvil offline
Todo es aritmética pura: la misma lógica de `agro_calc.py` se puede portar a la app (Dart/JS) y
funcionar **sin internet**, junto al clasificador on-device y el `knowledge_bundle.json`
(ver [MOBILE.md](MOBILE.md)).
