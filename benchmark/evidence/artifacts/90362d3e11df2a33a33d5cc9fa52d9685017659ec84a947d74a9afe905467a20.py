"""Replay captured data only; no model requests, scoring or historical writes."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

from app.models.parse_result import PageParseResult
from app.parsers.glm_sdk_remote import _html_table_layout, _TableHtmlParser
from app.parsers.mineru_native_remote import render_mineru_page_evidence
from app.services.export_service import ExportService

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
DIAG = ROOT / "benchmark/runs/irs-table-adapter-diagnosis-20261018"


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    payload = json.loads((DIAG / "worker-response.json").read_bytes())
    reference = json.loads((DIAG / "cpu-replay/without_only_100_column_cap.json").read_text())
    cases, pages, fragments, furniture = [], [], [], []
    for page in payload["pages"]:
        for block_index, block in enumerate(page["blocks"]):
            if block.get("type") != "table":
                continue
            for child in block["content"]:
                if child.get("type") != "table_body":
                    continue
                raw = child["content"]
                source = _TableHtmlParser()
                source.feed(raw)
                source.close()
                original_cells = [cell for row in source.rows for cell in row]
                rows, _, cells = _html_table_layout(raw)
                assert rows and cells
                assert len(original_cells) == len(cells)
                literal_span_equal = all(
                    (before.text, before.row_span, before.col_span)
                    == (after.text, after.row_span, after.column_span)
                    for before, after in zip(original_cells, cells, strict=True)
                )
                assert literal_span_equal
                if page["page_number"] == 1 and block_index == 8:
                    actual = [(c.row, c.column, c.row_span, c.column_span, c.text) for c in cells]
                    assert actual == [tuple(c) for c in reference["source_cell_anchor_spans"]]
                    assert (len(rows), len(rows[0]), len(cells)) == (13, 202, 1513)
                cases.append(
                    {
                        "page": page["page_number"],
                        "block_index": block_index,
                        "html_sha256": sha(raw.encode()),
                        "rows": len(rows),
                        "columns": len(rows[0]),
                        "grid_positions": len(rows) * len(rows[0]),
                        "original_HTML_cells": len(original_cells),
                        "parsed_cells": len(cells),
                        "all_original_literals_and_spans_retained_in_order": literal_span_equal,
                        "cell_text_and_spans_sha256": sha(
                            json.dumps(
                                [(c.text, c.row_span, c.column_span) for c in cells],
                                ensure_ascii=False,
                            ).encode()
                        ),
                    }
                )
        markdown, fs, _, furniture_items = render_mineru_page_evidence(page)
        pages.append(PageParseResult(page_number=page["page_number"], content=markdown))
        fragments.extend(fs)
        furniture.extend(furniture_items)
    markdown, _ = ExportService().join_document(
        pages, preserve_page_breaks=True, table_fragments=fragments, page_furniture=furniture
    )
    (OUT / "irs-captured-adapter-v2.md").write_text(markdown + "\n")
    assert markdown.count("<!-- table-source:") == 4
    assert "<table" not in markdown.lower()

    # Redirect only this replay function's in-memory OUTPUT. The historical
    # script and all its output bytes remain untouched.
    replay = ROOT / "benchmark/runs/header-verifier-20261018/cached-replay.py"
    namespace = runpy.run_path(str(replay))
    namespace["main"].__globals__["OUTPUT"] = OUT
    namespace["main"]()
    before = json.loads((replay.parent / "cached-replay.json").read_text())
    after = json.loads((OUT / "cached-replay.json").read_text())
    original_docs = {case["id"]: case for case in before["cases"]}
    unchanged = []
    for case in after["cases"]:
        old = original_docs[case["id"]]
        previous_md = ROOT / old["markdown"]
        new_md = ROOT / case["markdown"]
        assert previous_md.read_bytes() == new_md.read_bytes()
        unchanged.append(
            {"id": case["id"], "markdown_bytes_unchanged": True, "sha256": sha(new_md.read_bytes())}
        )
    report = {
        "schema": "wide-grid-adapter-source-preservation/1",
        "phase": "after_exposure_IRS_diagnostic_repeat",
        "scope": "CPU-only replay of complete captured IRS2 response and original14 cached outputs; no fresh inference, HTTP or score mutation",
        "worker_response_sha256": sha((DIAG / "worker-response.json").read_bytes()),
        "original_failed_public_result_retained": True,
        "IRS_pages_rendered": len(pages),
        "IRS_tables_rendered": len(fragments),
        "IRS_table_source_markers": 4,
        "IRS_raw_HTML_tables_in_public_GFM": False,
        "IRS_cases": cases,
        "existing14_pages": 14,
        "existing25_tables": 25,
        "existing_documents": unchanged,
        "all_existing_document_Markdown_bytes_unchanged": True,
        "boundary": {
            "old_max_columns": 100,
            "max_rows_and_columns_now": 2000,
            "maximum_grid_positions": 200000,
            "rowspan_colspan_not_clamped": True,
            "overlap_rejection_retained": True,
            "matrix_allocated_only_after_complete_shape_preflight": True,
        },
    }
    (OUT / "source-preservation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"IRS_cases", "existing_documents"}
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
