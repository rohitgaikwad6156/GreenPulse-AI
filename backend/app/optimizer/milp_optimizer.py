"""Integer intervention-block optimization for one explicitly named location.

All planning inputs are per block. Cooling is a modeled marginal LST change
in °C; its sum is only a linear planning proxy, not a site temperature forecast.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


DEFAULT_CONFIG = Path(__file__).with_name("objective_config.json")
REQUIRED_FIELDS = (
    "intervention_id", "name", "unit_type", "block_size", "capital_cost_inr",
    "annual_maintenance_inr", "ground_area_required_m2", "roof_area_required_m2",
    "predicted_cooling_benefit_c", "green_cover_gain_m2", "co_benefit_score_0_5",
    "maximum_feasible_units",
)


class OptimizerDataUnavailableError(RuntimeError):
    """Catalog lacks evidence needed for a defensible optimization run."""


def _finite_nonnegative(value: object, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite nonnegative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return number


def _nonnegative_integer(value: object, name: str) -> int:
    number = _finite_nonnegative(value, name)
    if not number.is_integer():
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(number)


def load_objective_config(path: Path = DEFAULT_CONFIG) -> dict:
    """Load positive normalization rules and configurable unitless weights."""
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        weights = config["weights"]
        norm = config["normalization"]
        for key in ("cooling", "green_cover", "co_benefit"):
            weights[key] = _finite_nonnegative(weights[key], f"weights.{key}")
        if sum(weights.values()) <= 0:
            raise ValueError("At least one objective weight must be positive")
        for key in ("cooling_reference_method", "green_reference_method"):
            if norm[key] != "maximum_positive_per_block_in_candidate_catalog":
                raise ValueError(f"Unsupported normalization method: {key}")
        norm["co_benefit_reference"] = _finite_nonnegative(
            norm["co_benefit_reference"], "co_benefit_reference")
        if norm["co_benefit_reference"] == 0:
            raise ValueError("co_benefit_reference must be positive")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Invalid optimizer configuration: {path}") from exc
    return config


def load_catalog(path: Path) -> list[dict]:
    """Read a CSV catalog, preserving blanks for explicit validation."""
    if not Path(path).is_file():
        raise OptimizerDataUnavailableError(f"Intervention catalog is missing: {path}")
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def optimize_actions(
    actions: list[dict], *, budget_inr: float, maintenance_cap_inr_per_year: float,
    available_ground_m2: float, available_roof_m2: float, location: str,
    config_path: Path = DEFAULT_CONFIG,
    priority_weights: dict[str, float] | None = None,
) -> dict:
    """Maximize normalized utility using SciPy MILP and integer block counts.

    Units: budget/cost INR; maintenance INR/year; ground/roof/green gain m²;
    per-block modeled cooling °C. Input limits must be finite and nonnegative.
    Missing cooling or site capacity is never replaced with a fabricated value.
    """
    if not isinstance(location, str) or not location.strip():
        raise ValueError("location must name a ward or planning area")
    limits = {
        "budget_inr": _finite_nonnegative(budget_inr, "budget_inr"),
        "maintenance_cap_inr_per_year": _finite_nonnegative(
            maintenance_cap_inr_per_year, "maintenance_cap_inr_per_year"),
        "available_ground_m2": _finite_nonnegative(available_ground_m2, "available_ground_m2"),
        "available_roof_m2": _finite_nonnegative(available_roof_m2, "available_roof_m2"),
    }
    if not actions:
        raise OptimizerDataUnavailableError("Intervention catalog has no candidate actions")
    config = load_objective_config(config_path)
    if priority_weights is not None:
        if set(priority_weights) != {"cooling", "green_cover", "co_benefit"}:
            raise ValueError("Priority weights must include cooling, green_cover and co_benefit")
        config["weights"] = {
            name: _finite_nonnegative(priority_weights[name], f"priority_weights.{name}")
            for name in ("cooling", "green_cover", "co_benefit")
        }
        if sum(config["weights"].values()) <= 0:
            raise ValueError("At least one policy priority must be positive")
    clean = []
    ids = set()
    labels = set()
    for action in actions:
        missing = [field for field in REQUIRED_FIELDS if field not in action]
        if missing:
            raise OptimizerDataUnavailableError(
                f"Catalog action lacks required fields: {', '.join(missing)}")
        action_id = str(action["intervention_id"]).strip()
        if not action_id or action_id in ids:
            raise ValueError("Intervention IDs must be nonempty and unique")
        ids.add(action_id)
        label = str(action.get("catalog_label", "")).strip()
        if not label:
            raise OptimizerDataUnavailableError(f"{action_id}: catalog_label provenance is missing")
        labels.add(label)
        # A global catalog cannot certify one ward's intervention capacity.
        # Keep this after benefit/capacity checks so today's incomplete catalog
        # reports its first actionable missing field.
        if not str(action["name"]).strip() or not str(action["unit_type"]).strip():
            raise ValueError(f"{action_id}: name and unit_type are required")
        if action["predicted_cooling_benefit_c"] in (None, ""):
            raise OptimizerDataUnavailableError(
                f"{action_id}: predicted_cooling_benefit_c is missing; calibrate a location-specific intervention benefit")
        if action["maximum_feasible_units"] in (None, ""):
            raise OptimizerDataUnavailableError(
                f"{action_id}: maximum_feasible_units is missing; verify site eligibility/capacity")
        if not str(action.get("location", "")).strip():
            raise OptimizerDataUnavailableError(
                f"{action_id}: location is missing; supply ward/site-specific action inputs")
        if str(action["location"]).strip() != location.strip():
            raise ValueError(f"{action_id}: catalog location does not match requested location")
        item = {
            "intervention_id": action_id,
            "name": str(action["name"]).strip(),
            "unit_type": str(action["unit_type"]).strip(),
            "block_size": _finite_nonnegative(action["block_size"], f"{action_id}.block_size"),
            "capital_cost_inr": _finite_nonnegative(action["capital_cost_inr"], f"{action_id}.capital_cost_inr"),
            "annual_maintenance_inr": _finite_nonnegative(
                action["annual_maintenance_inr"], f"{action_id}.annual_maintenance_inr"),
            "ground_area_required_m2": _finite_nonnegative(
                action["ground_area_required_m2"], f"{action_id}.ground_area_required_m2"),
            "roof_area_required_m2": _finite_nonnegative(
                action["roof_area_required_m2"], f"{action_id}.roof_area_required_m2"),
            "predicted_cooling_benefit_c": _finite_nonnegative(
                action["predicted_cooling_benefit_c"], f"{action_id}.predicted_cooling_benefit_c"),
            "green_cover_gain_m2": _finite_nonnegative(
                action["green_cover_gain_m2"], f"{action_id}.green_cover_gain_m2"),
            "co_benefit_score_0_5": _finite_nonnegative(
                action["co_benefit_score_0_5"], f"{action_id}.co_benefit_score_0_5"),
            "maximum_feasible_units": _nonnegative_integer(
                action["maximum_feasible_units"], f"{action_id}.maximum_feasible_units"),
            "time_horizon": str(action.get("time_horizon", "")).strip() or None,
        }
        if item["block_size"] <= 0 or item["capital_cost_inr"] <= 0:
            raise ValueError(f"{action_id}: block size and capital cost must be positive")
        if item["co_benefit_score_0_5"] > 5:
            raise ValueError(f"{action_id}: catalog co-benefit score must be within 0–5")
        if item["ground_area_required_m2"] + item["roof_area_required_m2"] <= 0:
            raise ValueError(f"{action_id}: each block must use ground or roof area")
        clean.append(item)
    if len(labels) != 1:
        raise ValueError("Candidate actions must share one catalog provenance label")
    cooling_ref = max(item["predicted_cooling_benefit_c"] for item in clean)
    green_ref = max(item["green_cover_gain_m2"] for item in clean)
    # A benefit dimension that is identically zero contributes zero utility.
    cooling_norm = np.array([item["predicted_cooling_benefit_c"] / cooling_ref
                             if cooling_ref > 0 else 0.0 for item in clean])
    green_norm = np.array([item["green_cover_gain_m2"] / green_ref
                           if green_ref > 0 else 0.0 for item in clean])
    score_ref = config["normalization"]["co_benefit_reference"]
    co_norm = np.array([item["co_benefit_score_0_5"] / score_ref for item in clean])
    weights = config["weights"]
    utility = (weights["cooling"] * cooling_norm + weights["green_cover"] * green_norm
               + weights["co_benefit"] * co_norm)
    matrix = np.array([[item[field] for item in clean] for field in (
        "capital_cost_inr", "annual_maintenance_inr",
        "ground_area_required_m2", "roof_area_required_m2")], dtype=float)
    upper = np.array([item["maximum_feasible_units"] for item in clean], dtype=float)
    result = milp(
        c=-utility, integrality=np.ones(len(clean), dtype=int),
        bounds=Bounds(np.zeros(len(clean)), upper),
        constraints=LinearConstraint(matrix, -np.inf, np.array(list(limits.values()))),
        options={"mip_rel_gap": 0.0},
    )
    if result.status != 0 or result.x is None:
        raise RuntimeError(f"MILP did not return an optimal solution (status={result.status}): {result.message}")
    rounded = np.rint(result.x)
    if np.any(np.abs(result.x - rounded) > 1e-6):
        raise RuntimeError("MILP returned noninteger action quantities")
    quantities = rounded.astype(int)
    if np.any(quantities < 0) or np.any(quantities > upper):
        raise RuntimeError("MILP returned quantities outside action capacity")
    used = matrix @ quantities
    if np.any(used > np.array(list(limits.values())) + 1e-6):
        raise RuntimeError("MILP solution violates a planning constraint")
    selected = []
    for item, quantity, unit_utility in zip(clean, quantities, utility):
        if quantity:
            selected.append({
                "intervention_id": item["intervention_id"], "name": item["name"],
                "quantity": int(quantity), "unit_type": item["unit_type"],
                "block_size": item["block_size"],
                "capital_cost_inr": item["capital_cost_inr"] * int(quantity),
                "annual_maintenance_inr": item["annual_maintenance_inr"] * int(quantity),
                "ground_used_m2": item["ground_area_required_m2"] * int(quantity),
                "roof_used_m2": item["roof_area_required_m2"] * int(quantity),
                "modeled_cooling_proxy_c": item["predicted_cooling_benefit_c"] * int(quantity),
                "green_cover_gain_m2": item["green_cover_gain_m2"] * int(quantity),
                "time_horizon": item["time_horizon"],
                "utility": float(unit_utility * quantity),
            })
    return {
        "location": location.strip(), "status": "optimal",
        "interpretation": "Optimal under the modeled objective, assumptions and constraints.",
        "selected_actions": selected,
        "capital_cost_inr": float(used[0]),
        "annual_maintenance_inr": float(used[1]),
        "ground_used_m2": float(used[2]), "roof_used_m2": float(used[3]),
        "unused_budget_inr": float(limits["budget_inr"] - used[0]),
        "objective_value": float(utility @ quantities),
        "modeled_cooling_estimate_c": float(sum(
            item["predicted_cooling_benefit_c"] * quantity
            for item, quantity in zip(clean, quantities))),
        "cooling_estimate_note": (
            "Sum of per-block modeled marginal LST cooling is a linear planning proxy; "
            "it is not a forecast of ward-average or pedestrian air temperature. "
            "Interactions, overlap, and spatial spillover require later validation."),
        "normalization": {
            "cooling_reference_c_per_block": cooling_ref,
            "green_reference_m2_per_block": green_ref,
            "co_benefit_reference": score_ref,
            "method": "maximum positive candidate per-block benefit; zero-only dimensions contribute zero",
        },
        "weights": weights,
        "catalog_label": labels.pop(),
    }


def optimize_catalog(catalog_path: Path, **kwargs) -> dict:
    """Load a saved catalog and solve only if benefit and capacity fields exist."""
    return optimize_actions(load_catalog(catalog_path), **kwargs)
