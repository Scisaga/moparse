"""Native-only semantic entry and scope regressions from invented tables."""

from copy import deepcopy

import pytest

from app.models.table_semantics import TextRef
from app.services.table_context_service import native_scopes
from app.services.table_semantics_service import bind_table_view, render_semantic_view
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows


def table(rows, name="native"):
    md = render_gfm_rows(rows)
    f = TableFragment(name, 1, 1, (0, 0, 1, 1), len(rows), len(rows[0]), deepcopy(rows), [], md, md,
                      source_kind="mineru", cells=[TableCellFragment(r, c, 1, 1, text)
                                                  for r, row in enumerate(rows) for c, text in enumerate(row)])
    f.native_evidence = native_scopes(f)
    f.source_header_scopes = f.native_evidence["header_scopes"]
    return f


def test_native_measurement_structure_does_not_require_a_pdf_vector_grid():
    f = table([["(人民币百万元)", "2024", "同比"], ["Alpha", "17", "5%"]])
    before = deepcopy(f)
    view = bind_table_view("view", [f], [f])
    assert f == before and view.status == "converted"
    text = render_semantic_view(view, [f])
    assert "2024：17（单位：(人民币百万元)）" in text
    assert "同比：5%（单位" not in text


def test_a_known_source_conflict_cannot_be_bypassed_by_native_structure():
    f = table([["Item", "2024"], ["Alpha", "17"]])
    f.pdf_evidence = {"bound": False, "reason": "source_cell_text_or_spans_disagree"}
    assert bind_table_view("view", [f], [f]).status == "retained"


def test_numeric_words_inside_grid_prose_do_not_establish_a_measurement_schema():
    f = table([["Independent discussion", "Another section"],
               ["Our team discussed 17 options.", "We did not approve the proposed change."]])
    assert f.native_evidence["content_kind"] == "unknown"
    assert bind_table_view("view", [f], [f]).status == "retained"


def test_mixed_grid_retains_unresolved_prose_beside_supported_numeric_records():
    f = table([["Item", "2024", "2023"], ["Alpha", "17", "11"],
               ["Independent prose paragraph", "", ""]])
    view = bind_table_view("view", [f], [f])
    assert view.status == "partial" and len(view.records) == 1
    rendered = render_semantic_view(view, [f])
    assert "Alpha；2024：17；2023：11" in rendered
    assert "Independent prose paragraph" in rendered


def test_external_native_period_and_title_are_visible_in_each_record():
    f = table([["Item", "Amount"], ["Alpha", "17"], ["Beta", "11"]])
    f.context_refs = (TextRef("native", 1, "p1", "2024年度排放情况：", "period", 0, 12, (1, 2), (0, 1)),
                      TextRef("native", 1, "p0", "Domestic operations", "title", 0, 19, (1, 2), (0, 1)))
    view = bind_table_view("view", [f], [f])
    rendered = render_semantic_view(view, [f])
    assert rendered.count("范围：Domestic operations") == 2
    assert rendered.count("期间：2024年度排放情况：") == 2


@pytest.mark.parametrize("label,visible", [
    (r"Corporate \( Cash^1 \)", "Corporate Cash（附注标记：1）"),
    (r"\( Reserve\ Funds^{1} \)", "Reserve Funds（附注标记：1）"),
])
def test_linked_textual_math_note_label_is_readable_and_keeps_its_marker(label, visible):
    f = table([["Item", "2034"], [label, "17"]])
    text = "1 Includes collateral held by the fund."
    f.context_refs = (TextRef("native", 1, "n1", text, "note", 0, len(text), (1,), (0, 1)),)
    before = deepcopy(f)
    view = bind_table_view("view", [f], [f])
    assert view.status == "converted"
    rendered = render_semantic_view(view, [f])
    assert visible in rendered and "2034：17" in rendered
    assert "附注：" + text in rendered
    assert f == before


