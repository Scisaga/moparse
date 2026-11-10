"""Invented legal list contracts through the full expected/candidate chain."""

from copy import deepcopy

import pytest

from moparse_eval.document_ast_comparison import _candidate_ast
from moparse_eval.expected_report import validate_evidence
from moparse_eval.field_sequence_requirements import read_field_sequence_requirements
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored

TERMS = '''# Contract

- If the bonds remain outstanding, the Borrower shall supply reports; provided that if trading ceases, the Borrower shall furnish:
  - (A) audited statements within 140 calendar days after the fiscal year ends; and
  - (B) interim statements within 80 calendar days, except when the Authority grants an exemption.
- If the Pricing Notice specifies the Overnight Option:
  - (i) if Averaging is applicable:
    - (A) use the earlier rate; or
    - (B) use the later rate.
  - (ii) replace “End Date” with “Maturity Date”.'''


def compiled(tmp_path, text=TERMS):
    original = authored(tmp_path, text)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    assert graph['source_obligation_inventory']['source_complete']
    return original, graph, evaluation_projection(graph)


def checked(required, text):
    score = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    if score['publishable']:
        validate_evidence(score)
    else:
        with pytest.raises(ValueError):
            validate_evidence(score)
    return score


def test_complete_nested_content_has_fixed_responsibility_and_final_proofs(tmp_path):
    _, graph, required = compiled(tmp_path)
    assert graph['comparison_coverage']['responsibility_complete']
    assert len(graph['source_form_requirements']) == 8
    assert not required['comparison_coverage']['retained_semantic_requirements']['B']
    good = checked(required, TERMS)
    assert good['publishable'], good['blockers']
    assert good['layers']['B']['denominator'] == 8
    assert good['layers']['B']['numerator'] == 8
    assert good['layers']['L']['numerator'] == good['layers']['L']['denominator']
    assert good['layers']['L']['denominator'] == 15  # Eight scopes plus seven order edges.
    assert not graph['comparison_coverage']['retained_semantic_requirements']['L']
    assert any(p['relation'] == 'printed_list_parent_scope' for p in graph['comparison_coverage']['content_relation_ownership'])
    wrapped = TERMS.replace('audited statements within', 'audited statements\n    within')
    changed = checked(required, wrapped)
    assert changed['publishable'] and changed['layers']['B'] == good['layers']['B']
    assert changed['layers']['L'] == good['layers']['L']


def test_terminal_empty_clause_label_is_not_a_field_sequence():
    parsed = read_field_sequence_requirements(
        'If listed, the borrower shall report; provided that if delisted, it shall furnish:',
        {'path': '<invented>', 'lines': [1, 1]})
    assert not parsed['matched'] and not parsed['facts']


@pytest.mark.parametrize('before,after', [
    ('140', '141'), ('calendar days', 'calendar years'),
    ('the Borrower shall furnish', 'the Trustee shall furnish'),
    ('except when the Authority grants an exemption', ''),
    ('if trading ceases', 'if trading continues'),
    ('use the earlier rate', 'use the later rate'),
    ('“End Date” with “Maturity Date”', '“Maturity Date” with “End Date”'),
])
def test_nested_duties_never_pass_mutated_business_content(tmp_path, before, after):
    _, _, required = compiled(tmp_path)
    good = checked(required, TERMS)
    bad = checked(required, TERMS.replace(before, after))
    assert any(r['outcome'] != 'correct' for r in bad['outcomes'] if r['layer'] == 'B')
    assert {k: v['denominator'] for k, v in good['layers'].items()} == {
        k: v['denominator'] for k, v in bad['layers'].items()}
    if before == '140':
        assert any(r['outcome'] == 'incorrect' for r in bad['outcomes'] if r['layer'] == 'B')


def test_intact_words_with_deleted_or_wrong_list_scope_are_rejected(tmp_path):
    _, _, required = compiled(tmp_path)
    flattened = '\n'.join(line.lstrip() for line in TERMS.splitlines())
    score = checked(required, flattened)
    assert any(r['outcome'] == 'incorrect' for r in score['outcomes'] if r['layer'] == 'L')
    borrowed = TERMS.replace('  - (i) if Averaging is applicable:', '- (i) if Averaging is applicable:')
    score = checked(required, borrowed)
    assert any(r['outcome'] != 'correct' for r in score['outcomes'] if r['layer'] == 'L')


def test_missing_structure_and_unhandled_rewrite_keep_fixed_denominators(tmp_path):
    _, _, required = compiled(tmp_path)
    good = checked(required, TERMS)
    for changed, expected_status in (('# Contract', 'missing'),
                                     (TERMS.replace('audited statements', 'certified accounts'), 'unresolved')):
        bad = checked(required, changed)
        assert bad['layers']['B']['denominator'] == good['layers']['B']['denominator']
        assert any(r['decision']['status'] == expected_status for r in bad['document_comparison']['decision']['proof']['rows'])
        assert any(r['outcome'] != 'correct' for r in bad['outcomes'] if r['layer'] == 'B')


def test_coverage_forgery_and_forged_parent_evidence_are_rejected(tmp_path):
    original, graph, required = compiled(tmp_path)
    bad = deepcopy(graph)
    bad['source_form_requirements'].pop()
    with pytest.raises(ValueError):
        validate_requirement_graph(bad, expected=original)
    bad = deepcopy(graph)
    bad['source_form_requirements'].append(deepcopy(bad['source_form_requirements'][-1]))
    with pytest.raises(ValueError):
        validate_requirement_graph(bad, expected=original)
    candidate = read_candidate_markdown(TERMS, sample_id=required['sample_id'])
    unit = next(u for u in candidate['syntax'] if u.get('parents'))
    unit['parents'] = ['Forged unrelated condition']
    with pytest.raises(ValueError):
        _candidate_ast(candidate)


def test_numeric_parent_and_series_bindings_are_never_replaced_by_content(tmp_path):
    text = '# Metrics\n\n单位：万元\n\n- 收入：2024年310；2023年270。\n  - 子项：2024年110；2023年90。'
    _, graph, required = compiled(tmp_path, text)
    facts = [f for f in required['business'] if f['id'] in graph['comparison_coverage']['retained_semantic_requirements']['B']]
    assert any(f['value'] == '310' for f in facts)
    assert any(f['value'] == '110' and f['qualifiers'].get('parent_metric') == '收入' for f in facts)
    assert all(b['source']['lines'][0] not in {5, 6} for b in graph['source_form_requirements'])


def test_nested_measured_change_stays_typed_when_outer_clause_is_unread(tmp_path):
    text = '# 技术\n\n- 系统采用以下技术：\n  - 产品提供独立的隔离防护技术，支持实时检测，相比传统方案误报率降低84%，满足业务需求。'
    _, graph, required = compiled(tmp_path, text)
    assert any(f['value'] == '84' and f['qualifiers'].get('unit') == '%'
               and f.get('logic', {}).get('kind') == 'year_on_year_change'
               and f['id'] in graph['comparison_coverage']['retained_semantic_requirements']['B'] for f in required['business'])
