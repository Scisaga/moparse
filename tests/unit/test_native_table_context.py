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


def test_an_explicit_midtable_period_band_replaces_the_earlier_year_headers():
    f = table([["Item", "2034年", "2033年", "同比(%)"], ["Revenue", "17", "11", "5"],
               ["", "2034年末", "2033年末", "本年末比上年末增减(%)"], ["Assets", "19", "13", "6"]])
    before = deepcopy(f)
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert view.status == "converted" and f == before
    assert "Revenue；2034年：17；2033年：11；同比(%)：5" in text
    assert "Assets；2034年末：19；2033年末：13；本年末比上年末增减(%)：6" in text
    assert "Assets；2034年：" not in text


@pytest.mark.parametrize("replacement", [["", "2034", "2033", "5"],
                                           ["", "2034年末", "No approval was given.", "6"],
                                           ["", "2034年末", "2033年末", ""]])
def test_unnamed_values_and_incomplete_rows_do_not_create_a_new_period_band(replacement):
    f = table([["Item", "2034年", "2033年", "同比(%)"], ["Revenue", "17", "11", "5"],
               replacement, ["Assets", "19", "13", "6"]])
    assert len(f.native_evidence["header_scopes"]) == 1


@pytest.mark.parametrize("quarters", [["第一季度", "第二季度", "第三季度", "第四季度"],
                                      ["第一季度(1-3月份)", "第二季度(4-6月份)", "第三季度(7-9月份)", "第四季度(10-12月份)"],
                                      ["Q1", "Q2", "Q3", "Q4"]])
def test_native_quarter_periods_preserve_all_literal_measurement_columns(quarters):
    f = table([["", *quarters], ["Revenue", "17", "11", "13", "19"], ["Profit", "7", "5", "9", "11"]])
    before = deepcopy(f)
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert f == before and view.status == "converted" and len(view.records) == 2
    assert "Revenue；" + "；".join(q + "：" + v for q, v in zip(quarters, ["17", "11", "13", "19"], strict=True)) in text
    assert "2034" not in text


def test_quarter_words_in_layout_prose_do_not_manufacture_measurement_records():
    f = table([["Q1 outlook", "Q2 concerns"], ["No approval was given.", "We considered several proposals."]])
    assert bind_table_view("view", [f], [f]).status == "retained"


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


def test_unnamed_values_repeat_their_printed_section_without_claiming_a_total():
    f = table([["Item", "2024"], ["Expenses", ""], ["Research", "17"],
               ["", "17"], ["Net income", "11"]])
    before = deepcopy(f)
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert "- Expenses；2024：17。" in text and "Total" not in text
    assert view.status == "converted" and f == before
    assert view.records[1].source_row == 3 and view.records[1].subject.row == 1
    assert view.records[-1].row_groups == ()


def test_full_width_context_supplies_a_label_but_not_an_invented_total_role():
    f = table([["Item", "2024", "Change"], ["Expenses", "", ""], ["Research", "17", "5%"],
               ["", "17", "5%"], ["Net income", "11", "7%"]])
    group = next(c for c in f.cells if (c.row, c.column) == (1, 0))
    group.column_span = 3
    f.cells = [c for c in f.cells if c.row != 1 or c.column == 0]
    f.native_evidence = native_scopes(f)
    f.source_header_scopes = f.native_evidence["header_scopes"]
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert "- Expenses；2024：17；Change：5%。" in text
    assert "Expenses / Net income" not in text and "Total" not in text
    assert view.status == "converted"


def test_an_unnamed_row_without_a_printed_section_keeps_its_original_values():
    f = table([["Item", "2024"], ["First payment", "$1.70"], ["Second payment", "$1.10"], ["", "$2.80"]])
    view = bind_table_view("view", [f], [f])
    assert view.status == "partial" and [r.source_row for r in view.records] == [1, 2]
    assert "$2.80" in render_semantic_view(view, [f])
    assert not f.native_evidence["retained_row_context"]


@pytest.mark.parametrize("bullet", ["-", "–", "—", "•"])
@pytest.mark.parametrize("label", ["Income from:", "Non-audit services"])
def test_literal_bulleted_child_list_ends_before_the_next_unmarked_record(bullet, label):
    f = table([["Item", "2024"], [label, ""], [bullet + " Deposits", "17"],
               [bullet + " Securities", "11"], ["Total income", "28"], ["Average balance", "7"]])
    view = bind_table_view("view", [f], [f])
    assert all(r.row_groups for r in view.records[:2])
    assert all(not r.row_groups for r in view.records[2:])
    assert "Income from: / Average balance" not in render_semantic_view(view, [f])


