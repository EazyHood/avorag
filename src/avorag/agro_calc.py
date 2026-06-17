"""Calculadoras agronómicas DETERMINISTAS para Hass de exportación.

Por qué existe: el RAG *cita*, no *calcula*. Decisiones cuantitativas clave —si el lote llegó al
corte de exportación por materia seca, cuánta cal echar por saturación de aluminio, cómo quedan las
relaciones y NIVELES foliares, cuánta agua regar, qué fracción de lavado ante agua salina— son
aritmética exacta que no debe pasar por un LLM (alucinaría cifras). Aquí se calculan con fórmulas
reconocidas, sin red ni modelo, y por eso sirven igual OFFLINE en el móvil.

Honestidad (la de siempre): los umbrales/bandas son ORIENTATIVOS (varían por mercado, norma y
laboratorio) y los supuestos de campo (densidad, profundidad, Kc, CEe…) se hacen explícitos. Es
apoyo de decisión citado, NO sustituye el criterio del agrónomo ni el análisis de tu laboratorio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ── 1) Materia seca (corte de exportación) ──────────────────────────────────────────────────────
# El Hass se corta por MATERIA SECA, no por color. Mínimo de madurez legal ~20,8% en varias normas
# (CODEX/California); el mercado de exportación suele exigir más (≈23% y a menudo 25%+). La parte que
# DE VERDAD falla es el MUESTREO: la MS varía 3-5 puntos entre fruto de sol y de sombra, así que el
# corte exige PROMEDIAR 10-20 frutos de varios árboles/estratos, no un solo fruto.
DRY_MATTER_LEGAL_MIN = 20.8
DRY_MATTER_EXPORT_DEFAULT = 23.0
DRY_MATTER_MIN_SAMPLE = 10  # frutos recomendados para un muestreo representativo


@dataclass
class DryMatterResult:
    materia_seca_pct: float  # media de la muestra
    umbral_pct: float
    veredicto: str  # "apto" | "limítrofe" | "por debajo"
    nota: str
    n_muestras: int = 1
    cv_pct: float | None = None  # coeficiente de variación de la muestra (heterogeneidad)
    minimo_muestra_pct: float | None = None  # MS del fruto más bajo de la muestra


def _dry_matter_verdict(media: float, umbral_pct: float, *, minimo: float | None, cv: float | None,
                        n: int) -> tuple[str, str]:
    """Veredicto sensible al muestreo: no basta con que la MEDIA supere el umbral si la muestra es
    pequeña o muy heterogénea (parte del lote puede estar por debajo)."""
    avisos: list[str] = []
    if n < DRY_MATTER_MIN_SAMPLE:
        avisos.append(
            f"Muestra de {n} fruto(s): insuficiente. Promedia ≥{DRY_MATTER_MIN_SAMPLE}-20 frutos de "
            "varios árboles y de sol y sombra (la MS varía 3-5 puntos dentro del mismo árbol)."
        )
    if cv is not None and cv > 8.0:
        avisos.append(f"Alta variabilidad (CV {cv:.0f}%): lote heterogéneo, parte puede estar por debajo del corte.")
    # Banda "limítrofe": justo por debajo del umbral, o la media lo supera pero el lote es
    # heterogéneo / hay frutos por debajo (parte del lote no llegaría al corte).
    bajo_riesgo = minimo is not None and minimo < umbral_pct <= media
    if media < umbral_pct - 1.0:
        veredicto = "por debajo"
        base = (
            f"Materia seca media {media}% < umbral {umbral_pct}%: aún no llega al corte; espera y "
            "vuelve a medir. Cosechar por debajo arriesga rechazo por madurez."
        )
    elif media < umbral_pct:
        veredicto = "limítrofe"
        base = f"Materia seca media {media}% justo por debajo del umbral {umbral_pct}%: amplía el muestreo y espera."
    elif bajo_riesgo or (cv is not None and cv > 8.0):
        veredicto = "limítrofe"
        base = (
            f"Materia seca media {media}% supera el umbral {umbral_pct}%"
            + (f", pero hay frutos en {minimo}%" if bajo_riesgo else " con muestra heterogénea")
            + ": amplía el muestreo antes de decidir cosecha."
        )
    else:
        veredicto = "apto"
        base = f"Materia seca media {media}% ≥ umbral {umbral_pct}%: el lote alcanza el corte indicado."
    if media < DRY_MATTER_LEGAL_MIN:
        base += f" (Además, por debajo del mínimo de madurez legal ~{DRY_MATTER_LEGAL_MIN}%.)"
    return veredicto, " ".join([base, *avisos])


def dry_matter_sample(
    materias_secas: list[float], *, umbral_pct: float = DRY_MATTER_EXPORT_DEFAULT
) -> DryMatterResult:
    """Materia seca a partir de una MUESTRA de %MS ya calculados (uno por fruto). Devuelve media, n,
    CV y el mínimo, y un veredicto sensible al muestreo (no basta la media si n es bajo o hay alta
    variabilidad)."""
    vals = [float(v) for v in materias_secas]
    if not vals:
        raise ValueError("Aporta al menos una medición de %MS.")
    if any(v <= 0 or v > 100 for v in vals):
        raise ValueError("Cada %MS debe estar entre 0 y 100.")
    n = len(vals)
    media = round(sum(vals) / n, 1)
    cv = None
    if n >= 2:
        sd = math.sqrt(sum((v - sum(vals) / n) ** 2 for v in vals) / (n - 1))
        cv = round(sd / (sum(vals) / n) * 100, 1) if media else None
    minimo = round(min(vals), 1)
    veredicto, nota = _dry_matter_verdict(media, umbral_pct, minimo=minimo, cv=cv, n=n)
    return DryMatterResult(
        materia_seca_pct=media, umbral_pct=umbral_pct, veredicto=veredicto, nota=nota,
        n_muestras=n, cv_pct=cv, minimo_muestra_pct=minimo,
    )


def dry_matter(
    peso_fresco_g: float, peso_seco_g: float, *, umbral_pct: float = DRY_MATTER_EXPORT_DEFAULT
) -> DryMatterResult:
    """Materia seca por gravimetría de UN fruto: %MS = peso_seco/peso_fresco×100. Devuelve el
    resultado pero AVISA de que un solo fruto no es muestreo válido (usa dry_matter_sample para el
    promedio de 10-20 frutos)."""
    if peso_fresco_g <= 0 or peso_seco_g <= 0:
        raise ValueError("Los pesos deben ser positivos.")
    if peso_seco_g > peso_fresco_g:
        raise ValueError("El peso seco no puede superar al peso fresco.")
    ms = round(peso_seco_g / peso_fresco_g * 100, 1)
    return dry_matter_sample([ms], umbral_pct=umbral_pct)


# ── 2) Encalado por saturación de aluminio ──────────────────────────────────────────────────────
# Fórmula de saturación objetivo (Cochrane et al.): requerimiento (cmol+/kg) = Al − (PSA_obj/100)·CICE.
# El aguacate es sensible al Al; PSA objetivo bajo (def. 15%). La conversión a t/ha depende de la
# densidad aparente y la profundidad; el default 1,5 t/ha por cmol+/kg ASUME densidad ~1,3 a 0-20 cm.
# OJO ANDISOLES: el Hass de altura crece en suelos de ceniza volcánica (densidad 0,6-0,9, altísimo
# poder tampón por alófana) donde esta fórmula NO es fiable: da una cota baja, no la dosis real.
AL_SAT_TARGET_DEFAULT = 15.0
LIME_FIELD_FACTOR_DEFAULT = 1.5  # t/ha de CaCO3 por cmol(+)/kg (≈ densidad 1,3 · 0-20 cm · tampón)


@dataclass
class LimingResult:
    cice_cmol_kg: float
    saturacion_al_pct: float
    requerimiento_cmol_kg: float
    cal_t_ha: float
    requiere_encalado: bool
    nota: str
    supuestos: str
    advertencia: str = ""  # andisol / suelo tampón: la fórmula no es fiable


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
    densidad_aparente: float | None = None,
    profundidad_cm: float = 20.0,
) -> LimingResult:
    """Requerimiento de cal por saturación de Al. Cationes en cmol(+)/kg (= meq/100 g) del análisis.

    Si pasas `densidad_aparente`, la t/ha se recalcula desde primeros principios
    (cal = req · 0,05 · profundidad_cm · densidad · 1,15_tampón / PRNT) en vez del factor 1,5 genérico;
    y si la densidad < 1,0 (andisol) se ADVIERTE que la fórmula de saturación no es fiable por el
    poder tampón (hace falta una curva de incubación/tampón)."""
    for nombre, v in (("Al", al), ("Ca", ca), ("Mg", mg), ("K", k), ("Na", na)):
        if v < 0:
            raise ValueError(f"{nombre} no puede ser negativo.")
    if prnt_pct <= 0:
        raise ValueError("El PRNT debe ser positivo.")
    if densidad_aparente is not None and densidad_aparente <= 0:
        raise ValueError("La densidad aparente debe ser positiva.")
    cice = al + ca + mg + k + na
    if cice <= 0:
        raise ValueError("La CICE (suma de cationes) debe ser positiva.")
    sat_al = round(al / cice * 100, 1)
    req = al - (psa_objetivo_pct / 100.0) * cice

    advertencia = ""
    if densidad_aparente is not None:
        factor = 0.05 * profundidad_cm * densidad_aparente * 1.15  # base CaCO3 + tampón ligero
        supuestos = (
            f"Densidad aparente {densidad_aparente} g/cm³, profundidad {profundidad_cm:g} cm, "
            f"PRNT {prnt_pct}% → factor {factor:.2f} t/ha por cmol(+)/kg."
        )
        if densidad_aparente < 1.0:
            advertencia = (
                "Densidad < 1,0: posible ANDISOL (ceniza volcánica). La fórmula de saturación de Al "
                "subestima por el altísimo poder tampón (alófana): toma esta cifra como cota inferior "
                "y define la dosis real con una CURVA DE INCUBACIÓN / tampón del laboratorio."
            )
    else:
        factor = factor_campo
        supuestos = (
            f"Factor de campo {factor_campo} t CaCO3/ha por cmol(+)/kg (asume densidad ~1,3 a 0-20 cm); "
            f"PRNT {prnt_pct}%. En ANDISOLES (densidad 0,6-0,9) pasa `densidad_aparente`: la fórmula no "
            "es fiable ahí por el poder tampón. PSA objetivo orientativo; ajústalo con tu agrónomo."
        )

    if req <= 0:
        return LimingResult(
            cice_cmol_kg=round(cice, 2), saturacion_al_pct=sat_al, requerimiento_cmol_kg=0.0,
            cal_t_ha=0.0, requiere_encalado=False,
            nota=(
                f"Saturación de Al {sat_al}% ya está en o por debajo del objetivo {psa_objetivo_pct}%: "
                "no se requiere encalado por aluminio."
            ),
            supuestos="—", advertencia=advertencia,
        )
    cal = round(req * factor / (prnt_pct / 100.0), 2)
    return LimingResult(
        cice_cmol_kg=round(cice, 2), saturacion_al_pct=sat_al, requerimiento_cmol_kg=round(req, 2),
        cal_t_ha=cal, requiere_encalado=True,
        nota=(
            f"Saturación de Al {sat_al}% > objetivo {psa_objetivo_pct}%. Estimación: ~{cal} t/ha de "
            "cal. Aplica, incorpora y reanaliza antes de la próxima fertilización."
        ),
        supuestos=supuestos, advertencia=advertencia,
    )


# ── 3) Diagnóstico foliar: relaciones + NIVELES absolutos + estrés salino ───────────────────────
# Calcula lo que el RAG no calcula. Dos defectos de la versión anterior, corregidos:
#  (a) ignoraba BORO y ZINC, los micronutrientes que más deciden floración/cuajado y calibre del Hass;
#  (b) era ciega al NIVEL ABSOLUTO (un árbol famélico con buena proporción salía "óptimo"). Ahora
#      evalúa cada elemento contra su rango de suficiencia y marca deficiencias aunque el cociente
#      esté "bien". Añade Cl/Na (estrés salino) y las relaciones K/Cl, K/Na. Bandas ORIENTATIVAS.
_FOLIAR_RATIOS: dict[str, tuple[str, str, float, float]] = {
    "K/Ca": ("k", "ca", 0.5, 1.5),
    "Ca/Mg": ("ca", "mg", 2.0, 5.0),
    "Mg/K": ("mg", "k", 0.3, 1.0),
    "N/K": ("n", "k", 1.2, 2.5),
    "K/Mg": ("k", "mg", 1.0, 3.0),
}
# Rangos de suficiencia foliar orientativos para Hass (hoja madura). Macros en % de MS; micros en ppm.
_FOLIAR_SUFFICIENCY: dict[str, tuple[float, float, str]] = {
    "n": (1.6, 2.4, "%"), "p": (0.08, 0.25, "%"), "k": (0.75, 2.0, "%"),
    "ca": (1.0, 3.0, "%"), "mg": (0.25, 0.8, "%"), "s": (0.2, 0.6, "%"),
    "b": (40, 100, "ppm"), "zn": (30, 150, "ppm"), "fe": (50, 200, "ppm"),
    "mn": (30, 500, "ppm"), "cu": (5, 25, "ppm"),
}
# Umbrales de estrés salino foliar (excesos): por encima → riesgo de quemado marginal.
_SALT_THRESHOLDS: dict[str, float] = {"cl": 0.5, "na": 0.25}  # % de MS


@dataclass
class RatioResult:
    valor: float
    banda_ref: str
    estado: str  # "bajo" | "óptimo" | "alto"


@dataclass
class LevelResult:
    valor: float
    rango_ref: str
    estado: str  # "deficiente" | "suficiente" | "alto/exceso"


@dataclass
class FoliarResult:
    relaciones: dict[str, RatioResult] = field(default_factory=dict)
    niveles: dict[str, LevelResult] = field(default_factory=dict)
    alertas: list[str] = field(default_factory=list)
    nota: str = ""


def foliar_ratios(
    *,
    n: float | None = None, p: float | None = None, k: float | None = None,
    ca: float | None = None, mg: float | None = None, s: float | None = None,
    b: float | None = None, zn: float | None = None, fe: float | None = None,
    mn: float | None = None, cu: float | None = None,
    cl: float | None = None, na: float | None = None,
) -> FoliarResult:
    """Diagnóstico foliar: relaciones (K/Ca, Ca/Mg, Mg/K, N/K, K/Mg) + NIVELES absolutos de cada
    elemento dado (incluye B y Zn) + alertas de deficiencia y de estrés salino (Cl/Na). Macros en %
    de MS, micros en ppm. Bandas/rangos ORIENTATIVOS (varían por norma y laboratorio)."""
    vals = {"n": n, "p": p, "k": k, "ca": ca, "mg": mg, "s": s, "b": b, "zn": zn,
            "fe": fe, "mn": mn, "cu": cu, "cl": cl, "na": na}
    for nombre, v in vals.items():
        if v is not None and v < 0:
            raise ValueError(f"{nombre.upper()} no puede ser negativo.")
    if all(v is None for v in vals.values()):
        raise ValueError("Aporta al menos un elemento foliar.")

    # Relaciones (las que se puedan formar con los datos dados).
    relaciones: dict[str, RatioResult] = {}
    for nombre, (num, den, lo, hi) in _FOLIAR_RATIOS.items():
        a, bb = vals[num], vals[den]
        if a is None or bb is None or bb == 0:
            continue
        r = round(a / bb, 2)
        estado = "bajo" if r < lo else ("alto" if r > hi else "óptimo")
        relaciones[nombre] = RatioResult(valor=r, banda_ref=f"{lo}–{hi}", estado=estado)
    # Relaciones de salinidad (si hay Cl/Na): se busca K alto frente a Cl/Na (≥1 deseable).
    for nombre, (num, den) in {"K/Cl": ("k", "cl"), "K/Na": ("k", "na")}.items():
        a, bb = vals[num], vals[den]
        if a is None or bb is None or bb == 0:
            continue
        r = round(a / bb, 2)
        relaciones[nombre] = RatioResult(valor=r, banda_ref="≥1", estado=("bajo" if r < 1.0 else "óptimo"))

    # Niveles absolutos (cada elemento dado vs su rango de suficiencia).
    niveles: dict[str, LevelResult] = {}
    alertas: list[str] = []
    for el, (lo, hi, unit) in _FOLIAR_SUFFICIENCY.items():
        v = vals[el]
        if v is None:
            continue
        if v < lo:
            estado = "deficiente"
            alertas.append(f"{el.upper()} {v}{unit} por DEBAJO de suficiencia ({lo}-{hi}{unit}).")
        elif v > hi:
            estado = "alto/exceso"
        else:
            estado = "suficiente"
        niveles[el] = LevelResult(valor=v, rango_ref=f"{lo}-{hi} {unit}", estado=estado)
    # Estrés salino (Cl/Na altos).
    for el, lim in _SALT_THRESHOLDS.items():
        v = vals[el]
        if v is not None and v > lim:
            alertas.append(
                f"{el.upper()} foliar {v}% supera ~{lim}%: riesgo de quemado marginal por sal "
                f"({'cloruro' if el == 'cl' else 'sodio'}); considera fuentes sin cloruro (p. ej. K2SO4)."
            )
            niveles[el] = LevelResult(valor=v, rango_ref=f"≤{lim} %", estado="alto/exceso")
    if (b is not None and b < _FOLIAR_SUFFICIENCY["b"][0]) or (zn is not None and zn < _FOLIAR_SUFFICIENCY["zn"][0]):
        alertas.append(
            "Boro y/o Zinc bajos: limitan cuajado (B: viabilidad del polen) y calibre/brotación (Zn) "
            "aunque las relaciones de macros estén 'óptimas'."
        )
    if not relaciones and not niveles:
        raise ValueError("Faltan datos utilizables (aporta valores foliares válidos).")
    return FoliarResult(
        relaciones=relaciones, niveles=niveles, alertas=alertas,
        nota=(
            "Bandas/rangos orientativos (varían por norma/laboratorio). Un nivel ABSOLUTO bajo limita "
            "la cosecha aunque la proporción esté 'óptima'; valida con tu agrónomo y el análisis completo."
        ),
    )


# ── 4) Riego: requerimiento por ETc = ETo · Kc ──────────────────────────────────────────────────
@dataclass
class IrrigationResult:
    etc_mm_dia: float
    lamina_neta_mm_dia: float
    lamina_bruta_mm_dia: float
    volumen_m3_ha_dia: float | None
    nota: str


def irrigation_requirement(
    *, eto_mm_dia: float, kc: float, precip_efectiva_mm_dia: float = 0.0,
    eficiencia: float = 0.9, area_ha: float | None = None,
) -> IrrigationResult:
    """Requerimiento de riego: ETc = ETo·Kc; lámina neta = ETc − precipitación efectiva; lámina bruta
    = neta / eficiencia. Si das `area_ha`, devuelve el volumen (1 mm/ha = 10 m³). Kc varía por etapa
    fenológica y la ETo viene del clima local — son tus datos, aquí va la aritmética."""
    if eto_mm_dia < 0 or kc <= 0 or precip_efectiva_mm_dia < 0:
        raise ValueError("ETo y precipitación ≥ 0 y Kc > 0.")
    if not (0 < eficiencia <= 1):
        raise ValueError("La eficiencia debe estar entre 0 y 1.")
    etc = round(eto_mm_dia * kc, 2)
    neta = round(max(0.0, etc - precip_efectiva_mm_dia), 2)
    bruta = round(neta / eficiencia, 2)
    vol = round(bruta * 10 * area_ha, 1) if area_ha and area_ha > 0 else None
    return IrrigationResult(
        etc_mm_dia=etc, lamina_neta_mm_dia=neta, lamina_bruta_mm_dia=bruta, volumen_m3_ha_dia=vol,
        nota=(
            "Kc depende de la etapa (cuaje/llenado mayor que reposo) y la ETo del clima local del día. "
            "El Hass es muy sensible al exceso de agua: evita encharcar (asfixia radical/Phytophthora)."
        ),
    )


# ── 5) Salinidad: fracción de lavado + RAS/SAR ──────────────────────────────────────────────────
# El Hass es de los frutales MÁS sensibles a la salinidad y al cloruro/sodio. CEe umbral ~1,3 dS/m.
HASS_CE_THRESHOLD_DSM = 1.3


@dataclass
class SalinityResult:
    fraccion_lavado: float | None
    sar: float | None
    ce_agua_dsm: float
    nota: str
    alertas: list[str] = field(default_factory=list)


def salinity_assessment(
    *, ce_agua_dsm: float, ce_umbral_suelo_dsm: float = HASS_CE_THRESHOLD_DSM,
    na_meq_l: float | None = None, ca_meq_l: float | None = None, mg_meq_l: float | None = None,
) -> SalinityResult:
    """Riesgo salino del agua de riego: fracción de lavado (Rhoades: LF = CEw / (5·CEe − CEw)) y SAR
    = Na / raíz((Ca+Mg)/2) (iones en meq/L). Umbral CEe del Hass ~1,3 dS/m (cultivo sensible)."""
    if ce_agua_dsm < 0 or ce_umbral_suelo_dsm <= 0:
        raise ValueError("CE del agua ≥ 0 y CEe umbral > 0.")
    alertas: list[str] = []
    denom = 5 * ce_umbral_suelo_dsm - ce_agua_dsm
    lf = round(ce_agua_dsm / denom, 3) if denom > 0 else None
    if lf is None:
        alertas.append(
            f"CE del agua ({ce_agua_dsm} dS/m) demasiado alta frente al umbral del Hass "
            f"({ce_umbral_suelo_dsm} dS/m): el lavado no es viable; considera otra fuente de agua."
        )
    elif lf > 0.3:
        alertas.append(f"Fracción de lavado alta ({lf}): agua salina; exige drenaje y lámina extra de lavado.")
    sar = None
    if na_meq_l is not None and ca_meq_l is not None and mg_meq_l is not None:
        if na_meq_l < 0 or ca_meq_l < 0 or mg_meq_l < 0:
            raise ValueError("Los iones (meq/L) no pueden ser negativos.")
        base = (ca_meq_l + mg_meq_l) / 2
        sar = round(na_meq_l / math.sqrt(base), 2) if base > 0 else None
        if sar is not None and sar > 6:
            alertas.append(f"SAR {sar} elevado: riesgo de sodicidad y de toxicidad por sodio (Hass sensible).")
    if ce_agua_dsm > ce_umbral_suelo_dsm:
        alertas.append(
            f"CE del agua {ce_agua_dsm} dS/m supera el umbral del Hass {ce_umbral_suelo_dsm} dS/m: "
            "habrá pérdida de rendimiento si no se maneja drenaje + lavado."
        )
    return SalinityResult(
        fraccion_lavado=lf, sar=sar, ce_agua_dsm=ce_agua_dsm, alertas=alertas,
        nota=(
            "El Hass es muy sensible a Cl⁻/Na⁺: el daño aparece a CE bajas. Verifica CEe del suelo y "
            "el Cl⁻ foliar; prefiere fuentes de K sin cloruro. Umbrales orientativos."
        ),
    )
