"""Cross-page header removal keeps source captions and unit scopes intact."""

from __future__ import annotations

from copy import deepcopy

import pytest
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    RefItem,
    Size,
    TableCell,
    TableData,
)

from app.models import PageParseResult
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    assemble_logical_tables,
    export_page_markdown,
    extract_table_fragments,
    link_cross_page_tables,
    render_gfm_rows,
)


def _fragment(page: int) -> TableFragment:
    rows = [["类别", "数量"], [f"来源 {page}", str(page * 100)]]
    markdown = render_gfm_rows(rows)
    identifier = f"p{page}_t1"
    return TableFragment(
        fragment_id=identifier,
        page_number=page,
        ordinal=1,
        normalized_bbox=(0.1, 0.02, 0.9, 0.97),
        num_rows=2,
        num_cols=2,
        rows=rows,
        column_boundaries=[0.1, 0.5, 0.9],
        markdown=markdown,
        rendered=f"<!-- table-fragment: {identifier} -->\n\n{markdown}",
        has_column_header=True,
        cells=[
            TableCellFragment(row, column, 1, 1, text, is_column_header=row == 0)
            for row, values in enumerate(rows)
            for column, text in enumerate(values)
        ],
    )


def _assemble(prefixes: list[str]) -> tuple[dict[int, str], list[TableFragment]]:
    fragments = [_fragment(page) for page in range(1, len(prefixes) + 1)]
    pages = [
        PageParseResult(page_number=fragment.page_number, content=prefix + fragment.rendered)
        for prefix, fragment in zip(prefixes, fragments, strict=True)
    ]
    return assemble_logical_tables(pages, fragments, enabled=True), fragments


@pytest.mark.parametrize(
    "formatting",
    [
        "**{}**",
        "__{}__",
        "*{}*",
        "`{}`",
        "> {}",
        "- {}",
        "## {}",
        "<strong>{}</strong>",
        "单位：**{}**",
    ],
)
def test_unit_conflict_in_markdown_keeps_both_source_tables(formatting: str) -> None:
    if formatting.startswith("单位"):
        first, second = formatting.format("米"), formatting.format("厘米")
    else:
        first, second = formatting.format("单位：米"), formatting.format("单位：厘米")
    content, fragments = _assemble([first + "\n\n", second + "\n\n"])

    assert "logical-table:" not in "".join(content.values())
    assert fragments[0].markdown in content[1]
    assert fragments[1].markdown in content[2]
    assert first in content[1] and second in content[2]


@pytest.mark.parametrize("new_text", ["数据集乙", "换用另一种统计口径。", "【观察组乙】"])
def test_unproven_new_table_prelude_is_a_boundary(new_text: str) -> None:
    content, fragments = _assemble(["数据集甲\n\n", new_text + "\n\n"])

    assert "logical-table:" not in "".join(content.values())
    assert all(fragment.markdown in content[fragment.page_number] for fragment in fragments)


def test_new_numbered_context_is_not_erased_as_list_decoration() -> None:
    content, fragments = _assemble(["1. 观察样本\n\n", "2. 观察样本\n\n"])

    assert "logical-table:" not in "".join(content.values())
    assert fragments[0].markdown in content[1]
    assert fragments[1].markdown in content[2]


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("观察_A_B", "观察AB"),
        ("单位：m_2_s", "单位：m2s"),
        (r"单位：\*米\*", "单位：米"),
        ("单位：&lt;strong&gt;米&lt;/strong&gt;", "单位：米"),
        ("观察&lt;strong&gt;米&lt;/strong&gt;", "观察米"),
        (r"单位：\<strong\>米\</strong\>", "单位：米"),
        (r"单位\：米", "单位：米"),
        ("单位：<measurement>米</measurement>", "单位：&lt;measurement&gt;米&lt;/measurement&gt;"),
    ],
)
def test_literal_markdown_characters_never_create_false_context_equivalence(
    left: str, right: str
) -> None:
    content, fragments = _assemble([left + "\n\n", right + "\n\n"])

    assert "logical-table:" not in "".join(content.values())
    assert all(fragment.markdown in content[fragment.page_number] for fragment in fragments)
    assert left in content[1] and right in content[2]


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (r"单位：m\_2\_s", "单位：`m_2_s`"),
        (r"单位：\*米\*", "单位：`*米*`"),
        (r"单位\:米", "单位:米"),
        ("单位：<strong>米</strong>", "单位：**米**"),
        ("观察**A**B", "观察AB"),
    ],
)
def test_real_markdown_visible_text_can_prove_repeated_source_context(
    left: str, right: str
) -> None:
    content, fragments = _assemble([left + "\n\n", right + "\n\n"])

    assert "table_p1_t1_p2_t1" in content[1]
    assert all(fragment.rows[-1][0] in content[1] for fragment in fragments)
    assert left in content[1] and right in content[2]


