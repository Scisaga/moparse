"""Source geometry and view contracts; no model inference is involved."""

from __future__ import annotations

import asyncio
import json
import re
import threading
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest
from markdown_it import MarkdownIt

from app.models import (
    ContentParseOptions,
    DocumentParseResult,
    PageParseResult,
    ParsePipeline,
    StoredSource,
)
from app.parsers.base import ParserCancelledError
from app.services import pdf_table_evidence_service as evidence
from app.services.ir_service import DocumentIRService
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    link_cross_page_tables,
    refresh_table_views,
    render_gfm_rows,
    table_view,
)


def fragment(rows: list[list[str]], *, page: int = 1) -> TableFragment:
    md = render_gfm_rows(rows)
    return TableFragment(
        fragment_id=f"p{page}_t1",
        page_number=page,
        ordinal=1,
        normalized_bbox=(0.1, 0.1, 0.9, 0.9),
        num_rows=len(rows),
        num_cols=len(rows[0]),
        rows=deepcopy(rows),
        column_boundaries=[0.1 + i * 0.8 / len(rows[0]) for i in range(len(rows[0]) + 1)],
        markdown=md,
        rendered=f"<!-- table-fragment: p{page}_t1 -->\n\n{md}",
        source_kind="mineru",
        cells=[
            TableCellFragment(r, c, 1, 1, text)
            for r, row in enumerate(rows)
            for c, text in enumerate(row)
        ],
        header_scope_complete=False,
    )


def meta(marker: str) -> dict:
    return json.loads(re.search(r"<!-- table-structure: (.*?) -->", marker)[1])


def test_unknown_first_row_is_data_with_source_coordinates_and_blank_source_row() -> None:
    item = fragment([["", ""], ["Alpha", "12|3"]])
    original = deepcopy(item.cells)
    marker, view = table_view(item)
    state = meta(marker)
    assert "version" not in state and state["num_rows"] == 2
    assert state["header_rows"] is None
    segment = state["gfm"]["segments"][0]
    assert segment["source_rows"] == [0, 1] and segment["synthetic_header_rows"] == [0]
    assert segment["source_to_rendered_row_offset"] == 1
    html = MarkdownIt("commonmark").enable("table").render(view)
    assert "<td>Alpha</td>" in html and "<th>Alpha</th>" not in html
    assert item.cells == original and item.rows[0] == ["", ""]
    assert view.count("|  |  |") == 2


def test_internal_band_segments_partition_source_rows_and_ir_keeps_roles() -> None:
    item = fragment(
        [["name", "value"], ["role", "amount"], ["A", "12"], ["period", "balance"], ["B", "15"]]
    )
    item.source_header_scopes = [
        {"header_rows": [1], "body_rows": [2], "complete": True},
        {"header_rows": [3], "body_rows": [4], "complete": True},
    ]
    item.has_column_header = True
    for cell in item.cells:
        cell.is_column_header = cell.row in (1, 3)
    marker, view = table_view(item)
    segments = meta(marker)["gfm"]["segments"]
    assert [s["source_rows"] for s in segments] == [[0], [1, 2], [3, 4]]
    assert [s["synthetic_header_rows"] for s in segments] == [[0], [], []]
    assert [s["source_to_rendered_row_offset"] for s in segments] == [1, -1, -3]
    assert view.count("table-view-segment:") == 3
    assert DocumentIRService._table(item).header_rows == [1, 3]
    assert item.header_row_indices == ()
    page = PageParseResult(page_number=1, content=item.rendered + "\n\nOriginal note")
    refresh_table_views([page], [item])
    first = page.content
    refresh_table_views([page], [item])
    assert page.content == first
    assert page.content.count("table-view-segment:") == 3
    assert view in page.content and page.content.endswith("Original note")


