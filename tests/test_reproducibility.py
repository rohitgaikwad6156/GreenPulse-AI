"""Reproducibility tests use temporary files and isolated Git repositories only."""

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import reproducibility as repro


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class GitStateTests(unittest.TestCase):
    def test_commit_dirty_content_change_and_ignored_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _git(root, "init")
            _write(root / ".gitignore", b"models/\n")
            tracked = _write(root / "code.py", b"ORIGINAL\n")
            _git(root, "add", ".gitignore", "code.py")
            _git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                 "commit", "-m", "initial")
            clean = repro.get_git_state(root)
            self.assertRegex(clean["commit"], r"^[0-9a-f]{40}$")
            self.assertFalse(clean["dirty"])
            _write(root / "models" / "ignored.joblib", b"ARTIFICIAL")
            self.assertEqual(clean, repro.get_git_state(root))

            tracked.write_bytes(b"FIRST CHANGE\n")
            dirty = repro.get_git_state(root)
            self.assertTrue(dirty["dirty"])
            self.assertEqual(dirty["commit"], clean["commit"])
            repro.assert_git_unchanged(dirty, repro.get_git_state(root))
            tracked.write_bytes(b"SECOND CHANGE\n")
            with self.assertRaisesRegex(ValueError, "working-tree content changed"):
                repro.assert_git_unchanged(dirty, repro.get_git_state(root))

            tracked.write_bytes(b"ORIGINAL\n")
            _git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                 "commit", "--allow-empty", "-m", "next")
            with self.assertRaisesRegex(ValueError, "commit changed"):
                repro.assert_git_unchanged(clean, repro.get_git_state(root))

    def test_untracked_content_change_is_detected_without_exposing_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _git(root, "init")
            _write(root / "tracked.txt", b"ARTIFICIAL")
            _git(root, "add", "tracked.txt")
            _git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                 "commit", "-m", "initial")
            secret_name = root / "private-note.txt"
            _write(secret_name, b"FIRST")
            first = repro.get_git_state(root)
            self.assertTrue(first["dirty"])
            self.assertNotIn("private-note", json.dumps(first))
            _write(secret_name, b"SECOND")
            with self.assertRaisesRegex(ValueError, "working-tree content changed"):
                repro.assert_git_unchanged(first, repro.get_git_state(root))

    def test_unavailable_and_malformed_sha_and_read_only_git_commands(self):
        with patch.object(repro, "_git", return_value=None):
            unavailable = repro.get_git_state(Path("fixture"))
        self.assertEqual(unavailable["state"], "unavailable")
        self.assertIsNone(unavailable["commit"])
        repro.assert_git_unchanged(unavailable, unavailable)
        with self.assertRaisesRegex(ValueError, "availability changed"):
            repro.assert_git_unchanged(unavailable, {"state": "available"})
        with patch.object(repro, "_git", return_value=b"main\n"):
            with self.assertRaisesRegex(ValueError, "malformed commit SHA"):
                repro.get_git_state(Path("fixture"))
        commands = []

        def fake_git(_root, *args):
            commands.append(args[0])
            if args[0] == "rev-parse" and args[1] == "--show-toplevel":
                return str(Path("fixture").resolve()).encode() + b"\n"
            return {"rev-parse": b"a" * 40 + b"\n", "diff": b"",
                    "ls-files": b""}[args[0]]

        with patch.object(repro, "_git", side_effect=fake_git):
            self.assertFalse(repro.get_git_state(Path("fixture"))["dirty"])
        self.assertEqual(commands, ["rev-parse", "rev-parse", "diff", "ls-files"])


