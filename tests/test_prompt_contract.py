"""Contrato del prompt evidence-first: 4 reglas críticas congeladas por intención.

Si alguien elimina una de ellas, el test falla. También versiona el prompt para correlacionar
métricas con su versión.
"""

from __future__ import annotations

import re

from avorag.rag.prompt import PROMPT_VERSION, SYSTEM_PROMPT


def test_prompt_version_is_set() -> None:
    assert PROMPT_VERSION.strip()


def test_evidence_first_rules_present() -> None:
    p = SYSTEM_PROMPT.lower()
    # 1) Solo usar los fragmentos / no conocimiento externo.
    assert re.search(r"(únicamente|unicamente|solo).{0,40}fragmento", p) or "no uses" in p
    # 2) Citar con [n].
    assert "[" in SYSTEM_PROMPT and re.search(r"\[\s*n\s*\]|\[3\]|corchetes", p)
    # 3) Nunca inventar dosis.
    assert "dosis" in p and ("nunca inventes" in p or "no inventes" in p or "etiqueta" in p)
    # 4) Abstención exacta con el marcador.
    assert "{abstention}" in SYSTEM_PROMPT or "abstention" in p
