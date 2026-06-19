"""Manifiesto de SINCRONIZACIÓN online↔offline (lado servidor).

El cliente compara este manifiesto con lo que tiene empaquetado y descarga los DELTAS. El SERVIDOR
reporta lo que conoce: `corpus_version` (de `data/corpus_manifest.json`) y `norm_version` (de las
normas versionadas). Los artefactos puramente OFFLINE (knowledge_bundle, modelo ONNX de visión) se
añaden cuando el lado offline publique su hash/URL/versión (su dominio). Firma = hash de
tamper-evidence (Ed25519 con clave del operador es la mejora de producción).

Colisión-safe: módulo NUEVO bajo `online/`. Lógica de construcción PURA (now inyectable).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

OFFLINE_CONTRACT_VERSION = "1"
_CORPUS_MANIFEST = Path(__file__).resolve().parents[3] / "data" / "corpus_manifest.json"


def _sign_manifest(body: dict) -> str:
    """Hash de tamper-evidence del manifiesto (sin el campo signature)."""
    payload = {k: v for k, v in body.items() if k != "signature"}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_manifest(
    *,
    corpus_version: str,
    norm_version: str,
    now: datetime,
    artifacts_extra: list[dict] | None = None,
) -> dict:
    """Arma el manifiesto firmado. PURO (testeable): `now` inyectable, sin IO."""
    artifacts = [
        {"name": "corpus", "version": corpus_version, "sha256": "", "url": "", "bytes": 0},
        {"name": "normas", "version": norm_version, "sha256": "", "url": "", "bytes": 0},
    ]
    if artifacts_extra:
        artifacts.extend(artifacts_extra)
    body = {
        "offline_contract_version": OFFLINE_CONTRACT_VERSION,
        "generated_at": now.isoformat(),
        "artifacts": artifacts,
    }
    body["signature"] = _sign_manifest(body)
    return body


def _corpus_version() -> str:
    try:
        return str(
            json.loads(_CORPUS_MANIFEST.read_text(encoding="utf-8")).get(
                "corpus_version", "unknown"
            )
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def _norm_version() -> str:
    from avorag.online.norms import NORM_VERSION

    return NORM_VERSION


def current_manifest(
    *, now: datetime | None = None, artifacts_extra: list[dict] | None = None
) -> dict:
    """Manifiesto vigente con las versiones que el servidor conoce."""
    return build_manifest(
        corpus_version=_corpus_version(),
        norm_version=_norm_version(),
        now=now or datetime.now(UTC),
        artifacts_extra=artifacts_extra,
    )
