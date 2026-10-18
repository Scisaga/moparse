"""Parser coordination, measured page routing, and faithful content export."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.models.backend import BackendStatus
from app.models.error import ServiceError
from app.models.parse_options import ContentParseOptions, ScanPolicy
from app.models.parse_result import (
    DocumentParseResult,
    GlmDiagnostics,
    PageDiagnostics,
    PageParseResult,
    PageSourceKind,
    PageStatus,
    ParsePipeline,
    ParseUsage,
    PipelineWarning,
    QualityVerdict,
    SelectionStrategy,
    WarningSeverity,
)
from app.models.source import StoredSource
from app.models.source_evidence import SourceRegionEvidence
from app.parsers import (
    DoclingStandardParser,
    GlmOcrRemoteAdapter,
    GlmSdkRemoteParser,
    ParserCancelledError,
    ParserError,
    ParserUnavailableError,
    ProgressCallback,
)
from app.parsers.mineru_native_remote import MinerUNativeRemoteParser
from app.security.file_validation import (
    DOCX_MIME,
    IMAGE_MIME_TYPES,
    PPTX_MIME,
    VIDEO_MIME_TYPES,
    FileValidationError,
    validate_stored_file,
)
from app.services.evidence_service import PageEvidence, PageEvidenceService
from app.services.export_service import ExportService
from app.services.glm_table_service import GlmTableService
from app.services.header_verification_service import DoclingHeaderVerificationService
from app.services.ir_service import DocumentIRService
from app.services.multimodal_service import MultimodalService
from app.services.quality_service import QualityService
from app.services.source_verification_service import SourceVerificationService
from app.services.storage_service import StorageService
from app.services.table_service import TableFragment
from app.utils.ids import new_content_id
from app.utils.page_range import PageRangeError, format_page_range, parse_page_range
from app.utils.settings import setting

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _SourcePageImage:
    """Original page view retained independently of recognition and layout routing."""

    page_number: int
    placeholder_index: int = 0
    caption: str = "扫描页原图"
    normalized_bbox: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    allow_description: bool = False


class ParserService:
    def __init__(
        self,
        settings: object | None,
        quality_service: QualityService | None = None,
        export_service: ExportService | None = None,
    ) -> None:
        self.settings = settings
        self.quality_service = quality_service or QualityService(settings)
        self.export_service = export_service or ExportService()
        self.evidence_service = PageEvidenceService(settings)
        self.ir_service = DocumentIRService(settings)
        self._semaphore = asyncio.Semaphore(int(setting(settings, "parser_workers", 1)))
        self._lifecycle_condition = asyncio.Condition()
        self._reloading = False
        self._active_parses = 0
        self._initialized = False
        self._build_adapters()

    def _build_adapters(self) -> None:
        self.glm_adapter = GlmOcrRemoteAdapter(self.settings)
        self.glm_sdk_parser = GlmSdkRemoteParser(self.settings)
        self.standard_parser = (
            MinerUNativeRemoteParser(self.settings, storage_service=StorageService(self.settings))
            if setting(self.settings, "native_parser_backend", "docling") == "mineru"
            else DoclingStandardParser(self.settings, self.glm_adapter)
        )
        self.image_parser = (
            self.glm_sdk_parser
            if isinstance(self.standard_parser, MinerUNativeRemoteParser)
            else self.standard_parser
        )
        self.header_verifier = (
            DoclingHeaderVerificationService(self.settings, self.glm_adapter)
            if isinstance(self.standard_parser, MinerUNativeRemoteParser)
            and setting(self.settings, "mineru_header_verifier", "off") == "docling"
            else None
        )
        self.source_verifier = (
            SourceVerificationService(self.header_verifier.parser)
            if self.header_verifier is not None
            and setting(self.settings, "mineru_source_verifier", "off") == "docling"
            else None
        )
        self.glm_table_service = GlmTableService()
        self.multimodal_service = MultimodalService(
            self.settings, StorageService(self.settings), self.glm_adapter
        )

    async def initialize(self) -> None:
        if self._initialized:
            return
        adapters = [self.standard_parser.initialize(), self.glm_sdk_parser.initialize()]
        if self.header_verifier is not None:
            adapters.append(self.header_verifier.initialize())
        await asyncio.gather(*adapters)
        # A missing optional backend must not prevent CPU/native-text startup.
        self._initialized = True

    async def reload(self) -> None:
        await self._begin_exclusive_lifecycle()
        try:
            await self._close_adapters()
            self._build_adapters()
            await self.initialize()
        finally:
            await self._end_exclusive_lifecycle()

    async def close(self) -> None:
        await self._begin_exclusive_lifecycle()
        try:
            await self._close_adapters()
        finally:
            await self._end_exclusive_lifecycle()

    async def _close_adapters(self) -> None:
        adapters = [
            self.standard_parser.close(),
            self.glm_adapter.close(),
            self.glm_sdk_parser.close(),
        ]
        if self.header_verifier is not None:
            adapters.append(self.header_verifier.close())
        await asyncio.gather(*adapters, return_exceptions=True)
        self._initialized = False

    async def _begin_exclusive_lifecycle(self) -> None:
        async with self._lifecycle_condition:
            while self._reloading:
                await self._lifecycle_condition.wait()
            self._reloading = True
            try:
                while self._active_parses:
                    await self._lifecycle_condition.wait()
            except BaseException:
                # A cancelled reload/close must not leave the admission gate
                # closed forever while it was waiting for an active parse.
                self._reloading = False
                self._lifecycle_condition.notify_all()
                raise

    async def _end_exclusive_lifecycle(self) -> None:
        async with self._lifecycle_condition:
            self._reloading = False
            self._lifecycle_condition.notify_all()

    async def _enter_parse(self) -> None:
        async with self._lifecycle_condition:
            while self._reloading:
                await self._lifecycle_condition.wait()
            self._active_parses += 1

    async def _leave_parse(self) -> None:
        async with self._lifecycle_condition:
            self._active_parses -= 1
            if self._active_parses == 0:
                self._lifecycle_condition.notify_all()

    async def probe_backends(self) -> list[BackendStatus]:
        if not self._initialized:
            await self.initialize()
        docling, glm, glm_sdk = await asyncio.gather(
            self.standard_parser.probe(),
            self.glm_adapter.probe(),
            self.glm_sdk_parser.probe(),
        )
        backends = [docling, glm, glm_sdk]
        if self.header_verifier is not None:
            backends.append(await self.header_verifier.probe())
        return backends

    def _coerce_source(self, source: StoredSource | str | Path) -> StoredSource:
        if isinstance(source, StoredSource):
            return source
        path = Path(source)
        try:
            filename, mime_type, size, page_count = validate_stored_file(
                path,
                path.name,
                max_bytes=int(setting(self.settings, "max_upload_bytes", 200 * 1024 * 1024)),
                max_pages=int(setting(self.settings, "max_content_units", 1_000)),
                max_video_seconds=int(setting(self.settings, "max_video_seconds", 30 * 60)),
                max_video_frame_pixels=int(
                    setting(self.settings, "video_max_frame_pixels", 7680 * 4320)
                ),
            )
        except FileValidationError as exc:
            raise ServiceError(exc.code, str(exc), status_code=415) from exc
        return StoredSource(
            path=path,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size,
            page_count=page_count,
        )

    def _finalize_exports(self, result: DocumentParseResult, options: ContentParseOptions) -> None:
        for page in result.pages:
            page.plain_text = self.export_service.markdown_to_text(
                page.content or "", source_regions=result._source_regions
            )
        markdown, plain_text = self.export_service.join_document(
            result.pages,
            preserve_page_breaks=True,
            table_fragments=result._table_fragments,
            page_furniture=result._page_furniture,
            source_regions=result._source_regions,
            merge_cross_page_tables=bool(
                setting(self.settings, "cross_page_table_merge_enabled", True)
            ),
        )
        result.markdown = markdown
        result.plain_text = plain_text
        result.processed_pages = sum(page.status.value != "failed" for page in result.pages)

    async def _page_evidence(
        self,
        source: StoredSource,
        result: DocumentParseResult,
    ) -> dict[int, PageEvidence]:
        pages = {page.page_number for page in result.pages}
        evidence = await asyncio.to_thread(self.evidence_service.inspect, source, pages)
        for page in result.pages:
            item = evidence.get(page.page_number)
            if item is None:
                continue
            page.diagnostics = PageDiagnostics(
                source_kind=item.source_kind,
                native_text_characters=item.native_text_characters,
                visual_ink_ratio=item.visual_ink_ratio,
                image_coverage_ratio=item.image_coverage_ratio,
                detected_rotation_degrees=item.detected_rotation_degrees,  # type: ignore[arg-type]
            )
        return evidence

    async def _parse_native_pages(
        self,
        source: StoredSource,
        options: ContentParseOptions,
        *,
        document_id: str,
        progress_callback: ProgressCallback | None,
        cancel_event: object | None,
    ) -> tuple[DocumentParseResult, dict[int, PageEvidence]]:
        """Classify original pages before conversion so scans do not run TableFormer."""

        selected = set(parse_page_range(options.page_range, source.page_count))
        result = DocumentParseResult(
            document_id=document_id,
            filename=source.filename,
            mime_type=source.mime_type,
            page_count=source.page_count,
            processed_pages=0,
            pages=[PageParseResult(page_number=number) for number in sorted(selected)],
            pipeline=ParsePipeline(
                profile=options.profile.value, primary=self.standard_parser.name
            ),
            usage=ParseUsage(input_bytes=source.size_bytes),
        )
        evidence = await self._page_evidence(source, result)
        scan_pages = {
            number
            for number, item in evidence.items()
            if item.source_kind in {PageSourceKind.SCANNED, PageSourceKind.MIXED}
        }
        if source.mime_type in IMAGE_MIME_TYPES:
            scan_pages = selected
        native_pages = selected - scan_pages
        if native_pages:
            native_options = options
            if native_pages != selected:
                native_options = options.model_copy(
                    update={"unit_range": format_page_range(sorted(native_pages))}
                )

            async def native_progress(current: int, _total: int, state: str) -> None:
                if progress_callback is not None:
                    value = progress_callback(current, len(selected), state)
                    if asyncio.iscoroutine(value):
                        await value

            native = await self.standard_parser.parse(
                source,
                native_options,
                document_id=document_id,
                progress_callback=native_progress,
                cancel_event=cancel_event,
            )
            returned = [page.page_number for page in native.pages]
            if set(returned) != native_pages or len(returned) != len(native_pages):
                raise ParserError("the native parser returned an incomplete or duplicate page set")
            seeded_pages = {page.page_number: page for page in result.pages}
            for page in native.pages:
                seeded = seeded_pages.get(page.page_number)
                if seeded is not None:
                    page.diagnostics = seeded.diagnostics
                    if page.diagnostics is not None and isinstance(
                        self.standard_parser, MinerUNativeRemoteParser
                    ):
                        page.diagnostics.selected_strategy = SelectionStrategy.MINERU
            native_numbers = {page.page_number for page in native.pages}
            native.pages.extend(
                page for number, page in seeded_pages.items() if number not in native_numbers
            )
            native.pages.sort(key=lambda page: page.page_number)
            result = native
        return result, evidence

    @staticmethod
    def _skip_scanned_pdf_pages(
        result: DocumentParseResult,
        evidence_by_page: dict[int, PageEvidence],
    ) -> set[int]:
        """Retain skipped scanned pages as images and emit no unbound OCR values."""

        skipped = {
            page.page_number
            for page in result.pages
            if (evidence := evidence_by_page.get(page.page_number)) is not None
            and evidence.source_kind in {PageSourceKind.SCANNED, PageSourceKind.MIXED}
        }
        if not skipped:
            return set()

        result._table_fragments = [
            fragment
            for fragment in result._table_fragments
            if getattr(fragment, "page_number", None) not in skipped
        ]
        result._picture_candidates = [
            picture
            for picture in result._picture_candidates
            if getattr(picture, "page_number", None) not in skipped
        ]
        result._picture_candidates.extend(
            _SourcePageImage(page_number=page_number) for page_number in sorted(skipped)
        )

        result.warnings = [
            warning
            for warning in result.warnings
            if warning.page_number not in skipped or warning.severity == WarningSeverity.INFO
        ]
        for page in result.pages:
            if page.page_number not in skipped:
                continue
            evidence = evidence_by_page[page.page_number]
            source_kind = evidence.source_kind.value
            marker = (
                f"> 扫描页未处理（scan_policy=skip）：第 {page.page_number} 页，"
                f"页面类型为 {source_kind}。"
            )
            native_text = "\n\n".join(
                block.text.strip()
                for block in evidence._blocks_in_reading_order()
                if block.text.strip()
            )
            page.content = f"{marker}\n\n## 原生文本\n\n{native_text}" if native_text else marker
            page.plain_text = None
            page.status = PageStatus.WARNING
            page.warnings = [
                warning for warning in page.warnings if warning.severity == WarningSeverity.INFO
            ]
            page.warnings.append(
                PipelineWarning(
                    code="scan_processing_skipped",
                    message="scanned page processing was disabled; the page image was retained as an asset",
                    severity=WarningSeverity.WARNING,
                    page_number=page.page_number,
                    backend="scan-policy",
                    details={"source_kind": source_kind},
                )
            )
            if page.diagnostics is not None:
                page.diagnostics.selected_strategy = SelectionStrategy.SCAN_SKIPPED
                page.diagnostics.quality_verdict = QualityVerdict.UNTRUSTED
                page.diagnostics.glm = None
        return skipped

    async def _apply_scan_ocr(
        self,
        result: DocumentParseResult,
        source: StoredSource,
        options: ContentParseOptions,
        evidence_by_page: dict[int, PageEvidence],
        *,
        document_id: str,
        cancel_event: object | None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Use the SDK only for measured scan/mixed pages, retaining its content verbatim."""

        targets = {
            page.page_number
            for page in result.pages
            if (evidence := evidence_by_page.get(page.page_number)) is not None
            and evidence.source_kind in {PageSourceKind.SCANNED, PageSourceKind.MIXED}
        }
        if source.mime_type in IMAGE_MIME_TYPES:
            targets = {page.page_number for page in result.pages}
        if not targets:
            return
        if not self.glm_adapter.enabled or not self.glm_sdk_parser.enabled:
            raise ParserUnavailableError("GLM-OCR and its SDK are required for scan_policy=auto")
        status = await self.glm_sdk_parser.probe()
        if not status.ready:
            raise ParserUnavailableError(
                "the GLM-OCR SDK is unavailable for scanned or mixed pages"
            )

        async def sdk_progress(current: int, _total: int, state: str) -> None:
            if progress_callback is not None:
                offset = len(result.pages) - len(targets)
                value = progress_callback(offset + current, len(result.pages), state)
                if asyncio.iscoroutine(value):
                    await value

        sdk_result = await self.glm_sdk_parser.parse(
            source,
            options.model_copy(update={"unit_range": format_page_range(sorted(targets))}),
            document_id=document_id,
            cancel_event=cancel_event,
            progress_callback=sdk_progress,
        )
        sdk_pages = {page.page_number: page for page in sdk_result.pages}
        if set(sdk_pages) != targets or len(sdk_result.pages) != len(targets):
            raise ParserError("the GLM-OCR SDK returned an incomplete page set")
        fragments_by_page: dict[int, list[TableFragment]] = {}
        for fragment in sdk_result._table_fragments:
            if isinstance(fragment, TableFragment):
                fragments_by_page.setdefault(fragment.page_number, []).append(fragment)
        for page in sdk_pages.values():
            evidence = evidence_by_page.get(page.page_number)
            if page.diagnostics is None:
                page.diagnostics = PageDiagnostics(
                    source_kind=evidence.source_kind if evidence else PageSourceKind.SCANNED,
                    native_text_characters=evidence.native_text_characters if evidence else None,
                    visual_ink_ratio=evidence.visual_ink_ratio if evidence else None,
                    image_coverage_ratio=evidence.image_coverage_ratio if evidence else None,
                )
            fragments = fragments_by_page.get(page.page_number, [])
            structure_warnings = self.glm_table_service.validate_fragments(fragments)
            page.warnings.extend(structure_warnings)
            if structure_warnings and page.status == PageStatus.COMPLETED:
                page.status = PageStatus.WARNING
            page.diagnostics.selected_strategy = SelectionStrategy.GLM_TABLE
            page.diagnostics.glm = GlmDiagnostics(
                sdk_requests=page._sdk_requests,
                sdk_duration_ms=page.duration_ms,
                table_count=len(fragments),
                structure_issue_count=len(structure_warnings),
            )
        result.pages = [sdk_pages.get(page.page_number, page) for page in result.pages]
        result._table_fragments = [
            fragment
            for fragment in result._table_fragments
            if getattr(fragment, "page_number", None) not in targets
        ]
        result._table_fragments.extend(sdk_result._table_fragments)
        if source.mime_type == "application/pdf":
            # OCR text does not preserve seals, handwriting, figures or their
            # position on a scanned/mixed page. Keep the original full-page
            # view through the same asset path used by scan_policy=skip.
            result._picture_candidates.extend(
                _SourcePageImage(page_number=page_number) for page_number in sorted(targets)
            )
        result.warnings = [
            warning for warning in result.warnings if warning.page_number not in targets
        ]
        result.warnings.extend(sdk_result.warnings)
        result.pipeline.ocr = self.glm_sdk_parser.name
        result.route_summary.pages_with_ocr = sum(
            page.status != PageStatus.FAILED for page in sdk_pages.values()
        )
        result.route_summary.ocr_regions = sdk_result.route_summary.ocr_regions
        result.route_summary.native_text_pages = len(result.pages) - len(targets)
        result.warnings.append(
            PipelineWarning(
                code="glm_sdk_scan_routing_used",
                message=f"the GLM-OCR SDK parsed {len(targets)} scanned or mixed page(s)",
                severity=WarningSeverity.INFO,
                backend=self.glm_sdk_parser.name,
                details={"pages": sorted(targets)},
            )
        )

    async def parse(
        self,
        source: StoredSource | str | Path,
        options: ContentParseOptions | dict[str, object],
        *,
        document_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: object | None = None,
    ) -> DocumentParseResult:
        stored = self._coerce_source(source)
        parsed_options = (
            options
            if isinstance(options, ContentParseOptions)
            else ContentParseOptions.model_validate(options)
        )
        if stored.mime_type in VIDEO_MIME_TYPES and parsed_options.unit_range is not None:
            raise ServiceError(
                "invalid_unit_range", "video inputs do not accept unit_range", status_code=400
            )
        if (
            stored.mime_type == DOCX_MIME
            or (stored.mime_type in IMAGE_MIME_TYPES and stored.mime_type != "image/tiff")
        ) and parsed_options.unit_range not in {None, "1"}:
            raise ServiceError(
                "invalid_unit_range",
                "DOCX and single-frame images only accept an omitted unit_range or 1",
                status_code=400,
            )
        try:
            parse_page_range(parsed_options.page_range, stored.page_count)
        except PageRangeError as exc:
            raise ServiceError("invalid_unit_range", str(exc), status_code=400) from exc
        timeout = float(
            parsed_options.timeout_seconds or setting(self.settings, "content_timeout_seconds", 900)
        )
        identifier = document_id or new_content_id()
        started = time.perf_counter()
        try:
            async with asyncio.timeout(timeout):
                await self._enter_parse()
                try:
                    if not self._initialized:
                        await self.initialize()
                    if stored.mime_type == "application/pdf" and self.header_verifier is not None:
                        await self.header_verifier.require_ready()
                    if stored.mime_type in VIDEO_MIME_TYPES:
                        return await self.multimodal_service.parse_video(
                            stored,
                            parsed_options,
                            content_id=identifier,
                            progress_callback=progress_callback,
                            cancel_event=cancel_event,
                        )
                    if stored.mime_type in {DOCX_MIME, PPTX_MIME}:
                        async with self._semaphore:
                            return await self.multimodal_service.parse_office(
                                stored,
                                parsed_options,
                                content_id=identifier,
                                progress_callback=progress_callback,
                                cancel_event=cancel_event,
                                image_parser=self.image_parser,
                            )
                    # Resolve after the reload gate: a waiter must never retain a
                    # parser instance that reload has just closed and replaced.
                    execution_options = parsed_options
                    async with self._semaphore:
                        result, evidence_by_page = await self._parse_native_pages(
                            stored,
                            execution_options,
                            document_id=identifier,
                            progress_callback=progress_callback,
                            cancel_event=cancel_event,
                        )
                        skip_scans = (
                            stored.mime_type == "application/pdf"
                            and parsed_options.scan_policy == ScanPolicy.SKIP
                        )
                        if skip_scans:
                            self._skip_scanned_pdf_pages(result, evidence_by_page)
                            self._finalize_exports(result, parsed_options)
                            self.quality_service.assess(result)
                        elif (
                            parsed_options.scan_policy == ScanPolicy.AUTO
                            or stored.mime_type in IMAGE_MIME_TYPES
                        ):
                            await self._apply_scan_ocr(
                                result,
                                stored,
                                execution_options,
                                evidence_by_page,
                                document_id=identifier,
                                cancel_event=cancel_event,
                                progress_callback=progress_callback,
                            )
                        if stored.mime_type == "application/pdf" and self.source_verifier is not None:
                            if progress_callback is not None:
                                value = progress_callback(
                                    len(result.pages), len(result.pages), "postprocess.sources.started"
                                )
                                if asyncio.iscoroutine(value):
                                    await value
                            await self.source_verifier.apply(
                                result, stored, parsed_options, cancel_event=cancel_event
                            )
                            await StorageService(self.settings).write_source_verification_evidence(
                                result.document_id,
                                {
                                    "schema": "native-source-verification/1",
                                    "observations": result._source_verification,
                                    "source_regions": [
                                        asdict(region)
                                        for region in result._source_regions
                                        if isinstance(region, SourceRegionEvidence)
                                    ],
                                },
                            )
                            if progress_callback is not None:
                                value = progress_callback(
                                    len(result.pages), len(result.pages), "postprocess.sources.completed"
                                )
                                if asyncio.iscoroutine(value):
                                    await value
                        if (
                            stored.mime_type == "application/pdf"
                            and self.header_verifier is not None
                        ):
                            if progress_callback is not None:
                                value = progress_callback(
                                    len(result.pages),
                                    len(result.pages),
                                    "postprocess.headers.started",
                                )
                                if asyncio.iscoroutine(value):
                                    await value
                            await self.header_verifier.apply(
                                result, stored, parsed_options, cancel_event=cancel_event
                            )
                            if progress_callback is not None:
                                value = progress_callback(
                                    len(result.pages),
                                    len(result.pages),
                                    "postprocess.headers.completed",
                                )
                                if asyncio.iscoroutine(value):
                                    await value
                        if self.source_verifier is not None:
                            result.pipeline.primary += "+docling-source-verifier"
                        self._finalize_exports(result, parsed_options)
                        self.quality_service.assess(result)
                        result.usage.duration_ms = max(
                            0, round((time.perf_counter() - started) * 1000)
                        )
                        result.parse_result = self.ir_service.build(
                            result,
                            stored,
                            evidence_by_page,
                        )
                        await self.multimodal_service.enrich_page_content(
                            result.parse_result,
                            result,
                            stored,
                            evidence_by_page,
                            parsed_options,
                            image_parser=self.image_parser,
                            cancel_event=cancel_event,
                        )
                        result.markdown = result.parse_result.renderings.markdown
                        result.plain_text = result.parse_result.renderings.plain_text
                        return result
                finally:
                    await self._leave_parse()
        except TimeoutError as exc:
            raise ServiceError(
                "parse_timeout", f"content parsing exceeded {timeout:g} seconds", status_code=504
            ) from exc
        except ParserCancelledError as exc:
            raise ServiceError("job_cancelled", str(exc), status_code=409) from exc
        except ParserUnavailableError as exc:
            details: dict[str, object] = {"scan_policy": parsed_options.scan_policy.value}
            if exc.details:
                details.update(exc.details)
            raise ServiceError(
                "backend_unavailable",
                str(exc),
                status_code=502,
                details=details,
            ) from exc
        except ParserError as exc:
            raise ServiceError(exc.code, str(exc), status_code=502, details=exc.details) from exc
