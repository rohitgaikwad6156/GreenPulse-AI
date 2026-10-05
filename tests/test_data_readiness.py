import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api import services
from backend.app.api.readiness_status import artifact_statuses, readiness_status
from backend.app.data_intake.readiness import CATALOG, readiness
from backend.app.main import app


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def evidence(tmp_path):
    sources = []
    for key in CATALOG:
        verified = key in {'landsat_lst_scenes', 'esa_worldcover', 'osm_roads', 'worldpop'}
        sources.append(dict(id=key, verification_status='verified' if verified else 'pending', data_classification='real', checksum='sha256:' + 'a'*64, local_path=f'data/raw/{key}.bin'))
        if verified:
            path = tmp_path / f'data/raw/{key}.bin'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic presence fixture')
    write(tmp_path, 'data/source_manifest.json', {'sources': sources})
    write(tmp_path, 'data/provenance/landsat_quality_audit_2025.json', {'summary': dict(scenes_expected=9, scenes_found=9, required_files_expected=36, required_files_found=36, scenes_passed=9, scenes_failed=0, overall_status='PASS')})
    write(tmp_path, 'data/provenance/landsat_processing_audit_2025.json', dict(expected_scene_count=9, scenes_processed=9, scenes_passed=9, scenes_failed=0, overall_status='PASS'))
    write(tmp_path, 'data/provenance/landsat_extreme_audit_2025.json', dict(scenes_expected=9, scenes_passed=9, scenes_failed=0, overall_status='PASS', scenes=synthetic_extremes()))
    write(tmp_path, 'data/provenance/sentinel_quality_audit_2025.json', dict(expected_product_count=6, safe_directories_found=0, minimum_required_files_expected=30, required_file_slots_found=0, products_passed=0, products_failed=6, overall_status='FAIL', intake_state='PENDING'))
    write(tmp_path, 'data/provenance/acquisition_pcmc_boundary.json', {'source_organization': 'Synthetic authority', 'file': {'path': 'data/outline.geojson', 'checksum': 'sha256:'+'b'*64}})
    (tmp_path / 'data/outline.geojson').write_text('synthetic fixture')
    return tmp_path


def test_current_evidence(evidence):
    result = readiness(evidence)
    rows = {r['id']: r for r in result['sources']}
    assert rows['landsat_lst_scenes']['status'] == 'verified'
    assert rows['landsat_lst_scenes']['audits'][0]['details'] == ['9/9 selected scenes', '36/36 required files']
    assert rows['sentinel2_l2a_scenes']['status'] == 'pending'
    assert rows['pcmc_outline']['status'] == 'staged'
    assert rows['pmc_outline']['status'] == 'pending'
    assert result['required_sources_ready'] == 3
    assert {b['id'] for b in result['first_heat_map_blockers']} == {'sentinel2_l2a_scenes', 'municipal_boundary'}
    assert str(evidence) not in json.dumps(result)


def test_wards_do_not_block(evidence):
    manifest = json.loads((evidence / 'data/source_manifest.json').read_text())
    for source in manifest['sources']:
        if source['id'] in {'sentinel2_l2a_scenes', 'municipal_boundary'}:
            source['verification_status'] = 'verified'
            (evidence / source['local_path']).write_bytes(b'synthetic')
    write(evidence, 'data/source_manifest.json', manifest)
    write(evidence, 'data/provenance/sentinel_quality_audit_2025.json', dict(expected_product_count=6, safe_directories_found=6, minimum_required_files_expected=30, required_file_slots_found=30, products_passed=6, products_failed=0, overall_status='PASS'))
    assert readiness(evidence)['first_heat_map_ready']


@pytest.mark.parametrize('value', [None, [], {'summary': 'broken'}, {'summary': {'overall_status': []}}])
def test_missing_or_malformed_audit_fails_closed(evidence, value):
    path = evidence / 'data/provenance/landsat_quality_audit_2025.json'
    if value is None:
        path.unlink()
    else:
        path.write_text(json.dumps(value))
    result = readiness(evidence)
    row = next(r for r in result['sources'] if r['id'] == 'landsat_lst_scenes')
    assert row['manifest_status'] == 'verified'  # preserves recorded truth
    assert row['audits'][0]['status'] == 'unavailable'
    assert row['blocked_reason']
    assert result['required_sources_ready'] == 2


def test_malformed_manifest_does_not_verify(evidence):
    write(evidence, 'data/source_manifest.json', {'sources': [{'id': 'landsat_lst_scenes', 'verification_status': []}]})
    assert not any(s['status'] == 'verified' for s in readiness(evidence)['sources'])


