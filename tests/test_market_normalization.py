"""Regresiones de la 2.ª tanda de la auditoría (núcleo, con el chat offline en pausa).

- #9/#10: una sola normalización canónica de `export_market` (alias us/usa/estados_unidos→eeuu) que
  comparten el guardarraíl de destino OFFLINE (`rag/destino.py`) y el cruce ONLINE; antes podían mirar
  mercados distintos en el mismo request y 'us'/'usa' no encontraban `destino_eeuu.json`.
- #2: marcas comerciales de i.a. PROHIBIDOS (ya en prohibidos_co.json) como backstop del guardarraíl.
"""

from __future__ import annotations

import pytest

from avorag.markets import normalize_market
from avorag.online import integration
from avorag.rag import destino, guardrails
from avorag.rag.freshness import FeedName, regulatory_feeds_for


# ── #9/#10: normalización canónica de mercado ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw", ["us", "usa", "USA", "estados unidos", "estados_unidos", "EE.UU.", "EE UU", "eeuu"]
)
def test_normalize_market_alias_eeuu(raw):
    assert normalize_market(raw) == "eeuu"


@pytest.mark.parametrize("raw", ["ue", "UE", "union europea", "eu", "Europa"])
def test_normalize_market_alias_ue(raw):
    assert normalize_market(raw) == "ue"


def test_normalize_market_vacio_y_desconocido():
    assert normalize_market(None) is None
    assert normalize_market("") is None
    assert normalize_market("   ") is None
    assert normalize_market("japon") == "japon"  # desconocido → normalizado, no se inventa alias
    assert normalize_market("Reino Unido") == "reino unido"


def test_offline_y_online_resuelven_el_mismo_mercado():
    # La clave del #10: ambos guardarraíles resuelven IDÉNTICO para cualquier grafía del mismo destino.
    for m in ["usa", "us", "estados_unidos", "EE.UU.", "ue", "eu", "union europea"]:
        assert destino._resolve_market(m) == integration._resolve_market(m)


def test_destino_alias_usa_carga_eeuu():
    # 'usa' debe encontrar destino_eeuu.json igual que 'eeuu' (antes quedaba apagado en silencio).
    assert destino._resolve_market("usa") == "eeuu"
    assert destino.market_name("usa") == destino.market_name("eeuu") != ""


def test_destino_unauthorized_con_alias_usa():
    # metamidofos está en no_autorizados de destino_eeuu.json → 'usa' debe detectarlo igual que 'eeuu'.
    hits = destino.unauthorized_for_destination("Aplica metamidofos 1 L/ha.", "usa")
    assert hits and any("metamidofos" in h for h in hits)


@pytest.mark.parametrize("market", ["usa", "us", "estados_unidos"])
def test_regulatory_feeds_for_alias_eeuu_usa_tol(market):
    needed = regulatory_feeds_for("Aplica abamectina 1 L/ha.", export_market=market)
    assert FeedName.TOL_EEUU in needed and FeedName.ICA in needed


def test_regulatory_feeds_for_ue():
    needed = regulatory_feeds_for("Aplica abamectina 1 L/ha.", export_market="union europea")
    assert FeedName.LMR_UE in needed


# ── #2: marcas comerciales de prohibidos (backstop del guardarraíl base) ─────────────────────────
@pytest.mark.parametrize(
    ("marca", "ia"),
    [
        (
            "Tamarón",
            "metamidofos",
        ),  # acentuada: prueba también el fix de acentos de commercial_actives_in
        ("Nuvacron", "monocrotofos"),
        ("Azodrin", "monocrotofos"),
        ("Temik", "aldicarb"),
        ("Folidol", "metil paration"),
    ],
)
def test_marca_de_prohibido_dispara_backstop(marca, ia):
    hits = guardrails.banned_ingredients_in_answer(f"Para la plaga apliqué {marca} 1 L/ha.")
    assert any(ia in h for h in hits)


def test_monitor_marca_solo_con_contexto_de_aplicacion():
    # 'monitorear' (palabra común) NO debe disparar; 'apliqué Monitor' (con contexto) SÍ.
    assert (
        guardrails.banned_ingredients_in_answer("Conviene monitorear la plaga cada semana.") == []
    )
    hits = guardrails.banned_ingredients_in_answer("Apliqué Monitor 1 L/ha contra el trips.")
    assert any("metamidofos" in h for h in hits)
