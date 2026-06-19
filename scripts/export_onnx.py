"""Convierte un modelo de visión TorchScript (`.pt`) a ONNX (portátil + mejor fallback CPU).

El export solo necesita `torch` (extra 'vision'); la INFERENCIA ONNX necesita el extra 'vision-onnx'
(onnxruntime). Copia el `labels.json` junto al `.onnx` para que el clasificador lo encuentre.

Uso:
    uv run python scripts/export_onnx.py --model models/vision/model.pt
    # genera models/vision/model.onnx (+ copia labels.json) y luego:
    #   .env -> VISION_PROVIDER=onnx, VISION_MODEL_PATH=models/vision/model.onnx
    #   uv sync --extra vision-onnx

Notas:
- El tamaño de entrada se lee del labels.json contiguo (input_size); si no existe, usa --img-size.
- Eje 0 dinámico (batch) en entrada y salida.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Consola Windows en cp1252 no encodea ✓ → fuerza UTF-8 (evita crash en los prints).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    ap = argparse.ArgumentParser(description="Exporta un modelo de visión TorchScript a ONNX.")
    ap.add_argument("--model", type=Path, required=True, help="Ruta del modelo TorchScript .pt.")
    ap.add_argument("--out", type=Path, default=None, help="Salida .onnx (def: junto al .pt).")
    ap.add_argument(
        "--img-size", type=int, default=224, help="Solo si no hay labels.json contiguo."
    )
    ap.add_argument("--opset", type=int, default=17)
    args = ap.parse_args()

    if not args.model.exists():
        raise SystemExit(f"No existe el modelo {args.model}")
    out = args.out or args.model.with_suffix(".onnx")

    import torch

    # Tamaño de entrada desde labels.json contiguo (si existe).
    labels = args.model.with_name("labels.json")
    size = args.img_size
    if labels.exists():
        size = int(json.loads(labels.read_text("utf-8")).get("input_size", size))

    model = torch.jit.load(str(args.model), map_location="cpu").eval()
    dummy = torch.randn(1, 3, size, size)
    out.parent.mkdir(parents=True, exist_ok=True)
    # dynamo=False usa el exportador clásico TorchScript: funciona sobre un ScriptModule y NO
    # requiere onnxscript (que sí exige el exportador dynamo por defecto en torch 2.11).
    torch.onnx.export(
        model,
        dummy,
        str(out),
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=args.opset,
        dynamo=False,
    )

    # Copia labels.json junto al .onnx para que el clasificador lo encuentre.
    if labels.exists():
        dest = out.with_name("labels.json")
        if labels.resolve() != dest.resolve():
            shutil.copy2(labels, dest)

    mb = out.stat().st_size / 1e6
    print(f"✓ ONNX: {out} ({mb:.1f} MB, opset {args.opset}, entrada 1x3x{size}x{size})")
    print(f"  Activa: VISION_PROVIDER=onnx · VISION_MODEL_PATH={out} · uv sync --extra vision-onnx")


if __name__ == "__main__":
    main()
