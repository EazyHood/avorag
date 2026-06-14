"""Esquema de metadata por chunk (habilita geofiltro y citación a fuente)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CategoriaToxicologica = Literal["N/A", "I", "II", "III", "IV"]
NivelAutoridad = Literal["oficial-regulador", "gremio", "academico", "interno-cliente"]


class ChunkMetadata(BaseModel):
    """Metadata citable y filtrable de cada fragmento."""

    pais: str = "CO"
    cultivo: str = "hass"
    tema: str | None = None  # plaga | enfermedad | fertilizacion | inocuidad | certificacion
    plaga_objetivo: str | None = None
    categoria_toxicologica: CategoriaToxicologica = "N/A"
    fuente: str = "por-verificar"
    pagina: int | None = None
    fecha_publicacion: str | None = None
    vigencia: Literal["vigente", "caducado", "por-verificar"] = "por-verificar"
    nivel_autoridad: NivelAutoridad = "oficial-regulador"
    registro_ica: str | None = None
    licencia_uso: str = "por-verificar"
    url: str | None = None  # enlace de descarga directa de la fuente
    doi: str | None = None  # DOI cuando la fuente lo tenga

    def as_dict(self) -> dict:
        return self.model_dump(exclude_none=False)


class DocumentMeta(BaseModel):
    """Metadata a nivel de documento, provista en la ingesta."""

    fuente: str = Field(
        ..., description="Nombre oficial citable, p.ej. 'Agrosavia — Modelo Productivo Hass'"
    )
    titulo: str | None = None
    pais: str = "CO"
    cultivo: str = "hass"
    licencia: str = "por-verificar"
    nivel_autoridad: NivelAutoridad = "oficial-regulador"
    fecha_publicacion: str | None = None
    corpus_version: str | None = None
    url: str | None = None  # enlace de descarga directa de la fuente
    doi: str | None = None  # DOI cuando la fuente lo tenga