def test_known_leading_band_has_explicit_display_mapping_and_unknown_ir_never_guesses() -> None:
    item = fragment([["role", "value"], ["A", "12"]])
    item.has_column_header = item.header_scope_complete = True
    for cell in item.cells:
        cell.is_column_header = cell.row == 0
    marker, view = table_view(item)
    state = meta(marker)
    assert "version" not in state
    assert state["gfm"] == {
        "segments": [{
            "index": 0,
            "source_rows": [0, 1],
            "header_rows": [0],
            "synthetic_header_rows": [],
            "rendered_num_rows": 2,
            "source_to_rendered_row_offset": 0,
            "source_header_scope_complete": True,
        }],
        "rendered_num_rows_total": 2,
    }
    assert view.endswith(item.markdown)
    item.cells = []
    table = DocumentIRService._table(item)
    assert table.header_rows == [] and not any(cell.is_column_header for cell in table.cells)


def test_refresh_preserves_source_matrix_and_updates_page_unit_view() -> None:
    item = fragment([["A", "12"]])
    original = deepcopy(item.rows)
    page = PageParseResult(page_number=1, content=item.rendered)
    refresh_table_views([page], [item])
    first = page.content
    refresh_table_views([page], [item])
    assert page.content == first == item.rendered
    assert item.rows == original and item.markdown == render_gfm_rows(original)
    assert meta(page.content)["gfm"]["segments"][0]["rendered_num_rows"] == 2


def test_refresh_replaces_owned_display_after_header_evidence_changes() -> None:
    item = fragment([["role", "value"], ["A", "12"]])
    original = deepcopy(item.rows)
    page = PageParseResult(page_number=1, content="Before\n\n" + item.rendered + "\n\nAfter")
    assert item._table_rendering.startswith("<!-- table-view-segment:")
    assert meta(page.content)["gfm"]["segments"][0]["synthetic_header_rows"] == [0]
    item.has_column_header = item.header_scope_complete = True
    for cell in item.cells:
        cell.is_column_header = cell.row == 0
    refresh_table_views([page], [item])
    first = page.content
    refresh_table_views([page], [item])
    assert page.content == first
    assert page.content.startswith("Before\n\n") and page.content.endswith("\n\nAfter")
    assert page.content.count("table-view-segment:") == 1
    assert meta(page.content)["gfm"]["segments"][0]["synthetic_header_rows"] == []
    assert item.rows == original


def test_display_segment_cannot_split_a_source_rowspan() -> None:
    item = fragment([["Group", "note"], ["", "Period"], ["A", "12"]])
    item.cells[0].row_span = 2
    item.cells = [cell for cell in item.cells if (cell.row, cell.column) != (1, 0)]
    item.source_header_scopes = [{"header_rows": [1], "body_rows": [2], "complete": True}]
    original = deepcopy(item.cells)
    marker, view = table_view(item)
    state = meta(marker)
    assert state["spans"] == [[0, 0, 2, 1]]
    assert state["display_format"] == "html"
    assert '<td rowspan="2">Group</td>' in view
    assert view.count('<tr>') == 3
    assert item.cells == original


def test_missing_source_grid_preserves_unresolved_rendering() -> None:
    markdown = "| Unresolved | 12 |\n| --- | --- |"
    item = TableFragment(
        fragment_id="unresolved",
        page_number=1,
        ordinal=1,
        normalized_bbox=(0, 0, 1, 1),
        num_rows=0,
        num_cols=2,
        rows=[],
        column_boundaries=[],
        markdown=markdown,
        rendered="<!-- table-fragment: unresolved -->\n\n" + markdown,
        valid=False,
    )
    marker, view = table_view(item)
    assert view == markdown and markdown in item.rendered
    assert meta(marker)["structure_valid"] is False
    assert meta(marker)["gfm"]["segments"] == []


