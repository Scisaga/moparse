"""A current pointer cannot select a partial or mixed eight-pipeline batch."""

import json
from types import SimpleNamespace

import pytest

from moparse_eval.packaging import read_json, write_json
from moparse_eval.service_evaluation import (
    _require_expected_gate,
    activate_executions,
    launch,
    prepare_run,
)


def prepare(tmp_path, monkeypatch):
    monkeypatch.setattr('moparse_eval.cli.code_identity', lambda: {'software_id': 'controlled-source'})
    checks = {'status': 'passed', 'expected_structure_gate': {'status': 'passed', 'software_id': 'controlled-source',
                                                           'allowed_input_scope_context': ['explicit pending boundary']}}
    validation = tmp_path / 'validation.json'
    write_json(validation, checks)
    runs = []
    for number in range(1, 9):
        pipeline = f'P{number:02}'
        path = tmp_path / 'executions' / 'controlled-source' / pipeline.lower()
        path.mkdir(parents=True)
        (path / 'final.md').write_text('An actual controlled rendering.\n')
        write_json(path / 'run.json', {'state': 'completed', 'native_pipeline': {'pipeline': pipeline},
            'software': {'software_id': 'controlled-source'}, 'validation': checks,
            'cases': [{'sample_id': 'fixture', 'suite': 'quality800', 'phase': 'measured', 'final_markdown': 'final.md'}]})
        runs.append(path)
    pointer = tmp_path / 'current' / 'index.json'
    write_json(pointer, {'state': 'old-selected-execution'})
    return runs, pointer, validation


def test_eight_new_runs_are_selected_together_without_overwriting_their_artifacts(tmp_path, monkeypatch):
    runs, pointer, validation = prepare(tmp_path, monkeypatch)
    before = {path: (path / 'final.md').read_bytes() for path in runs}
    activate_executions(runs, pointer, validation)
    selected = read_json(pointer)
    assert selected['state'] == 'active' and set(selected['pipelines']) == {f'P{n:02}' for n in range(1, 9)}
    assert selected['software_id'] == 'controlled-source'
    assert {path: (path / 'final.md').read_bytes() for path in runs} == before
    assert list(pointer.parent.glob('*.part')) == []


@pytest.mark.parametrize('mutation', ['missing_pipeline', 'old_software', 'missing_gate', 'missing_output', 'different_scope'])
def test_incomplete_or_mixed_batch_leaves_the_previous_current_pointer_intact(tmp_path, monkeypatch, mutation):
    runs, pointer, validation = prepare(tmp_path, monkeypatch)
    before = pointer.read_bytes()
    record = read_json(runs[-1] / 'run.json')
    if mutation == 'missing_pipeline':
        runs.pop()
    elif mutation == 'old_software':
        record['software']['software_id'] = 'old'
    elif mutation == 'missing_gate':
        record['validation'] = {'status': 'passed'}
    elif mutation == 'missing_output':
        (runs[-1] / 'final.md').unlink()
    else:
        record['cases'][0]['sample_id'] = 'another-scope'
    if mutation != 'missing_pipeline':
        write_json(runs[-1] / 'run.json', record)
    with pytest.raises(ValueError):
        activate_executions(runs, pointer, validation)
    assert pointer.read_bytes() == before


def test_old_diagnostic_status_cannot_substitute_for_the_expected_structure_gate():
    with pytest.raises(ValueError, match='expected structure gate'):
        _require_expected_gate({'status': 'passed', 'software_id': 'controlled-source'}, 'controlled-source')


def test_completed_execution_cannot_be_reused_for_warmup(tmp_path):
    write_json(tmp_path / 'run.json', {'state': 'completed'})
    original = (tmp_path / 'run.json').read_bytes()
    with pytest.raises(ValueError, match='immutable'):
        launch(tmp_path, 'warmup')
    assert (tmp_path / 'run.json').read_bytes() == original


def test_activation_cannot_replace_an_existing_delivered_markdown(tmp_path, monkeypatch):
    runs, _pointer, validation = prepare(tmp_path, monkeypatch)
    original = tmp_path / 'current' / 'final.md'
    original.write_text('Preserve the existing delivered output.')
    with pytest.raises(ValueError, match='current/index.json'):
        activate_executions(runs, original, validation)
    assert original.read_text() == 'Preserve the existing delivered output.'


