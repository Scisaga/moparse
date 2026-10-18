"""Optional independent Docling role verification for native cross-page tables.

MinerU owns every visible character and grid anchor. Docling can only establish
header roles and independent column geometry after complete source agreement.
A rejected edge remains unmergeable, even if its fragment was verified against
another neighbor. No document vocabulary or financial metric is consulted.
"""

from __future__ import annotations

import copy
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from types import SimpleNamespace

from markdown_it import MarkdownIt

from app.models.backend import BackendStatus
from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult, PipelineWarning, WarningSeverity
from app.models.source import StoredSource
from app.parsers.base import ParserUnavailableError
from app.parsers.docling_standard import DoclingStandardParser
from app.parsers.glm_ocr_remote import GlmOcrRemoteAdapter
from app.services.table_service import (
    PageFurnitureFragment,
    TableFragment,
    _context_evidence,
    _continuous_table_context,
    _has_column_boundaries,
    _preceding_content,
    _table_structure_marker,
    _units_are_consistent,
)
from app.utils.page_range import format_page_range

_MARKDOWN = MarkdownIt("commonmark")


def _text(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")


def _iou(left: tuple, right: tuple) -> float:
    intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    union = (
        (left[2] - left[0]) * (left[3] - left[1])
        + (right[2] - right[0]) * (right[3] - right[1])
        - intersection
    )
    return intersection / union if union > 0 else 0.0


def boundary_candidates(
    fragments: list[TableFragment],
) -> list[tuple[TableFragment, TableFragment]]:
    by_page: dict[int, list[TableFragment]] = defaultdict(list)
    for fragment in fragments:
        if fragment.source_kind == "mineru":
            by_page[fragment.page_number].append(fragment)
    pairs = []
    for page in sorted(by_page):
        if page + 1 not in by_page:
            continue
        left = max(by_page[page], key=lambda item: item.ordinal)
        right = min(by_page[page + 1], key=lambda item: item.ordinal)
        if (
            left.valid
            and right.valid
            and left.num_cols == right.num_cols
            and left.normalized_bbox[3] >= 0.85
            and right.normalized_bbox[1] <= 0.15
        ):
            pairs.append((left, right))
    return pairs


def _header_signature(fragment: TableFragment) -> tuple | None:
    rows = fragment.header_row_indices
    if not rows:
        return None
    # A partly labelled band does not prove roles for its nonempty cells.
    if any(
        cell.row in rows and cell.text.strip() and not cell.is_column_header
        for cell in fragment.cells
    ):
        return None
    return (
        tuple(tuple(_text(value) for value in fragment.rows[row]) for row in rows),
        tuple(
            sorted(
                (
                    cell.row,
                    cell.column,
                    cell.row_span,
                    cell.column_span,
                    _text(cell.text),
                    cell.is_column_header,
                    cell.is_row_header,
                )
                for cell in fragment.cells
                if cell.row in rows
            )
        ),
    )


def _same_source_band(native: TableFragment, independent: TableFragment) -> bool:
    rows = independent.header_row_indices
    if _header_signature(independent) is None or not rows or max(rows) >= len(native.rows):
        return False
    if any(
        tuple(_text(value) for value in native.rows[row])
        != tuple(_text(value) for value in independent.rows[row])
        for row in rows
    ):
        return False

    def cells(fragment):
        return sorted(
            (cell.row, cell.column, cell.row_span, cell.column_span, _text(cell.text))
            for cell in fragment.cells
            if cell.row in rows
        )

    return cells(native) == cells(independent)


def _unique_match(
    fragment: TableFragment, independent: list[TableFragment]
) -> TableFragment | None:
    matches = [
        item
        for item in independent
        if item.valid
        and item.page_number == fragment.page_number
        and item.num_cols == fragment.num_cols
        and _iou(item.normalized_bbox, fragment.normalized_bbox) >= 0.8
    ]
    return matches[0] if len(matches) == 1 else None


def _source_column_geometry(fragment: TableFragment) -> bool:
    """Reject the legacy uniform fallback unless actual cell boxes support it.

    Docling's exported boundaries average the source text-cell edges. Every
    boundary must have observed edges, and every header anchor needs a valid
    physical box. This checks the evidence behind the numbers, not their shape.
    """
    if not _has_column_boundaries(fragment) or not fragment.header_row_indices:
        return False
    observations: dict[int, list[float]] = defaultdict(list)
    for cell in fragment.cells:
        bbox = cell.normalized_bbox
        valid = (
            bbox is not None
            and len(bbox) == 4
            and all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in bbox)
            and bbox[0] < bbox[2]
            and bbox[1] < bbox[3]
        )
        if not valid:
            if cell.row in fragment.header_row_indices:
                return False
            continue
        assert bbox is not None
        observations[cell.column].append(bbox[0])
        observations[cell.column + cell.column_span].append(bbox[2])
    return all(
        observations[index]
        and abs(sum(observations[index]) / len(observations[index]) - value) <= 0.000002
        for index, value in enumerate(fragment.column_boundaries)
    )


