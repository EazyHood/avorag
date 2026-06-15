"""El disclaimer viaja SIEMPRE (amplifica la fortaleza #8).

Posicionamiento legal/ético: cada respuesta es apoyo a la decisión, no decisión. Las ramas de
abstención de `answer()` deben llevar el disclaimer; el camino normal lo fija en el Answer.
"""

from __future__ import annotations

import time

from avorag.rag.pipeline import _abstention
from avorag.rag.prompt import DISCLAIMER
from avorag.rag.schemas import AbstentionType


def test_disclaimer_constant_is_nonempty() -> None:
    assert DISCLAIMER.strip()


def test_every_abstention_branch_carries_disclaimer() -> None:
    for atype in AbstentionType:
        ans = _abstention(
            "pregunta",
            atype,
            text="texto",
            reason="razon",
            pinfo={},
            t0=time.perf_counter(),
        )
        assert ans.disclaimer.strip(), f"abstención {atype} sin disclaimer"
        assert ans.abstained is True
