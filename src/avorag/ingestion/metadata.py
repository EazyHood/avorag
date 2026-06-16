"""Esquema de metadata por chunk (habilita geofiltro y citación a fuente)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from avorag.agro_terms import extract_active_ingredient

CategoriaToxicologica = Literal["N/A", "I", "II", "III", "IV"]
NivelAutoridad = Literal["oficial-regulador", "gremio", "academico", "interno-cliente"]


class DoseRow(BaseModel):
    """Fila de dosis estructurada extraída de tablas de registro/etiqueta."""

    producto: str | None = None
    ingrediente_activo: str | None = None
    dosis_texto: str | None = None  # tal como aparece (p.ej. "200-300 cc/100 L")
    plaga: str | None = None
    carencia_texto: str | None = None  # carencia/reingreso tal como aparece
    registro_ica: str | None = None
    categoria_toxicologica: str | None = None


class ChunkMetadata(BaseModel):
    """Metadata citable y filtrable de cada fragmento."""

    pais: str = "CO"
    cultivo: str = "hass"
    tema: str | None = None  # plaga | enfermedad | fertilizacion | inocuidad | certificacion
    plaga_objetivo: str | None = None
    producto: str | None = None  # nombre comercial detectado en el fragmento
    ingrediente_activo: str | None = None  # i.a. detectado en el fragmento
    categoria_toxicologica: CategoriaToxicologica = "N/A"
    dosis_estructurada: list[dict] = Field(default_factory=list)  # filas DoseRow serializadas
    fuente: str = "por-verificar"
    pagina: int | None = None
    fecha_publicacion: str | None = None
    fecha_dato: str | None = (
        None  # fecha a la que se refiere el dato (p.ej. registro PQUA mar-2022)
    )
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


_DOSE_CELL_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:%|ppm|cc\s?/\s?\d*\s?l|cc|ml|l\s?/\s?ha|kg\s?/\s?ha|g\s?/\s?l|g\s?/\s?ha|kg|gr|g|l)\b",
    re.IGNORECASE,
)


def _classify_header(cell: str) -> str | None:
    """Mapea una celda de encabezado de tabla a una clave canónica de DoseRow."""
    c = cell.lower()
    c = "".join(ch for ch in c if ch.isalnum() or ch.isspace())
    if "ingredient" in c or "activo" in c or c.strip() in ("ia", "i a"):
        return "ingrediente_activo"
    if "producto" in c or "comercial" in c or "marca" in c:
        return "producto"
    if "dosis" in c or "dosificac" in c:
        return "dosis"
    if "plaga" in c or "objetivo" in c or "blanco" in c or "enfermedad" in c:
        return "plaga"
    if (
        "carencia" in c
        or "reingreso" in c
        or "reentrada" in c
        or "seguridad" in c
        or c.strip() == "pc"
    ):
        return "carencia"
    if "registro" in c or c.strip() == "reg":
        return "registro_ica"
    if "categor" in c or "toxicol" in c:
        return "categoria"
    return None


def _split_md_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator_row(line: str) -> bool:
    return set(line.replace("|", "").strip()) <= set("-: ")


def extract_dose_rows(text: str) -> list[DoseRow]:
    """Parsea tablas Markdown del fragmento a filas DoseRow; [] si no hay tabla reconocible."""
    md_lines = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    if len(md_lines) < 2:
        return []
    header = _split_md_row(md_lines[0])
    keymap = {i: _classify_header(h) for i, h in enumerate(header)}
    if not any(v in ("dosis", "producto", "ingrediente_activo") for v in keymap.values()):
        return []
    rows: list[DoseRow] = []
    for line in md_lines[1:]:
        if _is_separator_row(line):
            continue
        cells = _split_md_row(line)
        rec: dict[str, str] = {}
        for i, cell in enumerate(cells):
            key = keymap.get(i)
            if key and cell:
                rec[key] = cell
        row = _build_dose_row(rec, cells)
        if row is not None:
            rows.append(row)
    return rows


def _build_dose_row(rec: dict[str, str], cells: list[str]) -> DoseRow | None:
    """Construye una DoseRow desde las celdas mapeadas; None si no aporta nada útil."""
    joined = " ".join(cells)
    dosis_cell = rec.get("dosis", "")
    dosis_match = _DOSE_CELL_RE.search(dosis_cell) or _DOSE_CELL_RE.search(joined)
    ia = rec.get("ingrediente_activo") or extract_active_ingredient(joined)
    reg = rec.get("registro_ica")
    if reg:
        m = re.search(r"\d{2,6}", reg)
        reg = m.group(0) if m else None
    cat = rec.get("categoria")
    if cat:
        m2 = re.search(r"\b(IV|III|II|I)\b", cat)
        cat = m2.group(1) if m2 else None
    producto = rec.get("producto")
    plaga = rec.get("plaga")
    carencia = rec.get("carencia")
    if not (dosis_match or producto or ia):
        return None
    return DoseRow(
        producto=producto or None,
        ingrediente_activo=ia or None,
        dosis_texto=(dosis_match.group(0) if dosis_match else None),
        plaga=plaga or None,
        carencia_texto=carencia or None,
        registro_ica=reg,
        categoria_toxicologica=cat,
    )


# Registro PQUA del ICA: formato columnar, sin tabla Markdown. Se captura por patrón de línea
# solo cuando el chunk parece un registro de producto (evita falsos positivos en prosa).
_REGISTRY_CONTEXT_RE = re.compile(
    r"cat\.?\s*toxic|categor[ií]a\s+toxicol|registros?\s+nacionales|\bpqua\b|ingrediente\s+activo",
    re.IGNORECASE,
)
_STANDALONE_CAT_RE = re.compile(r"(?m)^\s*(IV|III|II|I)\s*$")
_STANDALONE_REG_RE = re.compile(r"(?m)^\s*(\d{3,5})\s*$")


def extract_chunk_fields(text: str) -> dict:
    """Extrae categoría toxicológica, registro ICA, tema, plaga, producto y filas de dosis."""
    low = text.lower()
    dose_rows = extract_dose_rows(text)
    ia = extract_active_ingredient(text) or next(
        (r.ingrediente_activo for r in dose_rows if r.ingrediente_activo), None
    )
    is_registry = ia is not None or bool(_REGISTRY_CONTEXT_RE.search(text))

    cats = [m.group(1).upper() for m in _CATTOX_RE.finditer(text)]
    cats += [r.categoria_toxicologica for r in dose_rows if r.categoria_toxicologica]
    if is_registry:  # formato columnar PQUA
        cats += [m.group(1).upper() for m in _STANDALONE_CAT_RE.finditer(text)]
    categoria = min(cats, key=lambda c: _SEVERITY.get(c, 9)) if cats else "N/A"

    reg = _REGICA_RE.search(text)
    registro = reg.group(1) if reg else None
    if not registro:
        registro = next((r.registro_ica for r in dose_rows if r.registro_ica), None)
    if not registro and is_registry:
        m_reg = _STANDALONE_REG_RE.search(text)
        registro = m_reg.group(1) if m_reg else None

    tema = next((name for name, kws in _TEMA_KEYWORDS if any(k in low for k in kws)), None)
    plaga = next((p for p in _PESTS if p in low), None)
    producto = next((r.producto for r in dose_rows if r.producto), None)
    return {
        "categoria_toxicologica": categoria,
        "registro_ica": registro,
        "tema": tema,
        "plaga_objetivo": plaga,
        "producto": producto,
        "ingrediente_activo": ia,
        "dosis_estructurada": [r.model_dump() for r in dose_rows],
    }
