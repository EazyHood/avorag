# ADR 0005 — La métrica correcta es seguridad + respaldo, no el verde global

**Estado:** aceptado · **Fecha:** 2026-06-15

## Contexto
Se corrió una simulación de **500 preguntas** (100 × plagas, fertilidad/suelos, fisiología,
insumos, otros) sobre el sistema completo (7B + corpus ampliado + guardarraíles), midiendo el
semáforo verde/amarillo/rojo por respuesta. Se evaluó contra un objetivo de mercado propuesto de
**≥80% verde / ≤20% amarillo / ≤3% rojo**.

Resultado (n=189, IC95% Wilson, estable durante toda la corrida):

| | valor | IC95% |
|---|---|---|
| 🟢 verde | 44% | [38–52] |
| 🟡 amarillo | 51% | [44–58] |
| 🔴 rojo | 4% | [2–8] |

El verde por categoría no supera el ~53% (plagas) ni siquiera en la categoría más fuerte; insumos
queda en 12% (preguntas de dosis/producto exacto). **El 80% verde global queda completamente fuera
del intervalo de confianza**, y tampoco se alcanza acotando por categoría.

## Decisión
**No se perseguirá el "80% verde sobre cualquier pregunta".** Es el KPI equivocado para un asesor
agronómico de seguridad: forzarlo solo se logra relajando el semáforo, lo que haría que el producto
afirme con confianza cosas sin respaldo — exactamente el riesgo que el producto existe para evitar.

El verde **no** se infla. El amarillo y la abstención son una **función** (el sistema dice "con
cautela / consulta" cuando el corpus no fundamenta la respuesta), no un fallo.

Las métricas de aceptación pasan a ser las de un asesor de seguridad:
1. **Respuestas peligrosas = 0%** — nunca verde sin respaldo citado. (medido: 0/189)
2. **Bloqueo de inseguros** — prohibido/off-label/dosis no rastreable → rojo. (medido: 4%, casi todo legítimo)
3. **Respaldo** — de las respuestas no-abstención, ≥1 cita verificable. (medido: 89%)
4. **Cobertura confiable** — verde citado donde el corpus sí fundamenta. (medido: 44%, creciendo con corpus)
5. **Deferencia honesta** — abstención/cautela cuando no hay fuente. (medido: 51%)

## Consecuencias
- (+) El posicionamiento del producto es la honestidad: responde con evidencia citada en su
  dominio (≈45% y creciendo), se pone en cautela cuando no, y **nunca recomienda un prohibido**.
  Es lo que un cliente real (exportadora, agrónomo) espera y lo que lo hace confiable.
- (+) La inversión en corpus se vuelve **quirúrgica**: se amplía donde paga (plagas, la más fuerte
  y de mayor valor) y no se malgasta persiguiendo un 80% global inalcanzable (~55–60% es el techo).
- (+) **Insumos se reposiciona**: preguntas de dosis/carencia exactas de un producto comercial se
  responden orientando + remitiendo al **registro ICA vigente (portal SimplifICA) y la etiqueta**,
  no como respuesta cerrada — porque la cifra exacta debe salir de la etiqueta viva, no de un PDF.
- (−) Quien espere "responde todo con seguridad" verá un número de verde "bajo"; se comunica que
  ese número alto solo se obtiene mintiendo, y que el valor está en el 0% de respuestas peligrosas.
