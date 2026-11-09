"""One source-bound parent responsibility, while independent relations survive."""

from copy import deepcopy

import pytest

from moparse_eval.document_ast_comparison import _without_grammar_analysis
from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection, validate_requirement_graph
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored

BODY = 'The archive retains security code 004721 for the retired issue.'


def production(tmp_path):
    text = '# Terms\n\n' + BODY
    original = authored(tmp_path, text)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    return original, graph, evaluation_projection(graph)


@pytest.mark.parametrize('text', [BODY, BODY.replace('retains ', 'retains\n\n'),
                                BODY.replace('004721', '004721.0')])
def test_source_split_or_numeric_rewrite_cannot_change_the_single_parent_requirement(tmp_path, text):
    _, graph, required = production(tmp_path)
    before = deepcopy(required)
    result = grade_layers(required, read_candidate_markdown('# Terms\n\n' + text, sample_id=required['sample_id']))
    assert required == before
    assert result['layers']['B']['denominator'] == result['layers']['L']['denominator'] == 1
    assert [r['id'] for r in result['outcomes'] if r['layer'] == 'L'] == ['L:content:0']
    assert result['layers']['L']['numerator'] == 1
    expected_business = 'unresolved' if '004721.0' in text else 'correct'
    assert [r['outcome'] for r in result['outcomes'] if r['layer'] == 'B'] == [expected_business]
    if expected_business == 'correct':
        validate_evidence(result)
    else:
        with pytest.raises(ValueError):
            validate_evidence(result)
    assert graph['comparison_coverage']['content_relation_ownership']
    assert 'statement_parent_scope_single_vote' in graph['comparison_coverage']['required_capabilities']


@pytest.mark.parametrize('kind', ['heading_parent', 'heading_membership', 'heading_order',
                                'list_membership', 'prose_reading_order'])
def test_relation_type_and_shared_source_cannot_erase_a_distinct_responsibility(tmp_path, kind):
    _, graph, required = production(tmp_path)
    # A controlled, independently injected relation tests the filter boundary;
    # it is not a pre-filled substitute for the production-chain cases above.
    changed = deepcopy(required)
    original_scope = next(e for e in changed['relations'] if e['type'] == 'prose_heading_membership')
    independent = {**deepcopy(original_scope), 'type': kind, 'id': 'independent:test'}
    changed['relations'].append(independent)
    retained = _without_grammar_analysis(changed, graph['source_form_requirements'])
    assert independent in retained['relations']
    assert original_scope not in retained['relations']


@pytest.mark.parametrize('mutation', ['different_parent', 'different_endpoint', 'different_origin',
                                     'borrowed_provenance', 'unowned_span'])
def test_parent_responsibility_needs_both_endpoints_and_its_actual_source(tmp_path, mutation):
    _, graph, required = production(tmp_path)
    changed = deepcopy(required)
    edge = next(e for e in changed['relations'] if e['type'] == 'prose_heading_membership')
    if mutation == 'different_parent':
        edge['left'] = ['Elsewhere']
    elif mutation == 'different_endpoint':
        edge['right']['scope'] = ['Elsewhere']
    elif mutation == 'different_origin':
        edge['source']['lines'] = [5, 5]
    elif mutation == 'borrowed_provenance':
        edge['scope_evidence']['sources'][0]['lines'] = [5, 5]
    else:
        edge['source']['text_span'] = [0, len(BODY) + 1]
    retained = _without_grammar_analysis(changed, graph['source_form_requirements'])
    assert edge in retained['relations']
    assert not retained['content_relation_ownership']


@pytest.mark.parametrize('mutation', ['owner_source', 'owner_parent', 'counted_relation'])
def test_ownership_ledger_and_final_evidence_are_recomputed_not_trusted(tmp_path, mutation):
    original, graph, _ = production(tmp_path)
    proof = graph['comparison_coverage']['content_relation_ownership'][0]['owners'][0]
    if mutation == 'owner_source':
        proof['source']['text_span'][0] += 1
    elif mutation == 'owner_parent':
        proof['scope'] = ['Elsewhere']
    else:
        proof['counted_relation_id'] = 'L:content:9'
    with pytest.raises(ValueError, match='comparison responsibility coverage'):
        validate_requirement_graph(graph, expected=original)
    required = evaluation_projection(graph)
    with pytest.raises(ValueError, match='fixed comparison responsibility'):
        grade_layers(required, read_candidate_markdown('# Terms\n\n' + BODY, sample_id=required['sample_id']))