def test_lfs_pointer_is_not_available(evidence):
    (evidence / 'data/raw/landsat_lst_scenes.bin').write_text('version https://git-lfs.github.com/spec/v1\noid sha256:abc')
    assert readiness(evidence)['required_sources_ready'] == 2


def test_read_only_endpoint_and_missing_repository(evidence, tmp_path, monkeypatch):
    before = {p: p.read_bytes() for p in evidence.rglob('*') if p.is_file()}
    monkeypatch.setattr(services, 'ROOT', evidence)
    with TestClient(app) as client:
        response = client.get('/api/data-readiness')
        assert response.status_code == 200
        assert response.json()['required_sources_ready'] == 3
        monkeypatch.setattr(services, 'ROOT', tmp_path / 'absent')
        missing = client.get('/api/data-readiness')
        assert missing.status_code == 200
        assert missing.json()['overall_status'] == 'blocked'
    assert before == {p: p.read_bytes() for p in evidence.rglob('*') if p.is_file()}


def test_canonical_endpoint_and_compatibility_share_evidence(evidence, monkeypatch):
    monkeypatch.setattr(services, 'ROOT', evidence)
    with TestClient(app) as client:
        canonical = client.get('/api/readiness')
        legacy = client.get('/api/data-readiness')
        assert canonical.status_code == legacy.status_code == 200
        assert canonical.json() == legacy.json() or (
            canonical.json()['checked_at'] != legacy.json()['checked_at']
            and {k: v for k, v in canonical.json().items() if k != 'checked_at'} ==
                {k: v for k, v in legacy.json().items() if k != 'checked_at'})
        data = canonical.json()
        assert data['software']['basis'] == 'backend_runtime'
        assert data['production_data'] == 'blocked'
        assert data['first_heat_map'] == {
            'ready': False, 'required_sources_ready': 3, 'required_sources_total': 5,
            'blocker_count': 2}
        assert {item['id'] for item in data['blockers']} == {
            'municipal_boundary', 'sentinel2_l2a_scenes'}
        assert data['source_status']['pmc_outline'] == 'pending'
        assert data['source_status']['pcmc_outline'] == 'staged'
        assert data['source_status']['ward_boundaries'] == 'pending'
        assert data['artifacts']['real_ml_grid'] == 'blocked'
        assert data['artifacts']['trained_xgboost_model'] == 'blocked'
        assert str(evidence) not in json.dumps(data)
        assert '/api/readiness' in client.get('/openapi.json').json()['paths']
        assert client.get('/openapi.json').json()['paths']['/api/data-readiness']['get']['deprecated']
        method = client.get('/api/methodology').json()['data_status']
        assert method['real_ml_grid_available'] == (data['artifacts']['real_ml_grid'] == 'ready')
        assert method['trained_model_available'] == (data['artifacts']['trained_xgboost_model'] == 'ready')


def test_dynamic_gate_and_fail_closed(evidence):
    result = readiness_status(evidence)
    assert result['software']['status'] == 'ready'  # Sentinel absence is a data blocker.
    assert result['first_heat_map']['blocker_count'] == 2
    manifest = json.loads((evidence / 'data/source_manifest.json').read_text())
    for source in manifest['sources']:
        if source['id'] == 'sentinel2_l2a_scenes':
            source['verification_status'] = 'verified'
            (evidence / source['local_path']).write_bytes(b'synthetic source')
    write(evidence, 'data/source_manifest.json', manifest)
    write(evidence, 'data/provenance/sentinel_quality_audit_2025.json', dict(
        expected_product_count=6, safe_directories_found=6,
        minimum_required_files_expected=30, required_file_slots_found=30,
        products_passed=6, products_failed=0, overall_status='PASS'))
    assert readiness_status(evidence)['first_heat_map']['blocker_count'] == 1
    for source in manifest['sources']:
        if source['id'] == 'municipal_boundary':
            source['verification_status'] = 'verified'
            (evidence / source['local_path']).write_bytes(b'synthetic combined boundary')
    write(evidence, 'data/source_manifest.json', manifest)
    ready = readiness_status(evidence)
    assert ready['production_data'] == 'source_ready'
    assert ready['first_heat_map']['blocker_count'] == 0
    assert ready['source_status']['ward_boundaries'] == 'pending'
    write(evidence, 'data/source_manifest.json', {'sources': []})
    unknown = readiness_status(evidence)
    assert unknown['production_data'] == 'unknown'
    assert unknown['first_heat_map']['ready'] is None
    assert unknown['source_status']['landsat_lst_scenes'] != 'verified'


