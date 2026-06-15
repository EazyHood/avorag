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

# --- Caché de respuestas en memoria (latencia) -----------------------------------
# Las preguntas repetidas (caso WhatsApp/FAQ de campo) responden al instante en vez de
# repetir embed + búsqueda híbrida + reranker (CPU) + LLM. TTL y on/off en config.
# Es por-proceso (no compartida entre workers); para multi-worker usar Redis más adelante.
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
    """Versión del corpus (del manifiesto), para que cada respuesta sea trazable a sus datos."""
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
                    quote=(c.content[:200] + "…") if len(c.content) > 200 else c.content,
                )
            )
    return citations


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
    """Devuelve el texto en claro, o su hash si la política minimiza datos (Habeas Data)."""
    if store_text:
        return value
    return f"<sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}>"


def _persist(session, ans: Answer, tenant: str) -> None:
    """Escribe el registro de auditoría de forma TOLERANTE A FALLO: un error de escritura NO
    debe tumbar una respuesta ya calculada (#34). Usa un SAVEPOINT para que el fallo no
    contamine la transacción de lectura, y respeta audit_store_text (minimización de datos)."""
    settings = get_settings()
    if not settings.audit_enabled:
        return
    store_text = settings.audit_store_text
    try:
        with session.begin_nested():  # savepoint
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
                    # La auditoría guarda también la JUSTIFICACIÓN (por qué ese semáforo): clave
                    # para reconstruir incidentes y para due-diligence B2B.
                    provider_info={
                        **ans.provider_info,
                        "reason": ans.reason,
                        "conflict": ans.conflict,
                        "warnings": ans.warnings,
                    },
                    latency_ms=ans.latency_ms,
                )
            )
    except Exception as exc:  # la auditoría nunca debe romper la respuesta al usuario
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

    # Caché: si esta misma pregunta (mismo tenant/país/suelo/región) ya se respondió y sigue
    # fresca, se devuelve al instante. Reemite la latencia real (≈0 ms) y marca "(cacheada)".
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

    # Contexto de la finca: el suelo y la región cambian la recomendación (sobre todo
    # de fertilización: en arenoso el N se lixivia más; en arcilloso cuidar el drenaje).
    fc_parts: list[str] = []
    if soil_type:
        fc_parts.append(f"suelo {soil_type}")
    if region:
        fc_parts.append(f"región {region}")
    farm_context = ", ".join(fc_parts)
    # La consulta de recuperación se enriquece con el contexto para traer fragmentos relevantes.
    retrieval_query = f"{question} {farm_context}".strip()

    with get_session(tenant=tenant) as session:
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

        query_vec = get_embedding_provider().embed_query(retrieval_query)
        candidates = hybrid_search(
            session, retrieval_query, query_vec, tenant=tenant, country=country
        )
        final = rerank_chunks(retrieval_query, candidates)

        # Señal de evidencia y umbral según el reranker: con reranker activo, el score del
        # cross-encoder/Cohere es discriminante (negativo = irrelevante); con 'none' usamos el
        # score RRF del candidato mejor rankeado (señal débil; ver config). La abstención ocurre
        # AQUÍ, antes de gastar el LLM de generación.
        if settings.rerank_provider.lower() == "none":
            evidence_score = candidates[0].score if candidates else float("-inf")
            evidence_threshold = settings.min_rrf_score
        else:
            evidence_score = final[0].score if final else float("-inf")
            evidence_threshold = settings.min_rerank_score
        pinfo["evidence_score"] = round(float(evidence_score), 5) if final else None

        # Sin evidencia suficiente → abstención honesta, etiquetada según el dominio.
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
            _persist(session, ans, tenant)
            return ans

        system = build_system_prompt(country)
        user = build_user_prompt(question, final, farm_context=farm_context)
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
        # Separa las preguntas de seguimiento del cuerpo de la respuesta.
        raw, follow_ups = _split_followups(raw)

        # Guardarraíles deterministas (atados al fragmento de origen, no al texto plano).
        if settings.dose_guardrail:
            doses_ok, unsupported = guardrails.dose_product_grounded(raw, final)
            phi_ok, phi_unsupported = guardrails.phi_grounded(raw, contexts_text)
            # La denylist mira la PREGUNTA y la respuesta: si el productor pregunta por un
            # producto prohibido/restringido, el sistema debe advertirlo (ROJO) aunque el modelo
            # no lo repita en su respuesta (hallazgo de la verificación en vivo).
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

        # Juez de asociación producto–plaga–dosis–carencia: SOLO si la respuesta es accionable
        # (trae dosis/carencia/aplicación). Evita latencia en respuestas generales.
        actionable = settings.dose_guardrail and guardrails.has_actionable_recommendation(raw)

        # Los dos jueces LLM (fidelidad y seguridad de dosis) son I/O-bound: se lanzan en
        # paralelo para no SUMAR sus latencias (#31).
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
        )
        if not doses_ok:
            reason += f" (dosis sin producto/fuente: {', '.join(unsupported)})"
        if not phi_ok:
            reason += f" (carencia sin fuente: {', '.join(phi_unsupported)})"
        if not citation_ok and citation_issues:
            reason += f" (citas: {'; '.join(citation_issues)})"

        # Ante un producto prohibido/restringido, antepone un AVISO explícito al cuerpo de la
        # respuesta (no basta con el campo `reason`): el productor debe verlo de inmediato.
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
        _persist(session, ans, tenant)
        log.info(
            "answered",
            tenant=tenant,
            semaforo=semaforo.value,
            faithfulness=faithfulness,
            n_citations=len(ans.citations),
            latency_ms=ans.latency_ms,
        )
        if settings.cache_enabled:
            _cache_put(ckey, ans)
        return ans
