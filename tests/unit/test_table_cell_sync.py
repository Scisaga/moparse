"""Source spans and final cell text survive the GLM fusion transformations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from app.parsers.glm_sdk_remote import GlmSdkRemoteParser
from app.services.ir_service import DocumentIRService
from app.services.parser_service import ParserService
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows
from app.services.visual_fusion_service import VisualFusionService


def _fragment(content: str) -> TableFragment:
    fragment = GlmSdkRemoteParser._table_fragment(
        {"content": content, "bbox_2d": [100, 100, 900, 900]}, 7, 1
    )
    assert fragment is not None
    fragment.caption = "来源表格"
    fragment.unit_text = "单位：万元"
    fragment.cell_evidence = [
        [{"glm": value, "final": value, "native": f"source-r{row}-c{column}"}
         for column, value in enumerate(values)]
        for row, values in enumerate(fragment.rows)
    ]
    return fragment


def test_blank_physical_row_removal_reindexes_spans_evidence_and_source_rows() -> None:
    original = _fragment(
        "<table><tr><th rowspan='2'>事项</th><th colspan='2'>金额</th></tr>"
        "<tr><th>本期</th><th>上期</th></tr>"
        "<tr><td rowspan='3'>项目甲</td><td>10</td><td>9</td></tr>"
        "<tr></tr><tr><td>2</td><td>1</td></tr></table>"
    )
    label = next(cell for cell in original.cells if cell.text == "项目甲")
    label.normalized_bbox = (0.1, 0.4, 0.3, 0.9)
    before = deepcopy(original)

    [fragment] = VisualFusionService._normalized_glm_fragments([original])

    assert fragment.rows == [
        ["事项", "金额", ""], ["", "本期", "上期"], ["项目甲", "10", "9"], ["", "2", "1"]
    ]
    assert fragment.source_row_indices == [0, 1, 2, 4]
    assert fragment.physical_num_rows == 5
    assert fragment.cell_evidence[3][1]["native"] == "source-r4-c1"
    assert fragment.cell_evidence[3][1]["final"] == "2"
    assert fragment.header_row_indices == (0, 1)
    table = DocumentIRService._table(fragment)
    merged = next(cell for cell in table.cells if cell.text == "项目甲")
    assert (merged.row, merged.row_span, merged.column_span) == (2, 2, 1)
    assert merged.bbox is not None
    assert (merged.bbox.top, merged.bbox.bottom) == (0.4, 0.9)
    assert table.source_units == [7]
    assert table.unit_text == "单位：万元"
    assert "来源表格" in fragment.rendered
    assert "单位：万元" in fragment.rendered
    assert original == before


def test_existing_cell_source_text_is_not_lost_when_its_row_view_is_empty() -> None:
    original = _fragment(
        "<table><tr><th>事项</th><th>金额</th></tr>"
        "<tr><td>项目甲</td><td>10</td></tr><tr><td>项目乙</td><td></td></tr></table>"
    )
    original.rows[2][0] = ""

    [fragment] = VisualFusionService._normalized_glm_fragments([original])

    assert fragment.rows[2] == ["项目乙", ""]
    assert next(cell for cell in DocumentIRService._table(fragment).cells if cell.row == 2).text == (
        "项目乙"
    )


def test_parallel_half_split_retains_contained_spans_geometry_and_evidence() -> None:
    headers = "<th>事项</th><th>备注</th><th>本期</th><th>上期</th>"
    original = _fragment(
        f"<table><tr>{headers}{headers}</tr>"
        "<tr><td rowspan='2'>左甲</td><td>注一</td><td>10</td><td>9</td>"
        "<td rowspan='2'>右甲</td><td colspan='2'>共同备注</td><td>8</td></tr>"
        "<tr><td>注二</td><td>2</td><td>1</td>"
        "<td>注三</td><td>3</td><td>2</td></tr></table>"
    )
    original.column_boundaries = [0.1, 0.2, 0.3, 0.4, 0.6, 0.65, 0.7, 0.8, 0.9]

    left, right = VisualFusionService._split_wide_fragment(original)

    assert left.normalized_bbox == (0.1, 0.1, 0.6, 0.9)
    assert right.normalized_bbox == (0.6, 0.1, 0.9, 0.9)
    assert right.column_boundaries == [0.6, 0.65, 0.7, 0.8, 0.9]
    assert right.cell_evidence[1][1]["native"] == "source-r1-c5"
    for fragment, label, expected_cells in ((left, "左甲", 11), (right, "右甲", 10)):
        table = DocumentIRService._table(fragment)
        merged = next(cell for cell in table.cells if cell.text == label)
        assert (merged.row, merged.column, merged.row_span) == (1, 0, 2)
        assert table.source_units == [7]
        assert table.unit_text == "单位：万元"
        assert len(fragment.cells) == expected_cells
    shared_note = next(cell for cell in right.cells if cell.text == "共同备注")
    assert (shared_note.column, shared_note.column_span) == (1, 2)
    # Copies must keep their evidence independent of the source fragment.
    right.cell_evidence[1][1]["final"] = "altered copy"
    assert original.cell_evidence[1][5]["final"] == "共同备注"


def test_parallel_half_split_declines_a_cell_crossing_the_half_boundary() -> None:
    headers = "<th>事项</th><th>备注</th><th>本期</th><th>上期</th>"
    original = _fragment(f"<table><tr>{headers}{headers}</tr></table>")
    original.cells.append(TableCellFragment(1, 3, 1, 2, "跨组标题"))
    original.rows.append(["甲", "", "", "跨组标题", "", "乙", "", ""])
    original.num_rows += 1

    assert VisualFusionService._split_wide_fragment(original) == [original]


def test_parallel_headers_do_not_hide_an_undeclared_body_column() -> None:
    headers = "<th>事项</th><th>备注</th><th>本期</th><th>上期</th>"
    original = _fragment(
        f"<table><tr>{headers}{headers}</tr>"
        "<tr><td>甲</td><td>注一</td><td>10</td><td>9</td>"
        "<td>乙</td><td>注二</td><td>8</td><td>7</td></tr></table>"
    )
    original.rows[1].append("-123.45")
    original.cell_evidence[1].append({"glm": "-123.45", "final": "-123.45"})
    before = deepcopy(original)

    [fragment] = VisualFusionService._normalized_glm_fragments([original])

    assert fragment.fragment_id == original.fragment_id
    assert fragment.rows == before.rows
    assert fragment.cells == before.cells
    assert fragment.cell_evidence == before.cell_evidence
    assert fragment.source_row_indices == before.source_row_indices
    assert fragment.unit_text == before.unit_text
    assert not fragment.valid
    assert "table_cell_topology_invalid" in fragment.invalid_reasons
    assert fragment.header_row_indices == ()
    assert original == before


def test_selected_final_value_updates_explicit_cells_and_ir_without_changing_spans() -> None:
    original = _fragment(
        "<table><tr><th>事项</th><th>金额</th></tr>"
        "<tr><td rowspan='2'>项目甲</td><td>10.00</td></tr>"
        "<tr><td>9.00</td></tr></table>"
    )
    [table] = VisualFusionService._glm_tables([original])
    table.rows[0][1] = "-10.25"
    table.evidence[0][1].update({"qwen": "-10.25", "final": "-10.25"})

    [updated] = VisualFusionService._updated_glm_fragments([original], [table], targeted=True)

    ir = DocumentIRService._table(updated)
    selected = next(cell for cell in ir.cells if (cell.row, cell.column) == (1, 1))
    assert selected.text == "-10.25"
    assert selected.provenance.selected_source.value == "qwen"
    merged = next(cell for cell in ir.cells if cell.text == "项目甲")
    assert merged.row_span == 2
    assert ir.source_units == [7]
    assert ir.caption == "来源表格"
    assert ir.unit_text == "单位：万元"
    assert updated.cell_evidence[1][1]["glm"] == "10.00"
    assert "-10.25" in updated.markdown
    assert original.rows[1][1] == "10.00"
    assert next(cell for cell in original.cells if (cell.row, cell.column) == (1, 1)).text == "10.00"


def test_financial_note_normalization_updates_cell_text_but_retains_source_evidence() -> None:
    original = _fragment(
        "<table><tr><th>项目</th><th>附注</th><th>2026年末</th><th>2025年末</th></tr>"
        "<tr><td>现金</td><td>五、一)</td><td>100</td><td>90</td></tr>"
        "<tr><td>库存</td><td></td><td>20</td><td>19</td></tr>"
        "<tr><td>合计</td><td></td><td>120</td><td>109</td></tr></table>"
    )

    [fragment] = VisualFusionService._normalized_glm_fragments([original])

    note = next(cell for cell in DocumentIRService._table(fragment).cells if (cell.row, cell.column) == (1, 1))
    assert note.text == "五、(一)"
    assert fragment.cell_evidence[1][1]["glm"] == "五、一)"
    assert fragment.cell_evidence[1][1]["final"] == "五、(一)"
    assert all(cell.text == fragment.rows[cell.row][cell.column] for cell in fragment.cells)


def test_unexpected_nonempty_extra_column_is_retained_as_a_topology_conflict() -> None:
    original = _fragment(
        "<table><tr><th>事项</th><th>金额</th></tr>"
        "<tr><td>项目甲</td><td>10</td></tr></table>"
    )
    malformed = replace(original, rows=[original.rows[0], [*original.rows[1], "不可丢字"]])

    [fragment] = VisualFusionService._normalized_glm_fragments([malformed])

    assert fragment.rows[1][-1] == "不可丢字"
    assert not fragment.valid
    assert "table_cell_topology_invalid" in fragment.invalid_reasons


def test_selected_text_inside_merged_continuation_is_visible_but_conflicted() -> None:
    original = _fragment(
        "<table><tr><th>事项</th><th>金额</th></tr>"
        "<tr><td rowspan='2'>项目甲</td><td>10</td></tr><tr><td>9</td></tr></table>"
    )
    [table] = VisualFusionService._glm_tables([original])
    table.rows[1][0] = "待核对新增字"
    table.evidence[1][0].update({"qwen": "待核对新增字", "final": "待核对新增字"})

    [candidate] = VisualFusionService._updated_glm_fragments([original], [table], targeted=True)

    assert not candidate.valid
    assert "table_cell_span_conflict" in candidate.invalid_reasons
    ir = DocumentIRService._table(candidate)
    assert "待核对新增字" in [cell.text for cell in ir.cells]
    assert "项目甲" in [cell.text for cell in ir.cells]
    assert all(cell.quality.value == "conflicted" for cell in ir.cells if cell.text)
    # The original remains available unchanged if the gate rejects this edit.
    assert next(cell for cell in original.cells if cell.text == "项目甲").row_span == 2


def test_normalized_glyph_refresh_synchronizes_ir_and_preserves_raw_cell_wrapping() -> None:
    fragment = _fragment(
        "<table><tr><th rowspan='2'>说明</th><th>日期</th></tr><tr><th>2026</th></tr>"
        "<tr><td>⾮控制&#124;A &amp; B</td><td>第一行<br/>第二行</td></tr></table>"
    )
    wrapped = next(cell for cell in fragment.cells if (cell.row, cell.column) == (2, 1))
    wrapped.text = fragment.rows[2][1] = "第一行\n第二行"
    displayed_rows = deepcopy(fragment.rows)
    displayed_rows[2][0] = "非控制|A & B"
    markdown = render_gfm_rows(displayed_rows)
    result = DocumentParseResult(
        document_id="glyph-refresh-test", filename="fixture.pdf", mime_type="application/pdf",
        page_count=7, processed_pages=1,
        pages=[PageParseResult(page_number=7, backend="docling-standard",
                               content=f"<!-- table-fragment: {fragment.fragment_id} -->\n\n{markdown}")],
        pipeline=ParsePipeline(profile="balanced", primary="docling-standard"),
    )
    result._table_fragments = [fragment]

    ParserService._refresh_table_fragment_renderings(result, native_glyph_pages={7})

    table = DocumentIRService._table(fragment)
    normalized_cell = next(cell for cell in table.cells if (cell.row, cell.column) == (2, 0))
    assert normalized_cell.text == "非控制|A & B"
    assert normalized_cell.provenance.selected_source.value == "native"
    assert fragment.rows[2][0] == "非控制|A & B"
    assert fragment.cell_evidence[2][0]["glm"] == "⾮控制|A & B"
    assert fragment.cell_evidence[2][0]["native_normalized"] == "非控制|A & B"
    assert wrapped.text == fragment.rows[2][1] == "第一行\n第二行"
    assert fragment.header_row_indices == (0, 1)
    assert next(cell for cell in table.cells if cell.text == "说明").row_span == 2
    assert table.caption == "来源表格"
    assert table.unit_text == "单位：万元"
    assert table.source_units == [7]
    assert "&#124;" in fragment.markdown and "&amp;" in fragment.markdown