@pytest.mark.parametrize("label,note", [
    (r"Corporate \( Cash^1 \)", "2 A different note."),
    (r"Corporate Cash^1", "1 A bare caret has no declared type."),
    (r"\( x^2 + y \)", "2 An equation is not a textual label."),
    (r"\( x^2 \)", "2 A matching note cannot change a mathematical variable."),
    (r"\( cm^{2} \)", "2 A matching note cannot change a squared unit."),
    (r"\( Revenue^2 \)", "2 A standalone mathematical word retains its exponent."),
    (r"\( Cash^{12} \)", "1 A different note number."),
])
def test_note_rendering_does_not_strip_unbound_markers_or_mathematics(label, note):
    from app.services.table_semantics_service import _literal

    f = table([["Item", "2034"], [label, "17"]])
    f.context_refs = (TextRef("native", 1, "n1", note, "note", 0, len(note), (1,), (0, 1)),)
    view = bind_table_view("view", [f], [f])
    assert _literal(label) in render_semantic_view(view, [f])
    assert "附注标记" not in render_semantic_view(view, [f])


def test_native_empty_section_rows_keep_bounded_group_names():
    f = table([["Item", "2024"], ["North", ""], ["Other", "17"], ["South", ""], ["Other", "11"]])
    view = bind_table_view("view", [f], [f])
    rendered = render_semantic_view(view, [f])
    assert "North / Other；2024：17" in rendered
    assert "South / Other；2024：11" in rendered


def test_date_meeting_decisions_have_explicit_field_schema_without_numeric_grid():
    f = table([["召开日期", "会议内容", "重要意见和建议"],
               ["2024年04月01日", "年度第一次会议", "审议通过方案，并同意提交董事会审议。"]])
    view = bind_table_view("view", [f], [f])
    assert view.status == "converted"
    assert "会议内容：年度第一次会议" in render_semantic_view(view, [f])
    assert view.records[0].subject.column == 1
    assert "召开日期：2024年04月01日" in render_semantic_view(view, [f])


def test_shared_native_value_span_keeps_the_literal_and_its_scope():
    f = table([["Item", "2024", "Standard"], ["Alpha", "17", "Scope A"], ["Beta", "11", ""]])
    value = next(c for c in f.cells if (c.row, c.column) == (1, 2))
    value.row_span = 2
    f.cells = [c for c in f.cells if (c.row, c.column) != (2, 2)]
    f.native_evidence = native_scopes(f)
    f.source_header_scopes = f.native_evidence["header_scopes"]
    view = bind_table_view("view", [f], [f])
    assert len(view.records) == 2
    assert all(r.values[1].value.row == 1 for r in view.records)
    assert render_semantic_view(view, [f]).count("Standard：Scope A") == 2


def test_internal_period_header_opens_a_new_scope_without_lending_previous_columns():
    f = table([["Item", "2024"], ["Alpha", "17"], ["Item", "2023"], ["Beta", "11"]])
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert "Alpha；2024：17" in text and "Beta；2023：11" in text
    assert "Beta；2024" not in text


def test_mixed_prose_row_is_retained_while_a_supported_neighbour_is_converted():
    f = table([["Item", "2024"], ["Alpha", "17"], ["Legal conditions", "No approval was given."]])
    view = bind_table_view("view", [f], [f])
    assert view.status == "partial" and len(view.records) == 1
    assert "No approval was given." in render_semantic_view(view, [f])


def test_currency_display_spacing_cannot_turn_a_data_record_into_a_header():
    f = table([["Item", "2024", "2023"], ["Revenue", "$ 17", "$ 11"], ["Margin", "50.0%", "40.0%"]])
    assert f.source_header_scopes[0]["header_rows"] == [0]
    view = bind_table_view("view", [f], [f])
    assert len(view.records) == 2 and view.records[0].subject.row == 1


def test_group_closes_at_its_explicit_total_instead_of_swallowing_later_records():
    f = table([["Item", "2024"], ["Operating expenses", ""], ["Research", "17"],
               ["Total operating expenses", "17"], ["Net income", "11"]])
    view = bind_table_view("view", [f], [f])
    assert view.records[-1].row_groups == ()
    assert "Operating expenses / Net income" not in render_semantic_view(view, [f])