@pytest.mark.parametrize("group,child", [("Financial assets", "Cash"), ("Financial assets:", "Cash")])
def test_an_unmarked_section_does_not_acquire_an_invented_bullet_boundary(group, child):
    f = table([["Item", "2024"], [group, ""], [child, "17"], ["Investments", "11"]])
    view = bind_table_view("view", [f], [f])
    assert all(r.row_groups for r in view.records)


def test_a_later_bullet_does_not_reinterpret_an_unmarked_parent_section():
    f = table([["Item", "2024"], ["Financial assets", ""], ["Cash", "17"],
               ["- Restricted cash", "11"], ["Investments", "7"]])
    view = bind_table_view("view", [f], [f])
    assert all(r.row_groups for r in view.records)


def test_numbered_measurement_sections_need_both_literal_boundaries_and_including_cue():
    f = table([["Item", "2034"], ["一、North", "17"], ["其中:Fees", "11"], ["Other", "6"],
               ["二、South", "19"], ["其中:Fees", "13"], ["Other", "6"],
               ["三、Equity", "7"], ["Per share", "1.7"], ["四、Loans", "9"], ["其中:Retail", "4"]])
    before = deepcopy(f)
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert "一、North / Other；2034：6" in text and "二、South / Other；2034：6" in text
    assert "三、Equity / Per share" not in text
    assert "四、Loans /" not in text
    assert view.status == "converted" and f == before
    assert len(view.records) == 10 and all(not r.row_groups for r in view.records if r.source_row in {1, 4, 7, 9})


@pytest.mark.parametrize("barrier", ["missing_including", "no_end", "changed_numbering", "unqualified_total", "note", "prose"])
def test_numbered_values_do_not_manufacture_an_unbounded_or_conflicting_parent(barrier):
    rows = [["Item", "2034"], ["一、North", "17"], ["其中:Fees", "11"], ["Other", "6"], ["二、South", "19"]]
    if barrier == "missing_including":
        rows[2][0] = "Fees"
    elif barrier == "no_end":
        rows.pop()
    elif barrier == "changed_numbering":
        rows[-1][0] = "二.South"
    elif barrier == "unqualified_total":
        rows[3][0] = "Total"
    elif barrier == "note":
        rows[3][0] = "Note: a separate matter"
    elif barrier == "prose":
        rows[3][1] = "No approval was given."
    f = table(rows)
    view = bind_table_view("view", [f], [f])
    assert all(not r.row_groups for r in view.records)


@pytest.mark.parametrize("label", ["附注", "附註", "Notes", "Note references", "序号", "Index", "Code"])
def test_table_currency_does_not_turn_a_note_reference_or_identifier_into_an_amount(label):
    f = table([["(人民币百万元)", label, "2024", "2023"], ["Revenue", "8", "1700", "1100"]])
    view = bind_table_view("view", [f], [f])
    record = view.records[0]
    assert not record.values[0].unit_refs
    assert record.values[1].unit_refs and record.values[2].unit_refs
    text = render_semantic_view(view, [f])
    assert label + "：8；2024：1700（单位：(人民币百万元)）" in text


def test_a_column_with_a_measurement_name_still_owns_its_unit():
    f = table([["(人民币百万元)", "Notes payable", "2024"], ["Alpha", "17", "11"]])
    record = bind_table_view("view", [f], [f]).records[0]
    assert record.values[0].unit_refs and record.values[1].unit_refs


@pytest.mark.parametrize("caption", ["（货币单位:人民币百万元）", " (貨幣單位：人民幣百萬元) ", "单位：人民币百万元"])
def test_wrapped_currency_declaration_keeps_its_literal_native_slice(caption):
    from app.services.table_context_service import _unit_caption

    unit, start = _unit_caption(caption)
    assert caption[start:start + len(unit)] == unit
    assert unit in {"人民币百万元", "人民幣百萬元"}
    assert _unit_caption("（货币单位：承运企业）") is None


