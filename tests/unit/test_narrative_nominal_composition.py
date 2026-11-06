"""Independent A-J grammar oracles; invented text never changes reference data."""
from copy import deepcopy

import pytest

from moparse_eval.narrative_requirements import read_narrative
from moparse_eval.requirement_ast import compare_requirement_ast

SOURCE = {'path': '<independent-A-J>', 'lines': [17, 17]}
CASES = [
    ('A', 'Under our "user first, AI-driven" strategy, we have sharpened our business focus to two core businesses of e-commerce and cloud.',
     [('we', 'sharpen', 'our business focus')]),
    ('B', 'The company develops and operates cloud services.',
     [('The company', 'develop', 'cloud services'), ('The company', 'operate', 'cloud services')]),
    ('C', 'The company provides hardware and software.',
     [('The company', 'provide', 'hardware'), ('The company', 'provide', 'software')]),
    ('D', 'The company provides services for international customers.', [('The company', 'provide', 'services')]),
    ('E', 'Revenue increased in 2024.', [('Revenue', 'increase', '')]),
    ('F', 'The company may acquire the subsidiary if the board approves the transaction.', [('The company', 'acquire', 'the subsidiary')]),
    ('G', 'The company does not acquire or operate the subsidiary.',
     [('The company', 'logical_alternative', 'The company does not acquire or operate the subsidiary')]),
    ('H', 'The company owns A and B, but does not operate C.',
     [('The company', 'own', 'A'), ('The company', 'own', 'B'), ('The company', 'operate', 'C')]),
    ('I1', 'The company manages the assets of its subsidiaries and affiliates.',
     [('The company', 'manage', 'the assets of its subsidiaries and affiliates')]),
    ('I2', 'The company manages the assets of its subsidiaries and manages its affiliates.',
     [('The company', 'manage', 'the assets of its subsidiaries'), ('The company', 'manage', 'its affiliates')]),
    ('J', 'The company must maintain at least 80% capacity within the approved range.',
     [('The company', 'maintain', 'at least 80% capacity')]),
]


def read(text, offset=0):
    return read_narrative(text, {**SOURCE, 'text_span': [offset, offset + len(text)]})


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def first(value, kind):
    return next(node for node in nodes(value) if node.get('kind') == kind)


