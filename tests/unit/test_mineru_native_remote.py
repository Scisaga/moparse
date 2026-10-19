"""Source-owned table/page semantics at the optional native-worker boundary."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import PageParseResult
from app.models.source import StoredSource
from app.parsers.base import ParserCancelledError, ParserError, ParserUnavailableError
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


@pytest.fixture
def one_page_source(tmp_path: Path) -> StoredSource:
    path = tmp_path / "source.pdf"
    path.write_bytes(b"%PDF-test")
    return StoredSource(
        path=path,
        filename=path.name,
        mime_type="application/pdf",
        size_bytes=path.stat().st_size,
        page_count=1,
    )


def ready_response(ready: bool) -> httpx.Response:
    return httpx.Response(
        200, json={"ready": ready, "text_matching": {"name": "native-text-matching-axis-v1"}}
    )


def parsed_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "schema": "mineru-native/1",
            "page_count": 1,
            "pages": [{"page_number": 1, "blocks": [{"type": "text", "markdown": "原件正文"}]}],
        },
    )


async def test_parse_refreshes_cached_failure_after_worker_recovers_and_posts_once(
    one_page_source: StoredSource,
):
    worker_ready = False
    requests = []

    def handle(request):
        requests.append((request.method, request.url.path))
        return ready_response(worker_ready) if request.method == "GET" else parsed_response()

    parser = MinerUNativeRemoteParser(SimpleNamespace(backend_health_ttl_seconds=3600))
    parser._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        unavailable = await parser.probe()
        assert not unavailable.ready
        worker_ready = True
        assert await parser.probe() is unavailable  # Monitoring still uses its unexpired cache.
        result = await parser.parse(one_page_source, ContentParseOptions(), document_id="recovered")
        assert result.processed_pages == 1 and result.pages[0].content == "原件正文"
        assert requests == [("GET", "/ready"), ("GET", "/ready"), ("POST", "/parse")]
        assert (await parser.probe()).ready
        assert len(requests) == 3  # The recovered ready status remains cached.
    finally:
        await parser.close()


@pytest.mark.parametrize("prime_failure_cache", [False, True])
async def test_parse_still_rejects_current_unavailable_worker_without_posting(
    one_page_source: StoredSource,
    prime_failure_cache: bool,
):
    requests = []

    def handle(request):
        requests.append((request.method, request.url.path))
        return ready_response(False)

    parser = MinerUNativeRemoteParser(SimpleNamespace(backend_health_ttl_seconds=3600))
    parser._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        if prime_failure_cache:
            assert not (await parser.probe()).ready
        with pytest.raises(ParserUnavailableError):
            await parser.parse(one_page_source, ContentParseOptions(), document_id="unavailable")
        assert requests == [("GET", "/ready")] * (1 + int(prime_failure_cache))
    finally:
        await parser.close()


async def test_parse_keeps_successful_readiness_cache_and_does_not_retry_failed_post(
    one_page_source: StoredSource,
):
    requests = []

    def handle(request):
        requests.append((request.method, request.url.path))
        return ready_response(True) if request.method == "GET" else httpx.Response(503)

    parser = MinerUNativeRemoteParser(SimpleNamespace(backend_health_ttl_seconds=3600))
    parser._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        assert (await parser.probe()).ready
        with pytest.raises(ParserError, match="native MinerU worker failed"):
            await parser.parse(one_page_source, ContentParseOptions(), document_id="failed_post")
        assert requests == [("GET", "/ready"), ("POST", "/parse")]
    finally:
        await parser.close()


@pytest.mark.parametrize("reason", ["cancel", "deadline"])
async def test_managed_request_stops_only_its_attempt_and_waits_for_ack(one_page_source, reason):
    from app.parsers.base import ParserTimeoutError
    from app.utils.deadline import attach_deadline

    entered, stop_received, cleanup_release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    cancel = asyncio.Event()
    requests = []
    phases = []

    async def handle(request):
        requests.append((request.method, request.url.path))
        if request.url.path == "/ready":
            return httpx.Response(
                200,
                json={
                    "ready": True,
                    "text_matching": {"name": "native-text-matching-axis-v1"},
                    "request_control": {"protocol": "native-request/1"},
                },
            )
        if request.url.path == "/parse":
            entered.set()
            await stop_received.wait()
            await cleanup_release.wait()
            return httpx.Response(409)
        if request.url.path.endswith("/cancel"):
            stop_received.set()
            return httpx.Response(200, json={"state": "stopping"})
        return httpx.Response(
            200,
            json={
                "state": "cancelled" if cleanup_release.is_set() else "running",
                "current": 1,
                "total": 1,
                "phase": "window.processed",
            },
        )

    parser = MinerUNativeRemoteParser(SimpleNamespace())
    parser._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    options = ContentParseOptions()
    if reason == "deadline":
        options = attach_deadline(options, 0.05)
    expected = ParserCancelledError if reason == "cancel" else ParserTimeoutError
    work = asyncio.create_task(
        parser.parse(
            one_page_source,
            options,
            document_id="owned",
            cancel_event=cancel,
            progress_callback=lambda *args: phases.append(args),
        )
    )
    try:
        await entered.wait()
        if reason == "cancel":
            cancel.set()
        await stop_received.wait()
        assert not work.done()
        assert sum(method == "POST" and path == "/parse" for method, path in requests) == 1
        stops = [path for method, path in requests if path.endswith("/cancel")]
        assert len(stops) == 1 and len(stops[0].split("/")[2]) == 32
        cleanup_release.set()
        with pytest.raises(expected):
            await work
    finally:
        cleanup_release.set()
        await parser.close()


@pytest.mark.parametrize("cancel_at", ["before_parse", "fresh_probe", "parse_post"])
async def test_cached_failure_refresh_preserves_cancellation(
    one_page_source: StoredSource,
    cancel_at: str,
):
    cancel_event = asyncio.Event()
    worker_ready = False
    requests = []

    def handle(request):
        requests.append((request.method, request.url.path))
        if request.method == "GET":
            if worker_ready and cancel_at == "fresh_probe":
                cancel_event.set()
            return ready_response(worker_ready)
        if cancel_at == "parse_post":
            cancel_event.set()
        return parsed_response()

    parser = MinerUNativeRemoteParser(SimpleNamespace(backend_health_ttl_seconds=3600))
    parser._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        assert not (await parser.probe()).ready
        worker_ready = True
        if cancel_at == "before_parse":
            cancel_event.set()
        with pytest.raises(ParserCancelledError):
            await parser.parse(
                one_page_source,
                ContentParseOptions(),
                document_id="cancelled",
                cancel_event=cancel_event,
            )
        assert requests.count(("GET", "/ready")) == (1 if cancel_at == "before_parse" else 2)
        assert requests.count(("POST", "/parse")) == int(cancel_at == "parse_post")
    finally:
        await parser.close()


async def test_http_read_timeout_is_not_worker_cleanup_ack():
    stop_received, release = asyncio.Event(), asyncio.Event()

    async def handle(request):
        if request.method == "POST":
            stop_received.set()
            return httpx.Response(200, json={"state": "stopping"})
        return httpx.Response(200, json={"state": "cancelled" if release.is_set() else "stopping"})

    async def lost_response():
        raise httpx.ReadTimeout("HTTP ended before worker thread cleanup")

    parser = MinerUNativeRemoteParser(SimpleNamespace())
    parser._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    parser._request_protocol = True
    work = asyncio.create_task(lost_response())
    await asyncio.sleep(0)
    cleanup = asyncio.create_task(parser._stop_request("owned-attempt", work))
    try:
        await stop_received.wait()
        await asyncio.sleep(0.01)
        assert work.done() and not cleanup.done()
        release.set()
        await asyncio.wait_for(cleanup, timeout=2)
    finally:
        release.set()
        await parser.close()


@pytest.mark.asyncio
async def test_readiness_follows_selected_mineru_and_keeps_legacy_check_key(tmp_path: Path):
    from unittest.mock import AsyncMock

    from starlette.requests import Request

    from app.api.health import health
    from app.config import Settings
    from app.lifespan import Runtime
    from app.models.backend import BackendState, BackendStatus

    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        native_parser_backend="mineru",
    )
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
