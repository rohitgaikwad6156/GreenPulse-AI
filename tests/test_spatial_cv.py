"""Tests use labelled artificial coordinates, never Pune validation scores."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.ml.spatial_cv import (
    SpatialBlockCV, assign_spatial_blocks, build_cv_artifacts,
    make_spatial_folds, summarize_blocks,
)


def _artificial_grid():
    x, y = [], []
    for bx in range(4):
        for by in range(3):
            for repeat in range(2 + bx):
                x.append(500000 + bx * 5000 + 15 + repeat * 30)
                y.append(2050000 + by * 5000 + 15)
    return np.array(x, dtype=float), np.array(y, dtype=float)


class SpatialCvTests(unittest.TestCase):
    def test_exact_floor_formula_and_block_boundary(self):
        x = np.array([100.0, 5099.9, 5100.0, 100.0])
        y = np.array([200.0, 200.0, 200.0, 5200.0])
        bx, by, ids, x_min, y_min = assign_spatial_blocks(x, y)
        self.assertEqual((x_min, y_min), (100.0, 200.0))
        np.testing.assert_array_equal(bx, [0, 0, 1, 0])
        np.testing.assert_array_equal(by, [0, 0, 0, 1])
        self.assertEqual(ids.tolist(), ["0:0", "0:0", "1:0", "0:1"])

    def test_five_folds_are_exclusive_complete_and_reproducible(self):
        x, y = _artificial_grid()
        assignment = make_spatial_folds(x, y)
        splitter = SpatialBlockCV(assignment)
        self.assertEqual(splitter.get_n_splits(), 5)
        validations = []
        for train, validation in splitter.split(X=x, groups=assignment.block_id):
            self.assertFalse(set(train) & set(validation))
            self.assertFalse(set(assignment.block_id[train]) & set(assignment.block_id[validation]))
            validations.extend(validation.tolist())
        self.assertEqual(sorted(validations), list(range(len(x))))
        blocks, folds = summarize_blocks(assignment)
        self.assertEqual(len(blocks), 12)
        self.assertEqual(sum(item["validation_rows"] for item in folds), len(x))
        self.assertTrue(all(item["validation_blocks"] >= 1 for item in folds))
        self.assertEqual(len({item["block_id"] for item in blocks}), len(blocks))
        shuffled = np.arange(len(x))[::-1]
        again = make_spatial_folds(x[shuffled], y[shuffled])
        first_map = {block["block_id"]: block["validation_fold"] for block in blocks}
        second_map = {block["block_id"]: block["validation_fold"] for block in summarize_blocks(again)[0]}
        self.assertEqual(first_map, second_map)

    def test_invalid_and_insufficient_blocks_fail(self):
        with self.assertRaisesRegex(ValueError, "at least 5"):
            make_spatial_folds([0, 100, 200, 300], [0, 0, 0, 0])
        with self.assertRaisesRegex(ValueError, "finite"):
            assign_spatial_blocks([0, np.nan], [0, 0])
        with self.assertRaisesRegex(ValueError, "equal-length"):
            assign_spatial_blocks([0, 1], [0])
        x, y = _artificial_grid()
        assignment = make_spatial_folds(x, y)
        with self.assertRaisesRegex(ValueError, "groups must match"):
            list(SpatialBlockCV(assignment).split(groups=np.zeros(len(x), dtype=int)))

    def test_artifacts_map_and_block_parquet(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            x, y = _artificial_grid()
            dataset = root / "greenpulse_ml_grid.parquet"
            pq.write_table(pa.table({"x": x, "y": y}), dataset)
            (root / "metadata.json").write_text(json.dumps({"crs": "EPSG:32643",
                "raster_resolution_m": 30, "row_count": len(x),
                "source": "ARTIFICIAL TEST FIXTURE"}))
            report = build_cv_artifacts(dataset, root / "cv")
            self.assertEqual(report["row_count"], len(x))
            self.assertEqual(report["unique_blocks"], 12)
            self.assertFalse(report["block_overlap_between_train_and_validation"])
            self.assertTrue((root / "cv" / "spatial_cv_folds.png").is_file())
            self.assertEqual(pq.read_table(root / "cv" / "spatial_cv_blocks.parquet").num_rows, 12)
            self.assertEqual(json.loads((root / "cv" / "spatial_cv_metadata.json").read_text())["n_folds"], 5)


if __name__ == "__main__":
    unittest.main()
