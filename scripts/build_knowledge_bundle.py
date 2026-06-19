"""Precalcula —UNA sola vez en el PC— una respuesta CITADA por cada clase de visión (madurez y
patología) usando el motor RAG, y la empaqueta en un JSON.

Para qué: la app móvil OFFLINE no puede correr el RAG (LLM + recuperación) en el teléfono. En su
lugar, el clasificador on-device (ONNX/TFLite) da la CLASE y la app muestra la entrada de este
bundle (manejo + citas). Todo el trabajo pesado se hace aquí, al construir; en el móvil es un simple
lookup, sin red ni LLM.

Uso:
    uv run python scripts/build_knowledge_bundle.py --out models/vision/knowledge_bundle.json

El bundle lleva su procedencia (prompt_version + corpus_version) para trazabilidad. Regenéralo cuando
cambie el corpus, el prompt o el catálogo de clases (src/avorag/vision/labels.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]


def _corpus_version() -> str:
    """Lee corpus_version del manifiesto si existe (trazabilidad)."""
    man = ROOT / "data" / "corpus_manifest.json"
    if man.exists():
        try:
            return str(json.loads(man.read_text("utf-8")).get("corpus_version", "desconocida"))
        except Exception:  # noqa: BLE001
            return "desconocida"
    return "desconocida"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Precalcula el conocimiento citado por clase (uso offline)."
    )
    ap.add_argument(
        "--out", type=Path, default=ROOT / "models" / "vision" / "knowledge_bundle.json"
    )
    ap.add_argument("--tenant", default=None, help="Tenant para el RAG (def: el de la config).")
    args = ap.parse_args()

    from avorag.rag import answer
    from avorag.rag.prompt import PROMPT_VERSION
    from avorag.vision.labels import LABELS

    entries: dict[str, dict] = {}
    for key, info in LABELS.items():
        print(f"  · {key} …", flush=True)
        ans = answer(info.question, tenant=args.tenant)
        entries[key] = {
            "label_es": info.es,
            "kind": info.kind.value,
            "pregunta": info.question,
            "semaforo": str(ans.semaforo),
            "abstenido": ans.abstained,
            "manejo": ans.text,
            "citas": [
                {
                    "fuente": c.fuente,
                    "pagina": c.pagina,
                    "url": c.url,
                    "nivel_autoridad": c.nivel_autoridad,
                }
                for c in ans.citations
            ],
            "disclaimer": ans.disclaimer,
        }

    bundle = {
        "schema": 1,
        "prompt_version": PROMPT_VERSION,
        "corpus_version": _corpus_version(),
        "nota": (
            "Conocimiento precalculado por el RAG para uso OFFLINE en la app móvil. El clasificador "
            "on-device da la clase; la app muestra esta entrada (manejo + citas). Es apoyo citado, "
            "NO sustituye al agrónomo; verifica la etiqueta y el registro ICA vigentes antes de aplicar."
        ),
        "clases": entries,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), "utf-8")
    kb = args.out.stat().st_size / 1024
    citadas = sum(1 for e in entries.values() if e["citas"])
    print(f"\n✓ Bundle: {args.out} ({len(entries)} clases, {citadas} con citas, {kb:.0f} KB)")
    print(
        "  En la app: clasificador on-device → clase → muestra clases[clase].manejo + citas (offline)."
    )


if __name__ == "__main__":
    main()
