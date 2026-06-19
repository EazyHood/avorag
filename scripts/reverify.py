"""Re-corre un subconjunto de la simulación (por semáforo) con el código ACTUAL (post-parche) y
compara el semáforo viejo vs el nuevo. Sirve para verificar que un parche cambió lo esperado.

Uso:  LLM_MODEL=qwen2.5:3b-instruct CACHE_ENABLED=false uv run python scripts/reverify.py rojo
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from avorag.rag import pipeline as P

_ROOT = Path(__file__).resolve().parents[1]
_IN = _ROOT / "data" / "eval" / "sweep_results.jsonl"


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "rojo"
    rows = [
        json.loads(line) for line in _IN.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    sel = [r for r in rows if r.get("semaforo") == target and "error" not in r]
    print(f"Re-corriendo {len(sel)} preguntas que antes fueron '{target}'...", flush=True)
    out = _ROOT / "data" / "eval" / f"reverify_{target}.jsonl"
    flips: Counter[str] = Counter()
    still_reason: Counter[str] = Counter()
    with out.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(sel, 1):
            q = r["pregunta"]
            try:
                ans = P.answer(q)
                new = ans.semaforo.value
            except Exception as exc:  # noqa: BLE001
                new = f"error:{exc}"
                ans = None
            flips[f"{target}->{new}"] += 1
            if new == target and ans is not None:
                key = (ans.reason or "")[:60]
                still_reason[key] += 1
            fh.write(
                json.dumps(
                    {
                        "pregunta": q,
                        "categoria": r.get("categoria"),
                        "viejo": target,
                        "nuevo": new,
                        "reason": (ans.reason if ans else None),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            fh.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(sel)}", flush=True)
    print("\n=== TRANSICIONES ===", flush=True)
    for k, n in flips.most_common():
        print(f"  {n:>4}  {k}", flush=True)
    if still_reason:
        print(f"\n=== siguen en '{target}' por: ===", flush=True)
        for k, n in still_reason.most_common():
            print(f"  {n:>3}  {k}", flush=True)


if __name__ == "__main__":
    main()
