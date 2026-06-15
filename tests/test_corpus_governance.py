"""Gobernanza del corpus: el manifiesto debe estar bien formado (autoridad, licencia, país, hash)."""

from __future__ import annotations

import json
import re
from pathlib import Path

_MANIFEST = Path(__file__).resolve().parents[1] / "data" / "corpus_manifest.json"
_VALID_AUTORIDAD = {"oficial-regulador", "gremio", "academico", "interno-cliente"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _docs() -> list[dict]:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))["documents"]


def test_manifest_is_well_formed() -> None:
    docs = _docs()
    assert docs, "el manifiesto no tiene documentos"
    filenames = [d["filename"] for d in docs]
    assert len(filenames) == len(set(filenames)), "filenames duplicados en el manifiesto"
    for d in docs:
        assert d.get("fuente", "").strip(), f"{d['filename']}: sin fuente citable"
        assert d.get("autoridad") in _VALID_AUTORIDAD, f"{d['filename']}: autoridad inválida"
        assert d.get("licencia", "").strip(), f"{d['filename']}: sin licencia declarada"
        assert re.fullmatch(r"[A-Z]{2}", d.get("pais", "")), f"{d['filename']}: país no ISO-2"
        assert d.get("download") in ("auto", "manual"), f"{d['filename']}: download inválido"


def test_manifest_hashes_present_and_valid() -> None:
    for d in _docs():
        sha = d.get("sha256")
        # Permite null para fuentes aún no descargadas.
        if sha is not None:
            assert _SHA256_RE.match(sha), f"{d['filename']}: sha256 mal formado"


def test_corpus_version_present() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("corpus_version"), "el manifiesto no declara corpus_version"
