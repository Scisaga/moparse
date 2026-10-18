"""The unchanged public reader must bind each source map to its own table."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.models import PageParseResult
from app.services.export_service import ExportService
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows
from benchmark.tools.check_release import load_reader

pytestmark = pytest.mark.integration


def fragment(page: int, ordinal: int, *, multilevel: bool = False) -> TableFragment:
    rows = [["项目", "原件值（元）"], [f"原文{page}-{ordinal}", "123.40"]]
    cells = [
        TableCellFragment(row, col, 1, 1, text, is_column_header=row == 0)
        for row, values in enumerate(rows)
        for col, text in enumerate(values)
    ]
    if multilevel:
        rows = [
            ["项目", "完整期间", ""],
            ["", "金额（元）", "占比(%)"],
            [f"原文{page}-{ordinal}", "123.40", "60"],
            ["", "82.10", "40"],
        ]
        cells = [
            TableCellFragment(0, 0, 2, 1, "项目", is_column_header=True),
            TableCellFragment(0, 1, 1, 2, "完整期间", is_column_header=True),
            TableCellFragment(1, 1, 1, 1, "金额（元）", is_column_header=True),
            TableCellFragment(1, 2, 1, 1, "占比(%)", is_column_header=True),
            TableCellFragment(2, 0, 2, 1, rows[2][0]),
            *[
                TableCellFragment(row, col, 1, 1, rows[row][col])
                for row in (2, 3)
                for col in (1, 2)
            ],
        ]
    identifier = f"p{page}_t{ordinal}"
    markdown = render_gfm_rows(rows)
    return TableFragment(
        fragment_id=identifier,
        page_number=page,
        ordinal=ordinal,
        normalized_bbox=(0.1, 0.02, 0.9, 0.97),
        num_rows=len(rows),
        num_cols=len(rows[0]),
        rows=rows,
        column_boundaries=[index / len(rows[0]) for index in range(len(rows[0]) + 1)],
        markdown=markdown,
        rendered=f"<!-- table-fragment: {identifier} -->\n\n{markdown}",
        has_column_header=True,
        cells=cells,
    )


def source_map(table: TableFragment, *, logical: str | None = None, skip: int = 0) -> dict:
    return {
        "fragment": table.fragment_id,
        "page": table.page_number,
        "source_rows": f"{skip + 1}-{len(table.rows)}",
        "logical_rows": logical or f"1-{len(table.rows)}",
        "repeated_header_rows": skip,
    }


def snapshot(fragments: list[TableFragment]) -> list:
    return deepcopy(
        [
            (
                table.rows,
                [(cell.row, cell.column, cell.row_span, cell.column_span, cell.text)
                 for cell in table.cells],
            )
            for table in fragments
        ]
    )


@pytest.mark.parametrize("merge", [False, True])
def test_adjacent_standalone_tables_have_exact_public_source_scopes(merge: bool) -> None:
    first, second = fragment(7, 1), fragment(7, 2, multilevel=True)
    fragments = [first, second]
    before = snapshot(fragments)
    pages = [PageParseResult(page_number=7, content=first.rendered + "\n\n" + second.rendered)]
    markdown, _ = ExportService().join_document(
        pages, preserve_page_breaks=True, table_fragments=fragments, merge_cross_page_tables=merge
    )
    tables = load_reader().public_tables(markdown)

    assert [table["id"] for table in tables] == [first.fragment_id, second.fragment_id]
    assert [table["sources"] for table in tables] == [[source_map(first)], [source_map(second)]]
    assert [table["rows"] for table in tables] == [first.rows, second.rows]
    assert tables[1]["meta"]["header_scope_rows"] == [0, 1]
    assert tables[1]["meta"]["spans"] == [[0, 0, 2, 1], [0, 1, 1, 2], [2, 0, 2, 1]]
    assert snapshot(fragments) == before
    for table in fragments:
        assert markdown.index(f"<!-- table-fragment: {table.fragment_id} -->") < markdown.index(
            f"<!-- table-source: {table.fragment_id};"
        ) < markdown.index(table._structure_marker)


def test_standalone_after_logical_table_cannot_leak_its_map_into_the_logical_scope() -> None:
    first, continuation = fragment(6, 1, multilevel=True), fragment(7, 1, multilevel=True)
    following = fragment(7, 2)
    fragments = [first, continuation, following]
    before = snapshot(fragments)
    pages = [
        PageParseResult(page_number=6, content=first.rendered),
        PageParseResult(page_number=7, content=continuation.rendered + "\n\n" + following.rendered),
    ]
    markdown, _ = ExportService().join_document(
        pages, preserve_page_breaks=True, table_fragments=fragments, merge_cross_page_tables=True
    )
    tables = load_reader().public_tables(markdown)

    assert len(tables) == 2
    logical, standalone = tables
    assert logical["id"] == f"table_{first.fragment_id}_{continuation.fragment_id}"
    assert logical["sources"] == [
        source_map(first),
        source_map(continuation, logical="5-6", skip=2),
    ]
    assert logical["rows"] == first.rows + continuation.rows[2:]
    assert logical["meta"]["header_scope_rows"] == [0, 1]
    assert logical["meta"]["spans"] == [
        [0, 0, 2, 1], [0, 1, 1, 2], [2, 0, 2, 1], [4, 0, 2, 1]
    ]
    assert standalone["id"] == following.fragment_id
    assert standalone["sources"] == [source_map(following)]
    assert standalone["rows"] == following.rows
    assert snapshot(fragments) == before
