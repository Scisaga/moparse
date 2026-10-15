"""Source-backed table completeness, independent of a label or business domain."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pymupdf
import pytest

from app.models.parse_result import PageParseResult
from app.services.ir_service import DocumentIRService
from app.services.native_table_service import restore_missing_native_merged_cells
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    _complete_header_signature,
    assemble_logical_tables,
    link_cross_page_tables,
    render_gfm_rows,
)

_WIDTH = 720.0
_HEIGHT = 600.0
_X = (40.0, 190.0, 340.0, 490.0, 640.0)
_Y = (80.0, 116.0, 152.0, 188.0, 224.0, 260.0, 296.0)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _source_cells(label: str) -> list[TableCellFragment]:
    specifications = [
        (0, 0, 2, 1, "Category"),
        (0, 1, 1, 2, "Observed Inputs"),
        (0, 3, 2, 1, "Unit"),
        (1, 1, 1, 1, "Current"),
        (1, 2, 1, 1, "Previous"),
        (2, 0, 3, 1, label),
        (2, 1, 1, 1, "12.50"),
        (2, 2, 1, 1, "-1.25"),
        (2, 3, 1, 1, "元／股"),
        (3, 1, 1, 1, "14.75"),
        (3, 2, 1, 1, "0.00"),
        (3, 3, 1, 1, "元／股"),
        (4, 1, 1, 1, "18.00"),
        (4, 2, 1, 1, "2.50"),
        (4, 3, 1, 1, "元／股"),
        (5, 0, 1, 1, "Total"),
        (5, 1, 1, 1, "45.25"),
        (5, 2, 1, 1, "1.25"),
        (5, 3, 1, 1, "元／股"),
    ]
    return [
        TableCellFragment(
            row,
            column,
            row_span,
            column_span,
            text,
            (
                _X[column] / _WIDTH,
                _Y[row] / _HEIGHT,
                _X[column + column_span] / _WIDTH,
                _Y[row + row_span] / _HEIGHT,
            ),
            is_column_header=row < 2,
            is_row_header=column == 0 and row >= 2,
        )
        for row, column, row_span, column_span, text in specifications
    ]


def _native_fixture(
    tmp_path: Path,
    *,
    label: str = "Archive Sources",
    source_overrides: dict[tuple[int, int], str] | None = None,
) -> tuple[Path, TableFragment]:
    path = tmp_path / "arbitrary-native-table.pdf"
    cells = _source_cells(label)
    for cell in cells:
        if source_overrides and (cell.row, cell.column) in source_overrides:
            cell.text = source_overrides[cell.row, cell.column]
    with pymupdf.open() as document:
        page = document.new_page(width=_WIDTH, height=_HEIGHT)
        for cell in cells:
            assert cell.normalized_bbox is not None
            left, top, right, bottom = (
                cell.normalized_bbox[0] * _WIDTH,
                cell.normalized_bbox[1] * _HEIGHT,
                cell.normalized_bbox[2] * _WIDTH,
                cell.normalized_bbox[3] * _HEIGHT,
            )
            page.draw_rect((left, top, right, bottom))
            lines = cell.text.splitlines()
            text_top = top + (bottom - top - len(lines) * 12) / 2 + 10
            for index, line in enumerate(lines):
                page.insert_text(
                    (left + 8, text_top + index * 12),
                    line,
                    fontsize=10,
                    fontname="china-s" if any(ord(char) > 127 for char in line) else "helv",
                )
        document.save(path)
    with pymupdf.open(path) as document:
        tables = document[0].find_tables(strategy="lines_strict").tables
        assert len(tables) == 1
        table = tables[0]
        assert (table.row_count, table.col_count) == (6, 4)
        rows = [[text or "" for text in row] for row in table.extract()]
        assert table.rows[0].cells[1] == (_X[1], _Y[0], _X[3], _Y[1])
        assert table.rows[2].cells[0] == (_X[0], _Y[2], _X[1], _Y[5])
        assert table.rows[3].cells[0] is None
        assert table.rows[4].cells[0] is None
        for cell in cells:
            assert _compact(rows[cell.row][cell.column]) == _compact(cell.text)
            # Expectations always use the text independently extracted from
            # the actual vector source, including its native line boundaries.
            cell.text = rows[cell.row][cell.column]
    markdown = render_gfm_rows(rows)
    return path, TableFragment(
        fragment_id="p1_t1",
        page_number=1,
        ordinal=1,
        normalized_bbox=(_X[0] / _WIDTH, _Y[0] / _HEIGHT, _X[-1] / _WIDTH, _Y[-1] / _HEIGHT),
        num_rows=6,
        num_cols=4,
        rows=rows,
        column_boundaries=[value / _WIDTH for value in _X],
        markdown=markdown,
        rendered=f"Before table\n\n{markdown}\n\nAfter table",
        has_column_header=True,
        caption="Independent source observations",
        unit_text="元／股",
        cells=cells,
    )


def _cell(fragment: TableFragment, row: int, column: int) -> TableCellFragment:
    return next(cell for cell in fragment.cells if (cell.row, cell.column) == (row, column))


def _refresh(fragment: TableFragment) -> None:
    fragment.markdown = render_gfm_rows(fragment.rows)
    fragment.rendered = f"Before table\n\n{fragment.markdown}\n\nAfter table"


def _replace(fragment: TableFragment, row: int, column: int, text: str) -> None:
    _cell(fragment, row, column).text = text
    fragment.rows[row][column] = text
    _refresh(fragment)


def _remove(fragment: TableFragment, row: int, column: int) -> None:
    fragment.cells.remove(_cell(fragment, row, column))
    fragment.rows[row][column] = ""
    _refresh(fragment)


def _insert_spurious_model_row(fragment: TableFragment) -> None:
    fragment.rows.insert(3, ["" for _ in range(fragment.num_cols)])
    fragment.num_rows += 1
    for cell in fragment.cells:
        if cell.row >= 3:
            cell.row += 1
        elif cell.row <= 2 and cell.row + cell.row_span >= 3:
            cell.row_span += 1
    _refresh(fragment)


def _assert_rendered_and_provenance(
    fragment: TableFragment, row: int, column: int, previous_text: str | None, source_text: str
) -> None:
    assert fragment.markdown == render_gfm_rows(fragment.rows)
    assert fragment.rendered == f"Before table\n\n{fragment.markdown}\n\nAfter table"
    assert fragment.cell_evidence[row][column] == {
        "docling": previous_text,
        "native": source_text,
        "final": source_text,
    }
    table = DocumentIRService._table(fragment)
    result_cell = next(cell for cell in table.cells if (cell.row, cell.column) == (row, column))
    assert result_cell.provenance.selected_source is not None
    assert result_cell.provenance.selected_source.value == "native"
    assert result_cell.text == source_text
    assert table.source_units == [1]


@pytest.mark.parametrize("anchor", [(2, 0), (0, 1)], ids=["rowspan", "colspan"])
def test_existing_empty_merged_cell_is_filled_without_losing_flags(
    tmp_path: Path, anchor: tuple[int, int]
) -> None:
    path, fragment = _native_fixture(tmp_path)
    original = deepcopy(fragment)
    row, column = anchor
    expected = deepcopy(_cell(fragment, row, column))
    _replace(fragment, row, column, "")

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    assert _cell(fragment, row, column) == expected
    assert fragment.rows == original.rows
    assert fragment.header_row_indices == (0, 1)
    assert fragment.unit_text == "元／股"
    _assert_rendered_and_provenance(fragment, row, column, "", expected.text)


def _misanchor(fragment: TableFragment, origin: tuple[int, int], target: tuple[int, int]) -> None:
    """Keep recognition geometry while corrupting only its logical assignment."""
    cell = _cell(fragment, *origin)
    fragment.cells.remove(_cell(fragment, *target))
    fragment.rows[origin[0]][origin[1]] = ""
    fragment.rows[target[0]][target[1]] = cell.text
    cell.row, cell.column = target
    _refresh(fragment)


@pytest.mark.parametrize(
    ("origin", "target"),
    [((2, 1), (2, 3)), ((3, 1), (4, 1)), ((5, 0), (5, 1))],
)
def test_same_grid_wrong_row_or_column_anchor_uses_unique_native_geometry(
    tmp_path: Path, origin: tuple[int, int], target: tuple[int, int],
) -> None:
    path, fragment = _native_fixture(tmp_path, source_overrides={target: ""})
    source_rows = deepcopy(fragment.rows)
    original_cell = deepcopy(_cell(fragment, *origin))
    _misanchor(fragment, origin, target)
    assert (fragment.num_rows, fragment.num_cols) == (6, 4)

    assert restore_missing_native_merged_cells(path, [fragment])

    assert fragment.rows == source_rows
    restored = _cell(fragment, *origin)
    assert (restored.is_column_header, restored.is_row_header) == (
        original_cell.is_column_header, original_cell.is_row_header,
    )
    assert _cell(fragment, *target).text == ""
    assert fragment.cell_evidence[origin[0]][origin[1]] == {
        "docling": original_cell.text, "native": original_cell.text, "final": original_cell.text,
    }
    assert fragment.cell_evidence[target[0]][target[1]]["final"] == ""
    table = DocumentIRService._table(fragment)
    ir_cell = next(cell for cell in table.cells if (cell.row, cell.column) == origin)
    assert ir_cell.text == original_cell.text
    assert ir_cell.provenance.selected_source is not None
    assert "native" in {source.value for source in ir_cell.provenance.supporting_sources}
    assert table.unit_text == "元／股" and table.source_units == [1]
    assert fragment.markdown == render_gfm_rows(source_rows)


@pytest.mark.parametrize("unsupported", ["99.99", "Unobserved claim"])
def test_same_grid_wrong_anchor_with_unsupported_text_never_rewrites_any_cell(
    tmp_path: Path, unsupported: str,
) -> None:
    path, fragment = _native_fixture(tmp_path, source_overrides={(2, 3): ""})
    _replace(fragment, 2, 1, unsupported)
    _misanchor(fragment, (2, 1), (2, 3))
    before = asdict(fragment)
    diagnostics: list[dict] = []

    assert restore_missing_native_merged_cells(path, [fragment], diagnostics) == {}

    assert asdict(fragment) == before
    assert diagnostics == [{
        "fragment_id": "p1_t1", "page_number": 1, "unresolved_cells": 1,
        "reasons": ["native_grid_alignment_unproved"],
    }]


def test_ambiguous_native_geometry_does_not_relocate_or_drop_recognized_candidate(
    tmp_path: Path,
) -> None:
    path, fragment = _native_fixture(tmp_path, source_overrides={(2, 3): ""})
    _misanchor(fragment, (2, 1), (2, 3))
    with pymupdf.open(path) as document:
        characters = next(
            span["chars"]
            for block in document[0].get_text("rawdict")["blocks"]
            for line in block.get("lines", []) for span in line["spans"]
            if "".join(character["c"] for character in span.get("chars", [])) == "12.50"
        )
    cutoff = (characters[1]["bbox"][2] + characters[2]["bbox"][0]) / 2
    candidate = _cell(fragment, 2, 3)
    candidate.normalized_bbox = (
        cutoff / _WIDTH, _Y[2] / _HEIGHT, _X[3] / _WIDTH, _Y[3] / _HEIGHT,
    )
    original_candidate = deepcopy(candidate)
    before = asdict(fragment)
    diagnostics: list[dict] = []

    assert restore_missing_native_merged_cells(path, [fragment], diagnostics) == {}

    # This box straddles two source cells but owns only the suffix of 12.50.
    # Neighbouring characters cannot establish ownership of the full number.
    assert asdict(fragment) == before
    assert _cell(fragment, 2, 3) == original_candidate
    assert fragment.rows[2][3] == original_candidate.text
    assert any("native_grid_alignment_unproved" in record["reasons"] for record in diagnostics)


@pytest.mark.parametrize(
    ("label", "partial"),
    [
        ("Archive Sources", "Arc Sources"),
        ("Evidence Category 7", "Evidence Cat 7"),
        ("任意来源标签", "任意标签"),
        ("來源 A と資料 B", "來源 A 資料 B"),
    ],
    ids=["latin", "unchanged-number", "cjk", "mixed-language"],
)
def test_literal_deletion_partial_text_uses_source_complete_label(
    tmp_path: Path, label: str, partial: str
) -> None:
    path, fragment = _native_fixture(tmp_path, label=label)
    expected = _cell(fragment, 2, 0).text
    original_rows = deepcopy(fragment.rows)
    _replace(fragment, 2, 0, partial)

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    assert _cell(fragment, 2, 0).text == expected
    assert (_cell(fragment, 2, 0).row_span, _cell(fragment, 2, 0).column_span) == (3, 1)
    assert fragment.rows == original_rows
    _assert_rendered_and_provenance(fragment, 2, 0, partial, expected)


def test_wrapped_native_label_recovers_partial_text_with_exact_source_lines(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path, label="Archive\nSource\nGroups")
    expected = _cell(fragment, 2, 0).text
    assert expected == "Archive\nSource\nGroups"
    _replace(fragment, 2, 0, "Archive Groups")

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    assert fragment.rows[2][0] == expected
    assert fragment.markdown.count("Archive Source Groups") == 1
    _assert_rendered_and_provenance(fragment, 2, 0, "Archive Groups", expected)


@pytest.mark.parametrize("anchor", [(2, 0), (0, 1)], ids=["rowspan", "colspan"])
def test_empty_model_subcells_reconsolidate_into_the_native_merged_rectangle(
    tmp_path: Path, anchor: tuple[int, int]
) -> None:
    path, fragment = _native_fixture(tmp_path)
    original = deepcopy(fragment)
    row, column = anchor
    expected = deepcopy(_cell(fragment, row, column))
    _remove(fragment, row, column)
    covered = {
        (r, c)
        for r in range(expected.row, expected.row + expected.row_span)
        for c in range(expected.column, expected.column + expected.column_span)
    }
    for r, c in sorted(covered):
        fragment.cells.append(
            TableCellFragment(
                r,
                c,
                1,
                1,
                "",
                (_X[c] / _WIDTH, _Y[r] / _HEIGHT, _X[c + 1] / _WIDTH, _Y[r + 1] / _HEIGHT),
                is_column_header=expected.is_column_header,
                is_row_header=expected.is_row_header,
            )
        )

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    assert _cell(fragment, row, column) == expected
    assert sum((cell.row, cell.column) in covered for cell in fragment.cells) == 1
    assert fragment.rows == original.rows
    assert fragment.header_row_indices == (0, 1)


def test_complete_label_split_across_model_subcells_is_reanchored_once(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path, label="Archive\nSource\nGroups")
    original = deepcopy(fragment)
    expected = deepcopy(_cell(fragment, 2, 0))
    _remove(fragment, 2, 0)
    for row, text in zip((2, 3, 4), ("Archive", "Source", "Groups"), strict=True):
        fragment.cells.append(
            TableCellFragment(
                row,
                0,
                1,
                1,
                text,
                (_X[0] / _WIDTH, _Y[row] / _HEIGHT, _X[1] / _WIDTH, _Y[row + 1] / _HEIGHT),
                is_row_header=True,
            )
        )
        fragment.rows[row][0] = text
    _refresh(fragment)

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    assert _cell(fragment, 2, 0) == expected
    assert fragment.rows == original.rows
    assert not any(cell.column == 0 and cell.row in (3, 4) for cell in fragment.cells)
    assert fragment.markdown.count("Archive Source Groups") == 1


def test_multiple_missing_merged_and_normal_cells_are_recovered_together(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path, label="Arbitrary Storage Groups")
    original = deepcopy(fragment)
    for row, column in [(2, 0), (0, 1), (3, 1)]:
        _replace(fragment, row, column, "")
    _remove(fragment, 4, 2)
    _remove(fragment, 4, 3)

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 5}

    assert fragment.rows == original.rows
    assert sorted(fragment.cells, key=lambda cell: (cell.row, cell.column)) == sorted(
        original.cells, key=lambda cell: (cell.row, cell.column)
    )
    assert fragment.unit_text == "元／股"
    assert fragment.rows[4][3] == "元／股"
    _assert_rendered_and_provenance(fragment, 4, 2, None, original.rows[4][2])


@pytest.mark.parametrize(
    ("anchor", "conflict"),
    [
        ((2, 2), "1.25"),
        ((3, 2), "0"),
        ((3, 2), "00"),
        ((4, 2), "2.5"),
        ((4, 2), "3.50"),
        ((2, 0), "Different Source"),
    ],
    ids=[
        "lost-negative-sign",
        "lost-decimal-zero",
        "lost-dot",
        "lost-trailing-zero",
        "changed-digit",
        "changed-words",
    ],
)
def test_present_sign_digit_or_word_conflict_is_local_and_never_overwritten(
    tmp_path: Path, anchor: tuple[int, int], conflict: str
) -> None:
    path, fragment = _native_fixture(tmp_path)
    row, column = anchor
    _replace(fragment, row, column, conflict)
    _remove(fragment, 4, 3)
    conflicted_cell = deepcopy(_cell(fragment, row, column))
    untouched = {
        (cell.row, cell.column): deepcopy(cell)
        for cell in fragment.cells
        if (cell.row, cell.column) != (4, 3)
    }

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    assert _cell(fragment, row, column) == conflicted_cell
    assert fragment.rows[row][column] == conflict
    assert fragment.rows[4][3] == "元／股"
    assert all(_cell(fragment, *position) == cell for position, cell in untouched.items())


def test_nonempty_conflicting_subcell_blocks_only_its_merged_rectangle(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path)
    _remove(fragment, 2, 0)
    fragment.cells.append(
        TableCellFragment(
            3,
            0,
            1,
            1,
            "Unrelated claim",
            (_X[0] / _WIDTH, _Y[3] / _HEIGHT, _X[1] / _WIDTH, _Y[4] / _HEIGHT),
        )
    )
    fragment.rows[3][0] = "Unrelated claim"
    _replace(fragment, 0, 1, "")
    source_header = "Observed Inputs"

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    assert fragment.rows[2][0] == ""
    assert fragment.rows[3][0] == "Unrelated claim"
    assert fragment.rows[0][1] == source_header


def test_correct_cells_spacing_and_multilevel_headers_are_preserved_on_other_repair(
    tmp_path: Path,
) -> None:
    path, fragment = _native_fixture(tmp_path)
    _replace(fragment, 2, 2, "- 1.25")
    _remove(fragment, 4, 3)
    correct_cells = deepcopy(fragment.cells)
    original_header = deepcopy(fragment.rows[:2])

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    assert all(_cell(fragment, cell.row, cell.column) == cell for cell in correct_cells)
    assert fragment.rows[:2] == original_header
    assert fragment.header_row_indices == (0, 1)
    assert fragment.rows[2][2] == "- 1.25"
    assert fragment.caption == "Independent source observations"
    assert fragment.unit_text == "元／股"


def test_general_recovery_is_idempotent_and_does_not_duplicate_native_text(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path, label="Independent Inventory")
    _replace(fragment, 2, 0, "Inventory")
    _replace(fragment, 0, 1, "")
    _remove(fragment, 4, 3)

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 3}
    after = asdict(fragment)
    assert restore_missing_native_merged_cells(path, [fragment]) == {}

    assert asdict(fragment) == after
    assert fragment.markdown.count("Independent Inventory") == 1


def test_empty_source_cells_are_not_filled_from_neighbouring_labels(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path, label="")
    before = asdict(fragment)

    assert restore_missing_native_merged_cells(path, [fragment]) == {}

    assert asdict(fragment) == before


def test_spurious_model_row_is_removed_only_using_the_complete_native_grid(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path, label="Independent Archive Groups")
    original = deepcopy(fragment)
    _replace(fragment, 2, 0, "Archive Groups")
    # Simulate a detector adding a row boundary through the middle of a
    # source row. Existing native cell rectangles are retained, providing
    # independent proof that this seven-row topology is incorrect.
    _insert_spurious_model_row(fragment)

    assert restore_missing_native_merged_cells(path, [fragment])

    assert fragment.num_rows == 6
    assert fragment.rows == original.rows
    assert sorted(fragment.cells, key=lambda cell: (cell.row, cell.column)) == sorted(
        original.cells, key=lambda cell: (cell.row, cell.column)
    )
    assert fragment.header_row_indices == (0, 1)
    assert fragment.unit_text == "元／股"
    assert fragment.markdown == original.markdown
    table = DocumentIRService._table(fragment)
    assert table.source_units == [1]


def test_different_grid_dimensions_with_a_conflicting_cell_do_not_regrid(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path)
    _replace(fragment, 2, 2, "1.25")
    _insert_spurious_model_row(fragment)
    before = asdict(fragment)

    assert restore_missing_native_merged_cells(path, [fragment]) == {}

    assert asdict(fragment) == before


def test_source_proved_invalid_overlap_can_rebuild_the_complete_grid(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path)
    original = deepcopy(fragment)
    fragment.cells.append(deepcopy(_cell(fragment, 2, 0)))
    fragment.valid = False
    fragment.invalid_reasons = ["overlapping_cells"]

    assert restore_missing_native_merged_cells(path, [fragment])

    assert fragment.valid
    assert fragment.invalid_reasons == []
    assert fragment.rows == original.rows
    assert sorted(fragment.cells, key=lambda cell: (cell.row, cell.column)) == sorted(
        original.cells, key=lambda cell: (cell.row, cell.column)
    )
    assert fragment.header_row_indices == (0, 1)


def test_regrid_never_drops_a_model_caption_outside_the_source_grid(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path)
    _insert_spurious_model_row(fragment)
    # The text really exists in the PDF, but outside the drawn table. A model
    # incorrectly including that caption must not authorize dropping it while
    # rebuilding the nearby table grid.
    caption = "Source notes outside the table"
    with pymupdf.open(path) as document:
        document[0].insert_text((80, 60), caption, fontsize=10)
        document.saveIncr()
    model = _cell(fragment, 0, 0)
    model.text = caption
    model.normalized_bbox = (75 / _WIDTH, 45 / _HEIGHT, 300 / _WIDTH, 65 / _HEIGHT)
    fragment.rows[0][0] = caption
    _refresh(fragment)
    before = asdict(fragment)

    assert restore_missing_native_merged_cells(path, [fragment]) == {}

    assert asdict(fragment) == before


@pytest.mark.parametrize("proved_geometry", [True, False], ids=["source-owned", "unproved"])
def test_propagated_duplicate_label_requires_each_copy_to_own_the_full_source_text(
    tmp_path: Path, proved_geometry: bool
) -> None:
    path, fragment = _native_fixture(tmp_path, label="Independent Sources")
    original = deepcopy(fragment)
    source = deepcopy(_cell(fragment, 2, 0))
    _remove(fragment, 2, 0)
    for row in (2, 3, 4):
        bbox = (
            source.normalized_bbox
            if proved_geometry
            else (_X[0] / _WIDTH, _Y[row] / _HEIGHT, _X[1] / _WIDTH, _Y[row + 1] / _HEIGHT)
        )
        fragment.cells.append(TableCellFragment(row, 0, 1, 1, source.text, bbox, False, True))
        fragment.rows[row][0] = source.text
    _refresh(fragment)
    before = asdict(fragment)

    result = restore_missing_native_merged_cells(path, [fragment])

    if proved_geometry:
        assert result == {"p1_t1": 1}
        assert fragment.rows == original.rows
        assert _cell(fragment, 2, 0) == source
        assert sum(cell.column == 0 and cell.row in (2, 3, 4) for cell in fragment.cells) == 1
        assert fragment.markdown.count("Independent Sources") == 1
    else:
        assert result == {}
        assert asdict(fragment) == before


def test_nonempty_matrix_text_without_an_explicit_cell_prevents_regrid(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path)
    _insert_spurious_model_row(fragment)
    fragment.rows[3][1] = "Unrepresented source claim"
    _refresh(fragment)
    before = asdict(fragment)

    assert restore_missing_native_merged_cells(path, [fragment]) == {}

    assert asdict(fragment) == before


def test_matrix_text_conflicting_with_its_explicit_cell_prevents_regrid(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path)
    _insert_spurious_model_row(fragment)
    fragment.rows[2][0] = "Unrepresented conflicting claim"
    _refresh(fragment)
    before = asdict(fragment)

    assert restore_missing_native_merged_cells(path, [fragment]) == {}

    assert asdict(fragment) == before


def test_reordered_present_label_is_a_conflict_during_source_grid_rebuild(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path, label="Archive Sources")
    _replace(fragment, 2, 0, "Sources Archive")
    _insert_spurious_model_row(fragment)
    before = asdict(fragment)

    assert restore_missing_native_merged_cells(path, [fragment]) == {}

    assert asdict(fragment) == before


def test_local_numeric_conflict_has_diagnostics_while_a_missing_unit_is_recovered(
    tmp_path: Path,
) -> None:
    path, fragment = _native_fixture(tmp_path)
    _replace(fragment, 2, 2, "1.25")
    _remove(fragment, 4, 3)
    diagnostics: list[dict] = []

    assert restore_missing_native_merged_cells(path, [fragment], diagnostics) == {"p1_t1": 1}

    assert fragment.rows[2][2] == "1.25"
    assert fragment.rows[4][3] == "元／股"
    assert diagnostics == [
        {
            "fragment_id": "p1_t1",
            "page_number": 1,
            "unresolved_cells": 1,
            "reasons": ["native_cell_text_conflict"],
        }
    ]


@pytest.mark.parametrize(
    "source_amount", ["- 1.25", "+ 1.25", "( 1.25 )", "（ 1.25 ）", "－ 1.25", "1.25 %"]
)
@pytest.mark.parametrize("rebuild_grid", [False, True], ids=["same-grid", "rebuild-grid"])
def test_source_number_with_spaced_sign_or_accounting_parentheses_is_not_a_text_completion(
    tmp_path: Path, source_amount: str, rebuild_grid: bool
) -> None:
    path, fragment = _native_fixture(tmp_path, source_overrides={(2, 2): source_amount})
    assert _compact(fragment.rows[2][2]) == _compact(source_amount)
    _replace(fragment, 2, 2, "1.25")
    _remove(fragment, 4, 3)
    if rebuild_grid:
        _insert_spurious_model_row(fragment)
        before = asdict(fragment)

    result = restore_missing_native_merged_cells(path, [fragment])

    if rebuild_grid:
        assert result == {}
        assert asdict(fragment) == before
    else:
        assert result == {"p1_t1": 1}
        assert fragment.rows[2][2] == "1.25"
        assert fragment.rows[4][3] == "元／股"


def test_cell_bbox_crossing_a_source_rectangle_does_not_authorize_reanchoring(
    tmp_path: Path,
) -> None:
    path, fragment = _native_fixture(tmp_path)
    _remove(fragment, 2, 0)
    fragment.cells.append(
        TableCellFragment(
            2,
            0,
            1,
            1,
            "",
            (_X[0] / _WIDTH, _Y[2] / _HEIGHT, _X[2] / _WIDTH, _Y[3] / _HEIGHT),
        )
    )
    before = asdict(fragment)

    assert restore_missing_native_merged_cells(path, [fragment]) == {}

    assert asdict(fragment) == before


def _merge_model_child_headers(
    fragment: TableFragment, *, text: str = "Current Previous",
    left: float = _X[1], right: float = _X[3],
) -> TableCellFragment:
    fragment.cells.remove(_cell(fragment, 1, 1))
    fragment.cells.remove(_cell(fragment, 1, 2))
    combined = TableCellFragment(
        1, 1, 1, 2, text,
        (left / _WIDTH, _Y[1] / _HEIGHT, right / _WIDTH, _Y[2] / _HEIGHT),
        is_column_header=True,
    )
    fragment.cells.append(combined)
    fragment.rows[1][1] = text
    fragment.rows[1][2] = ""
    _refresh(fragment)
    return combined


def test_source_split_model_header_keeps_full_role_and_original_candidate(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path)
    original_rows = deepcopy(fragment.rows)
    _merge_model_child_headers(fragment)

    assert restore_missing_native_merged_cells(path, [fragment])

    assert fragment.rows == original_rows
    assert fragment.header_row_indices == (0, 1)
    table = DocumentIRService._table(fragment)
    for column, text in ((1, "Current"), (2, "Previous")):
        cell = _cell(fragment, 1, column)
        assert (cell.text, cell.column_span, cell.is_column_header, cell.is_row_header) == (
            text, 1, True, False
        )
        evidence = fragment.cell_evidence[1][column]
        assert evidence == {"docling": "Current Previous", "native": text, "final": text}
        ir_cell = next(cell for cell in table.cells if (cell.row, cell.column) == (1, column))
        assert ir_cell.is_column_header
        assert ir_cell.provenance.selected_source.value == "native"
    assert table.header_rows == [0, 1]
    assert table.unit_text == "元／股"
    assert table.source_units == [1]


def test_source_split_conflicting_model_roles_remain_unknown(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path)
    combined = _merge_model_child_headers(fragment)
    opposite_role = deepcopy(combined)
    opposite_role.is_column_header = False
    opposite_role.is_row_header = True
    fragment.cells.append(opposite_role)
    fragment.valid = False
    fragment.invalid_reasons = ["overlapping_cells"]

    assert restore_missing_native_merged_cells(path, [fragment])

    for column, text in ((1, "Current"), (2, "Previous")):
        cell = _cell(fragment, 1, column)
        assert cell.text == text
        assert not cell.is_column_header and not cell.is_row_header
        evidence = fragment.cell_evidence[1][column]
        assert "Current Previous" in evidence["docling"]
        assert evidence["native"] == evidence["final"] == text


def test_source_split_half_owned_header_glyphs_do_not_establish_full_role(tmp_path: Path) -> None:
    path, fragment = _native_fixture(tmp_path)
    with pymupdf.open(path) as document:
        characters = next(
            span["chars"]
            for block in document[0].get_text("rawdict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"]
            if "".join(character["c"] for character in span.get("chars", [])) == "Current"
        )
    center_before = (characters[2]["bbox"][0] + characters[2]["bbox"][2]) / 2
    center_after = (characters[3]["bbox"][0] + characters[3]["bbox"][2]) / 2
    # The model really owns only the suffix of Current, plus all of Previous.
    # Its header flag cannot make that partial source-word scope complete.
    cutoff = (center_before + center_after) / 2
    _merge_model_child_headers(fragment, text="rent Previous", left=cutoff)

    assert restore_missing_native_merged_cells(path, [fragment])

    current = _cell(fragment, 1, 1)
    previous = _cell(fragment, 1, 2)
    assert current.text == "Current"
    assert not current.is_column_header and not current.is_row_header
    assert previous.text == "Previous"
    assert previous.is_column_header and not previous.is_row_header
    assert fragment.cell_evidence[1][1]["native"] == "Current"
    assert fragment.cell_evidence[1][2] == {
        "docling": "rent Previous", "native": "Previous", "final": "Previous"
    }


def test_merged_recovery_clears_continuation_final_but_retains_recognition_candidates(
    tmp_path: Path,
) -> None:
    path, fragment = _native_fixture(tmp_path, label="Archive Sources")
    _replace(fragment, 2, 0, "Arc Sources")
    fragment.cell_evidence = [[{} for _ in range(fragment.num_cols)]
                              for _ in range(fragment.num_rows)]
    for row in (3, 4):
        fragment.cell_evidence[row][0] = {
            "docling": "old recognition candidate", "qwen": "alternate candidate",
            "native": "stale native view", "final": "stale final view"
        }

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    for row in (3, 4):
        assert fragment.rows[row][0] == ""
        assert fragment.cell_evidence[row][0] == {
            "docling": "old recognition candidate", "qwen": "alternate candidate",
            "native": "", "final": ""
        }
    assert not any(cell.column == 0 and cell.row in (3, 4) for cell in fragment.cells)
    assert _cell(fragment, 2, 0).row_span == 3


def test_unknown_lower_header_band_cannot_link_or_remove_lookalike_top_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_factory = _source_cells

    def flat_header_cells(label: str) -> list[TableCellFragment]:
        cells = original_factory(label)
        for cell in cells:
            if cell.row == 0 and cell.column in (0, 3):
                cell.row_span = 1
                left, top, right, _ = cell.normalized_bbox
                cell.normalized_bbox = (left, top, right, _Y[1] / _HEIGHT)
        for column in (0, 3):
            cells.append(TableCellFragment(
                1, column, 1, 1, "",
                (_X[column] / _WIDTH, _Y[1] / _HEIGHT,
                 _X[column + 1] / _WIDTH, _Y[2] / _HEIGHT),
            ))
        return cells

    monkeypatch.setitem(globals(), "_source_cells", flat_header_cells)
    recovered = []
    for page_number, words, top in ((1, ("Current", "Previous"), 344.0),
                                    (2, ("Quarter", "Prior"), 40.0)):
        monkeypatch.setitem(globals(), "_Y", tuple(top + 36 * index for index in range(7)))
        directory = tmp_path / f"page-{page_number}"
        directory.mkdir()
        path, fragment = _native_fixture(
            directory, source_overrides={(1, 1): words[0], (1, 2): words[1]}
        )
        with pymupdf.open(path) as document:
            chars_by_word = {
                "".join(character["c"] for character in span.get("chars", [])): span["chars"]
                for block in document[0].get_text("rawdict")["blocks"]
                for line in block.get("lines", []) for span in line["spans"] if span.get("chars")
            }
        first, second = chars_by_word[words[0]], chars_by_word[words[1]]

        def center(character: dict) -> float:
            return (character["bbox"][0] + character["bbox"][2]) / 2

        left = (center(first[2]) + center(first[3])) / 2
        right = (center(second[3]) + center(second[4])) / 2
        _merge_model_child_headers(
            fragment, text=f"{words[0][3:]} {words[1][:4]}", left=left, right=right
        )
        assert fragment.header_row_indices == (0, 1)

        assert restore_missing_native_merged_cells(path, [fragment])

        assert not fragment.header_scope_complete
        assert fragment.header_row_indices == ()
        assert _complete_header_signature(fragment) is None
        assert fragment.rows[1][1:3] == list(words)
        fragment.page_number = page_number
        fragment.fragment_id = f"p{page_number}_t1"
        recovered.append(fragment)

    # Their real source rectangles satisfy the normal continuation geometry;
    # only the incomplete header scope must prevent joining and deletion.
    assert recovered[0].normalized_bbox[3] >= 0.85
    assert recovered[1].normalized_bbox[1] <= 0.15
    assert recovered[0].rows[0] == recovered[1].rows[0]
    assert link_cross_page_tables(recovered) == []
    pages = [PageParseResult(page_number=fragment.page_number, backend="docling-standard",
                             content=fragment.rendered) for fragment in recovered]
    assembled = assemble_logical_tables(pages, recovered, enabled=True)
    assert assembled == {fragment.page_number: fragment.rendered for fragment in recovered}
    assert "Current" in assembled[1] and "Previous" in assembled[1]
    assert "Quarter" in assembled[2] and "Prior" in assembled[2]


def test_same_grid_merged_role_conflict_does_not_authorize_complete_header_scope(
    tmp_path: Path,
) -> None:
    path, fragment = _native_fixture(tmp_path, label="Archive Sources")
    source = deepcopy(_cell(fragment, 2, 0))
    _remove(fragment, 2, 0)
    for row, text, column_header, row_header in (
        (2, "Archive", True, False), (3, "Sources", False, True), (4, "", False, False)
    ):
        fragment.cells.append(TableCellFragment(
            row, 0, 1, 1, text, source.normalized_bbox, column_header, row_header
        ))
        fragment.rows[row][0] = text
    _refresh(fragment)

    assert restore_missing_native_merged_cells(path, [fragment]) == {"p1_t1": 1}

    merged = _cell(fragment, 2, 0)
    assert merged.text == source.text
    assert merged.row_span == 3
    assert not merged.is_column_header and not merged.is_row_header
    assert not fragment.header_scope_complete
    assert fragment.header_row_indices == ()
    assert _complete_header_signature(fragment) is None
    assert _compact(fragment.cell_evidence[2][0]["docling"]) == "ArchiveSources"
    assert fragment.cell_evidence[2][0]["native"] == fragment.cell_evidence[2][0]["final"] == source.text


def test_completely_unmapped_empty_header_cannot_look_like_complete_header_after_regrid(
    tmp_path: Path,
) -> None:
    path, fragment = _native_fixture(tmp_path)
    missing_header = _cell(fragment, 1, 1)
    missing_header.text = fragment.rows[1][1] = ""
    missing_header.normalized_bbox = None
    assert missing_header.is_column_header
    _insert_spurious_model_row(fragment)
    diagnostics: list[dict] = []

    assert restore_missing_native_merged_cells(path, [fragment], diagnostics)

    assert fragment.rows[1][1] == "Current"
    assert not _cell(fragment, 1, 1).is_column_header
    assert not fragment.header_scope_complete
    assert fragment.header_row_indices == ()
    assert _complete_header_signature(fragment) is None
    assert any("native_header_scope_unproved" in record["reasons"] for record in diagnostics)
    assert fragment.cell_evidence[1][1]["native"] == fragment.cell_evidence[1][1]["final"] == "Current"
    assert fragment.unit_text == "元／股"
