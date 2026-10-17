"""Visible source content survives floating-item and furniture classifications."""

from __future__ import annotations

from copy import deepcopy

import pytest
from docling_core.types.doc import (
    BoundingBox,
    ContentLayer,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)

from app.models import PageParseResult
from app.services.table_service import (
    assemble_logical_tables,
    export_page_markdown,
    extract_table_fragments,
)


def _prov(page: int, top: float = 100, bottom: float = 150) -> ProvenanceItem:
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(l=60, t=top, r=540, b=bottom, coord_origin=CoordOrigin.TOPLEFT),
        charspan=(0, 0),
    )


def _document(pages: int = 2) -> DoclingDocument:
    document = DoclingDocument(name="source-owned-content")
    for page in range(1, pages + 1):
        document.add_page(page_no=page, size=Size(width=600, height=800))
    return document


def _table(document: DoclingDocument, page: int):  # type: ignore[no-untyped-def]
    rows = [["类别", "数量"], [f"源行{page}", str(100 * page)]]
    return document.add_table(
        prov=_prov(page, 16, 776),
        data=TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                TableCell(
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=column,
                    end_col_offset_idx=column + 1,
                    text=value,
                    column_header=row == 0,
                )
                for row, values in enumerate(rows)
                for column, value in enumerate(values)
            ],
        ),
    )


def _export(document: DoclingDocument):  # type: ignore[no-untyped-def]
    fragments = extract_table_fragments(document, (1, len(document.pages)))
    pages = [
        PageParseResult(
            page_number=page,
            content=export_page_markdown(document, page, fragments),
        )
        for page in document.pages
    ]
    return pages, fragments


@pytest.mark.parametrize("label", [DocItemLabel.FOOTNOTE, DocItemLabel.TEXT])
def test_attached_business_text_is_emitted_once_in_source_reading_order(label) -> None:  # type: ignore[no-untyped-def]
    document = _document(1)
    document.add_text(label=DocItemLabel.TEXT, text="表前正文", prov=_prov(1, 50, 60))
    table = _table(document, 1)
    note = document.add_text(
        label=label, text="下一节完整业务段落及否定结论。", parent=table, prov=_prov(1, 400, 450)
    )
    table.footnotes = [note.get_ref()]
    document.add_text(label=DocItemLabel.TEXT, text="后续正文", prov=_prov(1, 500, 550))
    source_before = deepcopy(document.model_dump())

    pages, fragments = _export(document)
    content = assemble_logical_tables(pages, fragments, enabled=True)[1]

    assert content.count(note.text) == 1
    assert content.index("表前正文") < content.index("| 类别 | 数量 |")
    assert content.index("| 源行1 | 100 |") < content.index(note.text) < content.index("后续正文")
    assert f"source-text: {note.self_ref}; source-page: 1; role: footnote" in content
    assert document.model_dump() == source_before


def test_attached_note_on_next_page_keeps_its_own_source_page() -> None:
    document = _document()
    table = _table(document, 1)
    note = document.add_text(
        label=DocItemLabel.FOOTNOTE, text="跨页的可见附属说明。", parent=table, prov=_prov(2)
    )
    table.footnotes = [note.get_ref()]

    pages, fragments = _export(document)
    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert note.text not in content[1]
    assert content[2].count(note.text) == 1
    assert "source-page: 2; role: footnote" in content[2]
    assert "table-fragment:" not in content[2]


def test_visible_table_in_furniture_layer_keeps_its_source_grid() -> None:
    document = _document(1)
    table = _table(document, 1)
    table.content_layer = ContentLayer.FURNITURE

    pages, fragments = _export(document)

    assert len(fragments) == 1
    assert "| 类别 | 数量 |" in (pages[0].content or "")
    assert "| 源行1 | 100 |" in (pages[0].content or "")
    assert 'source_pages":[1]' in (pages[0].content or "")


