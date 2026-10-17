"""Read candidate-image Docling page components with the same model-source tests.

Uses actual current-export GFM without rewriting it as MinerU HTML or adding
public comments. All table geometry is read from real public GFM metadata.
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


evaluator = load("docling_component_evaluator", "evaluate-mineru-source.py")
auditor = load("docling_component_coverage", "audit-visible-source-spans.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_public(content, page):
    parsed = evaluator.source_verifier.public_tables(content, page)
    tables = []
    for index, table in enumerate(parsed):
        rows, meta = table["rows"], table["meta"]
        cells = [
            {
                "row": r,
                "column": c,
                "rowspan": 1,
                "colspan": 1,
                "text": text,
                "semantic_markup": text,
                "HTML_line_column": None,
            }
            for r, row in enumerate(rows)
            for c, text in enumerate(row)
        ]
        tables.append(
            {
                "rows": rows,
                "num_rows": len(rows),
                "num_cols": meta["num_cols"],
                "spans": meta["spans"],
                "cells": cells,
                "block_index": index,
                "table_index": index,
                "block_bbox": None,
                "block_angle": None,
                "raw_pointer": f"Markdown table-fragment/structure {table['id']}",
                "complete_physical_coverage": all(len(row) == meta["num_cols"] for row in rows),
                "uncovered_grid_positions": [],
                "actual_public_metadata": meta,
            }
        )
    return tables


def extra_checks(pages):
    """The four source-confirmed additional observations; separate denominator."""
    out = []
    by_key = {(page["source"], page["source_page"]): page for page in pages}
    if ("1225474739", 40) in by_key:
        page = by_key[("1225474739", 40)]
        audit = auditor.audit(
            "1225474739",
            40,
            HERE.parents[4] / "pdf_sample/1225474739.pdf",
            page["_segments"],
            {"scope": "extra state audit"},
        )
        choices = audit["choice_state_context_checks"]
        first = next(
            (
                choice
                for choice in choices
                if choice["source_context"]
                and auditor.canonical(choice["source_context"]["text"]).startswith("持股5%")
            ),
            None,
        )
        out.append(
            {
                "check": "p40_first_post_table_not_applicable_checked_state",
                "status": first["status"] if first else "unknown",
                "source": "1225474739",
                "source_page": 40,
                "evidence": first,
            }
        )
    if ("1225475375", 74) in by_key:
        page = by_key[("1225475375", 74)]
        text = evaluator.prose("\n".join(evaluator.visible(v) for v in page["_segments"]))
        expected = "—公司期末不存在需计提在建工程减值准备的情形。"
        out.append(
            {
                "check": "p74_original_em_dash_not_changed_to_Chinese_one",
                "status": "pass" if evaluator.prose(expected) in text else "fail",
                "source": "1225475375",
                "source_page": 74,
                "expected": expected,
            }
        )
        out.append(
            {
                "check": "p74_QR_graphic_not_invented_as_verbatim_footer_text",
                "status": "fail" if "验证码" in text else "pass",
                "source": "1225475375",
                "source_page": 74,
                "source_visual_evidence": "additional-source-observations/1225475375-p74-QR-source.png",
                "observed_inferred_label": "验证码" if "验证码" in text else None,
            }
        )
    if ("1225474693", 3) in by_key:
        page = by_key[("1225474693", 3)]
        text = evaluator.prose("\n".join(evaluator.visible(v) for v in page["_segments"]))
        expected = "基本养老保险基金一零零一组合"
        out.append(
            {
                "check": "p3_original_institution_name_Chinese_one_not_hyphen",
                "status": "pass" if evaluator.prose(expected) in text else "fail",
                "source": "1225474693",
                "source_page": 3,
                "expected": expected,
                "source_evidence": "additional-source-observations/source-confirmed-identity-observation.json",
            }
        )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite model/component evaluation evidence")
    manifest = json.loads((args.run / "run-manifest.json").read_text())
    reference = json.loads((HERE / "source-reference.json").read_text())
    old_reference = json.loads(evaluator.BASELINE_REFERENCE.read_text())
    out = {
        "schema": "mosaicparse-docling-component-independent-source-evaluation/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "run_manifest": str(args.run / "run-manifest.json"),
        "run_manifest_SHA256": sha(args.run / "run-manifest.json"),
        "evaluator_SHA256": sha(Path(__file__)),
        "shared_model_checks_SHA256": sha(HERE / "evaluate-mineru-source.py"),
        "scope": "Same fourteen original source pages and fixed forty-six shared conditions; a CPU component experiment, not full-PDF HTTP or public-interface acceptance.",
        "pages": [],
    }
    for item in manifest["pages"]:
        page_dir = args.run / f"{item['id']}-p{item['page']}"
        path = page_dir / "page.md"
        if sha(path) != item["MD_SHA256"]:
            raise ValueError(f"Captured GFM SHA differs: {path}")
        text = path.read_text()
        tables = read_public(text, item["page"])
        blocks = [
            {
                "type": "evaluation_visible_text_view",
                "content": evaluator.source_verifier.visible_markdown(text),
                "raw_pointer": str(path) + "#rendered-visible-body",
            }
        ]
        checks = evaluator.model_checks(
            item["id"], item["page"], blocks, tables, reference, old_reference
        )
        for check in checks:
            check["status"] = "pass" if check["observed_pass"] else "fail"
        out["pages"].append(
            {
                "source": item["id"],
                "source_page": item["page"],
                "source_SHA256": item["source_pdf_SHA256"],
                "actual_GFM": str(path),
                "actual_GFM_SHA256": sha(path),
                "convert_status": item["conversion_status"],
                "generation_integrity": {
                    "status": "not_applicable_chat_EOS",
                    "reason": "Docling CPU model pipeline; no chat token generation or model HTTP request, actual convert status recorded.",
                },
                "table_shapes": [[table["num_rows"], table["num_cols"]] for table in tables],
                "checks": checks,
                "counts": {
                    status: sum(c["status"] == status for c in checks)
                    for status in ["pass", "fail", "unknown"]
                },
                "public_interface_source_mapping": "Current export metadata captured, but no full-PDF HTTP workflow is claimed by this component run.",
                "_segments": [text],
            }
        )
    out["additional_four_source_observations"] = extra_checks(out["pages"])
    for page in out["pages"]:
        page.pop("_segments")
    out["fixed_condition_counts"] = {
        status: sum(page["counts"][status] for page in out["pages"])
        for status in ["pass", "fail", "unknown"]
    }
    out["additional_observation_counts"] = {
        status: sum(c["status"] == status for c in out["additional_four_source_observations"])
        for status in ["pass", "fail", "unknown"]
    }
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pages": len(out["pages"]),
                "fixed_conditions": out["fixed_condition_counts"],
                "additional_observations": out["additional_observation_counts"],
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
