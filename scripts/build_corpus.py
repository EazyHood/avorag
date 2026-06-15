"""Reconstruye el corpus de AvoRAG desde las fuentes públicas oficiales.

Los PDF NO se versionan en git (licencia + peso), así que los números del caso de estudio
no serían reproducibles por un tercero. Este script cierra esa brecha: descarga lo que es
descargable por HTTP, indica con precisión lo que requiere bajada manual, y opcionalmente
ingiere todo lo presente en `data/corpus/`.

Uso:
    python scripts/build_corpus.py                 # descarga los 'auto' y lista los 'manual'
    python scripts/build_corpus.py --ingest        # además ingiere todo lo que esté presente
    python scripts/build_corpus.py --force         # re-descarga aunque el archivo ya exista

Requiere las deps del proyecto (httpx ya es dependencia). Las fuentes y licencias están
documentadas en `docs/SOURCES.md` y en `data/corpus_manifest.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "corpus_manifest.json"
CORPUS_DIR = ROOT / "data" / "corpus"


def _download(url: str, dest: Path) -> tuple[bool, str]:
    """Descarga `url` a `dest`. Devuelve (ok, mensaje)."""
    try:
        headers = {"User-Agent": "AvoRAG-corpus-builder/1.0 (+https://github.com/EazyHood/avorag)"}
        with httpx.Client(follow_redirects=True, timeout=120.0, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        kb = len(resp.content) / 1024
        return True, f"{kb:,.0f} KB"
    except Exception as exc:  # noqa: BLE001 — queremos reportar cualquier fallo de red sin abortar
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingest", action="store_true", help="Ingiere lo descargado tras bajar.")
    parser.add_argument(
        "--force", action="store_true", help="Re-descarga aunque exista el archivo."
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    docs = manifest["documents"]
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Corpus version: {manifest.get('corpus_version')}  ·  {len(docs)} documentos\n")

    present: list[dict] = []
    manual_pending: list[dict] = []

    for doc in docs:
        dest = CORPUS_DIR / doc["filename"]
        tag = f"[{doc['download']:6}] {doc['filename']}"

        if dest.exists() and not args.force:
            print(f"OK   {tag}  (ya presente)")
            present.append(doc)
            continue

        if doc["download"] == "auto":
            ok, msg = _download(doc["url"], dest)
            if ok:
                print(f"BAJA {tag}  ({msg})")
                present.append(doc)
            else:
                print(f"FALLO {tag}  -> {msg}")
                print(f"      Descárgalo a mano desde: {doc['url']}")
        else:  # manual
            print(f"MANUAL {tag}")
            print(f"      {doc['note']}")
            print(f"      Enlace: {doc['url']}")
            manual_pending.append(doc)

    print(
        f"\nPresentes para ingerir: {len(present)}  ·  Manuales pendientes: {len(manual_pending)}"
    )

    if manual_pending:
        print(
            "\nPendientes de bajada manual (abre el enlace, guarda el archivo con el nombre indicado):"
        )
        for d in manual_pending:
            print(f"  - {d['filename']}  <-  {d['url']}")

    if not args.ingest:
        print("\nPara ingerir lo presente: vuelve a ejecutar con --ingest")
        return 0

    # --- Ingesta ---
    from avorag.ingestion import DocumentMeta, ingest_document
    from avorag.logging import configure_logging

    configure_logging()
    print("\n--- Ingiriendo ---")
    total_chunks = 0
    for doc in present:
        dest = CORPUS_DIR / doc["filename"]
        if not dest.exists():
            continue
        meta = DocumentMeta(
            fuente=doc["fuente"],
            licencia=doc["licencia"],
            nivel_autoridad=doc["autoridad"],
            pais=doc["pais"],
            cultivo="hass",
            url=doc.get("url"),
            doi=doc.get("doi"),
        )
        res = ingest_document(dest, meta, force=args.force)
        if res.skipped:
            print(f"  omitido {doc['filename']}: {res.reason}")
        else:
            total_chunks += res.n_chunks
            print(f"  + {res.n_chunks:4} chunks  {doc['filename']}")
    print(f"\nTotal: {total_chunks} chunks ingeridos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
