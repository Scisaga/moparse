"""MinerU Advanced/TXT adapter across a dependency-neutral JSON boundary.

The worker owns PDF/native/model processing. This adapter owns the same GFM,
TableFragment and original-page contracts used by the other parser adapters.
No period, header, amount or source text is inferred from document vocabulary.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.models.backend import BackendState, BackendStatus
from app.models.parse_options import ContentParseOptions
from app.models.parse_result import (
    DocumentParseResult,
    PageDiagnostics,
    PageParseResult,
    PageSourceKind,
    ParsePipeline,
    ParseUsage,
    RouteSummary,
    SelectionStrategy,
)
from app.models.source import StoredSource
from app.parsers.base import (
    DocumentParser,
    ParserCancelledError,
    ParserError,
    ParserUnavailableError,
    ProgressCallback,
)
from app.parsers.glm_sdk_remote import _html_table_layout
from app.services.storage_service import StorageService
from app.services.table_service import PageFurnitureFragment, TableFragment, render_gfm_rows
from app.utils.page_range import parse_page_range
from app.utils.settings import setting

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MinerUPictureCandidate:
    page_number: int
    placeholder_index: int
    caption: str
    normalized_bbox: tuple[float, float, float, float]


def _bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        box = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) and 0 <= item <= 1 for item in box):
        return None
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box  # type: ignore[return-value]


def _source_text(value: object) -> str:
    """Read literal typed inline text for scope evidence, never render it anew."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_source_text(item) for item in value)
    if isinstance(value, dict):
        return _source_text(value.get("content"))
    return ""


class _PageRenderer:
    def __init__(self, page_number: int) -> None:
        self.page_number = page_number
        self.fragments: list[TableFragment] = []
        self.pictures: list[MinerUPictureCandidate] = []
        self.furniture: list[PageFurnitureFragment] = []

    def render(self, blocks: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            value for position, block in enumerate(blocks) if (value := self.block(block, position))
        ).strip()

    def table(self, block: dict[str, Any], rendered: str) -> str:
        children = block.get("content")
        if not isinstance(children, list):
            raise ParserError("MinerU table has no structured source content")
        bodies = [
            child
            for child in children
            if isinstance(child, dict) and child.get("type") == "table_body"
        ]
        caption = (
            "\n".join(
                _source_text(child.get("content"))
                for child in children
                if isinstance(child, dict) and child.get("type") == "table_caption"
            ).strip()
            or None
        )
        replacements = []
        cursor = 0
        for child in bodies:
            body_markdown = child.get("markdown")
            if not isinstance(body_markdown, str) or not body_markdown.strip():
                raise ParserError("MinerU table body is missing its official rendering")
            position = rendered.find(body_markdown, cursor)
            if position < 0:
                raise ParserError(
                    "MinerU source table body is absent from its official block rendering"
                )
            end = position + len(body_markdown)
            cursor = end
            source_html = child.get("content")
            if not isinstance(source_html, str):
                raise ParserError("MinerU table is missing source HTML")
            rows, has_header, cells = _html_table_layout(source_html)
            if not rows or not cells:
                raise ParserError("MinerU returned invalid table HTML/spans")
            box = _bbox(child.get("bbox")) or _bbox(block.get("bbox"))
            if box is None:
                raise ParserError("MinerU table is missing valid source geometry")
            ordinal = len(self.fragments) + 1
            fragment_id = f"mineru_p{self.page_number}_t{ordinal}"
            markdown = render_gfm_rows(rows)
            header_depth = max(
                (cell.row + cell.row_span for cell in cells if cell.is_column_header), default=0
            )
            complete_header = has_header and all(
                cell.is_column_header for cell in cells if cell.row < header_depth
            )
            fragment = TableFragment(
                fragment_id=fragment_id,
                page_number=self.page_number,
                ordinal=ordinal,
                normalized_bbox=box,
                num_rows=len(rows),
                num_cols=len(rows[0]),
                rows=rows,
                column_boundaries=[],
                markdown=markdown,
                rendered=f"<!-- table-fragment: {fragment_id} -->\n\n{markdown}",
                has_column_header=has_header,
                # <td> or a partly marked row cannot prove complete header
                # semantics. Retain every row and leave scope unknown.
                header_scope_complete=complete_header,
                caption=caption,
                caption_scope_complete=False,
                source_kind="mineru",
                cells=cells,
            )
            self.fragments.append(fragment)
            replacements.append((position, end, fragment.rendered))
        for start, end, replacement in reversed(replacements):
            rendered = rendered[:start] + replacement + rendered[end:]
        return rendered

    def block(self, block: dict[str, Any], position: int = 0) -> str:
        if not isinstance(block, dict):
            raise ParserError("MinerU returned a non-object content block")
        rendered = block.get("markdown")
        if not isinstance(rendered, str):
            raise ParserError("MinerU block is missing its official typed Markdown rendering")
        image_refs = block.get("source_images", [])
        if not isinstance(image_refs, list):
            raise ParserError("MinerU image references are invalid")
        for image in image_refs:
            box = _bbox(image.get("bbox")) if isinstance(image, dict) else None
            if box is None:
                raise ParserError("MinerU image reference is missing source geometry")
            self.pictures.append(
                MinerUPictureCandidate(
                    self.page_number,
                    len(self.pictures),
                    "",
                    box,
                )
            )
        if block.get("type") == "table":
            return self.table(block, rendered)
        role = {"header": "page_header", "footer": "page_footer", "page_number": "page_footer"}.get(
            str(block.get("type", ""))
        )
        box = _bbox(block.get("bbox"))
        if role and box is not None and rendered.strip():
            source_ref = f"mineru_p{self.page_number}_b{position}"
            wrapped = (
                f"<!-- source-furniture: {source_ref}; source-page: {self.page_number}; role: {role} -->"
                f"\n\n{rendered}"
            )
            self.furniture.append(
                PageFurnitureFragment(
                    source_ref=source_ref,
                    page_number=self.page_number,
                    label=role,
                    text=_source_text(block.get("content")),
                    rendered=wrapped,
                    normalized_bbox=box,
                )
            )
            return wrapped
        return rendered


