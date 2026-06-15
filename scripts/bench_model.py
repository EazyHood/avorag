"""Banco rápido para comparar un modelo LLM (velocidad, calidad, deriva de idioma).

Uso:  LLM_MODEL=llama3.2:3b  uv run python scripts/bench_model.py
Mide, por consulta: tiempo total, tok/s de generación pura, si derivó a otro alfabeto,
semáforo, si se abstuvo y la longitud de la respuesta. No toca el servidor.
"""

from __future__ import annotations

import re
import time

from avorag.config import get_settings
from avorag.rag import pipeline as P

_FOREIGN = re.compile("[　-〿぀-ヿ㐀-䶿一-鿿가-힯Ѐ-ӿ֐-׿؀-ۿ]")

QUERIES = [
    "¿Cómo manejo los trips en aguacate Hass?",
    "¿Qué dosis de nitrógeno aplico en Hass?",
    "¿Cuánto potasio aplicar en Hass durante el llenado del fruto?",
    "¿Cómo calculo los requerimientos nutricionales del Hass?",
]


def main() -> None:
    s = get_settings()
    print(f"MODELO: {s.llm_model}   (juez: {s.judge_llm_model or 'mismo'})")
    print("-" * 78)
    for q in QUERIES:
        t0 = time.perf_counter()
        ans = P.answer(q)
        dt = time.perf_counter() - t0
        foreign = bool(_FOREIGN.search(ans.text))
        print(
            f"{dt:6.1f}s | {ans.semaforo.value:8s} | abst={str(ans.abstained):5s} | "
            f"foráneo={str(foreign):5s} | len={len(ans.text):4d} | {q[:42]}"
        )
        print(f"         -> {ans.text[:100]!r}")
    print("-" * 78)


if __name__ == "__main__":
    main()
