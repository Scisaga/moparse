"""Capture actually emitted candidate stages without PDFs, references or inference."""

from __future__ import annotations

import copy
from typing import Any

from app.models.parse_result import DocumentParseResult
from app.services.export_service import ExportService

from .service_observation import build_service_observation

STAGE_CAPTURE_VERSION = "mo-parse-service-stage-capture-1"


def capture_stage(
    result: DocumentParseResult,
    *,
    stage: str,
    sample_id: str,
    pages_only: bool = False,
    pipeline: str = "P07",
) -> dict[str, Any]:
    """Project a stage's visible output now, before mutable service work continues.

    Before document assembly, the normal page exporter supplies a diagnostic
    concatenation. It does not merge tables, reorder pages or change the live
    result. Later stages use their actual document rendering. Hidden IR blocks
    never become candidate text merely because a snapshot is being captured.
    """
    observed = result.model_copy(deep=False)
    if pages_only:
        observed.markdown, observed.plain_text = ExportService().join_pages(
            result.pages, preserve_page_breaks=True, source_regions=result._source_regions,
        )
        observed._table_views = []
        observed._semantic_tables = []
        observed.parse_result = None
    elif result.parse_result is not None:
        observed.markdown = result.parse_result.renderings.markdown
        observed.plain_text = result.parse_result.renderings.plain_text
    # Freeze only the evidence needed by final-output readback. Candidate text
    # and these source-owned tables must not observe later in-place mutations.
    saved: dict[str, Any] = copy.deepcopy({
        "fragments": observed._table_fragments,
        "views": observed._table_views,
        "semantics": observed._semantic_tables,
    })
    observed._table_fragments = saved["fragments"]
    observed._table_views = saved["views"]
    observed._semantic_tables = saved["semantics"]
    observed.pages = [page.model_copy(update={"warnings": copy.deepcopy(page.warnings)})
                      for page in result.pages]
    observed.warnings = copy.deepcopy(result.warnings)
    if observed.parse_result is not None:
        observed.parse_result = observed.parse_result.model_copy(update={
            "renderings": observed.parse_result.renderings.model_copy(deep=True),
        })
    return {
        "schema": STAGE_CAPTURE_VERSION,
        "stage": stage,
        "scope": "diagnostic_page_export" if pages_only else "actual_document_rendering",
        "markdown": observed.markdown,
        "candidate": observed,
        "sample_id": sample_id,
        "pipeline": pipeline,
    }


def materialize_stage(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Read a frozen candidate stage after the primary processing timer stops."""
    observed = snapshot["candidate"]
    observation = build_service_observation(
        observed, sample_id=snapshot["sample_id"], pipeline=f"{snapshot['pipeline']}+MO-Parse:{snapshot['stage']}",
    )
    return {key: snapshot[key] for key in ("schema", "stage", "scope", "markdown")} | {
        "observation": observation,
    }
