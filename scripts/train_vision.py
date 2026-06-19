"""Entrena el clasificador de visión de AvoRAG (madurez o patología) y lo exporta a TorchScript.

Stack de licencia PERMISIVA (evita el AGPL-3.0 de Ultralytics YOLO):
  - torchvision (BSD-3-Clause) como backbone (MobileNetV3 / EfficientNet-B0).
  - El resultado se serializa a TorchScript (`model.pt`) + `labels.json`, que es lo único que
    necesita la inferencia (`src/avorag/vision/classifier.py`).

OJO licencia de PESOS: los pesos preentrenados de torchvision se entrenaron en ImageNet, liberado
"solo para investigación no comercial". Para un producto comercial 100% limpio: (a) afina sobre tu
propio dataset (transfer learning, opción por defecto) y declara el origen, o (b) entrena desde cero
con --no-pretrained. El dataset de madurez recomendado SÍ permite uso comercial (ver docs/VISION.md).

Estructura esperada del dataset (carpetas = clases; los nombres deben ser las claves canónicas de
`src/avorag/vision/labels.py`, p.ej. madurez_verde/, trips/, antracnosis/, sano/):

    data/vision/<dataset>/
        madurez_verde/  img001.jpg ...
        madurez_pinton/ ...
        ...

Uso:
    uv sync --extra vision
    uv run python scripts/train_vision.py --data-dir data/vision/madurez --out models/vision \
        --arch mobilenet_v3_large --epochs 15

Instalación de torch en RTX 50xx (Blackwell, sm_120), 2026 (VERIFICADO jun-2026 — cu128, NO cu130):
    uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
    # cu128 (CUDA 12.8) es el backend recomendado para sm_120; cu130/CUDA 13 da problemas de
    # compatibilidad con torch a jun-2026. Comprueba: torch.cuda.get_device_capability() -> (12, 0)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Consola Windows en cp1252 no encodea ✓/emojis → fuerza UTF-8 (si no, el print final crashea).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
_MEAN = [0.485, 0.456, 0.406]
_STD = [0.229, 0.224, 0.225]


def _fruit_id(path: str) -> str:
    """Id del fruto físico desde el nombre 'T20_d01_001_a_1.jpg' -> 'T20_001' (grupo + sample,
    ignorando día y lado a/b). Permite partir train/val por FRUTO y evitar la fuga (el mismo fruto
    en ambos splits) que inflaría el val_acc. Si el nombre no sigue el patrón, cada imagen es su
    propio grupo (no peor que un split por imagen)."""
    parts = Path(path).stem.split("_")
    if len(parts) >= 3 and parts[1][:1].lower() == "d" and parts[1][1:].isdigit():
        return f"{parts[0]}_{parts[2]}"
    return Path(path).stem


def _build_model(arch: str, num_classes: int, pretrained: bool):
    import torchvision.models as M
    from torch import nn

    if arch == "mobilenet_v3_large":
        w = M.MobileNet_V3_Large_Weights.IMAGENET1K_V2 if pretrained else None
        model = M.mobilenet_v3_large(weights=w)
        in_f = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_f, num_classes)
    elif arch == "mobilenet_v3_small":
        w = M.MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
        model = M.mobilenet_v3_small(weights=w)
        in_f = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_f, num_classes)
    elif arch == "efficientnet_b0":
        w = M.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
        model = M.efficientnet_b0(weights=w)
        in_f = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_f, num_classes)
    else:
        raise SystemExit(f"--arch desconocido: {arch!r}")
    return model


def _loaders(data_dir: Path, img_size: int, batch_size: int, val_split: float):
    import torch
    from torch.utils.data import DataLoader, Subset
    from torchvision import transforms
    from torchvision.datasets import ImageFolder

    train_tf = transforms.Compose(
        [
            transforms.Resize(int(img_size * 1.15)),
            transforms.RandomResizedCrop(img_size, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize(_MEAN, _STD),
        ]
    )
    eval_tf = transforms.Compose(
        [
            transforms.Resize(img_size),
            transforms.CenterCrop(img_size),
            transforms.ToTensor(),
            transforms.Normalize(_MEAN, _STD),
        ]
    )

    # Dos vistas del MISMO dataset: train con augmentation, val sin ella, con idéntica división de
    # índices. (Antes se mutaba el transform compartido y el train acababa SIN augmentation.)
    ds_train = ImageFolder(str(data_dir), transform=train_tf)
    ds_eval = ImageFolder(str(data_dir), transform=eval_tf)

    # Split por FRUTO, no por imagen: el dataset tiene ~478 frutos fotografiados por 2 lados (a/b)
    # durante varios días (~30 imgs/fruto). Partir por imagen mete el MISMO fruto en train y val
    # -> el modelo memoriza el fruto y el val_acc queda INFLADO. Agrupamos por id de fruto.
    groups: dict[str, list[int]] = {}
    for i, (path, _label) in enumerate(ds_train.samples):
        groups.setdefault(_fruit_id(path), []).append(i)
    group_ids = sorted(groups)
    gen = torch.Generator().manual_seed(42)
    perm = torch.randperm(len(group_ids), generator=gen).tolist()
    n_val_groups = max(1, int(len(group_ids) * val_split))
    val_gids = {group_ids[j] for j in perm[:n_val_groups]}
    train_idx = [i for gid in group_ids if gid not in val_gids for i in groups[gid]]
    val_idx = [i for gid in val_gids for i in groups[gid]]
    train_ds = Subset(ds_train, train_idx)
    val_ds = Subset(ds_eval, val_idx)
    print(
        f"Split por fruto (sin fuga): {len(group_ids)} frutos -> "
        f"{len(group_ids) - len(val_gids)} train / {len(val_gids)} val "
        f"({len(train_idx)} / {len(val_idx)} imgs)"
    )

    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_dl = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)
    return train_dl, val_dl, ds_train.classes


def _evaluate(model, loader, device) -> float:
    import torch

    model.eval()
    correct = total = 0
    with torch.no_grad():
        for x, y in loader:
            pred = model(x.to(device)).argmax(1).cpu()
            correct += int((pred == y).sum())
            total += y.numel()
    return correct / max(1, total)


def main() -> None:
    ap = argparse.ArgumentParser(description="Entrena el clasificador de visión de AvoRAG.")
    ap.add_argument(
        "--data-dir", type=Path, required=True, help="Raíz ImageFolder (carpetas=clases)."
    )
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "vision")
    ap.add_argument(
        "--arch",
        default="mobilenet_v3_large",
        choices=["mobilenet_v3_large", "mobilenet_v3_small", "efficientnet_b0"],
    )
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--val-split", type=float, default=0.15)
    ap.add_argument(
        "--no-pretrained",
        action="store_true",
        help="Entrena desde cero (sin pesos ImageNet) para limpieza total de licencia.",
    )
    args = ap.parse_args()

    import torch
    from torch import nn

    if not args.data_dir.exists():
        raise SystemExit(f"No existe {args.data_dir}. Ver docs/VISION.md para preparar el dataset.")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    train_dl, val_dl, classes = _loaders(
        args.data_dir, args.img_size, args.batch_size, args.val_split
    )
    print(f"Dispositivo: {device} | clases ({len(classes)}): {classes}")

    model = _build_model(args.arch, len(classes), pretrained=not args.no_pretrained).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    loss_fn = nn.CrossEntropyLoss(
        label_smoothing=0.1
    )  # calibra (-sobreconfianza) y suaviza fronteras adyacentes

    args.out.mkdir(parents=True, exist_ok=True)
    best_acc = 0.0
    best_path = args.out / "model.pt"
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for x, y in train_dl:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            opt.step()
            running += loss.item() * x.size(0)
        acc = _evaluate(model, val_dl, device)
        lr_now = opt.param_groups[0]["lr"]
        print(
            f"época {epoch:02d}/{args.epochs} | loss {running / len(train_dl.dataset):.4f} | val_acc {acc:.3f} | lr {lr_now:.2e}"
        )
        if acc >= best_acc:
            best_acc = acc
            scripted = torch.jit.script(model.eval().cpu())
            scripted.save(str(best_path))
            model.to(device)
        sched.step()

    labels = {
        "classes": classes,
        "input_size": args.img_size,
        "mean": _MEAN,
        "std": _STD,
        "model_version": f"{args.arch}-{date.today().isoformat()}-acc{best_acc:.2f}",
        "arch": args.arch,
        "pretrained_imagenet": not args.no_pretrained,
    }
    (args.out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n✓ Modelo: {best_path}  (val_acc {best_acc:.3f})")
    print(f"✓ Etiquetas: {args.out / 'labels.json'}")
    print("Configura .env -> VISION_PROVIDER=local, VISION_MODEL_PATH=" + str(best_path))
    print("Recuerda la ATRIBUCIÓN del dataset (CC BY 4.0) en docs/VISION.md y en el README.")


if __name__ == "__main__":
    main()
