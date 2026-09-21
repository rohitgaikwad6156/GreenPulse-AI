"""Tests for the executable source contract; all local data are TEST FIXTURES."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backend.app.data_intake.manifest import (
    ALL_SOURCE_IDS,
    REQUIRED_SOURCE_IDS,
    validate_manifest,
)


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _source(content: bytes, **updates):
    source = {
        "id": "artificial_test_source",
        "scope": "required_mvp",
        "source_organization": "ARTIFICIAL TEST FIXTURE organization",
        "product": "ARTIFICIAL TEST FIXTURE product",
        "dataset_identifier": "TEST-ONLY-ID",
        "license": "TEST-ONLY license statement",
        "access_date": "2025-05-31",
        "scene_date_range": {"start": "2025-03-01", "end": "2025-05-31"},
        "season_group": "peak_summer",
        "geographic_coverage": "ARTIFICIAL TEST FIXTURE extent",
        "crs": "EPSG:4326",
        "resolution": {"value": 1, "unit": "point"},
        "checksum": _sha256(content),
        "local_path": "fixture.csv",
        "verification_status": "verified",
        "data_classification": "real",
        "format": "tabular",
    }
    source.update(updates)
    return source


class DataManifestTests(unittest.TestCase):
    def _write(self, root: Path, document) -> Path:
        path = root / "manifest.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_complete_manifest_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = b"ARTIFICIAL TEST FIXTURE\n"
            (root / "fixture.csv").write_bytes(content)
            manifest = self._write(root, {"manifest_version": "1.0", "sources": [_source(content)]})
            report = validate_manifest(manifest, root, enforce_inventory=False)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(report.verified_sources, ["artificial_test_source"])

    def test_incomplete_manifest_reports_actionable_file_and_status_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _source(b"missing", verification_status="pending")
            manifest = self._write(root, {"manifest_version": "1.0", "sources": [source]})
            report = validate_manifest(manifest, root, enforce_inventory=False)
            joined = "\n".join(report.errors)
            self.assertIn("missing tabular at fixture.csv", joined)
            self.assertIn("required MVP source must be verified", joined)

    def test_malformed_manifest_is_rejected_precisely(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            manifest.write_text('{"manifest_version": "1.0", "sources": [', encoding="utf-8")
            report = validate_manifest(manifest, root, enforce_inventory=False)
            self.assertFalse(report.ok)
            self.assertIn("cannot parse JSON", report.errors[0])

    def test_synthetic_manifest_requires_explicit_test_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = b"EXPLICITLY LABELLED ARTIFICIAL TEST FIXTURE\n"
            (root / "fixture.csv").write_bytes(content)
            source = _source(content, data_classification="synthetic_test_fixture")
            manifest = self._write(root, {"manifest_version": "1.0", "sources": [source]})
            rejected = validate_manifest(manifest, root, enforce_inventory=False)
            accepted = validate_manifest(manifest, root, allow_synthetic=True, enforce_inventory=False)
            self.assertIn("synthetic data is forbidden", "\n".join(rejected.errors))
            self.assertTrue(accepted.ok, accepted.errors)

    def test_repository_inventory_has_every_authoritative_source_and_scope(self):
        root = Path(__file__).resolve().parents[1]
        document = json.loads((root / "data" / "source_manifest.json").read_text(encoding="utf-8"))
        by_id = {source["id"]: source for source in document["sources"]}
        self.assertEqual(set(by_id), ALL_SOURCE_IDS)
        self.assertTrue(all(by_id[source_id]["scope"] == "required_mvp" for source_id in REQUIRED_SOURCE_IDS))
        report = validate_manifest(root / "data" / "source_manifest.json", root)
        self.assertFalse(report.ok)  # Some required authority/credential-gated inputs remain absent.
        errors = "\n".join(report.errors)
        self.assertIn("ward_boundaries.local_path", errors)
        self.assertIn("periurban_lst_reference.companion_files[0].local_path", errors)


if __name__ == "__main__":
    unittest.main()
