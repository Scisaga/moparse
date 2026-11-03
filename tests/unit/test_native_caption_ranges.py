"""Native-only public conversion of bounded scalar-table fragments.

The fixtures declare their text and positions before conversion. No expected
corpus, evaluation module, PDF evidence or parser model is available.
"""

import re
from copy import deepcopy
from dataclasses import replace

import pytest

from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from app.parsers.mineru_native_remote import render_mineru_page_evidence
from app.services.table_context_service import prepare_native_table_scopes
from app.services.table_semantics_service import bind_table_view, render_semantic_view

FIRST = "<table><tr><td>Item</td><td>2027</td><td>2026</td><td>Change</td></tr><tr><td>Alpha</td><td>17</td><td>11</td><td>5%</td></tr></table>"
SECOND = "<table><tr><td colspan='4'>Per-unit measures:</td></tr><tr><td>Beta (元)</td><td>1.7</td><td>1.4</td><td>6%</td></tr></table>"


def source_table(markup):
    return {
        "type": "table",
        "bbox": [0.1, 0.1, 0.9, 0.4],
        "markdown": markup,
        "content": [{"type": "table_body", "content": markup, "markdown": markup}],
    }


def source_result(
    *, barrier=None, caption=True, scalar=True, producer_flag=None, repeated_furniture=False
):
    raw = {
        1: (
            [
                {"type": "table_caption", "content": "2027年经营指标"},
                {"type": "table_caption", "content": "（单位：元）"},
            ]
            if caption
            else []
        )
        + [source_table(FIRST)],
        2: ([barrier] if barrier else [])
        + [source_table(SECOND if scalar else SECOND.replace("1.7", "Approval is required."))],
    }
    if repeated_furniture:
        raw[1].insert(0, deepcopy(barrier))
    if producer_flag is not None:
        raw[2][-1]["continues_prev"] = producer_flag
    return result_from_blocks(raw)


@pytest.mark.parametrize("wide", [False, True])
@pytest.mark.parametrize("rows", [1, 2])
def test_leading_unfinished_continuation_text_is_retained_without_becoming_a_parent(wide, rows):
    lead = "<tr>" + ("<td colspan='4'>unfinished literal</td>" if wide else
                      "<td>unfinished literal</td><td></td><td></td><td></td>") + "</tr>"
    right = "<table>" + lead * rows + "<tr><td>Beta (元)</td><td>1.7</td><td>1.4</td><td>6%</td></tr></table>"
    result, fragments = result_from_blocks({
        1: [{"type": "table_caption", "content": "2027年经营指标"},
            {"type": "table_caption", "content": "（单位：元）"}, source_table(FIRST)],
        2: [source_table(right)],
    })
    original = deepcopy([(fragment.rows, fragment.cells) for fragment in fragments])
    prepare_native_table_scopes(result)
    assert not fragments[1].native_evidence["row_groups"]
    view = bind_table_view("right", [fragments[1]], fragments)
    text = render_semantic_view(view, fragments)
    assert view.status in {"partial", "retained"}
    if not wide:
        assert "inherited_header_scope" in fragments[1].native_evidence
        assert view.status == "partial" and "Beta (元)；2027：1.7" in text
    delivered = fragments[1].rendered if view.status == "retained" else text
    assert "unfinished literal" in delivered and "Beta (元)" in delivered and "1.7" in delivered
    assert "unfinished literal / Beta" not in text
    assert [(fragment.rows, fragment.cells) for fragment in fragments] == original


def result_from_blocks(raw):
    fragments, pages, furniture = [], [], []
    for page, blocks in raw.items():
        for block in blocks:
            block.setdefault("markdown", block.get("content", ""))
            block.setdefault("bbox", [0.1, 0.01, 0.9, 0.08])
        md, tables, _pictures, declared_furniture = render_mineru_page_evidence(
            {"page_number": page, "blocks": blocks}
        )
        pages.append(PageParseResult(page_number=page, content=md))
        fragments.extend(tables)
        furniture.extend(declared_furniture)
    result = DocumentParseResult(
        document_id="invented",
        filename="invented.pdf",
        mime_type="application/pdf",
        page_count=len(raw),
        processed_pages=len(raw),
        pipeline=ParsePipeline(profile="accurate", primary="mineru"),
        pages=pages,
    )
    result._table_fragments, result._native_page_blocks, result._page_furniture = (
        fragments,
        raw,
        furniture,
    )
    return result, fragments


