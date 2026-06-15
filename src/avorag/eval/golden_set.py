"""Carga y validación del golden set (JSONL versionado en git)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class GoldenItem(BaseModel):
    """Una pregunta de evaluación con su respuesta/expectativa verificada por el agrónomo."""

    id: str
    question: str
    expected_answer: str | None = None
    # Hechos atómicos verificables (dosis, producto, carencia, fuente) que la respuesta DEBE
    # contener. A diferencia de expected_answer (texto libre, difícil de comparar), estos SÍ se
    # evalúan automáticamente (avg_correctness) — cierra el hueco #2.
    expected_facts: list[str] = Field(default_factory=list)
    must_cite: list[str] = Field(default_factory=list)  # subcadenas de fuente que deben citarse
    category: str | None = None  # plaga | fertilizacion | dosis | inocuidad | mezcla | prohibido | ...
    is_trap: bool = False  # pregunta fuera de cobertura: se espera ABSTENCIÓN
    # Pregunta PELIGROSA (mezcla/incompatibilidad/fitotoxicidad/prohibido/dosis-trampa): un
    # sistema seguro NO debe dar un verde confiado; debe quedar en ROJO o abstenerse.
    expect_unsafe: bool = False


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
