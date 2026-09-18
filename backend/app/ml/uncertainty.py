"""Approximate, uncalibrated uncertainty ranges for XGBoost LST what-ifs.

Spatial block CV RMSE and explicitly configured intervention coefficients
are combined by the user-requested root-sum-of-squares approximation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).with_name("uncertainty_assumptions.json")
SUPPORTED_INTERVENTIONS = ("cool_roof", "tree_canopy", "green_roof", "cool_pavement")


class UncertaintyUnavailableError(ValueError):
    """A real saved spatial-CV RMSE or valid uncertainty configuration is missing."""


def load_uncertainty_assumptions(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Read and validate editable, labelled MVP uncertainty assumptions.

    CVs and thresholds are dimensionless and °C respectively; invalid or
    incomplete JSON raises UncertaintyUnavailableError.
    """
    if not config_path.is_file():
        raise UncertaintyUnavailableError(f"Uncertainty assumptions file is missing: {config_path}")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UncertaintyUnavailableError("Cannot read uncertainty assumptions JSON") from exc
    try:
        cvs = config["intervention_cv"]
        thresholds = config["confidence_thresholds_sigma_total_c"]
        horizons = config["prediction_horizon"]
        z = float(config["normal_multiplier_for_approx_90_percent"])
        high = float(thresholds["high_below"])
        medium = float(thresholds["medium_at_most"])
        cv_values = {name: float(cvs[name]) for name in SUPPORTED_INTERVENTIONS}
    except (KeyError, TypeError, ValueError) as exc:
        raise UncertaintyUnavailableError("Uncertainty assumptions JSON is incomplete or nonnumeric") from exc
    if (not isinstance(config.get("label"), str) or not config["label"].strip()
            or config.get("combined_cv_rule") != "root_sum_squares_of_selected_cvs"
            or not math.isclose(z, 1.645, rel_tol=0, abs_tol=1e-12)
            or not math.isfinite(high) or not math.isfinite(medium)
            or high <= 0 or medium < high
            or any(not math.isfinite(value) or value < 0 for value in cv_values.values())
            or not isinstance(horizons, dict)
            or any(not isinstance(horizons.get(name), str) or not horizons[name].strip()
                   for name in (*SUPPORTED_INTERVENTIONS, "tree_canopy_and_cool_roof"))):
        raise UncertaintyUnavailableError("Uncertainty assumptions JSON has invalid ranges or labels")
    return config


def spatial_cv_rmse_from_metadata(model_metadata_path: Path) -> tuple[float, dict]:
    """Read mean held-out 5-fold spatial CV RMSE (°C) from model metadata.

    Never substitutes in-sample RMSE, a research-paper number, or zero when
    metadata is missing. Returns RMSE and metadata for version validation.
    """
    if not model_metadata_path.is_file():
        raise UncertaintyUnavailableError("Real XGBoost model metadata is missing")
    try:
        metadata = json.loads(model_metadata_path.read_text(encoding="utf-8"))
        value = metadata["spatial_cv_metrics"]["rmse_c"]["mean"]
        rmse = float(value)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise UncertaintyUnavailableError("Saved model has no valid spatial-CV RMSE; do not display an uncertainty range") from exc
    if (not math.isfinite(rmse) or rmse < 0
            or metadata.get("outer_folds") != 5
            or "spatial" not in str(metadata.get("spatial_validation_method", "")).lower()
            or metadata.get("target") != "lst_c"
            or metadata.get("objective") != "reg:squarederror"
            or not isinstance(metadata.get("dataset_version"), str)):
        raise UncertaintyUnavailableError("Saved model RMSE must come from five held-out spatial folds for LST")
    return rmse, metadata


