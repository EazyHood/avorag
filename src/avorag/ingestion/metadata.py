"""Esquema de metadata por chunk (habilita geofiltro y citación a fuente)."""

from __future__ import annotations

import re
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


# --- Extracción de metadatos reales del texto del fragmento (revive el semáforo Cat I/II) ---
_CATTOX_RE = re.compile(
    r"(?:categor[ií]a\s+toxicol[oó]gica|cat\.?\s*tox\.?)\s*:?\s*(IV|III|II|I)\b", re.IGNORECASE
)
_REGICA_RE = re.compile(
    r"(?:registro\s+(?:nacional\s+)?ica|reg\.?\s*ica|registro\s+nacional)\s*(?:n[o°º.]*\s*)?([0-9]{2,6})",
    re.IGNORECASE,
)
_SEVERITY = {"I": 0, "II": 1, "III": 2, "IV": 3}
_TEMA_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "fertilizacion",
        (
            "fertiliz",
            "nutrici",
            "nitrógeno",
            "nitrogeno",
            "fósforo",
            "fosforo",
            "potasio",
            "abono",
            "enmienda",
            "encalado",
        ),
    ),
    (
        "inocuidad",
        (
            "carencia",
            "lmr",
            "residuo",
            "inocuidad",
            "exportaci",
            "límite máximo",
            "limite maximo",
            "reingreso",
        ),
    ),
    (
        "enfermedad",
        (
            "enfermedad",
            "hongo",
            "antracnosis",
            "pudrici",
            "mancha negra",
            "marchit",
            "phytophthora",
            "lenticelosis",
        ),
    ),
    (
        "plaga",
        (
            "plaga",
            "trips",
            "ácaro",
            "acaro",
            "insecto",
            "barrenador",
            "monalonion",
            "heilipus",
            "stenoma",
            "perforador",
        ),
    ),
    ("certificacion", ("globalgap", "global gap", "certificaci", "rainforest")),
]
_PESTS = (
    "trips",
    "monalonion",
    "heilipus",
    "stenoma",
    "ácaros",
    "acaros",
    "barrenador",
    "pega-pega",
    "lenticelosis",
)


def extract_chunk_fields(text: str) -> dict[str, str | None]:
    """Extrae del texto del fragmento la categoría toxicológica (la más severa), el registro
    ICA, el tema y la plaga objetivo. Sin esto, el semáforo Cat I/II nunca se dispara."""
    low = text.lower()
    cats = [m.group(1).upper() for m in _CATTOX_RE.finditer(text)]
    categoria = min(cats, key=lambda c: _SEVERITY.get(c, 9)) if cats else "N/A"
    reg = _REGICA_RE.search(text)
    tema = next((name for name, kws in _TEMA_KEYWORDS if any(k in low for k in kws)), None)
    plaga = next((p for p in _PESTS if p in low), None)
    return {
        "categoria_toxicologica": categoria,
        "registro_ica": reg.group(1) if reg else None,
        "tema": tema,
        "plaga_objetivo": plaga,
    }
