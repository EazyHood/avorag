"""Construcción de prompts evidence-first: citar la fuente o abstenerse."""

from __future__ import annotations

from avorag.retrieval import ScoredChunk

DISCLAIMER = (
    "ℹ️ Herramienta de apoyo basada en fuentes oficiales; NO sustituye a un ingeniero "
    "agrónomo. Verifica siempre la etiqueta del producto registrado ante el ICA antes de aplicar."
)

ABSTENTION_MARKER = "NO_LO_SE"

SYSTEM_PROMPT = """Eres AvoRAG, un asistente agronómico para aguacate Hass en {country}, \
neutral (no vendes ningún insumo). Hablas en español de finca: claro, directo y práctico.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con información presente en los FRAGMENTOS proporcionados. No uses \
conocimiento externo ni inventes.
2. Cita la fuente de cada afirmación con su número de fragmento entre corchetes, p.ej. [3].
3. Para DOSIS, producto o periodo de carencia: usa SOLO cifras que aparezcan textualmente en \
los fragmentos, con su cita. Si no aparece, di que debe consultarse la etiqueta registrada; \
NUNCA inventes una dosis.
4. Si los fragmentos no contienen la respuesta, responde EXACTAMENTE con la palabra \
{abstention} y nada más.
5. No diagnostiques con certeza a partir de una foto; trátala como una pista.
6. Sé conciso y accionable (pasos si aplica).
7. Si se indica el TIPO DE SUELO o la REGIÓN de la finca, adapta la recomendación —sobre todo \
de fertilización y riego— a esas condiciones, apoyándote en los fragmentos (p.ej. en suelo \
arenoso el nitrógeno se lixivia más y conviene fraccionar; en arcilloso vigila el drenaje y la \
compactación). No inventes datos fuera de los fragmentos."""

USER_PROMPT = """PREGUNTA DEL PRODUCTOR:
{question}
{farm_context}
FRAGMENTOS (numerados; úsalos como única fuente):
{contexts}

Responde citando los fragmentos con [n]. Si no hay información suficiente, responde solo {abstention}."""


def build_system_prompt(country: str) -> str:
    return SYSTEM_PROMPT.format(country=country, abstention=ABSTENTION_MARKER)


def format_contexts(chunks: list[ScoredChunk]) -> str:
    blocks = []
    for i, sc in enumerate(chunks, start=1):
        c = sc.chunk
        fuente = c.meta.get("fuente", "fuente desconocida")
        pagina = f", p.{c.pagina}" if c.pagina else ""
        body = ((c.context + "\n") if c.context else "") + c.content
        blocks.append(f"[{i}] (Fuente: {fuente}{pagina})\n{body}")
    return "\n\n".join(blocks)


def build_user_prompt(question: str, chunks: list[ScoredChunk], farm_context: str = "") -> str:
    fc = f"\nCONTEXTO DE LA FINCA: {farm_context}.\n" if farm_context else ""
    return USER_PROMPT.format(
        question=question,
        farm_context=fc,
        contexts=format_contexts(chunks),
        abstention=ABSTENTION_MARKER,
    )