def source_pdf(
    path: Path, *, numeric_header: bool = False, missing_rule: bool = False
) -> TableFragment:
    rows = [
        ["10", "20", "30"] if numeric_header else ["Name", "Value", "Rate"],
        ["Alpha", "120", "40%"],
    ]
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    xs = [40, 180, 270, 360]
    ys = [50, 80, 110]
    page.draw_rect((40, 50, 360, 80), color=None, fill=(0.8, 0.8, 0.8))
    for x in xs:
        if not missing_rule or x != 270:
            page.draw_line((x, 50), (x, 110), color=(0, 0, 0), width=0.5)
    for y in ys:
        page.draw_line((40, y), (360, y), color=(0, 0, 0), width=0.5)
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            page.insert_textbox(
                (xs[c] + 3, ys[r] + 8, xs[c + 1] - 3, ys[r + 1]),
                text,
                fontsize=9,
                align=1 if r == 0 else 0,
            )
    doc.save(path)
    doc.close()
    item = fragment(rows)
    item.normalized_bbox = (0.1, 50 / 300, 0.9, 110 / 300)
    return item


def test_original_vectors_and_all_glyphs_bind_roles_and_cell_boxes(tmp_path: Path) -> None:
    path = tmp_path / "arbitrary.pdf"
    item = source_pdf(path)
    observations = evidence.inspect_pdf_tables(path, [item])
    assert observations[0]["bound"] is True
    assert item.header_row_indices == (0,)
    assert item.header_verification_required is True
    assert all(cell.normalized_bbox is not None for cell in item.cells)
    assert item.source_header_scopes[0]["evidence"]["source_shading_contrast"] is True


@pytest.mark.parametrize("damage", ["numeric_header", "missing_rule", "changed_value"])
def test_source_style_or_partial_grid_cannot_invent_a_header(tmp_path: Path, damage: str) -> None:
    path = tmp_path / "negative.pdf"
    item = source_pdf(
        path, numeric_header=damage == "numeric_header", missing_rule=damage == "missing_rule"
    )
    if damage == "changed_value":
        item.cells[-1].text = "41%"
        item.rows[-1][-1] = "41%"
    observations = evidence.inspect_pdf_tables(path, [item])
    assert item.header_row_indices == () and item.source_header_scopes == []
    if damage != "numeric_header":
        assert observations[0]["bound"] is False


def continuation() -> tuple[list[TableFragment], list[PageParseResult]]:
    a = fragment([["Index", "Name", "Amount"], ["1", "A", "100"], ["2", "B", "200"]])
    b = fragment([["Index", "Name", "Amount"], ["3", "C", "300"]], page=2)
    for item in (a, b):
        item.has_column_header = item.header_scope_complete = item.caption_scope_complete = True
        for cell in item.cells:
            cell.is_column_header = cell.row == 0
        item.pdf_evidence = {"bound": True, "nearby_source_lines_above": []}
        item.header_verification_required = True
    b.source_continues_prev = True
    return [a, b], [
        PageParseResult(page_number=item.page_number, content=item.rendered) for item in (a, b)
    ]


def test_continuation_requires_full_native_and_source_context() -> None:
    items, pages = continuation()
    evidence._verify_numbered_continuations(items, pages, [])
    assert items[0].verified_next_fragments == [items[1].fragment_id]


@pytest.mark.parametrize("damage", ["hint", "header", "ordinal", "context", "unit"])
def test_continuation_negative_controls(damage: str) -> None:
    items, pages = continuation()
    a, b = items
    if damage == "hint":
        b.source_continues_prev = None
    if damage == "header":
        b.cells[1].text = b.rows[0][1] = "Other scope"
    if damage == "ordinal":
        b.cells[3].text = b.rows[1][0] = "4"
    if damage == "context":
        pages[0].content += "\n\nNew unrelated section"
    if damage == "unit":
        a.unit_text = "Unit: shares"
        b.unit_text = "Unit: currency"
    evidence._verify_numbered_continuations(items, pages, [])
    assert a.verified_next_fragments == [] and b.caption is None
    assert link_cross_page_tables(items) == []


