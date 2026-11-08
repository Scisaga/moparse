"""Local, hand-authored source-only software oracle; never a scoring input."""
import json
from collections import Counter
from pathlib import Path

from moparse_eval.expected_readback import read_expected
from moparse_eval.requirement_graph import (
    _semantic_literal,
    compile_requirement_graph,
    validate_requirement_graph,
)

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'benchmark/runs/lite/requirements/validation'
CURRENT = WORK.parent / 'current'
BIND_CURRENT = True
# Transcribed from the complete authorized text before consulting projection
# values. These records are a diagnostic test oracle, not runtime answers.
SERIES = [
    (1574, '销售收入', '862,072', '704,174', '22.4', None),
    (1575, '销售毛利', '382,571', '325,364', '17.6', None),
    (1576, '销售毛利率', '44.4', '46.2', '(1.8)', '销售毛利'),
    (1577, '期间费用', '(311,532)', '(283,644)', '9.8', None),
    (1578, '期间费用率', '36.1', '40.3', '(4.2)', '期间费用'),
    (1579, '其他净收支', '8,322', '62,681', '(86.7)', None),
    (1580, '营业利润', '79,361', '104,401', '(24.0)', None),
    (1581, '营业利润率', '9.2', '14.8', '(5.6)', '营业利润'),
    (1582, '净财务费用', '(8,255)', '(6,659)', '24.0', None),
    (1583, '所得税', '(8,295)', '(10,646)', '(22.1)', None),
    (1584, '净利润', '62,574', '86,950', '(28.0)', None),
    (1595, '研发费用', '179,687', '164,721', '9.1', None),
    (1596, '研发费用率', '20.8', '23.4', '(2.6)', '研发费用'),
    (1597, '销售和管理费用', '131,845', '118,923', '10.9', None),
    (1598, '销售和管理费用率', '15.3', '16.9', '(1.6)', '销售和管理费用'),
    (1599, '期间费用合计', '311,532', '283,644', '9.8', None),
    (1600, '期间费用率', '36.1', '40.3', '(4.2)', '期间费用合计'),
    (1610, '净汇兑损失', '133', '474', '(71.9)', None),
    (1611, '其他净财务损益', '8,122', '6,185', '31.3', None),
    (1612, '净财务费用合计', '8,255', '6,659', '24.0', None),
    (1620, '非流动资产', '475,693', '390,503', '21.8', None),
    (1621, '流动资产', '814,456', '873,094', '(6.7)', None),
    (1622, '资产合计', '1,290,149', '1,263,597', '2.1', None),
    (1623, '现金与短期投资', '372,232', '475,317', '(21.7)', '资产合计'),
    (1624, '应收账款', '109,558', '97,224', '12.7', '资产合计'),
    (1625, '合同资产', '60,640', '53,886', '12.5', '资产合计'),
    (1626, '存货及其他合同成本', '179,139', '154,558', '15.9', '资产合计'),
    (1627, '非流动负债', '250,252', '304,597', '(17.8)', None),
    (1628, '长期借款', '237,508', '291,688', '(18.6)', '非流动负债'),
    (1629, '流动负债', '495,278', '451,432', '9.7', None),
    (1630, '短期借款', '27,363', '16,726', '63.6', '流动负债'),
    (1631, '应付账款', '104,908', '86,362', '21.5', '流动负债'),
    (1632, '合同负债', '97,461', '95,101', '2.5', '流动负债'),
    (1633, '所有者权益', '544,619', '507,568', '7.3', None),
    (1634, '负债与所有者权益合计', '1,290,149', '1,263,597', '2.1', None),
]
HEADINGS = {1568: '经营结果', 1570: '经营业绩', 1591: '期间费用', 1606: '净财务费用', 1616: '财务状况'}
UNIT_LINES = [1572, 1593, 1608, 1618]
PARENT_LINES = {1576: 1575, 1578: 1577, 1581: 1580, 1596: 1595, 1598: 1597, 1600: 1599,
                1623: 1622, 1624: 1622, 1625: 1622, 1626: 1622, 1628: 1627,
                1630: 1629, 1631: 1629, 1632: 1629}
NARRATIVES = {
    1586: [('销售收入', '实现', '862,072'), ('销售收入', '同比增长', '22.4'), ('净利润', '为', '62,574')],
    1588: [('收入规模', '增长', '')],
    1589: [('主营业务盈利能力', '恢复', '')],
    1602: [('', '加大', '对AI、根技术、智能汽车等领域面向未来的基础研究与创新投入'), ('研发费用', '上升', ''), ('研发费用率', '下降', '')],
    1604: [('', '坚持', '对新业务领域发展、生态建设等的投入'), ('销售和管理费用率', '下降', '')],
    1614: [('净财务费用', '为', '8,255'), ('净财务费用', '同比增长', '24.0')],
    1636: [('总资产余额', '达到', '1,290,149'), ('总资产余额', '同比增长', '2.1'), ('流动资产余额', '占', '63.1')],
    1638: [('', '偿还', '部分债务'), ('长短期借款余额', '较年初减少', '43,543')],
}
OPERANDS = {
    1588: [('行业数字化、智能化、低碳化', '转型', ''), ('产品竞争力', '提升', '')],
    1589: [('收入规模', '增长', ''), ('产业组合', '稳健', '')],
    1602: [('收入规模', '增长', '')],
    1604: [('', '变革', ''), ('运营效率', '提升', '')],
    1614: [('其他净财务损益', '变动', '')],
    1638: [('', '优化', '债务结构')],
}


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def scope_for(line):
    if line >= 1616:
        return ['经营结果', '财务状况']
    base = ['经营结果', '经营业绩']
    if 1591 < line < 1606:
        base.append('期间费用')
    if 1606 < line < 1616:
        base.append('净财务费用')
    return base


