"""Public GFM retains only source-owned table structure, without text rewriting."""

from __future__ import annotations

import json
import re
from copy import deepcopy

import pytest

from app.models import PageParseResult
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    assemble_logical_tables,
    render_gfm_rows,
)

_MARKER = re.compile(r"<!-- table-structure: (.*?) -->")


def _metadata(markdown: str) -> list[dict[str, object]]:
    return [json.loads(match[1]) for match in _MARKER.finditer(markdown)]


def _visible_table(markdown: str) -> str:
    return "\n".join(line for line in markdown.splitlines() if line.startswith("|"))


def _fragment(
    page: int,
    rows: list[list[str]],
    cells: list[TableCellFragment],
    *,
    has_header: bool = True,
) -> TableFragment:
    markdown = render_gfm_rows(rows)
    fragment_id = f"p{page}_t1"
    columns = len(rows[0])
    return TableFragment(
        fragment_id=fragment_id,
        page_number=page,
        ordinal=1,
        normalized_bbox=(0.1, 0.02, 0.9, 0.97),
        num_rows=len(rows),
        num_cols=columns,
        rows=deepcopy(rows),
        column_boundaries=[column / columns for column in range(columns + 1)],
        markdown=markdown,
        rendered=f"<!-- table-fragment: {fragment_id} -->\n\n{markdown}",
        has_column_header=has_header,
        cells=deepcopy(cells),
    )


def _multilevel(page: int, label: str) -> TableFragment:
    rows = [
        ["项目", "本期", ""],
        ["", "金额", "占比"],
        [label, "100.00", "60%"],
        ["", "80.00", "40%"],
    ]
    cells = [
        TableCellFragment(0, 0, 2, 1, "项目", is_column_header=True),
        TableCellFragment(0, 1, 1, 2, "本期", is_column_header=True),
        TableCellFragment(1, 1, 1, 1, "金额", is_column_header=True),
        TableCellFragment(1, 2, 1, 1, "占比", is_column_header=True),
        TableCellFragment(2, 0, 2, 1, label),
        *[
            TableCellFragment(row, column, 1, 1, rows[row][column])
            for row in (2, 3)
            for column in (1, 2)
        ],
    ]
    return _fragment(page, rows, cells)


def test_source_multilevel_headers_and_spans_are_visible_without_coordinates() -> None:
    fragment = _multilevel(3, "原始分组")
    metadata = _metadata(fragment.rendered)[0]

    assert metadata == {
        "version": 1,
        "table_id": "p3_t1",
        "source_pages": [3],
        "num_rows": 4,
        "num_cols": 3,
        "encoding": "anchor_and_blanks",
        "structure_valid": True,
        "header_rows": [0, 1],
        "header_scope_rows": [0, 1],
        "header_scope_complete": True,
        "spans": [[0, 0, 2, 1], [0, 1, 1, 2], [2, 0, 2, 1]],
    }
    assert _visible_table(fragment.rendered) == fragment.markdown == render_gfm_rows(fragment.rows)
    assert not {"bbox", "cells", "text", "unit_text", "period"} & metadata.keys()
    assert "原始分组" not in json.dumps(metadata, ensure_ascii=False)


def test_first_row_hint_without_source_cells_never_invents_a_header_or_spans() -> None:
    fragment = _fragment(1, [["项目", "本期"], ["营业收入", "100"]], [])
    metadata = _metadata(fragment.rendered)[0]

    assert metadata["encoding"] == "unknown"
    assert metadata["structure_valid"] is False
    assert metadata["header_rows"] is None
    assert metadata["header_scope_rows"] is None
    assert metadata["header_scope_complete"] is False
    assert metadata["spans"] is None
    assert _visible_table(fragment.rendered) == fragment.markdown


def test_nonleading_source_header_flag_is_preserved_as_observed_with_unknown_scope() -> None:
    rows = [["说明", "原文"], ["项目", "本期"], ["甲", "12"]]
    cells = [
        TableCellFragment(row, column, 1, 1, text, is_column_header=row == 1)
        for row, values in enumerate(rows)
        for column, text in enumerate(values)
    ]
    fragment = _fragment(1, rows, cells)
    metadata = _metadata(fragment.rendered)[0]

    assert metadata["structure_valid"] is True
    assert metadata["header_rows"] == [1]
    assert metadata["header_scope_rows"] is None
    assert metadata["header_scope_complete"] is False
    assert fragment.header_row_indices == ()


