"""Geometry validation preserves model output and blocks unsafe header deletion."""

from copy import deepcopy

import pytest

from app.parsers.glm_sdk_remote import GlmSdkRemoteParser
from app.services.glm_table_service import GlmTableService
from app.services.ir_service import DocumentIRService
from app.services.table_service import TableCellFragment, TableFragment


def _fragment() -> TableFragment:
    fragment = GlmSdkRemoteParser._table_fragment(
        {
            "content": (
                "<table><tr><th rowspan='2'>事项（元／股）</th>"
                "<th colspan='2'>原件期间</th></tr>"
                "<tr><th>本期</th><th>上期</th></tr>"
                "<tr><td rowspan='2'>多行合并内容</td><td>0.2907</td><td>0.3042</td></tr>"
                "<tr><td>-10.25</td><td>9.00</td></tr></table>"
            ),
            "bbox_2d": [100, 100, 900, 900],
        },
        7,
        1,
    )
    assert fragment is not None
    fragment.unit_text = "单位：元／股"
    return fragment


def test_valid_model_table_keeps_all_source_text_spans_units_and_pages() -> None:
    fragment = _fragment()
    before = deepcopy(fragment)

    assert GlmTableService.validate_fragments([fragment]) == []

    assert fragment == before
    table = DocumentIRService._table(fragment)
    assert table.source_units == [7]
    assert table.unit_text == "单位：元／股"
    assert table.header_rows == [0, 1]
    assert next(cell for cell in table.cells if cell.text == "多行合并内容").row_span == 2
    assert [cell.text for cell in table.cells if cell.column == 1 and cell.row >= 2] == [
        "0.2907", "-10.25"
    ]


@pytest.mark.parametrize("damage", ["extra_column", "covered_text", "overlap", "out_of_bounds", "anchor_conflict"])
def test_invalid_model_geometry_is_flagged_without_dropping_recognized_content(damage: str) -> None:
    fragment = _fragment()
    if damage == "extra_column":
        fragment.rows[2].append("额外识别文字42.00")
    elif damage == "covered_text":
        fragment.rows[3][0] = "合并格中新增识别字"
    elif damage == "anchor_conflict":
        fragment.rows[2][0] = "锚点视图存在冲突文字"
    elif damage == "overlap":
        fragment.cells.append(TableCellFragment(3, 0, 1, 1, "重叠识别字"))
    else:
        fragment.cells.append(TableCellFragment(3, 2, 2, 1, "越界识别字"))
    before = deepcopy(fragment)

    warnings = GlmTableService.validate_fragments([fragment])

    assert len(warnings) == 1
    assert warnings[0].code == "table_structure_invalid"
    assert warnings[0].page_number == 7
    assert fragment.rows == before.rows
    assert fragment.cells == before.cells
    assert fragment.cell_evidence == before.cell_evidence
    assert fragment.markdown == before.markdown
    assert fragment.unit_text == before.unit_text
    assert not fragment.valid
    assert fragment.invalid_reasons
    assert fragment.header_row_indices == ()


def test_validation_does_not_rewrite_numbers_notes_or_invent_periods_from_row_names() -> None:
    fragment = GlmSdkRemoteParser._table_fragment(
        {
            "content": (
                "<table><tr><th>项目</th><th>原文注释</th><th>原文期间甲</th></tr>"
                "<tr><td>营业收入</td><td>五、一)</td><td>100,000,000.00</td></tr>"
                "<tr><td>净利润</td><td></td><td>142,000,000.00</td></tr></table>"
            ),
            "bbox_2d": [100, 100, 900, 900],
        }, 3, 1,
    )
    assert fragment is not None
    before = deepcopy(fragment)

    assert GlmTableService.validate_fragments([fragment]) == []

    assert fragment == before
    assert "五、一)" in fragment.markdown
    assert "本报告期" not in fragment.markdown
    assert "100,000,000.00" in fragment.markdown
    assert "142,000,000.00" in fragment.markdown
