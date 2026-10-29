"""Pure synthetic service export regressions; no document corpus is read."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.parse_result import PageParseResult
from app.services.export_service import ExportService
from app.services.ir_service import DocumentIRService
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows


@pytest.mark.parametrize("source", [
    "净收益 < 0 且限额 > 10。",
    "条件为 x < y 且 z > w。",
    "不等式 0 < x < 10。",
])
def test_plain_export_preserves_comparison_characters_and_enclosed_words(source):
    assert ExportService.markdown_to_text(source) == source


def test_plain_export_removes_actual_html_tags_and_decodes_entities_once():
    source = '<p>正文<b>强调</b><span class="key">仍保留</span><em>关系</em> &amp; 附注</p>'
    assert ExportService.markdown_to_text(source) == "正文强调仍保留关系 & 附注"
    assert ExportService.markdown_to_text("&amp;lt;tag&amp;gt;") == "&lt;tag&gt;"


def test_inline_code_is_literal_before_html_emphasis_or_entity_cleanup():
    source = "值 `<b>13.25</b> **literal** &amp;`。"
    assert ExportService.markdown_to_text(source) == "值 <b>13.25</b> **literal** &amp;。"
    assert ExportService.markdown_to_text("``a ` b < c``") == "a ` b < c"


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_code_blocks_preserve_business_text_markup_entities_and_whitespace(fence):
    body = "x < 0 且 y > 1\n<b>literal</b>\n**literal**\n&amp;\n  keep trailing  "
    source = f"前文\n\n{fence}text\n{body}\n{fence}\n\n后文"
    assert ExportService.markdown_to_text(source) == f"前文\n\n{body}\n\n后文"


def test_code_block_does_not_swallow_the_separator_before_following_prose():
    assert ExportService.markdown_to_text("```\nx < y\n```\n后文") == "x < y\n后文"
    assert ExportService.markdown_to_text("    <b>literal</b>\n\n后文") == "<b>literal</b>\n\n后文"


@pytest.mark.parametrize("source,expected", [
    ("150.1<sup>4</sup>", "150.1<sup>4</sup>"),
    ("H<sub>2</sub>O", "H<sub>2</sub>O"),
    ("150.1&lt;sup&gt;4&lt;/sup&gt;", "150.1<sup>4</sup>"),
    ("`150.1<sup>4</sup> &lt;tag&gt;`", "150.1<sup>4</sup> &lt;tag&gt;"),
])
def test_explicit_superscript_and_subscript_never_join_neighboring_digits(source, expected):
    assert ExportService.markdown_to_text(source) == expected


def _fragment() -> TableFragment:
    rows = [["项目", "金额"], ["收入", "(12.30)"]]
    markdown = render_gfm_rows(rows)
    return TableFragment(
        fragment_id="synthetic-table", page_number=1, ordinal=1,
        normalized_bbox=(0.1, 0.3, 0.9, 0.8), num_rows=2, num_cols=2,
        rows=rows, column_boundaries=[], markdown=markdown,
        rendered=f"<!-- table-fragment: synthetic-table -->\n\n{markdown}", source_kind="mineru",
        has_column_header=True,
        cells=[TableCellFragment(row, col, 1, 1, text, is_column_header=row == 0)
               for row, values in enumerate(rows) for col, text in enumerate(values)],
    )


@pytest.mark.parametrize("content", [
    "| 审核意见 | 本人已核查并签字 |\n\n日期：2026-10-28",
    "```text\n| literal | pipe |\n```\n\n后文",
    "首段\n\n| 普通竖线 | 完整正文 |\n\n尾段",
])
def test_unowned_pipe_text_is_retained_in_ir_body(content):
    unit = DocumentIRService._page(
        PageParseResult(page_number=1, content=content, backend="mineru-native"), None, {}, [])
    assert [block.text for block in unit.blocks] == [content]
    assert unit.renderings.markdown == content


def test_only_explicitly_owned_table_rendering_is_removed_from_ir_body():
    fragment = _fragment()
    table = DocumentIRService._table(fragment)
    content = f"# 业务标题\n\n{fragment.rendered}\n\n| 审核 | 已签字 |\n\n尾段"
    page = PageParseResult(page_number=1, content=content, backend="mineru-native")
    unit = DocumentIRService._page(page, None, {1: [table]}, [], table_fragments=[fragment])
    body = "\n".join(block.text for block in unit.blocks)
    assert "业务标题" in body and "| 审核 | 已签字 |" in body and "尾段" in body
    assert "(12.30)" not in body and "收入" not in body
    assert "(12.30)" in [cell.text for cell in table.cells]
    assert unit.table_ids == [fragment.fragment_id]
    assert unit.renderings.markdown == content


@pytest.mark.parametrize("problem", ["missing_owner", "ambiguous_rendering", "wrong_page"])
def test_unknown_rendering_ownership_never_authorizes_pipe_text_deletion(problem):
    fragment = _fragment()
    table = DocumentIRService._table(fragment)
    content = fragment.rendered
    if problem == "ambiguous_rendering":
        content += "\n\n" + fragment.rendered
    elif problem == "wrong_page":
        fragment.page_number = 2
    tables = {} if problem == "missing_owner" else {1: [table]}
    unit = DocumentIRService._page(PageParseResult(page_number=1, content=content), None, tables, [],
                                   table_fragments=[fragment])
    assert any("(12.30)" in block.text for block in unit.blocks)


def _source_page_picture():
    return SimpleNamespace(source_page_ref="synthetic_failed", source_region_ref=None,
                           normalized_bbox=(0.0, 0.0, 1.0, 1.0))


def test_source_page_fallback_preserves_valid_neighbors_and_unknown_candidate_text():
    candidate = "SDK候选文字（结构未知）\n\n```text\n未决区域原有候选文字\n```"
    content = ("# 业务标题\n\n前段有效正文\n\n" + candidate
               + "\n\n后段有效正文\n\n<!-- source-page-image: synthetic_failed -->")
    unit = DocumentIRService._page(
        PageParseResult(page_number=1, content=content, backend="mineru-native"),
        None, {}, [_source_page_picture()])
    body = "\n".join(block.text for block in unit.blocks)
    assert all(text in body for text in ("业务标题", "前段有效正文", candidate, "后段有效正文"))
    assert "source-page-image:" not in body
    assert any(region.region_id == "p1-source-page-synthetic_failed"
               and region.region_type.value == "unknown" for region in unit.regions)
    assert unit.renderings.markdown == content


@pytest.mark.parametrize("content", ["", "<!-- source-page-image: synthetic_failed -->",
                                     "<!-- image -->\n\n<!-- source-page-image: synthetic_failed -->"])
def test_source_page_placeholder_without_text_does_not_create_ir_body(content):
    unit = DocumentIRService._page(PageParseResult(page_number=1, content=content), None, {},
                                   [_source_page_picture()])
    assert unit.blocks == []
    assert len(unit.regions) == 1 and unit.regions[0].region_type.value == "unknown"


def test_source_page_fallback_with_owned_table_keeps_table_without_duplicate_body():
    fragment = _fragment()
    table = DocumentIRService._table(fragment)
    content = fragment.rendered + "\n\n<!-- source-page-image: synthetic_failed -->"
    unit = DocumentIRService._page(PageParseResult(page_number=1, content=content), None,
                                   {1: [table]}, [_source_page_picture()], table_fragments=[fragment])
    assert unit.blocks == []
    assert unit.table_ids == [fragment.fragment_id]
    assert any(region.region_type.value == "table" for region in unit.regions)
    assert any(region.region_type.value == "unknown" for region in unit.regions)
def test_code_placeholder_cannot_rewrite_previously_protected_literal():
    markdown = "```text\nMOPARSECODE1TOKEN\n```\n\n`actual literal`"

    assert ExportService.markdown_to_text(markdown) == "MOPARSECODE1TOKEN\n\nactual literal"


@pytest.mark.parametrize("fence", ["```text\n{body}\n```", "    {body}"])
def test_code_after_real_page_separator_is_neither_duplicated_nor_misplaced(fence):
    body = "<b>literal</b> &amp;"
    markdown = "Page one\n\n\f\n\n" + fence.format(body=body) + "\n\nPage two tail"

    assert ExportService.markdown_to_text(markdown) == "Page one\n\n\f\n\n" + body + "\n\nPage two tail"