def test_runner_records_new_audit_paths_under_the_actual_candidate_root(tmp_path, monkeypatch):
    monkeypatch.setattr('moparse_eval.cli.code_identity', lambda: {'software_id': 'controlled-source'})
    monkeypatch.setattr('moparse_eval.service_evaluation.docker_command', lambda *_args: ['controlled-worker'])
    def controlled_process(command, **_kwargs):
        data = [{'State': {'Running': False}}] if command[:2] == ['docker', 'inspect'] else {}
        return SimpleNamespace(returncode=0, stdout=json.dumps(data))
    monkeypatch.setattr('moparse_eval.service_evaluation.subprocess.run', controlled_process)
    checks = {'expected_structure_gate': {'status': 'passed', 'software_id': 'controlled-source'}}
    write_json(tmp_path / 'run.json', {'state': 'frozen', 'software': {'software_id': 'controlled-source'},
        'validation': checks, 'execution_environment': {}, 'cases': [{'case_id': 'fixture', 'phase': 'measured'}]})
    outcome = {'observation': 'artifacts/fixture/observation.json', 'final_markdown': 'artifacts/fixture/final.md',
               'final_json': 'artifacts/fixture/final.json', 'edit_ledger': 'artifacts/fixture/stage-edit-ledger.json',
               'service_evidence': 'artifacts/fixture/service-evidence.json',
               'stage_outputs': [{'stage': 'adapted', 'scope': 'actual_adapter_page_rendering',
                                  'markdown': 'artifacts/fixture/stages/adapted.md',
                                  'observation': 'artifacts/fixture/stages/adapted.json',
                                  'audit': 'artifacts/fixture/stages/adapted.audit.json'}]}
    write_json(tmp_path / 'candidate/artifacts/fixture/outcome.json', outcome)
    write_json(tmp_path / 'candidate/measured-environment.json', {'controlled': True})
    assert launch(tmp_path, 'measured') == 0
    saved = read_json(tmp_path / 'run.json')['cases'][0]
    assert saved['edit_ledger'] == 'candidate/artifacts/fixture/stage-edit-ledger.json'
    assert saved['service_evidence'] == 'candidate/artifacts/fixture/service-evidence.json'
    assert saved['stage_outputs'][0]['audit'] == 'candidate/artifacts/fixture/stages/adapted.audit.json'


@pytest.mark.parametrize('pipeline', [f'P{number:02}' for number in range(1, 9)])
def test_preparation_declares_actual_adapter_stages_and_keeps_backend_versions(tmp_path, monkeypatch, pipeline):
    baseline, dataset, project = tmp_path / 'baseline', tmp_path / 'dataset', tmp_path / 'project'
    baseline.mkdir()
    dataset.mkdir()
    monkeypatch.setattr('moparse_eval.cli.code_identity', lambda: {'software_id': 'controlled-source'})
    monkeypatch.setattr('moparse_eval.cli.snapshot_software', lambda path, _identity: path.mkdir())
    monkeypatch.setattr('moparse_eval.service_evaluation.ROOT', project)
    write_json(project / 'benchmark/execution-lock.json', {'pipelines': {pipeline: {'runtime': {'image': 'controlled-image'}}}})
    write_json(dataset / 'manifest.json', {'name': 'controlled', 'samples': [{'id': 'fixture', 'input': 'inputs/fixture.pdf'}]})
    observation = f'artifacts/{pipeline}/measured-quality800-r1/fixture/observation.json'
    write_json(baseline / observation, {'input_page_count': 1})
    write_json(baseline / 'run.json', {'dataset': str(dataset), 'cases': [{'pipeline': pipeline, 'sample_id': 'fixture',
        'suite': 'quality800', 'phase': 'measured', 'repetition': 1, 'observation': observation}],
        'configurations': [{'pipeline': pipeline, 'versions': {'docling-core': 'fixed-docling', 'paddlex': 'fixed-paddle'}}]})
    config = tmp_path / 'config.json'
    write_json(config, {'diagnostic_capture_stages': ['exported', 'final']})
    destination = tmp_path / 'new-execution' / pipeline.lower()
    prepare_run(baseline, destination, config, pipeline=pipeline)
    record = read_json(destination / 'run.json')
    assert record['native_pipeline']['versions'] == {'docling-core': 'fixed-docling', 'paddlex': 'fixed-paddle'}
    assert record['service_config']['diagnostic_capture_stages'][0] == 'adapted'
    assert record['execution_environment']['cpus'] == 8
    plan = read_json(destination / 'candidate/worker-plan.json')
    assert not {'expected', 'references', 'reference_root'} & set(plan)
    with pytest.raises(FileExistsError):
        prepare_run(baseline, destination, config, pipeline=pipeline)
