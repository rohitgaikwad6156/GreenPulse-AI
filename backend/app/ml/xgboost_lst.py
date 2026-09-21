"""Nested spatial CV, Optuna tuning, and final XGBoost LST persistence.

All reported metrics come from held-out real-data spatial blocks. No risk
categories, synthetic Pune results, SHAP, or intervention claims are created.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import optuna
import pyarrow
import sklearn
import xgboost
from optuna.samplers import TPESampler
from sklearn.model_selection import GroupKFold
from xgboost import XGBRegressor

from backend.app.ml.baselines import _read_ml_inputs, regression_metrics
from backend.app.ml.spatial_cv import SpatialBlockCV, load_cv_assignment, summarize_blocks

DEFAULT_TRIALS = 8
DEFAULT_INNER_FOLDS = 3
SEED = 42
METRICS = ("mae_c", "rmse_c", "r2")


def _training_feature_distributions(matrix: np.ndarray, names: list[str]) -> dict[str, dict]:
    """Return deterministic finite training support used by scenario guards."""
    return {name: {
        "count": int(matrix.shape[0]),
        "min": float(np.min(matrix[:, index])),
        "p01": float(np.quantile(matrix[:, index], 0.01)),
        "p05": float(np.quantile(matrix[:, index], 0.05)),
        "median": float(np.median(matrix[:, index])),
        "p95": float(np.quantile(matrix[:, index], 0.95)),
        "p99": float(np.quantile(matrix[:, index], 0.99)),
        "max": float(np.max(matrix[:, index])),
    } for index, name in enumerate(names)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _model(params: dict, jobs: int) -> XGBRegressor:
    return XGBRegressor(objective="reg:squarederror", tree_method="hist",
                        random_state=SEED, n_jobs=jobs, verbosity=0, **params)


def _suggest(trial: optuna.trial.Trial) -> dict:
    """Suggest the eight requested XGBoost hyperparameters in fixed ranges."""
    return {"max_depth": trial.suggest_int("max_depth", 2, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "gamma": trial.suggest_float("gamma", 0.0, 5.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-6, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 20.0, log=True)}


def _tune_on_blocks(features: np.ndarray, target: np.ndarray, groups: np.ndarray,
                    n_trials: int, inner_folds: int, jobs: int, seed: int
                    ) -> tuple[dict, float, int]:
    """Minimize mean inner-fold RMSE with whole 5 km groups only."""
    if np.unique(groups).size < inner_folds:
        raise ValueError(f"Need at least {inner_folds} training spatial blocks for inner tuning")
    splitter = GroupKFold(n_splits=inner_folds)
    inner_splits = list(splitter.split(features, target, groups=groups))
    for training, validation in inner_splits:
        if set(groups[training]) & set(groups[validation]):
            raise AssertionError("Inner tuning has shared training/validation blocks")

    def objective(trial: optuna.trial.Trial) -> float:
        params = _suggest(trial)
        losses = []
        for training, validation in inner_splits:
            estimator = _model(params, jobs)
            estimator.fit(features[training], target[training])
            prediction = estimator.predict(features[validation]).astype(np.float64)
            losses.append(float(np.sqrt(np.mean((target[validation] - prediction) ** 2))))
        return float(np.mean(losses))

    study = optuna.create_study(direction="minimize",
                                sampler=TPESampler(seed=seed, n_startup_trials=min(3, n_trials)))
    study.optimize(objective, n_trials=n_trials, n_jobs=1, show_progress_bar=False)
    if len(study.trials) != n_trials or not math.isfinite(study.best_value):
        raise ValueError("Optuna did not complete the requested spatial tuning trials")
    return dict(study.best_params), float(study.best_value), len(study.trials)


def _load_baselines(path: Path, dataset_path: Path, cv_dir: Path,
                    features: list[str], row_count: int, fold_rows: list[int]) -> dict:
    if not path.is_file():
        raise ValueError(f"Real baseline metrics are missing: {path}; run Step 14 on the same dataset first")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read baseline metrics: {path}") from exc
    if (Path(report.get("dataset", "")).resolve() != dataset_path.resolve()
            or report.get("dataset_checksum") != f"sha256:{_sha256(dataset_path)}"
            or Path(report.get("cv_block_mapping", "")).resolve() != (cv_dir / "spatial_cv_blocks.parquet").resolve()
            or report.get("dataset_rows") != row_count
            or report.get("feature_names") != features
            or report.get("cv_folds") != 5 or report.get("cv_block_size_m") != 5000.0
            or report.get("same_saved_folds_for_every_model") is not True):
        raise ValueError("Baseline metrics do not match this dataset, features, or saved spatial folds")
    models = report.get("models")
    expected = {"linear_regression", "decision_tree", "random_forest"}
    if not isinstance(models, dict) or set(models) != expected:
        raise ValueError("Baseline metrics must include the three Step 14 regressors")
    for name, result in models.items():
        folds = result.get("folds")
        if not isinstance(folds, list) or len(folds) != 5:
            raise ValueError(f"Baseline {name} lacks five held-out folds")
        for index, fold in enumerate(folds):
            if fold.get("fold") != index + 1 or fold.get("validation_rows") != fold_rows[index]:
                raise ValueError(f"Baseline {name} validation folds differ from saved spatial assignment")
            if any(not isinstance(fold.get(metric), (int, float)) or not math.isfinite(fold[metric]) for metric in METRICS):
                raise ValueError(f"Baseline {name} has invalid metrics")
    return report


def _comparison_plot(xgboost_summary: dict, baseline_report: dict, path: Path) -> None:
    names = ("linear_regression", "decision_tree", "random_forest", "xgboost")
    labels = ("Linear", "Decision Tree", "Random Forest", "XGBoost")
    palette = ("#92ae9f", "#759687", "#547d6f", "#225e4b")
    summaries = {name: baseline_report["models"][name]["summary"] for name in names[:3]}
    summaries["xgboost"] = xgboost_summary
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5), constrained_layout=True)
    for ax, metric, ylabel in zip(axes, METRICS, ("MAE (°C)", "RMSE (°C)", "R²")):
        means = [summaries[name][metric]["mean"] for name in names]
        errors = [summaries[name][metric]["std"] for name in names]
        ax.bar(range(4), means, yerr=errors, capsize=5, color=palette)
        ax.set_xticks(range(4), labels, rotation=25, ha="right")
        ax.set(ylabel=ylabel, title=f"{ylabel}: spatial folds")
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle("GreenPulse held-out LST regression — mean ± fold standard deviation")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def train_xgboost_lst(dataset_path: Path, cv_dir: Path, baseline_metrics_path: Path,
                      model_path: Path, metadata_path: Path,
                      n_trials: int = DEFAULT_TRIALS,
                      inner_folds: int = DEFAULT_INNER_FOLDS,
                      jobs: int = 2) -> dict:
    """Nested spatial evaluation, final spatial tuning, full-data fit, save.

    Outer folds are the saved Step 13 folds. Within each outer training set,
    Optuna sees only inner GroupKFold splits of the remaining 5 km blocks.
    Outer held-out LST never tunes its fold model. After evaluation, a fresh
    spatial CV on all blocks selects final hyperparameters for the full-data
    artifact. Outer metrics estimate this procedure, not final in-sample fit.
    """
    if (isinstance(n_trials, bool) or not isinstance(n_trials, int) or n_trials < 1
            or isinstance(inner_folds, bool) or not isinstance(inner_folds, int) or inner_folds < 2
            or isinstance(jobs, bool) or not isinstance(jobs, int) or jobs < 1):
        raise ValueError("n_trials and jobs must be positive integers; inner_folds must be at least 2")
    x, y, target, features, feature_names, dataset_metadata = _read_ml_inputs(
        dataset_path, dataset_path.with_name("metadata.json"))
    assignment = load_cv_assignment(x, y, dataset_path, cv_dir)
    outer_splits = list(SpatialBlockCV(assignment).split(X=features, groups=assignment.block_id))
    _, fold_summary = summarize_blocks(assignment)
    baselines = _load_baselines(baseline_metrics_path, dataset_path, cv_dir, feature_names,
                                len(target), [len(validation) for _, validation in outer_splits])
    if any(np.unique(assignment.block_id[training]).size < inner_folds for training, _ in outer_splits):
        raise ValueError("At least one outer training split has too few 5 km blocks for inner tuning")
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    outer_results = []
    for fold, (training, validation) in enumerate(outer_splits, start=1):
        if validation.size < 2 or np.var(target[validation]) <= 0:
            raise ValueError(f"Outer fold {fold} cannot produce a defined held-out R²")
        params, inner_rmse, completed = _tune_on_blocks(
            features[training], target[training], assignment.block_id[training],
            n_trials, inner_folds, jobs, SEED + fold)
        estimator = _model(params, jobs)
        estimator.fit(features[training], target[training])
        prediction = estimator.predict(features[validation])
        scores = regression_metrics(target[validation], prediction)
        outer_results.append({"fold": fold, "training_rows": int(training.size),
                              "validation_rows": int(validation.size),
                              "validation_blocks": fold_summary[fold - 1]["validation_blocks"],
                              "inner_spatial_folds": inner_folds,
                              "optuna_trials": completed,
                              "inner_cv_best_mean_rmse_c": inner_rmse,
                              "selected_hyperparameters": params,
                              **scores})
    summary = {metric: {"mean": float(np.mean([item[metric] for item in outer_results])),
                        "std": float(np.std([item[metric] for item in outer_results], ddof=1))}
               for metric in METRICS}
    # This second tuning run is for deployment selection, not for reporting
    # validation performance. It still groups by the original 5 km blocks.
    final_params, full_cv_rmse, final_trials = _tune_on_blocks(
        features, target, assignment.block_id, n_trials, assignment.n_folds, jobs, SEED + 100)
    final_model = _model(final_params, jobs)
    final_model.fit(features, target)
    dataset_hash = _sha256(dataset_path)
    report = {
        "system": "GreenPulse AI — An AI-powered Urban Climate Decision-Support System",
        "model_name": "XGBoost LST regressor", "objective": "reg:squarederror",
        "prediction_equation": "y_hat_i = sum(k=1..K) f_k(x_i)",
        "target": "lst_c", "target_units": "degrees Celsius, land surface temperature",
        "feature_list": feature_names,
        "reproducibility_seed": SEED,
        "training_date_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_version": f"sha256:{dataset_hash}",
        "dataset_path": str(dataset_path), "dataset_date_range": dataset_metadata.get("date_range"),
        "dataset_rows": int(len(target)), "dataset_metadata_path": str(dataset_path.with_name("metadata.json")),
        "training_feature_distributions": _training_feature_distributions(features, feature_names),
        "scenario_support_policy": {
            "hard_bounds": "reject any modified model feature outside the observed training min/max",
            "typical_bounds": "prominently flag modified features outside the observed training p01/p99",
            "valid_intervention_ranges": {
                "tree_canopy_increase_percentage_points": {"min": 0.0, "configured_max": 40.0},
                "cool_roof_retrofit_fraction_of_eligible_roof": {"min": 0.0, "configured_max": 0.5},
                "plantable_ground_area_m2": {"min": 0.0, "cell_max": 900.0},
                "eligible_roof_area_m2": {"min": 0.0, "cell_max": 900.0},
            },
            "evidence_status": "training-distribution guard only; intervention transformations require separate calibration",
        },
        "crs": dataset_metadata["crs"], "resolution_m": dataset_metadata["raster_resolution_m"],
        "spatial_validation_method": "Saved 5 km 5-fold outer block holdouts; Optuna inner GroupKFold by the same blocks",
        "outer_folds": assignment.n_folds, "block_size_m": assignment.block_size_m,
        "cv_mapping_path": str(cv_dir / "spatial_cv_blocks.parquet"),
        "outer_fold_results": outer_results,
        "spatial_cv_metrics": summary,
        "metric_units": {"mae_c": "degrees Celsius", "rmse_c": "degrees Celsius", "r2": "unitless"},
        "metric_summary": "arithmetic mean ± sample standard deviation across five untouched outer spatial folds (ddof=1)",
        "tuning": {"optimizer": "Optuna TPESampler", "trials_per_outer_fold": n_trials,
                   "inner_spatial_folds": inner_folds, "objective": "mean inner-fold RMSE in degrees Celsius",
                   "final_full_dataset_cv_folds": assignment.n_folds,
                   "final_full_dataset_trials": final_trials,
                   "final_full_dataset_best_mean_rmse_c": full_cv_rmse,
                   "search_space": {"max_depth": "2..8", "learning_rate": "0.01..0.2 log",
                                    "n_estimators": "100..500 step 50", "subsample": "0.6..1.0",
                                    "colsample_bytree": "0.6..1.0", "gamma": "0..5",
                                    "reg_alpha": "1e-6..10 log", "reg_lambda": "1e-3..20 log"}},
        "final_hyperparameters": final_params,
        "final_model_configuration": {"objective": "reg:squarederror", "tree_method": "hist",
                                      "random_state": SEED, "n_jobs": jobs, **final_params},
        "baseline_metrics_path": str(baseline_metrics_path),
        "baseline_comparison": {name: baselines["models"][name]["summary"]
                                for name in ("linear_regression", "decision_tree", "random_forest")},
        "software": {"python": platform.python_version(), "xgboost": xgboost.__version__,
                     "optuna": optuna.__version__, "scikit_learn": sklearn.__version__,
                     "numpy": np.__version__, "pyarrow": pyarrow.__version__,
                     "joblib": joblib.__version__},
        "scientific_limitations": ["30 m LST cells share a coarser thermal footprint; adjacent outer blocks can still be correlated.",
                                   "The complete-case input may overrepresent clear and well-mapped places.",
                                   "Outer metrics estimate the nested tuning procedure, not final full-data in-sample fit.",
                                   "LST is not pedestrian air temperature; this regression does not establish causal cooling effects."]}
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    plot_path = model_path.with_name("xgboost_baseline_comparison.png")
    with tempfile.TemporaryDirectory(prefix="greenpulse_xgboost_", dir=model_path.parent) as temporary:
        folder = Path(temporary)
        temporary_model = folder / model_path.name
        temporary_metadata = folder / metadata_path.name
        temporary_plot = folder / plot_path.name
        joblib.dump(final_model, temporary_model)
        report["model_artifact_sha256"] = f"sha256:{_sha256(temporary_model)}"
        # Check that the saved artifact reproduces the in-memory estimator.
        restored = joblib.load(temporary_model)
        probe = features[: min(5, len(features))]
        if not np.allclose(restored.predict(probe), final_model.predict(probe), rtol=0, atol=1e-6):
            raise ValueError("Saved XGBoost model failed reload/prediction verification")
        temporary_metadata.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        _comparison_plot(summary, baselines, temporary_plot)
        os.replace(temporary_plot, plot_path)
        os.replace(temporary_model, model_path)
        os.replace(temporary_metadata, metadata_path)
    return report