@pytest.mark.parametrize('case,text,facts', CASES, ids=[case[0] for case in CASES])
def test_independent_asserted_roles_and_composition_oracles(case, text, facts):
    result = read(text)
    assert result['complete'] is True and result['unresolved'] == []
    assert [(fact['subject'], fact['attribute'], fact['value']) for fact in result['facts']] == facts
    tree = result['logic'][0]
    if case == 'A':
        assert tree['kind'] == 'fronted_context'
        aspect = tree['child']
        assert (aspect['kind'], aspect['aspect'], aspect['tense']) == ('active_aspect', 'perfect', 'present')
        proposition = aspect['child']
        assert proposition['object_phrase']['head'] == 'focus'
        [direction] = proposition['prepositional_complements']
        assert (direction['preposition'], direction['semantic_role'], direction['attachment']['attribute']) == ('to', 'complement', 'sharpen')
        businesses = direction['complement']
        assert businesses['quantifier']['value'] == '2'
        assert businesses['head'] == 'businesses'
        [membership] = businesses['prepositional_complements']
        assert membership['attachment'] == {'kind': 'nominal', 'head': 'businesses'}
        assert membership['preposition'] == 'of'
        members = membership['complement']['coordination']
        assert (members['operator'], members['mode']) == ('and', 'nominal_members')
        assert [member['head'] for member in members['children']] == ['e-commerce', 'cloud']
    elif case in {'B', 'C'}:
        assert (tree['kind'], tree['operator'], tree['mode']) == ('coordination', 'and', 'actions' if case == 'B' else 'objects')
    elif case == 'D':
        [pp] = tree['prepositional_complements']
        assert (pp['preposition'], pp['semantic_role'], pp['attachment']['kind']) == ('for', 'beneficiary', 'predicate')
        assert pp['complement']['head'] == 'customers'
        assert pp['complement']['modifiers'] == ['international']
    elif case == 'E':
        assert tree['object_phrase'] is None
        [pp] = tree['prepositional_complements']
        assert (pp['semantic_role'], pp['complement']['head']) == ('temporal_scope', '2024')
        assert pp['complement']['quantifier'] is None
    elif case == 'F':
        assert tree['kind'] == 'conditions'
        assert tree['child']['kind'] == 'modality' and tree['child']['operator'] == 'may'
        [condition] = tree['bindings']
        assert condition['operator'] == 'if'
        assert (condition['operand']['subject'], condition['operand']['attribute'], condition['operand']['object']) == ('the board', 'approve', 'the transaction')
        assert [operand['qualifiers']['assertion_context'] for operand in result['semantic_operands']] == ['condition_operand']
    elif case == 'G':
        assert tree['kind'] == 'negation'
        assert (tree['child']['kind'], tree['child']['operator'], tree['child']['mode']) == ('coordination', 'or', 'actions')
        assert all(operand['qualifiers']['polarity'] == 'negative' for operand in result['semantic_operands'])
        assert result['facts'][0]['qualifiers']['polarity'] == 'negative'
    elif case == 'H':
        assert (tree['kind'], tree['operator'], tree['mode']) == ('coordination', 'but', 'contrast')
        left, right = tree['children']
        assert (left['operator'], left['mode']) == ('and', 'objects')
        assert right['kind'] == 'negation' and right['child']['attribute'] == 'operate'
        assert [fact['qualifiers']['polarity'] for fact in result['facts']] == ['positive', 'positive', 'negative']
    elif case == 'I1':
        assert tree['kind'] == 'proposition'
        [pp] = tree['object_phrase']['prepositional_complements']
        assert pp['attachment'] == {'kind': 'nominal', 'head': 'assets'}
        assert [member['head'] for member in pp['complement']['coordination']['children']] == ['subsidiaries', 'affiliates']
    elif case == 'I2':
        assert (tree['kind'], tree['operator'], tree['mode']) == ('coordination', 'and', 'actions')
        assert tree['children'][1]['object_phrase']['head'] == 'affiliates'
    elif case == 'J':
        assert tree['kind'] == 'modality' and tree['operator'] == 'must'
        prop = tree['child']
        quantity = prop['object_phrase']['quantifier']
        assert (quantity['operator'], quantity['value'], quantity['unit']) == ('ge', '80', '%')
        [pp] = prop['prepositional_complements']
        assert (pp['preposition'], pp['semantic_role'], pp['complement']['head']) == ('within', 'restriction', 'range')


@pytest.mark.parametrize('case,text,_facts', CASES, ids=[case[0] for case in CASES])
@pytest.mark.parametrize('offset', [0, 83])
def test_every_a_j_role_and_nominal_node_retains_actual_source_spans(case, text, _facts, offset):
    result = read(text, offset)
    assert result['complete']
    for node in nodes(result['logic']):
        if node.get('kind') in {'noun_phrase', 'prepositional_complement', 'quantity_comparison', 'proposition'}:
            assert node['source']['path'] == SOURCE['path']
            lo, hi = node['source']['text_span']
            assert offset <= lo <= hi <= offset + len(text)
        for key in ('head', 'subject', 'predicate', 'object', 'preposition', 'determiner'):
            if node.get(key) is not None and key + '_source' in node:
                a, b = node[key + '_source']['text_span']
                assert text[a - offset:b - offset] == node[key]


@pytest.mark.parametrize('case,text,_facts', CASES, ids=[case[0] for case in CASES])
@pytest.mark.parametrize('mutation', ['node_deletion', 'relation_deletion', 'scope_change', 'subject_change'])
def test_a_j_independently_established_oracles_reject_ast_mutations(case, text, _facts, mutation):
    required = read(text)['logic'][0]
    actual = deepcopy(required)
    leaf = first(actual, 'proposition')
    if mutation == 'node_deletion':
        del leaf['object_phrase']
    elif mutation == 'relation_deletion':
        # Grammatical roles themselves are required relationships, even when
        # an example has no PP or condition operator.
        del leaf['subject']
    elif mutation == 'scope_change':
        leaf['scope'] = ['A different heading']
    else:
        leaf['subject'] = 'A different owner'
    decision = compare_requirement_ast(required, actual)
    assert decision['equivalent'] is False
    assert decision['status'] in {'conflict', 'missing'}


