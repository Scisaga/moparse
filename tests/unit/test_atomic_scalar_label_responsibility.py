"""Literal words inside a bound scalar key are not extra prose operators."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection, validate_requirement_graph
from moparse_eval.source_obligations import audit_source_obligations
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored


@pytest.mark.parametrize('label,value', [('Coverage of local and regional hospitals', '88%.'),
                                       ('Large and small associations served', '61%+.')])
def test_explicit_scalar_keeps_its_literal_key_value_and_one_binding(tmp_path, label, value):
    text = '# Metrics\n\n' + label + ': ' + value
    original = authored(tmp_path, text)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    assert graph['source_form_requirements'] == []
    required = evaluation_projection(graph)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [('', label, value)]
    assert graph['comparison_coverage']['responsibility_complete']
    for candidate, expected_b in [(text, 'correct'), (text.replace(value[:2], '57'), 'incorrect')]:
        result = grade_layers(required, read_candidate_markdown(candidate, sample_id=required['sample_id']))
        assert result['layers']['B']['denominator'] == result['layers']['L']['denominator'] == 1
        assert [r['outcome'] for r in result['outcomes'] if r['layer'] == 'B'] == [expected_b]
        assert [r['outcome'] for r in result['outcomes'] if r['layer'] == 'L'] == ['correct']
        validate_evidence(result)


@pytest.mark.parametrize('mutation', ['delete', 'wrong_label', 'borrow_value'])
def test_scalar_label_role_proof_requires_its_own_complete_field_binding(tmp_path, mutation):
    text = '# Metrics\n\nCoverage of local and regional hospitals: 88%.\n\nOther coverage: 57%.'
    original = authored(tmp_path, text)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    changed = deepcopy(graph)
    fact = next(n for n in changed['nodes'] if n.get('attribute') == 'Coverage of local and regional hospitals')
    edge = next(e for e in changed['relations'] if e.get('fact_id') == fact['id'] and e['type'] == 'field_binding')
    if mutation == 'delete':
        changed['relations'].remove(edge)
    elif mutation == 'wrong_label':
        edge['right']['attribute'] = 'Other coverage'
    else:
        fact['value_source']['lines'] = [5, 5]
    audited = audit_source_obligations(changed['source_obligation_inventory'], changed)
    and_obligation = next(o for o in changed['source_obligation_inventory']['obligations'] if o['text'] == 'and')
    row = next(r for r in audited['dispositions'] if r['obligation_id'] == and_obligation['id'])
    assert row['status'] == 'pending'
