"""Resiliencia de la recuperación (amplifica las fortalezas #11 y #16).

Si el reranker o la búsqueda léxica fallan, la consulta NO se cae: degrada al orden RRF / al
canal denso. Congela esa tolerancia con pruebas.
"""

from __future__ import annotations

from types import SimpleNamespace

from avorag.retrieval import hybrid as H
from avorag.retrieval import rerank as R
from avorag.retrieval.types import ScoredChunk


class _RaisingRerank:
    def rerank(self, query, docs, top_k):
        raise RuntimeError("modelo de reranking caído")


def _cand(content: str, score: float) -> ScoredChunk:
    return ScoredChunk(
        chunk=SimpleNamespace(id="c", content=content, context=None, pagina=1, meta={}), score=score
    )


def test_rerank_degrades_to_rrf_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(R, "get_rerank_provider", lambda: _RaisingRerank())
    candidates = [_cand("a", 3.0), _cand("b", 2.0), _cand("c", 1.0)]
    out = R.rerank_chunks("consulta", candidates, final_k=2)
    # Degradó al orden RRF (los 2 primeros candidatos), sin propagar la excepción.
    assert [c.chunk.content for c in out] == ["a", "b"]


class _RaisingSession:
    def __init__(self) -> None:
        self.rolled_back = False

    def scalars(self, stmt):
        raise RuntimeError("query FTS malformada")

    def rollback(self) -> None:
        self.rolled_back = True


def test_lexical_search_degrades_and_rolls_back() -> None:
    sess = _RaisingSession()
    out = H.lexical_search(sess, "consulta :: rara", tenant="demo", country="CO", top_k=5)
    assert out == []  # cae al lado denso devolviendo vacío
    assert sess.rolled_back is True  # limpió la transacción