@pytest.mark.parametrize('case,text,_facts', CASES, ids=[case[0] for case in CASES])
def test_a_j_close_opposite_wording_is_not_semantically_equivalent(case, text, _facts):
    if case == 'A':
        changed = text.replace('and cloud', 'or cloud')
    elif case == 'B':
        changed = text.replace('develops and', 'develops or')
    elif case == 'C':
        changed = text.replace('hardware and software', 'hardware or software')
    elif case == 'D':
        changed = text.replace('international customers', 'domestic customers')
    elif case == 'E':
        changed = text.replace('2024', '2025')
    elif case == 'F':
        changed = text.replace('may acquire', 'must acquire')
    elif case == 'G':
        changed = text.replace('does not acquire or', 'acquires or')
    elif case == 'H':
        changed = text.replace('does not operate', 'does operate')
    elif case == 'I1':
        changed = text.replace('and affiliates', 'and manages its affiliates')
    elif case == 'I2':
        changed = text.replace('and manages its affiliates', 'and affiliates')
    else:
        changed = text.replace('at least 80%', 'at most 80%')
    expected, candidate = read(text), read(changed)
    assert expected['complete'] and candidate['complete']
    forward = compare_requirement_ast(expected['logic'][0], candidate['logic'][0])
    backward = compare_requirement_ast(candidate['logic'][0], expected['logic'][0])
    assert not forward['equivalent'] and not backward['equivalent']


@pytest.mark.parametrize('text', [
    'The company manages assets with a telescope.',
    'The company provides services in the new framework.',
    'The company manages assets of subsidiaries and affiliates or partners.',
])
def test_ambiguous_attachment_or_mixed_nominal_logic_is_retained_pending(text):
    result = read(text)
    assert result['complete'] is False and result['unresolved']
    assert result['text_atoms'][0]['text'] == text


def test_one_unknown_sentence_keeps_the_correct_prepositional_neighbor():
    text = 'The company provides services for customers. Business circumstances evolve unpredictably.'
    result = read(text)
    assert result['complete'] is False
    assert [(fact['attribute'], fact['value']) for fact in result['facts']] == [('provide', 'services')]
    assert result['unresolved'][0]['text'] == 'Business circumstances evolve unpredictably.'


def source_graph(raw):
    from moparse_eval.requirement_graph import compile_requirement_graph

    target = {'id': 'printed:17', 'kind': 'text', 'text': raw, 'raw_text': raw, 'raw': raw,
              'reference': SOURCE, 'cells': [], 'parents': [], 'has_children': False, 'context': [],
              'selected_heading_context': [], 'outside_selection_context': [], 'pages': [1], 'heading_level': None}
    return compile_requirement_graph({'sample_id': 'independent-A-J', 'document_id': 'invented-document',
        'source_pages': [1], 'standard': 'expected_only', 'targets': [target], 'scope': []})


@pytest.mark.parametrize('mutation', ['head', 'modifier', 'modifier_source', 'determiner', 'attachment', 'complement_source', 'preposition_source'])
def test_nominal_and_prepositional_source_audit_rejects_local_mutation(mutation):
    from moparse_eval.requirement_graph import validate_requirement_graph

    text = 'The company provides services for international customers.'
    graph = source_graph(text)
    validate_requirement_graph(graph)
    prop = first(graph['logic'], 'proposition')
    pp = prop['prepositional_complements'][0]
    if mutation == 'head':
        prop['object_phrase']['head'] = 'products'
    elif mutation == 'modifier':
        pp['complement']['modifiers'] = ['domestic']
    elif mutation == 'modifier_source':
        pp['complement']['modifier_sources'][0]['text_span'] = list(pp['complement']['head_source']['text_span'])
    elif mutation == 'determiner':
        prop['subject_phrase']['determiner'] = 'Another'
    elif mutation == 'attachment':
        pp['attachment'] = {'kind': 'nominal', 'head': 'services'}
    elif mutation == 'complement_source':
        pp['complement_source']['text_span'] = list(prop['subject_source']['text_span'])
    else:
        pp['preposition_source']['text_span'] = list(prop['predicate_source']['text_span'])
    with pytest.raises(ValueError, match='source|nominal|attachment|semantic'):
        validate_requirement_graph(graph)


