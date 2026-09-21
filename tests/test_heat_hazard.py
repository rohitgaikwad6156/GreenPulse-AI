"""Heat Hazard Score tests use ARTIFICIAL TEST FIXTURES only."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.ml.heat_hazard import (
    derive_heat_hazard_references, heat_hazard_score, score_from_model_metadata,
)


def _fixture(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    directory = root / "data" / "processed"
    directory.mkdir(parents=True)
    observed = np.linspace(29.0, 44.0, 100)
    dataset = directory / "greenpulse_ml_grid.parquet"
    pq.write_table(pa.table({"grid_id": [f"ARTIFICIAL-CITY-{i}" for i in range(100)],
                             "x": np.arange(100) * 30.0 + 500000,
                             "y": np.arange(100) * 30.0 + 2050000,
                             "lst_c": observed, "ndvi": np.linspace(0.1, 0.8, 100)}), dataset)
    (directory / "metadata.json").write_text(json.dumps({
        "crs": "EPSG:32643", "raster_resolution_m": 30, "row_count": 100,
        "date_range": "2025-03-01/2025-05-31", "features": ["ndvi"],
        "source": "ARTIFICIAL TEST FIXTURE"}), encoding="utf-8")
    rural = directory / "periurban_lst_reference.parquet"
    pq.write_table(pa.table({"grid_id": [f"ARTIFICIAL-PERIURBAN-{i}" for i in range(30)],
                             "lst_c": np.linspace(25.0, 31.0, 30)}), rural)
    provenance = directory / "periurban_lst_reference_metadata.json"
    provenance.write_text(json.dumps({
        "source_organization": "ARTIFICIAL TEST FIXTURE",
        "source_product": "ARTIFICIAL TEST FIXTURE",
        "source_scene_or_composite": "ARTIFICIAL TEST FIXTURE",
        "periurban_area_definition": "ARTIFICIAL TEST FIXTURE",
        "area_boundary_source": "ARTIFICIAL TEST FIXTURE",
        "qa_mask_method": "ARTIFICIAL TEST FIXTURE",
        "temperature_variable": "land_surface_temperature", "units": "degC",
        "date_range": "2025-03-01/2025-05-31",
        "region": "Pune rural/peri-urban outside PMC/PCMC"}), encoding="utf-8")
    model_dir = root / "models"
    model_dir.mkdir()
    model = model_dir / "xgboost_lst.joblib"
    model.write_text("ARTIFICIAL TEST FIXTURE; not a model", encoding="utf-8")
    model_metadata = model_dir / "model_metadata.json"
    model_metadata.write_text(json.dumps({
        "target": "lst_c", "objective": "reg:squarederror", "feature_list": ["ndvi"],
        "model_artifact_sha256": "sha256:" + hashlib.sha256(model.read_bytes()).hexdigest(),
        "dataset_version": "sha256:" + hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "dataset_rows": 100, "dataset_date_range": "2025-03-01/2025-05-31",
        "crs": "EPSG:32643", "resolution_m": 30}), encoding="utf-8")
    return dataset, model, model_metadata, rural, provenance


class HeatHazardTests(unittest.TestCase):
    def test_transparent_score_and_clipping(self):
        self.assertEqual(heat_hazard_score(30.0, 30.0, 40.0), 0.0)
        self.assertEqual(heat_hazard_score(35.0, 30.0, 40.0), 50.0)
        self.assertEqual(heat_hazard_score(40.0, 30.0, 40.0), 100.0)
        np.testing.assert_array_equal(heat_hazard_score(np.array([25.0, 35.0, 45.0]), 30.0, 40.0),
                                      np.array([0.0, 50.0, 100.0]))

    def test_invalid_temperatures_and_references(self):
        for value, background, hot in ((float("nan"), 30, 40), (35, 40, 40),
                                       (35, 45, 40), (-274, 30, 40), (35, -274, 40)):
            with self.assertRaises(ValueError):
                heat_hazard_score(value, background, hot)
        with self.assertRaises(ValueError):
            heat_hazard_score(np.array([30.0, float("inf")]), 30, 40)

    def test_observed_references_are_stored_separately_from_model_target(self):
        with tempfile.TemporaryDirectory() as temp:
            dataset, model, metadata, rural, provenance = _fixture(Path(temp))
            reference = derive_heat_hazard_references(dataset, model, metadata, rural, provenance)
            self.assertEqual(reference["name"], "Heat Hazard Score")
            self.assertEqual(reference["background_lst_c"], 28.0)
            self.assertAlmostEqual(reference["hot_reference_lst_c"],
                                   float(np.percentile(np.linspace(29, 44, 100), 95)))
            self.assertEqual(reference["background_rows"], 30)
            self.assertEqual(reference["hot_reference_rows"], 100)
            saved = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual(saved["target"], "lst_c")
            self.assertEqual(saved["heat_hazard_score"]["hot_reference_lst_c"], reference["hot_reference_lst_c"])
            self.assertEqual(score_from_model_metadata(35.0, metadata),
                             heat_hazard_score(35.0, 28.0, reference["hot_reference_lst_c"]))

    def test_missing_or_mismatched_provenance_does_not_write_score(self):
        with tempfile.TemporaryDirectory() as temp:
            dataset, model, metadata, rural, provenance = _fixture(Path(temp))
            with self.assertRaisesRegex(ValueError, "required"):
                derive_heat_hazard_references(dataset, model, metadata, rural.with_name("missing.parquet"), provenance)
            self.assertNotIn("heat_hazard_score", json.loads(metadata.read_text()))
            document = json.loads(provenance.read_text())
            document["date_range"] = "2024-03-01/2024-05-31"
            provenance.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "same-season"):
                derive_heat_hazard_references(dataset, model, metadata, rural, provenance)
            self.assertNotIn("heat_hazard_score", json.loads(metadata.read_text()))
            with self.assertRaisesRegex(ValueError, "unavailable"):
                score_from_model_metadata(35.0, metadata)

    def test_overlapping_periurban_ids_and_stale_model_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            dataset, model, metadata, rural, provenance = _fixture(Path(temp))
            table = pq.read_table(rural).to_pydict()
            table["grid_id"][0] = "ARTIFICIAL-CITY-0"
            pq.write_table(pa.table(table), rural)
            with self.assertRaisesRegex(ValueError, "overlapping"):
                derive_heat_hazard_references(dataset, model, metadata, rural, provenance)
            self.assertNotIn("heat_hazard_score", json.loads(metadata.read_text()))
            dataset, model, metadata, rural, provenance = _fixture(Path(temp) / "stale")
            model.write_text("CHANGED ARTIFICIAL MODEL", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "do not match"):
                derive_heat_hazard_references(dataset, model, metadata, rural, provenance)


if __name__ == "__main__":
    unittest.main()
