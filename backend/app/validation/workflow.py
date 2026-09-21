"""Provenance-aware post-intervention LST validation and calibration proposals."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats


SCHEMA_VERSION = "1.0"
REPORT_VERSION = "1.0"
REAL_LABEL = "REAL INTERVENTION OBSERVATIONS"
SYNTHETIC_LABEL = "SYNTHETIC TEST FIXTURE"
REQUIRED_OBSERVATION_COLUMNS = {
    "grid_id", "group", "period_id", "lst_c", "x", "y", "qa_valid",
}


class ValidationEvidenceError(RuntimeError):
    """Imported evidence is missing, inconsistent, stale, or untraceable."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=path.name, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationEvidenceError(f"{field} must be a nonblank string")
    return value.strip()


def _sha(value: Any, field: str) -> str:
    result = _text(value, field).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise ValidationEvidenceError(f"{field} must be a 64-character SHA-256")
    return result


def _date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationEvidenceError(f"{field} must use YYYY-MM-DD") from exc


def _minutes(value: Any, field: str) -> int:
    try:
        parsed = datetime.strptime(str(value), "%H:%M")
    except ValueError as exc:
        raise ValidationEvidenceError(f"{field} must use HH:MM local time") from exc
    return parsed.hour * 60 + parsed.minute


def _load_grid(path: Path) -> dict[str, tuple[float, float]]:
    if not path.is_file():
        raise ValidationEvidenceError(f"Reference grid is missing: {path}")
    try:
        if path.suffix.lower() == ".parquet":
            import pyarrow.parquet as pq
            table = pq.read_table(path, columns=["grid_id", "x", "y"]).to_pydict()
            rows = zip(table["grid_id"], table["x"], table["y"])
        else:
            stream = path.open(encoding="utf-8-sig", newline="")
            rows = ((row["grid_id"], row["x"], row["y"]) for row in csv.DictReader(stream))
        grid: dict[str, tuple[float, float]] = {}
        for grid_id, x, y in rows:
            key = str(grid_id).strip()
            if not key or key in grid:
                raise ValidationEvidenceError("Reference grid IDs must be nonblank and unique")
            grid[key] = (float(x), float(y))
        if path.suffix.lower() != ".parquet":
            stream.close()
    except ValidationEvidenceError:
        raise
    except Exception as exc:
        raise ValidationEvidenceError(f"Cannot read reference grid: {path}") from exc
    return grid


