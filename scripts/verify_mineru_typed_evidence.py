"""Correlate new official checks with immutable, already delivered JSON evidence.

No conversion, model, corpus, service, or quality evaluator is invoked. All
source inputs come from the prior explicit binding, not a sample search.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from moparse_eval.mineru_typed_validation import TextOnlyBoundary, observe  # noqa: E402
from tests.validation.mineru_native_assertions import accept_fixed_mineru  # noqa: E402

STABLE_FIELDS = (
    "native_path",
    "kind",
    "text",
    "native_block_type",
    "native_content",
    "native_payload",
    "native_fields",
    "parent_id",
    "native_sequence",
    "order_basis",
    "bbox",
    "branch_page",
    "source_view",
    "native_index",
    "native_block_id",
    "native_media_declaration",
)
CELL_FIELDS = ("native_path", "row", "col", "row_span", "col_span", "text", "source_locator")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def correlate(item, run):
    pipeline = item["pipeline"]
    native_path = ROOT / item["native_input"]
    old_output = ROOT / item["output"]
    if (
        sha(native_path) != item["native_sha256"]
        or sha(old_output / "evidence.json") != item["evidence_sha256"]
    ):
        raise ValueError("prior immutable binding mismatch")
    native = json.loads(native_path.read_text())
    previous = json.loads((old_output / "evidence.json").read_text())
    final = (old_output / "final.md").read_text()
    if sha(old_output / "final.md") != item["final_sha256"]:
        raise ValueError("historical final changed")
    official = json.loads((run / (pipeline + ".json")).read_text())
    if official["pipeline"] != pipeline or official["native_sha256"] != item["native_sha256"]:
        raise ValueError("official result belongs to a different input")
    if (
        not official["input_unchanged"]
        or not official["input_bytes_unchanged"]
        or official["boundary"]["violations"]
    ):
        raise ValueError("official validation crossed its boundary or changed input")
    # These independently authored assertions inspect caller-supplied native,
    # source cells, typed table relations, and actual final spans. They neither
    # load official classes nor provide a parser-quality answer.
    json_assertion = accept_fixed_mineru(native, previous, final)
    baseline = {
        b["native_path"]: b for blocks in previous["native_blocks"].values() for b in blocks
    }
    containers = {
        c["native_path"]: c
        for p in previous["bridge"]["pages"]
        for c in p.get("native_containers", [])
    }
    dispositions = {r["native_path"]: r for r in previous["content_dispositions"]}
    paths = set()
    comparisons, differences = [], []
    for row in official["objects"]:
        path = row["path"]
        if path in paths:
            raise ValueError("duplicate official source occurrence")
        paths.add(path)
        old = containers[path] if path in containers else baseline[path]
        fresh = row["common"]["projection"]
        fields = {key: observe(fresh.get(key)) == observe(old.get(key)) for key in STABLE_FIELDS}
        if not all(fields.values()):
            raise ValueError(
                f"common source projection differs from frozen delivery: {pipeline} {path} {fields}"
            )
        cells = [{key: c.get(key) for key in CELL_FIELDS} for c in fresh.get("cells", [])]
        old_cells = [{key: c.get(key) for key in CELL_FIELDS} for c in old.get("cells", [])]
        if cells != old_cells:
            raise ValueError(f"HTML source cells changed at {path}")
        if row["common"]["status"] != "retained" or row["text_comparison"]["status"] != "retained":
            raise ValueError(f"unresolved official/common comparison at {path}")
        display = row["projection"].get("text")
        disposition = dispositions.get(path)
        comparisons.append(
            {
                "path": path,
                "parent_path": row["parent_path"],
                "native_type": row["native_type"],
                "stable_fields_equal": fields,
                "source_cells_equal": len(cells),
                "schema": row["schema"],
                "official_text_sha256": row["projection"].get("utf8_sha256"),
                "delivery_disposition": disposition,
                "container_audit": {
                    "original_children": row.get("original_children"),
                    "final_children_retained": path in containers,
                }
                if path in containers
                else None,
            }
        )
        for category in row.get("difference_classifications", []):
            if category["category"] == 2:
                differences.append(
                    {
                        "path": path,
                        **category,
                        "full_diff": row["serialization"]["full_diff"],
                        "to_dict_diff": row["serialization"]["to_dict_diff"],
                    }
                )
        if display != old.get("markdown"):
            differences.append(
                {
                    "path": path,
                    "category": 1,
                    "reason": "source_bound_text_order_cells_and_final_relations_retained; product_display_differs",
                    "official_display": display,
                    "common_service_display": old.get("markdown"),
                    "final_disposition": disposition,
                }
            )
    expected_paths = {p for p in baseline | containers if p.startswith("#/documents/")}
    if paths != expected_paths:
        raise ValueError("official validation did not cover all own Middle occurrences")
    for record in [*official["documents"], *official["pages"]]:
        if record["schema"]["status"] == "rejected":
            differences.append(
                {
                    "path": record.get("path", record.get("page_path")),
                    "category": 3,
                    "reason": "saved_wire_payload_rejected_by_official_document_or_page_validator",
                    "schema": record["schema"],
                }
            )
    continuation_fields = [
        {
            "path": r["path"] + "/continues_prev",
            "value": r["raw_payload"]["continues_prev"],
            "explicitly_present": True,
            "parent_path": r["parent_path"],
        }
        for r in official["objects"]
        if r["parent_path"] is not None and "continues_prev" in r["raw_payload"]
    ]
    return {
        "pipeline": pipeline,
        "native_input": item["native_input"],
        "native_sha256": item["native_sha256"],
        "official_result": str(run / (pipeline + ".json")),
        "official_result_sha256": sha(run / (pipeline + ".json")),
        "old_output": item["output"],
        "old_evidence_sha256": item["evidence_sha256"],
        "old_final_sha256": item["final_sha256"],
        "states": item["states"],
        "summary": official["summary"],
        "objects": comparisons,
        "differences": differences,
        "nested_explicit_continuation_fields": continuation_fields,
        "independent_existing_JSON_assertion": {
            k: v for k, v in json_assertion.items() if k != "official_typed_acceptance"
        },
        "existing_assertion_scope": "JSON adapter/table/final source preservation only; historical Typed status literal not reused",
        "production_defects_found": [],
        "production_changed": False,
        "new_conversion_executed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("historical evidence cannot be overwritten")
    boundary = TextOnlyBoundary()
    boundary.install()
    binding = json.loads(args.binding.read_text())
    intake = json.loads(args.intake.read_text())
    checks = {p: sha(ROOT / p) == value["sha256"] for p, value in intake["files"].items()}
    main_packages = sorted((d.metadata["Name"], d.version) for d in metadata.distributions())
    unchanged_packages = main_packages == [tuple(row) for row in intake["main_packages"]]
    if not all(checks.values()) or not unchanged_packages:
        raise ValueError("protected inputs/history/locks/main dependencies changed")
    results = [
        correlate(o, args.run) for o in binding["outputs"] if o["pipeline"] in {"P06", "P07"}
    ]
    if {r["pipeline"] for r in results} != {"P06", "P07"}:
        raise ValueError("both own fixed inputs are required")
    record = {
        "purpose": "official_vs_existing_JSON_and_actual_delivery_correlation_without_reconversion",
        "command": [sys.executable, *sys.argv],
        "pipelines": results,
        "preservation": checks,
        "main_dependencies_unchanged": unchanged_packages,
        "P01_P05": "all bound inputs/finals/evidence preserved; no new real conversion",
        "boundary_violations": boundary.violations,
        "formal_current_index_exists": (
            ROOT / "benchmark/runs/lite/service/current/index.json"
        ).exists(),
        "expected_access": False,
        "quality_scores": None,
    }
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "preserved_files": len(checks),
                "pipelines": {r["pipeline"]: r["summary"] for r in results},
            },
            ensure_ascii=False,
        )
    )
    return int(bool(boundary.violations))


if __name__ == "__main__":
    raise SystemExit(main())
