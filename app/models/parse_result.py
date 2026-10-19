"""Parser-independent document result models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from app.models.content_result import ContentParseResult
from app.models.table_semantics import SemanticTableView


def utc_now() -> datetime:
    return datetime.now(UTC)


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PageStatus(StrEnum):
    COMPLETED = "completed"
    WARNING = "warning"
    FAILED = "failed"


class PageSourceKind(StrEnum):
    NATIVE = "native"
    SCANNED = "scanned"
    MIXED = "mixed"
    SPARSE = "sparse"


class QualityVerdict(StrEnum):
    TRUSTED = "trusted"
    DEGRADED = "degraded"
    UNTRUSTED = "untrusted"


class SelectionStrategy(StrEnum):
    DOCLING = "docling"
    MINERU = "mineru"
    NATIVE_REPAIR = "native_repair"
    SCAN_SKIPPED = "scan_skipped"
    GLM_TABLE = "glm_table"


class GlmDiagnostics(BaseModel):
    """Observed OCR activity and structure validation, without model arbitration."""

    model_config = ConfigDict(extra="forbid")

    glm_calls: int | None = Field(default=None, ge=0)
    sdk_requests: int | None = Field(default=None, ge=0)
    sdk_duration_ms: int = Field(default=0, ge=0)
    table_count: int = Field(default=0, ge=0)
    structure_issue_count: int = Field(default=0, ge=0)


class PageDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: PageSourceKind
    quality_verdict: QualityVerdict = QualityVerdict.TRUSTED
    selected_strategy: SelectionStrategy = SelectionStrategy.DOCLING
    native_text_characters: int | None = Field(default=None, ge=0)
    visual_ink_ratio: float | None = Field(default=None, ge=0, le=1)
    image_coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    detected_rotation_degrees: Literal[0, 90, 180, 270] | None = None
    logical_table_ids: list[str] = Field(default_factory=list)
    glm: GlmDiagnostics | None = None


class QualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trusted_pages: int = Field(default=0, ge=0)
    degraded_pages: int = Field(default=0, ge=0)
    untrusted_pages: int = Field(default=0, ge=0)
    repaired_pages: int = Field(default=0, ge=0)
    visual_pages: int = Field(default=0, ge=0)
    glm_calls: int | None = Field(default=None, ge=0)
    sdk_requests: int | None = Field(default=0, ge=0)
    unresolved_visual_conflicts: int = Field(default=0, ge=0)


class PipelineWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4_096)
    severity: WarningSeverity = WarningSeverity.WARNING
    page_number: int | None = Field(default=None, ge=1)
    backend: str | None = None
    details: dict[str, object] | None = None


class PageParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    status: PageStatus = PageStatus.COMPLETED
    backend: str | None = None
    content: str | None = None
    plain_text: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    warnings: list[PipelineWarning] = Field(default_factory=list)
    diagnostics: PageDiagnostics | None = None

    _sdk_requests: int | None = PrivateAttr(default=None)


class ParsePipeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    primary: str
    ocr: str | None = None


class RouteSummary(BaseModel):
    """Only values observed from an adapter may be populated.

    Docling does not consistently expose page-level routing details, hence most
    counters are nullable rather than guessed.
    """

    model_config = ConfigDict(extra="forbid")

    native_text_pages: int | None = Field(default=None, ge=0)
    pages_with_ocr: int | None = Field(default=None, ge=0)
    ocr_regions: int | None = Field(default=None, ge=0)
    failed_pages: int = Field(default=0, ge=0)


class ParseUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_bytes: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


class DocumentParseResult(BaseModel):
    """Stable result; no Docling object is allowed across this boundary."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    filename: str
    mime_type: str
    page_count: int = Field(ge=1)
    processed_pages: int = Field(ge=0)
    markdown: str = ""
    plain_text: str = ""
    pages: list[PageParseResult] = Field(default_factory=list)
    pipeline: ParsePipeline
    route_summary: RouteSummary = Field(default_factory=RouteSummary)
    warnings: list[PipelineWarning] = Field(default_factory=list)
    quality_summary: QualitySummary | None = None
    usage: ParseUsage = Field(default_factory=ParseUsage)
    created_at: datetime = Field(default_factory=utc_now)
    parse_result: ContentParseResult | None = None

    # Adapter-private, request-scoped enrichment hints.  These never cross the
    # stable API/storage boundary and deliberately stay out of the JSON schema.
    _picture_candidates: list[object] = PrivateAttr(default_factory=list)
    _table_fragments: list[object] = PrivateAttr(default_factory=list)
    _page_furniture: list[object] = PrivateAttr(default_factory=list)
    _source_regions: list[object] = PrivateAttr(default_factory=list)
    _native_page_blocks: dict[int, list[dict[str, object]]] = PrivateAttr(default_factory=dict)
    _source_verification: dict[str, object] = PrivateAttr(default_factory=dict)
    _table_views: list[object] = PrivateAttr(default_factory=list)
    _semantic_tables: list[SemanticTableView] = PrivateAttr(default_factory=list)
    _semantic_duration_ms: float = PrivateAttr(default=0.0)
    _source_markdown: str = PrivateAttr(default="")
