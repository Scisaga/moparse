"""Identity collection must not pass missing code, static assets or model files."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import pytest

from benchmark.tools import capture_deployment as capture


def test_file_comparison_checks_both_file_sets_and_contents(tmp_path: Path):
    (tmp_path / 'present.py').write_text('accepted')
    (tmp_path / 'new.py').write_text('new host source')
    cache = tmp_path / '__pycache__'
    cache.mkdir()
    (cache / 'ignored.pyc').write_bytes(b'cache')
    host = capture.local_code(tmp_path)
    assert set(host) == {'present.py', 'new.py'}
    result = capture.compare_files({'present.py': host['present.py']}, host)
    assert result['missing_in_container'] == ['new.py']
    assert not result['matches_host_files']
    deployed = {**host, 'unexpected.py': 'a' * 64, 'present.py': 'b' * 64}
    result = capture.compare_files(deployed, host)
    assert result['unexpected_in_container'] == ['unexpected.py']
    assert result['content_mismatches'] == ['present.py']
    assert not result['matches_host_files']
    assert capture.compare_files(host, host)['matches_host_files']
    assert not capture.compare_files({}, {})['matches_host_files']


def test_static_asset_changes_and_missing_chunks_are_detected():
    host = {'index.html': 'a' * 64, 'assets/index.js': 'b' * 64}
    result = capture.compare_files({'index.html': 'c' * 64}, host)
    assert result['content_mismatches'] == ['index.html']
    assert result['missing_in_container'] == ['assets/index.js']
    assert not result['matches_host_files']


def valid_report():
    return {
        'health': {'config': {'native_parser_backend': 'mineru', 'mineru_header_verifier': 'docling'}},
        'ready': {'ready': True},
        'selected_settings': {'native_parser_backend': 'mineru', 'mineru_header_verifier': 'docling'},
        'worker': {'ready': True, 'model': 'selected-model'},
        'models': {'data': [{'id': 'selected-model'}]},
        'containers': [{'running': True}],
        'source': {'app': {'matches_host_files': True}, 'worker': {'matches_host_files': True}},
        'static': {'matches_host_files': True},
        'package_versions': {'app': {'packages': {'docling': '2.139.0'}}},
        'worker_patched_dependency': {'matches_reviewed_patch': True},
        'model_artifacts': {
            'vlm': {'matches_locked_files': True}, 'native': {'matches_locked_files': True},
            'docling_header_verifier': {'complete': True, 'selected_mount': {'Name': 'selected-volume'}},
        },
        'errors': [],
    }


def test_docling_header_models_cannot_be_missing_while_http_is_ready():
    report = valid_report()
    assert all(capture.readiness_checks(report).values())
    inventory = {'directory_exists': False, 'files': {}}
    required = capture.required_files(inventory, list(capture.DOCLING_REQUIRED_FILES))
    assert not required['complete']
    assert set(required['missing_files']) == set(capture.DOCLING_REQUIRED_FILES)
    report['model_artifacts']['docling_header_verifier'] = {
        **required, 'selected_mount': {'Name': 'empty-volume'},
    }
    checks = capture.readiness_checks(report)
    assert checks['http_ready']
    assert not checks['required_docling_models_complete']
    assert not all(checks.values())


def test_source_verifier_requires_model_files_even_without_header_verifier():
    report = valid_report()
    for settings in (report['selected_settings'], report['health']['config']):
        settings['mineru_header_verifier'] = 'none'
        settings['mineru_source_verifier'] = 'docling'
    assert all(capture.readiness_checks(report).values())
    report['model_artifacts']['docling_header_verifier']['complete'] = False
    assert not capture.readiness_checks(report)['required_docling_models_complete']


def test_source_verifier_live_setting_mismatch_is_not_verified():
    report = valid_report()
    report['selected_settings']['mineru_source_verifier'] = 'docling'
    report['health']['config']['mineru_source_verifier'] = 'none'
    assert not capture.readiness_checks(report)['live_native_selection_matches_settings']


@pytest.mark.parametrize('missing', ['file', 'size', 'mount'])
def test_docling_completeness_requires_every_nonempty_file_and_selected_mount(missing):
    names = list(capture.DOCLING_REQUIRED_FILES)
    files = {name: {'bytes': 42, 'sha256': 'a' * 64} for name in names}
    if missing == 'file':
        del files[names[0]]
    elif missing == 'size':
        files[names[0]]['bytes'] = 0
    required = capture.required_files({'directory_exists': True, 'files': files}, names)
    report = valid_report()
    report['model_artifacts']['docling_header_verifier'] = {
        **required, 'selected_mount': None if missing == 'mount' else {'Name': 'selected'},
    }
    assert not capture.readiness_checks(report)['required_docling_models_complete']


def test_mount_identity_uses_the_selected_path_and_most_specific_mount():
    inspected = {'mounts': [
        {'Type': 'volume', 'Name': 'selected-models', 'Destination': '/models', 'RW': False},
        {'Type': 'volume', 'Name': 'selected-docling', 'Destination': '/models/docling', 'RW': True},
    ]}
    actual = capture.mount_for_path(inspected, '/models/docling/model/subdir')
    assert actual['Name'] == 'selected-docling'
    assert actual['path_in_mount'] == 'model/subdir'
    assert capture.mount_for_path(inspected, '/models-other') is None


def test_unpatched_worker_or_wrong_served_model_cannot_pass():
    report = valid_report()
    report['worker_patched_dependency']['matches_reviewed_patch'] = False
    assert not capture.readiness_checks(report)['worker_ready_and_patch_matches']
    report = valid_report()
    report['models']['data'] = [{'id': 'other-model'}]
    assert not capture.readiness_checks(report)['served_model_matches_worker']


def test_identity_does_not_record_env_or_cli_tokens(monkeypatch):
    inspected = {
        'Id': 'container-id', 'Image': 'image-id',
        'Config': {'Env': ['API_KEY=do-not-copy'], 'Image': 'model:tag',
                   'Cmd': ['server', '--api-key', 'do-not-copy', '--max-num-seqs', '2'],
                   'Labels': {'private-token': 'do-not-copy'}},
        'State': {'StartedAt': 'now', 'Running': True}, 'Mounts': [],
    }
    monkeypatch.setattr(capture, 'command', lambda _args: json.dumps([inspected]))
    result = capture.identity('selected')
    assert 'do-not-copy' not in json.dumps(result)
    assert 'Env' not in result
    assert result['model_startup_options'] == {'--max-num-seqs': '2'}
    assert len(result['startup_command_SHA256']) == 64


def test_probe_whitelist_excludes_credentials_and_does_not_mutate_payload():
    payload = {'ready': True, 'Config': {'Env': ['API_KEY=secret']}, 'api_key': 'secret',
               'backends': [{'name': 'backend', 'state': 'ready', 'detail': 'private secret'}]}
    original = deepcopy(payload)
    result = capture.safe_probe('ready', payload)
    assert 'secret' not in json.dumps(result)
    assert payload == original


def test_collector_failure_produces_unverified_report_without_secret_exception_text(tmp_path, monkeypatch):
    def fail(*_args):
        raise RuntimeError('API_KEY=must-not-be-recorded')

    monkeypatch.setattr(capture, 'command', fail)
    monkeypatch.setattr(capture, 'endpoint', fail)
    args = argparse.Namespace(app='app', worker='worker', model='model', base_url='http://app',
                              worker_url='http://worker', model_url='http://model', static_dir=tmp_path)
    report = capture.collect(args)
    assert report['status'] == 'unverified' and not report['ready_and_source_matched']
    assert report['errors']
    assert 'must-not-be-recorded' not in json.dumps(report)


def test_empty_docling_volume_is_decisive_in_full_collection(tmp_path, monkeypatch):
    settings = {'native_parser_backend': 'mineru', 'mineru_header_verifier': 'docling',
                'docling_artifacts_path': '/models/docling', 'glm_ocr_enabled': False}
    monkeypatch.setattr(capture, 'command', lambda _args: '')
    monkeypatch.setattr(capture, 'selected_settings', lambda _container: settings)
    monkeypatch.setattr(capture, 'endpoint', lambda url: (
        {'status': 'ok', 'config': settings} if url.endswith('/health')
        else {'data': [{'id': 'selected-model'}]} if url.endswith('/v1/models')
        else {'ready': True, 'model': 'selected-model'}))
    monkeypatch.setattr(capture, 'identity', lambda name: {
        'container': name, 'running': True, 'mounts': [
            {'Name': 'selected-docling-volume', 'Destination': '/models/docling', 'Type': 'volume'},
            {'Name': 'selected-mineru', 'Destination': '/models/mineru', 'Type': 'volume'},
            {'Name': 'selected-native', 'Destination': '/models/mineru-native', 'Type': 'volume'},
        ]})
    monkeypatch.setattr(capture, 'package_versions', lambda _name: {'packages': {'recorded': '1'}})
    monkeypatch.setattr(capture, 'patched_dependency', lambda _name: {'matches_reviewed_patch': True})
    monkeypatch.setattr(capture, 'code', lambda *_args: {'source.py': 'a' * 64})
    monkeypatch.setattr(capture, 'local_code', lambda _path: {'source.py': 'a' * 64})
    lock = json.loads((capture.ROOT / 'native_worker/models.lock.json').read_text())
    complete_docling = False

    def inventory(container, directory, _names):
        if container == 'app':
            files = {name: {'sha256': 'a' * 64, 'bytes': 42}
                     for name in capture.DOCLING_REQUIRED_FILES} if complete_docling else {}
        else:
            key = 'vlm' if container == 'model' else 'native'
            entry = next(item for item in lock['models'] if item['id'] == key)
            files = {item['path']: {field: item[field] for field in ('sha256', 'bytes')}
                     for item in entry['files']}
        return {'directory': directory, 'directory_exists': True, 'files': files}

    monkeypatch.setattr(capture, 'artifacts', inventory)
    args = argparse.Namespace(app='app', worker='worker', model='model', base_url='http://app',
                              worker_url='http://worker', model_url='http://model', static_dir=tmp_path)
    report = capture.collect(args)
    assert report['all_locked_models_match']
    assert not report['ready_and_source_matched']
    assert [name for name, passed in report['identity_checks'].items() if not passed] == [
        'required_docling_models_complete']
    assert report['model_artifacts']['docling_header_verifier']['selected_mount']['Name'] == 'selected-docling-volume'
    complete_docling = True
    report = capture.collect(args)
    assert report['ready_and_source_matched'] and report['status'] == 'verified'
