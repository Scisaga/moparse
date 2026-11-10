"""Independent text-only literal-label, provenance and final-outcome probes."""

import json
from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored
from tests.validation.lite_stage5_assertions import IEA, check_literal_source

SOURCE = '# Disclosures\n\nNote: (2) Regional clients hold valid service contracts.'
DEFINITIONS = ('# Hardware\n\nNote: kW = kilowatt; GWh = gigawatt hour.\n\n'
               'Different projections can lead to uncertain estimates.')


def production(tmp_path, text=SOURCE):
    expected = authored(tmp_path, text)
    graph = compile_requirement_graph(expected, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=expected)
    return expected, graph, evaluation_projection(graph)


def final(required, text):
    candidate = read_candidate_markdown(text, sample_id=required['sample_id'])
    result = grade_layers(required, candidate)
    if result['publishable']:
        validate_evidence(result)
    else:
        with pytest.raises(ValueError):
            validate_evidence(result)
    # Replay serialized independent inputs through the same production grader.
    replay = grade_layers(json.loads(json.dumps(required)), json.loads(json.dumps(candidate)))
    assert replay['outcomes'] == result['outcomes']
    assert replay['layers'] == result['layers']
    return result


@pytest.mark.parametrize('label', ['Note', 'Condition', 'Exception', '附注', '条件', '例外'])
def test_visible_qualifier_label_has_one_real_literal_owner(tmp_path, label):
    text = '# Disclosures\n\n' + label + ': (2) Regional clients hold valid service contracts.'
    expected, graph, required = production(tmp_path, text)
    assert graph['comparison_coverage']['responsibility_complete']
    labels = [n for n in required['text'] if n['text'] == label]
    assert len(labels) == 1
    assert labels[0]['source']['lines'] == [3, 3]
    assert labels[0]['source']['text_span'] == [0, len(label)]
    assert expected['targets'][1]['raw_text'][slice(*labels[0]['source']['text_span'])] == label
    result = final(required, text)
    assert result['layers']['T']['denominator'] == len('Disclosures') + len(label) + len('(2) Regional clients hold valid service contracts.')
    assert all(o['outcome'] == 'correct' for o in result['outcomes'])


@pytest.mark.parametrize('change', ['correct', 'softbreak', 'word', 'digit', 'unit', 'punctuation', 'footnote', 'label'])
def test_final_T_checks_label_number_unit_punctuation_and_footnote(tmp_path, change):
    source = '# Disclosures\n\nNote: (2) Load remains 18 MW.'
    _, graph, required = production(tmp_path, source)
    assert graph['comparison_coverage']['responsibility_complete']
    changes = {'correct': source, 'softbreak': source.replace('Load remains', 'Load\nremains'),
               'word': source.replace('remains', 'remain'), 'digit': source.replace('18', '19'),
               'unit': source.replace('MW', 'MWh'), 'punctuation': source.replace('MW.', 'MW'),
               'footnote': source.replace('(2)', ''), 'label': source.replace('Note:', '')}
    score = final(required, changes[change])
    assert score['layers']['T']['denominator'] == len('DisclosuresNote(2) Load remains 18 MW.')
    rows = [o for o in score['outcomes'] if o['layer'] == 'T']
    if change in {'correct', 'softbreak'}:
        assert all(o['outcome'] == 'correct' for o in rows)
    else:
        assert any(o['outcome'] == 'incorrect' for o in rows)
        assert sum(score['layers']['T'][k] for k in ('S', 'D', 'I')) > 0


def test_equal_note_labels_in_distinct_parents_keep_distinct_T_capacity(tmp_path):
    source = '# A\n\nNote: (2) Load remains 18 MW.\n\n# B\n\nNote: (2) Load remains 18 MW.'
    _, _, required = production(tmp_path, source)
    labels = [n for n in required['text'] if n['text'] == 'Note']
    assert len(labels) == 2 and labels[0]['source']['lines'] != labels[1]['source']['lines']
    score = final(required, source.replace('Note:', '', 1))
    rows = [o for o in score['outcomes'] if o['layer'] == 'T' and o['expected']['text'] == 'Note']
    assert [o['outcome'] for o in rows].count('correct') == 1
    assert [o['outcome'] for o in rows].count('incorrect') == 1
    assert len({o['actual']['id'] for o in rows if o['actual']}) == 1


