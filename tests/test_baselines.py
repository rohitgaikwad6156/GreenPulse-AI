"""Baseline tests use artificial temporary data, never Pune scores."""

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.ml.baselines import evaluate_baselines, regression_metrics
from backend.app.ml.spatial_cv import build_cv_artifacts


def _artificial_dataset(root: Path) -> Path:
    rng = np.random.default_rng(7)
    block = np.repeat(np.arange(10), 25)
    within = np.tile(np.arange(25), 10)
    x = 500000.0 + block * 5000 + (within % 5) * 30 + 15
    y = 2050000.0 + (within // 5) * 30 + 15
    ndvi = 0.2 + 0.05 * block + 0.005 * within
    ndbi = 0.6 - 0.04 * block + 0.003 * within
    target = 30 + 5 * ndbi - 3 * ndvi + 0.2 * block + rng.normal(0, 0.2, len(block))
    dataset = root / "data" / "processed" / "greenpulse_ml_grid.parquet"
    dataset.parent.mkdir(parents=True)
    pq.write_table(pa.table({"x": x, "y": y, "lst_c": target,
                             "ndvi": ndvi, "ndbi": ndbi}), dataset)
    dataset.with_name("metadata.json").write_text(json.dumps({
        "crs": "EPSG:32643", "raster_resolution_m": 30,
        "row_count": len(block), "date_range": "2025-03-01/2025-05-31",
        "features": ["ndvi", "ndbi"], "source": "ARTIFICIAL TEST FIXTURE"}))
    build_cv_artifacts(dataset, dataset.parent)
    return dataset


class BaselineTests(unittest.TestCase):
    def test_metric_formulas(self):
        result = regression_metrics([1, 2, 3], [1, 1, 4])
        self.assertAlmostEqual(result["mae_c"], 2 / 3)
        self.assertAlmostEqual(result["rmse_c"], math.sqrt(2 / 3))
        self.assertAlmostEqual(result["r2"], 0)
        with self.assertRaisesRegex(ValueError, "zero variance"):
            regression_metrics([2, 2], [1, 2])
        with self.assertRaisesRegex(ValueError, "at least two"):
            regression_metrics([1], [1])

    def test_three_models_share_saved_folds_and_write_only_test_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = _artificial_dataset(root)
            output = root / "models" / "baseline_metrics.json"
            report = evaluate_baselines(dataset, dataset.parent, output, rf_trees=8, rf_jobs=1)
            self.assertEqual(set(report["models"]), {"linear_regression", "decision_tree", "random_forest"})
            self.assertTrue(report["same_saved_folds_for_every_model"])
            validation_patterns = []
            for model in report["models"].values():
                self.assertEqual(len(model["folds"]), 5)
                validation_patterns.append([(fold["validation_rows"], fold["validation_blocks"])
                                            for fold in model["folds"]])
                self.assertEqual(sum(fold["validation_rows"] for fold in model["folds"]), 250)
                for fold in model["folds"]:
                    self.assertTrue(math.isfinite(fold["mae_c"]))
                    self.assertTrue(math.isfinite(fold["rmse_c"]))
                    self.assertTrue(math.isfinite(fold["r2"]))
                    self.assertGreaterEqual(fold["mae_c"], 0)
                    self.assertGreaterEqual(fold["rmse_c"], 0)
            self.assertEqual(validation_patterns[0], validation_patterns[1])
            self.assertEqual(validation_patterns[1], validation_patterns[2])
            self.assertTrue(output.is_file())
            self.assertTrue(output.with_name("baseline_comparison.png").is_file())
            self.assertEqual(json.loads(output.read_text())["target"], "lst_c")

    def test_missing_real_dataset_and_invalid_feature_metadata_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "baseline_metrics.json"
            with self.assertRaisesRegex(ValueError, "missing"):
                evaluate_baselines(root / "absent.parquet", root, output)
            self.assertFalse(output.exists())
            dataset = _artificial_dataset(root)
            metadata_path = dataset.with_name("metadata.json")
            metadata = json.loads(metadata_path.read_text())
            metadata["features"].append("lst_c")
            metadata_path.write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "target/identity leakage"):
                evaluate_baselines(dataset, dataset.parent, output, rf_trees=5, rf_jobs=1)
            self.assertFalse(output.exists())

    def test_changed_fold_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = _artificial_dataset(root)
            mapping = dataset.parent / "spatial_cv_blocks.parquet"
            table = pq.read_table(mapping)
            values = table.to_pydict()
            values["validation_fold"][0] = 1 + values["validation_fold"][0] % 5
            pq.write_table(pa.table(values), mapping)
            with self.assertRaisesRegex(ValueError, "mapping differs from metadata"):
                evaluate_baselines(dataset, dataset.parent, root / "models" / "baseline_metrics.json",
                                   rf_trees=5, rf_jobs=1)


if __name__ == "__main__":
    unittest.main()
