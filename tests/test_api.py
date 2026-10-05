"""API contract tests use temporary ARTIFICIAL / SYNTHETIC grid fixtures."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.api import routes, services
from backend.app.main import app, health_check
from backend.app.schemas.api import (
    DidRequest,
    ExplainRequest,
    GridIdRequest,
    OptimizeRequest,
    SimulateRequest,
)


class ApiTests(unittest.TestCase):
    def test_swagger_contains_all_requested_endpoints_and_schemas(self):
        spec = app.openapi()
        expected = {
            "/api/health": "get", "/api/model/metrics": "get", "/api/wards": "get",
            "/api/grid": "get", "/api/ward/{ward_id}": "get", "/api/predict": "post",
            "/api/explain": "post", "/api/simulate": "post", "/api/optimize": "post",
            "/api/optimizer/config": "get", "/api/optimizer/locations": "get",
            "/api/validation/did": "post", "/api/methodology": "get",
            "/api/validation/demo": "get", "/api/validation/datasets": "get",
            "/api/validation/analyze/{dataset_id}": "post",
            "/api/research/status": "get", "/api/research/sensors/nearby": "get",
        }
        for path, method in expected.items():
            self.assertIn(path, spec["paths"])
            operation = spec["paths"][path][method]
            self.assertIn("responses", operation)
            self.assertIn("200", operation["responses"])
        self.assertEqual(health_check(), {"status": "ok"})

    def test_input_validation_and_missing_artifact_errors(self):
        for invalid in (
            {"grid_id": "x", "scenario_type": "tree_canopy",
             "canopy_increase_percentage_points": -1, "feasible_ground_area_m2": 100},
            {"grid_id": "x", "scenario_type": "cool_roof",
             "retrofit_fraction": 1.1, "eligible_roof_area_m2": 50},
            {"grid_id": "x", "scenario_type": "cool_roof",
             "retrofit_fraction": 0.5, "eligible_roof_area_m2": 901},
        ):
            with self.assertRaises(ValidationError):
                SimulateRequest(**invalid)
        for invalid in ({"budget_inr": -1}, {"location_id": ""}):
            valid = {"location_id": "ARTIFICIAL TEST AREA", "budget_inr": 100,
                     "maintenance_cap_inr_per_year": 10}
            valid.update(invalid)
            with self.assertRaises(ValidationError):
                OptimizeRequest(**valid)
        valid = {"location_id": "ARTIFICIAL TEST AREA", "budget_inr": 100,
                 "maintenance_cap_inr_per_year": 10}
        for weights in ({"cooling": 0, "green_cover": 0, "co_benefit": 0},
                        {"cooling": -1, "green_cover": 1, "co_benefit": 0}):
            with self.assertRaises(ValidationError):
                OptimizeRequest(**valid, priority_weights=weights)
        with patch.object(services, "MODEL", Path("missing_model.joblib")), \
             patch.object(services, "MODEL_METADATA", Path("missing_meta.json")), \
             patch.object(services, "GRID", Path("missing_grid.parquet")), \
             patch.object(services, "GRID_METADATA", Path("missing_grid_meta.json")):
            with self.assertRaises(HTTPException) as context:
                routes.get_model_metrics()
            self.assertEqual(context.exception.status_code, 503)
            with self.assertRaises(HTTPException) as context:
                routes.post_predict(GridIdRequest(grid_id="missing"))
            self.assertEqual(context.exception.status_code, 503)
            with self.assertRaises(HTTPException) as context:
                routes.post_explain(ExplainRequest(grid_id="missing"))
            self.assertEqual(context.exception.status_code, 503)

    def test_grid_and_ward_routes_on_labelled_artificial_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            grid = folder / "grid.parquet"
            metadata = folder / "metadata.json"
            pq.write_table(pa.table({
                "grid_id": ["ARTIFICIAL-1", "ARTIFICIAL-2", "ARTIFICIAL-3"],
                "x": [1.0, 31.0, 61.0], "y": [1.0, 1.0, 1.0],
                "latitude": [18.0, 18.0, 18.0], "longitude": [73.0, 73.0, 73.0],
                "ward_id": ["A", "A", "B"], "ward_name": ["Test A", "Test A", "Test B"],
                "lst_c": [30.0, 32.0, 34.0], "ndvi": [0.2, 0.3, 0.1],
            }), grid)
            metadata.write_text(json.dumps({"raster_resolution_m": 30,
                                            "features": ["ndvi"], "row_count": 3}), encoding="utf-8")
            with patch.object(services, "GRID", grid), patch.object(services, "GRID_METADATA", metadata), \
                 patch.object(services, "_require_ward_reporting", return_value=folder / "ARTIFICIAL-WARDS.geojson"):
                wards = routes.get_wards()
                self.assertEqual(wards["total"], 2)
                self.assertEqual(wards["wards"][0]["grid_cell_count"], 2)
                page = routes.get_grid(limit=1, offset=1, ward_id="A")
                self.assertEqual(page["total"], 2)
                self.assertEqual(page["cells"][0]["grid_id"], "ARTIFICIAL-2")
                self.assertEqual(page["cells"][0]["features"], {"ndvi": 0.3})
                self.assertEqual(routes.get_ward("A")["observed_lst_c_mean"], 31)
                with self.assertRaises(HTTPException) as context:
                    routes.get_ward("Z")
                self.assertEqual(context.exception.status_code, 404)

    def test_cell_grid_remains_available_without_ward_reporting(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            grid = folder / "grid.parquet"
            metadata = folder / "metadata.json"
            pq.write_table(pa.table({
                "grid_id": ["ARTIFICIAL-1"], "x": [1.0], "y": [1.0],
                "latitude": [18.0], "longitude": [73.0],
                "ward_id": pa.array([None], type=pa.string()),
                "ward_name": pa.array([None], type=pa.string()),
                "lst_c": [30.0], "ndvi": [0.2],
            }), grid)
            metadata.write_text(json.dumps({"raster_resolution_m": 30,
                                            "features": ["ndvi"], "row_count": 1,
                                            "ward_reporting_available": False}), encoding="utf-8")
            with patch.object(services, "GRID", grid), patch.object(services, "GRID_METADATA", metadata):
                cell = routes.get_grid(limit=10, offset=0, ward_id=None)["cells"][0]
                self.assertIsNone(cell["ward_id"])
                self.assertIsNone(cell["ward_name"])
                for call in (routes.get_wards, lambda: routes.get_ward("PMC:1"),
                             lambda: routes.get_grid(limit=10, offset=0, ward_id="PMC:1")):
                    with self.assertRaises(HTTPException) as context:
                        call()
                    self.assertEqual(context.exception.status_code, 503)

    def test_did_uses_paired_user_values_and_labels_provenance(self):
        request = DidRequest(intervention="ARTIFICIAL TEST INTERVENTION",
                             pre_period="artificial pre", post_period="artificial post",
                             observations=[
                                 {"grid_id": "T", "group": "treated", "period": "pre", "lst_c": 35},
                                 {"grid_id": "T", "group": "treated", "period": "post", "lst_c": 32},
                                 {"grid_id": "C", "group": "control", "period": "pre", "lst_c": 33},
                                 {"grid_id": "C", "group": "control", "period": "post", "lst_c": 32},
                             ])
        result = routes.post_validation_did(request)
        self.assertEqual(result["difference_in_differences_c"], -2)
        self.assertIn("PROVENANCE NOT VERIFIED", result["label"])
        bad = request.model_copy(update={"post_period": "artificial pre"})
        with self.assertRaises(HTTPException) as context:
            routes.post_validation_did(bad)
        self.assertEqual(context.exception.status_code, 422)

    def test_methodology_reports_validated_grid_availability(self):
        with patch.object(services, "_real_grid", side_effect=services.DataUnavailableError("unavailable")):
            result = routes.get_methodology()
        self.assertIn("LST", result["target"])
        self.assertFalse(result["data_status"]["real_ml_grid_available"])
        self.assertFalse(result["data_status"]["trained_model_available"])
        self.assertFalse(result["data_status"]["optimizer_location_available"])
        self.assertFalse(result["data_status"]["real_validation_dataset_available"])

    def test_optimizer_exposes_no_unverified_production_location(self):
        result = routes.get_optimizer_locations()
        self.assertEqual(result["locations"], [])
        self.assertEqual(result["total"], 0)
        self.assertTrue(result["blockers"])

    def test_real_validation_registry_is_blocked_without_genuine_data(self):
        result = routes.get_validation_datasets()
        self.assertEqual(result["datasets"], [])
        self.assertEqual(result["validation_status"], "BLOCKED")
        with self.assertRaises(HTTPException) as context:
            routes.post_validation_analysis("missing-dataset")
        self.assertEqual(context.exception.status_code, 404)

    def test_research_status_keeps_point_and_context_layers_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = root / "data" / "research" / "layers.json"
            registry.parent.mkdir(parents=True)
            source = root / "synthetic-exposure.txt"
            source.write_bytes(b"SYNTHETIC API FIXTURE; not population observations")
            registry.write_text(json.dumps({"schema_version": "1.0", "layers": [
                {"layer_id": "test_exposure", "layer_type": "exposure",
                 "status": "source_verified_processing_blocked", "source": {
                     "local_path": source.name,
                     "checksum": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()}},
                {"layer_id": "test_vulnerability", "layer_type": "vulnerability", "status": "missing"},
            ]}), encoding="utf-8")
            with patch.object(services, "RESEARCH_LAYERS", registry), \
                 patch.object(services, "SENSOR_IMPORTS", root / "sensors"):
                result = routes.get_research_status()
        self.assertEqual(result["sensors"]["status"], "missing")
        self.assertFalse(result["sensors"]["wall_to_wall_interpolation"])
        self.assertTrue(result["context_layers"]["heat_hazard_score_separate"])
        self.assertFalse(result["context_layers"]["composite_risk_available"])


if __name__ == "__main__":
    unittest.main()
