"""Independent source/evidence binding mutations over controlled generated JSON."""

from copy import deepcopy

import pytest
from requirement_gate_fixture import artifact, controlled_gate

from moparse_eval.packaging import read_json, write_json
from moparse_eval.requirement_gate import (
    replay_gate_receipt,
    validate_expected_structure_gate,
    validate_replay_gate_receipt,
)


def test_bare_status_cannot_start_a_replay():
    with pytest.raises(ValueError, match="requirement index"):
        validate_expected_structure_gate({"expected_structure_gate": {"status": "passed", "software_id": "current"}}, "current")


def test_complete_controlled_artifacts_are_bound_without_candidate_or_pdf_reads(tmp_path):
    validation = controlled_gate(tmp_path)
    index = validate_expected_structure_gate(validation, "controlled-source", scope={"fixture"})
    assert [row["sample_id"] for row in index["records"]] == ["fixture"]
    receipt = replay_gate_receipt(validation, "controlled-source", scope={"fixture"})
    validate_replay_gate_receipt(receipt, "controlled-source", scope={"fixture"})
    assert "path" not in repr(receipt) and "Name" not in repr(receipt) and "Revenue" not in repr(receipt)


@pytest.mark.parametrize("source", [None, {"sample_id": "another", "targets": []}, {"sample_id": "fixture"}])
def test_invalid_external_source_map_cannot_silently_disable_canonical_binding(tmp_path, source):
    validation = controlled_gate(tmp_path)
    with pytest.raises(ValueError, match="actual authorized expected"):
        validate_expected_structure_gate(validation, "controlled-source", expected_by_sample={"fixture": source})


@pytest.mark.parametrize("mutation", ["missing", "wrong_digest", "old_source", "different_scope", "pending", "missing_inventory"])
def test_missing_stale_or_incomplete_requirement_manifest_fails_closed(tmp_path, mutation):
    validation = controlled_gate(tmp_path)
    gate = validation["expected_structure_gate"]
    if mutation == "missing":
        (tmp_path / "index.json").unlink()
    elif mutation == "wrong_digest":
        gate["requirement_index"]["sha256"] = "0" * 64
    elif mutation == "different_scope":
        with pytest.raises(ValueError, match="sample scope"):
            validate_expected_structure_gate(validation, "controlled-source", scope={"another"})
        return
    else:
        index = read_json(tmp_path / "index.json")
        if mutation == "old_source":
            index["software_id"] = "old"
        elif mutation == "pending":
            index["semantic_complete"] = False
        else:
            index.pop("source_obligation_inventory_complete")
        write_json(tmp_path / "index.json", index)
        gate["requirement_index"] = artifact(tmp_path / "index.json")
    with pytest.raises(ValueError, match="expected structure gate"):
        validate_expected_structure_gate(validation, "controlled-source")


@pytest.mark.parametrize("purpose", ["oracle", "mutations", "comparison"])
@pytest.mark.parametrize("mutation", ["absent", "changed", "old_index", "self_derived", "known_defect", "missing_category", "mismatch", "no_input", "duplicate_case"])
def test_independent_evidence_cannot_be_replaced_by_flags_totals_or_partial_observations(tmp_path, purpose, mutation):
    validation = controlled_gate(tmp_path)
    gate = validation["expected_structure_gate"]
    path = tmp_path / f"{purpose}.json"
    if mutation == "absent":
        gate["evidence"].pop(purpose)
    elif mutation == "changed":
        path.write_text(path.read_text() + "\n")
    else:
        record = read_json(path)
        if mutation == "old_index":
            record["requirement_index_sha256"] = "0" * 64
        elif mutation == "self_derived":
            record["oracle_origin"] = "production_compiler"
        elif mutation == "known_defect":
            record["known_defects"] = ["false acceptance"]
        elif mutation == "missing_category":
            record["cases"].pop()
        elif mutation == "mismatch":
            record["cases"][0]["observed"] = {"accepted": True}
        elif mutation == "no_input":
            record["cases"][0].pop("input")
        else:
            record["cases"].append(deepcopy(record["cases"][0]))
        write_json(path, record)
        gate["evidence"][purpose] = artifact(path)
    with pytest.raises(ValueError, match="expected structure gate"):
        validate_expected_structure_gate(validation, "controlled-source")


def test_changed_generated_view_fails_even_if_the_manifest_is_still_unchanged(tmp_path):
    validation = controlled_gate(tmp_path)
    view = tmp_path / "samples/fixture.json"
    view.write_text(view.read_text() + "\n")
    with pytest.raises(ValueError, match="requirement view"):
        validate_expected_structure_gate(validation, "controlled-source")


@pytest.mark.parametrize("mutation", ["software", "scope", "digest", "extra_path"])
def test_worker_receipt_cannot_drift_or_carry_reference_locations(tmp_path, mutation):
    validation = controlled_gate(tmp_path)
    receipt = replay_gate_receipt(validation, "controlled-source")
    if mutation == "software":
        receipt["software_id"] = "old"
    elif mutation == "scope":
        receipt["sample_ids"] = ["another"]
    elif mutation == "digest":
        receipt["evidence_sha256"]["oracle"] = "0" * 64
    else:
        receipt["expected_path"] = "/forbidden"
    with pytest.raises(ValueError, match="expected structure gate"):
        validate_replay_gate_receipt(receipt, "controlled-source", scope={"fixture"})


