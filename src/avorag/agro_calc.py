"""Calculadoras agronómicas DETERMINISTAS para Hass de exportación.

Por qué existe: el RAG *cita*, no *calcula*. Decisiones cuantitativas clave —si el lote llegó al
corte de exportación por materia seca, cuánta cal echar por saturación de aluminio, cómo quedan las
relaciones foliares— son aritmética exacta que no debe pasar por un LLM (alucinaría cifras). Aquí se
calculan con fórmulas reconocidas, sin red ni modelo, y por eso sirven igual OFFLINE en el móvil.

Honestidad (la de siempre): los umbrales/bandas son ORIENTATIVOS (varían por mercado, norma y
laboratorio) y la conversión a campo (t/ha de cal) depende de supuestos que se hacen explícitos. Es
apoyo de decisión citado, NO sustituye el criterio del agrónomo ni el análisis de tu laboratorio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── 1) Materia seca (corte de exportación) ──────────────────────────────────────────────────────
# El corte del Hass es por MATERIA SECA, no por color. Mínimo de madurez legal ~20,8% en varias
# normas (CODEX/California); el mercado de exportación suele exigir más (≈23% y a menudo 25%+).
DRY_MATTER_LEGAL_MIN = 20.8
DRY_MATTER_EXPORT_DEFAULT = 23.0


@dataclass
class DryMatterResult:
    materia_seca_pct: float
    umbral_pct: float
    veredicto: str  # "apto" | "limítrofe" | "por debajo"
    nota: str


def dry_matter(
    peso_fresco_g: float, peso_seco_g: float, *, umbral_pct: float = DRY_MATTER_EXPORT_DEFAULT
) -> DryMatterResult:
    """Materia seca por gravimetría (método de microondas/estufa): %MS = peso_seco/peso_fresco×100.

    Pesa una muestra de pulpa fresca, sécala a peso constante y mete ambos pesos. Compara contra el
    umbral de corte (def. 23% de exportación; el mínimo legal de madurez ronda 20,8%)."""
    if peso_fresco_g <= 0 or peso_seco_g <= 0:
        raise ValueError("Los pesos deben ser positivos.")
    if peso_seco_g > peso_fresco_g:
        raise ValueError("El peso seco no puede superar al peso fresco.")
    ms = round(peso_seco_g / peso_fresco_g * 100, 1)
    if ms >= umbral_pct:
        veredicto = "apto"
        nota = f"Materia seca {ms}% ≥ umbral {umbral_pct}%: el lote alcanza el corte indicado."
    elif ms >= umbral_pct - 1.0:
        veredicto = "limítrofe"
        nota = (
            f"Materia seca {ms}% está a menos de 1 punto del umbral {umbral_pct}%: repite el "
            "muestreo en más frutos/árboles antes de decidir cosecha."
        )
    else:
        veredicto = "por debajo"
        nota = (
            f"Materia seca {ms}% < umbral {umbral_pct}%: aún no llega al corte; espera y vuelve a "
            "medir. Cosechar por debajo arriesga rechazo por madurez."
        )
    if ms < DRY_MATTER_LEGAL_MIN:
        nota += f" (Además, por debajo del mínimo de madurez legal ~{DRY_MATTER_LEGAL_MIN}%.)"
    return DryMatterResult(materia_seca_pct=ms, umbral_pct=umbral_pct, veredicto=veredicto, nota=nota)


# ── 2) Encalado por saturación de aluminio ──────────────────────────────────────────────────────
# Fórmula de saturación objetivo (Cochrane et al.): requerimiento (cmol+/kg) = Al − (PSA_obj/100)·CICE.
# El aguacate es sensible al Al; PSA objetivo bajo (def. 15%). La conversión a t/ha usa un factor de
# campo (def. 1,5 t CaCO3/ha por cmol+/kg a 0-20 cm) ajustado por el PRNT/RE de la cal.
AL_SAT_TARGET_DEFAULT = 15.0
LIME_FIELD_FACTOR_DEFAULT = 1.5  # t/ha de CaCO3 puro por cmol(+)/kg (0-20 cm; ver supuestos)


@dataclass
class LimingResult:
    cice_cmol_kg: float
    saturacion_al_pct: float
    requerimiento_cmol_kg: float
    cal_t_ha: float
    requiere_encalado: bool
    nota: str
    supuestos: str


def liming_by_al_saturation(
    *,
    al: float,
    ca: float,
    mg: float,
    k: float,
    na: float = 0.0,
    psa_objetivo_pct: float = AL_SAT_TARGET_DEFAULT,
    factor_campo: float = LIME_FIELD_FACTOR_DEFAULT,
    prnt_pct: float = 100.0,
) -> LimingResult:
    """Requerimiento de cal por saturación de Al. Cationes en cmol(+)/kg (= meq/100 g) del análisis.

    CICE = Al+Ca+Mg+K+Na; %Sat Al = Al/CICE×100; requerimiento = Al − (PSA_obj/100)·CICE. La t/ha es
    una ESTIMACIÓN de campo (supuestos explícitos): ajústala al PRNT real de tu cal y valídala."""
    for nombre, v in (("Al", al), ("Ca", ca), ("Mg", mg), ("K", k), ("Na", na)):
        if v < 0:
            raise ValueError(f"{nombre} no puede ser negativo.")
    if prnt_pct <= 0:
        raise ValueError("El PRNT debe ser positivo.")
    cice = al + ca + mg + k + na
    if cice <= 0:
        raise ValueError("La CICE (suma de cationes) debe ser positiva.")
    sat_al = round(al / cice * 100, 1)
    req = al - (psa_objetivo_pct / 100.0) * cice
    if req <= 0:
        return LimingResult(
            cice_cmol_kg=round(cice, 2),
            saturacion_al_pct=sat_al,
            requerimiento_cmol_kg=0.0,
            cal_t_ha=0.0,
            requiere_encalado=False,
            nota=(
                f"Saturación de Al {sat_al}% ya está en o por debajo del objetivo "
                f"{psa_objetivo_pct}%: no se requiere encalado por aluminio."
            ),
            supuestos="—",
        )
    cal = round(req * factor_campo / (prnt_pct / 100.0), 2)
    return LimingResult(
        cice_cmol_kg=round(cice, 2),
        saturacion_al_pct=sat_al,
        requerimiento_cmol_kg=round(req, 2),
        cal_t_ha=cal,
        requiere_encalado=True,
        nota=(
            f"Saturación de Al {sat_al}% > objetivo {psa_objetivo_pct}%. Estimación: ~{cal} t/ha de "
            "cal. Aplica, incorpora y reanaliza antes de la próxima fertilización."
        ),
        supuestos=(
            f"Factor de campo {factor_campo} t CaCO3/ha por cmol(+)/kg (0-20 cm, densidad ~1,3); "
            f"PRNT de la cal {prnt_pct}%. La profundidad, densidad y PRNT reales cambian la dosis: "
            "ajústala con tu agrónomo y la ficha de tu cal."
        ),
    )


# ── 3) Relaciones foliares (balance nutricional) ────────────────────────────────────────────────
# Calcula las relaciones que el RAG no calcula. Las bandas son ORIENTATIVAS (varían por norma y
# laboratorio); la interpretación final es del agrónomo con el análisis completo. Macros en % de MS.
_FOLIAR_RATIOS: dict[str, tuple[str, str, float, float]] = {
    # clave: (numerador, denominador, banda_baja, banda_alta)
    "K/Ca": ("k", "ca", 0.5, 1.5),
    "Ca/Mg": ("ca", "mg", 2.0, 5.0),
    "Mg/K": ("mg", "k", 0.3, 1.0),
    "N/K": ("n", "k", 1.2, 2.5),
}


@dataclass
class RatioResult:
    valor: float
    banda_ref: str
    estado: str  # "bajo" | "óptimo" | "alto"


@dataclass
class FoliarResult:
    relaciones: dict[str, RatioResult] = field(default_factory=dict)
    nota: str = ""


def foliar_ratios(*, n: float | None = None, k: float | None = None, ca: float | None = None,
                   mg: float | None = None) -> FoliarResult:
    """Relaciones foliares clave (K/Ca, Ca/Mg, Mg/K, N/K) a partir de los macros en % de materia
    seca. Solo calcula las que puede con los datos dados. Bandas ORIENTATIVAS; interpretación final
    del agrónomo con el análisis completo y la referencia de tu laboratorio."""
    vals = {"n": n, "k": k, "ca": ca, "mg": mg}
    for nombre, v in vals.items():
        if v is not None and v <= 0:
            raise ValueError(f"{nombre.upper()} debe ser positivo.")
    out: dict[str, RatioResult] = {}
    for nombre, (num, den, lo, hi) in _FOLIAR_RATIOS.items():
        a, b = vals[num], vals[den]
        if a is None or b is None:
            continue
        r = round(a / b, 2)
        estado = "bajo" if r < lo else ("alto" if r > hi else "óptimo")
        out[nombre] = RatioResult(valor=r, banda_ref=f"{lo}–{hi}", estado=estado)
    if not out:
        raise ValueError("Faltan datos: aporta al menos dos macros (p. ej. K y Ca) en % de MS.")
    return FoliarResult(
        relaciones=out,
        nota=(
            "Bandas orientativas (varían por norma/laboratorio). Un desbalance de relaciones puede "
            "limitar la calidad aunque cada elemento esté 'en rango'; valida con tu agrónomo."
        ),
    )
