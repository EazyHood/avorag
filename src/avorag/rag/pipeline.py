"""Orquestador RAG: la función `answer()` de principio a fin, con auditoría."""

from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from avorag.config import get_settings
from avorag.db import QueryLog, get_session
from avorag.logging import get_logger
from avorag.providers import get_embedding_provider, get_llm_provider
from avorag.rag import conversation, guardrails
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

# Caché en memoria por proceso. Multi-worker requeriría Redis.
_RESPONSE_CACHE: dict[str, tuple[float, Answer]] = {}
_CACHE_MAX = 256


def _cache_key(
    question: str,
    tenant: str,
    country: str,
    soil_type: str | None,
    region: str | None,
) -> str:
    raw = "|".join([question.strip().lower(), tenant, country, soil_type or "", region or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str, ttl: int) -> Answer | None:
    item = _RESPONSE_CACHE.get(key)
    if item is not None and (time.time() - item[0]) < ttl:
        return item[1]
    return None


def _cache_put(key: str, ans: Answer) -> None:
    if len(_RESPONSE_CACHE) >= _CACHE_MAX:
        oldest = min(_RESPONSE_CACHE, key=lambda k: _RESPONSE_CACHE[k][0])
        _RESPONSE_CACHE.pop(oldest, None)
    _RESPONSE_CACHE[key] = (time.time(), ans)


@lru_cache(maxsize=1)
def _corpus_version() -> str:
    """Versión del corpus desde el manifiesto."""
    try:
        p = Path(__file__).resolve().parents[3] / "data" / "corpus_manifest.json"
        return str(json.loads(p.read_text(encoding="utf-8")).get("corpus_version", "desconocido"))
    except Exception:
        return "desconocido"


def _provider_info() -> dict:
    from avorag.providers import judge_provider_label
    from avorag.rag.prompt import PROMPT_VERSION

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
        "judge": judge_provider_label(),
        "prompt_version": PROMPT_VERSION,
        "corpus_version": _corpus_version(),
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
                    url=c.meta.get("url"),
                    doi=c.meta.get("doi"),
                    nivel_autoridad=c.meta.get("nivel_autoridad"),
                    licencia_uso=c.meta.get("licencia_uso"),
                    quote=_targeted_quote(c.content),
                )
            )
    return citations


_QUOTE_RADIUS = 120
_FIRST_DOSE_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s?(?:%|ppm|cc\s?/\s?l|cc|ml|l\s?/\s?ha|kg\s?/\s?ha|g\s?/\s?l|g\s?/\s?ha|kg|g|l)",
    re.IGNORECASE,
)


def _targeted_quote(content: str) -> str:
    """Cita centrada en la primera dosis del fragmento; si no hay dosis, usa el inicio."""
    m = _FIRST_DOSE_RE.search(content)
    if m:
        start = max(0, m.start() - _QUOTE_RADIUS)
        end = min(len(content), m.end() + _QUOTE_RADIUS)
        snippet = content[start:end].strip()
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(content) else ""
        return f"{prefix}{snippet}{suffix}"
    return (content[:200] + "…") if len(content) > 200 else content


_FOLLOWUP_RE = re.compile(r"\n?\s*SEGUIMIENTO\s*:\s*", re.IGNORECASE)


def _split_followups(text: str) -> tuple[str, list[str]]:
    """Separa la sección 'SEGUIMIENTO:' del cuerpo y devuelve (texto, preguntas)."""
    m = _FOLLOWUP_RE.search(text)
    if not m:
        return text, []
    body = text[: m.start()].rstrip()
    follow: list[str] = []
    for line in text[m.end() :].splitlines():
        q = line.strip().lstrip("-•*0123456789. ").strip()
        if "?" in q and len(q) > 8:
            follow.append(q)
    return body, follow[:3]


def _audit_text(value: str, store_text: bool) -> str:
    """Texto en claro o su hash SHA-256 según la política de minimización."""
    if store_text:
        return value
    return f"<sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}>"


def _persist(ans: Answer, tenant: str) -> None:
    """Escribe la auditoría en una sesión propia y corta. Tolerante a fallo: un error de
    escritura no cancela la respuesta ya calculada."""
    settings = get_settings()
    if not settings.audit_enabled:
        return
    store_text = settings.audit_store_text
    try:
        with get_session(tenant=tenant) as session:
            session.add(
                QueryLog(
                    tenant=tenant,
                    question=_audit_text(ans.question, store_text),
                    answer=_audit_text(ans.text, store_text),
                    semaforo=ans.semaforo.value,
                    abstained=ans.abstained,
                    abstention_type=ans.abstention_type.value,
                    faithfulness=ans.faithfulness,
                    citations=[c.model_dump() for c in ans.citations],
                    retrieved_chunk_ids=[ctx.chunk_id for ctx in ans.contexts],
                    corpus_version=ans.provider_info.get("corpus_version"),
                    provider_info={
                        **ans.provider_info,
                        "reason": ans.reason,
                        "conflict": ans.conflict,
                        "warnings": ans.warnings,
                    },
                    latency_ms=ans.latency_ms,
                )
            )
    except Exception as exc:
        log.warning("audit_persist_failed", error=str(exc))


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


