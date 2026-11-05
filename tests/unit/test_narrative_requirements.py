"""Hand-written source semantics; no corpus, candidate answers or inference."""

from copy import deepcopy

import pytest

from moparse_eval.narrative_requirements import read_narrative

SOURCE = {"path": "<invented-narrative>", "lines": [11, 11]}


def tuples(result):
    return [(fact['subject'], fact['attribute'], fact['value']) for fact in result['facts']]


def read(text, **kwargs):
    return read_narrative(text, SOURCE, **kwargs)


def test_copula_entity_description_and_enumeration_are_atomic_not_a_paragraph_field():
    text = 'Lumen is a supplier. Lumen includes Alpha, Beta and Gamma.'
    result = read(text, scope=['Profile'])
    assert result['complete'] is True
    assert tuples(result) == [('Lumen', 'be', 'a supplier'), ('Lumen', 'include', 'Alpha'),
                              ('Lumen', 'include', 'Beta'), ('Lumen', 'include', 'Gamma')]
    assert result['facts'][0]['role'] == 'entity_description'
    assert all(fact['scope'] == ['Profile'] for fact in result['facts'])
    assert all(fact['value'] != text for fact in result['facts'])
    assert len(result['logic']) == 2


def test_ability_and_coordinated_actions_do_not_assert_that_actions_happened():
    result = read('Lumen is able to store records and retrieve records.')
    assert result['complete'] is True
    assert tuples(result) == [('Lumen', 'store', 'records'), ('Lumen', 'retrieve', 'records')]
    assert all(fact['qualifiers']['modality'] == 'ability' for fact in result['facts'])
    assert all(fact['logic']['assertion_context'] == 'ability' for fact in result['facts'])
    assert any(edge['type'] == 'narrative_modality_scope' for edge in result['relations'])


def test_inability_negates_the_ability_operator_not_an_alleged_action():
    text = 'Lumen is not able to store records.'
    result = read(text)
    assert result['complete'] is True
    [tree] = result['logic']
    assert (tree['kind'], tree['operator'], tree['polarity']) == ('modality', 'ability', 'negative')
    assert tree['child']['kind'] == 'proposition'
    [fact] = result['facts']
    assert fact['qualifiers'] == {'modality': 'ability', 'modal_polarity': 'negative', 'polarity': 'positive', 'tense': 'present'}
    a, b = fact['qualifier_sources']['modal_polarity']['text_span']
    assert text[a:b] == 'not'


def test_reported_ability_keeps_both_operator_contexts():
    result = read('The auditor reported that Lumen is able to store records.')
    assert result['complete'] is True
    [fact] = result['facts']
    assert fact['qualifiers']['modality'] == 'ability'
    assert fact['qualifiers']['reporting'][0]['subject'] == 'The auditor'
    assert fact['qualifiers']['assertion_contexts'] == ['reported', 'ability']
    assert 'nested_operator_scopes' in result['required_matcher_features']


def test_an_explicit_shared_final_object_has_one_literal_source_for_two_ability_leaves():
    text = 'Lumen is able to store and retrieve records.'
    result = read(text)
    assert result['complete'] is True
    assert tuples(result) == [('Lumen', 'store', 'records'), ('Lumen', 'retrieve', 'records')]
    assert result['facts'][0]['value_source'] == result['facts'][1]['value_source']
    assert result['text_atoms'][0]['text'] == text and len(result['text_atoms']) == 1


def test_permission_and_negation_remain_independent_printed_operators():
    fact = read('Lumen may not release cargo.')['facts'][0]
    assert (fact['subject'], fact['attribute'], fact['value']) == ('Lumen', 'release', 'cargo')
    assert fact['qualifiers'] == {'modality': 'may', 'modal_polarity': 'positive', 'polarity': 'negative'}
    assert fact['logic']['assertion_context'] == 'modal'
    changed = read('Lumen may release cargo.')['facts'][0]
    assert changed['qualifiers']['polarity'] == 'positive'
    assert changed['attribute'] == fact['attribute']


