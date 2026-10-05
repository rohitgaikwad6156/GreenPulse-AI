"""Small, allowlisted projections of saved audits for the readiness viewer."""
from __future__ import annotations

import math
import re

DOCS = 'https://github.com/rohitgaikwad6156/GreenPulse-AI/blob/main/docs/'
DISCLAIMER = 'These are full-scene diagnostics, not Pune/PMC/PCMC temperature results.'
UNCHANGED = 'The extreme audit did not change production QA rules or alter source pixels.'
AUDITS = {
    'quality': ('landsat_source', 'Landsat Source Audit', 'Source integrity', 'Original Landsat scene files', 'landsat_quality_audit.md'),
    'processing': ('landsat_processing', 'Landsat Processing Audit', 'Source processing', 'Original Landsat scene footprints', 'landsat_processing_audit.md'),
    'extreme': ('landsat_extremes', 'Landsat Extreme Diagnostics', 'Extreme diagnostic review', 'QA-valid full-scene pixels', 'landsat_extreme_audit.md'),
    'sentinel': ('sentinel_intake', 'Sentinel-2 Manual Intake', 'Manual source intake', 'Selected Sentinel-2 L2A SAFE products', 'sentinel_quality_audit.md'),
}


def audit_template(kind):
    id_, title, type_, scope, doc = AUDITS[kind]
    return dict(id=id_, title=title, audit_type=type_, scope=scope,
                display_status='UNAVAILABLE', audit_result=None, summary=[],
                interpretation='Evidence unavailable: saved audit is missing or inconsistent.',
                documentation_url=DOCS + doc, diagnostics=[])


def _integer(value, maximum=None):
    return type(value) is int and value >= 0 and (maximum is None or value <= maximum)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def extreme_summaries(raw):
    """Copy only selected scalars; never return arbitrary prose, paths or arrays."""
    scenes = raw.get('scenes')
    if not isinstance(scenes, list) or len(scenes) != raw['scenes_expected']:
        raise ValueError('Invalid scene list')
    if not all(isinstance(s, dict) for s in scenes):
        raise ValueError('Invalid scene record')
    output = []
    for date, extreme, percentile, ranges in [
        ('2025-03-10', 'maximum', 'p99', [('above_80', '>80 °C'), ('above_90', '>90 °C')]),
        ('2025-04-03', 'minimum', 'p01', [('below_10', '<10 °C'), ('below_0', '<0 °C')]),
    ]:
        matches = [s for s in scenes if s.get('acquisition_date') == date]
        if len(matches) != 1:
            raise ValueError('Missing or duplicate investigation')
        s = matches[0]
        product = s.get('product_id')
        if not isinstance(product, str) or not re.fullmatch(r'LC0[89]_L2SP_147047_' + date.replace('-', '') + r'_\d{8}_02_T1', product) or s.get('status') != 'PASS':
            raise ValueError('Invalid investigation identity')
        stats, pixel, clusters, counts = s.get('statistics_celsius'), s.get(extreme + '_pixel'), s.get('clusters'), s.get('threshold_counts')
        if not all(isinstance(v, dict) for v in (stats, pixel, clusters, counts)):
            raise ValueError('Missing diagnostic fields')
        values = [stats.get(k) for k in ('minimum', 'p01', 'p99', 'maximum')]
        if not all(_number(v) for v in values) or values != sorted(values):
            raise ValueError('Invalid distribution')
        total = s.get('qa_valid_pixel_count')
        if not _integer(total) or total == 0 or not _integer(pixel.get('st_dn'), 65535) or not _integer(pixel.get('same_dn_qa_valid_pixel_count'), total) or pixel['same_dn_qa_valid_pixel_count'] == 0 or not _integer(pixel.get('invalid_qa_neighbor_count'), 24):
            raise ValueError('Invalid pixel evidence')
        if not _number(pixel.get('celsius')) or not math.isclose(pixel['celsius'], stats[extreme], abs_tol=1e-6):
            raise ValueError('Extreme mismatch')
        thresholds = []
        for key, label in ranges:
            c = clusters.get(key)
            if not isinstance(c, dict) or not all(_integer(c.get(k), total) for k in ('pixel_count', 'cluster_count', 'largest_cluster_size')):
                raise ValueError('Invalid cluster counts')
            n, groups, largest = c['pixel_count'], c['cluster_count'], c['largest_cluster_size']
            if not ((n == groups == largest == 0) or (1 <= groups <= n and 1 <= largest <= n and largest + groups - 1 <= n <= largest * groups)):
                raise ValueError('Impossible cluster counts')
            if key == 'below_10':
                if not all(_integer(counts.get(k), total) for k in ('below_0', 'from_0_to_10')):
                    raise ValueError('Invalid threshold counts')
                expected = counts['below_0'] + counts['from_0_to_10']
            else:
                expected = counts.get(key)
                if not _integer(expected, total):
                    raise ValueError('Invalid threshold count')
            if n != expected:
                raise ValueError('Threshold/cluster mismatch')
            thresholds.append(dict(label=label, pixel_count=n, cluster_count=groups, largest_cluster_size=largest))
        if thresholds[1]['pixel_count'] > thresholds[0]['pixel_count']:
            raise ValueError('Nested thresholds disagree')
        if extreme == 'maximum':
            finding = (f"Maximum DN {pixel['st_dn']}; {pixel['same_dn_qa_valid_pixel_count']} QA-valid pixels share this DN. "
                       + ('Possible source saturation/capping signal. Cause not established.' if pixel['st_dn'] == 65535 and pixel['same_dn_qa_valid_pixel_count'] > 1 else 'Cause not established; review source evidence.'))
        else:
            finding = (f"{pixel['invalid_qa_neighbor_count']} of 24 neighbouring pixels fail the production QA mask. "
                       + ('Possible QA-edge effect. Cause not established.' if pixel['invalid_qa_neighbor_count'] else 'Cause not established; review source evidence.'))
        output.append(dict(date=date, product_id=product, extreme_label='Absolute max' if extreme == 'maximum' else 'Absolute min',
                           extreme_celsius=stats[extreme], percentile_label='P99' if percentile == 'p99' else 'P1', percentile_celsius=stats[percentile],
                           thresholds=thresholds, finding=finding))
    return output


