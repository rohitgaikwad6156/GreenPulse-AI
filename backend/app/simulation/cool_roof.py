"""Cool-roof and combined what-if scenarios using XGBoost LST re-prediction."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from xgboost import XGBRegressor

from .config import (CoolRoofAssumptions, TreeCanopyAssumptions,
                     cool_roof_assumptions_from_env, tree_canopy_assumptions_from_env)
from .tree_canopy import (_resolve_capacity, assess_training_support,
                          load_saved_grid_cell, simulate_tree_canopy)


def _roof_modified_features(feature_names: list[str], baseline_features: dict[str, float],
                            retrofit_percent: float, eligible_roof_area_m2: float,
                            assumptions: CoolRoofAssumptions) -> tuple[dict[str, float], dict]:
    """Apply the area-weighted grid albedo formula to eligible roof only."""
    if (not isinstance(feature_names, list) or len(feature_names) != len(set(feature_names))
            or "albedo" not in feature_names or set(feature_names) != set(baseline_features)):
        raise ValueError("A matching model feature vector with measured grid albedo is required for cool roofs")
    try:
        percent = float(retrofit_percent)
        area = float(eligible_roof_area_m2)
        base = {name: float(baseline_features[name]) for name in feature_names}
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("Cool-roof inputs and model features must be numeric") from exc
    if (not math.isfinite(percent) or not math.isfinite(area)
            or not all(math.isfinite(value) for value in base.values())
            or not 0 <= percent <= assumptions.max_retrofit_percent_of_eligible_roof
            or not 0 <= area <= assumptions.cell_area_m2
            or not 0 <= base["albedo"] <= 1):
        raise ValueError("Retrofit percentage, eligible roof area, or grid albedo is outside valid range")
    roof_fraction = area / assumptions.cell_area_m2
    if "roof_fraction" in base and (not 0 <= base["roof_fraction"] <= 1
                                    or roof_fraction > base["roof_fraction"] + 1e-9):
        raise ValueError("Eligible roof area exceeds the grid's mapped roof fraction")
    retrofit_fraction = percent / 100.0
    retrofit_area = area * retrofit_fraction
    modified = base.copy()
    modified["albedo"] = base["albedo"] + roof_fraction * retrofit_fraction * (
        assumptions.cool_roof_albedo - assumptions.existing_roof_albedo)
    if modified["albedo"] > 1 + 1e-9:
        raise ValueError("Area-weighted scenario albedo would exceed 1; inspect roof assumptions")
    modified["albedo"] = min(1.0, modified["albedo"])
    ndbi_change = None
    if assumptions.k_roof_ndbi_per_retrofit_fraction > 0 and retrofit_fraction > 0:
        if "ndbi" not in base or not -1 <= base["ndbi"] <= 1:
            raise ValueError("Optional k_roof adjustment requires valid NDBI in the trained model")
        new_ndbi = base["ndbi"] - assumptions.k_roof_ndbi_per_retrofit_fraction * retrofit_fraction
        if new_ndbi < -1 or new_ndbi > 1:
            raise ValueError("Optional k_roof adjustment would make NDBI invalid")
        modified["ndbi"] = new_ndbi
        ndbi_change = {"baseline": base["ndbi"], "scenario": new_ndbi}
        for name, count in (("ndbi_mean_3x3", assumptions.focal_3x3_valid_cells),
                            ("ndbi_mean_5x5", assumptions.focal_5x5_valid_cells)):
            if name in modified:
                candidate = base[name] + (new_ndbi - base["ndbi"]) / count
                if not -1 <= candidate <= 1:
                    raise ValueError(f"Optional k_roof adjustment would make {name} invalid")
                modified[name] = candidate
    details = {
        "retrofit_percent_of_eligible_roof": percent,
        "retrofit_fraction": retrofit_fraction,
        "roof_fraction_of_grid": roof_fraction,
        "eligible_roof_area_m2": area,
        "retrofit_area_m2": retrofit_area,
        "changed_albedo": {"baseline": base["albedo"], "scenario": modified["albedo"]},
        "changed_ndbi": ndbi_change,
        "assumptions": {
            "label": assumptions.assumption_label,
            "cell_area_m2": assumptions.cell_area_m2,
            "max_retrofit_percent_of_eligible_roof": assumptions.max_retrofit_percent_of_eligible_roof,
            "existing_roof_albedo": assumptions.existing_roof_albedo,
            "cool_roof_albedo": assumptions.cool_roof_albedo,
            "k_roof_ndbi_per_retrofit_fraction": assumptions.k_roof_ndbi_per_retrofit_fraction,
            "evidence_status": assumptions.evidence_status,
            "provenance": {"roof_albedo": assumptions.albedo_source,
                           "roof_to_ndbi": assumptions.ndbi_source,
                           "aging_horizon": assumptions.aging_horizon_source},
            "ndbi_note": "k_roof is an empirical calibration parameter, not a physical law; 0 disables NDBI changes",
            "albedo_note": "Only the eligible roof fraction changes; the non-roof component of grid albedo is held fixed",
            "area_note": "Eligible roof area must be verified from roof geometry/assessment; it is not inferred from built percentage",
            "limitations": "Illustrative roof albedos are not Pune measurements. This is model sensitivity, not observed or causal cooling. LST is not pedestrian air temperature."
        }
    }
    return modified, details


def simulate_cool_roof(model: XGBRegressor, feature_names: list[str],
                       baseline_features: dict[str, float], retrofit_percent: float,
                       eligible_roof_area_m2: float,
                       assumptions: CoolRoofAssumptions | None = None,
                       training_distributions: dict | None = None) -> dict:
    """Re-run XGBoost after retrofitting 0–50% of eligible roof area.

    Area is m² within one 30 m cell; albedo and NDBI are unitless. All LST
    outputs are °C. Invalid geometry, feature ranges, or model raises
    ValueError. A trained model without albedo cannot simulate cool roofs.
    """
    assumptions = assumptions or cool_roof_assumptions_from_env()
    if not isinstance(model, XGBRegressor) or model.get_params().get("objective") != "reg:squarederror":
        raise ValueError("Cool-roof simulation requires a fitted XGBoost LST regressor")
    if "albedo" not in feature_names:
        raise ValueError("Cool-roof simulation requires albedo in the trained model feature list")
    if model.n_features_in_ != len(feature_names):
        raise ValueError("Model feature count differs from the supplied feature list")
    modified, details = _roof_modified_features(
        feature_names, baseline_features, retrofit_percent, eligible_roof_area_m2, assumptions)
    support = assess_training_support(
        {name: float(baseline_features[name]) for name in feature_names}, modified,
        training_distributions)
    base_vector = np.array([[baseline_features[name] for name in feature_names]], dtype=np.float64)
    modified_vector = np.array([[modified[name] for name in feature_names]], dtype=np.float64)
    predictions = np.asarray(model.predict(np.vstack([base_vector, modified_vector])), dtype=np.float64)
    if predictions.shape != (2,) or not np.isfinite(predictions).all():
        raise ValueError("XGBoost returned invalid LST predictions")
    baseline_lst, scenario_lst = map(float, predictions)
    delta = scenario_lst - baseline_lst
    changes = {name: {"baseline": float(baseline_features[name]), "scenario": modified[name]}
               for name in feature_names if modified[name] != baseline_features[name]}
    return {
        "label": "MODEL WHAT-IF ESTIMATE — NOT OBSERVED COOLING",
        "scenario_type": "cool_roof", "target": "land_surface_temperature", "unit": "°C",
        "baseline_lst_c": baseline_lst, "scenario_lst_c": scenario_lst,
        "delta_lst_c": delta, "cooling_magnitude_c": max(0.0, -delta),
        "modified_features": changes, "scenario_features": modified,
        "training_support": support,
        **details,
    }


def simulate_combined(model: XGBRegressor, feature_names: list[str],
                      baseline_features: dict[str, float], canopy_increase_pp: float,
                      feasible_ground_area_m2: float, retrofit_percent: float,
                      eligible_roof_area_m2: float,
                      tree_assumptions: TreeCanopyAssumptions | None = None,
                      roof_assumptions: CoolRoofAssumptions | None = None,
                      training_distributions: dict | None = None) -> dict:
    """Apply canopy and roof changes to one vector, then predict jointly.

    The combined response comes from XGBoost on the jointly modified vector,
    not from adding two separate cooling estimates. The two eligible areas
    must fit within one grid cell without assuming overlapping ground/roof.
    """
    tree_settings = tree_assumptions or tree_canopy_assumptions_from_env()
    roof_settings = roof_assumptions or cool_roof_assumptions_from_env()
    if tree_settings.cell_area_m2 != roof_settings.cell_area_m2:
        raise ValueError("Tree and roof scenarios must use the same 30 m cell area")
    if float(feasible_ground_area_m2) + float(eligible_roof_area_m2) > tree_settings.cell_area_m2 + 1e-9:
        raise ValueError("Available planting ground plus eligible roof area exceeds one grid cell")
    tree = simulate_tree_canopy(model, feature_names, baseline_features,
                                canopy_increase_pp, feasible_ground_area_m2, tree_settings,
                                training_distributions)
    roof = simulate_cool_roof(model, feature_names, tree["scenario_features"],
                              retrofit_percent, eligible_roof_area_m2, roof_settings,
                              training_distributions)
    combined_features = roof["scenario_features"]
    original = {name: float(baseline_features[name]) for name in feature_names}
    combined_prediction = roof["scenario_lst_c"]
    baseline_prediction = tree["baseline_lst_c"]
    delta = combined_prediction - baseline_prediction
    return {
        "label": "MODEL WHAT-IF ESTIMATE — NOT OBSERVED COOLING",
        "scenario_type": "tree_canopy_and_cool_roof",
        "target": "land_surface_temperature", "unit": "°C",
        "baseline_lst_c": baseline_prediction,
        "scenario_lst_c": combined_prediction,
        "delta_lst_c": delta,
        "cooling_magnitude_c": max(0.0, -delta),
        "canopy_increase_percentage_points": tree["canopy_increase_percentage_points"],
        "additional_canopy_area_m2": tree["additional_canopy_area_m2"],
        "feasible_ground_area_m2": tree["feasible_ground_area_m2"],
        "retrofit_percent_of_eligible_roof": roof["retrofit_percent_of_eligible_roof"],
        "eligible_roof_area_m2": roof["eligible_roof_area_m2"],
        "roof_fraction_of_grid": roof["roof_fraction_of_grid"],
        "retrofit_area_m2": roof["retrofit_area_m2"],
        "changed_albedo": roof["changed_albedo"],
        "changed_ndbi": roof["changed_ndbi"],
        "modified_features": {name: {"baseline": original[name], "scenario": combined_features[name]}
                              for name in feature_names if combined_features[name] != original[name]},
        "scenario_features": combined_features,
        "training_support": assess_training_support(original, combined_features, training_distributions),
        "assumptions": {
            "tree_canopy": tree["assumptions"],
            "cool_roof": roof["assumptions"],
            "combined_note": "Joint XGBoost re-prediction includes fitted model interactions; separate scenario deltas are not summed. This does not establish causal intervention effects."
        }
    }


def simulate_saved_cool_roof(dataset_path: Path, model_path: Path, metadata_path: Path,
                             grid_id: str, retrofit_percent: float, eligible_roof_area_m2: float | None,
                             assumptions: CoolRoofAssumptions | None = None) -> dict:
    """Run a cool-roof scenario for one verified saved grid row."""
    model, names, features, metadata = load_saved_grid_cell(
        dataset_path, model_path, metadata_path, grid_id)
    eligible, feasibility = _resolve_capacity(
        eligible_roof_area_m2, metadata, "eligible_roof_area_m2", "eligible roof area")
    result = simulate_cool_roof(model, names, features, retrofit_percent,
                                eligible, assumptions, metadata["training_feature_distributions"])
    result["grid_id"] = str(grid_id)
    result["model_dataset_version"] = metadata["dataset_version"]
    result["feasibility"] = {"eligible_roof": feasibility}
    return result


def simulate_saved_combined(dataset_path: Path, model_path: Path, metadata_path: Path,
                            grid_id: str, canopy_increase_pp: float,
                            feasible_ground_area_m2: float | None, retrofit_percent: float,
                            eligible_roof_area_m2: float | None,
                            tree_assumptions: TreeCanopyAssumptions | None = None,
                            roof_assumptions: CoolRoofAssumptions | None = None) -> dict:
    """Run a joint canopy and roof scenario for one verified saved grid row."""
    model, names, features, metadata = load_saved_grid_cell(
        dataset_path, model_path, metadata_path, grid_id)
    feasible, ground_source = _resolve_capacity(
        feasible_ground_area_m2, metadata, "plantable_ground_m2", "plantable ground area")
    eligible, roof_source = _resolve_capacity(
        eligible_roof_area_m2, metadata, "eligible_roof_area_m2", "eligible roof area")
    result = simulate_combined(model, names, features, canopy_increase_pp,
                               feasible, retrofit_percent, eligible, tree_assumptions,
                               roof_assumptions, metadata["training_feature_distributions"])
    result["grid_id"] = str(grid_id)
    result["model_dataset_version"] = metadata["dataset_version"]
    result["feasibility"] = {"plantable_ground": ground_source, "eligible_roof": roof_source}
    return result
