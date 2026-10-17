"""Additional p62 original-grid acceptance, outside the fourteen-page cohort.

Checks all 99 source positions, nine merged spans, three header levels and six
body rows. Character/picture-text coverage is diagnostic and never sufficient
for table restoration. No source values are inserted into output artifacts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


reader = load("p62_docling_reader", "evaluate-docling-component.py")
evaluator, auditor = reader.evaluator, reader.auditor


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument(
        "--public-capture",
        type=Path,
        help="Actual captured HTTP run containing summary.json and cases/1225475375/result.md",
    )
    inputs.add_argument(
        "--official-page",
        type=Path,
        help="Official raw model p62 output directory with request/blocks/generation calls",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite additional-page acceptance evidence")
    reference_path = HERE / "source-reference-p62.json"
    reference = json.loads(reference_path.read_text())
    original_pdf = HERE.parents[4] / reference["source_pdf"]
    if sha(original_pdf) != reference["source_SHA256"]:
        raise ValueError("Original PDF identity mismatch")
    if args.public_capture:
        capture = args.public_capture
        cases = json.loads((capture / "summary.json").read_text())
        case = next(c for c in cases if c["source"] == "1225475375")
        if case["status"] != "completed":
            raise ValueError("Actual full-document HTTP case is not completed")
        md = capture / "cases/1225475375/result.md"
        if sha(md) != case["MD_SHA256"]:
            raise ValueError("Captured Markdown SHA differs from real HTTP receipt")
        plan = json.loads((capture / "run-plan.json").read_text())
        planned = next(c for c in plan["sources"] if c["source"] == "1225475375")
        if planned["sha256"] != reference["source_SHA256"]:
            raise ValueError("Actual HTTP request source SHA differs")
        page_text = evaluator.source_verifier.pages(md.read_text())[62]
        tables = reader.read_public(page_text, 62)
        segments = [page_text]
        origin = {
            "type": "real_full_PDF_HTTP_capture",
            "job": case["job"],
            "input_total_pages": 119,
            "MD": str(md),
            "MD_SHA256": sha(md),
            "capture_summary_SHA256": sha(capture / "summary.json"),
        }
        integrity = {
            "status": "not_applicable_chat_EOS",
            "reason": "Actual Docling-backed HTTP completion; no autoregressive chat API token evidence.",
        }
        public_source = {
            "status": "pass"
            if all(t["actual_public_metadata"].get("source_pages") == [62] for t in tables)
            and tables
            else "fail",
            "actual_metadata": [t["actual_public_metadata"] for t in tables],
        }
        header_roles = any(
            t["actual_public_metadata"].get("header_scope_rows") == [0, 1, 2]
            and t["actual_public_metadata"].get("header_scope_complete")
            for t in tables
        )
    else:
        page_dir = args.official_page
        request = json.loads((page_dir / "request.json").read_text())
        if request["page"] != 62 or request["source_pdf_SHA256"] != reference["source_SHA256"]:
            raise ValueError("Official per-page input identity differs")
        blocks_path = page_dir / "official-blocks.json"
        blocks = json.loads(blocks_path.read_text())
        tables, errors = evaluator.read_tables(blocks)
        segments = [block["content"] for block in blocks if block.get("content")]
        origin = {
            "type": "official_model_page_trial",
            "request": str(page_dir / "request.json"),
            "request_SHA256": sha(page_dir / "request.json"),
            "blocks": str(blocks_path),
            "blocks_SHA256": sha(blocks_path),
            "HTML_reader_errors": errors,
            "source_total_pages": request.get("source_total_pages"),
        }
        integrity = evaluator.assess_generation(page_dir)
        public_source = {
            "status": "unknown",
            "reason": "Per-page model trial is not a MosaicParse HTTP source/table-source implementation.",
        }
        # Explicit original header cells and their full source spans constitute
        # the visible header topology; never invent missing role metadata.
        header_roles = None
    comparison = evaluator.grid_comparison(tables, reference["rows_raw"], reference["spans"])
    full_grid = comparison.pop("pass")
    body_expected = reference["rows_raw"][3:]
    body_candidates = []
    for table in tables:
        if table["num_rows"] != 9 or table["num_cols"] != 11:
            continue
        errors = [
            {"row": r + 3, "column": c, "source": expected, "actual": table["rows"][r + 3][c]}
            for r, values in enumerate(body_expected)
            for c, expected in enumerate(values)
            if evaluator.prose(expected) != evaluator.prose(table["rows"][r + 3][c])
        ]
        body_candidates.append(
            {
                "location": evaluator.locations(table),
                "mismatches": errors,
                "positions": 66,
                "source_six_body_rows_exact": not errors,
            }
        )
    normalized = auditor.canonical("\n".join(segments))
    body_anchors = [value for row in body_expected for value in row if value.strip()]
    covered = [value for value in body_anchors if auditor.covered(value, normalized)]
    ambiguous_generation = integrity["status"] not in {
        "all_calls_EOS",
        "all_calls_server_stop",
        "not_applicable_chat_EOS",
    }
    status = (
        "pass"
        if full_grid and header_roles is not False
        else "unknown"
        if ambiguous_generation
        else "fail"
    )
    result = {
        "schema": "mosaicparse-additional-p62-grid-acceptance/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "scope": "Separate extra p62 only; never included in the original fourteen-page denominator.",
        "verifier_SHA256": sha(Path(__file__)),
        "source_reference_SHA256": sha(reference_path),
        "source_original_SHA256": reference["source_SHA256"],
        "source_page": 62,
        "origin": origin,
        "generation_integrity": integrity,
        "source_table_positions": 99,
        "source_body_positions": 66,
        "source_header_rows": 3,
        "source_body_rows": 6,
        "source_spans": 9,
        "table_restoration_status": status,
        "all_99_positions_and_nine_spans_equal": full_grid,
        "public_header_roles_complete_three_levels": header_roles,
        "comparison": comparison,
        "six_body_rows_bound_to_original_columns": body_candidates,
        "text_only_diagnostic": {
            "source_nonempty_body_anchors": len(body_anchors),
            "covered": len(covered),
            "coverage_alone_cannot_pass_table_restoration": True,
        },
        "public_source_mapping": public_source,
    }
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "table_restoration": status,
                "source_grid": [9, 11],
                "actual_shapes": comparison["actual_shapes"],
                "text_only_anchor_coverage": [len(covered), len(body_anchors)],
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
