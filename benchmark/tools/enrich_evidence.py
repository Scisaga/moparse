"""Attach already judged source gates and external identity proof to new evidence.

This is a reporting operation: it cannot evaluate, repair or change Markdown,
gold, model recipes or recorded metric counts. The input record is preserved;
the enriched record must be written to a different, previously absent path.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from benchmark import moparse_benchmark as bench

ANNOTATIONS = bench.DEFAULT_DATASET.parent / "annotations"


def source_gate_metrics(evaluation: dict, record: dict) -> dict:
    """Extract fixed source checks without invoking or changing any predicate."""
    if evaluation.get("schema") != "moparse-public-evaluation/1":
        raise ValueError("Supplementary source gates require public evaluation")
    if not evaluation.get("coverage", {}).get("complete"):
        raise ValueError("Supplementary fixed denominators require complete source coverage")
    scores = evaluation["public_structure_aware"]
    received = {item["document_id"]: item["sha256"] for item in record["received_MD_proofs"]}
    cases = scores["cases"]
    for case in cases:
        if received.get(case["source"]) != case["MD_SHA256"]:
            raise ValueError("Evaluation Markdown identity differs from captured evidence")
    reader = record["quality"]["core209"]["reader_fingerprint"]

    def metric(count: int, total: int, gold: str) -> dict:
        if type(count) is not int or not 0 <= count <= total:
            raise ValueError("Invalid frozen source count")
        return {
            "pass": count,
            "total": total,
            "gold_fingerprint": bench.digest(ANNOTATIONS / gold),
            "reader_fingerprint": reader,
            "scope_cohort_id": "regression-502",
        }

    stock_gold = bench.read(ANNOTATIONS / "shareholder-source-gold.json")
    stock_id = Path(stock_gold["source_document"]).stem
    stock = [item for item in scores["stock"] if item["source"] == stock_id]
    if len(stock) != 1:
        raise ValueError("Missing or ambiguous frozen shareholder-count check")
    same_header = bench.read(ANNOTATIONS / "same-header-source-gold.json")
    normal_total = same_header["complete_atomic_fields"]
    header_total = same_header["source_header_leaves_per_page"] * len(same_header["tables"])
    normal = scores["supplements"]["normal33"]["literal"]
    if normal["target_count"] != normal_total:
        raise ValueError("Normal continuation denominator differs from frozen source gold")
    return {
        "financial30": metric(
            scores["financial30"].get("pass", 0), 30, "full-selected-source-tables.json"
        ),
        "shareholder_count1": metric(
            int(stock[0]["status"] == "pass"), 1, "shareholder-source-gold.json"
        ),
        "normal_continuation33": metric(
            normal["literal_row_and_complete_header_pass"],
            normal_total,
            "same-header-source-gold.json",
        ),
        "normal_header10": metric(
            scores["normal_header_leaves_pass"], header_total, "same-header-source-gold.json"
        ),
    }


def snapshot(path: Path) -> dict:
    item = bench.artifact(path)
    target = bench.BENCH / "evidence/artifacts" / (item["sha256"] + path.suffix)
    if target.exists() and bench.digest(target) != item["sha256"]:
        raise ValueError("Evidence snapshot identity collision")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    return {
        **bench.artifact(target),
        "original_path": item["path"],
        "snapshot_bytes_unchanged": True,
    }


def bind_release_gates(record: dict, proof: dict) -> None:
    if proof.get("schema") != "moparse-source-release-acceptance/1":
        raise ValueError("Unsupported release source-gate proof")
    received = {item["document_id"]: item["sha256"] for item in record["received_MD_proofs"]}
    if not proof.get("documents"):
        raise ValueError("Release proof has no captured document identity")
    for item in proof["documents"]:
        if received.get(item["document_id"]) != item["MD_SHA256"]:
            raise ValueError("Release proof Markdown differs from captured evidence")
    record["source_release_gates"] = {
        "status": proof["status"],
        "pass": proof["pass"],
        "checks": {
            name: {"pass": check["pass"], "status": check["status"]}
            for name, check in proof["checks"].items()
        },
        "scope": proof["scope"],
        "checker_SHA256": proof["checker_SHA256"],
        "gold": proof["gold"],
    }


def enrich(
    source: Path,
    output: Path,
    *,
    evaluation: Path | None = None,
    deployment: Path | None = None,
    release_check: Path | None = None,
) -> dict:
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError("Enriched evidence requires a new output; input records are immutable")
    original = bench.read(source)
    errors = bench.validate_evidence(original)
    if errors:
        raise ValueError("; ".join(errors))
    record = copy.deepcopy(original)
    record["report_enrichment"] = {
        "created_at": bench.utc(),
        "original_evidence": snapshot(source),
        "tool": bench.artifact(Path(__file__)),
        "gold_or_scoring_predicates_changed": False,
        "Markdown_changed": False,
    }
    record["provenance"].append(snapshot(source))
    if evaluation:
        metrics = source_gate_metrics(bench.read(evaluation), record)
        if any(
            key in record["quality"] and record["quality"][key] != value
            for key, value in metrics.items()
        ):
            raise ValueError("Enrichment cannot change an existing metric")
        record["quality"].update(metrics)
        record["provenance"].append(snapshot(evaluation))
    if deployment:
        proof = bench.read(deployment)
        if proof.get("schema") != "moparse-observed-deployment/1":
            raise ValueError("Unsupported external deployment identity proof")
        # This field means the external readback passed. It does not change the
        # capture client's separate server_deployment_verified=false statement.
        record["qualification"]["external_source_identity_verified"] = (
            proof.get("ready_and_source_matched") is True
        )
        record["qualification"]["external_identity_proof"] = snapshot(deployment)
        record["provenance"].append(snapshot(deployment))
    if release_check:
        bind_release_gates(record, bench.read(release_check))
        record["provenance"].append(snapshot(release_check))
    # Release acceptance remains an explicit separate decision; adding a proof
    # never upgrades deployment_acceptance or fresh_model_inference by itself.
    errors = bench.validate_evidence(record)
    if errors:
        raise ValueError("; ".join(errors))
    bench.save(output, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evaluation", type=Path)
    parser.add_argument("--deployment", type=Path)
    parser.add_argument("--release-check", type=Path)
    args = parser.parse_args()
    record = enrich(
        args.evidence,
        args.output,
        evaluation=args.evaluation,
        deployment=args.deployment,
        release_check=args.release_check,
    )
    print(json.dumps({"id": record["id"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
