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


class _RecoveringLLM:
    """Primera generación rota (chino o solo SEGUIMIENTO); al reintentar (prompt con 'AVISO')
    devuelve una respuesta válida en español. Sirve para probar la detección + regeneración."""

    name = "recovering"

    def __init__(self, broken: str) -> None:
        self._broken = broken
        self.good = "Según la fuente, aplica un plan de manejo integrado [1].\nSEGUIMIENTO:\n- ¿Y el riego?"

    def complete(self, system, user, *, temperature=None, max_tokens=None) -> str:
        if "faithful" in system.lower() or "seguro" in system.lower():
            return '{"faithful": true, "score": 0.9, "unsupported": []}'
        return self.good if "AVISO" in system else self._broken

    def stream(self, system, user, *, temperature=None, max_tokens=None):
        for word in self.complete(system, user).split(" "):
            yield word + " "


class _AbstainingLLM:
    """Se abstiene (NO_LO_SE) pero le pega una sección SEGUIMIENTO, como hace el modelo real."""

    name = "abstain"

    def complete(self, system, user, *, temperature=None, max_tokens=None) -> str:
        return "NO_LO_SE\n\nSEGUIMIENTO:\n- ¿Cuál es tu tipo de suelo?\n- ¿Hiciste análisis de suelo?"

    def stream(self, system, user, *, temperature=None, max_tokens=None):
        for word in self.complete(system, user).split(" "):
            yield word + " "


def _wire(monkeypatch, chunks, llm=None) -> None:
    monkeypatch.setattr(P, "get_embedding_provider", lambda: FakeEmbedding())
    monkeypatch.setattr(P, "get_llm_provider", lambda: llm or FakeLLM())
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


def test_answer_regenera_si_deriva_a_chino(monkeypatch) -> None:
    chino = "[6] 根据计算，土壤中钾的含量为274.83 kg K/ha。建议施用钾肥。"
    _wire(monkeypatch, [_chunk("Plan de fertilización del Hass con potasio.")], llm=_RecoveringLLM(chino))
    ans = P.answer("¿Cuál es el plan de fertilización del Hass?")
    assert "钾" not in ans.text  # no chino en la respuesta final
    assert ans.text.strip()  # no vacía
    assert ans.semaforo.value != "rojo"  # la regeneración la salvó, no es un rechazo


def test_answer_stream_resetea_y_recupera_ante_deriva(monkeypatch) -> None:
    chino = "[6] 根据计算，土壤中钾的含量。建议施用钾肥以补充养分。"
    _wire(monkeypatch, [_chunk("Plan de fertilización del Hass.")], llm=_RecoveringLLM(chino))
    events = list(P.answer_stream("¿Cuál es el plan de fertilización del Hass?"))
    kinds = [k for k, _ in events]
    assert "reset" in kinds  # detectó el chino y avisó al cliente que limpie
    assert kinds[-1] == "final"
    final = events[-1][1]
    assert "钾" not in final.text and final.text.strip()
    assert final.semaforo.value != "rojo"


def test_answer_regenera_si_cuerpo_vacio(monkeypatch) -> None:
    # El modelo solo emite la sección SEGUIMIENTO: -> cuerpo vacío -> debe regenerar.
    solo_seguimiento = "SEGUIMIENTO:\n- ¿Cuál es tu tipo de suelo?\n- ¿Hiciste análisis de suelo?"
    _wire(monkeypatch, [_chunk("Plan de fertilización del Hass.")], llm=_RecoveringLLM(solo_seguimiento))
    ans = P.answer("¿Cuál es el plan de fertilización del Hass?")
    assert len(ans.text.strip()) > 20  # ya no sale vacía


def test_pregunta_fijada_se_sirve_sin_recuperacion(monkeypatch) -> None:
    from avorag.rag.schemas import Answer, Semaforo

    monkeypatch.setattr(P, "_PINNED", {})  # aislar de otros tests

    def _boom(*a, **k):
        raise AssertionError("una respuesta fijada no debe recuperar ni generar")

    monkeypatch.setattr(P, "hybrid_search", _boom)

    pinned = Answer(question="¿pregunta fija?", text="Respuesta fija [1].", semaforo=Semaforo.VERDE)
    P.pin_answer("¿Pregunta fija?", pinned)

    ans = P.answer("¿Pregunta fija?")  # mayúsculas distintas: la clave normaliza con .lower()
    assert ans.text == "Respuesta fija [1]."
    events = list(P.answer_stream("¿Pregunta fija?"))
    assert [k for k, _ in events] == ["final"]
    assert events[0][1].text == "Respuesta fija [1]."


