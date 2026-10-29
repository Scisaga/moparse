"""Source-scoped relation coverage using authored structures, never corpus data."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.models import ContentParseOptions, DocumentParseResult, PageParseResult, ParsePipeline
from app.models.content_result import (
    ContentLinks,
    ContentParseResult,
    ContentRenderings,
    ContentSource,
    ParseRuntime,
    SourceKind,
)
from app.models.table_semantics import CellRef
from app.services.export_service import ExportService
from app.services.pdf_table_evidence_service import _field_candidates
from app.services.table_semantics_service import (
    TableSemanticsService,
    bind_table_view,
    render_semantic_view,
    retained_table_parts,
)
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows


def bound_table(rows: list[list[str]], *, headers=(), body=None, name="source") -> TableFragment:
    cells = [TableCellFragment(r, c, 1, 1, text)
             for r, row in enumerate(rows) for c, text in enumerate(row)]
    markdown = render_gfm_rows(rows)
    fragment = TableFragment(name, 1, 1, (0.1, 0.1, 0.9, 0.9), len(rows), len(rows[0]),
                             deepcopy(rows), [], markdown, markdown, cells=cells)
    if headers:
        fragment.source_header_scopes = [{
            "header_rows": list(headers), "body_rows": list(body if body is not None else range(max(headers) + 1, len(rows))),
            "complete": True, "evidence_source": "authored_source_scope",
        }]
    refresh_source(fragment)
    return fragment


def refresh_source(fragment: TableFragment) -> None:
    fragment.pdf_evidence = {"bound": True, "content_kind": "data_table", "source_cells": [
        {"row": c.row, "column": c.column, "row_span": c.row_span,
         "column_span": c.column_span, "text": c.text, "shaded": False}
        for c in fragment.cells
    ]}


def merge(fragment: TableFragment, row: int, col: int, rowspan=1, colspan=1) -> None:
    anchor = next(c for c in fragment.cells if (c.row, c.column) == (row, col))
    anchor.row_span, anchor.column_span = rowspan, colspan
    covered = {(r, c) for r in range(row, row + rowspan) for c in range(col, col + colspan)}
    fragment.cells = [c for c in fragment.cells
                      if (c.row, c.column) == (row, col) or (c.row, c.column) not in covered]
    refresh_source(fragment)


def test_complete_multilevel_headers_keep_parent_period_and_leaf_distinctions():
    fragment = bound_table([
        ["Item", "2024", ""], ["", "Revenue", "Cost"], ["Alpha", "11", "7"],
    ], headers=[0, 1])
    merge(fragment, 0, 0, rowspan=2)
    merge(fragment, 0, 1, colspan=2)
    before = deepcopy(fragment)
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "converted"
    assert len(view.records[0].values[0].column_headers) == 2
    assert view.records[0].values[0].period_refs == (CellRef("source", 0, 1),)
    rendered = render_semantic_view(view, [fragment])
    assert "2024 / Revenue：11" in rendered and "2024 / Cost：7" in rendered
    assert fragment == before


def test_explicit_row_group_columns_preserve_shared_source_subject_scope():
    fragment = bound_table([
        ["Region", "Metric", "2024"], ["North", "Revenue", "11"], ["", "Cost", "7"],
    ], headers=[0])
    merge(fragment, 1, 0, rowspan=2)
    fragment.source_header_scopes[0]["row_header_columns"] = [0, 1]
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "converted" and len(view.records) == 2
    assert all(r.row_groups == (CellRef("source", 1, 0),) for r in view.records)
    assert view.records[1].values[0].row_headers == (CellRef("source", 1, 0), CellRef("source", 2, 1))
    rendered = render_semantic_view(view, [fragment])
    assert "North / Revenue" in rendered and "North / Cost" in rendered
    assert "Region / Metric" in rendered
    assert view.covered_source_cells == len(fragment.cells)


def test_explicit_nonfirst_subject_column_keeps_index_as_a_value_not_a_group():
    fragment = bound_table([["Index", "Name", "Amount"], ["1", "Alpha", "111"]], headers=[0])
    fragment.source_header_scopes[0]["row_header_columns"] = [1]
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "converted"
    assert not view.records[0].row_groups
    assert view.records[0].subject == CellRef("source", 1, 1)
    assert view.records[0].values[0].value == CellRef("source", 1, 0)
    rendered = render_semantic_view(view, [fragment])
    assert "Name：Alpha；Index：1；Amount：111" in rendered


def test_bound_but_unclassified_two_column_prose_does_not_create_field_relations():
    fragment = bound_table([["First independent paragraph.", "Second independent paragraph."],
                            ["Third independent paragraph.", "Fourth independent paragraph."]])
    fragment.pdf_evidence["content_kind"] = "unknown"
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "retained" and not view.records


def test_shaded_long_grid_prose_without_independent_field_scope_is_not_verbalized():
    fragment = bound_table([
        ["The following paragraphs describe independent contractual responsibilities.",
         "This neighboring paragraph describes an independent condition and its exception."],
        ["Another paragraph has a source background color for layout emphasis.",
         "A number such as 100 here does not make this prose a field/value record."],
    ])
    fragment.pdf_evidence["content_kind"] = "unknown"
    for cell in fragment.pdf_evidence["source_cells"]:
        cell["shaded"] = cell["column"] == 0
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "retained" and not view.records


def test_explicit_layout_grid_is_never_interpreted_using_header_or_field_layout():
    fragment = bound_table([["Label", "Text"], ["Paragraph", "100"]], headers=[0])
    fragment.pdf_evidence["content_kind"] = "layout_grid"
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "retained"
    assert view.reason_codes == ("layout_grid_not_semantic_table",)


def test_unshaded_fields_require_a_complete_independently_evidenced_local_pair():
    fragment = bound_table([["Company:", "Acme"], ["Date:", "2025-01-01"]])
    fragment.pdf_evidence["field_scopes"] = [{
        "body_rows": [r], "pairs": [{"label": [r, 0], "value": [r, 1]}],
        "complete": True, "evidence_source": "authored_source_delimiters",
        "evidence": {"explicit_label_delimiters": True},
    } for r in range(2)]
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "converted"
    rendered = render_semantic_view(view, [fragment])
    assert "Company:Acme" in rendered and "Date:2025-01-01" in rendered
    assert "Company:：" not in rendered
    del fragment.pdf_evidence["field_scopes"][1]["evidence_source"]
    partial = bind_table_view("view", [fragment], [fragment])
    assert partial.status == "partial" and len(partial.records) == 1
    assert ("source", 1) in partial.retained_rows


def test_source_typed_styled_name_field_scope_is_used_without_requiring_numbers():
    fragment = bound_table([["联系人", "张三"]])
    cells = fragment.pdf_evidence["source_cells"]
    cells[0]["bold"] = True
    fragment.pdf_evidence["field_scopes"] = _field_candidates(fragment.pdf_evidence, 1)
    assert fragment.pdf_evidence["field_scopes"][0]["evidence"]["explicit_field_label_type"]
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "converted"
    assert "联系人：张三" in render_semantic_view(view, [fragment])


def test_one_unresolved_row_preserves_supported_neighbors_once_and_in_order():
    fragment = bound_table([
        ["Item", "Value"], ["Alpha", "111"], ["", "222"], ["Beta", "333"],
    ], headers=[0])
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "partial"
    assert [r.source_row for r in view.records] == [1, 3]
    rendered = render_semantic_view(view, [fragment])
    assert rendered.count("111") == rendered.count("222") == rendered.count("333") == 1
    assert rendered.index("111") < rendered.index("222") < rendered.index("333")
    parts = retained_table_parts(view, [fragment])
    assert len(parts) == 1 and parts[0]["source_rows"] == [0, 2]
    assert parts[0]["source_to_display_rows"] == {0: 1, 2: 2}
    assert parts[0]["synthetic_header_rows"] == [0]
    assert parts[0]["header_rows"] == [0]


def test_mixed_grid_keeps_independent_prose_and_does_not_invent_its_fields():
    fragment = bound_table([
        ["Item", "Value"], ["Alpha", "111"], ["Independent left prose.", "Independent right prose."],
    ], headers=[0], body=[1])
    fragment.pdf_evidence["content_kind"] = "mixed"
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "partial" and len(view.records) == 1
    rendered = render_semantic_view(view, [fragment])
    assert "Independent left prose." in rendered and "Independent right prose." in rendered
    assert "Independent left prose.：" not in rendered
    assert rendered.count("111") == 1


def test_cross_record_shared_value_is_not_repeated_to_satisfy_individual_records():
    fragment = bound_table([
        ["Person", "Shared amount"], ["Alice", "777"], ["Bob", ""], ["Carol", "333"],
    ], headers=[0])
    merge(fragment, 1, 1, rowspan=2)
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "partial"
    assert [r.source_row for r in view.records] == [3]
    rendered = render_semantic_view(view, [fragment])
    assert rendered.count("777") == 1 and rendered.count("333") == 1
    parts = retained_table_parts(view, [fragment])
    assert parts[0]["source_rows"] == [0, 1, 2]
    assert [2, 1, 2, 1] in parts[0]["spans"]


def test_supported_fragment_survives_unbound_neighbor_without_header_invention():
    first = bound_table([["Metric", "Value"], ["Alpha", "111"]], headers=[0], name="first")
    second = bound_table([["Beta", "222"]], name="second")
    second.pdf_evidence = {}
    view = bind_table_view("view", [first, second], [first, second])
    assert view.status == "partial" and len(view.records) == 1
    rendered = render_semantic_view(view, [first, second])
    assert rendered.count("111") == rendered.count("222") == 1
    assert view.records[0].source_table_id == "first"
    assert not any(value.column_headers[0].table_id == "first" for record in view.records
                   if record.source_table_id == "second" for value in record.values)


def test_partial_view_retains_literal_pipe_with_explicit_row_mapping():
    fragment = bound_table([["Item", "Value"], ["Alpha", "111"], ["", "left | right"]], headers=[0])
    view = bind_table_view("view", [fragment], [fragment])
    parts = retained_table_parts(view, [fragment])
    assert "left &#124; right" in parts[0]["rendered"]
    assert parts[0]["source_to_display_rows"][2] == 2


def test_invalid_later_scope_does_not_erase_supported_earlier_scope():
    fragment = bound_table([["Item", "Value"], ["Alpha", "111"], ["Other", "222"]], headers=[0], body=[1])
    fragment.source_header_scopes.append({"header_rows": [4], "body_rows": [2], "complete": True})
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "partial" and view.records[0].source_row == 1
    assert ("source", 2, "invalid_header_scope") in view.row_issues
    assert render_semantic_view(view, [fragment]).count("222") == 1


def test_retained_projection_refuses_to_slice_a_source_span():
    fragment = bound_table([["Item", "Value"], ["Alpha", "111"], ["Beta", ""]], headers=[0])
    merge(fragment, 1, 1, rowspan=2)
    view = bind_table_view("view", [fragment], [fragment])
    broken = type(view)(view.view_id, view.source_tables, "partial", "unknown",
                        retained_rows=(("source", 1),))
    with pytest.raises(ValueError, match="rowspan"):
        retained_table_parts(broken, [fragment])


@pytest.mark.asyncio
async def test_actual_service_replaces_only_owned_partial_span_and_keeps_assets():
    fragment = bound_table([["Metric", "Value"], ["Alpha", "111"], ["", "222"],
                            ["Beta", "333"]], headers=[0])
    result = DocumentParseResult(
        document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
        page_count=1, processed_pages=1,
        pages=[PageParseResult(page_number=1, content=fragment.rendered)],
        pipeline=ParsePipeline(profile="balanced", primary="synthetic"),
    )
    result._table_fragments = [fragment]
    views = []
    markdown, _ = ExportService().join_document(
        result.pages, preserve_page_breaks=True, table_fragments=[fragment], public_views=views,
    )
    result._table_views = views
    result.parse_result = ContentParseResult(
        units=[], runtime=ParseRuntime(profile="balanced", primary_backend="synthetic", parser_version="synthetic"),
        links=ContentLinks(job="/job", events="/events", result="/result", assets="/assets", bundle="/bundle"),
        source=ContentSource(content_id="synthetic", source_sha256="0" * 64, filename="synthetic.pdf",
                             mime_type="application/pdf", kind=SourceKind.PDF, size_bytes=1,
                             unit_count=1, page_count=1),
        renderings=ContentRenderings(markdown=markdown + "\n\n![Authored asset](/asset)"),
    )
    before = deepcopy(fragment)
    await TableSemanticsService().apply(result, ContentParseOptions())
    final = result.parse_result.renderings.markdown
    assert result._semantic_tables[0].status == "partial"
    assert final.count("111") == final.count("222") == final.count("333") == 1
    assert "![Authored asset](/asset)" in final
    assert "status=partial" in final and "semantic-retained:" in final
    assert fragment == before
