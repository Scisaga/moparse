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