def continuation_result():
    from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline

    left = table([["Item", "2034", "2033", "Change"], ["Before", "17", "11", "5%"]], "left")
    right = table([["After", "19", "13", "6%"]], "right")
    right.page_number = 2
    right.source_continues_prev = True
    result = DocumentParseResult(document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
                                 page_count=2, processed_pages=2,
                                 pipeline=ParsePipeline(profile="accurate", primary="mineru"),
                                 pages=[PageParseResult(page_number=1, content=left.rendered),
                                        PageParseResult(page_number=2, content=right.rendered)])
    result._table_fragments = [left, right]
    result._native_page_blocks = {1: [{"type": "table", "content": [
        {"type": "table_caption", "content": "（货币单位:人民币百万元）"}]}],
                                 2: [{"type": "table", "content": []}]}
    return result, left, right


def test_declared_native_continuation_keeps_complete_headers_units_and_physical_cells():
    from app.services.table_context_service import prepare_native_table_scopes

    result, left, right = continuation_result()
    before = deepcopy((left.rows, left.cells, right.rows, right.cells))
    prepare_native_table_scopes(result)
    view = bind_table_view("view", [right], [left, right])
    assert view.status == "converted"
    text = render_semantic_view(view, [left, right])
    assert "After；2034：19（单位：人民币百万元）；2033：13（单位：人民币百万元）；Change：6%。" in text
    assert right.source_header_scopes == [] and not right.pdf_evidence
    assert (left.rows, left.cells, right.rows, right.cells) == before
    assert view.records[0].values[0].column_headers[0].table_id == "left"
    unit = view.records[0].values[0].unit_refs[0]
    assert unit.page == 1 and unit.text == "人民币百万元"


@pytest.mark.parametrize("barrier", ["missing_declaration", "false_declaration", "own_headers", "new_caption",
                                   "new_unit", "intervening_heading", "left_tail", "source_conflict", "column_span",
                                   "missing_field_path", "arithmetic_boundary"])
def test_native_continuation_never_borrows_incompatible_or_unresolved_context(barrier):
    from app.services.table_context_service import prepare_native_table_scopes

    result, left, right = continuation_result()
    if barrier == "missing_declaration":
        right.source_continues_prev = None
    elif barrier == "false_declaration":
        right.source_continues_prev = False
    elif barrier == "own_headers":
        right.source_header_scopes = [{"complete": True, "header_rows": [0], "body_rows": []}]
    elif barrier == "new_caption":
        right.caption = "A different scope"
    elif barrier == "new_unit":
        result._native_page_blocks[2][0]["content"] = [{"type": "table_caption", "content": "单位：元"}]
    elif barrier == "intervening_heading":
        result.pages[1].content = "## A different scope\n\n" + right.rendered
    elif barrier == "left_tail":
        result.pages[0].content += "\n\nThe preceding scope has ended."
    elif barrier == "source_conflict":
        right.pdf_evidence = {"bound": False, "reason": "source_cell_text_or_spans_disagree"}
    elif barrier == "column_span":
        right.cells[1].column_span = 2
        right.cells = [c for c in right.cells if c.column != 2]
    elif barrier == "missing_field_path":
        next(c for c in left.cells if (c.row, c.column) == (0, 2)).text = ""
    elif barrier == "arithmetic_boundary":
        left = table([["Item", "2034", "2033", "Change"], ["Profit", "17", "11", "5%"],
                      ["Add:", "", "", ""], ["Adjustment", "3", "2", "6%"]], "left")
        result._table_fragments = [left, right]
        result.pages[0].content = left.rendered
    prepare_native_table_scopes(result)
    assert "inherited_header_scope" not in right.native_evidence


def test_a_declared_continuation_keeps_the_original_header_corner_unit():
    from app.models.table_semantics import CellRef
    from app.services.table_context_service import prepare_native_table_scopes

    result, left, right = continuation_result()
    next(c for c in left.cells if (c.row, c.column) == (0, 0)).text = "(人民币百万元)"
    left.rows[0][0] = "(人民币百万元)"
    result._native_page_blocks[1][0]["content"] = []
    prepare_native_table_scopes(result)
    view = bind_table_view("view", [right], [left, right])
    assert view.records[0].values[0].unit_refs == (CellRef("left", 0, 0),)
    assert not view.records[0].values[-1].unit_refs
    assert "2034：19（单位：(人民币百万元)）" in render_semantic_view(view, [left, right])


