"""Invariantes fail-safe del semáforo (amplifica la fortaleza #4).

En vez de probar `decide_semaforo` en puntos sueltos, ENUMERA exhaustivamente todas las
combinaciones de sus señales y verifica invariantes DURAS de seguridad:

- VERDE es alcanzable SOLO desde el estado totalmente sano (ninguna señal de riesgo).
- Cualquier condición ROJO (prohibido / off-label / dosis no rastreable / sin registro /
  carencia sin fuente / categoría I / asociación insegura) ⇒ ROJO, siempre.
- Nunca VERDE si el juez cayó, si faltó verificar la seguridad, o si no hay citas.

Si alguien refactoriza el árbol de decisión y abre un "VERDE indebido", este test lo caza.
No usa LLM ni BD: es lógica pura.
"""

from __future__ import annotations

import itertools

from avorag.rag.guardrails import DoseSafety, decide_semaforo
from avorag.rag.schemas import Semaforo

_THRESH = 0.6
_SAFE = DoseSafety(safe=True, issues=[], cat_i_ii=False)
_UNSAFE = DoseSafety(safe=False, issues=["x"], cat_i_ii=False)
_CATII = DoseSafety(safe=True, issues=[], cat_i_ii=True)


def _is_red(*, banned, offlabel, doses_ok, phi_ok, registro_required, registro_ok, cat_tox, safety):
    return (
        bool(banned)
        or offlabel
        or (not doses_ok)
        or (registro_required and not registro_ok)
        or (not phi_ok)
        or ("I" in cat_tox)
        or (safety is not None and safety.cat_i_ii)
        or (safety is not None and not safety.safe)
    )


def test_failsafe_invariants_exhaustive() -> None:
    bool_flags = [
        "doses_ok",
        "phi_ok",
        "has_citations",
        "judge_failed",
        "safety_required",
        "offlabel",
        "registro_ok",
        "registro_required",
        "citation_ok",
    ]
    cat_options = [{"N/A"}, {"I"}, {"II"}, {"III"}]
    safety_options = [None, _SAFE, _UNSAFE, _CATII]
    faith_options = [0.9, 0.5]
    banned_options = [[], ["clorpirifos (restringido)"]]
    conflict_options = [[], ["abamectina: 2,5 vs 10"]]

    checked = 0
    for bits in itertools.product([False, True], repeat=len(bool_flags)):
        flags = dict(zip(bool_flags, bits, strict=True))
        for cat_tox, safety, faith, banned, conflicts in itertools.product(
            cat_options, safety_options, faith_options, banned_options, conflict_options
        ):
            semaforo, _ = decide_semaforo(
                cat_tox=cat_tox,
                faithfulness=faith,
                safety=safety,
                banned=banned,
                conflicts=conflicts,
                faithfulness_threshold=_THRESH,
                **flags,
            )
            checked += 1
            red = _is_red(
                banned=banned,
                offlabel=flags["offlabel"],
                doses_ok=flags["doses_ok"],
                phi_ok=flags["phi_ok"],
                registro_required=flags["registro_required"],
                registro_ok=flags["registro_ok"],
                cat_tox=cat_tox,
                safety=safety,
            )
            # (1) Toda condición ROJO ⇒ ROJO.
            if red:
                assert semaforo == Semaforo.ROJO, (flags, cat_tox, safety, banned)
            # (2) VERDE ⇔ estado totalmente sano.
            healthy = (
                not red
                and not (flags["safety_required"] and safety is None)
                and "II" not in cat_tox
                and flags["citation_ok"]
                and not conflicts
                and not flags["judge_failed"]
                and faith >= _THRESH
                and flags["has_citations"]
            )
            assert (semaforo == Semaforo.VERDE) == healthy, (flags, cat_tox, safety, faith)
            # (3) Nunca VERDE con juez caído / verificación faltante / sin citas.
            if (
                flags["judge_failed"]
                or (flags["safety_required"] and safety is None)
                or not flags["has_citations"]
            ):
                assert semaforo != Semaforo.VERDE

    assert checked > 4000  # se cubrió un espacio amplio, no un puñado de casos
