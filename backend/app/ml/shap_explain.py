"""TreeSHAP descriptions of the saved continuous LST model, never causal effects."""

from __future__ import annotations

import json
import math
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq
import shap
from xgboost import XGBRegressor

from backend.app.ml.baselines import _read_ml_inputs
from backend.app.ml.xgboost_lst import _sha256

SEED = 42
REDUNDANCY_THRESHOLD = 0.85
CATEGORIES = ("Built Environment", "Vegetation / Canopy", "Surface Reflectivity",
              "Road / Infrastructure", "Other")


def feature_category(name: str) -> str:
    """Map a model feature to one display category; unknown features go to Other."""
    if name in {"ndbi", "ndbi_mean_3x3", "ndbi_mean_5x5", "built_pct", "building_fraction"}:
        return "Built Environment"
    if name in {"ndvi", "ndvi_mean_3x3", "ndvi_mean_5x5", "tree_canopy_pct",
                "distance_green_m"}:
        return "Vegetation / Canopy"
    if name == "albedo":
        return "Surface Reflectivity"
    if name == "road_density":
        return "Road / Infrastructure"
    return "Other"


def feature_correlations(matrix: np.ndarray, names: list[str],
                         threshold: float = REDUNDANCY_THRESHOLD) -> dict:
    """Calculate Pearson r on finite rows; constant columns have undefined r.

    Correlations are unitless in [-1, 1]. Invalid shapes, nonfinite inputs,
    or fewer than two rows raise ValueError. This is descriptive, not causal.
    """
    values = np.asarray(matrix, dtype=np.float64)
    if (values.ndim != 2 or values.shape[0] < 2 or values.shape[1] != len(names)
            or not np.isfinite(values).all() or len(set(names)) != len(names)
            or not 0 < threshold <= 1):
        raise ValueError("Correlation input must be a finite matrix with matching unique features")
    pairs = []
    for i, left in enumerate(names):
        for j in range(i + 1, len(names)):
            right = names[j]
            if np.std(values[:, i]) == 0 or np.std(values[:, j]) == 0:
                coefficient = None
            else:
                coefficient = float(np.corrcoef(values[:, i], values[:, j])[0, 1])
                if not math.isfinite(coefficient):
                    coefficient = None
            pairs.append({"feature_a": left, "feature_b": right, "pearson_r": coefficient,
                          "highly_redundant": coefficient is not None and abs(coefficient) >= threshold})
    pairs.sort(key=lambda pair: abs(pair["pearson_r"]) if pair["pearson_r"] is not None else -1,
               reverse=True)
    return {"method": "Pearson", "sample_rows": int(values.shape[0]),
            "absolute_r_threshold": threshold, "pairs": pairs,
            "highly_redundant_pairs": [pair for pair in pairs if pair["highly_redundant"]]}


def _load_inputs(dataset_path: Path, model_path: Path, metadata_path: Path
                 ) -> tuple[XGBRegressor, np.ndarray, list[str], np.ndarray, dict]:
    if not model_path.is_file() or not metadata_path.is_file():
        raise ValueError("Real trained XGBoost model and model metadata are required; run Step 15 first")
    _, _, _, matrix, names, dataset_metadata = _read_ml_inputs(
        dataset_path, dataset_path.with_name("metadata.json"))
    try:
        report = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot read XGBoost model metadata") from exc
    if (report.get("feature_list") != names or report.get("dataset_version") != f"sha256:{_sha256(dataset_path)}"
            or report.get("dataset_rows") != len(matrix) or report.get("crs") != dataset_metadata["crs"]
            or report.get("resolution_m") != dataset_metadata["raster_resolution_m"]
            or report.get("target") != "lst_c" or report.get("objective") != "reg:squarederror"):
        raise ValueError("Model metadata does not match the real ML dataset and continuous LST target")
    try:
        grid_ids = np.asarray(pq.read_table(dataset_path, columns=["grid_id"]).column("grid_id").to_pylist())
    except Exception as exc:
        raise ValueError("ML dataset needs a grid_id column for local explanations") from exc
    if len(grid_ids) != len(matrix) or len(set(map(str, grid_ids))) != len(grid_ids):
        raise ValueError("ML grid IDs must be present and unique")
    # joblib uses pickle: load only the artifact produced by this trusted workspace.
    model = joblib.load(model_path)
    if not isinstance(model, XGBRegressor) or model.get_params().get("objective") != "reg:squarederror":
        raise ValueError("Saved artifact must be an XGBoost continuous LST regressor")
    if model.n_features_in_ != len(names):
        raise ValueError("Saved model feature count differs from ML metadata")
    return model, matrix, names, grid_ids, report


