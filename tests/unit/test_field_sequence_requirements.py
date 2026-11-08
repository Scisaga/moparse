"""Handwritten semantic and source oracles for explicit field sequences."""

from copy import deepcopy

import pytest

from moparse_eval.field_sequence_requirements import read_field_sequence_requirements
from moparse_eval.scalar_evidence import validate_scalar_sources

SOURCE = {"path": "<own-printed-fields>", "lines": [7, 7]}
FINANCIAL_RECORDS = ('# 資產數據\n\n與計量相關的項目單位：單位：人民幣百萬元。\n\n'
    '- 金融資產：期初金額17；期末金額19；本期公允價值變動損益3；資金來源–。\n'
    '  - 票據：期初金額5；期末金額6；本期公允價值變動損益1；資金來源–。')
TRAINING_RECORDS = ('# 培訓\n\n'
    '- 陳文；職位：董事長、非執行董事；法規之更新：閱讀材料√，培訓、講座√；財務/經營情況：閱讀材料√，調研√。\n'
    '- 林月；職位：副董事長、執行董事、總裁；法規之更新：閱讀材料√，培訓、講座√；財務/經營情況：閱讀材料√，調研√。')


def test_untimed_person_collection_owns_each_training_field_without_inventing_a_year(tmp_path):
    from moparse_eval.expected_report import validate_evidence
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    text = TRAINING_RECORDS.replace('# 培訓\n\n', '# 培訓\n\n現任董事參與培訓的情況如下：\n\n')
    graph, required = compiled(tmp_path, text)
    context, = graph['context']['enumeration_contexts']
    roles = context['declaration']['roles']
    assert {k: v['text'] for k, v in roles.items()} == {'subject': '現任董事', 'collection': '參與培訓的情況', 'operator': '如下'}
    assert context['declaration']['qualifiers'] == {} and 'period' not in roles
    assert len([r for r in required['relations'] if r['type'] == 'enumeration_membership']) == 10
    assert all('period' not in f['qualifiers'] for f in required['business'])
    actual = read_candidate_markdown(text.replace('√', '☑'), sample_id=required['sample_id'])
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    assert result['layers']['T']['score'] < 100
    for mutation in ['member', 'declaration', 'year', 'neighbor']:
        changed = deepcopy(graph)
        if mutation == 'member':
            changed['relations'] = [r for r in changed['relations'] if r['type'] != 'enumeration_membership']
        elif mutation == 'declaration':
            changed['relations'] = [r for r in changed['relations'] if r['type'] != 'enumeration_declaration']
        else:
            fact = next(n for n in changed['nodes'] if n['id'] in changed['projections']['B'])
            if mutation == 'year':
                fact['qualifiers']['period'] = '2029年'
                fact['qualifier_sources']['period'] = deepcopy(fact['subject_source'])
            else:
                fact['enumeration_evidence']['member_source']['lines'] = [6, 6]
        from moparse_eval.requirement_graph import validate_requirement_graph
        with pytest.raises(ValueError):
            validate_requirement_graph(changed)
    actual['enumeration_contexts'] = []
    result = grade_layers(required, actual)
    assert not result['publishable']


def test_person_position_lists_and_two_level_marked_fields_are_complete_independent_records(tmp_path):
    from moparse_eval.expected_report import validate_evidence
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    _, required = compiled(tmp_path, TRAINING_RECORDS)
    assert [(f['subject'], f['attribute'], f['identity_facets'], f['value']) for f in required['business']] == [
        (person, attribute, {'field_domain': domain} if domain else {}, value)
        for person, roles in [('陳文', '董事長、非執行董事'), ('林月', '副董事長、執行董事、總裁')]
        for attribute, domain, value in [('職位', None, roles), ('閱讀材料', '法規之更新', '√'),
            ('培訓、講座', '法規之更新', '√'), ('閱讀材料', '財務/經營情況', '√'), ('調研', '財務/經營情況', '√')]]
    assert len([r for r in required['relations'] if r['type'] == 'record_label_scope']) == 10
    assert len([r for r in required['relations'] if r['type'] == 'record_position_member']) == 5
    for candidate, wrong in [(TRAINING_RECORDS, set()), (TRAINING_RECORDS.replace('√', '✓'), set()),
        (TRAINING_RECORDS.replace('董事長、非執行董事', '非執行董事、董事長', 1), set()),
        (TRAINING_RECORDS.replace('閱讀材料√', '閱讀材料×', 1), {'B:1'}),
        (TRAINING_RECORDS.replace('副董事長、執行董事、總裁', '副董事長、非執行董事、總裁'), {'B:5'})]:
        actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
        assert not actual['blockers'] and not actual['pending_requirements']
        result = grade_layers(required, actual)
        assert result['publishable'], result['blockers']
        validate_evidence(result)
        assert result['layers']['B']['denominator'] == 10
        assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
            f'B:{i}': 'incorrect' if f'B:{i}' in wrong else 'correct' for i in range(10)}
        if not wrong:
            assert result['layers']['L']['score'] == 100
        if candidate != TRAINING_RECORDS:
            assert result['layers']['T']['score'] < 100


