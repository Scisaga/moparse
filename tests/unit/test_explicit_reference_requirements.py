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


def test_quoted_terminal_full_stop_does_not_absorb_the_following_sentence():
    text, result = read_for('Revenue', 'See “Operating Results.” Additional risks remain.')
    reference, = result['references']
    assert reference['text'] == 'See “Operating Results.”'
    assert reference['target']['title'] == 'Operating Results.'
    assert any('Additional risks remain.' in item['text'] for item in result['residual_spans'])


def test_quoted_terminal_full_stop_retains_an_explicit_reference_purpose():
    _, result = read_for('Revenue', 'See “Operating Results.” for more information. Additional risks remain.')
    reference, = result['references']
    assert reference['purpose_text'] == 'for more information'
    assert reference['text'].endswith('for more information.')


@pytest.mark.parametrize('directive,target', [
    ('參見本報告「營運」關於設備擔保的有關內容。',
     {'role': 'reference_target', 'kind': 'document_location', 'document': '本報告', 'title': '營運', 'topic': '設備擔保'}),
    ('參見本報告「展望」關於購置設備部分描述。',
     {'role': 'reference_target', 'kind': 'document_location', 'document': '本報告', 'title': '展望', 'topic': '購置設備'}),
    ('詳情請參見按中國企業會計準則編製的財務報表附註2(17)和按國際財務報告會計準則編製的財務報表附註8。',
     {'role': 'reference_target', 'kind': 'reference_group', 'operator': 'and', 'members': [
         {'role': 'reference_target', 'kind': 'numbered_reference', 'reference_kind': 'note', 'identifier': '2(17)', 'document': '財務報表', 'accounting_basis': '中國企業會計準則'},
         {'role': 'reference_target', 'kind': 'numbered_reference', 'reference_kind': 'note', 'identifier': '8', 'document': '財務報表', 'accounting_basis': '國際財務報告會計準則'}]}),
])
def test_report_reference_paths_and_note_groups_through_the_production_chain(tmp_path, directive, target):
    from moparse_eval.expected_report import validate_evidence
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    text = '# 擔保\n\n' + directive
    graph, required = compiled(tmp_path, text)
    reference, = graph['explicit_references']
    assert reference['target'] == target
    assert reference['owner_proof']['owner'] == {'identity': {'role': 'heading_scope'}, 'scope': ['擔保']}
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert all(result['layers'][key]['score'] == 100 for key in ('T', 'L', 'B') if result['layers'][key]['denominator'])


def test_accounting_difference_owns_a_report_page_and_section_without_invented_amount(tmp_path):
    from moparse_eval.expected_report import validate_evidence
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    text = ('# 會計\n\n本公司根據國際財務報告會計準則和中國企業會計準則編製的會計報表的主要差異'
            '見本年度報告第219頁的本公司財務會計報告的D節。')
    graph, required = compiled(tmp_path, text)
    reference, = graph['explicit_references']
    assert reference['target'] == {'role': 'reference_target', 'kind': 'document_location', 'document': '本年度報告',
                                   'pages': ['219', '219'], 'actor': '本公司', 'component': '財務會計報告', 'section': 'D'}
    assert reference['owner_proof']['owner']['identity'] == {'role': 'accounting_difference_explanation', 'actor': '本公司',
        'left_basis': '國際財務報告會計準則', 'right_basis': '中國企業會計準則'}
    assert not required['business']
    for candidate, correct in [(text, True), (text.replace('219', '220'), False), (text.replace('D節', 'E節'), False)]:
        actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
        assert not actual['blockers'] and not actual['pending_requirements']
        result = grade_layers(required, actual)
        assert result['publishable'], result['blockers']
        validate_evidence(result)
        outcomes = [o for o in result['outcomes'] if o['layer'] == 'L']
        target_id = next(r['id'] for r in required['relations'] if r['type'] == 'explicit_reference_target')
        assert next(o['outcome'] for o in outcomes if o['id'] == target_id) == ('correct' if correct else 'incorrect')
        assert result['layers']['L']['denominator'] == len(required['relations'])


@pytest.mark.parametrize('mutation', ['target', 'binding', 'owner', 'neighbor_source', 'all_semantics'])
def test_report_reference_semantics_cannot_be_forged_while_retaining_all_literal_text(tmp_path, mutation):
    from moparse_eval.expected_report import validate_evidence
    from moparse_eval.requirement_graph import validate_requirement_graph
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    text = '# 擔保\n\n參見本報告「營運」關於設備擔保的有關內容。\n\n# 支出\n\n參見本報告「展望」關於購置設備部分描述。'
    graph, required = compiled(tmp_path, text)
    changed = deepcopy(graph)
    reference = changed['explicit_references'][0]
    if mutation == 'target':
        reference['target']['topic'] = '購置設備'
    elif mutation == 'binding':
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'explicit_reference_target']
    elif mutation == 'owner':
        reference['owner_proof'] = deepcopy(changed['explicit_references'][1]['owner_proof'])
    elif mutation == 'neighbor_source':
        reference['target_source'] = deepcopy(changed['explicit_references'][1]['target_source'])
    else:
        changed['explicit_references'] = []
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    actual['explicit_references'] = []
    result = grade_layers(required, actual)
    assert result['layers']['T']['score'] == 100 and not result['publishable']
    with pytest.raises(ValueError):
        validate_evidence(result)


def test_wrong_report_topic_changes_only_the_owned_reference_target(tmp_path):
    from moparse_eval.expected_report import validate_evidence
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    text = '# 擔保\n\n參見本報告「營運」關於設備擔保的有關內容。'
    _, required = compiled(tmp_path, text)
    for candidate in (text.replace('設備擔保', '設備租賃'), text.replace('「營運」', '「風險」')):
        actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
        assert not actual['blockers'] and not actual['pending_requirements']
        result = grade_layers(required, actual)
        assert result['publishable'], result['blockers']
        validate_evidence(result)
        target_id = next(r['id'] for r in required['relations'] if r['type'] == 'explicit_reference_target')
        assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'L'} == {
            r['id']: 'incorrect' if r['id'] == target_id else 'correct' for r in required['relations']}


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
