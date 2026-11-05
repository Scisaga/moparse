"""Hand-written reference identities and owner bindings; no corpus input."""

from copy import deepcopy

import pytest

from moparse_eval.explicit_reference_requirements import read_explicit_references
from moparse_eval.prose_requirements import read_prose_sequence

SOURCE = {'path': '<invented-references>', 'lines': [5, 5]}


def owner(label):
    return {'identity': {'role': 'printed_field', 'attribute': label}, 'scope': ['North']}


def read_for(label, directive):
    text = f'{label}: available. {directive}'
    result = read_explicit_references(text, SOURCE, scope=['North'], owner=owner(label), owner_evidence=[
        {'kind': 'printed_field_label', 'text': label, 'source': {**SOURCE, 'text_span': [0, len(label)]}}])
    return text, result


def test_quoted_title_and_directive_are_separate_source_bound_roles_not_business_facts():
    text, result = read_for('Revenue', 'See also “Operations — Rivalry.”')
    assert result['matched'] and result['reference_complete']
    assert not result['complete']  # The preceding business prose is a residual.
    assert result['facts'] == []
    [reference] = result['references']
    assert reference['directive_kind'] == 'see_also'
    assert reference['directive_text'] == 'See also'
    assert reference['target'] == {'role': 'reference_target', 'kind': 'quoted_title', 'title': 'Operations — Rivalry.'}
    for field in ('directive', 'target', 'title'):
        a, b = reference[field + '_source']['text_span']
        assert text[a:b] == reference[field + '_text']
    assert [item['role'] for item in result['semantic_roles']] == ['reference_directive', 'reference_target']
    assert result['text_atoms'][0]['text'] == text and len(result['text_atoms']) == 1
    assert result['required_matcher_features'] == ['explicit_reference_binding']


@pytest.mark.parametrize('directive,kind,identifier', [
    ('See Article 07.', 'article', '07'),
    ('See Clause 2.4(a) for more information.', 'clause', '2.4(a)'),
    ('See Section IV.', 'section', 'IV'),
    ('See Note3.', 'note', '3'),
    ('参见第十三条。', '条', '十三'),
    ('见附注4。', 'note', '4'),
])
def test_numbered_reference_identity_is_not_a_business_value(directive, kind, identifier):
    text, result = read_for('Revenue', directive)
    assert result['reference_complete']
    [reference] = result['references']
    assert reference['target'] == {'role': 'reference_target', 'kind': 'numbered_reference',
                                    'reference_kind': kind, 'identifier': identifier}
    a, b = reference['identifier_source']['text_span']
    assert text[a:b] == identifier
    assert reference['identifier_text'] == identifier
    assert result['facts'] == []
    target_edges = [item for item in result['relations'] if item['type'] == 'explicit_reference_target']
    assert len(target_edges) == 1 and target_edges[0]['right']['identifier'] == identifier


def test_cjk_quoted_title_and_trailing_reference_purpose_remain_literal():
    text, result = read_for('Cost', '参见《港口运行规则》。')
    [reference] = result['references']
    assert reference['directive_kind'] == '参见'
    assert reference['target']['title'] == '港口运行规则'
    assert reference['target_text'] == '《港口运行规则》'
    assert result['reference_complete']
    text, result = read_for('Cost', 'See “Port Rules” for more information.')
    [reference] = result['references']
    a, b = reference['purpose_source']['text_span']
    assert text[a:b] == 'for more information'


def test_target_existence_and_scope_words_do_not_prove_directive_ownership():
    text = 'See Note 3.'
    result = read_explicit_references(text, SOURCE, scope=['North'])
    assert result['matched'] and not result['reference_complete']
    assert result['references'][0]['target']['identifier'] == '3'
    assert result['pending_requirements'][0]['reason'] == 'reference_owner_scope_unproven'
    assert result['pending_requirements'][0]['layers'] == ['L']
    assert not any(item['type'] == 'reference_directive_scope' for item in result['relations'])


def test_reference_target_cannot_supply_its_own_owner_proof():
    text = 'See Note 3.'
    result = read_explicit_references(text, SOURCE, owner=owner('Note'), owner_evidence=[
        {'kind': 'printed_field_label', 'text': 'Note', 'source': {**SOURCE, 'text_span': [4, 8]}}])
    assert not result['reference_complete']
    assert result['pending_requirements'][0]['reason'] == 'reference_owner_scope_unproven'


