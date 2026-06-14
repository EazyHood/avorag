"""Métricas de evaluación y gate de calidad (para CI)."""

from __future__ import annotations

from dataclasses import dataclass, field

from avorag.eval.golden_set import GoldenItem
from avorag.rag.schemas import Answer

# Umbrales del gate. Ajustables a medida que el corpus crece.
GATE_THRESHOLDS = {
    "correct_abstention_rate": 0.80,  # las preguntas-trampa deben abstenerse
    "citation_rate": 0.80,  # las respuestas reales deben citar fuente
    "avg_faithfulness": 0.60,  # si el juez está activo
}


@dataclass
class EvalMetrics:
    n: int = 0
    n_traps: int = 0
    n_real: int = 0
    n_answered: int = 0  # respuestas reales efectivamente contestadas (no abstenidas)
    answered_rate: float = 0.0  # respuestas reales no-abstenidas / reales
    correct_abstention_rate: float = 1.0  # trampas abstenidas / trampas
    citation_rate: float = 1.0  # respuestas reales con cita / respuestas reales contestadas
    must_cite_rate: float = 1.0  # items con must_cite cumplido
    rojo_rate: float = 0.0
    avg_faithfulness: float | None = None
    avg_latency_ms: float = 0.0
    details: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


def _must_cite_ok(item: GoldenItem, ans: Answer) -> bool:
    if not item.must_cite:
        return True
    cited = " ".join(c.fuente.lower() for c in ans.citations)
    return any(sub.lower() in cited for sub in item.must_cite)


def compute_metrics(pairs: list[tuple[GoldenItem, Answer]]) -> EvalMetrics:
    m = EvalMetrics(n=len(pairs))
    if not pairs:
        return m

    traps = [(i, a) for i, a in pairs if i.is_trap]
    real = [(i, a) for i, a in pairs if not i.is_trap]
    m.n_traps, m.n_real = len(traps), len(real)

    if traps:
        m.correct_abstention_rate = sum(1 for _, a in traps if a.abstained) / len(traps)

    if real:
        answered = [(i, a) for i, a in real if not a.abstained]
        m.n_answered = len(answered)
        m.answered_rate = len(answered) / len(real)
        if answered:
            m.citation_rate = sum(1 for _, a in answered if a.citations) / len(answered)
        m.must_cite_rate = sum(1 for i, a in real if _must_cite_ok(i, a)) / len(real)

    m.rojo_rate = sum(1 for _, a in pairs if a.semaforo.value == "rojo") / len(pairs)
    m.avg_latency_ms = sum(a.latency_ms for _, a in pairs) / len(pairs)

    faiths = [a.faithfulness for _, a in pairs if a.faithfulness is not None]
    m.avg_faithfulness = (sum(faiths) / len(faiths)) if faiths else None

    m.details = [
        {
            "id": i.id,
            "is_trap": i.is_trap,
            "abstained": a.abstained,
            "semaforo": a.semaforo.value,
            "n_citations": len(a.citations),
            "faithfulness": a.faithfulness,
            "must_cite_ok": _must_cite_ok(i, a),
            "latency_ms": a.latency_ms,
        }
        for i, a in pairs
    ]
    return m


def gate(m: EvalMetrics) -> tuple[bool, list[str]]:
    """Decide si las métricas pasan el umbral. Devuelve (passed, fallos)."""
    failures: list[str] = []
    if m.n_traps and m.correct_abstention_rate < GATE_THRESHOLDS["correct_abstention_rate"]:
        failures.append(
            f"correct_abstention_rate {m.correct_abstention_rate:.2f} < {GATE_THRESHOLDS['correct_abstention_rate']}"
        )
    # Solo exigir citación si de verdad hubo respuestas reales contestadas
    # (evita un pase/fallo falso en datasets de solo-trampas o todo-abstención).
    if m.n_answered > 0 and m.citation_rate < GATE_THRESHOLDS["citation_rate"]:
        failures.append(f"citation_rate {m.citation_rate:.2f} < {GATE_THRESHOLDS['citation_rate']}")
    if m.avg_faithfulness is not None and m.avg_faithfulness < GATE_THRESHOLDS["avg_faithfulness"]:
        failures.append(
            f"avg_faithfulness {m.avg_faithfulness:.2f} < {GATE_THRESHOLDS['avg_faithfulness']}"
        )
    return (len(failures) == 0, failures)