@pytest.mark.parametrize('mutation', ['operator', 'value', 'unit', 'value_source'])
def test_quantity_boundaries_have_independent_original_source_audit(mutation):
    from moparse_eval.requirement_graph import validate_requirement_graph

    graph = source_graph('The company must maintain at least 80% capacity within the approved range.')
    validate_requirement_graph(graph)
    quantifier = first(graph['logic'], 'quantity_comparison')
    if mutation == 'operator':
        quantifier['operator'] = 'le'
    elif mutation == 'value':
        quantifier['value'] = '81'
    elif mutation == 'unit':
        quantifier['unit'] = 'count'
    else:
        quantifier['value_source']['text_span'] = list(quantifier['operator_source']['text_span'])
    with pytest.raises(ValueError, match='source|quantity|semantic|comparison'):
        validate_requirement_graph(graph)


def test_chinese_and_english_propositions_share_the_same_nominal_node_schema():
    from moparse_eval.cjk_narrative_requirements import read_cjk_narrative

    english = read('Lumen provides services.')
    chinese = read_cjk_narrative('甲公司提供服务。', SOURCE)
    assert english['complete'] and chinese['complete']
    for result in [english, chinese]:
        prop = first(result['logic'], 'proposition')
        for key in ['subject_phrase', 'object_phrase']:
            assert prop[key]['kind'] == 'noun_phrase'
            assert {'head', 'determiner', 'quantifier', 'modifiers', 'prepositional_complements', 'coordination', 'source'} <= set(prop[key])
        assert prop['scope'] == []


def test_subject_coordination_owns_a_single_shared_predicate_without_inferred_actors():
    text = 'The company and the subsidiary provide hardware.'
    result = read(text)
    assert result['complete']
    [prop] = result['logic']
    [fact] = result['facts']
    assert fact['subject'] == 'The company and the subsidiary'
    assert prop['kind'] == 'proposition' and prop['attribute'] == 'provide'
    coordination = prop['subject_phrase']['coordination']
    assert (coordination['operator'], coordination['mode']) == ('and', 'nominal_members')
    assert [member['head'] for member in coordination['children']] == ['company', 'subsidiary']
    assert any(edge['type'] == 'narrative_nominal_coordination_scope' for edge in result['relations'])


def test_shared_nominal_of_attachment_remains_pending_without_disambiguating_evidence():
    result = read('The development and use of technologies are complex.')
    assert result['complete'] is False
    assert result['unresolved'][0]['reason'] == 'narrative_nominal_shared_complement_attachment_unresolved'


def test_nested_object_and_does_not_erase_outer_contrast_relationships():
    result = read('The company owns A and B, but does not operate C.')
    assert result['complete']
    for fact in result['facts']:
        own_edges = [edge for edge in result['relations'] if edge.get('fact_id') == fact['id']]
        assert any(edge['type'] == 'narrative_coordination_scope' and edge['left']['operator'] == 'but'
                   for edge in own_edges)
    owners = result['facts'][:2]
    for fact in owners:
        own_edges = [edge for edge in result['relations'] if edge.get('fact_id') == fact['id']]
        assert any(edge['type'] == 'narrative_coordination_scope' and edge['left']['operator'] == 'and'
                   for edge in own_edges)


@pytest.mark.parametrize('deletion', ['modifier', 'quantifier', 'preposition'])
def test_synchronized_constituent_and_provenance_deletion_cannot_hide_uninterpreted_nominal_text(deletion):
    from moparse_eval.requirement_graph import validate_requirement_graph

    text = ('The company provides international services.' if deletion == 'modifier' else
            'The company maintains two core businesses.' if deletion == 'quantifier' else
            'The company manages the assets of its subsidiaries.')
    graph = source_graph(text)
    validate_requirement_graph(graph)
    phrase = first(graph['logic'], 'proposition')['object_phrase']
    if deletion == 'modifier':
        phrase['modifiers'] = []
        phrase['modifier_sources'] = []
    elif deletion == 'quantifier':
        phrase['quantifier'] = None
    else:
        phrase['prepositional_complements'] = []
    with pytest.raises(ValueError, match='nominal|source|constituent'):
        validate_requirement_graph(graph)