def wordmark_result(right_header="ALPHABANK", *, bbox=(0.72, 0.04, 0.88, 0.06)):
    result, fragments = source_result(producer_flag=True)
    from app.services.table_service import PageFurnitureFragment

    left = PageFurnitureFragment(
        "brand1",
        1,
        "page_header",
        "A 星辰银行 ALPHA BANK",
        "<!-- source-furniture: brand1 -->\n\nA 星辰银行 ALPHA BANK",
        (0.7, 0.03, 0.9, 0.07),
    )
    right = PageFurnitureFragment(
        "brand2",
        2,
        "page_header",
        right_header,
        "<!-- source-furniture: brand2 -->\n\n" + right_header,
        bbox,
    )
    result._page_furniture = [left, right]
    for page, furniture in zip(result.pages, (left, right), strict=True):
        page.content = furniture.rendered + "\n\n" + page.content
    return result, fragments


@pytest.mark.parametrize("component", ["星辰银行", "ALPHABANK"])
def test_declared_continuation_recognizes_complete_split_wordmark_without_removing_public_text(
    component,
):
    result, fragments = wordmark_result(component)
    pages = [page.content for page in result.pages]
    prepare_native_table_scopes(result)
    view = bind_table_view("right", [fragments[1]], fragments)
    text = render_semantic_view(view, fragments)
    assert view.status == "converted" and "Beta (元)；2027：1.7" in text
    evidence = fragments[1].native_evidence["inherited_header_scope"]["furniture_evidence"]
    assert evidence[0]["literal_component"] == component
    assert [page.content for page in result.pages] == pages


@pytest.mark.parametrize(
    ("component", "bbox"),
    [
        ("星辰", (0.72, 0.04, 0.88, 0.06)),
        ("ALPHA", (0.72, 0.04, 0.88, 0.06)),
        ("A new business", (0.72, 0.04, 0.88, 0.06)),
        ("2027", (0.72, 0.04, 0.88, 0.06)),
        ("单位：元", (0.72, 0.04, 0.88, 0.06)),
        ("ALPHABANK", None),
        ("ALPHABANK", (0.72, 0.4, 0.88, 0.6)),
    ],
)
def test_incomplete_names_units_new_words_and_unproven_header_positions_remain_boundaries(
    component, bbox
):
    result, fragments = wordmark_result(component, bbox=bbox)
    prepare_native_table_scopes(result)
    assert "inherited_header_scope" not in fragments[1].native_evidence


def unit_only_result(*, flag=True, barrier=None, own_unit=None):
    left = "<table><tr><td>Distribution</td><td>17.25</td></tr></table>"
    right = "<table><tr><td>Annual profit</td><td>28.50</td></tr></table>"
    body = source_table(right)
    if flag is not None:
        body["continues_prev"] = flag
    raw = {
        1: [{"type": "table_caption", "content": "单位：元 币种：人民币"}, source_table(left)],
        2: ([barrier] if barrier else [])
        + ([{"type": "table_caption", "content": own_unit}] if own_unit else [])
        + [body],
    }
    return result_from_blocks(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [True, None])
async def test_unit_only_range_prints_original_legend_in_actual_delivery_without_inventing_headers(
    flag,
):
    from app.models import ContentParseOptions
    from app.models.content_result import (
        ContentLinks,
        ContentParseResult,
        ContentRenderings,
        ContentSource,
        ParseRuntime,
        SourceKind,
    )
    from app.services.export_service import ExportService
    from app.services.table_semantics_service import TableSemanticsService

    result, fragments = unit_only_result(flag=flag)
    cells = deepcopy([fragment.cells for fragment in fragments])
    views = []
    md, _ = ExportService().join_document(
        result.pages, preserve_page_breaks=True, table_fragments=fragments, public_views=views
    )
    result._table_views = views
    result.parse_result = ContentParseResult(
        units=[],
        runtime=ParseRuntime(
            profile="accurate", primary_backend="mineru", parser_version="synthetic"
        ),
        links=ContentLinks(
            job="/job", events="/events", result="/result", assets="/assets", bundle="/bundle"
        ),
        source=ContentSource(
            content_id="synthetic",
            source_sha256="0" * 64,
            filename="synthetic.pdf",
            mime_type="application/pdf",
            kind=SourceKind.PDF,
            size_bytes=1,
            unit_count=2,
            page_count=2,
        ),
        renderings=ContentRenderings(markdown=md),
    )
    await TableSemanticsService().apply(result, ContentParseOptions())
    final = result.parse_result.renderings.markdown
    public = re.sub(r"<!--.*?-->", "", final, flags=re.S)
    start = public.index("Annual profit")
    assert public[:start].rfind("单位：元 币种：人民币") > public.index("Distribution")
    assert "28.50" in final and [fragment.cells for fragment in fragments] == cells
    assert (
        fragments[1].native_evidence["continuation_unit_context"]["semantic_headers_inferred"]
        is False
    )
    assert "inherited_header_scope" not in fragments[1].native_evidence
    assert not fragments[1].source_header_scopes
    assert all(view.status == "retained" for view in result._semantic_tables)


