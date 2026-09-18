"""Spatially evaluated LST regression baselines; no risk categories."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import sklearn
from sklearn.base import clone
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeRegressor

from backend.app.ml.spatial_cv import SpatialBlockCV, load_cv_assignment, summarize_blocks

TARGET = "lst_c"
RANDOM_STATE = 42
TREE_MAX_DEPTH = 16
MIN_SAMPLES_LEAF = 5


def regression_metrics(y_true: object, y_pred: object) -> dict[str, float]:
    """Calculate MAE, RMSE (°C) and held-out R² from their exact formulas.

    Requires at least two finite observed/predicted values and nonzero
    observed variance; otherwise R² is undefined and evaluation stops.
    """
    try:
        observed = np.asarray(y_true, dtype=np.float64)
        predicted = np.asarray(y_pred, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("Regression metrics require numeric arrays") from exc
    if (observed.ndim != 1 or predicted.ndim != 1 or observed.shape != predicted.shape
            or observed.size < 2 or not np.isfinite(observed).all()
            or not np.isfinite(predicted).all()):
        raise ValueError("Regression metrics require at least two matching finite observations and predictions")
    error = observed - predicted
    denominator = float(np.sum((observed - observed.mean()) ** 2))
    if denominator <= 0:
        raise ValueError("Held-out R² is undefined because validation LST has zero variance")
    return {"mae_c": float(np.mean(np.abs(error))),
            "rmse_c": float(np.sqrt(np.mean(error ** 2))),
            "r2": float(1 - np.sum(error ** 2) / denominator)}


def _estimators(rf_trees: int, rf_jobs: int) -> dict:
    if isinstance(rf_trees, bool) or not isinstance(rf_trees, int) or rf_trees < 1:
        raise ValueError("rf_trees must be a positive integer")
    if isinstance(rf_jobs, bool) or not isinstance(rf_jobs, int) or rf_jobs < 1:
        raise ValueError("rf_jobs must be a positive integer")
    return {
        "linear_regression": make_pipeline(StandardScaler(), LinearRegression()),
        "decision_tree": DecisionTreeRegressor(max_depth=TREE_MAX_DEPTH,
                                                min_samples_leaf=MIN_SAMPLES_LEAF,
                                                random_state=RANDOM_STATE),
        "random_forest": RandomForestRegressor(n_estimators=rf_trees,
                                               max_depth=TREE_MAX_DEPTH,
                                               min_samples_leaf=MIN_SAMPLES_LEAF,
                                               random_state=RANDOM_STATE,
                                               n_jobs=rf_jobs),
    }


def _read_ml_inputs(dataset_path: Path, metadata_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str], dict]:
    if not dataset_path.is_file():
        raise ValueError(f"Real ML Parquet dataset is missing: {dataset_path}")
    if not metadata_path.is_file():
        raise ValueError(f"ML metadata is missing: {metadata_path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read ML metadata: {metadata_path}") from exc
    if metadata.get("crs") != "EPSG:32643" or metadata.get("raster_resolution_m") != 30:
        raise ValueError("ML metadata must declare EPSG:32643 and 30 m raster resolution")
    features = metadata.get("features")
    forbidden = {"lst_c", "grid_id", "x", "y", "latitude", "longitude", "ward_id", "ward_name"}
    if (not isinstance(features, list) or not features or len(set(features)) != len(features)
            or any(not isinstance(name, str) or name in forbidden for name in features)):
        raise ValueError("ML metadata has invalid feature names or includes target/identity leakage")
    columns = ["x", "y", TARGET, *features]
    try:
        table = pq.read_table(dataset_path, columns=columns)
    except (OSError, KeyError, pa.ArrowException) as exc:
        raise ValueError(f"Cannot read required numeric columns from {dataset_path}") from exc
    if table.num_rows != metadata.get("row_count"):
        raise ValueError("ML metadata row count differs from Parquet")
    try:
        x = np.asarray(table.column("x").to_numpy(), dtype=np.float64)
        y = np.asarray(table.column("y").to_numpy(), dtype=np.float64)
        target = np.asarray(table.column(TARGET).to_numpy(), dtype=np.float64)
        matrix = np.column_stack([np.asarray(table.column(name).to_numpy(), dtype=np.float64)
                                  for name in features])
    except (TypeError, ValueError) as exc:
        raise ValueError("ML table has nonnumeric or missing feature data") from exc
    if (not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(target).all()
            or not np.isfinite(matrix).all() or np.any(target <= -273.15)):
        raise ValueError("ML table contains missing, nonfinite, or physically impossible training values")
    return x, y, target, matrix, features, metadata


def _comparison_plot(results: dict, path: Path) -> None:
    names = list(results)
    display = [name.replace("_", " ").title() for name in names]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    for ax, metric, label in zip(axes, ("mae_c", "rmse_c", "r2"), ("MAE (°C)", "RMSE (°C)", "R²")):
        means = [results[name]["summary"][metric]["mean"] for name in names]
        standard_deviations = [results[name]["summary"][metric]["std"] for name in names]
        ax.bar(range(len(names)), means, yerr=standard_deviations, capsize=5,
               color=["#709e89", "#59837a", "#2f6856"])
        for index, name in enumerate(names):
            points = [fold[metric] for fold in results[name]["folds"]]
            ax.scatter([index] * len(points), points, color="#263f37", s=18, zorder=3)
        ax.set_xticks(range(len(names)), display, rotation=25, ha="right")
        ax.set(ylabel=label, title=f"{label}: 5 spatial folds")
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle("GreenPulse baseline LST regression — held-out 5 km blocks")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def evaluate_baselines(dataset_path: Path, cv_dir: Path, output_path: Path,
                       rf_trees: int = 100, rf_jobs: int = 2) -> dict:
    """Fit three fixed baselines on identical saved 5-fold spatial splits.

    StandardScaler for LinearRegression is fitted *inside each training fold*.
    DecisionTree and RandomForest are also newly fitted per fold. The function
    saves only held-out metrics and a comparison plot, not trained models.
    """
    estimators = _estimators(rf_trees, rf_jobs)
    metadata_path = dataset_path.with_name("metadata.json")
    x, y, target, features, feature_names, metadata = _read_ml_inputs(dataset_path, metadata_path)
    assignment = load_cv_assignment(x, y, dataset_path, cv_dir)
    splitter = SpatialBlockCV(assignment)
    split_indices = list(splitter.split(X=features, groups=assignment.block_id))
    _, fold_summary = summarize_blocks(assignment)
    results = {}
    for name, estimator in estimators.items():
        per_fold = []
        for fold, (train_index, validation_index) in enumerate(split_indices, start=1):
            if validation_index.size < 2 or np.var(target[validation_index]) <= 0:
                raise ValueError(f"Fold {fold} cannot produce a defined held-out R²")
            fold_estimator = clone(estimator)
            fold_estimator.fit(features[train_index], target[train_index])
            prediction = fold_estimator.predict(features[validation_index])
            scores = regression_metrics(target[validation_index], prediction)
            per_fold.append({"fold": fold, "training_rows": int(train_index.size),
                             "validation_rows": int(validation_index.size),
                             "validation_blocks": fold_summary[fold - 1]["validation_blocks"],
                             **scores})
        summary = {metric: {"mean": float(np.mean([item[metric] for item in per_fold])),
                            "std": float(np.std([item[metric] for item in per_fold], ddof=1))}
                   for metric in ("mae_c", "rmse_c", "r2")}
        results[name] = {"folds": per_fold, "summary": summary}
    report = {"system": "GreenPulse AI — An AI-powered Urban Climate Decision-Support System",
              "target": "lst_c", "target_units": "degrees Celsius, land surface temperature",
              "dataset": str(dataset_path), "dataset_date_range": metadata.get("date_range"),
              "dataset_rows": int(target.size), "feature_names": feature_names,
              "cv_block_mapping": str(cv_dir / "spatial_cv_blocks.parquet"),
              "cv_metadata": str(cv_dir / "spatial_cv_metadata.json"),
              "cv_folds": assignment.n_folds, "cv_block_size_m": assignment.block_size_m,
              "same_saved_folds_for_every_model": True,
              "metric_definitions": {"mae_c": "mean(abs(y_true-y_pred))",
                                     "rmse_c": "sqrt(mean((y_true-y_pred)^2))",
                                     "r2": "1-sum((y_true-y_pred)^2)/sum((y_true-mean(y_true))^2)"},
              "summary_std": "sample standard deviation across five held-out folds (ddof=1)",
              "model_configuration": {"linear_regression": {"standard_scaler": "fit on training fold only", "fit_intercept": True},
                                      "decision_tree": {"max_depth": TREE_MAX_DEPTH,
                                                        "min_samples_leaf": MIN_SAMPLES_LEAF,
                                                        "random_state": RANDOM_STATE},
                                      "random_forest": {"n_estimators": rf_trees,
                                                        "max_depth": TREE_MAX_DEPTH,
                                                        "min_samples_leaf": MIN_SAMPLES_LEAF,
                                                        "random_state": RANDOM_STATE,
                                                        "n_jobs": rf_jobs}},
              "software": {"scikit_learn": sklearn.__version__, "numpy": np.__version__},
              "models": results,
              "scientific_limitations": ["Nearby 5 km blocks can still be spatially dependent at their borders.",
                                         "Landsat LST is not pedestrian air temperature.",
                                         "These fixed baseline comparisons do not tune hyperparameters or prove causal drivers."]}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plot_path = output_path.with_name("baseline_comparison.png")
    with tempfile.TemporaryDirectory(prefix="greenpulse_baseline_", dir=output_path.parent) as temporary:
        temporary_json = Path(temporary) / output_path.name
        temporary_plot = Path(temporary) / plot_path.name
        temporary_json.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        _comparison_plot(results, temporary_plot)
        os.replace(temporary_plot, plot_path)
        os.replace(temporary_json, output_path)
    return report
