"""Recover omitted merged cells only from independent native PDF grid evidence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pymupdf
import pytest

from app.services.ir_service import DocumentIRService
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows

_X = (50.0, 200.0, 350.0, 500.0)
_Y = (100.0, 124.0, 148.0, 172.0, 196.0, 220.0)
_ROWS = [
    ["Project", "Type", "Amount"],
    ["", "2011", "101.25"],
    ["", "2015", "-202.50"],
    ["", "2016", "303.75"],
    ["Total", "-", "202.50"],
]


def _native_pdf(tmp_path: Path, *, label: str = "Funding History") -> Path:
    path = tmp_path / "native-merged-cell.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        for x in _X:
            page.draw_line((x, _Y[0]), (x, _Y[-1]))
        for index, y in enumerate(_Y):
            # The left cell spans rows 1, 2 and 3; its label is vertically centered.
            left = _X[1] if index in (2, 3) else _X[0]
            page.draw_line((left, y), (_X[-1], y))
        for row, values in enumerate(_ROWS):
            for column, text in enumerate(values):
                if text:
                    page.insert_text((_X[column] + 8, _Y[row] + 16), text, fontsize=10)
        if label:
            for line, text in enumerate(label.splitlines()):
                page.insert_text((70, 157 + line * 12), text, fontsize=10)
        document.save(path)
    # Assert that the independent source really contains the intended merged geometry.
    with pymupdf.open(path) as document:
        tables = document[0].find_tables().tables
        assert len(tables) == 1
        assert (tables[0].row_count, tables[0].col_count) == (5, 3)
        assert tables[0].rows[1].cells[0] == (50.0, 124.0, 200.0, 196.0)
        assert tables[0].rows[2].cells[0] is None
        assert tables[0].rows[3].cells[0] is None
    return path


def _fragment() -> TableFragment:
    rows = deepcopy(_ROWS)
    markdown = render_gfm_rows(rows)
    cells = [
        TableCellFragment(
            row=row,
            column=column,
            row_span=1,
            column_span=1,
            text=text,
            normalized_bbox=(
                _X[column] / 600,
                _Y[row] / 800,
                _X[column + 1] / 600,
                _Y[row + 1] / 800,
            ),
            is_column_header=row == 0,
        )
        for row, values in enumerate(rows)
        for column, text in enumerate(values)
        if not (column == 0 and row in (1, 2, 3))
    ]
    return TableFragment(
        fragment_id="p1_t1",
        page_number=1,
        ordinal=1,
        normalized_bbox=(_X[0] / 600, _Y[0] / 800, _X[-1] / 600, _Y[-1] / 800),
        num_rows=5,
        num_cols=3,
        rows=rows,
        column_boundaries=[x / 600 for x in _X],
        markdown=markdown,
        rendered=f"<!-- table-fragment: p1_t1 -->\n\n{markdown}",
        has_column_header=True,
        cells=cells,
    )


def _restore(path: Path, fragment: TableFragment) -> dict[str, int]:
    from app.services.native_table_service import restore_missing_native_merged_cells

    return restore_missing_native_merged_cells(path, [fragment])


def _sync_text(fragment: TableFragment, row: int, column: int, text: str) -> None:
    fragment.rows[row][column] = text
    next(cell for cell in fragment.cells if (cell.row, cell.column) == (row, column)).text = text
    fragment.markdown = render_gfm_rows(fragment.rows)
    fragment.rendered = f"<!-- table-fragment: {fragment.fragment_id} -->\n\n{fragment.markdown}"


@pytest.mark.parametrize("label", ["Funding History", "Funding\nHistory"])
def test_omitted_native_merged_cell_is_recovered_at_span_anchor(tmp_path: Path, label: str) -> None:
    path = _native_pdf(tmp_path, label=label)
    fragment = _fragment()
    original_rows = deepcopy(fragment.rows)

    assert _restore(path, fragment) == {"p1_t1": 1}

    recovered = next(cell for cell in fragment.cells if (cell.row, cell.column) == (1, 0))
    assert (recovered.row_span, recovered.column_span) == (3, 1)
    assert recovered.text == label
    assert recovered.normalized_bbox == pytest.approx((50 / 600, 124 / 800, 200 / 600, 196 / 800))
    assert not recovered.is_column_header
    assert not recovered.is_row_header
    assert fragment.rows[1][0] == label
    assert fragment.rows[2][0] == fragment.rows[3][0] == ""
    original_rows[1][0] = label
    assert fragment.rows == original_rows
    assert fragment.markdown == render_gfm_rows(fragment.rows)
    assert fragment.rendered == f"<!-- table-fragment: p1_t1 -->\n\n{fragment.markdown}"
    assert fragment.cell_evidence[1][0] == {"docling": None, "native": label, "final": label}
    # Adjacent years and values cannot be copied into the missing left cell.
    assert "2011" not in recovered.text
    assert "-202.50" not in recovered.text
    assert fragment.markdown.count("Funding") == 1
    assert fragment.markdown.count("-202.50") == 1

    table = DocumentIRService._table(fragment)
    ir_cell = next(cell for cell in table.cells if (cell.row, cell.column) == (1, 0))
    assert (ir_cell.text, ir_cell.row_span, ir_cell.column_span) == (label, 3, 1)
    assert ir_cell.provenance.selected_source.value == "native"
    assert table.source_units == [1]
    assert not any(cell.column == 0 and cell.row in (2, 3) for cell in table.cells)


def test_truly_empty_native_merged_cell_is_preserved(tmp_path: Path) -> None:
    path = _native_pdf(tmp_path, label="")
    fragment = _fragment()
    before = asdict(fragment)

    assert _restore(path, fragment) == {}
    assert asdict(fragment) == before


@pytest.mark.parametrize("existing_text", ["Funding History", "Conflicting label"])
def test_existing_model_merged_cell_is_preserved(tmp_path: Path, existing_text: str) -> None:
    path = _native_pdf(tmp_path)
    fragment = _fragment()
    fragment.cells.append(TableCellFragment(1, 0, 3, 1, existing_text))
    fragment.rows[1][0] = existing_text
    fragment.markdown = render_gfm_rows(fragment.rows)
    fragment.rendered = f"<!-- table-fragment: p1_t1 -->\n\n{fragment.markdown}"
    before = asdict(fragment)

    assert _restore(path, fragment) == {}
    assert asdict(fragment) == before


def test_nonempty_anchor_without_explicit_cell_is_preserved(tmp_path: Path) -> None:
    path = _native_pdf(tmp_path)
    fragment = _fragment()
    fragment.rows[1][0] = "Existing label"
    before = asdict(fragment)

    assert _restore(path, fragment) == {}
    assert asdict(fragment) == before


def test_empty_subcell_inside_proved_merged_span_is_reconsolidated(tmp_path: Path) -> None:
    path = _native_pdf(tmp_path)
    fragment = _fragment()
    fragment.cells.append(TableCellFragment(2, 0, 1, 1, ""))
    assert _restore(path, fragment) == {"p1_t1": 1}
    recovered = next(cell for cell in fragment.cells if (cell.row, cell.column) == (1, 0))
    assert (recovered.text, recovered.row_span, recovered.column_span) == ("Funding History", 3, 1)
    assert not any(cell.row == 2 and cell.column == 0 for cell in fragment.cells)


@pytest.mark.parametrize("wrong_text", ["202.50", "Different value"])
def test_native_model_conflict_is_preserved_while_an_independent_omission_recovers(
    tmp_path: Path, wrong_text: str
) -> None:
    path = _native_pdf(tmp_path)
    fragment = _fragment()
    # Source is -202.50. Removing its sign must remain a conflict after normalization.
    _sync_text(fragment, 2, 2, wrong_text)
    conflicted = deepcopy(next(cell for cell in fragment.cells if (cell.row, cell.column) == (2, 2)))
    assert _restore(path, fragment) == {"p1_t1": 1}
    assert next(cell for cell in fragment.cells if (cell.row, cell.column) == (2, 2)) == conflicted
    assert fragment.rows[2][2] == wrong_text
    assert fragment.rows[1][0] == "Funding History"


def test_layout_whitespace_differences_allow_recovery(tmp_path: Path) -> None:
    path = _native_pdf(tmp_path)
    fragment = _fragment()
    _sync_text(fragment, 2, 2, "- 202.50")

    assert _restore(path, fragment) == {"p1_t1": 1}
    assert fragment.rows[2][2] == "- 202.50"
    assert fragment.rows[1][0] == "Funding History"


def test_ambiguous_matching_native_grids_do_not_authorize_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _native_pdf(tmp_path)
    fragment = _fragment()
    before = asdict(fragment)
    original = pymupdf.Page.find_tables

    def ambiguous_tables(page: pymupdf.Page, *args: object, **kwargs: object) -> object:
        finder = original(page, *args, **kwargs)
        finder.tables = [*finder.tables, *finder.tables]
        return finder

    monkeypatch.setattr(pymupdf.Page, "find_tables", ambiguous_tables)

    assert _restore(path, fragment) == {}
    assert asdict(fragment) == before


def test_recovery_is_idempotent(tmp_path: Path) -> None:
    path = _native_pdf(tmp_path)
    fragment = _fragment()

    assert _restore(path, fragment) == {"p1_t1": 1}
    after = asdict(fragment)
    assert _restore(path, fragment) == {}
    assert asdict(fragment) == after
