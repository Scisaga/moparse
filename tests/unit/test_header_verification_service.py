"""Independent roles may authorize an edge, never replace native content."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.backend import BackendState, BackendStatus
from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from app.models.source import StoredSource
from app.parsers.base import ParserError, ParserUnavailableError
from app.parsers.mineru_native_remote import render_mineru_page_evidence
from app.services.header_verification_service import (
    DoclingHeaderVerificationService,
    _same_source_band,
    _source_column_geometry,
    boundary_candidates,
    verify_cached_header_evidence,
)
from app.services.table_service import (
    PageFurnitureFragment,
    TableCellFragment,
    TableFragment,
    assemble_logical_tables,
    render_gfm_rows,
)


def fragment(page, *, native=False, header="本期", multilevel=False):
    rows = [["项目", header, "同期"], [f"原件行{page}", f"{page}.25", f"{page}.50"]]
    cells = [
        TableCellFragment(r, c, 1, 1, value, is_column_header=r == 0 and not native)
        for r, row in enumerate(rows)
        for c, value in enumerate(row)
    ]
    if multilevel:
        rows = [["项目", "期间", ""], ["", header, "同期"], [f"原件行{page}", "1", "2"]]
        cells = [
            TableCellFragment(0, 0, 2, 1, "项目", is_column_header=not native),
            TableCellFragment(0, 1, 1, 2, "期间", is_column_header=not native),
            TableCellFragment(1, 1, 1, 1, header, is_column_header=not native),
            TableCellFragment(1, 2, 1, 1, "同期", is_column_header=not native),
            *[TableCellFragment(2, c, 1, 1, value) for c, value in enumerate(rows[2])],
        ]
    boundaries = [0.1, 0.35, 0.65, 0.9]
    for cell in cells:
        cell.normalized_bbox = (
            boundaries[cell.column],
            0.1 + cell.row * 0.1,
            boundaries[cell.column + cell.column_span],
            0.1 + (cell.row + cell.row_span) * 0.1,
        )
    fid = f"{'mineru_' if native else ''}p{page}_t1"
    markdown = render_gfm_rows(rows)
    return TableFragment(
        fragment_id=fid,
        page_number=page,
        ordinal=1,
        normalized_bbox=(0.1, 0.02, 0.9, 0.97),
        num_rows=len(rows),
        num_cols=3,
        rows=rows,
        column_boundaries=[] if native else boundaries,
        markdown=markdown,
        rendered=f"<!-- table-fragment: {fid} -->\n\n{markdown}",
        has_column_header=not native,
        header_scope_complete=not native,
        caption_scope_complete=not native,
        cells=cells,
        source_kind="mineru" if native else "docling",
    )


def document(fragments):
    result = DocumentParseResult(
        document_id="doc_test",
        filename="source.pdf",
        mime_type="application/pdf",
        page_count=max((f.page_number for f in fragments), default=1),
        processed_pages=len(fragments),
        pages=[PageParseResult(page_number=f.page_number, content=f.rendered) for f in fragments],
        pipeline=ParsePipeline(profile="balanced", primary="test"),
    )
    result._table_fragments = fragments
    return result


def pair(*, multilevel=False):
    return (
        document([fragment(p, native=True, multilevel=multilevel) for p in (6, 7)]),
        document([fragment(p, multilevel=multilevel) for p in (6, 7)]),
    )


def snapshot(result):
    return [
        (
            copy.deepcopy(f.rows),
            [(c.row, c.column, c.row_span, c.column_span, c.text) for c in f.cells],
        )
        for f in result._table_fragments
    ]


@pytest.mark.parametrize("multilevel", [False, True])
def test_exact_independent_headers_authorize_only_roles_and_preserve_native_values(multilevel):
    native, independent = pair(multilevel=multilevel)
    original = snapshot(native)
    # The independent model's body is deliberately wrong. It must never win.
    independent._table_fragments[0].rows[-1][1] = "WRONG INDEPENDENT VALUE"
    decisions = verify_cached_header_evidence(native, independent)
    assert len(decisions) == 1 and decisions[0].accepted
    assert snapshot(native) == original
    assert all(f.header_role_source for f in native._table_fragments)
    output = assemble_logical_tables(native.pages, native._table_fragments, enabled=True)
    assert "logical-table: table_mineru_p6_t1_mineru_p7_t1" in output[6]
    assert "WRONG" not in output[6]
    assert "原件行6" in output[6] and "原件行7" in output[6]
    assert output[7] == ""
    assert f"repeated-header-rows: {2 if multilevel else 1}" in output[6]
    if multilevel:
        assert '"header_rows":[0,1]' in output[6]
        assert '"spans":[[0,0,2,1],[0,1,1,2]]' in output[6]


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("period", "independent_complete_headers_differ"),
        ("native_text", "complete_header_text_or_spans_disagree"),
        ("partial_roles", "complete_header_text_or_spans_disagree"),
        ("missing_geometry", "independent_column_geometry_unknown"),
        ("uniform_fallback", "independent_column_geometry_unknown"),
        ("missing_header_box", "independent_column_geometry_unknown"),
        ("ambiguous", "missing_or_ambiguous_physical_table_match"),
        ("different_page", "missing_or_ambiguous_physical_table_match"),
        ("unit", "source_title_or_unit_context_disagrees"),
        ("title", "source_title_or_unit_context_disagrees"),
        ("body_tail", "cross_page_source_context_not_established"),
    ],
)
def test_incomplete_or_conflicting_evidence_keeps_original_headers(damage, reason):
    native, independent = pair()
    left, right = independent._table_fragments
    if damage == "period":
        independent = document([left, fragment(7, header="期末")])
        native = document([native._table_fragments[0], fragment(7, native=True, header="期末")])
    elif damage == "native_text":
        native._table_fragments[1].cells[0].text = "不同原文"
    elif damage == "partial_roles":
        right.cells[1].is_column_header = False
    elif damage == "missing_geometry":
        right.column_boundaries = []
    elif damage == "uniform_fallback":
        right.column_boundaries = [0, 1 / 3, 2 / 3, 1]
    elif damage == "missing_header_box":
        right.cells[0].normalized_bbox = None
    elif damage == "ambiguous":
        independent._table_fragments.append(copy.deepcopy(right))
    elif damage == "different_page":
        right.page_number = 8
    elif damage == "unit":
        native.pages[0].content = "单位：元\n\n" + native.pages[0].content
        independent.pages[0].content = "单位：股\n\n" + independent.pages[0].content
    elif damage == "title":
        native.pages[0].content = "# 原标题\n\n" + native.pages[0].content
        independent.pages[0].content = "# 不同标题\n\n" + independent.pages[0].content
    elif damage == "body_tail":
        native.pages[0].content += "\n\n附注：这是业务说明，不能作为页脚跳过。"
        independent._table_fragments[0].page_furniture.append(
            PageFurnitureFragment(
                "wrong",
                6,
                "page_footer",
                "附注：这是业务说明，不能作为页脚跳过。",
                "x",
                (0.1, 0.9, 0.9, 0.95),
            )
        )
    original = [p.content for p in native.pages]
    values = snapshot(native)
    decisions = verify_cached_header_evidence(native, independent)
    assert len(decisions) == 1 and not decisions[0].accepted
    assert decisions[0].reason == reason
    assert [p.content for p in native.pages] == original
    assert snapshot(native) == values
    assert all(not f.header_scope_complete for f in native._table_fragments)
    output = assemble_logical_tables(native.pages, native._table_fragments, enabled=True)
    assert "logical-table:" not in "\n".join(output.values())
    assert sum(text.count("table-source:") for text in output.values()) == 2


def furniture(page, text):
    markdown = (
        f"<!-- source-furniture: footer{page}; source-page: {page}; role: page_footer -->\n\n{text}"
    )
    return PageFurnitureFragment(
        f"footer{page}", page, "page_footer", text, markdown, (0.45, 0.93, 0.55, 0.95)
    )


@pytest.mark.parametrize("third_page", [False, True])
def test_hierarchical_pagination_requires_document_evidence_including_pageless_tables(third_page):
    native, independent = pair()
    for result in (native, independent):
        for page, frag in zip(result.pages, result._table_fragments, strict=True):
            source = furniture(page.page_number, f"3-1-{page.page_number - 1}")
            frag.page_furniture.append(source)
            page.content += "\n\n" + source.rendered
            result._page_furniture.append(source)
        if third_page:
            source = furniture(5, "3-1-4")
            result._page_furniture.append(source)
            result.pages.insert(
                0, PageParseResult(page_number=5, content="原件正文\n\n" + source.rendered)
            )
    decisions = verify_cached_header_evidence(native, independent)
    assert decisions[0].accepted is third_page
    output = assemble_logical_tables(
        native.pages, native._table_fragments, enabled=True, page_furniture=native._page_furniture
    )
    public = "\n".join(output.values())
    assert all(f"3-1-{n}" in public for n in ([4, 5, 6] if third_page else [5, 6]))
    assert ("logical-table:" in public) is third_page


def test_permission_is_per_edge_and_is_not_inherited_by_an_unverified_neighbor():
    native = document([fragment(p, native=True) for p in (6, 7, 8)])
    independent = document([fragment(p) for p in (6, 7)])
    decisions = verify_cached_header_evidence(native, independent)
    assert [d.accepted for d in decisions] == [True, False]
    output = assemble_logical_tables(native.pages, native._table_fragments, enabled=True)
    assert "source-pages: 6,7" in output[6]
    assert "table-source: mineru_p8_t1" in output[8]
    assert "原件行8" in output[8]


@pytest.mark.parametrize("enabled", [False, True])
def test_standalone_source_mapping_is_complete_and_repeated_export_is_stable(enabled):
    native = document([fragment(9, native=True)])
    source = native.pages[0].content
    first = assemble_logical_tables(native.pages, native._table_fragments, enabled=enabled)
    second = assemble_logical_tables(native.pages, native._table_fragments, enabled=enabled)
    assert first == second
    assert native.pages[0].content == source
    assert first[9].count("table-source:") == 1
    assert "source-rows: 1-2; logical-rows: 1-2; repeated-header-rows: 0" in first[9]
    assert re.sub(r"<!-- table-source: [^\n]* -->\n\n", "", first[9]) == source


def test_typed_furniture_only_preserves_business_notes_and_exact_original_markdown():
    blocks = [
        {
            "type": role,
            "bbox": [0.1, 0.92, 0.9, 0.95],
            "markdown": text,
            "content": [{"type": "text", "content": text}],
        }
        for role, text in [
            ("header", "原件页眉"),
            ("page_number", "3-1-5"),
            ("footnote", "业务附注"),
            ("table_footnote", "表格附注"),
        ]
    ]
    markdown, _, _, sources = render_mineru_page_evidence({"page_number": 6, "blocks": blocks})
    assert [source.text for source in sources] == ["原件页眉", "3-1-5"]
    assert all(value in markdown for value in ["原件页眉", "3-1-5", "业务附注", "表格附注"])
    assert markdown.count("source-furniture:") == 2


def test_verifier_has_one_fixed_cpu_converter_and_reports_its_actual_recipe():
    service = DoclingHeaderVerificationService(
        SimpleNamespace(docling_page_workers=3, docling_num_threads=16, parser_workers=2),
        SimpleNamespace(),
    )
    assert service.parser._page_worker_count == 1
    assert service.parser._converter_count == 1
    assert service.parser._num_threads == 4
    assert service.parser.settings.docling_device == "cpu"
    assert service.parser.settings.docling_do_cell_matching is False
    assert service.parser.settings.docling_pdf_backend == "pypdfium"


@pytest.mark.asyncio
async def test_lifecycle_and_candidate_page_selection_keep_callback_owned_by_primary(tmp_path):
    native, independent = pair()
    service = DoclingHeaderVerificationService(SimpleNamespace(), SimpleNamespace())
    parser = SimpleNamespace(
        initialize=AsyncMock(),
        close=AsyncMock(),
        probe=AsyncMock(
            return_value=BackendStatus(name="docling-standard", state=BackendState.READY)
        ),
        parse=AsyncMock(return_value=independent),
    )
    service.parser = parser
    source = StoredSource(
        path=tmp_path / "source.pdf",
        filename="source.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        page_count=10,
    )
    await service.initialize()
    await service.apply(native, source, ContentParseOptions())
    await service.close()
    assert parser.initialize.await_count == parser.close.await_count == 1
    call = parser.parse.call_args
    assert call.args[1].unit_range == "6-7"
    assert call.kwargs["progress_callback"] is None
    assert native.pipeline.primary == "mineru-advanced-txt+docling-header-verifier"
    assert native.warnings[-1].details["accepted_pairs"] == 1
    assert "workers=1, threads=4" in (await service.probe()).detail


@pytest.mark.asyncio
async def test_unavailable_or_incomplete_verifier_never_silently_accepts(tmp_path):
    native, independent = pair()
    service = DoclingHeaderVerificationService(SimpleNamespace(), SimpleNamespace())
    service.parser = SimpleNamespace(
        probe=AsyncMock(
            return_value=BackendStatus(name="docling-standard", state=BackendState.UNAVAILABLE)
        ),
        parse=AsyncMock(),
    )
    with pytest.raises(ParserUnavailableError):
        await service.require_ready()
    service.parser.probe.return_value.state = BackendState.READY
    independent.pages.pop()
    service.parser.parse.return_value = independent
    source = StoredSource(
        path=tmp_path / "source.pdf",
        filename="source.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        page_count=10,
    )
    with pytest.raises(ParserError, match="incomplete physical page"):
        await service.apply(native, source, ContentParseOptions())


@pytest.mark.asyncio
async def test_health_requires_the_enabled_verifier_and_keeps_existing_json_keys(tmp_path):
    from starlette.requests import Request

    from app.api.health import health
    from app.config import Settings
    from app.lifespan import Runtime

    statuses = [BackendStatus(name="mineru-advanced-txt", state=BackendState.READY)]
    runtime = Runtime(
        settings=Settings(
            data_dir=tmp_path, native_parser_backend="mineru", mineru_header_verifier="docling"
        ),
        repository=SimpleNamespace(ping=AsyncMock(return_value=True)),
        storage_service=SimpleNamespace(is_writable=AsyncMock(return_value=True)),
        source_service=SimpleNamespace(),
        parser_service=SimpleNamespace(probe_backends=AsyncMock(return_value=statuses)),
        job_service=SimpleNamespace(queue_depth=0),
        cleanup_service=SimpleNamespace(),
    )
    request = Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(runtime=runtime))}
    )
    assert (await runtime.ready_checks())[0]["docling"] is False
    assert (await health(request)).status == "degraded"
    statuses.append(BackendStatus(name="docling-header-verifier", state=BackendState.READY))
    assert (await runtime.ready_checks())[0]["docling"] is True
    assert (await health(request)).status == "ok"


def _read_cached_docling(directory):
    fragments = []
    for raw in json.loads((directory / "table-fragments.json").read_text()):
        values = {
            key: value
            for key, value in raw.items()
            if key in {f.name for f in fields(TableFragment) if f.init}
        }
        values["cells"] = [TableCellFragment(**cell) for cell in raw["cells"]]
        values["page_furniture"] = [
            PageFurnitureFragment(**source) for source in raw["page_furniture"]
        ]
        values["rendered"] = f"<!-- table-fragment: {raw['fragment_id']} -->\n\n{raw['markdown']}"
        fragments.append(TableFragment(**values))
    return fragments, (directory / "page.md").read_text()


def test_cached_real_normal_continuation_has_complete_source_header_and_real_geometry():
    root = Path(__file__).resolve().parents[2]
    native_root = root / "benchmark/runs/native-axis-adapter-20261018/adapter-render"
    docling_root = (
        root
        / "benchmark-results/clean-model-comparison-20261015/followup/20261017/content-preservation-mineru/docling-target14-component"
    )
    if not (native_root / "1225473526-p6/worker-page.json").is_file():
        pytest.skip("private source replay artifacts are not included in the public checkout")
    native, independent = document([]), document([])
    for page in (6, 7):
        key = f"1225473526-p{page}"
        markdown, tables, _, sources = render_mineru_page_evidence(
            json.loads((native_root / key / "worker-page.json").read_text())
        )
        native.pages.append(PageParseResult(page_number=page, content=markdown))
        native._table_fragments.extend(tables)
        native._page_furniture.extend(sources)
        docs, doc_md = _read_cached_docling(docling_root / key)
        independent.pages.append(PageParseResult(page_number=page, content=doc_md))
        independent._table_fragments.extend(docs)
    pairs = boundary_candidates(native._table_fragments)
    assert len(pairs) == 1
    left, right = pairs[0]
    by_id = {f.fragment_id: f for f in independent._table_fragments}
    dl, dr = by_id["p6_t2"], by_id["p7_t1"]
    # Select the physical continuation, excluding p6 t1's known false role.
    assert dl.fragment_id == "p6_t2" and dr.fragment_id == "p7_t1"
    assert all(_source_column_geometry(f) for f in (dl, dr))
    assert _same_source_band(left, dl) and _same_source_band(right, dr)
    original = snapshot(native)
    decisions = verify_cached_header_evidence(native, independent)
    assert snapshot(native) == original
    # The cached14 subset has only two hierarchical footer pages. It must wait
    # for the full document's independent third page before authorizing removal.
    assert not decisions[0].accepted
    assert decisions[0].reason == "cross_page_source_context_not_established"