@pytest.mark.parametrize('mutation', ['selection', 'domain', 'header', 'value_logic', 'position_member', 'record_scope', 'all_structure'])
def test_selection_record_evidence_cannot_repair_or_borrow_a_neighboring_slot(tmp_path, mutation):
    from moparse_eval.requirement_graph import validate_requirement_graph
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    graph, required = compiled(tmp_path, TRAINING_RECORDS)
    changed = deepcopy(graph)
    fields = [f for f in changed['nodes'] if f['id'] in changed['projections']['B']]
    if mutation == 'selection':
        fields[1]['value'] = '×'
    elif mutation == 'domain':
        fields[1]['identity_facets']['field_domain'] = '財務/經營情況'
    elif mutation == 'header':
        fields[1]['header_evidence'] = deepcopy(fields[3]['header_evidence'])
    elif mutation == 'value_logic':
        fields[0]['value_logic']['parts'][0]['children'].pop()
    elif mutation == 'position_member':
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'record_position_member']
    elif mutation == 'record_scope':
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'record_label_scope']
    else:
        for ident in changed['projections']['B']:
            changed['nodes'] = [n for n in changed['nodes'] if n['id'] != ident]
    with pytest.raises(ValueError):
        validate_requirement_graph(changed)
    actual = read_candidate_markdown(TRAINING_RECORDS, sample_id=required['sample_id'])
    actual['business'] = []
    with pytest.raises(ValueError):
        grade_layers(required, actual)


def literal(text, source):
    a, b = source["text_span"]
    return text[a:b]


def test_labelled_records_have_each_field_relative_position_unit_and_real_parent(tmp_path):
    from moparse_eval.expected_report import validate_evidence
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    graph, required = compiled(tmp_path, FINANCIAL_RECORDS)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [
        ('金融資產', '期初金額', '17'), ('金融資產', '期末金額', '19'), ('金融資產', '本期公允價值變動損益', '3'), ('金融資產', '資金來源', '–'),
        ('票據', '期初金額', '5'), ('票據', '期末金額', '6'), ('票據', '本期公允價值變動損益', '1'), ('票據', '資金來源', '–')]
    for i, fact in enumerate(required['business']):
        assert fact['qualifiers']['table_caption'] == '與計量相關的項目'
        assert fact['identity_facets'].get('group', []) == ([] if i < 4 else ['金融資產'])
        if i % 4 != 3:
            assert fact['qualifiers']['period'] == ['期初', '期末', '本期'][i % 4]
            assert fact['qualifiers']['unit'] == '人民幣百萬元' and fact['qualifiers']['currency'] == '人民幣'
        else:
            assert 'unit' not in fact['qualifiers'] and 'currency' not in fact['qualifiers']
            assert fact['semantic_type'] == 'printed_unspecified_value'
    candidate = FINANCIAL_RECORDS.replace('期初金額5', '期初金額500人民幣萬元')
    result = grade_layers(required, read_candidate_markdown(candidate, sample_id=required['sample_id']))
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    assert result['layers']['T']['score'] < 100
    assert any(n.get('text') == '單位' for n in graph['nodes'])


@pytest.mark.parametrize('mutation,wrong', [('value', {5}), ('parent', {4, 5, 6, 7}), ('unknown_to_zero', {7})])
def test_valid_financial_record_errors_preserve_full_denominators_and_independent_correct_fields(tmp_path, mutation, wrong):
    from moparse_eval.expected_report import validate_evidence
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    _, required = compiled(tmp_path, FINANCIAL_RECORDS)
    candidate = (FINANCIAL_RECORDS.replace('期末金額6', '期末金額7') if mutation == 'value' else
                 FINANCIAL_RECORDS.replace('\n  - 票據', '\n- 票據') if mutation == 'parent' else
                 FINANCIAL_RECORDS.rsplit('資金來源–', 1)[0] + '資金來源0。')
    actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
    assert not actual['blockers'] and not actual['pending_requirements']
    result = grade_layers(required, actual)
    assert result['publishable'], result['blockers']
    validate_evidence(result)
    assert result['layers']['B']['denominator'] == 8
    assert {o['id']: o['outcome'] for o in result['outcomes'] if o['layer'] == 'B'} == {
        f'B:{i}': 'incorrect' if i in wrong else 'correct' for i in range(8)}
    if mutation == 'value':
        assert result['layers']['L']['numerator'] == result['layers']['L']['denominator']