def test_restrictive_relative_is_attached_to_the_actual_antecedent():
    result = read('The device that stores records is portable.', scope=['Products'])
    assert result['complete'] is True
    assert tuples(result) == [('The device', 'be', 'portable')]
    [relative], [main] = result['semantic_operands'], result['facts']
    assert relative['qualifiers']['assertion_context'] == 'restrictive_relative'
    assert main['qualifiers']['subject_restriction'] == {
        'subject': 'The device', 'attribute': 'store', 'value': 'records', 'polarity': 'positive', 'tense': 'present'}
    assert any(edge['type'] == 'narrative_relative_attachment' for edge in result['relations'])
    changed = read('The device that deletes records is portable.')
    assert changed['facts'][-1]['qualifiers']['subject_restriction']['attribute'] == 'delete'


def test_reported_content_is_not_promoted_to_an_unqualified_assertion():
    result = read('The auditor reported that Lumen is not solvent.')
    assert result['complete'] is True
    assert tuples(result) == [('Lumen', 'be', 'solvent')]
    [fact] = result['facts']
    assert fact['qualifiers']['polarity'] == 'negative'
    assert fact['qualifiers']['reporting'] == [{'subject': 'The auditor', 'attribute': 'report', 'polarity': 'positive', 'tense': 'past'}]
    assert fact['qualifiers']['assertion_context'] == 'reported'
    assert any(edge['type'] == 'narrative_reporting_scope' for edge in result['relations'])
    assert 'scoped_reporting' in result['required_matcher_features']


def test_negated_reporting_does_not_negate_the_reported_subject_property():
    result = read('The auditor did not report that Lumen is solvent.')
    assert result['complete'] is True
    [fact] = result['facts']
    assert fact['qualifiers']['polarity'] == 'positive'
    assert fact['qualifiers']['reporting'][0]['polarity'] == 'negative'
    assert fact['logic']['assertion_context'] == 'reported'


def test_two_conditions_are_separate_operands_not_two_asserted_facts_or_one_overwrite():
    text = 'If the gate is open, Lumen may not release cargo unless the permit is valid.'
    result = read(text, scope=['Policy'])
    assert result['complete'] is True
    assert tuples(result) == [('Lumen', 'release', 'cargo')]
    assert [(item['subject'], item['attribute'], item['value']) for item in result['semantic_operands']] == [
        ('the gate', 'be', 'open'), ('the permit', 'be', 'valid')]
    assert all(fact['qualifiers']['assertion_context'] == 'condition_operand' for fact in result['semantic_operands'])
    main = result['facts'][-1]
    assert main['qualifiers']['polarity'] == 'negative' and main['qualifiers']['modality'] == 'may'
    assert main['qualifiers']['conditions'] == [
        {'operator': 'if', 'operand': {'subject': 'the gate', 'attribute': 'be', 'value': 'open', 'polarity': 'positive', 'tense': 'present'}},
        {'operator': 'unless', 'operand': {'subject': 'the permit', 'attribute': 'be', 'value': 'valid', 'polarity': 'positive', 'tense': 'present'}},
    ]
    edges = [edge for edge in result['relations'] if edge['type'] == 'narrative_condition_scope']
    assert [edge['left']['operator'] for edge in edges] == ['if', 'unless']
    assert all(edge['right']['subject'] == 'Lumen' and edge['right']['attribute'] == 'release' for edge in edges)
    assert 'open' not in repr([edge['left'] for edge in edges])
    assert 'valid' not in repr([edge['left'] for edge in edges])


def test_or_membership_remains_alternative_membership_not_a_conjunction():
    text = 'Lumen includes Alpha or Beta.'
    result = read(text)
    assert result['complete'] is True
    [group] = result['facts']
    assert (group['subject'], group['attribute'], group['value']) == ('Lumen', 'logical_alternative', text[:-1])
    assert group['role'] == 'logical_group'
    assert group['logic']['kind'] == 'logical_group'
    assert group['logic']['tree']['operator'] == 'or'
    assert [(item['subject'], item['attribute'], item['value']) for item in result['semantic_operands']] == [
        ('Lumen', 'include', 'Alpha'), ('Lumen', 'include', 'Beta')]
    assert all(item['qualifiers']['assertion_context'] == 'alternative_member' for item in result['semantic_operands'])
    a, b = group['value_source']['text_span']
    assert text[a:b] == group['value']
    assert 'alternative_membership' in result['required_matcher_features']
    assert not result['blockers']