class SnapshotTests(unittest.TestCase):
    def test_file_hashes_and_actual_requirement_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _write(root / "backend/requirements.txt", b"numpy==1.2.3\n")
            _write(root / "backend/requirements-data.txt", b"-r requirements.txt\npyarrow==1.2.3\n")
            _write(root / "backend/requirements-ml.txt", b"-r requirements-data.txt\n")
            _write(root / "backend/requirements-xgboost.txt", b"-r requirements-ml.txt\nxgboost==1.2.3\n")
            lock = _write(root / "frontend/package-lock.json", b"{\"lockfileVersion\":3}\n")
            dependencies = repro.collect_dependency_files(root)
            self.assertEqual(len(dependencies["python_requirement_files"]), 4)
            self.assertEqual(dependencies["frontend_package_lock"]["sha256"],
                             "sha256:" + hashlib.sha256(lock.read_bytes()).hexdigest())
            self.assertEqual(repro.hash_file(lock), dependencies["frontend_package_lock"]["sha256"])
            with self.assertRaisesRegex(ValueError, "missing"):
                repro.hash_file(root / "missing")

    def test_snapshot_includes_finalized_artifact_hashes_and_portable_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stage = root / "data/interim/stage"
            _write(root / "backend/requirements.txt", b"numpy==1.2.3\n")
            _write(root / "backend/requirements-data.txt", b"-r requirements.txt\n")
            _write(root / "backend/requirements-ml.txt", b"-r requirements-data.txt\n")
            _write(root / "backend/requirements-xgboost.txt", b"-r requirements-ml.txt\n")
            _write(root / "frontend/package-lock.json", b"ARTIFICIAL LOCK")
            manifest = _write(root / "data/source_manifest.json", b"{\"sources\":[]}")
            paths = {
                "ml_grid": "data/processed/greenpulse_ml_grid.parquet",
                "grid_metadata": "data/processed/metadata.json",
                "spatial_cv_blocks": "data/processed/spatial_cv_blocks.parquet",
                "spatial_cv_metadata": "data/processed/spatial_cv_metadata.json",
                "baseline_metrics": "models/baseline_metrics.json",
                "model": "models/xgboost_lst.joblib",
            }
            for key, relative in paths.items():
                _write(stage / relative, f"ARTIFICIAL {key}".encode())
            runtime = {"python_version": "3.14.test", "python_implementation": "CPython",
                       "node_version": None, "node_status": "not_available",
                       "platform": {"system": "Test", "release": "Test", "machine": "Test"},
                       "scientific_packages": {package: "fixture" for package in repro.SCIENTIFIC_PACKAGES}}
            git = {"commit": "a" * 40, "dirty": True, "state": "available",
                   "status_summary": "tracked changes and/or untracked files",
                   "working_tree_fingerprint": "b" * 64}
            sources = {"landsat_lst_scenes": {"dataset_identifier": "TEST PRODUCT",
                        "checksum": "sha256:" + "c" * 64, "verification_status": "verified"}}
            report = {"dataset_version": repro.hash_file(stage / paths["ml_grid"]),
                      "model_artifact_sha256": repro.hash_file(stage / paths["model"]),
                      "training_date_utc": "2025-01-01T00:00:00+00:00", "reproducibility_seed": 42,
                      "git_commit": git["commit"], "git_dirty": git["dirty"]}
            pipeline = repro.build_pipeline_record(root, manifest, 2025, 8, 2)
            snapshot = repro.build_reproducibility_snapshot(
                root, stage, manifest, git, pipeline, sources, set(sources), paths, report,
                runtime=runtime)
            self.assertEqual(snapshot["schema_version"], "1.0")
            self.assertEqual(snapshot["git"]["commit"], "a" * 40)
            self.assertEqual(snapshot["reproducibility_status"], "working_tree_modified")
            self.assertEqual(snapshot["pipeline"]["resolved_parameters"]["trials"], 8)
            self.assertEqual(snapshot["sources"]["model_sources"][0]["checksum"], sources["landsat_lst_scenes"]["checksum"])
            self.assertEqual(snapshot["artifacts"]["ml_grid"]["sha256"], report["dataset_version"])
            self.assertEqual(snapshot["artifacts"]["model"]["sha256"], report["model_artifact_sha256"])
            self.assertNotIn(str(root), json.dumps(snapshot))
            self.assertFalse((root / "models/reproducibility_snapshot.json").exists())
            snapshot["artifacts"]["model"]["path"] = "C:/private/model.joblib"
            with self.assertRaisesRegex(ValueError, "portable model checksum"):
                repro.validate_reproducibility_snapshot(snapshot)
            report["model_artifact_sha256"] = "sha256:" + "d" * 64
            with self.assertRaisesRegex(ValueError, "Model checksum differs"):
                repro.build_reproducibility_snapshot(
                    root, stage, manifest, git, pipeline, sources, set(sources), paths, report,
                    runtime=runtime)

    def test_node_absence_is_optional_and_unavailable_git_is_explicit(self):
        with patch.object(repro.shutil, "which", return_value=None), patch.object(
                repro.importlib.metadata, "version", return_value="fixture"):
            runtime = repro.collect_runtime_versions()
        self.assertIsNone(runtime["node_version"])
        self.assertEqual(runtime["node_status"], "not_available")
        self.assertEqual(runtime["scientific_packages"]["numpy"], "fixture")

    def test_credential_like_source_identifier_is_not_serialized(self):
        sources = {"fixture": {"dataset_identifier": "https://example.test/data?token=PRIVATE",
                               "checksum": "sha256:" + "a" * 64,
                               "verification_status": "verified"}}
        record = repro.source_records(sources, {"fixture"})["model_sources"][0]
        self.assertIsNone(record["dataset_identifier"])
        self.assertEqual(record["checksum"], sources["fixture"]["checksum"])
        sources["ward_boundaries"] = {"dataset_identifier": "OFFICIAL-WARD-FIXTURE",
                                      "checksum": "sha256:" + "b" * 64,
                                      "verification_status": "verified"}
        result = repro.source_records(sources, {"fixture"})
        self.assertEqual([item["source_id"] for item in result["model_sources"]], ["fixture"])
        self.assertEqual(result["reporting_dependency"]["role"], "reporting_dependency")


if __name__ == "__main__":
    unittest.main()