def review():
    diagnosis = json.loads((WORK / 'actual-source-diagnosis.json').read_text())
    package = next(w for w in diagnosis['work_packages'] if w['sample_id'] == 'huawei-operating-results-p062-063')
    transport = package['independent_source_acceptance']['input_transport']
    sample = transport['sample_declaration']
    authored = read_expected(sample, Path('/opt/moparse/pdf_sample/parsing/expected'))
    graph = compile_requirement_graph(authored, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=authored)
    assert graph['source_obligation_inventory']['selection'] == transport['selection']
    assert graph['source_obligation_inventory']['sources'] == transport['sources']
    from moparse_eval.cli import code_identity
    current = CURRENT
    index = json.loads((current / 'index.json').read_text())
    row = next(r for r in index['records'] if r['sample_id'] == sample['id'])
    if BIND_CURRENT:
        assert row['software_id'] == index['software_id'] == code_identity()['software_id']
        assert graph == json.loads((current / row['json']).read_text())
    assert authored['scope'] == [
        {'lines': [1568, 1604], 'pages': [1], 'declared_source_pages': [62], 'outside_source_pages': []},
        {'lines': [1606, 1638], 'pages': [2], 'declared_source_pages': [63], 'outside_source_pages': []}]
    targets = {row['reference']['lines'][0]: row for row in authored['targets']}
    covered_lines = set(HEADINGS) | set(UNIT_LINES) | set(NARRATIVES) | {row[0] for row in SERIES}
    assert set(targets) == covered_lines
    nodes = {n['id']: n for n in graph['nodes']}
    facts = [nodes[n] for n in graph['projections']['B']]
    operands = [n for n in graph['nodes'] if n['kind'] == 'semantic_operand']
    results = []
    for line, label, current, prior, change, parent in SERIES:
        own = [f for f in facts if f['source']['lines'] == [line, line]]
        assert [(f['subject'], f['attribute'], f['value']) for f in own] == [
            ('', label, current), ('', label, prior), (label, '同比变动', change)], (line, own)
        periods = ['2024年12月31日', '2023年12月31日'] if line >= 1620 else ['2024年', '2023年']
        expected_scope = scope_for(line) + ([parent] if parent else [])
        for index, f in enumerate(own):
            q = {'unit': '%' if index == 2 or label.endswith('率') else '人民币百万元'}
            if q['unit'] != '%':
                q['currency'] = '人民币'
            q.update({'period': periods[index]} if index < 2 else {'from_period': periods[1], 'to_period': periods[0]})
            if parent:
                q['parent_metric'] = parent
            if line in (1623, 1624, 1625, 1626, 1628, 1630, 1631, 1632):
                q['membership_operator'] = '其中'
            assert f['qualifiers'] == q, (line, f['qualifiers'], q)
            assert f['scope'] == scope_for(line)
            bound = [r for r in graph['relations'] if r.get('fact_id') == f['id'] and r['type'] == 'field_binding']
            assert len(bound) == 1 and bound[0]['right']['scope'] == expected_scope
            assert bound[0]['right']['qualifiers'] == q
            unit_line = 1572 if line < 1591 else 1593 if line < 1606 else 1608 if line < 1616 else 1618
            assert f['qualifier_sources']['unit']['lines'] == ([line, line] if q['unit'] == '%' else [unit_line, unit_line])
            if q['unit'] != '%':
                assert f['qualifier_sources']['currency']['lines'] == [unit_line, unit_line]
            for key in ('period', 'from_period', 'to_period'):
                if key in q:
                    assert f['qualifier_sources'][key]['lines'] == [line, line]
                    assert _semantic_literal(graph['sources'], f['qualifier_sources'][key]) == q[key]
            if parent:
                assert f['row_evidence'][0]['text'] == parent
                assert f['qualifier_sources']['parent_metric']['lines'] == [PARENT_LINES[line], PARENT_LINES[line]]
        results.append({'line': line, 'kind': 'printed_series', 'expected_values': [current, prior, change],
                        'metric': label, 'parent': parent, 'assertions': 'two printed periods, sign, scale/unit, YoY pair, actual parent and membership', 'status': 'passed'})
    for line, triples in NARRATIVES.items():
        own = [f for f in facts if f['source']['lines'] == [line, line]]
        assert [(f['subject'], f['attribute'], f['value']) for f in own] == triples, line
        assert all(f['scope'] == scope_for(line) for f in own)
        assert [(f['subject'], f['attribute'], f['value']) for f in operands if f['source']['lines'] == [line, line]] == OPERANDS.get(line, [])
        results.append({'line': line, 'kind': 'narrative', 'expected_main_assertions': triples,
                        'expected_noncounting_operations': OPERANDS.get(line, []), 'status': 'passed'})
    by_line = {line: [f for f in facts if f['source']['lines'] == [line, line]] for line in NARRATIVES}
    assert by_line[1586][0]['qualifiers'] == {'unit': '百万元', 'currency': '人民币', 'period': '2024年'}
    assert by_line[1586][1]['qualifiers'] == {'comparison_basis': 'year_on_year', 'change_direction': 'increase', 'unit': '%', 'period': '2024年'}
    assert by_line[1586][2]['qualifiers'] == {'unit': '百万元', 'currency': '人民币'}
    for line, operator, manner in ((1588, 'means', '保持'), (1589, 'background', '逐步')):
        f = by_line[line][0]
        assert set(f['qualifiers']) == {'polarity', 'manner', 'circumstances'}
        assert f['qualifiers']['manner'] == manner
        [c] = f['qualifiers']['circumstances']
        assert (c['operator'], c['direction'], c['degree'], c['simultaneous']) == (operator, 'operand_to_child', None, False)
        assert c['operand']['operator'] == 'and' and len(c['operand']['operands']) == 2
    action, expense, ratio = by_line[1602]
    assert action['qualifiers'] == {'polarity': 'positive', 'manner': '持续'}
    assert expense['qualifiers'] == {'polarity': 'positive', 'comparison_basis': 'year_on_year'}
    assert set(ratio['qualifiers']) == {'polarity', 'comparison_basis', 'circumstances'}
    assert ratio['qualifiers']['comparison_basis'] == 'year_on_year'
    [cause] = ratio['qualifiers']['circumstances']
    assert (cause['operator'], cause['degree'], cause['simultaneous'], cause['operand']['subject'], cause['operand']['attribute']) == ('cause', None, True, '收入规模', '增长')
    np = action['object_phrase']
    roles = Counter(n['role'] for n in walk(np) if n.get('kind') == 'cjk_dependency')
    assert roles == {'target_domain': 1, 'orientation': 1, 'activity': 1, 'non_exhaustive_members': 1}
    heads = [n['head'] for n in walk(np) if n.get('kind') == 'cjk_nominal' and n['head']]
    assert set(heads) == {'投入', '领域', 'AI', '根技术', '智能汽车', '基础研究', '创新', '未来'}
    assert by_line[1604][0]['qualifiers'] == {'polarity': 'positive'}
    nominal_events = [(n['subject'], n['attribute']) for n in walk(by_line[1604][0]['object_phrase']) if n.get('kind') == 'proposition']
    assert nominal_events == [('新业务领域', '发展'), ('生态', '建设')]
    [cause] = by_line[1604][1]['qualifiers']['circumstances']
    assert cause['operator'] == 'cause' and cause['simultaneous'] is True
    chain = cause['operand']
    assert chain['kind'] == 'circumstance_scope' and chain['operator'] == 'cause'
    assert (chain['operand']['subject'], chain['operand']['attribute'], chain['operand']['manner']) == ('', '变革', '持续')
    assert (chain['child']['subject'], chain['child']['attribute']) == ('运营效率', '提升')
    amount, growth = by_line[1614]
    assert amount['qualifiers'] == {'unit': '百万元', 'currency': '人民币', 'period': '2024年'}
    assert growth['qualifiers']['period'] == '2024年' and growth['qualifiers']['unit'] == '%'
    [cause] = growth['qualifiers']['circumstances']
    assert (cause['operator'], cause['degree'], cause['operand']['subject'], cause['operand']['attribute']) == ('cause', '主要', '其他净财务损益', '变动')
    assert 'circumstances' not in amount['qualifiers']
    total, growth, share = by_line[1636]
    assert total['qualifiers'] == {'unit': '百万元', 'currency': '人民币', 'period': '2024年底', 'period_operator': '截至'}
    assert growth['qualifiers'] == {'comparison_basis': 'year_on_year', 'change_direction': 'increase', 'unit': '%', 'period': '2024年底', 'period_operator': '截至'}
    assert share['qualifiers'] == {'denominator': '总资产余额', 'ratio_link': '的', 'membership_operator': '其中', 'unit': '%', 'period': '2024年底', 'period_operator': '截至'}
    repayment, reduction = by_line[1638]
    assert set(repayment['qualifiers']) == {'polarity', 'circumstances'}
    assert repayment['object_phrase']['quantifier'] == '部分'
    [means] = repayment['qualifiers']['circumstances']
    assert (means['operator'], means['operand']['attribute'], means['operand']['value']) == ('means', '优化', '债务结构')
    assert reduction['qualifiers'] == {'comparison_basis': '较年初', 'change_direction': 'decrease', 'from_period': '年初',
                                        'unit': '百万元', 'currency': '人民币', 'period': '2024年底'}
    assert reduction['qualifier_sources']['from_period']['lines'] == [1638, 1638]
    assert 'period' not in repayment['qualifiers'] and 'circumstances' not in reduction['qualifiers']
    for f in facts + operands:
        assert _semantic_literal(graph['sources'], f['value_source']) == f['value']
        if f.get('subject') and f.get('predicate'):
            assert _semantic_literal(graph['sources'], f['subject_source']) == f['subject']
        if f.get('predicate'):
            assert _semantic_literal(graph['sources'], f['predicate_source']) == f['predicate']
    for line, label in HEADINGS.items():
        assert targets[line]['text'] == label
        assert not any(f['source']['lines'] == [line, line] for f in facts)
        expected_parent = {1570: '经营结果', 1591: '经营业绩', 1606: '经营业绩', 1616: '经营结果'}.get(line)
        parent_edges = [edge for edge in graph['relations'] if edge['type'] == 'heading_parent' and edge['source']['lines'] == [line, line]]
        assert [(edge['left'], edge['right']) for edge in parent_edges] == ([(expected_parent, label)] if expected_parent else [])
        results.append({'line': line, 'kind': 'heading', 'meaning': 'T literal and L heading hierarchy; no unconditional business fact', 'status': 'passed'})
    for line in UNIT_LINES:
        assert targets[line]['text'] == '金额单位：人民币百万元。'
        assert not any(f['source']['lines'] == [line, line] for f in facts)
        results.append({'line': line, 'kind': 'unit_declaration', 'meaning': 'T literal and bounded amount-series qualifier; percentage and prose scopes stay separate', 'status': 'passed'})
    assert len(facts) == 122 and len(operands) == 9
    assert graph['semantic_complete'] and not graph['unresolved']
    retained = ('text', 'source', 'role', 'kind')
    old_text = transport['T_literal_projection']
    new_text = [{k: n.get(k) for k in retained} for n in graph['nodes'] if n['id'] in graph['projections']['T']]
    assert old_text == new_text
    return {'purpose': 'independent_hand_authored_complete_selected_source_oracle_not_quality_grades',
            'scope': authored['scope'], 'status': 'passed', 'all_52_authorized_sources_reviewed': True,
            'previously_explained_sources_included': True, 'source_records': sorted(results, key=lambda r: r['line']),
            'source_preservation': 'Original authorized source arrays, selections and T literal projection unchanged',
            'fresh_production_compile_matches_saved_current': BIND_CURRENT,
            'facts': len(facts), 'noncounting_operands': len(operands),
            'critical_scope_decisions': [
                'Means and accompanying background remain different; no causal meaning assigned to 随着.',
                'Development, sales and management rate descriptions retain qualitative changes and nested investment domains, orientation and non-exhaustive scope.',
                'The trailing main cause attaches to the immediately preceding YoY change, not the earlier expense amount; 主要 is not 唯一.',
                'Debt optimization is a means of partial repayment; the separately dated reduction has a printed 年初 baseline, with no invented causal edge, year or repayment amount.',
                'The last sentence at L1586 has no printed year; it remains undeclared rather than borrowing the first sentence year.'],
            'oracle_values_supplied_to_runtime': False, 'actual_expected_used_as_candidate': False,
            'candidate_read': False, 'pdf_or_image_read': False, 'quality_acceptance': False}