def test_a_continuation_keeps_its_own_note_and_does_not_inherit_an_unreferenced_note():
    from app.services.table_context_service import prepare_native_table_scopes

    result, left, right = continuation_result()
    result._native_page_blocks[1][0]["content"].append({"type": "table_footnote", "content": "1 Left-side note."})
    result._native_page_blocks[2][0]["content"] = [{"type": "table_footnote", "content": "2 Right-side note."}]
    prepare_native_table_scopes(result)
    assert bind_table_view("view", [right], [left, right]).status == "converted"
    assert [ref.text for ref in right.context_refs if ref.kind == "note"] == ["2 Right-side note."]
    assert right.context_refs[0].body_rows == (0,)


@pytest.mark.parametrize("intro,expected", [
    ("Net income is allocated to the following segments:", True),
    ("本表各项情况如下：", True),
    ("An unrelated paragraph mentions net income.", False),
    ("A preceding example refers to the following paragraphs.", False),
])
def test_only_an_explicit_adjacent_introduction_becomes_a_record_scope(intro, expected):
    from app.services.table_context_service import prepare_native_table_scopes

    result, left, right = continuation_result()
    result._native_page_blocks[1] = [{"type": "text", "content": intro}, {"type": "table", "content": []}]
    prepare_native_table_scopes(result)
    text = render_semantic_view(bind_table_view("view", [left], [left, right]), [left, right])
    assert ("范围：" + intro in text) == expected


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


@pytest.mark.parametrize("unit", ["(in RMB million)", "(in RMB)", "(百万美元)", "(美元)", "(万盎司)"])
def test_complete_currency_and_physical_units_are_literal_expressions(unit):
    from app.services.table_context_service import unit_description

    assert unit_description(unit)


@pytest.mark.parametrize("pdf_bound", [False, True])
def test_a_currency_corner_is_context_while_explicit_row_units_override_it(pdf_bound):
    from app.models.table_semantics import CellRef

    f = table([["(in RMB million)", "2034", "2033"], ["Operating profit", "1700", "1100"],
               ["Number of customers (in million)", "2.47", "2.31"],
               ["Number of contracts per customer (contract)", "2.92", "2.93"],
               ["Retails customers entitled to benefits (in million)", "1.52", "1.47"],
               ["Operating ROE(1) (%)", "12.7", "12.5"], ["Dividend per share (in RMB)", "2.55", "2.43"]])
    if pdf_bound:
        f.source_header_scopes[0]["evidence_source"] = "source_style_contrast"
        f.pdf_evidence = {"bound": True, "source_cells": [
            {"row": c.row, "column": c.column, "row_span": c.row_span,
             "column_span": c.column_span, "text": c.text} for c in f.cells]}
    before = deepcopy(f)
    view = bind_table_view("view", [f], [f])
    rendered = render_semantic_view(view, [f])
    assert f == before and view.status == "converted"
    assert "(in RMB million)：" not in rendered
    assert "2034：1700（单位：(in RMB million)）" in rendered
    assert all(not record.subject_headers for record in view.records)
    assert all(all(ref != CellRef("native", 0, 0) for ref in value.unit_refs)
               for record in view.records[1:] for value in record.values)
    assert "Number of contracts per customer (contract)；2034：2.92；2033：2.93" in rendered
    assert "Retails customers entitled to benefits (in million)；2034：1.52；2033：1.47" in rendered
    assert "Operating ROE(1) (%)；2034：12.7；2033：12.5" in rendered
    assert "Dividend per share (in RMB)；2034：2.55；2033：2.43" in rendered


def test_an_overridden_corner_unit_is_preserved_when_no_row_uses_it():
    f = table([["(in RMB million)", "2034"], ["Number of customers (in million)", "2.47"]])
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert view.status == "converted" and "(in RMB million)\n\n" in text
    assert "单位：(in RMB million)" not in text


def test_a_scale_on_a_monetary_row_is_not_misclassified_by_a_customer_word():
    from app.services.table_context_service import row_unit_description

    assert not row_unit_description("Revenue from customers (in million)")
    assert not row_unit_description("Profit (in million)")
    assert not row_unit_description("Number of customers (business strategy)")


