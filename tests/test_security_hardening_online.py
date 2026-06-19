"""Regresiones de la auditoría adversarial de la ruta de seguridad ONLINE (contrato "0 errores").

Cada test ancla un agujero confirmado por la auditoría (causa raíz dominante: el cruce solo miraba i.a.
del diccionario; fail-safe fail-open; 0 ppm tratado como autorizado; tildes/estados; frescura de
destino; mercados sin feed; esquema drifteado). Todo es lógica PURA (con stubs de Session): sin BD/LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from avorag.online import feeds, integration, regulatory
from avorag.online.feeds import FeedSnapshot
from avorag.rag.freshness import FeedName, FeedSnapshotView, FreshnessState, freshness_state
from avorag.rag.schemas import Answer, Semaforo

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
_ICA_MAP = feeds.DEFAULT_CSV_MAPPING[FeedName.ICA]
_LMR_MAP = feeds.DEFAULT_CSV_MAPPING[FeedName.LMR_UE]
_EEUU_MAP = feeds.DEFAULT_CSV_MAPPING[FeedName.TOL_EEUU]


def _answer(text: str, sem: Semaforo = Semaforo.VERDE) -> Answer:
    return Answer(question="q", text=text, semaforo=sem, warnings=[])


def _install_feeds(monkeypatch, mapping: dict) -> None:
    """mapping: {FeedName: (payload, as_of, status)}. Parchea latest_snapshot/latest_view de `feeds`."""
    snaps = {
        feed.value: FeedSnapshot(
            feed_name=feed.value,
            as_of=as_of,
            ttl_seconds=7 * 24 * 3600,
            sha256="0" * 64,
            payload=payload,
            status=status,
        )
        for feed, (payload, as_of, status) in mapping.items()
    }

    def latest_snapshot(_s, feed):
        return snaps.get(str(getattr(feed, "value", feed)))

    def latest_view(_s, feed):
        snap = snaps.get(str(getattr(feed, "value", feed)))
        if snap is None or (snap.status and snap.status != "ok"):
            return None
        return FeedSnapshotView(snap.feed_name, snap.as_of, snap.ttl_seconds)

    monkeypatch.setattr(feeds, "latest_snapshot", latest_snapshot)
    monkeypatch.setattr(feeds, "latest_view", latest_view)


# ── #1 (CRÍTICO): el cruce ya NO depende solo del diccionario ───────────────────────────────────
def test_feed_flagged_active_outside_dictionary_blocks(monkeypatch):
    # 'profenofos' marcado CANCELADO por el feed ICA y mencionado en la respuesta: ROJO aunque
    # agro_terms no lo conozca (cierra el falso negativo existencial, causa raíz de la auditoría).
    payload = {"registros": [{"ingrediente_activo": "profenofos", "estado": "cancelado"}]}
    _install_feeds(monkeypatch, {FeedName.ICA: (payload, NOW, "ok")})
    findings = regulatory.live_regulatory_findings(
        object(), "Para el barrenador aplica profenofos 1 L/ha.", now=NOW
    )
    assert any(
        f.severity is Semaforo.ROJO and "profenofos" in f.ingrediente_activo for f in findings
    )


def test_feed_flagged_eeuu_sin_tolerancia_blocks(monkeypatch):
    payload = {"avocado_tolerances_ppm": {}, "sin_tolerancia": ["fenamidona"]}
    _install_feeds(
        monkeypatch,
        {FeedName.TOL_EEUU: (payload, NOW, "ok"), FeedName.ICA: ({"registros": []}, NOW, "ok")},
    )
    findings = regulatory.live_regulatory_findings(
        object(), "Aplica fenamidona 1 L/ha.", export_market="eeuu", now=NOW
    )
    assert any(f.severity is Semaforo.ROJO and f.feed == FeedName.TOL_EEUU.value for f in findings)


def test_dosis_sin_ia_identificable_es_amarillo(monkeypatch):
    _install_feeds(monkeypatch, {FeedName.ICA: ({"registros": []}, NOW, "ok")})
    # Contexto fitosanitario con dosis pero sin i.a. reconocible ni en feed ni en diccionario.
    findings = regulatory.live_regulatory_findings(
        object(), "Aplica el producto a 2 cc/L cada 15 días.", now=NOW
    )
    assert findings and all(f.severity is Semaforo.AMARILLO for f in findings)


# ── #4 (CRÍTICO): tolerancia EE.UU. de 0 ppm NO autoriza ────────────────────────────────────────
def test_eeuu_tolerance_zero_ppm_no_autoriza():
    assert feeds.eeuu_tolerance({"avocado_tolerances_ppm": {"x": 0.0}}, "x") == (False, None)
    assert feeds.eeuu_tolerance({"avocado_tolerances_ppm": {"x": 1.0}}, "x") == (True, 1.0)


def test_norm_eeuu_zero_ppm_va_a_sin_tolerancia():
    rows = [
        {"ingrediente_activo": "azoxistrobina", "tolerancia_ppm": "0", "tiene_tolerancia": "si"}
    ]
    out = feeds._norm_eeuu(rows, _EEUU_MAP)
    assert "azoxistrobina" in out["sin_tolerancia"]
    assert "azoxistrobina" not in out["avocado_tolerances_ppm"]


# ── #5: tildes feed↔lookup + estados no-vigentes (no solo 'cancelado' exacto) ───────────────────
def test_ica_status_ignora_acentos():
    payload = {"registros": [{"ingrediente_activo": "clorpirifós", "estado": "Cancelado"}]}
    assert feeds.ica_status(payload, "clorpirifos") == "cancelado"


@pytest.mark.parametrize(
    "estado",
    [
        "cancelado",
        "Cancelado",
        "cancelado parcialmente",
        "cancelación",
        "suspendido",
        "revocado",
        "anulado",
        "no vigente",
    ],
)
def test_is_no_vigente_detecta_variantes(estado):
    assert regulatory._is_no_vigente(estado) is True


@pytest.mark.parametrize("estado", ["vigente", "desconocido", ""])
def test_is_no_vigente_respeta_vigentes(estado):
    assert regulatory._is_no_vigente(estado) is False


# ── #6 / #12: LMR UE — no afirmativo ⇒ no_aprobado; vacío ⇒ desconocido (no over-block masivo) ──
@pytest.mark.parametrize(
    "estado", ["no", "false", "revocado", "no renovado", "pendiente", "not approved"]
)
def test_norm_lmr_ue_no_afirmativo_es_no_aprobado(estado):
    rows = [{"ingrediente_activo": "mancozeb", "lmr_mg_kg": "", "aprobado": estado}]
    out = feeds._norm_lmr_ue(rows, _LMR_MAP)
    assert out["no_aprobados"] == ["mancozeb"]


def test_norm_lmr_ue_vacio_es_desconocido_no_no_aprobado():
    rows = [{"ingrediente_activo": "mancozeb", "lmr_mg_kg": "0.01", "aprobado": ""}]
    out = feeds._norm_lmr_ue(rows, _LMR_MAP)
    assert "mancozeb" not in out["no_aprobados"]
    assert "mancozeb" not in out["lmr_mg_kg"]


def test_norm_lmr_ue_afirmativo_es_aprobado():
    rows = [{"ingrediente_activo": "abamectina", "lmr_mg_kg": "0,01", "aprobado": "si"}]
    out = feeds._norm_lmr_ue(rows, _LMR_MAP)
    assert out["lmr_mg_kg"]["abamectina"] == 0.01


# ── #7: as_of "del futuro" más allá del skew ⇒ STALE (no evade el gate) ──────────────────────────
def test_as_of_futuro_lejano_es_stale():
    view = FeedSnapshotView(FeedName.ICA.value, NOW + timedelta(days=400))
    assert freshness_state(view, now=NOW) is FreshnessState.STALE


def test_as_of_futuro_dentro_del_skew_sigue_ok():
    view = FeedSnapshotView(FeedName.ICA.value, NOW + timedelta(minutes=2))
    assert freshness_state(view, now=NOW) is FreshnessState.OK


# ── #8: frescura del feed de DESTINO también se evalúa (antes solo ICA) ──────────────────────────
def test_frescura_destino_stale_emite_amarillo(monkeypatch):
    ica = {"registros": [{"ingrediente_activo": "abamectina", "estado": "vigente"}]}
    lmr = {"lmr_mg_kg": {"abamectina": 0.01}, "no_aprobados": []}
    _install_feeds(
        monkeypatch,
        {
            FeedName.ICA: (ica, NOW, "ok"),
            FeedName.LMR_UE: (lmr, NOW - timedelta(days=90), "ok"),  # stale (ttl 7d)
        },
    )
    findings = regulatory.live_regulatory_findings(
        object(), "Aplica abamectina 0.5 L/ha.", export_market="ue", now=NOW
    )
    assert any(
        f.severity is Semaforo.AMARILLO and f.feed == FeedName.LMR_UE.value for f in findings
    )


# ── #9: destino de exportación SIN feed mapeado ⇒ no es VERDE confiable (fail-closed) ────────────
def test_mercado_no_soportado_degrada_a_amarillo(monkeypatch):
    ica = {"registros": [{"ingrediente_activo": "abamectina", "estado": "vigente"}]}
    _install_feeds(monkeypatch, {FeedName.ICA: (ica, NOW, "ok")})
    ans = _answer("Aplica abamectina 0.5 L/ha.")
    integration.apply_online_safety(object(), ans, export_market="japon", now=NOW)
    assert ans.semaforo is Semaforo.AMARILLO
    assert any("japon" in w for w in ans.warnings)


# ── #11: payload con esquema drifteado NO se sirve como feed fresco ──────────────────────────────
def test_payload_status_detecta_esquema_drifteado():
    assert feeds.payload_status(FeedName.ICA.value, {"records": []}) == "schema_invalid"
    assert feeds.payload_status(FeedName.ICA.value, {"registros": []}) == "ok"


def test_latest_view_none_si_esquema_invalido(monkeypatch):
    bad = FeedSnapshot(
        feed_name=FeedName.ICA.value,
        as_of=NOW,
        ttl_seconds=7 * 24 * 3600,
        sha256="0" * 64,
        payload={"records": []},
        status="schema_invalid",
    )
    monkeypatch.setattr(feeds, "latest_snapshot", lambda _s, f: bad)
    assert feeds.latest_view(object(), FeedName.ICA) is None


# ── #13: UN solo aviso de frescura ICA por respuesta (no uno por i.a.) ───────────────────────────
def test_un_solo_aviso_de_frescura_ica(monkeypatch):
    ica = {
        "registros": [
            {"ingrediente_activo": "clorpirifos", "estado": "cancelado"},
            {"ingrediente_activo": "abamectina", "estado": "vigente"},
        ]
    }
    _install_feeds(monkeypatch, {FeedName.ICA: (ica, NOW - timedelta(days=90), "ok")})  # stale
    findings = regulatory.live_regulatory_findings(
        object(), "Aplica clorpirifos 1 L/ha y abamectina 0.5 L/ha.", now=NOW
    )
    fresh = [f for f in findings if f.severity is Semaforo.AMARILLO and f.ingrediente_activo == "*"]
    assert len(fresh) == 1
