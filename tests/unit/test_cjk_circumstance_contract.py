"""Invented source oracles for attached means, background and causes."""

import json
from copy import deepcopy

import pytest

from moparse_eval.expected_readback import read_expected
from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.source_obligations import audit_source_obligations
from moparse_eval.three_layer import grade_layers, read_candidate_markdown


def authored(tmp_path, text):
    directory = tmp_path / 'invented-circumstances'
    directory.mkdir(exist_ok=True)
    (directory / 'expected.md').write_text(text + '\n', encoding='utf-8')
    (directory / 'manifest.json').write_text(json.dumps({
        'markdown': {'path': 'expected.md'},
        'source_map': {'entries': [{'source_pages': [1], 'markdown_lines': [1, len(text.splitlines())]}]},
    }), encoding='utf-8')
    return read_expected({'id': 'invented-circumstances', 'document_id': 'invented-circumstances',
                          'source_pages': [1]}, tmp_path)


def compiled(tmp_path, text):
    expected = authored(tmp_path, text)
    before = deepcopy(expected)
    graph = compile_requirement_graph(expected)
    assert graph['semantic_complete'], graph['unresolved']
    assert audit_source_obligations(graph['source_obligation_inventory'], graph)['semantic_complete']
    validate_requirement_graph(graph, expected=expected)
    assert expected == before
    return graph, evaluation_projection(graph)


def compared(required, text):
    result = grade_layers(required, read_candidate_markdown(text, sample_id='invented-circumstances'))
    validate_evidence(result)
    return result


def test_means_retains_two_operations_and_a_separate_qualified_result(tmp_path):
    text = '借助生产流程优化以及设备性能提升，产出规模保持增长。'
    graph, required = compiled(tmp_path, text)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [
        ('产出规模', '增长', '')]
    operands = [n for n in graph['nodes'] if n['kind'] == 'semantic_operand']
    assert [(f['subject'], f['attribute'], f['value']) for f in operands] == [
        ('生产流程', '优化', ''), ('设备性能', '提升', '')]
    [scope] = [e for e in required['relations'] if e['type'] == 'narrative_circumstance_scope']
    assert scope['left']['operator'] == 'means'
    assert scope['right']['subject'] == '产出规模'
    result = compared(required, '通过生产流程优化以及设备性能提升，产出规模保持增长。')
    assert result['layers']['T']['score'] < 100
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    assert result['publishable'], result['blockers']


@pytest.mark.parametrize('candidate', [
    '随着生产流程优化以及设备性能提升，产出规模保持增长。',
    '借助生产流程优化，产出规模保持增长。',
    '借助生产流程优化以及设备性能下降，产出规模保持增长。',
    '借助生产流程优化以及设备性能提升，产出规模增长。',
])
def test_means_wrong_operator_operand_or_restriction_fails_final_BL(tmp_path, candidate):
    _, required = compiled(tmp_path, '借助生产流程优化以及设备性能提升，产出规模保持增长。')
    result = compared(required, candidate)
    assert all(result['layers'][k]['numerator'] < result['layers'][k]['denominator'] for k in ('B', 'L'))


BACKGROUND = '随着产出规模的增长、产品组合的稳健，核心业务盈利能力逐步恢复。'
INVESTMENT = '持续加大对新材料、储能、自动化等领域面向未来的基础研究与创新投入，开发费用同比上升，同时受益于产出规模增长，开发费用率同比下降。'
ADMIN = '坚持对新产品领域发展、供应体系建设等的投入，同时受益于持续变革带来的运营效率提升，销售和管理费用率同比下降。'
CAUSE = '2029年，运输费用为人民币417万元，同比增长6.2%，主要受其他运输损益变动的影响。'
DEBT = '通过优化融资结构，偿还部分债务，2029年底长短期借款余额较年初减少人民币137万元。'


