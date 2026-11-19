"""Independent invented answers through native-format readers to final credits.

Only literal text, invented JSON and tmp_path reference text are used. Expected
edit counts below are hand authored, never computed by the implementation.
"""

from copy import deepcopy

import pytest

from moparse_eval.ast_alignment import METHOD
from moparse_eval.layer_aggregation import summarize_layers
from moparse_eval.native_candidate import bind_native_syntax_scopes, expose_native_heading_fields
from moparse_eval.native_evaluation import requirement_inventory, retain_limits
from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection
from moparse_eval.saved_native import read_saved_native
from moparse_eval.three_layer import grade_layers, read_candidate, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored
from tests.unit.test_three_layer_native_formats import (
    _docling,
    _glm,
    _mineru,
    _observation,
    _paddle,
    _visual,
)


def compare(tmp_path, expected, candidate, *, pipeline='invented'):
    graph = compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast')
    required = evaluation_projection(graph)
    actual = read_candidate_markdown(candidate, sample_id=required['sample_id'], pipeline=pipeline)
    return grade_layers(required, actual, scoring_method=METHOD)


def t_edits(score):
    return {key: sum(row['edits'][key] for row in score['outcomes'] if row['layer'] == 'T')
            for key in ('S', 'D', 'I')}


@pytest.mark.parametrize(('edit', 'expected_credits', 'ordered'), [
    ('identical', [1, 1, 1, 1, 1, 1], True),
    ('move_records', [1, 1, 1, 1, 1, 1], False),
    ('swap_signs', [1, 1, 1, 1, 0, 0], True),
    ('percentage_points', [1, 1, 1, 1, 1, 0], True),
    ('missing_field', [1, 1, 1, 1, 1, 0], False),
    ('changed_amount', [0, 1, 1, 1, 1, 1], True),
    ('explicit_minus', [1, 1, 1, 1, 1, 1], True),
])
def test_two_record_asts_keep_the_unshared_scalar_and_printed_order(tmp_path, edit, expected_credits, ordered):
    from moparse_eval.continuous_projection import extend_projection

    north = '- North (USD millions): 2025: 17; 2024: 26; Yield: (3%).'
    south = '- South (USD millions): 2025: 28; 2024: 20; Yield: 3%.'
    title = '# Invented register\n\n'
    graph = compile_requirement_graph(authored(tmp_path, title + north + '\n' + south), comparison_contract='document_ast')
    required = extend_projection(graph, evaluation_projection(graph))
    rows = [north, south]
    if edit == 'move_records':
        rows.reverse()
    elif edit == 'swap_signs':
        rows = [north.replace('(3%)', '3%'), south.replace('3%.', '(3%).')]
    elif edit == 'percentage_points':
        rows[1] = south.replace('3%.', '3 percentage points.')
    elif edit == 'missing_field':
        rows[1] = south.split('; Yield:')[0] + '.'
    elif edit == 'changed_amount':
        rows[0] = north.replace('17;', '18;')
    elif edit == 'explicit_minus':
        rows[0] = north.replace('(3%)', '-3%')
    actual = read_candidate_markdown(title + '\n'.join(rows), sample_id=required['sample_id'])
    result = grade_layers(required, actual, scoring_method=METHOD)
    fields = [r for r in result['outcomes'] if r['layer'] == 'B']
    assert [f['id'] for f in fields] == ['B:0', 'B:1', 'B:2', 'B:3', 'B:content:0', 'B:content:1']
    assert [f['credit'] for f in fields] == expected_credits
    order, = [r for r in result['outcomes'] if r['role'] == 'reading_order']
    assert bool(order['credit']) == ordered
    record = fields[4]['expected']
    body = north.removeprefix('- ')
    for key, word in [('source', '(3%)'), ('subject_source', 'North'), ('attribute_source', 'Yield'), ('value_source', '3')]:
        assert body[slice(*record[key]['text_span'])] == word
    assert [body[slice(*s['text_span'])] for s in record['accounting_sign_sources']] == ['(', ')']
    assert record['qualifiers'] == {'unit': '%'}
    assert record['dated_child_ids'] == ['B:0', 'B:1']
    if edit == 'move_records':
        assert [f['actual']['subject_source']['lines'] for f in fields[4:]] == [[4, 4], [3, 3]]


@pytest.mark.parametrize('extra', [
    'Yield: 3%; Rework: 2%', 'Yield: 3% if approved', 'Yield: (3%]', 'Yield: (-3%)', 'Yield: 3',
])
def test_unaccounted_record_content_keeps_its_original_owner(tmp_path, extra):
    from moparse_eval.continuous_document import _scalar_content_views
    from moparse_eval.continuous_projection import extend_projection

    source = '# Register\n\n- North (USD millions): 2025: 17; 2024: 26; ' + extra
    graph = compile_requirement_graph(authored(tmp_path, source), comparison_contract='document_ast')
    required = extend_projection(graph, evaluation_projection(graph))
    assert required['source_form_requirements']
    assert not _scalar_content_views(required)


def test_relative_comparison_in_a_dated_record_retains_the_complete_printed_basis(tmp_path):
    from moparse_eval.continuous_projection import extend_projection

    original = '# 仓储\n\n- 检修费（万元）：2025年末73；2024年末60；本年末比上年末变动2.1%；2023年末90。'
    graph = compile_requirement_graph(authored(tmp_path, original), comparison_contract='document_ast')
    required = extend_projection(graph, evaluation_projection(graph))
    for before, after, credit in [('变动2.1', '变动：2.1', 1), ('2.1%', '2.1个百分点', 0),
                                  ('本年末比上年末', '上年末比本年末', 0)]:
        candidate = read_candidate_markdown(original.replace(before, after), sample_id=required['sample_id'])
        result = grade_layers(required, candidate, scoring_method=METHOD)
        fields = [r for r in result['outcomes'] if r['layer'] == 'B']
        assert [f['credit'] for f in fields] == [1, 1, 1, credit]
        view = fields[-1]['expected']
        assert view['qualifiers'] == {'unit': '%', 'comparison_basis': '本年末比上年末'}
        span = view['qualifier_sources']['comparison_basis']['text_span']
        assert original.split('- ')[1][slice(*span)] == '本年末比上年末'


def test_a_field_only_vote_gets_its_owner_from_the_whole_original_record(tmp_path):
    from moparse_eval.continuous_projection import extend_projection

    text = '# 测量\n\n- 业务回报率：2026年0.91；2025年0.81；2024年0.83；本年同比增减+0.10个百分点。'
    graph = compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast')
    required = extend_projection(graph, evaluation_projection(graph))
    for payload, credit in [('+0.10', 1), ('-0.10', 0)]:
        candidate = read_candidate_markdown(text.replace('+0.10', payload), sample_id=required['sample_id'])
        result = grade_layers(required, candidate, scoring_method=METHOD)
        field, = [r for r in result['outcomes'] if r['id'] == 'B:content:0']
        assert field['expected']['source_form_extent'] == 'field'
        for side in ('expected', 'actual'):
            fact = field[side]
            assert fact['subject'] == '业务回报率'
            assert fact['subject_source']['text_span'][1] < fact['series_field_source']['text_span'][0]
        assert field['credit'] == credit


@pytest.mark.parametrize('second', ['3%', '3 percentage points'])
def test_duplicate_record_names_cannot_use_a_sign_or_unit_to_choose_the_answer(tmp_path, second):
    from moparse_eval.continuous_projection import extend_projection

    line = '- North (USD millions): 2025: 17; 2024: 26; Yield: (3%).'
    text = '# Register\n\n' + line
    graph = compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast')
    required = extend_projection(graph, evaluation_projection(graph))
    changed = line.replace('(3%)', second)
    for rows in ((line, changed), (changed, line)):
        actual = read_candidate_markdown('# Register\n\n' + '\n'.join(rows), sample_id=required['sample_id'])
        result = grade_layers(required, actual, scoring_method=METHOD)
        field, = [r for r in result['outcomes'] if r['id'] == 'B:content:0']
        assert field['outcome'] == 'unresolved' and field['credit'] is None


