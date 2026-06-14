"""Orquestador RAG: la función `answer()` de principio a fin, con auditoría."""

from __future__ import annotations

import re
import time

from avorag.config import get_settings
from avorag.db import QueryLog, get_session
from avorag.logging import get_logger
from avorag.providers import get_embedding_provider, get_llm_provider
from avorag.rag import guardrails
from avorag.rag.prompt import (
    ABSTENTION_MARKER,
    DISCLAIMER,
    build_system_prompt,
    build_user_prompt,
)
from avorag.rag.schemas import (
    AbstentionType,
    Answer,
    Citation,
    RetrievedContext,
    Semaforo,
)
from avorag.retrieval import ScoredChunk, hybrid_search, rerank_chunks

log = get_logger(__name__)
_CITE_RE = re.compile(r"\[(\d+)\]")


def _provider_info() -> dict:
    s = get_settings()
    llm_model = {
        "ollama": s.llm_model,
        "anthropic": s.anthropic_model,
        "openai": s.openai_llm_model,
    }.get(s.llm_provider, s.llm_model)
    return {
        "llm": f"{s.llm_provider}:{llm_model}",
        "embedding": f"{s.embedding_provider}:{s.embedding_model}",
        "rerank": s.rerank_provider,
    }


def _build_contexts(chunks: list[ScoredChunk]) -> list[RetrievedContext]:
    return [
        RetrievedContext(
            chunk_id=str(sc.chunk.id),
            fuente=sc.chunk.meta.get("fuente", "desconocida"),
            pagina=sc.chunk.pagina,
            score=round(float(sc.score), 5),
            content=sc.chunk.content,
        )
        for sc in chunks
    ]


def _extract_citations(answer_text: str, chunks: list[ScoredChunk]) -> list[Citation]:
    used = sorted({int(n) for n in _CITE_RE.findall(answer_text)})
    citations: list[Citation] = []
    for n in used:
        if 1 <= n <= len(chunks):
            c = chunks[n - 1].chunk
            citations.append(
                Citation(
                    chunk_id=str(c.id),
                    fuente=c.meta.get("fuente", "desconocida"),
                    pagina=c.pagina,
                    fecha_publicacion=c.meta.get("fecha_publicacion"),
                    quote=(c.content[:200] + "…") if len(c.content) > 200 else c.content,
                )
            )
    return citations


def _persist(session, ans: Answer, tenant: str) -> None:
    session.add(
        QueryLog(
            tenant=tenant,
            question=ans.question,
            answer=ans.text,
            semaforo=ans.semaforo.value,
            abstained=ans.abstained,
            abstention_type=ans.abstention_type.value,
            faithfulness=ans.faithfulness,
            citations=[c.model_dump() for c in ans.citations],
            retrieved_chunk_ids=[ctx.chunk_id for ctx in ans.contexts],
            provider_info=ans.provider_info,
            latency_ms=ans.latency_ms,
        )
    )


def _abstention(
    question: str,
    atype: AbstentionType,
    *,
    text: str,
    reason: str,
    pinfo: dict,
    t0: float,
    contexts: list[RetrievedContext] | None = None,
) -> Answer:
    return Answer(
        question=question,
        text=text,
        semaforo=Semaforo.AMARILLO,
        abstained=True,
        abstention_type=atype,
        reason=reason,
        contexts=contexts or [],
        disclaimer=DISCLAIMER,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        provider_info=pinfo,
    )


def answer(question: str, *, tenant: str | None = None, country: str | None = None) -> Answer:
    settings = get_settings()
    tenant = tenant or settings.default_tenant
    country = country or settings.country
    t0 = time.perf_counter()
    pinfo = _provider_info()

    with get_session() as session:
        # Pre-filtro de intención: cultivo ajeno → corta antes de gastar embeddings/LLM.
        intent = guardrails.classify_intent(question)
        if intent is not None:
            ans = _abstention(
                question,
                intent,
                text="Mi especialidad es el aguacate Hass; no tengo fuentes verificadas "
                "para ese cultivo. Consulta a tu técnico.",
                reason="Cultivo fuera de la colección curada.",
                pinfo=pinfo,
                t0=t0,
            )
            _persist(session, ans, tenant)
            return ans

        query_vec = get_embedding_provider().embed_query(question)
        candidates = hybrid_search(session, question, query_vec, tenant=tenant, country=country)
        final = rerank_chunks(question, candidates)

        # Sin evidencia suficiente → abstención honesta, etiquetada según el dominio.
        if not final or (final[0].score < settings.min_retrieval_score):
            atype = (
                AbstentionType.OUT_OF_CONTENT
                if guardrails.has_agronomic_signal(question)
                else AbstentionType.OUT_OF_CONTEXT
            )
            ans = _abstention(
                question,
                atype,
                text="No tengo información verificada sobre eso en mis fuentes. "
                "Te recomiendo consultarlo con tu agrónomo o el técnico de tu zona.",
                reason="Recuperación insuficiente en el corpus.",
                pinfo=pinfo,
                t0=t0,
            )
            _persist(session, ans, tenant)
            return ans

        system = build_system_prompt(country)
        user = build_user_prompt(question, final)
        raw = get_llm_provider().complete(system, user).strip()

        contexts = _build_contexts(final)
        contexts_text = "\n\n".join(c.content for c in contexts)

        # El modelo declaró no saber.
        if ABSTENTION_MARKER in raw and len(raw) <= len(ABSTENTION_MARKER) + 5:
            ans = _abstention(
                question,
                AbstentionType.OUT_OF_CONTENT,
                text="No encontré esa información en mis fuentes verificadas. "
                "Consulta a tu técnico antes de actuar.",
                reason="El modelo se abstuvo (sin respaldo en el contexto).",
                pinfo=pinfo,
                t0=t0,
                contexts=contexts,
            )
            _persist(session, ans, tenant)
            return ans

        # Si el modelo dejó el marcador de abstención suelto en una respuesta larga, lo quitamos.
        raw = raw.replace(ABSTENTION_MARKER, "").strip()

        # Guardarraíles.
        doses_ok, unsupported = (
            guardrails.doses_grounded(raw, contexts_text) if settings.dose_guardrail else (True, [])
        )
        faithfulness: float | None = None
        judge_failed = False
        if settings.faithfulness_judge:
            faithfulness, _ = guardrails.faithfulness_judge(question, raw, contexts_text)
            judge_failed = faithfulness is None
        citations = _extract_citations(raw, final)
        cat_tox = guardrails.cited_categoria_toxicologica(final)
        semaforo, reason = guardrails.decide_semaforo(
            doses_ok=doses_ok,
            cat_tox=cat_tox,
            faithfulness=faithfulness,
            has_citations=bool(citations),
            judge_failed=judge_failed,
        )
        if not doses_ok:
            reason += f" (valores sin fuente: {', '.join(unsupported)})"

        ans = Answer(
            question=question,
            text=raw,
            semaforo=semaforo,
            abstained=False,
            faithfulness=faithfulness,
            reason=reason,
            citations=citations,
            contexts=contexts,
            disclaimer=DISCLAIMER,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            provider_info=pinfo,
        )
        _persist(session, ans, tenant)
        log.info(
            "answered",
            tenant=tenant,
            semaforo=semaforo.value,
            faithfulness=faithfulness,
            n_citations=len(ans.citations),
            latency_ms=ans.latency_ms,
        )
        return ans
