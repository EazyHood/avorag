# Corpus — fuentes y licencias

> **Regla de oro:** el corpus solo contiene fuentes **legales, citables y con licencia
> verificada**. Nada de material pirateado (p.ej. Sci-Hub): contamina el activo y es el
> riesgo #1 de la due diligence. Para *descubrir* fuentes usa Elicit, Google Scholar,
> Semantic Scholar, OpenAlex o CORE, y baja siempre la versión legal/open-access.

## Estado de cada fuente
Marca aquí el estado de licencia ANTES de ingerir cada documento al producto comercial.

| Fuente | Tipo | Uso comercial | Estado | Notas |
|---|---|---|---|---|
| Agrosavia — Modelo Productivo Hass (Antioquia) | Manual técnico | ¿permite derivados? | ⛔ por verificar | Repositorio institucional abierto; confirmar términos |
| Fichas Agroclimáticas Quindío/Risaralda/Caldas | Ficha técnica | — | ⛔ por verificar | Convenio Agrosavia/Corpohass |
| Corpohass — lineamientos producción sostenible + protocolo material vegetal | Guía gremial | — | ⛔ por verificar | PDF público; idealmente conseguir aval de Corpohass |
| Etiquetas ICA de fitosanitarios registrados para aguacate | Regulatorio | info pública vs. material protegido | ⛔ por verificar | **Núcleo del guardarraíl de dosis**; validar con abogado |
| Boletines MIPE (trips, monalonion, pega-pega, lenticelosis) | Boletín | — | ⛔ por verificar | Agrosavia/ICA |
| GlobalGAP / Rainforest Alliance | Norma de certificación | ❌ NO redistribuir | ⛔ restringido | Copyright: **referenciar** la norma, no copiar su texto |
| Boletines agroclimáticos IDEAM | Datos públicos | — | ⛔ por verificar | — |

## Procedimiento de ingesta
1. Confirmar licencia de uso (registrar en `meta.licencia_uso` por chunk).
2. Descargar el PDF a `data/corpus/` (no se versiona en git).
3. `uv run avorag ingest data/corpus/<archivo>.pdf --fuente "<Nombre oficial>" --licencia "<licencia>" --autoridad <oficial-regulador|gremio|academico>`
4. Marcar vigencia; los registros ICA **caducan** → chequeo periódico (ver RUNBOOK).

## Descargados e ingeridos (2026-06-14)
Bajados de fuentes públicas para **desarrollo/portafolio**. ⚠️ Para uso **comercial**,
confirmar licencia de cada uno (Agrosavia suele ser CC BY-NC = *no comercial*).

| Archivo (`data/corpus/`) | Fuente | Autoridad | Licencia | Uso comercial |
|---|---|---|---|---|
| `ica_manejo_fitosanitario_hass.pdf` | ICA — Manejo fitosanitario del aguacate Hass (75 pp.) | oficial-regulador | Pública (ICA) | Probable OK (info regulatoria pública) — confirmar |
| `agrosavia_hass_doc.pdf` | Agrosavia — Bases técnicas manejo de plagas Hass, Cauca (14 pp.) | académico | CC BY-NC (a verificar) | ❌ NC = revisar antes de vender |
| `agrosavia_poscosecha_hass.pdf` | Agrosavia — Cosecha y poscosecha Hass, Cap. VII (16 pp.) | académico | CC BY-NC (a verificar) | ❌ NC = revisar antes de vender |
| `guia_plagas_hass.pdf` | Agrosavia — Guía reconocimiento y manejo de plagas Hass (guía **visual**, 6 MB) | académico | CC BY-NC (a verificar) | ❌ NC; ojo: info en figuras/imágenes (poco texto extraíble) |
| `fertilizacion_hass.pdf` | Agrosavia — Criterios de fertilización del Hass | académico | CC BY-NC (a verificar) | ❌ NC = revisar antes de vender |

**Lección de cobertura (2026-06-14):** con 5 docs / ~460 chunks, el sistema responde
**preguntas específicas** con cita y fidelidad alta, pero **se abstiene** en consultas
amplias de síntesis (p.ej. "trips y principales plagas"). Causa: (1) la guía de plagas es
**visual** (su info está en figuras, no en texto), y (2) las páginas de portada/título
ganan en recuperación sin un **reranker**. Fixes por impacto: **reranker** (mayor salto) >
fuentes ricas en texto > Contextual Retrieval > query más específica. El golden set + `eval`
cuantifican esto. Se añadió un limpiador de encabezados/pies repetidos en la ingesta.

> Los PDF no se versionan en git (`data/corpus/` está en `.gitignore`), así que no se
> redistribuyen desde el repo. Para la fase comercial, sustituir/complementar con fuentes
> de licencia comercial o conseguir permiso de Agrosavia/Corpohass.

## Para fase España/UE
Registro nacional MAPA (Reg. CE 1107/2009), RD 1311/2012 (GIP), LMR UE.
