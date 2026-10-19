from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pymupdf
import pytest

from app.models import (
    ContentParseOptions,
    DocumentParseResult,
    PageDiagnostics,
    PageParseResult,
    PageSourceKind,
    ParsePipeline,
    RouteSummary,
    ScanPolicy,
    ServiceError,
    StoredSource,
)
from app.parsers import ParserUnavailableError
from app.services.evidence_service import PageEvidence
from app.services.parser_service import ParserService
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows


def stored_source() -> StoredSource:
    path = Path("tests/fixtures/native-report.pdf").resolve()
    return StoredSource(
        path=path,
        filename=path.name,
        mime_type="application/pdf",
        size_bytes=path.stat().st_size,
        page_count=1,
    )


def result(document_id: str, content: str = "# Page 1") -> DocumentParseResult:
    return DocumentParseResult(
        document_id=document_id,
        filename="native-report.pdf",
        mime_type="application/pdf",
        page_count=1,
        processed_pages=1,
        pages=[
            PageParseResult(
                page_number=1,
                backend="fake",
                content=content,
                plain_text=content,
            )
        ],
        pipeline=ParsePipeline(profile="balanced", primary="fake"),
        route_summary=RouteSummary(failed_pages=0),
    )


class ImmediateParser:
    name = "fake"

    def __init__(self, content: str = "# Page 1") -> None:
        self.calls = 0
        self.content = content

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def parse(
        self, source, options, *, document_id, progress_callback=None, cancel_event=None
    ):
        self.calls += 1
        return result(document_id, self.content)


class BlockingParser(ImmediateParser):
    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()

    async def parse(
        self, source, options, *, document_id, progress_callback=None, cancel_event=None
    ):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        self.finished.set()
        return result(document_id)


class UnavailableParser(ImmediateParser):
    async def parse(
        self, source, options, *, document_id, progress_callback=None, cancel_event=None
    ):
        self.calls += 1
        raise ParserUnavailableError(
            "primary parser is unavailable",
            details={"backend": "fake", "state": "unavailable"},
        )