def test_direct_list_fields_keep_their_printed_parent_when_values_repeat(tmp_path):
    prefix = '# Returns\n\n'
    def section(label):
        return f'- {label}\n  - Balance: 13; Basis: gross'
    coast, inland = section('Coastal'), section('Inland')
    expected = prefix + coast + '\n' + inland
    for candidate, credits in [(prefix + inland + '\n' + coast, [1, 1, 1, 1]),
                               (prefix + coast + '\n' + coast, [1, 1, 0, 0])]:
        score = compare(tmp_path, expected, candidate)
        fields = [r for r in score['outcomes'] if r['role'] == 'metric']
        assert [r['credit'] for r in fields] == credits
        layout = [r for r in score['outcomes'] if r['role'] == 'field_binding']
        assert [r['credit'] == 1 for r in layout] == [bool(c) for c in credits]


def test_conditional_list_parent_remains_attached_to_its_formula(tmp_path):
    title = '# Interest\n\n'
    normal = '- If a quarter is complete\n  - Interest = (A + B) / 4'
    short = '- If a quarter is partial\n  - Interest = (A - B) / 4'
    expected = title + normal + '\n' + short
    result = compare(tmp_path, expected, title + short + '\n' + normal)
    assert [r['credit'] for r in result['outcomes'] if r['role'] == 'metric'] == [1, 1]
    observed = [r['actual'] for r in result['outcomes'] if r['role'] == 'metric']
    assert [r['row_evidence'][0]['text'] for r in observed] == [
        'If a quarter is complete', 'If a quarter is partial']
    swapped = expected.replace('A + B', 'A x B').replace('A - B', 'A + B').replace('A x B', 'A - B')
    for candidate in (swapped, expected.replace('If a quarter is', 'Unless a quarter is')):
        wrong = compare(tmp_path, expected, candidate)
        assert [r['credit'] for r in wrong['outcomes'] if r['role'] == 'metric'] == [0, 0]


def test_list_parent_and_field_label_cannot_exchange_roles(tmp_path):
    source = '# Inventory\n\n- Coastal\n  - Balance: 13'
    swapped = '# Inventory\n\n- Balance\n  - Coastal: 13'
    score = compare(tmp_path, source, swapped)
    assert [r['credit'] for r in score['outcomes'] if r['role'] == 'metric'] == [0]
    assert all(r['credit'] < 1 for r in score['outcomes'] if r['role'] == 'field_binding')


def test_repeated_metric_name_cannot_create_an_extra_parent(tmp_path):
    source = '# Inventory\n\n- Balance: 13'
    for record in ('- Balance\n  - Balance: 13', '- Category: Balance; Balance: 13'):
        result = compare(tmp_path, source, '# Inventory\n\n' + record)
        assert [r['credit'] for r in result['outcomes'] if r['role'] == 'metric'] == [0]
        assert all(r['credit'] < 1 for r in result['outcomes'] if r['role'] == 'field_binding')


def test_prose_under_labelled_list_parent_uses_its_printed_value(tmp_path):
    text = ('# Register\n\n- Region: Coastal\n  - Controls\n    - Vehicles remain under inspection.\n'
            '- Region: Inland\n  - Controls\n    - If needed, deploy the available vehicles.')
    graph = compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast')
    issues = {r['id'] for r in graph['unresolved'] if r['reason'] == 'list_group_scope_interpretation_unsupported'}
    assert issues
    receipts = [r for r in graph['comparison_coverage']['analysis_limitations'] if r['issue_id'] in issues]
    assert all(r['status'] != 'blocking' for r in receipts)
    wrong = text.replace('- Region: Inland', '- Region: Coastal')
    for candidate, passes in [(text, True), (wrong, False)]:
        result = compare(tmp_path, text, candidate)
        assert (result['layers']['L']['score'] == 100) == passes


@pytest.mark.parametrize('damage', ['earlier_parent', 'displaced_value', 'unrelated_label', 'missing_field'])
def test_list_field_receipt_rejects_borrowed_sources(tmp_path, damage):
    from moparse_eval.document_ast_comparison import comparison_requirement_coverage

    text = '# Inventory\n\n- Coastal\n  - Balance: 11\n- Inland\n  - Balance: 27\n- Coastal\n  - Balance: 13'
    graph = compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast')
    fact = next(n for n in graph['nodes'] if n.get('value') == '13')
    earlier = next(n for n in graph['nodes'] if n.get('value') == '11')
    if damage == 'earlier_parent':
        fact['row_evidence'] = earlier['row_evidence']
    elif damage == 'displaced_value':
        fact['value_source']['text_span'][0] += 1
    elif damage == 'unrelated_label':
        fact['attribute_source'] = earlier['attribute_source']
    else:
        child = next(r for r in graph['context']['syntax'] if r.get('list_field_ids') == [fact['id']])
        child['list_field_ids'] *= 2
    with pytest.raises(ValueError, match='List (item|field)'):
        comparison_requirement_coverage(graph)


def test_nested_caption_attaches_to_its_own_list_item(tmp_path):
    source = '# Observations\n\n- Coastal\n  - ![Survey map](coast.png)\n- Inland\n  - ![Survey map](inland.png)'
    altered = source.replace('- Inland', '- Coastal')
    graph = compile_requirement_graph(authored(tmp_path, source), comparison_contract='document_ast')
    rels = [r for r in graph['relations'] if r['type'] == 'list_membership' and 'parents' in r['right']]
    assert [r['right']['parents'] for r in rels] == [['Coastal'], ['Inland']]
    assert [r['binding_evidence']['rows'][0]['source']['lines'] for r in rels] == [[3, 3], [5, 5]]
    for candidate, full in [(source, True), (altered, False)]:
        result = compare(tmp_path, source, candidate)
        rows = [r for r in result['outcomes'] if r['id'] in {e['id'] for e in rels}]
        assert len(rows) == 2 and all(r['credit'] == 1 for r in rows) == full


def test_row_fields_follow_the_named_category_through_reordering(tmp_path):
    a = '- Segment: Coastal; Revenue: 17; Margin: 2.5%'
    b = '- Segment: Inland; Revenue: 35; Margin: 4.2%'
    title = '# Operations\n\n'
    original = title + a + '\n' + b
    for candidate, credit in [(b + '\n' + a, 1),
                              (a.replace('Coastal', 'Inland') + '\n' + b.replace('Inland', 'Coastal'), 0),
                              ('| Segment | Revenue | Margin |\n| --- | --- | --- |\n| Inland | 35 | 4.2% |\n| Coastal | 17 | 2.5% |', 1),
                              ('| Market | Revenue | Margin |\n| --- | --- | --- |\n| Inland | 35 | 4.2% |\n| Coastal | 17 | 2.5% |', 0)]:
        score = compare(tmp_path, original, title + candidate)
        fields = [r for r in score['outcomes'] if r['role'] == 'metric' and r['expected']['attribute'] != 'Segment']
        assert [r['credit'] for r in fields] == [credit] * 4
        if credit:
            assert [r['actual']['record_axis']['text'] for r in fields] == ['Coastal'] * 2 + ['Inland'] * 2