# Independent transcription of all 40 SF sources, including the already
# implemented seven rows, six-column schema and sixteen classified records.
# These expected structures are diagnostic assertions, never parser inputs.
SF_SERIES = [
    (902, '經營活動產生的現金淨額', '32,186,373', '26,569,819', '21.14'),
    (903, '投資活動使用的現金淨額', '-12,054,744', '-13,505,617', '10.74'),
    (904, '融資活動使用的現金淨額', '-27,979,113', '-12,994,685', '-115.31'),
    (905, '現金及現金等價物減少/增加淨額', '-7,847,484', '69,517', '-11,388.58'),
    (906, '現金及現金等價物的匯兌收益', '45,231', '98,844', '-54.24'),
    (907, '年初現金及現金等價物', '40,448,308', '40,279,947', '0.42'),
    (908, '年末現金及現金等價物', '32,646,055', '40,448,308', '-19.29'),
]
SF_RECORDS = [
    (923, '物業、廠房及設備', '非流動資產', ['59,174,305', '27.67', '60,104,416', '27.14', '-1.55', '0.53']),
    (924, '使用權資產', '非流動資產', ['19,625,629', '9.18', '20,890,047', '9.43', '-6.05', '-0.25']),
    (925, '投資性房地產', '非流動資產', ['7,241,199', '3.39', '6,418,720', '2.90', '12.81', '0.49']),
    (926, '對聯營企業及合營企業的投資', '非流動資產', ['6,203,642', '2.90', '7,378,831', '3.33', '-15.93', '-0.43']),
    (928, '存貨', '流動資產', ['2,432,383', '1.14', '2,440,425', '1.10', '-0.33', '0.04']),
    (929, '合同資產', '流動資產', ['2,740,820', '1.28', '1,632,592', '0.74', '67.88', '0.54']),
    (930, '貿易應收款項及應收票據', '流動資產', ['27,981,633', '13.09', '25,360,433', '11.45', '10.34', '1.64']),
    (931, '以公允價值計量且其變動計入當期損益的金融資產', '流動資產', ['11,246,156', '5.26', '6,809,742', '3.07', '65.15', '2.19']),
    (932, '現金及現金等價物', '流動資產', ['32,646,055', '15.27', '40,448,308', '18.26', '-19.29', '-2.99']),
    (934, '借款', '非流動負債', ['26,319,260', '12.31', '30,396,912', '13.72', '-13.41', '-1.41']),
    (935, '租賃負債', '非流動負債', ['7,094,483', '3.32', '8,038,495', '3.63', '-11.74', '-0.31']),
    (937, '貿易應付款項及應付票據', '流動負債', ['27,395,524', '12.81', '24,914,300', '11.25', '9.96', '1.56']),
    (938, '合同負債', '流動負債', ['2,039,198', '0.95', '1,832,018', '0.83', '11.31', '0.12']),
    (939, '借款', '流動負債', ['18,365,122', '8.59', '22,309,103', '10.07', '-17.68', '-1.48']),
    (940, '租賃負債', '流動負債', ['5,501,314', '2.57', '5,769,965', '2.61', '-4.66', '-0.04']),
    (942, '庫存股', '權益', ['758,081', '0.35', '2,575,532', '1.16', '-70.57', '-0.81']),
]
SF_NARRATIVES = {
    910: [('經營活動產生的現金淨額', '為', '321.9'), ('經營活動產生的現金淨額', '相較2023年同期增長', '21.14')],
    912: [('投資活動使用的現金淨額流出', '為', '120.5'), ('投資活動使用的現金淨額流出', '相較2023年同期下降', '10.74')],
    914: [('融資活動使用的現金淨額流出', '為', '279.8'), ('融資活動使用的現金淨額流出', '相較2023年同期增長', '115.31')],
    944: [('合同資產', '為', '27.4'), ('合同資產', '較2023年末增長', '67.88')],
    946: [('以公允價值計量且變動計入當期損益的金融資產', '為', '112.5'), ('以公允價值計量且變動計入當期損益的金融資產', '較2023年末增長', '65.15')],
    948: [('非流動負債中的借款', '為', '263.2'), ('非流動負債中的借款', '較2023年末下降', '13.41'),
          ('流動負債中的借款', '為', '183.7'), ('流動負債中的借款', '較2023年末下降', '17.68')],
    950: [('庫存股', '為', '7.6'), ('庫存股', '較2023年末下降', '70.57')],
}
SF_OPERANDS = {
    910: [('盈利', '增長', ''), ('', '優化', '經營性現金流管理')],
    912: [('購買物業廠房設備淨現金流出', '減少', ''), ('取得子公司及其他投資的淨現金流出', '減少', ''), ('購買結構性存款淨現金流出', '增加', '')],
    914: [('借款淨流出', '增加', ''), ('分配股利淨流出', '增加', ''), ('發行H股股份募集資金', '流入', '')],
    944: [('業務', '增長', '')], 946: [('結構性存款', '增加', '')],
    948: [('', '償還', '借款')], 950: [('', '註銷', '本公司購回股份')],
}


def review_sf():
    from moparse_eval.cli import code_identity
    from moparse_eval.represented_feature_comparison import _check_references, _reference_sources
    from moparse_eval.requirement_graph import evaluation_projection
    from moparse_eval.source_obligations import audit_source_obligations

    diagnosis = json.loads((WORK / 'actual-source-diagnosis.json').read_text())
    package = next(w for w in diagnosis['work_packages'] if w['sample_id'] == 'sf-cashflow-assets-liabilities-p040-041')
    transport = package['independent_source_acceptance']['input_transport']
    authored = read_expected(transport['sample_declaration'], Path('/opt/moparse/pdf_sample/parsing/expected'))
    graph = compile_requirement_graph(authored, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=authored)
    assert graph['source_obligation_inventory']['sources'] == transport['sources']
    assert graph['source_obligation_inventory']['selection'] == transport['selection']
    current = CURRENT
    index = json.loads((current / 'index.json').read_text())
    row = next(r for r in index['records'] if r['sample_id'] == authored['sample_id'])
    if BIND_CURRENT:
        assert row['software_id'] == index['software_id'] == code_identity()['software_id']
        assert graph == json.loads((current / row['json']).read_text())
    assert authored['scope'] == [
        {'lines': [898, 914], 'pages': [1], 'declared_source_pages': [40], 'outside_source_pages': []},
        {'lines': [916, 950], 'pages': [2], 'declared_source_pages': [41], 'outside_source_pages': []}]
    assert audit_source_obligations(graph['source_obligation_inventory'], graph)['semantic_complete'], [
        (p['reason'], p['source']) for p in graph['unresolved'] if p['reason'] != 'source_obligation_pending']
    headings = {898: '現金流', 916: '資產及負債', 918: '主要資產和負債項目變動情況'}
    groups = {922: '非流動資產', 927: '流動資產', 933: '非流動負債', 936: '流動負債', 941: '權益'}
    targets = {t['reference']['lines'][0]: t for t in authored['targets']}
    assert set(targets) == set(headings) | set(groups) | {900, 920} | set(SF_NARRATIVES) | {x[0] for x in SF_SERIES + SF_RECORDS}
    nodes = {n['id']: n for n in graph['nodes']}
    facts = [nodes[n] for n in graph['projections']['B']]
    operands = [n for n in graph['nodes'] if n['kind'] == 'semantic_operand']
    def own(line, bank=facts):
        return [n for n in bank if n['source']['lines'] == [line, line]]
    results = []
    def record(line, kind, meaning):
        results.append({'line': line, 'kind': kind, 'independent_assertions': meaning, 'status': 'passed'})
    for line, metric, value, prior, change in SF_SERIES:
        items = own(line)
        assert [(f['subject'], f['attribute'], f['value']) for f in items] == [('', metric, value), ('', metric, prior), (metric, '同比變動', change)]
        for i, f in enumerate(items):
            expected = {'period_basis': '截至12月31日止年度', 'unit': '%' if i == 2 else '人民幣千元'}
            expected.update({'from_period': '2023年', 'to_period': '2024年'} if i == 2 else {'period': ['2024年', '2023年'][i], 'currency': '人民幣'})
            assert f['qualifiers'] == expected and f['scope'] == ['現金流']
            assert f['qualifier_sources']['period_basis']['lines'] == [900, 900]
            assert f['qualifier_sources']['unit']['lines'] == ([line, line] if i == 2 else [900, 900])
        record(line, 'annual_cashflow_series', [metric, value, prior, change, 'printed 2024/2023 pairing and bounded annual unit'])
    labels = ['金額', '佔總資產比', '金額', '佔總資產比', '金額同比變動', '佔總資產比重同比增減']
    for line, metric, group, values in SF_RECORDS:
        items = own(line)
        assert [(f['subject'], f['attribute'], f['value']) for f in items] == [(metric, label, value) for label, value in zip(labels, values, strict=True)]
        for i, f in enumerate(items):
            expected = {'period_basis': '於12月31日', 'unit': '人民幣千元' if i in (0, 2) else '%'}
            expected.update({'period': '2024年' if i < 2 else '2023年'} if i < 4 else {'from_period': '2023年', 'to_period': '2024年'})
            if i in (0, 2):
                expected['currency'] = '人民幣'
            assert f['qualifiers'] == expected
            assert f['identity_facets']['group'] == group
            assert f['scope'] == ['資產及負債', '主要資產和負債項目變動情況']
            assert any(e['text'] == group and e['source']['lines'] == [next(k for k, v in groups.items() if v == group)] * 2 for e in f['row_evidence'])
        record(line, 'six_column_classified_record', [metric, group, labels, values])
    field_labels = {910: '經營活動產生的現金淨額', 912: '投資活動使用的現金淨額', 914: '融資活動使用的現金淨額',
                    944: '合同資產', 946: '以公允價值計量且變動計入當期損益的金融資產', 948: '借款', 950: '庫存股'}
    for line, triples in SF_NARRATIVES.items():
        items = own(line)
        assert [(f['subject'], f['attribute'], f['value']) for f in items] == triples
        assert [(f['subject'], f['attribute'], f['value']) for f in own(line, operands)] == SF_OPERANDS[line]
        scope = ['現金流'] if line < 916 else ['資產及負債', '主要資產和負債項目變動情況']
        assert all(f['scope'] == scope + [field_labels[line]] for f in items + own(line, operands))
        for i, f in enumerate(items):
            q = f['qualifiers']
            assert q['actor'] == '本集團'
            assert q['period'] == ('2024年' if line < 916 else '2024年12月31日')
            assert q['unit'] == ('億元' if i % 2 == 0 else '%')
            if line in (912, 914):
                assert q['flow_direction'] == 'outflow'
                assert _semantic_literal(graph['sources'], f['qualifier_sources']['flow_direction']) == '流出'
            if i % 2 == 0:
                assert q['currency'] == '人民幣' and 'circumstances' not in q
            else:
                assert q['from_period'] == ('2023年同期' if line < 916 else '2023年末')
                assert q['change_direction'] == ('decrease' if line in (912, 948, 950) else 'increase')
                cause, = q['circumstances']
                assert (cause['operator'], cause['direction'], cause['degree'], cause['simultaneous']) == ('cause', 'operand_to_child', '主要', False)
                assert cause.get('combined', False) == (line in (910, 912, 914))
                assert cause.get('non_exhaustive', False) == (line in (912, 914))
                if line in (910, 912, 914):
                    assert cause['operand']['shared_actor'] == '本集團'
            if line == 948:
                assert q['parent_metric'] == ('非流動負債' if i < 2 else '流動負債') and q['membership_operator'] == '中的'
        record(line, 'source_bound_narrative_and_causes', {'main': triples, 'noncounting_operands': SF_OPERANDS[line],
            'amounts_not_cause_operands': True, 'cause_owners': [1, 3] if line == 948 else [1],
            'main_degree': '主要', 'combined': line in (910, 912, 914), 'non_exhaustive': line in (912, 914)})
    for f in own(946):
        assert [(d['role'], d['marker'], d['child']['head']) for d in f['subject_phrase']['parts']] == [
            ('measurement_basis', '計量', '公允價值'), ('valuation_change_recognition', '變動計入', '當期損益')]
    nested = [n for n in walk(own(914, operands)) if n.get('kind') == 'proposition']
    assert {('發行', 'H股股份'), ('募集', '資金')} <= {(n.get('attribute'), n.get('object')) for n in nested}
    net_borrowing = own(914, operands)[0]['subject_phrase']
    assert net_borrowing['head'] == '淨流出'
    assert [(d['role'], d['child']['head']) for d in net_borrowing['parts']] == [('flow_item', '借款')]
    repurchase = [n for n in walk(own(950, operands)) if n.get('kind') == 'proposition' and n.get('attribute') == '購回']
    assert repurchase and all((n['subject'], n['object']) == ('本公司', '股份') for n in repurchase)
    projection = evaluation_projection(graph)
    _check_references(projection, lambda s: _semantic_literal(graph['sources'], s), _reference_sources(projection))
    reference, = graph['explicit_references']
    assert reference['owner_proof']['owner'] == {'identity': {'role': 'difference_explanation', 'left_metric': '經營活動產生的現金淨額',
        'right_metric': '淨利潤', 'actor': '本集團', 'period': '2024年'}, 'scope': ['現金流']}
    # This sentence prints its own pair; the bold preceding amount label is
    # not an additional heading or a substitute reference-owner identity.
    assert reference['target'] == {'role': 'reference_target', 'kind': 'numbered_reference', 'reference_kind': 'note', 'identifier': '34(a)', 'document': '合併財務報表'}
    assert reference['source']['lines'] == [910, 910]
    for line, label in headings.items():
        assert targets[line]['text'] == label and not own(line)
        record(line, 'heading', 'literal, selected hierarchy and content scope; no independent amount')
    assert any(e['type'] == 'heading_parent' and e['left'] == '資產及負債' and e['right'] == '主要資產和負債項目變動情況' for e in graph['relations'])
    for line, label in groups.items():
        assert targets[line]['text'] == label and targets[line]['has_children'] and not own(line)
        assert all(any(e['text'] == label and e['source']['lines'] == [line, line] for e in f['row_evidence'])
                   for f in facts if f.get('identity_facets', {}).get('group') == label)
        record(line, 'financial_classification_parent', 'actual parent identity of separately bound child records; never an amount')
    for line in (900, 920):
        assert not own(line)
        record(line, 'printed_bounded_schema', 'full literal, printed period basis, currency/unit and actual following record bindings')
    for fact in facts + operands:
        assert _semantic_literal(graph['sources'], fact['value_source']) == fact['value']
        if fact.get('predicate'):
            assert _semantic_literal(graph['sources'], fact['predicate_source']) == fact['predicate']
        if fact.get('subject') and fact.get('predicate'):
            assert _semantic_literal(graph['sources'], fact['subject_source']) == fact['subject']
        assert any(e.get('type') == 'field_binding' and e.get('fact_id') == fact['id']
                   for e in graph['relations'] + graph['operand_relations'])
    retained = ('text', 'source', 'role', 'kind')
    assert transport['T_literal_projection'] == [{k: n.get(k) for k in retained} for n in graph['nodes'] if n['id'] in graph['projections']['T']]
    assert len(results) == len(targets) == 40 and len(facts) == 133 and len(operands) == 12
    assert graph['semantic_complete'] and not graph['unresolved']
    return {'purpose': 'independent_hand_authored_complete_selected_source_oracle_not_quality_grades',
        'status': 'passed', 'all_authorized_sources': 40, 'previously_explained_sources_included': True,
        'source_records': sorted(results, key=lambda r: r['line']), 'facts': 133, 'noncounting_operands': 12,
        'cause_scope_relations': 8, 'explicit_difference_reference': 'two printed metrics, group actor, 2024 and consolidated note 34(a)',
        'fresh_production_compile_matches_saved_current': BIND_CURRENT, 'source_preservation': 'authorized source arrays, selection and T literal projection unchanged',
        'oracle_values_supplied_to_runtime': False, 'actual_expected_used_as_candidate': False,
        'candidate_read': False, 'pdf_or_image_read': False, 'quality_acceptance': False}