@pytest.mark.parametrize("change", ["denied", "new_heading", "new_prose", "own_unit", "nonscalar"])
def test_unit_range_does_not_cross_business_boundaries_or_override_local_information(change):
    result, fragments = unit_only_result(
        flag=False if change == "denied" else None,
        barrier={
            "type": "title" if change == "new_heading" else "text",
            "content": "Another operation",
        }
        if change in {"new_heading", "new_prose"}
        else None,
        own_unit="单位：千元" if change == "own_unit" else None,
    )
    if change == "nonscalar":
        fragments[1].cells = [
            replace(cell, text="Approval required") if cell.column == 1 else cell
            for cell in fragments[1].cells
        ]
    prepare_native_table_scopes(result)
    assert "continuation_unit_context" not in fragments[1].native_evidence


@pytest.mark.parametrize(
    "change",
    [None, "different_total", "inconsistent_numerator", "date", "no_third_page", "unlocated"],
)
def test_unit_continuation_ignores_only_corroborated_fraction_style_page_footers(change):
    from app.services.table_service import PageFurnitureFragment

    result, fragments = unit_only_result()
    labels = ["11 / 80", "12 / 80", "13 / 80"]
    if change == "different_total":
        labels[1] = "12 / 81"
    elif change == "inconsistent_numerator":
        labels[1] = "17 / 80"
    elif change == "date":
        labels = ["2030/11/11", "2030/11/12", "2030/11/13"]
    elif change == "no_third_page":
        labels = labels[:2]
    furniture = [
        PageFurnitureFragment(
            f"footer{page}",
            page,
            "page_footer",
            text,
            f"<!-- source-furniture: footer{page} -->\n\n{text}",
            None if change == "unlocated" else (0.45, 0.94, 0.55, 0.96),
        )
        for page, text in enumerate(labels, 1)
    ]
    result._page_furniture = furniture
    for page, item in zip(result.pages, furniture, strict=False):
        page.content += "\n\n" + item.rendered
    if len(furniture) == 3:
        result.pages.append(PageParseResult(page_number=3, content=furniture[2].rendered))
        result.page_count = result.processed_pages = 3
    prepare_native_table_scopes(result)
    assert ("continuation_unit_context" in fragments[1].native_evidence) is (change is None)


def test_printed_caption_and_complete_native_measurement_paths_support_public_conversion():
    result, fragments = source_result()
    before = deepcopy([(fragment.rows, fragment.cells) for fragment in fragments])
    prepare_native_table_scopes(result)
    view = bind_table_view("right", [fragments[1]], fragments)
    text = render_semantic_view(view, fragments)
    assert view.status == "converted"
    assert "Beta (元)；2027：1.7" in text and "2026：1.4" in text and "Change：6%" in text
    assert fragments[1].source_continues_prev is None
    assert (
        fragments[1].native_evidence["inherited_header_scope"]["evidence_source"]
        == "native_literal_caption_range"
    )
    assert [(fragment.rows, fragment.cells) for fragment in fragments] == before
    assert view.records[0].values[0].column_headers[0].table_id == fragments[0].fragment_id


@pytest.mark.parametrize(
    "change",
    [
        None,
        "literal_total",
        "slash_in_record",
        "new_category",
        "wrong_amount",
        "prose_header",
        "new_caption",
        "denial",
    ],
)
def test_a_typed_category_can_continue_only_with_its_prior_literal_vocabulary(change):
    left = "<table><tr><td>Name</td><td>Relationship</td><td>Amount</td></tr><tr><td>Alpha</td><td>Member</td><td>17</td></tr><tr><td>Beta</td><td>Other</td><td>11</td></tr></table>"
    right = "<table><tr><td>Gamma</td><td>Other</td><td>8</td></tr></table>"
    if change in {"literal_total", "slash_in_record"}:
        right = right.replace(
            "</table>",
            f"<tr><td>{'Total' if change == 'literal_total' else 'Delta'}</td><td>/</td><td>/</td></tr></table>",
        )
    if change == "new_category":
        right = right.replace("Other", "Unseen")
    if change == "wrong_amount":
        right = right.replace(">8<", ">An unrelated sentence.<")
    if change == "prose_header":
        left = left.replace("Relationship", "Business narrative")
    raw = {
        1: [{"type": "table_caption", "content": "Unit: 元"}, source_table(left)],
        2: ([{"type": "title", "content": "A new division"}] if change == "new_caption" else [])
        + [source_table(right)],
    }
    if change == "denial":
        raw[2][-1]["continues_prev"] = False
    result, fragments = result_from_blocks(raw)
    source = deepcopy([(f.rows, f.cells) for f in fragments])
    prepare_native_table_scopes(result)
    assert ("inherited_header_scope" in fragments[1].native_evidence) is (
        change in {None, "literal_total"}
    )
    assert [(f.rows, f.cells) for f in fragments] == source
    if change in {None, "literal_total"}:
        text = render_semantic_view(bind_table_view("right", [fragments[1]], fragments), fragments)
        assert "Gamma" in text and "Relationship：Other" in text and "Amount：8" in text
        proof = fragments[1].native_evidence["inherited_header_scope"]["caption_range"][
            "literal_category_columns"
        ]
        assert proof[1]["header_cells"][0][2] == "Relationship"


