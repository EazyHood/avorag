"""Guardarraíles de seguridad: dosis rastreable, categoría toxicológica, fidelidad y semáforo."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from avorag.agro_terms import active_ingredients_in, extract_active_ingredient
from avorag.logging import get_logger
from avorag.providers import get_judge_llm_provider
from avorag.rag.schemas import AbstentionType, Semaforo
from avorag.retrieval.types import ScoredChunk

log = get_logger(__name__)

# Unidades agronómicas de dosis.
# OJO: NO incluir "mm" — son milímetros de lluvia (clima), no una dosis fitosanitaria; incluirlos
# marcaba "2.000 mm de lluvia" como dosis no respaldada y volvía ROJO respuestas de suelo/clima.
_UNITS = r"(?:%|ppm|cc\s?/\s?l|cc|ml|l\s?/\s?ha|kg\s?/\s?ha|g\s?/\s?l|g\s?/\s?ha|kg|gr|g|l|litros|cm3)"
# (?!\w) en lugar de \b: captura unidades que terminan en no-letra (p.ej. "1.8%").
_DOSE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s?" + _UNITS + r"(?!\w)", re.IGNORECASE)


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


def extract_dose_numbers(text: str) -> list[str]:
    """Devuelve los valores numéricos (normalizados, con punto decimal) de cada dosis."""
    return [m.group(1).replace(",", ".") for m in _DOSE_RE.finditer(text)]


# Normaliza unidades para comparar dosis equivalentes (5 kg/ha == 5000 g/ha).
_DOSE_PAIR_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s?(" + _UNITS + r")(?!\w)", re.IGNORECASE)
_UNIT_FACTORS: dict[str, tuple[str, float]] = {
    "%": ("pct", 1.0),
    "ppm": ("ppm", 1.0),
    "g": ("mass", 1.0),
    "gr": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "ml": ("vol", 1.0),
    "cc": ("vol", 1.0),
    "cm3": ("vol", 1.0),
    "l": ("vol", 1000.0),
    "litros": ("vol", 1000.0),
    "g/ha": ("mass_ha", 1.0),
    "kg/ha": ("mass_ha", 1000.0),
    "l/ha": ("vol_ha", 1000.0),
    "g/l": ("conc_g_l", 1.0),
    "cc/l": ("conc_ml_l", 1.0),
}


# Un "%" aparece en pendiente, materia orgánica, saturación, humedad, arcilla/arena… no solo en
# concentración de plaguicida. Un "%" en ese contexto NO es una dosis fitosanitaria.
_NON_DOSE_PCT_CTX = re.compile(
    r"pendient|inclinaci|declive|talud|saturaci|humedad|materia\s+org|\bm\.?o\.?\b|arcill|"
    r"areno|\barena\b|retenci[oó]n|drenaj|capacidad de campo|saturaci[oó]n de al",
    re.IGNORECASE,
)


def _is_non_dose_match(text: str, m: re.Match) -> bool:
    """True si el match es un '%' en contexto de pendiente/suelo (no una dosis fitosanitaria)."""
    unit = re.sub(r"\s+", "", (m.group(2) if m.lastindex and m.lastindex >= 2 else "").lower())
    if unit != "%":
        return False
    window = text[max(0, m.start() - 40) : min(len(text), m.end() + 15)]
    return bool(_NON_DOSE_PCT_CTX.search(window))


def _canonical_doses(text: str) -> set[tuple[str, float]]:
    """Extrae dosis como (dimensión, valor en unidad base), normalizando equivalencias."""
    out: set[tuple[str, float]] = set()
    for m in _DOSE_PAIR_RE.finditer(text):
        if _is_non_dose_match(text, m):
            continue
        value = float(m.group(1).replace(",", "."))
        unit = re.sub(r"\s+", "", m.group(2).lower())
        dim, factor = _UNIT_FACTORS.get(unit, (unit, 1.0))
        out.add((dim, round(value * factor, 6)))
    return out


def doses_grounded(answer_text: str, contexts_text: str) -> tuple[bool, list[str]]:
    """Cada dosis de la respuesta debe estar respaldada por una dosis equivalente en el contexto."""
    ctx = _canonical_doses(contexts_text)
    unsupported: list[str] = []
    for m in _DOSE_PAIR_RE.finditer(answer_text):
        if _is_non_dose_match(answer_text, m):
            continue
        value = float(m.group(1).replace(",", "."))
        unit = re.sub(r"\s+", "", m.group(2).lower())
        dim, factor = _UNIT_FACTORS.get(unit, (unit, 1.0))
        if (dim, round(value * factor, 6)) not in ctx:
            unsupported.append(m.group(1).replace(",", "."))
    return (len(unsupported) == 0, unsupported)


# Periodo de carencia (PHI) y reingreso — crítico para LMR/rechazos.
_PHI_TERMS = r"(?:carencia|per[ií]odo de seguridad|periodo de seguridad|plazo de seguridad|reingreso|reentrada)"
_PHI_RE = re.compile(
    rf"(?:{_PHI_TERMS}\D{{0,40}}?(\d+)\s*(d[ií]as?|horas?|h)\b)"
    rf"|(?:(\d+)\s*(d[ií]as?|horas?|h)\b\D{{0,25}}?{_PHI_TERMS})",
    re.IGNORECASE,
)


def _phi_values(text: str) -> set[tuple[str, float]]:
    out: set[tuple[str, float]] = set()
    for m in _PHI_RE.finditer(text):
        num = m.group(1) or m.group(3)
        unit = (m.group(2) or m.group(4) or "").lower()
        if not num:
            continue
        base = "hora" if unit.startswith("h") else "dia"
        out.add((base, float(num.replace(",", "."))))
    return out


def phi_grounded(answer_text: str, contexts_text: str) -> tuple[bool, list[str]]:
    """El periodo de carencia/reingreso de la respuesta debe aparecer en el contexto."""
    ctx = _phi_values(contexts_text)
    unsupported = [f"{int(v)} {u}" for (u, v) in _phi_values(answer_text) if (u, v) not in ctx]
    return (len(unsupported) == 0, unsupported)


_ACTIONABLE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?\s?" + _UNITS + r")|" + _PHI_TERMS + r"|\baplica(?:r|ci[oó]n)?\b|\bdosis\b",
    re.IGNORECASE,
)


def has_actionable_recommendation(answer_text: str) -> bool:
    """True si la respuesta contiene una dosis, carencia o indicación de aplicación."""
    return bool(_ACTIONABLE_RE.search(answer_text))


_FOREIGN_SCRIPT_RE = re.compile(
    "[　-〿぀-ヿ㐀-䶿一-鿿가-힯"  # CJK, kana, hangul
    "Ѐ-ӿ֐-׿؀-ۿ]"  # cirílico, hebreo, árabe
)


def contains_foreign_script(answer_text: str) -> bool:
    """True si el texto incluye caracteres de alfabetos ajenos al español (CJK, hangul, cirílico,
    hebreo, árabe). Detecta la deriva idiomática del LLM: la respuesta debe ir 100% en español."""
    return bool(_FOREIGN_SCRIPT_RE.search(answer_text))


@dataclass
class DoseSafety:
    safe: bool
    issues: list[str]
    cat_i_ii: bool


_SAFETY_SYSTEM = (
    "Eres un ingeniero agrónomo revisor de seguridad fitosanitaria. Dada una RESPUESTA y los "
    "FRAGMENTOS fuente, verifica que CADA recomendación accionable de la respuesta esté EXACTAMENTE "
    "respaldada por un fragmento, asociando correctamente: PRODUCTO/ingrediente activo + PLAGA u "
    "objetivo + DOSIS (valor y unidad) + PERIODO DE CARENCIA/reingreso. Es un PROBLEMA GRAVE si la "
    "respuesta pega una dosis o una carencia a un producto o a una plaga DISTINTOS de los del "
    "fragmento, o si inventa una carencia/dosis. Indica además si algún producto citado es de "
    'categoría toxicológica I o II. Devuelve SOLO un JSON: {"seguro": true|false, '
    '"problemas": ["..."], "categoria_I_II": true|false}.'
)


def dose_safety_judge(answer: str, contexts_text: str) -> DoseSafety | None:
    """Verifica la asociación producto–plaga–dosis–carencia. None si el juez falla."""
    try:
        llm = get_judge_llm_provider()
        raw = llm.complete(
            _SAFETY_SYSTEM,
            f"FRAGMENTOS:\n{contexts_text}\n\nRESPUESTA:\n{answer}\n\nJSON:",
            temperature=0.0,
            max_tokens=400,
        )
        data = _extract_json(raw)
        if not data:
            return None
        return DoseSafety(
            safe=bool(data.get("seguro", False)),
            issues=[str(x) for x in data.get("problemas", [])][:4],
            cat_i_ii=bool(data.get("categoria_I_II", False)),
        )
    except Exception as exc:
        log.warning("dose_safety_judge_failed", error=str(exc))
        return None


def cited_categoria_toxicologica(chunks: list[ScoredChunk]) -> set[str]:
    """Categorías toxicológicas presentes en los fragmentos."""
    return {str(sc.chunk.meta.get("categoria_toxicologica", "N/A")).upper() for sc in chunks}


# Verificación determinista por fragmento de origen (asocia cada dosis a su producto/registro).


def _chunk_content(sc: ScoredChunk) -> str:
    return getattr(sc.chunk, "content", "") or ""


def _chunk_meta(sc: ScoredChunk) -> dict:
    return getattr(sc.chunk, "meta", {}) or {}


def _chunk_actives(sc: ScoredChunk) -> set[str]:
    """Ingredientes activos y productos asociados a un fragmento (texto + filas estructuradas)."""
    actives = active_ingredients_in(_chunk_content(sc))
    meta = _chunk_meta(sc)
    for key in ("ingrediente_activo", "producto"):
        v = meta.get(key)
        if v:
            actives.add(str(v).lower())
    for row in meta.get("dosis_estructurada") or []:
        for key in ("ingrediente_activo", "producto"):
            v = row.get(key)
            if v:
                actives.add(str(v).lower())
    return actives


def dose_product_grounded(answer_text: str, chunks: list[ScoredChunk]) -> tuple[bool, list[str]]:
    """Cada dosis debe co-ocurrir en el mismo fragmento con el producto/i.a. que la respuesta le asocia."""
    answer_actives = active_ingredients_in(answer_text)
    unsupported: list[str] = []
    for m in _DOSE_PAIR_RE.finditer(answer_text):
        if _is_non_dose_match(answer_text, m):
            continue
        value = float(m.group(1).replace(",", "."))
        unit = re.sub(r"\s+", "", m.group(2).lower())
        dim, factor = _UNIT_FACTORS.get(unit, (unit, 1.0))
        target = (dim, round(value * factor, 6))
        supported = False
        for sc in chunks:
            if target in _canonical_doses(_chunk_content(sc)) and (
                not answer_actives or (answer_actives & _chunk_actives(sc))
            ):
                supported = True
                break
        if not supported:
            unsupported.append(m.group(1).replace(",", "."))
    return (len(unsupported) == 0, unsupported)


def recommends_pesticide(answer_text: str) -> bool:
    """True si la respuesta recomienda un fitosanitario a dosis (no fertilizante)."""
    return (
        bool(_DOSE_PAIR_RE.search(answer_text))
        and extract_active_ingredient(answer_text) is not None
    )


def ica_registro_ok(chunks: list[ScoredChunk]) -> bool:
    """True si hay al menos un fragmento con registro ICA vigente de autoridad oficial."""
    for sc in chunks:
        meta = _chunk_meta(sc)
        if (
            meta.get("registro_ica")
            and str(meta.get("vigencia", "por-verificar")) != "caducado"
            and str(meta.get("nivel_autoridad", "")) == "oficial-regulador"
        ):
            return True
    return False


_DOSE_CITE_RE = re.compile(r"(\d+(?:[.,]\d+)?\s?" + _UNITS + r")\D{0,40}?\[(\d+)\]", re.IGNORECASE)


def citation_supports_claim(answer_text: str, chunks: list[ScoredChunk]) -> tuple[bool, list[str]]:
    """Cada 'dosis … [n]' debe aparecer en el chunk n; detecta también citas fuera de rango."""
    issues: list[str] = []
    for m in _DOSE_CITE_RE.finditer(answer_text):
        dose_txt = m.group(1).strip()
        n = int(m.group(2))
        if not (1 <= n <= len(chunks)):
            issues.append(f"cita [{n}] inexistente")
            continue
        if not (_canonical_doses(dose_txt) & _canonical_doses(_chunk_content(chunks[n - 1]))):
            issues.append(f"[{n}] no contiene «{dose_txt}»")
    for m in re.finditer(r"\[(\d+)\]", answer_text):
        n = int(m.group(1))
        if not (1 <= n <= len(chunks)):
            issues.append(f"cita [{n}] fuera de rango")
    uniq: list[str] = []
    for i in issues:
        if i not in uniq:
            uniq.append(i)
    return (len(uniq) == 0, uniq[:4])


def dose_conflicts(chunks: list[ScoredChunk]) -> list[str]:
    """Detecta dosis sustancialmente distintas (ratio > 1.5) para un mismo i.a. en ≥2 fragmentos."""
    by_active: dict[str, dict[str, set[float]]] = {}
    for sc in chunks:
        doses = _canonical_doses(_chunk_content(sc))
        for active in _chunk_actives(sc):
            for dim, val in doses:
                by_active.setdefault(active, {}).setdefault(dim, set()).add(val)
    conflicts: list[str] = []
    for active, bydim in by_active.items():
        for _dim, vals in bydim.items():
            if len(vals) >= 2 and max(vals) / max(min(vals), 1e-9) >= 1.5:
                svals = sorted(vals)
                if len(svals) > 3:
                    pretty = f"de {round(svals[0], 1)} a {round(svals[-1], 1)}, {len(svals)} valores distintos"
                else:
                    pretty = ", ".join(str(round(v, 1)) for v in svals)
                conflicts.append(f"{active}: dosis dispares entre fuentes ({pretty})")
    return conflicts[:3]


def is_offlabel(answer_text: str, chunks: list[ScoredChunk]) -> bool:
    """True si la dosis recomendada solo se respalda en fragmentos de otro cultivo."""
    if not recommends_pesticide(answer_text):
        return False
    supporting = [
        sc for sc in chunks if _canonical_doses(_chunk_content(sc)) & _canonical_doses(answer_text)
    ]
    if not supporting:
        return False
    return all(str(_chunk_meta(sc).get("cultivo", "hass")).lower() != "hass" for sc in supporting)


@lru_cache(maxsize=1)
def _banned_index() -> dict[str, dict]:
    path = Path(__file__).resolve().parents[3] / "data" / "prohibidos_co.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        log.warning("banned_list_load_failed", error=str(exc))
        return {}
    return {str(it["ingrediente_activo"]).lower(): it for it in data.get("ingredientes", [])}


def banned_ingredients_in_answer(answer_text: str, country: str = "CO") -> list[str]:
    """Ingredientes activos prohibidos o restringidos mencionados en la respuesta."""
    low = _strip_accents(answer_text)
    hits: list[str] = []
    for ia, item in _banned_index().items():
        if _strip_accents(ia) in low:
            hits.append(f"{ia} ({item.get('estado', 'restringido')}: {item.get('motivo', '')})")
    return hits[:3]


def stale_data_warnings(chunks: list[ScoredChunk]) -> list[str]:
    """Avisa cuando un fragmento de registro/dosis trae fecha antigua. No bloquea."""
    warnings: list[str] = []
    for sc in chunks:
        meta = _chunk_meta(sc)
        fecha = meta.get("fecha_dato") or meta.get("fecha_publicacion")
        if meta.get("registro_ica") and fecha:
            msg = f"Dato de registro fechado «{fecha}»: verifica la vigencia actual en SimplifICA (ICA)."
            if msg not in warnings:
                warnings.append(msg)
    return warnings[:2]


# Clasificación de intención.
_HASS_TERMS = {"aguacate", "hass", "palta", "palto"}
_OTHER_CROPS = {
    "tomate",
    "papa",
    "patata",
    "maiz",
    "arroz",
    "cafe",
    "cacao",
    "cana",
    "banano",
    "platano",
    "fresa",
    "cebolla",
    "frijol",
    "trigo",
    "soya",
    "soja",
    "mango",
    "citrico",
    "naranja",
    "pina",
    "yuca",
    "sorgo",
    "algodon",
    "uva",
    "lechuga",
}
_AGRO_SIGNAL = {
    "cultivo",
    "planta",
    "arbol",
    "hoja",
    "fruto",
    "flor",
    "raiz",
    "plaga",
    "enfermedad",
    "hongo",
    "riego",
    "agua",
    "fertiliz",
    "abono",
    "nutricion",
    "suelo",
    "dosis",
    "aplicar",
    "fumig",
    "poda",
    "cosecha",
    "siembra",
    "semilla",
    "trips",
    "acaro",
    "mancha",
    "pudricion",
    "carencia",
    "ica",
    "pesticida",
    "fitosanitario",
    "rendimiento",
    "produccion",
    "finca",
}


def is_other_crop(question: str) -> bool:
    """True si la pregunta es claramente sobre OTRO cultivo y no menciona aguacate Hass."""
    q = _strip_accents(question)
    if any(h in q for h in _HASS_TERMS):
        return False
    return any(re.search(rf"\b{c}", q) for c in _OTHER_CROPS)


def has_agronomic_signal(question: str) -> bool:
    """True si la pregunta contiene alguna señal agronómica reconocible."""
    q = _strip_accents(question)
    return any(t in q for t in (_AGRO_SIGNAL | _HASS_TERMS | _OTHER_CROPS))


def classify_intent(question: str) -> AbstentionType | None:
    """Pre-clasificación sin embedding. None si se puede continuar con la recuperación."""
    if is_other_crop(question):
        return AbstentionType.OUT_OF_COLLECTION
    return None


_JUDGE_SYSTEM = (
    "Eres un evaluador estricto de fidelidad. Dado un CONTEXTO y una RESPUESTA, "
    "determinas si TODA afirmación de la respuesta está respaldada por el contexto. "
    'Devuelves SOLO un JSON: {"faithful": true|false, "score": 0.0-1.0, '
    '"unsupported": ["..."]}.'
)


def faithfulness_judge(
    question: str, answer: str, contexts_text: str
) -> tuple[float | None, list[str]]:
    """LLM-as-judge de fidelidad. (None, []) si falla — el pipeline lo trata como AMARILLO."""
    try:
        llm = get_judge_llm_provider()
        raw = llm.complete(
            _JUDGE_SYSTEM,
            f"CONTEXTO:\n{contexts_text}\n\nPREGUNTA:\n{question}\n\nRESPUESTA:\n{answer}\n\nJSON:",
            temperature=0.0,
            max_tokens=300,
        )
        data = _extract_json(raw)
        if not data:
            return None, []
        score = float(data.get("score", 1.0 if data.get("faithful") else 0.0))
        return max(0.0, min(1.0, score)), list(data.get("unsupported", []))
    except Exception as exc:
        log.warning("faithfulness_judge_failed", error=str(exc))
        return None, []


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def decide_semaforo(
    *,
    doses_ok: bool,
    cat_tox: set[str],
    faithfulness: float | None,
    has_citations: bool = True,
    judge_failed: bool = False,
    phi_ok: bool = True,
    safety: DoseSafety | None = None,
    safety_required: bool = False,
    faithfulness_threshold: float = 0.6,
    banned: list[str] | None = None,
    offlabel: bool = False,
    registro_ok: bool = True,
    registro_required: bool = False,
    citation_ok: bool = True,
    conflicts: list[str] | None = None,
    language_ok: bool = True,
) -> tuple[Semaforo, str]:
    """Combina las señales en un semáforo con razón. Prioridad: idioma > prohibido > off-label >
    dosis > registro > PHI > cat I/II > asociación > cita > conflicto > fidelidad > citas."""
    banned = banned or []
    conflicts = conflicts or []
    if not language_ok:
        return (
            Semaforo.ROJO,
            "La generación se desvió a otro idioma; la respuesta no es confiable. "
            "Vuelve a hacer la consulta.",
        )
    if banned:
        return (
            Semaforo.ROJO,
            f"Ingrediente prohibido o restringido: {'; '.join(banned[:2])}. No recomendar; "
            "verificar la resolución ICA vigente.",
        )
    if offlabel:
        return (
            Semaforo.ROJO,
            "Uso off-label: la dosis solo se respalda en fuentes de OTRO cultivo. Requiere agrónomo.",
        )
    if not doses_ok:
        return (
            Semaforo.ROJO,
            "Dosis no rastreable al producto correcto en una fuente citada: requiere validación "
            "de un agrónomo.",
        )
    if registro_required and not registro_ok:
        return (
            Semaforo.ROJO,
            "Dosis de un producto fitosanitario sin etiqueta ICA registrada y vigente en las "
            "fuentes citadas: no es rastreable a un registro. Requiere validación de un agrónomo.",
        )
    if not phi_ok:
        return (
            Semaforo.ROJO,
            "Periodo de carencia no rastreable a una fuente: riesgo de superar el LMR y rechazo "
            "en destino. Requiere validación de un agrónomo.",
        )
    # Cat II coarse (fragmento de registro) → AMARILLO; juez distingue el producto recomendado.
    if "I" in cat_tox or (safety is not None and safety.cat_i_ii):
        return (
            Semaforo.ROJO,
            "Producto de categoría toxicológica I/II: requiere receta firmada por profesional.",
        )
    if safety is not None and not safety.safe:
        detalle = "; ".join(safety.issues[:2]) if safety.issues else "asociación no verificable"
        return (
            Semaforo.ROJO,
            f"Asociación producto–plaga–dosis–carencia insegura: {detalle}. Requiere agrónomo.",
        )
    if safety_required and safety is None:
        return (
            Semaforo.AMARILLO,
            "No se pudo verificar la asociación dosis–producto–plaga (juez no disponible): revisar.",
        )
    if "II" in cat_tox:
        return (
            Semaforo.AMARILLO,
            "La evidencia citada incluye productos de categoría toxicológica II: verifica que el "
            "recomendado no lo sea y manéjalo con precaución (EPP, receta).",
        )
    if not citation_ok:
        return (
            Semaforo.AMARILLO,
            "Una cifra citada no aparece en el fragmento citado: revisar la cita antes de actuar.",
        )
    if conflicts:
        return (
            Semaforo.AMARILLO,
            f"Las fuentes citadas discrepan ({conflicts[0]}): revisar cuál aplica a tu caso.",
        )
    if judge_failed:
        return Semaforo.AMARILLO, "No se pudo verificar la fidelidad (juez no disponible): revisar."
    if faithfulness is not None and faithfulness < faithfulness_threshold:
        return Semaforo.AMARILLO, "Fidelidad por debajo del umbral: revisar antes de actuar."
    if not has_citations:
        return Semaforo.AMARILLO, "Respuesta sin citas de fuente: requiere verificación."
    return Semaforo.VERDE, "Respuesta respaldada por las fuentes citadas."