def test_unmarked_business_note_is_not_assigned_to_unrelated_records_or_periods():
    f = table([["Item", "2024", "2023"], ["Alpha", "17", "11"]])
    note = "Note: in 2024, a separate operation included internal sales."
    f.context_refs = (TextRef("native", 1, "note", note, "note", 0, len(note), (1,), (1, 2)),)
    view = bind_table_view("view", [f], [f])
    assert all(not value.note_refs for value in view.records[0].values)


def test_ordinal_column_is_a_field_while_explicit_project_name_identifies_the_record():
    f = table([["序号", "项目", "金额(万元)"], ["1", "Alpha", "17"], ["2", "Beta", "11"]])
    view = bind_table_view("view", [f], [f])
    assert all(r.subject.column == 1 and not r.row_groups for r in view.records)
    rendered = render_semantic_view(view, [f])
    assert "项目：Alpha；序号：1" in rendered and "金额(万元)：17" in rendered


def test_numbered_sibling_does_not_become_a_child_of_the_previous_empty_band():
    f = table([["Item", "2024"], ["二、Category", ""], ["Child", "17"], ["三、Total", "11"]])
    view = bind_table_view("view", [f], [f])
    assert not view.records[-1].row_groups
    assert "Category / 三、Total" not in render_semantic_view(view, [f])


def test_first_key_value_record_does_not_become_an_invented_column_header():
    f = table([["Cumulative dividend amount", "17000"], ["Annual net income", "11000"]])
    assert f.native_evidence["content_kind"] == "unknown"
    view = bind_table_view("view", [f], [f])
    assert view.status == "retained" and not view.records
    assert view.source_tables == (f.fragment_id,)
    assert f.rows == [["Cumulative dividend amount", "17000"], ["Annual net income", "11000"]]


def test_full_width_section_label_is_printed_in_each_supported_child_record():
    f = table([["Item", "2024"], ["Revenue", "17"], ["Expenses", ""], ["Staff", "11"], ["", "11"], ["Profit", "6"]])
    group = next(c for c in f.cells if (c.row, c.column) == (2, 0))
    group.column_span = 2
    f.cells = [c for c in f.cells if (c.row, c.column) != (2, 1)]
    f.native_evidence = native_scopes(f)
    f.source_header_scopes = f.native_evidence["header_scopes"]
    view = bind_table_view("view", [f], [f])
    rendered = render_semantic_view(view, [f])
    assert "Expenses / Staff" in rendered and "Expenses / Profit" not in rendered
    assert next(r for r in view.records if r.source_row == 3).row_groups


def test_full_width_group_after_headers_does_not_erase_the_header_band():
    f = table([["Item", "2024"], ["Expenses", ""], ["Staff", "11"]])
    next(c for c in f.cells if (c.row, c.column) == (1, 0)).column_span = 2
    f.cells = [c for c in f.cells if (c.row, c.column) != (1, 1)]
    f.native_evidence = native_scopes(f)
    f.source_header_scopes = f.native_evidence["header_scopes"]
    view = bind_table_view("view", [f], [f])
    assert "Expenses / Staff；2024：11" in render_semantic_view(view, [f])


def test_arithmetic_instruction_is_not_a_business_parent_for_adjustment_totals():
    f = table([["Item", "2024"], ["Profit", "17"], ["Add:", ""], ["Depreciation", "11"], ["Adjusted profit", "28"]])
    view = bind_table_view("view", [f], [f])
    rendered = render_semantic_view(view, [f])
    assert all(not r.row_groups for r in view.records)
    assert "Add: /" not in rendered and "Adjusted profit" in rendered and "Add:" in rendered
    assert [r.source_row for r in view.records] == [1] and view.status == "partial"


def test_undelimited_arithmetic_region_does_not_block_a_later_explicit_period_scope():
    f = table([["Item", "2024"], ["Profit", "17"], ["Add:", ""], ["Adjustment", "11"],
               ["Total", "28"], ["Item", "2023"], ["Other profit", "9"]])
    view = bind_table_view("view", [f], [f])
    assert [r.source_row for r in view.records] == [1, 6]
    assert "Other profit；2023：9" in render_semantic_view(view, [f])


