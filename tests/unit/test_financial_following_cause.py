"""Independent source and comparison assertions for a following explanation."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import validate_requirement_graph
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import compiled

FOLLOWING = ('2029年末本公司總資產為人民幣80億元，比上年末增加人民幣9億元。'
             '主要歸因於公司加大升級投入，以及固定資產及在建工程比上年末增加人民幣7億元。')
UNMARKED = FOLLOWING.replace('，以及', '，')
CHAIN = FOLLOWING.replace('，以及', '導致')
SEMICOLON = ('流動資產為人民幣89億元，比上年末減少人民幣7億元。'
             '主要歸因於存貨增加人民幣3億元；現金及存款比上年末減少人民幣5億元。')
INVESTMENT_EXPLANATION = ('非流動資產為人民幣79億元，比上年末增加人民幣6億元。'
    '主要歸因於公司持續推進轉型升級，新材料基地項目建設投資力度加大，設備及在建工程比上年末增加人民幣8億元；'
    '加強境外合資合作，於合作公司的權益比上年末增加人民幣2億元。')
RECLASSIFICATION = ('流動負債為人民幣67億元，比上年末增加人民幣9億元。'
                    '主要歸因於部分長期借款重分類為一年內到期的非流動負債。')
SHARED_ACTIONS = '本公司建立並持續健全與會計核算、信息披露相關的決策機制、業務流程和內部控制制度。'
BASIS_ACTION = ('2029年，本公司根據董事會批准的金融業務年度計劃，開展了商品類及貨幣類金融業務，'
                '相關業務符合金融業務的監管要求，運行規範，實現了平抑價格波動、穩定經營收益、防範市場風險的目標。')
FORMULA_NOTE = '註：淨利率=（銷售收入－銷售成本、稅金及附加）/銷售收入。'
NOTED_RECORDS = ('# 部門\n\n- 東部：營業收入80元；毛利率（註）25%。\n- 西部：營業收入60元；毛利率（註）20%。\n\n'
                 '註：毛利率=（營業收入－營業成本、稅金及附加）/營業收入。')
DATED_BALANCES = '單位：人民幣百萬元。\n\n- 資產：於2029年12月31日89；於2028年12月31日82；變化額7。'
GOVERNANCE_ACTIONS = ('本報告期內，遠海公司遵守《公司章程》和監管規定，堅持規範運作，依法合規經營，持續提升治理水平。'
                      '完成董事會換屆，調整專門委員會設置，提高多元化水平。')


def test_governance_content_does_not_require_expanding_the_chinese_verb_dictionary(tmp_path):
    from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection
    from tests.unit.test_cjk_circumstance_contract import authored

    graph = compile_requirement_graph(authored(tmp_path, GOVERNANCE_ACTIONS), comparison_contract='document_ast')
    assert graph['unresolved'] and graph['content_comparison_ready']
    result = grade_layers(evaluation_projection(graph), read_candidate_markdown(GOVERNANCE_ACTIONS, sample_id=graph['sample_id']))
    assert result['publishable'], result['blockers']
    assert result['layers']['B']['denominator'] == result['layers']['B']['numerator'] == 1
    validate_evidence(result)


def test_printed_completed_actions_and_book_titles_have_their_own_roles_and_equivalence(tmp_path):
    text = '本公司已制定《核算及披露規則》。'
    graph, required = compiled(tmp_path, text)
    fact, = required['business']
    assert (fact['subject'], fact['attribute'], fact['value'], fact['qualifiers']) == (
        '本公司', '制定', '《核算及披露規則》', {'polarity': 'positive', 'aspect': 'perfect'})
    assert fact['object_phrase']['designation'] == 'book_title'
    assert fact['object_phrase']['head'] == '核算及披露規則'
    assert not graph['unresolved']
    for candidate, correct in [(text, True), (text.replace('已制定', '制定了'), True),
        (text.replace('已制定', '已經制定'), True), (text.replace('披露規則', '審閱規則'), False),
        (text.replace('已制定', '制定'), False)]:
        actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
        assert not actual['blockers'] and not actual['pending_requirements']
        result = grade_layers(required, actual)
        assert result['publishable'], result['blockers']
        validate_evidence(result)
        assert result['layers']['B']['denominator'] == 1
        assert [o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'] == ['correct' if correct else 'incorrect']
        if correct:
            assert result['layers']['L']['score'] == 100
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    actual['logical_statements'] = []
    result = grade_layers(required, actual)
    assert result['layers']['T']['score'] == 100 and not result['publishable']
    with pytest.raises(ValueError):
        validate_evidence(result)


def test_dated_balance_positions_and_change_amount_are_three_independent_assertions(tmp_path):
    _, required = compiled(tmp_path, DATED_BALANCES)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [
        ('', '資產', '89'), ('', '資產', '82'), ('資產', '變化額', '7')]
    first, second, delta = required['business']
    assert first['qualifiers']['period'] == '2029年12月31日' and first['qualifiers']['period_basis'] == '於'
    assert second['qualifiers']['period'] == '2028年12月31日'
    assert delta['qualifiers'] == {'unit': '人民幣百萬元', 'currency': '人民幣', 'from_period': '2028年12月31日', 'to_period': '2029年12月31日'}
    for candidate, incorrect in [(DATED_BALANCES, set()), (DATED_BALANCES.replace('變化額7', '變化額8'), {'B:2'}),
        (DATED_BALANCES.replace('日89', '日90'), {'B:0'}),
        (DATED_BALANCES.replace('於2029年12月31日89；於2028年12月31日82', '於2028年12月31日82；於2029年12月31日89'), set())]:
        actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
        assert not actual['blockers'] and not actual['pending_requirements']
        result = grade_layers(required, actual)
        assert result['publishable'], result['blockers']
        validate_evidence(result)
        assert result['layers']['B']['denominator'] == 3
        assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
            f'B:{i}': 'incorrect' if f'B:{i}' in incorrect else 'correct' for i in range(3)}
        if not incorrect:
            assert result['layers']['L']['score'] == 100


def test_alphabetic_item_marker_is_layout_and_does_not_change_the_business_assertion(tmp_path):
    text = 'a. 本報告期內，本公司披露報告。'
    graph, required = compiled(tmp_path, text)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [('本公司', '披露', '報告')]
    root, = graph['logic']
    assert (root['kind'], root['role'], root['marker']) == ('discourse_scope', 'item_label', 'a.')
    result = grade_layers(required, read_candidate_markdown(text.replace('a.', 'b.'), sample_id=required['sample_id']))
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['score'] == 100
    edge, = [r for r in required['relations'] if r['type'] == 'narrative_discourse_scope']
    assert next(o['outcome'] for o in result['outcomes'] if o['layer'] == 'L' and o['id'] == edge['id']) == 'incorrect'
    changed = deepcopy(graph)
    changed['logic'] = [changed['logic'][0]['child']]
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


def test_formula_note_owns_only_the_marked_columns_in_the_preceding_physical_list(tmp_path):
    graph, required = compiled(tmp_path, NOTED_RECORDS)
    edges = [r for r in required['relations'] if r['type'] == 'financial_note_scope']
    assert [(r['left'], r['right']) for r in edges] == [
        ({'note_label': '註', 'defined_metric': '毛利率'}, {'subject': name, 'attribute': '毛利率（註）', 'scope': ['部門']})
        for name in ['東部', '西部']]
    assert all(r['binding_evidence']['note_label_source']['lines'] == [6, 6] for r in edges)
    candidate = NOTED_RECORDS.replace('註：毛利率=', '註：淨利率=')
    actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
    assert not actual['blockers'] and not actual['pending_requirements']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
        'B:0': 'correct', 'B:1': 'correct', 'B:2': 'correct', 'B:3': 'correct', 'B:4': 'incorrect'}
    assert all(next(o['outcome'] for o in result['outcomes'] if o['id'] == edge['id'] and o['layer'] == 'L') == 'incorrect' for edge in edges)
    assert result['layers']['B']['denominator'] == 5


@pytest.mark.parametrize('mutation', ['edge', 'row', 'formula_metric', 'neighbor_source', 'all_structure'])
def test_formula_note_header_ownership_cannot_be_deleted_or_rebound(tmp_path, mutation):
    graph, required = compiled(tmp_path, NOTED_RECORDS)
    changed = deepcopy(graph)
    note = next(r for r in changed['relations'] if r['type'] == 'financial_note_scope')
    if mutation == 'edge':
        changed['relations'].remove(note)
    elif mutation == 'row':
        note['right']['subject'] = '西部'
    elif mutation == 'formula_metric':
        note['left']['defined_metric'] = '淨利率'
    elif mutation == 'neighbor_source':
        note['binding_evidence']['header_source']['lines'] = [4, 4]
    else:
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'financial_note_scope']
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)
    actual = read_candidate_markdown(NOTED_RECORDS, sample_id=required['sample_id'])
    actual['relations'] = [r for r in actual['relations'] if r['type'] != 'financial_note_scope']
    result = grade_layers(required, actual)
    assert result['layers']['T']['score'] == 100 and not result['publishable']
    with pytest.raises(ValueError):
        validate_evidence(result)


def test_formula_note_exposes_arithmetic_roles_instead_of_an_opaque_note_value(tmp_path):
    graph, required = compiled(tmp_path, FORMULA_NOTE)
    fact, = required['business']
    assert (fact['subject'], fact['attribute'], fact['role']) == ('淨利率', '=', 'formula_definition')
    assert fact['printed_label'] == '註'
    division = fact['object_phrase']
    assert [p['role'] for p in division['parts']] == ['dividend', 'divisor']
    numerator = division['parts'][0]['child']['parts'][0]['child']
    assert [(p['role'], p['child']['head']) for p in numerator['parts']] == [
        ('arithmetic_base', '銷售收入'), ('subtrahend', '銷售成本'), ('subtrahend', '稅金及附加')]
    assert division['parts'][1]['child']['head'] == '銷售收入'
    for candidate, correct in [(FORMULA_NOTE, True), (FORMULA_NOTE.replace('－', '-'), True), (FORMULA_NOTE.replace('/', '÷'), True),
        (FORMULA_NOTE.replace('－', '+'), False), (FORMULA_NOTE.replace('/銷售收入', '/經營收入'), False),
        (FORMULA_NOTE.replace('銷售成本', '經營成本'), False)]:
        actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
        assert not actual['blockers'] and not actual['pending_requirements']
        result = grade_layers(required, actual)
        assert result['publishable'], result['blockers']
        validate_evidence(result)
        assert result['layers']['B']['denominator'] == 1
        assert [o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'] == ['correct' if correct else 'incorrect']
        assert result['layers']['L']['denominator'] == len(required['relations'])
        if correct:
            assert result['layers']['L']['score'] == 100
        if candidate not in {FORMULA_NOTE, FORMULA_NOTE.replace('－', '-')}:
            assert result['layers']['T']['score'] < 100


@pytest.mark.parametrize('mutation', ['denominator', 'subtrahend', 'relation', 'neighbor_source'])
def test_formula_note_cannot_omit_an_operand_or_borrow_an_adjacent_formula(tmp_path, mutation):
    graph, _ = compiled(tmp_path, '# 第一節\n\n' + FORMULA_NOTE + '\n\n# 第二節\n\n' + FORMULA_NOTE.replace('淨利率', '毛利率'))
    changed = deepcopy(graph)
    expression = changed['logic'][0]['object_phrase']
    if mutation == 'denominator':
        expression['parts'].pop()
    elif mutation == 'subtrahend':
        expression['parts'][0]['child']['parts'][0]['child']['parts'].pop()
    elif mutation == 'relation':
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'narrative_cjk_nominal_scope']
    else:
        expression['parts'][1]['child']['source'] = deepcopy(changed['logic'][1]['object_phrase']['parts'][1]['child']['source'])
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


def test_approved_basis_business_categories_and_achieved_goals_have_distinct_responsibilities(tmp_path):
    graph, required = compiled(tmp_path, BASIS_ACTION)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [
        ('本公司', '開展', '商品類及貨幣類金融業務'), ('相關業務', '符合', '金融業務的監管要求'),
        ('相關業務', '運行', '規範'), ('相關業務', '實現', '平抑價格波動、穩定經營收益、防範市場風險的目標')]
    root, = graph['logic']
    basis = root['child']
    assert root['kind'] == 'temporal_scope' and root['qualifiers'] == {'period': '2029年'}
    assert basis['kind'] == 'fronted_context' and basis['role'] == 'basis'
    approval, = basis['context_phrase']['parts']
    assert approval['marker'] == '批准' and approval['child']['head'] == '董事會'
    first, _, _, last = basis['child']['children']
    assert first['object_phrase']['parts'][0]['role'] == 'shared_categories'
    assert [n['head'] for n in first['object_phrase']['parts'][0]['child']['parts'][0]['children']] == ['商品類', '貨幣類']
    goals, = last['object_phrase']['parts']
    assert goals['role'] == 'goal_description'
    assert [(n['predicate'], n['object']) for n in goals['child']['children']] == [
        ('平抑', '價格波動'), ('穩定', '經營收益'), ('防範', '市場風險')]
    for candidate, wrong in [(BASIS_ACTION, set()), (BASIS_ACTION.replace('商品類', '利率類'), {'B:0'}),
        (BASIS_ACTION.replace('規範，', '不規範，'), {'B:2'}), (BASIS_ACTION.replace('市場風險', '信用風險'), {'B:3'})]:
        actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
        assert not actual['blockers'] and not actual['pending_requirements']
        result = grade_layers(required, actual)
        assert result['publishable'], result['blockers']
        validate_evidence(result)
        assert result['layers']['B']['denominator'] == 4
        assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
            f'B:{i}': 'incorrect' if f'B:{i}' in wrong else 'correct' for i in range(4)}


@pytest.mark.parametrize('mutation', ['basis', 'basis_edge', 'approval_actor', 'goal', 'category', 'source'])
def test_basis_categories_and_goals_cannot_be_lost_or_borrowed(tmp_path, mutation):
    graph, _ = compiled(tmp_path, BASIS_ACTION + '\n\n' + BASIS_ACTION.replace('2029', '2030'))
    changed = deepcopy(graph)
    root = changed['logic'][0]
    basis = root['child']
    if mutation == 'basis':
        root['child'] = basis['child']
    elif mutation == 'basis_edge':
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'narrative_fronted_context_scope']
    elif mutation == 'approval_actor':
        basis['context_phrase']['parts'] = []
    elif mutation == 'goal':
        basis['child']['children'][-1]['object_phrase']['parts'][0]['child']['children'].pop()
    elif mutation == 'category':
        basis['child']['children'][0]['object_phrase']['parts'][0]['child']['parts'][0]['children'].pop()
    else:
        basis['context_phrase']['source'] = deepcopy(changed['logic'][1]['child']['context_phrase']['source'])
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


def test_shared_object_actions_do_not_select_an_embedded_nominal_verb_as_the_predicate(tmp_path):
    graph, required = compiled(tmp_path, SHARED_ACTIONS)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [
        ('本公司', '建立', '與會計核算、信息披露相關的決策機制、業務流程和內部控制制度'),
        ('本公司', '健全', '與會計核算、信息披露相關的決策機制、業務流程和內部控制制度')]
    assert 'manner' not in required['business'][0]['qualifiers']
    assert required['business'][1]['qualifiers']['manner'] == '持續'
    root, = graph['logic']
    assert root['kind'] == 'coordination' and root['mode'] == 'actions'
    for leaf in root['children']:
        phrase = leaf['object_phrase']
        assert phrase['parts'][0]['kind'] == 'coordination'
        assert [p['head'] for p in phrase['parts'][0]['children']] == ['決策機制', '業務流程', '內部控制制度']
        related = next(p for p in phrase['parts'] if p.get('role') == 'related_to')
        assert [p['head'] for p in related['child']['parts'][0]['children']] == ['會計核算', '信息披露']
    for candidate, incorrect in [(SHARED_ACTIONS, set()), (SHARED_ACTIONS.replace('健全', '制定'), {'B:1'}),
        (SHARED_ACTIONS.replace('持續', '逐步'), {'B:1'}), (SHARED_ACTIONS.replace('信息披露', '資訊管理'), {'B:0', 'B:1'})]:
        actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
        assert not actual['blockers'] and not actual['pending_requirements']
        result = grade_layers(required, actual)
        assert result['publishable'], result['blockers']
        validate_evidence(result)
        assert result['layers']['B']['denominator'] == 2
        assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
            'B:0': 'incorrect' if 'B:0' in incorrect else 'correct', 'B:1': 'incorrect' if 'B:1' in incorrect else 'correct'}


@pytest.mark.parametrize('mutation', ['action', 'coordination_edge', 'modifier', 'neighbor_source', 'nominal_dependency'])
def test_shared_action_and_nominal_dependencies_require_their_own_sources(tmp_path, mutation):
    graph, _ = compiled(tmp_path, SHARED_ACTIONS + '\n\n' + SHARED_ACTIONS.replace('本公司', '本集團'))
    changed = deepcopy(graph)
    root = changed['logic'][0]
    if mutation == 'action':
        root['children'].pop(0)
    elif mutation == 'coordination_edge':
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'narrative_coordination_scope']
    elif mutation == 'modifier':
        root['children'][1]['lexical_qualifiers'] = {}
        root['children'][1]['lexical_qualifier_sources'] = {}
    elif mutation == 'neighbor_source':
        root['children'][1]['object_phrase']['source'] = deepcopy(changed['logic'][1]['children'][1]['object_phrase']['source'])
    else:
        root['children'][1]['object_phrase']['parts'].pop()
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


def test_following_cause_has_one_joint_explanation_and_no_invented_middle_mechanism(tmp_path):
    graph, required = compiled(tmp_path, FOLLOWING)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [
        ('總資產', '為', '80'), ('總資產', '比上年末增加', '9')]
    operands = [n for n in graph['nodes'] if n['kind'] == 'semantic_operand']
    assert [(n['subject'], n['attribute'], n['value']) for n in operands] == [
        ('公司', '加大', '升級投入'), ('固定資產及在建工程', '比上年末增加', '7')]
    assert 'circumstances' not in required['business'][0]['qualifiers']
    cause, = required['business'][1]['qualifiers']['circumstances']
    assert (cause['operator'], cause['degree'], cause['direction']) == ('cause', '主要', 'operand_to_child')
    assert cause['operand']['operator'] == 'and'
    assert all('period' not in n['qualifiers'] for n in operands)
    assert not any(n.get('kind') == 'circumstance_scope' for n in graph['logic'][0]['operand']['children'])
    assert len([r for r in required['relations'] if r['type'] == 'narrative_circumstance_scope']) == 1
    actual = read_candidate_markdown(FOLLOWING, sample_id=required['sample_id'])
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert all(result['layers'][k]['score'] == 100 for k in ['T', 'L', 'B'])


@pytest.mark.parametrize('before,after', [('80億元', '81億元'), ('9億元', '8億元'), ('7億元', '6億元')])
def test_supported_wrong_main_or_cause_amount_is_comparable_with_exact_outcomes(tmp_path, before, after):
    _, required = compiled(tmp_path, FOLLOWING)
    actual = read_candidate_markdown(FOLLOWING.replace(before, after), sample_id=required['sample_id'])
    assert not actual['blockers'] and not actual['pending_requirements']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    wrong = 'B:0' if before == '80億元' else 'B:1'
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
        'B:0': 'incorrect' if wrong == 'B:0' else 'correct',
        'B:1': 'incorrect' if wrong == 'B:1' else 'correct'}
    assert result['layers']['B']['denominator'] == 2
    assert result['layers']['L']['denominator'] == len(required['relations'])


@pytest.mark.parametrize('mutation', ['operand', 'cause_edge', 'collective_member', 'borrowed_source', 'balance_target'])
def test_explanation_and_collective_metric_cannot_be_deleted_or_borrowed(tmp_path, mutation):
    graph, _ = compiled(tmp_path, FOLLOWING + '\n\n' + FOLLOWING.replace('2029', '2030').replace('7億元', '6億元'))
    changed = deepcopy(graph)
    wrapper = changed['logic'][0]
    if mutation == 'operand':
        changed['nodes'] = [n for n in changed['nodes'] if n['kind'] != 'semantic_operand']
    elif mutation == 'cause_edge':
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'narrative_circumstance_scope']
    elif mutation == 'collective_member':
        leaf = wrapper['operand']['children'][1]['clauses'][0]
        leaf['subject_phrase']['parts'][0]['children'].pop()
    elif mutation == 'borrowed_source':
        wrapper['operand']['children'][1]['source']['lines'] = [3, 3]
    else:
        wrapper['target_source'] = deepcopy(wrapper['child']['clauses'][0]['source'])
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


def test_source_attachment_unknown_keeps_its_independently_observable_prose_position(tmp_path):
    from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection
    from tests.unit.test_cjk_circumstance_contract import authored
    from tests.unit.test_financial_cause_source_closure import AMBIGUOUS_LOANS, ASSET, SHARES

    expected = authored(tmp_path, ASSET + '\n\n' + AMBIGUOUS_LOANS + '\n\n' + SHARES)
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    assert not graph['semantic_complete']
    projection = evaluation_projection(graph)
    assert [n['source']['lines'] for n in projection['prose_endpoints']] == [[1, 1], [3, 3], [5, 5]]
    ordered = [r for r in graph['relations'] if r['type'] == 'prose_reading_order']
    assert len(ordered) == 2
    assert ordered[1]['left'] == ordered[0]['right']


def test_comma_explanation_keeps_both_contents_without_inventing_an_internal_cause(tmp_path):
    graph, required = compiled(tmp_path, UNMARKED)
    cause, = required['business'][1]['qualifiers']['circumstances']
    assert cause['operand']['operator'] == 'and'
    contents = graph['logic'][0]['operand']['children']
    assert len(contents) == 2
    assert contents[0]['attribute'] == '加大'
    assert contents[1]['clauses'][0]['value'] == '7'
    assert not any(n.get('kind') == 'circumstance_scope' for n in contents)
    assert len([r for r in graph['relations'] if r['type'] == 'narrative_circumstance_scope']) == 1
    same = grade_layers(required, read_candidate_markdown(FOLLOWING, sample_id=required['sample_id']))
    assert same['publishable'], same['blockers']
    validate_evidence(same)
    assert same['layers']['B']['score'] == same['layers']['L']['score'] == 100
    assert same['layers']['T']['score'] < 100


def test_explicit_chain_is_distinct_from_joint_explanation_with_identical_quantities(tmp_path):
    graph, required = compiled(tmp_path, CHAIN)
    nested = graph['logic'][0]['operand']
    assert nested['kind'] == 'circumstance_scope' and nested['direction'] == 'operand_to_child'
    assert nested['operand']['attribute'] == '加大'
    assert nested['child']['clauses'][0]['value'] == '7'
    positive = grade_layers(required, read_candidate_markdown(CHAIN, sample_id=required['sample_id']))
    assert positive['publishable'], positive['blockers']
    validate_evidence(positive)
    assert positive['layers']['B']['numerator'] == 2
    negative = grade_layers(required, read_candidate_markdown(FOLLOWING, sample_id=required['sample_id']))
    assert negative['publishable'], negative['blockers']
    validate_evidence(negative)
    assert {o['id']: o['outcome'] for o in negative['outcomes'] if o['layer'] == 'B'} == {'B:0': 'correct', 'B:1': 'incorrect'}


@pytest.mark.parametrize('candidate', [FOLLOWING.replace('歸因於', '因為'), FOLLOWING.replace('7億元', '70000萬元')])
def test_legal_explanation_marker_or_exact_operand_scale_keeps_BL_and_literal_T_difference(tmp_path, candidate):
    _, required = compiled(tmp_path, FOLLOWING)
    actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
    assert not actual['blockers']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    assert result['layers']['T']['score'] < 100


def test_all_explanation_text_without_its_semantics_is_not_valid_comparison_evidence(tmp_path):
    _, required = compiled(tmp_path, FOLLOWING)
    actual = read_candidate_markdown(FOLLOWING, sample_id=required['sample_id'])
    actual['logical_statements'] = []
    result = grade_layers(required, actual)
    assert result['layers']['T']['score'] == 100
    assert not result['publishable']
    with pytest.raises(ValueError):
        validate_evidence(result)


def test_collective_position_quantity_is_one_assertion_not_a_value_for_each_member(tmp_path):
    text = '流動資產及非流動資產為人民幣17億元。'
    _, required = compiled(tmp_path, text)
    assert len(required['business']) == 1
    correct = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    assert correct['publishable']
    validate_evidence(correct)
    assert correct['layers']['B']['numerator'] == correct['layers']['B']['denominator'] == 1
    actual = read_candidate_markdown('流動資產為人民幣17億元，非流動資產為人民幣17億元。', sample_id=required['sample_id'])
    assert not actual['blockers']
    wrong = grade_layers(required, actual)
    assert wrong['publishable'], wrong['blockers']
    validate_evidence(wrong)
    assert [o['outcome'] for o in wrong['outcomes'] if o['layer'] == 'B'] == ['incorrect']
    assert wrong['layers']['B']['denominator'] == 1


@pytest.mark.parametrize('statement,value', [('本公司提供服務。', '服務'), ('本公司提供A3服務。', 'A3服務')])
def test_new_following_measurement_frame_does_not_swallow_a_supported_qualitative_neighbor(tmp_path, statement, value):
    from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection
    from tests.unit.test_cjk_circumstance_contract import authored

    expected = authored(tmp_path, statement + '主要歸因於業務增長。')
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    assert not graph['semantic_complete']
    assert [(f['subject'], f['attribute'], f['value']) for f in evaluation_projection(graph)['business']] == [
        ('本公司', '提供', value)]


def test_company_bond_nominal_does_not_invent_a_company_actor(tmp_path):
    graph, _ = compiled(tmp_path, FOLLOWING[:FOLLOWING.index('主要')] + '主要歸因於公司債券增加。')
    operand, = [n for n in graph['nodes'] if n['kind'] == 'semantic_operand']
    assert (operand['subject'], operand['attribute']) == ('公司債券', '增加')
    assert 'actor' not in operand['qualifiers']


def test_semicolon_inside_following_explanation_keeps_both_changes_as_noncounting_operands(tmp_path):
    graph, required = compiled(tmp_path, SEMICOLON)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [
        ('流動資產', '為', '89'), ('流動資產', '比上年末減少', '7')]
    operands = [n for n in graph['nodes'] if n['kind'] == 'semantic_operand']
    assert [(n['subject'], n['attribute'], n['value']) for n in operands] == [
        ('存貨', '增加', '3'), ('現金及存款', '比上年末減少', '5')]
    assert 'comparison_basis' not in operands[0]['qualifiers']
    assert operands[1]['qualifiers']['comparison_basis'] == '比上年末'
    assert 'circumstances' not in required['business'][0]['qualifiers']
    cause, = required['business'][1]['qualifiers']['circumstances']
    assert cause['degree'] == '主要' and cause['operand']['operator'] == 'and'
    result = grade_layers(required, read_candidate_markdown(SEMICOLON.replace('；', '，'), sample_id=required['sample_id']))
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100


@pytest.mark.parametrize('before,after', [('3億元', '4億元'), ('增加人民幣3', '減少人民幣3')])
def test_bare_amount_change_is_read_and_wrong_cause_retains_independent_balance(tmp_path, before, after):
    _, required = compiled(tmp_path, SEMICOLON)
    actual = read_candidate_markdown(SEMICOLON.replace(before, after), sample_id=required['sample_id'])
    assert not actual['blockers'] and not actual['pending_requirements']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
        'B:0': 'correct', 'B:1': 'incorrect'}
    assert result['layers']['B']['denominator'] == 2


def test_multicomponent_investment_explanation_has_five_operands_and_no_invented_inner_cause(tmp_path):
    graph, required = compiled(tmp_path, INVESTMENT_EXPLANATION)
    assert [(n['subject'], n['attribute'], n['value']) for n in graph['nodes'] if n['kind'] == 'semantic_operand'] == [
        ('公司', '推進', '轉型升級'), ('新材料基地項目建設投資力度', '加大', ''),
        ('設備及在建工程', '比上年末增加', '8'), ('', '加強', '境外合資合作'),
        ('於合作公司的權益', '比上年末增加', '2')]
    assert [f['value'] for f in required['business']] == ['79', '6']
    scope, = [r for r in required['relations'] if r['type'] == 'narrative_circumstance_scope']
    assert scope['left']['degree'] == '主要'
    result = grade_layers(required, read_candidate_markdown(INVESTMENT_EXPLANATION, sample_id=required['sample_id']))
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert all(result['layers'][k]['score'] == 100 for k in ('T', 'L', 'B'))


@pytest.mark.parametrize('before,after', [('合作公司的權益', '另一公司的權益'), ('8億元', '9億元')])
def test_wrong_explanation_investee_or_amount_is_a_valid_local_business_failure(tmp_path, before, after):
    _, required = compiled(tmp_path, INVESTMENT_EXPLANATION)
    actual = read_candidate_markdown(INVESTMENT_EXPLANATION.replace(before, after), sample_id=required['sample_id'])
    assert not actual['blockers'] and not actual['pending_requirements']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {'B:0': 'correct', 'B:1': 'incorrect'}
    assert result['layers']['B']['denominator'] == 2


def test_reclassification_retains_partial_loan_scope_and_explicit_maturity(tmp_path):
    graph, required = compiled(tmp_path, RECLASSIFICATION)
    operand, = [n for n in graph['nodes'] if n['kind'] == 'semantic_operand']
    assert (operand['subject'], operand['attribute'], operand['value']) == ('部分長期借款', '重分類為', '一年內到期的非流動負債')
    assert operand['subject_phrase']['quantifier'] == '部分'
    part, = operand['object_phrase']['parts']
    assert (part['role'], part['marker'], part['child']['head']) == ('maturity_term', '到期', '一年內')
    actual = read_candidate_markdown(RECLASSIFICATION.replace('一年內', '二年內'), sample_id=required['sample_id'])
    assert not actual['blockers']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {'B:0': 'correct', 'B:1': 'incorrect'}
    changed = deepcopy(graph)
    node = next(n for n in changed['nodes'] if n['kind'] == 'semantic_operand')
    node['object_phrase']['parts'] = []
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


def test_image_caption_cannot_absorb_and_suppress_the_following_financial_record(tmp_path):
    text = ('![工廠照片](assets/fictional.png)\n\n'
            '2029年本公司經營活動現金淨流入為人民幣73億元，同比減少現金流入人民幣8億元，主要歸因於淨利潤減少。')
    graph, required = compiled(tmp_path, text)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [
        ('經營活動現金淨流入', '為', '73'), ('經營活動現金淨流入', '同比減少現金流入', '8')]
    assert all(f['source']['lines'] == [3, 3] for f in required['business'])
    assert any(n.get('text') == '工廠照片' and n['source']['lines'] == [1, 1] for n in graph['nodes'])
    actual = read_candidate_markdown(text.replace('8億元', '9億元'), sample_id=required['sample_id'])
    assert not actual['blockers']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {'B:0': 'correct', 'B:1': 'incorrect'}


def test_repeated_literal_media_captions_keep_two_heading_bindings_without_becoming_prose(tmp_path):
    text = '# 工程情況\n\n![設備照片](assets/one.png)\n\n![設備照片](assets/two.png)\n\n' + FOLLOWING
    graph, required = compiled(tmp_path, text)
    captions = [n for n in graph['context']['prose_endpoints'] if n.get('kind') == 'image_caption']
    assert len(captions) == 2 and [n['source']['lines'] for n in captions] == [[3, 3], [5, 5]]
    edges = [e for e in required['relations'] if e['type'] == 'prose_heading_membership'
             and e.get('right', {}).get('identity', {}).get('role') == 'image_caption']
    assert len(edges) == 2
    assert not any(e['type'] == 'prose_reading_order' for e in required['relations'])
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert all(result['layers'][k]['score'] == 100 for k in ('T', 'L', 'B'))


@pytest.mark.parametrize('text,triples', [
    ('2029年本公司研發支出為人民幣37億元，其中費用支出人民幣20億元，投資支出人民幣17億元。',
     [('研發支出', '為', '37'), ('費用支出', '', '20'), ('投資支出', '', '17')]),
    ('2029年本公司淨利潤為人民幣71億元，同比減少人民幣9億元，降低12.5%。',
     [('淨利潤', '為', '71'), ('淨利潤', '同比減少', '9'), ('淨利潤', '降低', '12.5')]),
])
def test_inline_components_and_paired_change_magnitudes_keep_their_distinct_roles(tmp_path, text, triples):
    graph, required = compiled(tmp_path, text)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == triples
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert all(result['layers'][k]['score'] == 100 for k in ('T', 'L', 'B'))
    if triples[0][0] == '研發支出':
        assert all(f['qualifiers']['parent_metric'] == '研發支出' for f in required['business'][1:])
        assert all(f['qualifiers']['membership_operator'] == '其中' for f in required['business'][1:])
        assert required['business'][1]['predicate_source']['text_span'][0] == required['business'][1]['predicate_source']['text_span'][1]
    else:
        assert required['business'][1]['qualifiers']['unit'] == '億元'
        assert required['business'][2]['qualifiers']['unit'] == '%'
        assert required['business'][2]['qualifiers']['comparison_basis'] == 'year_on_year'
    changed = deepcopy(graph)
    changed['nodes'] = [n for n in changed['nodes'] if n['id'] != changed['projections']['B'][1]]
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


@pytest.mark.parametrize('text,before,after,wrong', [
    ('2029年本公司研發支出為人民幣37億元，其中費用支出人民幣20億元，投資支出人民幣17億元。', '20億元', '21億元', 'B:1'),
    ('2029年本公司淨利潤為人民幣71億元，同比減少人民幣9億元，降低12.5%。', '12.5%', '13.5%', 'B:2'),
    ('2029年本公司淨利潤為人民幣71億元，同比減少人民幣9億元，降低12.5%。', '12.5%', '12.5億元', 'B:2'),
])
def test_inline_component_or_second_magnitude_wrong_values_keep_the_other_two_business_requirements(tmp_path, text, before, after, wrong):
    _, required = compiled(tmp_path, text)
    actual = read_candidate_markdown(text.replace(before, after), sample_id=required['sample_id'])
    assert not actual['blockers'] and not actual['pending_requirements']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['denominator'] == 3
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
        f'B:{i}': 'incorrect' if f'B:{i}' == wrong else 'correct' for i in range(3)}


def test_definition_has_collective_cost_content_and_a_structured_related_domain(tmp_path):
    text = '開發支出是指本公司與技術和開發相關的費用和投資支出。'
    graph, required = compiled(tmp_path, text)
    fact, = required['business']
    assert (fact['subject'], fact['attribute']) == ('開發支出', '是指')
    assert fact['object_phrase']['parts'][0]['operator'] == 'and'
    assert [c['head'] for c in fact['object_phrase']['parts'][0]['children']] == ['費用', '投資支出']
    domain, owner = fact['object_phrase']['parts'][1:]
    assert (domain['role'], domain['marker'], owner['role'], owner['child']['head']) == ('related_to', '相關', 'owner', '本公司')
    candidate = text.replace('技術和開發', '開發和技術')
    actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    assert result['layers']['T']['score'] < 100
    changed = deepcopy(graph)
    node = next(n for n in changed['nodes'] if n['id'] == changed['projections']['B'][0])
    node['object_phrase']['parts'].pop(1)
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


@pytest.mark.parametrize('before,after,wrong', [('不包括', '包括', 'B:1'), ('本公司支付', '本集團支付', 'B:0')])
def test_definition_payer_and_exclusion_are_distinct_source_bound_business_assertions(tmp_path, before, after, wrong):
    text = '治理支出是指本公司支付的合理的設備清理費用，不包括裝置的資本化費用。'
    graph, required = compiled(tmp_path, text)
    assert [(f['subject'], f['attribute'], f['qualifiers']['polarity']) for f in required['business']] == [
        ('治理支出', '是指', 'positive'), ('治理支出', '包括', 'negative')]
    payer, = [p for p in required['business'][0]['object_phrase']['parts'] if p.get('role') == 'payer']
    assert payer['child']['head'] == '本公司' and payer['marker'] == '支付'
    actual = read_candidate_markdown(text.replace(before, after), sample_id=required['sample_id'])
    assert not actual['blockers'] and not actual['pending_requirements']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['denominator'] == 2
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
        f'B:{i}': 'incorrect' if f'B:{i}' == wrong else 'correct' for i in range(2)}
    changed = deepcopy(graph)
    owner = next(n for n in changed['nodes'] if n['id'] == changed['projections']['B'][0])
    owner['object_phrase']['parts'] = []
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


@pytest.mark.parametrize('text,subject,qualifier,value', [
    ('2027年，星港公司提供物流服務。', '星港公司', 'period', '2027年'),
    ('本報告期內，本公司披露報告。', '本公司', 'period', '本報告期內'),
    ('董事會每年審閱預算。', '董事會', 'frequency', '每年'),
    ('公司同日不披露報告。', '公司', 'period', '同日'),
])
def test_printed_time_or_frequency_is_not_part_of_the_actor_and_has_its_own_scope(tmp_path, text, subject, qualifier, value):
    graph, required = compiled(tmp_path, text)
    fact, = required['business']
    assert fact['subject'] == subject and fact['qualifiers'][qualifier] == value
    origin = fact['qualifier_sources'][qualifier]
    assert text[slice(*origin['text_span'])] == value
    assert graph['logic'][0]['kind'] == 'temporal_scope'
    positive = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    assert positive['publishable'], positive['blockers']
    validate_evidence(positive)
    assert all(positive['layers'][k]['score'] == 100 for k in ('T', 'L', 'B'))
    changed = deepcopy(graph)
    changed['logic'] = [changed['logic'][0]['child']]
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)


def test_temporal_company_name_and_relative_time_are_distinct_valid_readings(tmp_path):
    _, required = compiled(tmp_path, '公司同日披露報告。')
    actual = read_candidate_markdown('同日公司披露報告。', sample_id=required['sample_id'])
    fact, = actual['business']
    assert fact['subject'] == '同日公司' and 'period' not in fact['qualifiers']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['denominator'] == 1 and result['layers']['B']['numerator'] == 0


def test_wrong_supported_year_is_comparable_and_not_borrowed_by_the_next_statement(tmp_path):
    text = '2029年，本公司披露報告。\n\n本公司提供服務。'
    _, required = compiled(tmp_path, text)
    assert required['business'][0]['qualifiers']['period'] == '2029年'
    assert 'period' not in required['business'][1]['qualifiers']
    actual = read_candidate_markdown(text.replace('2029年', '2030年'), sample_id=required['sample_id'])
    assert not actual['blockers']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {'B:0': 'incorrect', 'B:1': 'correct'}
