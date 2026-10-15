from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.models.parse_result import PageParseResult
from app.services.parser_service import ParserService
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows


def _fragment(rows: list[list[str]]) -> TableFragment:
    markdown = render_gfm_rows(rows)
    return TableFragment(
        fragment_id="p6_t2",
        page_number=6,
        ordinal=2,
        normalized_bbox=(0.1, 0.1, 0.9, 0.9),
        num_rows=len(rows),
        num_cols=len(rows[0]),
        rows=deepcopy(rows),
        column_boundaries=[],
        markdown=markdown,
        rendered="<!-- table-fragment: p6_t2 -->\n\n" + markdown,
        has_column_header=True,
        cells=[
            TableCellFragment(row, column, 1, 1, value, is_column_header=row == 0)
            for row, values in enumerate(rows)
            for column, value in enumerate(values)
        ],
        unit_text="单位：股",
        cell_evidence=[[{"docling": value, "final": value} for value in values] for values in rows],
        source_row_indices=list(range(len(rows))),
        physical_num_rows=len(rows),
    )


def _refresh(fragment: TableFragment) -> None:
    page = PageParseResult(page_number=6, backend="docling-standard", content=fragment.rendered)
    result = SimpleNamespace(pages=[page], _table_fragments=[fragment])
    ParserService._refresh_table_fragment_renderings(result)


@pytest.mark.parametrize("linebreak", ["\r", "\r\n", "\n"])
def test_wrapped_name_and_amount_survive_gfm_refresh(linebreak: str) -> None:
    fragment = _fragment(
        [
            ["序号", "股东名称", "持股数量", "持股比例", "有限售条件的股" + linebreak + "份数量"],
            ["5", "基本养老保险基金一六零" + linebreak + "三二组合", "18,669,504", "1.79%", "-"],
        ]
    )
    before = deepcopy(fragment)

    _refresh(fragment)

    assert fragment.rows == before.rows
    assert fragment.cells == before.cells
    assert fragment.cell_evidence == before.cell_evidence
    assert fragment.header_row_indices == (0,)
    assert fragment.unit_text == before.unit_text
    assert fragment.source_row_indices == before.source_row_indices
    assert all(
        line.startswith("|") and line.endswith("|") for line in fragment.markdown.splitlines()
    )
    assert "基本养老保险基金一六零 三二组合 | 18,669,504 | 1.79%" in fragment.markdown


def test_linebreak_rendering_preserves_multi_level_headers_and_source_spans() -> None:
    fragment = _fragment(
        [
            ["项目", "本报告期\r\n金额", ""],
            ["", "本报告期", "上年同期"],
            ["营业收入", "4,607,261,132.46", "-9.54"],
        ]
    )
    fragment.cells = [
        TableCellFragment(0, 0, 2, 1, fragment.rows[0][0], is_column_header=True),
        TableCellFragment(0, 1, 1, 2, fragment.rows[0][1], is_column_header=True),
        TableCellFragment(1, 1, 1, 1, fragment.rows[1][1], is_column_header=True),
        TableCellFragment(1, 2, 1, 1, fragment.rows[1][2], is_column_header=True),
        *[TableCellFragment(2, column, 1, 1, text) for column, text in enumerate(fragment.rows[2])],
    ]
    before = deepcopy(fragment)

    _refresh(fragment)

    assert fragment.rows == before.rows
    assert fragment.cells == before.cells
    assert fragment.cell_evidence == before.cell_evidence
    assert fragment.header_row_indices == (0, 1)
    assert fragment.cells[1].column_span == 2
    assert fragment.cells[0].row_span == 2
    assert "-9.54" in fragment.markdown
    assert "4,607,261,132.46" in fragment.markdown


def test_linebreak_rendering_preserves_html_pipe_and_unit_escaping() -> None:
    markdown = render_gfm_rows([["事项", "单位"], ["A&B\nC|D", "元／股"]])

    assert "A&amp;B C&#124;D" in markdown
    assert "元／股" in markdown
