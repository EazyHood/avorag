"""Pipeline de ingesta: load → hash (idempotencia) → chunk → contextualizar →
embeber → persistir. Devuelve un resumen."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from avorag.config import get_settings
from avorag.db import Chunk, Document, get_session
from avorag.ingestion.chunking import chunk_text
from avorag.ingestion.contextual import build_doc_summary, contextualize_chunk
from avorag.ingestion.loaders import load_document, sha256_file
from avorag.ingestion.metadata import ChunkMetadata, DocumentMeta, extract_chunk_fields
from avorag.logging import get_logger
from avorag.providers import get_embedding_provider

log = get_logger(__name__)


@dataclass
class IngestResult:
    document_id: str | None
    fuente: str
    n_chunks: int
    skipped: bool
    reason: str = ""
    contextual_failures: int = 0


def ingest_document(
    path: str | Path,
    meta: DocumentMeta,
    *,
    tenant: str | None = None,
    contextual: bool = True,
    force: bool = False,
) -> IngestResult:
    settings = get_settings()
    tenant = tenant or settings.default_tenant
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    digest = sha256_file(path)

    with get_session() as session:
        existing = session.scalar(
            select(Document).where(Document.sha256 == digest, Document.tenant == tenant)
        )
        if existing and not force:
            log.info("ingest_skip_duplicate", fuente=meta.fuente, sha256=digest[:12])
            return IngestResult(
                document_id=str(existing.id),
                fuente=meta.fuente,
                n_chunks=0,
                skipped=True,
                reason="documento ya ingerido (mismo sha256); usa --force para re-ingerir",
            )
        if existing and force:
            session.delete(existing)
            session.flush()

        pages = load_document(path)
        full_text = "\n".join(p.text for p in pages)
        doc_summary = build_doc_summary(full_text)

        document = Document(
            tenant=tenant,
            fuente=meta.fuente,
            titulo=meta.titulo,
            pais=meta.pais,
            cultivo=meta.cultivo,
            licencia=meta.licencia,
            nivel_autoridad=meta.nivel_autoridad,
            fecha_publicacion=meta.fecha_publicacion,
            sha256=digest,
            raw_path=str(path.resolve()),
            corpus_version=meta.corpus_version,
            url=meta.url,
            doi=meta.doi,
        )
        session.add(document)
        session.flush()  # asigna document.id

        embedder = get_embedding_provider()

        ordinal = 0
        contextual_failures = 0
        all_chunks: list[Chunk] = []
        texts_to_embed: list[str] = []
        for page in pages:
            for tc in chunk_text(page.text, page=page.page_number, start_ordinal=ordinal):
                ordinal = tc.ordinal + 1
                ctx = contextualize_chunk(tc.text, doc_summary, meta.fuente) if contextual else ""
                if contextual and not ctx:
                    contextual_failures += 1
                fields = extract_chunk_fields(tc.text)
                cmeta = ChunkMetadata(
                    pais=meta.pais,
                    cultivo=meta.cultivo,
                    fuente=meta.fuente,
                    pagina=tc.page,
                    fecha_publicacion=meta.fecha_publicacion,
                    nivel_autoridad=meta.nivel_autoridad,
                    licencia_uso=meta.licencia,
                    url=meta.url,
                    doi=meta.doi,
                    categoria_toxicologica=fields["categoria_toxicologica"],
                    registro_ica=fields["registro_ica"],
                    tema=fields["tema"],
                    plaga_objetivo=fields["plaga_objetivo"],
                )
                chunk = Chunk(
                    document_id=document.id,
                    tenant=tenant,
                    ordinal=tc.ordinal,
                    pagina=tc.page,
                    content=tc.text,
                    context=ctx or None,
                    meta=cmeta.as_dict(),
                    embedding=[0.0] * embedder.dim,  # placeholder; se llena abajo
                )
                all_chunks.append(chunk)
                texts_to_embed.append(((ctx + "\n") if ctx else "") + tc.text)

        # Embeber en lote.
        vectors = embedder.embed_documents(texts_to_embed)
        for chunk, vec in zip(all_chunks, vectors, strict=True):
            chunk.embedding = vec
            session.add(chunk)

        log.info(
            "ingest_done",
            fuente=meta.fuente,
            document_id=str(document.id),
            n_chunks=len(all_chunks),
            contextual=contextual,
            contextual_failures=contextual_failures,
        )
        return IngestResult(
            document_id=str(document.id),
            fuente=meta.fuente,
            n_chunks=len(all_chunks),
            skipped=False,
            contextual_failures=contextual_failures,
        )
