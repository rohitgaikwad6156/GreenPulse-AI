"""Tree-canopy what-if re-prediction with the saved XGBoost LST model."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from xgboost import XGBRegressor

from .config import TreeCanopyAssumptions, tree_canopy_assumptions_from_env


class SimulationUnavailableError(ValueError):
    """The trusted real model or matching real feature table is unavailable."""


def assess_training_support(baseline: dict[str, float], scenario: dict[str, float],
                            distributions: dict | None) -> dict:
    """Reject extrapolation beyond training extrema and flag p01/p99 tails."""
    if distributions is None:
        return {"status": "not_checked", "is_ood": None, "warnings": [],
                "policy": "Training-distribution metadata was not supplied to this low-level call"}
    if set(distributions) != set(baseline) or set(scenario) != set(baseline):
        raise ValueError("Training feature distributions do not match the model feature vector")
    warnings = []
    for name in baseline:
        stats = distributions.get(name)
        if (not isinstance(stats, dict)
                or any(not isinstance(stats.get(key), (int, float)) or not math.isfinite(float(stats[key]))
                       for key in ("min", "p01", "p99", "max"))
                or not float(stats["min"]) <= float(stats["p01"]) <= float(stats["p99"]) <= float(stats["max"])):
            raise ValueError(f"Training distribution metadata is invalid for feature: {name}")
        for vector_name, value in (("baseline", baseline[name]), ("scenario", scenario[name])):
            if value < float(stats["min"]) - 1e-12 or value > float(stats["max"]) + 1e-12:
                raise ValueError(f"{vector_name} feature {name}={value:g} is outside observed training support [{stats['min']:g}, {stats['max']:g}]")
        if scenario[name] < float(stats["p01"]) or scenario[name] > float(stats["p99"]):
            warnings.append({"feature": name, "scenario_value": scenario[name],
                             "typical_training_range": [float(stats["p01"]), float(stats["p99"])],
                             "message": f"{name} is inside training extrema but outside the training p01–p99 range"})
    return {"status": "within_training_bounds_but_ood_warning" if warnings else "within_typical_training_range",
            "is_ood": bool(warnings), "warnings": warnings,
            "policy": "Modified features outside training min/max are rejected; p01/p99 tail values are prominently flagged"}


def _resolve_capacity(requested: float | None, metadata: dict, key: str, label: str) -> tuple[float, dict]:
    calculated = metadata.get("_selected_capacity", {}).get(key)
    if requested is None:
        if calculated is None:
            raise ValueError(f"{label} is required because no verified spatial capacity is available for this cell")
        return float(calculated["value_m2"]), {"source_type": "calculated_verified_spatial_input", **calculated}
    try:
        value = float(requested)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if calculated is not None and value > float(calculated["value_m2"]) + 1e-9:
        raise ValueError(f"User-supplied {label} exceeds the verified spatial capacity")
    source = {"source_type": "user_supplied", "value_m2": value,
              "verification_status": "not_independently_verified_by_api"}
    if calculated is not None:
        source.update({"source_type": "user_supplied_with_verified_upper_bound",
                       "verified_upper_bound_m2": float(calculated["value_m2"]),
                       "verified_source": calculated["source"], "verified_source_sha256": calculated["source_sha256"]})
    return value, source


def simulate_tree_canopy(model: XGBRegressor, feature_names: list[str],
                         baseline_features: dict[str, float], canopy_increase_pp: float,
                         feasible_ground_area_m2: float,
                         assumptions: TreeCanopyAssumptions | None = None,
                         training_distributions: dict | None = None) -> dict:
    """Modify one 30 m feature vector and re-run XGBoost twice.

    Inputs: canopy increase in absolute percentage points (0–40 by default),
    additional verified plantable ground area in m² (0–900), and finite model
    features in their training order. Returns LST predictions and signed
    change in °C; cooling magnitude cannot be negative. Invalid or infeasible
    interventions raise ValueError instead of being silently clamped.
    """
    assumptions = assumptions or tree_canopy_assumptions_from_env()
    if not isinstance(model, XGBRegressor) or model.get_params().get("objective") != "reg:squarederror":
        raise ValueError("Tree simulation requires the fitted XGBoost LST regressor")
    if (not isinstance(feature_names, list) or len(feature_names) != len(set(feature_names))
            or "tree_canopy_pct" not in feature_names or "ndvi" not in feature_names
            or model.n_features_in_ != len(feature_names)
            or set(feature_names) != set(baseline_features)):
        raise ValueError("Feature vector must exactly match the trained model and contain canopy and NDVI")
    try:
        increase = float(canopy_increase_pp)
        feasible = float(feasible_ground_area_m2)
        base = {name: float(baseline_features[name]) for name in feature_names}
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("Scenario inputs and model features must be numeric") from exc
    if (not math.isfinite(increase) or not math.isfinite(feasible)
            or not all(math.isfinite(value) for value in base.values())
            or not 0 <= increase <= assumptions.max_canopy_increase_pp
            or not 0 <= feasible <= assumptions.cell_area_m2
            or not 0 <= base["tree_canopy_pct"] <= 100
            or not assumptions.ndvi_min <= base["ndvi"] <= assumptions.ndvi_max):
        raise ValueError("Canopy, NDVI, slider value, and feasible ground area are outside valid ranges")
    requested_new_canopy = base["tree_canopy_pct"] + increase
    required_area = assumptions.cell_area_m2 * increase / 100.0
    if requested_new_canopy > 100 + 1e-9:
        raise ValueError("New tree canopy would exceed 100% of the grid cell")
    if required_area > feasible + 1e-9:
        raise ValueError("Requested tree canopy area exceeds verified feasible ground area")

    modified = base.copy()
    modified["tree_canopy_pct"] = min(100.0, requested_new_canopy)
    ndvi_requested = increase * assumptions.ndvi_per_canopy_percentage_point
    modified["ndvi"] = min(assumptions.ndvi_max, max(assumptions.ndvi_min,
                                                    base["ndvi"] + ndvi_requested))
    actual_ndvi_change = modified["ndvi"] - base["ndvi"]
    # A one-cell NDVI change contributes to a complete 3x3/5x5 focal mean.
    # Effective valid-cell counts are explicit MVP assumptions, not measured.
    for name, count in (("ndvi_mean_3x3", assumptions.focal_3x3_valid_cells),
                        ("ndvi_mean_5x5", assumptions.focal_5x5_valid_cells)):
        if name in modified:
            modified[name] = min(assumptions.ndvi_max, max(assumptions.ndvi_min,
                                 base[name] + actual_ndvi_change / count))
    support = assess_training_support(base, modified, training_distributions)
    base_vector = np.array([[base[name] for name in feature_names]], dtype=np.float64)
    scenario_vector = np.array([[modified[name] for name in feature_names]], dtype=np.float64)
    predictions = np.asarray(model.predict(np.vstack([base_vector, scenario_vector])), dtype=np.float64)
    if predictions.shape != (2,) or not np.isfinite(predictions).all():
        raise ValueError("XGBoost returned invalid LST predictions")
    baseline_lst, scenario_lst = map(float, predictions)
    delta = scenario_lst - baseline_lst
    changed = {name: {"baseline": base[name], "scenario": modified[name]}
               for name in feature_names if modified[name] != base[name]}
    return {
        "label": "MODEL WHAT-IF ESTIMATE — NOT OBSERVED COOLING",
        "target": "land_surface_temperature", "unit": "°C",
        "baseline_lst_c": baseline_lst, "scenario_lst_c": scenario_lst,
        "delta_lst_c": delta, "cooling_magnitude_c": max(0.0, -delta),
        "canopy_increase_percentage_points": increase,
        "additional_canopy_area_m2": required_area,
        "feasible_ground_area_m2": feasible,
        "modified_features": changed,
        "scenario_features": modified,
        "training_support": support,
        "assumptions": {
            "label": assumptions.assumption_label,
            "cell_area_m2": assumptions.cell_area_m2,
            "max_canopy_increase_percentage_points": assumptions.max_canopy_increase_pp,
            "ndvi_per_canopy_percentage_point": assumptions.ndvi_per_canopy_percentage_point,
            "focal_3x3_valid_cells": assumptions.focal_3x3_valid_cells,
            "focal_5x5_valid_cells": assumptions.focal_5x5_valid_cells,
            "ndvi_requested_change": ndvi_requested,
            "ndvi_actual_change_after_clipping": actual_ndvi_change,
            "evidence_status": assumptions.evidence_status,
            "provenance": {"canopy_to_ndvi": assumptions.coefficient_source,
                           "growth_horizon": assumptions.growth_horizon_source,
                           "survival": assumptions.survival_source},
            "other_features": "held fixed, including NDBI and built fraction; no uncalibrated cross-feature change",
            "feasible_area": "must be externally verified plantable ground, excluding existing canopy",
            "limitations": "Model sensitivity is not a causal or validated intervention effect; canopy growth, survival, shade, and adjacent-cell spillover are not modelled. LST is not pedestrian air temperature."
        }
    }


def simulate_saved_grid_cell(dataset_path: Path, model_path: Path, metadata_path: Path,
                             grid_id: str, canopy_increase_pp: float,
                             feasible_ground_area_m2: float | None,
                             assumptions: TreeCanopyAssumptions | None = None) -> dict:
    """Load a matching trusted saved model and one real cell, then simulate.

    Raises SimulationUnavailableError if model/table files are missing.
    Raises ValueError for stale metadata, unknown IDs, or invalid scenarios.
    """
    model, names, features, metadata = load_saved_grid_cell(
        dataset_path, model_path, metadata_path, grid_id)
    feasible, feasibility = _resolve_capacity(
        feasible_ground_area_m2, metadata, "plantable_ground_m2", "plantable ground area")
    report = simulate_tree_canopy(model, names, features, canopy_increase_pp,
                                  feasible, assumptions, metadata["training_feature_distributions"])
    report["grid_id"] = str(grid_id)
    report["model_dataset_version"] = metadata["dataset_version"]
    report["feasibility"] = {"plantable_ground": feasibility}
    return report


def load_saved_grid_cell(dataset_path: Path, model_path: Path, metadata_path: Path,
                         grid_id: str) -> tuple[XGBRegressor, list[str], dict[str, float], dict]:
    """Read the model and one grid row after dataset-version and schema checks."""
    dataset_metadata_path = dataset_path.with_name("metadata.json")
    for path in (dataset_path, dataset_metadata_path, model_path, metadata_path):
        if not path.is_file():
            raise SimulationUnavailableError(f"Required real model or grid data is missing: {path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        dataset_metadata = json.loads(dataset_metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot read model or dataset metadata") from exc
    names = metadata.get("feature_list")
    hasher = hashlib.sha256()
    with dataset_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    digest = hasher.hexdigest()
    distributions = metadata.get("training_feature_distributions")
    if (not isinstance(names, list) or not names
            or metadata.get("dataset_version") != f"sha256:{digest}"
            or metadata.get("target") != "lst_c"
            or metadata.get("objective") != "reg:squarederror"
            or metadata.get("dataset_rows") != dataset_metadata.get("row_count")
            or names != dataset_metadata.get("features")
            or metadata.get("crs") != dataset_metadata.get("crs")
            or metadata.get("resolution_m") != dataset_metadata.get("raster_resolution_m")
            or metadata.get("dataset_date_range") != dataset_metadata.get("date_range")
            or not isinstance(distributions, dict) or set(distributions) != set(names)):
        raise ValueError("Saved XGBoost model metadata does not match the real grid dataset")
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if metadata.get("model_artifact_sha256") != f"sha256:{model_hash}":
        raise ValueError("Saved XGBoost model artifact hash does not match model metadata")
    capacity_columns = []
    capacity_contract = dataset_metadata.get("capacity_fields", {})
    for key in ("plantable_ground_m2", "eligible_roof_area_m2"):
        entry = capacity_contract.get(key)
        checksum = entry.get("source_sha256") if isinstance(entry, dict) else None
        if (isinstance(entry, dict) and entry.get("verification_status") == "verified"
                and isinstance(entry.get("source"), str) and entry["source"].strip()
                and isinstance(entry.get("method"), str) and entry["method"].strip()
                and isinstance(checksum, str) and len(checksum) == 71 and checksum.startswith("sha256:")
                and all(character in "0123456789abcdef" for character in checksum[7:])):
            capacity_columns.append(key)
    try:
        table = pq.read_table(dataset_path, columns=["grid_id", *names, *capacity_columns])
    except (OSError, KeyError, pa.ArrowException) as exc:
        raise ValueError("Cannot read grid IDs and model feature columns") from exc
    if table.num_rows != metadata["dataset_rows"]:
        raise ValueError("Grid table row count differs from model metadata")
    ids = [str(value) for value in table.column("grid_id").to_pylist()]
    indices = [index for index, value in enumerate(ids) if value == str(grid_id)]
    if len(indices) != 1:
        raise ValueError("Selected grid_id was not found exactly once")
    row = indices[0]
    try:
        features = {name: float(table.column(name)[row].as_py()) for name in names}
    except (TypeError, ValueError) as exc:
        raise ValueError("Selected grid cell has invalid model features") from exc
    selected_capacity = {}
    for key in capacity_columns:
        value = table.column(key)[row].as_py()
        if value is not None and math.isfinite(float(value)) and 0 <= float(value) <= 900:
            selected_capacity[key] = {"value_m2": float(value),
                                      "source": capacity_contract[key]["source"],
                                      "source_sha256": capacity_contract[key]["source_sha256"],
                                      "method": capacity_contract[key]["method"],
                                      "verification_status": "verified"}
    metadata = {**metadata, "_selected_capacity": selected_capacity}
    # joblib/pickle is trusted only for the model produced in this workspace.
    model = joblib.load(model_path)
    if not isinstance(model, XGBRegressor) or model.get_params().get("objective") != "reg:squarederror":
        raise ValueError("Saved artifact must be an XGBoost LST regressor")
    if model.n_features_in_ != len(names):
        raise ValueError("Saved model feature count differs from metadata")
    return model, names, features, metadata
