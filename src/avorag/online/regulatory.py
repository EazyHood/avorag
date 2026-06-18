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

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from avorag.agro_terms import active_ingredients_in, commercial_actives_in
from avorag.online import feeds
from avorag.rag.freshness import FeedName, FreshnessState, freshness_state
from avorag.rag.schemas import Semaforo


@dataclass(frozen=True)
class RegulatoryFinding:
    severity: Semaforo  # ROJO o AMARILLO
    feed: str
    ingrediente_activo: str
    message: str


def _actives_in(answer_text: str) -> set[str]:
    """i.a. presentes en la respuesta, por nombre técnico Y por marca comercial (lectura de agro_terms)."""
    return active_ingredients_in(answer_text) | commercial_actives_in(answer_text)


def live_regulatory_findings(
    session: Session,
    answer_text: str,
    *,
    export_market: str | None = None,
    now: datetime | None = None,
) -> list[RegulatoryFinding]:
    """Cruza los i.a. de la respuesta contra los feeds vivos y devuelve hallazgos (ROJO/AMARILLO)."""
    actives = _actives_in(answer_text)
    if not actives:
        return []
    findings: list[RegulatoryFinding] = []

    ica = feeds.latest_snapshot(session, FeedName.ICA)
    ica_view = feeds.latest_view(session, FeedName.ICA)
    market = (export_market or "").strip().lower()
    lmr = feeds.latest_snapshot(session, FeedName.LMR_UE) if market == "ue" else None
    tol = (
        feeds.latest_snapshot(session, FeedName.TOL_EEUU)
        if market in ("eeuu", "us", "usa")
        else None
    )

    for ia in sorted(actives):
        # 1) Vigencia ICA (país de producción).
        if ica is not None:
            estado = feeds.ica_status(ica.payload, ia)
            if estado == "cancelado":
                findings.append(
                    RegulatoryFinding(
                        Semaforo.ROJO,
                        FeedName.ICA.value,
                        ia,
                        f"«{ia}»: registro ICA CANCELADO según el dato en vivo. No recomendar.",
                    )
                )
        # Frescura del feed ICA: si no se puede verificar, degradar (no afirmar vigencia).
        if freshness_state(ica_view, now=now) is not FreshnessState.OK:
            findings.append(
                RegulatoryFinding(
                    Semaforo.AMARILLO,
                    FeedName.ICA.value,
                    ia,
                    f"«{ia}»: vigencia ICA NO verificada en vivo (dato ausente o vencido). Verifica en SimplifICA.",
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