def test_artifacts_require_accepted_grid_and_model_metadata(tmp_path, monkeypatch):
    class Reader:
        def close(self): pass
    grid_meta = {'features': ['ndvi'], 'row_count': 4, 'crs': 'EPSG:32643'}
    monkeypatch.setattr(services, '_real_grid', lambda: (Reader(), grid_meta))
    monkeypatch.setattr(services, 'model_metrics', lambda: {'target': 'lst_c'})
    metadata = tmp_path / 'model.json'
    monkeypatch.setattr(services, 'MODEL_METADATA', metadata)
    metadata.write_text(json.dumps({'target': 'lst_c'}))
    assert artifact_statuses(tmp_path)['trained_xgboost_model'] == 'blocked'
    metadata.write_text(json.dumps(dict(model_artifact_sha256='sha256:' + 'a'*64,
                                        dataset_version='sha256:' + 'b'*64,
                                        feature_list=['ndvi'], dataset_rows=4,
                                        crs='EPSG:32643', resolution_m=30)))
    assert artifact_statuses(tmp_path)['trained_xgboost_model'] == 'ready'
    monkeypatch.setattr(services, '_real_grid', lambda: (_ for _ in ()).throw(
        services.DataUnavailableError('legacy grid rejected')))
    assert artifact_statuses(tmp_path)['real_ml_grid'] == 'blocked'
    assert artifact_statuses(tmp_path)['trained_xgboost_model'] == 'blocked'

@pytest.mark.parametrize('content', ['{broken', 'null'])
def test_invalid_json_is_unavailable(evidence, content):
    (evidence / 'data/provenance/landsat_quality_audit_2025.json').write_text(content)
    assert readiness(evidence)['required_sources_ready'] == 2


def test_audit_cannot_promote_pending_manifest(evidence):
    manifest = json.loads((evidence / 'data/source_manifest.json').read_text())
    manifest['sources'][0]['verification_status'] = 'pending'
    write(evidence, 'data/source_manifest.json', manifest)
    row = readiness(evidence)['sources'][0]
    assert row['status'] == 'pending'
    assert row['audits'][0]['status'] == 'pass'


def synthetic_extremes():
    """Invented scalar fixtures, not production temperatures or coordinates."""
    rows = []
    for date, extreme in [('2025-03-10', 'maximum'), ('2025-04-03', 'minimum')]:
        stats = dict(minimum=-5., maximum=95., p01=20., p99=50.)
        pixel = dict(st_dn=65535 if extreme == 'maximum' else 32000, celsius=stats[extreme], same_dn_qa_valid_pixel_count=2, invalid_qa_neighbor_count=12)
        rows.append(dict(product_id=f"LC09_L2SP_147047_{date.replace('-', '')}_20250411_02_T1", acquisition_date=date, status='PASS', qa_valid_pixel_count=1000,
                         statistics_celsius=stats, **{extreme+'_pixel': pixel}, threshold_counts=dict(above_80=4, above_90=2, below_0=2, from_0_to_10=4),
                         clusters={k: dict(pixel_count=n, cluster_count=1, largest_cluster_size=n) for k,n in [('above_80',4),('above_90',2),('below_10',6),('below_0',2)]}))
    return rows + [{'status': 'PASS'} for _ in range(7)]


def test_audit_trail_summaries(evidence):
    trail = {a['id']: a for a in readiness(evidence)['audit_trail']}
    assert trail['landsat_source']['status'] == 'pass'
    assert '9/9 scenes passed' in trail['landsat_source']['summary']
    assert '36/36 required files' in trail['landsat_source']['summary']
    assert 'QA masking and Celsius conversion completed.' in trail['landsat_processing']['summary']
    assert trail['landsat_extremes']['status'] == 'review'
    assert trail['landsat_extremes']['audit_result'] == 'PASS'
    assert trail['sentinel_intake']['status'] == 'pending'
    assert trail['sentinel_intake']['audit_result'] == 'FAIL'
    assert 'source files are missing' in trail['sentinel_intake']['interpretation']


