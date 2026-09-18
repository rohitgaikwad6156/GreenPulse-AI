"""HTTP integration checks using isolated ARTIFICIAL / SYNTHETIC TEST DATA only.

The values here are fixtures for software behavior. They are not Pune/PCMC
observations, measured cooling, or real spatial-validation performance.
"""

import csv
import hashlib
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from pyproj import Transformer
from sklearn.model_selection import GroupKFold
from xgboost import XGBRegressor

from backend.app.api import map_data, services
from backend.app.main import app


FEATURES = [
    "ndvi", "ndbi", "tree_canopy_pct", "built_pct", "albedo",
    "road_density", "ndvi_mean_3x3", "ndvi_mean_5x5",
    "ndbi_mean_3x3", "ndbi_mean_5x5", "roof_fraction",
]
CELL_ID = "ARTIFICIAL-CELL-0"
WARD_ID = "PMC:ARTIFICIAL"
LOCATION = "ARTIFICIAL TEST WARD"


def _synthetic_artifacts(root: Path) -> dict[str, Path]:
    processed = root / "data" / "processed"
    boundaries = root / "data" / "boundaries"
    models = root / "models"
    for directory in (processed, boundaries, models):
        directory.mkdir(parents=True)

    count = 80
    rng = np.random.default_rng(2901)
    ndvi = rng.uniform(0.12, 0.62, count)
    ndbi = rng.uniform(-0.05, 0.45, count)
    canopy = rng.uniform(8.0, 55.0, count)
    albedo = rng.uniform(0.15, 0.42, count)
    values = {
        "ndvi": ndvi, "ndbi": ndbi, "tree_canopy_pct": canopy,
        "built_pct": rng.uniform(15, 65, count), "albedo": albedo,
        "road_density": rng.uniform(1, 15, count),
        "ndvi_mean_3x3": np.clip(ndvi + rng.normal(0, 0.03, count), -1, 1),
        "ndvi_mean_5x5": np.clip(ndvi + rng.normal(0, 0.02, count), -1, 1),
        "ndbi_mean_3x3": np.clip(ndbi + rng.normal(0, 0.03, count), -1, 1),
        "ndbi_mean_5x5": np.clip(ndbi + rng.normal(0, 0.02, count), -1, 1),
        "roof_fraction": rng.uniform(0.25, 0.6, count),
    }
    target = 35 - 2 * ndvi + 3 * ndbi - 0.025 * canopy - 2 * albedo
    matrix = np.column_stack([values[name] for name in FEATURES])
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    x0, y0 = transformer.transform(73.8, 18.5)
    blocks = np.arange(count) // 8
    east = x0 + blocks * 5000 + (np.arange(count) % 8) * 30
    north = np.full(count, y0 + 15)
    fold_rmse = []
    for train, held_out in GroupKFold(n_splits=5).split(matrix, target, groups=blocks):
        fold_model = XGBRegressor(
            objective="reg:squarederror", n_estimators=24, max_depth=3,
            tree_method="hist", random_state=2901, n_jobs=1,
        )
        fold_model.fit(matrix[train], target[train])
        fold_rmse.append(float(np.sqrt(np.mean((target[held_out] - fold_model.predict(matrix[held_out])) ** 2))))
    model = XGBRegressor(
        objective="reg:squarederror", n_estimators=24, max_depth=3,
        tree_method="hist", random_state=2901, n_jobs=1,
    )
    model.fit(matrix, target)
    lon, lat = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform(east, north)
    grid = processed / "greenpulse_ml_grid.parquet"
    pq.write_table(pa.table({
        "grid_id": [f"ARTIFICIAL-CELL-{i}" for i in range(count)],
        "ward_id": [WARD_ID] * count, "ward_name": [LOCATION] * count,
        "x": east, "y": north, "longitude": lon, "latitude": lat,
        "lst_c": target, **values,
    }), grid)
    grid_meta = processed / "metadata.json"
    grid_meta.write_text(json.dumps({
        "crs": "EPSG:32643", "raster_resolution_m": 30,
        "row_count": count, "features": FEATURES,
        "date_range": "ARTIFICIAL TEST PERIOD",
        "source": "ARTIFICIAL / SYNTHETIC TEST DATA",
    }), encoding="utf-8")
    model_path = models / "xgboost_lst.joblib"
    joblib.dump(model, model_path)
    model_meta = models / "model_metadata.json"
    model_meta.write_text(json.dumps({
        "feature_list": FEATURES,
        "dataset_version": "sha256:" + hashlib.sha256(grid.read_bytes()).hexdigest(),
        "dataset_rows": count, "dataset_date_range": "ARTIFICIAL TEST PERIOD",
        "target": "lst_c", "objective": "reg:squarederror",
        "crs": "EPSG:32643", "resolution_m": 30,
        "spatial_validation_method": "ARTIFICIAL TEST FIXTURE: five 5 km spatial GroupKFold folds",
        "outer_folds": 5,
        "spatial_cv_metrics": {"rmse_c": {"mean": float(np.mean(fold_rmse)),
                                             "std": float(np.std(fold_rmse, ddof=1))}},
    }), encoding="utf-8")
    boundary = boundaries / "wards.geojson"
    boundary.write_text(json.dumps({
        "type": "FeatureCollection", "features": [{
            "type": "Feature",
            "properties": {"municipality": "PMC", "ward_id": "ARTIFICIAL", "ward_name": LOCATION},
            "geometry": {"type": "Polygon", "coordinates": [[
                [73.79, 18.49], [74.3, 18.49], [74.3, 18.52],
                [73.79, 18.52], [73.79, 18.49],
            ]]},
        }, {
            "type": "Feature",
            "properties": {"municipality": "PCMC", "ward_id": "ARTIFICIAL", "ward_name": "ARTIFICIAL PCMC WARD"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [74.35, 18.49], [74.4, 18.49], [74.4, 18.52],
                [74.35, 18.52], [74.35, 18.49],
            ]]},
        }],
    }), encoding="utf-8")
    catalog = processed / "interventions.csv"
    actions = [
        {"intervention_id": "tree", "name": "ARTIFICIAL tree block", "unit_type": "tree",
         "block_size": 1, "capital_cost_inr": 100, "annual_maintenance_inr": 10,
         "ground_area_required_m2": 5, "roof_area_required_m2": 0,
         "predicted_cooling_benefit_c": 0.2, "green_cover_gain_m2": 5,
         "co_benefit_score_0_5": 4, "maximum_feasible_units": 3},
        {"intervention_id": "roof", "name": "ARTIFICIAL roof block", "unit_type": "m2",
         "block_size": 50, "capital_cost_inr": 150, "annual_maintenance_inr": 5,
         "ground_area_required_m2": 0, "roof_area_required_m2": 50,
         "predicted_cooling_benefit_c": 0.3, "green_cover_gain_m2": 0,
         "co_benefit_score_0_5": 2, "maximum_feasible_units": 2},
    ]
    with catalog.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["catalog_label", "location", *actions[0].keys()])
        writer.writeheader()
        for action in actions:
            writer.writerow({"catalog_label": "ARTIFICIAL / SYNTHETIC TEST CATALOG",
                             "location": LOCATION, **action})
    return {"root": root, "grid": grid, "grid_meta": grid_meta, "model": model_path,
            "model_meta": model_meta, "boundary": boundary, "catalog": catalog}


class FullSystemHttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        paths = _synthetic_artifacts(Path(self.temporary.name))
        self.stack = ExitStack()
        for module, attribute, key in (
            (services, "ROOT", "root"), (services, "GRID", "grid"),
            (services, "GRID_METADATA", "grid_meta"),
            (services, "MODEL", "model"), (services, "MODEL_METADATA", "model_meta"),
            (services, "CATALOG", "catalog"), (map_data, "BOUNDARY", "boundary"),
        ):
            self.stack.enter_context(patch.object(module, attribute, paths[key]))
        map_data._verified_model.cache_clear()
        map_data._ward_prediction_summary.cache_clear()
        self.client = TestClient(app)
        self.paths = paths

    def tearDown(self):
        self.client.close()
        map_data._verified_model.cache_clear()
        map_data._ward_prediction_summary.cache_clear()
        self.stack.close()
        self.temporary.cleanup()

    def test_map_prediction_explanation_and_model_metrics(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        methodology = self.client.get("/api/methodology").json()
        self.assertTrue(methodology["data_status"]["trained_model_available"])
        metrics = self.client.get("/api/model/metrics")
        self.assertEqual(metrics.status_code, 200)
        self.assertIn("ARTIFICIAL TEST FIXTURE", metrics.json()["spatial_validation_method"])

        wards = self.client.get("/api/map/wards")
        self.assertEqual(wards.status_code, 200, wards.text)
        self.assertEqual(wards.json()["features"][0]["properties"]["ward_id"], WARD_ID)
        heat = self.client.get("/api/map/heat/wards")
        self.assertEqual(heat.status_code, 200, heat.text)
        selection = self.client.get(f"/api/map/ward/{WARD_ID}")
        self.assertEqual(selection.status_code, 200, selection.text)
        self.assertEqual(selection.json()["grid_cell_count"], 80)
        self.assertTrue(np.isfinite(selection.json()["predicted_lst_c"]))
        cell = self.client.get(f"/api/map/cell/{CELL_ID}")
        self.assertEqual(cell.status_code, 200, cell.text)
        self.assertTrue(cell.json()["top_shap_factors"])
        self.assertIsNone(cell.json()["heat_hazard_score"])

        predicted = self.client.post("/api/predict", json={"grid_id": CELL_ID})
        self.assertEqual(predicted.status_code, 200, predicted.text)
        self.assertAlmostEqual(predicted.json()["predicted_lst_c"], cell.json()["predicted_lst_c"], places=5)
        explanation = self.client.post("/api/explain", json={"grid_id": CELL_ID, "sample_size": 24})
        self.assertEqual(explanation.status_code, 200, explanation.text)
        local = explanation.json()["local_explanation"]
        self.assertAlmostEqual(local["predicted_lst"], predicted.json()["predicted_lst_c"], places=3)
        self.assertAlmostEqual(local["baseline_lST"] + sum(
            row["shap_value_c"] for row in local["features"]),
            local["predicted_lst"], places=3)

    def test_zero_and_changed_scenarios_with_uncertainty(self):
        prediction = self.client.post("/api/predict", json={"grid_id": CELL_ID}).json()["predicted_lst_c"]
        cases = [
            ("tree_canopy", {"canopy_increase_percentage_points": 0, "feasible_ground_area_m2": 90}),
            ("cool_roof", {"retrofit_fraction": 0, "eligible_roof_area_m2": 180}),
            ("combined", {"canopy_increase_percentage_points": 0, "feasible_ground_area_m2": 90,
                          "retrofit_fraction": 0, "eligible_roof_area_m2": 180}),
        ]
        for scenario_type, fields in cases:
            with self.subTest(scenario_type=scenario_type):
                response = self.client.post("/api/simulate", json={
                    "grid_id": CELL_ID, "scenario_type": scenario_type, **fields,
                })
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertAlmostEqual(result["baseline_lst_c"], prediction, places=5)
                self.assertAlmostEqual(result["scenario_lst_c"], result["baseline_lst_c"], places=6)
                self.assertEqual(result["delta_lst_c"], 0)
                self.assertEqual(result["cooling_magnitude_c"], 0)
                self.assertEqual(result["modified_features"], {})
                self.assertEqual(result["uncertainty"]["mean_cooling_c"], 0)

        for scenario_type, fields in (
            ("tree_canopy", {"canopy_increase_percentage_points": 10, "feasible_ground_area_m2": 90}),
            ("cool_roof", {"retrofit_fraction": 0.5, "eligible_roof_area_m2": 180}),
            ("combined", {"canopy_increase_percentage_points": 10, "feasible_ground_area_m2": 90,
                          "retrofit_fraction": 0.5, "eligible_roof_area_m2": 180}),
        ):
            with self.subTest(scenario_type=scenario_type):
                response = self.client.post("/api/simulate", json={
                    "grid_id": CELL_ID, "scenario_type": scenario_type, **fields,
                })
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertAlmostEqual(result["delta_lst_c"],
                                       result["scenario_lst_c"] - result["baseline_lst_c"])
                self.assertEqual(result["cooling_magnitude_c"], max(0, -result["delta_lst_c"]))
                self.assertGreater(result["uncertainty"]["upper_bound_c"],
                                   result["uncertainty"]["lower_bound_c"])
                self.assertGreaterEqual(result["uncertainty"]["lower_bound_c"], 0)
                if scenario_type in {"tree_canopy", "combined"}:
                    self.assertEqual(result["modified_features"]["tree_canopy_pct"]["scenario"],
                                     result["modified_features"]["tree_canopy_pct"]["baseline"] + 10)
                if scenario_type in {"cool_roof", "combined"}:
                    self.assertGreater(result["modified_features"]["albedo"]["scenario"],
                                       result["modified_features"]["albedo"]["baseline"])

    def test_optimizer_constraints_and_http_validation(self):
        limits = {"location": LOCATION, "budget_inr": 250,
                  "maintenance_cap_inr_per_year": 15,
                  "available_ground_m2": 10, "available_roof_m2": 50}
        response = self.client.post("/api/optimize", json=limits)
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()
        self.assertEqual(plan["status"], "optimal")
        self.assertLessEqual(plan["capital_cost_inr"], limits["budget_inr"])
        self.assertLessEqual(plan["annual_maintenance_inr"], limits["maintenance_cap_inr_per_year"])
        self.assertLessEqual(plan["ground_used_m2"], limits["available_ground_m2"])
        self.assertLessEqual(plan["roof_used_m2"], limits["available_roof_m2"])
        self.assertTrue(all(isinstance(item["quantity"], int) and item["quantity"] >= 0
                            for item in plan["selected_actions"]))
        self.assertAlmostEqual(plan["unused_budget_inr"],
                               limits["budget_inr"] - plan["capital_cost_inr"])
        for field in ("capital_cost_inr", "annual_maintenance_inr", "ground_used_m2", "roof_used_m2"):
            item_field = {"capital_cost_inr": "capital_cost_inr",
                          "annual_maintenance_inr": "annual_maintenance_inr",
                          "ground_used_m2": "ground_used_m2", "roof_used_m2": "roof_used_m2"}[field]
            self.assertAlmostEqual(plan[field], sum(item[item_field] for item in plan["selected_actions"]))
        empty = self.client.post("/api/optimize", json={**limits, "budget_inr": 0}).json()
        self.assertEqual(empty["selected_actions"], [])
        self.assertEqual(empty["capital_cost_inr"], 0)
        self.assertEqual(self.client.post("/api/optimize", json={**limits, "budget_inr": -1}).status_code, 422)
        self.assertEqual(self.client.post("/api/simulate", json={
            "grid_id": CELL_ID, "scenario_type": "tree_canopy",
            "canopy_increase_percentage_points": -1, "feasible_ground_area_m2": 90,
        }).status_code, 422)
        self.assertEqual(self.client.post("/api/simulate", json={
            "grid_id": CELL_ID, "scenario_type": "cool_roof",
            "retrofit_fraction": 1.1, "eligible_roof_area_m2": 180,
        }).status_code, 422)

    def test_did_and_missing_model_behavior(self):
        payload = {
            "intervention": "ARTIFICIAL TEST INTERVENTION", "pre_period": "synthetic pre",
            "post_period": "synthetic post", "observations": [
                {"grid_id": "T", "group": "treated", "period": "pre", "lst_c": 35, "ndvi": 0.2},
                {"grid_id": "T", "group": "treated", "period": "post", "lst_c": 32, "ndvi": 0.3},
                {"grid_id": "C", "group": "control", "period": "pre", "lst_c": 33, "ndvi": 0.1},
                {"grid_id": "C", "group": "control", "period": "post", "lst_c": 32, "ndvi": 0.11},
            ], "predictions": [{"grid_id": "T", "predicted_delta_lst_c": -1.5}],
            "source_note": "ARTIFICIAL / SYNTHETIC TEST DATA",
        }
        response = self.client.post("/api/validation/did", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(report["difference_in_differences_c"], -2)
        self.assertEqual(report["realized_cooling_c"], 2)
        self.assertAlmostEqual(report["ndvi_changes"]["treated"], 0.1)
        self.assertAlmostEqual(report["performance"]["mae_c"], 0.5)
        self.assertAlmostEqual(report["performance"]["rmse_c"], 0.5)
        self.assertIn("PROVENANCE NOT VERIFIED", report["label"])

        with patch.object(services, "MODEL", self.paths["root"] / "missing.joblib"):
            self.assertEqual(self.client.post("/api/predict", json={"grid_id": CELL_ID}).status_code, 503)
            self.assertEqual(self.client.post("/api/simulate", json={
                "grid_id": CELL_ID, "scenario_type": "tree_canopy",
                "canopy_increase_percentage_points": 0, "feasible_ground_area_m2": 90,
            }).status_code, 503)


if __name__ == "__main__":
    unittest.main()
