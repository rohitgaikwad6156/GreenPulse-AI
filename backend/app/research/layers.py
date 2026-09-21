"""Status contract for separate exposure and vulnerability evidence layers."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=8)
def _sha256_signature(path_text: str, size: int, modified_ns: int) -> str:
    digest = hashlib.sha256()
    with Path(path_text).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def research_layer_status(path: Path) -> dict:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema_version") != "1.0" or not isinstance(document.get("layers"), list):
        raise ValueError("Invalid research layer registry")
    exposure = [item for item in document["layers"] if item.get("layer_type") == "exposure"]
    vulnerability = [item for item in document["layers"] if item.get("layer_type") == "vulnerability"]
    if not exposure or not vulnerability:
        raise ValueError("Registry must keep exposure and vulnerability layers separate")
    root = Path(path).resolve().parents[2]
    for layer in exposure + vulnerability:
        if layer.get("status") == "source_verified_processing_blocked":
            source_path = root / layer["source"]["local_path"]
            if not source_path.is_file():
                raise ValueError(f"Verified research source is missing: {source_path}")
            signature = source_path.stat()
            checksum = _sha256_signature(str(source_path), signature.st_size, signature.st_mtime_ns)
            if layer["source"].get("checksum") != checksum:
                raise ValueError(f"Research source checksum mismatch: {layer['layer_id']}")
    return {
        **document,
        "exposure_layers": exposure,
        "vulnerability_layers": vulnerability,
        "heat_hazard_score_separate": True,
        "composite_risk_available": False,
        "composite_risk_reason": (
            "No established framework has been configured with complete hazard, exposure, "
            "vulnerability, capacity, and sensitivity-analysis inputs; no weighted sum is computed."),
    }