def test_extreme_allowlist_and_disclaimers(evidence):
    path = evidence / 'data/provenance/landsat_extreme_audit_2025.json'
    raw = json.loads(path.read_text())
    raw['source_directory'] = r'C:\private\secret'
    raw['scenes'][0]['maximum_pixel']['neighborhood_5x5'] = [[{'secret': 'raw QA'}]]
    raw['scenes'][0]['injected'] = r'D:\secrets'
    write(evidence, 'data/provenance/landsat_extreme_audit_2025.json', raw)
    result = readiness(evidence)
    text = json.dumps(result)
    assert 'neighborhood_5x5' not in text and 'secret' not in text and 'raw QA' not in text
    audit = next(a for a in result['audit_trail'] if a['id'] == 'landsat_extremes')
    assert set(audit['diagnostics'][0]) == {'date','product_id','extreme_label','extreme_celsius','percentile_label','percentile_celsius','thresholds','finding'}
    assert audit['diagnostics'][0]['extreme_celsius'] == 95
    assert audit['diagnostics'][0]['percentile_celsius'] == 50
    assert audit['diagnostics'][1]['thresholds'][0]['pixel_count'] == 6
    assert 'not Pune/PMC/PCMC' in result['audit_disclaimer']
    assert 'did not change production QA' in result['audit_preservation_note']


@pytest.mark.parametrize('patch', [
    {'scenes_found': 10}, {'scenes_passed': -1}, {'scenes_passed': True},
    {'required_files_expected': 0}, {'required_files_found': 35},
    {'overall_status': 'APPROVED'}, {'overall_status': 'FAIL'}, {'overall_status': []},
])
def test_impossible_audit_counts_unavailable(evidence, patch):
    path = evidence / 'data/provenance/landsat_quality_audit_2025.json'
    raw = json.loads(path.read_text())
    raw['summary'].update(patch)
    write(evidence, 'data/provenance/landsat_quality_audit_2025.json', raw)
    assert readiness(evidence)['audit_trail'][0]['status'] == 'unavailable'


@pytest.mark.parametrize('fault', ['missing', 'nan', 'clusters', 'wrong_product'])
def test_malformed_extremes_unavailable(evidence, fault):
    path = evidence / 'data/provenance/landsat_extreme_audit_2025.json'
    raw = json.loads(path.read_text())
    if fault == 'missing':
        raw.pop('scenes')
    elif fault == 'nan':
        raw['scenes'][0]['statistics_celsius']['maximum'] = float('nan')
    elif fault == 'clusters':
        raw['scenes'][0]['clusters']['above_80']['cluster_count'] = 20
    else:
        raw['scenes'][0]['product_id'] = r'C:\private\wrong'
    write(evidence, 'data/provenance/landsat_extreme_audit_2025.json', raw)
    audit = readiness(evidence)['audit_trail'][2]
    assert audit['status'] == 'unavailable' and audit['diagnostics'] == []


def test_sentinel_existing_but_invalid_sources_require_review(evidence):
    path = evidence / 'data/provenance/sentinel_quality_audit_2025.json'
    raw = json.loads(path.read_text())
    raw.update(safe_directories_found=6, required_file_slots_found=30)
    write(evidence, 'data/provenance/sentinel_quality_audit_2025.json', raw)
    assert readiness(evidence)['audit_trail'][3]['status'] == 'review'


def test_chain_never_infers_production_completion(evidence):
    result = readiness(evidence)
    chain = result['evidence_chains'][0]['stages']
    assert [s['status'] for s in chain] == ['COMPLETE', 'PASS', 'PASS', 'REVIEWED', 'WAITING FOR BOUNDARY', 'BLOCKED']
    (evidence / 'data/provenance/landsat_quality_audit_2025.json').unlink()
    assert readiness(evidence)['evidence_chains'][0]['stages'][1]['status'] == 'UNAVAILABLE'


def test_api_never_opens_rasters(evidence, monkeypatch):
    path = evidence / 'data/raw/scene.TIF'
    path.write_bytes(b'x' * 2048)
    manifest = json.loads((evidence / 'data/source_manifest.json').read_text())
    manifest['sources'][0]['local_path'] = 'data/raw/scene.TIF'
    write(evidence, 'data/source_manifest.json', manifest)
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert path.suffix.lower() not in {'.tif', '.tiff', '.jp2'}
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    assert readiness(evidence)['required_sources_ready'] == 3


def test_row_results_cannot_contradict_pass_summary(evidence):
    path = evidence / 'data/provenance/landsat_quality_audit_2025.json'
    raw = json.loads(path.read_text())
    raw['scenes'] = [{'status': 'FAIL'}] * 9
    write(evidence, 'data/provenance/landsat_quality_audit_2025.json', raw)
    assert readiness(evidence)['audit_trail'][0]['status'] == 'unavailable'
