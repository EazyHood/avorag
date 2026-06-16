"""Soberanía de datos verificable: EXPORTA o BORRA todos los datos de un tenant (exportadora).

Convierte la promesa "tus datos son tuyos y te los llevas cuando quieras" en un comando que el
propio cliente puede correr y comprobar. Resuelve las objeciones del comprador:
  - #3 «¿quién ve mis datos? no firmo nada que te deje quedártelos» → puede exportarlos y borrarlos él.
  - #6 «¿y si desapareces? quedo atrapado» → sus datos salen en formato abierto (JSONL) y se purgan.

Uso:
    uv run python scripts/tenant_data.py export --tenant finca1 --out ./export_finca1
    uv run python scripts/tenant_data.py purge  --tenant finca1 --yes

Notas de honestidad:
  - EXPORT vuelca el corpus del tenant (documentos + fragmentos: contenido y metadatos citables) y su
    auditoría de consultas (`queries`). NO incluye los vectores de embedding (son derivados,
    reconstruibles; pesan y no son "datos del cliente"). Todo en JSONL abierto, sin lock-in.
  - PURGE borra documentos (los fragmentos caen por ON DELETE CASCADE) y la auditoría del tenant.
    Es IRREVERSIBLE; exige --yes. Hace un export automático antes de borrar (salvo --no-backup).
  - Requiere acceso a la BD (DATABASE_URL). El aislamiento por tenant (RLS) ya impide cruzar datos
    entre exportadoras; este script solo toca el tenant indicado.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _jsonl(rows: list[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=_default) + "\n")
    return len(rows)


def _default(o: Any) -> str:
    if isinstance(o, datetime | date):
        return o.isoformat()
    return str(o)


def _export(tenant: str, out: Path) -> dict[str, int]:
    from sqlalchemy import select

    from avorag.db import get_session
    from avorag.db.models import Chunk, Document, QueryLog

    counts: dict[str, int] = {}
    with get_session(tenant=tenant) as s:
        docs = list(s.scalars(select(Document).where(Document.tenant == tenant)))
        counts["documentos"] = _jsonl(
            [
                {
                    "id": str(d.id), "fuente": d.fuente, "titulo": d.titulo, "pais": d.pais,
                    "cultivo": d.cultivo, "licencia": d.licencia, "nivel_autoridad": d.nivel_autoridad,
                    "fecha_publicacion": d.fecha_publicacion, "vigente": d.vigente, "sha256": d.sha256,
                    "url": d.url, "doi": d.doi, "corpus_version": d.corpus_version,
                    "created_at": d.created_at,
                }
                for d in docs
            ],
            out / "documentos.jsonl",
        )
        chunks = list(s.scalars(select(Chunk).where(Chunk.tenant == tenant)))
        counts["fragmentos"] = _jsonl(
            [
                {
                    "id": str(c.id), "document_id": str(c.document_id), "ordinal": c.ordinal,
                    "pagina": c.pagina, "content": c.content, "context": c.context, "meta": c.meta,
                }
                for c in chunks  # sin 'embedding': derivado, reconstruible
            ],
            out / "fragmentos.jsonl",
        )
        queries = list(s.scalars(select(QueryLog).where(QueryLog.tenant == tenant)))
        counts["consultas"] = _jsonl(
            [
                {
                    "id": str(q.id), "created_at": q.created_at, "question": q.question,
                    "answer": q.answer, "semaforo": q.semaforo, "abstained": q.abstained,
                    "faithfulness": q.faithfulness, "citations": q.citations,
                    "corpus_version": q.corpus_version, "latency_ms": q.latency_ms,
                }
                for q in queries
            ],
            out / "consultas.jsonl",
        )
    (out / "MANIFIESTO.json").write_text(
        json.dumps(
            {"tenant": tenant, "exportado": datetime.now().isoformat(), "conteos": counts,
             "nota": "Datos del tenant en JSONL abierto. Los embeddings no se incluyen (derivados)."},
            ensure_ascii=False, indent=2,
        ),
        "utf-8",
    )
    return counts


def _purge(tenant: str) -> dict[str, int]:
    from sqlalchemy import delete, func, select

    from avorag.db import get_session
    from avorag.db.models import Chunk, Document, QueryLog

    counts: dict[str, int] = {}
    with get_session(tenant=tenant) as s:
        counts["fragmentos"] = s.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.tenant == tenant)
        ) or 0
        counts["documentos"] = s.execute(
            delete(Document).where(Document.tenant == tenant)
        ).rowcount  # los fragmentos caen por ON DELETE CASCADE
        counts["consultas"] = s.execute(
            delete(QueryLog).where(QueryLog.tenant == tenant)
        ).rowcount
        s.commit()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Exporta o borra los datos de un tenant (soberanía de datos).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("export", help="Vuelca los datos del tenant a JSONL abierto.")
    pe.add_argument("--tenant", required=True)
    pe.add_argument("--out", type=Path, required=True)
    pp = sub.add_parser("purge", help="Borra TODOS los datos del tenant (irreversible).")
    pp.add_argument("--tenant", required=True)
    pp.add_argument("--yes", action="store_true", help="Confirma el borrado (sin esto, no borra).")
    pp.add_argument("--no-backup", action="store_true", help="No exportar antes de borrar.")
    args = ap.parse_args()

    from avorag.logging import configure_logging

    configure_logging()

    if args.cmd == "export":
        counts = _export(args.tenant, args.out)
        print(f"✓ Exportado tenant «{args.tenant}» a {args.out}: " +
              ", ".join(f"{v} {k}" for k, v in counts.items()))
        return

    # purge
    if not args.yes:
        raise SystemExit("Borrado IRREVERSIBLE. Añade --yes para confirmar.")
    if not args.no_backup:
        backup = Path(f"backup_{args.tenant}_{date.today().isoformat()}")
        _export(args.tenant, backup)
        print(f"  (respaldo previo en {backup})")
    counts = _purge(args.tenant)
    print(f"✓ Borrado tenant «{args.tenant}»: " +
          ", ".join(f"{v} {k}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
