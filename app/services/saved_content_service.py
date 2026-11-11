"""Source-free finalization of already adapted saved native content.

This does not initialize a parser, read a source, or extract media. The declared
source checksum is existing metadata, never a newly measured checksum.
"""

from __future__ import annotations

from collections.abc import Callable

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult
from app.models.source import StoredSource
from app.services.export_service import ExportService
from app.services.final_content_service import FinalContentService
from app.services.ir_service import DocumentIRService
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
        saved_state = result._source_verification.get("saved_p01")
        if not isinstance(saved_state, dict):
            raise ValueError(
                "saved content finalization currently accepts the validated P01 bridge"
            )

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
        capture("semantic")
        FinalContentService().apply(result)
        capture("final")
