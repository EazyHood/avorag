"""Corre la simulación de N preguntas por el pipeline y registra señales por respuesta.

Lee data/eval/questions_500.json ({categoria: [preguntas...]}) y escribe, una línea JSON por
respuesta, en data/eval/sweep_results.jsonl. Reanudable: salta las preguntas ya registradas.
La CALIFICACIÓN 1-10 NO se hace aquí (se hace aparte con jueces); aquí solo se genera y registra.

Uso:  LLM_MODEL=qwen2.5:3b-instruct  CACHE_ENABLED=false  uv run python scripts/eval_sweep.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from avorag.rag import pipeline as P

_ROOT = Path(__file__).resolve().parents[1]
_QS = _ROOT / "data" / "eval" / "questions_500.json"
_OUT = _ROOT / "data" / "eval" / "sweep_results.jsonl"
_FOREIGN = re.compile("[　-〿぀-ヿ㐀-䶿一-鿿가-힯Ѐ-ӿ֐-׿؀-ۿ]")


def _done_questions() -> set[str]:
    if not _OUT.exists():
        return set()
    done = set()
    for line in _OUT.read_text(encoding="utf-8").splitlines():
        try:
            done.add(json.loads(line)["pregunta"])
        except Exception:  # noqa: BLE001
            continue
    return done


def main() -> None:
    data = json.loads(_QS.read_text(encoding="utf-8"))
    items = [(cat, q) for cat, qs in data.items() for q in qs]
    done = _done_questions()
    pending = [(c, q) for c, q in items if q not in done]
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Total={len(items)}  hechas={len(done)}  pendientes={len(pending)}", flush=True)

    with _OUT.open("a", encoding="utf-8") as fh:
        for i, (cat, q) in enumerate(pending, 1):
            t0 = time.time()
            try:
                ans = P.answer(q)
                rec = {
                    "categoria": cat,
                    "pregunta": q,
                    "semaforo": ans.semaforo.value,
                    "abstenida": ans.abstained,
                    "n_citas": len(ans.citations),
                    "fuentes": [c.fuente for c in ans.citations][:6],
                    "faithfulness": ans.faithfulness,
                    "foraneo": bool(_FOREIGN.search(ans.text)),
                    "len": len(ans.text),
                    "reason": ans.reason,
                    "texto": ans.text,
                    "latency_s": round(time.time() - t0, 1),
                }
            except Exception as exc:  # noqa: BLE001
                rec = {"categoria": cat, "pregunta": q, "error": str(exc)}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 10 == 0 or i == len(pending):
                print(f"  {i}/{len(pending)}  [{cat}] {q[:50]}", flush=True)


if __name__ == "__main__":
    main()
