"""Provenance-aware validation tests use explicitly synthetic fixtures only."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api import services
from backend.app.main import app
from backend.app.validation.workflow import (
    ValidationEvidenceError, analyze_validation_dataset,
    approve_calibration_report, import_validation_dataset, list_imported_datasets,
)


PERIODS = [
    {"period_id": "PRE-1", "phase": "pre", "acquisition_date": "2023-03-15",
     "scene_id": "SYNTHETIC-SCENE-PRE-1", "season": "March-May",
     "scene_checksum_sha256": "b" * 64,
     "overpass_time_local": "10:30", "qa_criteria": "SYNTHETIC QA VALID"},
    {"period_id": "PRE-2", "phase": "pre", "acquisition_date": "2024-03-16",
     "scene_id": "SYNTHETIC-SCENE-PRE-2", "season": "March-May",
     "scene_checksum_sha256": "c" * 64,
     "overpass_time_local": "10:32", "qa_criteria": "SYNTHETIC QA VALID"},
    {"period_id": "POST-1", "phase": "post", "acquisition_date": "2025-03-17",
     "scene_id": "SYNTHETIC-SCENE-POST-1", "season": "March-May",
     "scene_checksum_sha256": "d" * 64,
     "overpass_time_local": "10:31", "qa_criteria": "SYNTHETIC QA VALID"},
]


def fixture(root: Path, *, contaminated: bool = False, failed_trends: bool = False,
            duplicate: bool = False, incomplete: bool = False) -> tuple[Path, Path, Path]:
    grid_rows = [("T1", 0, 0), ("T2", 0, 100),
                 ("C1", 50 if contaminated else 1000, 0),
                 ("C2", 60 if contaminated else 1000, 100)]
    grid = root / "grid.csv"
    with grid.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["grid_id", "x", "y"]); writer.writerows(grid_rows)
    values = {
        "T1": [35, 35 if failed_trends else 34, 30],
        "T2": [36, 36 if failed_trends else 35, 31],
        "C1": [34, 33, 31], "C2": [35, 34, 32],
    }
    rows = []
    positions = {item[0]: item[1:] for item in grid_rows}
    for grid_id, sequence in values.items():
        for period, lst in zip(PERIODS, sequence):
            rows.append({"grid_id": grid_id, "group": "treated" if grid_id.startswith("T") else "control",
                         "period_id": period["period_id"], "lst_c": lst,
                         "x": positions[grid_id][0], "y": positions[grid_id][1],
                         "qa_valid": "true", "ndvi": ""})
    if incomplete:
        rows = [row for row in rows if not (row["grid_id"] == "C2" and row["period_id"] == "PRE-2")]
    if duplicate:
        rows.append(dict(rows[0]))
    observations = root / "observations.csv"
    with observations.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    manifest = {
        "schema_version": "1.0", "dataset_id": "SYNTHETIC_VALIDATION",
        "dataset_version": "synthetic-v1", "evidence_label": "SYNTHETIC TEST FIXTURE",
        "location_id": "SYNTHETIC-AREA", "intervention_id": "SYNTHETIC-TREES",
        "target": "lst_c", "crs": "EPSG:32643", "season": "March-May",
        "season_start_mm_dd": "03-01", "season_end_mm_dd": "05-31",
        "qa_policy": "SYNTHETIC TEST QA; all fixture rows marked valid",
        "observations_sha256": hashlib.sha256(observations.read_bytes()).hexdigest(),
        "source": {"organization": "Synthetic test suite", "product": "Synthetic LST fixture",
                   "url_or_identifier": "test://synthetic-validation", "license": "TEST ONLY",
                   "access_date": "2026-09-21"},
        "periods": PERIODS, "overpass_tolerance_minutes": 5,
        "control_selection": {"method": "SYNTHETIC distance match",
                              "eligibility_rule": "SYNTHETIC untreated controls"},
        "spillover_distance_m": 200, "spatial_autocorrelation_distance_m": 150,
        "parallel_trends_max_abs_slope_difference_c_per_period": 0.2,
        "predictions": [{"grid_id": "T1", "predicted_delta_lst_c": -1.5},
                        {"grid_id": "T2", "predicted_delta_lst_c": -1.5}],
        "prediction_model": {"dataset_version": "SYNTHETIC-MODEL-V1",
                             "model_checksum_sha256": "a" * 64},
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, observations, grid


class ValidationWorkflowTests(unittest.TestCase):
    def test_synthetic_fixture_import_analysis_and_residuals(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest, observations, grid = fixture(root)
            imported = import_validation_dataset(
                manifest, observations, grid, root / "imported", allow_synthetic=True)
            self.assertEqual(imported, import_validation_dataset(
                manifest, observations, grid, root / "imported", allow_synthetic=True))
            report_path = root / "report.json"
            report = analyze_validation_dataset(imported, output_path=report_path)
            self.assertEqual(report["validation_status"], "BLOCKED")
            self.assertTrue(report["parallel_trends"]["passed"])
            self.assertTrue(report["control_diagnostics"]["passed"])
            self.assertEqual(report["sample_size"]["pre_periods"], 2)
            self.assertEqual(report["performance"]["count"], 2)
            self.assertEqual(report["calibration_proposal"], None)
            self.assertTrue(report_path.is_file())
            self.assertEqual(list_imported_datasets(root / "imported")["total"], 0)
            with self.assertRaisesRegex(ValidationEvidenceError, "review-ready"):
                approve_calibration_report(report_path, root / "approval.json",
                                           approver="Synthetic tester", decision="approve",
                                           rationale="Synthetic test only")

    def test_mismatched_season_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest, observations, grid = fixture(root)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["periods"][1]["season"] = "June-August"
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValidationEvidenceError, "season does not match"):
                import_validation_dataset(manifest, observations, grid, root / "imported", allow_synthetic=True)

    def test_incomplete_pairs_and_duplicate_cells_are_rejected(self):
        for option, message in (("incomplete", "missing periods"), ("duplicate", "Duplicate cell-period")):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                manifest, observations, grid = fixture(root, **{option: True})
                with self.assertRaisesRegex(ValidationEvidenceError, message):
                    import_validation_dataset(manifest, observations, grid, root / "imported", allow_synthetic=True)

    def test_failed_parallel_trends_blocks_calibration(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest, observations, grid = fixture(root, failed_trends=True)
            imported = import_validation_dataset(manifest, observations, grid, root / "imported", allow_synthetic=True)
            report = analyze_validation_dataset(imported)
            self.assertFalse(report["parallel_trends"]["passed"])
            self.assertEqual(report["validation_status"], "BLOCKED")
            self.assertIsNone(report["calibration_proposal"])

    def test_controls_inside_spillover_distance_are_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest, observations, grid = fixture(root, contaminated=True)
            imported = import_validation_dataset(manifest, observations, grid, root / "imported", allow_synthetic=True)
            report = analyze_validation_dataset(imported)
            self.assertFalse(report["control_diagnostics"]["passed"])
            self.assertEqual(len(report["control_diagnostics"]["contaminated_controls"]), 2)
            self.assertEqual(report["validation_status"], "BLOCKED")

    def test_api_returns_versioned_blocked_report_for_synthetic_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest, observations, grid = fixture(root)
            imports = root / "imported"; reports = root / "reports"
            import_validation_dataset(manifest, observations, grid, imports, allow_synthetic=True)
            with patch.object(services, "VALIDATION_IMPORTS", imports), patch.object(services, "VALIDATION_REPORTS", reports):
                with TestClient(app) as client:
                    response = client.post("/api/validation/analyze/SYNTHETIC_VALIDATION")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["validation_status"], "BLOCKED")
            self.assertTrue((reports / "SYNTHETIC_VALIDATION.json").is_file())


if __name__ == "__main__":
    unittest.main()