def test_change_field_uses_the_sibling_metric_label_even_if_amounts_match(tmp_path):
    a = '- Receipts: 13; year on year: up 20%'
    b = '- Expenses: 13; year on year: up 10%'
    prefix = '# Results\n\n'
    for other, wanted in [(b + '\n' + a, 1),
                          (a.replace('20%', '10%') + '\n' + b.replace('10%', '20%'), 0)]:
        score = compare(tmp_path, prefix + a + '\n' + b, prefix + other)
        fields = [r for r in score['outcomes'] if r['role'] == 'metric' and r['expected']['attribute'] == 'year on year']
        assert [r['credit'] for r in fields] == [wanted, wanted]


def test_record_axis_cannot_borrow_another_items_category(tmp_path):
    from moparse_eval.document_ast_comparison import comparison_requirement_coverage

    expected = '# Summary\n\n- Category: Northern; Returns: 7\n- Category: Eastern; Returns: 7'
    graph = compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast')
    a, b = [f for f in graph['nodes'] if f.get('record_axis')]
    b['record_axis'] = a['record_axis']
    with pytest.raises(ValueError, match='Record axis'):
        comparison_requirement_coverage(graph)
    neutral = read_candidate_markdown('- Unit: USD; year on year: 7%\n- Statement: 7\n- Category: 9万元; Returns: 7')
    assert all(not f.get('record_axis') for f in neutral['business'])
@pytest.mark.parametrize("caption,values,axis_credit,value_credit", [
    ("Unit: USD million.", ("7", "11"), 1, 1),
    ("Unit: EUR million.", ("7", "11"), 0, 0),
    ("", ("7", "11"), 0, 0),
    ("Unit: USD thousand.", ("7", "11"), 1, 0),
    ("Unit: USD thousand.", ("7000", "11000"), 1, 1),
])
def test_inherited_caption_checks_the_existing_field_without_adding_votes(tmp_path, caption, values, axis_credit, value_credit):
    def statement(unit, first, second):
        return (f"# Statement of cash flows\n\n{unit}\n\n- Cash and cash equivalents\n"
                f"  - Reserve:2029年{first};2028年{second}")

    source = statement("Unit: USD million.", "7", "11")
    score = compare(tmp_path, source, statement(caption, *values))
    assert {layer: item['denominator'] for layer, item in score['layers'].items()} == {'T': 86, 'L': 5, 'B': 3}
    fields = [r for r in score['outcomes'] if r['role'] == 'field_binding']
    axes = [next(c for c in r['components'] if c['relation'] == 'row_column_period_axes') for r in fields]
    metrics = [r for r in score['outcomes'] if r['layer'] == 'B' and r['role'] == 'metric']
    assert [a['credit'] for a in axes] == [axis_credit] * 2
    assert all(set(a['caption_dimensions']) == {'unit', 'currency'} for a in axes)
    assert [r['credit'] for r in metrics] == [value_credit] * 2


def test_business_amounts_follow_the_printed_group_when_same_named_rows_move(tmp_path):
    title = "# Statement of financial position\n\nUnit: USD million.\n\n"
    current = "- Current assets\n  - Balance:2029年7;2028年11"
    long_term = "- Non-current assets\n  - Balance:2029年17;2028年13"
    expected = title + current + "\n" + long_term
    result = compare(tmp_path, expected, title + long_term + "\n" + current)
    rows = [r for r in result["outcomes"] if r["layer"] == "B"]
    assert [(r["actual"]["value"], r["credit"]) for r in rows] == [
        ("7", 1), ("11", 1), ("17", 1), ("13", 1)]
    assert result["layers"]["B"]["denominator"] == 4


def test_equal_amounts_cannot_prove_membership_in_a_different_group(tmp_path):
    a = "- Current assets\n  - Balance:2029年7;2028年11"
    b = a.replace("Current assets", "Non-current assets")
    prefix = "# Statement of financial position\n\nUnit: USD million.\n\n"
    result = compare(tmp_path, prefix + a + "\n" + b, prefix + a + "\n" + a)
    rows = [r for r in result["outcomes"] if r["layer"] == "B"]
    assert [r["credit"] for r in rows] == [1, 1, 0, 0]
    bindings = [r for r in result["outcomes"] if r["layer"] == "L" and r["role"] == "field_binding"]
    assert len(bindings) == 4 and all(r["credit"] < 1 for r in bindings[2:])


def test_nested_parent_order_survives_printed_metric_path_equivalence(tmp_path):
    prefix = "# Statement of financial position\n\nUnit: USD million.\n\n"
    source = prefix + "- Assets\n  - Current assets\n    - Balance:2029年7;2028年11"
    for path, credit in [("Assets / Current assets / Balance", 1), ("Current assets / Assets / Balance", 0)]:
        public = prefix + f"- {path}\n  - 2029年：7\n    - 单位：USD million\n  - 2028年：11\n    - 单位：USD million"
        result = compare(tmp_path, source, public)
        assert [r["credit"] for r in result["outcomes"] if r["layer"] == "B"] == [credit, credit]


@pytest.mark.parametrize("caption,unit", [("USD million", "USD million"), ("单位：人民币万元", "人民币万元")])
@pytest.mark.parametrize("second_caption", ["", "单位：港元百万元"])
def test_a_shared_unit_is_consumed_by_its_own_physical_table(caption, unit, second_caption):
    from moparse_eval.native_grid_fields import syntax_grid_fields

    first = "| 项目 | 2029年 |\n| --- | --- |\n| 钢 | 7 |"
    second = "| 项目 | 2030年 |\n| --- | --- |\n| 铜 | 7 |"
    text = "\n\n".join(s for s in [caption, first, second_caption, second] if s)
    evidence = read_candidate_markdown(text)
    fields = syntax_grid_fields(evidence)
    assert len(fields) == 2
    assert [f["qualifiers"].get("unit") for f in fields] == [unit, "港元百万元" if second_caption else None]
    for f in evidence["business"]:
        if f["attribute"] == "铜":
            assert f["qualifiers"].get("unit") == ("港元百万元" if second_caption else None)
    if second_caption:
        assert fields[1]["unit_evidence"][1]["lines"] == [7, 7]
    else:
        assert fields[1]["unit_evidence"] is None


def test_page_range_belongs_to_the_printed_document_in_the_final_business_vote(tmp_path):
    start = "# Statement of financial position\n\nUnit: USD million.\n\n- Reserve:2029年7;2028年11\n\n"
    note = "Notes on pages 31 to 46 are part of these financial statements."
    for changed, credit in [(note, 1), (note.replace("31 to 46", "46 to 31"), 0),
                            (note.replace("these financial statements", "this annual report"), 0),
                            (note.replace("are part of", "are not part of"), 0)]:
        result = compare(tmp_path, start + note, start + changed)
        assert [(r["role"], r["credit"]) for r in result["outcomes"] if r["layer"] == "B"] == [
            ("source_form_assertion", credit), ("metric", 1), ("metric", 1)]
        assert result["layers"]["B"]["denominator"] == 3


@pytest.mark.parametrize("when", ["2028年2月29日", "2028-02-29", "February 29, 2028"])
def test_dated_list_field_preserves_the_whole_calendar_selector_and_local_sources(when):
    from moparse_eval.expected_readback import markdown_observation
    md = f"- 短期负债 / 借款\n  - 附注：9\n  - {when}：17\n    - 单位：USD million\n  - 2027年12月31日：17\n    - 单位：人民币万元"
    for g in (read_candidate_markdown(md), read_candidate(markdown_observation(md, sample_id="loans", pipeline="test", pages=[1]))):
        facts = [f for f in g["business"] if f["role"] == "metric"]
        assert [(f["attribute"], f["value"]) for f in facts] == [("短期负债 / 借款", "17")] * 2
        for i, (f, period, unit, currency) in enumerate(zip(facts, (when, "2027年12月31日"), ("USD million", "人民币万元"), ("USD", "人民币"), strict=True)):
            assert f["qualifiers"] == {"period": period, "note": "9", "unit": unit, "currency": currency}
            loc = f["qualifier_provenance"]["period"]["source"]
            assert loc["lines"] == [3 + 2*i] * 2 and loc["text_span"] == [0, len(period)]