def document_gate(tmp_path, body=None):
    from requirement_gate_fixture import controlled_evidence

    from moparse_eval.requirement_gate import _digest
    from moparse_eval.requirement_graph import write_requirement_graph
    from tests.unit.test_document_ast_comparison import TRAINING, compile_content_document

    graph, _ = compile_content_document(tmp_path, '# 治理\n\n' + (TRAINING if body is None else body))
    assert not graph['semantic_complete'] and graph['comparison_coverage']['responsibility_complete']
    view = tmp_path / 'samples/document.json'
    write_requirement_graph(graph, view, view.with_suffix('.xml'))
    row = {'sample_id': graph['sample_id'], 'json': 'samples/document.json',
        'software_id': 'controlled-source', 'worker_software_unchanged': True,
        'comparison_contract': 'document_ast', 'comparison_contract_version': 'document_ast/1',
        'semantic_complete': False, 'source_obligation_inventory_complete': True,
        'inventory_validation': {'status': 'passed'}, 'generated_view_sha256': artifact(view)['sha256'],
        'comparison_coverage_sha256': _digest(graph['comparison_coverage'])}
    path = tmp_path / 'index.json'
    write_json(path, {'purpose': 'expected_output_requirements_not_corpus_review',
        'comparison_contract': 'document_ast', 'comparison_contract_version': 'document_ast/1',
        'software_id': 'controlled-source', 'software_unchanged': True, 'semantic_complete': False,
        'source_obligation_inventory_complete': True, 'inventory_validation': {'status': 'passed'}, 'records': [row]})
    return controlled_evidence(tmp_path, path, 'controlled-source')


def test_new_contract_accepts_independently_evidenced_content_without_forging_semantic_completion(tmp_path):
    validation = document_gate(tmp_path)
    index = validate_expected_structure_gate(validation, 'controlled-source')
    assert index['semantic_complete'] is False
    receipt = replay_gate_receipt(validation, 'controlled-source')
    validate_replay_gate_receipt(receipt, 'controlled-source')
    assert receipt['comparison_contract_version'] == 'document_ast/1'
    assert not any(token in repr(receipt) for token in ['董事', 'source_span', 'expected.md'])


@pytest.mark.parametrize('omit', ['sample', 'case', 'both'])
def test_mixed_order_is_a_required_independently_bound_responsibility(tmp_path, omit):
    body = ('Aster builds a one-stop online and offline service platform for users. '
            'Context about additional arrangements remains under discussion.')
    validation = document_gate(tmp_path, body)
    validate_expected_structure_gate(validation, 'controlled-source')
    path = tmp_path / 'oracle.json'
    record = read_json(path)
    sample = record['samples'][0]
    [case] = [c for c in record['cases'] if c['case_id'] in sample['case_ids']]
    assert any(ident.startswith('L:mixed-order:') for ident in sample['requirement_ids'])
    for row in ([sample] if omit == 'sample' else [case] if omit == 'case' else [sample, case]):
        row['requirement_ids'] = [ident for ident in row['requirement_ids'] if not ident.startswith('L:mixed-order:')]
    write_json(path, record)
    validation['expected_structure_gate']['evidence']['oracle'] = artifact(path)
    with pytest.raises(ValueError, match='responsibilities'):
        validate_expected_structure_gate(validation, 'controlled-source')


@pytest.mark.parametrize('mutation', ['no_samples', 'partial_samples', 'missing_requirement', 'missing_obligation',
    'missing_limitation', 'no_capability', 'unexecuted_capability', 'wrong_coverage', 'wrong_view', 'wrong_contract',
    'no_case_reference', 'no_source_assertions', 'uncovered_assertion_case'])
def test_document_contract_needs_complete_independent_coverage_and_capability_evidence(tmp_path, mutation):
    validation = document_gate(tmp_path)
    gate = validation['expected_structure_gate']
    path = tmp_path / ('comparison.json' if 'capability' in mutation else 'oracle.json')
    evidence = read_json(path)
    if mutation == 'no_samples':
        evidence.pop('samples')
    elif mutation == 'partial_samples':
        evidence['samples'] = []
    elif mutation == 'no_capability':
        evidence['capabilities'].pop(next(iter(evidence['capabilities'])))
    elif mutation == 'unexecuted_capability':
        evidence['capabilities'][next(iter(evidence['capabilities']))] = ['never-executed']
    elif mutation == 'no_case_reference':
        evidence['samples'][0]['case_ids'] = []
    elif mutation == 'no_source_assertions':
        case = evidence['cases'][-1]
        case['expected'] = case['observed'] = {'accepted': True}
    elif mutation == 'uncovered_assertion_case':
        evidence['cases'][-1]['requirement_ids'].pop()
    else:
        sample = evidence['samples'][0]
        if mutation.startswith('missing_'):
            sample[{'missing_requirement': 'requirement_ids', 'missing_obligation': 'obligation_ids',
                    'missing_limitation': 'analysis_limitation_ids'}[mutation]].pop()
        else:
            sample[{'wrong_coverage': 'comparison_coverage_sha256', 'wrong_view': 'generated_view_sha256',
                    'wrong_contract': 'comparison_contract_version'}[mutation]] = 'wrong'
    write_json(path, evidence)
    gate['evidence']['comparison' if 'capability' in mutation else 'oracle'] = artifact(path)
    with pytest.raises(ValueError, match='expected structure gate'):
        validate_expected_structure_gate(validation, 'controlled-source')