@pytest.mark.parametrize('mutation', ['delete', 'duplicate', 'source', 'offset'])
def test_source_Oracle_rejects_full_source_with_incomplete_or_wrong_literal_projection(tmp_path, mutation):
    expected, graph, _ = production(tmp_path, SOURCE)
    target = expected['targets'][1]
    independent = {**expected, 'sample_id': IEA}
    # Only this invented field's source location is renamed for the helper's
    # finite syntax declaration; no real source text is used as candidate.
    target = deepcopy(target)
    target['reference']['lines'] = [914, 914]
    changed = deepcopy(graph)
    for n in changed['nodes']:
        if n['source'].get('lines') == [3, 3]:
            n['source']['lines'] = [914, 914]
    check_literal_source(changed, independent, target)
    label = next(n for n in changed['nodes'] if n.get('kind') == 'text' and n['text'] == 'Note')
    if mutation == 'delete':
        changed['projections']['T'].remove(label['id'])
    elif mutation == 'duplicate':
        duplicate = {**deepcopy(label), 'id': 'extra-literal'}
        changed['nodes'].append(duplicate)
        changed['projections']['T'].append(duplicate['id'])
    elif mutation == 'source':
        label['source']['path'] = 'different-source'
    else:
        label['source']['text_span'] = [1, 5]
    with pytest.raises(AssertionError):
        check_literal_source(changed, independent, target)


def test_full_text_can_keep_T_while_ownership_and_order_fail_L(tmp_path):
    source = '# A\n\nNote: Regional clients hold valid service contracts.\n\n# B\n\nNote: Local clients hold valid permits.'
    _, _, required = production(tmp_path, source)
    score = final(required, source.replace('Regional clients hold valid service contracts.', 'TEMP').replace(
        'Local clients hold valid permits.', 'Regional clients hold valid service contracts.').replace(
        'TEMP', 'Local clients hold valid permits.'))
    assert score['layers']['T']['score'] == 100
    assert any(o['outcome'] != 'correct' for o in score['outcomes'] if o['layer'] == 'L')


def test_source_Oracle_cannot_exempt_an_equation_sign_inside_a_literal_value(tmp_path):
    expected, graph, _ = production(tmp_path, DEFINITIONS)
    target = deepcopy(expected['targets'][1])
    target['reference']['lines'] = [914, 914]
    independent = {**expected, 'sample_id': IEA}
    changed = deepcopy(graph)
    for node in changed['nodes']:
        if node['source'].get('lines') == [3, 3]:
            node['source']['lines'] = [914, 914]
    check_literal_source(changed, independent, target)
    value = next(n for n in changed['nodes'] if n.get('kind') == 'text' and n['text'] == 'kW = kilowatt')
    changed['nodes'].remove(value)
    changed['projections']['T'].remove(value['id'])
    for start, end in [(6, 8), (11, 19)]:
        node = {**deepcopy(value), 'id': value['id'] + f':{start}',
                'text': target['raw_text'][start:end],
                'source': {**deepcopy(value['source']), 'text_span': [start, end]}}
        changed['nodes'].append(node)
        changed['projections']['T'].append(node['id'])
    with pytest.raises(AssertionError, match='missing literal responsibility'):
        check_literal_source(changed, independent, target)


@pytest.mark.parametrize('before,after,outcome', [
    ('18万元', '18.0万元', 'correct'),
    ('18 MW', '18.0 MW', 'incorrect'),
])
def test_T_keeps_quantity_spelling_and_B_equivalence_requires_typed_unit(tmp_path, before, after, outcome):
    source = '# Values\n\nRevenue: ' + before
    _, _, required = production(tmp_path, source)
    score = final(required, '# Values\n\nRevenue: ' + after)
    assert score['layers']['T']['score'] < 100
    assert score['layers']['B']['denominator'] == 1
    assert [o['outcome'] for o in score['outcomes'] if o['layer'] == 'B'] == [outcome]
    assert bool(required['business'][0]['qualifiers'].get('unit')) == (outcome == 'correct')


def test_table_and_markdown_syntax_keep_only_visible_text_without_loading_links(tmp_path):
    source = '# Disclosures\n\n| Name | Revenue |\n| --- | --- |\n| Orion | 18万元 |\n\nNote: Regional clients hold valid contracts.\n\n![Caption](unopened.png) and [Policy](unopened.pdf)'
    expected, graph, required = production(tmp_path, source)
    assert graph['source_obligation_inventory']['source_complete']
    words = [n['text'] for n in required['text']]
    assert words.count('Note') == 1 and 'Caption and Policy' in words
    assert not any('unopened' in word or '| ---' in word for word in words)
    score = final(required, source)
    assert all(o['outcome'] == 'correct' for o in score['outcomes'] if o['layer'] == 'T')
    assert len(expected['targets']) == 4