@pytest.mark.parametrize("label", ["2027年2月29日", "2028-02-30", "December 40, 2029", "2028年12月31日以后可能"])
def test_invalid_dates_and_prose_cannot_supply_a_dated_financial_field(label):
    g = read_candidate_markdown(f"- 借款\n  - {label}：7\n    - 单位：人民币万元")
    assert not any(f["attribute"] == "借款" and f["qualifiers"].get("period") for f in g["business"])


@pytest.mark.parametrize("unit", ["（人民币万元", "人民币万元）"])
def test_invalid_printed_day_keeps_amount_and_complete_unit_with_separate_evidence(unit):
    text = f"- 保证金\n  - 2027年 2月31日：83\n    - 单位：{unit}\n  - 2028年 2月29日：91\n    - 单位：（人民币百万"
    graph = read_candidate_markdown(text)
    first, second = [f for f in graph['business'] if f['attribute'] == '保证金']
    assert (first['value'], first['qualifiers']) == ('83', {'unit': '人民币万元', 'currency': '人民币'})
    printed = first['role_basis']['unresolved_period']
    assert printed['text'] == '2027年 2月31日' and printed['source']['lines'] == [2, 2]
    assert any(b['reason'] == 'invalid_printed_calendar_period' and b['source'] == printed['source'] for b in graph['blockers'])
    proof = first['qualifier_provenance']['unit']['source']
    assert proof['lines'] == [3, 3] and ('单位：' + unit)[slice(*proof['text_span'])] == '人民币万元'
    assert second['value'] == '91' and second['qualifiers'] == {'period': '2028年 2月29日'}


def test_exact_document_and_partial_wording_without_grammar_gate(tmp_path):
    text = '# 治理\n\n委員積極參與調研。\n\n董事接受專業培訓。'
    good = compare(tmp_path, text, text)
    assert [good['layers'][k]['score'] for k in ('T', 'L', 'B')] == [100, 100, 100]
    bad = compare(tmp_path, text, text.replace('專業', '職業'))
    assert t_edits(bad) == {'S': 1, 'D': 0, 'I': 0}
    assert bad['layers']['L']['score'] == 100
    assert 0 < bad['layers']['B']['score'] < 100
    assert bad['comparison_complete']


@pytest.mark.parametrize('candidate,edits,score', [
    ('甲乙丙。', {'S': 0, 'D': 0, 'I': 0}, 100),
    ('甲丁丙。', {'S': 1, 'D': 0, 'I': 0}, 75),
    ('甲丙。', {'S': 0, 'D': 1, 'I': 0}, 75),
    ('甲乙丁丙。', {'S': 0, 'D': 0, 'I': 1}, 75),
])
def test_hand_authored_character_counts(tmp_path, candidate, edits, score):
    result = compare(tmp_path, '甲乙丙。', candidate)
    assert t_edits(result) == edits
    assert result['layers']['T']['denominator'] == 4
    assert result['layers']['T']['score'] == score


def test_missing_node_is_local_and_new_text_is_debited(tmp_path):
    text = '甲方開展調研。\n\n乙方完成培訓。'
    dropped = compare(tmp_path, text, '甲方開展調研。')
    assert t_edits(dropped) == {'S': 0, 'D': 7, 'I': 0}
    assert any(r['credit'] == 1 for r in dropped['outcomes'] if r['layer'] == 'B')
    extra = compare(tmp_path, text, text + '\n\n無關文字。')
    assert t_edits(extra) == {'S': 0, 'D': 0, 'I': 5}
    duplicate = compare(tmp_path, text, text + '\n\n甲方開展調研。')
    assert duplicate['layers']['T']['score'] < 100


@pytest.mark.parametrize('expected,candidate', [
    ('甲方積極參與調研並接受培訓。', '甲方積極參與調研\n\n並接受培訓。'),
    ('甲方積極參與調研\n\n並接受培訓。', '甲方積極參與調研並接受培訓。'),
    ('Alpha conducts research and training.', 'Alpha conducts research\n\nand training.'),
])
def test_legal_splits_and_merges_keep_text(tmp_path, expected, candidate):
    score = compare(tmp_path, expected, candidate)
    assert score['layers']['T']['score'] == 100
    assert score['layers']['B']['score'] == 100


def test_reversal_and_wrong_heading_are_relation_errors(tmp_path):
    original = '# 調研\n\n甲方積極參與調研。\n\n# 培訓\n\n乙方完成專業培訓。'
    swapped = '# 調研\n\n乙方完成專業培訓。\n\n# 培訓\n\n甲方積極參與調研。'
    result = compare(tmp_path, original, swapped)
    assert result['layers']['T']['score'] == 100
    assert 0 < result['layers']['L']['score'] < 100
    assert any(p['relation'] == 'heading_ownership' and p['credit'] == 0
               for r in result['outcomes'] if r['layer'] == 'L' for p in r['components'])


@pytest.mark.parametrize('before,after', [('1000', '9000'), ('萬元', '元'), ('不得', '必須'), ('以上', '以下')])
def test_critical_source_content_cannot_pass_by_high_similarity(tmp_path, before, after):
    text = '甲公司不得發行1000萬元以上的債券。'
    result = compare(tmp_path, text, text.replace(before, after))
    assert result['layers']['T']['score'] > 70
    assert result['layers']['B']['score'] == 0
    assert result['layers']['L']['score'] == 100


def test_typed_amount_is_zero_with_correct_structure(tmp_path):
    result = compare(tmp_path, 'Revenue: 1000; Profit: 50', 'Revenue: 9000; Profit: 50')
    values = {r['expected']['attribute']: r['credit'] for r in result['outcomes'] if r['layer'] == 'B'}
    assert values == {'Revenue': 0, 'Profit': 1}
    assert result['layers']['B']['score'] == 50
    assert result['layers']['L']['score'] == 100


def test_field_binding_checks_column_identity_after_fuzzy_correspondence(tmp_path):
    text = '| Name | Revenue |\n| --- | --- |\n| Delta | 17 |'
    good = compare(tmp_path, text, text)
    wrong = compare(tmp_path, text, text.replace('Revenue', 'Profit'))
    assert good['layers']['L']['score'] == 100
    # Name is intact. Revenue's membership is intact, but its column axis is
    # wrong: (1 + (1+0)/2) / 2 = 3/4, independent of the unchanged value 17.
    assert wrong['layers']['L']['score'] == 75
    assert wrong['layers']['B']['score'] == 50
    assert any(p['relation'] == 'row_column_period_axes' and p['credit'] == 0
               for r in wrong['outcomes'] if r['layer'] == 'L' for p in r['components'])


def test_same_named_fields_do_not_borrow_other_parent_values(tmp_path):
    expected = '# Alpha\n\nRevenue: 1000\n\n# Beta\n\nRevenue: 9000'
    candidate = '# Alpha\n\nRevenue: 9000\n\n# Beta\n\nRevenue: 1000'
    score = compare(tmp_path, expected, candidate)
    assert score['layers']['B']['score'] == 0
    assert score['layers']['L']['score'] == 100


def test_one_occurrence_cannot_satisfy_two_expected_nodes(tmp_path):
    result = compare(tmp_path, '委員參與調研。\n\n委員參與調研。', '委員參與調研。')
    assert t_edits(result) == {'S': 0, 'D': 7, 'I': 0}
    assert result['layers']['B']['score'] == 50


def test_inserted_condition_is_not_skipped(tmp_path):
    result = compare(tmp_path, 'Alpha shall pay the fee.', 'Alpha shall pay if approved the fee.')
    assert t_edits(result)['I'] > 0
    assert result['layers']['B']['score'] == 0


