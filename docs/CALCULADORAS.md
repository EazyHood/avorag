# Calculadoras agronómicas (cálculo determinista)

El RAG **cita**, no **calcula**. Algunas decisiones cuantitativas clave son aritmética exacta que no
debe pasar por un LLM (alucinaría cifras) y que el agrónomo necesita al pie del árbol. Estas
calculadoras las resuelven con fórmulas reconocidas, **sin red ni modelo** — por eso sirven igual
**offline** en la futura app móvil.

Motor: [`src/avorag/agro_calc.py`](../src/avorag/agro_calc.py) (puro, sin infra) ·
API: `POST /api/calc/*` ([`routes_calc.py`](../src/avorag/api/routes_calc.py)) ·
UI: botón **🧮 Calculadoras** en la barra superior.

## 1) Materia seca — el corte de exportación
El Hass se corta por **materia seca**, no por color. Pesa una muestra de pulpa fresca, sécala a peso
constante (microondas/estufa) y mete ambos pesos: `%MS = peso_seco / peso_fresco × 100`.

- `POST /api/calc/materia-seca` → `{peso_fresco_g, peso_seco_g, umbral_pct?}`
- Umbral por defecto **23%** (exportación); el mínimo de madurez legal ronda **20,8%** (CODEX/California).
- Veredicto: `apto` / `limítrofe` (< 1 punto del umbral) / `por debajo`.

## 2) Encalado por saturación de aluminio
El aguacate es sensible al Al. Fórmula de saturación objetivo (Cochrane et al.):
`requerimiento (cmol⁺/kg) = Al − (PSA_obj/100) · CICE`, con `CICE = Al+Ca+Mg+K+Na`.

- `POST /api/calc/encalado` → `{al, ca, mg, k, na?, psa_objetivo_pct?, factor_campo?, prnt_pct?}` (cationes en cmol⁺/kg).
- Saturación objetivo por defecto **15%**. La **t/ha** es una estimación de campo
  (factor 1,5 t CaCO₃/ha por cmol⁺/kg a 0-20 cm, densidad ~1,3) **ajustada por el PRNT de tu cal**.
- Honestidad: profundidad, densidad y PRNT reales cambian la dosis — ajústala con tu agrónomo.

## 3) Relaciones foliares (balance nutricional)
Calcula las relaciones que el RAG no calcula: **K/Ca, Ca/Mg, Mg/K, N/K** (macros en % de materia seca).

- `POST /api/calc/relaciones-foliares` → `{n?, k?, ca?, mg?}` (al menos dos).
- Cada relación se compara con una **banda orientativa** y se marca `bajo`/`óptimo`/`alto`.
- Honestidad: las bandas **varían por norma y laboratorio**; es apoyo, la interpretación final es del
  agrónomo con el análisis completo (no es un DRIS con normas locales).

## Por qué importa para el móvil offline
Todo es aritmética pura: la misma lógica de `agro_calc.py` se puede portar a la app (Dart/JS) y
funcionar **sin internet**, junto al clasificador on-device y el `knowledge_bundle.json`
(ver [MOBILE.md](MOBILE.md)).
