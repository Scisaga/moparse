"""Fixed qualifier tokens must survive reader and graph copying unchanged."""

from copy import deepcopy

import pytest

from moparse_eval.proposition_requirements import read_propositions
from moparse_eval.prose_requirements import read_prose_requirements
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.series_requirements import read_series_requirements

PATH = '<invented-qualifier-source>'


def declaration(text, *, agenda=False):
    targets = []
    if agenda:
        targets.append({'id': 'agenda', 'kind': 'item', 'text': 'Agenda:', 'raw_text': 'Agenda:', 'raw': '- Agenda:',
            'reference': {'path': PATH, 'lines': [1, 1]}, 'cells': [], 'parents': [], 'has_children': True,
            'context': [], 'selected_heading_context': [], 'outside_selection_context': [], 'pages': [1], 'heading_level': None})
    line = 2 if agenda else 1
    targets.append({'id': 'body', 'kind': 'item' if agenda else 'text', 'text': text, 'raw_text': text, 'raw': text,
        'reference': {'path': PATH, 'lines': [line, line]}, 'cells': [], 'parents': ['Agenda:'] if agenda else [],
        'has_children': False, 'context': [], 'selected_heading_context': [], 'outside_selection_context': [],
        'pages': [1], 'heading_level': None})
    return {'sample_id': 'invented-qualifier-source', 'document_id': 'invented-document', 'source_pages': [1],
        'standard': 'expected_only', 'targets': targets,
        'scope': [{'lines': [1, line], 'pages': [1], 'declared_source_pages': [1], 'outside_source_pages': []}]}


@pytest.mark.parametrize('text,span,literal', [
    ('Lumen does not own Kappa.', [11, 14], 'not'),
    ('甲公司将不持有乙公司股权。', [4, 5], '不'),
])
def test_proposition_negation_has_its_own_original_token_even_with_an_auxiliary(text, span, literal):
    source = {'path': PATH, 'lines': [3, 3], 'text_span': [19, 19 + len(text)]}
    before = deepcopy(source)
    result = read_propositions(text, source)
    [fact] = result['facts']
    assert fact['qualifiers']['polarity'] == 'negative'
    assert fact['qualifier_sources']['polarity'] == {**source, 'text_span': [19 + span[0], 19 + span[1]]}
    assert text[slice(*span)] == literal
    assert source == before


@pytest.mark.parametrize('mutation', [None, 'span', 'text', 'source'])
def test_joined_scalar_uses_its_own_original_fragment_coordinates(mutation):
    from moparse_eval.cjk_measurement_requirements import read_cjk_measurements
    from moparse_eval.scalar_evidence import validate_scalar_sources
    from moparse_eval.three_layer import canonical

    first, second = '資產為人民幣', '17億元，比上年末增加人民幣9億元。'
    a, b = {'path': PATH, 'lines': [1, 1], 'text_span': [3, 3 + len(first)]}, {'path': PATH, 'lines': [2, 2]}
    text = first + ' ' + second
    source = {**a, 'text_span': [3, 3 + len(text)], 'joined_fragments': [
        {'source': a, 'text': first, 'joined_span': [0, len(first)]},
        {'source': b, 'text': second, 'joined_span': [len(first) + 1, len(text)]}]}
    reading = read_cjk_measurements(text, source)
    assert [fact['value'] for fact in reading['facts']] == ['17', '9']
    for fact in reading['facts']:
        fact['raw_value'] = fact['value']
        fact['source'] = deepcopy(fact['value_source'])
    projection = {'source_fragments': [{'source': {'path': PATH, 'lines': [1, 1]}, 'text': '前文。' + first},
                                       {'source': b, 'text': second}]}
    if mutation:
        fact = reading['facts'][0]
        fragment = fact['value_source']['joined_fragments'][1]
        if mutation == 'span':
            fragment['joined_span'][0] += 1
        elif mutation == 'text':
            fragment['text'] = second.replace('17', '18')
        else:
            fragment['source']['lines'] = [3, 3]
        with pytest.raises(ValueError):
            validate_scalar_sources(reading['facts'], projection, canonicalize=canonical)
    else:
        validate_scalar_sources(reading['facts'], projection, canonicalize=canonical)


def test_agenda_condition_operator_and_operand_have_separate_sources():
    text = 'Plan, if approved.'
    source = {'path': PATH, 'lines': [3, 3], 'text_span': [19, 19 + len(text)]}
    [fact] = read_prose_requirements(text, source, parents=['Agenda:'])['facts']
    assert fact['qualifiers']['condition_operator'] == 'if'
    assert fact['qualifier_sources']['condition_operator']['text_span'] == [25, 27]
    assert fact['qualifier_sources']['condition']['text_span'] == [28, 36]
    assert text[6:8] == 'if' and text[9:17] == 'approved'


@pytest.mark.parametrize('label,basis', [('本年比上年增减', '本年比上年'), ('本年比上年增減', '本年比上年'),
                                       ('較上年同期增減', '較上年同期'), ('较上年同期增减', '较上年同期')])
def test_series_relative_basis_is_a_real_label_subrange_without_guessed_periods(label, basis):
    text = f'Revenue：2028年17万元；2027年11万元；{label}4.3%。'
    source = {'path': PATH, 'lines': [3, 3], 'text_span': [19, 19 + len(text)]}
    result = read_series_requirements(text, source)
    fact = result['facts'][-1]
    assert fact['qualifiers']['comparison_basis'] == basis
    expected_start = text.index(label)
    assert fact['qualifier_sources']['comparison_basis']['text_span'] == [19 + expected_start, 19 + expected_start + len(basis)]
    assert fact['source']['qualifier_sources']['comparison_basis'] == fact['qualifier_sources']['comparison_basis']
    assert 'from_period' not in fact['qualifiers'] and 'to_period' not in fact['qualifiers']
    assert any(item['reason'] == 'series_comparison_periods_unresolved' for item in result['blockers'])


@pytest.mark.parametrize('kind', ['negative', 'agenda', 'comparison'])
def test_public_graph_guard_rejects_removed_or_rebound_qualifier_proofs(kind):
    text = {'negative': 'Lumen does not guarantee revenue.', 'agenda': 'Plan, if approved.',
            'comparison': 'Revenue：2028年17万元；2027年11万元；本年比上年增减4.3%。'}[kind]
    graph = compile_requirement_graph(declaration(text, agenda=kind == 'agenda'))
    validate_requirement_graph(graph)
    facts = [node for node in graph['nodes'] if node['id'] in graph['projections']['B']]
    key = {'negative': 'polarity', 'agenda': 'condition_operator', 'comparison': 'comparison_basis'}[kind]
    fact = next(item for item in facts if item.get('qualifiers', {}).get(key) in {'negative', 'if', '本年比上年'})
    if kind == 'negative':
        del fact['qualifier_sources'][key]
    else:
        fact['qualifier_sources'][key]['text_span'] = [0, 4]
    with pytest.raises(ValueError, match='source|literal|operator|qualifier'):
        validate_requirement_graph(graph)