SINOPEC_AMOUNTS = {
    752: ('總資產', '20,814', '比上年末增加', '567'),
    754: ('流動資產', '5,245', '比上年末減少', '99'),
    756: ('非流動資產', '15,569', '比上年末增加', '667'),
    758: ('總負債', '11,093', '比上年末增加', '404'),
    760: ('流動負債', '6,732', '比上年末增加', '262'),
    762: ('非流動負債', '4,361', '比上年末增加', '142'),
    764: ('股東應佔權益', '8,158', '比上年末增加', '128'),
    778: ('經營活動現金淨流入', '1,494', '同比減少現金流入', '121'),
    780: ('投資活動現金淨流出', '1,612', '同比增加流出', '54'),
    782: ('融資活動現金淨流出', '192', '同比增加流出', '420'),
    860: ('總資產', '20,848', '比上年末增加', '581'),
    862: ('非流動負債', '4,352', '比上年末增加', '143'),
    864: ('股東權益', '9,763', '比上年末增加', '176'),
}
SINOPEC_FAIR_HEADERS = ['期初金額', '期末金額', '本期公允價值變動損益', '計入權益的累計公允價值變動',
                      '本期計提的減值', '資金來源', '本期購買金額', '本期出售/贖回金額', '其他變動']
SINOPEC_FAIR = [
    (806, '交易性金融資產', ['3', '4', '1', '–', '–', '–', '86', '(86)', '–']),
    (807, '基金', ['3', '4', '1', '–', '–', '–', '–', '–', '–']),
    (808, '衍生金融工具及現金流量套期工具', ['6,969', '(858)', '805', '(1,193)', '–', '–', '–', '(7,439)', '–']),
    (809, '應收款項融資', ['2,221', '2,613', '–', '–', '–', '–', '72,154', '(71,762)', '–']),
    (810, '其他權益工具投資', ['450', '416', '–', '(8)', '–', '–', '–', '(14)', '(12)']),
    (811, '合計', ['9,643', '2,175', '806', '(1,201)', '–', '–', '72,240', '(79,301)', '(12)']),
]
SINOPEC_DEPARTMENTS = [
    (824, '勘探及開發事業部', '297,249', '300,019'), (825, '煉油事業部', '1,481,502', '1,529,786'),
    (826, '營銷及分銷事業部', '1,714,358', '1,818,429'), (827, '化工事業部', '523,862', '515,307'),
    (828, '本部及其他', '1,457,226', '1,538,320'), (829, '抵銷分部間銷售', '(2,399,635)', '(2,489,646)'),
    (830, '合併營業收入', '3,074,562', '3,212,215'),
    (832, '勘探及開發事業部', '49,058', '37,976'), (833, '煉油事業部', '6,303', '19,358'),
    (834, '營銷及分銷事業部', '17,698', '25,531'), (835, '化工事業部', '(14,046)', '(10,273)'),
    (836, '本部及其他', '(914)', '1,915'), (837, '抵銷分部間銷售', '(630)', '750'),
    (838, '財務費用、投資收益及公允價值變動損益等', '14,788', '11,487'),
    (839, '合併營業利潤', '72,257', '86,744'),
]
SINOPEC_INDUSTRY_HEADERS = ['營業收入', '營業成本', '毛利率（註）', '營業收入比上年同期增減', '營業成本比上年同期增減', '毛利率比上年增減']
SINOPEC_INDUSTRY = [
    (868, '勘探及開發', ['297,249', '202,388', '25.2', '(0.9)', '(2.5)', '3.1']),
    (869, '煉油', ['1,481,502', '1,216,284', '1.6', '(3.2)', '(3.0)', '(0.8)']),
    (870, '營銷及分銷', ['1,714,358', '1,624,356', '5.1', '(5.7)', '(5.6)', '(0.1)']),
    (871, '化工', ['523,862', '517,448', '0.9', '1.7', '3.1', '(0.9)']),
    (872, '其他', ['1,457,226', '1,437,464', '1.3', '(5.3)', '(5.2)', '(0.1)']),
    (873, '抵銷分部間銷售', ['(2,399,635)', '(2,399,005)', '不適用', '不適用', '不適用', '不適用']),
    (874, '合計', ['3,074,562', '2,598,935', '6.8', '(4.3)', '(4.1)', '(0.3)']),
]
SINOPEC_TRAINING = [
    (942, '馬永生', '董事長、非執行董事'), (943, '趙東', '副董事長、執行董事、總裁'),
    (944, '鍾韌', '非執行董事'), (945, '李永林', '執行董事、高級副總裁'),
    (946, '呂亮功', '執行董事、高級副總裁'), (947, '牛栓文', '執行董事、高級副總裁'),
    (948, '萬濤', '執行董事、高級副總裁'), (949, '喻寶才', '執行董事、高級副總裁'),
    (950, '徐林', '獨立非執行董事'), (951, '張麗英', '獨立非執行董事'),
    (952, '廖子彬', '獨立非執行董事'), (953, '張希良', '獨立非執行董事'),
]
SINOPEC_FINANCIAL_CAUSES = {
    754: [('存貨', '增加', '57'), ('現金及現金等價物與金融機構定期存款', '比2023年末減少', '180')],
    756: [('公司', '推進', '轉型升級'), ('煉化基地項目建設投資力度', '加大', ''),
          ('物業廠房設備及在建工程', '比上年末增加', '547'), ('', '加強', '對外合資合作'),
          ('於聯合營公司的權益', '比上年末增加', '109')],
    760: [('部分長期借款', '重分類為', '一年內到期的非流動負債')],
    762: [('', '發行', '低成本長期債券融資')],
    778: [('淨利潤', '減少', '')],
    780: [('', '加強', '對外合資合作'), ('投資聯合營企業', '增加', '47')],
    782: [('公司付息債務淨變動', '同比減少流入', '551'), ('定向增發', '同比增加流入', '120')],
    860: [('公司', '加大', '轉型升級投入'), ('固定資產及在建工程', '比上年末增加', '546')],
    862: [('', '發行', '低成本長期債券融資')],
}