@pytest.mark.parametrize("damage", ["overlap", "out_of_bounds", "hidden_text"])
def test_invalid_source_geometry_is_unknown_and_never_claims_aligned_spans(damage: str) -> None:
    source = _multilevel(1, "原始分组")
    rows, cells = deepcopy(source.rows), deepcopy(source.cells)
    if damage == "overlap":
        cells.append(deepcopy(cells[0]))
    elif damage == "out_of_bounds":
        cells[-1].column_span = 2
    else:
        rows[0][2] = "仍应可见"
    fragment = _fragment(1, rows, cells)
    metadata = _metadata(fragment.rendered)[0]

    assert metadata["structure_valid"] is False
    assert metadata["encoding"] == "unknown"
    assert metadata["spans"] is None
    assert metadata["header_scope_complete"] is False
    assert _visible_table(fragment.rendered) == render_gfm_rows(rows)


def test_matching_continuation_translates_source_spans_after_complete_header_removal() -> None:
    first, second = _multilevel(6, "分组甲"), _multilevel(7, "分组乙")
    originals = deepcopy([first.cells, second.cells])
    pages = [
        PageParseResult(page_number=f.page_number, content=f.rendered) for f in (first, second)
    ]

    content = assemble_logical_tables(pages, [first, second], enabled=True)
    metadata = _metadata(content[6])

    assert len(metadata) == 1
    assert metadata[0]["table_id"] == "table_p6_t1_p7_t1"
    assert metadata[0]["source_pages"] == [6, 7]
    assert metadata[0]["num_rows"] == 6
    assert metadata[0]["header_rows"] == [0, 1]
    assert metadata[0]["header_scope_rows"] == [0, 1]
    assert metadata[0]["spans"] == [
        [0, 0, 2, 1],
        [0, 1, 1, 2],
        [2, 0, 2, 1],
        [4, 0, 2, 1],
    ]
    assert "source-page: 6; source-rows: 1-4; logical-rows: 1-4" in content[6]
    assert (
        "source-page: 7; source-rows: 3-4; logical-rows: 5-6; repeated-header-rows: 2" in content[6]
    )
    assert content[7] == ""
    assert _visible_table(content[6]) == render_gfm_rows(first.rows + second.rows[2:])
    assert [first.cells, second.cells] == originals
    assert first.markdown == render_gfm_rows(first.rows)
    assert second.markdown == render_gfm_rows(second.rows)


def test_different_period_headers_keep_separate_structure_and_original_visible_values() -> None:
    fragments = []
    for page, headers, body in (
        (
            2,
            ["项目", "本报告期末", "上年度末"],
            ["总资产", "21,467,154,275.58", "21,158,183,575.04"],
        ),
        (3, ["项目", "本报告期", "上年同期"], ["营业收入", "4,607,261,132.46", "5,093,234,252.91"]),
    ):
        rows = [headers, body]
        cells = [
            TableCellFragment(row, column, 1, 1, text, is_column_header=row == 0)
            for row, values in enumerate(rows)
            for column, text in enumerate(values)
        ]
        fragments.append(_fragment(page, rows, cells))
    pages = [PageParseResult(page_number=f.page_number, content=f.rendered) for f in fragments]

    content = assemble_logical_tables(pages, fragments, enabled=True)

    for fragment in fragments:
        assert re.sub(
            r"<!-- table-source: [^\n]* -->\n\n", "", content[fragment.page_number]
        ) == fragment.rendered
        assert "repeated-header-rows: 0" in content[fragment.page_number]
        assert _visible_table(content[fragment.page_number]) == fragment.markdown
        assert _metadata(content[fragment.page_number])[0]["source_pages"] == [fragment.page_number]
    assert "logical-table:" not in "\n".join(content.values())


def test_unknown_structure_comment_is_not_removed_as_if_owned_by_the_fragment() -> None:
    first, second = _multilevel(1, "甲"), _multilevel(2, "乙")
    second.rendered = "<!-- table-structure: external source note -->\n\n" + second.rendered
    pages = [
        PageParseResult(page_number=f.page_number, content=f.rendered) for f in (first, second)
    ]

    content = assemble_logical_tables(pages, [first, second], enabled=True)

    assert all(
        re.sub(r"<!-- table-source: [^\n]* -->\n\n", "", content[page.page_number]) == page.content
        for page in pages
    )
    assert "<!-- table-structure: external source note -->" in content[2]
    assert "logical-table:" not in "\n".join(content.values())
    assert first.logical_table_id is second.logical_table_id is None
    assert "external source note" in content[2]