@pytest.mark.parametrize('text', [
    'Lumen is ready because the supply chain varies.',
    'Lumen does not store records and retrieve files.',
    'The device that stores records.',
    'The auditor reported that "Lumen is solvent.',
    'If the gate is open Lumen may release cargo.',
    'Lumen cannot not store records.',
    'There is a supplier.',
    'Lumen never owns Alpha.',
    'Lumen includes "Research and Development".',
    'Lumen is a research and development provider.',
    'The Board shall not review and approve Report.',
])
def test_unsupported_or_ambiguous_scope_keeps_same_source_unresolved(text):
    result = read(text)
    assert result['complete'] is False
    assert result['unresolved'] and result['blockers']
    assert all(item['source']['path'] == SOURCE['path'] and item['layers'] == ['B', 'L'] for item in result['unresolved'])
    assert result['text_atoms'][0]['text'] == text


def test_known_sentence_cannot_hide_an_unread_neighbor():
    result = read('Lumen is ready. Business circumstances evolve unpredictably.')
    assert tuples(result) == [('Lumen', 'be', 'ready')]
    assert result['complete'] is False
    assert result['unresolved'][0]['text'] == 'Business circumstances evolve unpredictably.'


def test_source_ranges_cover_original_text_once_and_preserve_nested_offsets():
    text = 'If the gate is open, Lumen may not release cargo unless the permit is valid.'
    source = {**SOURCE, 'text_span': [19, 19 + len(text)]}
    before = deepcopy(source)
    result = read_narrative(text, source, scope=['Policy'])
    assert source == before
    assert result['text_atoms'] == [{'text': text, 'role': 'literal', 'source': {**source, 'text_span': [19, 19 + len(text)]}}]
    for fact in result['facts'] + result['semantic_operands']:
        for text_key, source_key in [('subject', 'subject_source'), ('predicate', 'predicate_source'), ('value', 'value_source')]:
            a, b = fact[source_key]['text_span']
            assert text[a - 19:b - 19] == fact[text_key]
    assert result['controls'] == []


def test_entire_source_scope_is_not_inferred_from_business_values():
    north = read('Lumen is ready.', scope=['North'])
    south = read('Lumen is ready.', scope=['South'])
    assert tuples(north) == tuples(south)
    assert north['facts'][0]['scope'] == ['North'] and south['facts'][0]['scope'] == ['South']
    assert north['relations'][0]['right']['scope'] != south['relations'][0]['right']['scope']


@pytest.mark.parametrize('present,past', [
    ('Lumen is ready.', 'Lumen was ready.'),
    ('Lumen owns Alpha.', 'Lumen owned Alpha.'),
    ('Lumen does not own Alpha.', 'Lumen did not own Alpha.'),
    ('Lumen is able to store records.', 'Lumen was able to store records.'),
])
def test_explicit_finite_tense_is_never_erased_by_canonical_predicates(present, past):
    current, former = read(present), read(past)
    assert current['complete'] and former['complete']
    [now], [then] = current['facts'], former['facts']
    assert (now['subject'], now['attribute'], now['value']) == (then['subject'], then['attribute'], then['value'])
    assert now['qualifiers']['tense'] == 'present'
    assert then['qualifiers']['tense'] == 'past'
    for text, fact in [(present, now), (past, then)]:
        a, b = fact['qualifier_sources']['tense']['text_span']
        assert text[a:b] in {'is', 'was', 'owns', 'owned', 'does', 'did'}
    assert current['relations'][0]['right']['qualifiers']['tense'] == 'present'
    assert former['relations'][0]['right']['qualifiers']['tense'] == 'past'


def test_reporter_tense_does_not_overwrite_the_reported_property_tense():
    result = read('The auditor did not report that Lumen is solvent.')
    [fact] = result['facts']
    assert fact['qualifiers']['tense'] == 'present'
    assert fact['qualifiers']['reporting'][0]['tense'] == 'past'
    [tree] = result['logic']
    assert tree['tense'] == 'past'
    assert tree['tense_source']['text_span'] == [12, 15]
    changed = read('The auditor does not report that Lumen is solvent.')
    assert changed['facts'][0]['qualifiers']['reporting'][0]['tense'] == 'present'


