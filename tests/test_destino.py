"""Guardarraíl de autorización por país de DESTINO de exportación.

Unitarios (sin DB/LLM) del módulo `destino` + un test de integración que comprueba que el pipeline
fuerza ROJO cuando la respuesta recomienda un activo permitido en Colombia pero NO autorizado en el
destino (mancozeb en la UE) — el caso que el guardarraíl de prohibidos del ICA NO cubría.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from avorag.config import Settings
from avorag.providers.fakes import FakeEmbedding, FakeLLM
from avorag.rag import destino as D
from avorag.rag import guardrails as G
from avorag.rag import pipeline as P
from avorag.retrieval.types import ScoredChunk


# ---------------- unitarios del módulo ----------------
def test_detecta_activo_no_autorizado_en_ue() -> None:
    hits = D.unauthorized_for_destination("Para el control aplica clorpirifos 0.5 L/ha", market="ue")
    assert hits and "clorpirifos" in hits[0].lower()
    assert "europ" in hits[0].lower()  # nombra el mercado de destino


def test_apagado_si_no_hay_mercado() -> None:
    assert D.unauthorized_for_destination("usar clorpirifos", market="") == []


def test_mercado_desconocido_no_rompe() -> None:
    assert D.unauthorized_for_destination("usar clorpirifos", market="narnia") == []


def test_activo_permitido_no_marca() -> None:
    assert D.unauthorized_for_destination("aplica azufre y aceite agrícola", market="ue") == []


def test_match_insensible_a_acentos_y_mayusculas() -> None:
    assert D.unauthorized_for_destination("MANCOZEB en mezcla", market="ue")


def test_lmr_estricto_avisa_sin_bloquear() -> None:
    w = D.strict_lmr_for_destination("se usó imidacloprid", market="ue")
    assert w and "imidacloprid" in w[0].lower()


def test_available_markets_incluye_ue() -> None:
    assert "ue" in D.available_markets()


def test_market_por_defecto_desde_settings(monkeypatch) -> None:
    monkeypatch.setattr(D, "get_settings", lambda: Settings(export_market="ue"))
    assert D.unauthorized_for_destination("clorpirifos")  # sin market → usa EXPORT_MARKET


def test_market_name() -> None:
    assert D.market_name("ue").lower().startswith("uni")  # "Unión Europea"


# ---------------- integración con el pipeline ----------------
@contextmanager
def _fake_session(tenant=None):
    yield SimpleNamespace(add=lambda *a, **k: None)


def _chunk(content: str) -> ScoredChunk:
    chunk = SimpleNamespace(
        id="c1", content=content, context=None, pagina=12,
        meta={"fuente": "ICA - Manejo fitosanitario", "cultivo": "hass"},
    )
    return ScoredChunk(chunk=chunk, score=3.0)


class _MancozebLLM:
    """Recomienda mancozeb: permitido en Colombia, NO aprobado en la UE."""

    name = "mancozeb"

    def complete(self, system, user, *, temperature=None, max_tokens=None) -> str:
        if "faithful" in system.lower() or "seguro" in system.lower():
            return '{"faithful": true, "score": 0.9, "unsupported": []}'
        return "Para la antracnosis, aplica mancozeb 2.5 g/L [1]."

    def stream(self, system, user, *, temperature=None, max_tokens=None):
        yield self.complete(system, user)


def test_pipeline_fuerza_rojo_si_no_autorizado_en_destino(monkeypatch) -> None:
    s = Settings(export_market="ue")
    monkeypatch.setattr(P, "get_settings", lambda: s)
    monkeypatch.setattr(D, "get_settings", lambda: s)
    monkeypatch.setattr(P, "get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr(P, "get_llm_provider", lambda: _MancozebLLM())
    monkeypatch.setattr(G, "get_judge_llm_provider", lambda: FakeLLM())
    monkeypatch.setattr(P, "hybrid_search", lambda *a, **k: [_chunk("mancozeb 2.5 g/L para antracnosis")])
    monkeypatch.setattr(P, "rerank_chunks", lambda q, c, **k: c)
    monkeypatch.setattr(P, "get_session", _fake_session)
    monkeypatch.setattr(P, "_persist", lambda *a, **k: None)
    monkeypatch.setattr(P, "_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(P, "_cache_put", lambda *a, **k: None)

    ans = P.answer("¿con qué controlo la antracnosis para exportar a Europa?")
    assert ans.semaforo.value == "rojo"
    assert "⛔" in ans.text
    assert "destino" in ans.text.lower()  # el mensaje nombra la restricción de destino


def test_pipeline_no_rojo_sin_mercado_destino(monkeypatch) -> None:
    # Sin EXPORT_MARKET, el guardarraíl de destino está apagado (no debe forzar rojo por mancozeb).
    s = Settings(export_market="")
    monkeypatch.setattr(P, "get_settings", lambda: s)
    monkeypatch.setattr(D, "get_settings", lambda: s)
    monkeypatch.setattr(P, "get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr(P, "get_llm_provider", lambda: _MancozebLLM())
    monkeypatch.setattr(G, "get_judge_llm_provider", lambda: FakeLLM())
    monkeypatch.setattr(P, "hybrid_search", lambda *a, **k: [_chunk("mancozeb 2.5 g/L para antracnosis")])
    monkeypatch.setattr(P, "rerank_chunks", lambda q, c, **k: c)
    monkeypatch.setattr(P, "get_session", _fake_session)
    monkeypatch.setattr(P, "_persist", lambda *a, **k: None)
    monkeypatch.setattr(P, "_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(P, "_cache_put", lambda *a, **k: None)

    ans = P.answer("¿con qué controlo la antracnosis?")
    assert "destino" not in ans.text.lower()  # guardarraíl de destino apagado


# ---------------- contrato de datos: los JSON de destino no pueden romperse en silencio ----------------
_DESTINOS = Path(__file__).resolve().parents[1] / "data" / "destinos"


def test_archivos_destino_bien_formados_y_usables() -> None:
    files = list(_DESTINOS.glob("destino_*.json"))
    assert files, "debe existir al menos un archivo data/destinos/destino_*.json"
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data.get("mercado") and data.get("nombre"), f"{f.name}: falta mercado/nombre"
        items = data.get("no_autorizados")
        assert isinstance(items, list) and items, f"{f.name}: no_autorizados vacío o ausente"
        market = data["mercado"]
        for it in items:
            assert it.get("ingrediente_activo") and it.get("estado") and it.get("motivo"), f"{f.name}: entrada incompleta"
            assert it["estado"] in {"no_aprobado", "retirado", "prohibido", "cancelado_epa", "sin_tolerancia"}, \
                f"{f.name}: estado inválido {it['estado']}"
        # Round-trip: cada activo listado DEBE detectarse en un texto que lo menciona (la lista es usable).
        for it in items:
            ia = it["ingrediente_activo"]
            assert D.unauthorized_for_destination(f"se recomienda aplicar {ia} en el cultivo", market=market), \
                f"{f.name}: '{ia}' está en la lista pero no se detecta"


def test_ue_conserva_activos_criticos() -> None:
    # Un edit futuro NO debe poder dropear silenciosamente los activos clave (verificados) de la UE.
    data = json.loads((_DESTINOS / "destino_ue.json").read_text(encoding="utf-8"))
    actives = {i["ingrediente_activo"] for i in data["no_autorizados"]}
    for crit in ("clorpirifos", "mancozeb", "clorotalonil", "paraquat", "carbendazim"):
        assert crit in actives, f"falta el activo crítico verificado «{crit}» en destino_ue.json"
