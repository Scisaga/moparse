"""Reproduce service entrypoint limits using authored in-memory structures only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import (
    DocumentParseResult,
    PageParseResult,
    PageSourceKind,
    ParsePipeline,
)
from app.models.source import StoredSource
from app.services.evidence_service import NativeBlock, PageEvidence
from app.services.export_service import ExportService
from app.services.ir_service import DocumentIRService
from app.services.native_text_service import NativeTextService
from app.services.parser_service import ParserService
from app.services.pdf_table_evidence_service import _header_candidates, _period_label
from app.services.table_semantics_service import bind_table_view
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows


def native_rendering_probe() -> dict:
    native = "Authored native-only paragraph."
    parser = "Authored native-only paragrapx."
    result = DocumentParseResult(
        document_id="synthetic-entrypoints", filename="synthetic.pdf",
        mime_type="application/pdf", page_count=1, processed_pages=1,
        pages=[PageParseResult(page_number=1, content=parser)],
        markdown=parser, plain_text=parser,
        pipeline=ParsePipeline(profile="balanced", primary="synthetic"),
    )
    evidence = PageEvidence(
        page_number=1, source_kind=PageSourceKind.NATIVE,
        native_blocks=[NativeBlock(native, (10, 10, 90, 20), 10, False)],
        page_width=100, page_height=100,
    )
    source = StoredSource(
        path=Path("/not-opened/synthetic.pdf"), filename="synthetic.pdf",
        mime_type="application/pdf", size_bytes=0, page_count=1,
    )
    # The IR's source-byte bookkeeping is irrelevant to this synthetic flow.
    with patch("app.services.ir_service._sha256", return_value="0" * 64):
        ir = DocumentIRService(None).build(result, source, {1: evidence})
    result._native_page_blocks = {1: [{
        "type": "text", "bbox": (0.1, 0.1, 0.9, 0.2), "markdown": parser,
    }]}
    changes = NativeTextService().apply(result, {1: evidence}, ContentParseOptions())
    service = object.__new__(ParserService)
    service.settings, service.export_service = None, ExportService()
    service._finalize_exports(result, ContentParseOptions())
    return {
        "native_text_in_ir": any(block.text == native for block in ir.units[0].blocks),
        "before_native_text_in_rendering": native in ir.renderings.markdown,
        "after_native_text_in_rendering": native in result.markdown,
        "replaced_regions": changes["replaced_regions"],
    }


def header_probe() -> dict:
    def candidates(labels: list[str], *, centered: bool = True) -> list[dict]:
        rows = [labels, ["Alpha", "100", "90"]]
        cells = [
            {"row": row, "column": col, "row_span": 1, "column_span": 1,
             "text": text, "centered": centered if row == 0 else False, "shaded": False}
            for row, values in enumerate(rows) for col, text in enumerate(values)
        ]
        return _header_candidates({"source_cells": cells}, 2, 3)

    return {
        "centered_numeric_period_scopes": len(candidates(["Metric", "2024", "2023"])),
        "centered_word_period_scopes": len(candidates(["Metric", "Current", "Prior"])),
        "left_aligned_word_period_scopes": len(candidates(["Metric", "Current", "Prior"], centered=False)),
        "amount_like_labels_are_periods": {
            text: _period_label(text)
            for text in ("20240", "12024", "2024.50", "2024%", "-2024", "20240年", "12024年度")
        },
        "amount_like_header_scopes": len(candidates(["Metric", "20240", "20230"])),
    }


def whole_view_probe() -> dict:
    def evaluate(rows: list[list[str]]) -> dict:
        cells = [TableCellFragment(r, c, 1, 1, text)
                 for r, row in enumerate(rows) for c, text in enumerate(row)]
        markdown = render_gfm_rows(rows)
        fragment = TableFragment(
            "synthetic-table", 1, 1, (0.1, 0.1, 0.9, 0.9), len(rows), 2,
            rows, [], markdown, markdown, cells=cells,
        )
        fragment.pdf_evidence = {"bound": True, "source_cells": [
            {"row": c.row, "column": c.column, "row_span": 1, "column_span": 1,
             "text": c.text, "shaded": False} for c in cells
        ]}
        fragment.source_header_scopes = [
            {"header_rows": [0], "body_rows": list(range(1, len(rows))), "complete": True}
        ]
        view = bind_table_view("synthetic-view", [fragment], [fragment])
        return {"status": view.status, "records": len(view.records), "reasons": list(view.reason_codes)}

    return {
        "supported_row_only": evaluate([["Metric", "Value"], ["Alpha", "10"]]),
        "same_row_then_unresolved_subject": evaluate([
            ["Metric", "Value"], ["Alpha", "10"], ["", "20"],
        ]),
    }


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("This controlled probe does not accept input files or corpus paths.")
    print(json.dumps({
        "schema": "moparse-service-entrypoints-probe-1",
        "scope": "Authored in-memory structures; no PDFs, references, models or services.",
        "native_rendering": native_rendering_probe(),
        "header_policy": header_probe(),
        "whole_view_fallback": whole_view_probe(),
    }, indent=2))