def decorate_audit(result, raw, kind):
    """Called only after the shared readiness count validator accepts a report."""
    data = raw['summary'] if kind == 'quality' else raw
    expected_key = {'quality': 'scenes_expected', 'processing': 'expected_scene_count', 'extreme': 'scenes_expected', 'sentinel': 'expected_product_count'}[kind]
    passed_key = 'products_passed' if kind == 'sentinel' else 'scenes_passed'
    result['audit_result'] = data['overall_status']
    result['summary'] = result['details'] + [f"{data[passed_key]}/{data[expected_key]} {'products' if kind == 'sentinel' else 'scenes'} passed"]
    result['display_status'] = 'PASS' if result['status'] == 'pass' else 'REVIEW'
    result['interpretation'] = 'Saved audit checks completed. This does not establish municipal coverage or production acceptance.' if result['status'] == 'pass' else 'The saved audit requires review. Consult the source report for unresolved checks.'
    if kind == 'processing' and result['status'] == 'pass':
        result['summary'].append('QA masking and Celsius conversion completed.')
    if kind == 'extreme' and result['status'] == 'pass':
        try:
            result['diagnostics'] = extreme_summaries(raw)
        except (ValueError, TypeError, KeyError):
            result.update(status='unavailable', display_status='UNAVAILABLE', summary=[], details=[], diagnostics=[], interpretation='Evidence unavailable: extreme diagnostic fields are missing or inconsistent.')
            return
        result['display_status'] = 'REVIEW'
        result['summary'].append(f"{data['scenes_passed']}/{data['scenes_expected']} scenes reviewed; investigated clusters retained unchanged.")
        result['interpretation'] = 'The diagnostic audit passed; the causes of the extremes remain unconfirmed. ' + UNCHANGED
    if kind == 'sentinel' and result['status'] == 'fail':
        missing = data['safe_directories_found'] < data['expected_product_count'] or data['required_file_slots_found'] < data['minimum_required_files_expected']
        if raw.get('intake_state') == 'PENDING' and missing:
            result['display_status'] = 'PENDING'
            result['interpretation'] = 'Pending source acquisition. Audit result: FAIL — required source files are missing. Any acquired files still require validation; this is not a project or software failure.'


def evidence_chains(rows, audits, discovery, blockers):
    by_id = {r['id']: r for r in rows}
    by_audit = {a['id']: a for a in audits}
    def stage(label, status):
        return dict(label=label, status=status)
    def audit_state(id_):
        a = by_audit[id_]
        return 'REVIEWED' if a['status'] == 'pass' and id_ == 'landsat_extremes' else a['display_status']
    landsat = by_id['landsat_lst_scenes']
    boundary = by_id['municipal_boundary']
    boundary_ready = boundary['status'] == 'verified' and boundary['local_available']
    selected = discovery.get('sentinel2', {}).get('items') if isinstance(discovery.get('sentinel2'), dict) else None
    selection_ok = isinstance(selected, list) and bool(selected) and all(isinstance(s, dict) and isinstance(s.get('product_id'), str) and re.fullmatch(r'S2[ABC]_MSIL2A_\d{8}T\d{6}_N\d{4}_R\d{3}_T\d{2}[A-Z]{3}_\d{8}T\d{6}', s['product_id']) for s in selected)
    selection_ok = selection_ok and len({s['product_id'] for s in selected}) == len(selected)
    sentinel = by_audit['sentinel_intake']
    sentinel_ready = sentinel['status'] == 'pass' and by_id['sentinel2_l2a_scenes']['status'] == 'verified'
    return [dict(title='Landsat evidence chain', stages=[
        stage('Source acquisition', 'COMPLETE' if landsat['status'] == 'verified' else 'PENDING'),
        stage('Integrity audit', audit_state('landsat_source')),
        stage('Processing audit', audit_state('landsat_processing')),
        stage('Extreme diagnostic review', audit_state('landsat_extremes')),
        stage('Municipal clipping', 'NOT ESTABLISHED' if boundary_ready else 'WAITING FOR BOUNDARY'),
        stage('Model dataset', 'BLOCKED' if blockers else 'NOT ESTABLISHED'),
    ]), dict(title='Sentinel evidence chain', stages=[
        stage('Source selection', 'COMPLETE' if selection_ok else 'UNAVAILABLE'),
        stage('Manual file intake', sentinel['display_status']),
        stage('Band validation', 'PASS' if sentinel['status'] == 'pass' else 'WAITING' if sentinel['display_status'] == 'PENDING' else sentinel['display_status']),
        stage('NDVI/NDBI processing', 'NOT ESTABLISHED' if sentinel_ready and boundary_ready else 'BLOCKED'),
    ])]