def test_currency_bands_keep_same_year_columns_distinct_without_currency_units_on_ratios():
    f = table([["Item", "2024", ""], ["", "(美元百万元)", "(人民币百万元)"],
               ["Revenue", "17", "11"], ["Margin", "9%", "8%"]])
    next(c for c in f.cells if (c.row, c.column) == (0, 0)).row_span = 2
    next(c for c in f.cells if (c.row, c.column) == (0, 1)).column_span = 2
    f.cells = [c for c in f.cells if (c.row, c.column) not in {(0, 2), (1, 0)}]
    f.native_evidence = native_scopes(f)
    f.source_header_scopes = f.native_evidence["header_scopes"]
    view = bind_table_view("view", [f], [f])
    margin = next(r for r in view.records if r.subject.row == 3)
    assert all(not value.unit_refs for value in margin.values)
    rendered = render_semantic_view(view, [f])
    assert "2024 / (美元百万元)：9%" in rendered and "2024 / (人民币百万元)：8%" in rendered


def test_currency_words_inside_business_labels_are_not_dropped_as_unit_legends():
    from app.services.table_context_service import unit_description
    assert unit_description("(美元百万元)")
    assert unit_description("($ in millions, except per share data)")
    assert not unit_description("(美元业务)")
    assert not unit_description("(USD business line)")


def test_embedded_amount_column_unit_yields_to_printed_row_units_and_percentages():
    f = table([["Item", "2024$m", "2023$m"], ["Revenue", "1700", "1100"],
               ["Average pool ($bn)", "17.0", "11.0"], ["Net return", "2.30%", "2.69%"],
               ["Earnings per share", "$1.70", "$1.10"]])
    before = deepcopy(f)
    view = bind_table_view("view", [f], [f])
    rendered = render_semantic_view(view, [f])
    assert "Revenue；2024$m：1700；2023$m：1100" in rendered
    assert "Average pool ($bn)；2024：17.0；2023：11.0" in rendered
    assert "Net return；2024：2.30%；2023：2.69%" in rendered
    assert "Earnings per share；2024：$1.70；2023：$1.10" in rendered
    assert f == before


def test_currency_values_and_currency_business_names_do_not_override_column_scale():
    f = table([["Item", "2024$m"], ["Foreign currency business", "$17"],
               ["Fund (USD business line)", "11"], ["Index code", "12"]])
    rendered = render_semantic_view(bind_table_view("view", [f], [f]), [f])
    assert "business；2024$m：$17" in rendered
    assert "(USD business line)；2024$m：11" in rendered
    assert "Index code；2024$m：12" in rendered
    f = table([["Item", "Rate", "Code$m"], ["Alpha", "17", "5%"]])
    assert "Code$m：5%" in render_semantic_view(bind_table_view("view", [f], [f]), [f])


def test_retained_unnamed_row_keeps_its_explicit_section_without_claiming_a_total():
    from app.services.table_semantics_service import retained_table_parts

    f = table([["Item", "2024"], ["Expenses", ""], ["Research", "17"],
               ["", "17"], ["Net income", "11"]])
    view = bind_table_view("view", [f], [f])
    part = next(p for p in retained_table_parts(view, [f]) if 3 in p["source_rows"])
    assert part["context_rows"] == [1]
    assert "Expenses" in part["rendered"] and "17" in part["rendered"]
    assert "Research" not in part["rendered"] and "Total" not in part["rendered"]
    assert view.records[-1].row_groups == ()


def test_retained_unnamed_row_cannot_borrow_a_section_after_its_explicit_close():
    from app.services.table_semantics_service import retained_table_parts

    f = table([["Item", "2024"], ["Expenses", ""], ["Research", "17"],
               ["Total expenses", "17"], ["", "11"]])
    view = bind_table_view("view", [f], [f])
    part = next(p for p in retained_table_parts(view, [f]) if 4 in p["source_rows"])
    assert part["context_rows"] == [] and "Expenses" not in part["rendered"]


