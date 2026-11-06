"""Synthetic gates must fail before any actual container or candidate work."""

import asyncio
from copy import deepcopy

import pytest
from requirement_gate_fixture import controlled_expected, controlled_gate, controlled_source_run

from moparse_eval.packaging import read_json, write_json
from moparse_eval.requirement_gate import replay_gate_receipt
from moparse_eval.service_evaluation import _authorized_expected, launch, prepare_run, worker


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
    monkeypatch.setattr('moparse_eval.service_evaluation.read_expected',
                        lambda sample, _root, **_kwargs: controlled_expected(sample['id']))
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
    checks = controlled_gate(tmp_path / 'gate', software_id='source-current', sample_id='one')
    write_json(validation, checks)
    before = deepcopy(checks)
    run = prepare_run(baseline, tmp_path / 'prepared', config, pipeline='P05', validation=validation)
    assert read_json(run / 'run.json')['state'] == 'prepared'
    assert read_json(run / 'run.json')['validation'] == before
    plan = read_json(run / 'candidate/worker-plan.json')
    assert plan['replay_gate_receipt'] == replay_gate_receipt(before, 'source-current', scope={'one'})
    assert 'expected_structure_gate' not in plan
    assert checks['expected_structure_gate']['requirement_index']['path'] not in repr(plan)
    assert not (run / 'warmup-command.json').exists()
    assert read_json(validation) == before


def test_valid_synthetic_worker_function_does_not_need_corpus_or_a_container(tmp_path, monkeypatch):
    checks = controlled_gate(tmp_path / 'gate', software_id='source-controlled', sample_id='one')
    receipt = replay_gate_receipt(checks, 'source-controlled', scope={'one'})
    path = tmp_path / 'worker-plan.json'
    write_json(path, {'software_id': 'source-controlled', 'replay_gate_receipt': receipt,
                     'run_id': 'controlled', 'cases': [
                         {'phase': 'warmup', 'case_id': 'warmup-one', 'sample_id': 'one', 'suite': 'warmup'},
                         {'phase': 'measured', 'case_id': 'quality-one', 'sample_id': 'one', 'suite': 'quality800'}]})
    monkeypatch.setattr('moparse_eval.runtime.actual_worker_limits', lambda: {'controlled': True})
    monkeypatch.setattr('moparse_eval.runtime.package_versions', lambda _names: {})
    calls = []
    async def controlled_case(_plan, case, _output):
        calls.append(case['case_id'])
        return {'case_id': case['case_id'], 'status': 'completed', 'timing': {'postprocessing_seconds': 0}}
    monkeypatch.setattr('moparse_eval.service_evaluation.execute_case', controlled_case)
    asyncio.run(worker(path, 'warmup'))
    assert calls == ['warmup-one']


def test_host_rechecks_current_authorized_expected_before_any_candidate_container(tmp_path, monkeypatch):
    monkeypatch.setattr('moparse_eval.cli.code_identity', lambda: {'software_id': 'source-current'})
    no_container(monkeypatch)
    checks = controlled_gate(tmp_path / 'gate', software_id='source-current')
    baseline = controlled_source_run(tmp_path / 'source')
    receipt = replay_gate_receipt(checks, 'source-current', scope={'fixture'})
    # The current synthetic source differs while every generated artifact and
    # its rebound evidence still agrees. Host validation must read the source.
    current = controlled_expected()
    [target] = current['targets']
    target.update(text='Name: Echo; Revenue: 17', raw_text='Name: Echo; Revenue: 17', raw='Name: Echo; Revenue: 17')
    monkeypatch.setattr('moparse_eval.service_evaluation.read_expected', lambda *_a, **_k: current)
    write_json(tmp_path / 'run.json', {'state': 'prepared', 'software': {'software_id': 'source-current'},
        'baseline_run': str(baseline), 'validation': checks,
        'cases': [{'sample_id': 'fixture', 'suite': 'quality800', 'phase': 'measured'}]})
    write_json(tmp_path / 'candidate/worker-plan.json', {'replay_gate_receipt': receipt})
    before = (tmp_path / 'run.json').read_bytes()
    with pytest.raises(ValueError, match='source|semantics'):
        launch(tmp_path, 'warmup')
    assert (tmp_path / 'run.json').read_bytes() == before
    assert not (tmp_path / 'warmup-command.json').exists()


