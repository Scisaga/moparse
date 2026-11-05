"""Independent reference oracles through the public expected/native entrypoints."""

from collections import Counter
from copy import deepcopy

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.saved_native import read_saved_native
from moparse_eval.three_layer import compile_expected, grade_layers, read_candidate

PATH = '<reference-contract>'
SAMPLE = 'invented-reference-contract'


def expected(*lines, heading=None):
    targets = []
    context = [{'text': heading, 'source': {'path': PATH, 'lines': [1, 1]}}] if heading else []
    for number, text in enumerate(([heading] if heading else []) + list(lines), 1):
        is_heading = bool(heading and number == 1)
        targets.append({'id': f'source:{number}', 'kind': 'heading' if is_heading else 'text',
                        'text': text, 'raw_text': text, 'raw': text,
                        'reference': {'path': PATH, 'lines': [number, number]}, 'cells': [], 'parents': [],
                        'has_children': False, 'context': [heading] if heading else [],
                        'selected_heading_context': context, 'outside_selection_context': [],
                        'pages': [1], 'heading_level': 1 if is_heading else None})
    return {'sample_id': SAMPLE, 'document_id': 'invented-document', 'source_pages': [1],
            'standard': 'expected_only', 'scope': [{'lines': [1, len(targets)], 'pages': [1],
                'declared_source_pages': [1], 'outside_source_pages': []}], 'targets': targets}


def bindings(graph):
    return [(edge['left']['owner'], edge['right']) for edge in graph['relations']
            if edge['type'] == 'explicit_reference_target']


@pytest.mark.parametrize('directive,target', [
    ('See also “Operations — Rivalry.”', {'role': 'reference_target', 'kind': 'quoted_title', 'title': 'Operations — Rivalry.'}),
    ('参见《港口运行规则》。', {'role': 'reference_target', 'kind': 'quoted_title', 'title': '港口运行规则'}),
    ('See Note 03 for more information.', {'role': 'reference_target', 'kind': 'numbered_reference', 'reference_kind': 'note', 'identifier': '03'}),
])
def test_complete_navigation_has_no_business_vote_and_keeps_actual_heading_owner(directive, target):
    declaration = expected(directive, heading='North')
    before = deepcopy(declaration)
    graph = compile_requirement_graph(declaration)
    assert graph['complete'] and graph['semantic_complete']
    assert graph['projections']['B'] == []
    [(owner, actual_target)] = bindings(graph)
    assert owner == {'identity': {'role': 'heading_scope'}, 'scope': ['North']}
    assert actual_target == target
    [reference] = graph['explicit_references']
    [proof] = reference['owner_proof']['evidence']
    assert proof['text'] == 'North' and proof['source']['lines'] == [1, 1]
    assert reference['directive_source']['lines'] == [2, 2]
    assert 'explicit_reference_binding' in graph['required_matcher_features']
    validate_requirement_graph(graph, expected=declaration)
    assert declaration == before
    required = compile_expected(declaration)
    observation = markdown_observation('# North\n\n' + directive, sample_id=SAMPLE, pipeline='test', pages=[1])
    candidate = read_candidate(observation)
    result = grade_layers(required, candidate)
    assert result['layers']['T']['score'] == 100
    assert result['layers']['B']['denominator'] == 0
    assert result['layers']['L']['score'] is None and not result['publishable']
    assert any('explicit_reference_binding' in issue.get('required_features', []) for issue in result['blockers'])


def test_ownerless_navigation_has_positive_nonbusiness_disposition_but_pending_relation_scope():
    graph = compile_requirement_graph(expected('See Note 3.'))
    assert graph['projections']['B'] == []
    assert not graph['semantic_complete']
    assert any(issue['reason'] == 'reference_owner_scope_unproven' and issue['layers'] == ['L']
               for issue in graph['unresolved'])
    assert not any('B' in issue['layers'] for issue in graph['unresolved'])
    assert all(row['layers']['B']['status'] == 'not_applicable' for row in graph['dispositions'])
    assert graph['explicit_references'][0]['owner_proof'] is None