def render_mineru_page_evidence(
    page: dict[str, Any],
) -> tuple[str, list[TableFragment], list[MinerUPictureCandidate], list[PageFurnitureFragment]]:
    number = page.get("page_number")
    blocks = page.get("blocks")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ParserError("MinerU returned an invalid source page number")
    if not isinstance(blocks, list):
        raise ParserError("MinerU returned a page without content blocks")
    renderer = _PageRenderer(number)
    markdown = renderer.render(blocks)
    for fragment in renderer.fragments:
        fragment.page_furniture = renderer.furniture[:]
    return markdown, renderer.fragments, renderer.pictures, renderer.furniture


def render_mineru_page(
    page: dict[str, Any],
) -> tuple[str, list[TableFragment], list[MinerUPictureCandidate]]:
    markdown, fragments, pictures, _furniture = render_mineru_page_evidence(page)
    return markdown, fragments, pictures


class MinerUNativeRemoteParser(DocumentParser):
    name = "mineru-advanced-txt"

    def __init__(
        self, settings: object | None, *, storage_service: StorageService | None = None
    ) -> None:
        self.settings = settings
        self.storage_service = storage_service
        self.base_url = str(
            setting(settings, "mineru_native_base_url", "http://mineru-native:8010")
        ).rstrip("/")
        self.timeout = float(setting(settings, "mineru_native_timeout_seconds", 3600))
        self._client: httpx.AsyncClient | None = None
        self._last_status: BackendStatus | None = None
        self._last_probe = 0.0

    async def initialize(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(trust_env=False, timeout=self.timeout)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def probe(self, *, force: bool = False) -> BackendStatus:
        ttl = float(setting(self.settings, "backend_health_ttl_seconds", 15))
        if not force and self._last_status and time.monotonic() - self._last_probe < ttl:
            return self._last_status
        await self.initialize()
        try:
            assert self._client is not None
            response = await self._client.get(f"{self.base_url}/ready", timeout=10)
            response.raise_for_status()
            payload = response.json()
            if payload.get("ready") is not True:
                raise ValueError("worker or configured VLM is not ready")
            if payload.get("text_matching", {}).get("name") != "native-text-matching-axis-v1":
                raise ValueError("worker is missing the reviewed native text matching fix")
            status = BackendStatus(
                name=self.name,
                state=BackendState.READY,
                model=str(payload.get("model", "")) or None,
                detail=(
                    f"MinerU {payload.get('versions', {}).get('mineru', 'unknown')} "
                    f"Advanced/TXT; remote GPU VLM concurrency={payload.get('max_concurrency')}; "
                    "PDF source text and directional matching on CPU"
                ),
            )
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            status = BackendStatus(name=self.name, state=BackendState.UNAVAILABLE, detail=str(exc))
        self._last_status, self._last_probe = status, time.monotonic()
        return status

    async def parse(
        self,
        source: StoredSource,
        options: ContentParseOptions,
        *,
        document_id: str,
        progress_callback: ProgressCallback | None = None,
        cancel_event: object | None = None,
    ) -> DocumentParseResult:
        if source.mime_type != "application/pdf":
            raise ParserError("the native MinerU adapter only accepts PDF sources")

        def cancelled() -> bool:
            return bool(
                cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)()
            )

        if cancelled():
            raise ParserCancelledError("content parsing was cancelled")
        status = await self.probe()
        if not status.ready:
            raise ParserUnavailableError(status.detail or "the native MinerU worker is unavailable")
        selected = set(parse_page_range(options.page_range, source.page_count))
        if progress_callback is not None:
            value = progress_callback(0, len(selected), "document.started")
            if asyncio.iscoroutine(value):
                await value
        started = time.perf_counter()
        try:
            assert self._client is not None
            with source.path.open("rb") as stream:
                response = await self._client.post(
                    f"{self.base_url}/parse",
                    files={"file": (source.filename, stream, "application/pdf")},
                    data={"page_range": options.page_range or ""},
                    timeout=float(options.timeout_seconds or self.timeout),
                )
            response.raise_for_status()
            if self.storage_service is not None:
                await self.storage_service.write_native_evidence(document_id, response.content)
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ParserError(f"native MinerU worker failed: {exc}") from exc
        if cancelled():
            raise ParserCancelledError("content parsing was cancelled")
        if (
            payload.get("schema") != "mineru-native/1"
            or payload.get("page_count") != source.page_count
        ):
            raise ParserError("native MinerU worker returned an incompatible document result")
        raw_pages = payload.get("pages")
        if not isinstance(raw_pages, list):
            raise ParserError("native MinerU worker did not return source pages")
        numbers = [page.get("page_number") for page in raw_pages if isinstance(page, dict)]
        if (
            len(numbers) != len(raw_pages)
            or len(numbers) != len(selected)
            or set(numbers) != selected
        ):
            raise ParserError("native MinerU worker returned an incomplete or duplicate page set")
        result = DocumentParseResult(
            document_id=document_id,
            filename=source.filename,
            mime_type=source.mime_type,
            page_count=source.page_count,
            processed_pages=len(raw_pages),
            pipeline=ParsePipeline(profile=options.profile.value, primary=self.name),
            route_summary=RouteSummary(native_text_pages=len(raw_pages), pages_with_ocr=0),
            usage=ParseUsage(
                input_bytes=source.size_bytes,
                duration_ms=round((time.perf_counter() - started) * 1000),
            ),
        )
        for raw in sorted(raw_pages, key=lambda page: page["page_number"]):
            markdown, fragments, pictures, furniture = render_mineru_page_evidence(raw)
            result._native_page_blocks[raw["page_number"]] = raw["blocks"]
            result.pages.append(
                PageParseResult(
                    page_number=raw["page_number"],
                    backend=self.name,
                    content=markdown,
                    diagnostics=PageDiagnostics(
                        source_kind=PageSourceKind.NATIVE,
                        selected_strategy=SelectionStrategy.MINERU,
                    ),
                )
            )
            result._table_fragments.extend(fragments)
            result._picture_candidates.extend(pictures)
            result._page_furniture.extend(furniture)
            if progress_callback is not None:
                value = progress_callback(len(result.pages), len(selected), "page.completed")
                if asyncio.iscoroutine(value):
                    await value
        return result
