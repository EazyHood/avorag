"""Orquestador RAG: la función `answer()` de principio a fin, con auditoría."""

from __future__ import annotations

import hashlib
import json
import re
import threading
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
# Respuestas "fijadas": preguntas por defecto precalculadas. No expiran y se sirven al instante.
_PINNED: dict[str, Answer] = {}
# Protege las cachés: el hilo de precálculo escribe mientras las peticiones HTTP leen.
_CACHE_LOCK = threading.Lock()


def _cache_key(
    question: str,
    tenant: str,
    country: str,
    soil_type: str | None,
    region: str | None,
) -> str:
    raw = "|".join([question.strip().lower(), tenant, country, soil_type or "", region or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def pin_answer(question: str, ans: Answer) -> None:
    """Fija la respuesta de una pregunta por defecto (clave con tenant/país por defecto, sin
    suelo/región) para servirla al instante. La usa el precálculo de arranque."""
    s = get_settings()
    with _CACHE_LOCK:
        _PINNED[_cache_key(question, s.default_tenant, s.country, None, None)] = ans


def _cache_get(key: str, ttl: int) -> Answer | None:
    with _CACHE_LOCK:
        pinned = _PINNED.get(key)
        if pinned is not None:
            return pinned
        item = _RESPONSE_CACHE.get(key)
        if item is None:
            return None
        if (time.time() - item[0]) < ttl:
            return item[1]
        _RESPONSE_CACHE.pop(key, None)  # expirada: limpieza proactiva
        return None


def _cache_put(key: str, ans: Answer) -> None:
    with _CACHE_LOCK:
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


_QUOTE_NOISE = re.compile(r"<br\s*/?>|\|", re.IGNORECASE)  # etiquetas y barras de tabla markdown
_QUOTE_SEP = re.compile(r"[-:]{3,}")  # separadores de tabla |---|
_QUOTE_FUENTE = re.compile(r"Fuente:\s*Elaboraci[oó]n propia\.?", re.IGNORECASE)
_QUOTE_LEADING_NUM = re.compile(r"^(?:\d{1,4}\b[\s.]*)+")  # números de página repetidos al inicio
_QUOTE_MULTISPACE = re.compile(r"\s+")


def _clean_for_quote(content: str) -> str:
    """Limpia el fragmento crudo para una cita legible: quita sintaxis de tabla (|, <br>, ---),
    el ruido de 'Fuente: Elaboración propia', los números de página sueltos y colapsa espacios."""
    t = _QUOTE_NOISE.sub(" ", content)
    t = _QUOTE_SEP.sub(" ", t)
    t = _QUOTE_FUENTE.sub(" ", t)
    t = re.sub(r"([a-záéíóúñ])-\s+([a-záéíóúñ])", r"\1\2", t, flags=re.IGNORECASE)  # une corte de línea
    t = _QUOTE_MULTISPACE.sub(" ", t).strip()
    t = _QUOTE_LEADING_NUM.sub("", t).strip()
    return t


def _targeted_quote(content: str) -> str:
    """Cita legible centrada en la primera dosis del fragmento; si no hay dosis, usa el inicio.
    Recorta a límites de palabra y limpia la sintaxis de tabla/ruido del chunk."""
    text = _clean_for_quote(content)
    if not text:
        return ""
    m = _FIRST_DOSE_RE.search(text)
    if m:
        start = max(0, m.start() - _QUOTE_RADIUS)
        end = min(len(text), m.end() + _QUOTE_RADIUS)
        if start > 0:  # no cortar a media palabra
            start = text.find(" ", start - 1) + 1 or start
        if end < len(text):
            cut = text.rfind(" ", m.end(), end)
            end = cut if cut > m.end() else end
        snippet = text[start:end].strip()
        return f"{'…' if start > 0 else ''}{snippet}{'…' if end < len(text) else ''}"
    snippet = text[:200].rsplit(" ", 1)[0] if len(text) > 200 else text
    return snippet + ("…" if len(text) > 200 else "")


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


_RETRY_SYSTEM_SUFFIX = (
    "\n\nAVISO: tu intento anterior fue inválido (cambió de idioma o no respondió). "
    "Ahora responde la PREGUNTA de forma directa y completa, en ESPAÑOL en cada palabra "
    "(prohibido chino u otros alfabetos), citando los fragmentos con [n]. Escribe PRIMERO la "
    "respuesta y solo al final la línea SEGUIMIENTO con 2 preguntas."
)

_FALLBACK_TEXT = (
    "No pude redactar una respuesta clara para esta pregunta en este momento. Intenta "
    "reformularla o consulta a tu técnico. Abajo tienes los fragmentos de fuente recuperados."
)


def _strip_latex(text: str) -> str:
    """Convierte la notación LaTeX que a veces emite el modelo a texto plano legible (la UI no
    renderiza matemáticas): quita \\[ \\] \\( \\) y $, \\text{x}->x, \\times->×, \\frac{a}{b}->(a/b)."""
    t = re.sub(r"\\[\[\]()]", "", text)
    t = re.sub(r"\\text\s*\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\\frac\s*\{([^}]*)\}\s*\{([^}]*)\}", r"(\1/\2)", t)
    t = t.replace("\\times", "×").replace("\\cdot", "·").replace("\\approx", "≈")
    t = re.sub(r"\\,", " ", t)
    t = re.sub(r"(?<!\d)\$|\$(?!\d)", "", t)  # $ delimitadores (no precios)
    return re.sub(r"[ \t]{2,}", " ", t)


def _is_abstention(body: str) -> bool:
    """True SOLO si el cuerpo es el marcador NO_LO_SE prácticamente solo. OJO: el 3B a veces
    antepone NO_LO_SE como tic y luego da una respuesta válida; en ese caso NO es abstención —
    el marcador se quita aparte y se conserva la respuesta. Solo abstiene si no hay nada más."""
    b = body.strip()
    if ABSTENTION_MARKER not in b:
        return False
    return len(b.replace(ABSTENTION_MARKER, "").strip()) <= 5


# Preámbulos/colofones de "meta-charla" que los modelos pequeños añaden en vez de ir al grano.
_META_PATTERNS = [
    re.compile(r"^\s*Para responder a (?:esta solicitud|esta pregunta|tu pregunta)[^.\n]*[.\n]\s*", re.IGNORECASE),
    re.compile(r"^\s*Sin embargo,?\s*bas[áa]ndome[^.\n]*[.\n]\s*", re.IGNORECASE),
    re.compile(r"^\s*Bas[áa]ndome en (?:el contenido de )?los fragmentos[^.\n]*[.\n]\s*", re.IGNORECASE),
    re.compile(r"\s*Para (?:obtener|dar) una respuesta m[áa]s (?:completa|precisa)[^.]*\.?\s*$", re.IGNORECASE),
    re.compile(r"\s*Estos son (?:solo )?algunos[^.]*\.?\s*$", re.IGNORECASE),
]


def _strip_meta(text: str) -> str:
    """Quita preámbulos/colofones sobre la tarea o los fragmentos, sin vaciar la respuesta."""
    out = text.strip()
    for _ in range(4):
        before = out
        for pat in _META_PATTERNS:
            cand = pat.sub("", out).strip()
            if cand != out and len(cand) >= 30:
                out = cand
        if out == before:
            break
    return out or text.strip()


_PROMPT_ECHO_RE = re.compile(r"PREGUNTA DEL PRODUCTOR|FRAGMENTOS \(numerados", re.IGNORECASE)


def _generation_problem(body: str) -> str | None:
    """Devuelve el motivo si la respuesta generada es inservible: idioma ajeno, eco del prompt
    (modelos pequeños a veces repiten la plantilla en vez de responder) o cuerpo vacío."""
    if guardrails.contains_foreign_script(body):
        return "idioma"
    if _PROMPT_ECHO_RE.search(body):
        return "eco"
    if len(body.strip()) < 20:
        return "vacia"
    return None


def _raw_is_bad(raw: str) -> bool:
    """True si la generación está rota (idioma ajeno o cuerpo vacío). Una abstención legítima
    NO se considera rota: no hay que regenerarla, hay que mostrar el mensaje de abstención."""
    body, _ = _split_followups(raw.strip())
    if _is_abstention(body):
        return False
    return _generation_problem(body.replace(ABSTENTION_MARKER, "").strip()) is not None


def _regenerate(gen: dict) -> str:
    """Reintenta la generación con un prompt más firme; si vuelve a fallar, texto de reserva."""
    raw = get_llm_provider().complete(
        gen["system"] + _RETRY_SYSTEM_SUFFIX, gen["user"], temperature=0.35
    )
    return raw if not _raw_is_bad(raw) else _FALLBACK_TEXT


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
    body, follow_ups = _split_followups(raw)

    if _is_abstention(body):
        ans = _abstention(
            question,
            AbstentionType.OUT_OF_CONTENT,
            text="No encontré suficiente respaldo sobre eso en mis fuentes verificadas (centradas "
            "en el cultivo del aguacate Hass). Prueba a reformular la pregunta de forma más "
            "concreta o consúltalo con tu técnico agrónomo.",
            reason="El modelo se abstuvo (sin respaldo en el contexto).",
            pinfo=pinfo,
            t0=t0,
            contexts=contexts,
        )
        _persist(ans, tenant)
        return ans

    raw = _strip_latex(_strip_meta(body.replace(ABSTENTION_MARKER, "").strip()))

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

    # Autorización por país de DESTINO de exportación (EXPORT_MARKET): un activo no aprobado en el
    # destino → ROJO (evita rechazo por LMR); un activo con LMR estricto → aviso. Apagado si no hay
    # mercado configurado. Mira el DESTINO, complementario a 'banned' que mira el registro ICA local.
    from avorag.rag import destino

    destino_no_auth = destino.unauthorized_for_destination(question + "\n" + raw)
    destino_lmr = destino.strict_lmr_for_destination(raw)
    forbidden = banned + destino_no_auth
    if destino_lmr:
        warnings = [*warnings, *destino_lmr]

    # El juez de seguridad, la categoría toxicológica y el registro ICA SOLO aplican si la respuesta
    # recomienda un PLAGUICIDA QUÍMICO con dosis. Antes se disparaban con cualquier "aplicar" (incluido
    # control biológico/cultural) o por la metadata de un fragmento recuperado -> falsos ROJOS.
    chem_pesticide = settings.dose_guardrail and guardrails.recommends_pesticide(raw)

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
            ex.submit(guardrails.dose_safety_judge, raw, contexts_text) if chem_pesticide else None
        )
        if fut_faith is not None:
            faithfulness, _ = fut_faith.result()
            judge_failed = faithfulness is None
        if fut_safety is not None:
            safety = fut_safety.result()

    language_ok = not guardrails.contains_foreign_script(raw)
    citations = _extract_citations(raw, final)
    # La categoría toxicológica solo penaliza si la respuesta recomienda un plaguicida químico,
    # no por la metadata de un fragmento recuperado que no se está recomendando.
    cat_tox = guardrails.cited_categoria_toxicologica(final) if chem_pesticide else set()
    # La trazabilidad dosis-producto y la carencia (PHI) solo fuerzan ROJO si la respuesta
    # recomienda un plaguicida químico; las dosis de fertilizante/riego/nutrición (kg de N,
    # litros de agua, niveles foliares, % de saturación) NO son dosis fitosanitarias.
    semaforo, reason = guardrails.decide_semaforo(
        doses_ok=(doses_ok or not chem_pesticide),
        phi_ok=(phi_ok or not chem_pesticide),
        cat_tox=cat_tox,
        faithfulness=faithfulness,
        has_citations=bool(citations),
        judge_failed=judge_failed,
        safety=safety,
        safety_required=chem_pesticide,
        banned=forbidden,
        offlabel=offlabel,
        registro_ok=registro_ok,
        registro_required=registro_required and chem_pesticide,
        citation_ok=citation_ok,
        conflicts=conflicts,
        language_ok=language_ok,
    )
    if chem_pesticide and not doses_ok:
        reason += f" (dosis sin producto/fuente: {', '.join(unsupported)})"
    if chem_pesticide and not phi_ok:
        reason += f" (carencia sin fuente: {', '.join(phi_unsupported)})"
    if not citation_ok and citation_issues:
        reason += f" (citas: {'; '.join(citation_issues)})"

    if forbidden:
        # Producto prohibido/restringido (ICA) o NO autorizado en el mercado de destino: la respuesta
        # es la advertencia, directa y limpia. Se descarta el cuerpo del modelo (suele divagar) y el
        # ruido de dosis/avisos (irrelevante si no debe usarse).
        nombres = " ni ".join(s.split(" (")[0] for s in forbidden[:2])
        destino_txt = (
            f" No está autorizado en tu mercado de destino ({destino.market_name()})."
            if destino_no_auth
            else ""
        )
        raw = (
            f"⛔ No, no debes usar {nombres} en aguacate Hass de exportación.{destino_txt}\n\n"
            "Es un producto prohibido/restringido o no autorizado en el destino. Consulta con tu "
            "técnico alternativas registradas y vigentes ante el ICA, y verifica el límite máximo de "
            "residuos (LMR) del país de destino antes de cualquier aplicación."
        )
        conflicts, warnings, citations, follow_ups = [], [], [], []

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

    raw = get_llm_provider().complete(gen["system"], gen["user"])
    if _raw_is_bad(raw):
        raw = _regenerate(gen)
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
    raw = "".join(parts)
    body, _ = _split_followups(raw.strip())

    if _is_abstention(body):
        # El modelo se abstuvo (a veces con SEGUIMIENTO pegado): limpia el texto crudo y deja
        # que _finalize muestre el mensaje de abstención. No hay que verificar ni regenerar.
        yield "reset", None
        ans = _finalize(question, raw, gen, pinfo=pinfo, t0=t0, tenant=tenant)
        yield "final", ans
        return

    if _raw_is_bad(raw):
        raw = _regenerate(gen)
        regen_body, _ = _split_followups(raw.strip())
        yield "reset", None
        if _is_abstention(regen_body):
            ans = _finalize(question, raw, gen, pinfo=pinfo, t0=t0, tenant=tenant)
            yield "final", ans
            return
        new_body = regen_body.replace(ABSTENTION_MARKER, "").strip()
        yield "delta", (new_body if new_body else raw)

    yield "verifying", None
    ans = _finalize(question, raw, gen, pinfo=pinfo, t0=t0, tenant=tenant)
    if settings.cache_enabled:
        _cache_put(ckey, ans)
    yield "final", ans