@pytest.mark.parametrize("tail", ["另一个观察区", "单位：厘米", "**单位：厘米**"])
def test_unproven_left_page_tail_cannot_change_continuation_scope(tail: str) -> None:
    fragments = [_fragment(1), _fragment(2)]
    pages = [
        PageParseResult(page_number=1, content=fragments[0].rendered + "\n\n" + tail),
        PageParseResult(page_number=2, content=fragments[1].rendered),
    ]

    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert "logical-table:" not in "".join(content.values())
    assert all(fragment.markdown in content[fragment.page_number] for fragment in fragments)
    assert content[1].endswith(tail)


@pytest.mark.parametrize("tail", ["\n\n", "\n\n<!-- page: 1 -->\n\n"])
def test_empty_left_tail_and_explicit_page_markers_allow_continuation(tail: str) -> None:
    fragments = [_fragment(1), _fragment(2)]
    pages = [
        PageParseResult(page_number=1, content=fragments[0].rendered + tail),
        PageParseResult(page_number=2, content=fragments[1].rendered),
    ]

    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert "table_p1_t1_p2_t1" in content[1]
    assert all(fragment.rows[-1][0] in content[1] for fragment in fragments)


@pytest.mark.parametrize("right", ["已有局部文字", "已有局部文字\n\n完整观察范围"])
def test_partial_or_reordered_prelude_does_not_prove_same_context(right: str) -> None:
    content, fragments = _assemble(["完整观察范围\n\n已有局部文字\n\n", right + "\n\n"])

    assert "logical-table:" not in "".join(content.values())
    assert all(fragment.markdown in content[fragment.page_number] for fragment in fragments)


def test_source_caption_can_repeat_without_other_prior_page_context() -> None:
    fragments = [_fragment(1), _fragment(2)]
    for fragment in fragments:
        fragment.caption = "明确来源表题"
    pages = [
        PageParseResult(
            page_number=1, content="来源文档\n\n明确来源表题\n\n" + fragments[0].rendered
        ),
        PageParseResult(page_number=2, content="明确来源表题\n\n" + fragments[1].rendered),
    ]

    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert "table_p1_t1_p2_t1" in content[1]
    assert all(fragment.rows[-1][0] in content[1] for fragment in fragments)


def test_repeated_source_context_and_same_unit_formatting_can_continue() -> None:
    prefixes = [
        "设备清单\n\n单位：件 币种：人民币\n\n",
        "设备清单\n\n**单位：件** 币种：人民币\n\n",
        "设备清单\n\n",
        "设备清单\n\n`单位：件 币种：人民币`\n\n",
    ]
    content, fragments = _assemble(prefixes)

    assert "table_p1_t1_p4_t1; source-pages: 1,2,3,4" in content[1]
    assert content[1].count("| 类别 | 数量 |") == 1
    assert all(fragment.rows[-1][0] in content[1] for fragment in fragments)
    assert "source-page: 4; source-rows: 2; logical-rows: 5-5" in content[1]