def install_parser(service: ParserService, parser: ImmediateParser, monkeypatch) -> None:
    service.standard_parser = parser  # type: ignore[assignment]
    service._initialized = True

    async def no_page_evidence(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(service, "_page_evidence", no_page_evidence)


@pytest.mark.parametrize("model_text", ["888", "88888"])
async def test_mineru_does_not_construct_docling_or_rewrite_from_character_counts(
    monkeypatch, tmp_path, model_text
):
    def forbidden_docling(*_args, **_kwargs):
        raise AssertionError("MinerU must not construct a second Docling parser")

    monkeypatch.setattr("app.services.parser_service.DoclingStandardParser", forbidden_docling)
    service = ParserService(SimpleNamespace(data_dir=tmp_path / "data", native_parser_backend="mineru"))
    assert service.standard_parser.name == "mineru-advanced-txt"
    path = tmp_path / "source.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        page.insert_text((80, 300), "888", fontsize=12)
        pdf.save(path)
    source = StoredSource(
        path=path, filename=path.name, mime_type="application/pdf",
        size_bytes=path.stat().st_size, page_count=1,
    )
    markdown = render_gfm_rows([[model_text]])
    fragment = TableFragment(
        fragment_id="mineru_p1_t1", page_number=1, ordinal=1,
        normalized_bbox=(0.05, 0.1, 0.95, 0.9), num_rows=1, num_cols=1,
        rows=[[model_text]], cells=[TableCellFragment(0, 0, 1, 1, model_text)],
        column_boundaries=[], markdown=markdown,
        rendered=f"<!-- table-fragment: mineru_p1_t1 -->\n\n{markdown}",
        source_kind="mineru", header_scope_complete=False, caption_scope_complete=False,
    )
    parsed = result("no_secondary", fragment.rendered)
    parsed._table_fragments = [fragment]
    native = ImmediateParser()
    monkeypatch.setattr(native, "parse", AsyncMock(return_value=parsed))
    install_parser(service, native, monkeypatch)
    output = await service.parse(source, ContentParseOptions(), document_id="no_secondary")
    native.parse.assert_awaited_once()
    assert model_text in output.markdown
    assert output._source_regions == []
    assert output._table_fragments[0].rows == [[model_text]]
    logs = tmp_path / "data" / "jobs" / "no_secondary" / "logs"
    source_log = json.loads((logs / "native-source-verification.json").read_text())
    assert source_log["schema"] == "native-source-verification"
    table_evidence = source_log["observations"]["pdf_table_evidence"]
    assert "version" not in table_evidence
    assert table_evidence["policy"] == "vector-grid-glyph-binding"
    semantics = json.loads((logs / "table-semantics.json").read_text())
    assert semantics["schema"] == "mo-parse-table-semantics"
    assert semantics["views"][0]["policy"] == "source-scoped-relations"
    assert "version=" not in output.markdown


async def test_idle_gate_waits_for_active_request_and_owned_backend_cleanup(monkeypatch, tmp_path):
    service = ParserService(SimpleNamespace(data_dir=tmp_path))
    install_parser(service, ImmediateParser(), monkeypatch)
    sdk_idle = AsyncMock(return_value=True)
    standard_idle = AsyncMock()
    monkeypatch.setattr(service.glm_sdk_parser, "wait_for_idle", sdk_idle, raising=False)
    monkeypatch.setattr(service.standard_parser, "wait_idle", standard_idle, raising=False)
    await service._enter_parse()
    assert not await service.wait_for_idle(0.01)
    sdk_idle.assert_not_awaited()
    standard_idle.assert_not_awaited()
    await service._leave_parse()
    assert await service.wait_for_idle(1)
    sdk_idle.assert_awaited_once()
    assert 0 < sdk_idle.call_args.args[0] <= 1
    standard_idle.assert_awaited_once()
    sdk_idle.return_value = False
    assert not await service.wait_for_idle(1)
    assert standard_idle.await_count == 1


async def test_total_timeout_includes_waiting_for_parser_semaphore(monkeypatch) -> None:
    service = ParserService(SimpleNamespace(parser_workers=1, content_timeout_seconds=0.05))
    parser = ImmediateParser()
    install_parser(service, parser, monkeypatch)
    await service._semaphore.acquire()
    try:
        with pytest.raises(ServiceError) as caught:
            await service.parse(
                stored_source(), ContentParseOptions(), document_id="docparse_timeout"
            )
        assert caught.value.code == "parse_timeout"
        assert caught.value.status_code == 504
        assert parser.calls == 0
        assert service._active_parses == 0
    finally:
        service._semaphore.release()


async def test_backend_unavailable_preserves_probe_details(monkeypatch) -> None:
    service = ParserService(SimpleNamespace(parser_workers=1, content_timeout_seconds=1.0))
    parser = UnavailableParser()
    install_parser(service, parser, monkeypatch)

    with pytest.raises(ServiceError) as caught:
        await service.parse(
            stored_source(), ContentParseOptions(), document_id="docparse_unavailable"
        )
    assert caught.value.code == "backend_unavailable"
    assert caught.value.details == {
        "scan_policy": "auto",
        "backend": "fake",
        "state": "unavailable",
    }


async def test_reload_waits_for_active_parse_and_uses_rebuilt_parser(monkeypatch) -> None:
    service = ParserService(SimpleNamespace(parser_workers=2, content_timeout_seconds=2.0))
    old_parser = BlockingParser()
    new_parser = ImmediateParser()
    install_parser(service, old_parser, monkeypatch)
    close_started = asyncio.Event()

    async def fake_close_adapters() -> None:
        assert old_parser.finished.is_set()
        close_started.set()
        service._initialized = False

    def fake_build_adapters() -> None:
        service.standard_parser = new_parser  # type: ignore[assignment]

    async def fake_initialize() -> None:
        service._initialized = True

    monkeypatch.setattr(service, "_close_adapters", fake_close_adapters)
    monkeypatch.setattr(service, "_build_adapters", fake_build_adapters)
    monkeypatch.setattr(service, "initialize", fake_initialize)

    first = asyncio.create_task(
        service.parse(stored_source(), ContentParseOptions(), document_id="docparse_old")
    )
    await old_parser.entered.wait()
    reloading = asyncio.create_task(service.reload())
    second = asyncio.create_task(
        service.parse(stored_source(), ContentParseOptions(), document_id="docparse_new")
    )
    await asyncio.sleep(0)
    assert new_parser.calls == 0

    old_parser.release.set()
    await first
    await reloading
    await second
    assert close_started.is_set()
    assert old_parser.calls == 1
    assert new_parser.calls == 1


async def test_parse_always_materializes_content_parse_result(monkeypatch) -> None:
    service = ParserService(SimpleNamespace(parser_workers=1, content_timeout_seconds=1.0))
    install_parser(service, ImmediateParser("Evidence text"), monkeypatch)

    parsed = await service.parse(stored_source(), ContentParseOptions(), document_id="docparse_ir")

    assert parsed.parse_result is not None
    assert parsed.parse_result.object == "content.parse_result"
    assert parsed.parse_result.source.content_id == "docparse_ir"
    assert parsed.parse_result.units[0].blocks[0].text == "Evidence text"
    assert parsed.parse_result.renderings.markdown.endswith("Evidence text")


async def test_parse_preserves_multi_section_gfm_table_without_domain_rewrite(
    monkeypatch,
) -> None:
    markdown = """## 截至报告期末的财务指标

| 项目 | 本报告期末 | 上年末 | 本报告期末比上年末增减 |
| --- | ---: | ---: | ---: |
| 流动比率 | 1.75 | 1.95 | -10.26% |
|  | 本报告期 | 上年同期 | 本报告期比上年同期增减 |
| 扣除非经常性损益后净利润 | 69,780.34 | 59,811.73 | 16.67% |"""
    service = ParserService(SimpleNamespace(parser_workers=1, content_timeout_seconds=1.0))
    install_parser(service, ImmediateParser(markdown), monkeypatch)

    parsed = await service.parse(stored_source(), ContentParseOptions(), document_id="docparse_gfm")

    assert markdown in parsed.markdown
    assert "|  | 本报告期 | 上年同期 |" in parsed.markdown
    assert "<fact" not in parsed.markdown


async def test_scan_policy_controls_glm_processing(monkeypatch) -> None:
    service = ParserService(SimpleNamespace(parser_workers=1, content_timeout_seconds=1.0))
    install_parser(service, ImmediateParser("content"), monkeypatch)
    calls = 0

    async def visual(*_args, **_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(service, "_apply_scan_ocr", visual)
    await service.parse(
        stored_source(),
        ContentParseOptions(scan_policy=ScanPolicy.SKIP),
        document_id="docparse_skip",
    )
    await service.parse(
        stored_source(),
        ContentParseOptions(scan_policy=ScanPolicy.AUTO),
        document_id="docparse_auto",
    )
    assert calls == 1


def test_skip_scan_policy_removes_unbound_ocr_and_retains_full_page_asset() -> None:
    service = ParserService(SimpleNamespace(parser_workers=1, content_timeout_seconds=1.0))
    parsed = result("docparse_skip_scan", "货币资金\n999,999.00\n999,999.00")
    parsed.pages[0].diagnostics = PageDiagnostics(source_kind=PageSourceKind.SCANNED)
    parsed._table_fragments = [SimpleNamespace(page_number=1)]
    parsed._picture_candidates = [SimpleNamespace(page_number=1)]
    evidence = PageEvidence(
        page_number=1,
        source_kind=PageSourceKind.SCANNED,
        page_width=595,
        page_height=842,
    )

    skipped = service._skip_scanned_pdf_pages(parsed, {1: evidence})

    assert skipped == {1}
    assert "扫描页未处理（scan_policy=skip）" in (parsed.pages[0].content or "")
    assert "999,999.00" not in (parsed.pages[0].content or "")
    assert parsed._table_fragments == []
    assert len(parsed._picture_candidates) == 1
    assert parsed._picture_candidates[0].normalized_bbox == (0.0, 0.0, 1.0, 1.0)
    assert parsed._picture_candidates[0].allow_description is False
    assert [warning.code for warning in parsed.pages[0].warnings] == ["scan_processing_skipped"]
    assert parsed.pages[0].diagnostics.selected_strategy.value == "scan_skipped"


@pytest.mark.parametrize("filename", ["renamed-input.pdf", "1225474693.pdf"])
@pytest.mark.parametrize("observed_requests", [None, 1])
async def test_glm_page_selection_uses_measured_source_kind_and_keeps_sdk_output_verbatim(
    filename: str,
    observed_requests: int | None,
) -> None:
    from app.models import BackendState, BackendStatus

    service = ParserService(SimpleNamespace(parser_workers=1))
    original = result("docparse_measured_route")
    original.pages = [
        PageParseResult(page_number=number, backend="docling-standard", content=f"native-{number}")
        for number in (3, 8, 17, 43)
    ]
    original.page_count = 43
    original.processed_pages = 4
    kinds = (
        PageSourceKind.NATIVE,
        PageSourceKind.SCANNED,
        PageSourceKind.SPARSE,
        PageSourceKind.MIXED,
    )
    evidence = {
        page.page_number: PageEvidence(page_number=page.page_number, source_kind=kind)
        for page, kind in zip(original.pages, kinds, strict=True)
    }
    sdk = result("docparse_measured_route")
    sdk.pages = [
        PageParseResult(
            page_number=8,
            backend="glm-sdk-remote",
            content="| 原件期间 | 金额 |\n| --- | --- |\n| 收入 | 100,000,000.00 |",
        ),
        PageParseResult(page_number=43, backend="glm-sdk-remote", content="SDK原件合并格文字"),
    ]
    sdk.page_count = 43
    sdk.processed_pages = 2
    calls = AsyncMock(return_value=sdk)
    service.glm_adapter = SimpleNamespace(enabled=True)
    service.glm_sdk_parser = SimpleNamespace(
        enabled=True,
        name="glm-sdk-remote",
        parse=calls,
        probe=AsyncMock(
            return_value=BackendStatus(name="glm-sdk-remote", state=BackendState.READY)
        ),
    )
    source = stored_source().model_copy(update={"filename": filename, "page_count": 43})
    before_native = original.pages[0]
    before_sparse = original.pages[2]
    sdk_texts = [page.content for page in sdk.pages]
    for page in sdk.pages:
        page._sdk_requests = observed_requests

    await service._apply_scan_ocr(
        original,
        source,
        ContentParseOptions(scan_policy=ScanPolicy.AUTO),
        evidence,
        document_id=original.document_id,
        cancel_event=None,
    )

    calls.assert_awaited_once()
    called_source, called_options = calls.await_args.args
    assert called_source is source
    assert called_options.unit_range == "8,43"
    assert original.pages[0] is before_native
    assert original.pages[2] is before_sparse
    assert [original.pages[1].content, original.pages[3].content] == sdk_texts
    assert original.pipeline.ocr == "glm-sdk-remote"
    assert original.route_summary.pages_with_ocr == 2
    assert original.pages[1].diagnostics.source_kind == PageSourceKind.SCANNED
    assert original.pages[3].diagnostics.source_kind == PageSourceKind.MIXED
    assert original.pages[1].diagnostics.glm.sdk_requests == observed_requests


async def test_failed_scan_structure_keeps_original_page_image_and_other_page_content() -> None:
    from app.models import BackendState, BackendStatus
    from app.models.parse_result import PageStatus, PipelineWarning, WarningSeverity

    service = ParserService(SimpleNamespace(parser_workers=1))
    original = result("doc_scan_structure_failure", "Original native text")
    native_page = original.pages[0]
    original.pages.extend(PageParseResult(page_number=n, content=f"pending-{n}") for n in (2, 3))
    original.page_count = original.processed_pages = 3
    sdk = result(original.document_id)
    sdk.pages = [
        PageParseResult(
            page_number=2,
            status=PageStatus.FAILED,
            backend="glm-sdk-remote",
            warnings=[
                PipelineWarning(
                    code="glm_sdk_unusable_table_structure",
                    message="unusable structure",
                    severity=WarningSeverity.ERROR,
                    page_number=2,
                    backend="glm-sdk-remote",
                )
            ],
        ),
        PageParseResult(page_number=3, backend="glm-sdk-remote", content="Other source text"),
    ]
    sdk.page_count = 3
    sdk.processed_pages = 2
    service.glm_adapter = SimpleNamespace(enabled=True)
    service.glm_sdk_parser = SimpleNamespace(
        enabled=True,
        name="glm-sdk-remote",
        parse=AsyncMock(return_value=sdk),
        probe=AsyncMock(
            return_value=BackendStatus(name="glm-sdk-remote", state=BackendState.READY)
        ),
    )
    evidence = {
        1: PageEvidence(page_number=1, source_kind=PageSourceKind.NATIVE),
        2: PageEvidence(page_number=2, source_kind=PageSourceKind.SCANNED),
        3: PageEvidence(page_number=3, source_kind=PageSourceKind.MIXED),
    }
    await service._apply_scan_ocr(
        original,
        stored_source().model_copy(update={"page_count": 3}),
        ContentParseOptions(),
        evidence,
        document_id=original.document_id,
        cancel_event=None,
    )

    assert original.pages[0] is native_page
    assert original.pages[0].content == "Original native text"
    assert original.pages[1].status == PageStatus.FAILED
    assert original.pages[1].warnings[0].code == "glm_sdk_unusable_table_structure"
    assert original.pages[2].content == "Other source text"
    assert original.route_summary.pages_with_ocr == 1
    assert {picture.page_number for picture in original._picture_candidates} == {2, 3}
    failed_source_image = next(p for p in original._picture_candidates if p.page_number == 2)
    assert failed_source_image.normalized_bbox == (0.0, 0.0, 1.0, 1.0)
    assert failed_source_image.allow_description is False
    assert not any("<table" in (page.content or "").casefold() for page in original.pages)


async def test_native_pages_do_not_probe_or_call_remote_ocr() -> None:
    service = ParserService(SimpleNamespace(parser_workers=1))
    parsed = result("docparse_no_remote")
    forbidden = AsyncMock(side_effect=AssertionError("native PDF must use the CPU parser"))
    service.glm_sdk_parser = SimpleNamespace(probe=forbidden, parse=forbidden)

    await service._apply_scan_ocr(
        parsed,
        stored_source(),
        ContentParseOptions(),
        {1: PageEvidence(page_number=1, source_kind=PageSourceKind.NATIVE)},
        document_id=parsed.document_id,
        cancel_event=None,
    )
    forbidden.assert_not_awaited()
    assert parsed.pages[0].content == "# Page 1"


@pytest.mark.parametrize("worker_recovers", [False, True])
async def test_scan_admission_refreshes_cached_sdk_failure_once(
    monkeypatch: pytest.MonkeyPatch,
    worker_recovers: bool,
) -> None:
    import httpx

    from app.parsers.glm_sdk_remote import GlmSdkRemoteParser

    worker_ready = False
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200 if worker_ready else 503, json={"status": "ok"})
        return httpx.Response(200, json={"layout_details": [], "md_results": "SDK原件正文"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    parser = GlmSdkRemoteParser(
        SimpleNamespace(
            glm_ocr_enabled=True,
            glm_sdk_enabled=True,
            glm_sdk_orientation_enabled=False,
            glm_sdk_url="http://sdk:5002/glmocr/parse",
            backend_health_ttl_seconds=3600,
            glm_sdk_max_retries=0,
        ),
        http_client=client,
    )
    monkeypatch.setattr(parser, "_render_page", lambda *_args: "data:image/png;base64,aW1hZ2U=")
    service = ParserService(SimpleNamespace(parser_workers=1))
    service.glm_adapter = SimpleNamespace(enabled=True)
    service.glm_sdk_parser = parser
    parsed = result("sdk_recovery")
    evidence = {1: PageEvidence(page_number=1, source_kind=PageSourceKind.SCANNED)}
    try:
        unavailable = await parser.probe()
        assert not unavailable.ready
        worker_ready = worker_recovers
        assert await parser.probe() is unavailable
        call = service._apply_scan_ocr(
            parsed,
            stored_source(),
            ContentParseOptions(),
            evidence,
            document_id=parsed.document_id,
            cancel_event=None,
        )
        if worker_recovers:
            await call
            assert parsed.pages[0].content == "SDK原件正文"
            assert (await parser.probe()).ready
        else:
            with pytest.raises(ParserUnavailableError, match="SDK is unavailable"):
                await call
        assert requests.count(("GET", "/health")) == 2
        assert requests.count(("POST", "/glmocr/parse")) == int(worker_recovers)
    finally:
        await client.aclose()


async def test_skip_mixed_page_preserves_native_text_and_avoids_remote_inference() -> None:
    from app.services.evidence_service import NativeBlock

    service = ParserService(SimpleNamespace(parser_workers=1))
    parsed = result("docparse_mixed_skip", "untrusted-ocr-only-9999")
    native = "原件可复制的说明文本"
    evidence = PageEvidence(
        page_number=1,
        source_kind=PageSourceKind.MIXED,
        native_blocks=[NativeBlock(native, (10, 10, 100, 30), 10, False)],
        page_width=595,
        page_height=842,
    )

    assert service._skip_scanned_pdf_pages(parsed, {1: evidence}) == {1}

    assert native in parsed.pages[0].content
    assert "untrusted-ocr-only-9999" not in parsed.pages[0].content
    assert parsed._picture_candidates[0].normalized_bbox == (0.0, 0.0, 1.0, 1.0)
    assert parsed._picture_candidates[0].allow_description is False


@pytest.mark.parametrize(
    "model_text",
    [
        "制造企业 已经拥 有，M ES 与 Physical World Model。",
        "G B /T 1243 -2024；ISO 9 001 : 201 5。",
        "| 项目 | 原文期间 |\n| --- | --- |\n| 营业收入 | 749,666,443.46 |",
        "`M E S 中 文`\n\n```mermaid\nflowchart TD\nn1[中 文] --> n2[M E S]\n```",
    ],
)
async def test_model_text_is_preserved_without_legacy_normalization(
    monkeypatch: pytest.MonkeyPatch,
    model_text: str,
) -> None:
    service = ParserService(SimpleNamespace(parser_workers=1, content_timeout_seconds=1.0))
    install_parser(service, ImmediateParser(model_text), monkeypatch)

    parsed = await service.parse(
        stored_source(), ContentParseOptions(), document_id="docparse_faithful_model"
    )

    assert parsed.pages[0].content == model_text
    assert model_text in parsed.markdown
    assert not any(warning.code.startswith("auto_") for warning in parsed.warnings)


@pytest.mark.parametrize("scan_policy", [ScanPolicy.AUTO, ScanPolicy.SKIP])
@pytest.mark.parametrize("kind", [PageSourceKind.SCANNED, PageSourceKind.MIXED])
async def test_all_scan_pages_bypass_docling_and_skip_makes_no_model_calls(
    monkeypatch: pytest.MonkeyPatch,
    scan_policy: ScanPolicy,
    kind: PageSourceKind,
) -> None:
    from app.models import BackendState, BackendStatus

    service = ParserService(SimpleNamespace(parser_workers=1, content_timeout_seconds=2.0))
    service._initialized = True
    no_docling = AsyncMock(side_effect=AssertionError("scan page must not run native Docling"))
    service.standard_parser = SimpleNamespace(name="docling-standard", parse=no_docling)
    evidence = {number: PageEvidence(page_number=number, source_kind=kind) for number in (3, 8)}
    monkeypatch.setattr(service, "_page_evidence", AsyncMock(return_value=evidence))
    service.multimodal_service.enrich_page_content = AsyncMock()
    sdk_result = result("docparse_scan_only")
    sdk_result.pages = [
        PageParseResult(
            page_number=number, backend="glm-sdk-remote", content=f"原件第{number}页GLM文字"
        )
        for number in (3, 8)
    ]
    sdk_result.page_count = 8
    sdk_result.processed_pages = 2
    remote = AsyncMock(return_value=sdk_result)
    probe = AsyncMock(return_value=BackendStatus(name="glm-sdk-remote", state=BackendState.READY))
    service.glm_adapter = SimpleNamespace(enabled=True)
    service.glm_sdk_parser = SimpleNamespace(
        enabled=True, name="glm-sdk-remote", parse=remote, probe=probe
    )
    source = stored_source().model_copy(update={"page_count": 8, "filename": "arbitrary.pdf"})

    parsed = await service.parse(
        source,
        ContentParseOptions(scan_policy=scan_policy, unit_range="3,8"),
        document_id="docparse_scan_only",
    )

    no_docling.assert_not_awaited()
    assert [page.page_number for page in parsed.pages] == [3, 8]
    if scan_policy == ScanPolicy.SKIP:
        remote.assert_not_awaited()
        probe.assert_not_awaited()
        assert len(parsed._picture_candidates) == 2
        assert all("scan_policy=skip" in page.content for page in parsed.pages)
    else:
        remote.assert_awaited_once()
        assert remote.await_args.args[1].unit_range == "3,8"
        assert [page.content for page in parsed.pages] == [
            page.content for page in sdk_result.pages
        ]
        assert parsed.route_summary.pages_with_ocr == 2
