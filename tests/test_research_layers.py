"""Research-layer tests use explicitly synthetic point fixtures only."""

import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.app.research.layers import research_layer_status
from backend.app.research.sensors import (
    import_sensor_observations, nearby_sensor_context, sensor_status,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "data" / "source_manifest.json"


def sensor_fixture(root: Path, timestamp: str, *, minimum_stations: int = 1) -> tuple[Path, Path]:
    observations = root / "observations.csv"
    with observations.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "observation_id", "station_id", "timestamp_utc", "latitude", "longitude",
            "qa_status", "air_temperature_c", "relative_humidity_pct", "aqi"])
        writer.writeheader(); writer.writerow({
            "observation_id": "SYNTHETIC-OBS-1", "station_id": "SYNTHETIC-STATION-1",
            "timestamp_utc": timestamp, "latitude": 18.52, "longitude": 73.85,
            "qa_status": "valid", "air_temperature_c": 30,
            "relative_humidity_pct": 40, "aqi": 50,
        })
    manifest = {
        "schema_version": "1.0", "dataset_id": "SYNTHETIC_SENSORS",
        "dataset_version": "synthetic-v1", "evidence_status": "verified_point_observations",
        "observations_sha256": hashlib.sha256(observations.read_bytes()).hexdigest(),
        "source": {"organization": "SYNTHETIC TEST FIXTURE", "product": "SYNTHETIC point observations",
                   "url_or_identifier": "test://synthetic-sensors", "license": "TEST ONLY",
                   "access_date": "2026-09-21"},
        "variables": ["air_temperature_c", "relative_humidity_pct", "aqi"],
        "freshness_threshold_hours": 24, "temporal_match_tolerance_minutes": 30,
        "minimum_station_count_for_context": minimum_stations,
        "stations": [{"station_id": "SYNTHETIC-STATION-1", "provider_station_id": "TEST-1",
                      "latitude": 18.52, "longitude": 73.85, "measurement_height_m": 2,
                      "instrument": "SYNTHETIC TEST INSTRUMENT",
                      "calibration_reference": "SYNTHETIC TEST CALIBRATION"}],
    }
    path = root / "manifest.json"; path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, observations


class ResearchLayerTests(unittest.TestCase):
    def test_missing_sensor_state_and_separate_context_layers(self):
        with tempfile.TemporaryDirectory() as temp:
            status = sensor_status(Path(temp), SOURCE_MANIFEST)
        self.assertEqual(status["status"], "missing")
        self.assertFalse(status["wall_to_wall_interpolation"])
        layers = research_layer_status(ROOT / "data" / "research" / "research_layers.json")
        self.assertTrue(layers["heat_hazard_score_separate"])
        self.assertFalse(layers["composite_risk_available"])
        self.assertEqual(layers["exposure_layers"][0]["layer_type"], "exposure")
        self.assertEqual(layers["vulnerability_layers"][0]["layer_type"], "vulnerability")

    def test_sparse_sensor_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest, observations = sensor_fixture(
                root, "2025-04-01T05:00:00+00:00", minimum_stations=2)
            imported = root / "imported"
            import_sensor_observations(manifest, observations, imported)
            status = sensor_status(imported, SOURCE_MANIFEST,
                                   reference_time=datetime(2025, 4, 1, 6, tzinfo=timezone.utc))
            self.assertEqual(status["status"], "sparse")

    def test_stale_sensor_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest, observations = sensor_fixture(root, "2025-04-01T05:00:00Z")
            imported = root / "imported"; import_sensor_observations(manifest, observations, imported)
            status = sensor_status(imported, SOURCE_MANIFEST,
                                   reference_time=datetime(2025, 4, 3, 6, tzinfo=timezone.utc))
            self.assertEqual(status["status"], "stale")

    def test_temporally_mismatched_sensor_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest, observations = sensor_fixture(root, "2024-04-01T05:00:00Z")
            imported = root / "imported"; import_sensor_observations(manifest, observations, imported)
            status = sensor_status(imported, SOURCE_MANIFEST,
                                   reference_time=datetime(2024, 4, 1, 6, tzinfo=timezone.utc))
            self.assertEqual(status["status"], "temporally_mismatched")

    def test_nearby_context_reports_distance_and_time_without_lst_confidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest, observations = sensor_fixture(root, "2025-04-01T05:00:00Z")
            imported = root / "imported"; import_sensor_observations(manifest, observations, imported)
            result = nearby_sensor_context(
                imported, 18.52, 73.85, datetime(2025, 4, 1, 5, 10, tzinfo=timezone.utc))
            self.assertEqual(result["status"], "matched")
            self.assertAlmostEqual(result["nearest"]["distance_m"], 0)
            self.assertIn("not_calibrated_for_lst", result["confidence"])


if __name__ == "__main__":
    unittest.main()