@pytest.mark.parametrize(
    "layer", [ContentLayer.BACKGROUND, ContentLayer.INVISIBLE, ContentLayer.NOTES]
)
def test_hidden_or_author_note_layers_are_not_released(layer: ContentLayer) -> None:
    document = _document(1)
    table = _table(document, 1)
    note = document.add_text(
        label=DocItemLabel.FOOTNOTE,
        text="非原件可见正文",
        parent=table,
        prov=_prov(1),
        content_layer=layer,
    )
    caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text="隐藏的表题",
        parent=table,
        prov=_prov(1),
        content_layer=layer,
    )
    table.footnotes = [note.get_ref()]
    table.captions = [caption.get_ref()]

    pages, _ = _export(document)

    assert note.text not in (pages[0].content or "")
    assert caption.text not in (pages[0].content or "")


def test_header_and_footer_are_preserved_without_any_table() -> None:
    document = _document(1)
    for label, text, top in [
        (DocItemLabel.PAGE_HEADER, "证券代码：000123", 12),
        (DocItemLabel.TEXT, "正文内容", 100),
        (DocItemLabel.PAGE_FOOTER, "1", 760),
    ]:
        document.add_text(
            label=label,
            text=text,
            prov=_prov(1, top, top + 10),
            content_layer=(
                ContentLayer.BODY if label == DocItemLabel.TEXT else ContentLayer.FURNITURE
            ),
        )

    content = export_page_markdown(document, 1, [])

    assert content.index("证券代码：000123") < content.index("正文内容") < content.rindex("1")
    assert "source-page: 1; role: page_header" in content
    assert "source-page: 1; role: page_footer" in content


def test_unpaginated_docling_document_retains_existing_page_filter_semantics() -> None:
    # Direct Word/HTML documents have no PDF page provenance. The existing
    # page-specific interface never claimed those items belonged to page 1.
    # Keep its behavior unchanged rather than assigning a fabricated page.
    document = DoclingDocument(name="unpaginated")
    document.add_text(label=DocItemLabel.TEXT, text="无物理页依据的正文")

    assert document.export_to_markdown() == "无物理页依据的正文"
    assert export_page_markdown(document, 1, []) == document.export_to_markdown(page_no=1) == ""


def test_real_serializer_failure_is_reported_instead_of_silent_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from docling_core.transforms.serializer.markdown import MarkdownTextSerializer

    document = _document(1)
    document.add_text(label=DocItemLabel.TEXT, text="可见正文", prov=_prov(1))

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValueError("explicit serializer failure")

    monkeypatch.setattr(MarkdownTextSerializer, "serialize", fail)

    with pytest.raises(ValueError, match="explicit serializer failure"):
        export_page_markdown(document, 1, [])


def _continuation(
    *,
    headers: tuple[str, str] = ("文档重复页眉", "文档重复页眉"),
    footers: tuple[str, str] = ("1", "2"),
    extra_label: DocItemLabel | None = None,
):  # type: ignore[no-untyped-def]
    document = _document()
    for page in (1, 2):
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text=headers[page - 1],
            prov=_prov(page, 2, 12),
            content_layer=ContentLayer.FURNITURE,
        )
        _table(document, page)
        if extra_label is not None and page == 1:
            document.add_text(
                label=extra_label,
                text="不能当作装饰忽略的业务正文。",
                prov=_prov(page, 700, 720),
                content_layer=ContentLayer.FURNITURE,
            )
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=footers[page - 1],
            prov=_prov(page, 780, 790),
            content_layer=ContentLayer.FURNITURE,
        )
    return document


def test_proven_repeated_furniture_does_not_break_a_normal_continuation() -> None:
    pages, fragments = _export(_continuation())
    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert "logical-table: table_p1_t1_p2_t1" in content[1]
    assert content[1].count("| 类别 | 数量 |") == 1
    assert "| 源行2 | 200 |" in content[1]
    for page in (1, 2):
        assert "文档重复页眉" in content[page]
        assert f"source-page: {page}; role: page_footer" in content[page]
    assert "source-rows: 2; logical-rows: 3-3; repeated-header-rows: 1" in content[1]


