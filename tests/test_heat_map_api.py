"""Map tests use ARTIFICIAL / SYNTHETIC fixture geometry and model only."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import HTTPException
from pyproj import Transformer
from xgboost import XGBRegressor

from backend.app.api import map_data, map_routes, services
from backend.app.main import app


def artificial_files(root: Path):
    boundary = root / "wards.geojson"
    features = []
    for municipality, number, name, west in (("PMC", "1", "Test PMC", 73.78),
                                              ("PCMC", "2", "Test PCMC", 73.88)):
        features.append({"type": "Feature", "properties": {
            "municipality": municipality, "ward_id": number, "ward_name": name},
            "geometry": {"type": "Polygon", "coordinates": [[
                [west, 18.48], [west + 0.07, 18.48], [west + 0.07, 18.55],
                [west, 18.55], [west, 18.48]]]}})
    boundary.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    lon = [73.80, 73.81, 73.90, 73.91]
    lat = [18.50, 18.51, 18.50, 18.51]
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform(lon, lat)
    grid = root / "greenpulse_ml_grid.parquet"
    pq.write_table(pa.table({
        "grid_id": [f"ARTIFICIAL-{i}" for i in range(4)],
        "ward_id": ["PMC:1", "PMC:1", "PCMC:2", "PCMC:2"],
        "ward_name": ["Test PMC", "Test PMC", "Test PCMC", "Test PCMC"],
        "x": x, "y": y, "latitude": lat, "longitude": lon,
        "lst_c": [34.0, 35.0, 36.0, 37.0],
        "ndvi": [0.2, 0.3, 0.1, 0.15], "ndbi": [0.2, 0.1, 0.3, 0.25],
    }), grid)
    grid_meta = root / "metadata.json"
    grid_meta.write_text(json.dumps({"crs": "EPSG:32643", "raster_resolution_m": 30,
                                     "row_count": 4, "features": ["ndvi", "ndbi"]}), encoding="utf-8")
    rng = np.random.default_rng(11)
    training = rng.uniform(0, 1, size=(40, 2))
    target = 35 - 2 * training[:, 0] + training[:, 1]
    model = XGBRegressor(objective="reg:squarederror", n_estimators=12, max_depth=2,
                         tree_method="hist", random_state=11, n_jobs=1)
    model.fit(training, target)
    model_path = root / "xgboost_lst.joblib"
    joblib.dump(model, model_path)
    metadata = root / "model_metadata.json"
    metadata.write_text(json.dumps({
        "feature_list": ["ndvi", "ndbi"], "dataset_version": "sha256:" + hashlib.sha256(grid.read_bytes()).hexdigest(),
        "dataset_rows": 4, "crs": "EPSG:32643", "resolution_m": 30,
        "target": "lst_c", "objective": "reg:squarederror",
    }), encoding="utf-8")
    return boundary, grid, grid_meta, model_path, metadata


class HeatMapApiTests(unittest.TestCase):
    def test_missing_real_layers_report_unavailable(self):
        with self.assertRaises(HTTPException) as context:
            map_routes.map_wards()
        self.assertEqual(context.exception.status_code, 503)
        with self.assertRaises(HTTPException) as context:
            map_routes.map_ward_heat()
        self.assertEqual(context.exception.status_code, 503)

    def test_ward_and_cell_heat_selection_with_artificial_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            boundary, grid, grid_meta, model, metadata = artificial_files(Path(temp))
            map_data._verified_model.cache_clear()
            map_data._ward_prediction_summary.cache_clear()
            with (patch.object(map_data, "BOUNDARY", boundary),
                  patch.object(services, "GRID", grid),
                  patch.object(services, "GRID_METADATA", grid_meta),
                  patch.object(services, "MODEL", model),
                  patch.object(services, "MODEL_METADATA", metadata)):
                wards = map_routes.map_wards()
                self.assertEqual({f["properties"]["ward_id"] for f in wards["features"]},
                                 {"PMC:1", "PCMC:2"})
                heat = map_routes.map_ward_heat()
                self.assertEqual(len(heat["features"]), 2)
                self.assertTrue(all(np.isfinite(f["properties"]["predicted_lst_c"])
                                    for f in heat["features"]))
                cells = map_routes.map_cell_heat(73.79, 18.49, 73.82, 18.52)
                self.assertEqual(len(cells["features"]), 2)
                self.assertFalse(cells["too_many_cells"])
                self.assertEqual(cells["features"][0]["geometry"]["type"], "Polygon")
                cell = map_routes.map_cell_detail("ARTIFICIAL-0")
                self.assertEqual(cell["selection_type"], "grid_cell")
                self.assertEqual(cell["ward_id"], "PMC:1")
                self.assertEqual(cell["geometry"]["type"], "Polygon")
                self.assertAlmostEqual(cell["latitude"], 18.50)
                self.assertIsNone(cell["heat_hazard_score"])
                self.assertEqual(cell["confidence"]["label"], "Unavailable")
                self.assertTrue(cell["top_shap_factors"])
                ward = map_routes.map_ward_detail("PMC:1")
                self.assertEqual(ward["grid_cell_count"], 2)
                self.assertEqual(ward["selection_type"], "ward")
                with self.assertRaises(HTTPException) as context:
                    map_routes.map_cell_detail("UNKNOWN")
                self.assertEqual(context.exception.status_code, 404)
            map_data._verified_model.cache_clear()
            map_data._ward_prediction_summary.cache_clear()

    def test_viewport_validation_and_openapi(self):
        with self.assertRaises(HTTPException) as context:
            map_routes.map_cell_heat(74, 18, 73, 19)
        self.assertEqual(context.exception.status_code, 422)
        paths = app.openapi()["paths"]
        for path in ("/api/map/wards", "/api/map/heat/wards", "/api/map/heat/cells",
                     "/api/map/cell/{grid_id}", "/api/map/ward/{ward_id}"):
            self.assertIn(path, paths)


if __name__ == "__main__":
    unittest.main()