@pytest.mark.parametrize('caption_in_table', [False, True])
def test_table_amount_caption_is_not_a_business_title_overriding_row_units(caption_in_table):
    from app.models.parse_result import DocumentParseResult, ParsePipeline
    from app.services.table_context_service import prepare_native_table_scopes

    f = table([["Item", "2024", "Change(%)"], ["Revenue", "1700", "17"],
               ["Return(%)", "2.30", "11"], ["Earnings(元/股)", "1.70", "9"],
               ["Dividend per share", "$1.70", "8"]])
    cap = {'type': 'table_caption', 'content': '单位：人民币百万元'}
    result = DocumentParseResult(document_id='synthetic', filename='synthetic.pdf', mime_type='application/pdf',
                                 page_count=1, processed_pages=1, pipeline=ParsePipeline(profile='accurate', primary='mineru'))
    result._table_fragments = [f]
    result._native_page_blocks = {1: ([{'type': 'table', 'content': [cap]}] if caption_in_table else
                                     [cap, {'type': 'table', 'content': []}])}
    prepare_native_table_scopes(result)
    unit = next(ref for ref in f.context_refs if ref.kind == 'unit')
    assert cap['content'][unit.start:unit.end] == unit.text == '人民币百万元'
    view = bind_table_view('view', [f], [f])
    rendered = render_semantic_view(view, [f])
    assert '范围：单位' not in rendered
    assert '2024：1700（单位：人民币百万元）' in rendered
    assert 'Return(%)；2024：2.30；Change(%)：11' in rendered
    assert 'Earnings(元/股)；2024：1.70；Change(%)：9' in rendered
    assert 'Dividend per share；2024：$1.70；Change(%)：8' in rendered
    assert all(not record.scope_refs for record in view.records)


def test_business_caption_is_not_reclassified_by_the_word_currency_or_unit():
    from app.services.table_context_service import _unit_caption

    assert _unit_caption('单位：承运企业') is None
    assert _unit_caption('Revenue ($m)') is None
    assert _unit_caption('(USD business line)') is None


def test_nested_native_list_period_is_printed_with_its_exact_literal_slice_and_closes():
    from app.models.parse_result import DocumentParseResult, ParsePipeline
    from app.services.table_context_service import prepare_native_table_scopes

    first = table([["Item", "Amount"], ["Alpha", "17"]], "first")
    second = table([["Item", "Amount"], ["Beta", "11"]], "second")
    intro = {"type": "list", "content": [
        {"type": "text", "content": [{"type": "text", "content": "（1）Other context。"}]},
        {"type": "text", "content": [{"type": "text", "content": "（3）2024 年度测量数据:"}]},
    ]}
    result = DocumentParseResult(document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
                                 page_count=1, processed_pages=1, pipeline=ParsePipeline(profile="balanced", primary="synthetic"))
    result._table_fragments = [first, second]
    result._native_page_blocks = {1: [intro, {"type": "title", "content": "① Measurements"}, {"type": "table"},
                                        {"type": "title", "content": "（4）Other operations"}, {"type": "table"}]}
    prepare_native_table_scopes(result)
    period = next(ref for ref in first.context_refs if ref.kind == "period")
    projection = "（1）Other context。\n（3）2024 年度测量数据:"
    assert projection[period.start:period.end] == period.text == "（3）2024 年度测量数据:"
    assert "期间：（3）2024 年度测量数据:" in render_semantic_view(bind_table_view("a", [first], [first]), [first])
    assert not any(ref.kind == "period" for ref in second.context_refs)


def test_textual_performance_records_are_not_absorbed_into_a_numeric_rows_header():
    f = table([['', 'Cash plan', 'Stock plan'],
               ['Performance achievement', '$125.5 billion revenue', '80th percentile return'],
               ['Payout as % of target', '150%', '120%']])
    assert f.native_evidence['content_kind'] == 'unknown'
    assert bind_table_view('view', [f], [f]).status == 'retained'


def test_a_leading_text_record_is_preserved_beside_a_later_numeric_record():
    f = table([['Item', '2024'], ['Legal conditions', 'No approval was given.'], ['Revenue', '17']])
    assert f.source_header_scopes[0]['header_rows'] == [0]
    view = bind_table_view('view', [f], [f])
    assert view.status == 'partial'
    rendered = render_semantic_view(view, [f])
    assert 'Legal conditions' in rendered and 'No approval was given.' in rendered and 'Revenue；2024：17' in rendered
