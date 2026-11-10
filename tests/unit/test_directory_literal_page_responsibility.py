"""Declared directories bind literal page slots, parent groups and headings."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.source_obligations import audit_source_obligations
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored

TEXT = '# Contents\n\n## North\n\n- Safety and Review Committee: 017\n\n## South\n\n- Notes to the Accounts: 028'


def production(tmp_path):
    original = authored(tmp_path, TEXT)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    return original, graph, evaluation_projection(graph)


@pytest.mark.parametrize('explicit_page', [False, True])
def test_navigation_page_and_parent_roles_survive_the_complete_production_chain(tmp_path, explicit_page):
    _, graph, required = production(tmp_path)
    retained = graph['comparison_coverage']['retained_semantic_requirements']
    assert [(f['subject'], f['attribute'], f['value'], f['identity_facets'])
            for f in graph['nodes'] if f['id'] in retained['B']] == [
        ('Safety and Review Committee', 'Page', '017', {'toc_parent': ['North']}),
        ('Notes to the Accounts', 'Page', '028', {'toc_parent': ['South']})]
    assert not graph['source_form_requirements']
    assert graph['comparison_coverage']['responsibility_complete']
    assert 'literal_navigation_role' in graph['comparison_coverage']['required_capabilities']
    candidate = TEXT.replace(': ', ': Page ') if explicit_page else TEXT
    score = grade_layers(required, read_candidate_markdown(candidate, sample_id=required['sample_id']))
    assert (score['layers']['B']['numerator'], score['layers']['B']['denominator']) == (2, 2)
    assert (score['layers']['L']['numerator'], score['layers']['L']['denominator']) == (7, 7)  # Six original relations plus the declared navigation order.
    assert [r['role'] for r in score['outcomes'] if r['layer'] == 'L'].count('heading_parent') == 2
    validate_evidence(score)


@pytest.mark.parametrize('change', ['wrong_page', 'wrong_group', 'wrong_level', 'missing', 'duplicate', 'arithmetic_rewrite', 'leading_zero'])
def test_navigation_errors_cannot_change_fixed_denominators_or_become_quantities(tmp_path, change):
    _, _, required = production(tmp_path)
    candidate = {
        'wrong_page': TEXT.replace('017', '018'),
        'wrong_group': TEXT.replace('## North', '## West'),
        'wrong_level': TEXT.replace('## South', '### South'),
        'missing': TEXT.replace('- Safety and Review Committee: 017', ''),
        'duplicate': TEXT.replace('- Safety and Review Committee: 017', '- Safety and Review Committee: 017\n- Safety and Review Committee: 017'),
        'arithmetic_rewrite': TEXT.replace('017', '17.0'),
        'leading_zero': TEXT.replace('017', '17'),
    }[change]
    score = grade_layers(required, read_candidate_markdown(candidate, sample_id=required['sample_id']))
    assert [score['layers'][k]['denominator'] for k in ('B', 'L')] == [2, 7]
    assert any(r['outcome'] != 'correct' for r in score['outcomes'] if r['layer'] in {'B', 'L'})
    if change in {'wrong_page', 'leading_zero'}:
        assert score['layers']['B']['numerator'] == 1
        assert score['layers']['L']['numerator'] == 7
        assert all(c['value']['quantity_equivalence_applicable'] is False
                   for r in score['outcomes'] if r['layer'] == 'B' for c in r['comparisons'])
        validate_evidence(score)


@pytest.mark.parametrize('change', ['drop_page_edge', 'drop_parent_edge', 'borrow_page', 'borrow_parent', 'invent_attribute'])
def test_literal_navigation_proof_requires_its_own_source_slots_and_relations(tmp_path, change):
    _, graph, _ = production(tmp_path)
    changed = deepcopy(graph)
    facts = [f for f in changed['nodes'] if f['id'] in changed['projections']['B']]
    first, second = facts
    if change.startswith('drop_'):
        kind = 'toc_entry_page' if change == 'drop_page_edge' else 'toc_parent'
        edge = next(e for e in changed['relations'] if e['type'] == kind)
        changed['relations'].remove(edge)
        changed['projections']['L'].remove(edge['id'])
    elif change == 'borrow_page':
        first['value_source'] = deepcopy(second['value_source'])
    elif change == 'borrow_parent':
        first['row_evidence'][-1] = deepcopy(second['row_evidence'][-1])
    else:
        first['attribute_source'] = deepcopy(first['value_source'])
    audited = audit_source_obligations(changed['source_obligation_inventory'], changed)
    assert not audited['semantic_complete']
