"""Seguridad de `export_market`: una sola normalización canónica (config + API + online), fail-loud.

Cierra el falso negativo EXISTENCIAL del reporte: una grafía de mercado de destino NO soportada NO
debe apagar EN SILENCIO el cruce de tolerancias EE.UU. (40 CFR 180) y dejar salir VERDE un i.a. sin
tolerancia para aguacate. La normalización canónica vive en `avorag.markets` y la comparten la config,
el borde de la API y el guardarraíl online (DRY); un valor con cobertura se CANONIZA a {ue, eeuu} y una
grafía sin cobertura FALLA RUIDOSAMENTE (arranque/422) o, en el online, fail-closed (nunca VERDE mudo).

Complementa (no duplica) test_market_normalization.py (#9/#10) y test_security_hardening_online.py (#9).

NOTA sobre qué muerde el bug del VALIDADOR de config: como `normalize_market` ya aliasaba
'estados_unidos'→'eeuu' (de #40) y la ruta online re-normaliza aguas abajo, los dos tests existenciales
del online (estados_unidos→ROJO) PASARÍAN incluso sin el validador: guardan el OUTCOME end-to-end, no la
regresión del validador. Los tests que de verdad distinguen old-vs-new del validador son los de config
(`test_config_canoniza_export_market` para grafías aliasables y `test_config_rechaza_export_market_
desconocido_al_arrancar` para las NO aliasables) y los del borde de la API.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from avorag import markets
from avorag.api.routes_chat import AskRequest
from avorag.config import Settings
from avorag.online import feeds, integration, regulatory
from avorag.online.feeds import FeedSnapshot
from avorag.rag.freshness import FeedName, FeedSnapshotView
from avorag.rag.schemas import Answer, Semaforo

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)


# ── markets: ÚNICA fuente de verdad del conjunto soportado (DRY, punto 4) ─────────────────────────
def test_supported_markets_es_la_fuente_unica():
    assert frozenset({"ue", "eeuu"}) == markets.SUPPORTED_MARKETS
    # online/integration consume EL MISMO objeto, no un duplicado que pueda divergir.
    assert integration.SUPPORTED_MARKETS is markets.SUPPORTED_MARKETS


@pytest.mark.parametrize(
    "raw",
    [
        "eeuu",
        "us",
        "usa",
        "USA",
        "estados_unidos",
        "estados unidos",
        "EE.UU.",
        "EE UU",
        "ue",
        "UE",
        "eu",
        "europa",
        "union europea",
    ],
)
def test_is_supported_market_acepta_alias(raw):
    assert markets.is_supported_market(raw) is True


@pytest.mark.parametrize(
    "raw", ["usa-en", "japon", "estadosunidos", "reino unido", "america", "", "   ", None]
)
def test_is_supported_market_rechaza_desconocidos_y_vacio(raw):
    assert markets.is_supported_market(raw) is False


# ── config: validación de ARRANQUE (fail-loud, no apagado silencioso — punto 2) ───────────────────
@pytest.mark.parametrize(
    ("raw", "canon"),
    [
        ("estados_unidos", "eeuu"),  # el ejemplo del reporte → ya NO se acepta como mercado mudo
        ("EE.UU.", "eeuu"),
        ("usa", "eeuu"),
        ("us", "eeuu"),
        ("eeuu", "eeuu"),
        ("ue", "ue"),
        ("union europea", "ue"),
        ("EUROPA", "ue"),
        ("", ""),  # vacío = guardarraíl de destino apagado (permitido)
        ("   ", ""),
    ],
)
def test_config_canoniza_export_market(raw, canon):
    assert Settings(export_market=raw).export_market == canon


@pytest.mark.parametrize(
    "raw", ["usa-en", "japon", "estadosunidos", "reino unido", "america", "uee"]
)
def test_config_rechaza_export_market_desconocido_al_arrancar(raw):
    # Una grafía no soportada ABORTA la construcción de Settings (arranque), en vez de apagar en
    # silencio el cruce de tolerancias del destino. Fail-loud, no fail-open.
    with pytest.raises(ValidationError):
        Settings(export_market=raw)


# ── API (routes_chat): el borde canoniza (punto 3); grafía sin cobertura → 422 ────────────────────
@pytest.mark.parametrize(
    ("raw", "canon"),
    [
        ("us", "eeuu"),  # antes daba 422; ahora se canoniza (alineado con el núcleo)
        ("usa", "eeuu"),
        ("estados_unidos", "eeuu"),
        ("eeuu", "eeuu"),
        ("ue", "ue"),
        ("union europea", "ue"),
        (None, None),
        ("", None),
    ],
)
def test_api_canoniza_export_market(raw, canon):
    req = AskRequest(question="¿qué aplico para el trips?", export_market=raw)
    assert req.export_market == canon


@pytest.mark.parametrize("raw", ["usa-en", "japon", "estadosunidos"])
def test_api_rechaza_export_market_desconocido(raw):
    # ValidationError de pydantic ⇒ FastAPI responde 422 (rechazo ruidoso, no aceptación silenciosa).
    with pytest.raises(ValidationError):
        AskRequest(question="¿qué aplico para el trips?", export_market=raw)


# ── Fixtures online: TOL_EEUU (40 CFR 180) fresco con i.a. SIN tolerancia + ICA vacío ─────────────
def _install_tol_eeuu(monkeypatch, sin_tolerancia: list[str]) -> None:
    snaps = {
        FeedName.TOL_EEUU.value: FeedSnapshot(
            feed_name=FeedName.TOL_EEUU.value,
            as_of=NOW,
            ttl_seconds=7 * 24 * 3600,
            sha256="0" * 64,
            payload={"avocado_tolerances_ppm": {}, "sin_tolerancia": sin_tolerancia},
            status="ok",
        ),
        FeedName.ICA.value: FeedSnapshot(
            feed_name=FeedName.ICA.value,
            as_of=NOW,
            ttl_seconds=7 * 24 * 3600,
            sha256="0" * 64,
            payload={"registros": []},
            status="ok",
        ),
    }

    def latest_snapshot(_s, feed):
        return snaps.get(str(getattr(feed, "value", feed)))

    def latest_view(_s, feed):
        snap = snaps.get(str(getattr(feed, "value", feed)))
        return (
            None if snap is None else FeedSnapshotView(snap.feed_name, snap.as_of, snap.ttl_seconds)
        )

    monkeypatch.setattr(feeds, "latest_snapshot", latest_snapshot)
    monkeypatch.setattr(feeds, "latest_view", latest_view)


# ── PUNTO 5 (existencial, GUARDA DE OUTCOME): una grafía ALIASABLE cruza la tolerancia EE.UU. y BLOQUEA
# OJO: estos dos tests pasan también sin el validador de config (el alias 'estados_unidos'→'eeuu' ya
# existía en #40 y el online re-normaliza); guardan el resultado end-to-end, NO la regresión del
# validador (esa la muerden los tests de config/API de arriba). Ver la NOTA del docstring del módulo.
@pytest.mark.parametrize("grafia", ["estados_unidos", "EE.UU.", "usa", "us", "eeuu"])
def test_grafia_aliasable_cruza_tolerancia_eeuu_y_bloquea(monkeypatch, grafia):
    # El mercado se pasa por la MISMA canonización que aplicaría config/API → 'eeuu' → carga TOL_EEUU.
    _install_tol_eeuu(monkeypatch, sin_tolerancia=["fenamidona"])
    market = Settings(export_market=grafia).export_market  # lo que vería el núcleo tras canonizar
    findings = regulatory.live_regulatory_findings(
        object(), "Aplica fenamidona 1 L/ha.", export_market=market, now=NOW
    )
    assert any(f.severity is Semaforo.ROJO and f.feed == FeedName.TOL_EEUU.value for f in findings)


def test_estados_unidos_no_deja_verde_en_online(monkeypatch):
    # End-to-end (guarda de OUTCOME): 'estados_unidos' → eeuu → i.a. sin tolerancia ⇒ ROJO, no VERDE.
    _install_tol_eeuu(monkeypatch, sin_tolerancia=["fenamidona"])
    market = Settings(export_market="estados_unidos").export_market
    ans = Answer(
        question="q", text="Aplica fenamidona 1 L/ha.", semaforo=Semaforo.VERDE, warnings=[]
    )
    integration.apply_online_safety(object(), ans, export_market=market, now=NOW)
    assert ans.semaforo is Semaforo.ROJO


def test_grafia_no_aliasable_directa_al_online_no_es_verde_confiable(monkeypatch):
    # Defensa en profundidad: si una grafía SIN cobertura llega DIRECTA al online (saltándose
    # config/API), el fail-closed la degrada (nunca un VERDE mudo) y avisa. Aquí 'usa-en' → 'usa en'.
    _install_tol_eeuu(monkeypatch, sin_tolerancia=["fenamidona"])
    ans = Answer(
        question="q", text="Aplica fenamidona 1 L/ha.", semaforo=Semaforo.VERDE, warnings=[]
    )
    integration.apply_online_safety(object(), ans, export_market="usa-en", now=NOW)
    assert ans.semaforo is not Semaforo.VERDE
    assert ans.warnings


# ── Invariante de NO-escalado: el ramal de destino no soportado nunca toca un ROJO ya decidido ───
def test_destino_no_soportado_no_degrada_rojo_existente(monkeypatch):
    _install_tol_eeuu(monkeypatch, sin_tolerancia=[])
    ans = Answer(
        question="q", text="Aplica abamectina 1 L/ha.", semaforo=Semaforo.ROJO, warnings=[]
    )
    integration.apply_online_safety(object(), ans, export_market="japon", now=NOW)
    assert ans.semaforo is Semaforo.ROJO  # ni sube ni degrada un ROJO ya decidido