def test_a_literal_physical_row_unit_overrides_a_currency_caption_without_conversion():
    f = table([["Item", "2034", "2033"], ["外汇", "17", "11"], ["黄金(万盎司)", "6264", "6264"]])
    f.context_refs = (TextRef("native", 1, "cap", "百万美元", "unit", 3, 7, (1, 2), (0, 1, 2)),)
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert "外汇；2034：17（单位：百万美元）；2033：11（单位：百万美元）" in text
    assert "黄金(万盎司)；2034：6264；2033：6264" in text
    assert all(ref.text != "百万美元" for value in view.records[1].values for ref in value.unit_refs
               if isinstance(ref, TextRef))


@pytest.mark.parametrize("barrier", [None, "prose", "reference", "math", "other_table_number"])
def test_adjacent_native_captions_keep_their_order_and_stop_at_unowned_context(barrier):
    from app.models.parse_result import DocumentParseResult, ParsePipeline
    from app.services.table_context_service import prepare_native_table_scopes

    f = table([["Item", "2034"], ["Alpha", "17"]])
    blocks = [{"type": "table_caption", "content": "附表 7"},
              {"type": "table_caption", "content": "金融指标"},
              {"type": "text", "content": "(年末余额)"},
              {"type": "table_caption", "content": "单位：百万美元"},
              {"type": "table", "content": []}]
    if barrier == "prose":
        blocks[2]["content"] = "A separate ordinary paragraph."
    elif barrier == "reference":
        blocks[1]["content"] = "See Table 7 for details"
    elif barrier == "math":
        blocks[2]["content"] = "(x = y + 7)"
    elif barrier == "other_table_number":
        blocks.insert(0, {"type": "table_caption", "content": "附表 6"})
    result = DocumentParseResult(document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
                                 page_count=1, processed_pages=1, pipeline=ParsePipeline(profile="accurate", primary="mineru"))
    result._table_fragments = [f]
    result._native_page_blocks = {1: blocks}
    prepare_native_table_scopes(result)
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert "2034：17（单位：百万美元）" in text and "范围：单位" not in text
    if barrier in {None, "other_table_number"}:
        assert [ref.text for ref in f.context_refs if ref.kind == "title"] == ["附表 7", "金融指标", "(年末余额)"]
        assert "范围：附表 7 / 金融指标 / (年末余额)" in text
        assert "附表 6" not in text
    else:
        assert "附表 7" not in text
        assert "A separate" not in text and "See Table" not in text and "x =" not in text


@pytest.mark.parametrize("barrier", [None, "no_number", "sentence", "intervening", "reference"])
def test_a_complete_literal_table_caption_run_does_not_require_native_caption_tags(barrier):
    from app.models.parse_result import DocumentParseResult, ParsePipeline
    from app.services.table_context_service import prepare_native_table_scopes

    f = table([["Item", "2034"], ["Alpha", "17"]])
    blocks = [{"type": "text", "content": "附表 7"}, {"type": "text", "content": "金融指标（一）"},
              {"type": "text", "content": "（年末余额）"},
              {"type": "table", "content": [{"type": "table_caption", "content": "单位：亿元"}]}]
    if barrier == "no_number":
        blocks[0]["content"] = "A nearby chapter"
    elif barrier == "sentence":
        blocks[1]["content"] = "这是另一段正文。"
    elif barrier == "intervening":
        blocks.insert(3, {"type": "text", "content": "A separate ordinary paragraph."})
    elif barrier == "reference":
        blocks[0]["content"] = "See Table 7"
    result = DocumentParseResult(document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
                                 page_count=1, processed_pages=1, pipeline=ParsePipeline(profile="accurate", primary="mineru"))
    result._table_fragments = [f]
    result._native_page_blocks = {1: blocks}
    prepare_native_table_scopes(result)
    text = render_semantic_view(bind_table_view("view", [f], [f]), [f])
    assert "2034：17（单位：亿元）" in text
    if barrier is None:
        assert "范围：附表 7 / 金融指标（一） / （年末余额）" in text
    else:
        assert "范围：" not in text