@pytest.mark.parametrize('body', ['Revenue: 1000', 'Alpha shall pay the fee.'])
@pytest.mark.parametrize('heading', ['If approved', 'Unless rejected', '仅在批准后', '若经批准', 'Not approved'])
def test_new_conditional_heading_changes_its_business_scope(tmp_path, body, heading):
    result = compare(tmp_path, body, f'# {heading}\n\n{body}')
    assert result['layers']['B']['score'] == 0
    assert result['layers']['L']['score'] < 100
    assert t_edits(result)['I'] > 0
    same = compare(tmp_path, f'# {heading}\n\n{body}', f'# {heading}\n\n{body}')
    assert same['layers']['B']['score'] == 100
    wrapper = compare(tmp_path, body, '# Report\n\n' + body)
    assert wrapper['layers']['B']['score'] == 100


@pytest.mark.parametrize('body', ['Revenue: 1000', '甲公司積極參與調研。'])
def test_combined_document_title_and_separate_own_title_fragments(tmp_path, body):
    expected = '# 甲企業年度公告\n\n## 收入\n\n' + body
    actual = '# 甲企業\n\n# 年度公告\n\n## 收入\n\n' + body
    result = compare(tmp_path, expected, actual)
    assert result['layers']['B']['score'] == 100
    wrong = compare(tmp_path, expected, actual.replace('甲企業', '乙企業'))
    assert wrong['layers']['B']['score'] == 0


@pytest.mark.parametrize('company,expected_credit', [('甲企业', 100), ('甲企业集团', 0)])
@pytest.mark.parametrize('brand_prefix', ['', 'ACME '])
def test_saved_native_bilingual_brand_title_keeps_complete_company_fragment(tmp_path, company, expected_credit, brand_prefix):
    expected = '# 甲企业\n\n## 年度公告\n\n### 调研\n\n甲方完成專業培訓。'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    native = {'pages': [{'page': 1, 'branch': 'glm', 'raw': {'json_result': [[
        {'index': 0, 'label': 'title', 'content': f'{brand_prefix}{company} ACME GROUP CO., LTD.'},
        {'index': 1, 'label': 'title', 'content': '年度公告'},
        {'index': 2, 'label': 'title', 'content': '调研'},
        {'index': 3, 'label': 'text', 'content': '甲方完成專業培訓。'},
    ]]}}]}
    observed, _ = expose_native_heading_fields(read_saved_native(native, observation))
    actual = read_candidate(observed)
    bind_native_syntax_scopes(actual)
    result = grade_layers(required, actual, scoring_method=METHOD)
    assert result['layers']['B']['score'] == expected_credit


def test_partial_scope_context_disambiguates_same_label_without_using_values(tmp_path):
    expected = '# Report\n\n## Financials\n\n### Revenue\n\nNote: 1000\n\n### Profit\n\nNote: 50'
    actual = '# Report\n\n## Revenue\n\nNote: 1000\n\n## Profit\n\nNote: 50'
    result = compare(tmp_path, expected, actual)
    assert result['layers']['B']['complete']
    alignment = result['document_comparison']['typed_alignment']
    assert all(r['status'] == 'matched' for r in alignment['rows'])
    changed = compare(tmp_path, expected, actual.replace('1000', '9000'))
    assert all(r['status'] == 'matched' for r in changed['document_comparison']['typed_alignment']['rows'])
    assert [r['actual_pieces'][0]['index'] for r in alignment['rows']] == [r['actual_pieces'][0]['index'] for r in changed['document_comparison']['typed_alignment']['rows']]


def test_reader_failure_is_not_an_edit_deletion(tmp_path):
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, '甲方參與調研。'), comparison_contract='document_ast'))
    failed = read_candidate_markdown('', sample_id=required['sample_id'])
    failed['status'] = 'failed'
    with pytest.raises(ValueError, match='reader_failure'):
        grade_layers(required, failed, scoring_method=METHOD)
    deleted = compare(tmp_path, '甲方參與調研。', '')
    assert t_edits(deleted) == {'S': 0, 'D': 7, 'I': 0}


@pytest.mark.parametrize('factory', [_docling, _paddle, _glm, _mineru, _visual])
def test_saved_table_formats_run_to_final_scores(tmp_path, factory):
    text = '| Name | Revenue | Profit |\n| --- | --- | --- |\n| Delta | 17 | 5 |'
    if factory in (_mineru, _visual):
        text = 'Results\n\n' + text  # Both invented native fixtures print this caption.
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    observed, _ = expose_native_heading_fields(read_saved_native(factory(), observation))
    actual = read_candidate(observed)
    bind_native_syntax_scopes(actual)
    score = grade_layers(required, actual, scoring_method=METHOD)
    assert [score['layers'][k]['score'] for k in ('T', 'L', 'B')] == [100, 100, 100]
    summary = summarize_layers([score])
    assert summary['score'] == 100 and not summary['publication_authorized']


def test_old_readiness_cannot_erase_new_credits(tmp_path):
    text = '委員參與調研。'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast'))
    score = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']), scoring_method=METHOD)
    mask = {'layers': {k: {'state': 'blocked', 'not_comparable_reasons': {r['id']: 'old_limit' for r in score['outcomes'] if r['layer'] == k}}
                       for k in ('T', 'L', 'B')}}
    retained = retain_limits(score, mask, requirement_inventory(required))
    assert retained['score'] == 100
    assert retained['outcomes'] == score['outcomes']


def test_pipeline_labels_are_irrelevant(tmp_path):
    a = compare(tmp_path, 'Revenue: 1000', 'Revenue: 9000', pipeline='P01')
    b = compare(tmp_path, 'Revenue: 1000', 'Revenue: 9000', pipeline='renamed')
    assert a['layers'] == b['layers']
    assert a['outcomes'] == b['outcomes']


def test_component_tampering_is_rejected(tmp_path):
    score = compare(tmp_path, 'Revenue: 1000', 'Revenue: 9000')
    damaged = deepcopy(score)
    next(r for r in damaged['outcomes'] if r['layer'] == 'B')['credit'] = 1
    with pytest.raises(ValueError, match='components'):
        summarize_layers([damaged])


def test_display_wrapper_and_actual_reversal(tmp_path):
    text = '甲方參與調研。\n\n乙方完成培訓。'
    wrapped = compare(tmp_path, text, '# 文件\n\n' + text)
    assert wrapped['layers']['L']['score'] == 100
    assert wrapped['layers']['B']['score'] == 100
    reversed_doc = compare(tmp_path, text, '乙方完成培訓。\n\n甲方參與調研。')
    assert reversed_doc['layers']['T']['score'] == 100
    assert reversed_doc['layers']['L']['score'] < 100


def test_page_value_does_not_select_another_entry(tmp_path):
    text = '# Contents\n\nOverview: 12\n\nStrategy: 20'
    score = compare(tmp_path, text, text.replace('12', '13'))
    assert t_edits(score) == {'S': 1, 'D': 0, 'I': 0}
    assert score['layers']['B']['score'] == 50
    assert score['layers']['L']['score'] == 100


def test_period_identity_cannot_borrow_the_correct_value(tmp_path):
    text = '# 2023\n\nRevenue: 1000\n\n# 2024\n\nRevenue: 9000'
    score = compare(tmp_path, text, text.replace('1000', '8000'))
    assert score['layers']['B']['score'] == 50


def test_unrelated_numbers_do_not_change_field_correspondence(tmp_path):
    a = compare(tmp_path, 'Revenue: 1000; Profit: 7', 'Revenue: 9000; Profit: 7')
    b = compare(tmp_path, 'Revenue: 1000; Profit: 8', 'Revenue: 9000; Profit: 8')
    assert a['document_comparison']['typed_alignment']['rows'] == b['document_comparison']['typed_alignment']['rows']