def test_field_owners_are_independent_of_swapped_reference_numbers():
    first = compile_expected(expected('Revenue: See Note 3.', 'Cost: See Note 4.', heading='North'))
    actual = read_candidate(markdown_observation('# North\n\nRevenue: See Note 4.\n\nCost: See Note 3.',
        sample_id=SAMPLE, pipeline='test', pages=[1]))
    assert first['business'] == actual['business'] == []
    def numbered(graph):
        return [(owner['identity']['attribute'], target['identifier']) for owner, target in bindings(graph)]
    assert numbered(first) == [('Revenue', '3'), ('Cost', '4')]
    assert numbered(actual) == [('Revenue', '4'), ('Cost', '3')]
    assert Counter(''.join(item['text'] for item in first['text'])) == Counter(''.join(item['text'] for item in actual['text']))
    result = grade_layers(first, actual)
    assert result['layers']['L']['score'] is None and not result['layers']['L']['complete']
    assert not result['publishable']


def test_unknown_neighbor_cannot_be_declared_navigation_nonbusiness():
    graph = compile_requirement_graph(expected('See Note 3. Business conditions evolve unpredictably.', heading='North'))
    assert not graph['semantic_complete']
    assert any('Business conditions' in issue['text'] and 'B' in issue['layers'] for issue in graph['unresolved'])
    assert any(row['layers']['B']['status'] == 'unresolved' for row in graph['dispositions'])


def test_a_scope_label_without_an_actual_heading_cannot_own_a_reference():
    declaration = expected('See Note 3.')
    declaration['targets'][0]['context'] = ['North']
    declaration['targets'][0]['selected_heading_context'] = [
        {'text': 'North', 'source': {'path': PATH, 'lines': [99, 99]}}]
    graph = compile_requirement_graph(declaration)
    assert graph['explicit_references'][0]['owner_proof'] is None
    assert not graph['semantic_complete']
    assert any(item['reason'] == 'reference_owner_scope_unproven' for item in graph['unresolved'])


def test_a_known_reference_prefix_cannot_hide_an_uninterpreted_field_tail():
    graph = compile_requirement_graph(expected('Revenue: See Note 3 about future planning.', heading='North'))
    assert not graph['semantic_complete']
    assert graph['projections']['B'] == []
    assert any('B' in item['layers'] and 'future planning' in item['text'] for item in graph['unresolved'])


def test_reference_role_metadata_is_frozen_by_the_public_graph_guard():
    declaration = expected('See Note 3.', heading='North')
    graph = compile_requirement_graph(declaration)
    graph['reference_roles'][0]['text'] = 'Invented directive'
    with pytest.raises(ValueError, match='reference_roles'):
        validate_requirement_graph(graph, expected=declaration)


def test_docling_reference_text_uses_its_own_native_heading_source():
    texts = [{'self_ref': '#/texts/0', 'label': 'section_header', 'text': 'North', 'level': 1,
              'parent': {'$ref': '#/body'}, 'prov': [{'page_no': 1}]},
             {'self_ref': '#/texts/1', 'label': 'text', 'text': 'See Clause 2.4(a).',
              'parent': {'$ref': '#/texts/0'}, 'prov': [{'page_no': 1}]}]
    document = {'body': {'self_ref': '#/body', 'children': [{'$ref': '#/texts/0'}, {'$ref': '#/texts/1'}]},
                'texts': texts, 'tables': [], 'pictures': [], 'pages': {'1': {'size': {'width': 100, 'height': 100}}}}
    native = {'documents': [{'document': document}], 'pages': [{'page': 1, 'branch': 'docling',
                                                               'raw': {'native_document': '#/documents/0'}}]}
    observation = {'sample_id': SAMPLE, 'pipeline': 'invented-docling', 'status': 'completed',
                   'pages': [{'page': 1, 'blocks': []}], 'relations': []}
    before = deepcopy(native)
    observation = read_saved_native(native, observation)
    graph = read_candidate(observation)
    assert graph['business'] == []
    [reference] = graph['explicit_references']
    assert reference['target']['identifier'] == '2.4(a)'
    assert reference['directive_source']['path'] == '#/documents/0/document/texts/1'
    assert reference['owner_proof']['evidence'][0]['source']['path'] == '#/documents/0/document/texts/0'
    assert native == before