@pytest.mark.parametrize('owner', ['index', 'record', 'graph', 'gate', 'receipt'])
@pytest.mark.parametrize('version', ['document_ast/99', 'semantic/1', None])
def test_declared_contract_version_must_be_known_and_consistent_at_every_boundary(tmp_path, owner, version):
    validation = document_gate(tmp_path)
    gate = validation['expected_structure_gate']
    if owner == 'gate':
        gate['comparison_contract_version'] = version
    elif owner == 'receipt':
        from moparse_eval.requirement_gate import _digest
        receipt = replay_gate_receipt(validation, 'controlled-source')
        receipt['comparison_contract_version'] = version
        receipt['receipt_sha256'] = _digest({k: v for k, v in receipt.items() if k != 'receipt_sha256'})
        with pytest.raises(ValueError, match='contract'):
            validate_replay_gate_receipt(receipt, 'controlled-source')
        return
    else:
        path = tmp_path / 'index.json'
        index = read_json(path)
        row = index['records'][0]
        if owner == 'index':
            index['comparison_contract_version'] = version
        elif owner == 'record':
            row['comparison_contract_version'] = version
        else:
            graph_path = tmp_path / row['json']
            graph = read_json(graph_path)
            graph['comparison_contract_version'] = version
            write_json(graph_path, graph)
            row['generated_view_sha256'] = artifact(graph_path)['sha256']
        write_json(path, index)
        gate['requirement_index'] = artifact(path)
    with pytest.raises(ValueError, match='contract'):
        validate_expected_structure_gate(validation, 'controlled-source')


@pytest.mark.parametrize('mutation', ['no_coverage', 'forged_coverage', 'source', 'structure', 'new_scope_gap'])
def test_content_ready_flag_cannot_waive_real_source_structure_or_coverage_gaps(tmp_path, mutation):
    from moparse_eval.requirement_gate import _digest

    validation = document_gate(tmp_path)
    gate = validation['expected_structure_gate']
    path = tmp_path / 'index.json'
    index = read_json(path)
    row = index['records'][0]
    graph_path = tmp_path / row['json']
    graph = read_json(graph_path)
    graph['content_comparison_ready'] = True
    if mutation == 'no_coverage':
        graph.pop('comparison_coverage')
    elif mutation == 'forged_coverage':
        graph['comparison_coverage']['obligations'].pop()
    elif mutation == 'source':
        graph['sources'][0]['text'] += '偽造'
    elif mutation == 'structure':
        graph['document_ast']['children'].pop()
    else:
        graph['unresolved'].append({'id': 'new-scope', 'reason': 'input_scope_context', 'layers': ['L', 'B'],
            'source': graph['sources'][-1]['source']})
    write_json(graph_path, graph)
    row['generated_view_sha256'] = artifact(graph_path)['sha256']
    row['comparison_coverage_sha256'] = _digest(graph.get('comparison_coverage'))
    write_json(path, index)
    gate['requirement_index'] = artifact(path)
    with pytest.raises(ValueError):
        validate_expected_structure_gate(validation, 'controlled-source')


def test_typed_comparison_capabilities_are_preserved_in_document_contract_coverage(tmp_path):
    from tests.unit.test_document_ast_comparison import TRAINING, compile_content_document

    graph, _ = compile_content_document(tmp_path, '# 治理\n\n流動資產為人民幣80億元。' + TRAINING)
    assert 'quantity_assertion' in graph['required_matcher_features']
    assert 'quantity_assertion' in graph['comparison_coverage']['required_capabilities']


@pytest.mark.parametrize('mutation', ['sample_software', 'changed_worker', 'false_semantic_aggregate'])
def test_document_gate_checks_sample_software_and_truthful_semantic_aggregate(tmp_path, mutation):
    validation = document_gate(tmp_path)
    path = tmp_path / 'index.json'
    index = read_json(path)
    if mutation == 'sample_software':
        index['records'][0]['software_id'] = 'stale'
    elif mutation == 'changed_worker':
        index['records'][0]['worker_software_unchanged'] = False
    else:
        index['semantic_complete'] = True
    write_json(path, index)
    validation['expected_structure_gate']['requirement_index'] = artifact(path)
    with pytest.raises(ValueError, match='software|semantic-analysis status'):
        validate_expected_structure_gate(validation, 'controlled-source')
