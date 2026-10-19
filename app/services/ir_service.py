"""Materialize a content parse result from the proven page-oriented parser pipeline."""

from __future__ import annotations

import hashlib
import re
import statistics
from pathlib import Path

from app.models.content_result import (
    ContentLinks,
    ContentParseResult,
    ContentQualitySummary,
    ContentRegion,
    ContentRenderings,
    ContentSource,
    ContentUnit,
    ElementProvenance,
    ElementQuality,
    LogicalTable,
    NormalizedBBox,
    ParsedTable,
    ParseRuntime,
    ParseWarning,
    ProvenanceSource,
    ProvenanceSourceKind,
    RegionType,
    SourceKind,
    TableCell,
    TextBlock,
    UnitDiagnostics,
    UnitType,
)
from app.models.parse_result import (
    DocumentParseResult,
    PageParseResult,
    PageStatus,
    QualityVerdict,
)
from app.models.source import StoredSource
from app.models.source_evidence import SourceRegionEvidence
from app.services.evidence_service import PageEvidence, compact_text
from app.services.table_service import TableCellFragment, TableFragment
from app.utils.settings import setting

_MARKDOWN_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
_MARKER_LINE = re.compile(r"^\s*<!--.*-->\s*$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _bbox(values: tuple[float, float, float, float] | None) -> NormalizedBBox | None:
    if values is None:
        return None
    left, top, right, bottom = values
    try:
        return NormalizedBBox(left=left, top=top, right=right, bottom=bottom)
    except ValueError:
        return None


def _native_bbox(
    values: tuple[float, float, float, float], evidence: PageEvidence
) -> NormalizedBBox | None:
    if evidence.page_width <= 0 or evidence.page_height <= 0:
        return None
    left, top, right, bottom = values
    return _bbox(
        (
            max(0.0, min(1.0, left / evidence.page_width)),
            max(0.0, min(1.0, top / evidence.page_height)),
            max(0.0, min(1.0, right / evidence.page_width)),
            max(0.0, min(1.0, bottom / evidence.page_height)),
        )
    )


def _source_kind(value: str) -> ProvenanceSourceKind:
    normalized = value.casefold()
    if "mineru" in normalized:
        return ProvenanceSourceKind.MINERU
    if "glm" in normalized or "sdk" in normalized:
        return ProvenanceSourceKind.GLM
    if "native" in normalized or "pymupdf" in normalized:
        return ProvenanceSourceKind.NATIVE
    return ProvenanceSourceKind.DOCLING


def _cell_evidence(
    *,
    text: str,
    fragment: TableFragment,
    row: int,
    column: int,
) -> tuple[ElementQuality, ElementProvenance]:
    base_source = _source_kind(fragment.source_kind)
    values: dict[str, str | None] = {}
    if row < len(fragment.cell_evidence) and column < len(fragment.cell_evidence[row]):
        values = fragment.cell_evidence[row][column]
    sources = {
        _source_kind(name)
        for name, value in values.items()
        if name != "final" and value is not None
    }
    sources.add(base_source)
    selected = [
        source
        for name, value in values.items()
        if name != "final"
        and value is not None
        and compact_text(value) == compact_text(text)
        and (source := _source_kind(name))
    ]
    selected_source = selected[0] if selected else base_source
    supporting = sorted(set(selected), key=lambda item: item.value)
    quality = ElementQuality.CONFIRMED if len(supporting) >= 2 else ElementQuality.SELECTED
    if not fragment.valid:
        quality = ElementQuality.CONFLICTED
    return quality, ElementProvenance(
        selected_source=selected_source,
        supporting_sources=supporting,
        sources=[
            ProvenanceSource(source=source) for source in sorted(sources, key=lambda x: x.value)
        ],
        reason_codes=list(fragment.invalid_reasons),
    )


def _fragment_cells(fragment: TableFragment) -> list[TableCell]:
    explicit = {(cell.row, cell.column): cell for cell in fragment.cells}
    occupied: set[tuple[int, int]] = set()
    output: list[TableCell] = []
    for row in range(fragment.num_rows):
        values = fragment.rows[row] if row < len(fragment.rows) else []
        for column in range(fragment.num_cols):
            if (row, column) in occupied:
                continue
            source: TableCellFragment | None = explicit.get((row, column))
            row_span = source.row_span if source else 1
            column_span = source.column_span if source else 1
            for occupied_row in range(row, min(fragment.num_rows, row + row_span)):
                for occupied_column in range(column, min(fragment.num_cols, column + column_span)):
                    occupied.add((occupied_row, occupied_column))
            text = source.text if source else (values[column] if column < len(values) else "")
            quality, evidence = _cell_evidence(text=text, fragment=fragment, row=row, column=column)
            if not text and not fragment.valid:
                quality = ElementQuality.MISSING
            output.append(
                TableCell(
                    cell_id=f"{fragment.fragment_id}-r{row}-c{column}",
                    row=row,
                    column=column,
                    row_span=row_span,
                    column_span=column_span,
                    bbox=_bbox(source.normalized_bbox if source else None),
                    text=text,
                    is_column_header=(source.is_column_header if source else False),
                    is_row_header=source.is_row_header if source else False,
                    quality=quality,
                    provenance=evidence,
                )
            )
    return output


def _plain_non_table_text(markdown: str) -> str:
    return "\n".join(
        line
        for line in markdown.splitlines()
        if not _MARKDOWN_TABLE_LINE.match(line) and not _MARKER_LINE.match(line)
    ).strip()


def _coverage(inner: NormalizedBBox | None, outer: NormalizedBBox | None) -> float:
    if inner is None or outer is None:
        return 0.0
    width = max(0.0, min(inner.right, outer.right) - max(inner.left, outer.left))
    height = max(0.0, min(inner.bottom, outer.bottom) - max(inner.top, outer.top))
    area = max(0.0, inner.right - inner.left) * max(0.0, inner.bottom - inner.top)
    return width * height / area if area > 0 else 0.0


def _region_order(region: ContentRegion) -> tuple[float, float, int]:
    if region.bbox is not None:
        return region.bbox.top, region.bbox.left, region.reading_order
    return 2.0, 2.0, region.reading_order


def _warning_count(details: dict[str, object] | None) -> int | None:
    value = details.get("count") if details else None
    return value if isinstance(value, int) and value >= 0 else None


class DocumentIRService:
    def __init__(self, settings: object | None = None) -> None:
        self.settings = settings

    def build(
        self,
        result: DocumentParseResult,
        source: StoredSource,
        evidence_by_page: dict[int, PageEvidence],
    ) -> ContentParseResult:
        fragments = [
            fragment for fragment in result._table_fragments if isinstance(fragment, TableFragment)
        ]
        tables = [self._table(fragment) for fragment in fragments]
        tables_by_page: dict[int, list[ParsedTable]] = {}
        for table in tables:
            tables_by_page.setdefault(table.source_units[0], []).append(table)
        pictures_by_page: dict[int, list[object]] = {}
        for picture in result._picture_candidates:
            page_number = getattr(picture, "page_number", None)
            if isinstance(page_number, int):
                pictures_by_page.setdefault(page_number, []).append(picture)

        source_regions_by_page: dict[int, list[SourceRegionEvidence]] = {}
        for region in result._source_regions:
            if isinstance(region, SourceRegionEvidence):
                source_regions_by_page.setdefault(region.page_number, []).append(region)

        units = [
            self._page(
                page,
                evidence_by_page.get(page.page_number),
                tables_by_page,
                pictures_by_page.get(page.page_number, []),
                source_regions_by_page.get(page.page_number, []),
            )
            for page in sorted(result.pages, key=lambda item: item.page_number)
        ]
        if source.mime_type.startswith("image/") and len(units) == 1:
            units[0].unit_type = UnitType.IMAGE
        logical_groups: dict[str, list[ParsedTable]] = {}
        for table in tables:
            if table.logical_table_id:
                logical_groups.setdefault(table.logical_table_id, []).append(table)
        logical_tables = [
            LogicalTable(
                logical_table_id=logical_id,
                fragment_table_ids=[table.table_id for table in group],
                source_units=sorted({unit for table in group for unit in table.source_units}),
            )
            for logical_id, group in sorted(logical_groups.items())
        ]

        summary = result.quality_summary
        glm_calls = summary.glm_calls if summary is not None else None
        return ContentParseResult(
            status=(
                "partial"
                if result.route_summary.failed_pages or result._source_regions
                else "completed"
            ),
            source=ContentSource(
                content_id=result.document_id,
                source_sha256=_sha256(source.path),
                filename=result.filename,
                mime_type=result.mime_type,
                kind=SourceKind.PDF if source.mime_type == "application/pdf" else SourceKind.IMAGE,
                size_bytes=source.size_bytes,
                unit_count=result.page_count,
                page_count=(
                    result.page_count
                    if source.mime_type in {"application/pdf", "image/tiff"}
                    else None
                ),
            ),
            units=units,
            tables=tables,
            logical_tables=logical_tables,
            renderings=ContentRenderings(
                markdown=result.markdown,
                plain_text=result.plain_text,
            ),
            diagnostics=ContentQualitySummary(
                trusted_units=summary.trusted_pages if summary else 0,
                degraded_units=summary.degraded_pages if summary else 0,
                untrusted_units=summary.untrusted_pages if summary else 0,
                repaired_units=summary.repaired_pages if summary else 0,
                visual_units=summary.visual_pages if summary else 0,
                unresolved_visual_conflicts=(summary.unresolved_visual_conflicts if summary else 0),
            ),
            warnings=[
                ParseWarning(
                    code=warning.code,
                    severity=warning.severity.value,
                    unit_index=warning.page_number,
                    count=_warning_count(warning.details),
                )
                for warning in result.warnings
            ],
            runtime=ParseRuntime(
                profile=result.pipeline.profile,  # type: ignore[arg-type]
                primary_backend=result.pipeline.primary,
                ocr_backend=result.pipeline.ocr,
                visual_backend=result.pipeline.ocr,
                parser_version=str(setting(self.settings, "version", "0.5.0")),
                input_bytes=result.usage.input_bytes,
                duration_ms=result.usage.duration_ms,
                glm_calls=glm_calls,
                sdk_requests=summary.sdk_requests if summary else 0,
            ),
            links=ContentLinks(
                job=f"/v1/content/jobs/{result.document_id}",
                events=f"/v1/content/jobs/{result.document_id}/events",
                result=f"/v1/content/jobs/{result.document_id}/result",
                assets=f"/v1/content/jobs/{result.document_id}/assets",
                bundle=f"/v1/content/jobs/{result.document_id}/bundle",
            ),
            created_at=result.created_at,
        )

    @staticmethod
    def _table(fragment: TableFragment) -> ParsedTable:
        quality = ElementQuality.COMPLETE if fragment.valid else ElementQuality.CONFLICTED
        return ParsedTable(
            table_id=fragment.fragment_id,
            unit_id=f"p{fragment.page_number}",
            region_id=f"{fragment.fragment_id}-region",
            source_units=[fragment.page_number],
            bbox=_bbox(fragment.normalized_bbox),
            caption=fragment.caption,
            unit_text=fragment.unit_text,
            row_count=fragment.num_rows,
            column_count=fragment.num_cols,
            header_rows=sorted({cell.row for cell in fragment.cells if cell.is_column_header}),
            cells=_fragment_cells(fragment),
            logical_table_id=fragment.logical_table_id,
            quality=quality,
            reason_codes=list(fragment.invalid_reasons),
        )

    @staticmethod
    def _page(
        page: PageParseResult,
        evidence: PageEvidence | None,
        tables_by_page: dict[int, list[ParsedTable]],
        picture_candidates: list[object],
        source_regions: list[SourceRegionEvidence] | None = None,
    ) -> ContentUnit:
        page_number = int(page.page_number)
        page_id = f"p{page_number}"
        page_tables = tables_by_page.get(page_number, [])
        blocks: list[TextBlock] = []
        regions: list[ContentRegion] = []
        source_regions = source_regions or []
        if evidence and evidence.native_blocks:
            ordered = evidence._blocks_in_reading_order()
            sizes = [block.max_font_size for block in ordered if block.max_font_size > 0]
            median = statistics.median(sizes) if sizes else 0.0
            for index, native_block in enumerate(ordered, 1):
                block_id = f"{page_id}-b{index}"
                region_id = f"{page_id}-r{index}"
                block_type = (
                    RegionType.HEADING
                    if median > 0
                    and (native_block.bold or native_block.max_font_size >= median * 1.28)
                    else RegionType.TEXT
                )
                bbox = _native_bbox(native_block.bbox, evidence)
                if any(_coverage(bbox, table.bbox) >= 0.5 for table in page_tables):
                    continue
                item = TextBlock(
                    block_id=block_id,
                    unit_id=page_id,
                    region_id=region_id,
                    block_type=block_type,
                    bbox=bbox,
                    reading_order=index,
                    text=native_block.text,
                    quality=ElementQuality.COMPLETE,
                    provenance=ElementProvenance(
                        selected_source=ProvenanceSourceKind.NATIVE,
                        supporting_sources=[ProvenanceSourceKind.NATIVE],
                        sources=[ProvenanceSource(source=ProvenanceSourceKind.NATIVE)],
                    ),
                )
                blocks.append(item)
                regions.append(
                    ContentRegion(
                        region_id=region_id,
                        unit_id=page_id,
                        region_type=block_type,
                        bbox=bbox,
                        reading_order=index,
                        block_ids=[block_id],
                    )
                )
        else:
            has_source_page_fallback = any(
                getattr(picture, "source_page_ref", None) is not None
                for picture in picture_candidates
            )
            text = (
                ""
                if has_source_page_fallback
                else _plain_non_table_text(str(getattr(page, "content", "") or ""))
            )
            if text:
                block_id = f"{page_id}-b1"
                region_id = f"{page_id}-r1"
                source = _source_kind(str(getattr(page, "backend", "") or "docling"))
                blocks.append(
                    TextBlock(
                        block_id=block_id,
                        unit_id=page_id,
                        region_id=region_id,
                        reading_order=1,
                        text=text,
                        quality=ElementQuality.SELECTED,
                        provenance=ElementProvenance(
                            selected_source=source,
                            supporting_sources=[source],
                            sources=[ProvenanceSource(source=source)],
                        ),
                    )
                )
                regions.append(
                    ContentRegion(
                        region_id=region_id,
                        unit_id=page_id,
                        region_type=RegionType.TEXT,
                        reading_order=1,
                        block_ids=[block_id],
                        quality=ElementQuality.SELECTED,
                    )
                )
        for offset, table in enumerate(page_tables, len(regions) + 1):
            regions.append(
                ContentRegion(
                    region_id=table.region_id,
                    unit_id=page_id,
                    region_type=RegionType.TABLE,
                    bbox=table.bbox,
                    reading_order=offset,
                    table_ids=[table.table_id],
                    quality=table.quality,
                )
            )

        for source_region in source_regions:
            region_id = f"{page_id}-source-{source_region.source_ref}"
            block_id = f"{region_id}-text"
            box = _bbox(source_region.normalized_bbox)
            blocks.append(
                TextBlock(
                    block_id=block_id,
                    unit_id=page_id,
                    region_id=region_id,
                    block_type=RegionType.UNKNOWN,
                    bbox=box,
                    reading_order=len(regions) + 1,
                    text=source_region.literal_text,
                    quality=ElementQuality.CONFLICTED,
                    provenance=ElementProvenance(
                        selected_source=ProvenanceSourceKind.NATIVE,
                        supporting_sources=[ProvenanceSourceKind.NATIVE],
                        sources=[ProvenanceSource(source=ProvenanceSourceKind.NATIVE)],
                        reason_codes=list(source_region.reason_codes),
                    ),
                )
            )
            regions.append(
                ContentRegion(
                    region_id=region_id,
                    unit_id=page_id,
                    region_type=RegionType.UNKNOWN,
                    bbox=box,
                    reading_order=len(regions) + 1,
                    block_ids=[block_id],
                    quality=ElementQuality.CONFLICTED,
                )
            )

        if picture_candidates:
            for index, picture in enumerate(picture_candidates, 1):
                if getattr(picture, "source_region_ref", None) is not None:
                    continue
                source_page_ref = getattr(picture, "source_page_ref", None)
                regions.append(
                    ContentRegion(
                        region_id=(
                            f"{page_id}-source-page-{source_page_ref}"
                            if source_page_ref is not None
                            else f"{page_id}-image-{index}"
                        ),
                        unit_id=page_id,
                        region_type=(
                            RegionType.UNKNOWN if source_page_ref is not None else RegionType.IMAGE
                        ),
                        bbox=_bbox(getattr(picture, "normalized_bbox", None)),
                        reading_order=len(regions) + 1,
                        quality=(
                            ElementQuality.CONFLICTED
                            if source_page_ref is not None
                            else ElementQuality.COMPLETE
                        ),
                    )
                )
        elif "<!-- image -->" in str(getattr(page, "content", "") or ""):
            regions.append(
                ContentRegion(
                    region_id=f"{page_id}-image",
                    unit_id=page_id,
                    region_type=RegionType.IMAGE,
                    reading_order=len(regions) + 1,
                    quality=ElementQuality.SELECTED,
                )
            )

        regions.sort(key=_region_order)
        order_by_region: dict[str, int] = {}
        for reading_order, region in enumerate(regions, 1):
            region.reading_order = reading_order
            order_by_region[region.region_id] = reading_order
        for ir_block in blocks:
            ir_block.reading_order = order_by_region.get(ir_block.region_id, ir_block.reading_order)

        diagnostics = getattr(page, "diagnostics", None)
        visual = diagnostics.glm if diagnostics else None
        source_kind = diagnostics.source_kind.value if diagnostics else "native"
        verdict = (
            diagnostics.quality_verdict.value
            if diagnostics
            else (
                QualityVerdict.UNTRUSTED.value
                if page.status != PageStatus.COMPLETED
                else QualityVerdict.TRUSTED.value
            )
        )
        return ContentUnit(
            unit_id=page_id,
            unit_type=UnitType.PAGE,
            index=page_number,
            width=evidence.page_width if evidence and evidence.page_width > 0 else None,
            height=evidence.page_height if evidence and evidence.page_height > 0 else None,
            rotation_degrees=(diagnostics.detected_rotation_degrees if diagnostics else None),
            status=page.status.value,
            regions=regions,
            blocks=blocks,
            table_ids=[table.table_id for table in page_tables],
            renderings=ContentRenderings(
                markdown=str(getattr(page, "content", "") or ""),
                plain_text=str(getattr(page, "plain_text", "") or ""),
            ),
            diagnostics=UnitDiagnostics(
                source_kind=source_kind,  # type: ignore[arg-type]
                quality_verdict=verdict,  # type: ignore[arg-type]
                selected_strategy=(
                    diagnostics.selected_strategy.value if diagnostics else "docling"
                ),
                native_text_characters=(
                    diagnostics.native_text_characters if diagnostics else None
                ),
                visual_ink_ratio=diagnostics.visual_ink_ratio if diagnostics else None,
                image_coverage_ratio=(diagnostics.image_coverage_ratio if diagnostics else None),
                detected_rotation_degrees=(
                    diagnostics.detected_rotation_degrees if diagnostics else None
                ),
                warning_codes=[warning.code for warning in getattr(page, "warnings", [])],
                glm_calls=visual.glm_calls if visual else None,
                sdk_requests=visual.sdk_requests if visual else 0,
                sdk_duration_ms=visual.sdk_duration_ms if visual else None,
                unresolved_conflicts=visual.structure_issue_count if visual else None,
            ),
            duration_ms=int(getattr(page, "duration_ms", 0) or 0),
        )
