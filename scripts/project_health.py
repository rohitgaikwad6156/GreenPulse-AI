"""Read-only, machine-readable projection of existing GreenPulse evidence gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.data_intake.readiness import readiness
from scripts.build_heat_map_pipeline import SOURCE_IDS

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ("python_lint", "frontend_eslint", "frontend_format", "python_tests",
          "frontend_tests", "frontend_build", "repository_diff")
AUDITS = {
    "landsat_source": "landsat_source_audit",
    "landsat_processing": "landsat_processing_audit",
    "landsat_extremes": "landsat_extreme_diagnostics",
    "sentinel_intake": "sentinel_manual_intake",
}
SOURCES = {
    "pmc_outline": "pmc_boundary",
    "pcmc_outline": "pcmc_boundary",
    "esa_worldcover": "worldcover",
    "osm_roads": "osm_roads",
    "worldpop": "worldpop",
    "ward_boundaries": "ward_gis",
}


def software_status(checks: dict | None) -> str:
    """A skipped or absent check cannot count as a successful check."""
    return "READY" if isinstance(checks, dict) and all(checks.get(key) == "PASS" for key in CHECKS) else "NOT READY"


def _source_status(row: dict | None) -> str:
    if not isinstance(row, dict):
        return "UNAVAILABLE"
    status = row.get("status")
    if status == "verified":
        return "VERIFIED" if row.get("local_available") and not row.get("blocked_reason") else "BLOCKED"
    return status.upper() if status in {"staged", "pending", "blocked"} else "UNAVAILABLE"


def _readiness_evidence(snapshot: dict | None) -> tuple[dict, dict]:
    unavailable = {key: "UNAVAILABLE" for key in (*AUDITS.values(), *SOURCES.values())}
    unknown = {"status": "PRODUCTION READINESS UNKNOWN", "required_sources_ready": None,
               "required_sources_total": None, "blockers": []}
    if not isinstance(snapshot, dict) or snapshot.get("evidence_warnings"):
        return unavailable, unknown
    required = snapshot.get("required_sources")
    blockers = snapshot.get("first_heat_map_blockers")
    audits = snapshot.get("audit_trail")
    sources = snapshot.get("sources")
    ready, total = snapshot.get("required_sources_ready"), snapshot.get("required_sources_total")
    if (not isinstance(required, list) or not isinstance(blockers, list)
            or not isinstance(audits, list) or not isinstance(sources, list)
            or type(ready) is not int or type(total) is not int or total <= 0
            or len(required) != total or not 0 <= ready <= total
            or {item.get("id") for item in required if isinstance(item, dict)} != SOURCE_IDS
            or len(blockers) != total - ready or snapshot.get("first_heat_map_ready") != (not blockers)
            or not all(isinstance(item, dict) and isinstance(item.get("id"), str)
                       and type(item.get("ready")) is bool for item in required)
            or sum(item["ready"] for item in required) != ready
            or not all(isinstance(item, dict) and isinstance(item.get("id"), str)
                       and isinstance(item.get("name"), str) for item in blockers)
            or {item["id"] for item in blockers} != {item["id"] for item in required if not item["ready"]}
            or not all(isinstance(item, dict) for item in (*audits, *sources))):
        return unavailable, unknown
    by_audit = {item.get("id"): item for item in audits}
    by_source = {item.get("id"): item for item in sources}
    evidence = {}
    for audit_id, key in AUDITS.items():
        item = by_audit.get(audit_id, {})
        status = item.get("status")
        if audit_id == "landsat_extremes" and status == "review" and item.get("audit_result") == "PASS":
            evidence[key] = "REVIEWED"
        elif status in {"pass", "pending", "review", "unavailable"}:
            evidence[key] = status.upper()
        else:
            evidence[key] = "UNAVAILABLE"
    for source_id, key in SOURCES.items():
        evidence[key] = _source_status(by_source.get(source_id))
    count = len(blockers)
    status = ("READY FOR REAL HEAT-MAP BUILD" if count == 0 else
              f"WAITING FOR {count} REQUIRED SOURCE {'GROUP' if count == 1 else 'GROUPS'}")
    return evidence, {"status": status, "required_sources_ready": ready,
                      "required_sources_total": total,
                      "blockers": [{"name": item["name"], "id": item["id"]} for item in blockers]}


def _artifact_status(check: Callable[[], object], paths: tuple[Path, ...],
                     upstream_ready: bool, upstream_known: bool) -> str:
    if not upstream_known:
        return "UNAVAILABLE"
    if not all(path.is_file() for path in paths):
        return "BLOCKED"
    try:
        result = check()
        if isinstance(result, tuple) and result and hasattr(result[0], "close"):
            result[0].close()
    except Exception:
        if not upstream_ready or not all(path.is_file() for path in paths):
            return "BLOCKED"
        return "INVALID / REVIEW"
    return "READY"


def _accepted_grid():
    from backend.app.api import services
    return services._real_grid()


def _accepted_model():
    from backend.app.api import map_data, services
    # Match the artifact hash required by the saved-model simulation contract
    # before allowing the model loader to deserialize the local joblib file.
    metadata = services._read_json(services.MODEL_METADATA)
    expected = metadata.get("model_artifact_sha256")
    if not isinstance(expected, str) or len(expected) != 71 or not expected.startswith("sha256:"):
        raise services.DataUnavailableError("Model artifact digest is missing")
    digest = hashlib.sha256()
    with services.MODEL.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if expected != f"sha256:{digest.hexdigest()}":
        raise services.DataUnavailableError("Model artifact digest does not match metadata")
    # The map contract validates the real grid, dataset digest, model schema,
    # objective and model type. Metrics must pass the API's validation too.
    model = map_data._bundle()
    services.model_metrics()
    return model


def collect_health(root: Path = ROOT, *, checks: dict | None = None,
                   readiness_loader: Callable[[Path], dict] = readiness,
                   grid_check: Callable[[], object] = _accepted_grid,
                   model_check: Callable[[], object] = _accepted_model,
                   grid_paths: tuple[Path, ...] | None = None,
                   model_paths: tuple[Path, ...] | None = None) -> dict:
    """Use repository validators for artifacts and the existing readiness engine for sources."""
    grid_paths = grid_paths or (root / "data/processed/greenpulse_ml_grid.parquet",
                                 root / "data/processed/metadata.json")
    model_paths = model_paths or (root / "models/xgboost_lst.joblib",
                                   root / "models/model_metadata.json")
    try:
        snapshot = readiness_loader(root)
    except (OSError, ValueError, TypeError, KeyError):
        snapshot = None
    evidence, production = _readiness_evidence(snapshot)
    known = production["required_sources_total"] is not None
    source_ready = production["required_sources_ready"] == production["required_sources_total"] if known else False
    grid = _artifact_status(grid_check, grid_paths, source_ready, known)
    model = (_artifact_status(model_check, model_paths, source_ready, known) if grid == "READY"
             else "UNAVAILABLE" if not known else "BLOCKED")
    production.update(ml_grid=grid, xgboost_model=model)
    return {"software": {key: (checks or {}).get(key, "NOT RUN") for key in CHECKS},
            "data_evidence": evidence, "production": production,
            "overall": {"software": software_status(checks), "production": production["status"]}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks-json", help="JSON object of actual local software-check outcomes")
    args = parser.parse_args()
    try:
        checks_text = args.checks_json or os.environ.get("GREENPULSE_HEALTH_CHECKS_JSON")
        checks = json.loads(checks_text) if checks_text else None
        if checks is not None and not isinstance(checks, dict):
            raise ValueError("checks must be an object")
        print(json.dumps(collect_health(checks=checks), ensure_ascii=False))
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