def check_sinopec_training(graph, projected):
    collection = {'subject': '中國石化現任董事', 'collection': '參與培訓的情況'}
    for line, name, roles in SINOPEC_TRAINING:
        facts = [f for f in projected['business'] if f['source']['lines'] == [line, line]]
        assert [(f['subject'], f['attribute'], f['value'], f['identity_facets']) for f in facts] == [
            (name, attribute, value, {**({'field_domain': domain} if domain else {}), 'enumeration': collection}) for attribute, value, domain in [
                ('職位', roles, None), ('閱讀材料', '√', '法律、法規之更新'), ('培訓、講座', '√', '法律、法規之更新'),
                ('閱讀材料', '√', '公司會計/財務/經營管理情況'), ('調研', '√', '公司會計/財務/經營管理情況')]], line
        assert all(not f['qualifiers'] for f in facts)
        position = facts[0]['value_logic']
        parts = [p['head'] for c in position['parts'] if c.get('kind') == 'coordination' for p in c['children']] or [position['head']]
        assert parts == roles.split('、')
        for fact in facts:
            assert _semantic_literal(graph['sources'], fact['subject_source']) == name
            assert _semantic_literal(graph['sources'], fact['attribute_source']) == fact['attribute']
            assert len([e for e in projected['relations'] if e['type'] == 'record_label_scope' and e.get('fact_id') == fact['id']]) == 1
            assert fact['enumeration_evidence']['introduction_source']['lines'] == [940, 940]
            assert len([e for e in projected['relations'] if e['type'] == 'enumeration_membership' and e.get('fact_id') == fact['id']]) == 1
    assert not [u for u in graph['unresolved'] if 942 <= u['source']['lines'][0] <= 953]
    return {'reviewed_sources': 12, 'business_assertions': 60, 'marks': 48, 'whole_sample_acceptance': False}


def check_sinopec_financial(graph, projected, targets):
    """Hand-read financial assertions, including records formerly opaque."""
    def own(line):
        return [f for f in projected['business'] if f['source']['lines'] == [line, line]]

    def triples(line, expected):
        actual = [(f['subject'], f['attribute'], f['value']) for f in own(line)]
        assert actual == expected, (line, expected, actual)

    reviewed_assertions = set()
    for line, (metric, amount, change, delta) in SINOPEC_AMOUNTS.items():
        triples(line, [(metric, '為', amount), (metric, change, delta)])
        assert all(f['qualifiers']['unit'] == '億元' and f['qualifiers']['currency'] == '人民幣' for f in own(line))
        reviewed_assertions.add(line)
    for line, subject, values in SINOPEC_FAIR:
        triples(line, [(subject, label, value) for label, value in zip(SINOPEC_FAIR_HEADERS, values, strict=True)])
        for fact, header in zip(own(line), SINOPEC_FAIR_HEADERS, strict=True):
            assert _semantic_literal(graph['sources'], fact['attribute_source']) == header
            assert fact['identity_facets'].get('group', []) == (['交易性金融資產'] if line == 807 else [])
            assert fact['qualifiers']['table_caption'] == '與公允價值計量相關的項目'
            assert fact['qualifier_sources']['table_caption']['lines'] == [804, 804]
            if header == '資金來源':
                assert not {'unit', 'currency'} & fact['qualifiers'].keys()
            else:
                assert fact['qualifiers']['unit'] == '人民幣百萬元'
            if fact['value'] == '–':
                assert fact['semantic_type'] == 'printed_unspecified_value'
        reviewed_assertions.add(line)
    for line, subject, current, previous in SINOPEC_DEPARTMENTS:
        metric = '營業收入' if line < 831 else '營業利潤/（虧損）'
        triples(line, [(subject, metric, current), (subject, metric, previous)])
        for fact, year in zip(own(line), ['2024年', '2023年'], strict=True):
            assert fact['qualifiers']['period'] == year and fact['qualifiers']['unit'] == '人民幣百萬元'
            assert fact['attribute_source']['lines'] == ([823, 823] if line < 831 else [831, 831])
            assert fact['qualifier_sources']['unit']['lines'] == [821, 821]
            assert _semantic_literal(graph['sources'], fact['subject_source']) == subject
        reviewed_assertions.add(line)
    for line, subject, values in SINOPEC_INDUSTRY:
        triples(line, [(subject, label, value) for label, value in zip(SINOPEC_INDUSTRY_HEADERS, values, strict=True)])
        for index, fact in enumerate(own(line)):
            assert _semantic_literal(graph['sources'], fact['attribute_source']) == SINOPEC_INDUSTRY_HEADERS[index]
            if index < 2:
                assert fact['qualifiers']['unit'] == '人民幣百萬元'
            elif fact['value'] == '不適用':
                assert fact['semantic_type'] == 'printed_not_applicable'
            else:
                assert fact['qualifiers']['unit'] == '%' and 'currency' not in fact['qualifiers']
            if index in (3, 4):
                assert fact['qualifiers']['comparison_basis'] == '比上年同期'
            elif index == 5:
                assert fact['qualifiers']['comparison_basis'] == '比上年'
        reviewed_assertions.add(line)
    for line, metric, current, previous in [
            (772, '經營活動所得的現金流量淨額', '149,360', '161,475'),
            (773, '投資活動所用的現金流量淨額', '(161,240)', '(155,865)'),
            (774, '融資活動（所用）/所得的現金流量淨額', '(19,237)', '22,732'),
            (840, '歸屬於母公司股東的淨利潤', '50,313', '60,463')]:
        triples(line, [('', metric, current), ('', metric, previous)])
        assert [f['qualifiers']['period'] for f in own(line)] == ['2024年', '2023年']
        assert all(f['qualifiers']['unit'] == '人民幣百萬元' for f in own(line))
        reviewed_assertions.add(line)
    for line, metric, current, previous, delta in [
            (854, '總資產', '2,084,771', '2,026,674', '58,097'),
            (855, '非流動負債', '435,241', '420,943', '14,298'),
            (856, '股東權益', '976,293', '958,655', '17,638')]:
        triples(line, [('', metric, current), ('', metric, previous), (metric, '變化額', delta)])
        first, second, change = own(line)
        assert first['qualifiers']['period'] == '2024年12月31日' and first['qualifiers']['period_basis'] == '於'
        assert second['qualifiers']['period'] == '2023年12月31日' and second['qualifiers']['period_basis'] == '於'
        assert change['qualifiers']['from_period'] == '2023年12月31日' and change['qualifiers']['to_period'] == '2024年12月31日'
        assert 'period' not in change['qualifiers'] and all(f['qualifiers']['unit'] == '人民幣百萬元' for f in own(line))
        reviewed_assertions.add(line)
    explicit = {
        768: [('下表', '列示', '本公司2024年及2023年合併現金流量表主要項目')],
        784: [('現金及現金等價物', '為', '913')],
        796: [('研究及開發支出', '是指', '本公司與研究和開發相關的費用和投資支出'),
              ('研究開發支出', '為', '236'), ('費用支出', '', '152'), ('投資支出', '', '84')],
        798: [('環保支出', '是指', '本公司支付的標準的污染物清理費用'), ('環保支出', '包括', '排污裝置的資本化費用'),
              ('環保支出', '為', '184')],
        802: [('本公司', '建立', '與金融工具會計核算、信息披露相關的決策機制、業務流程和內部控制制度'),
              ('本公司', '健全', '與金融工具會計核算、信息披露相關的決策機制、業務流程和內部控制制度'),
              ('下表', '列示', '與公允價值計量相關的項目')],
        813: [('本公司', '開展', '商品類及貨幣類金融衍生品業務'), ('相關業務', '符合', '金融衍生品業務的監管要求'),
              ('相關業務', '運行', '規範'), ('相關業務', '實現', '平抑價格波動、穩定經營收益、防範市場風險的目標')],
        842: [('營業利潤', '實現', '723'), ('營業利潤', '同比減少', '145')],
        844: [('歸屬於母公司股東的淨利潤', '為', '503'), ('歸屬於母公司股東的淨利潤', '同比減少', '102'),
              ('歸屬於母公司股東的淨利潤', '降低', '16.8')],
        876: [('毛利率', '=', '（營業收入－營業成本、稅金及附加）/營業收入')],
    }
    for line, expected in explicit.items():
        triples(line, expected)
        reviewed_assertions.add(line)
    assert own(784)[0]['qualifiers']['period'] == '2024年期末'
    assert own(798)[1]['qualifiers']['polarity'] == 'negative'
    assert own(802)[1]['qualifiers']['manner'] == '持續'
    assert all(f['qualifiers']['period'] == '2024年' for f in own(813))
    assert own(844)[2]['qualifiers']['unit'] == '%' and 'currency' not in own(844)[2]['qualifiers']
    for line, expected in SINOPEC_FINANCIAL_CAUSES.items():
        operands = [n for n in graph['nodes'] if n['kind'] == 'semantic_operand' and n['source']['lines'] == [line, line]]
        assert [(f['subject'], f['attribute'], f['value']) for f in operands] == expected, line
        main, change = own(line)
        assert 'circumstances' not in main['qualifiers']
        cause, = change['qualifiers']['circumstances']
        assert cause['operator'] == 'cause' and cause['degree'] == '主要' and cause['direction'] == 'operand_to_child'
        wrapper, = [n for n in graph['logic'] if n.get('source', {}).get('lines') == [line, line]]
        assert wrapper['target_source'] == wrapper['child']['clauses'][1]['source']
        assert not [n for n in walk(wrapper['operand']) if n.get('kind') == 'circumstance_scope']
    summaries = graph['context']['financial_summary_contexts']
    assert [(c['parent']['text'], [m['text'] for m in c['members']]) for c in summaries] == [
        ('總資產', ['流動資產', '非流動資產']), ('總負債', ['流動負債', '非流動負債'])]
    for line in (754, 756):
        assert all(f['qualifiers']['actor'] == '本公司' and f['qualifiers']['period'] == '2024年12月31日' for f in own(line))
    for line in (758, 760, 762):
        assert all(not {'actor', 'period'} & f['qualifiers'].keys() for f in own(line))
    refs = {r['source']['lines'][0]: r for r in graph['explicit_references'] if r['source']['lines'][0] <= 880}
    assert set(refs) == {788, 792, 817, 880}
    assert refs[788]['target'] == {'role': 'reference_target', 'kind': 'document_location', 'document': '本報告',
                                   'title': '重要事項', 'topic': '重大擔保及其履行情況'}
    assert refs[792]['target'] == {'role': 'reference_target', 'kind': 'document_location', 'document': '本報告',
                                   'title': '經營業績回顧及展望', 'topic': '資本支出'}
    assert refs[817]['target']['pages'] == ['213', '213'] and refs[817]['target']['section'] == 'C'
    assert refs[817]['owner_proof']['owner']['identity'] == {'role': 'accounting_difference_explanation', 'actor': '本公司',
        'left_basis': '國際財務報告會計準則', 'right_basis': '中國企業會計準則'}
    assert [(m['accounting_basis'], m['identifier']) for m in refs[880]['target']['members']] == [
        ('中國企業會計準則', '3(27)'), ('國際財務報告會計準則', '1')]
    notes = [e for e in projected['relations'] if e['type'] == 'financial_note_scope']
    assert [(e['right']['subject'], e['right']['attribute'], e['left']) for e in notes] == [
        (subject, '毛利率（註）', {'note_label': '註', 'defined_metric': '毛利率'}) for _, subject, _ in SINOPEC_INDUSTRY]
    assert all(e['binding_evidence']['note_label_source']['lines'] == [876, 876] for e in notes)
    financial_facts = [f for f in projected['business'] if 752 <= f['source']['lines'][0] <= 880]
    assert len(financial_facts) == 191, len(financial_facts)
    assert {f['source']['lines'][0] for f in financial_facts} == reviewed_assertions
    assert not [u for u in graph['unresolved'] if 752 <= u['source']['lines'][0] <= 880]
    return {'business_assertions': 191, 'assertive_sources': sorted(reviewed_assertions),
            'financial_note_bindings': 7, 'whole_sample_acceptance': False}


