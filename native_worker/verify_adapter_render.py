"""Offline verification of the official typed-renderer/JSON/GFM boundary.

Uses existing model outputs, never starts a model, and labels that scope in the
artifact. It is supplementary to full-PDF fresh HTTP acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from mineru.parser.base import ParseResult

from app.parsers.mineru_native_remote import render_mineru_page
from app.services.table_service import render_gfm_rows
from native_worker.server import export_source_blocks

TABLE = re.compile(r"<table\b[^>]*>[\s\S]*?</table\s*>", re.IGNORECASE)


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    base = (
        args.repo
        / "benchmark-results/clean-model-comparison-20261015/followup/20261017/content-preservation-mineru/mineru-trial"
    )
    plans = json.loads((base / "first-pages.json").read_text()) + json.loads(
        (base / "remaining-pages.json").read_text()
    )
    plans.append({"id": "1225475375", "page": 62})
    results = []
    for plan in plans:
        source = base / "official-native-advanced" / f"{plan['id']}-p{plan['page']}" / "result.json"
        parsed = ParseResult.from_dict(json.loads(source.read_text()))
        assert len(parsed.pages) == 1
        number = parsed.pages[0].page_idx + 1
        assert number == plan["page"]
        payload = {"page_number": number, "blocks": export_source_blocks(parsed.pages[0])}
        # Exercise the actual byte-level JSON boundary rather than sharing types.
        serialized = json.dumps(payload, ensure_ascii=False).encode()
        payload = json.loads(serialized)
        markdown, fragments, pictures = render_mineru_page(payload)
        expected = parsed.markdown(add_markers=True).strip()
        actual_without_tables = markdown
        for fragment in fragments:
            assert fragment.markdown == render_gfm_rows(fragment.rows)
            assert fragment.page_number == number
            assert not fragment.header_scope_complete or fragment.header_row_indices
            assert (
                sum(cell.row_span * cell.column_span for cell in fragment.cells)
                == fragment.num_rows * fragment.num_cols
            )
            actual_without_tables = actual_without_tables.replace(
                fragment.rendered, "<SOURCE_TABLE>", 1
            )
        expected_without_tables = expected
        for block in payload["blocks"]:
            if block.get("type") == "table":
                for child in block["content"]:
                    if child.get("type") == "table_body":
                        expected_without_tables = expected_without_tables.replace(
                            child["markdown"], "<SOURCE_TABLE>", 1
                        )
        assert actual_without_tables == expected_without_tables, (
            plan,
            actual_without_tables,
            expected_without_tables,
        )
        target = args.out / "adapter-render" / f"{plan['id']}-p{number}"
        target.mkdir(parents=True, exist_ok=True)
        (target / "worker-page.json").write_bytes(serialized + b"\n")
        (target / "result.md").write_text(markdown + "\n")
        results.append(
            {
                "id": plan["id"],
                "source_page": number,
                "source_result_sha256": sha(source.read_bytes()),
                "worker_page_sha256": sha(serialized),
                "markdown_sha256": sha(markdown.encode()),
                "official_non_table_markdown_exact": True,
                "tables": len(fragments),
                "cells": sum(len(item.cells) for item in fragments),
                "merged_cells": sum(
                    cell.row_span > 1 or cell.column_span > 1
                    for item in fragments
                    for cell in item.cells
                ),
                "source_images": len(pictures),
            }
        )
    evidence = {
        "schema": "native-adapter-render-verification/1",
        "GPU_requests": 0,
        "scope": "Previously generated typed results; official non-table rendering exact, all source table text/spans retained through JSON and GFM. Not fresh inference or full-document HTTP acceptance.",
        "cases": results,
        "cases_passed": len(results),
    }
    (args.out / "official-renderer-json-gfm-replay.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "cases": len(results),
                "tables": sum(item["tables"] for item in results),
                "cells": sum(item["cells"] for item in results),
                "official_non_table_markdown_exact": True,
            }
        )
    )


if __name__ == "__main__":
    main()
