"""A complete typed sentence survives unresolved prose in the same source."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection, validate_requirement_graph
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored

FIRST = 'Aster builds a one-stop online and offline service platform for users.'
TAIL = 'Context about additional arrangements remains under discussion.'


def production(tmp_path):
    text = '# Platform\n\n' + FIRST + ' ' + TAIL
    original = authored(tmp_path, text)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    return text, graph, evaluation_projection(graph)


def test_complete_first_sentence_keeps_typed_endpoints_and_ordered_remainder(tmp_path):
    text, graph, required = production(tmp_path)
    retained = graph['comparison_coverage']['retained_semantic_requirements']
    facts = [n for n in graph['nodes'] if n['id'] in retained['B']]
    assert [(f['subject'], f['attribute'], f['value']) for f in facts] == [
        ('Aster', 'build', 'a one-stop online and offline service platform')]
    assert facts[0]['source']['text_span'] == [0, len(FIRST) - 1]
    assert facts[0]['statement_boundary_evidence']['sentence_source']['text_span'] == [0, len(FIRST)]
    [content] = graph['source_form_requirements']
    assert content['source']['text_span'] == [len(FIRST), len(FIRST) + 1 + len(TAIL)]
    relations = [r for r in graph['relations'] if r['id'] in retained['L']]
    assert {'field_binding', 'narrative_nominal_coordination_scope',
            'narrative_nominal_compound_scope', 'narrative_prepositional_attachment'} <= {r['type'] for r in relations}
    assert graph['comparison_coverage']['responsibility_complete']
    score = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    assert score['layers']['B']['numerator'] == score['layers']['B']['denominator'] == 2
    assert score['publishable'], score['blockers']
    orders = [r for r in score['outcomes'] if r['id'].startswith('L:mixed-order:')]
    assert len(orders) == 1 and orders[0]['outcome'] == 'correct'
    assert score['layers']['L']['denominator'] == len(retained['L']) + 2
    validate_evidence(score)


@pytest.mark.parametrize('change', ['wrong_beneficiary', 'delete_typed', 'reverse', 'negation', 'wrong_tense'])
def test_mixed_requirement_identity_and_denominators_do_not_follow_candidate(tmp_path, change):
    text, _, required = production(tmp_path)
    if change == 'wrong_beneficiary':
        candidate = text.replace('for users', 'for providers')
    elif change == 'delete_typed':
        candidate = text.replace(FIRST + ' ', '')
    elif change == 'negation':
        candidate = text.replace('builds', 'does not build')
    elif change == 'wrong_tense':
        candidate = text.replace('builds', 'built')
    else:
        candidate = text.replace(FIRST + ' ' + TAIL, TAIL + ' ' + FIRST)
    good = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    changed = grade_layers(required, read_candidate_markdown(candidate, sample_id=required['sample_id']))
    assert {k: v['denominator'] for k, v in changed['layers'].items()} == {
        k: v['denominator'] for k, v in good['layers'].items()}
    if change == 'reverse':
        assert changed['layers']['L']['numerator'] < changed['layers']['L']['denominator']
    else:
        assert any(r['outcome'] != 'correct' for r in changed['outcomes'] if r['layer'] in {'B', 'L'})
    if change in {'negation', 'wrong_tense'}:
        assert changed['layers']['B']['numerator'] == 1
        assert [r['outcome'] for r in changed['outcomes'] if r['layer'] == 'B'].count('incorrect') == 1


@pytest.mark.parametrize('change', ['source', 'typed_owner', 'remove_order', 'replay_order'])
def test_mixed_order_requirements_and_final_evidence_cannot_be_rebound(tmp_path, change):
    text, graph, required = production(tmp_path)
    if change == 'replay_order':
        score = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
        next(r for r in score['outcomes'] if r['id'].startswith('L:mixed-order:'))['outcome'] = 'incorrect'
        with pytest.raises(ValueError):
            validate_evidence(score)
        return
    changed = deepcopy(required)
    if change == 'source':
        changed['source_form_order_anchors'][0]['source']['text_span'][1] += 1
    elif change == 'typed_owner':
        changed['source_form_order_anchors'][0]['typed_requirement_ids'] = ['invented-owner']
    else:
        changed['comparison_coverage']['mixed_order_requirement_ids'] = []
    with pytest.raises(ValueError):
        grade_layers(changed, read_candidate_markdown(text, sample_id=required['sample_id']))
    graph['source_form_order_anchors'] = []
    with pytest.raises(ValueError):
        validate_requirement_graph(graph)


@pytest.mark.parametrize('body', [
    'The company owns the platform. ' + TAIL,
    'Notes: ' + FIRST + ' ' + TAIL,
])
def test_whole_content_policy_and_external_field_ownership_survive_the_sentence_boundary(tmp_path, body):
    original = authored(tmp_path, '# Terms\n\n' + body)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    assert not graph['source_form_order_anchors']
    assert not graph['comparison_coverage']['retained_semantic_requirements']['B']
    assert [b['source']['text_span'] for b in graph['source_form_requirements']] == [[0, len(body)]]
    required = evaluation_projection(graph)
    score = grade_layers(required, read_candidate_markdown('# Terms\n\n' + body, sample_id=required['sample_id']))
    assert score['layers']['B']['denominator'] == score['layers']['L']['denominator'] == 1
    validate_evidence(score)