def test_relative_restriction_retains_its_own_finite_tense():
    present = read('The device that stores records is portable.')['facts'][-1]
    past = read('The device that stored records is portable.')['facts'][-1]
    assert present['qualifiers']['subject_restriction']['tense'] == 'present'
    assert past['qualifiers']['subject_restriction']['tense'] == 'past'
    assert present['qualifiers']['tense'] == past['qualifiers']['tense'] == 'present'


def test_nested_ability_inside_a_condition_retains_the_operator_not_an_actual_action():
    result = read('If Lumen is able to store records, the gate is open.')
    assert result['complete']
    condition = result['facts'][-1]['qualifiers']['conditions'][0]
    assert condition['operator'] == 'if'
    assert condition['operand']['kind'] == 'modality'
    assert condition['operand']['modality'] == 'ability' and condition['operand']['polarity'] == 'positive'
    assert condition['operand']['child']['attribute'] == 'store'


def test_conditional_operand_does_not_create_an_extra_business_question():
    result = read('If the gate is open, the Board may pay Dividend.')
    assert result['complete']
    assert tuples(result) == [('the Board', 'pay', 'Dividend')]
    [operand] = result['semantic_operands']
    assert (operand['subject'], operand['attribute'], operand['value']) == ('the gate', 'be', 'open')
    assert not any(edge['type'] == 'field_binding' and edge['right']['subject'] == 'the gate'
                   for edge in result['relations'])
    assert result['semantic_operand_relations']


def test_negated_modal_and_modal_with_a_negated_action_have_different_scopes():
    prohibited = read('Lumen must not release cargo.')
    impossible = read('Lumen cannot release cargo.')
    [must], [cannot] = prohibited['logic'], impossible['logic']
    assert must['kind'] == 'modality' and must['polarity'] == 'positive'
    assert must['child']['kind'] == 'negation'
    assert cannot['kind'] == 'modality' and cannot['polarity'] == 'negative'
    assert cannot['child']['kind'] == 'proposition'
    assert prohibited['facts'][0]['qualifiers']['modal_polarity'] == 'positive'
    assert prohibited['facts'][0]['qualifiers']['polarity'] == 'negative'
    assert impossible['facts'][0]['qualifiers']['modal_polarity'] == 'negative'
    assert impossible['facts'][0]['qualifiers']['polarity'] == 'positive'


def test_changed_objects_do_not_select_or_change_a_logical_binding_endpoint():
    left = read('Lumen owns Alpha.')
    right = read('Lumen owns Beta.')
    assert left['facts'][0]['value'] != right['facts'][0]['value']
    assert [(edge['type'], edge['left'], edge['right']) for edge in left['relations']] == [
        (edge['type'], edge['left'], edge['right']) for edge in right['relations']]


def test_all_external_qualifier_sources_are_present_without_creating_extra_text_atoms():
    text = 'The auditor reported that Lumen may release cargo if the gate is open.'
    result = read(text)
    assert result['complete']
    [fact] = result['facts']
    [condition] = fact['qualifier_sources']['conditions']
    [report] = fact['qualifier_sources']['reporting']
    for source, literal in [(condition['operator_source'], 'if'), (condition['operand_source'], 'the gate is open'),
                            (report['speaker_source'], 'The auditor'), (report['predicate_source'], 'reported')]:
        a, b = source['text_span']
        assert text[a:b] == literal
    assert result['text_atoms'][0]['text'] == text and len(result['text_atoms']) == 1


@pytest.mark.parametrize('text,complete', [
    ('Lumen had owned Alpha.', False),
    ('Lumen has acquired Alpha.', True),
    ('Lumen was acquired by Alpha.', False),
    ('Lumen may stored records.', False),
    ('Lumen did owns Alpha.', False),
])
def test_present_active_perfect_does_not_accept_passive_past_or_malformed_auxiliaries(text, complete):
    result = read(text)
    assert result['complete'] is complete
    if complete:
        [fact] = result['facts']
        assert (fact['subject'], fact['attribute'], fact['value']) == ('Lumen', 'acquire', 'Alpha')
        assert fact['qualifiers']['aspect'] == 'perfect' and fact['qualifiers']['tense'] == 'present'
        assert 'active_aspect_scope' in result['required_matcher_features']
    else:
        assert not result['facts']
        assert result['unresolved'][0]['source']['path'] == SOURCE['path']
    assert result['text_atoms'][0]['text'] == text