def _scope(
    fragment: TableFragment, content: dict[int, str], fragments: list[TableFragment]
) -> tuple | None:
    prefix = _preceding_content(content.get(fragment.page_number, ""), fragment, fragments)
    units, _other = _context_evidence(prefix)
    caption_units, caption_text = _context_evidence(fragment.caption or "")
    for dimension, values in caption_units.items():
        units[dimension] = units.get(dimension, ()) + values
    if not _units_are_consistent(units):
        return None
    canonical_units = tuple(sorted((dimension, values[0]) for dimension, values in units.items()))
    tokens = _MARKDOWN.parse(prefix)
    headings = tuple(
        _text(tokens[index + 1].content)
        for index, token in enumerate(tokens[:-1])
        if token.type == "heading_open" and tokens[index + 1].type == "inline"
    )
    return canonical_units, headings, caption_text


def _furniture_agrees(native: TableFragment, independent: TableFragment) -> bool:
    # Use the native typed roles in the exporter. The optional verifier also
    # checks those same physical decorations against independent source labels.
    sources = [
        source for source in native.page_furniture if source.page_number == native.page_number
    ]
    for source in sources:
        matches = [
            other
            for other in independent.page_furniture
            if other.page_number == source.page_number
            and other.label == source.label
            and _text(other.text) == _text(source.text)
            and source.normalized_bbox is not None
            and other.normalized_bbox is not None
            and max(
                abs(a - b)
                for a, b in zip(source.normalized_bbox, other.normalized_bbox, strict=True)
            )
            <= 0.02
        ]
        if len(matches) != 1:
            return False
    return True


def _copy_header_metadata(native: TableFragment, independent: TableFragment) -> None:
    rows = independent.header_row_indices
    roles = {
        (cell.row, cell.column, cell.row_span, cell.column_span): cell
        for cell in independent.cells
        if cell.row in rows
    }
    for cell in native.cells:
        role = roles.get((cell.row, cell.column, cell.row_span, cell.column_span))
        if role is not None:
            cell.is_column_header = role.is_column_header
            cell.is_row_header = role.is_row_header
    native.has_column_header = True
    native.header_scope_complete = True
    native.caption_scope_complete = True
    native.column_boundaries = independent.column_boundaries[:]
    native.header_role_source = "docling-v1:complete-source-band-agreement"


@dataclass(slots=True)
class HeaderDecision:
    left: str
    right: str
    accepted: bool
    reason: str


def verify_cached_header_evidence(
    result: DocumentParseResult,
    independent: DocumentParseResult,
    pairs: list[tuple[TableFragment, TableFragment]] | None = None,
) -> list[HeaderDecision]:
    """Pure metadata verification using completed outputs; never invokes models."""
    native = [item for item in result._table_fragments if isinstance(item, TableFragment)]
    docs = [item for item in independent._table_fragments if isinstance(item, TableFragment)]
    content = {page.page_number: page.content or "" for page in result.pages}
    doc_content = {page.page_number: page.content or "" for page in independent.pages}
    furniture = [item for item in result._page_furniture if isinstance(item, PageFurnitureFragment)]
    for fragment in native:
        if fragment.source_kind == "mineru":
            fragment.header_verification_required = True
            fragment.verified_next_fragments = []
    decisions = []
    accepted: dict[str, tuple[TableFragment, TableFragment]] = {}
    for left, right in pairs if pairs is not None else boundary_candidates(native):

        def reject(reason, left=left, right=right):
            decisions.append(HeaderDecision(left.fragment_id, right.fragment_id, False, reason))

        dl, dr = _unique_match(left, docs), _unique_match(right, docs)
        if dl is None or dr is None:
            reject("missing_or_ambiguous_physical_table_match")
            continue
        if not _source_column_geometry(dl) or not _source_column_geometry(dr):
            reject("independent_column_geometry_unknown")
            continue
        if not _same_source_band(left, dl) or not _same_source_band(right, dr):
            reject("complete_header_text_or_spans_disagree")
            continue
        if _header_signature(dl) != _header_signature(dr):
            reject("independent_complete_headers_differ")
            continue
        if (
            content.get(left.page_number, "").count(left.rendered) != 1
            or content.get(right.page_number, "").count(right.rendered) != 1
        ):
            reject("native_rendering_not_uniquely_located")
            continue
        left_scope, right_scope = _scope(left, content, native), _scope(right, content, native)
        if (
            left_scope is None
            or right_scope is None
            or left_scope != _scope(dl, doc_content, docs)
            or right_scope != _scope(dr, doc_content, docs)
        ):
            reject("source_title_or_unit_context_disagrees")
            continue
        if not _furniture_agrees(left, dl) or not _furniture_agrees(right, dr):
            reject("source_furniture_disagrees")
            continue
        # Reuse the existing exact-period, explicit-unit, surrounding-body and
        # full-document furniture checks BEFORE authorizing any header removal.
        left_view, right_view = copy.deepcopy(left), copy.deepcopy(right)
        _copy_header_metadata(left_view, dl)
        _copy_header_metadata(right_view, dr)
        left_view.verified_next_fragments = [right.fragment_id]
        if not _continuous_table_context([left_view, right_view], content, native, furniture):
            reject("cross_page_source_context_not_established")
            continue
        accepted[left.fragment_id] = (left, dl)
        accepted[right.fragment_id] = (right, dr)
        left.verified_next_fragments.append(right.fragment_id)
        decisions.append(
            HeaderDecision(
                left.fragment_id,
                right.fragment_id,
                True,
                "complete_independent_header_and_source_scope_agreement",
            )
        )
    pages = {page.page_number: page for page in result.pages}
    for fragment, doc in accepted.values():
        old_rendered = fragment.rendered
        old_marker = fragment._structure_marker
        _copy_header_metadata(fragment, doc)
        marker = _table_structure_marker([fragment], fragment.fragment_id)
        fragment.rendered = old_rendered.replace(old_marker, marker, 1)
        fragment._structure_marker = marker
        page = pages[fragment.page_number]
        page.content = (page.content or "").replace(old_rendered, fragment.rendered, 1)
    return decisions