def _shap_values(model: XGBRegressor, matrix: np.ndarray) -> tuple[float, np.ndarray]:
    """Compute path-dependent TreeSHAP in model-output units (LST °C)."""
    explainer = shap.TreeExplainer(model, model_output="raw",
                                  feature_perturbation="tree_path_dependent")
    values = np.asarray(explainer.shap_values(matrix, check_additivity=True), dtype=np.float64)
    baseline = float(np.asarray(explainer.expected_value).reshape(-1)[0])
    predictions = np.asarray(model.predict(matrix), dtype=np.float64)
    if (values.shape != matrix.shape or not np.isfinite(values).all() or not math.isfinite(baseline)
            or not np.allclose(baseline + values.sum(axis=1), predictions, rtol=1e-5, atol=1e-3)):
        raise ValueError("TreeSHAP additivity or output shape check failed")
    return baseline, values


def explain_saved_model(dataset_path: Path, model_path: Path, metadata_path: Path,
                        grid_id: str, output_dir: Path, sample_size: int = 2000) -> tuple[dict, dict]:
    """Write global and one-cell TreeSHAP JSON/plots from the matching real model.

    Global mean absolute contributions and local contributions use °C. The
    deterministic sample has at most sample_size cells. A missing real model,
    dataset mismatch, unknown grid ID, or invalid sample size stops processing.
    """
    if isinstance(sample_size, bool) or sample_size < 2:
        raise ValueError("sample_size must be at least 2")
    model, matrix, names, grid_ids, report = _load_inputs(dataset_path, model_path, metadata_path)
    matches = np.flatnonzero(np.asarray([str(value) == str(grid_id) for value in grid_ids]))
    if len(matches) != 1:
        raise ValueError(f"grid_id was not found exactly once: {grid_id}")
    local_index = int(matches[0])
    rng = np.random.default_rng(SEED)
    sample_indices = np.sort(rng.choice(len(matrix), size=min(sample_size, len(matrix)), replace=False))
    sample = matrix[sample_indices]

    # Calculate correlations before assigning category-level display summaries.
    correlations = feature_correlations(sample, names)
    baseline, global_values = _shap_values(model, sample)
    local_baseline, local_values = _shap_values(model, matrix[local_index:local_index + 1])
    if not np.isclose(baseline, local_baseline, atol=1e-5):
        raise ValueError("Global and local TreeSHAP baselines differ")
    local_phi = local_values[0]
    prediction = float(model.predict(matrix[local_index:local_index + 1])[0])
    mean_abs = np.mean(np.abs(global_values), axis=0)
    bars = sorted(({"feature": name, "category": feature_category(name),
                    "mean_abs_shap_c": float(mean_abs[i])} for i, name in enumerate(names)),
                  key=lambda item: item["mean_abs_shap_c"], reverse=True)
    group_importance = [{"category": category,
                         "sum_feature_mean_abs_shap_c": float(sum(
                             item["mean_abs_shap_c"] for item in bars if item["category"] == category))}
                        for category in CATEGORIES]
    warning = ("Strongly correlated predictors can split or exchange SHAP credit; individual and grouped "
               "importance may change with the feature set, fitted trees, and dependence assumption. "
               "SHAP describes this model's predictions and does not establish causation.")
    global_report = {
        "label": "REAL DATA MODEL EXPLANATION", "method": "TreeSHAP tree_path_dependent raw regression output",
        "target": "LST", "unit": "°C", "model_dataset_version": report["dataset_version"],
        "dataset_rows": int(len(matrix)), "sample_rows": int(len(sample)), "sample_seed": SEED,
        "baseline_lST": baseline, "feature_correlations": correlations,
        "feature_importance_bar_data": bars, "group_importance_bar_data": group_importance,
        "redundancy_warning": warning, "scientific_limit": "SHAP is model attribution, not a causal intervention estimate. LST is not pedestrian air temperature."
    }
    positive_total = float(np.sum(local_phi[local_phi > 0]))
    feature_rows = []
    for i, name in enumerate(names):
        phi = float(local_phi[i])
        feature_rows.append({"feature": name, "category": feature_category(name),
                             "raw_value": float(matrix[local_index, i]), "shap_value_c": phi,
                             "direction": "warming" if phi > 0 else "cooling" if phi < 0 else "neutral",
                             "warming_percentage_ui": 100.0 * phi / positive_total if phi > 0 and positive_total > 0 else 0.0})
    feature_rows.sort(key=lambda item: abs(item["shap_value_c"]), reverse=True)
    running = baseline
    waterfall = []
    for row in feature_rows:
        end = running + row["shap_value_c"]
        waterfall.append({**row, "start_c": running, "end_c": end})
        running = end
    if not np.isclose(running, prediction, rtol=1e-5, atol=1e-3):
        raise ValueError("Local waterfall does not reconstruct the model prediction")
    local_groups = [{"category": category,
                     "shap_value_c": float(sum(row["shap_value_c"] for row in feature_rows
                                                if row["category"] == category))}
                    for category in CATEGORIES]
    local_report = {
        "label": "REAL DATA MODEL EXPLANATION", "grid_id": str(grid_ids[local_index]),
        "baseline_lST": baseline, "predicted_lst": prediction,
        "unit": "°C", "features": feature_rows, "waterfall_data": waterfall,
        "bar_chart_data": feature_rows, "group_contributions": local_groups,
        "warming_percentage_denominator_c": positive_total,
        "redundancy_warning": warning if correlations["highly_redundant_pairs"] else None,
        "scientific_limit": "Feature contributions explain this fitted LST prediction; they are not causal temperature changes."
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "shap_global.json").write_text(json.dumps(global_report, indent=2), encoding="utf-8")
    (output_dir / "shap_local.json").write_text(json.dumps(local_report, indent=2), encoding="utf-8")
    _plot_global(bars, output_dir / "shap_global_importance.png")
    _plot_local(waterfall, output_dir / "shap_local_waterfall.png")
    return global_report, local_report


def _plot_global(bars: list[dict], path: Path) -> None:
    """Save a descriptive global mean-absolute-SHAP bar plot in °C."""
    fig, ax = plt.subplots(figsize=(9, max(4, len(bars) * 0.4)))
    ax.barh([row["feature"] for row in reversed(bars)],
            [row["mean_abs_shap_c"] for row in reversed(bars)], color="#287a5a")
    ax.set_xlabel("Mean absolute TreeSHAP contribution (°C)")
    ax.set_title("LST model feature importance (sampled grid cells)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_local(waterfall: list[dict], path: Path) -> None:
    """Save the signed local waterfall contributions in LST °C."""
    fig, ax = plt.subplots(figsize=(9, max(4, len(waterfall) * 0.4)))
    rows = list(reversed(waterfall))
    for i, row in enumerate(rows):
        ax.barh(i, row["shap_value_c"], left=row["start_c"],
                color="#c46542" if row["shap_value_c"] > 0 else "#287a5a")
    ax.set_yticks(range(len(rows)), [row["feature"] for row in rows])
    ax.set_xlabel("Model LST prediction (°C)")
    ax.set_title("One grid cell: signed TreeSHAP contributions")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