SINOPEC_GOVERNANCE_CONTENT = {
    886: ('1 本報告期公司治理的完善情況', ['完成董事會、監事會換屆', '2024年－2026年', '綠色企業行動第二階段計劃']),
    888: ('1 本報告期公司治理的完善情況', ['不存在重大差異', '無異議', '沒有受到']),
    892: ('2 股東會', ['2024年6月28日', '2023年年度股東會', '2024年10月22日', '2024年10月23日']),
    896: ('3 董事、監事及其他高級管理人員的股本權益情況', ['2024年12月31日', '均未持有', '第352條', '權益及淡倉']),
    898: ('3 董事、監事及其他高級管理人員的股本權益情況', ['上述兩項制度不低於', '特定查詢後', '所有董事均確認']),
    902: ('4 公司相對於控股股東的獨立性情況', ['在業務、資產、財務等各方面具有獨立性', '未出現超越', '未發現控股股東']),
    906: ('5 與控股股東存在同業競爭方面的情況', ['參見「重要事項」', '相關主體主要承諾事項履行情況']),
    910: ('6 內部控制制度的健全和實施情況', ['同日披露', '內部控制評價報告和內部控制審計報告']),
    914: ('7 對子公司的管理控制情況', ['不同類型的子公司', '未發生達到重大標準', '也沒有']),
    918: ('8 高級管理人員考評和激勵機制', ['公正、透明', '績效評價標準與激勵約束機制']),
    924: ('(1) 《企業管治守則》遵循情況', ['本報告期內', '附錄C1', '守則條文']),
    930: ('A.1 企業策略、業務模式及文化', ['穩中求進', '中長期發展戰略', '為利益相關方創造價值']),
    932: ('A.1 企業策略、業務模式及文化', ['愛我中華、振興石化', '苦幹實幹', 'http://www.sinopec.com']),
    936: ('A.2 企業管治職能', ['董事會負責履行', '制定和批准', '《企業管治報告》中予以披露']),
    938: ('A.2 企業管治職能', ['董事、監事及高級管理人員參加培訓', '持續專業發展']),
    959: ('B.1 董事會組成、繼任及評核', ['決策機構', '由中國石化管理層落實']),
    961: ('B.1 董事會組成、繼任及評核', ['12名成員', '6名執行董事、6名非執行董事', '獨立非執行董事4名', '約佔董事會總人數的33%']),
    963: ('B.1 董事會組成、繼任及評核', ['年度確認書', '第3.13條', '董事會認為', '每年評估']),
    965: ('B.1 董事會組成、繼任及評核', ['包括但不限於', '女性董事現佔比8%', '至少一位女性董事']),
    967: ('B.1 董事會組成、繼任及評核', ['2024年公司女性員工比例為29.9%', '男女平等', '2024年可持續發展報告']),
    971: ('B.2 委任、重選和罷免', ['每屆任期均為3年', '連任時間不超過6年', '2024年6月', '本章節第11部分']),
    973: ('B.2 委任、重選和罷免', ['均經過股東會選舉', '沒有權力委任臨時董事']),
    975: ('B.2 委任、重選和罷免', ['全體董事', '足夠時間及精力']),
    979: ('B.3 提名委員會', ['張麗英女士任主任委員', '馬永生先生', '廖子彬先生', '同時也評估']),
    981: ('B.3 提名委員會', ['可聘請專業人員', '合理費用由中國石化承擔', '諮詢委員', '列入中國石化預算']),
    983: ('B.3 提名委員會', ['本報告期內', '召開4次會議', '獨立董事專門會議召開情況']),
    989: ('C.1 董事責任', ['每名董事均已於2024年6月28日', '法律意見', '責任保險以減少']),
    991: ('C.1 董事責任', ['非執行董事均享有與執行董事同等職權', '獨立非執行董事具有某些特定職權']),
    993: ('C.1 董事責任', ['全體董事已確認', '一直遵守', '標準不低於']),
    995: ('C.1 董事責任', ['定期出席', '建設性意見', '會議出席情況請參見']),
    999: ('C.2 主席及行政總裁', ['馬永生先生任董事長', '由全體董事選舉產生', '趙東先生任中國石化總裁', '由董事會提名並聘任']),
    1001: ('C.2 主席及行政總裁', ['所有董事', '充分、清晰、完整的資訊']),
    1003: ('C.2 主席及行政總裁', ['與獨立非執行董事單獨會面', '中長期發展規劃']),
    1005: ('C.2 主席及行政總裁', ['公開、積極討論', '重大決策事項充分深入討論']),
    1009: ('C.3 管理功能', ['董事會、管理層均書面訂立', '職權及授權', 'http://www.sinopec.com']),
    1013: ('C.4 董事會專門委員會', ['戰略委員會', '5位董事組成', '可持續發展委員會', '4位董事組成', '張希良先生']),
    1015: ('C.4 董事會專門委員會', ['須向董事會匯報', '均訂立工作規則', 'http://www.sinopec.com']),
    1019: ('C.5 獨立董事專門會議', ['應當披露的關聯交易', '全體獨立董事過半數同意後', '方可提交董事會審議']),
    1021: ('C.5 獨立董事專門會議', ['本報告期內', '召開2次獨立董事專門會議']),
    1025: ('C.6 董事會議事程序以及資料提供及使用', ['《董事會議事規則》', '議事程序有明確規定']),
    1027: ('C.6 董事會議事程序以及資料提供及使用', ['最少每季度召開一次', '14天前', '提前10天', '2024年', '7次董事會會議']),
    1029: ('C.6 董事會議事程序以及資料提供及使用', ['可以提出議案', '有權要求', '會前預先分發']),
    1031: ('C.6 董事會議事程序以及資料提供及使用', ['董事會秘書組織', '管理層負責', '並可於必要時尋求專業顧問']),
    1033: ('C.6 董事會議事程序以及資料提供及使用', ['指定的會議記錄人', '記錄並存檔', '董事審閱確認']),
    1035: ('C.6 董事會議事程序以及資料提供及使用', ['進行了評估', '認為', '聽取黨組織、監事會、管理層的意見']),
    1039: ('C.7 公司秘書', ['由董事長提名、董事會聘任', '向董事長、總裁匯報工作', '入職培訓及專業發展']),
    1041: ('C.7 公司秘書', ['協助董事', '持續向董事提供', '協助董事規範履職']),
    1043: ('C.7 公司秘書', ['本報告期內', '培訓時間達15小時以上']),
    1049: ('D.1 財務匯報', ['每個財政期間', '2024年財務報告', '不存在任何虛假記載', '個別及連帶責任']),
    1051: ('D.1 財務匯報', ['管理層每月向董事提供', '監管最新變化']),
    1053: ('D.1 財務匯報', ['內部控制機制', '向董事會及審計委員會提供']),
    1055: ('D.1 財務匯報', ['外部審計師', '對其審計責任做出了聲明']),
    1059: ('D.2 內部監控及風險管理', ['每年至少一次', '每年至少兩次', '旨在管理風險', '無法確保消除所有風險']),
    1061: ('D.2 內部監控及風險管理', ['COSO', '全要素內部控制', '總部及各企業全部納入', '董事會每年審議']),
    1063: ('D.2 內部監控及風險管理', ['信息披露制度和內幕知情人登記制度', '定期進行評估', '公司網站']),
    1065: ('D.2 內部監控及風險管理', ['每年組織開展年度風險評估', '定期跟蹤', '關注、監控與應對']),
    1067: ('D.2 內部監控及風險管理', ['ESG', '反腐敗和反賄賂法律', '董事會已經評估', '是否足夠', '充足性']),
    1069: ('D.2 內部監控及風險管理', ['董事會審議評價', '董事會認為', '風險管理有效']),
    1073: ('D.3 審計委員會', ['監督及評估內外部審計工作', '審閱公司的財務報告', '廖子彬先生任主任委員', '徐林先生、張麗英女士和張希良先生']),
    1075: ('D.3 審計委員會', ['召開了6次會議', '出具審閱意見', '沒有不同意見']),
    1077: ('D.3 審計委員會', ['可聘請專業人員', '合理費用由中國石化承擔', '應積極配合審計委員會']),
    1079: ('D.3 審計委員會', ['是否足夠', '管理層已履行', '暗中及以不具名方式', '接收、保留、處理']),
    1085: ('E.1 薪酬水平、組成及其披露', ['非執行董事不在公司領取薪酬', '獨立非執行董事的薪酬由股東會批准', '第41頁至第49頁']),
    1087: ('E.1 薪酬水平、組成及其披露', ['徐林先生任主任委員', '鍾韌先生', '廖子彬先生', '向董事會報告']),
    1089: ('E.1 薪酬水平、組成及其披露', ['諮詢董事長及總裁', '認為', '2024年履行了董事服務合同']),
    1091: ('E.1 薪酬水平、組成及其披露', ['可聘請專業人員', '合理費用由中國石化承擔', '列入中國石化預算', '應積極配合薪酬與考核委員會']),
    1093: ('E.1 薪酬水平、組成及其披露', ['本報告期內', '召開2次會議']),
    1099: ('F.1 有效溝通', ['實施股份回購並完成註銷', '股本結構和註冊資本', '2024年3月25日、2024年6月29日', '2024年3月24日、2024年6月28日']),
    1101: ('F.1 有效溝通', ['股利分配政策', '第67頁至第68頁']),
    1103: ('F.1 有效溝通', ['畢明建先生', '徐林先生', '年度網絡業績說明會', '半年度網絡業績說明會', '在符合監管規定的情況下']),
    1105: ('F.1 有效溝通', ['董事會秘書負責', '反饋給董事會或管理層', '持續監督及評估']),
    1109: ('F.2 股東會', ['每項實際獨立的事宜', '所有議案均以投票方式表決', '45日（不含會議召開當日）前']),
    1111: ('F.2 股東會', ['董事長主持召開', '外部審計師出席', '沒有提出需要各專門委員會回答', '股東年會和臨時股東會後']),
}