def test_unbound_table_note_qualifier_remains_rejected_instead_of_certifying_a_source(tmp_path):
    # Retain the independently discovered unsupported case. It is outside
    # the fixed two samples and supplies no accepted table/source capability.
    source = '# Disclosures\n\n| Name | Note |\n| --- | --- |\n| Orion | 18 MW |'
    with pytest.raises(ValueError, match='qualifier note None'):
        production(tmp_path, source)


def test_visible_label_in_a_partial_record_keeps_its_nonzero_source_offset(tmp_path):
    text = '# Disclosures\n\nName: Orion; Note: Regional clients hold valid contracts.'
    expected, graph, required = production(tmp_path, text)
    [label] = [n for n in required['text'] if n['text'] == 'Note']
    assert label['source']['text_span'] == [13, 17]
    assert expected['targets'][1]['raw_text'][13:17] == 'Note'
    assert graph['comparison_coverage']['responsibility_complete']
    assert all(o['outcome'] == 'correct' for o in final(required, text)['outcomes'])


@pytest.mark.parametrize('change', ['correct', 'softbreak', 'label_deleted', 'definition_deleted',
                                   'negation', 'explicitly_empty'])
def test_definition_note_and_typed_modal_statement_have_distinct_complete_responsibilities(tmp_path, change):
    _, graph, required = production(tmp_path, DEFINITIONS)
    assert graph['comparison_coverage']['responsibility_complete']
    changes = {'correct': DEFINITIONS,
               'softbreak': DEFINITIONS.replace('gigawatt hour', 'gigawatt\nhour'),
               'label_deleted': DEFINITIONS.replace('Note:', ''),
               'definition_deleted': DEFINITIONS.replace('; GWh = gigawatt hour.', '.'),
               'negation': DEFINITIONS.replace('can lead', 'cannot lead'),
               'explicitly_empty': ''}
    score = final(required, changes[change])
    assert {k: score['layers'][k]['denominator'] for k in ('B', 'L')} == {'B': 2, 'L': 4}
    if change in {'correct', 'softbreak'}:
        assert all(o['outcome'] == 'correct' for o in score['outcomes'])
    elif change == 'explicitly_empty':
        # The existing empty-candidate failure policy retains every fixed
        # denominator and emits final binary incorrect decisions.
        assert {o['outcome'] for o in score['outcomes'] if o['layer'] in {'B', 'L'}} == {'incorrect'}
        assert score['layers']['B']['numerator'] == score['layers']['L']['numerator'] == 0
    else:
        assert any(o['outcome'] == 'incorrect' for o in score['outcomes'] if o['layer'] == 'T')
        assert any(o['outcome'] != 'correct' for o in score['outcomes'] if o['layer'] in {'B', 'L'})


@pytest.mark.parametrize('tail', ['The board shall publish the notice.', 'Name: Vega'])
def test_equation_softwrap_never_absorbs_an_independent_assertion_or_field(tmp_path, tail):
    from moparse_eval.source_requirements import plan_mixed_source

    text = 'Name: Orion; Limit = 18\n' + tail
    plan = plan_mixed_source(text, {'path': '<invented>', 'lines': [3, 4]})
    assert plan is not None
    assert [p['text'] for p in plan['fragments']] == ['Name: Orion', 'Limit = 18', tail]
    original, graph, required = production(tmp_path, '# Boundaries\n\n' + text)
    validate_requirement_graph(graph, expected=original)
    score = final(required, '# Boundaries\n\n' + text)
    assert score['layers']['T']['score'] == 100
    if tail == 'Name: Vega':
        assert all(o['outcome'] == 'correct' for o in score['outcomes'])
    else:
        # The existing mixed scalar/modal document alignment cannot prove
        # this full-content correspondence. Preserve its specific unresolved
        # result and reject publication; the equation continuation fix must
        # never hide the independent modal statement inside a scalar value.
        assert not score['publishable']
        assert {o['outcome'] for o in score['outcomes'] if o['layer'] in {'B', 'L'}} == {'unresolved'}
        assert any(b['reason'] == 'document_block_identity_ambiguous' for b in score['blockers'])
