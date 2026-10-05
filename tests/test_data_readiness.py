import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend.app.data_intake.readiness import readiness, CATALOG
from backend.app.main import app
from backend.app.api import services


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
    write(tmp_path, 'data/provenance/landsat_extreme_audit_2025.json', dict(scenes_expected=9, scenes_passed=9, scenes_failed=0, overall_status='PASS'))
    write(tmp_path, 'data/provenance/sentinel_quality_audit_2025.json', dict(expected_product_count=6, safe_directories_found=0, minimum_required_files_expected=30, required_file_slots_found=0, products_passed=0, products_failed=6, overall_status='FAIL'))
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