def _validate_manifest(document: dict, *, synthetic_allowed: bool) -> tuple[list[dict], dict[str, dict]]:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValidationEvidenceError(f"schema_version must be {SCHEMA_VERSION}")
    for field in ("dataset_id", "dataset_version", "location_id", "intervention_id",
                  "season", "season_start_mm_dd", "season_end_mm_dd", "target", "crs",
                  "qa_policy", "observations_sha256"):
        _text(document.get(field), field)
    if document["target"] != "lst_c" or document["crs"] != "EPSG:32643":
        raise ValidationEvidenceError("target must be lst_c and CRS must be EPSG:32643")
    label = document.get("evidence_label")
    if label not in {REAL_LABEL, SYNTHETIC_LABEL}:
        raise ValidationEvidenceError("evidence_label must explicitly identify real or synthetic observations")
    if label == SYNTHETIC_LABEL and not synthetic_allowed:
        raise ValidationEvidenceError("Synthetic observations require --allow-synthetic and cannot be real evidence")
    _sha(document["observations_sha256"], "observations_sha256")
    season_start = document["season_start_mm_dd"]
    season_end = document["season_end_mm_dd"]
    try:
        datetime.strptime(f"2000-{season_start}", "%Y-%m-%d")
        datetime.strptime(f"2000-{season_end}", "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationEvidenceError("season_start_mm_dd and season_end_mm_dd must use MM-DD") from exc
    if season_start > season_end:
        raise ValidationEvidenceError("Season date range cannot wrap across a calendar year")
    source = document.get("source")
    if not isinstance(source, dict):
        raise ValidationEvidenceError("source provenance is required")
    for field in ("organization", "product", "url_or_identifier", "license", "access_date"):
        _text(source.get(field), f"source.{field}")
    if _date(source["access_date"], "source.access_date") > date.today():
        raise ValidationEvidenceError("source.access_date cannot be in the future")
    if label == REAL_LABEL:
        provenance_text = " ".join(str(source.get(field, "")) for field in
                                   ("organization", "product", "url_or_identifier")).lower()
        if "synthetic" in provenance_text or "demo" in provenance_text:
            raise ValidationEvidenceError("Synthetic/demo provenance cannot be labelled as real observations")
    periods = document.get("periods")
    if not isinstance(periods, list) or not periods:
        raise ValidationEvidenceError("periods must be a nonempty array")
    ids: set[str] = set()
    phases = []
    overpasses = []
    clean_periods = []
    for period in periods:
        if not isinstance(period, dict):
            raise ValidationEvidenceError("Each period must be an object")
        period_id = _text(period.get("period_id"), "period_id")
        if period_id in ids:
            raise ValidationEvidenceError(f"Duplicate period_id: {period_id}")
        ids.add(period_id)
        phase = period.get("phase")
        if phase not in {"pre", "post"}:
            raise ValidationEvidenceError(f"{period_id}: phase must be pre or post")
        phases.append(phase)
        acquired = _date(period.get("acquisition_date"), f"{period_id}.acquisition_date")
        month_day = acquired.strftime("%m-%d")
        if not season_start <= month_day <= season_end:
            raise ValidationEvidenceError(f"{period_id}: acquisition date is outside the declared season")
        if period.get("season") != document["season"]:
            raise ValidationEvidenceError(f"{period_id}: season does not match dataset season")
        overpasses.append(_minutes(period.get("overpass_time_local"), f"{period_id}.overpass_time_local"))
        for field in ("scene_id", "qa_criteria"):
            _text(period.get(field), f"{period_id}.{field}")
        _sha(period.get("scene_checksum_sha256"), f"{period_id}.scene_checksum_sha256")
        clean_periods.append({**period, "acquisition_date": acquired.isoformat()})
    if phases.count("pre") < 2 or phases.count("post") < 1:
        raise ValidationEvidenceError("At least two pre periods and one post period are required")
    tolerance = document.get("overpass_tolerance_minutes")
    if not isinstance(tolerance, int) or tolerance < 0:
        raise ValidationEvidenceError("overpass_tolerance_minutes must be a nonnegative integer")
    if max(overpasses) - min(overpasses) > tolerance:
        raise ValidationEvidenceError("Scene overpass times exceed the declared tolerance")
    controls = document.get("control_selection")
    if not isinstance(controls, dict):
        raise ValidationEvidenceError("control_selection diagnostics plan is required")
    for field in ("method", "eligibility_rule"):
        _text(controls.get(field), f"control_selection.{field}")
    for field in ("spillover_distance_m", "spatial_autocorrelation_distance_m",
                  "parallel_trends_max_abs_slope_difference_c_per_period"):
        value = document.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValidationEvidenceError(f"{field} must be a finite nonnegative number")
    predictions = document.get("predictions", [])
    if not isinstance(predictions, list):
        raise ValidationEvidenceError("predictions must be an array")
    prediction_map: dict[str, dict] = {}
    for item in predictions:
        grid_id = _text(item.get("grid_id"), "prediction.grid_id")
        if grid_id in prediction_map:
            raise ValidationEvidenceError(f"Duplicate prediction for grid cell {grid_id}")
        try:
            value = float(item["predicted_delta_lst_c"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationEvidenceError(f"{grid_id}: invalid predicted_delta_lst_c") from exc
        if not math.isfinite(value):
            raise ValidationEvidenceError(f"{grid_id}: predicted_delta_lst_c must be finite")
        prediction_map[grid_id] = {**item, "predicted_delta_lst_c": value}
    if predictions:
        model = document.get("prediction_model")
        if not isinstance(model, dict):
            raise ValidationEvidenceError("prediction_model provenance is required with predictions")
        _text(model.get("dataset_version"), "prediction_model.dataset_version")
        _sha(model.get("model_checksum_sha256"), "prediction_model.model_checksum_sha256")
    return clean_periods, prediction_map


def import_validation_dataset(manifest_path: Path, observations_path: Path, grid_path: Path,
                              output_root: Path, *, allow_synthetic: bool = False) -> Path:
    """Validate and atomically import a real or explicitly synthetic observation dataset."""
    try:
        document = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationEvidenceError(f"Cannot read validation manifest: {manifest_path}") from exc
    if not isinstance(document, dict):
        raise ValidationEvidenceError("Validation manifest must be a JSON object")
    periods, prediction_map = _validate_manifest(document, synthetic_allowed=allow_synthetic)
    observations_path = Path(observations_path)
    if not observations_path.is_file():
        raise ValidationEvidenceError(f"Observation CSV is missing: {observations_path}")
    expected_hash = _sha(document["observations_sha256"], "observations_sha256")
    if sha256_file(observations_path) != expected_hash:
        raise ValidationEvidenceError("Observation CSV checksum does not match the manifest")
    grid = _load_grid(Path(grid_path))
    expected_periods = {item["period_id"] for item in periods}
    cells: dict[str, dict[str, str]] = defaultdict(dict)
    groups: dict[str, str] = {}
    rows: list[dict] = []
    with observations_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = sorted(REQUIRED_OBSERVATION_COLUMNS - set(reader.fieldnames or []))
        if missing:
            raise ValidationEvidenceError(f"Observation CSV is missing columns: {', '.join(missing)}")
        for line, raw in enumerate(reader, start=2):
            grid_id = _text(raw.get("grid_id"), f"row {line}.grid_id")
            group = raw.get("group")
            period_id = raw.get("period_id")
            if group not in {"treated", "control"} or period_id not in expected_periods:
                raise ValidationEvidenceError(f"row {line}: invalid group or period_id")
            if period_id in cells[grid_id]:
                raise ValidationEvidenceError(f"Duplicate cell-period observation: {grid_id}/{period_id}")
            if grid_id in groups and groups[grid_id] != group:
                raise ValidationEvidenceError(f"Grid cell {grid_id} cannot change treatment group")
            if grid_id not in grid:
                raise ValidationEvidenceError(f"Grid cell is absent from the verified reference grid: {grid_id}")
            try:
                lst = float(raw["lst_c"]); x = float(raw["x"]); y = float(raw["y"])
            except (TypeError, ValueError) as exc:
                raise ValidationEvidenceError(f"row {line}: LST/x/y must be numeric") from exc
            if not all(math.isfinite(item) for item in (lst, x, y)) or not -100 <= lst <= 100:
                raise ValidationEvidenceError(f"row {line}: invalid LST or coordinate")
            gx, gy = grid[grid_id]
            if abs(x - gx) > 0.01 or abs(y - gy) > 0.01:
                raise ValidationEvidenceError(f"{grid_id}: coordinates do not match the verified grid")
            if str(raw["qa_valid"]).strip().lower() not in {"true", "1", "yes"}:
                raise ValidationEvidenceError(f"{grid_id}/{period_id}: observation failed declared QA")
            ndvi = raw.get("ndvi", "").strip()
            clean = {"grid_id": grid_id, "group": group, "period_id": period_id,
                     "lst_c": lst, "x": x, "y": y, "qa_valid": True,
                     "ndvi": None if ndvi == "" else float(ndvi)}
            if clean["ndvi"] is not None and not -1 <= clean["ndvi"] <= 1:
                raise ValidationEvidenceError(f"{grid_id}/{period_id}: NDVI must be within -1 to 1")
            rows.append(clean); groups[grid_id] = group; cells[grid_id][period_id] = group
    if not rows or "treated" not in groups.values() or "control" not in groups.values():
        raise ValidationEvidenceError("At least one treated and one control cell are required")
    for grid_id, observed in cells.items():
        if set(observed) != expected_periods:
            missing = sorted(expected_periods - set(observed))
            raise ValidationEvidenceError(f"Grid cell {grid_id} is missing periods: {', '.join(missing)}")
    treated = {grid_id for grid_id, group in groups.items() if group == "treated"}
    if prediction_map and set(prediction_map) != treated:
        raise ValidationEvidenceError("Predictions must match every treated grid ID exactly")
    dataset_id = _text(document["dataset_id"], "dataset_id")
    if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in dataset_id):
        raise ValidationEvidenceError("dataset_id may contain only letters, numbers, hyphens, and underscores")
    destination = Path(output_root) / dataset_id
    grid_hash = sha256_file(Path(grid_path))
    existing_path = destination / "manifest.json"
    if existing_path.is_file():
        try:
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationEvidenceError(f"Existing imported dataset is unreadable: {destination}") from exc
        identity = ("dataset_version", "observations_sha256", "reference_grid_sha256")
        candidate = {**document, "reference_grid_sha256": grid_hash}
        if any(existing.get(field) != candidate.get(field) for field in identity):
            raise ValidationEvidenceError(
                f"Dataset ID {dataset_id} already exists with different version or evidence hashes")
        return destination
    destination.mkdir(parents=True, exist_ok=False)
    saved_observations = destination / "observations.csv"
    shutil.copyfile(observations_path, saved_observations)
    imported = {
        **document, "periods": periods,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "reference_grid_sha256": grid_hash,
        "reference_grid_path": str(Path(grid_path).resolve()),
        "observation_rows": len(rows), "grid_cell_count": len(cells),
        "treated_cell_count": len(treated), "control_cell_count": len(cells) - len(treated),
        "import_status": "validated_synthetic_fixture" if document["evidence_label"] == SYNTHETIC_LABEL else "validated_real_observations",
    }
    _atomic_json(destination / "manifest.json", imported)
    return destination


def _read_imported(dataset_dir: Path) -> tuple[dict, list[dict]]:
    manifest_path = Path(dataset_dir) / "manifest.json"
    observations_path = Path(dataset_dir) / "observations.csv"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationEvidenceError(f"Cannot read imported manifest: {manifest_path}") from exc
    _validate_manifest(manifest, synthetic_allowed=True)
    if sha256_file(observations_path) != manifest.get("observations_sha256"):
        raise ValidationEvidenceError("Imported observations are missing or checksum-mismatched")
    grid_path = Path(manifest.get("reference_grid_path", ""))
    if not grid_path.is_file() or sha256_file(grid_path) != manifest.get("reference_grid_sha256"):
        raise ValidationEvidenceError("Verified reference grid is missing or checksum-mismatched")
    rows = []
    with observations_path.open(encoding="utf-8-sig", newline="") as stream:
        for raw in csv.DictReader(stream):
            rows.append({**raw, "lst_c": float(raw["lst_c"]), "x": float(raw["x"]),
                         "y": float(raw["y"]), "ndvi": None if not raw.get("ndvi") else float(raw["ndvi"])})
    return manifest, rows


def _slope(values: list[float]) -> float:
    return float(np.polyfit(np.arange(len(values), dtype=float), np.asarray(values), 1)[0])


def _moran_i(values: np.ndarray, coords: np.ndarray, distance_m: float) -> dict:
    centered = values - values.mean()
    denominator = float(centered @ centered)
    if len(values) < 3 or denominator == 0 or distance_m <= 0:
        return {"moran_i": None, "neighbor_links": 0,
                "warning": "Spatial autocorrelation could not be estimated from this sample."}
    distances = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=2)
    weights = ((distances > 0) & (distances <= distance_m)).astype(float)
    total_weight = float(weights.sum())
    if total_weight == 0:
        return {"moran_i": None, "neighbor_links": 0,
                "warning": "No cell pairs fall within the declared autocorrelation distance."}
    value = float(len(values) / total_weight * np.sum(weights * centered[:, None] * centered[None, :]) / denominator)
    return {"moran_i": value, "neighbor_links": int(total_weight),
            "warning": ("Positive residual spatial autocorrelation may make the unadjusted confidence interval too narrow."
                        if value > 0 else None)}


def analyze_validation_dataset(dataset_dir: Path, *, output_path: Path | None = None) -> dict:
    """Analyze complete multi-period cells and write an immutable calibration proposal report."""
    manifest, rows = _read_imported(Path(dataset_dir))
    periods = sorted(manifest["periods"], key=lambda item: item["acquisition_date"])
    pre_ids = [item["period_id"] for item in periods if item["phase"] == "pre"]
    post_ids = [item["period_id"] for item in periods if item["phase"] == "post"]
    by_cell: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        if row["period_id"] in by_cell[row["grid_id"]]:
            raise ValidationEvidenceError(f"Duplicate imported observation: {row['grid_id']}/{row['period_id']}")
        by_cell[row["grid_id"]][row["period_id"]] = row
    group_ids = {group: sorted(grid_id for grid_id, values in by_cell.items()
                               if next(iter(values.values()))["group"] == group)
                 for group in ("treated", "control")}
    period_means = {group: {period["period_id"]: float(np.mean([
        by_cell[grid_id][period["period_id"]]["lst_c"] for grid_id in group_ids[group]]))
        for period in periods} for group in group_ids}
    treated_pre = [period_means["treated"][item] for item in pre_ids]
    control_pre = [period_means["control"][item] for item in pre_ids]
    treated_slope = _slope(treated_pre); control_slope = _slope(control_pre)
    slope_difference = treated_slope - control_slope
    threshold = float(manifest["parallel_trends_max_abs_slope_difference_c_per_period"])
    parallel = {"pre_period_count": len(pre_ids), "treated_slope_c_per_period": treated_slope,
                "control_slope_c_per_period": control_slope,
                "absolute_slope_difference_c_per_period": abs(slope_difference),
                "declared_threshold_c_per_period": threshold,
                "passed": abs(slope_difference) <= threshold,
                "method": "OLS slope over ordered group-mean pre-period LST; diagnostic, not a proof of parallel counterfactual trends"}
    changes = {}
    for grid_id, values in by_cell.items():
        changes[grid_id] = float(np.mean([values[item]["lst_c"] for item in post_ids])
                                 - np.mean([values[item]["lst_c"] for item in pre_ids]))
    treated_changes = np.asarray([changes[item] for item in group_ids["treated"]], dtype=float)
    control_changes = np.asarray([changes[item] for item in group_ids["control"]], dtype=float)
    did = float(treated_changes.mean() - control_changes.mean())
    if len(treated_changes) >= 2 and len(control_changes) >= 2:
        se = math.sqrt(float(treated_changes.var(ddof=1) / len(treated_changes)
                             + control_changes.var(ddof=1) / len(control_changes)))
        numerator = (treated_changes.var(ddof=1) / len(treated_changes)
                     + control_changes.var(ddof=1) / len(control_changes)) ** 2
        denominator = ((treated_changes.var(ddof=1) / len(treated_changes)) ** 2 / (len(treated_changes) - 1)
                       + (control_changes.var(ddof=1) / len(control_changes)) ** 2 / (len(control_changes) - 1))
        degrees = numerator / denominator if denominator else math.inf
        critical = float(stats.t.ppf(0.975, degrees)) if math.isfinite(degrees) else 1.96
        interval = {"method": "unadjusted Welch difference-in-means 95% confidence interval",
                    "standard_error_c": se, "degrees_of_freedom": degrees,
                    "lower_c": did - critical * se, "upper_c": did + critical * se,
                    "coverage_warning": "Does not correct for spatial autocorrelation, matching uncertainty, or scene-level dependence."}
    else:
        interval = {"method": "unavailable", "lower_c": None, "upper_c": None,
                    "coverage_warning": "At least two treated and two control cells are required for a sample-based interval."}
    treated_xy = np.asarray([[by_cell[item][pre_ids[0]]["x"], by_cell[item][pre_ids[0]]["y"]]
                             for item in group_ids["treated"]], dtype=float)
    contaminated = []
    nearest = []
    spillover = float(manifest["spillover_distance_m"])
    for grid_id in group_ids["control"]:
        row = by_cell[grid_id][pre_ids[0]]
        distance = float(np.min(np.linalg.norm(treated_xy - np.array([row["x"], row["y"]]), axis=1)))
        nearest.append(distance)
        if distance <= spillover:
            contaminated.append({"grid_id": grid_id, "nearest_treated_distance_m": distance})
    all_ids = group_ids["treated"] + group_ids["control"]
    residualized = np.asarray([changes[item] - (treated_changes.mean() if item in group_ids["treated"]
                                                else control_changes.mean()) for item in all_ids])
    coords = np.asarray([[by_cell[item][pre_ids[0]]["x"], by_cell[item][pre_ids[0]]["y"]]
                         for item in all_ids])
    spatial = _moran_i(residualized, coords, float(manifest["spatial_autocorrelation_distance_m"]))
    pre_cell_t = np.asarray([np.mean([by_cell[item][period]["lst_c"] for period in pre_ids])
                             for item in group_ids["treated"]])
    pre_cell_c = np.asarray([np.mean([by_cell[item][period]["lst_c"] for period in pre_ids])
                             for item in group_ids["control"]])
    pooled = math.sqrt(((len(pre_cell_t) - 1) * pre_cell_t.var(ddof=1)
                        + (len(pre_cell_c) - 1) * pre_cell_c.var(ddof=1))
                       / max(1, len(pre_cell_t) + len(pre_cell_c) - 2)) if min(len(pre_cell_t), len(pre_cell_c)) > 1 else 0
    smd = float((pre_cell_t.mean() - pre_cell_c.mean()) / pooled) if pooled else None
    predictions = {item["grid_id"]: float(item["predicted_delta_lst_c"])
                   for item in manifest.get("predictions", [])}
    residual_rows = []
    if predictions:
        control_change = float(control_changes.mean())
        for grid_id in group_ids["treated"]:
            adjusted = changes[grid_id] - control_change
            residual_rows.append({"grid_id": grid_id, "predicted_delta_lst_c": predictions[grid_id],
                                  "control_adjusted_observed_delta_lst_c": adjusted,
                                  "residual_c": adjusted - predictions[grid_id]})
    residuals = np.asarray([item["residual_c"] for item in residual_rows])
    performance = None if not len(residuals) else {
        "count": len(residuals), "mean_residual_c": float(residuals.mean()),
        "mae_c": float(np.mean(np.abs(residuals))), "rmse_c": float(np.sqrt(np.mean(residuals ** 2))),
        "definition": "control-adjusted observed ΔLST minus predicted ΔLST",
    }
    real = manifest["evidence_label"] == REAL_LABEL
    diagnostics_pass = parallel["passed"] and not contaminated
    status = "READY_FOR_HUMAN_REVIEW" if real and diagnostics_pass else "BLOCKED"
    proposal = None
    if status == "READY_FOR_HUMAN_REVIEW":
        proposal = {
            "status": "PROPOSED_NOT_ADOPTED", "parameter": "modeled_marginal_cooling_c",
            "proposed_value": max(0.0, -did), "unit": "°C",
            "basis": "descriptive control-adjusted multi-period LST estimate",
            "requires_human_approval": True,
            "warning": "Proposal is not causal and must not overwrite production assumptions automatically.",
        }
    report = {
        "report_schema_version": REPORT_VERSION,
        "report_id": f"{manifest['dataset_id']}--{manifest['dataset_version']}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "validation_status": status, "evidence_label": manifest["evidence_label"],
        "dataset_id": manifest["dataset_id"], "dataset_version": manifest["dataset_version"],
        "location_id": manifest["location_id"], "intervention_id": manifest["intervention_id"],
        "provenance": {"source": manifest["source"], "season": manifest["season"],
                       "crs": manifest["crs"], "qa_policy": manifest["qa_policy"],
                       "periods": periods, "observations_sha256": manifest["observations_sha256"],
                       "reference_grid_sha256": manifest["reference_grid_sha256"],
                       "prediction_model": manifest.get("prediction_model")},
        "sample_size": {"treated_cells": len(treated_changes), "control_cells": len(control_changes),
                        "pre_periods": len(pre_ids), "post_periods": len(post_ids),
                        "observations": len(rows)},
        "period_group_means_c": period_means,
        "treated_change_c": float(treated_changes.mean()),
        "control_change_c": float(control_changes.mean()),
        "difference_in_differences_c": did, "realized_cooling_c": -did,
        "uncertainty": interval, "parallel_trends": parallel,
        "control_diagnostics": {"selection_method": manifest["control_selection"],
                                "pre_period_lst_standardized_mean_difference": smd,
                                "nearest_treated_distance_m_min": min(nearest),
                                "nearest_treated_distance_m_median": float(np.median(nearest)),
                                "declared_spillover_distance_m": spillover,
                                "contaminated_controls": contaminated,
                                "passed": not contaminated},
        "spatial_autocorrelation": spatial,
        "prediction_comparison": residual_rows, "performance": performance,
        "calibration_proposal": proposal,
        "approval": {"status": "NOT_REQUESTED", "required_before_adoption": True},
        "limitations": [
            "Difference-in-Differences depends on an untestable counterfactual even when pre-trend diagnostics pass.",
            "The confidence interval is not spatially or scene-cluster adjusted and may be too narrow.",
            "Landsat LST is not pedestrian air temperature; nearby 30 m cells are not independent sensors.",
            "Spillover, land-cover changes, weather, acquisition differences, and control selection can confound the estimate.",
            "Synthetic fixtures are software tests and cannot calibrate production intervention parameters.",
        ],
    }
    report["report_content_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if output_path:
        _atomic_json(Path(output_path), report)
    return report


def approve_calibration_report(report_path: Path, approval_path: Path, *, approver: str,
                               decision: str, rationale: str) -> dict:
    """Record an explicit human decision; never mutate production assumptions."""
    if decision not in {"approve", "reject"}:
        raise ValidationEvidenceError("decision must be approve or reject")
    report_path = Path(report_path)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationEvidenceError(f"Cannot read calibration report: {report_path}") from exc
    if report.get("validation_status") != "READY_FOR_HUMAN_REVIEW" or not report.get("calibration_proposal"):
        raise ValidationEvidenceError("Only evidence-complete review-ready reports can be approved")
    if report.get("evidence_label") != REAL_LABEL:
        raise ValidationEvidenceError("Only explicitly real intervention evidence can be approved")
    claimed = report.get("report_content_sha256")
    unsigned = {key: value for key, value in report.items() if key != "report_content_sha256"}
    actual = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if claimed != actual:
        raise ValidationEvidenceError("Calibration report content hash is invalid")
    record = {
        "approval_schema_version": "1.0", "report_id": report["report_id"],
        "report_file_sha256": sha256_file(report_path), "report_content_sha256": report["report_content_sha256"],
        "decision": decision, "approver": _text(approver, "approver"),
        "rationale": _text(rationale, "rationale"),
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "production_assumptions_modified": False,
    }
    _atomic_json(Path(approval_path), record)
    return record


def list_imported_datasets(import_root: Path) -> dict:
    datasets = []
    root = Path(import_root)
    if root.is_dir():
        for manifest_path in sorted(root.glob("*/manifest.json")):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                datasets.append({"dataset_id": manifest["dataset_id"],
                                 "dataset_version": manifest["dataset_version"],
                                 "location_id": manifest["location_id"],
                                 "intervention_id": manifest["intervention_id"],
                                 "evidence_label": manifest["evidence_label"],
                                 "season": manifest["season"],
                                 "treated_cells": manifest["treated_cell_count"],
                                 "control_cells": manifest["control_cell_count"]})
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                continue
    real = [item for item in datasets if item["evidence_label"] == REAL_LABEL]
    return {"datasets": real, "total": len(real),
            "validation_status": "AVAILABLE" if real else "BLOCKED",
            "blocker": None if real else "No genuine imported intervention dataset is locally available."}
