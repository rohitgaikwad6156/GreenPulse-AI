"""Build a labelled discrete-action catalog without fabricating cooling."""

from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from pathlib import Path

from backend.app.ml.uncertainty import load_uncertainty_assumptions


CATALOG_COLUMNS = (
    "catalog_label", "intervention_id", "name", "unit_type", "block_size",
    "capital_cost_inr", "annual_maintenance_inr", "ground_area_required_m2",
    "roof_area_required_m2", "predicted_cooling_benefit_c", "green_cover_gain_m2",
    "co_benefit_score_0_5", "maximum_feasible_units", "time_horizon",
    "maximum_feasible_units_rule", "uncertainty_cv", "assumptions", "source_reference", "benefit_status",
    "feasibility_status", "uncertainty_status", "cost_status",
)
REQUIRED_IDS = (
    "street_trees", "cool_roofs", "green_roofs", "shade_structures",
    "green_corridors", "reflective_pavements",
)
EXPECTED_BLOCKS = {
    "street_trees": ("tree", 1),
    "cool_roofs": ("m2", 50),
    "green_roofs": ("m2", 25),
    "shade_structures": ("structure", 1),
    "green_corridors": ("m2", 25),
    "reflective_pavements": ("m2", 50),
}


def build_intervention_catalog(assumptions_path: Path, uncertainty_config_path: Path,
                               output_path: Path) -> list[dict]:
    """Validate demo planning inputs and save six integer-block CSV rows.

    Costs are INR per discrete action block and annual maintenance INR/year.
    Area is m²; cooling would be °C. Unknown cooling and site-specific
    maximum units remain blank. Invalid or unlabelled assumptions fail
    before writing any output. This function does not solve a MILP.
    """
    if not assumptions_path.is_file():
        raise ValueError(f"Demo catalog assumptions are missing: {assumptions_path}")
    try:
        document = json.loads(assumptions_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot read demo catalog assumptions JSON") from exc
    if (not isinstance(document, dict)
            or document.get("currency") != "INR"
            or "DEMO / SYNTHETIC DATA" not in str(document.get("catalog_label", ""))
            or "DEMO COST ASSUMPTIONS" not in str(document.get("catalog_label", ""))
            or not isinstance(document.get("cost_basis"), str) or not document["cost_basis"].strip()
            or not isinstance(document.get("co_benefit_scale"), str) or not document["co_benefit_scale"].strip()
            or not isinstance(document.get("interventions"), list)):
        raise ValueError("Catalog must explicitly identify DEMO COST ASSUMPTIONS in INR")
    actions = document["interventions"]
    if (len(actions) != len(REQUIRED_IDS) or any(not isinstance(item, dict) for item in actions)
            or [item.get("intervention_id") for item in actions] != list(REQUIRED_IDS)):
        raise ValueError("Catalog must contain the six unique interventions in the declared order")
    uncertainty = load_uncertainty_assumptions(uncertainty_config_path)
    coefficients = uncertainty["intervention_cv"]
    rows = []
    for item in actions:
        action_id = item["intervention_id"]
        if (item.get("unit_type"), item.get("block_size")) != EXPECTED_BLOCKS[action_id]:
            raise ValueError(f"Invalid discrete block for {action_id}")
        numeric_fields = ("capital_cost_inr", "annual_maintenance_inr",
                          "ground_area_required_m2", "roof_area_required_m2",
                          "green_cover_gain_m2", "co_benefit_score_0_5")
        try:
            numbers = {name: float(item[name]) for name in numeric_fields}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Missing numeric demo planning field for {action_id}") from exc
        if (not all(math.isfinite(value) and value >= 0 for value in numbers.values())
                or numbers["capital_cost_inr"] <= 0
                or not numbers["capital_cost_inr"].is_integer()
                or not numbers["annual_maintenance_inr"].is_integer()
                or numbers["co_benefit_score_0_5"] > 5
                or numbers["ground_area_required_m2"] + numbers["roof_area_required_m2"] <= 0
                or any(not isinstance(item.get(name), str) or not item[name].strip()
                       for name in ("name", "time_horizon", "assumptions", "source_reference"))
                or "DEMO" not in item["assumptions"].upper()
                or item.get("predicted_cooling_benefit_c") is not None
                or item.get("maximum_feasible_units") is not None):
            raise ValueError(f"Invalid demo assumptions or fabricated cooling/feasibility for {action_id}")
        cv_key = item.get("uncertainty_cv_key")
        if cv_key is not None and cv_key not in coefficients:
            raise ValueError(f"Unknown uncertainty CV key for {action_id}")
        row = {
            "catalog_label": document["catalog_label"],
            "intervention_id": action_id, "name": item["name"],
            "unit_type": item["unit_type"], "block_size": item["block_size"],
            "capital_cost_inr": int(numbers["capital_cost_inr"]),
            "annual_maintenance_inr": int(numbers["annual_maintenance_inr"]),
            "ground_area_required_m2": numbers["ground_area_required_m2"],
            "roof_area_required_m2": numbers["roof_area_required_m2"],
            "predicted_cooling_benefit_c": "",
            "green_cover_gain_m2": numbers["green_cover_gain_m2"],
            "co_benefit_score_0_5": numbers["co_benefit_score_0_5"],
            "maximum_feasible_units": "",
            "time_horizon": item["time_horizon"],
            "maximum_feasible_units_rule": (
                "floor(verified_eligible_roof_m2 / roof_area_required_m2)"
                if numbers["roof_area_required_m2"] > 0 else
                "floor(verified_available_ground_m2 / ground_area_required_m2)"),
            "uncertainty_cv": float(coefficients[cv_key]) if cv_key else "",
            "assumptions": item["assumptions"],
            "source_reference": item["source_reference"],
            "benefit_status": "NOT ESTIMATED — NO VERIFIED INTERVENTION COOLING MODEL",
            "feasibility_status": "NOT ESTIMATED — REQUIRES WARD/SITE SPACE AND ELIGIBILITY",
            "uncertainty_status": "MVP CONFIG ASSUMPTION — NOT PUNE CALIBRATED" if cv_key else "NOT CALIBRATED",
            "cost_status": "DEMO COST ASSUMPTIONS — NOT VERIFIED PMC/PCMC COSTS",
        }
        rows.append(row)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", suffix=".csv",
                                     prefix="intervention_catalog_", dir=output_path.parent,
                                     delete=False) as stream:
        temporary_path = Path(stream.name)
        writer = csv.DictWriter(stream, fieldnames=CATALOG_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    try:
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return rows
