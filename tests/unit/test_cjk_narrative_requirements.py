"""Invented CJK semantics fixed independently of source readers and corpus."""

from copy import deepcopy

import pytest

from moparse_eval.cjk_narrative_requirements import read_cjk_narrative

SOURCE = {'path': '<invented-cjk>', 'lines': [7, 7]}


def read(text, **kwargs):
    return read_cjk_narrative(text, SOURCE, **kwargs)


def triples(result):
    return [(item['subject'], item['attribute'], item['value']) for item in result['facts']]


def test_adjacent_copula_and_svo_are_separate_source_bound_requirements():
    text = '星港公司是一家供应商。星港公司提供存储服务。'
    result = read(text, scope=['业务'])
    assert result['complete']
    assert triples(result) == [('星港公司', '是', '一家供应商'), ('星港公司', '提供', '存储服务')]
    assert result['facts'][0]['role'] == 'entity_description'
    assert all(item['scope'] == ['业务'] for item in result['facts'])
    assert all('tense' not in item['qualifiers'] for item in result['facts'])
    assert result['text_atoms'] == [{'text': text, 'role': 'literal', 'source': {**SOURCE, 'text_span': [0, len(text)]}}]


def test_two_explicit_subjects_on_a_comma_are_not_merged_into_one_value():
    result = read('星港公司是一家供应商，远山公司提供物流服务。')
    assert result['complete']
    assert triples(result) == [('星港公司', '是', '一家供应商'), ('远山公司', '提供', '物流服务')]


def test_condition_and_negation_qualify_one_business_requirement():
    text = '如果许可是有效的，星港公司不得释放货物。'
    result = read(text, scope=['North', 'Policy'])
    assert result['complete']
    assert triples(result) == [('星港公司', '释放', '货物')]
    [operand] = result['semantic_operands']
    assert (operand['subject'], operand['attribute'], operand['value']) == ('许可', '是', '有效的')
    [fact] = result['facts']
    assert fact['qualifiers']['conditions'] == [
        {'operator': 'if', 'operand': {'subject': '许可', 'attribute': '是', 'value': '有效的', 'polarity': 'positive'}}]
    assert fact['qualifiers']['modality'] == 'must'
    assert fact['qualifiers']['modal_polarity'] == 'positive'
    assert fact['qualifiers']['polarity'] == 'negative'
    assert all(edge['right']['subject'] == '星港公司' for edge in result['relations'])
    [binding] = fact['qualifier_sources']['conditions']
    a, b = binding['operator_source']['text_span']
    assert text[a:b] == '如果'
    assert result['semantic_operand_relations']


def test_leading_if_and_trailing_unless_keep_two_distinct_operands():
    text = '如果许可是有效的，星港公司可以释放货物，除非通道是不安全的。'
    result = read(text)
    assert result['complete']
    assert triples(result) == [('星港公司', '释放', '货物')]
    assert len(result['semantic_operands']) == 2
    assert [item['operator'] for item in result['facts'][0]['qualifiers']['conditions']] == ['if', 'unless']
    assert result['facts'][0]['qualifiers']['conditions'][1]['operand']['value'] == '不安全的'


def test_explicit_list_punctuation_produces_three_and_members():
    result = read('星港公司包括甲部、乙部和丙部。')
    assert result['complete']
    assert triples(result) == [('星港公司', '包括', '甲部'), ('星港公司', '包括', '乙部'), ('星港公司', '包括', '丙部')]
    assert all(item['qualifiers']['coordination'] == 'and' for item in result['facts'])


def test_or_is_one_structured_business_group_with_two_noncounting_operands():
    text = '星港公司提供甲服务或乙服务。'
    result = read(text)
    assert result['complete']
    [group] = result['facts']
    assert (group['subject'], group['attribute'], group['value']) == ('星港公司', 'logical_alternative', text[:-1])
    assert group['role'] == 'logical_group'
    assert group['logic']['tree']['operator'] == 'or'
    assert [item['value'] for item in result['semantic_operands']] == ['甲服务', '乙服务']
    assert 'alternative_membership' in result['required_matcher_features']


def test_explicit_predicate_coordination_can_share_only_its_printed_final_object():
    text = '星港公司审查并批准报告。'
    result = read(text)
    assert result['complete']
    assert triples(result) == [('星港公司', '审查', '报告'), ('星港公司', '批准', '报告')]
    assert result['facts'][0]['value_source'] == result['facts'][1]['value_source']


