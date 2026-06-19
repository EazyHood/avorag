"""Genera de una sola vez las respuestas de las 500 preguntas de evaluación y las guarda como un
BANCO de respuestas fijadas (para servirlas al instante). Resumible: salta las ya generadas.

Guarda el Answer COMPLETO (model_dump) por pregunta, con la firma del sistema (modelo+prompt+
corpus+lógica) con que se generó. El servidor lo carga al arrancar y fija cada respuesta.

Uso:  LLM_MODEL=qwen2.5:7b-instruct CACHE_ENABLED=false uv run python scripts/build_answer_bank.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from avorag.rag import pipeline as P
from avorag.rag import prewarm

_ROOT = Path(__file__).resolve().parents[1]
_QS = _ROOT / "data" / "eval" / "questions_500.json"
_BANK = _ROOT / "data" / "cache" / "answer_bank.jsonl"


def _done() -> set[str]:
    if not _BANK.exists():
        return set()
    out = set()
    for line in _BANK.read_text(encoding="utf-8").splitlines():
        try:
            out.add(json.loads(line)["pregunta"])
        except Exception:  # noqa: BLE001
            continue
    return out


def main() -> None:
    data = json.loads(_QS.read_text(encoding="utf-8"))
    items = [q for qs in data.values() for q in qs]
    done = _done()
    pending = [q for q in items if q not in done]
    _BANK.parent.mkdir(parents=True, exist_ok=True)
    sig = prewarm._signature()
    print(
        f"Banco: total={len(items)} hechas={len(done)} pendientes={len(pending)} | firma={sig}",
        flush=True,
    )

    with _BANK.open("a", encoding="utf-8") as fh:
        for i, q in enumerate(pending, 1):
            t0 = time.time()
            try:
                ans = P.answer(q)
                rec = {"pregunta": q, "firma": sig, "answer": ans.model_dump(mode="json")}
            except Exception as exc:  # noqa: BLE001
                rec = {"pregunta": q, "error": str(exc)}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 5 == 0 or i == len(pending):
                print(f"  {i}/{len(pending)}  ({time.time() - t0:.0f}s)  {q[:50]}", flush=True)


if __name__ == "__main__":
    main()
