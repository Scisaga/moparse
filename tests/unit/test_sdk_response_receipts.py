"""Private response bytes survive decoding failure without extra recognition."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.models import ContentParseOptions, StoredSource
from app.parsers.base import ParserCancelledError
from app.parsers.glm_sdk_remote import GlmSdkRemoteParser
from app.services.storage_service import StorageService


def source(path):
    return StoredSource(path=path, filename=path.name, mime_type="application/pdf",
                        size_bytes=path.stat().st_size, page_count=1)


def receipts(data, job):
    return sorted((data / "jobs" / job / "logs/glm-sdk").glob("*/page-*/*.json"))


def adapter(data, handler):
    return GlmSdkRemoteParser(
        SimpleNamespace(data_dir=data, glm_ocr_enabled=True, glm_sdk_enabled=True,
                        glm_sdk_orientation_enabled=False, glm_sdk_max_retries=0,
                        glm_sdk_url="http://sdk.fixture/glmocr/parse"),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_bad_table_raw_bytes_survive_render_failure_without_cross_request_state(
    tmp_path: Path, native_pdf: Path,
):
    # Synthetic malformed HTML; not the unavailable Census SDK response.
    raw = json.dumps({"layout_details": [[{"label": "table", "bbox_2d": [0, 0, 1000, 1000],
        "content": "<table><tr><td rowspan='0'>synthetic private body</td></tr></table>"}]]}).encode()
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=raw)

    parser = adapter(tmp_path, handler)
    try:
        for job in ("job_first", "job_second"):
            parsed = await parser.parse(source(native_pdf), ContentParseOptions(), document_id=job)
            assert parsed.pages[0].status.value == "failed"
            assert parsed.pages[0].warnings[0].code == "glm_sdk_unusable_table_structure"
            assert "synthetic private body" in parsed.pages[0].content
            assert "structure: unknown" in parsed.pages[0].content
            assert "<table" not in parsed.pages[0].content
            [path] = receipts(tmp_path, job)
            meta = json.loads(path.read_text())
            assert (path.parent / meta["body_file"]).read_bytes() == raw
            assert meta["body_sha256"] == hashlib.sha256(raw).hexdigest()
            assert meta["source_sha256"] == hashlib.sha256(native_pdf.read_bytes()).hexdigest()
            assert meta["physical_page"] == 1 and meta["attempt"] == 1
            assert meta["http_status"] == 200 and meta["body_complete"] is True
            assert meta["document_id"] == job and "headers" not in meta and "url" not in meta
        assert calls == 2
        assert json.loads(receipts(tmp_path, "job_first")[0].read_text())["request_id"] != json.loads(
            receipts(tmp_path, "job_second")[0].read_text())["request_id"]
    finally:
        await parser._client.aclose()


@pytest.mark.parametrize("status,body", [(503, b"private temporary failure"), (200, b"invalid JSON")])
async def test_response_is_saved_before_http_or_json_validation(tmp_path, native_pdf, status, body):
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(status, content=body)

    parser = adapter(tmp_path, handler)
    try:
        parsed = await parser.parse(source(native_pdf), ContentParseOptions(), document_id="job_error")
        assert parsed.pages[0].status.value == "failed" and calls == 1
        [path] = receipts(tmp_path, "job_error")
        meta = json.loads(path.read_text())
        assert meta["http_status"] == status
        assert (path.parent / meta["body_file"]).read_bytes() == body
    finally:
        await parser._client.aclose()


async def test_receipt_io_error_does_not_fail_or_retry_healthy_page(tmp_path, native_pdf, monkeypatch, caplog):
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"layout_details": [[{
            "label": "text", "content": "Unchanged healthy SDK body", "bbox_2d": [0, 0, 1000, 1000],
        }]]})

    def broken_write(*_args):
        raise OSError("deliberately private exception text")

    monkeypatch.setattr(StorageService, "_atomic_write", broken_write)
    parser = adapter(tmp_path, handler)
    try:
        parsed = await parser.parse(source(native_pdf), ContentParseOptions(), document_id="job_ok")
        assert parsed.pages[0].status.value == "completed"
        assert parsed.pages[0].content == "Unchanged healthy SDK body" and calls == 1
        assert "deliberately private" not in caplog.text and "error_type=OSError" in caplog.text
    finally:
        await parser._client.aclose()


async def test_cancel_before_request_has_no_post_or_response_receipt(tmp_path, native_pdf):
    async def forbidden(_request):
        raise AssertionError("cancelled parse must not post")

    parser = adapter(tmp_path, forbidden)
    cancel = asyncio.Event()
    cancel.set()
    try:
        with pytest.raises(ParserCancelledError):
            await parser.parse(source(native_pdf), ContentParseOptions(), document_id="job_cancel",
                               cancel_event=cancel)
        assert receipts(tmp_path, "job_cancel") == []
    finally:
        await parser._client.aclose()


def test_imported_application_matches_this_checkout():
    import app.parsers.glm_sdk_remote as sdk_module
    import app.services.parser_service as coordinator_module

    root = Path(__file__).resolve().parents[2]
    actual = {
        "app/parsers/glm_sdk_remote.py": Path(sdk_module.__file__).resolve(),
        "app/services/parser_service.py": Path(coordinator_module.__file__).resolve(),
    }
    for relative, path in actual.items():
        assert path == root / relative
    print("IMPORTED_APPLICATION " + json.dumps({key: str(value) for key, value in actual.items()}))
