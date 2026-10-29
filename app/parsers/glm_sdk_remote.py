"""Thin adapter for the official self-hosted GLM-OCR SDK server.

The SDK owns layout detection, region cropping and task-specific recognition.
This adapter deliberately does not reinterpret OCR values: it validates the
region envelope, renders stable Markdown, and exposes table regions through the
same private ``TableFragment`` contract used by the Docling parser.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import math
import re
import time
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image

from app.models.backend import BackendState, BackendStatus
from app.models.parse_options import ContentParseOptions
from app.models.parse_result import (
    DocumentParseResult,
    PageParseResult,
    PageStatus,
    ParsePipeline,
    ParseUsage,
    PipelineWarning,
    RouteSummary,
    WarningSeverity,
)
from app.models.source import StoredSource
from app.parsers.base import (
    DocumentParser,
    ParserCancelledError,
    ParserTimeoutError,
    ProgressCallback,
)
from app.services.orientation_service import DocumentOrientationService
from app.services.storage_service import StorageService
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows
from app.utils.deadline import attach_deadline, remaining_timeout
from app.utils.page_range import parse_page_range
from app.utils.settings import setting

logger = logging.getLogger(__name__)

# The public grid has a bounded total size. A legitimate wide table must not
# fail merely because its span encoding uses more than 100 logical columns.
MAX_TABLE_DIMENSION = 2_000
MAX_TABLE_GRID_CELLS = 200_000


def _bounded_table_shape(rows: int, columns: int) -> bool:
    return (
        0 < rows <= MAX_TABLE_DIMENSION
        and 0 < columns <= MAX_TABLE_DIMENSION
        and rows * columns <= MAX_TABLE_GRID_CELLS
    )


@dataclass(frozen=True, slots=True)
class _HtmlCell:
    text: str
    row_span: int
    col_span: int
    header: bool
    row_header: bool = False


class _TableHtmlParser(HTMLParser):
    """Small dependency-free HTML table reader with explicit span handling."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_HtmlCell]] = []
        self._row: list[_HtmlCell] | None = None
        self._cell_tag: str | None = None
        self._cell_parts: list[str] = []
        self._row_span = 1
        self._col_span = 1
        self._row_header = False
        self._table_count = 0
        self._table_depth = 0
        self._inline_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag == "table":
            self._table_count += 1
            self._table_depth += 1
            if self._table_count != 1 or self._table_depth != 1:
                raise ValueError("multiple or nested HTML tables have no single grid")
        elif tag == "tr":
            if self._row is not None or len(self.rows) >= MAX_TABLE_DIMENSION:
                raise ValueError("invalid HTML table rows")
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            if self._cell_tag is not None:
                raise ValueError("nested HTML table cells")
            values = {key.casefold(): value for key, value in attrs}
            self._cell_tag = tag
            self._cell_parts = []
            self._inline_stack = []
            self._row_span = _positive_span(values.get("rowspan"))
            self._col_span = _positive_span(values.get("colspan"))
            self._row_header = tag == "th" and (values.get("scope") or "").casefold() in {
                "row",
                "rowgroup",
            }
        elif tag == "br" and self._cell_tag is not None:
            self._cell_parts.append("\n")
        elif tag in {"sup", "sub"} and self._cell_tag is not None:
            # Keep the producer's explicit boundary. Its meaning may be a
            # note, exponent, or something else; never concatenate its digits.
            self._cell_parts.append(f"<{tag}>")
            self._inline_stack.append(tag)

    def handle_data(self, data: str) -> None:
        if self._cell_tag is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        # Close only the one open cell at an explicit td/th end; never infer
        # cell/row ends. Its opening tag owns the text, spans and header role.
        if tag in {"sup", "sub"} and self._cell_tag is not None:
            if not self._inline_stack or self._inline_stack.pop() != tag:
                raise ValueError("unbalanced HTML superscript or subscript")
            self._cell_parts.append(f"</{tag}>")
        elif tag in {"td", "th"} and self._cell_tag is not None and self._row is not None:
            if self._inline_stack:
                raise ValueError("unclosed HTML superscript or subscript")
            self._row.append(
                _HtmlCell(
                    text=re.sub(r"\s+", " ", "".join(self._cell_parts)).strip(),
                    row_span=self._row_span,
                    col_span=self._col_span,
                    header=self._cell_tag == "th",
                    row_header=self._row_header,
                )
            )
            self._cell_tag = None
            self._cell_parts = []
        elif tag == "tr" and self._row is not None:
            if self._cell_tag is not None:
                raise ValueError("unclosed HTML table cell")
            # A row fully covered by a preceding rowspan can legitimately have
            # no cells. It still consumes a row index in the source table.
            self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table_depth != 1 or self._row is not None:
                raise ValueError("unclosed HTML table structure")
            self._table_depth = 0