@pytest.mark.parametrize('text,triples,operands', [
    (BACKGROUND, [('核心业务盈利能力', '恢复', '')], [('产出规模', '增长', ''), ('产品组合', '稳健', '')]),
    (INVESTMENT, [('', '加大', '对新材料、储能、自动化等领域面向未来的基础研究与创新投入'),
                  ('开发费用', '上升', ''), ('开发费用率', '下降', '')], [('产出规模', '增长', '')]),
    (ADMIN, [('', '坚持', '对新产品领域发展、供应体系建设等的投入'), ('销售和管理费用率', '下降', '')],
     [('', '变革', ''), ('运营效率', '提升', '')]),
    (CAUSE, [('运输费用', '为', '417'), ('运输费用', '同比增长', '6.2')], [('其他运输损益', '变动', '')]),
    (DEBT, [('', '偿还', '部分债务'), ('长短期借款余额', '较年初减少', '137')], [('', '优化', '融资结构')]),
])
def test_complete_independent_production_oracles(tmp_path, text, triples, operands):
    graph, required = compiled(tmp_path, text)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == triples
    assert [(f['subject'], f['attribute'], f['value']) for f in graph['nodes']
            if f['kind'] == 'semantic_operand'] == operands
    result = compared(required, text)
    assert result['publishable'], result['blockers']
    assert all(result['layers'][k]['score'] == 100 for k in ('T', 'B', 'L'))


@pytest.mark.parametrize('text,candidate', [
    (BACKGROUND, BACKGROUND.replace('随着', '借助')),
    (BACKGROUND, BACKGROUND.replace('随着', '由于')),
    (BACKGROUND, BACKGROUND.replace('、产品组合的稳健', '')),
    (INVESTMENT, INVESTMENT.replace('新材料、', '')),
    (INVESTMENT, INVESTMENT.replace('等领域', '领域')),
    (INVESTMENT, INVESTMENT.replace('面向未来的', '面向当前的')),
    (INVESTMENT, INVESTMENT.replace('上升', '下降')),
    (INVESTMENT, INVESTMENT.replace('同时', '')),
    (INVESTMENT, INVESTMENT.replace('持续', '')),
    (ADMIN, ADMIN.replace('供应体系建设', '供应体系发展')),
    (ADMIN, ADMIN.replace('同时受益于', '同时借助')),
    (CAUSE, CAUSE.replace('主要', '')),
    (CAUSE, CAUSE.replace('变动', '提升')),
    (DEBT, DEBT.replace('部分', '全部')),
    (DEBT, DEBT.replace('较年初', '较2028年末')),
])
def test_independent_nearby_but_wrong_meanings_do_not_pass(tmp_path, text, candidate):
    _, required = compiled(tmp_path, text)
    result = grade_layers(required, read_candidate_markdown(candidate, sample_id='invented-circumstances'))
    assert result['layers']['B']['numerator'] < result['layers']['B']['denominator']
    assert result['layers']['L']['numerator'] < result['layers']['L']['denominator']
    if result['publishable']:
        validate_evidence(result)


def test_causal_quantity_error_keeps_independent_layout_and_correct_amount(tmp_path):
    _, required = compiled(tmp_path, CAUSE)
    result = compared(required, CAUSE.replace('6.2%', '8.7%'))
    assert result['layers']['B']['numerator'] == 1
    assert result['layers']['B']['denominator'] == 2
    assert result['layers']['L']['score'] == 100


def test_one_qualitative_clause_error_preserves_unrelated_correct_assertions(tmp_path):
    _, required = compiled(tmp_path, INVESTMENT)
    result = grade_layers(required, read_candidate_markdown(INVESTMENT.replace('开发费用同比上升', '开发费用同比下降'),
                                                          sample_id='invented-circumstances'))
    assert result['layers']['B']['numerator'] == 2
    assert result['layers']['B']['denominator'] == 3


@pytest.mark.parametrize('text,candidate', [
    (BACKGROUND, BACKGROUND.replace('的增长', '增长').replace('的稳健', '稳健')),
    ('借助生产数字化、低碳化转型以及设备性能提升，产出规模保持增长。',
     '通过低碳化、生产数字化转型以及设备性能提升，产出规模保持增长。'),
    (INVESTMENT, INVESTMENT.replace('新材料、储能、自动化', '新材料、储能和自动化')),
    (ADMIN, ADMIN.replace('领域发展、供应', '领域发展和供应')),
    (CAUSE, CAUSE.replace('主要受', '主要受到')),
    (DEBT, DEBT.replace('通过', '借助')),
])
def test_legal_source_variations_preserve_BL_while_T_retains_the_difference(tmp_path, text, candidate):
    _, required = compiled(tmp_path, text)
    result = compared(required, candidate)
    assert result['layers']['T']['score'] < 100
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100


