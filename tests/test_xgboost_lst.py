"""All model tests use ARTIFICIAL TEST FIXTURES in temporary directories."""

import json
import math
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.ml.baselines import evaluate_baselines
from backend.app.ml.spatial_cv import build_cv_artifacts
from backend.app.ml.xgboost_lst import train_xgboost_lst


def _fixture(root: Path) -> tuple[Path, Path]:
    rng = np.random.default_rng(11)
    block = np.repeat(np.arange(10), 18)
    cell = np.tile(np.arange(18), 10)
    x = 500000.0 + block * 5000 + (cell % 6) * 30 + 15
    y = 2050000.0 + (cell // 6) * 30 + 15
    ndvi = 0.15 + block * 0.045 + (cell % 6) * 0.008
    ndbi = 0.65 - block * 0.035 + (cell // 6) * 0.02
    target = 31 + 5 * ndbi - 2 * ndvi + block * 0.15 + rng.normal(0, 0.3, len(block))
    data_dir = root / "data" / "processed"
    data_dir.mkdir(parents=True)
    dataset = data_dir / "greenpulse_ml_grid.parquet"
    pq.write_table(pa.table({"x": x, "y": y, "lst_c": target,
                             "ndvi": ndvi, "ndbi": ndbi}), dataset)
    (data_dir / "metadata.json").write_text(json.dumps({
        "crs": "EPSG:32643", "raster_resolution_m": 30,
        "row_count": len(target), "date_range": "2025-03-01/2025-05-31",
        "features": ["ndvi", "ndbi"], "source": "ARTIFICIAL TEST FIXTURE"}))
    build_cv_artifacts(dataset, data_dir)
    baseline_path = root / "models" / "baseline_metrics.json"
    evaluate_baselines(dataset, data_dir, baseline_path, rf_trees=5, rf_jobs=1)
    return dataset, baseline_path


class XgboostLstTests(unittest.TestCase):
    def test_nested_spatial_training_and_final_model_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset, baselines = _fixture(root)
            model_path = root / "models" / "xgboost_lst.joblib"
            metadata_path = root / "models" / "model_metadata.json"
            report = train_xgboost_lst(dataset, dataset.parent, baselines, model_path,
                                       metadata_path, n_trials=1, inner_folds=2, jobs=1)
            self.assertEqual(report["objective"], "reg:squarederror")
            self.assertEqual(report["target"], "lst_c")
            self.assertEqual(report["feature_list"], ["ndvi", "ndbi"])
            self.assertEqual(report["resolution_m"], 30)
            self.assertEqual(report["crs"], "EPSG:32643")
            self.assertTrue(report["dataset_version"].startswith("sha256:"))
            self.assertEqual(len(report["outer_fold_results"]), 5)
            self.assertEqual(sum(fold["validation_rows"] for fold in report["outer_fold_results"]), 180)
            for fold in report["outer_fold_results"]:
                self.assertEqual(fold["inner_spatial_folds"], 2)
                self.assertEqual(fold["optuna_trials"], 1)
                self.assertTrue(all(math.isfinite(fold[key]) for key in ("mae_c", "rmse_c", "r2")))
                self.assertEqual(set(fold["selected_hyperparameters"]),
                                 {"max_depth", "learning_rate", "n_estimators", "subsample",
                                  "colsample_bytree", "gamma", "reg_alpha", "reg_lambda"})
            self.assertTrue(model_path.is_file())
            self.assertTrue(metadata_path.is_file())
            self.assertTrue(model_path.with_name("xgboost_baseline_comparison.png").is_file())
            model = joblib.load(model_path)
            self.assertEqual(model.get_params()["objective"], "reg:squarederror")
            self.assertEqual(model.predict(np.array([[0.2, 0.5]])).shape, (1,))
            self.assertEqual(json.loads(metadata_path.read_text())["dataset_version"], report["dataset_version"])

    def test_missing_data_or_mismatched_baselines_stop_without_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_path = root / "models" / "xgboost_lst.joblib"
            metadata_path = root / "models" / "model_metadata.json"
            with self.assertRaisesRegex(ValueError, "missing"):
                train_xgboost_lst(root / "absent.parquet", root, root / "absent.json",
                                  model_path, metadata_path, n_trials=1, inner_folds=2, jobs=1)
            dataset, baselines = _fixture(root)
            baseline_report = json.loads(baselines.read_text())
            baseline_report["feature_names"] = ["wrong_feature"]
            baselines.write_text(json.dumps(baseline_report))
            with self.assertRaisesRegex(ValueError, "do not match"):
                train_xgboost_lst(dataset, dataset.parent, baselines, model_path,
                                  metadata_path, n_trials=1, inner_folds=2, jobs=1)
            self.assertFalse(model_path.exists())
            self.assertFalse(metadata_path.exists())


if __name__ == "__main__":
    unittest.main()
