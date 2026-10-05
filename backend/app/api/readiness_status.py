"""Lightweight API projection of the existing source-readiness evidence."""

from __future__ import annotations

import re
from pathlib import Path

from backend.app.api import services
from backend.app.data_intake.readiness import readiness
from scripts.build_heat_map_pipeline import SOURCE_IDS


def _source_gate(snapshot: dict) -> bool:
    """Reject contradictory or incomplete evidence before summarizing it."""
    required = snapshot.get("required_sources")
    blockers = snapshot.get("first_heat_map_blockers")
    ready = snapshot.get("required_sources_ready")
    total = snapshot.get("required_sources_total")
    if (snapshot.get("evidence_warnings") or not isinstance(required, list)
            or not isinstance(blockers, list) or type(ready) is not int
            or type(total) is not int or total != len(SOURCE_IDS)
            or len(required) != total or not 0 <= ready <= total
            or not all(isinstance(row, dict) and isinstance(row.get("id"), str)
                       and type(row.get("ready")) is bool for row in required)
            or {row["id"] for row in required} != SOURCE_IDS
            or len({row["id"] for row in required}) != total
            or sum(row["ready"] for row in required) != ready
            or not all(isinstance(row, dict) and isinstance(row.get("id"), str)
                       and isinstance(row.get("name"), str) for row in blockers)
            or {row["id"] for row in blockers} != {row["id"] for row in required if not row["ready"]}
            or len(blockers) != total - ready
            or snapshot.get("first_heat_map_ready") is not (not blockers)):
        return False
    return True


def artifact_statuses(root: Path) -> dict[str, str]:
    """Use accepted grid and model metadata checks, without reading source rasters or hashes."""
    grid_status = "blocked"
    grid_metadata = None
    try:
        reader, grid_metadata = services._real_grid()
        reader.close()
        grid_status = "ready"
    except (services.DataUnavailableError, OSError, ValueError, ImportError, KeyError, TypeError):
        pass

    model_status = "blocked"
    if grid_status == "ready":
        try:
            services.model_metrics()
            model_metadata = services._read_json(services.MODEL_METADATA)
            digest = model_metadata.get("model_artifact_sha256")
            dataset = model_metadata.get("dataset_version")
            if (not re.fullmatch(r"sha256:[0-9a-f]{64}", str(digest))
                    or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(dataset))
                    or model_metadata.get("feature_list") != grid_metadata["features"]
                    or model_metadata.get("dataset_rows") != grid_metadata["row_count"]
                    or model_metadata.get("crs") != grid_metadata.get("crs")
                    or grid_metadata.get("crs") != "EPSG:32643"
                    or model_metadata.get("resolution_m") != 30):
                raise services.DataUnavailableError("Model metadata does not match the accepted grid")
            model_status = "ready"
        except (services.DataUnavailableError, OSError, ValueError, ImportError, KeyError, TypeError):
            pass

    planning_status = "pending"
    try:
        from backend.app.optimizer.location_catalog import list_planning_locations
        if services.CATALOG.is_file() and list_planning_locations(
                services.CATALOG, project_root=root)["total"] > 0:
            planning_status = "ready"
    except (RuntimeError, OSError, ValueError, KeyError, TypeError):
        pass
    return {"real_ml_grid": grid_status, "trained_xgboost_model": model_status,
            "planning_evidence": planning_status}


def readiness_status(root: Path | None = None) -> dict:
    """Add a typed summary to the detailed, authoritative readiness snapshot."""
    root = root or services.ROOT
    snapshot = readiness(root)
    gate_known = _source_gate(snapshot)
    sources = snapshot.get("sources", [])
    source_status = {
        row["id"]: ("blocked" if row.get("status") == "verified" and
                    (not row.get("local_available") or row.get("blocked_reason"))
                    else row.get("status", "blocked"))
        for row in sources if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    blockers = ([{"id": row["id"], "name": row["name"],
                  "reason": row.get("reason") or "Source evidence is unavailable."}
                 for row in snapshot["first_heat_map_blockers"]] if gate_known else [])
    later = {row.get("name"): row for row in snapshot.get("later_stage_dependencies", [])
             if isinstance(row, dict)}
    artifacts = artifact_statuses(root)
    artifacts["field_validation"] = (
        "staged" if later.get("Field validation", {}).get("status") == "staged"
        else "pending")
    return {**snapshot,
            "software": {"status": "ready", "basis": "backend_runtime",
                         "note": "The readiness API is running; this is not a CI or test result."},
            "production_data": ("source_ready" if snapshot["first_heat_map_ready"] else "blocked")
            if gate_known else "unknown",
            "first_heat_map": {
                "ready": snapshot["first_heat_map_ready"] if gate_known else None,
                "required_sources_ready": snapshot["required_sources_ready"] if gate_known else None,
                "required_sources_total": snapshot["required_sources_total"] if gate_known else None,
                "blocker_count": len(blockers) if gate_known else None,
            },
            "source_status": source_status,
            "artifacts": artifacts,
            "artifact_basis": "Accepted grid schema and matching model metadata; production use still validates artifact hashes and model loading.",
            "blockers": blockers}