def _conversational(question: str, conv: str, pinfo: dict, t0: float) -> Answer:
    return Answer(
        question=question,
        text=conversation.conversational_reply(question, conv),
        semaforo=Semaforo.VERDE,
        abstained=False,
        reason="Mensaje conversacional (sin consulta técnica).",
        latency_ms=int((time.perf_counter() - t0) * 1000),
        provider_info=pinfo,
    )


def _retrieve(
    question: str, *, tenant: str, country: str, soil_type: str | None, region: str | None,
    pinfo: dict, t0: float,
) -> tuple[Answer | None, dict | None]:
    """Recupera y decide abstención. La sesión de BD se mantiene SOLO durante la consulta (no
    durante el LLM). Devuelve (respuesta_temprana, None) si abstiene, o (None, datos-de-generación)."""
    settings = get_settings()
    fc_parts: list[str] = []
    if soil_type:
        fc_parts.append(f"suelo {soil_type}")
    if region:
        fc_parts.append(f"región {region}")
    farm_context = ", ".join(fc_parts)
    retrieval_query = f"{question} {farm_context}".strip()

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
        _persist(ans, tenant)
        return ans, None

    query_vec = get_embedding_provider().embed_query(retrieval_query)
    with get_session(tenant=tenant) as session:
        candidates = hybrid_search(
            session, retrieval_query, query_vec, tenant=tenant, country=country
        )
    final = rerank_chunks(retrieval_query, candidates)  # fuera de la sesión (no la usa)

    if settings.rerank_provider.lower() == "none":
        evidence_score = candidates[0].score if candidates else float("-inf")
        evidence_threshold = settings.min_rrf_score
    else:
        evidence_score = final[0].score if final else float("-inf")
        evidence_threshold = settings.min_rerank_score
    pinfo["evidence_score"] = round(float(evidence_score), 5) if final else None

    if not final or (evidence_score < evidence_threshold):
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
        _persist(ans, tenant)
        return ans, None

    contexts = _build_contexts(final)
    gen = {
        "system": build_system_prompt(country),
        "user": build_user_prompt(question, final, farm_context=farm_context),
        "final": final,
        "contexts": contexts,
        "contexts_text": "\n\n".join(c.content for c in contexts),
        "country": country,
    }
    return None, gen


def _finalize(question: str, raw: str, gen: dict, *, pinfo: dict, t0: float, tenant: str) -> Answer:
    """Aplica guardarraíles y jueces sobre la respuesta generada y arma el Answer. No usa la
    sesión de BD durante los jueces (que llaman al LLM); persiste en una sesión propia y corta."""
    settings = get_settings()
    final = gen["final"]
    contexts = gen["contexts"]
    contexts_text = gen["contexts_text"]
    country = gen["country"]
    raw = raw.strip()

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
        _persist(ans, tenant)
        return ans

    raw = raw.replace(ABSTENTION_MARKER, "").strip()
    raw, follow_ups = _split_followups(raw)

    if settings.dose_guardrail:
        doses_ok, unsupported = guardrails.dose_product_grounded(raw, final)
        phi_ok, phi_unsupported = guardrails.phi_grounded(raw, contexts_text)
        banned = guardrails.banned_ingredients_in_answer(question + "\n" + raw, country)
        offlabel = guardrails.is_offlabel(raw, final)
        registro_required = guardrails.recommends_pesticide(raw)
        registro_ok = guardrails.ica_registro_ok(final)
        citation_ok, citation_issues = guardrails.citation_supports_claim(raw, final)
        conflicts = guardrails.dose_conflicts(final)
        warnings = guardrails.stale_data_warnings(final)
    else:
        doses_ok, unsupported = True, []
        phi_ok, phi_unsupported = True, []
        banned, offlabel = [], False
        registro_required, registro_ok = False, True
        citation_ok, citation_issues = True, []
        conflicts, warnings = [], []

    actionable = settings.dose_guardrail and guardrails.has_actionable_recommendation(raw)

    faithfulness: float | None = None
    judge_failed = False
    safety: guardrails.DoseSafety | None = None
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_faith = (
            ex.submit(guardrails.faithfulness_judge, question, raw, contexts_text)
            if settings.faithfulness_judge
            else None
        )
        fut_safety = (
            ex.submit(guardrails.dose_safety_judge, raw, contexts_text) if actionable else None
        )
        if fut_faith is not None:
            faithfulness, _ = fut_faith.result()
            judge_failed = faithfulness is None
        if fut_safety is not None:
            safety = fut_safety.result()

    language_ok = not guardrails.contains_foreign_script(raw)
    citations = _extract_citations(raw, final)
    cat_tox = guardrails.cited_categoria_toxicologica(final)
    semaforo, reason = guardrails.decide_semaforo(
        doses_ok=doses_ok,
        phi_ok=phi_ok,
        cat_tox=cat_tox,
        faithfulness=faithfulness,
        has_citations=bool(citations),
        judge_failed=judge_failed,
        safety=safety,
        safety_required=actionable,
        banned=banned,
        offlabel=offlabel,
        registro_ok=registro_ok,
        registro_required=registro_required and actionable,
        citation_ok=citation_ok,
        conflicts=conflicts,
        language_ok=language_ok,
    )
    if not doses_ok:
        reason += f" (dosis sin producto/fuente: {', '.join(unsupported)})"
    if not phi_ok:
        reason += f" (carencia sin fuente: {', '.join(phi_unsupported)})"
    if not citation_ok and citation_issues:
        reason += f" (citas: {'; '.join(citation_issues)})"

    if banned:
        raw = (
            "⛔ AVISO: tu consulta involucra un producto PROHIBIDO o RESTRINGIDO "
            f"({banned[0]}). No lo apliques; consulta alternativas registradas y vigentes "
            "ante el ICA con tu técnico.\n\n" + raw
        )

    ans = Answer(
        question=question,
        text=raw,
        semaforo=semaforo,
        abstained=False,
        faithfulness=faithfulness,
        reason=reason,
        citations=citations,
        contexts=contexts,
        follow_ups=follow_ups,
        conflict=conflicts,
        warnings=warnings,
        disclaimer=DISCLAIMER,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        provider_info=pinfo,
    )
    _persist(ans, tenant)
    log.info(
        "answered",
        tenant=tenant,
        semaforo=semaforo.value,
        faithfulness=faithfulness,
        n_citations=len(ans.citations),
        latency_ms=ans.latency_ms,
    )
    return ans


