"""Invented metric comparisons; source roles and semantics are hand-fixed."""

from copy import deepcopy

import pytest

from moparse_eval.cjk_measurement_requirements import read_cjk_measurements
from moparse_eval.cjk_narrative_requirements import read_cjk_narrative
from moparse_eval.three_layer import (
    compile_expected,
    compile_markdown,
    grade_layers,
    read_candidate_markdown,
)

SOURCE = {'path': '<invented-cjk-measurements>', 'lines': [3, 3]}
TEXT = '2028年，工业产值超过137万元，同比增长4.3%。'


def read(text=TEXT, **kwargs):
    return read_cjk_measurements(text, SOURCE, **kwargs)


def test_total_threshold_and_same_subject_relative_change_are_two_requirements():
    result = read(scope=['North'])
    assert result['complete'] and not result['pending_requirements']
    total, growth = result['facts']
    assert [(item['subject'], item['attribute'], item['value']) for item in result['facts']] == [
        ('工业产值', '超过', '137'), ('工业产值', '同比增长', '4.3')]
    assert total['qualifiers'] == {'comparison_operator': 'gt', 'unit': '万元', 'period': '2028年'}
    assert growth['qualifiers'] == {'comparison_basis': 'year_on_year', 'change_direction': 'increase',
                                    'unit': '%', 'period': '2028年'}
    assert all(item['scope'] == ['North'] for item in result['facts'])
    assert total['logic']['kind'] == 'quantity_comparison'
    assert total['logic']['operator'] == 'gt' and total['logic']['right_role'] == 'threshold'
    assert growth['logic']['kind'] == 'year_on_year_change'
    assert growth['logic']['baseline_period'] is None
    assert all('from_period' not in item['qualifiers'] and 'to_period' not in item['qualifiers'] for item in result['facts'])
    assert result['semantic_operands'] == []
    assert result['required_matcher_features'] == [
        'quantity_comparison', 'same_subject_relative_clause', 'shared_period_scope', 'year_on_year_comparison']


def test_every_operator_quantity_unit_and_shared_period_has_its_own_literal_source():
    total, growth = read()['facts']
    checks = [
        (total['subject_source'], [6, 10], '工业产值'),
        (total['predicate_source'], [10, 12], '超过'),
        (total['value_source'], [12, 15], '137'),
        (total['qualifier_sources']['unit'], [15, 17], '万元'),
        (total['qualifier_sources']['period'], [0, 5], '2028年'),
        (growth['subject_source'], [6, 10], '工业产值'),
        (growth['predicate_source'], [18, 22], '同比增长'),
        (growth['value_source'], [22, 25], '4.3'),
        (growth['qualifier_sources']['comparison_basis'], [18, 20], '同比'),
        (growth['qualifier_sources']['change_direction'], [20, 22], '增长'),
        (growth['qualifier_sources']['unit'], [25, 26], '%'),
    ]
    for source, span, literal in checks:
        assert source == {**SOURCE, 'text_span': span}
        assert TEXT[slice(*span)] == literal
    assert growth['qualifier_sources']['period'] == total['qualifier_sources']['period']
    assert growth['subject_binding_evidence']['kind'] == 'immediate_printed_year_on_year_antecedent'


@pytest.mark.parametrize('printed,operator', [('超过', 'gt'), ('低于', 'lt'), ('不低于', 'gte'), ('不超过', 'lte'), ('等于', 'eq')])
def test_comparison_polarity_is_not_erased_into_an_exact_amount(printed, operator):
    result = read(f'工业产值{printed}137万元，同比增长4.3%。')
    assert result['complete']
    assert result['facts'][0]['attribute'] == printed
    assert result['facts'][0]['qualifiers']['comparison_operator'] == operator


def test_ratio_direction_sign_and_unit_do_not_borrow_the_total_currency():
    result = read('2029年，元器件销售额超过21人民币百万元，同比下降-2.7‰。')
    assert result['complete']
    total, growth = result['facts']
    assert total['subject'] == growth['subject'] == '元器件销售额'
    assert total['qualifiers']['unit'] == '人民币百万元' and total['qualifiers']['currency'] == '人民币'
    assert growth['attribute'] == '同比下降' and growth['value'] == '-2.7'
    assert growth['qualifiers']['change_direction'] == 'decrease' and growth['qualifiers']['unit'] == '‰'
    assert 'currency' not in growth['qualifiers']


@pytest.mark.parametrize('tail', ['增长4.3%', '同比增长4.3'])
def test_unsupported_relative_unit_or_omitted_actor_is_not_an_opaque_second_fact(tail):
    text = f'工业产值超过137万元，{tail}。'
    result = read(text)
    assert not result['complete']
    assert [(item['subject'], item['attribute'], item['value']) for item in result['facts']] == [('工业产值', '超过', '137')]
    [pending] = result['pending_requirements']
    assert pending['text'] == text and pending['layers'] == ['B', 'L']
    assert pending['source'] == {**SOURCE, 'text_span': [0, len(text)]}


