"""Cruce REGULATORIO EN VIVO (modo online) — convierte los feeds en bloqueos del semáforo.

Es el capstone del superpoder online: no basta con saber si el dato está fresco (eso lo hace
`freshness`); aquí se CRUZA el contenido de la respuesta contra el dato vivo y se emiten hallazgos
que el semáforo aplica:

- Registro ICA **cancelado** (vivo) para un i.a. recomendado            → ROJO.
- Activo **no aprobado en el destino UE** (LMR)                          → ROJO.
- Activo **sin tolerancia para AGUACATE en EE.UU.** (40 CFR 180)         → ROJO (residuo violatorio).
- Dato regulatorio necesario **no verificable en vivo** (stale/missing)  → AMARILLO (verificar).

Lógica PURA salvo el acceso a snapshots (recibe una `Session`). Importa `agro_terms` SOLO DE LECTURA
(detección de i.a. y marcas comerciales): NO edita el núcleo. Archivo NUEVO bajo `online/`.

Integración (núcleo, requiere aviso): el pipeline llama a `live_regulatory_findings(...)` y compone
`apply_regulatory_findings(...)` con el semáforo, ANTES o junto al guardarraíl de prohibidos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from avorag.agro_terms import active_ingredients_in, commercial_actives_in
from avorag.markets import normalize_market
from avorag.online import feeds
from avorag.rag.freshness import (
    FeedName,
    FreshnessState,
    freshness_state,
    mentions_pesticide_context,
    strip_accents,
)
from avorag.rag.schemas import Semaforo

# Estados de registro que NO son vigencia (cancelado/suspendido/revocado/…): cualquier estado cuyo
# texto (sin acentos) contenga uno de estos tokens se trata como NO vigente → ROJO. Evita que
# 'Cancelado', 'cancelado parcialmente', 'cancelación', 'suspendido' o 'revocado' se escapen por una
# igualdad estricta con la cadena 'cancelado'.
_NO_VIGENTE_TOKENS = (
    "cancel",
    "suspend",
    "revoc",
    "anulad",
    "negad",
    "retir",
    "prohib",
    "vencid",
    "no vigente",
    "no aprob",
)


@dataclass(frozen=True)
class RegulatoryFinding:
    severity: Semaforo  # ROJO o AMARILLO
    feed: str
    ingrediente_activo: str
    message: str


def _actives_in(answer_text: str) -> set[str]:
    """i.a. presentes en la respuesta, por nombre técnico Y por marca comercial (lectura de agro_terms)."""
    return active_ingredients_in(answer_text) | commercial_actives_in(answer_text)


def _is_no_vigente(estado: str) -> bool:
    """True si el estado de un registro ICA NO es una vigencia (cancelado/suspendido/revocado/…)."""
    e = strip_accents((estado or "").strip())
    return any(tok in e for tok in _NO_VIGENTE_TOKENS)


def _mentioned(answer_norm: str, name: str) -> bool:
    """True si `name` (i.a.) aparece como palabra completa en el texto ya normalizado sin acentos."""
    n = strip_accents(str(name).strip())
    return bool(n) and re.search(rf"\b{re.escape(n)}\b", answer_norm) is not None


def _feed_flagged_actives(ica, lmr, tol, answer_norm: str) -> set[str]:
    """i.a. que el PROPIO FEED marca peligrosos (ICA no-vigente / UE no aprobado / EE.UU. sin tolerancia)
    Y que aparecen en la respuesta — aunque agro_terms NO los conozca. Cierra el falso negativo
    existencial: el feed sabe que están cancelados/sin-tolerancia pero el diccionario no los nombraba.
    """
    flagged: set[str] = set()
    if ica is not None:
        for r in ica.payload.get("registros", []):
            if _is_no_vigente(str(r.get("estado", ""))) and _mentioned(
                answer_norm, r.get("ingrediente_activo", "")
            ):
                flagged.add(strip_accents(str(r.get("ingrediente_activo", "")).strip()))
    if lmr is not None:
        for ia in lmr.payload.get("no_aprobados", []):
            if _mentioned(answer_norm, ia):
                flagged.add(strip_accents(str(ia).strip()))
    if tol is not None:
        for ia in tol.payload.get("sin_tolerancia", []):
            if _mentioned(answer_norm, ia):
                flagged.add(strip_accents(str(ia).strip()))
    return flagged


def live_regulatory_findings(
    session: Session,
    answer_text: str,
    *,
    export_market: str | None = None,
    now: datetime | None = None,
) -> list[RegulatoryFinding]:
    """Cruza los i.a. de la respuesta contra los feeds vivos y devuelve hallazgos (ROJO/AMARILLO).

    Candidatos = UNIÓN de (a) i.a. detectados por el diccionario agro_terms y (b) i.a. que el PROPIO
    FEED marca peligrosos y aparecen en la respuesta. (b) cierra el falso negativo existencial: un
    activo cancelado/sin-tolerancia que el diccionario no conoce igual dispara ROJO con el dato vivo.
    """
    answer_norm = strip_accents(answer_text or "")
    market = normalize_market(export_market)

    ica = feeds.latest_snapshot(session, FeedName.ICA)
    ica_view = feeds.latest_view(session, FeedName.ICA)
    lmr = feeds.latest_snapshot(session, FeedName.LMR_UE) if market == "ue" else None
    lmr_view = feeds.latest_view(session, FeedName.LMR_UE) if market == "ue" else None
    en_eeuu = market == "eeuu"
    tol = feeds.latest_snapshot(session, FeedName.TOL_EEUU) if en_eeuu else None
    tol_view = feeds.latest_view(session, FeedName.TOL_EEUU) if en_eeuu else None

    candidates = {strip_accents(a) for a in _actives_in(answer_text)}
    candidates |= _feed_flagged_actives(ica, lmr, tol, answer_norm)
    candidates = {c for c in candidates if c}

    findings: list[RegulatoryFinding] = []

    # Contexto fitosanitario con dosis pero SIN i.a. identificable: no se puede verificar en vivo.
    if not candidates:
        if mentions_pesticide_context(answer_text):
            findings.append(
                RegulatoryFinding(
                    Semaforo.AMARILLO,
                    FeedName.ICA.value,
                    "*",
                    "Recomendación fitosanitaria sin ingrediente activo identificable: no verificable "
                    "en vivo. Confirma el registro ICA y la admisibilidad en destino.",
                )
            )
        return findings

    # Frescura de los feeds (propiedad del FEED, no del i.a.): UN aviso por feed, no uno por i.a.
    if freshness_state(ica_view, now=now) is not FreshnessState.OK:
        findings.append(
            RegulatoryFinding(
                Semaforo.AMARILLO,
                FeedName.ICA.value,
                "*",
                "Vigencia ICA NO verificada en vivo (dato ausente o vencido). Verifica en SimplifICA.",
            )
        )
    if lmr is not None and freshness_state(lmr_view, now=now) is not FreshnessState.OK:
        findings.append(
            RegulatoryFinding(
                Semaforo.AMARILLO,
                FeedName.LMR_UE.value,
                "*",
                "Admisibilidad UE (LMR) NO verificada en vivo (dato ausente o vencido). "
                "Verifica en EU Pesticides Database.",
            )
        )
    if tol is not None and freshness_state(tol_view, now=now) is not FreshnessState.OK:
        findings.append(
            RegulatoryFinding(
                Semaforo.AMARILLO,
                FeedName.TOL_EEUU.value,
                "*",
                "Admisibilidad EE.UU. (40 CFR 180) NO verificada en vivo (dato ausente o vencido). "
                "Verifica las tolerancias.",
            )
        )

    for ia in sorted(candidates):
        # 1) Vigencia ICA (país de producción) — cualquier estado no-vigente, no solo 'cancelado'.
        if ica is not None and _is_no_vigente(feeds.ica_status(ica.payload, ia)):
            findings.append(
                RegulatoryFinding(
                    Semaforo.ROJO,
                    FeedName.ICA.value,
                    ia,
                    f"«{ia}»: registro ICA CANCELADO/no vigente según el dato en vivo. No recomendar.",
                )
            )
        # 2) Admisibilidad en el DESTINO.
        if lmr is not None:
            estado, _val = feeds.ue_lmr(lmr.payload, ia)
            if estado == "no_aprobado":
                findings.append(
                    RegulatoryFinding(
                        Semaforo.ROJO,
                        FeedName.LMR_UE.value,
                        ia,
                        f"«{ia}»: NO aprobado en la UE (dato en vivo). Residuo no admisible en destino.",
                    )
                )
            elif estado == "desconocido":
                findings.append(
                    RegulatoryFinding(
                        Semaforo.AMARILLO,
                        FeedName.LMR_UE.value,
                        ia,
                        f"«{ia}»: sin LMR UE conocido en el feed. Verifica en EU Pesticides Database.",
                    )
                )
        if tol is not None:
            has_tol, _ppm = feeds.eeuu_tolerance(tol.payload, ia)
            if not has_tol:
                findings.append(
                    RegulatoryFinding(
                        Semaforo.ROJO,
                        FeedName.TOL_EEUU.value,
                        ia,
                        f"«{ia}»: SIN tolerancia para aguacate en 40 CFR 180 (EE.UU.). Residuo violatorio.",
                    )
                )
    return findings


def apply_regulatory_findings(
    semaforo: Semaforo,
    reason: str,
    findings: list[RegulatoryFinding],
) -> tuple[Semaforo, str, list[str]]:
    """Compone los hallazgos con el semáforo, respetando la invariante de NO-escalado:
    - cualquier hallazgo ROJO ⇒ ROJO (a menos que ya lo sea);
    - si no hay ROJO pero sí AMARILLO y el semáforo es VERDE ⇒ AMARILLO;
    - NUNCA degrada un ROJO ni sube un AMARILLO a VERDE.
    Devuelve (semaforo, reason, avisos).
    """
    avisos = [f.message for f in findings]
    rojos = [f for f in findings if f.severity is Semaforo.ROJO]
    if rojos and semaforo is not Semaforo.ROJO:
        return Semaforo.ROJO, f"Bloqueo regulatorio en vivo: {rojos[0].message}", avisos
    if not rojos and findings and semaforo is Semaforo.VERDE:
        return Semaforo.AMARILLO, f"Regulatorio en vivo a verificar: {findings[0].message}", avisos
    return semaforo, reason, avisos