@pytest.mark.parametrize("barrier", [None, "ordinary_prose", "new_heading"])
def test_a_native_quarterly_heading_and_its_unit_stay_with_the_adjacent_table(barrier):
    from app.models.parse_result import DocumentParseResult, ParsePipeline
    from app.services.table_context_service import prepare_native_table_scopes

    f = table([["", "第一季度", "第二季度"], ["Revenue", "17", "11"]])
    blocks = [{"type": "title", "content": "八、分季度主要财务指标"},
              {"type": "table_caption", "content": "单位：千元"}, {"type": "table", "content": []}]
    if barrier == "ordinary_prose":
        blocks.insert(1, {"type": "text", "content": "A separate paragraph."})
    elif barrier == "new_heading":
        blocks.insert(1, {"type": "title", "content": "Other operations"})
    result = DocumentParseResult(document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
                                 page_count=1, processed_pages=1, pipeline=ParsePipeline(profile="accurate", primary="mineru"))
    result._table_fragments = [f]
    result._native_page_blocks = {1: blocks}
    prepare_native_table_scopes(result)
    text = render_semantic_view(bind_table_view("view", [f], [f]), [f])
    assert "第一季度：17（单位：千元）；第二季度：11（单位：千元）" in text
    assert "2034" not in text
    assert ("范围：八、分季度主要财务指标" in text) == (barrier is None)


@pytest.mark.parametrize("owner", ["table", "text", "table_caption"])
@pytest.mark.parametrize("escaped", [False, True])
def test_neighboring_table_body_cannot_become_a_current_records_unit_or_title(owner, escaped):
    import html

    from app.models.parse_result import DocumentParseResult, ParsePipeline
    from app.services.table_context_service import prepare_native_table_scopes

    previous = table([["Name", "2024"], ["Separate loan", "777"]], "previous")
    current = table([["Item", "Party", "Reporting period"], ["Interest", "Alpha", "17"]], "current")
    current.source_header_scopes = [{"header_rows": [0], "body_rows": [1],
                                     "row_header_columns": [0, 1], "complete": True}]
    current.pdf_evidence = {"bound": True, "source_cells": [
        {"row": c.row, "column": c.column, "row_span": c.row_span,
         "column_span": c.column_span, "text": c.text, "shaded": False} for c in current.cells
    ]}
    raw = "单位:元 币种:人民币<table><tr><td>Separate loan</td><td>777</td></tr></table>"
    if escaped:
        raw = html.escape(raw)
    blocks = [{"type": "table", "content": raw if owner == "table" else "other native table"}]
    if owner != "table":
        blocks.append({"type": owner, "content": raw})
    blocks.append({"type": "table", "content": [{"type": "table_caption", "content": "Interest received"}]})
    result = DocumentParseResult(document_id="authored", filename="authored.pdf", mime_type="application/pdf",
                                 page_count=1, processed_pages=1,
                                 pipeline=ParsePipeline(profile="accurate", primary="mineru"))
    result._table_fragments = [previous, current]
    result._native_page_blocks = {1: blocks}
    prepare_native_table_scopes(result)
    assert all("777" not in ref.text and "table" not in ref.text for ref in current.context_refs)
    rendered = render_semantic_view(bind_table_view("view", [current], [current]), [current])
    assert "17" in rendered and "777" not in rendered
    assert "单位：单位" not in rendered


def test_complete_amount_and_currency_caption_keeps_its_exact_literal_payload():
    from app.services.table_context_service import _unit_caption

    text = "单位:元 币种:人民币"
    unit, start = _unit_caption(text)
    assert text[start:start + len(unit)] == unit == "元 币种:人民币"
    assert _unit_caption("单位:元 币种:贷款申请方") is None