def test_two_conflicting_duplicate_fields_preserve_ambiguity(tmp_path):
    score = compare(tmp_path, 'Revenue: 1000', 'Revenue: 1000\n\nRevenue: 9000')
    assert score['layers']['T']['score'] is not None
    assert score['layers']['B']['score'] is None
    assert score['layers']['B']['unresolved_requirement_ids'] == ['B:0']


def test_list_parent_error_is_local(tmp_path):
    text = '- Alpha\n  - Delta performs research.\n- Beta\n  - Echo attends training.'
    candidate = '- Alpha\n  - Echo attends training.\n- Beta\n  - Delta performs research.'
    score = compare(tmp_path, text, candidate)
    assert score['layers']['T']['score'] == 100
    assert score['layers']['L']['score'] < 100


def test_many_to_many_uses_all_contiguous_content(tmp_path):
    score = compare(tmp_path, '甲方進行\n\n完整調研及\n\n專業培訓。', '甲方進行完整\n\n調研及專業培訓。')
    assert score['layers']['T']['score'] == 100
    assert score['layers']['B']['score'] == 100


def test_native_entry_canonicalizes_paths_before_isolated_writes(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from moparse_eval import native_evaluation as entry

    monkeypatch.setattr(entry, 'ROOT', tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(entry, 'limit_resources', lambda: None)
    seen = []
    monkeypatch.setattr(entry, '_output', lambda p, **kw: seen.append(p))
    monkeypatch.setattr(entry, 'preflight', lambda p: {'preflight_status': 'ready_for_authorization'})
    target = tmp_path / 'benchmark/runs/lite/native-only/invented/check.json'
    args = SimpleNamespace(phase='preflight', freeze=tmp_path / 'freeze.json',
                           output=target.relative_to(tmp_path), authorization=None)
    assert entry.native_command(args) == 0
    assert seen == [target]


@pytest.mark.parametrize('candidate', ['"Alpha" shall pay 1000 dollars.', '“ Alpha ” shall pay 1000 dollars.'])
def test_quote_wrappers_do_not_create_false_business_conflicts(tmp_path, candidate):
    result = compare(tmp_path, '“Alpha” shall pay 1000 dollars.', candidate)
    assert result['layers']['B']['score'] > 90
    assert result['layers']['T']['score'] < 100


def test_heading_display_spaces_and_split_titles_do_not_change_owner(tmp_path):
    text = '# 甲公司2024年度公告\n\n甲方積極參與調研。'
    candidate = '# 甲公司\n\n# 2024 年度公告\n\n甲方積極參與調研。'
    result = compare(tmp_path, text, candidate)
    assert result['layers']['B']['score'] == 100
    assert result['layers']['L']['score'] == 100


def test_page_first_native_block_is_not_a_single_unmatchable_atom(tmp_path):
    expected = '# Contents\n\nOverview: 12\n\nStrategy: 20\n\nGovernance: 31'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    native = {'pages': [{'page': 1, 'branch': 'glm', 'raw': {'json_result': [[
        {'index': 0, 'label': 'title', 'content': 'Operating Review'},
        {'index': 1, 'label': 'text', 'content': '12 Overview\n20 Strategy 31 Governance'},
    ]]}}]}
    observed, _ = expose_native_heading_fields(read_saved_native(native, observation))
    candidate = read_candidate(observed)
    bind_native_syntax_scopes(candidate)
    score = grade_layers(required, candidate, scoring_method=METHOD)
    assert score['layers']['B']['score'] == 100
    titles = [r for r in score['outcomes'] if r['layer'] == 'T' and r['role'] in {'toc_title', 'page_reference'}]
    assert len(titles) == 6
    assert all(r['edits']['D'] == r['edits']['S'] == 0 for r in titles)


def test_two_quantities_are_not_a_navigation_schema(tmp_path):
    from moparse_eval.continuous_document import _navigation

    observation = read_candidate_markdown('12 employees\n\n20 people', sample_id='neutral')
    assert _navigation(observation) == []


def test_deleted_node_inside_a_fuzzy_group_has_no_membership_credit(tmp_path):
    result = compare(tmp_path, '甲方進行專業調研。\n\n乙方完成正式培訓。', '甲方進行科學調研。')
    assert result['layers']['L']['score'] < 100
    assert any(r['credit'] == 0 for r in result['outcomes'] if r['layer'] == 'B')


def test_explicit_wrong_native_table_header_binding_loses_relations(tmp_path):
    text = '| Name | Revenue | Profit |\n| --- | --- | --- |\n| Delta | 17 | 5 |'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast'))
    native = _paddle()
    region = native['pages'][0]['raw']['res']['parsing_res_list'][0]
    region['block_content'] = region['block_content'].replace('<td headers="r">17', '<td headers="p">17')
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    score = grade_layers(required, read_candidate(read_saved_native(native, observation)), scoring_method=METHOD)
    assert score['layers']['L']['score'] < 100
    assert any(p['credit'] == 0 for r in score['outcomes'] if r['layer'] == 'L' for p in r['components'])


def test_sample_names_do_not_change_matching(tmp_path):
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, 'Revenue: 1000; Profit: 50'), comparison_contract='document_ast'))
    candidate = read_candidate_markdown('Revenue: 9000; Profit: 50', sample_id=required['sample_id'])
    first = grade_layers(required, candidate, scoring_method=METHOD)
    required['sample_id'] = candidate['sample_id'] = 'unrelated-name'
    second = grade_layers(required, candidate, scoring_method=METHOD)
    assert first['layers'] == second['layers']
    assert first['outcomes'] == second['outcomes']


@pytest.mark.parametrize('before,after', [('2024', '2025'), ('>=', '<='), ('万元', '元')])
def test_protected_period_operator_and_unit_changes_are_business_losses(tmp_path, before, after):
    text = '甲公司2024年度不得发行1000万元，金额必须>=100万元。'
    result = compare(tmp_path, text, text.replace(before, after))
    assert result['layers']['B']['score'] < 100
    assert result['layers']['T']['score'] > 70


def test_one_field_value_cannot_also_supply_a_separate_prose_occurrence(tmp_path):
    text = '备注: 委員積極參與調研。\n\n委員積極參與調研。'
    result = compare(tmp_path, text, '备注: 委員積極參與調研。')
    assert result['layers']['B']['score'] <= 50
    assert result['layers']['T']['score'] < 100


def test_row_column_period_axes_compare_across_native_table_and_source_series(tmp_path):
    from moparse_eval.continuous_projection import extend_projection

    text = '营业收入：2014年100；2013年80；本年同比增减25%。'
    graph = compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast')
    original = evaluation_projection(graph)
    required = extend_projection(graph, original)
    assert {f['id'] for f in original['business']} <= {f['id'] for f in required['business']}
    native = _paddle()
    native['pages'][0]['raw']['res']['parsing_res_list'][0]['block_content'] = (
        '<table><tr><th>项目</th><th>2014年</th><th>2013年</th><th>本年同比增减(%)</th></tr>'
        '<tr><th scope="row">营业收入</th><td>100</td><td>80</td><td>25</td></tr></table>')
    observed = _observation('neutral')
    observed['sample_id'] = required['sample_id']
    candidate = read_candidate(read_saved_native(native, observed))
    score = grade_layers(required, candidate, scoring_method=METHOD)
    assert score['layers']['B']['score'] == 100
    growth = next(r for r in score['outcomes'] if r['layer'] == 'B' and r['expected'].get('attribute') == '本年同比增减')
    assert growth['expected']['value'] == '25' and growth['credit'] == 1
    native['pages'][0]['raw']['res']['parsing_res_list'][0]['block_content'] = native['pages'][0]['raw']['res']['parsing_res_list'][0]['block_content'].replace('<td>25</td>', '<td>35</td>')
    bad = grade_layers(required, read_candidate(read_saved_native(native, observed)), scoring_method=METHOD)
    assert next(r for r in bad['outcomes'] if r['id'] == growth['id'])['credit'] == 0
    assert bad['layers']['B']['score'] == pytest.approx(200 / 3)


