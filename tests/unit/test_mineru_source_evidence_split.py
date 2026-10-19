"""Without independent parsing, unknown native evidence keeps physical tables intact."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.models.parse_result import PageParseResult
from app.parsers.mineru_native_remote import render_mineru_page_evidence
from app.services.table_service import (
    TableFragment,
    assemble_logical_tables,
    link_cross_page_tables,
)


def _native_pages(*, header_tag: str = "th") -> tuple[list[PageParseResult], list[TableFragment]]:
    pages, fragments = [], []
    for number, label, value in ((1, "营业收入", "100"), (2, "净利润", "60")):
        markup = (
            f"<table><tr><{header_tag}>项目</{header_tag}>"
            f"<{header_tag}>本报告期</{header_tag}></tr>"
            f"<tr><td>{label}</td><td>{value}</td></tr></table>"
        )
        content, tables, _, _ = render_mineru_page_evidence(
            {
                "page_number": number,
                "blocks": [
                    {
                        "type": "table",
                        "markdown": markup,
                        "bbox": [0.1, 0.03, 0.9, 0.96],
                        "content": [
                            {
                                "type": "table_body",
                                "markdown": markup,
                                "content": markup,
                                "bbox": [0.1, 0.03, 0.9, 0.96],
                            }
                        ],
                    }
                ],
            }
        )
        pages.append(PageParseResult(page_number=number, content=content))
        fragments.extend(tables)
    return pages, fragments


def _assert_complete_split(pages: list[PageParseResult], fragments: list[TableFragment]) -> None:
    original_rows = deepcopy([fragment.rows for fragment in fragments])
    original_content = [page.content for page in pages]
    assert all(not fragment.header_verification_required for fragment in fragments)
    assert link_cross_page_tables(fragments) == []

    assembled = assemble_logical_tables(pages, fragments, enabled=True)

    assert "logical-table:" not in "\n".join(assembled.values())
    for index, (page, fragment) in enumerate(zip(pages, fragments, strict=True)):
        output = assembled[page.page_number]
        assert fragment._table_rendering in output
        assert f"table-fragment: {fragment.fragment_id}" in output
        assert (
            f"table-source: {fragment.fragment_id}; source-page: {page.page_number}; "
            "source-rows: 1-2; logical-rows: 1-2; repeated-header-rows: 0"
        ) in output
        assert fragment.rows == original_rows[index]
        assert fragment.logical_table_id is None
        assert page.content == original_content[index]
    assert sum(value.count("| 项目 | 本报告期 |") for value in assembled.values()) == 2
    assert "| 营业收入 | 100 |" in assembled[1]
    assert "| 净利润 | 60 |" in assembled[2]


@pytest.mark.parametrize("header_tag", ["td", "th"])
def test_real_native_evidence_keeps_all_rows_without_independent_parser(header_tag: str) -> None:
    pages, fragments = _native_pages(header_tag=header_tag)

    assert all(fragment.column_boundaries == [] for fragment in fragments)
    assert all(not fragment.caption_scope_complete for fragment in fragments)
    assert all(fragment.header_scope_complete == (header_tag == "th") for fragment in fragments)
    _assert_complete_split(pages, fragments)


@pytest.mark.parametrize("missing", ["header", "column_geometry", "caption_scope"])
def test_each_missing_source_evidence_dimension_prevents_header_removal(missing: str) -> None:
    pages, fragments = _native_pages(header_tag="td" if missing == "header" else "th")
    for fragment in fragments:
        if missing != "column_geometry":
            fragment.column_boundaries = [0.1, 0.5, 0.9]
        if missing != "caption_scope":
            fragment.caption_scope_complete = True

    _assert_complete_split(pages, fragments)


def test_complete_existing_source_evidence_can_still_merge_without_another_parser() -> None:
    pages, fragments = _native_pages()
    for fragment in fragments:
        fragment.column_boundaries = [0.1, 0.5, 0.9]
        fragment.caption_scope_complete = True
    assert all(not fragment.header_verification_required for fragment in fragments)

    assembled = assemble_logical_tables(pages, fragments, enabled=True)

    assert assembled[1].count("| 项目 | 本报告期 |") == 1
    assert "| 营业收入 | 100 |" in assembled[1]
    assert "| 净利润 | 60 |" in assembled[1]
    assert "source-pages: 1,2" in assembled[1]
    assert "source-rows: 2; logical-rows: 3-3; repeated-header-rows: 1" in assembled[1]
    assert assembled[2] == ""


@pytest.mark.parametrize("context", ["new_title", "body_after_table"])
def test_complete_headers_do_not_override_new_source_context(context: str) -> None:
    pages, fragments = _native_pages()
    for fragment in fragments:
        fragment.column_boundaries = [0.1, 0.5, 0.9]
        fragment.caption_scope_complete = True
    if context == "new_title":
        pages[1].content = "## 另一张表\n\n" + (pages[1].content or "")
    else:
        pages[0].content = (pages[0].content or "") + "\n\n独立业务说明。"

    # Header/geometry candidates alone cannot remove any row during assembly.
    assert link_cross_page_tables(fragments) == [fragments]
    assembled = assemble_logical_tables(pages, fragments, enabled=True)
    assert "logical-table:" not in "\n".join(assembled.values())
    assert sum(value.count("| 项目 | 本报告期 |") for value in assembled.values()) == 2
    assert all(fragment.markdown in assembled[fragment.page_number] for fragment in fragments)
    assert all(fragment.logical_table_id is None for fragment in fragments)
