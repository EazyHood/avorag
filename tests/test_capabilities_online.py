"""Capacidades del servidor online → mode_hint (1/2) según proveedores y frescura de feeds."""

from __future__ import annotations

from datetime import UTC, datetime

from avorag.online.capabilities import build_capabilities, current_capabilities
from avorag.rag.freshness import FeedName, FreshnessState

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


def _all_fresh():
    return dict.fromkeys(
        (FeedName.ICA, FeedName.IDEAM, FeedName.LMR_UE, FeedName.TOL_EEUU), (FreshnessState.OK, NOW)
    )


def _full(states):
    return build_capabilities(
        states, llm_up=True, judge_up=True, judge_independent=True, reranker_up=True
    )


def test_modo1_si_todo_verde():
    cap = _full(_all_fresh())
    assert cap["mode_hint"] == 1
    assert cap["subsystems"]["feed_ica"]["stale"] is False
    assert cap["subsystems"]["judge"]["up"] is True


def test_feed_regulatorio_stale_baja_a_modo2():
    states = _all_fresh()
    states[FeedName.ICA] = (FreshnessState.STALE, NOW)
    cap = _full(states)
    assert cap["mode_hint"] == 2 and cap["subsystems"]["feed_ica"]["stale"] is True


def test_feed_no_regulatorio_stale_no_baja_modo():
    # IDEAM (clima) stale NO gatea el modo (no es regulatorio).
    states = _all_fresh()
    states[FeedName.IDEAM] = (FreshnessState.STALE, NOW)
    cap = _full(states)
    assert cap["mode_hint"] == 1 and cap["subsystems"]["feed_ideam"]["stale"] is True


def test_juez_no_independiente_baja_a_modo2():
    cap = build_capabilities(
        _all_fresh(), llm_up=True, judge_up=True, judge_independent=False, reranker_up=True
    )
    assert cap["mode_hint"] == 2 and cap["subsystems"]["judge"]["up"] is False


def test_reranker_caido_baja_a_modo2():
    cap = build_capabilities(
        _all_fresh(), llm_up=True, judge_up=True, judge_independent=True, reranker_up=False
    )
    assert cap["mode_hint"] == 2


def test_current_capabilities_smoke_con_defaults():
    # Defaults del repo: juez autoeval (no independiente) + reranker 'none' ⇒ mode_hint 2.
    cap = current_capabilities(now=NOW)
    assert cap["mode_hint"] == 2
    assert "feed_ica" in cap["subsystems"]
    assert cap["subsystems"]["llm_fuerte"]["up"] is True  # llm_provider por defecto = 'ollama'