def test_legacy_unparsed_statement_gets_one_complete_content_owner(tmp_path):
    from moparse_eval.continuous_projection import extend_projection
    from moparse_eval.document_ast_comparison import document_order_requirements

    text = '机构于2020年6月13日发行可转换债券，截至2021年6月12日发行满一年。根据募集说明书规定，现将付息有关事项公告如下：'
    graph = compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast')
    base = evaluation_projection(graph)
    before = deepcopy(base)
    old_orders = document_order_requirements(base)
    required = extend_projection(graph, base)
    assert base == before
    assert required['continuous_coverage']['bounded_responsibility_complete']
    assert required['continuous_coverage']['added_owners']
    assert all(e in document_order_requirements(required) for e in old_orders)
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    result = grade_layers(required, actual, scoring_method=METHOD)
    assert result['layers']['B']['score'] == 100


def test_checkbox_selection_cannot_pass_by_character_similarity(tmp_path):
    text = '本机构是否重述以前年度数据：√是 □否。'
    result = compare(tmp_path, text, text.replace('√是 □否', '□是 √否'))
    assert result['layers']['T']['score'] > 70
    assert result['layers']['B']['score'] == 0


def test_nine_selection_scope_rejects_missing_and_extra_members():
    from moparse_eval.native_evaluation import ALL_SCOPE, ALL_SELECTIONS, PIPELINES, _keys

    rows = [{'sample_id': s, 'pipeline': p} for s in ALL_SELECTIONS for p in PIPELINES]
    assert len(_keys(rows, ALL_SCOPE)) == 72
    for changed in (rows[:-1], rows + [rows[0]], [{**rows[0], 'sample_id': 'outside'}] + rows[1:]):
        with pytest.raises(ValueError):
            _keys(changed, ALL_SCOPE)


def test_compact_pooling_keeps_the_full_weighted_result(tmp_path):
    from moparse_eval.layer_aggregation import continuous_aggregation_record

    score = compare(tmp_path, 'Revenue: 1000; Profit: 50', 'Revenue: 9000; Profit: 50')
    assert summarize_layers([score]) == summarize_layers([continuous_aggregation_record(score)])


def test_native_completion_pools_compact_records_without_legacy_publication_key(tmp_path):
    from moparse_eval.layer_aggregation import continuous_aggregation_record
    from moparse_eval.native_evaluation import aggregate_native_scores

    score = compare(tmp_path, 'Revenue: 1000', 'Revenue: 1000\n\nRevenue: 9000')
    record = continuous_aggregation_record(score)
    assert 'publishable' not in record
    result = aggregate_native_scores({'invented': [record]}, METHOD)['invented']
    assert result == summarize_layers([score])
    assert result['layers']['T']['score'] is not None
    assert result['layers']['B']['score'] is None
    assert result['layers']['L']['score'] == 100


def test_complete_nine_selection_research_pooling_preserves_all_fractional_evidence(tmp_path):
    from moparse_eval.native_evaluation import ALL_SELECTIONS, PIPELINES
    from scripts.native_limited_research import aggregate, build_common

    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, 'Revenue: 1000; Profit: 50'), comparison_contract='document_ast'))
    score = compare(tmp_path, 'Revenue: 1000; Profit: 50', 'Revenue: 9000; Profit: 50')
    inventory = requirement_inventory(required)
    common = build_common(dict.fromkeys(ALL_SELECTIONS, required), dict.fromkeys(ALL_SELECTIONS, inventory), scoring_method=METHOD)
    scores = {(sid, p): {**deepcopy(score), 'sample_id': sid, 'pipeline': p, 'benchmark': 'native'}
              for sid in ALL_SELECTIONS for p in PIPELINES}
    result = aggregate(common, scores, dict.fromkeys(ALL_SELECTIONS, inventory))
    assert result['combinations'] == len(result['by_selection']) == 72
    assert result['excluded_denominators'] == dict.fromkeys(('T', 'L', 'B'), 0)
    for pipeline in result['rows']:
        assert pipeline['layers']['B']['score'] == 50
        assert pipeline['layers']['B']['denominator'] == 18
    assert len(result['requirement_records']) == 72 * len(score['outcomes'])


def test_code_digits_are_literal_business_identifiers(tmp_path):
    result = compare(tmp_path, 'Code: 00123', 'Code: 123')
    assert result['layers']['B']['score'] == 0


@pytest.mark.parametrize('label', ['电话', 'Phone', 'Fax', '邮编'])
def test_contact_identifiers_do_not_use_quantity_equivalence(tmp_path, label):
    exact = compare(tmp_path, f'{label}: 00123', f'{label}: 00123')
    wrong = compare(tmp_path, f'{label}: 00123', f'{label}: 123')
    assert exact['layers']['B']['score'] == 100
    assert wrong['layers']['B']['score'] == 0


@pytest.mark.parametrize('actual_email,credit', [('one@delta.example', 100), ('ne@delta.example', 0)])
def test_saved_email_grid_is_read_without_a_business_entity_class(tmp_path, actual_email, credit):
    expected = 'Email / Left: one@delta.example。'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    native = {'pages': [{'page': 1, 'branch': 'glm', 'raw': {'json_result': [[
        {'index': 0, 'label': 'table', 'content': f'| Slot | Left | Right |\n| --- | --- | --- |\n| Email | {actual_email} | other@delta.example |'},
    ]]}}]}
    actual = read_candidate(read_saved_native(native, observation))
    result = grade_layers(required, actual, scoring_method=METHOD)
    assert result['layers']['B']['score'] == credit
    field = next(r for r in result['outcomes'] if r['layer'] == 'B')['actual']
    assert field['value'] == actual_email
    assert field['semantic_entity_class_inferred'] is False


def test_native_cells_keep_table_positions_and_do_not_cross_table_boundaries(tmp_path):
    from moparse_eval.continuous_document import _nodes, _source_order_ast
    from moparse_eval.document_ast_comparison import _candidate_ast

    text = '| Field | Value |\n| --- | --- |\n| Alpha | 17 |\n\nBetween tables.\n\n| Field | Value |\n| --- | --- |\n| Beta | 19 |\n\nAfter tables.'
    actual = read_candidate_markdown(text, sample_id='invented')
    ast = _source_order_ast(_candidate_ast(actual))
    nodes = _nodes(actual, ast, clauses=True)
    assert not ast['unplaced_cell_sources']
    indices = {n['text']: i for i, n in enumerate(nodes) if n.get('text')}
    assert indices['17'] < indices['Between tables.'] < indices['19'] < indices['After tables.']
    assert any(n.get('barrier') for n in nodes[indices['17']+1:indices['19']])


def test_short_own_table_label_supports_local_scope_and_keeps_condition(tmp_path):
    expected = '# Results\n\n| Name | Revenue |\n| --- | --- |\n| Delta | 17 |'
    actual = 'Results\n\n| Name | Revenue |\n| --- | --- |\n| Delta | 17 |'
    result = compare(tmp_path, expected, actual)
    assert result['layers']['B']['score'] == 100
    assert result['layers']['L']['score'] == 100
    conditioned = compare(tmp_path, expected, actual.replace('Results\n', 'Results\n\nIf approved\n'))
    assert conditioned['layers']['B']['score'] == 0


