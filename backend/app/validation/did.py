"""Paired-cell post-implementation LST and NDVI validation.

All values come from the request. The only bundled observations are an
explicitly labelled DEMO / SYNTHETIC scenario.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from backend.app.schemas.api import DidRequest


DEMO_PATH = Path(__file__).resolve().parents[3] / "data" / "demo" / "validation_scenario.json"


def load_demo_scenario() -> dict:
    """Read the bundled DEMO / SYNTHETIC validation fixture without estimating results."""
    scenario = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    if scenario.get("scenario_label") != "DEMO VALIDATION SCENARIO":
        raise ValueError("Demo validation scenario is not clearly labelled")
    return DidRequest.model_validate(scenario).model_dump()


def calculate_did(request: DidRequest) -> dict:
    """Calculate descriptive DiD and optional prediction residuals in °C.

    Each 30 m grid ID belongs to one group and has one pre and one post row.
    With predictions, each treated cell's actual ΔLST is its observed post-pre
    change minus the mean control post-pre change. Thus the mean adjusted
    actual ΔLST equals the DiD estimate. MAE/RMSE use treated-cell residuals.
    NDVI is unitless and must be present in every row or none.
    This arithmetic does not establish causal intervention effects.
    """
    if request.pre_period == request.post_period:
        raise ValueError("Pre and post periods must be different")
    cells: dict[tuple[str, str], dict[str, object]] = defaultdict(dict)
    assigned_group: dict[str, str] = {}
    has_ndvi = [row.ndvi is not None for row in request.observations]
    if any(has_ndvi) and not all(has_ndvi):
        raise ValueError("NDVI must be supplied for every pre and post observation or omitted entirely")
    for row in request.observations:
        if row.grid_id in assigned_group and assigned_group[row.grid_id] != row.group:
            raise ValueError(f"Grid cell {row.grid_id} cannot be both treated and control")
        assigned_group[row.grid_id] = row.group
        key = (row.group, row.grid_id)
        if row.period in cells[key]:
            raise ValueError(f"Duplicate observation for {row.group}/{row.grid_id}/{row.period}")
        cells[key][row.period] = row

    groups = {"treated": {"pre": [], "post": []}, "control": {"pre": [], "post": []}}
    ndvi_groups = {"treated": {"pre": [], "post": []}, "control": {"pre": [], "post": []}}
    for (group, grid_id), periods in cells.items():
        if set(periods) != {"pre", "post"}:
            raise ValueError(f"Grid cell {grid_id} needs both pre and post LST observations")
        for period in ("pre", "post"):
            groups[group][period].append(periods[period].lst_c)
            if all(has_ndvi):
                ndvi_groups[group][period].append(periods[period].ndvi)
    if not groups["treated"]["pre"] or not groups["control"]["pre"]:
        raise ValueError("At least one paired treated and control grid cell is required")

    means = {group: {period: math.fsum(values) / len(values) for period, values in periods.items()}
             for group, periods in groups.items()}
    counts = {group: {period: len(values) for period, values in periods.items()}
              for group, periods in groups.items()}
    treated_change = means["treated"]["post"] - means["treated"]["pre"]
    control_change = means["control"]["post"] - means["control"]["pre"]
    did = treated_change - control_change

    ndvi_means = None
    ndvi_changes = None
    if all(has_ndvi):
        ndvi_means = {group: {period: math.fsum(values) / len(values)
                              for period, values in periods.items()}
                      for group, periods in ndvi_groups.items()}
        ndvi_changes = {group: values["post"] - values["pre"]
                        for group, values in ndvi_means.items()}

    prediction_rows: list[dict] = []
    performance = None
    if request.predictions:
        predictions = {}
        for prediction in request.predictions:
            if prediction.grid_id in predictions:
                raise ValueError(f"Duplicate prediction for grid cell {prediction.grid_id}")
            predictions[prediction.grid_id] = prediction.predicted_delta_lst_c
        treated_ids = {grid_id for group, grid_id in cells if group == "treated"}
        if set(predictions) != treated_ids:
            raise ValueError("Predictions must contain exactly one predicted ΔLST for every treated grid cell")
        for grid_id in sorted(treated_ids):
            periods = cells[("treated", grid_id)]
            observed_change = periods["post"].lst_c - periods["pre"].lst_c
            actual = observed_change - control_change
            predicted = predictions[grid_id]
            prediction_rows.append({
                "grid_id": grid_id,
                "predicted_delta_lst_c": predicted,
                "observed_treated_delta_lst_c": observed_change,
                "actual_control_adjusted_delta_lst_c": actual,
                "residual_c": actual - predicted,
            })
        residuals = [row["residual_c"] for row in prediction_rows]
        performance = {
            "count_treated_cells": len(residuals),
            "mae_c": math.fsum(abs(value) for value in residuals) / len(residuals),
            "rmse_c": math.sqrt(math.fsum(value * value for value in residuals) / len(residuals)),
            "residual_definition": "control-adjusted observed ΔLST minus predicted intervention ΔLST",
        }

    return {
        "label": request.scenario_label, "source_note": request.source_note,
        "target": "lst_c", "unit": "°C", "intervention": request.intervention,
        "pre_period": request.pre_period, "post_period": request.post_period,
        "group_means_c": means, "counts": counts,
        "treated_change_c": treated_change, "control_change_c": control_change,
        "difference_in_differences_c": did, "realized_cooling_c": -did,
        "ndvi_group_means": ndvi_means, "ndvi_changes": ndvi_changes,
        "prediction_comparison": prediction_rows, "performance": performance,
        "interpretation": "Negative DiD means the treated LST fell relative to the control; realized cooling = -DiD, so a negative value indicates relative warming.",
        "limitations": [
            "This descriptive DiD is not proof of a causal intervention effect.",
            "Parallel trends, comparable seasons and satellite overpasses, stable group composition, spillover, and confounding must be assessed.",
            "Prediction MAE/RMSE are over paired treated cells in this follow-up sample, not spatial cross-validation metrics.",
            "Nearby 30 m cells are spatially autocorrelated; no causal standard error or confidence interval is estimated here.",
            "The API does not verify that caller-supplied observations are real or remotely sensed.",
            "A DEMO VALIDATION SCENARIO is synthetic and cannot establish model performance in Pune or PCMC.",
            "LST is not pedestrian air temperature.",
        ],
    }
