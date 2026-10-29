"""Authored source fixtures for structural binding and relation-entry limits."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest

from app.services.pdf_table_evidence_service import (
    _field_candidates,
    _header_candidates,
    _measure_label,
    _named_subject_column,
    _period_label,
    inspect_pdf_tables,
)
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows


def _fragment(rows: list[list[str]], *, kind: str = "mineru", boxes: bool = False) -> TableFragment:
    width, top, step = 320 / len(rows[0]), 50, 30
    cells = [TableCellFragment(
        row, col, 1, 1, text,
        ((40 + width * col) / 400, (top + step * row) / 300,
         (40 + width * (col + 1)) / 400, (top + step * (row + 1)) / 300) if boxes else None,
    ) for row, values in enumerate(rows) for col, text in enumerate(values)]
    md = render_gfm_rows(rows)
    return TableFragment(
        "synthetic-table", 1, 1, (0.1, top / 300, 0.9, (top + step * len(rows)) / 300),
        len(rows), len(rows[0]), deepcopy(rows), [], md, md,
        source_kind=kind, cells=cells, header_scope_complete=False,
    )


def _source(path: Path, rows: list[list[str]], *, borders: bool = True,
            grouped: bool = False, shade: bool = False, header_rows: int = 1,
            left: bool = True, kind: str = "mineru", boxes: bool = False) -> TableFragment:
    item = _fragment(rows, kind=kind, boxes=boxes)
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        xs = [40 + 320 * col / item.num_cols for col in range(item.num_cols + 1)]
        ys = [50 + 30 * row for row in range(item.num_rows + 1)]
        if shade:
            page.draw_rect((xs[0], ys[0], xs[-1], ys[header_rows]), color=None, fill=(0.8, 0.8, 0.8))
        if borders:
            shape = page.new_shape()
            for x in xs:
                shape.draw_line((x, ys[0]), (x, ys[-1]))
            for y in ys:
                shape.draw_line((xs[0], y), (xs[-1], y))
            if grouped:
                # This unrelated segment enlarges the PDF path's overall bbox.
                shape.draw_line((10, 10), (390, 10))
            shape.finish(color=(0, 0, 0), width=1)
            shape.commit()
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                page.insert_textbox((xs[c] + 4, ys[r] + 8, xs[c + 1] - 4, ys[r + 1]), text,
                                    fontsize=9, fontname="hebo" if r < header_rows else "helv",
                                    align=0 if left or r >= header_rows else 1)
        document.save(path)
    return item


def test_grouped_page_path_keeps_actual_grid_segments_inside_roi(tmp_path: Path):
    path = tmp_path / "authored-grouped-path.pdf"
    item = _source(path, [["Metric", "2024", "2023"], ["Alpha", "100", "90"]], grouped=True)
    state = inspect_pdf_tables(path, [item])[0]
    assert state["bound"] and state["binding_method"] == "vector_grid"
    assert item.header_row_indices == (0,)
    assert state["content_kind"] == "data_table"


@pytest.mark.parametrize("kind", ["mineru", "glm", "docling"])
def test_source_binding_accepts_supported_cell_structures_from_each_backend(tmp_path: Path, kind: str):
    path = tmp_path / "authored-backend.pdf"
    item = _source(path, [["Metric", "2024", "2023"], ["Alpha", "100", "90"]], kind=kind)
    state = inspect_pdf_tables(path, [item])[0]
    assert state["bound"] and item.header_row_indices == (0,)
    assert state["source_header_scopes"][0]["evidence"]["source_period_and_stub_scope"]


def test_borderless_explicit_cell_partition_is_structure_not_assumed_semantics(tmp_path: Path):
    path = tmp_path / "authored-borderless.pdf"
    item = _source(path, [["Metric", "2024", "2023"], ["Alpha", "100", "90"]],
                   borders=False, boxes=True)
    state = inspect_pdf_tables(path, [item])[0]
    assert state["bound"] and state["binding_method"] == "native_cell_boxes"
    assert state["vector_attempt_reason"] == "no_complete_source_vector_grid"
    assert state["content_kind"] == "data_table" and item.header_row_indices == (0,)


@pytest.mark.parametrize("damage", ["missing_boxes", "changed_value", "inconsistent_boundary"])
def test_borderless_structure_does_not_guess_missing_or_conflicting_evidence(tmp_path: Path, damage: str):
    path = tmp_path / "authored-conflict.pdf"
    item = _source(path, [["Metric", "2024", "2023"], ["Alpha", "100", "90"]],
                   borders=False, boxes=damage != "missing_boxes")
    if damage == "changed_value":
        item.cells[-1].text = "99"
    if damage == "inconsistent_boundary":
        box = item.cells[-1].normalized_bbox
        assert box is not None
        item.cells[-1].normalized_bbox = (box[0] + 0.02, box[1], box[2], box[3])
    state = inspect_pdf_tables(path, [item])[0]
    assert not state["bound"] and not item.source_header_scopes
    assert state["cell_box_attempt_reason"] in {
        "native_cell_boxes_unavailable", "source_cell_box_text_disagrees", "native_cell_boundaries_disagree",
    }


def test_bordered_prose_and_backend_header_flags_do_not_establish_data_relations(tmp_path: Path):
    path = tmp_path / "authored-layout.pdf"
    item = _source(path, [["First heading", "Second heading"], ["First prose paragraph.", "Second prose paragraph."]],
                   header_rows=1, shade=True, boxes=True)
    for cell in item.cells:
        cell.is_column_header = cell.row == 0
    state = inspect_pdf_tables(path, [item])[0]
    assert state["bound"] and state["content_kind"] == "unknown"
    assert state["source_header_scopes"] == state["field_scopes"] == []


def test_explicit_unshaded_field_delimiters_have_local_source_pairs(tmp_path: Path):
    path = tmp_path / "authored-fields.pdf"
    item = _source(path, [["Name:", "Alpha"], ["Amount:", "10"]], header_rows=0)
    state = inspect_pdf_tables(path, [item])[0]
    assert state["bound"] and state["source_header_scopes"] == []
    assert [scope["pairs"] for scope in state["field_scopes"]] == [
        [{"label": [0, 0], "value": [0, 1]}], [{"label": [1, 0], "value": [1, 1]}],
    ]
    assert all(scope["evidence"]["explicit_label_delimiters"] for scope in state["field_scopes"])


def test_source_named_fields_with_label_style_are_not_lost_without_colons(tmp_path: Path):
    rows = [["Company name", "Alpha"], ["Contact", "Beta"]]
    item = _fragment(rows)
    path = tmp_path / "authored-named-fields.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        for x in (40, 200, 360):
            page.draw_line((x, 50), (x, 110))
        for y in (50, 80, 110):
            page.draw_line((40, y), (360, y))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                page.insert_textbox((44 + c * 160, 58 + r * 30, 196 + c * 160, 80 + r * 30), text,
                                    fontsize=9, fontname="hebo" if c == 0 else "helv")
        document.save(path)
    state = inspect_pdf_tables(path, [item])[0]
    assert state["bound"] and len(state["field_scopes"]) == 2
    assert all(scope["evidence"]["explicit_field_label_type"] for scope in state["field_scopes"])


@pytest.mark.parametrize("suffix", ["", ":"])
def test_source_label_shading_cannot_turn_long_grid_prose_into_fields(suffix):
    rows = [["Name" + suffix, "A long paragraph " * 12], ["Contact" + suffix, "Another paragraph " * 12]]
    # The binding itself is synthetic here; classification must still inspect
    # content relations instead of accepting the shaded-label pattern alone.
    grid = _grid(rows)
    for cell in grid["source_cells"]:
        cell["shaded"] = cell["column"] == 0
    assert _field_candidates(grid, 2) == []


def _grid(rows: list[list[str]], *, centered: bool = False, bold: bool = False) -> dict:
    return {"source_cells": [
        {"row": r, "column": c, "row_span": 1, "column_span": 1, "text": text,
         "centered": centered if r == 0 else False, "bold": bold if r == 0 else False, "shaded": False}
        for r, row in enumerate(rows) for c, text in enumerate(row)
    ]}


def test_left_aligned_period_headers_and_bold_scalar_headers_have_independent_evidence():
    periods = _header_candidates(_grid([["Metric", "2024", "2023"], ["Alpha", "100", "90"]]), 2, 3)
    assert periods[0]["header_rows"] == [0]
    assert periods[0]["evidence"]["source_period_and_stub_scope"]
    labels = _header_candidates(_grid([["Name", "Amount"], ["Alpha", "100"]], bold=True), 2, 2)
    assert labels[0]["evidence"]["source_bold_contrast"]


@pytest.mark.parametrize("labels", [
    ["项目", "2014年度", "2013年度", "增减%"],
    ["项目", "金额", "占业务总收入比重", "较上年同期增减(%)"],
    ["Metric", "2024", "2023", "Change %"],
    ["Metric", "Amount", "Share %", "Difference"],
])
@pytest.mark.parametrize("centered", [False, True])
def test_typed_period_and_measure_matrix_does_not_depend_on_alignment_contrast(labels, centered):
    grid = _grid([labels, ["Alpha", "120", "100", "20%"]])
    for cell in grid["source_cells"]:
        cell["centered"] = centered
    scopes = _header_candidates(grid, 2, 4)
    assert len(scopes) == 1 and scopes[0]["header_rows"] == [0]
    evidence = scopes[0]["evidence"]
    assert evidence["source_typed_measure_scope"]
    assert not evidence["source_shading_contrast"]
    assert not evidence["source_bold_contrast"]
    assert not evidence["source_numeric_column_alignment_contrast"]


def test_typed_measure_matrix_keeps_a_non_numeric_explanation_column():
    grid = _grid([
        ["Metric", "2024", "2023", "Change %", "Reason"],
        ["Alpha", "120", "100", "20%", "Operating scope changed."],
    ])
    for cell in grid["source_cells"]:
        cell["centered"] = True
    scopes = _header_candidates(grid, 2, 5)
    assert len(scopes) == 1
    assert scopes[0]["body_rows"] == [1]
    assert scopes[0]["evidence"]["numeric_body_columns"] == [1, 2, 3]


@pytest.mark.parametrize("rows", [
    [["Outline", "Amount", "Share %"], ["Alpha", "120", "10%"]],
    [["Metric", "Amount", "Description"], ["Alpha", "120", "A prose description."]],
    [["Metric", "Amount 2024.50", "2023"], ["Alpha", "120", "100"]],
    [["Metric", "2024", "Discussion"], ["Alpha", "120", "100"]],
    [["Metric", "Amount", "Share %"], ["A prose description.", "Another explanation.", "Final note."]],
])
def test_unstyled_numeric_cells_and_keyword_fragments_do_not_invent_a_measure_scope(rows):
    grid = _grid(rows)
    for cell in grid["source_cells"]:
        cell["centered"] = True
    assert _header_candidates(grid, 2, 3) == []


@pytest.mark.parametrize("label", [
    "Amount 2024", "Amount 2024.50", "金额2024", "2024.50", "-2024", "2024%",
    "Not an amount", "The amount is discussed here.", "金额说明。", "金额(万元", "金额(万元))",
])
def test_complete_measure_roles_do_not_accept_values_or_arbitrary_substrings(label):
    assert not _measure_label(label)


def test_uniform_source_pdf_period_and_change_columns_have_complete_source_association(tmp_path):
    rows = [["Metric", "2024", "2023", "Change %"], ["Alpha", "120", "100", "20%"]]
    item = _fragment(rows)
    path = tmp_path / "authored-uniform-measures.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        xs, ys = [40, 120, 200, 280, 360], [50, 80, 110]
        for x in xs:
            page.draw_line((x, ys[0]), (x, ys[-1]), width=1)
        for y in ys:
            page.draw_line((xs[0], y), (xs[-1], y), width=1)
        for row, values in enumerate(rows):
            for col, text in enumerate(values):
                page.insert_textbox((xs[col] + 4, ys[row] + 8, xs[col + 1] - 4, ys[row + 1]),
                                    text, fontsize=9, fontname="helv", align=1)
        document.save(path)
    state = inspect_pdf_tables(path, [item])[0]
    assert state["bound"] and state["content_kind"] == "data_table"
    scope = state["source_header_scopes"][0]
    assert scope["header_rows"] == [0] and scope["body_rows"] == [1]
    assert scope["evidence"]["source_typed_measure_scope"]
    assert not scope["evidence"]["source_shading_contrast"]
    assert not scope["evidence"]["source_bold_contrast"]
    assert not scope["evidence"]["source_numeric_column_alignment_contrast"]


def test_all_numeric_source_rows_remain_data_even_when_values_look_like_years():
    for labels in (["10", "20", "30"], ["2000", "2024", "2023"]):
        assert _header_candidates(_grid([labels, ["Alpha", "100", "90"]], centered=True), 2, 3) == []


@pytest.mark.parametrize("value", [
    "20240", "12024", "2024.50", "2024%", "-2024", "20240年", "12024年度",
    "Amount 2024.50", "金额2024.50", "本期金额2024.50", "Amount 2024", "金额2024",
])
def test_year_substrings_in_amounts_and_identifiers_do_not_establish_periods(value):
    assert not _period_label(value)
    grid = _grid([["Metric", value, "2023"], ["A", "11", "10"]])
    assert _header_candidates(grid, 2, 3) == []


@pytest.mark.parametrize("value", [
    "2024", "2024年度", "2024年12月31日", "2024-12-31", "2024/12/31", "截至2024年12月31日",
    "本期", "上期", "本年", "上年", "报告期", "同期", "期末", "年末", "月末", "年度",
    "current", "prior", "previous", "reporting period", "year ended", "as of",
])
def test_complete_period_literals_and_existing_period_words_remain_supported(value):
    assert _period_label(value)


@pytest.mark.parametrize("center_body", [False, True])
def test_year_valued_body_record_cannot_deepen_the_header_band(center_body):
    grid = _grid([
        ["Metric", "2024", "2023"], ["Sales", "2024", "2023"], ["Costs", "11", "10"],
    ], centered=True, bold=True)
    if center_body:
        for cell in grid["source_cells"]:
            if cell["row"] == 1:
                cell["centered"] = True
    scopes = _header_candidates(grid, 3, 3)
    assert [(scope["header_rows"], scope["body_rows"]) for scope in scopes] == [([0], [1, 2])]


def test_styled_key_value_row_is_not_a_header_for_following_fields():
    assert _header_candidates(_grid([["Name", "Alpha"], ["Amount", "10"]], bold=True), 2, 2) == []


def test_explicit_ordinal_and_named_record_columns_do_not_disable_header_binding(tmp_path: Path):
    path = tmp_path / "authored-index.pdf"
    item = _source(path, [["Index", "Name", "Amount"], ["1", "Alpha", "100"]])
    state = inspect_pdf_tables(path, [item])[0]
    scope = state["source_header_scopes"][0]
    assert scope["header_rows"] == [0] and scope["row_header_columns"] == [1]
    assert scope["evidence"]["source_ordinal_record_role"]


def test_internal_period_header_changes_remain_distinct_scopes():
    scopes = _header_candidates(_grid([
        ["Metric", "2024", "2023"], ["Alpha", "100", "90"],
        ["Metric", "2022", "2021"], ["Beta", "80", "70"],
    ]), 4, 3)
    assert [(scope["header_rows"], scope["body_rows"]) for scope in scopes] == [([0], [1]), ([2], [3])]


@pytest.mark.parametrize('period', ['2025年1-6月', '2025年1至9月', '2025年1—12月'])
def test_month_range_opens_its_own_period_scope_without_inheriting_a_balance_date(period):
    scopes = _header_candidates(_grid([
        ['项目', '2025年9月30日'], ['资产', '17'], ['项目', period], ['收入', '8'],
    ]), 4, 2)
    assert [(s['header_rows'], s['body_rows']) for s in scopes] == [([0], [1]), ([2], [3])]
    assert not _period_label(period + '预计增加收入')


def test_explicit_entity_column_is_the_record_subject_and_metric_stays_present(tmp_path: Path):
    from app.services.table_semantics_service import bind_table_view, render_semantic_view
    path = tmp_path / 'invented-entities.pdf'
    item = _source(path, [['Metric', 'Counterparty', '2025'], ['Interest', 'Alpha', '17'],
                          ['Interest', 'Beta', '8']])
    state = inspect_pdf_tables(path, [item])[0]
    assert state['source_header_scopes'][0]['row_header_columns'] == [0, 1]
    view = bind_table_view('invented', [item], [item])
    assert view.status == 'converted'
    rendered = render_semantic_view(view, [item])
    assert 'Metric / Counterparty：Interest / Alpha；2025：17' in rendered
    assert 'Metric / Counterparty：Interest / Beta；2025：8' in rendered


def test_entity_wording_does_not_classify_prose_grids_or_choose_between_two_subjects():
    grid = _grid([['Metric', 'Counterparty', 'Notes'], ['Policy', 'A paragraph ' * 20, 'No transaction.']])
    assert _header_candidates(grid, 2, 3) == []
    scope = {'header_rows': [0], 'body_rows': [1]}
    assert _named_subject_column(grid, scope) is None
    ambiguous = _grid([['Metric', 'Counterparty', 'Company name', '2025'], ['Interest', 'Alpha', 'Beta', '17']])
    assert _named_subject_column(ambiguous, scope) is None


def test_real_source_rowspans_and_colspans_support_complete_multilevel_header(tmp_path: Path):
    rows = [["Metric", "Revenue", ""], ["", "2024", "2023"], ["Alpha", "100", "90"]]
    item = _fragment(rows)
    item.cells = [cell for cell in item.cells if (cell.row, cell.column) not in {(0, 2), (1, 0)}]
    item.cells[0].row_span = 2
    item.cells[1].column_span = 2
    xs, ys = [40, 146.666667, 253.333333, 360], [50, 80, 110, 140]
    path = tmp_path / "authored-spans.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        for x in (xs[0], xs[1], xs[-1]):
            page.draw_line((x, ys[0]), (x, ys[-1]), width=1)
        page.draw_line((xs[2], ys[1]), (xs[2], ys[-1]), width=1)
        for y in (ys[0], ys[2], ys[3]):
            page.draw_line((xs[0], y), (xs[-1], y), width=1)
        page.draw_line((xs[1], ys[1]), (xs[-1], ys[1]), width=1)
        for cell in item.cells:
            page.insert_textbox((xs[cell.column] + 4, ys[cell.row] + 8,
                                 xs[cell.column + cell.column_span] - 4, ys[cell.row + cell.row_span]),
                                cell.text, fontsize=9, fontname="hebo" if cell.row < 2 else "helv")
        document.save(path)
    state = inspect_pdf_tables(path, [item])[0]
    assert state["bound"] and item.header_row_indices == (0, 1)
    assert state["source_header_scopes"][0]["header_rows"] == [0, 1]
    assert state["source_header_scopes"][0]["evidence"]["source_multirow_span_scope"]


def test_group_row_is_not_swallowed_into_a_multilevel_column_header():
    grid = _grid([["Metric", "2024", "2023"], ["Group A", "", ""], ["Alpha", "100", "90"]])
    assert _header_candidates(grid, 3, 3) == []


@pytest.mark.parametrize("leading_header,expected", [("Group", [0, 1]), ("Note", None)])
def test_source_row_group_columns_require_named_group_role_and_real_span(tmp_path: Path, leading_header, expected):
    rows = [[leading_header, "Metric", "2024", "2023"], ["North", "Alpha", "100", "90"],
            ["", "Beta", "80", "70"]]
    item = _fragment(rows)
    item.cells = [cell for cell in item.cells if (cell.row, cell.column) != (2, 0)]
    next(cell for cell in item.cells if (cell.row, cell.column) == (1, 0)).row_span = 2
    xs, ys = [40, 120, 200, 280, 360], [50, 80, 110, 140]
    path = tmp_path / "authored-row-groups.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=300)
        for x in xs:
            page.draw_line((x, ys[0]), (x, ys[-1]), width=1)
        for y in (ys[0], ys[1], ys[3]):
            page.draw_line((xs[0], y), (xs[-1], y), width=1)
        page.draw_line((xs[1], ys[2]), (xs[-1], ys[2]), width=1)
        for cell in item.cells:
            page.insert_textbox((xs[cell.column] + 4, ys[cell.row] + 8,
                                 xs[cell.column + 1] - 4, ys[cell.row + cell.row_span]),
                                cell.text, fontsize=9, fontname="hebo" if cell.row == 0 else "helv")
        document.save(path)
    state = inspect_pdf_tables(path, [item])[0]
    assert state["bound"]
    scope = state["source_header_scopes"][0]
    assert scope.get("row_header_columns") == expected
    if expected:
        assert scope["evidence"]["source_typed_row_group_span"]