def test_unique_table_hit_cannot_borrow_an_earlier_heading_across_a_new_label(tmp_path):
    text = '# Alpha\n\n| Name | Revenue |\n| --- | --- |\n| Delta | 17 |'
    actual = text.replace('| Name', 'Beta\n\n| Name')
    result = compare(tmp_path, text, actual)
    assert result['layers']['B']['score'] == 0
    assert result['layers']['L']['score'] < 100


@pytest.mark.parametrize('cny,usd,credit', [('1', '9', 1), ('9', '1', 0)])
def test_currency_column_is_located_before_comparing_amount(tmp_path, cny, usd, credit):
    text = 'Revenue / 2024年（人民币百万元）: 1'
    actual = f'| Slot | 2024年（人民币百万元） | 2024年（美元百万元） |\n| --- | --- | --- |\n| Revenue | {cny} | {usd} |'
    result = compare(tmp_path, text, actual)
    fields = [r for r in result['outcomes'] if r['layer'] == 'B']
    assert len(fields) == 1
    assert fields[0]['credit'] == credit
    assert fields[0]['actual']['value'] == cny


@pytest.mark.parametrize('actual_value,credit', [('10000', 1), ('9999', 0)])
def test_explicit_row_unit_is_not_part_of_the_metric_name(tmp_path, actual_value, credit):
    text = 'Revenue / 2024（万元）: 1'
    actual = f'| Slot | 2024 |\n| --- | --- |\n| Revenue（元） | {actual_value} |'
    result = compare(tmp_path, text, actual)
    fields = [r for r in result['outcomes'] if r['layer'] == 'B']
    assert len(fields) == 1
    assert fields[0]['credit'] == credit


def test_whitespace_inside_a_numeric_period_is_not_display_equivalence(tmp_path):
    result = compare(tmp_path, '# 2024年\n\nRevenue: 1000', '# 2 024年\n\nRevenue: 1000')
    assert result['layers']['B']['score'] == 0
    assert result['layers']['L']['score'] < 100
    assert t_edits(result)['I'] > 0


def test_original_page_routes_compare_the_same_saved_locator():
    from moparse_eval.native_scope import same_page_routes

    plan = [{'input_page': 1, 'branch': 'docling', 'raw_locator': '#/pages/0/raw'}]
    original = [{'input_page': 1, 'branch': 'docling', 'entry': '#/pages/0', 'original_page': 77}]
    assert same_page_routes(plan, original)
    assert not same_page_routes(plan, [{**original[0], 'branch': 'glm'}])
    assert not same_page_routes(plan, [{**original[0], 'entry': '#/pages/1'}])


def test_unknown_matrix_record_class_does_not_block_literal_scoring(tmp_path):
    text = '| Left | Middle | Right |\n| --- | --- | --- |\n| Delta | 17 | 5 |\n| Epsilon | 19 | 6 |'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast'))
    native = _docling()
    for cell, name in zip(native['documents'][0]['document']['tables'][0]['data']['table_cells'][:3], ['Left', 'Middle', 'Right'], strict=True):
        cell['text'] = name
    data = native['documents'][0]['document']['tables'][0]['data']
    data['num_rows'] = 3
    data['table_cells'].extend({**cell, 'text': text, 'start_row_offset_idx': 2, 'end_row_offset_idx': 3}
                              for cell, text in zip(deepcopy(data['table_cells'][3:6]), ['Epsilon', '19', '6'], strict=True))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    candidate = read_candidate(read_saved_native(native, observation))
    assert candidate['text_projection']['complete'] is False
    result = grade_layers(required, candidate, scoring_method=METHOD)
    assert result['layers']['T']['score'] == 100
    assert result['candidate_literal_projection_audit']['legacy_projection_complete'] is False


def test_unknown_native_heading_depth_keeps_ordered_context(tmp_path):
    expected = '# Report\n\n## Finance\n\n### Metrics\n\nRevenue: 1000'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    native = {'pages': [{'page': 1, 'branch': 'visual', 'raw': [
        {'type': 'title', 'content': t, 'bbox': [0, i / 5, 1, (i + 1) / 5], 'angle': 0}
        for i, t in enumerate(['Report', 'Finance', 'Metrics'])] + [
        {'type': 'text', 'content': 'Revenue: 1000', 'bbox': [0, .6, 1, 1], 'angle': 0}]}]}
    observed, _ = expose_native_heading_fields(read_saved_native(native, observation))
    candidate = read_candidate(observed)
    bind_native_syntax_scopes(candidate)
    result = grade_layers(required, candidate, scoring_method=METHOD)
    assert result['layers']['B']['score'] == 100


def test_lexical_grid_reader_keeps_prose_and_mixed_rows_separate():
    from moparse_eval.native_grid_fields import syntax_grid_fields

    native = _paddle()
    table = native['pages'][0]['raw']['res']['parsing_res_list'][0]
    table['block_content'] = '<table><tr><th>Item</th><th>Value</th></tr><tr><td>Our mission</td><td>Support all customers.</td></tr></table>'
    candidate = read_candidate(read_saved_native(native, _observation('neutral')))
    candidate['business'] = []  # Independently examine the lexical syntax reader.
    assert syntax_grid_fields(candidate) == []
    table['block_content'] = table['block_content'].replace('</table>', '<tr><td>Revenue</td><td>17</td></tr></table>')
    candidate = read_candidate(read_saved_native(native, _observation('neutral')))
    candidate['business'] = []
    fields = syntax_grid_fields(candidate)
    assert [(f['subject'], f['attribute'], f['value']) for f in fields] == [('Revenue', 'Value', '17')]


@pytest.mark.parametrize("reader", ["markdown", "observation"])
def test_field_qualifiers_are_owned_by_their_printed_occurrence(reader):
    from moparse_eval.continuous_document import _field_axes
    from moparse_eval.expected_readback import markdown_observation

    markdown = ("## 表甲\n\n- 流动 / 借款\n  - 范围：境内\n  - 附注：4\n"
                "  - 2025年：7\n    - 单位：（人民币万元）\n"
                "  - 2023年：7\n    - 单位：USD millions\n\n"
                "## 表乙\n\n- 非流动 / 借款\n  - 2025年：7")
    actual = (read_candidate_markdown(markdown) if reader == "markdown" else
              read_candidate(markdown_observation(markdown, sample_id="two-tables", pipeline="test", pages=[1])))
    fields = [f for f in actual["business"] if f["value"] == "7" and f["role"] == "metric"]
    assert len(fields) == 3
    first, second, third = fields
    assert first["qualifiers"] == {"period": "2025年", "unit": "人民币万元", "currency": "人民币",
                                    "note": "4", "scope": "境内"}
    assert second["qualifiers"] == {"period": "2023年", "unit": "USD millions", "currency": "USD",
                                     "note": "4", "scope": "境内"}
    assert third["qualifiers"] == {"period": "2025年"}
    assert third["scope"] == ["表乙"] and second["scope"] == first["scope"] == ["表甲"]
    assert _field_axes(first) != _field_axes(second) != _field_axes(third)
    for field in (first, second):
        proof = field["qualifier_provenance"]["unit"]["source"]
        assert proof["text_span"]
        assert any(edge["type"] == "qualifier_scope" and edge.get("fact_id") == field["id"]
                   and edge["left"] == {"type": "unit", "text": field["qualifiers"]["unit"]}
                   and edge["source"] == proof for edge in actual["relations"])
    inline = {**first, "attribute": "流动 / 借款（附注4）",
              "qualifiers": {k: v for k, v in first["qualifiers"].items() if k != "note"}}
    assert _field_axes(inline) == _field_axes(first)
    for changed in ({"period": "2022年"}, {"note": "3"}, {"currency": "USD", "unit": "USD millions"}):
        assert _field_axes({**first, "qualifiers": {**first["qualifiers"], **changed}}) != _field_axes(inline)
