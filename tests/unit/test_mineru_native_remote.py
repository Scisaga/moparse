"""Source-owned table/page semantics at the optional native-worker boundary."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import PageParseResult
from app.models.source import StoredSource
from app.parsers.base import ParserError
from app.parsers.mineru_native_remote import MinerUNativeRemoteParser, render_mineru_page
from app.services.export_service import ExportService


def table(html: str, y: float = 0.1) -> dict:
    return {
        "type": "table",
        "markdown": html,
        "bbox": [0.1, y, 0.9, 0.9],
        "content": [
            {"type": "table_body", "markdown": html, "bbox": [0.1, y, 0.9, 0.9], "content": html},
        ],
    }


def test_preserves_complete_multilevel_headers_spans_auxiliary_and_source_pages():
    raw = {
        "page_number": 7,
        "blocks": [
            {
                "type": "header",
                "markdown": "原件页眉",
                "content": [{"type": "text", "content": "原件页眉"}],
            },
            {
                "type": "text",
                "markdown": "单位：元／股",
                "content": [{"type": "text", "content": "单位：元／股"}],
            },
            table(
                '<table><tr><th rowspan="2">项目</th><th colspan="2">报告期间</th></tr>'
                "<tr><th>本期</th><th>同期</th></tr><tr><td>收益</td><td>0.2907</td><td>0.3042</td></tr></table>"
            ),
            {"type": "page_number", "markdown": "7", "content": [{"type": "text", "content": "7"}]},
        ],
    }
    markdown, fragments, _ = render_mineru_page(raw)
    fragment = fragments[0]
    assert fragment.page_number == 7
    assert fragment.header_row_indices == (0, 1)
    assert [(cell.row_span, cell.column_span) for cell in fragment.cells[:2]] == [(2, 1), (1, 2)]
    assert fragment.rows == [
        ["项目", "报告期间", ""],
        ["", "本期", "同期"],
        ["收益", "0.2907", "0.3042"],
    ]
    assert "原件页眉" in markdown and "单位：元／股" in markdown and markdown.endswith("7")
    assert "table-structure:" in markdown


def test_unknown_td_header_cannot_authorize_dedup_and_no_unit_is_invented():
    markup = "<table><tr><td>项目</td><td>本期</td></tr><tr><td>收入</td><td>3</td></tr></table>"
    pages, fragments = [], []
    for number in (2, 3):
        markdown, tables, _ = render_mineru_page({"page_number": number, "blocks": [table(markup)]})
        pages.append(PageParseResult(page_number=number, content=markdown))
        fragments.extend(tables)
    output, _ = ExportService().join_document(
        pages, preserve_page_breaks=True, table_fragments=fragments, merge_cross_page_tables=True
    )
    assert output.count("项目 | 本期") == 2
    assert all(
        not fragment.header_scope_complete and fragment.unit_text is None for fragment in fragments
    )


def test_distinct_period_headers_remain_scoped_to_their_financial_rows():
    headers = ["本报告期末", "本报告期"]
    pages, fragments = [], []
    for number, header in enumerate(headers, 2):
        raw = table(
            f"<table><tr><th>项目</th><th>{header}</th></tr><tr><td>数值</td><td>{number}</td></tr></table>"
        )
        markdown, tables, _ = render_mineru_page({"page_number": number, "blocks": [raw]})
        pages.append(PageParseResult(page_number=number, content=markdown))
        fragments.extend(tables)
    output, _ = ExportService().join_document(
        pages, preserve_page_breaks=True, table_fragments=fragments, merge_cross_page_tables=True
    )
    assert "本报告期末" in output and "| 项目 | 本报告期 |" in output
    assert "logical-table: mineru_p2_t1_p3_t1" not in output


def test_image_bbox_and_caption_are_retained_for_the_original_page_asset():
    output, fragments, pictures = render_mineru_page(
        {
            "page_number": 11,
            "blocks": [
                {
                    "type": "image",
                    "markdown": "<!-- image -->\n\n原图标题",
                    "source_images": [{"bbox": [0.1, 0.2, 0.4, 0.8]}],
                    "bbox": [0.1, 0.2, 0.4, 0.8],
                    "content": [
                        {"type": "image_body", "content": "internal-image-path.png"},
                        {
                            "type": "image_caption",
                            "content": [{"type": "text", "content": "原图标题"}],
                        },
                    ],
                },
            ],
        }
    )
    assert output == "<!-- image -->\n\n原图标题" and not fragments
    assert pictures[0].page_number == 11 and pictures[0].normalized_bbox == (0.1, 0.2, 0.4, 0.8)
    assert "internal-image-path" not in output


@pytest.mark.asyncio
async def test_rejects_duplicate_worker_pages_instead_of_inventing_page_associations(
    tmp_path: Path,
):
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(b"%PDF-test")
    source = StoredSource(
        path=source_file,
        filename=source_file.name,
        mime_type="application/pdf",
        size_bytes=9,
        page_count=2,
    )

    def handle(request):
        if request.url.path == "/ready":
            return httpx.Response(
                200, json={"ready": True, "text_matching": {"name": "native-text-matching-axis-v1"}}
            )
        return httpx.Response(
            200,
            json={
                "schema": "mineru-native/1",
                "page_count": 2,
                "pages": [{"page_number": 1}, {"page_number": 1}],
            },
        )

    parser = MinerUNativeRemoteParser(SimpleNamespace())
    parser._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with pytest.raises(ParserError, match="incomplete or duplicate"):
        await parser.parse(source, ContentParseOptions(), document_id="doc_test")
    await parser.close()


async def test_managed_native_worker_keeps_the_exact_response_privately(tmp_path: Path):
    from app.services.storage_service import StorageService

    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(b"%PDF-test")
    source = StoredSource(
        path=source_file,
        filename=source_file.name,
        mime_type="application/pdf",
        size_bytes=9,
        page_count=1,
    )
    body = b'{ "schema": "mineru-native/1", "page_count": 1, "pages": [] }\n'

    def handle(request):
        if request.url.path == "/ready":
            return httpx.Response(
                200, json={"ready": True, "text_matching": {"name": "native-text-matching-axis-v1"}}
            )
        return httpx.Response(200, content=body)

    storage = StorageService(SimpleNamespace(data_dir=tmp_path / "data"))
    parser = MinerUNativeRemoteParser(SimpleNamespace(), storage_service=storage)
    parser._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with pytest.raises(ParserError, match="incomplete or duplicate"):
        await parser.parse(source, ContentParseOptions(), document_id="job_native_evidence")
    assert (
        storage.logs_dir("job_native_evidence") / "mineru-native-worker.json"
    ).read_bytes() == body
    assert not (storage.output_dir("job_native_evidence") / "asset-index.json").exists()
    assert not list(storage.assets_dir("job_native_evidence").rglob("*.json"))
    await parser.close()


def test_official_rich_markdown_passes_through_without_changing_spaces_or_syntax():
    source = (
        "English **bold** with spaces and $x^2$.\n\n- first\n  - nested\n\n```python\nx = 1\n```"
    )
    markdown, fragments, pictures = render_mineru_page(
        {"page_number": 3, "blocks": [{"type": "text", "markdown": source}]}
    )
    assert markdown == source and not fragments and not pictures


def test_partial_th_header_is_unknown_and_does_not_enable_dedup():
    raw = table(
        "<table><tr><th>标记</th><td>仍可能是数据</td></tr><tr><td>A</td><td>B</td></tr></table>"
    )
    _, fragments, _ = render_mineru_page({"page_number": 3, "blocks": [raw]})
    assert not fragments[0].header_scope_complete
    assert fragments[0].header_row_indices == ()


@pytest.mark.asyncio
async def test_readiness_follows_selected_mineru_and_keeps_legacy_check_key(tmp_path: Path):
    from unittest.mock import AsyncMock

    from starlette.requests import Request

    from app.api.health import health
    from app.config import Settings
    from app.lifespan import Runtime
    from app.models.backend import BackendState, BackendStatus

    settings = Settings(data_dir=tmp_path, native_parser_backend="mineru")
    statuses = [BackendStatus(name="mineru-advanced-txt", state=BackendState.READY)]
    parser = SimpleNamespace(probe_backends=AsyncMock(return_value=statuses))
    runtime = Runtime(
        settings=settings,
        repository=SimpleNamespace(ping=AsyncMock(return_value=True)),
        storage_service=SimpleNamespace(is_writable=AsyncMock(return_value=True)),
        source_service=SimpleNamespace(),
        parser_service=parser,
        job_service=SimpleNamespace(queue_depth=0),
        cleanup_service=SimpleNamespace(),
    )
    checks, _ = await runtime.ready_checks()
    assert checks == {"writable_data_dir": True, "writable_database": True, "docling": True}
    request = Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(runtime=runtime))}
    )
    assert (await health(request)).status == "ok"
    statuses[0].state = BackendState.UNAVAILABLE
    assert (await health(request)).status == "degraded"
    checks, _ = await runtime.ready_checks()
    assert checks["docling"] is False