def test_a_literal_empty_amount_slot_keeps_its_unit_without_inventing_a_value():
    from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
    from app.services.final_content_service import FinalContentService
    from moparse_eval.matching import match_units
    from moparse_eval.scoring import _score_records
    from moparse_eval.service_observation import build_service_observation, read_final_observation

    f = table([["Name", "贷款金额", "本期合计还款金额", "利率(%)", "备注", "序号"],
               ["Alpha", "17", "", "", "", ""]])
    f.context_refs = (TextRef("native", 1, "caption", "元 币种:人民币", "unit", 3, 11,
                              (1,), (0, 1, 2, 3, 4, 5)),)
    view = bind_table_view("view", [f], [f])
    record = view.records[0]
    blank = next(v for v in record.values if v.value.column == 2)
    assert blank.value_state == "literal" and blank.unit_refs == f.context_refs
    rendered = render_semantic_view(view, [f])
    assert "本期合计还款金额：（单位：元 币种:人民币）" in rendered
    assert "本期合计还款金额：0" not in rendered and "原表留空" not in rendered
    assert all(not v.unit_refs for v in record.values if v.value.column in {4, 5})
    ratio = next(v for v in record.values if v.value.column == 3)
    assert all(ref != f.context_refs[0] for ref in ratio.unit_refs)
    result = DocumentParseResult(document_id="authored", filename="authored.pdf", mime_type="application/pdf",
                                 page_count=1, processed_pages=1, markdown=rendered,
                                 pages=[PageParseResult(page_number=1, content=rendered)],
                                 pipeline=ParsePipeline(profile="accurate", primary="mineru"))
    result._table_fragments = [f]
    result._semantic_tables = [view]
    FinalContentService().apply(result)
    observation, _diagnostic = read_final_observation(build_service_observation(result, sample_id="authored"))
    target = {"id": "blank-amount", "kind": "table_record", "pages": [1],
              "table": {"row_header_path": ["Alpha"], "fields": [
                  {"column_header_path": ["本期合计还款金额"], "value": "", "unit": "元"}]}}
    _units, metrics = _score_records([target], observation, True, match_units([target], observation))
    assert metrics["target_fields"] == metrics["information_correct_fields"] == 1


def test_existing_source_scope_owns_amount_caption_when_native_headers_are_unclassified():
    from app.models.parse_result import DocumentParseResult, ParsePipeline
    from app.services.table_context_service import prepare_native_table_scopes

    f = table([["", "Window A", "Window B"], ["Cash generated", "170", "110"],
               ["Margin", "17%", "11%"]])
    assert f.native_evidence["header_scopes"] == []
    f.source_header_scopes = [{"header_rows": [0], "body_rows": [1, 2], "complete": True}]
    f.pdf_evidence = {"bound": True, "source_cells": [
        {"row": c.row, "column": c.column, "row_span": c.row_span,
         "column_span": c.column_span, "text": c.text, "shaded": False} for c in f.cells
    ]}
    result = DocumentParseResult(document_id="authored", filename="authored.pdf", mime_type="application/pdf",
                                 page_count=1, processed_pages=1,
                                 pipeline=ParsePipeline(profile="accurate", primary="mineru"))
    result._table_fragments = [f]
    result._native_page_blocks = {1: [{"type": "table", "content": [
        {"type": "table_caption", "content": "单位:千元"}]}]}
    prepare_native_table_scopes(result)
    assert f.context_refs[0].body_rows == (1, 2)
    rendered = render_semantic_view(bind_table_view("view", [f], [f]), [f])
    assert "Window A：170（单位：千元）" in rendered
    assert "Window B：110（单位：千元）" in rendered
    assert "17%（单位：千元）" not in rendered


@pytest.mark.parametrize("header", ["增减%", "Change(%)", "变化（％）", "增减率", "增減率", "本年末比上年末增减"])
def test_percent_only_column_label_does_not_inherit_an_amount_caption(header):
    f = table([["Item", "2024", header], ["Revenue", "170", "11"]])
    f.context_refs = (TextRef("native", 1, "cap", "千元", "unit", 3, 5, (1,), (0, 1, 2)),)
    rendered = render_semantic_view(bind_table_view("view", [f], [f]), [f])
    assert "2024：170（单位：千元）" in rendered
    assert header + "：11（单位：千元）" not in rendered
    assert header + "：11。" in rendered


def test_ratio_dash_and_empty_amount_slots_keep_distinct_unit_meanings():
    f = table([["Item", "Amount", "增减率"], ["Cash movement", "", "—"]])
    f.context_refs = (TextRef("native", 1, "cap", "万元", "unit", 3, 5, (1,), (0, 1, 2)),)
    view = bind_table_view("view", [f], [f])
    # A declared source header permits an empty monetary slot without
    # manufacturing zero; the neighboring rate's dash is still unitless.
    assert view.records[0].values[0].unit_refs
    assert not view.records[0].values[1].unit_refs
    text = render_semantic_view(view, [f])
    assert "Amount：（单位：万元）" in text and "增减率：—。" in text


def test_parenthetical_equity_business_terms_are_not_mistaken_for_units():
    f = table([["Item", "2034", "本年末比上年末增减"],
               ["资产处置（包括股权及其他投资）", "17", "—"]])
    f.context_refs = (TextRef("native", 1, "cap", "万元", "unit", 0, 2, (1,), (0, 1, 2)),)
    view = bind_table_view("view", [f], [f])
    text = render_semantic_view(view, [f])
    assert "2034：17（单位：万元）；本年末比上年末增减：—。" in text
    assert view.records[0].values[0].unit_refs == f.context_refs


