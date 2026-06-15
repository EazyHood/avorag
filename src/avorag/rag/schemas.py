"""Esquemas de entrada/salida del RAG."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Semaforo(StrEnum):
    VERDE = "verde"  # auto-responde
    AMARILLO = "amarillo"  # responde con cautela / pide datos
    ROJO = "rojo"  # requiere agrónomo (HITL) o se rehúsa


class AbstentionType(StrEnum):
    NONE = "none"
    OUT_OF_CONTENT = "out_of_content"  # no hay info suficiente en el corpus
    OUT_OF_CONTEXT = "out_of_context"  # pregunta no agrícola
    OUT_OF_COLLECTION = "out_of_collection"  # cultivo/tema fuera de cobertura


class Citation(BaseModel):
    chunk_id: str
    fuente: str
    pagina: int | None = None
    fecha_publicacion: str | None = None
    url: str | None = None
    doi: str | None = None
    # Procedencia visible: la neutralidad comercial se VE, no se promete (autoridad + licencia).
    nivel_autoridad: str | None = None
    licencia_uso: str | None = None
    quote: str | None = None


class RetrievedContext(BaseModel):
    chunk_id: str
    fuente: str
    pagina: int | None = None
    score: float
    content: str


class Answer(BaseModel):
    question: str
    text: str
    semaforo: Semaforo = Semaforo.VERDE
    abstained: bool = False
    abstention_type: AbstentionType = AbstentionType.NONE
    faithfulness: float | None = None
    reason: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    contexts: list[RetrievedContext] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)  # preguntas de seguimiento sugeridas
    conflict: list[str] = Field(default_factory=list)  # discrepancias entre fuentes citadas
    warnings: list[str] = Field(default_factory=list)  # avisos (p.ej. dato desactualizado)
    disclaimer: str = ""
    latency_ms: int = 0
    provider_info: dict = Field(default_factory=dict)