@pytest.mark.parametrize('mutation', ['no_facts', 'borrow_header', 'no_binding', 'borrow_parent', 'change_state_type'])
def test_internal_record_omission_or_forged_sources_are_rejected_before_comparison(tmp_path, mutation):
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown
    from tests.unit.test_cjk_circumstance_contract import compiled

    _, required = compiled(tmp_path, FINANCIAL_RECORDS)
    actual = read_candidate_markdown(FINANCIAL_RECORDS, sample_id=required['sample_id'])
    if mutation == 'no_facts':
        actual['business'] = []
    elif mutation == 'borrow_header':
        actual['business'][4]['attribute_source'] = deepcopy(actual['business'][0]['attribute_source'])
    elif mutation == 'no_binding':
        actual['relations'] = [e for e in actual['relations'] if e['type'] != 'field_binding']
    elif mutation == 'borrow_parent':
        group = next(r for r in actual['business'][4]['row_evidence'] if r['role'] == 'row_group')
        group['source']['lines'] = [6, 6]
    else:
        actual['business'][7]['semantic_type'] = 'financial_quantity'
    with pytest.raises(ValueError):
        grade_layers(required, actual)


def test_ratio_and_printed_not_applicable_fields_are_not_money_or_zero(tmp_path):
    from tests.unit.test_cjk_circumstance_contract import compiled

    text = ('某業務：營業收入73人民幣百萬元；營業成本51人民幣百萬元；毛利率（註）21.7%；'
            '營業收入比上年同期增減(0.8)%；營業成本比上年同期增減不適用。')
    _, required = compiled(tmp_path, text)
    assert [(f['attribute'], f['value']) for f in required['business']] == [
        ('營業收入', '73'), ('營業成本', '51'), ('毛利率（註）', '21.7'),
        ('營業收入比上年同期增減', '(0.8)'), ('營業成本比上年同期增減', '不適用')]
    assert required['business'][2]['qualifiers'] == {'unit': '%'}
    assert required['business'][3]['qualifiers'] == {'unit': '%', 'comparison_basis': '比上年同期'}
    assert required['business'][4]['semantic_type'] == 'printed_not_applicable'
    assert required['business'][4]['qualifiers'] == {'comparison_basis': '比上年同期'}


def test_a_generic_explicit_attribute_and_printed_subject_columns_keep_independent_non_numeric_facts():
    text = "Primary purpose; Engine Alpha: Scientific discovery, national security; Engine Beta: AI model training"
    result = read_field_sequence_requirements(text, SOURCE, scope=["Comparison"])
    assert result["matched"] is True and result["blockers"] == []
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in result["facts"]] == [
        ("Engine Alpha", "Primary purpose", "Scientific discovery, national security", "metric"),
        ("Engine Beta", "Primary purpose", "AI model training", "metric")]
    assert result["text_projection_complete"] is True
    for fact in result["facts"]:
        assert literal(text, fact["subject_source"]) == fact["subject"]
        assert literal(text, fact["attribute_source"]) == fact["attribute"]
        assert literal(text, fact["value_source"]) == fact["value"]
        assert fact["scope"] == ["Comparison"]
    assert len([edge for edge in result["relations"] if edge["type"] == "field_binding"]) == 2


@pytest.mark.parametrize("offset", [0, 40])
def test_a_printed_metric_declaration_gives_numeric_fields_precise_own_sources_without_scaling(offset):
    text = "Metric: Throughput; Engine Alpha: 20万元; Engine Beta: 20万元."
    source = {**SOURCE, "text_span": [offset, offset + len(text)]}
    before = deepcopy(source)
    result = read_field_sequence_requirements(text, source)
    assert source == before and result["blockers"] == []
    assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("Engine Alpha", "Throughput", "20", {"unit": "万元"}),
        ("Engine Beta", "Throughput", "20", {"unit": "万元"})]
    for fact, label in zip(result["facts"], ("Engine Alpha", "Engine Beta"), strict=True):
        start = text.index(label + ":") + len(label + ": ")
        assert fact["value_source"]["text_span"] == [offset + start, offset + start + 2]
        assert fact["raw_value"] == "20万元"
        assert fact["attribute_source"]["text_span"] == [offset + 8, offset + 18]
    validate_scalar_sources(result["facts"], {"source_fragments": [{"text": text, "source": source}]}, canonicalize=str.strip)


