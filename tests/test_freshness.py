"""Guardarraíl de frescura regulatoria (P-5): un dato regulatorio fuera de SLA NO sale en verde."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from avorag.rag.freshness import (
    FeedName,
    FeedSnapshotView,
    FreshnessState,
    apply_freshness_gate,
    freshness_state,
    regulatory_feeds_for,
    verde_permitido,
)
from avorag.rag.schemas import Semaforo

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


def _snap(feed: FeedName, *, age_days: float, ttl_seconds: int | None = None) -> FeedSnapshotView:
    return FeedSnapshotView(
        feed_name=str(feed), as_of=NOW - timedelta(days=age_days), ttl_seconds=ttl_seconds
    )


# ── freshness_state ─────────────────────────────────────────────────────────────────────────────
def test_state_ok_dentro_de_sla():
    assert freshness_state(_snap(FeedName.ICA, age_days=3), now=NOW) is FreshnessState.OK


def test_state_stale_pasado_el_sla():
    # ICA SLA = 7 días; 8 días → stale.
    assert freshness_state(_snap(FeedName.ICA, age_days=8), now=NOW) is FreshnessState.STALE


def test_state_missing_sin_snapshot():
    assert freshness_state(None, now=NOW) is FreshnessState.MISSING
    assert freshness_state(FeedSnapshotView("ica_simplifica", None), now=NOW) is FreshnessState.MISSING


def test_state_borde_exacto_es_ok():
    # Exactamente en el límite del TTL → OK (<=).
    snap = FeedSnapshotView(str(FeedName.IDEAM), as_of=NOW - timedelta(hours=6), ttl_seconds=6 * 3600)
    assert freshness_state(snap, now=NOW) is FreshnessState.OK


def test_state_ttl_del_snapshot_prevalece():
    # TTL explícito de 1 día; dato de 2 días → stale aunque el default del feed fuera mayor.
    snap = FeedSnapshotView(str(FeedName.ICA), as_of=NOW - timedelta(days=2), ttl_seconds=24 * 3600)
    assert freshness_state(snap, now=NOW) is FreshnessState.STALE


def test_state_naive_datetime_se_trata_como_utc():
    snap = FeedSnapshotView(str(FeedName.ICA), as_of=datetime(2026, 6, 14, 12, 0))  # naive
    assert freshness_state(snap, now=NOW) is FreshnessState.OK


# ── regulatory_feeds_for ──────────────────────────────────────────────────────────────────────
def test_deps_pesticida_implica_ica():
    txt = "Aplica abamectina 2,5 cc/L para trips; respeta la carencia [1]."
    assert FeedName.ICA in regulatory_feeds_for(txt)


def test_deps_export_ue_agrega_lmr():
    txt = "Dosis de spinetoram según registro ICA."
    feeds = regulatory_feeds_for(txt, export_market="ue")
    assert FeedName.ICA in feeds and FeedName.LMR_UE in feeds


def test_deps_export_eeuu_agrega_tolerancia():
    feeds = regulatory_feeds_for("dosis y carencia del producto", export_market="eeuu")
    assert FeedName.TOL_EEUU in feeds


def test_deps_respuesta_no_fitosanitaria_no_depende():
    assert regulatory_feeds_for("El aguacate Hass florece en dicogamia protogínica.") == set()


# ── verde_permitido ───────────────────────────────────────────────────────────────────────────
def test_verde_prohibido_si_feed_regulatorio_stale():
    snaps = {str(FeedName.ICA): _snap(FeedName.ICA, age_days=30)}
    ok, avisos = verde_permitido(depends_on_feeds={FeedName.ICA}, snapshots=snaps, now=NOW)
    assert ok is False and avisos


def test_verde_prohibido_si_feed_regulatorio_missing():
    ok, avisos = verde_permitido(depends_on_feeds={FeedName.ICA}, snapshots={}, now=NOW)
    assert ok is False and avisos


def test_verde_permitido_si_feed_fresco():
    snaps = {str(FeedName.ICA): _snap(FeedName.ICA, age_days=1)}
    ok, avisos = verde_permitido(depends_on_feeds={FeedName.ICA}, snapshots=snaps, now=NOW)
    assert ok is True and avisos == []


def test_feed_no_regulatorio_no_bloquea_verde():
    # IDEAM (clima) stale NO debe prohibir verde de una recomendación fitosanitaria.
    snaps = {str(FeedName.IDEAM): _snap(FeedName.IDEAM, age_days=5)}
    ok, _ = verde_permitido(depends_on_feeds={FeedName.IDEAM}, snapshots=snaps, now=NOW)
    assert ok is True


# ── apply_freshness_gate (invariante de NO-escalado) ─────────────────────────────────────────────
def test_gate_degrada_verde_a_amarillo_si_no_fresco():
    sem, reason, av = apply_freshness_gate(
        Semaforo.VERDE, "ok", verde_ok=False, avisos=["dato viejo"]
    )
    assert sem is Semaforo.AMARILLO and "Frescura" in reason


def test_gate_no_toca_verde_si_fresco():
    sem, reason, _ = apply_freshness_gate(Semaforo.VERDE, "ok", verde_ok=True, avisos=[])
    assert sem is Semaforo.VERDE and reason == "ok"


def test_gate_nunca_escala_rojo():
    sem, _, _ = apply_freshness_gate(Semaforo.ROJO, "prohibido", verde_ok=False, avisos=["x"])
    assert sem is Semaforo.ROJO


def test_gate_nunca_sube_amarillo_a_verde():
    sem, _, _ = apply_freshness_gate(Semaforo.AMARILLO, "cautela", verde_ok=True, avisos=[])
    assert sem is Semaforo.AMARILLO
