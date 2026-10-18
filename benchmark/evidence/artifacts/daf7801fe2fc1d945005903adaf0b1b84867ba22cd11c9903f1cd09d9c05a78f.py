"""Capture completion must remain separate from API partial-quality status."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from benchmark import moparse_benchmark as b
from benchmark.tools.capture_transport import aggregate, inspect_capture


@pytest.fixture
def receipt(tmp_path: Path):
    markdown = b'<!-- page: 1 -->\nsource -1,234.56\r\n'
    for name in ['result.md', 'persisted-result.md', 'response-body.bin', 'persisted-result-response.bin']:
        (tmp_path / name).write_bytes(markdown)
    asset = tmp_path / 'original.png'
    asset.write_bytes(b'original-raster-bytes')
    listed = [{'download_url': '/v1/content/jobs/job_X/assets/asset_X', 'sha256': b.digest(asset)}]
    (tmp_path / 'assets-list.bin').write_text(json.dumps(listed))
    # GET of an already terminal job may return a valid empty SSE response.
    (tmp_path / 'events.bin').write_bytes(b'')
    for name, raw in [('response', 'response-body.bin'), ('persisted-result-response', 'persisted-result-response.bin'),
                      ('events', 'events.bin'), ('assets-list', 'assets-list.bin')]:
        (tmp_path / (name + '.json')).write_text(json.dumps({
            'status': 200, 'body_sha256': b.digest(tmp_path / raw),
            'headers': {'content-type': 'text/event-stream' if name == 'events' else 'application/octet-stream'}}))
    (tmp_path / 'job.json').write_text(json.dumps({'status': 'partial', 'error': None}))
    entry = {'id': 'original', 'status': 'partial', 'job': 'job_X', 'page_count': 1,
             'MD_SHA256': b.digest(tmp_path / 'result.md'),
             'persisted_MD_SHA256': b.digest(tmp_path / 'persisted-result.md'),
             'assets': [{'public_path': listed[0]['download_url'], 'path': str(asset), 'sha256': b.digest(asset), 'status': 200}]}
    return tmp_path, entry


def test_partial_remains_API_partial_and_only_explicit_capture_scope_completes(receipt):
    directory, entry = receipt
    original = deepcopy(entry)
    result = inspect_capture(directory, entry)
    assert result['transport_complete'] and result['capture_status'] == 'completed'
    assert result['actual_job_status'] == 'partial' and not result['quality_fully_resolved']
    assert entry == original
    case = {**entry, **result}
    assert aggregate([case], 'documents')['status'] == 'failed'
    explicit = aggregate([case], 'capture')
    assert explicit['status'] == 'completed' and explicit['completion_scope'] == 'transport_capture'
    assert explicit['actual_job_status_counts'] == {'partial': 1}
    assert explicit['partial_document_ids'] == ['original']
    assert not explicit['quality_fully_resolved']
    assert case['status'] == 'partial'


@pytest.mark.parametrize('damage', ['MD_bytes', 'MD_SHA', 'asset_bytes', 'asset_missing', 'asset_HTTP',
                                   'index_missing_asset', 'events_missing', 'events_HTTP',
                                   'persisted_HTTP', 'submit_HTTP', 'job_failed', 'missing_page'])
def test_transport_failure_cannot_be_accepted_as_expected_partial(receipt, damage):
    directory, entry = receipt
    if damage == 'MD_bytes':
        (directory / 'persisted-result.md').write_bytes(b'different\n')
    elif damage == 'MD_SHA':
        entry['MD_SHA256'] = '0' * 64
    elif damage == 'asset_bytes':
        Path(entry['assets'][0]['path']).write_bytes(b'replaced')
    elif damage == 'asset_missing':
        Path(entry['assets'][0]['path']).unlink()
    elif damage == 'asset_HTTP':
        entry['assets'][0]['status'] = 404
    elif damage == 'index_missing_asset':
        entry['assets'] = []
    elif damage == 'events_missing':
        (directory / 'events.bin').unlink()
    elif damage in {'events_HTTP', 'persisted_HTTP', 'submit_HTTP'}:
        name = {'events_HTTP': 'events', 'persisted_HTTP': 'persisted-result-response', 'submit_HTTP': 'response'}[damage]
        path = directory / (name + '.json')
        data = json.loads(path.read_text())
        data['status'] = 502
        path.write_text(json.dumps(data))
    elif damage == 'job_failed':
        (directory / 'job.json').write_text(json.dumps({'status': 'failed', 'error': None}))
    else:
        entry['page_count'] = 2
    result = inspect_capture(directory, entry)
    assert not result['transport_complete'] and result['capture_status'] == 'failed'
    assert entry['status'] == 'partial'
    assert aggregate([{**entry, **result}], 'capture')['status'] == 'failed'
