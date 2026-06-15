"""End-to-end del pipeline `answer()` con proveedores FAKE.

Ejercita la orquestación completa —intención → recuperación → prompt → generación → jueces →
guardarraíles → semáforo → cita— sin Ollama, sin claves y sin Postgres.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from avorag.providers.fakes import FakeEmbedding, FakeLLM
from avorag.rag import guardrails as G
from avorag.rag import pipeline as P
from avorag.retrieval.types import ScoredChunk


@contextmanager
def _fake_session(tenant=None):
    yield SimpleNamespace(add=lambda *a, **k: None)


def _chunk(content: str, **meta) -> ScoredChunk:
    base = {"fuente": "ICA - Manejo fitosanitario", "cultivo": "hass"}
    chunk = SimpleNamespace(
        id="c1", content=content, context=None, pagina=12, meta={**base, **meta}
    )
    return ScoredChunk(chunk=chunk, score=3.0)


def _wire(monkeypatch, chunks) -> None:
    monkeypatch.setattr(P, "get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr(P, "get_llm_provider", lambda: FakeLLM())
    monkeypatch.setattr(G, "get_judge_llm_provider", lambda: FakeLLM())
    monkeypatch.setattr(P, "hybrid_search", lambda *a, **k: chunks)
    monkeypatch.setattr(P, "rerank_chunks", lambda q, c, **k: c)
    monkeypatch.setattr(P, "get_session", _fake_session)
    monkeypatch.setattr(P, "_persist", lambda *a, **k: None)
    monkeypatch.setattr(P, "_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(P, "_cache_put", lambda *a, **k: None)


def test_answer_e2e_verde_con_cita(monkeypatch) -> None:
    _wire(
        monkeypatch,
        [_chunk("Para el trips en aguacate Hass se recomienda monitoreo y manejo integrado.")],
    )
    ans = P.answer("¿Cómo manejo el trips en aguacate Hass?")
    assert ans.semaforo.value in ("verde", "amarillo")
    assert not ans.abstained
    assert "[1]" in ans.text
    assert len(ans.citations) == 1
    assert ans.citations[0].fuente.startswith("ICA")
    assert ans.citations[0].pagina == 12
    assert ans.provider_info.get("prompt_version")


def test_answer_e2e_abstains_on_other_crop(monkeypatch) -> None:
    # Pre-filtro de intención: cultivo ajeno -> abstención antes de recuperar.
    _wire(monkeypatch, [_chunk("contenido irrelevante")])
    ans = P.answer("¿Cómo siembro arroz en zona inundable?")
    assert ans.abstained
    assert ans.abstention_type.value == "out_of_collection"
    assert ans.disclaimer.strip()


def test_answer_stream_emite_delta_verifying_final(monkeypatch) -> None:
    _wire(
        monkeypatch,
        [_chunk("Para el trips en aguacate Hass se recomienda monitoreo y manejo integrado.")],
    )
    events = list(P.answer_stream("¿Cómo manejo el trips en aguacate Hass?"))
    kinds = [k for k, _ in events]
    assert kinds.count("delta") >= 1
    assert "verifying" in kinds
    assert kinds[-1] == "final"
    assert kinds.index("verifying") < kinds.index("final")
    streamed = "".join(p for k, p in events if k == "delta")
    final = events[-1][1]
    assert streamed.strip() == final.text.strip()
    assert "[1]" in final.text
    assert final.provider_info.get("prompt_version")


def test_answer_stream_conversational_solo_final(monkeypatch) -> None:
    _wire(monkeypatch, [_chunk("irrelevante")])
    events = list(P.answer_stream("Hola, buenas"))
    assert [k for k, _ in events] == ["final"]
    assert events[0][1].semaforo.value == "verde"
    assert not events[0][1].abstained