def test_full_clauses_with_distinct_actors_form_one_compound_condition_operand():
    text = 'If Gate is open and Permit is valid, Board may pay Fee.'
    result = read(text, scope=['North'])
    assert result['complete']
    assert tuples(result) == [('Board', 'pay', 'Fee')]
    assert [(item['subject'], item['attribute'], item['value']) for item in result['semantic_operands']] == [
        ('Gate', 'be', 'open'), ('Permit', 'be', 'valid')]
    [condition] = result['facts'][0]['qualifiers']['conditions']
    assert condition == {'operator': 'if', 'operand': {'operator': 'and', 'operands': [
        {'subject': 'Gate', 'attribute': 'be', 'value': 'open', 'polarity': 'positive', 'tense': 'present'},
        {'subject': 'Permit', 'attribute': 'be', 'value': 'valid', 'polarity': 'positive', 'tense': 'present'},
    ]}}
    [tree] = result['logic']
    operand = tree['bindings'][0]['operand']
    assert operand['mode'] == 'clauses' and operand['operator'] == 'and'
    for child in operand['children']:
        a, b = child['subject_source']['text_span']
        assert text[a:b] == child['subject']
    assert all(edge['right']['subject'] == 'Board' for edge in result['relations'])


def test_full_clause_and_keeps_each_explicit_actor_and_negation():
    result = read('Gate is not open and Permit is valid.')
    assert result['complete']
    assert tuples(result) == [('Gate', 'be', 'open'), ('Permit', 'be', 'valid')]
    assert [item['qualifiers']['polarity'] for item in result['facts']] == ['negative', 'positive']


def test_full_clause_or_is_one_group_and_does_not_invent_a_common_actor():
    text = 'Gate is open or Permit is valid.'
    result = read(text)
    assert result['complete']
    [group] = result['facts']
    assert group['subject'] == '' and group['subject_source'] is None
    assert group['attribute'] == 'logical_alternative' and group['value'] == text[:-1]
    assert group['logic']['tree']['mode'] == 'clauses'
    assert [item['subject'] for item in result['semantic_operands']] == ['Gate', 'Permit']
    assert 'alternative_membership' in result['required_matcher_features']


def test_full_clause_or_inside_if_is_still_a_noncounting_compound_operand():
    result = read('If Gate is open or Permit is valid, Board may pay Fee.')
    assert result['complete']
    assert tuples(result) == [('Board', 'pay', 'Fee')]
    [condition] = result['facts'][0]['qualifiers']['conditions']
    assert condition['operator'] == 'if'
    assert condition['operand']['operator'] == 'or'
    assert [item['subject'] for item in condition['operand']['operands']] == ['Gate', 'Permit']
    groups = [item for item in result['semantic_operands'] if item['role'] == 'logical_group']
    assert len(groups) == 1 and groups[0]['subject'] == ''
    assert all(item['semantic_role'] == 'operand' for item in result['semantic_operands'])
    assert all(edge['right']['subject'] == 'Board' for edge in result['relations'])


def test_or_of_two_explicit_modal_clauses_can_keep_a_genuinely_shared_actor():
    result = read('Board may review Report or Board may approve Budget.')
    assert result['complete']
    [group] = result['facts']
    assert group['subject'] == 'Board'
    assert [item['attribute'] for item in result['semantic_operands']] == ['review', 'approve']
    assert all(item['qualifiers']['modality'] == 'may' for item in result['semantic_operands'])


@pytest.mark.parametrize('text', [
    'Board shall not review and approve Report.',
    'Board includes "Gate is open and Permit is valid".',
    "Board includes 'Gate is open or Permit is valid'.",
    'Board includes ‘review and approve Report’.',
    'Gate is open and Permit is valid or Board is ready.',
])
def test_clause_coordination_never_splits_quoted_text_or_distributes_ambiguous_negation(text):
    result = read(text)
    assert not result['complete'] and result['unresolved']
    assert result['facts'] == []
    assert result['text_atoms'][0]['text'] == text


def test_an_internal_possessive_apostrophe_is_not_a_quote_delimiter():
    result = read("Board owns Lumen's records.")
    assert result['complete']
    assert tuples(result) == [('Board', 'own', "Lumen's records")]
