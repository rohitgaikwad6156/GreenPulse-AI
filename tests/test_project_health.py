"""Synthetic evidence and artifact gates for the local project-health summary."""

from pathlib import Path

from scripts.build_heat_map_pipeline import SOURCE_IDS
from scripts.project_health import CHECKS, collect_health, software_status


PASSING = {key: "PASS" for key in CHECKS}


def snapshot(*, missing=("municipal_boundary", "sentinel2_l2a_scenes")):
    required = [{"id": key, "ready": key not in missing} for key in sorted(SOURCE_IDS)]
    blockers = [{"id": key, "name": f"Synthetic {key}"} for key in missing]
    sources = [
        {"id": "pmc_outline", "status": "pending"},
        {"id": "pcmc_outline", "status": "staged"},
        {"id": "ward_boundaries", "status": "pending"},
        {"id": "esa_worldcover", "status": "verified", "local_available": True},
        {"id": "osm_roads", "status": "verified", "local_available": True},
    ]
    audits = [
        {"id": "landsat_source", "status": "pass"},
        {"id": "landsat_processing", "status": "pass"},
        {"id": "landsat_extremes", "status": "review", "audit_result": "PASS"},
        {"id": "sentinel_intake", "status": "pending", "audit_result": "FAIL"},
    ]
    return {"required_sources": required, "required_sources_ready": len(required) - len(missing),
            "required_sources_total": len(required), "first_heat_map_ready": not missing,
            "first_heat_map_blockers": blockers, "sources": sources,
            "audit_trail": audits, "evidence_warnings": []}


def _reject():
    raise ValueError("Synthetic legacy artifact rejected")


def _files(tmp_path: Path):
    paths = (tmp_path / "grid.parquet", tmp_path / "grid.json",
             tmp_path / "legacy.joblib", tmp_path / "model.json")
    for path in paths:
        path.write_bytes(b"synthetic fixture")
    return paths[:2], paths[2:]


def test_current_like_readiness_comes_from_snapshot(tmp_path):
    grid, model = _files(tmp_path)
    result = collect_health(tmp_path, checks=PASSING, readiness_loader=lambda _: snapshot(),
                            grid_check=_reject, model_check=_reject,
                            grid_paths=grid, model_paths=model)
    production = result["production"]
    assert (production["required_sources_ready"], production["required_sources_total"]) == (3, 5)
    assert len(production["blockers"]) == 2
    assert production["status"] == "WAITING FOR 2 REQUIRED SOURCE GROUPS"
    assert (production["ml_grid"], production["xgboost_model"]) == ("BLOCKED", "BLOCKED")
    assert result["overall"]["software"] == "READY"
    assert result["data_evidence"]["sentinel_manual_intake"] == "PENDING"
    assert result["data_evidence"]["landsat_extreme_diagnostics"] == "REVIEWED"
    assert result["data_evidence"]["pmc_boundary"] == "PENDING"
    assert result["data_evidence"]["pcmc_boundary"] == "STAGED"
    assert result["data_evidence"]["ward_gis"] == "PENDING"


def test_blocker_count_updates_without_ward(tmp_path):
    grid, model = _files(tmp_path)
    state = snapshot(missing=("sentinel2_l2a_scenes",))
    result = collect_health(tmp_path, checks=PASSING, readiness_loader=lambda _: state,
                            grid_check=_reject, model_check=_reject,
                            grid_paths=grid, model_paths=model)
    assert result["production"]["status"] == "WAITING FOR 1 REQUIRED SOURCE GROUP"
    assert [item["id"] for item in result["production"]["blockers"]] == ["sentinel2_l2a_scenes"]


def test_legacy_files_do_not_become_accepted_artifacts(tmp_path):
    grid, model = _files(tmp_path)
    result = collect_health(tmp_path, checks=PASSING,
                            readiness_loader=lambda _: snapshot(missing=()),
                            grid_check=_reject, model_check=_reject,
                            grid_paths=grid, model_paths=model)
    assert result["production"]["ml_grid"] == "INVALID / REVIEW"
    assert result["production"]["xgboost_model"] == "BLOCKED"
    result = collect_health(tmp_path, checks=PASSING,
                            readiness_loader=lambda _: snapshot(missing=()),
                            grid_check=lambda: True, model_check=_reject,
                            grid_paths=grid, model_paths=model)
    assert result["production"]["xgboost_model"] == "INVALID / REVIEW"


def test_missing_readiness_is_unknown(tmp_path):
    result = collect_health(tmp_path, checks=PASSING, readiness_loader=lambda _: {},
                            grid_check=_reject, model_check=_reject)
    assert result["production"]["status"] == "PRODUCTION READINESS UNKNOWN"
    assert result["production"]["required_sources_ready"] is None
    assert result["production"]["ml_grid"] == "UNAVAILABLE"
    assert all(value == "UNAVAILABLE" for value in result["data_evidence"].values())


def test_failed_or_skipped_software_checks_are_not_ready(tmp_path):
    assert software_status(PASSING) == "READY"
    assert software_status({**PASSING, "frontend_tests": "FAIL"}) == "NOT READY"
    assert software_status({**PASSING, "python_tests": "NOT RUN"}) == "NOT READY"
    assert software_status(None) == "NOT READY"
    result = collect_health(tmp_path, checks={**PASSING, "frontend_build": "FAIL"},
                            readiness_loader=lambda _: snapshot())
    assert result["overall"]["software"] == "NOT READY"


def test_inconsistent_source_counts_fail_closed(tmp_path):
    state = snapshot()
    state["required_sources_ready"] = 4
    result = collect_health(tmp_path, checks=PASSING, readiness_loader=lambda _: state)
    assert result["production"]["status"] == "PRODUCTION READINESS UNKNOWN"
