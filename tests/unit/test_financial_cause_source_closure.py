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
         '流動負債中的借款為人民幣11億元，較2028年末下降6%，兩項變化均主要是償還借款導致。')
IMPLICIT_LOANS = LOANS.replace('兩項變化均', '')
AMBIGUOUS_LOANS = IMPLICIT_LOANS.replace('償還借款', '優化資金管理')
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


def compare(required, text, *, allow_unresolved=False):
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    if not allow_unresolved:
        assert not actual['blockers'], actual['blockers']
        assert not actual['pending_requirements'], actual['pending_requirements']
        assert not [i for i in actual['candidate_issues'] if i.get('category') == 'software_unsupported']
    result = grade_layers(required, actual)
    if not allow_unresolved:
        assert result['publishable'], result['blockers']
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
        candidate = text[:text.rfind('，', 0, text.index('主要'))] + '。'
    result = compare(required, candidate, allow_unresolved=error == 'cause_to_condition')
    if error in {'actor', 'year', 'value', 'unit', 'direction'}:
        facts = required['business']
        wrong = ({facts[0]['id']} if error in {'value', 'unit'} else
                 {f['id'] for i, f in enumerate(facts) if error == 'actor' or i % 2 == 1})
        outcomes = {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'}
        assert outcomes == {f['id']: 'incorrect' if f['id'] in wrong else 'correct' for f in facts}
        assert result['layers']['B']['denominator'] == len(facts)
        assert result['layers']['L']['denominator'] == len(required['relations'])
        if error in {'value', 'unit'}:
            assert all(o['outcome'] == 'correct' for o in result['outcomes'] if o['layer'] == 'L')
        unaffected = {f['id'] for f in facts} - wrong
        independent = [o for o in result['outcomes'] if o['layer'] == 'L'
                       and o['expected'].get('fact_id') in unaffected]
        if unaffected:
            assert independent
            assert all(o['outcome'] == 'correct' for o in independent)
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
    result = compare(required, candidate, allow_unresolved=change == 'joint_scope')
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


# Scope answers are written independently of causal_targets and production AST.
# Every case owns repayment as a cause operand; balances 0/2 are never targets.
@pytest.mark.parametrize('marker,owners,excluded', [
    ('兩項變化均', [1, 3], [0, 2]),
    ('两项变化共同', [1, 3], [0, 2]),
    ('均', [1, 3], [0, 2]),
    ('僅後者的變化', [3], [0, 1, 2]),
    ('僅前者的變化', [1], [0, 2, 3]),
])
def test_independent_shared_former_and_latter_cause_scopes(tmp_path, marker, owners, excluded):
    text = LOANS.replace('兩項變化均', marker).replace('償還借款導致', '償還借款等綜合影響導致')
    graph, required = compiled(tmp_path, text)
    facts = required['business']
    assert [(n['subject'], n['attribute'], n['value']) for n in graph['nodes']
            if n['kind'] == 'semantic_operand'] == [('', '償還', '借款')]
    assert [i for i, f in enumerate(facts) if f['qualifiers'].get('circumstances')] == owners
    for i in owners:
        cause, = facts[i]['qualifiers']['circumstances']
        assert (cause['degree'], cause['direction'], cause['non_exhaustive'], cause['combined']) == (
            '主要', 'operand_to_child', True, True)
    assert all('circumstances' not in facts[i]['qualifiers'] for i in excluded)
    result = compare(required, text)
    assert all(result['layers'][k]['score'] == 100 for k in ('T', 'L', 'B'))


@pytest.mark.parametrize('text', [
    AMBIGUOUS_LOANS,
    AMBIGUOUS_LOANS.replace('主要是優化資金管理導致', '主要受本集團優化資金管理的影响'),
    AMBIGUOUS_LOANS.replace('流動負債中的借款為人民幣11', '本公司流動負債中的借款為人民幣11'),
    AMBIGUOUS_LOANS.replace('流動負債中的借款為人民幣11', '非流動負債中的借款為人民幣11'),
])
def test_no_scope_word_equal_names_or_equal_classifications_cannot_prove_shared_cause(tmp_path, text):
    from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection
    from tests.unit.test_cjk_circumstance_contract import authored

    expected = authored(tmp_path, text)
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    assert not graph['semantic_complete']
    ambiguity, = [p for p in graph['unresolved'] if p['reason'] == 'cjk_causal_scope_evidence_unresolved']
    assert ambiguity['category'] == 'software_unsupported'
    assert [h['scope'] for h in ambiguity['attachment_hypotheses']] == ['latter_change', 'joint_changes']
    assert [len(h['target_sources']) for h in ambiguity['attachment_hypotheses']] == [1, 2]
    facts = evaluation_projection(graph)['business']
    assert [f['value'] for f in facts] == ['17', '9', '11', '6']
    assert all('circumstances' not in f['qualifiers'] for f in facts)
    assert not any(e['type'] == 'narrative_circumstance_scope' for e in graph['relations'])


def test_different_actors_independent_records_and_each_own_cause_do_not_share(tmp_path):
    first = ASSET.replace('合同資產', '非流動負債中的借款')
    second = ASSET.replace('合同資產', '流動負債中的借款').replace('本集團', '本公司').replace('業務增長', '盈利增長')
    graph, required = compiled(tmp_path, first + '\n\n# 獨立記錄\n\n' + second)
    facts = required['business']
    assert [i for i, f in enumerate(facts) if f['qualifiers'].get('circumstances')] == [1, 3]
    assert [facts[i]['qualifiers']['circumstances'][0]['operand']['subject'] for i in (1, 3)] == ['業務', '盈利']
    assert [f['qualifiers']['actor'] for f in facts] == ['本集團', '本集團', '本公司', '本公司']
    assert all('circumstances' not in facts[i]['qualifiers'] for i in (0, 2))
    actual = read_candidate_markdown(first + '\n\n# 獨立記錄\n\n' + second, sample_id=required['sample_id'])
    actual['logical_statements'][-1]['target_source'] = deepcopy(actual['logical_statements'][0]['target_source'])
    result = grade_layers(required, actual)
    assert not result['publishable']
    with pytest.raises(ValueError):
        validate_evidence(result)


@pytest.mark.parametrize('mutation', ['balance_target', 'omit_first', 'duplicate', 'drop_scope_source', 'raw_scope'])
def test_scope_audit_independently_rejects_target_and_original_scope_mutations(tmp_path, mutation):
    text = LOANS if mutation != 'raw_scope' else LOANS.replace('兩項變化均', '前者的變化')
    graph, _ = compiled(tmp_path, text)
    changed = deepcopy(graph)
    wrapper = changed['logic'][0]
    if mutation == 'balance_target':
        wrapper['target_sources'][0] = deepcopy(wrapper['child']['clauses'][0]['source'])
    elif mutation == 'omit_first':
        wrapper['target_sources'].pop(0)
    elif mutation == 'duplicate':
        wrapper['target_sources'][1] = deepcopy(wrapper['target_sources'][0])
    elif mutation == 'drop_scope_source':
        del wrapper['attachment_source']
    else:
        # Same-length source edit leaves positions intact, but changes which
        # result the original words require. No parser-produced oracle here.
        def replace_source(value):
            if isinstance(value, dict):
                for key, item in list(value.items()):
                    if isinstance(item, str):
                        value[key] = item.replace('前者的變化', '後者的變化')
                    else:
                        replace_source(item)
            elif isinstance(value, list):
                for item in value:
                    replace_source(item)
        replace_source(changed['sources'])
        replace_source(changed['source_obligation_inventory'])
        from moparse_eval.cjk_circumstances import validate_circumstance_graph
        from moparse_eval.requirement_graph import _semantic_literal
        with pytest.raises(ValueError, match='attachment differs'):
            validate_circumstance_graph(changed, lambda source, label: _semantic_literal(changed['sources'], source))
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


def test_supported_flow_direction_error_is_a_valid_wrong_candidate_with_other_business_preserved(tmp_path):
    text = INVESTING + '\n\n' + ASSET
    _, required = compiled(tmp_path, text)
    result = compare(required, text.replace('現金淨額流出', '現金淨額流入', 1))
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
        'B:0': 'incorrect', 'B:1': 'incorrect', 'B:2': 'correct', 'B:3': 'correct'}
    assert result['layers']['B']['denominator'] == 4
    assert result['layers']['L']['denominator'] == len(required['relations'])
    assert all(o['outcome'] == 'correct' for o in result['outcomes']
               if o['layer'] == 'L' and o['expected'].get('fact_id') in {'B:2', 'B:3'})