class _CandidateTextParser(HTMLParser):
    """Keep candidate words without treating malformed HTML as public markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "br":
            self.parts.append("\n")
        elif tag.casefold() in {"sup", "sub"}:
            self.parts.append(f"<{tag.casefold()}>")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"sup", "sub"}:
            self.parts.append(f"</{tag.casefold()}>")
        elif tag.casefold() in {"td", "th"}:
            self.parts.append("\t")
        elif tag.casefold() == "tr":
            self.parts.append("\n")


def _unknown_table_candidate(content: str, page_number: int, region_index: int) -> str:
    """Expose retained candidate text as unverified, never a guessed table."""
    parser = _CandidateTextParser()
    parser.feed(content)
    parser.close()
    text = "".join(parser.parts).strip()
    # Candidate text may itself contain Markdown fences. Keep the entire text
    # inside one literal block, including instruction-looking strings.
    longest = max((len(match[0]) for match in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    ref = f"sdk_p{page_number}_r{region_index}_failed_table"
    return (
        f"<!-- source-region: {ref}; source-page: {page_number}; structure: unknown -->\n\n"
        f"SDK候选文字（结构未知，非原件核验结果）。\n\n{fence}text\n{text}\n{fence}\n\n"
        f"<!-- /source-region: {ref} -->"
    )


def _positive_span(value: str | None) -> int:
    parsed = int(value or "1")
    if not 1 <= parsed <= MAX_TABLE_DIMENSION:
        raise ValueError("HTML table span out of bounds")
    return parsed


def _html_table_layout(
    content: str,
) -> tuple[list[list[str]], bool, list[TableCellFragment]]:
    """Retain source HTML spans and reject ambiguous overlapping rectangles."""
    parser = _TableHtmlParser()
    try:
        parser.feed(content)
        parser.close()
    except (ValueError, TypeError):
        return [], False, []
    if (not parser.rows or parser._row is not None or len(parser.rows) > MAX_TABLE_DIMENSION
            or parser._table_count != 1 or parser._table_depth != 0):
        return [], False, []
    anchors: dict[tuple[int, int], str] = {}
    # Track only each column's exclusive span end during the shape preflight.
    # No rectangular occupancy set or output matrix exists until the complete
    # source grid satisfies both axis limits and the total cell budget.
    occupied_until = [0] * MAX_TABLE_DIMENSION
    total_rows = len(parser.rows)
    columns = 0
    has_header = False
    layout: list[TableCellFragment] = []
    for row_index, cells in enumerate(parser.rows):
        column_index = 0
        for cell in cells:
            while column_index < MAX_TABLE_DIMENSION and occupied_until[column_index] > row_index:
                column_index += 1
            end_column = column_index + cell.col_span
            end_row = row_index + cell.row_span
            projected_rows = max(total_rows, end_row)
            projected_columns = max(columns, end_column)
            if not _bounded_table_shape(projected_rows, projected_columns):
                return [], False, []
            # The anchor can be free while a later column of its colspan is
            # covered by a preceding rowspan. Checking only the anchor loses
            # the association between both source cells.
            if any(
                occupied_until[column] > row_index for column in range(column_index, end_column)
            ):
                return [], False, []
            anchors[(row_index, column_index)] = cell.text
            column_header = cell.header and not cell.row_header
            has_header = has_header or (row_index == 0 and column_header)
            for column in range(column_index, end_column):
                occupied_until[column] = end_row
            layout.append(
                TableCellFragment(
                    row=row_index,
                    column=column_index,
                    row_span=cell.row_span,
                    column_span=cell.col_span,
                    text=cell.text,
                    is_column_header=column_header,
                    is_row_header=cell.row_header,
                )
            )
            total_rows, columns = projected_rows, projected_columns
            column_index = end_column
    if not _bounded_table_shape(total_rows, columns):
        return [], False, []
    rows = [
        [anchors.get((row_index, column_index), "") for column_index in range(columns)]
        for row_index in range(total_rows)
    ]
    return rows, has_header, layout


def _html_table_rows(content: str) -> tuple[list[list[str]], bool]:
    """Compatibility view for callers that only need the anchored text grid."""
    rows, has_header, _cells = _html_table_layout(content)
    return rows, has_header


def _markdown_table_rows(content: str) -> list[list[str]]:
    lines = [line.strip() for line in content.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return []
    rows: list[list[str]] = []
    for index, line in enumerate(lines):
        cells = [
            value.replace(r"\|", "|").strip()
            for value in re.split(r"(?<!\\)\|", line.strip().strip("|"))
        ]
        if index == 1 and cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    columns = max((len(row) for row in rows), default=0)
    if not _bounded_table_shape(len(rows), columns):
        return []
    return [row + [""] * (columns - len(row)) for row in rows]


class GlmSdkRemoteParser(DocumentParser):
    """Parse complete pages through the official ``glmocr`` HTTP service."""

    name = "glm-sdk-remote"

    def __init__(
        self,
        settings: object | None,
        http_client: httpx.AsyncClient | None = None,
        orientation_service: DocumentOrientationService | None = None,
    ) -> None:
        self.settings = settings
        self.enabled = bool(setting(settings, "glm_sdk_enabled", True)) and bool(
            setting(settings, "glm_ocr_enabled", False)
        )
        self.orientation_enabled = bool(setting(settings, "glm_sdk_orientation_enabled", True))
        self.orientation_service = orientation_service or DocumentOrientationService(
            Path(
                setting(
                    settings,
                    "glm_sdk_orientation_model_path",
                    "/models/huggingface/PP-LCNet_x1_0_doc_ori_safetensors",
                )
            ),
            allow_download=bool(setting(settings, "docling_model_download", True)),
        )
        self.api_url = str(setting(settings, "glm_sdk_url", "http://glm-ocr-sdk:5002/glmocr/parse"))
        self.timeout = float(setting(settings, "glm_sdk_timeout_seconds", 120.0))
        self.scale = float(setting(settings, "glm_sdk_render_scale", 200.0 / 72.0))
        self.max_pixels = int(setting(settings, "glm_sdk_max_image_pixels", 8_000_000))
        self.max_retries = int(setting(settings, "glm_sdk_max_retries", 1))
        self.health_ttl = float(setting(settings, "backend_health_ttl_seconds", 15.0))
        concurrency = int(setting(settings, "glm_sdk_max_concurrency", 1))
        self._semaphore = asyncio.Semaphore(concurrency)
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout), trust_env=False
        )
        self._last_status: BackendStatus | None = None
        self._last_probe_monotonic = 0.0
        self._inflight_requests: set[asyncio.Task] = set()

    @property
    def inflight_count(self) -> int:
        """Owned page tasks, including cleanup after cancellation/deadline."""
        return sum(not task.done() for task in self._inflight_requests)

    async def wait_for_idle(self, timeout: float | None = None) -> bool:
        pending = {task for task in self._inflight_requests if not task.done()}
        if not pending:
            return True
        _done, pending = await asyncio.wait(pending, timeout=timeout)
        return not pending

    @staticmethod
    async def _drain_request(request: asyncio.Task) -> None:
        # Cancelling an HTTP client does not acknowledge remote inference
        # cancellation. Keep ownership until the original HTTP task returns.
        # Cleanup may outlive the execution budget; no new request is issued.
        while not request.done():
            try:
                await asyncio.shield(request)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not request.cancelled():
            request.exception()  # retrieve an exception without replacing the caller's failure

    def _health_url(self) -> str:
        parsed = urlsplit(self.api_url)
        path = parsed.path
        if path.endswith("/glmocr/parse"):
            path = path[: -len("/glmocr/parse")] + "/health"
        else:
            path = "/health"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    async def initialize(self) -> None:
        if self.enabled and self.orientation_enabled:
            await asyncio.to_thread(self.orientation_service.initialize)

    async def probe(
        self, *, force: bool = False, refresh_unavailable: bool = False
    ) -> BackendStatus:
        if not self.enabled:
            return BackendStatus(
                name=self.name,
                state=BackendState.DISABLED,
                enabled=False,
                detail="official GLM-OCR SDK routing is disabled",
                model="glmocr",
            )
        if refresh_unavailable and self._last_status is not None and not self._last_status.ready:
            force = True
        now = time.monotonic()
        if (
            not force
            and self._last_status is not None
            and now - self._last_probe_monotonic <= self.health_ttl
        ):
            return self._last_status
        started = time.perf_counter()
        try:
            if self.orientation_enabled:
                await self.initialize()
            response = await self._client.get(self._health_url())
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                raise ValueError("unexpected health response")
            status = BackendStatus(
                name=self.name,
                state=BackendState.READY,
                detail=(
                    "official GLM-OCR SDK pipeline responded; "
                    f"CPU document orientation {'on' if self.orientation_enabled else 'off'}"
                ),
                model="glmocr",
                latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
            )
        except (httpx.HTTPError, ValueError, TypeError, OSError, RuntimeError):
            status = BackendStatus(
                name=self.name,
                state=BackendState.UNAVAILABLE,
                detail="health probe failed",
                model="glmocr",
                latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
            )
        self._last_status = status
        self._last_probe_monotonic = now
        return status

    @staticmethod
    def _cancelled(cancel_event: object | None) -> bool:
        return bool(cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)())

    def _render_page(
        self,
        source: StoredSource,
        page_number: int,
        rotation_degrees: int = 0,
    ) -> str:
        if source.mime_type != "application/pdf":
            payload = source.path.read_bytes()
            mime_type = source.mime_type if source.mime_type.startswith("image/") else "image/png"
            return f"data:{mime_type};base64,{base64.b64encode(payload).decode('ascii')}"
        import pymupdf

        with pymupdf.open(source.path) as document:
            page = document.load_page(page_number - 1)
            scale = self.scale
            pixels = max(1.0, page.rect.width * scale * page.rect.height * scale)
            if pixels > self.max_pixels:
                scale *= math.sqrt(self.max_pixels / pixels)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            payload = pixmap.tobytes("png")
        if rotation_degrees in {90, 180, 270}:
            with Image.open(io.BytesIO(payload)) as source_image:
                upright = source_image.convert("RGB").rotate(-rotation_degrees, expand=True)
                buffer = io.BytesIO()
                upright.save(buffer, format="PNG")
                payload = buffer.getvalue()
        return f"data:image/png;base64,{base64.b64encode(payload).decode('ascii')}"

    @staticmethod
    def _map_regions_to_source(
        regions: list[dict[str, object]], clockwise_rotation: int
    ) -> list[dict[str, object]]:
        """Map normalized upright SDK rectangles back to the rendered source."""

        def inverse(x: float, y: float) -> tuple[float, float]:
            if clockwise_rotation == 90:
                return y, 1_000 - x
            if clockwise_rotation == 180:
                return 1_000 - x, 1_000 - y
            if clockwise_rotation == 270:
                return 1_000 - y, x
            return x, y

        if clockwise_rotation not in {0, 90, 180, 270}:
            raise ValueError("Invalid applied document rotation")
        output = []
        for region in regions:
            mapped = dict(region)
            bbox = region.get("bbox_2d")
            if isinstance(bbox, list) and len(bbox) == 4:
                left, top, right, bottom = map(float, bbox)
                points = [
                    inverse(x, y)
                    for x, y in [(left, top), (right, top), (right, bottom), (left, bottom)]
                ]
                mapped["bbox_2d"] = [
                    min(p[0] for p in points),
                    min(p[1] for p in points),
                    max(p[0] for p in points),
                    max(p[1] for p in points),
                ]
            output.append(mapped)
        return output

    @staticmethod
    def _page_regions(
        payload: object, *, warnings: list[PipelineWarning] | None = None, page_number: int | None = None,
    ) -> list[dict[str, object]]:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError("SDK layout JSON is invalid") from exc
        if not isinstance(payload, list):
            raise ValueError("SDK layout is not a list")
        if len(payload) == 1 and isinstance(payload[0], list):
            payload = payload[0]
        regions: list[dict[str, object]] = []
        for fallback_index, raw in enumerate(payload):
            try:
                if not isinstance(raw, dict):
                    raise ValueError("SDK region is not an object")
                label = raw.get("label")
                native_label = raw.get("native_label")
                content = raw.get("content")
                bbox = raw.get("bbox_2d")
                if not isinstance(label, str) or not label.strip():
                    raise ValueError("SDK region has no label")
                if content is not None and not isinstance(content, str):
                    raise ValueError("SDK region content is not text")
                normalized_bbox: list[float] | None = None
                if bbox is not None:
                    if (not isinstance(bbox, list) or len(bbox) != 4
                            or not all(type(value) in {int, float} for value in bbox)):
                        raise ValueError("SDK region bbox is invalid")
                    normalized_bbox = [float(value) for value in bbox]
                    if not all(math.isfinite(value) and 0 <= value <= 1_000 for value in normalized_bbox):
                        raise ValueError("SDK region bbox is out of range")
                    if normalized_bbox[0] > normalized_bbox[2] or normalized_bbox[1] > normalized_bbox[3]:
                        raise ValueError("SDK region bbox is inverted")
                raw_index = raw.get("index", fallback_index)
                index = raw_index if type(raw_index) is int and raw_index >= 0 else fallback_index
                regions.append({"index": index, "label": label.strip().casefold(),
                                "native_label": native_label.casefold() if isinstance(native_label, str) else "",
                                "content": content or "", "bbox_2d": normalized_bbox})
            except ValueError as exc:
                if warnings is not None:
                    warnings.append(PipelineWarning(
                        code="glm_sdk_local_region_unreadable",
                        message="an SDK region could not be fully read; valid neighboring regions were retained",
                        severity=WarningSeverity.ERROR, page_number=page_number, backend=GlmSdkRemoteParser.name,
                        details={"region_index": fallback_index, "stage": "native_region_readback",
                                 "reason": str(exc), "raw_response_modified": False},
                    ))
                # Literal content remains useful even if its envelope is bad.
                # Unknown geometry and roles stay unknown; no answer is added.
                if isinstance(raw, dict) and isinstance(raw.get("content"), str):
                    label = raw.get("label")
                    regions.append({"index": fallback_index,
                                    "label": label.strip().casefold() if isinstance(label, str) and label.strip() else "unknown",
                                    "native_label": "", "content": raw["content"], "bbox_2d": None})

        def region_index(item: dict[str, object]) -> int:
            value = item.get("index")
            return value if isinstance(value, int) else 0

        return sorted(regions, key=region_index)

    @staticmethod
    def _table_fragment(
        region: dict[str, object], page_number: int, ordinal: int
    ) -> TableFragment | None:
        content = str(region.get("content", "") or "").strip()
        rows: list[list[str]]
        has_header = False
        cells: list[TableCellFragment] = []
        if re.search(r"<table\b", content, re.IGNORECASE):
            rows, has_header, cells = _html_table_layout(content)
        else:
            rows = _markdown_table_rows(content)
        bbox = region.get("bbox_2d")
        if not rows or not isinstance(bbox, list):
            return None
        columns = max(len(row) for row in rows)
        if columns <= 0:
            return None
        left, top, right, bottom = (float(value) / 1_000 for value in bbox)
        fragment_id = f"sdk_p{page_number}_t{ordinal}"
        marker = f"<!-- table-fragment: {fragment_id} -->"
        markdown = render_gfm_rows(rows)
        width = max(0.0, right - left)
        boundaries = [left + width * index / columns for index in range(columns + 1)]
        return TableFragment(
            fragment_id=fragment_id,
            page_number=page_number,
            ordinal=ordinal,
            normalized_bbox=(left, top, right, bottom),
            num_rows=len(rows),
            num_cols=columns,
            rows=rows,
            column_boundaries=[round(value, 6) for value in boundaries],
            markdown=markdown,
            rendered=f"{marker}\n\n{markdown}",
            has_column_header=has_header,
            source_kind="glm",
            cells=cells,
        )

    @classmethod
    def _render_regions(
        cls, regions: list[dict[str, object]], page_number: int,
        *, warnings: list[PipelineWarning] | None = None,
    ) -> tuple[str, list[TableFragment]]:
        output: list[str] = []
        fragments: list[TableFragment] = []
        table_ordinal = 0
        for region in regions:
            label = str(region["label"])
            native_label = str(region.get("native_label", ""))
            content = str(region.get("content", "") or "").strip()
            if label == "table" or native_label == "table":
                table_ordinal += 1
                fragment = cls._table_fragment(region, page_number, table_ordinal)
                if fragment is not None:
                    fragments.append(fragment)
                    output.append(fragment.rendered)
                elif re.search(r"<table\b", content, re.IGNORECASE):
                    index = region.get("index", table_ordinal - 1)
                    region_index = index if isinstance(index, int) and index >= 0 else table_ordinal - 1
                    output.append(_unknown_table_candidate(content, page_number, region_index))
                    if warnings is not None:
                        warnings.append(PipelineWarning(
                            code="glm_sdk_unusable_table_structure",
                            message="an SDK table candidate has unknown structure; other page regions were retained",
                            severity=WarningSeverity.ERROR, page_number=page_number, backend=cls.name,
                            details={"source_ref": f"sdk_p{page_number}_r{region_index}_failed_table",
                                     "region_index": region_index,
                                     "candidate_text_is_original_source_truth": False},
                        ))
                elif content:
                    output.append(content)
                continue
            if label == "image" or native_label in {
                "chart",
                "image",
                "footer_image",
                "header_image",
            }:
                output.append("<!-- image -->")
                if content:
                    output.append(content)
                continue
            if not content:
                continue
            if native_label == "doc_title" and not content.lstrip().startswith("#"):
                content = f"# {content}"
            elif native_label == "paragraph_title" and not content.lstrip().startswith("#"):
                content = f"## {content}"
            output.append(content)
        obstruction_regions: list[tuple[float, float, float, float]] = []
        for region in regions:
            obstruction = str(region.get("label", "")) == "image" or str(
                region.get("native_label", "")
            ) in {"seal", "signature", "handwriting", "watermark"}
            bbox = region.get("bbox_2d")
            if not obstruction or not isinstance(bbox, list) or len(bbox) != 4:
                continue
            obstruction_regions.append(
                (
                    float(bbox[0]) / 1_000,
                    float(bbox[1]) / 1_000,
                    float(bbox[2]) / 1_000,
                    float(bbox[3]) / 1_000,
                )
            )
        for fragment in fragments:
            left, top, right, bottom = fragment.normalized_bbox
            fragment.visual_obstructions = [
                obstruction
                for obstruction in obstruction_regions
                if obstruction[0] < right
                and obstruction[2] > left
                and obstruction[1] < bottom
                and obstruction[3] > top
            ]
        return "\n\n".join(output).strip(), fragments

    def _record_response(
        self,
        response: httpx.Response,
        *,
        document_id: str,
        request_id: str,
        page_number: int,
        attempt: int,
        source_sha256: str | None,
        rotation_degrees: int,
    ) -> None:
        """Keep received bytes private before decoding, without affecting parsing."""
        try:
            directory = (
                StorageService(self.settings).logs_dir(document_id)
                / "glm-sdk"
                / request_id
                / f"page-{page_number:06d}"
            )
            body = response.content
            body_file = f"attempt-{attempt:03d}.body"
            metadata = {
                "schema": "glm-sdk-http-response/1",
                "document_id": document_id,
                "request_id": request_id,
                "source_sha256": source_sha256,
                "physical_page": page_number,
                "attempt": attempt,
                "applied_rotation_degrees": rotation_degrees,
                "http_status": response.status_code,
                "body_file": body_file,
                "body_bytes": len(body),
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "body_complete": True,
                "phase": "received_before_validation",
            }
            StorageService._atomic_write(directory / body_file, body)
            StorageService._atomic_write(
                directory / f"attempt-{attempt:03d}.json",
                json.dumps(metadata, separators=(",", ":")).encode(),
            )
        except Exception as exc:
            # Never log response content, request URLs, headers or exception text.
            logger.warning(
                "GLM SDK private response recording failed page=%d error_type=%s",
                page_number,
                type(exc).__name__,
            )

    def _record_transport_failure(
        self, *, document_id: str, request_id: str, page_number: int, attempt: int,
        source_sha256: str | None, details: dict[str, object],
    ) -> None:
        """Record unknown remote execution without inventing a received body."""
        try:
            target = (StorageService(self.settings).logs_dir(document_id) / "glm-sdk" / request_id
                      / f"page-{page_number:06d}" / f"attempt-{attempt:03d}.transport")
            StorageService._atomic_write(target, json.dumps({
                "schema": "glm-sdk-http-transport-failure/1", "document_id": document_id,
                "request_id": request_id, "physical_page": page_number, "attempt": attempt,
                "source_sha256": source_sha256, "response_received": False,
                "server_model_calls": None, **details,
            }, separators=(",", ":")).encode())
        except Exception as exc:
            logger.warning("GLM SDK transport receipt failed page=%d error_type=%s",
                           page_number, type(exc).__name__)

    @staticmethod
    def _source_digest(source: StoredSource) -> str | None:
        try:
            with source.path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError:
            return None

    async def _request_page(
        self,
        source: StoredSource,
        page_number: int,
        cancel_event: object | None,
        rotation_degrees: int = 0,
        *,
        document_id: str,
        request_id: str,
        source_sha256: str | None,
        options: ContentParseOptions,
    ) -> tuple[PageParseResult, list[TableFragment], int]:
        started = time.perf_counter()
        request_count = 0
        http_duration_ms = 0
        failure_details: dict[str, object] = {}
        source_id = (
            source.path.parent.parent.name
            if source.path.parent.name == "input"
            else source.path.stem
        )
        source_id = re.sub(r"[^A-Za-z0-9_-]", "_", source_id)[:128] or "unknown"

        def _page_result(**values: Any) -> PageParseResult:
            page = PageParseResult(**values)
            page._sdk_requests = request_count
            logger.info(
                "GLM_SDK_PAGE source_id=%s page=%d status=%s sdk_requests=%d "
                "page_duration_ms=%d http_duration_ms=%d",
                source_id,
                page_number,
                page.status.value,
                request_count,
                page.duration_ms,
                http_duration_ms,
            )
            return page

        if self._cancelled(cancel_event):
            raise ParserCancelledError("job was cancelled")
        try:
            image_uri = await asyncio.to_thread(
                self._render_page,
                source,
                page_number,
                rotation_degrees,
            )
            applied_rotation = rotation_degrees % 360
            if self.orientation_enabled:
                image_uri, clockwise_rotation, confidence = await asyncio.to_thread(
                    self.orientation_service.orient, image_uri
                )
                applied_rotation = (applied_rotation + clockwise_rotation) % 360
                logger.info(
                    "GLM SDK orientation page=%d clockwise_rotation=%d confidence=%.6f",
                    page_number,
                    applied_rotation,
                    confidence,
                )
            payload: dict[str, Any] | None = None
            last_error_code = "glm_sdk_http_error"
            async with self._semaphore:
                for attempt in range(self.max_retries + 1):
                    if self._cancelled(cancel_event):
                        raise ParserCancelledError("job was cancelled")
                    try:
                        request_timeout = remaining_timeout(options, cap=min(self.timeout, 120.0))
                        request_count += 1
                        http_started = time.perf_counter()
                        try:
                            response = await self._client.post(
                                self.api_url,
                                json={"images": [image_uri]},
                                headers={"Content-Type": "application/json"},
                                timeout=request_timeout,
                            )
                        finally:
                            http_duration_ms += max(
                                0, round((time.perf_counter() - http_started) * 1_000)
                            )
                        await asyncio.to_thread(
                            self._record_response,
                            response,
                            document_id=document_id,
                            request_id=request_id,
                            page_number=page_number,
                            attempt=request_count,
                            source_sha256=source_sha256,
                            rotation_degrees=applied_rotation,
                        )
                        if self._cancelled(cancel_event):
                            raise ParserCancelledError("job was cancelled")
                        remaining_timeout(options, cap=min(self.timeout, 120.0))
                        response.raise_for_status()
                        value = response.json()
                        if not isinstance(value, dict):
                            raise ValueError("SDK response is not an object")
                        if value.get("error"):
                            raise ValueError("SDK response contains an error")
                        payload = value
                        break
                    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
                        # Only a failure before an HTTP request can reach the
                        # server may be retried. There is no SDK idempotency or
                        # remote cancellation contract for an accepted request.
                        last_error_code = "glm_sdk_connection_unavailable"
                        failure_details = {"retry_classification": "before_http_send",
                                           "server_model_calls": None, "remote_execution_unknown": False}
                        await asyncio.to_thread(self._record_transport_failure,
                            document_id=document_id, request_id=request_id, page_number=page_number,
                            attempt=request_count, source_sha256=source_sha256, details=failure_details)
                    except httpx.TimeoutException:
                        last_error_code = "glm_sdk_timeout"
                        failure_details = {"retry_classification": "execution_unknown_no_retry",
                                           "server_model_calls": None, "remote_execution_unknown": True}
                        await asyncio.to_thread(self._record_transport_failure,
                            document_id=document_id, request_id=request_id, page_number=page_number,
                            attempt=request_count, source_sha256=source_sha256, details=failure_details)
                        break
                    except httpx.HTTPStatusError as exc:
                        last_error_code = "glm_sdk_http_error"
                        failure_details = {"http_status": exc.response.status_code,
                                           "retry_classification": "response_received_no_idempotency_no_retry",
                                           "server_model_calls": None, "remote_execution_unknown": True}
                        break
                    except httpx.HTTPError:
                        last_error_code = "glm_sdk_http_error"
                        failure_details = {"retry_classification": "execution_unknown_no_retry",
                                           "server_model_calls": None, "remote_execution_unknown": True}
                        await asyncio.to_thread(self._record_transport_failure,
                            document_id=document_id, request_id=request_id, page_number=page_number,
                            attempt=request_count, source_sha256=source_sha256, details=failure_details)
                        break
                    except (ValueError, TypeError):
                        last_error_code = "glm_sdk_invalid_response"
                        failure_details = {"retry_classification": "invalid_response_no_retry",
                                           "server_model_calls": None}
                        break
                    if attempt < self.max_retries:
                        await asyncio.sleep(min(2.0, 0.25 * (2**attempt),
                                                remaining_timeout(options, cap=min(self.timeout, 120.0))))
            if payload is None:
                raise ValueError(last_error_code)
            layout = payload.get("layout_details", payload.get("json_result"))
            warnings: list[PipelineWarning] = []
            regions = self._page_regions(layout, warnings=warnings, page_number=page_number)
            regions = self._map_regions_to_source(regions, applied_rotation)
            markdown, fragments = self._render_regions(regions, page_number, warnings=warnings)
            if not markdown:
                markdown_result = payload.get("md_results", payload.get("markdown_result", ""))
                if isinstance(markdown_result, str):
                    markdown = re.sub(
                        r"!\[[^\]]*\]\([^)]*\)", "<!-- image -->", markdown_result
                    ).strip()
            status = PageStatus.FAILED if warnings else PageStatus.COMPLETED
            if not markdown:
                status = PageStatus.FAILED
                warnings.append(
                    PipelineWarning(
                        code="glm_sdk_empty_page",
                        message="the official GLM-OCR SDK returned no usable page content",
                        severity=WarningSeverity.ERROR,
                        page_number=page_number,
                        backend=self.name,
                    )
                )
            return (
                _page_result(
                    page_number=page_number,
                    status=status,
                    backend=self.name,
                    content=markdown or None,
                    duration_ms=max(0, round((time.perf_counter() - started) * 1_000)),
                    warnings=warnings,
                ),
                fragments,
                len(regions),
            )
        except (ParserCancelledError, ParserTimeoutError, TimeoutError, MemoryError):
            raise
        except (ValueError, TypeError, OSError, httpx.HTTPError) as exc:
            code = str(exc) if str(exc).startswith("glm_sdk_") else "glm_sdk_invalid_response"
            return (
                _page_result(
                    page_number=page_number,
                    status=PageStatus.FAILED,
                    backend=self.name,
                    duration_ms=max(0, round((time.perf_counter() - started) * 1_000)),
                    warnings=[
                        PipelineWarning(
                            code=code,
                            message="the official GLM-OCR SDK page candidate could not be produced",
                            severity=WarningSeverity.ERROR,
                            page_number=page_number,
                            backend=self.name,
                            details=failure_details or None,
                        )
                    ],
                ),
                [],
                0,
            )

    async def parse(
        self,
        source: StoredSource,
        options: ContentParseOptions,
        *,
        document_id: str,
        progress_callback: ProgressCallback | None = None,
        cancel_event: object | None = None,
        rotation_by_page: dict[int, int] | None = None,
    ) -> DocumentParseResult:
        if not self.enabled:
            from app.parsers.base import ParserUnavailableError

            raise ParserUnavailableError("official GLM-OCR SDK routing is disabled")
        pages = parse_page_range(options.page_range, source.page_count)
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        source_sha256 = await asyncio.to_thread(self._source_digest, source)

        async def notify(completed: int, event: str) -> None:
            if progress_callback is None:
                return
            value = progress_callback(completed, len(pages), event)
            if asyncio.iscoroutine(value):
                await value

        await notify(0, "document.started")
        completed = 0

        async def run(page_number: int) -> tuple[PageParseResult, list[TableFragment], int]:
            nonlocal completed
            page_started = time.perf_counter()
            budget = remaining_timeout(options, cap=min(self.timeout, 120.0))
            page_options = attach_deadline(options, budget)
            try:
                async with asyncio.timeout(budget):
                    request = asyncio.create_task(self._request_page(
                        source,
                        page_number,
                        cancel_event,
                        (rotation_by_page or {}).get(page_number, 0),
                        document_id=document_id,
                        request_id=request_id,
                        source_sha256=source_sha256,
                        options=page_options,
                    ))
                    self._inflight_requests.add(request)
                    try:
                        while not request.done():
                            if self._cancelled(cancel_event):
                                raise ParserCancelledError("job was cancelled")
                            await asyncio.wait({request}, timeout=0.05)
                        value = await request
                    finally:
                        await self._drain_request(request)
                        self._inflight_requests.discard(request)
            except TimeoutError:
                value = (
                    PageParseResult(
                        page_number=page_number,
                        status=PageStatus.FAILED,
                        backend=self.name,
                        duration_ms=min(
                            max(0, round((time.perf_counter() - page_started) * 1_000)),
                            max(0, round(budget * 1_000)),
                        ),
                        warnings=[
                            PipelineWarning(
                                code="glm_sdk_timeout",
                                message=(
                                    "the official GLM-OCR SDK page candidate exceeded "
                                    "the complete per-page time budget"
                                ),
                                severity=WarningSeverity.ERROR,
                                page_number=page_number,
                                backend=self.name,
                                details={"budget_seconds": budget, "server_model_calls": None,
                                         "remote_execution_stopped": None},
                            )
                        ],
                    ),
                    [],
                    0,
                )
            completed += 1
            event = "page.failed" if value[0].status == PageStatus.FAILED else "page.completed"
            await notify(completed, event)
            return value

        # Keep page requests ordered. The official SDK already parallelizes OCR
        # regions inside a page, while starting every page task at once made the
        # per-page diagnostic duration include semaphore queue time. More
        # importantly, a timed-out page must stop later candidate calls so the
        # primary parser result remains available within a bounded budget.
        page_outputs: list[tuple[PageParseResult, list[TableFragment], int]] = []
        stop_after_timeout = False
        for page_number in pages:
            if stop_after_timeout:
                completed += 1
                page_outputs.append(
                    (
                        PageParseResult(
                            page_number=page_number,
                            status=PageStatus.FAILED,
                            backend=self.name,
                            duration_ms=0,
                            warnings=[
                                PipelineWarning(
                                    code="glm_sdk_skipped_after_timeout",
                                    message=(
                                        "the official GLM-OCR SDK page candidate was skipped "
                                        "after an earlier page exhausted the time budget"
                                    ),
                                    severity=WarningSeverity.ERROR,
                                    page_number=page_number,
                                    backend=self.name,
                                )
                            ],
                        ),
                        [],
                        0,
                    )
                )
                await notify(completed, "page.failed")
                continue
            value = await run(page_number)
            page_outputs.append(value)
            stop_after_timeout = any(
                warning.code == "glm_sdk_timeout" for warning in value[0].warnings
            )
        parsed_pages = sorted((item[0] for item in page_outputs), key=lambda page: page.page_number)
        fragments = [fragment for item in page_outputs for fragment in item[1]]
        region_count = sum(item[2] for item in page_outputs)
        failed = sum(page.status == PageStatus.FAILED for page in parsed_pages)
        markdown = "\n\n\f\n\n".join(page.content or "" for page in parsed_pages)
        result = DocumentParseResult(
            document_id=document_id,
            filename=source.filename,
            mime_type=source.mime_type,
            page_count=source.page_count,
            processed_pages=len(parsed_pages) - failed,
            markdown=markdown,
            plain_text="",
            pages=parsed_pages,
            pipeline=ParsePipeline(
                profile=options.profile.value,
                primary=self.name,
                ocr=self.name,
            ),
            route_summary=RouteSummary(
                native_text_pages=0,
                pages_with_ocr=len(parsed_pages) - failed,
                ocr_regions=region_count,
                failed_pages=failed,
            ),
            usage=ParseUsage(
                input_bytes=source.size_bytes,
                duration_ms=max(0, round((time.perf_counter() - started) * 1_000)),
            ),
        )
        result._table_fragments.extend(fragments)
        return result

    async def close(self) -> None:
        await self.wait_for_idle()
        if self._owns_client:
            await self._client.aclose()