def test_cpu_source_inspection_checks_cancel_before_page(tmp_path: Path) -> None:
    path = tmp_path / "cancel.pdf"
    item = source_pdf(path)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ParserCancelledError):
        evidence.inspect_pdf_tables(path, [item], cancel_event=cancel)


@pytest.mark.asyncio
async def test_cancelled_apply_drains_its_source_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "drain.pdf"
    item = source_pdf(path)
    result = DocumentParseResult(
        document_id="test",
        filename=path.name,
        mime_type="application/pdf",
        page_count=1,
        processed_pages=1,
        pipeline=ParsePipeline(profile="test", primary="mineru"),
    )
    result._table_fragments = [item]
    entered = threading.Event()
    release = threading.Event()
    exited = threading.Event()

    def inspect(*args, **kwargs):
        entered.set()
        release.wait(3)
        exited.set()
        return []

    monkeypatch.setattr(evidence, "inspect_pdf_tables", inspect)
    source = StoredSource(
        path=path,
        filename=path.name,
        mime_type="application/pdf",
        size_bytes=path.stat().st_size,
        page_count=1,
    )
    task = asyncio.create_task(
        evidence.PDFTableEvidenceService(object()).apply(result, source, ContentParseOptions())
    )
    await asyncio.to_thread(entered.wait, 1)
    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert exited.is_set()


def split_scope() -> tuple[list[TableFragment], list[PageParseResult]]:
    left = fragment(
        [
            ["Key", "Value", "", "", ""],
            ["Role", "Person A", "", "Person B", ""],
            ["Name", "A", "", "", ""],
        ]
    )
    right = fragment([["Address", "A street", ""], ["Phone", "123", ""]], page=2)
    left.source_header_scopes = [{"header_rows": [1], "body_rows": [2], "complete": True}]
    left.pdf_evidence = {
        "bound": True,
        "source_cells": [
            {"row": 1, "column": c, "column_span": span, "bbox": bbox}
            for c, span, bbox in [
                (0, 1, [40, 50, 150, 80]),
                (1, 2, [150, 50, 250, 80]),
                (3, 2, [250, 50, 360, 80]),
            ]
        ],
    }
    right.source_continues_prev = True
    right.pdf_evidence = {
        "bound": True,
        "x_grid": [40, 150, 250, 360],
        "source_cells": [
            {"row": r, "column": c, "row_span": 1, "shaded": c == 0}
            for r in range(2)
            for c in range(3)
        ],
    }
    pages = [PageParseResult(page_number=f.page_number, content=f.rendered) for f in (left, right)]
    return [left, right], pages


def test_inherited_scope_maps_source_column_spans_without_merging_grids() -> None:
    items, pages = split_scope()
    evidence._bind_header_scope_continuations(items, pages, [])
    binding = items[1].pdf_evidence["inherited_header_scope"]
    assert binding["source_column_groups"] == [[0], [1, 2], [3, 4]]
    assert binding["body_rows"] == [0, 1] and binding["header_rows"] == [1]
    assert [item.num_cols for item in items] == [5, 3]
    assert all(item.logical_table_id is None for item in items)


@pytest.mark.parametrize(
    "damage",
    ["no_hint", "column_scope", "new_context", "source_unbound", "new_unit", "different_style"],
)
def test_inherited_scope_requires_each_independent_source_witness(damage: str) -> None:
    items, pages = split_scope()
    left, right = items
    if damage == "no_hint":
        right.source_continues_prev = None
    if damage == "column_scope":
        right.pdf_evidence["x_grid"] = [40, 155, 250, 360]
    if damage == "new_context":
        pages[0].content += "\n\nNew section"
    if damage == "source_unbound":
        left.pdf_evidence["bound"] = False
    if damage == "new_unit":
        right.unit_text = "Unit: other"
    if damage == "different_style":
        for cell in right.pdf_evidence["source_cells"]:
            cell["shaded"] = False
    evidence._bind_header_scope_continuations(items, pages, [])
    assert "inherited_header_scope" not in right.pdf_evidence
