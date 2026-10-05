"""Pipeline publication and provenance gates; no production climate data generated."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.api import services
from backend.app.data_intake.manifest import validate_manifest
from backend.app.data_intake.provenance import reject_demo_metadata
from scripts import build_heat_map_pipeline as pipeline


class HeatMapPipelineTests(unittest.TestCase):
    def test_ward_source_is_not_a_training_preflight_dependency(self):
        self.assertNotIn('ward_boundaries', pipeline.SOURCE_IDS)
        self.assertIn('municipal_boundary', pipeline.SOURCE_IDS)

    def test_subset_manifest_keeps_required_gates_without_unrelated_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'manifest.json'
            path.write_text(json.dumps({'manifest_version': '1.0', 'sources': [
                {'id': 'osm_roads', 'scope': 'required_mvp'},
                {'id': 'worldpop', 'scope': 'required_mvp'}]}))
            report = validate_manifest(path, root, source_ids={'osm_roads'})
            self.assertFalse(report.ok)
            self.assertTrue(any('osm_roads' in error for error in report.errors))
            self.assertFalse(any('worldpop' in error for error in report.errors))
            absent = validate_manifest(path, root, source_ids={'ward_boundaries'})
            self.assertTrue(any('entry is missing: ward_boundaries' in error for error in absent.errors))

    def test_demo_artifacts_are_rejected_before_model_load(self):
        for label in ('DEMO / SYNTHETIC DATA', 'synthetic_test_fixture'):
            with self.assertRaisesRegex(ValueError, 'Demo/synthetic'):
                reject_demo_metadata({'source': label})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            grid = root / 'grid.parquet'
            grid.write_bytes(b'not a real parquet')
            metadata = root / 'metadata.json'
            metadata.write_text(json.dumps({'source': 'DEMO / SYNTHETIC DATA'}))
            with patch.object(services, 'GRID', grid), patch.object(services, 'GRID_METADATA', metadata):
                with self.assertRaisesRegex(services.DataUnavailableError, 'Demo/synthetic'):
                    services._real_grid()
                self.assertFalse(services.methodology()['data_status']['real_ml_grid_available'])

    def test_failed_preflight_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'models/xgboost_lst.joblib'
            target.parent.mkdir()
            target.write_bytes(b'previous artifact')
            with patch.object(pipeline, 'preflight', return_value={'ok': False, 'errors': ['missing real scenes']}):
                with self.assertRaisesRegex(ValueError, 'missing real scenes'):
                    pipeline.run_pipeline(root, root / 'manifest.json', 2025)
            self.assertEqual(target.read_bytes(), b'previous artifact')
            self.assertFalse((root / 'data/processed').exists())

    def test_publish_keeps_backup_and_rolls_back_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'project'
            stage = Path(temporary) / 'stage'
            (root / 'models').mkdir(parents=True)
            (stage / 'models').mkdir(parents=True)
            (root / 'models/a').write_bytes(b'previous')
            (stage / 'models/a').write_bytes(b'new')
            (stage / 'models/b').write_bytes(b'new second')
            replace = pipeline.os.replace
            def fail_second(source, target):
                if Path(source).name == 'b':
                    raise OSError('simulated write failure')
                replace(source, target)
            with patch.object(pipeline.os, 'replace', side_effect=fail_second):
                with self.assertRaisesRegex(OSError, 'simulated write failure'):
                    pipeline._publish(stage, root)
            self.assertEqual((root / 'models/a').read_bytes(), b'previous')
            self.assertFalse((root / 'models/b').exists())
            self.assertEqual(next((root / 'data/interim/heat_map_backups').glob('*/models/a')).read_bytes(), b'previous')

    def test_successful_publication_preserves_prior_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'project'
            stage = Path(temporary) / 'stage'
            (root / 'models').mkdir(parents=True)
            (stage / 'models').mkdir(parents=True)
            (root / 'models/model_metadata.json').write_text('old metadata')
            (stage / 'models/model_metadata.json').write_text('new metadata')
            (stage / 'models/reproducibility_snapshot.json').write_text('artificial snapshot')
            backup = pipeline._publish(stage, root)
            self.assertEqual((root / 'models/model_metadata.json').read_text(), 'new metadata')
            self.assertEqual((root / 'models/reproducibility_snapshot.json').read_text(), 'artificial snapshot')
            self.assertEqual((backup / 'models/model_metadata.json').read_text(), 'old metadata')
            self.assertEqual(pipeline._rewrite_paths({'path': str(stage / 'models')}, stage, root),
                             {'path': str(root / 'models')})

    def test_requested_year_must_match_verified_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = [{'id': name, 'scene_date_range': {'start': '2025-03-01', 'end': '2025-05-31'}}
                       for name in pipeline.SOURCE_IDS]
            path = root / 'manifest.json'
            path.write_text(json.dumps({'sources': sources}))
            from backend.app.data_intake.manifest import ValidationReport
            with patch.object(pipeline, 'validate_manifest', return_value=ValidationReport()):
                self.assertFalse(pipeline.preflight(root, path, 2024)['ok'])
                self.assertTrue(pipeline.preflight(root, path, 2025)['ok'])


if __name__ == '__main__':
    unittest.main()