def test_explicit_second_metric_change_keeps_its_printed_subject_instead_of_the_previous_metric():
    result = read('工业产值超过137万元，港口吞吐量同比增长4.3%。')
    assert result['complete']
    assert [(f['subject'], f['attribute'], f['value']) for f in result['facts']] == [
        ('工业产值', '超过', '137'), ('港口吞吐量', '同比增长', '4.3')]
    assert result['facts'][1]['subject_binding_evidence']['kind'] == 'explicit_local_metric'
    assert not any(e['type'] == 'cjk_year_on_year_subject_binding' for e in result['relations'])


def test_causal_tail_keeps_known_measurements_and_the_whole_unresolved_statement():
    text = TEXT[:-1] + '，因为需求有所恢复。'
    result = read(text)
    assert not result['complete'] and len(result['facts']) == 2
    assert result['pending_requirements'][0]['text'] == text
    assert result['pending_requirements'][0]['fragments'][0]['text'] == '因为需求有所恢复'


@pytest.mark.parametrize('text', ['同比增长4.3%。', '工业产值接近137万元，同比增长4.3%。',
                                '如果工业产值超过137万元，同比增长4.3%。', '工业产值超过137万元？',
                                '去年工业产值超过137万元，同比增长4.3%。',
                                '工业产值和营业收入超过137万元，同比增长4.3%。'])
def test_absent_antecedent_unknown_comparator_and_conditional_prefix_do_not_create_asserted_values(text):
    result = read(text)
    assert result['matched'] and not result['complete']
    assert result['facts'] == []
    assert result['pending_requirements'][0]['text'] == text


def test_scope_and_period_do_not_leak_between_independent_reads_or_sentence_boundaries():
    north = read(scope=['North'])
    south = read('2029年，工业产值超过137万元，同比增长4.3%。', scope=['South'])
    assert north['facts'][0]['scope'] == ['North'] and south['facts'][0]['scope'] == ['South']
    assert north['facts'][1]['qualifiers']['period'] == '2028年'
    assert south['facts'][1]['qualifiers']['period'] == '2029年'
    separated = read_cjk_narrative('工业产值超过137万元。同比增长4.3%。', SOURCE)
    assert not separated['complete'] and len(separated['facts']) == 1
    assert separated['pending_requirements'][0]['text'] == '同比增长4.3%。'


def test_parent_offsets_t_text_and_inputs_are_preserved_without_quantity_conversion():
    source = {**SOURCE, 'text_span': [31, 31 + len(TEXT)]}
    before = deepcopy(source)
    result = read_cjk_measurements(TEXT, source)
    assert source == before
    assert result['text_atoms'] == [{'text': TEXT, 'role': 'literal', 'source': source}]
    assert result['facts'][0]['value_source']['text_span'] == [43, 46]
    assert result['facts'][0]['value'] == '137'
    assert result['controls'] == []


def test_cjk_dispatch_and_public_controlled_chain_keep_two_facts_and_execute_native_comparison():
    parsed = read_cjk_narrative(TEXT, SOURCE)
    assert parsed['complete'] and len(parsed['facts']) == 2
    required = compile_markdown(TEXT, sample_id='invented-cjk-quantities')
    candidate = read_candidate_markdown(TEXT, sample_id='invented-cjk-quantities')
    assert len(required['business']) == len(candidate['business']) == 2
    result = grade_layers(required, candidate)
    assert result['layers']['T']['score'] == 100
    assert result['layers']['B']['denominator'] == 2
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    assert result['publishable'] and not result['blockers']
    assert result['semantic_comparison']['decisions']['B']['equivalent']
    assert result['semantic_comparison']['decisions']['L']['equivalent']


def test_expected_requirement_graph_keeps_two_measurements_and_their_relation_sources():
    declaration = {'sample_id': 'invented-cjk-quantity-graph', 'document_id': 'invented', 'source_pages': [1],
        'standard': 'expected_only', 'scope': [{'lines': [3, 3], 'pages': [1], 'declared_source_pages': [1], 'outside_source_pages': []}],
        'targets': [{'id': 'metric-source', 'kind': 'text', 'text': TEXT, 'raw_text': TEXT, 'raw': TEXT,
                     'reference': SOURCE, 'cells': [], 'parents': [], 'has_children': False, 'context': [],
                     'selected_heading_context': [], 'outside_selection_context': [], 'pages': [1], 'heading_level': None}]}
    required = compile_expected(declaration)
    assert len(required['business']) == 2
    model = required['requirement_model']
    assert model['semantic_complete'] and not model['unresolved']
    [binding] = [edge for edge in required['relations'] if edge['type'] == 'cjk_year_on_year_subject_binding']
    assert binding['left'] == {'subject': '工业产值', 'role': 'antecedent_metric', 'scope': []}
    assert binding['right'] == {'subject': '工业产值', 'attribute': '同比增长', 'scope': []}
    assert binding['binding_evidence']['antecedent_source']['text_span'] == [6, 10]
    assert binding['source']['text_span'] == [18, 20]


def test_two_independent_metric_sentences_have_distinct_local_fact_identities():
    text = '工业产值超过137万元，同比增长4.3%。港口吞吐量超过23万吨，同比下降2.7%。'
    result = read_cjk_narrative(text, SOURCE)
    assert result['complete'] and len(result['facts']) == 4
    assert len({item['id'] for item in result['facts']}) == 4
    assert [item['subject'] for item in result['facts']] == ['工业产值', '工业产值', '港口吞吐量', '港口吞吐量']