def test_inability_and_an_obligatory_negated_action_keep_opposite_operator_scopes():
    unable = read('星港公司不能释放货物。')
    forbidden = read('星港公司必须不释放货物。')
    assert unable['complete'] and forbidden['complete']
    [cannot], [must] = unable['logic'], forbidden['logic']
    assert cannot['polarity'] == 'negative' and cannot['child']['kind'] == 'proposition'
    assert must['polarity'] == 'positive' and must['child']['kind'] == 'negation'
    assert unable['facts'][0]['qualifiers']['polarity'] == 'positive'
    assert forbidden['facts'][0]['qualifiers']['polarity'] == 'negative'


def test_copula_negation_has_a_real_negation_source():
    text = '星港公司不是供应商。'
    [fact] = read(text)['facts']
    assert (fact['subject'], fact['attribute'], fact['value']) == ('星港公司', '是', '供应商')
    assert fact['qualifiers']['polarity'] == 'negative'
    a, b = fact['qualifier_sources']['polarity']['text_span']
    assert text[a:b] == '不'


@pytest.mark.parametrize('text', [
    '星港公司不得审查并批准报告。',
    '如果许可是有效的星港公司释放货物。',
    '其提供物流服务。',
    '星港公司提供可以保存记录的系统。',
    '面向客户，星港公司提供物流服务。',
    '为了扩大业务，星港公司提供物流服务。',
    '星港公司是一家全球运营的公司。',
    '星港公司表示远山公司是供应商。',
    '星港公司提供“研究和开发”服务。',
    '甲公司和乙公司提供物流服务。',
    '星港公司是供应商吗？',
    '如果许可是有效的，则星港公司释放货物。',
    '星港公司将释放货物。',
])
def test_unsupported_scope_never_becomes_an_opaque_complete_business_field(text):
    result = read(text)
    assert not result['complete']
    assert result['unresolved'] and result['pending_requirements'] and result['blockers']
    assert result['text_atoms'][0]['text'] == text
    assert all(item['source']['path'] == SOURCE['path'] and item['layers'] == ['B', 'L']
               for item in result['unresolved'])


def test_known_sentence_preserved_but_unread_neighbor_cannot_hide():
    text = '星港公司是供应商。业务环境持续演化。'
    result = read(text)
    assert triples(result) == [('星港公司', '是', '供应商')]
    assert not result['complete']
    assert result['unresolved'][0]['text'] == '业务环境持续演化。'


def test_comma_neighbor_without_its_own_subject_is_unresolved_not_inherited():
    result = read('星港公司是供应商，提供物流服务。')
    assert triples(result) == [('星港公司', '是', '供应商')]
    assert not result['complete']
    assert result['unresolved'][0]['text'] == '提供物流服务。'


def test_source_offsets_and_every_leaf_role_are_original_substrings():
    text = '如果许可是有效的，星港公司不得释放货物。'
    source = {**SOURCE, 'text_span': [23, 23 + len(text)]}
    original = deepcopy(source)
    result = read_cjk_narrative(text, source, scope=['North'])
    assert source == original
    for item in result['facts'] + result['semantic_operands']:
        for field, evidence in [('subject', 'subject_source'), ('predicate', 'predicate_source'), ('value', 'value_source')]:
            a, b = item[evidence]['text_span']
            assert text[a - 23:b - 23] == item[field]
    assert result['controls'] == []
    assert len(result['text_atoms']) == 1


def test_scope_and_condition_identity_do_not_depend_on_the_action_value():
    north = read('如果许可是有效的，星港公司提供物流服务。', scope=['North'])
    south = read('如果许可是无效的，星港公司提供物流服务。', scope=['South'])
    assert north['facts'][0]['scope'] == ['North']
    assert south['facts'][0]['scope'] == ['South']
    assert north['facts'][0]['qualifiers']['conditions'] != south['facts'][0]['qualifiers']['conditions']
    assert all('有效的' not in repr(edge['left']) for edge in north['relations'])


def test_non_cjk_is_not_claimed_by_this_language_dispatch():
    result = read('Lumen owns Alpha.')
    assert result['matched'] is False
    assert result['facts'] == []


def test_words_containing_operator_characters_are_not_rewritten_or_split():
    result = read('智能公司提供能力平台。')
    assert result['complete']
    assert triples(result) == [('智能公司', '提供', '能力平台')]


def test_a_condition_with_a_coordinated_operand_keeps_both_operators():
    result = read('如果许可包括甲类、乙类，星港公司提供服务。')
    assert result['complete']
    assert triples(result) == [('星港公司', '提供', '服务')]
    [condition] = result['facts'][0]['qualifiers']['conditions']
    assert condition['operator'] == 'if'
    assert condition['operand']['operator'] == 'and'
    assert [item['value'] for item in condition['operand']['operands']] == ['甲类', '乙类']
