"""Region isolation, bounded client retries and cancellation without inference."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.models import ContentParseOptions, StoredSource
from app.parsers.base import ParserCancelledError
from app.parsers.glm_sdk_remote import GlmSdkRemoteParser
from app.utils.deadline import attach_deadline


def source(path: Path, pages: int = 1) -> StoredSource:
    return StoredSource(path=path, filename=path.name, mime_type="application/pdf",
                        size_bytes=path.stat().st_size, page_count=pages)


def adapter(tmp_path, handler, *, timeout=120):
    parser = GlmSdkRemoteParser(
        SimpleNamespace(data_dir=tmp_path, glm_ocr_enabled=True, glm_sdk_enabled=True,
                        glm_sdk_orientation_enabled=False, glm_sdk_max_retries=1,
                        glm_sdk_timeout_seconds=timeout),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    parser._render_page = lambda *_args: "data:image/png;base64,fixture"
    return parser


async def test_one_bad_table_retains_before_after_regions_and_valid_table(tmp_path, native_pdf):
    bad = "<table><tr><td rowspan='0'>Unverified `value` ``` &amp; 42</td></tr></table>"
    regions = [
        {"label": "text", "content": "Complete preceding paragraph."},
        {"label": "table", "content": "<table><tr><th>A</th></tr><tr><td>17</td></tr></table>",
         "bbox_2d": [0, 0, 1000, 200]},
        {"label": "table", "content": bad, "bbox_2d": [0, 200, 1000, 500]},
        {"label": "text", "content": "Complete following paragraph."},
    ]
    raw = json.dumps({"layout_details": [regions]}).encode()
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=raw)

    parser = adapter(tmp_path, handler)
    try:
        result = await parser.parse(source(native_pdf), ContentParseOptions(), document_id="isolated")
        [page] = result.pages
        assert page.status.value == "failed" and result.route_summary.failed_pages == 1
        assert calls == page._sdk_requests == 1
        assert "Complete preceding paragraph." in page.content
        assert "Complete following paragraph." in page.content
        assert "Unverified `value` ``` & 42" in page.content
        assert "````text\n" in page.content and "<table" not in page.content
        assert "structure: unknown" in page.content
        assert len(result._table_fragments) == 1
        assert result._table_fragments[0].rows == [["A"], ["17"]]
        [warning] = page.warnings
        assert warning.details["region_index"] == 2
        assert warning.details["source_ref"] == "sdk_p1_r2_failed_table"
        assert warning.details["candidate_text_is_original_source_truth"] is False
        [body] = list((tmp_path / "jobs/isolated/logs/glm-sdk").glob("*/page-*/attempt-*.body"))
        assert body.read_bytes() == raw
    finally:
        await parser._client.aclose()


@pytest.mark.parametrize("status,body", [
    (400, b"bad request"), (401, b"unauthorized"), (429, b"rate limited"),
    (503, b"execution uncertain"), (200, b"not json"),
    (200, b'{"error":"candidate failed"}'),
])
async def test_received_response_never_reposts_without_idempotency(tmp_path, native_pdf, status, body):
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(status, content=body)

    parser = adapter(tmp_path, handler)
    try:
        result = await parser.parse(source(native_pdf), ContentParseOptions(), document_id="no-duplicate")
        [page] = result.pages
        assert page.status.value == "failed" and calls == page._sdk_requests == 1
        assert page.warnings[0].details["server_model_calls"] is None
        [saved] = list((tmp_path / "jobs/no-duplicate/logs/glm-sdk").glob("*/page-*/attempt-*.body"))
        assert saved.read_bytes() == body
    finally:
        await parser._client.aclose()


async def test_read_timeout_does_not_resubmit_uncertain_execution(tmp_path, native_pdf):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("server execution is unknown", request=request)

    parser = adapter(tmp_path, handler)
    try:
        result = await parser.parse(source(native_pdf), ContentParseOptions(), document_id="read-timeout")
        assert calls == result.pages[0]._sdk_requests == 1
        assert result.pages[0].warnings[0].code == "glm_sdk_timeout"
        assert result.pages[0].warnings[0].details["server_model_calls"] is None
        [receipt] = list((tmp_path / "jobs/read-timeout/logs/glm-sdk").glob("*/page-*/*.transport"))
        assert json.loads(receipt.read_text())["remote_execution_unknown"] is True
    finally:
        await parser._client.aclose()


async def test_shared_deadline_is_not_reset_for_later_pages(tmp_path, native_pdf):
    calls = 0
    observed_timeouts = []

    async def handler(request):
        nonlocal calls
        calls += 1
        observed_timeouts.append(request.extensions["timeout"]["read"])
        if calls == 1:
            # Simulate one second of shared budget consumption without a
            # sub-second wall-clock assumption during concurrent builds.
            options._deadline_monotonic -= 1
        else:
            raise httpx.ReadTimeout("remaining page budget exhausted", request=request)
        return httpx.Response(200, json={"layout_details": [[{"label": "text", "content": "kept"}]]})

    parser = adapter(tmp_path, handler)
    try:
        options = attach_deadline(ContentParseOptions(), 120)
        result = await parser.parse(source(native_pdf, pages=3), options, document_id="shared-budget")
        assert calls == 2
        assert 0 < observed_timeouts[1] < observed_timeouts[0] - 0.5 <= 120
        assert result.pages[0].content == "kept"
        assert result.pages[1].warnings[0].code == "glm_sdk_timeout"
        assert result.pages[2].warnings[0].code == "glm_sdk_skipped_after_timeout"
        assert result.pages[1]._sdk_requests == 1  # one actual client POST; server model calls stay unknown
    finally:
        await parser._client.aclose()


async def test_cancel_keeps_ownership_until_original_http_returns(tmp_path, native_pdf):
    entered = asyncio.Event()
    interrupted = asyncio.Event()
    release = asyncio.Event()
    cancel = asyncio.Event()
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        entered.set()
        try:
            await release.wait()
            return httpx.Response(200, json={"layout_details": [[{"label": "text", "content": "late"}]]})
        except asyncio.CancelledError:
            interrupted.set()
            raise

    parser = adapter(tmp_path, handler)
    try:
        task = asyncio.create_task(parser.parse(source(native_pdf, pages=2), ContentParseOptions(),
                                                document_id="cancel-client", cancel_event=cancel))
        await asyncio.wait_for(entered.wait(), 1)
        cancel.set()
        await asyncio.sleep(0.08)
        assert not task.done() and parser.inflight_count == 1 and not interrupted.is_set()
        assert await parser.wait_for_idle(0.01) is False
        release.set()
        with pytest.raises(ParserCancelledError):
            await asyncio.wait_for(task, 0.5)
        assert not interrupted.is_set() and calls == 1 and parser.inflight_count == 0
        # The local job stays in cancellation cleanup until the original HTTP
        # returns. This does not create a remote SDK cancellation protocol.
    finally:
        release.set()
        await parser._client.aclose()
