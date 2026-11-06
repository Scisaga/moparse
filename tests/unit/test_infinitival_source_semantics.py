"""Independent invented controller, purpose, discourse and nominal-PP oracles."""
from copy import deepcopy

import pytest

from moparse_eval.infinitival_syntax import validate_infinitival_sources
from moparse_eval.narrative_requirements import read_narrative
from moparse_eval.nominal_syntax import validate_nominal_sources

SOURCE = {'path': '<invented-infinitive>', 'lines': [9, 9]}


def read(text, offset=0):
    return read_narrative(text, {**SOURCE, 'text_span': [offset, offset + len(text)]})


def walk(node):
    if isinstance(node, dict):
        yield node
        for child in node.values():
            yield from walk(child)
    elif isinstance(node, list):
        for child in node:
            yield from walk(child)


def node_of(result, kind):
    return next(node for node in walk(result['logic']) if node.get('kind') == kind)


def validate(result, text, offset=0):
    def literal(origin, _label):
        if not isinstance(origin, dict) or origin.get('path') != SOURCE['path'] or origin.get('lines') != [9, 9]:
            raise ValueError('outside independent source identity')
        lo, hi = origin.get('text_span', [0, 0])
        if not offset <= lo <= hi <= offset + len(text):
            raise ValueError('outside independent source span')
        return text[lo - offset:hi - offset]
    graph = {'logic': result['logic']}
    validate_infinitival_sources(graph, {}, literal)
    validate_nominal_sources(graph, {}, literal)


@pytest.mark.parametrize('offset', [0, 41])
def test_subject_purpose_and_object_control_keep_different_explicit_actors(offset):
    text = 'Orion provides tools to help partners to use systems.'
    result = read(text, offset)
    assert result['complete'] and not result['unresolved']
    assert [(fact['subject'], fact['attribute'], fact['value']) for fact in result['facts']] == [('Orion', 'provide', 'tools')]
    assert {(fact['subject'], fact['attribute'], fact['value']) for fact in result['semantic_operands']} == {
        ('Orion', 'help', 'partners'), ('partners', 'use', 'systems')}
    purpose = node_of(result, 'purpose_scope')
    complement = node_of(result, 'controlled_infinitive_scope')
    assert (purpose['operator'], purpose['control']['kind'], purpose['control']['controller']) == ('purpose', 'subject_control', 'Orion')
    assert (complement['operator'], complement['control']['kind'], complement['control']['controller']) == ('complement', 'object_control', 'partners')
    assert all('tense' not in fact['qualifiers'] for fact in result['semantic_operands'])
    assert {fact['qualifiers']['assertion_context'] for fact in result['semantic_operands']} == {'purpose_operand', 'controlled_infinitive_operand'}
    validate(result, text, offset)


@pytest.mark.parametrize('marker,operator,role', [('For example', 'for_example', 'example'),
    ('For instance', 'for_instance', 'example'), ('However', 'however', 'contrast'),
    ('Moreover', 'moreover', 'addition'), ('In addition', 'in_addition', 'addition'),
    ('In particular', 'in_particular', 'focus')])
def test_discourse_marker_has_its_own_source_and_does_not_become_a_subject(marker, operator, role):
    text = marker + ', Orion is making investments in storage to capture market opportunities.'
    result = read(text)
    assert result['complete']
    assert [(fact['subject'], fact['attribute'], fact['value']) for fact in result['facts']] == [('Orion', 'make', 'investments in storage')]
    discourse = result['logic'][0]
    assert (discourse['kind'], discourse['operator'], discourse['role']) == ('discourse_scope', operator, role)
    assert result['facts'][0]['qualifiers']['aspect'] == 'progressive'
    [capture] = result['semantic_operands']
    assert (capture['subject'], capture['attribute'], capture['value']) == ('Orion', 'capture', 'market opportunities')
    nominal = node_of(result, 'proposition')['object_phrase']
    [pp] = nominal['prepositional_complements']
    assert (pp['preposition'], pp['attachment'], pp['semantic_role']) == ('in', {'kind': 'nominal', 'head': 'investments'}, 'complement')
    validate(result, text)


def test_enumerated_controller_and_deeper_purpose_coordination_keep_nearest_attachment():
    text = 'Orion provides tools to help merchants, retailers and other users to leverage the power of technology to engage with their customers and operate in an efficient way.'
    result = read(text)
    assert result['complete']
    assert [(fact['attribute'], fact['value']) for fact in result['facts']] == [('provide', 'tools')]
    controller = 'merchants, retailers and other users'
    downstream = [fact for fact in result['semantic_operands'] if fact['attribute'] in {'leverage', 'engage', 'operate'}]
    assert {fact['subject'] for fact in downstream} == {controller}
    assert {fact['attribute'] for fact in downstream} == {'leverage', 'engage', 'operate'}
    coordinated = next(node for node in walk(result['logic']) if node.get('kind') == 'coordination' and node.get('mode') == 'actions')
    assert [child['attribute'] for child in coordinated['children']] == ['engage', 'operate']
    engage, operate = coordinated['children']
    assert engage['object'] == operate['object'] == ''
    assert engage['prepositional_complements'][0]['semantic_role'] == 'complement'
    assert operate['prepositional_complements'][0]['semantic_role'] == 'manner'
    assert all(fact['qualifiers']['assertion_context'] in {'purpose_operand', 'controlled_infinitive_operand'} for fact in result['semantic_operands'])
    validate(result, text)