@pytest.mark.parametrize('marker', ['如果', '为了', '由于'])
def test_means_cannot_be_replaced_with_condition_purpose_or_cause(tmp_path, marker):
    text = '借助设备性能提升，产出规模保持增长。'
    _, required = compiled(tmp_path, text)
    result = compared(required, text.replace('借助', marker))
    assert result['layers']['B']['score'] == 0
    assert result['layers']['L']['score'] < 100


def test_debt_actions_and_change_have_no_inferred_causal_edge_or_unprinted_date(tmp_path):
    _, required = compiled(tmp_path, DEBT)
    repayment, change = required['business']
    assert repayment['subject'] == ''
    assert 'period' not in repayment['qualifiers']
    assert repayment['qualifiers']['circumstances'][0]['operand']['attribute'] == '优化'
    assert change['qualifiers']['from_period'] == '年初'
    assert change['qualifiers']['period'] == '2029年底'
    assert 'circumstances' not in change['qualifiers']
    assert '2028' not in json.dumps(change, ensure_ascii=False)
    assert [edge['right']['attribute'] for edge in required['relations']
            if edge['type'] == 'narrative_circumstance_scope'] == ['偿还']


@pytest.mark.parametrize('mutation', ['cause_target', 'cause_direction', 'cause_operand_neighbor', 'cause_marker_neighbor',
                                    'all_structure', 'nominal_event_predicate', 'nominal_quantifier_relation'])
def test_source_and_semantic_mutations_fail_final_comparison_and_report_review(tmp_path, mutation):
    from moparse_eval.three_layer import compile_markdown

    text = CAUSE if mutation.startswith('cause') else ADMIN if mutation == 'nominal_event_predicate' else DEBT
    _, required = compiled(tmp_path, text)
    actual = read_candidate_markdown(text, sample_id='invented-circumstances')
    if mutation == 'cause_target':
        wrapper = actual['logical_statements'][0]
        wrapper['target_source'] = deepcopy(wrapper['child']['clauses'][0]['source'])
    elif mutation == 'cause_direction':
        actual['logical_statements'][0]['direction'] = 'child_to_operand'
    elif mutation == 'cause_operand_neighbor':
        actual['semantic_operands'][0]['subject_source']['lines'] = [99, 99]
    elif mutation == 'cause_marker_neighbor':
        actual['business'][1]['qualifier_sources']['circumstances'][0]['operator_source']['lines'] = [99, 99]
    elif mutation == 'all_structure':
        for key in ('logical_statements', 'relations', 'semantic_operands', 'semantic_operand_relations', 'required_matcher_features'):
            actual[key] = []
        for f in actual['business']:
            f['qualifiers'].pop('circumstances', None)
            f['qualifier_sources'].pop('circumstances', None)
    elif mutation == 'nominal_quantifier_relation':
        actual['relations'] = [e for e in actual['relations'] if e['type'] != 'narrative_cjk_quantifier_scope']
    else:
        def change(value):
            if isinstance(value, dict):
                if value.get('kind') == 'proposition' and value.get('attribute') == '建设':
                    value['attribute'] = '优化'
                for child in value.values():
                    change(child)
            elif isinstance(value, list):
                for child in value:
                    change(child)
        change(actual)
    assert compile_markdown(text)['text']  # Original candidate words are retained.
    result = grade_layers(required, actual)
    assert result['layers']['T']['score'] == 100
    assert not result['publishable'] or any(result['layers'][k]['score'] < 100 for k in ('B', 'L'))
    if not result['publishable']:
        with pytest.raises(ValueError):
            validate_evidence(result)
    else:
        validate_evidence(result)


