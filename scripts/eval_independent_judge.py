"""Re-corre el eval del golden set con un JUEZ INDEPENDIENTE (Claude) — rompe la autoevaluación.

El groundedness 0.79 del README lo juzga el MISMO modelo que genera (autocorrelación). Esto lo
corrige: pone el juez de fidelidad en Anthropic/Claude, DISTINTO del generador, y re-corre el eval.

Requiere ANTHROPIC_API_KEY (no se puede correr sin tu clave; por eso es un script, no un cambio
ejecutado). Uso:

    # PowerShell:  $env:ANTHROPIC_API_KEY = "sk-ant-..."
    # bash:        export ANTHROPIC_API_KEY=sk-ant-...

    python scripts/eval_independent_judge.py                 # juez=Claude, generador=el configurado (ollama)
    python scripts/eval_independent_judge.py --cloud         # generador y juez en Claude (modelos DISTINTOS), sin ollama

Tras correr: eval/reports/last_report.json — `provider_info.judge` debe indicar que el juez es
INDEPENDIENTE del generador, y el gate vuelve a evaluarse con esa medición honesta.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main() -> None:
    ap = argparse.ArgumentParser(description="Eval del golden con juez independiente (Claude).")
    ap.add_argument("--golden", default="data/golden/hass_v1.jsonl", help="Golden set a evaluar.")
    ap.add_argument("--judge-model", default="claude-sonnet-4-6", help="Modelo Claude del JUEZ.")
    ap.add_argument(
        "--gen-model", default="claude-opus-4-8", help="Modelo Claude del GENERADOR (con --cloud)."
    )
    ap.add_argument("--cloud", action="store_true", help="Generador y juez en Claude (sin ollama).")
    args = ap.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("✗ Falta ANTHROPIC_API_KEY. Expórtala y reintenta (ver el docstring de este script).")
        sys.exit(2)
    if args.cloud and args.judge_model == args.gen_model:
        print("✗ Con --cloud, el juez y el generador DEBEN ser modelos distintos (independencia).")
        sys.exit(2)

    env = dict(os.environ)
    env["JUDGE_LLM_PROVIDER"] = "anthropic"
    env["JUDGE_LLM_MODEL"] = args.judge_model
    if args.cloud:
        env["LLM_PROVIDER"] = "anthropic"
        env["LLM_MODEL"] = args.gen_model

    modo = "cloud (generador+juez Claude)" if args.cloud else "juez Claude sobre el generador local"
    print(
        f"▶ Eval con juez INDEPENDIENTE — {modo}\n  juez={args.judge_model}"
        + (f" · generador={args.gen_model}" if args.cloud else "")
        + f"\n  golden={args.golden}"
    )
    rc = subprocess.call(["uv", "run", "avorag", "eval", args.golden], env=env)
    print(
        "\n✔ Revisa eval/reports/last_report.json:\n"
        "  - provider_info.judge debe ser distinto del generador (independiente).\n"
        "  - groundedness/citación/peligrosas re-medidos sin autocorrelación.\n"
        "  - actualiza el README con esta corrida (sustituye la nota 'autoevaluación')."
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