@pytest.mark.parametrize(
    "barrier",
    [
        {"type": "title", "content": "Another operation"},
        {"type": "table_caption", "content": "2026年其他业务指标"},
        {"type": "text", "content": "（单位：千元）"},
        {"type": "text", "content": "The previous comparison has ended."},
        {"type": "image", "content": ""},
    ],
)
def test_native_caption_range_stops_before_new_business_content(barrier):
    result, fragments = source_result(barrier=barrier)
    prepare_native_table_scopes(result)
    assert "inherited_header_scope" not in fragments[1].native_evidence


@pytest.mark.parametrize("change", ["no_caption", "layout_prose", "producer_denial"])
def test_proximity_and_equal_columns_cannot_supply_missing_relations(change):
    result, fragments = source_result(
        caption=change != "no_caption",
        scalar=change != "layout_prose",
        producer_flag=False if change == "producer_denial" else None,
    )
    prepare_native_table_scopes(result)
    assert "inherited_header_scope" not in fragments[1].native_evidence


def test_declared_page_furniture_remains_text_but_does_not_create_a_business_boundary():
    result, fragments = source_result(
        barrier={"type": "header", "content": "Annual results"}, repeated_furniture=True
    )
    prepare_native_table_scopes(result)
    assert "inherited_header_scope" in fragments[1].native_evidence
    assert "Annual results" in result.pages[1].content


def test_a_single_header_classification_does_not_hide_a_new_business_title():
    result, fragments = source_result(barrier={"type": "header", "content": "New business title"})
    prepare_native_table_scopes(result)
    assert "inherited_header_scope" not in fragments[1].native_evidence


@pytest.mark.parametrize(
    "change", [None, "unseen_word", "different_position", "body_role", "explicit_denial"]
)
def test_a_caption_range_can_recognize_an_earlier_identical_header_piece_without_guessing_new_words(
    change,
):
    def header(text, bbox):
        return {"type": "header", "content": text, "bbox": bbox}

    small = [0.1, 0.02, 0.2, 0.06]
    raw = {
        1: [
            header(
                "xyz" if change != "unseen_word" else "abc",
                [0.6, 0.02, 0.7, 0.06] if change == "different_position" else small,
            )
        ],
        2: [
            header("星辰银行 ALPHA BANK", [0.1, 0.02, 0.5, 0.06]),
            {"type": "table_caption", "content": "单位：元"},
            source_table(FIRST),
        ],
        3: [
            header("xyz", small),
            header("星辰银行", [0.25, 0.02, 0.5, 0.04]),
            header("ALPHA BANK", [0.25, 0.04, 0.5, 0.06]),
            source_table(SECOND),
        ],
    }
    if change == "body_role":
        raw[1][0]["type"] = "text"
    if change == "explicit_denial":
        raw[3][-1]["continues_prev"] = False
    result, fragments = result_from_blocks(raw)
    pages = [page.content for page in result.pages]
    prepare_native_table_scopes(result)
    assert ("inherited_header_scope" in fragments[1].native_evidence) is (change is None)
    assert [page.content for page in result.pages] == pages
    if change is None:
        assert fragments[1].source_continues_prev is None
        proof = fragments[1].native_evidence["inherited_header_scope"]["furniture_evidence"]
        assert any(
            item["literal_component"] == "xyz"
            and item["preceding_source_ref"].startswith("mineru_p1_")
            for item in proof
        )
        text = render_semantic_view(bind_table_view("right", [fragments[1]], fragments), fragments)
        assert "Beta (元)；2027：1.7" in text
