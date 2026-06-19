"""Capacidades del servidor online → el cliente decide a qué MODO (1–4) degradar.

Lógica PURA (testeable): dado el estado de cada subsistema, arma la respuesta de `GET /api/capabilities`.
El `mode_hint` es la sugerencia del SERVIDOR (1 = online-pleno, 2 = online-degradado). Los modos 3
(caché) y 4 (fallback-offline) los decide el CLIENTE según su propia red — el servidor no los conoce.
"""

from __future__ import annotations

from datetime import datetime

from avorag.config import get_settings
from avorag.logging import get_logger
from avorag.rag.freshness import REGULATORY_FEEDS, FeedName, FreshnessState, freshness_state


def _cap(up: bool, *, as_of: datetime | None = None, stale: bool = False) -> dict:
    return {"up": up, "as_of": as_of.isoformat() if as_of else None, "stale": stale}


def build_capabilities(
    feed_states: dict[FeedName, tuple[FreshnessState, datetime | None]],
    *,
    llm_up: bool,
    judge_up: bool,
    judge_independent: bool,
    reranker_up: bool,
) -> dict:
    """Arma la respuesta de capacidades + el `mode_hint`.

    `feed_states`: por feed, (estado_de_frescura, as_of). mode_hint=1 SOLO si el modelo fuerte, el
    juez INDEPENDIENTE y el reranker están arriba Y todos los feeds REGULATORIOS están frescos (OK);
    cualquier degradación ⇒ 2 (online-degradado).
    """
    subsystems: dict[str, dict] = {
        "llm_fuerte": _cap(llm_up),
        "judge": _cap(judge_up and judge_independent),
        "reranker": _cap(reranker_up),
    }
    regulatorios_ok = True
    for feed in (FeedName.ICA, FeedName.IDEAM, FeedName.LMR_UE, FeedName.TOL_EEUU):
        estado, as_of = feed_states.get(feed, (FreshnessState.MISSING, None))
        stale = estado is not FreshnessState.OK
        subsystems[f"feed_{_short(feed)}"] = _cap(
            estado is not FreshnessState.MISSING, as_of=as_of, stale=stale
        )
        if feed in REGULATORY_FEEDS and stale:
            regulatorios_ok = False

    pleno = llm_up and judge_up and judge_independent and reranker_up and regulatorios_ok
    return {"mode_hint": 1 if pleno else 2, "subsystems": subsystems}


def current_capabilities(*, now: datetime | None = None) -> dict:
    """Reúne el estado REAL (config de proveedores + frescura de feeds en BD) y arma las capacidades.

    Robusto: si los feeds no están disponibles (tabla ausente, BD caída) se reportan como MISSING y
    el `mode_hint` cae a 2 (degradado). El juez cuenta como apto solo si es INDEPENDIENTE del generador.
    """
    s = get_settings()
    llm_up = bool(s.llm_provider)
    reranker_up = s.rerank_provider.lower() != "none"
    judge_independent = bool(
        s.judge_llm_provider
        and (
            s.judge_llm_provider != s.llm_provider
            or (s.judge_llm_model and s.judge_llm_model != s.llm_model)
        )
    )
    feed_states: dict[FeedName, tuple[FreshnessState, datetime | None]] = {}
    try:
        from avorag.db import get_session
        from avorag.online import feeds

        with get_session(system=True) as session:
            for feed in (FeedName.ICA, FeedName.IDEAM, FeedName.LMR_UE, FeedName.TOL_EEUU):
                view = feeds.latest_view(session, feed)
                feed_states[feed] = (
                    freshness_state(view, now=now),
                    view.as_of if view else None,
                )
    except Exception as exc:  # noqa: BLE001 — feeds no disponibles ⇒ MISSING, no rompe el endpoint
        get_logger(__name__).warning("capabilities_feed_read_failed", error=str(exc))
    return build_capabilities(
        feed_states,
        llm_up=llm_up,
        judge_up=True,
        judge_independent=judge_independent,
        reranker_up=reranker_up,
    )


def _short(feed: FeedName) -> str:
    return {
        FeedName.ICA: "ica",
        FeedName.IDEAM: "ideam",
        FeedName.LMR_UE: "lmr_ue",
        FeedName.TOL_EEUU: "eeuu",
    }[feed]
