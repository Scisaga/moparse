"""Source-free finalization of already adapted saved native content.

This does not initialize a parser, read a source, or extract media. The declared
source checksum is existing metadata, never a newly measured checksum.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult
from app.models.source import StoredSource
from app.services.export_service import ExportService
from app.services.final_content_service import FinalContentService
from app.services.ir_service import DocumentIRService
from app.services.native_content_evidence import (
    native_partial,
    validate_ir_handoff,
    validate_native_content,
    validate_table_relations,
)
from app.services.table_semantics_service import TableSemanticsService


class SavedContentService:
    async def finalize(
        self,
        result: DocumentParseResult,
        source: StoredSource,
        options: ContentParseOptions,
        *,
        declared_source_sha256: str,
        on_stage: Callable[[str], None] | None = None,
    ) -> None:
        validate_native_content(result)
        saved_state = cast(dict[str, Any], result._source_verification["native_content"])

        def capture(name):
            if on_stage is not None:
                on_stage(name)

        ExportService().apply_document(result)
        capture("exported")
        result.parse_result = DocumentIRService().build(
            result,
            source,
            {},
            declared_source_sha256=declared_source_sha256,
        )
        validate_ir_handoff(result)
        capture("ir")
        saved_state["source_identity_basis"] = "declared_metadata_not_source_byte_verification"
        # Resolve delivery status only. A path or an inline URI cannot certify
        # an asset. No placeholder ContentAsset/file is manufactured.
        media = saved_state.get("media")
        if not isinstance(media, list):
            raise ValueError("saved media declarations must be a list")
        saved_state["asset_delivery"] = {
            "declared": len(media),
            "delivered": 0,
            "status": "unverified" if media else "no_declared_media",
            "media_io": False,
        }
        if media:
            result.parse_result.status = "partial"
        capture("assets")
        await TableSemanticsService().apply(result, options)
        validate_table_relations(result)
        capture("semantic")
        FinalContentService().apply(result)
        validate_native_content(result)
        if native_partial(result):
            result.parse_result.status = "partial"
        bridge = cast(dict[str, Any], result._source_verification['saved_native_bridge'])
        issues = [issue for page in bridge['pages']
                  for issue in page.get('local_read_errors', []) if issue.get('code') not in {
                      'saved_native_media_unverified', 'saved_native_producer_incomplete'}]
        saved_state["conversion"] = {"status": "partial" if issues or any(
            view.status != "converted" for view in result._semantic_tables) else "completed", "issues": issues}
        saved_state["delivery"] = {"status": result.parse_result.status,
                                   "media": saved_state["asset_delivery"]}
        capture("final")