def test_ambiguous_investment_domain_is_not_split_into_two_main_actions():
    text = 'For example, Orion is making significant investments in quantum computing and machine learning infrastructure to capture market opportunities.'
    result = read(text)
    assert result['complete'] is False
    assert result['facts'] == []
    assert [(fact['subject'], fact['attribute'], fact['value']) for fact in result['semantic_operands']] == [('Orion', 'capture', 'market opportunities')]
    assert result['unresolved'][0]['text'] == 'quantum computing and machine learning infrastructure'
    assert result['unresolved'][0]['reason'] == 'narrative_nominal_coordination_unresolved'
    validate(result, text)


@pytest.mark.parametrize('text', ['Orion provides the right to review Report.',
    'Orion requires partners to provides systems.', 'Orion provides tools to capture new markets because conditions vary.'])
def test_unlicensed_nominal_attachment_or_infinitival_form_is_never_complete(text):
    result = read(text)
    assert result['complete'] is False and result['unresolved']
    assert result['text_atoms'][0]['text'] == text


@pytest.mark.parametrize('mutation', ['controller_text', 'controller_source', 'control_kind', 'operator_source', 'operand_subject', 'finite_tense', 'main_actor'])
def test_independent_infinitival_source_audit_rejects_controller_scope_and_relation_mutations(mutation):
    text = 'Orion provides tools to help partners to use systems.'
    result = read(text)
    validate(result, text)
    changed = deepcopy(result)
    purpose = node_of(changed, 'purpose_scope')
    complement = node_of(changed, 'controlled_infinitive_scope')
    if mutation == 'controller_text':
        complement['control']['controller'] = 'Orion'
    elif mutation == 'controller_source':
        complement['control']['controller_source'] = deepcopy(purpose['control']['controller_source'])
        complement['control']['controller'] = 'Orion'
    elif mutation == 'control_kind':
        complement['control']['kind'] = 'subject_control'
    elif mutation == 'operator_source':
        complement['operator_source']['text_span'] = list(complement['child']['predicate_source']['text_span'])
    elif mutation == 'operand_subject':
        complement['operand']['subject_source'] = deepcopy(purpose['control']['controller_source'])
        complement['operand']['subject'] = 'Orion'
    elif mutation == 'finite_tense':
        complement['operand']['tense'] = 'present'
    else:
        purpose['child']['subject_source'] = deepcopy(complement['control']['controller_source'])
        purpose['child']['subject'] = 'partners'
    with pytest.raises(ValueError, match='source|controller|infinitiv|purpose|tense'):
        validate(changed, text)


def test_unsupported_neighbor_does_not_erase_a_supported_purpose_sentence():
    text = 'Orion provides tools to help partners. Business circumstances evolve unpredictably.'
    result = read(text)
    assert not result['complete']
    assert [(fact['attribute'], fact['value']) for fact in result['facts']] == [('provide', 'tools')]
    assert result['unresolved'][0]['text'] == 'Business circumstances evolve unpredictably.'


def test_newly_supported_active_nominal_domain_preserves_the_old_literal_and_role_sources():
    text = 'Lumen is making investments in research.'
    result = read(text)
    assert result['complete'] and not result['unresolved']
    [fact] = result['facts']
    assert (fact['subject'], fact['attribute'], fact['value']) == ('Lumen', 'make', 'investments in research')
    assert fact['qualifiers'] == {'polarity': 'positive', 'tense': 'present', 'aspect': 'progressive'}
    [pp] = fact['object_phrase']['prepositional_complements']
    assert (pp['preposition'], pp['attachment'], pp['complement']['head']) == ('in', {'kind': 'nominal', 'head': 'investments'}, 'research')
    validate(result, text)
    changed = deepcopy(result)
    node_of(changed, 'prepositional_complement')['attachment']['kind'] = 'predicate'
    with pytest.raises(ValueError, match='attachment|owner'):
        validate(changed, text)


def source_graph(text):
    from moparse_eval.requirement_graph import compile_requirement_graph

    target = {'id': 'invented', 'kind': 'text', 'text': text, 'raw_text': text, 'raw': text,
        'reference': SOURCE, 'cells': [], 'parents': [], 'has_children': False, 'context': [],
        'selected_heading_context': [], 'outside_selection_context': [], 'pages': [1], 'heading_level': None}
    return compile_requirement_graph({'sample_id': 'invented-infinitive', 'document_id': 'invented',
        'source_pages': [1], 'standard': 'expected_only', 'targets': [target], 'scope': []})


@pytest.mark.parametrize('text', ['Lumen is making investments in research.',
    'Orion provides tools to help partners to use systems.',
    'For example, Orion is making investments in storage to capture market opportunities.'])
def test_new_nominal_domain_and_control_family_reach_complete_public_source_graph(text):
    from moparse_eval.requirement_graph import validate_requirement_graph

    graph = source_graph(text)
    validate_requirement_graph(graph)
    assert graph['semantic_complete']


def test_partial_main_cannot_substitute_another_licensed_predicate_for_its_source():
    text = 'For example, Orion is making investments in quantum computing and machine learning infrastructure to capture new opportunities.'
    result = read(text)
    assert not result['complete']
    validate(result, text)
    node_of(result, 'unknown')['known_roles']['attribute'] = 'provide'
    with pytest.raises(ValueError, match='predicate|source|attribute'):
        validate(result, text)
