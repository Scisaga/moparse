"""Native-only semantic entry and scope regressions from invented tables."""

from copy import deepcopy

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