@pytest.mark.parametrize('entrypoint', ['host', 'compiler'])
@pytest.mark.parametrize('mutation', ['narrowed_quality', 'duplicate_samples', 'duplicate_lite', 'duplicate_quality'])
def test_original_manifest_scope_cannot_shrink_or_duplicate_before_any_expected_source_read(
        tmp_path, monkeypatch, entrypoint, mutation):
    from moparse_eval.requirement_graph import compile_saved_requirements

    baseline, dataset = tmp_path / 'original-native', tmp_path / 'original-package'
    session = {'dataset': str(dataset), 'cases': [
        {'pipeline': 'P01', 'sample_id': ident, 'suite': 'quality800', 'phase': 'measured'} for ident in ['A', 'B']]}
    manifest = {'samples': [{'id': 'A'}, {'id': 'B'}], 'suites': {'lite': ['A', 'B']}}
    scope = {'A', 'B'}
    if mutation == 'narrowed_quality':
        session['cases'].pop()
        scope = {'A'}
    elif mutation == 'duplicate_samples':
        manifest['samples'].append({'id': 'A'})
    elif mutation == 'duplicate_lite':
        manifest['suites']['lite'].append('A')
    else:
        session['cases'].append(deepcopy(session['cases'][0]))

    def controlled_json(path):
        return session if path == baseline / 'run.json' else manifest

    def forbidden(*_args, **_kwargs):
        pytest.fail('invalid authorization must fail before source reads, snapshots or execution')

    monkeypatch.setattr('moparse_eval.service_evaluation.read_json', controlled_json)
    monkeypatch.setattr('moparse_eval.packaging.read_json', controlled_json)
    monkeypatch.setattr('moparse_eval.service_evaluation.read_expected', forbidden)
    monkeypatch.setattr('moparse_eval.expected_readback.read_expected', forbidden)
    monkeypatch.setattr('moparse_eval.cli.code_identity', forbidden)
    output = baseline / 'requirements' / 'new-view'
    with pytest.raises(ValueError, match='complete declared Lite'):
        if entrypoint == 'host':
            _authorized_expected(baseline, scope)
        else:
            compile_saved_requirements(baseline, output, expected_root=tmp_path / 'expected')
    assert not output.exists()


@pytest.mark.parametrize('explicit_suite', [False, True])
def test_host_authorization_uses_exact_lite_manifest_or_all_sample_fallback_without_extra_reads(
        tmp_path, monkeypatch, explicit_suite):
    baseline, dataset = tmp_path / 'original-native', tmp_path / 'original-package'
    session = {'dataset': str(dataset), 'cases': [
        {'pipeline': pipeline, 'sample_id': ident, 'suite': 'quality800', 'phase': 'measured'}
        for pipeline in ['P01', 'P02'] for ident in ['A', 'B']]}
    manifest = {'samples': [{'id': 'A'}, {'id': 'B'}]}
    if explicit_suite:
        manifest['samples'].append({'id': 'OutsideLite'})
        manifest['suites'] = {'lite': ['A', 'B']}
    monkeypatch.setattr('moparse_eval.service_evaluation.read_json',
                        lambda path: session if path == baseline / 'run.json' else manifest)
    calls = []
    def controlled_source(sample, *_args, **_kwargs):
        calls.append(sample['id'])
        return {'sample_id': sample['id'], 'targets': []}
    monkeypatch.setattr('moparse_eval.service_evaluation.read_expected', controlled_source)
    assert set(_authorized_expected(baseline, {'A', 'B'})) == {'A', 'B'}
    assert calls == ['A', 'B']
