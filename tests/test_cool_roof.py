"""Cool-roof tests use ARTIFICIAL TEST FIXTURES, never Pune climate data."""

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

from backend.app.simulation.config import CoolRoofAssumptions
from backend.app.simulation.cool_roof import (
    simulate_combined, simulate_cool_roof, simulate_saved_combined, simulate_saved_cool_roof,
)


NAMES = ["ndvi", "tree_canopy_pct", "ndvi_mean_3x3", "ndvi_mean_5x5",
         "ndbi", "ndbi_mean_3x3", "ndbi_mean_5x5", "albedo", "roof_fraction"]


def _distributions() -> dict:
    limits = {name: (-1, -0.5, 0.8, 1) for name in NAMES}
    limits.update({"tree_canopy_pct": (0, 5, 65, 100), "albedo": (0, 0.1, 0.5, 1),
                   "roof_fraction": (0, 0.1, 0.65, 1)})
    return {name: {"count": 140, "min": values[0], "p01": values[1], "p99": values[2], "max": values[3]}
            for name, values in limits.items()}


def _model() -> XGBRegressor:
    rng = np.random.default_rng(27)
    ndvi = rng.uniform(0.05, 0.7, 140)
    canopy = rng.uniform(5, 65, 140)
    ndbi = rng.uniform(-0.2, 0.5, 140)
    albedo = rng.uniform(0.1, 0.5, 140)
    roof_fraction = rng.uniform(0.1, 0.65, 140)
    matrix = np.column_stack([ndvi, canopy, ndvi, ndvi, ndbi, ndbi, ndbi,
                              albedo, roof_fraction])
    target = 35 - 2 * ndvi - 0.04 * canopy + 3 * ndbi - 3 * albedo
    model = XGBRegressor(objective="reg:squarederror", n_estimators=35, max_depth=3,
                         random_state=27, tree_method="hist", n_jobs=1)
    model.fit(matrix, target)
    return model


def _features() -> dict[str, float]:
    return {"ndvi": 0.3, "tree_canopy_pct": 20.0, "ndvi_mean_3x3": 0.3,
            "ndvi_mean_5x5": 0.3, "ndbi": 0.2, "ndbi_mean_3x3": 0.2,
            "ndbi_mean_5x5": 0.2, "albedo": 0.25, "roof_fraction": 0.4}


class CoolRoofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = _model()

    def test_area_weighted_roof_albedo_and_xgboost_reprediction(self):
        result = simulate_cool_roof(self.model, NAMES, _features(), 50.0, 180.0)
        expected_albedo = 0.25 + (180 / 900) * 0.5 * (0.65 - 0.20)
        self.assertAlmostEqual(result["changed_albedo"]["scenario"], expected_albedo)
        self.assertEqual(result["retrofit_area_m2"], 90.0)
        self.assertEqual(result["roof_fraction_of_grid"], 0.2)
        self.assertIsNone(result["changed_ndbi"])
        self.assertEqual(result["scenario_features"]["ndvi"], 0.3)
        self.assertEqual(result["scenario_features"]["roof_fraction"], 0.4)
        expected_vector = np.array([[0.3, 20.0, 0.3, 0.3, 0.2, 0.2, 0.2,
                                     expected_albedo, 0.4]])
        self.assertAlmostEqual(result["scenario_lst_c"], float(self.model.predict(expected_vector)[0]), places=5)
        self.assertAlmostEqual(result["delta_lst_c"], result["scenario_lst_c"] - result["baseline_lst_c"])
        self.assertEqual(result["cooling_magnitude_c"], max(0, -result["delta_lst_c"]))

    def test_zero_retrofit_and_optional_empirical_ndbi(self):
        zero = simulate_cool_roof(self.model, NAMES, _features(), 0.0, 180.0)
        self.assertEqual(zero["baseline_lst_c"], zero["scenario_lst_c"])
        self.assertEqual(zero["retrofit_area_m2"], 0.0)
        settings = CoolRoofAssumptions(k_roof_ndbi_per_retrofit_fraction=0.1)
        adjusted = simulate_cool_roof(self.model, NAMES, _features(), 50.0, 180.0, settings)
        self.assertAlmostEqual(adjusted["changed_ndbi"]["scenario"], 0.15)
        self.assertAlmostEqual(adjusted["scenario_features"]["ndbi_mean_3x3"], 0.2 - 0.05 / 9)
        self.assertIn("not a physical law", adjusted["assumptions"]["ndbi_note"])

    def test_invalid_areas_albedo_and_missing_feature(self):
        with self.assertRaisesRegex(ValueError, "mapped roof"):
            simulate_cool_roof(self.model, NAMES, _features(), 50.0, 450.0)
        for percent, area in ((51, 180), (-1, 180), (10, 901), (10, float("nan"))):
            with self.assertRaises(ValueError):
                simulate_cool_roof(self.model, NAMES, _features(), percent, area)
        with self.assertRaisesRegex(ValueError, "albedo"):
            names = [name for name in NAMES if name != "albedo"]
            simulate_cool_roof(self.model, names, {name: _features()[name] for name in names}, 10, 180)
        with self.assertRaises(ValueError):
            CoolRoofAssumptions(existing_roof_albedo=0.8, cool_roof_albedo=0.65)

    def test_combined_is_joint_prediction_not_sum_of_deltas(self):
        result = simulate_combined(self.model, NAMES, _features(), 10.0, 120.0,
                                   50.0, 180.0)
        vector = np.array([[result["scenario_features"][name] for name in NAMES]])
        self.assertAlmostEqual(result["scenario_lst_c"], float(self.model.predict(vector)[0]), places=5)
        self.assertAlmostEqual(result["changed_albedo"]["scenario"],
                               0.25 + (180 / 900) * 0.5 * (0.65 - 0.2))
        self.assertAlmostEqual(result["scenario_features"]["ndvi"], 0.4)
        self.assertEqual(result["retrofit_area_m2"], 90.0)
        self.assertIn("not summed", result["assumptions"]["combined_note"])
        with self.assertRaisesRegex(ValueError, "exceeds one grid cell"):
            simulate_combined(self.model, NAMES, _features(), 10, 700, 50, 300)

    def test_roof_training_support_ood_and_hard_boundary(self):
        distributions = _distributions()
        distributions["albedo"]["p99"] = 0.26
        result = simulate_cool_roof(self.model, NAMES, _features(), 50, 180,
                                    training_distributions=distributions)
        self.assertTrue(result["training_support"]["is_ood"])
        distributions["albedo"]["max"] = 0.27
        with self.assertRaisesRegex(ValueError, "outside observed training support"):
            simulate_cool_roof(self.model, NAMES, _features(), 50, 180,
                               training_distributions=distributions)

    def test_saved_model_wrappers_use_matching_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            processed = root / "data" / "processed"
            processed.mkdir(parents=True)
            dataset = processed / "greenpulse_ml_grid.parquet"
            pq.write_table(pa.table({"grid_id": ["ARTIFICIAL-CELL"], "plantable_ground_m2": [120.0],
                                     "eligible_roof_area_m2": [180.0],
                                     **{name: [value] for name, value in _features().items()}}), dataset)
            (processed / "metadata.json").write_text(json.dumps({
                "row_count": 1, "features": NAMES, "crs": "EPSG:32643",
                "raster_resolution_m": 30, "date_range": "2025-03-01/2025-05-31",
                "source": "ARTIFICIAL TEST FIXTURE", "capacity_fields": {
                    "plantable_ground_m2": {"verification_status": "verified", "source": "ARTIFICIAL TEST FIXTURE", "method": "ARTIFICIAL TEST FIXTURE calculation", "source_sha256": "sha256:" + "0" * 64},
                    "eligible_roof_area_m2": {"verification_status": "verified", "source": "ARTIFICIAL TEST FIXTURE", "method": "ARTIFICIAL TEST FIXTURE calculation", "source_sha256": "sha256:" + "1" * 64}}}), encoding="utf-8")
            models = root / "models"
            models.mkdir()
            model_path = models / "xgboost_lst.joblib"
            metadata_path = models / "model_metadata.json"
            joblib.dump(self.model, model_path)
            metadata_path.write_text(json.dumps({
                "feature_list": NAMES, "dataset_version": "sha256:" + hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "target": "lst_c", "objective": "reg:squarederror", "dataset_rows": 1,
                "dataset_date_range": "2025-03-01/2025-05-31", "crs": "EPSG:32643",
                "resolution_m": 30, "training_feature_distributions": _distributions(),
                "model_artifact_sha256": "sha256:" + hashlib.sha256(model_path.read_bytes()).hexdigest()}), encoding="utf-8")
            roof = simulate_saved_cool_roof(dataset, model_path, metadata_path,
                                            "ARTIFICIAL-CELL", 50, 180)
            combined = simulate_saved_combined(dataset, model_path, metadata_path,
                                               "ARTIFICIAL-CELL", 10, 120, 50, 180)
            self.assertEqual(roof["grid_id"], "ARTIFICIAL-CELL")
            self.assertEqual(combined["scenario_type"], "tree_canopy_and_cool_roof")
            derived = simulate_saved_cool_roof(dataset, model_path, metadata_path,
                                               "ARTIFICIAL-CELL", 50, None)
            self.assertEqual(derived["feasibility"]["eligible_roof"]["source_type"],
                             "calculated_verified_spatial_input")


if __name__ == "__main__":
    unittest.main()