def test_actual_label_source_cannot_prove_a_different_business_owner():
    text = 'Revenue: available. See Note 3.'
    result = read_explicit_references(text, SOURCE, scope=['North'], owner=owner('Cost'), owner_evidence=[
        {'kind': 'printed_field_label', 'text': 'Revenue', 'source': {**SOURCE, 'text_span': [0, 7]}}])
    assert not result['reference_complete']
    assert result['pending_requirements'][0]['reason'] == 'reference_owner_scope_unproven'


@pytest.mark.parametrize('text', [
    'See 17.',
    'See “Unclosed title.',
    'See Note 3 about a topic not declared here.',
    'See Note 3 and Note 4.',
])
def test_uninterpreted_target_or_tail_keeps_the_original_region_pending(text):
    result = read_explicit_references(text, SOURCE)
    assert result['matched'] and not result['reference_complete']
    assert result['pending_requirements']
    assert result['text_atoms'][0]['text'] == text
    assert result['facts'] == []


def test_a_quoted_example_containing_see_is_not_an_actual_directive():
    result = read_explicit_references('The sign reads “See Note 3”.', SOURCE)
    assert not result['matched']
    assert result['references'] == []


def test_parent_source_offsets_and_input_objects_are_not_mutated():
    text = 'See Clause 2.4(a).'
    source = {**SOURCE, 'text_span': [29, 29 + len(text)]}
    before = deepcopy(source)
    result = read_explicit_references(text, source)
    assert source == before
    [reference] = result['references']
    for field in ('directive', 'target', 'identifier'):
        a, b = reference[field + '_source']['text_span']
        assert text[a - 29:b - 29] == reference[field + '_text']


def sequence_unit(label, number, ordinal):
    text = f'{label}: 17. See Note {number}.'
    return {'id': f'paragraph:{ordinal}', 'kind': 'paragraph', 'text': text,
            'source': {'path': '<sequence>', 'lines': [ordinal, ordinal]}, 'scope': ['North'],
            'label': label, 'label_source': {'path': '<sequence>', 'lines': [ordinal, ordinal], 'text_span': [0, len(label)]}}


def test_swapping_note_numbers_preserves_words_but_changes_independently_bound_relations():
    original = [sequence_unit('Revenue', '3', 1), sequence_unit('Cost', '4', 2)]
    changed = [sequence_unit('Revenue', '4', 1), sequence_unit('Cost', '3', 2)]
    before = deepcopy(original)
    required, actual = read_prose_sequence(original), read_prose_sequence(changed)
    assert original == before
    def bindings(result):
        return [(item['left']['owner']['identity']['attribute'], item['right']['identifier'])
                for item in result['relations'] if item['type'] == 'explicit_reference_target']
    assert bindings(required) == [('Revenue', '3'), ('Cost', '4')]
    assert bindings(actual) == [('Revenue', '4'), ('Cost', '3')]
    assert sorted(unit['text'].split('Note ')[1] for unit in original) == sorted(unit['text'].split('Note ')[1] for unit in changed)
    assert required['required_matcher_features'] == ['explicit_reference_binding']
    assert all(slot['text'] == '17' for node in required['endpoints'] for slot in node['content_slots'])
    assert required['facts'] == actual['facts'] == []
    assert all(item.get('object_anchor') is None for item in required['relations'] if item['type'].startswith(('explicit_reference', 'reference_directive')))


def test_sequence_owner_scope_never_falls_back_to_a_reference_target():
    unit = {'id': 'reference', 'kind': 'paragraph', 'text': 'See Note 3.', 'source': SOURCE, 'scope': ['North']}
    result = read_prose_sequence([unit])
    assert any(item['reason'] == 'reference_owner_scope_unproven' for item in result['blockers'])
    assert result['endpoints'][0]['content_slots'] == []
    assert 'lexical_anchor' not in result['endpoints'][0]['identity']


def test_pure_reference_endpoints_keep_proven_owners_and_ignore_note_numbers_as_owners():
    units = []
    for ordinal, label in enumerate(('Revenue', 'Cost'), 1):
        units.append({'id': f'ref:{ordinal}', 'kind': 'paragraph', 'text': 'See Note 3.',
                      'source': {'path': '<sequence>', 'lines': [ordinal * 2, ordinal * 2]},
                      'scope': ['North'], 'label': label,
                      'label_source': {'path': '<sequence>', 'lines': [ordinal * 2 - 1, ordinal * 2 - 1],
                                       'text_span': [0, len(label)]}})
    result = read_prose_sequence(units)
    assert [node['identity']['owner']['identity']['attribute'] for node in result['endpoints']] == ['Revenue', 'Cost']
    assert not any(item['reason'] == 'prose_endpoint_role_collision' for item in result['blockers'])
