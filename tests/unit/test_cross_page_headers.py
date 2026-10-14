"""Cross-page merges require complete, source-backed header equivalence."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.models import PageParseResult
from app.services.ir_service import DocumentIRService
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    _headers_match,
    _merged_rows,
    assemble_logical_tables,
    link_cross_page_tables,
    render_gfm_rows,
)


def _fragment(
    page: int,
    rows: list[list[str]],
    *,
    header_depth: int = 1,
    cells: list[TableCellFragment] | None = None,
    unit: str | None = None,
) -> TableFragment:
    columns = len(rows[0])
    markdown = render_gfm_rows(rows)
    fragment_id = f"p{page}_t1"
    if cells is None:
        cells = [
            TableCellFragment(
                row=row,
                column=column,
                row_span=1,
                column_span=1,
                text=text,
                is_column_header=row < header_depth,
            )
            for row, values in enumerate(rows)
            for column, text in enumerate(values)
        ]
    return TableFragment(
        fragment_id=fragment_id,
        page_number=page,
        ordinal=1,
        normalized_bbox=(0.1, 0.03, 0.9, 0.96),
        num_rows=len(rows),
        num_cols=columns,
        rows=deepcopy(rows),
        column_boundaries=[0.1 + index * 0.8 / columns for index in range(columns + 1)],
        markdown=markdown,
        rendered=f"<!-- table-fragment: {fragment_id} -->\n\n{markdown}",
        has_column_header=header_depth > 0,
        unit_text=unit,
        cells=cells,
    )


def _financial_fragments() -> tuple[TableFragment, TableFragment]:
    # The periods and values are from 1225474693.pdf, not inferred from row labels.
    assets = _fragment(
        2,
        [
            ["", "本报告期末", "上年度末", "本报告期末比上年度末增减(%)"],
            ["总资产", "21,467,154,275.58", "21,158,183,575.04", "1.46"],
        ],
    )
    income = _fragment(
        3,
        [
            ["", "本报告期", "上年同期", "本报告期比上年同期增减(%)"],
            ["营业收入", "4,607,261,132.46", "5,093,234,252.91", "-9.54"],
            ["归属于上市公司股东的净利润", "645,981,172.66", "676,061,297.92", "-4.45"],
            ["基本每股收益（元／股）", "0.2907", "0.3042", "-4.44"],
        ],
    )
    return assets, income


def _multilevel(page: int, label: str = "营业收入") -> TableFragment:
    rows = [
        ["项目", "本报告期", "", "上年同期", ""],
        ["", "金额", "占比(%)", "金额", "占比(%)"],
        [label, "100", "60", "90", "55"],
    ]
    headers = [
        TableCellFragment(0, 0, 2, 1, "项目", is_column_header=True),
        TableCellFragment(0, 1, 1, 2, "本报告期", is_column_header=True),
        TableCellFragment(0, 3, 1, 2, "上年同期", is_column_header=True),
        *[
            TableCellFragment(1, column, 1, 1, text, is_column_header=True)
            for column, text in enumerate(rows[1])
            if column > 0
        ],
    ]
    body = [TableCellFragment(2, column, 1, 1, text) for column, text in enumerate(rows[2])]
    return _fragment(page, rows, header_depth=2, cells=headers + body, unit="单位：万元")


def test_actual_financial_period_change_keeps_both_headers_and_values() -> None:
    assets, income = _financial_fragments()
    pages = [
        PageParseResult(page_number=2, content=assets.rendered),
        PageParseResult(page_number=3, content=income.rendered),
    ]

    assert not _headers_match(assets, income)
    assert link_cross_page_tables([assets, income]) == []
    content = assemble_logical_tables(pages, [assets, income], enabled=True)

    assert "logical-table" not in "\n".join(content.values())
    assert content[2] == assets.rendered
    assert content[3] == income.rendered
    assert "|  | 本报告期末 | 上年度末 | 本报告期末比上年度末增减(%) |" in content[2]
    assert "| 总资产 | 21,467,154,275.58 | 21,158,183,575.04 |" in content[2]
    assert "|  | 本报告期 | 上年同期 | 本报告期比上年同期增减(%) |" in content[3]
    assert "| 营业收入 | 4,607,261,132.46 | 5,093,234,252.91 |" in content[3]
    assert "| 归属于上市公司股东的净利润 | 645,981,172.66 | 676,061,297.92 |" in content[3]
    assert "| 基本每股收益（元／股） | 0.2907 | 0.3042 |" in content[3]
    assert assets.logical_table_id is None
    assert income.logical_table_id is None


def test_unsafe_group_cannot_drop_changed_header() -> None:
    assets, income = _financial_fragments()
    original = deepcopy([assets.rows, income.rows])

    rows = _merged_rows([assets, income])

    assert rows == assets.rows + income.rows
    assert [assets.rows, income.rows] == original
    rows[0][0] = "changed output"
    assert assets.rows == original[0]


@pytest.mark.parametrize(
    "changed_header",
    [
        ["项目", "本报告期末", "上年同期"],
        ["项目", "本报告期", "上年度末"],
        ["项目", "上年度末", "本报告期末"],
        ["项目", "本报告期末（万元）", "上年度末"],
    ],
)
def test_layout_and_partially_equal_text_do_not_prove_column_meaning(
    changed_header: list[str],
) -> None:
    first = _fragment(1, [["项目", "本报告期末", "上年度末"], ["资产", "100", "90"]])
    second = _fragment(2, [changed_header, ["收入", "80", "70"]])

    assert first.column_boundaries == second.column_boundaries
    assert not _headers_match(first, second)
    assert link_cross_page_tables([first, second]) == []
    assert _merged_rows([first, second]) == first.rows + second.rows


def test_matching_parent_row_does_not_hide_changed_leaf_header() -> None:
    first, second = _multilevel(1), _multilevel(2)
    second.rows[1][1] = "数量"
    next(cell for cell in second.cells if cell.row == 1 and cell.column == 1).text = "数量"

    assert first.rows[0] == second.rows[0]
    assert not _headers_match(first, second)
    assert link_cross_page_tables([first, second]) == []
    assert _merged_rows([first, second]) == first.rows + second.rows


@pytest.mark.parametrize("span", ["row", "column"])
def test_same_anchored_text_with_different_header_spans_does_not_merge(span: str) -> None:
    first, second = _multilevel(1), _multilevel(2)
    if span == "row":
        second.cells[0].row_span = 1
        second.cells.append(TableCellFragment(1, 0, 1, 1, "", is_column_header=True))
    else:
        second.cells[1].column_span = 1
        second.cells.append(TableCellFragment(0, 2, 1, 1, "", is_column_header=True))

    assert first.rows == second.rows
    assert first.header_row_indices == second.header_row_indices == (0, 1)
    assert not _headers_match(first, second)
    assert link_cross_page_tables([first, second]) == []


@pytest.mark.parametrize("damage", ["missing_cells", "missing_cell", "overlap", "crossing"])
def test_unknown_or_incomplete_header_scope_preserves_continuation(damage: str) -> None:
    first, second = _multilevel(1), _multilevel(2)
    if damage == "missing_cells":
        second.cells = []
    elif damage == "missing_cell":
        second.cells.pop(1)
    elif damage == "overlap":
        second.cells.append(deepcopy(second.cells[0]))
    else:
        second.cells[1].row_span = 3
        second.cells[1].is_column_header = False

    assert second.header_row_indices == ()
    assert not _headers_match(first, second)
    assert link_cross_page_tables([first, second]) == []
    assert _merged_rows([first, second]) == first.rows + second.rows


@pytest.mark.parametrize("unit", [None, "单位：元"])
def test_header_equality_requires_same_unit_scope(unit: str | None) -> None:
    first, second = _multilevel(1), _multilevel(2)
    second.unit_text = unit

    assert first.rows == second.rows
    assert not _headers_match(first, second)
    assert link_cross_page_tables([first, second]) == []
    assert _merged_rows([first, second]) == first.rows + second.rows


def test_repeated_multilevel_header_removes_every_header_row_and_retains_evidence() -> None:
    first, second = _multilevel(1, "营业收入"), _multilevel(2, "净利润")
    original_cells = deepcopy([first.cells, second.cells])
    pages = [
        PageParseResult(page_number=1, content=first.rendered),
        PageParseResult(page_number=2, content=second.rendered),
    ]

    assert _merged_rows([first, second]) == first.rows + second.rows[2:]
    content = assemble_logical_tables(pages, [first, second], enabled=True)

    assert content[1].count("| 项目 | 本报告期 |  | 上年同期 |  |") == 1
    assert content[1].count("|  | 金额 | 占比(%) | 金额 | 占比(%) |") == 1
    assert "| 营业收入 | 100 | 60 | 90 | 55 |" in content[1]
    assert "| 净利润 | 100 | 60 | 90 | 55 |" in content[1]
    assert "source-pages: 1,2" in content[1]
    assert "table-source: p1_t1; source-page: 1; source-rows: 1-3" in content[1]
    assert "table-source: p2_t1; source-page: 2; source-rows: 3" in content[1]
    assert "repeated-header-rows: 2" in content[1]
    assert content[2] == ""
    assert [first.cells, second.cells] == original_cells
    assert first.unit_text == second.unit_text == "单位：万元"
    assert pages[0].content == first.rendered
    assert pages[1].content == second.rendered
    assert first.logical_table_id == second.logical_table_id == "table_p1_t1_p2_t1"
    assert all(page.diagnostics.logical_table_ids == ["table_p1_t1_p2_t1"] for page in pages)


def test_three_page_continuation_has_one_complete_header_and_one_logical_id() -> None:
    fragments = [_multilevel(page, f"财务行{page}") for page in range(1, 4)]
    pages = [PageParseResult(page_number=f.page_number, content=f.rendered) for f in fragments]

    assert link_cross_page_tables(fragments) == [fragments]
    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert content[1].count("logical-table:") == 1
    assert "table_p1_t1_p3_t1; source-pages: 1,2,3" in content[1]
    assert content[1].count("|  | 金额 | 占比(%) | 金额 | 占比(%) |") == 1
    for page in range(1, 4):
        assert f"| 财务行{page} | 100 | 60 | 90 | 55 |" in content[1]
    assert content[2] == content[3] == ""
    assert all(fragment.logical_table_id == "table_p1_t1_p3_t1" for fragment in fragments)


def test_whitespace_wrapping_is_compatible_without_rewriting_source_text() -> None:
    first = _fragment(1, [["项目", "本报告期末", "上年度末"], ["资产", "100", "90"]])
    second = _fragment(2, [["项目", "本报告期\n末", "上年 度末"], ["净资产", "80", "70"]])
    original = deepcopy(second.rows)

    assert _headers_match(first, second)
    assert _merged_rows([first, second]) == first.rows + second.rows[1:]
    assert second.rows == original


def test_ir_retains_all_header_levels_spans_units_and_page_relation() -> None:
    fragment = _multilevel(2)
    fragment.logical_table_id = "table_p1_t1_p2_t1"

    table = DocumentIRService._table(fragment)

    assert table.header_rows == [0, 1]
    assert table.unit_text == "单位：万元"
    assert table.source_units == [2]
    assert table.logical_table_id == "table_p1_t1_p2_t1"
    assert next(cell for cell in table.cells if cell.text == "项目").row_span == 2
    assert next(cell for cell in table.cells if cell.text == "本报告期").column_span == 2
    assert table.unit_id == "p2"
    assert all(cell.cell_id.startswith("p2_t1-") for cell in table.cells)


def test_ir_no_cell_header_keeps_legacy_metadata_but_cannot_authorize_merge() -> None:
    fragment = _multilevel(2)
    fragment.cells = []

    assert DocumentIRService._table(fragment).header_rows == [0]
    assert not _headers_match(_multilevel(1), fragment)


@pytest.mark.parametrize("page_number", [1, 2])
@pytest.mark.parametrize("damage", ["missing", "duplicate"])
def test_unavailable_unique_rendered_fragment_aborts_group_without_data_loss(
    page_number: int, damage: str
) -> None:
    first, second = _multilevel(1), _multilevel(2)
    fragments = [first, second]
    pages = [PageParseResult(page_number=f.page_number, content=f.rendered) for f in fragments]
    pages[page_number - 1].content = (
        "source content whose table marker cannot be found"
        if damage == "missing"
        else fragments[page_number - 1].rendered + "\n\n" + fragments[page_number - 1].rendered
    )
    original = {page.page_number: page.content for page in pages}

    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert content == original
    assert all(fragment.logical_table_id is None for fragment in fragments)
    assert all(
        page.diagnostics.logical_table_ids == [fragment.fragment_id]
        for page, fragment in zip(pages, fragments, strict=True)
    )


def test_equal_source_preludes_preserve_title_and_unit_during_merge() -> None:
    first, second = _multilevel(1), _multilevel(2, "净利润")
    for fragment in [first, second]:
        fragment.rendered = (
            f"<!-- table-fragment: {fragment.fragment_id} -->\n\n"
            f"销售统计\n\n单位：万元\n\n{fragment.markdown}"
        )
    pages = [
        PageParseResult(page_number=f.page_number, content=f.rendered) for f in [first, second]
    ]

    content = assemble_logical_tables(pages, [first, second], enabled=True)

    assert "logical-table:" in content[1]
    assert "销售统计" in content[1]
    assert "单位：万元" in content[1]
    assert "| 净利润 | 100 | 60 | 90 | 55 |" in content[1]
    assert content[2] == ""


def test_identical_headers_with_changed_caption_do_not_merge() -> None:
    first, second = _multilevel(1), _multilevel(2)
    first.caption = "资产结构"
    second.caption = "收入结构"

    assert not _headers_match(first, second)
    assert link_cross_page_tables([first, second]) == []
    assert _merged_rows([first, second]) == first.rows + second.rows


@pytest.mark.parametrize(
    ("first_unit", "second_unit", "should_merge"),
    [
        ("单位：万元", "单位：元", False),
        (None, "单位：万元", False),
        ("单位：万元", None, True),
    ],
)
def test_explicit_nearby_units_govern_safe_merge_scope(
    first_unit: str | None, second_unit: str | None, should_merge: bool
) -> None:
    first, second = _multilevel(1), _multilevel(2, "净利润")
    first.unit_text = second.unit_text = None
    pages = [
        PageParseResult(
            page_number=1, content=(first_unit + "\n\n" if first_unit else "") + first.rendered
        ),
        PageParseResult(
            page_number=2, content=(second_unit + "\n\n" if second_unit else "") + second.rendered
        ),
    ]
    original = {page.page_number: page.content for page in pages}

    content = assemble_logical_tables(pages, [first, second], enabled=True)

    if should_merge:
        assert "logical-table:" in content[1]
        assert first_unit in content[1]
        assert "| 净利润 | 100 | 60 | 90 | 55 |" in content[1]
        assert content[2] == ""
    else:
        assert content == original
        assert first.logical_table_id is second.logical_table_id is None


def test_all_empty_header_cells_cannot_prove_column_meaning() -> None:
    first = _fragment(1, [["", "", ""], ["资产", "100", "90"]])
    second = _fragment(2, [["", "", ""], ["收入", "80", "70"]])

    assert not _headers_match(first, second)
    assert link_cross_page_tables([first, second]) == []
    assert _merged_rows([first, second]) == first.rows + second.rows


@pytest.mark.parametrize("third_unit", ["单位：元", "单位：万元"])
def test_three_page_continuation_carries_explicit_unit_scope_past_omitted_unit(
    third_unit: str,
) -> None:
    fragments = [_multilevel(page, f"财务行{page}") for page in range(1, 4)]
    for fragment in fragments:
        fragment.unit_text = None
    pages = [
        PageParseResult(page_number=1, content="单位：元\n\n" + fragments[0].rendered),
        PageParseResult(page_number=2, content=fragments[1].rendered),
        PageParseResult(page_number=3, content=third_unit + "\n\n" + fragments[2].rendered),
    ]
    original = {page.page_number: page.content for page in pages}

    content = assemble_logical_tables(pages, fragments, enabled=True)

    if third_unit == "单位：元":
        assert "table_p1_t1_p3_t1; source-pages: 1,2,3" in content[1]
        assert "单位：元" in content[1]
        assert content[2] == ""
        assert "table-fragment:" not in content[3]
        for page in range(1, 4):
            assert f"| 财务行{page} | 100 | 60 | 90 | 55 |" in content[1]
        assert all(fragment.logical_table_id == "table_p1_t1_p3_t1" for fragment in fragments)
    else:
        assert content == original
        assert all(fragment.logical_table_id is None for fragment in fragments)
