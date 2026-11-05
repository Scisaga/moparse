"""Synthetic gates must fail before any actual container or candidate work."""

import asyncio
from copy import deepcopy

import pytest

from moparse_eval.packaging import read_json, write_json
from moparse_eval.service_evaluation import launch, prepare_run, worker


def no_container(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('gate rejection must precede container construction or spawning')
    monkeypatch.setattr('moparse_eval.service_evaluation.docker_command', forbidden)
    monkeypatch.setattr('moparse_eval.service_evaluation.subprocess.run', forbidden)


@pytest.mark.parametrize('phase,state', [('warmup', 'prepared'), ('measured', 'frozen')])
def test_missing_run_gate_stops_before_container_or_record_mutation(tmp_path, monkeypatch, phase, state):
    monkeypatch.setattr('moparse_eval.cli.code_identity', lambda: {'software_id': 'source-current'})
    no_container(monkeypatch)
    write_json(tmp_path / 'run.json', {'state': state, 'software': {'software_id': 'source-current'}})
    before = (tmp_path / 'run.json').read_bytes()
    with pytest.raises(ValueError, match='expected structure gate'):
        launch(tmp_path, phase)
    assert (tmp_path / 'run.json').read_bytes() == before
    assert not (tmp_path / f'{phase}-command.json').exists()


def test_warmup_cannot_run_a_different_source_even_with_an_old_matching_gate(tmp_path, monkeypatch):
    monkeypatch.setattr('moparse_eval.cli.code_identity', lambda: {'software_id': 'source-new'})
    no_container(monkeypatch)
    write_json(tmp_path / 'run.json', {'state': 'prepared', 'software': {'software_id': 'source-old'},
        'validation': {'expected_structure_gate': {'status': 'passed', 'software_id': 'source-old'}}})
    with pytest.raises(ValueError, match='changed'):
        launch(tmp_path, 'warmup')


@pytest.mark.parametrize('phase', ['warmup', 'measured'])
@pytest.mark.parametrize('gate', [None, {'status': 'passed', 'software_id': 'source-other'}])
def test_worker_gate_is_checked_before_environment_or_execute_case(tmp_path, monkeypatch, phase, gate):
    plan = {'software_id': 'source-current', 'run_id': 'synthetic', 'cases': [{'phase': phase, 'case_id': 'fixture'}]}
    if gate is not None:
        plan['expected_structure_gate'] = gate
    path = tmp_path / 'worker-plan.json'
    write_json(path, plan)
    calls = []
    async def forbidden_case(*_args, **_kwargs):
        calls.append('execute_case')
        raise AssertionError('a missing gate must not execute a candidate')
    def forbidden_write(*_args, **_kwargs):
        calls.append('environment')
        raise AssertionError('a missing gate must not start the worker lifecycle')
    monkeypatch.setattr('moparse_eval.service_evaluation.execute_case', forbidden_case)
    monkeypatch.setattr('moparse_eval.service_evaluation.write_json', forbidden_write)
    with pytest.raises(ValueError, match='expected structure gate'):
        asyncio.run(worker(path, phase))
    assert calls == []


def test_preparation_can_attach_a_real_gate_without_executing_any_candidate(tmp_path, monkeypatch):
    baseline, dataset, project = tmp_path / 'baseline', tmp_path / 'dataset', tmp_path / 'project'
    monkeypatch.setattr('moparse_eval.cli.code_identity', lambda: {'software_id': 'source-current'})
    monkeypatch.setattr('moparse_eval.cli.snapshot_software', lambda path, _identity: path.mkdir())
    monkeypatch.setattr('moparse_eval.service_evaluation.ROOT', project)
    no_container(monkeypatch)
    write_json(project / 'benchmark/execution-lock.json', {'pipelines': {'P05': {'runtime': {'image': 'synthetic'}}}})
    write_json(dataset / 'manifest.json', {'name': 'invented', 'samples': [{'id': 'one', 'input': 'inputs/one.pdf'}]})
    observation = 'artifacts/P05/measured-quality800-r1/one/observation.json'
    write_json(baseline / observation, {'input_page_count': 1})
    write_json(baseline / 'run.json', {'dataset': str(dataset), 'cases': [{'pipeline': 'P05', 'sample_id': 'one',
        'suite': 'quality800', 'phase': 'measured', 'repetition': 1, 'observation': observation}],
        'configurations': [{'pipeline': 'P05', 'versions': {}}]})
    config, validation = tmp_path / 'config.json', tmp_path / 'validation.json'
    write_json(config, {})
    checks = {'expected_structure_gate': {'status': 'passed', 'software_id': 'source-current'}}
    write_json(validation, checks)
    before = deepcopy(checks)
    run = prepare_run(baseline, tmp_path / 'prepared', config, pipeline='P05', validation=validation)
    assert read_json(run / 'run.json')['state'] == 'prepared'
    assert read_json(run / 'run.json')['validation'] == before
    assert read_json(run / 'candidate/worker-plan.json')['expected_structure_gate'] == before['expected_structure_gate']
    assert not (run / 'warmup-command.json').exists()
    assert read_json(validation) == before


def test_valid_synthetic_worker_function_does_not_need_corpus_or_a_container(tmp_path, monkeypatch):
    gate = {'status': 'passed', 'software_id': 'source-controlled'}
    path = tmp_path / 'worker-plan.json'
    write_json(path, {'software_id': 'source-controlled', 'expected_structure_gate': gate,
                     'run_id': 'controlled', 'cases': [{'phase': 'warmup', 'case_id': 'one'}]})
    monkeypatch.setattr('moparse_eval.runtime.actual_worker_limits', lambda: {'controlled': True})
    monkeypatch.setattr('moparse_eval.runtime.package_versions', lambda _names: {})
    calls = []
    async def controlled_case(_plan, case, _output):
        calls.append(case['case_id'])
        return {'case_id': case['case_id'], 'status': 'completed', 'timing': {'postprocessing_seconds': 0}}
    monkeypatch.setattr('moparse_eval.service_evaluation.execute_case', controlled_case)
    asyncio.run(worker(path, 'warmup'))
    assert calls == ['one']