def estimate_cooling_uncertainty(mean_cooling_c: float, spatial_cv_rmse_c: float,
                                 intervention_types: tuple[str, ...] | list[str],
                                 config: dict) -> dict:
    """Return an approximate normal-style 90% cooling range in °C.

    σ_param = |cooling| × CV; σ_total = sqrt(RMSE² + σ_param²).
    A joint tree/roof scenario combines CVs in quadrature as an explicit
    MVP independence assumption. Invalid, negative, or nonfinite inputs fail.
    This is not a coverage-calibrated statistical prediction interval.
    """
    try:
        cooling = float(mean_cooling_c)
        model_sigma = float(spatial_cv_rmse_c)
    except (TypeError, ValueError) as exc:
        raise ValueError("Cooling and spatial CV RMSE must be numeric °C values") from exc
    if (not math.isfinite(cooling) or cooling < 0
            or not math.isfinite(model_sigma) or model_sigma < 0
            or not isinstance(intervention_types, (tuple, list)) or not intervention_types
            or len(set(intervention_types)) != len(intervention_types)
            or any(name not in SUPPORTED_INTERVENTIONS for name in intervention_types)):
        raise ValueError("Cooling, spatial CV RMSE, or intervention selection is invalid")
    cvs = config["intervention_cv"]
    threshold = config["confidence_thresholds_sigma_total_c"]
    cv_values = [float(cvs[name]) for name in intervention_types]
    combined_cv = math.sqrt(sum(value * value for value in cv_values))
    parameter_sigma = abs(cooling) * combined_cv
    total_sigma = math.hypot(model_sigma, parameter_sigma)
    multiplier = float(config["normal_multiplier_for_approx_90_percent"])
    lower = max(0.0, cooling - multiplier * total_sigma)
    upper = cooling + multiplier * total_sigma
    high = float(threshold["high_below"])
    medium = float(threshold["medium_at_most"])
    confidence = "High" if total_sigma < high else "Medium" if total_sigma <= medium else "Low"
    horizon_key = "tree_canopy_and_cool_roof" if set(intervention_types) == {"tree_canopy", "cool_roof"} else intervention_types[0]
    return {
        "mean_cooling_c": cooling,
        "lower_bound_c": lower,
        "upper_bound_c": upper,
        "confidence_category": confidence,
        "prediction_horizon": config["prediction_horizon"][horizon_key],
        "sigma_model_c": model_sigma,
        "sigma_param_c": parameter_sigma,
        "sigma_total_c": total_sigma,
        "interval_label": "Approximate nominal 90% normal-style range; coverage is not calibrated",
        "assumptions": {
            "label": config["label"],
            "selected_interventions": list(intervention_types),
            "selected_cv_coefficients": {name: float(cvs[name]) for name in intervention_types},
            "effective_intervention_cv": combined_cv,
            "combined_cv_rule": config["combined_cv_rule"] if len(intervention_types) > 1 else "single configured CV",
            "normal_multiplier": multiplier,
            "confidence_thresholds_sigma_total_c": threshold,
            "model_error_source": "mean held-out XGBoost RMSE across five 5 km spatial CV folds",
            "limitations": "Spatial LST RMSE is a proxy for intervention-delta error, not a validated delta-error estimate. Normality and independence are untested; nominal 90% coverage is not guaranteed. Confidence categories are MVP communication thresholds, not probabilities. LST is not pedestrian air temperature."
        }
    }


def add_uncertainty_to_scenario(scenario: dict, model_metadata_path: Path,
                                intervention_types: tuple[str, ...] | list[str],
                                config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Attach a range to a real-model scenario, or fail without spatial RMSE.

    The scenario dataset hash must match saved model metadata. Existing
    scenario fields are preserved and no fabricated interval is inserted.
    """
    rmse, metadata = spatial_cv_rmse_from_metadata(model_metadata_path)
    if scenario.get("model_dataset_version") != metadata["dataset_version"]:
        raise UncertaintyUnavailableError("Scenario and spatial-CV RMSE refer to different model datasets")
    config = load_uncertainty_assumptions(config_path)
    try:
        cooling = scenario["cooling_magnitude_c"]
    except KeyError as exc:
        raise ValueError("Scenario has no XGBoost cooling magnitude") from exc
    uncertainty = estimate_cooling_uncertainty(cooling, rmse, intervention_types, config)
    return {**scenario, "uncertainty": uncertainty}