def answer(
    question: str,
    *,
    tenant: str | None = None,
    country: str | None = None,
    soil_type: str | None = None,
    region: str | None = None,
) -> Answer:
    settings = get_settings()
    tenant = tenant or settings.default_tenant
    country = country or settings.country
    t0 = time.perf_counter()
    pinfo = _provider_info()

    conv = conversation.classify_conversational(question)
    if conv is not None:
        return _conversational(question, conv, pinfo, t0)

    ckey = _cache_key(question, tenant, country, soil_type, region)
    if settings.cache_enabled:
        cached = _cache_get(ckey, settings.cache_ttl_seconds)
        if cached is not None:
            return cached.model_copy(
                update={
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "reason": ((cached.reason or "") + " · (cacheada)").strip(" ·"),
                }
            )

    early, gen = _retrieve(
        question, tenant=tenant, country=country, soil_type=soil_type, region=region,
        pinfo=pinfo, t0=t0,
    )
    if early is not None or gen is None:
        return early  # type: ignore[return-value]

    llm = get_llm_provider()
    raw = llm.complete(gen["system"], gen["user"])
    if guardrails.contains_foreign_script(raw):
        raw = llm.complete(gen["system"], gen["user"], temperature=0.0)
    ans = _finalize(question, raw, gen, pinfo=pinfo, t0=t0, tenant=tenant)
    if settings.cache_enabled:
        _cache_put(ckey, ans)
    return ans


def answer_stream(
    question: str,
    *,
    tenant: str | None = None,
    country: str | None = None,
    soil_type: str | None = None,
    region: str | None = None,
):
    """Versión en streaming de `answer()`. Genera tuplas ('delta', texto) mientras el LLM produce
    la respuesta, y al final ('final', Answer) con el semáforo, citas y guardarraíles aplicados.
    Las respuestas conversacionales, cacheadas y de abstención llegan directo como ('final', …)."""
    settings = get_settings()
    tenant = tenant or settings.default_tenant
    country = country or settings.country
    t0 = time.perf_counter()
    pinfo = _provider_info()

    conv = conversation.classify_conversational(question)
    if conv is not None:
        yield "final", _conversational(question, conv, pinfo, t0)
        return

    ckey = _cache_key(question, tenant, country, soil_type, region)
    if settings.cache_enabled:
        cached = _cache_get(ckey, settings.cache_ttl_seconds)
        if cached is not None:
            yield "final", cached.model_copy(
                update={
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "reason": ((cached.reason or "") + " · (cacheada)").strip(" ·"),
                }
            )
            return

    early, gen = _retrieve(
        question, tenant=tenant, country=country, soil_type=soil_type, region=region,
        pinfo=pinfo, t0=t0,
    )
    if early is not None or gen is None:
        yield "final", early
        return

    parts: list[str] = []
    for piece in get_llm_provider().stream(gen["system"], gen["user"]):
        parts.append(piece)
        yield "delta", piece
    yield "verifying", None
    ans = _finalize(question, "".join(parts), gen, pinfo=pinfo, t0=t0, tenant=tenant)
    if settings.cache_enabled:
        _cache_put(ckey, ans)
    yield "final", ans
