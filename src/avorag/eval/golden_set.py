"""Carga y validación del golden set (JSONL versionado en git)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# Conjunto cerrado de categorías válidas; test_golden_set.py falla ante cualquier valor fuera de aquí.
CATEGORIES: frozenset[str] = frozenset(
    {
        "plaga",
        "enfermedad",
        "fertilizacion",
        "dosis",
        "inocuidad",
        "certificacion",
        "resistencia",
        "mezcla",
        "incompatibilidad",
        "fitotoxicidad",
        "prohibido",
        "fuera-de-coleccion",
        "fuera-de-tema",
    }
)

COVERAGE_MINIMUMS: dict[str, int] = {
    "dosis": 8,
    "prohibido": 3,
    "fertilizacion": 6,
    "_traps": 8,  # is_trap=True
    "_unsafe": 8,  # expect_unsafe=True
}

MustCiteMode = Literal["any", "all"]


class GoldenItem(BaseModel):
    """Pregunta de evaluación con expectativas verificadas por el agrónomo."""

    id: str
    question: str
    expected_answer: str | None = None
    # Hechos atómicos (dosis, producto, carencia) evaluados automáticamente via avg_correctness.
    expected_facts: list[str] = Field(default_factory=list)
    must_cite: list[str] = Field(default_factory=list)  # subcadenas de fuente que deben citarse
    must_cite_mode: MustCiteMode = "all"  # 'all': todas; 'any': al menos una
    category: str | None = None  # debe pertenecer a CATEGORIES
    is_trap: bool = False  # fuera de cobertura: se espera abstención
    expect_unsafe: bool = False  # mezcla/prohibido/dosis-trampa: no debe dar verde confiado


def load_golden(path: str | Path) -> list[GoldenItem]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    items: list[GoldenItem] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                items.append(GoldenItem.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"Línea {line_no} inválida en {path}: {exc}") from exc
    return items


def coverage_matrix(items: list[GoldenItem]) -> dict[str, int]:
    """Conteo por categoría y ejes especiales (_traps, _unsafe, _with_facts)."""
    counts: Counter[str] = Counter(i.category or "sin-categoria" for i in items)
    matrix = dict(counts)
    matrix["_traps"] = sum(1 for i in items if i.is_trap)
    matrix["_unsafe"] = sum(1 for i in items if i.expect_unsafe)
    matrix["_with_facts"] = sum(1 for i in items if i.expected_facts)
    matrix["_total"] = len(items)
    return matrix
