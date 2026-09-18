"""TreeSHAP tests use ARTIFICIAL TEST FIXTURES, never Pune measurements."""

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

from backend.app.ml.shap_explain import explain_saved_model, feature_correlations


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    rng = np.random.default_rng(93)
    n = 100
    ndvi = rng.uniform(0.1, 0.7, n)
    ndvi_context = ndvi * 0.98 + rng.normal(0, 0.002, n)
    ndbi = rng.uniform(-0.3, 0.5, n)
    albedo = rng.uniform(0.1, 0.4, n)
    roads = rng.uniform(0, 0.02, n)
    target = 35 - 3 * ndvi + 4 * ndbi - 2 * albedo + 8 * roads + rng.normal(0, 0.2, n)
    names = ["ndvi", "ndvi_mean_3x3", "ndbi", "albedo", "road_density"]
    data_dir = root / "data" / "processed"
    data_dir.mkdir(parents=True)
    dataset = data_dir / "greenpulse_ml_grid.parquet"
    pq.write_table(pa.table({"grid_id": [f"ARTIFICIAL-{i}" for i in range(n)],
                             "x": 500000 + np.arange(n) * 30, "y": 2050000 + np.arange(n) * 30,
                             "lst_c": target, "ndvi": ndvi, "ndvi_mean_3x3": ndvi_context,
                             "ndbi": ndbi, "albedo": albedo, "road_density": roads}), dataset)
    (data_dir / "metadata.json").write_text(json.dumps({
        "crs": "EPSG:32643", "raster_resolution_m": 30, "row_count": n,
        "features": names, "source": "ARTIFICIAL TEST FIXTURE"}), encoding="utf-8")
    matrix = np.column_stack([ndvi, ndvi_context, ndbi, albedo, roads])
    model = XGBRegressor(objective="reg:squarederror", n_estimators=35, max_depth=3,
                         tree_method="hist", n_jobs=1, random_state=7)
    model.fit(matrix, target)
    model_dir = root / "models"
    model_dir.mkdir()
    model_path = model_dir / "xgboost_lst.joblib"
    metadata_path = model_dir / "model_metadata.json"
    joblib.dump(model, model_path)
    metadata_path.write_text(json.dumps({
        "feature_list": names, "dataset_version": "sha256:" + hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "dataset_rows": n, "crs": "EPSG:32643", "resolution_m": 30,
        "target": "lst_c", "objective": "reg:squarederror"}), encoding="utf-8")
    return dataset, model_path, metadata_path


class TreeShapTests(unittest.TestCase):
    def test_global_local_additivity_and_ui_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset, model, metadata = _fixture(root)
            output = root / "output"
            global_report, local = explain_saved_model(dataset, model, metadata,
                                                       "ARTIFICIAL-7", output, sample_size=80)
            self.assertEqual(global_report["sample_rows"], 80)
            self.assertEqual(global_report["target"], "LST")
            self.assertEqual(len(global_report["feature_importance_bar_data"]), 5)
            self.assertTrue(any(pair["feature_a"] == "ndvi" and pair["feature_b"] == "ndvi_mean_3x3"
                                for pair in global_report["feature_correlations"]["highly_redundant_pairs"]))
            self.assertAlmostEqual(local["baseline_lST"] + sum(row["shap_value_c"] for row in local["features"]),
                                   local["predicted_lst"], places=3)
            self.assertAlmostEqual(sum(row["warming_percentage_ui"] for row in local["features"]), 100, places=5)
            self.assertAlmostEqual(sum(row["shap_value_c"] for row in local["group_contributions"]),
                                   local["predicted_lst"] - local["baseline_lST"], places=3)
            self.assertEqual(local["waterfall_data"][-1]["end_c"],
                             local["baseline_lST"] + sum(row["shap_value_c"] for row in local["features"]))
            self.assertTrue(all(row["warming_percentage_ui"] == 0 for row in local["features"]
                                if row["direction"] != "warming"))
            for filename in ("shap_global.json", "shap_local.json", "shap_global_importance.png",
                             "shap_local_waterfall.png"):
                self.assertTrue((output / filename).is_file())

    def test_model_dataset_mismatch_and_missing_model_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset, model, metadata = _fixture(root)
            with self.assertRaisesRegex(ValueError, "required"):
                explain_saved_model(dataset, root / "missing.joblib", metadata, "ARTIFICIAL-0", root / "out")
            report = json.loads(metadata.read_text())
            report["dataset_version"] = "sha256:wrong"
            metadata.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "does not match"):
                explain_saved_model(dataset, model, metadata, "ARTIFICIAL-0", root / "out")

    def test_correlation_invalid_and_constant(self):
        with self.assertRaises(ValueError):
            feature_correlations(np.array([[1.0, float("nan")]]), ["a", "b"])
        report = feature_correlations(np.array([[1.0, 2.0], [1.0, 3.0]]), ["a", "b"])
        self.assertIsNone(report["pairs"][0]["pearson_r"])


if __name__ == "__main__":
    unittest.main()
