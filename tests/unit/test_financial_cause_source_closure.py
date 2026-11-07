"""Independent invented financial source oracles, fixed before compilation."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import validate_requirement_graph
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import compiled

OPERATING = ('2029年本集團運輸現金淨額為人民幣15億元，相較2028年同期增長12%，'
             '主要由於本集團盈利增長，以及優化經營性現金流管理綜合影響所致。')
INVESTING = ('2029年本集團投資現金淨額流出為人民幣12億元，相較2028年同期下降7%，'
             '主要由於本集團購買物業廠房設備淨現金流出減少、取得子公司及其他投資的淨現金流出減少，'
             '以及購買結構性存款淨現金流出增加等綜合影響。')
FINANCING = ('2029年本集團融資現金淨額流出為人民幣19億元，相較2028年同期增長16%，'
             '主要由於本集團借款淨流出增加，分配股利淨流出增加，以及發行H股股份募集資金流入等綜合影響。')
ASSET = '於2029年12月31日，本集團合同資產為人民幣8億元，較2028年末增長15%，主要由於本集團業務增長所致。'
FINANCIAL = ('於2029年12月31日，本集團以公允價值計量且變動計入當期損益的金融資產為人民幣17億元，'
             '較2028年末增長16%，主要是結構性存款增加導致。')
LOANS = ('於2029年12月31日，本集團非流動負債中的借款為人民幣17億元，較2028年末下降9%，'
         '流動負債中的借款為人民幣11億元，較2028年末下降6%，主要是償還借款導致。')
SHARES = '於2029年12月31日，本集團庫存股為人民幣6億元，較2028年末下降15%，主要是註銷本公司購回股份導致。'
REFERENCE = '本集團2029年運輸現金淨額與淨利潤之間的差異說明請詳見合併財務報表附註8(b)。'

# These tuples are hand-authored expectations, not generated reader output.
ORACLES = [
    (OPERATING, ['15', '12'], [('盈利', '增長', ''), ('', '優化', '經營性現金流管理')], [1]),
    (INVESTING, ['12', '7'], [('購買物業廠房設備淨現金流出', '減少', ''),
                            ('取得子公司及其他投資的淨現金流出', '減少', ''),
                            ('購買結構性存款淨現金流出', '增加', '')], [1]),
    (FINANCING, ['19', '16'], [('借款淨流出', '增加', ''), ('分配股利淨流出', '增加', ''),
                             ('發行H股股份募集資金', '流入', '')], [1]),
    (ASSET, ['8', '15'], [('業務', '增長', '')], [1]),
    (FINANCIAL, ['17', '16'], [('結構性存款', '增加', '')], [1]),
    (LOANS, ['17', '9', '11', '6'], [('', '償還', '借款')], [1, 3]),
    (SHARES, ['6', '15'], [('', '註銷', '本公司購回股份')], [1]),
]


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def compare(required, text):
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    if result['publishable']:
        validate_evidence(result)
    else:
        with pytest.raises(ValueError):
            validate_evidence(result)
    return result


@pytest.mark.parametrize('text,values,operands,owners', ORACLES)
def test_independent_financial_cause_oracles_through_the_complete_production_chain(tmp_path, text, values, operands, owners):
    graph, required = compiled(tmp_path, text)
    assert [f['value'] for f in required['business']] == values
    assert [(n['subject'], n['attribute'], n['value']) for n in graph['nodes'] if n['kind'] == 'semantic_operand'] == operands
    assert [i for i, f in enumerate(required['business']) if f['qualifiers'].get('circumstances')] == owners
    for i in owners:
        cause, = required['business'][i]['qualifiers']['circumstances']
        assert cause['operator'] == 'cause' and cause['degree'] == '主要' and cause['direction'] == 'operand_to_child'
        assert required['business'][i]['qualifiers']['from_period'].startswith('2028年')
        assert required['business'][i]['qualifiers']['period'].startswith('2029年')
    result = compare(required, text)
    assert result['publishable'], result['blockers']
    assert all(result['layers'][k]['score'] == 100 for k in ('T', 'L', 'B'))


def test_classifications_and_shared_actor_do_not_create_repayment_amount_or_balance(tmp_path):
    _, required = compiled(tmp_path, LOANS)
    for f, parent in zip(required['business'], ['非流動負債'] * 2 + ['流動負債'] * 2, strict=True):
        assert f['qualifiers']['parent_metric'] == parent
        assert f['qualifiers']['membership_operator'] == '中的'
        assert f['qualifiers']['actor'] == '本集團'
    assert len(required['business']) == 4
    assert [f['qualifiers']['unit'] for f in required['business']] == ['億元', '%', '億元', '%']


def test_financial_designation_and_repurchase_have_internal_source_bound_roles(tmp_path):
    graph, required = compiled(tmp_path, FINANCIAL + '\n\n' + SHARES)
    for f in required['business'][:2]:
        phrase = f['subject_phrase']
        assert phrase['head'] == '金融資產'
        assert [(d['role'], d['marker'], d['child']['head']) for d in phrase['parts']] == [
            ('measurement_basis', '計量', '公允價值'), ('valuation_change_recognition', '變動計入', '當期損益')]
    repurchase = [n for n in walk(graph['nodes']) if n.get('kind') == 'proposition' and n.get('attribute') == '購回']
    assert repurchase and all((p['subject'], p['object']) == ('本公司', '股份') for p in repurchase)


def test_net_outflow_has_its_actual_metric_and_direction_not_a_truncated_actor(tmp_path):
    graph, required = compiled(tmp_path, FINANCING)
    assert all(f['qualifiers']['flow_direction'] == 'outflow' for f in required['business'])
    operand = next(n for n in graph['nodes'] if n['kind'] == 'semantic_operand' and n['subject'] == '借款淨流出')
    phrase = operand['subject_phrase']
    assert phrase['head'] == '淨流出'
    assert [(d['role'], d['child']['head']) for d in phrase['parts']] == [('flow_item', '借款')]
    assert not any(n.get('subject') == '借款淨' for n in walk(phrase))


@pytest.mark.parametrize('text', [OPERATING, INVESTING, FINANCING, ASSET, FINANCIAL, LOANS, SHARES])
@pytest.mark.parametrize('error', ['actor', 'year', 'value', 'unit', 'direction', 'cause_to_condition', 'cause_deletion'])
def test_every_financial_family_rejects_wrong_roles_measurements_and_removed_causes(tmp_path, text, error):
    _, required = compiled(tmp_path, text)
    if error == 'actor':
        candidate = text.replace('本集團', '本公司')
    elif error == 'year':
        candidate = text.replace('2028', '2027')
    elif error == 'value':
        candidate = text.replace('億元', '0億元', 1)
    elif error == 'unit':
        candidate = text.replace('億元', '萬元', 1)
    elif error == 'direction':
        candidate = text.replace('增長', '下降') if '增長' in text else text.replace('下降', '增長')
    elif error == 'cause_to_condition':
        candidate = text.replace('主要由於', '只有').replace('主要是', '只有')
    else:
        candidate = text[:text.index('，主要')] + '。'
    result = compare(required, candidate)
    assert result['layers']['B']['numerator'] < result['layers']['B']['denominator']
    if error in {'value', 'unit'}:
        assert result['layers']['L']['numerator'] > 0
    else:
        assert result['layers']['L']['numerator'] < result['layers']['L']['denominator']


@pytest.mark.parametrize('text', [OPERATING, INVESTING, FINANCING, ASSET])
def test_legal_cause_marker_change_preserves_BL_but_retains_literal_T_difference(tmp_path, text):
    _, required = compiled(tmp_path, text)
    result = compare(required, text.replace('由於', '因為'))
    assert result['publishable'], result['blockers']
    assert result['layers']['T']['score'] < 100
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100


def test_difference_reference_has_two_metrics_its_own_period_and_document_target(tmp_path):
    graph, required = compiled(tmp_path, OPERATING + REFERENCE)
    reference, = graph['explicit_references']
    assert reference['owner_proof']['owner']['identity'] == {
        'role': 'difference_explanation', 'actor': '本集團', 'period': '2029年',
        'left_metric': '運輸現金淨額', 'right_metric': '淨利潤'}
    assert reference['target'] == {'role': 'reference_target', 'kind': 'numbered_reference',
                                  'reference_kind': 'note', 'identifier': '8(b)', 'document': '合併財務報表'}
    assert [f['value'] for f in required['business']] == ['15', '12']
    assert compare(required, OPERATING + REFERENCE)['publishable']


@pytest.mark.parametrize('old,new', [('淨利潤', '總資產'), ('8(b)', '9(b)'), ('2029', '2028'), ('本集團', '本公司')])
def test_difference_pair_reference_or_owner_changes_lose_L_without_erasing_independent_B(tmp_path, old, new):
    _, required = compiled(tmp_path, OPERATING + REFERENCE)
    result = compare(required, OPERATING + REFERENCE.replace(old, new))
    assert result['layers']['L']['numerator'] < result['layers']['L']['denominator']
    assert result['layers']['B']['numerator'] == result['layers']['B']['denominator'] == 2


@pytest.mark.parametrize('mutation', ['cause_target', 'cause_direction', 'group_actor_source', 'operand_source',
                                    'combination', 'non_exhaustive', 'scope_edge', 'relation_only', 'all_relations',
                                    'reference_owner_span', 'reference_target_neighbor', 'classification', 'nominal_parts'])
def test_all_words_retained_cannot_replace_semantics_or_borrow_adjacent_source(tmp_path, mutation):
    text = LOANS + '\n\n' + FINANCIAL + '\n\n' + INVESTING + '\n\n' + REFERENCE
    _, required = compiled(tmp_path, text)
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    wrapper = actual['logical_statements'][0]
    if mutation == 'cause_target':
        wrapper['target_sources'][0] = deepcopy(wrapper['child']['clauses'][0]['source'])
    elif mutation == 'cause_direction':
        wrapper['direction'] = 'child_to_operand'
    elif mutation == 'group_actor_source':
        actual['logical_statements'][2]['operand']['shared_actor_source']['lines'] = [1, 1]
    elif mutation == 'operand_source':
        actual['semantic_operands'][0]['object_source']['lines'] = [3, 3]
    elif mutation in {'combination', 'non_exhaustive'}:
        actual['logical_statements'][2]['combined' if mutation == 'combination' else mutation] = False
    elif mutation in {'scope_edge', 'relation_only', 'all_relations'}:
        actual['relations'] = [] if mutation == 'all_relations' else [e for e in actual['relations']
                            if e['type'] != ('narrative_circumstance_scope' if mutation == 'scope_edge' else 'reference_directive_scope')]
    elif mutation.startswith('reference_'):
        ref = actual['explicit_references'][0]
        ref['owner_roles']['left']['source']['lines'] = [1, 1] if mutation == 'reference_owner_span' else [5, 5]
        if mutation == 'reference_target_neighbor':
            ref['target_source']['lines'] = [5, 5]
    elif mutation == 'classification':
        actual['business'][0]['qualifiers']['parent_metric'] = '流動負債'
    else:
        actual['business'][4]['subject_phrase']['parts'] = []
    result = grade_layers(required, actual)
    assert result['layers']['T']['score'] == 100
    assert not result['publishable'] or any(result['layers'][k]['score'] < 100 for k in ('B', 'L'))
    if not result['publishable']:
        with pytest.raises(ValueError):
            validate_evidence(result)


@pytest.mark.parametrize('mutation', ['cause_target', 'cause_edge', 'operand', 'financial_dependency', 'reference_edge'])
def test_requirement_source_audit_rejects_deleted_or_borrowed_relationships(tmp_path, mutation):
    graph, _ = compiled(tmp_path, LOANS + '\n\n' + FINANCIAL + '\n\n' + REFERENCE)
    changed = deepcopy(graph)
    if mutation == 'cause_target':
        changed['logic'][0]['target_sources'].pop(0)
    elif mutation in {'cause_edge', 'reference_edge'}:
        target = 'narrative_circumstance_scope' if mutation == 'cause_edge' else 'reference_directive_scope'
        changed['relations'] = [r for r in changed['relations'] if r['type'] != target]
    elif mutation == 'operand':
        changed['nodes'] = [n for n in changed['nodes'] if n['kind'] != 'semantic_operand']
    else:
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'narrative_cjk_nominal_scope']
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


@pytest.mark.parametrize('change', ['quantity_scale', 'joint_scope', 'exhaustiveness', 'factor_direction'])
def test_lossless_quantity_change_and_semantically_different_cause_restrictions(tmp_path, change):
    _, required = compiled(tmp_path, INVESTING)
    candidate = {
        'quantity_scale': INVESTING.replace('12億元', '120000萬元'),
        'joint_scope': INVESTING.replace('綜合影響', '影響'),
        'exhaustiveness': INVESTING.replace('等綜合', '綜合'),
        'factor_direction': INVESTING.replace('存款淨現金流出增加', '存款淨現金流出減少'),
    }[change]
    result = compare(required, candidate)
    if change == 'quantity_scale':
        assert result['publishable'], result['blockers']
        assert result['layers']['T']['score'] < 100
        assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    else:
        assert result['layers']['B']['numerator'] < result['layers']['B']['denominator']
        assert result['layers']['L']['numerator'] < result['layers']['L']['denominator']


def test_references_and_causes_cannot_borrow_a_new_heading_or_independent_record(tmp_path):
    text = OPERATING + REFERENCE + '\n\n# 新業務\n\n' + ASSET
    _, required = compiled(tmp_path, text)
    candidate = OPERATING + '\n\n# 新業務\n\n' + REFERENCE + ASSET
    result = compare(required, candidate)
    assert result['layers']['L']['numerator'] < result['layers']['L']['denominator']
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    actual['business'][-1]['qualifiers']['circumstances'] = deepcopy(actual['business'][1]['qualifiers']['circumstances'])
    result = grade_layers(required, actual)
    assert result['layers']['T']['score'] == 100
    assert not result['publishable']


@pytest.mark.parametrize('text', [
    ASSET.replace('本集團業務增長', '本集團業務增長人民幣9億元'),
    LOANS.replace('非流動負債中的', '未知分類中的'),
    OPERATING.replace('主要由於', '如果'),
])
def test_unsupported_source_is_retained_as_local_unresolved_not_new_amount_or_ambiguity(tmp_path, text):
    from moparse_eval.requirement_graph import compile_requirement_graph
    from tests.unit.test_cjk_circumstance_contract import authored

    source = authored(tmp_path, text)
    graph = compile_requirement_graph(source)
    validate_requirement_graph(graph, expected=source)
    assert not graph['semantic_complete'] and graph['unresolved']
    assert all(n.get('value') != '9' for n in graph['nodes'] if n['id'] in graph['projections']['B'])
