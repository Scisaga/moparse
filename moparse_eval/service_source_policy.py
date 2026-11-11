"""Apply optional PDF supplementation only to permitted saved native pages."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.models.parse_result import DocumentParseResult
from app.services.evidence_service import PageEvidenceService
from app.services.native_text_service import NativeTextService
from app.services.pdf_table_evidence_service import PDFTableEvidenceService
from app.services.table_service import refresh_table_views

from .service_native_adapters import permitted_pages


async def apply_source_stages(result: DocumentParseResult, bridge: dict[str, Any], source: Any,
                              options: Any, settings: Any, *, inspect_pages=None,
                              apply_tables=None, apply_text=None, on_stage=None,
                              allow_source_reads: bool = True) -> tuple[dict[int, Any], dict[str, float], dict[str, Any]]:
    """Narrow every source-reading call before entering production services.

    A mixed document's GLM pages never enter a text/vector service. The scoped
    result shares actual native page/fragment objects so their permitted edits
    reach the live result; source-free final assembly still sees every page.
    """
    text_pages = permitted_pages(bridge, "pdf_text")
    vector_pages = permitted_pages(bridge, "pdf_vector")
    all_pages = {page.page_number for page in result.pages}
    text_pages &= all_pages
    vector_pages &= all_pages
    if not allow_source_reads:
        text_pages, vector_pages = set(), set()
    timings: dict[str, float] = {}
    applicability = {}
    for stage, pages in (("page_evidence", text_pages | vector_pages), ("table_source", vector_pages),
                         ("native_text", text_pages)):
        applicability[stage] = {"applicable": bool(pages), "pages": sorted(pages),
                                "not_applicable_pages": sorted(all_pages - pages),
                                "reason": ("source_access_disabled_for_saved_json_validation" if not allow_source_reads
                                           else "declared_native_branch_source_permission" if pages else "no_permitted_native_branch")}
    started = time.perf_counter()
    eligible = text_pages | vector_pages
    if eligible:
        inspect_pages = inspect_pages or PageEvidenceService(settings).inspect
        evidence = await asyncio.to_thread(inspect_pages, source, eligible)
        if not set(evidence) <= eligible:
            raise ValueError("page evidence escaped the saved branch capability")
    else:
        evidence = {}
    timings["page_evidence_seconds"] = time.perf_counter() - started
    started = time.perf_counter()
    if vector_pages:
        scoped = result.model_copy(deep=False)
        scoped.pages = [page for page in result.pages if page.page_number in vector_pages]
        scoped._table_fragments = [fragment for fragment in result._table_fragments if fragment.page_number in vector_pages]
        scoped._page_furniture = [item for item in result._page_furniture if item.page_number in vector_pages]
        scoped._native_page_blocks = {page: blocks for page, blocks in result._native_page_blocks.items() if page in vector_pages}
        scoped._source_verification = dict(result._source_verification)
        apply_tables = apply_tables or PDFTableEvidenceService(settings).apply
        await apply_tables(scoped, source, options)
        result._source_verification.update(scoped._source_verification)
        # This is formatting over the retained fragments, not another PDF read.
        refresh_table_views(result.pages, result._table_fragments)
    timings["table_source_seconds"] = time.perf_counter() - started
    if on_stage is not None:
        on_stage("source_pages", applicability["table_source"])
    started = time.perf_counter()
    if text_pages:
        apply_text = apply_text or NativeTextService().apply_async
        scoped = result.model_copy(deep=False)
        scoped.pages = [page for page in result.pages if page.page_number in text_pages]
        scoped._native_page_blocks = {page: blocks for page, blocks in result._native_page_blocks.items() if page in text_pages}
        scoped._table_fragments = [fragment for fragment in result._table_fragments if fragment.page_number in text_pages]
        scoped._source_regions = [region for region in result._source_regions if region.page_number in text_pages]
        scoped._source_verification = dict(result._source_verification)
        await apply_text(scoped, {page: item for page, item in evidence.items() if page in text_pages}, options)
        result._source_verification.update(scoped._source_verification)
        original_regions = result._source_regions
        result._source_regions = [region for page in result.pages
                                  for region in (scoped._source_regions if page.page_number in text_pages else original_regions)
                                  if region.page_number == page.page_number]
    timings["native_text_seconds"] = time.perf_counter() - started
    if on_stage is not None:
        on_stage("native_pages", applicability["native_text"])
    return evidence, timings, applicability