@pytest.mark.parametrize('scope,wrong', [('前者的變化', {'B:3'}), ('後者的變化', {'B:1'})])
def test_wrong_but_supported_local_scope_is_comparable_and_only_its_owner_fails(tmp_path, scope, wrong):
    _, required = compiled(tmp_path, LOANS)
    result = compare(required, LOANS.replace('兩項變化均', scope))
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
        f['id']: 'incorrect' if f['id'] in wrong else 'correct' for f in required['business']}
    assert result['layers']['B']['denominator'] == 4
    assert result['layers']['L']['denominator'] == len(required['relations'])
    assert all(o['outcome'] == 'correct' for o in result['outcomes'] if o['layer'] == 'L'
               and o['expected'].get('fact_id') in {'B:0', 'B:2'})


def test_explicit_leading_cause_owns_its_whole_printed_result_without_trailing_scope_inference(tmp_path):
    text = '由于业务增长，2029年运输收入为人民币15亿元，同比增长12%。'
    _, required = compiled(tmp_path, text)
    assert [f['value'] for f in required['business']] == ['15', '12']
    assert all(f['qualifiers']['circumstances'][0]['operand']['subject'] == '业务' for f in required['business'])


def test_unmarked_closed_parallel_borrowing_record_has_independent_common_reference(tmp_path):
    graph, required = compiled(tmp_path, IMPLICIT_LOANS)
    assert [i for i, f in enumerate(required['business']) if f['qualifiers'].get('circumstances')] == [1, 3]
    assert [(n['subject'], n['attribute'], n['value']) for n in graph['nodes'] if n['kind'] == 'semantic_operand'] == [('', '償還', '借款')]
    assert graph['logic'][0]['attachment'] == 'all'
    assert len(graph['logic'][0]['implicit_attachment_sources']) == 2
    result = compare(required, LOANS)
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    assert result['layers']['T']['score'] < 100


