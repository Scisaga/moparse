"""Capture actually emitted candidate stages without PDFs, references or inference."""

from __future__ import annotations

import copy
from dataclasses import asdict, is_dataclass
from difflib import SequenceMatcher
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
    applicability: dict[str, Any] | None = None,
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
    observed._native_page_blocks = copy.deepcopy(result._native_page_blocks)
    observed._source_verification = copy.deepcopy(result._source_verification)
    observed._page_furniture = copy.deepcopy(result._page_furniture)
    observed._source_regions = copy.deepcopy(result._source_regions)
    observed._final_text_evidence = copy.deepcopy(result._final_text_evidence)
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
        "scope": ("actual_adapter_page_rendering" if stage == "adapted" else "diagnostic_page_export")
                 if pages_only else "actual_document_rendering",
        "markdown": observed.markdown,
        "candidate": observed,
        "sample_id": sample_id,
        "pipeline": pipeline,
        "applicability": copy.deepcopy(applicability or {"applicable": True, "reason": "actual_emitted_stage"}),
    }


def materialize_stage(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Read a frozen candidate stage after the primary processing timer stops."""
    observed = snapshot["candidate"]
    observation = build_service_observation(
        observed, sample_id=snapshot["sample_id"], pipeline=f"{snapshot['pipeline']}+MO-Parse:{snapshot['stage']}",
    )
    return {key: snapshot[key] for key in ("schema", "stage", "scope", "markdown", "applicability")} | {
        "observation": observation,
        "source_audit": {"native_blocks": copy.deepcopy(observed._native_page_blocks),
                         "table_fragments": [asdict(fragment) if is_dataclass(fragment) else copy.deepcopy(fragment)
                                             for fragment in observed._table_fragments],
                         "source_verification": copy.deepcopy(observed._source_verification),
                         "final_text_evidence": copy.deepcopy(observed._final_text_evidence)},
    }


def stage_edit_ledger(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Describe actual stage string edits; never assign semantic correctness."""
    ledger = []
    for before, after in zip(snapshots, snapshots[1:], strict=False):
        edits = []
        prior, current = before["markdown"].splitlines(keepends=True), after["markdown"].splitlines(keepends=True)
        prior_offsets, current_offsets = [0], [0]
        for line in prior:
            prior_offsets.append(prior_offsets[-1] + len(line))
        for line in current:
            current_offsets.append(current_offsets[-1] + len(line))
        for operation, i, j, k, stop in SequenceMatcher(None, prior, current, autojunk=False).get_opcodes():
            if operation != "equal":
                a, b, c, d = prior_offsets[i], prior_offsets[j], current_offsets[k], current_offsets[stop]
                edits.append({"operation": operation, "before_span": [a, b], "after_span": [c, d],
                              "before": before["markdown"][a:b], "after": after["markdown"][c:d]})
        ledger.append({"from_stage": before["stage"], "to_stage": after["stage"],
                       "from_scope": before["scope"], "to_scope": after["scope"],
                       "applicability": copy.deepcopy(after["applicability"]), "edits": edits,
                       "judgment": "unjudged_actual_string_changes"})
    return ledger