def test_hierarchical_pagination_needs_three_consecutive_source_pages() -> None:
    document = _document(3)
    for page in (1, 2, 3):
        _table(document, page)
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=f"4 - 2 - {page + 6}",
            prov=_prov(page, 780, 790),
            content_layer=ContentLayer.FURNITURE,
        )

    pages, fragments = _export(document)
    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert "logical-table: table_p1_t1_p3_t1" in content[1]
    assert "| 源行3 | 300 |" in content[1]
    assert all(f"4 - 2 - {page + 6}" in content[page] for page in (1, 2, 3))


def test_independent_page_conversions_share_source_pagination_evidence_at_assembly() -> None:
    pages = []
    fragments = []
    for page in (4, 5, 6):
        # Each converter receives exactly one physical page, as the production
        # parallel path does. Local self_ref IDs consequently repeat.
        document = DoclingDocument(name=f"independent-page-{page}")
        document.add_page(page_no=page, size=Size(width=600, height=800))
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text="完整相同的原件页眉",
            prov=_prov(page, 2, 12),
            content_layer=ContentLayer.FURNITURE,
        )
        _table(document, page)
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text=f"4 - 2 - {page + 6}",
            prov=_prov(page, 780, 790),
            content_layer=ContentLayer.FURNITURE,
        )
        source_fragments = extract_table_fragments(document, (page, page))
        pages.append(
            PageParseResult(
                page_number=page,
                content=export_page_markdown(document, page, source_fragments),
            )
        )
        fragments.extend(source_fragments)

    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert "logical-table: table_p4_t1_p6_t1" in content[4]
    assert "| 源行6 | 600 |" in content[4]
    assert all(f"4 - 2 - {page + 6}" in content[page] for page in (4, 5, 6))
    assert all(f"source-page: {page}; role: page_header" in content[page] for page in (4, 5, 6))


def test_repeated_furniture_unit_cannot_hide_a_conflicting_body_unit() -> None:
    document = _document()
    for page in (1, 2):
        document.add_text(label=DocItemLabel.TEXT, text="单位：元", prov=_prov(page, 2, 12))
        _table(document, page)
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text="单位：万元",
            prov=_prov(page, 780, 790),
            content_layer=ContentLayer.FURNITURE,
        )

    pages, fragments = _export(document)
    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert "logical-table:" not in "".join(content.values())
    for page in (1, 2):
        assert "单位：元" in content[page]
        assert "单位：万元" in content[page]
        assert fragments[page - 1].markdown in content[page]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"headers": ("第一张表的表题", "误分类为页眉的新表题")},
        {"headers": ("2026年度", "2025年度")},
        {"footers": ("单位：元", "单位：万元")},
        {"footers": ("1", "999")},
        {"footers": ("4 - 2 - 1", "4 - 2 - 2")},
        {"footers": ("2026-6-1", "2026-6-2")},
        {"extra_label": DocItemLabel.TEXT},
        {"extra_label": DocItemLabel.FOOTNOTE},
    ],
)
def test_furniture_classification_cannot_hide_new_business_scope(kwargs: dict) -> None:
    pages, fragments = _export(_continuation(**kwargs))
    before = deepcopy([fragment.rows for fragment in fragments])
    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert "logical-table:" not in "".join(content.values())
    assert all(fragment.markdown in content[fragment.page_number] for fragment in fragments)
    assert before == [fragment.rows for fragment in fragments]


def test_attached_note_between_pages_is_a_real_continuity_boundary() -> None:
    document = _continuation()
    note = document.add_text(
        label=DocItemLabel.FOOTNOTE,
        text="原件业务说明，应结束当前表范围。",
        parent=document.tables[0],
        prov=_prov(1, 700, 720),
    )
    document.tables[0].footnotes = [note.get_ref()]

    pages, fragments = _export(document)
    content = assemble_logical_tables(pages, fragments, enabled=True)

    assert note.text in content[1]
    assert "logical-table:" not in "".join(content.values())