def test_complete_period_selectors_and_basis_are_not_reduced_to_their_calendar_year():
    text = "Gross margin; Year Ended March 31, 2028: 61%; Year Ended March 30, 2027: 56%; Change: Up 5 pts."
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is True and len(result["facts"]) == 2
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("Gross margin", "61", {"period": "March 31, 2028", "period_basis": "Year Ended", "unit": "%"}),
        ("Gross margin", "56", {"period": "March 30, 2027", "period_basis": "Year Ended", "unit": "%"})]
    for fact in result["facts"]:
        for key in ("period", "period_basis", "unit"):
            assert literal(text, fact["qualifier_sources"][key]) == fact["qualifiers"][key]
    [pending] = [p for p in result["pending_requirements"] if p["kind"] == "comparison_period_binding"]
    assert pending["label"] == "Change" and pending["value"] == "Up 5 pts."
    assert literal(text, pending["value_source"]) == "Up 5 pts."
    assert set().union(*(set(b["layers"]) for b in result["blockers"])) >= {"B", "L"}


def test_an_unknown_prefix_cannot_turn_a_record_name_into_a_metric_or_become_one_opaque_fact():
    text = "Container; Type A: Ready; Type B: Blocked"
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is True and result["facts"] == []
    [pending] = result["pending_requirements"]
    assert pending["text"] == text and pending["prefix"]["text"] == "Container"
    assert [(x["label"], x["value"]) for x in pending["segments"]] == [("Type A", "Ready"), ("Type B", "Blocked")]
    assert result["blockers"] and result["text_projection_complete"] is True


def test_an_actual_printed_schema_can_prove_an_otherwise_unknown_attribute_role():
    text = "Custom property; Alpha: ready; Beta: waiting"
    declaration = {"text": "Attribute: Custom property", "source": {"path": "<own-column-description>", "lines": [2, 2]}}
    result = read_field_sequence_requirements(text, SOURCE, schema=declaration)
    assert result["blockers"] == [] and len(result["facts"]) == 2
    assert result["scope"]["attribute_declaration"] == declaration
    assert {f["attribute"] for f in result["facts"]} == {"Custom property"}


@pytest.mark.parametrize("text", ["Revenue:17; Profit:5", "Narrative: Alpha; Beta",
                                  "Date and time:9:00; Location:https://example.invalid/notice"])
def test_ordinary_key_value_fields_time_and_urls_are_left_to_their_own_reader(text):
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is False and result["facts"] == []


def test_unread_chinese_complete_dates_are_kept_whole_instead_of_becoming_year_only_fields():
    text = "Revenue; 截至二〇二八年三月三十一日止六个月:17; 截至二〇二七年三月三十一日止六个月:11"
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is True
    assert all(f["qualifiers"].get("period") not in {"2028", "2028年", "2027", "2027年"} for f in result["facts"])
    assert len(result["facts"]) == 2 or result["pending_requirements"] and result["blockers"]
    if len(result["facts"]) == 2:
        for fact in result["facts"]:
            assert "三十一日" in fact["qualifiers"]["period"]
            assert literal(text, fact["qualifier_sources"]["period"]) == fact["qualifiers"]["period"]
            assert fact["qualifiers"].get("period_basis")
    assert result["text_projection_complete"] is True


def test_a_change_label_own_unit_does_not_turn_it_into_another_record_subject():
    text = "Gross margin; Year Ended March 31, 2028:61%; Year Ended March 30, 2027:56%; Change (%):5"
    result = read_field_sequence_requirements(text, SOURCE)
    assert len(result["facts"]) == 2
    assert any(item["kind"] == "comparison_period_binding" and item["label"] == "Change (%)"
               for item in result["pending_requirements"])
    assert result["text_projection_complete"] is True


@pytest.mark.parametrize("text", ["Metric:; Alpha:17; Beta:11", "Revenue; 2028年3月:17; 2027年3月:11"])
def test_empty_attributes_and_incomplete_dates_never_create_complete_business_facts(text):
    result = read_field_sequence_requirements(text, SOURCE)
    assert result["matched"] is True and result["facts"] == []
    assert result["pending_requirements"] and result["blockers"]


def test_caller_qualifiers_without_their_actual_sources_remain_partial_instead_of_borrowing_the_value_source():
    result = read_field_sequence_requirements("Revenue; 2028年:17; 2027年:11", SOURCE, qualifiers={"unit": "万元"})
    assert len(result["facts"]) == 2
    assert any(item["reason"] == "field_sequence_qualifier_source_unresolved" for item in result["pending_requirements"])