def check_sinopec_document(graph, authored, financial_review):
    """Hand-read scope/content obligations; never candidate self-comparison."""
    from moparse_eval.requirement_ast import validate_content_ast

    blocks = {block['source']['lines'][0]: block for block in graph['document_ast']['children']}
    targets = {target['reference']['lines'][0]: target for target in authored['targets']}
    assert len(blocks) == len(targets) == 202
    assert graph['content_comparison_ready']
    assert Counter(target['kind'] for target in targets.values()) == {'text': 105, 'heading': 45, 'item': 49, 'image_caption': 3}
    for line, (scope, obligations) in SINOPEC_GOVERNANCE_CONTENT.items():
        target, block = targets[line], blocks[line]
        assert target['kind'] == 'text' and block['scope'][-1] == scope, (line, scope, block['scope'])
        assert all(literal in target['text'] for literal in obligations), (line, obligations)
        validate_content_ast(block['content'], lambda source: _semantic_literal(graph['sources'], source))
        assert ''.join(n['text'] for n in block['content']['children']) == ''.join(target['text'].split())
    labels = {770, 788, 792, 804, 817, 821, 823, 831, 852, 858, 880, 940}
    assert targets[858]['text'] == '變動分析：'
    assert targets[823]['text'] == '營業收入' and targets[831]['text'] == '營業利潤/（虧損）'
    assert targets[940]['text'] == '中國石化現任董事參與培訓的情況如下：'
    assert {line for line, target in targets.items() if target['kind'] == 'image_caption'} == {776, 846, 848}
    reviewed = set(financial_review['assertive_sources']) | set(range(942, 954)) | set(SINOPEC_GOVERNANCE_CONTENT) | labels
    reviewed |= {line for line, target in targets.items() if target['kind'] in {'heading', 'image_caption'}}
    assert reviewed == set(targets), (set(targets) - reviewed, reviewed - set(targets))
    assert {graph['document_ast']['children'][i]['source']['lines'][0] for i in graph['source_form_units']} == set(SINOPEC_GOVERNANCE_CONTENT) | {1023, 1083}
    return {'status': 'passed', 'reviewed_sources': 202, 'governance_source_form_assertions': 73,
            'labels_and_reference_declarations': 12, 'heading_nodes': 45, 'caption_nodes': 3,
            'source_form_scope': 'ordered_content_and_document_ownership_not_unrestricted_paraphrase',
            'semantic_analysis_limitations_retained': len(graph['unresolved']),
            'candidate_read': False, 'candidate_self_comparison': False}


def review_sinopec_boundary():
    """Check complete document-content contract and independently typed finance."""
    import hashlib

    from moparse_eval.cli import code_identity
    from moparse_eval.requirement_graph import evaluation_projection

    sample_id = 'sinopec-finance-governance-p025-036'
    run = json.loads((ROOT / 'benchmark/runs/lite/run.json').read_text())
    manifest = json.loads((Path(run['dataset']) / 'manifest.json').read_text())
    sample = next(s for s in manifest['samples'] if s['id'] == sample_id)
    assert sample['document_id'] == 'complex-sinopec-2024-annual'
    assert sample['source_pages'] == list(range(25, 37))
    authored = read_expected(sample, ROOT / 'pdf_sample/parsing/expected')
    targets = {t['reference']['lines'][0]: t for t in authored['targets']}
    literal = ('2024年末本公司總資產為人民幣20,848億元，比上年末增加人民幣581億元。'
               '主要歸因於公司加大轉型升級投入，固定資產及在建工程比上年末增加人民幣546億元。')
    assert targets[860]['text'] == literal
    # Handwritten source cuts and meanings precede compilation. The outer
    # explanation contains both contents; it asserts no internal cause edge.
    spans = {'main': [0, 40], 'degree': [40, 42], 'cause_marker': [42, 45],
             'action': [45, 55], 'comma': [55, 56], 'quantified_change': [56, 79]}
    assert literal[45:55] == '公司加大轉型升級投入'
    assert literal[55:56] == '，'
    assert literal[56:79] == '固定資產及在建工程比上年末增加人民幣546億元'
    graph = compile_requirement_graph(authored, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=authored)
    projected = evaluation_projection(graph)
    financial_review = check_sinopec_financial(graph, projected, targets)
    training_review = check_sinopec_training(graph, projected)
    document_review = check_sinopec_document(graph, authored, financial_review)
    def own(line):
        return [f for f in projected['business'] if f['source']['lines'] == [line, line]]
    assert [(f['subject'], f['attribute'], f['value']) for f in own(860)] == [
        ('總資產', '為', '20,848'), ('總資產', '比上年末增加', '581')]
    assert [(f['subject'], f['attribute'], f['value']) for f in own(864)] == [
        ('股東權益', '為', '9,763'), ('股東權益', '比上年末增加', '176')]
    for line in (860, 864):
        for f in own(line):
            assert f['qualifiers']['actor'] == '本公司' and f['qualifiers']['period'] == '2024年末'
            assert f['qualifiers']['unit'] == '億元' and f['qualifiers']['currency'] == '人民幣'
    assert 'circumstances' not in own(860)[0]['qualifiers']
    assert all('circumstances' not in f['qualifiers'] for f in own(864))
    cause, = own(860)[1]['qualifiers']['circumstances']
    assert (cause['operator'], cause['degree'], cause['direction']) == ('cause', '主要', 'operand_to_child')
    assert cause['operand']['operator'] == 'and'
    wrapper, = [n for n in graph['logic'] if n['source']['lines'] == [860, 860]]
    assert [n['kind'] for n in wrapper['operand']['children']] == ['proposition', 'cjk_measurement_sequence']
    assert not any(n.get('kind') == 'circumstance_scope' for n in wrapper['operand']['children'])
    operands = [n for n in graph['nodes'] if n['kind'] == 'semantic_operand' and n['source']['lines'] == [860, 860]]
    assert [(n['subject'], n['attribute'], n['value']) for n in operands] == [
        ('公司', '加大', '轉型升級投入'), ('固定資產及在建工程', '比上年末增加', '546')]
    assert operands[1]['qualifiers']['unit'] == '億元' and operands[1]['qualifiers']['currency'] == '人民幣'
    assert 'period' not in operands[1]['qualifiers']
    assert not [p for p in graph['unresolved'] if p['source']['lines'] in ([860, 860], [864, 864])]
    assert not graph['semantic_complete']
    index = json.loads((CURRENT / 'index.json').read_text())
    row = next(r for r in index['records'] if r['sample_id'] == sample_id)
    if BIND_CURRENT:
        assert row['software_id'] == index['software_id'] == code_identity()['software_id']
        assert graph == json.loads((CURRENT / row['json']).read_text())
    selection = graph['source_obligation_inventory']['selection']
    assert len(graph['source_obligation_inventory']['sources']) == 202
    return {'status': 'passed', 'sample_id': sample_id,
            'complete_source_acceptance': True, 'all_authorized_sources_independently_reviewed': True,
            'acceptance_contract': 'document_ast_and_content_with_existing_typed_financial_semantics',
            'unrestricted_chinese_semantics_complete': False,
            'retained_sources': 202, 'sample_declaration': sample,
            'financial_review': financial_review,
            'training_review': training_review,
            'document_review': document_review,
            'selection_sha256': hashlib.sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest(),
            'authorized_sources_sha256': hashlib.sha256(json.dumps(graph['source_obligation_inventory']['sources'], sort_keys=True).encode()).hexdigest(),
            'original_source': targets[860]['reference'], 'literal': literal, 'independent_spans': spans,
            'independent_assertion': 'one outer major cause with action and collective financial change; no invented internal causal mechanism',
            'authorized_context_read': {str(line): targets[line]['text'] for line in [756, 860, 862, 864]},
            'semantic_analysis_limitations_retained': True, 'fresh_production_compile_matches_saved_current': BIND_CURRENT,
            'candidate_read': False, 'pdf_or_image_read': False, 'quality_acceptance': False}