@pytest.mark.parametrize('mutation', ['scope_edge', 'operand', 'all_semantics', 'direction', 'neighbor', 'metric_binding', 'nominal_child'])
def test_all_text_retained_cannot_replace_deleted_or_misbound_semantic_structure(tmp_path, mutation):
    graph, _ = compiled(tmp_path, INVESTMENT + '\n\n' + BACKGROUND)
    changed = deepcopy(graph)
    if mutation == 'scope_edge':
        changed['relations'] = [e for e in changed['relations'] if e['type'] != 'narrative_circumstance_scope']
    elif mutation == 'operand':
        changed['nodes'] = [n for n in changed['nodes'] if n['kind'] != 'semantic_operand']
    elif mutation == 'all_semantics':
        changed['logic'] = []
    elif mutation == 'direction':
        next(e for e in changed['relations'] if e['type'] == 'narrative_circumstance_scope')['left']['direction'] = 'child_to_operand'
    elif mutation == 'neighbor':
        n = next(n for n in changed['nodes'] if n['kind'] == 'semantic_operand')
        n['predicate_source']['lines'] = [3, 3]
    elif mutation == 'metric_binding':
        next(e for e in changed['relations'] if e['type'] == 'narrative_circumstance_scope')['right']['subject'] = '开发费用'
    else:
        phrase = next(n for n in changed['nodes'] if n['id'] in changed['projections']['B'])['object_phrase']
        phrase['parts'] = []
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


@pytest.mark.parametrize('label', ['投资余额', 'Report', 'Revenue'])
def test_noncalendar_scalar_native_role_basis_does_not_enter_calendar_label_proof(tmp_path, label):
    expected = authored(tmp_path, f'| 指标 | 数值 |\n| --- | --- |\n| {label} | 17 |')
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    facts = [f for f in graph['nodes'] if f['id'] in graph['projections']['B']]
    assert any(f['value'] == '17' and isinstance(f.get('role_basis'), str) for f in facts)


@pytest.mark.parametrize('text,subject,attribute,value', [
    ('通过多源系统协同，将处理模块升级为“新型中心”，问题闭环率大于93%。', '问题闭环率', '大于', '93'),
    ('为了完成设备交付，在相关业务范围内，合作方按照比例提供风险担保，担保金额不超过人民币137万元。', '担保金额', '不超过', '137'),
])
def test_unsupported_introduction_does_not_discard_a_valid_independent_quantity(tmp_path, text, subject, attribute, value):
    expected = authored(tmp_path, text)
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    required = evaluation_projection(graph)
    assert (subject, attribute, value) in [(f['subject'], f['attribute'], f['value']) for f in required['business']]
    assert graph['unresolved'] and not graph['semantic_complete']
    actual = read_candidate_markdown(text, sample_id='invented-circumstances')
    assert (subject, attribute, value) in [(f['subject'], f['attribute'], f['value']) for f in actual['business']]
    result = grade_layers(required, actual)
    assert not result['publishable']
    with pytest.raises(ValueError):
        validate_evidence(result)


def test_an_enumerated_causative_clause_cannot_be_a_qualitative_subject_string(tmp_path):
    expected = authored(tmp_path, '一是流程升级带动产值、业务利润双增长。')
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    assert not graph['semantic_complete']
    assert not any(f.get('subject', '').startswith('一是') for f in graph['nodes'])


@pytest.mark.parametrize('text,subject,predicate,obj', [
    ('加速释放库存', '加速', '释放', '库存'),
    ('让产出快速释放价值', '让产出快速', '释放', '价值'),
    ('通过设备改进来提供服务', '通过设备改进来', '提供', '服务'),
    ('通过拓宽通道增加容量是一个重要方向', '通过拓宽通道增加容量', '是', '一个重要方向'),
])
def test_old_introductory_or_adverbial_role_cannot_certify_semantic_coverage(text, subject, predicate, obj):
    from moparse_eval.source_obligations import proposition_role_conflicts

    source = {'path': '<independent-role-oracle>', 'lines': [1, 1]}
    def origin(a, b):
        return {**source, 'text_span': [a, b]}
    a = text.index(predicate)
    fact = {'subject': subject, 'predicate': predicate, 'object': obj,
            'subject_source': origin(0, len(subject)), 'predicate_source': origin(a, a + len(predicate)),
            'object_source': origin(a + len(predicate), len(text))}
    conflicts = proposition_role_conflicts({'text': text, 'source': source}, fact)
    assert any(c['role'] == 'subject' for c in conflicts)