def test_generation_problem_detecta_fallos() -> None:
    assert P._generation_problem("PREGUNTA DEL PRODUCTOR:\n¿algo?\n\nFRAGMENTOS:\n[1]") == "eco"
    assert P._generation_problem("[6] 根据计算，施用钾肥。") == "idioma"
    assert P._generation_problem("ok") == "vacia"
    assert P._generation_problem("Para los trips, haz monitoreo con trampas azules [1].") is None


def test_is_abstention_solo_marcador_no_si_hay_respuesta() -> None:
    # NO_LO_SE solo = abstención. NO_LO_SE + respuesta real = NO es abstención (el 3B antepone
    # el marcador como tic; hay que conservar la respuesta, no descartarla).
    assert P._is_abstention("NO_LO_SE")
    assert P._is_abstention("NO_LO_SE.")
    assert not P._is_abstention("NO_LO_SE\n\nPara el trips usa monitoreo con trampas azules [1].")
    assert not P._is_abstention("Aplica monitoreo de trips con trampas azules [1].")


def test_tic_no_lo_se_no_mata_la_respuesta(monkeypatch) -> None:
    # El 3B antepone NO_LO_SE pero responde bien: el pipeline debe conservar la respuesta.
    class _TicLLM:
        name = "tic"

        def complete(self, system, user, *, temperature=None, max_tokens=None) -> str:
            if "faithful" in system.lower() or "seguro" in system.lower():
                return '{"faithful": true, "score": 0.9, "unsupported": []}'
            return "NO_LO_SE\n\nPara el trips, aplica manejo integrado con monitoreo [1]."

        def stream(self, system, user, *, temperature=None, max_tokens=None):
            for w in self.complete(system, user).split(" "):
                yield w + " "

    _wire(monkeypatch, [_chunk("El trips se maneja con monitoreo y control biológico.")], llm=_TicLLM())
    ans = P.answer("¿Cómo manejo los trips en aguacate Hass?")
    assert not ans.abstained
    assert "manejo integrado" in ans.text and "NO_LO_SE" not in ans.text


def test_strip_meta_quita_preambulos_y_colofones() -> None:
    txt = (
        "Para responder a esta solicitud, primero se necesita identificar qué se busca. "
        "Sin embargo, basándome en los fragmentos, puedo decir lo siguiente. "
        "El manejo del trips se hace con monitoreo y control biológico [1]. "
        "Para obtener una respuesta más completa, se necesitaría revisar todos los fragmentos."
    )
    out = P._strip_meta(txt)
    assert "Para responder a esta solicitud" not in out
    assert "Para obtener una respuesta más completa" not in out
    assert "monitoreo y control biológico [1]" in out
    # No debe vaciar una respuesta que ya es directa.
    directa = "El trips se controla con trampas azules y hongos entomopatógenos [2]."
    assert P._strip_meta(directa) == directa


def test_answer_abstencion_con_seguimiento_pegado(monkeypatch) -> None:
    # Bug real: NO_LO_SE + SEGUIMIENTO pegado dejaba la respuesta VACÍA. Ahora se abstiene bien.
    _wire(monkeypatch, [_chunk("contenido")], llm=_AbstainingLLM())
    ans = P.answer("¿Cuál es el plan de fertilización del Hass?")
    assert ans.abstained
    assert ans.text.strip() and "NO_LO_SE" not in ans.text and "SEGUIMIENTO" not in ans.text


def test_answer_stream_abstencion_resetea_y_no_verifica(monkeypatch) -> None:
    _wire(monkeypatch, [_chunk("contenido")], llm=_AbstainingLLM())
    events = list(P.answer_stream("¿Cuál es el plan de fertilización del Hass?"))
    kinds = [k for k, _ in events]
    assert "reset" in kinds  # limpia el NO_LO_SE que se streameó
    assert "verifying" not in kinds  # una abstención no pasa por los jueces
    final = events[-1][1]
    assert final.abstained and final.text.strip() and "NO_LO_SE" not in final.text