def test_shared_subject_and_clause_cannot_be_misread_as_a_third_ownership_object():
    text = 'The company owns A and B, and does not operate C.'
    result = read(text)
    assert result['complete']
    assert [(fact['attribute'], fact['value'], fact['qualifiers']['polarity']) for fact in result['facts']] == [
        ('own', 'A', 'positive'), ('own', 'B', 'positive'), ('operate', 'C', 'negative')]
    [tree] = result['logic']
    assert (tree['kind'], tree['operator'], tree['mode']) == ('coordination', 'and', 'clauses')
    assert tree['children'][1]['kind'] == 'negation'
    assert tree['children'][1]['child']['subject'] == 'The company'
    assert tree['children'][1]['child']['subject_source']['text_span'] == [0, 11]
    opposite = read('The company owns A and B, but does not operate C.')
    assert compare_requirement_ast(tree, opposite['logic'][0])['status'] == 'conflict'


def test_shared_subject_clause_cannot_inherit_two_different_explicit_actors():
    result = read('Alpha owns A and Beta owns B, and does not operate C.')
    assert not result['complete']
    assert result['unresolved'][0]['reason'] == 'narrative_shared_subject_coordination_unresolved'


@pytest.mark.parametrize('case,text,_facts', CASES, ids=[case[0] for case in CASES])
def test_each_a_j_source_audit_requires_the_real_relation_edges(case, text, _facts):
    from moparse_eval.source_obligations import audit_source_obligations

    graph = source_graph(text)
    assert graph['semantic_complete']
    required_type = {
        'A': 'narrative_prepositional_attachment', 'B': 'narrative_coordination_scope',
        'C': 'narrative_coordination_scope', 'D': 'narrative_prepositional_attachment',
        'E': 'narrative_prepositional_attachment', 'F': 'narrative_condition_scope',
        'G': 'narrative_alternative_scope', 'H': 'narrative_coordination_scope',
        'I1': 'narrative_nominal_coordination_scope', 'I2': 'narrative_coordination_scope',
        'J': 'narrative_quantity_scope',
    }[case]
    relation_types = {required_type}
    if required_type == 'narrative_coordination_scope':
        relation_types.add('proposition_coordination_scope')
    removed = {edge['id'] for edge in graph['relations'] if edge['type'] in relation_types}
    assert removed
    graph['relations'] = [edge for edge in graph['relations'] if edge['id'] not in removed]
    graph['projections']['L'] = [ident for ident in graph['projections']['L'] if ident not in removed]
    changed = audit_source_obligations(graph['source_obligation_inventory'], graph)
    explained = {row['obligation_id'] for row in graph['source_obligation_coverage']['dispositions'] if row['status'] == 'explained'}
    assert any(row['status'] == 'pending' and row['obligation_id'] in explained for row in changed['dispositions'])


@pytest.mark.parametrize('modifier', ['12-year', 'three-year', '80%-capacity'])
def test_numeric_hyphenated_modifier_is_not_a_partial_count_quantifier(modifier):
    from moparse_eval.requirement_graph import validate_requirement_graph

    text = 'The ' + modifier + ' average investment yield increased in 2031.'
    result = read(text)
    assert result['complete']
    phrase = result['logic'][0]['subject_phrase']
    assert phrase['quantifier'] is None
    assert phrase['modifiers'][0] == modifier
    offset = text.index(modifier)
    assert phrase['modifier_sources'][0]['text_span'] == [offset, offset + len(modifier)]
    graph = source_graph(text)
    validate_requirement_graph(graph)
    changed = deepcopy(graph)
    changed_phrase = first(changed['logic'], 'proposition')['subject_phrase']
    changed_phrase['modifiers'] = changed_phrase['modifiers'][1:]
    changed_phrase['modifier_sources'] = changed_phrase['modifier_sources'][1:]
    with pytest.raises(ValueError, match='nominal|source|constituent'):
        validate_requirement_graph(changed)


@pytest.mark.parametrize('marker', ['⁴', '⁹'])
def test_unread_superscript_source_token_stays_pending_and_does_not_enter_a_false_subject(marker):
    from moparse_eval.requirement_graph import validate_requirement_graph

    text = marker + ' This approach provides services. Orion owns records.'
    result = read(text)
    assert not result['complete']
    assert [(fact['subject'], fact['attribute'], fact['value']) for fact in result['facts']] == [('Orion', 'own', 'records')]
    assert result['unresolved'][0]['reason'] == 'narrative_nominal_token_boundary_unresolved'
    assert marker in result['unresolved'][0]['text']
    graph = source_graph(text)
    validate_requirement_graph(graph)
    assert not graph['semantic_complete']