def test_new_unit_cannot_inherit_an_unknown_prior_scope() -> None:
    content, _ = _assemble(["", "**单位：件**\n\n"])

    assert "logical-table:" not in "".join(content.values())


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("单位：米", "单位：厘米\n\n单位：米"),
        ("单位：厘米\n\n单位：米", "单位：米"),
        ("单位：厘米\n\n单位：米", "单位：厘米\n\n单位：米"),
        ("单位：米", "单位：厘米 单位：米"),
        ("单位：厘米 单位：米", "单位：厘米 单位：米"),
        ("单位：米\n币种：人民币\n币种：美元", "单位：米\n币种：美元"),
        ("单位：", ""),
        ("单位：米", "单位：米 单位："),
    ],
)
def test_conflicting_or_unknown_unit_declarations_preserve_both_tables(
    left: str, right: str
) -> None:
    content, fragments = _assemble([left + "\n\n", right + "\n\n"])

    assert "logical-table:" not in "".join(content.values())
    assert all(fragment.markdown in content[fragment.page_number] for fragment in fragments)
    assert content[1].startswith(left) and content[2].startswith(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("单位：米", "单位：米\n\n单位：米"),
        ("单位：米\n\n单位：米", "单位：米"),
        ("单位：米", "单位：米 单位：米"),
        ("单位：米 单位：米", "单位：米"),
        ("单位：米 币种：人民币", "单位：米 币种：人民币 币种：人民币"),
    ],
)
def test_repeated_identical_unit_declarations_allow_continuation(left: str, right: str) -> None:
    content, fragments = _assemble([left + "\n\n", right + "\n\n"])

    assert "table_p1_t1_p2_t1" in content[1]
    assert all(fragment.rows[-1][0] in content[1] for fragment in fragments)
    assert content[1].startswith(left) and content[2].startswith(right)


def _source_document(captions: list[str | None]) -> DoclingDocument:
    document = DoclingDocument(name="caption-provenance")
    for page, caption_text in enumerate(captions, start=1):
        document.add_page(page_no=page, size=Size(width=600, height=800))
        provenance = ProvenanceItem(
            page_no=page,
            bbox=BoundingBox(l=60, t=16, r=540, b=776, coord_origin=CoordOrigin.TOPLEFT),
            charspan=(0, 0),
        )
        caption = (
            document.add_text(label=DocItemLabel.CAPTION, text=caption_text, prov=provenance)
            if caption_text is not None
            else None
        )
        rows = [["类别", "数量"], [f"来源 {page}", str(page * 100)]]
        document.add_table(
            caption=caption,
            prov=provenance,
            data=TableData(
                num_rows=2,
                num_cols=2,
                table_cells=[
                    TableCell(
                        start_row_offset_idx=row,
                        end_row_offset_idx=row + 1,
                        start_col_offset_idx=column,
                        end_col_offset_idx=column + 1,
                        text=text,
                        column_header=row == 0,
                    )
                    for row, values in enumerate(rows)
                    for column, text in enumerate(values)
                ],
            ),
        )
    return document


@pytest.mark.parametrize(
    ("captions", "should_merge"),
    [
        (["来源表甲", "来源表乙"], False),
        (["来源表甲", None], True),
        ([None, "来源表乙"], False),
        (["来源表甲", "来源表甲"], True),
        (["来源表甲", None, "来源表甲"], True),
        (["来源表甲", None, "来源表乙"], False),
    ],
)
def test_source_caption_refs_govern_scope_without_changing_cells(
    captions: list[str | None], should_merge: bool
) -> None:
    document = _source_document(captions)
    fragments = extract_table_fragments(document, (1, len(captions)))
    original = deepcopy([(fragment.rows, fragment.cells) for fragment in fragments])
    pages = [
        PageParseResult(
            page_number=page,
            content=export_page_markdown(
                document, page, [fragment for fragment in fragments if fragment.page_number == page]
            ),
        )
        for page in range(1, len(captions) + 1)
    ]

    assert [fragment.caption for fragment in fragments] == captions
    content = assemble_logical_tables(pages, fragments, enabled=True)

    if should_merge:
        assert f"table_p1_t1_p{len(captions)}_t1" in content[1]
        assert content[1].count("| 类别 | 数量 |") == 1
        assert all(fragment.rows[-1][0] in content[1] for fragment in fragments)
    else:
        assert f"table_p1_t1_p{len(captions)}_t1" not in content[1]
        assert fragments[-1].markdown in content[len(captions)]
        if len(captions) == 2:
            assert "logical-table:" not in "".join(content.values())
            assert fragments[0].markdown in content[1]
    assert [(fragment.rows, fragment.cells) for fragment in fragments] == original
    assert all(caption in "".join(content.values()) for caption in captions if caption)


@pytest.mark.parametrize("caption_ref", ["#/texts/9999", "#/groups/9999"])
def test_unresolved_source_caption_cannot_authorize_header_removal(caption_ref: str) -> None:
    document = _source_document([None, None])
    document.tables[1].captions = [RefItem(cref=caption_ref)]

    fragments = extract_table_fragments(document, (1, 2))

    assert fragments[1].caption_scope_complete is False
    assert link_cross_page_tables(fragments) == []
    assert fragments[1].rows[-1] == ["来源 2", "200"]