def comparison_coverage_diagnosis(current, results, capability_evidence):
    """Summarize generated views along independent, overlapping dimensions."""
    import hashlib

    from moparse_eval.cli import code_identity
    from moparse_eval.requirement_gate import _digest

    identity = code_identity()['software_id']
    index = json.loads((current / 'index.json').read_text())
    assert index['software_id'] == identity and index['software_unchanged']
    verified = {}
    if capability_evidence is not None and capability_evidence.exists():
        evidence = json.loads(capability_evidence.read_text())
        if evidence.get('software_id') == identity and evidence.get('status') == 'passed':
            verified = evidence.get('verified_capabilities', {})
    accepted = {value['sample_id']: value for value in results.values() if value['status'] == 'passed'}
    rows = []
    for row in index['records']:
        graph_path = current / row['json']
        assert hashlib.sha256(graph_path.read_bytes()).hexdigest() == row['generated_view_sha256']
        graph = json.loads(graph_path.read_text())
        coverage = graph['comparison_coverage']
        assert _digest(coverage) == row['comparison_coverage_sha256']
        acceptance = accepted.get(row['sample_id'], {})
        independently_accepted = (acceptance.get('generated_view_sha256') == row['generated_view_sha256']
                                  and acceptance.get('comparison_coverage_sha256') == _digest(coverage))
        missing_capabilities = sorted(set(coverage['required_capabilities']) - set(verified))
        rows.append({'sample_id': row['sample_id'], 'comparison_contract_version': graph['comparison_contract_version'],
            'source_structure_complete': coverage['source_complete'] and coverage['structure_complete'],
            'comparison_responsibility_complete': coverage['responsibility_complete'],
            'unverified_capabilities': missing_capabilities,
            'independently_source_accepted': independently_accepted,
            'independently_contract_accepted': independently_accepted and not missing_capabilities and coverage['responsibility_complete'],
            'language_analysis_limitations': row['language_analysis_only'],
            'only_language_analysis_limitations': bool(row['language_analysis_only']) and coverage['responsibility_complete'],
            'input_scope_pending': row['input_scope_pending'],
            'semantic_complete': graph['semantic_complete'],
            'analysis_projection_units': row['layers'], 'comparison_requirement_counts': row['comparison_requirement_counts'],
            'blocking_obligations': [n['obligation_id'] for n in coverage['obligations'] if n['status'] == 'blocking'],
            'blocking_analysis_limits': [n['issue_id'] for n in coverage['analysis_limitations'] if n['status'] == 'blocking'],
            'comparison_coverage_sha256': row['comparison_coverage_sha256']})
    counts = {
        'source_or_structure_incomplete': sum(not r['source_structure_complete'] for r in rows),
        'comparison_obligations_uncovered': sum(not r['comparison_responsibility_complete'] for r in rows),
        'required_capabilities_not_independently_evidenced': sum(bool(r['unverified_capabilities']) for r in rows),
        'complete_requirements_lacking_independent_sample_acceptance': sum(
            r['comparison_responsibility_complete'] and not r['independently_source_accepted'] for r in rows),
        'independently_source_accepted': sum(r['independently_source_accepted'] for r in rows),
        'independently_contract_accepted': sum(r['independently_contract_accepted'] for r in rows),
        'only_language_analysis_limitations': sum(r['only_language_analysis_limitations'] for r in rows),
        'with_retained_input_scope': sum(bool(r['input_scope_pending']) for r in rows),
        'retained_input_scope_targets': sum(r['input_scope_pending'] for r in rows)}
    return {'comparison_contract_version': 'document_ast/1', 'software_id': identity,
            'source_index_sha256': hashlib.sha256((current / 'index.json').read_bytes()).hexdigest(),
            'dimensions_overlap': True, 'counts': counts, 'records': rows,
            'formal_execution_authorized': False, 'quality_scores_withheld': True,
            'capability_evidence': str(capability_evidence) if capability_evidence else None,
            'meaning': 'Language analysis, comparison coverage, independent sample acceptance and execution permission are separate.'}


if __name__ == '__main__':
    import argparse
    import hashlib
    import sys
    import traceback

    from moparse_eval.cli import code_identity

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current', type=Path, default=CURRENT)
    parser.add_argument('--fresh-only', action='store_true', help='Development check without asserting saved-view identity')
    parser.add_argument('--output', type=Path, help='Local validation record; never a quality result')
    parser.add_argument('--diagnosis-output', type=Path, help='Update the existing source-only diagnosis with contract dimensions')
    parser.add_argument('--comparison-evidence', type=Path, default=WORK / 'comparison-validation.json')
    args = parser.parse_args()
    CURRENT, BIND_CURRENT = args.current, not args.fresh_only
    identity = code_identity()
    result = {}
    checks = [('huawei', 'huawei-operating-results-p062-063', review),
              ('sf', 'sf-cashflow-assets-liabilities-p040-041', review_sf),
              ('sinopec', 'sinopec-finance-governance-p025-036', review_sinopec_boundary)]
    for name, sample_id, check in checks:
        try:
            value = check()
            value['sample_id'] = sample_id
            value['comparison_contract_version'] = 'document_ast/1'
            if BIND_CURRENT:
                from moparse_eval.requirement_gate import _digest

                graph = json.loads((CURRENT / 'samples' / (sample_id + '.json')).read_text())
                assert graph['comparison_coverage']['responsibility_complete']
                value['generated_view_sha256'] = hashlib.sha256((CURRENT / 'samples' / (sample_id + '.json')).read_bytes()).hexdigest()
                value['comparison_coverage_sha256'] = _digest(graph['comparison_coverage'])
        except (AssertionError, ValueError, KeyError) as error:
            # Keep the incoming hand-authored assertion. A discovered error
            # must fail its original acceptance, never silently turn green.
            value = {'status': 'failed', 'error': type(error).__name__, 'detail': str(error),
                     'traceback': traceback.format_exc(), 'complete_source_acceptance': False}
        result[name] = value
    output = {'purpose': 'source_only_software_oracles_not_quality_grades', 'software': identity,
              'validation_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'command': [sys.executable, *sys.argv], 'bind_current': BIND_CURRENT,
              'source_index_sha256': hashlib.sha256((CURRENT / 'index.json').read_bytes()).hexdigest(),
              'results': result, 'candidate_read': False, 'pdf_or_image_read': False,
              'quality_acceptance': False, 'software_unchanged': identity['software_id'] == code_identity()['software_id']}
    if args.diagnosis_output:
        assert BIND_CURRENT, 'Coverage diagnosis requires current-bound independent Oracles'
        diagnosis = json.loads(args.diagnosis_output.read_text())
        diagnosis['comparison_contract_coverage'] = comparison_coverage_diagnosis(CURRENT, result, args.comparison_evidence)
        args.diagnosis_output.write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2) + '\n')
    if args.output:
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({name: {k: v for k, v in value.items() if k not in {'source_records', 'traceback'}} for name, value in result.items()}, ensure_ascii=False))
    raise SystemExit(0 if all(v['status'] == 'passed' for v in result.values()) else 1)
