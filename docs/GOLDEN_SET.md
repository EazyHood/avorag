# Guía del Golden Set

El **golden set** es el activo más valioso del proyecto para tu portafolio: es lo que
convierte "construí un RAG" en "construí un RAG **medido**, con 0 alucinaciones de dosis
en N preguntas verificadas". También es el **gate de CI** que impide que un cambio empeore
la calidad. Lo curas TÚ (el agrónomo) — esa es la parte que la IA no puede replicar.

## Formato (JSONL — un objeto por línea)
Archivo: `data/golden/<nombre>.jsonl`. Campos por línea:

| Campo | Obligatorio | Qué es |
|---|---|---|
| `id` | sí | identificador corto y único (ej. `trips-01`) |
| `question` | sí | la pregunta tal como la haría un productor |
| `expected_answer` | no | la respuesta correcta (referencia; aún no se compara automáticamente) |
| `must_cite` | no | lista de subcadenas de fuente que DEBEN aparecer en las citas (ej. `["Agrosavia"]`) |
| `category` | no | `plaga` \| `enfermedad` \| `fertilizacion` \| `dosis` \| `inocuidad` \| `certificacion` |
| `is_trap` | no | `true` = pregunta fuera de cobertura; se espera que el bot **se abstenga** |

Ejemplo de línea:
```json
{"id": "trips-01", "question": "¿Cómo manejo el trips en aguacate Hass?", "category": "plaga", "must_cite": ["Agrosavia"], "is_trap": false}
```

## Cómo escribir buenas preguntas
1. **Saca preguntas REALES**, no inventadas: foros de caficultura/aguacate, grupos de
   WhatsApp de productores, lo que te preguntan en campo. El realismo es el valor.
2. **Cubre las categorías que causan dinero:** las plagas/enfermedades que generan
   rechazos de exportación (trips, monalonion, pega-pega, lenticelosis) y el LMR/carencia.
3. **Incluye un subconjunto de DOSIS** (8-12 preguntas): son las que prueban el
   guardarraíl más importante. Para estas, define `must_cite` con la fuente de la etiqueta.
4. **Incluye 15-20% de TRAMPAS** (`is_trap: true`): otro cultivo, pregunta no agrícola,
   o algo que el corpus no cubre. Miden la **abstención correcta** (no inventar).
5. **Apunta a 50 preguntas** para el MVP de portafolio (escala a 200+ después).
6. **Versiónalo en git:** cada cambio del corpus/modelo se corre contra esta versión.

## Cómo se usa
```powershell
uv run avorag eval data/golden/golden_set.example.jsonl
```
Genera: tabla en consola + `eval/reports/last_report.json` + **`eval/reports/report.html`**
(el dashboard que capturas para el portafolio). El comando devuelve código de salida ≠ 0
si el gate falla — por eso sirve como gate de CI.

## Qué mide el gate (umbrales en `eval/metrics.py`)
- **Abstención correcta** en trampas ≥ 80%.
- **Citación** en respuestas contestadas ≥ 80%.
- **Fidelidad media** ≥ 0.60 (si el juez está activo).
Ajusta los umbrales a medida que el corpus madura.
