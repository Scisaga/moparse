"""Controlled native responses only; no real documents or model calls."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import PageStatus
from app.models.source import StoredSource
from app.parsers.base import ParserCancelledError, ParserTimeoutError
from app.parsers.glm_sdk_remote import GlmSdkRemoteParser, _html_table_layout
from app.parsers.mineru_native_remote import (
    MinerUNativeRemoteParser,
    _PageRenderer,
    render_mineru_page_evidence,
)
from app.services.storage_service import StorageService


def _source(tmp_path: Path, pages: int = 1) -> StoredSource:
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"%PDF-controlled-response-fixture")
    return StoredSource(path=path, filename=path.name, mime_type="application/pdf",
                        size_bytes=path.stat().st_size, page_count=pages)


def _table(html: str):
    return {"type": "table", "markdown": html, "bbox": [.1, .2, .8, .8], "content": [
        {"type": "table_body", "markdown": html, "content": html, "bbox": [.1, .2, .8, .8]},
    ]}


@pytest.mark.parametrize("bad", [
    None,
    {"type": "text", "content": [{"type": "text", "content": "Received literal candidate"}]},
    {"type": "text", "markdown": "Received partial official rendering",
     "export_error": {"type": "ValueError", "stage": "body_export"}},
    {"type": "image", "markdown": "<!-- image -->", "source_images": [{"bbox": None}]},
    _table('<table><tr><td rowspan="invalid">Unresolved candidate</td></tr></table>'),
])
def test_mineru_local_errors_keep_valid_neighbors_and_original_page_view(bad):
    page = {"page_number": 1, "blocks": [
        {"type": "text", "markdown": "Valid before"}, bad,
        {"type": "text", "markdown": "Valid after"},
    ]}
    before = deepcopy(page)
    warnings = []
    markdown, fragments, pictures, _ = render_mineru_page_evidence(page, warnings=warnings)
    assert page == before
    assert "Valid before" in markdown and "Valid after" in markdown
    assert len(warnings) == 1 and warnings[0].details["region_index"] == 1
    assert warnings[0].code == "mineru_native_local_region_unreadable"
    assert not fragments
    assert pictures[-1].normalized_bbox == (0, 0, 1, 1)
    assert pictures[-1].source_page_ref in markdown
    assert pictures[-1].allow_description is False


@pytest.mark.parametrize("error", [MemoryError, TimeoutError, ParserCancelledError, ParserTimeoutError, RuntimeError])
def test_mineru_does_not_turn_resource_deadline_or_unexpected_errors_into_local_content(monkeypatch, error):
    def fail(*_args):
        raise error("controlled failure")
    monkeypatch.setattr(_PageRenderer, "block", fail)
    with pytest.raises(error):
        render_mineru_page_evidence({"page_number": 1, "blocks": [{"type": "text", "markdown": "text"}]})


async def test_mineru_later_unreadable_page_does_not_discard_earlier_page_or_raw_response(tmp_path):
    source = _source(tmp_path, 2)
    payload = {"schema": "mineru-native/1", "page_count": 2, "pages": [
        {"page_number": 1, "blocks": [{"type": "text", "markdown": "Valid first page"}]},
        {"page_number": 2, "blocks": None},
    ]}
    response = httpx.Response(200, json=payload)
    posts = []
    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json={"ready": True, "text_matching": {"name": "native-text-matching-axis-v1"}})
        posts.append(request)
        return response
    settings = SimpleNamespace(data_dir=tmp_path / "data")
    storage = StorageService(settings)
    parser = MinerUNativeRemoteParser(settings, storage_service=storage)
    parser._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        result = await parser.parse(source, ContentParseOptions(), document_id="synthetic")
    finally:
        await parser.close()
    assert len(posts) == 1
    assert result.pages[0].content == "Valid first page" and result.pages[0].status == PageStatus.COMPLETED
    assert result.pages[1].status == PageStatus.FAILED and "source-page-image" in result.pages[1].content
    assert result.processed_pages == 1 and result.route_summary.failed_pages == 1
    assert result.pages[1].warnings[0].code == "mineru_native_page_unreadable"
    assert (storage.logs_dir("synthetic") / "mineru-native-worker.json").read_bytes() == response.content


@pytest.mark.parametrize("content", [
    '<table><tr><td>First</td></tr></table><table><tr><td>Second</td></tr></table>',
    '<table><tr><td>Outer<table><tr><td>Inner</td></tr></table></td></tr></table>',
])
def test_distinct_or_nested_tables_are_not_silently_one_grid(content):
    assert _html_table_layout(content) == ([], False, [])
    warnings = []
    markdown, fragments = GlmSdkRemoteParser._render_regions([
        {"label": "text", "content": "Before"},
        {"label": "table", "content": content, "bbox_2d": [0, 0, 1000, 1000]},
        {"label": "text", "content": "After"},
    ], 1, warnings=warnings)
    assert not fragments and "Before" in markdown and "After" in markdown
    assert "structure: unknown" in markdown and warnings


@pytest.mark.parametrize("markup", ["150.1<sup>4</sup>", "H<sub>2</sub>O", "m<sup>2</sup>"])
def test_table_inline_boundaries_survive_without_inventing_notes_or_exponents(markup):
    html = f"<table><tr><td>{markup}</td></tr></table>"
    rows, _header, cells = _html_table_layout(html)
    assert rows == [[markup]] and cells[0].text == markup
    markdown, fragments, _pictures, _furniture = render_mineru_page_evidence({
        "page_number": 1, "blocks": [_table(html)],
    })
    assert fragments[0].cells[0].text == markup
    # Existing GFM escaping shows the explicit boundary literally. No broad
    # HTML passthrough or inferred numeric/note interpretation is introduced.
    assert "&lt;sup&gt;" in markdown or "&lt;sub&gt;" in markdown
    assert "150.14" not in markdown


async def test_glm_bad_local_regions_keep_neighbors_raw_response_and_do_not_retry(tmp_path, monkeypatch):
    source = _source(tmp_path)
    payload = {"layout_details": [[
        {"label": "text", "content": "Valid before", "bbox_2d": [0, 0, 1000, 100]},
        None,
        {"label": "text", "content": "Received text with unknown geometry", "bbox_2d": ["bad"]},
        {"label": "text", "content": "Valid after", "bbox_2d": [0, 200, 1000, 300]},
    ]]}
    before = deepcopy(payload)
    response = httpx.Response(200, json=payload)
    posts = []
    async def handle(request):
        posts.append(request)
        return response
    settings = SimpleNamespace(data_dir=tmp_path / "data", glm_ocr_enabled=True, glm_sdk_enabled=True,
                               glm_sdk_orientation_enabled=False, glm_sdk_max_retries=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        parser = GlmSdkRemoteParser(settings, http_client=client)
        monkeypatch.setattr(parser, "_render_page", lambda *_: "data:image/png;base64,controlled")
        result = await parser.parse(source, ContentParseOptions(), document_id="synthetic")
    assert payload == before and len(posts) == 1
    page = result.pages[0]
    assert page.status == PageStatus.FAILED
    assert all(text in page.content for text in ("Valid before", "Valid after", "Received text with unknown geometry"))
    assert len(page.warnings) == 2
    bodies = list((tmp_path / "data").rglob("*.body"))
    assert len(bodies) == 1 and bodies[0].read_bytes() == response.content


@pytest.mark.parametrize("error", [MemoryError, TimeoutError, ParserCancelledError, ParserTimeoutError, RuntimeError])
async def test_glm_local_rendering_does_not_swallow_resource_or_execution_failures(tmp_path, monkeypatch, error):
    source = _source(tmp_path)
    parser = GlmSdkRemoteParser(SimpleNamespace(glm_ocr_enabled=True, glm_sdk_enabled=True,
                                                glm_sdk_orientation_enabled=False))
    def fail(*_args):
        raise error("controlled failure")
    monkeypatch.setattr(parser, "_render_page", fail)
    try:
        with pytest.raises(error):
            await parser._request_page(source, 1, None, document_id="synthetic", request_id="controlled",
                                       source_sha256=None, options=ContentParseOptions())
    finally:
        await parser.close()