@pytest.mark.parametrize('before,after,wrong', [('17億元', '18億元', {'B:0'}),
                                            ('2028年末下降9%', '2027年末下降9%', {'B:1'}),
                                            ('下降9%', '增長9%', {'B:1'})])
def test_implicit_scope_is_not_selected_by_correct_numeric_year_or_direction_values(tmp_path, before, after, wrong):
    _, required = compiled(tmp_path, IMPLICIT_LOANS)
    result = compare(required, IMPLICIT_LOANS.replace(before, after, 1))
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
        f['id']: 'incorrect' if f['id'] in wrong else 'correct' for f in required['business']}
    assert result['layers']['B']['denominator'] == 4


def test_declared_but_unspecified_one_or_two_targets_remains_unknown(tmp_path):
    from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection
    from tests.unit.test_cjk_circumstance_contract import authored

    expected = authored(tmp_path, LOANS.replace('兩項變化均', '其中一項或兩項變化'))
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    unresolved, = [p for p in graph['unresolved'] if p['reason'] == 'cjk_causal_attachment_declared_uncertain']
    assert unresolved['category'] == 'source_attachment_ambiguity'
    assert [h['scope'] for h in unresolved['attachment_hypotheses']] == ['former_change', 'latter_change', 'joint_changes']
    assert not graph['semantic_complete']
    assert [f['value'] for f in evaluation_projection(graph)['business']] == ['17', '9', '11', '6']