class DoclingHeaderVerificationService:
    name = "docling-header-verifier"

    def __init__(self, settings: object | None, glm_adapter: GlmOcrRemoteAdapter):
        overrides = {
            "docling_device": "cpu",
            "docling_table_mode": "accurate",
            "docling_do_cell_matching": False,
            "docling_pdf_backend": "pypdfium",
            "docling_page_workers": 1,
            "docling_num_threads": 4,
            "parser_workers": 1,
        }
        if hasattr(settings, "model_copy"):
            configured = settings.model_copy(update=overrides)
        else:
            configured = SimpleNamespace(**{**getattr(settings, "__dict__", {}), **overrides})
        self.parser = DoclingStandardParser(configured, glm_adapter)

    async def initialize(self) -> None:
        await self.parser.initialize()

    async def close(self) -> None:
        await self.parser.close()

    async def probe(self, *, force: bool = False) -> BackendStatus:
        status = await self.parser.probe(force=force)
        return status.model_copy(
            update={
                "name": self.name,
                "detail": "Independent complete header-role verification; "
                "TableFormer V1, CPU, matching=False, PyPdfium, workers=1, threads=4; "
                + (status.detail or ""),
            }
        )

    async def require_ready(self) -> None:
        status = await self.probe()
        if not status.ready:
            raise ParserUnavailableError(
                "the configured independent Docling header verifier is unavailable",
                details={"backend": self.name, "reason": status.detail},
            )

    async def apply(
        self,
        result: DocumentParseResult,
        source: StoredSource,
        options: ContentParseOptions,
        *,
        cancel_event: object | None = None,
    ) -> None:
        await self.require_ready()
        fragments = [item for item in result._table_fragments if isinstance(item, TableFragment)]
        pairs = boundary_candidates(fragments)
        result.pipeline.primary = "mineru-advanced-txt+docling-header-verifier"
        if not pairs:
            return
        pages = sorted({fragment.page_number for pair in pairs for fragment in pair})
        started = time.perf_counter()
        independent = await self.parser.parse(
            source,
            options.model_copy(update={"unit_range": format_page_range(pages)}),
            document_id=result.document_id,
            progress_callback=None,
            cancel_event=cancel_event,
        )
        returned = [page.page_number for page in independent.pages]
        if len(returned) != len(pages) or set(returned) != set(pages):
            from app.parsers.base import ParserError

            raise ParserError(
                "the independent header verifier returned an incomplete physical page set"
            )
        decisions = verify_cached_header_evidence(result, independent, pairs)
        result.warnings.append(
            PipelineWarning(
                code="independent_header_verification_used",
                message="independent complete header roles and source scope were checked without changing native text or cell values",
                severity=WarningSeverity.INFO,
                backend=self.name,
                details={
                    "pages": pages,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "candidate_pairs": len(pairs),
                    "accepted_pairs": sum(item.accepted for item in decisions),
                    "decisions": [
                        {
                            "left": item.left,
                            "right": item.right,
                            "accepted": item.accepted,
                            "reason": item.reason,
                        }
                        for item in decisions
                    ],
                },
            )
        )
