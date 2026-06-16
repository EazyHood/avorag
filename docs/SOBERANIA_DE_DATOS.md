# Soberanía de datos y no-lock-in de AvoRAG

> Resuelve las objeciones del comprador exportador **#3 («mis datos no son tuyos»)** y **#6 («¿y si
> desapareces?»)**. Distingue con honestidad lo que ya es **técnico y verificable hoy** de lo que es
> **contractual** (requiere firmar un acuerdo y revisión de un abogado). No afirma nada que no se pueda comprobar.

## Lo que YA es verdad y puedes comprobar (técnico)

1. **Tus datos no salen de tu servidor (despliegue local).** Por defecto AvoRAG corre con LLM y
   embeddings **locales (Ollama + tu GPU)**: las preguntas, respuestas y datos de finca **nunca se
   envían a una nube ajena**. (Solo si *eliges* un proveedor por API —Claude/OpenAI— los datos salen a
   ese proveedor; ver "Pendiente contractual".)
2. **Aislamiento por exportadora (multi-tenant + RLS).** Cada tenant tiene sus filas aisladas a nivel
   de base de datos (Row-Level Security, migración 0003) y un test de aislamiento en CI. Los datos de
   una exportadora **no se cruzan** con los de otra.
3. **Minimización (Habeas Data, Ley 1581/2012).** Con `AUDIT_STORE_TEXT=false`, la auditoría guarda
   solo un **hash** de la consulta, no el texto.
4. **Exportable y portable (anti-lock-in).** `scripts/tenant_data.py export --tenant <t> --out <dir>`
   vuelca **todo** tu corpus (documentos + fragmentos) y tu auditoría a **JSONL abierto**. Te los
   llevas cuando quieras, sin formato propietario.
5. **Borrable (derecho al olvido / salida).** `scripts/tenant_data.py purge --tenant <t> --yes` borra
   todos tus datos (hace un respaldo previo). Irreversible y demostrable.
6. **Código abierto (MIT) y autohospedable.** El motor es MIT y corre en tu infraestructura: **aunque
   el proyecto desaparezca, te quedas el software funcionando** (ver `docs/AUTOHOSPEDAJE.md`). No
   dependes de una nube que un tercero pueda apagar (a diferencia de plataformas cerradas).

## Compromisos que van en el CONTRATO (pendiente: firmar + abogado)

Lo siguiente es **política**, no código — debe quedar por escrito en el acuerdo de servicio y
revisado por un abogado (no soy abogado; esto es un borrador honesto, no asesoría legal):

- **Propiedad:** los datos de la finca/exportadora son **del cliente**. AvoRAG es procesador, no dueño.
- **No reventa ni agregación a terceros** de los datos del cliente, en ninguna forma.
- **No entrenar el modelo con tus datos** sin consentimiento explícito (opt-in). Por defecto, **no**.
- **Sin retención del proveedor de IA:** si se usa LLM por API, contratar el modo *zero-retention /
  no-training* del proveedor y declararlo en el contrato (con Ollama local, no aplica).
- **Exportación y borrado garantizados a la salida**, con plazos.
- **Habeas Data:** registro ante la SIC y tratamiento conforme a Ley 1581/2012 (Colombia); AI Act / GDPR
  si se opera en la UE.
- **Estilo *Ag Data Transparent*:** términos claros y sin ambigüedad sobre recolección, uso y cesión.

## Honestidad — lo que NO está resuelto aún
- La verificación "no entrena con tus datos" con un proveedor de IA por API depende de **sus términos**;
  con el despliegue **local** el punto desaparece (los datos no salen).
- El **contrato** y el registro **SIC/Habeas Data** son trabajo legal pendiente, no de software.
- `purge`/`export` requieren acceso a la BD del despliegue; están **probados en código** (importan
  limpio, ruff/mypy), pero su corrida contra una BD real es parte del despliegue, no de esta entrega.