def test_an_explicit_share_unit_is_preserved_without_matching_equity_business_words():
    from app.services.table_context_service import unit_description

    assert unit_description("(股)") and unit_description("(万股)")
    assert not unit_description("(股权及其他投资)")
    f = table([["Item", "2034"], ["Issued shares(万股)", "17"]])
    record = bind_table_view("view", [f], [f]).records[0]
    assert record.values[0].unit_refs == (record.subject,)


@pytest.mark.parametrize("unit", ["人民币十亿元", "港元百萬元", "亿元", "万亿元"])
def test_explicit_currency_scale_words_keep_precedence_over_a_table_caption(unit):
    f = table([["Item", "2034$m"], ["Reserve(" + unit + ")", "17"]])
    f.context_refs = (TextRef("native", 1, "cap", "千元", "unit", 0, 2, (1,), (0, 1)),)
    view = bind_table_view("view", [f], [f])
    assert view.records[0].values[0].unit_refs == (view.records[0].subject,)
    assert "Reserve(" + unit + ")；2034：17。" in render_semantic_view(view, [f])
    assert "单位：千元" not in render_semantic_view(view, [f])


@pytest.mark.parametrize("value", ["≥25", "≤10.5", ">=8.5", "<4", "≧7.5"])
def test_numeric_limits_keep_their_printed_operator_and_declared_unit(value):
    f = table([["Item", "Standard", "2034"], ["Liquidity", value, "52.51"]])
    f.context_refs = (TextRef("native", 1, "cap", "%", "unit", 0, 1, (1,), (0, 1, 2)),)
    view = bind_table_view("view", [f], [f])
    assert view.records[0].values[0].unit_refs == f.context_refs
    text = render_semantic_view(view, [f])
    assert "Standard：" + value.replace(">", "&gt;").replace("<", "&lt;") + "（单位：%）" in text
    assert "2034：52.51（单位：%）" in text


def test_a_first_numeric_limit_is_data_and_cannot_supply_a_header():
    f = table([["Liquidity minimum", "≥25"], ["Capital minimum", "≥8.5"]])
    assert bind_table_view("view", [f], [f]).status == "retained"


@pytest.mark.parametrize('name_header', ['认购方', '股东名称', 'Subscriber'])
def test_explicit_total_spanning_ordinal_and_identity_fields_is_not_an_entity_name(name_header):
    f = table([["序号", name_header, "Amount(万元)", "Shares(股)"],
               ["1", "Alpha", "17.00", "1100"], ["2", "Beta", "11.00", "700"],
               ["合计", "", "28.00", "1800"]])
    total = next(c for c in f.cells if (c.row, c.column) == (3, 0))
    total.column_span = 2
    f.cells = [c for c in f.cells if (c.row, c.column) != (3, 1)]
    f.native_evidence = native_scopes(f)
    f.source_header_scopes = f.native_evidence['header_scopes']
    before = deepcopy(f)
    view = bind_table_view('view', [f], [f])
    assert view.status == 'converted' and len(view.records) == 3
    rendered = render_semantic_view(view, [f])
    assert name_header + '：Alpha；序号：1' in rendered
    assert '- 合计；Amount(万元)：28.00；Shares(股)：1800。' in rendered
    assert name_header + '：合计' not in rendered and f == before


@pytest.mark.parametrize('text,span', [('Unlabelled operation', 2), ('合计', 3)])
def test_summary_span_rule_cannot_invent_a_total_or_cross_a_measurement_column(text, span):
    f = table([["No", "Name", "Amount(万元)", "Shares(股)"],
               ["1", "Alpha", "17", "1100"], [text, "", "" if span == 3 else "28", "1800"]])
    stub = next(c for c in f.cells if (c.row, c.column) == (2, 0))
    stub.column_span = span
    f.cells = [c for c in f.cells if not (c.row == 2 and 0 < c.column < span)]
    f.native_evidence = native_scopes(f)
    f.source_header_scopes = f.native_evidence['header_scopes']
    view = bind_table_view('view', [f], [f])
    assert view.status == 'partial' and [r.source_row for r in view.records] == [1]


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
