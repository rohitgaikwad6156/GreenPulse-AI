"""Tree scenario tests use ARTIFICIAL TEST FIXTURES, not Pune observations."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from xgboost import XGBRegressor

from backend.app.simulation.config import TreeCanopyAssumptions
from backend.app.simulation.tree_canopy import (
    SimulationUnavailableError, simulate_saved_grid_cell, simulate_tree_canopy,
)


NAMES = ["ndvi", "tree_canopy_pct", "ndvi_mean_3x3", "ndvi_mean_5x5", "ndbi"]


def _model() -> XGBRegressor:
    rng = np.random.default_rng(18)
    ndvi = rng.uniform(0.0, 0.8, 120)
    canopy = rng.uniform(5.0, 65.0, 120)
    context3 = np.clip(ndvi + rng.normal(0, 0.05, 120), -1, 1)
    context5 = np.clip(ndvi + rng.normal(0, 0.03, 120), -1, 1)
    ndbi = rng.uniform(-0.3, 0.5, 120)
    matrix = np.column_stack([ndvi, canopy, context3, context5, ndbi])
    target = 36 - 2 * ndvi - 0.04 * canopy + 3 * ndbi + rng.normal(0, 0.15, 120)
    model = XGBRegressor(objective="reg:squarederror", n_estimators=35, max_depth=3,
                         random_state=18, tree_method="hist", n_jobs=1)
    model.fit(matrix, target)
    return model


def _features() -> dict[str, float]:
    return {"ndvi": 0.3, "tree_canopy_pct": 20.0, "ndvi_mean_3x3": 0.25,
            "ndvi_mean_5x5": 0.2, "ndbi": 0.2}


class TreeCanopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = _model()

    def test_model_is_rerun_on_modified_features(self):
        report = simulate_tree_canopy(self.model, NAMES, _features(), 10.0, 120.0)
        self.assertEqual(report["additional_canopy_area_m2"], 90.0)
        self.assertEqual(report["modified_features"]["tree_canopy_pct"]["scenario"], 30.0)
        self.assertAlmostEqual(report["modified_features"]["ndvi"]["scenario"], 0.4)
        self.assertAlmostEqual(report["modified_features"]["ndvi_mean_3x3"]["scenario"], 0.25 + 0.1 / 9)
        self.assertAlmostEqual(report["modified_features"]["ndvi_mean_5x5"]["scenario"], 0.2 + 0.1 / 25)
        scenario_vector = np.array([[0.4, 30.0, 0.25 + 0.1 / 9, 0.2 + 0.1 / 25, 0.2]])
        self.assertAlmostEqual(report["scenario_lst_c"], float(self.model.predict(scenario_vector)[0]), places=5)
        self.assertAlmostEqual(report["delta_lst_c"], report["scenario_lst_c"] - report["baseline_lst_c"])
        self.assertEqual(report["cooling_magnitude_c"], max(0, -report["delta_lst_c"]))
        self.assertIn("REQUIRES LOCAL CALIBRATION", report["assumptions"]["label"])

    def test_zero_slider_and_configurable_coefficient(self):
        zero = simulate_tree_canopy(self.model, NAMES, _features(), 0.0, 0.0)
        self.assertEqual(zero["baseline_lst_c"], zero["scenario_lst_c"])
        self.assertEqual(zero["delta_lst_c"], 0.0)
        assumption = TreeCanopyAssumptions(ndvi_per_canopy_percentage_point=0.005)
        changed = simulate_tree_canopy(self.model, NAMES, _features(), 10.0, 90.0, assumption)
        self.assertAlmostEqual(changed["modified_features"]["ndvi"]["scenario"], 0.35)

    def test_ndvi_clipping_uses_actual_change_for_focal_features(self):
        features = _features()
        features["ndvi"] = 0.95
        report = simulate_tree_canopy(self.model, NAMES, features, 10.0, 90.0)
        self.assertEqual(report["scenario_features"]["ndvi"], 1.0)
        self.assertAlmostEqual(report["scenario_features"]["ndvi_mean_3x3"], 0.25 + 0.05 / 9)
        self.assertAlmostEqual(report["assumptions"]["ndvi_actual_change_after_clipping"], 0.05)

    def test_area_canopy_slider_and_invalid_inputs_rejected(self):
        with self.assertRaisesRegex(ValueError, "feasible"):
            simulate_tree_canopy(self.model, NAMES, _features(), 20.0, 100.0)
        with self.assertRaisesRegex(ValueError, "100%"):
            features = _features()
            features["tree_canopy_pct"] = 90.0
            simulate_tree_canopy(self.model, NAMES, features, 20.0, 300.0)
        for increase in (-1.0, 41.0, float("nan")):
            with self.assertRaises(ValueError):
                simulate_tree_canopy(self.model, NAMES, _features(), increase, 300.0)
        with self.assertRaises(ValueError):
            simulate_tree_canopy(self.model, NAMES, _features(), 10.0, float("inf"))

    def test_saved_real_path_contract_uses_matching_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir = root / "data" / "processed"
            data_dir.mkdir(parents=True)
            dataset = data_dir / "greenpulse_ml_grid.parquet"
            features = _features()
            pq.write_table(pa.table({"grid_id": ["ARTIFICIAL-CELL"],
                                     **{name: [value] for name, value in features.items()}}), dataset)
            (data_dir / "metadata.json").write_text(json.dumps({
                "row_count": 1, "features": NAMES, "crs": "EPSG:32643",
                "raster_resolution_m": 30, "date_range": "2025-03-01/2025-05-31",
                "source": "ARTIFICIAL TEST FIXTURE"}), encoding="utf-8")
            model_dir = root / "models"
            model_dir.mkdir()
            model_path = model_dir / "xgboost_lst.joblib"
            metadata_path = model_dir / "model_metadata.json"
            joblib.dump(self.model, model_path)
            metadata_path.write_text(json.dumps({
                "feature_list": NAMES, "dataset_version": "sha256:" + hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "target": "lst_c", "objective": "reg:squarederror", "dataset_rows": 1,
                "dataset_date_range": "2025-03-01/2025-05-31", "crs": "EPSG:32643",
                "resolution_m": 30}), encoding="utf-8")
            report = simulate_saved_grid_cell(dataset, model_path, metadata_path,
                                              "ARTIFICIAL-CELL", 10.0, 90.0)
            self.assertEqual(report["grid_id"], "ARTIFICIAL-CELL")
            with self.assertRaisesRegex(ValueError, "not found"):
                simulate_saved_grid_cell(dataset, model_path, metadata_path, "OTHER", 10.0, 90.0)
            metadata = json.loads(metadata_path.read_text())
            metadata["dataset_version"] = "sha256:wrong"
            metadata_path.write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "does not match"):
                simulate_saved_grid_cell(dataset, model_path, metadata_path,
                                         "ARTIFICIAL-CELL", 10.0, 90.0)
            with self.assertRaises(SimulationUnavailableError):
                simulate_saved_grid_cell(dataset, root / "missing.joblib", metadata_path,
                                         "ARTIFICIAL-CELL", 10.0, 90.0)


if __name__ == "__main__":
    unittest.main()
