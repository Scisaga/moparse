"""Fixed, development-exposed Native study, isolated from full Lite activation.

Preparation is immutable and unapproved. Only a separate explicit user decision
can admit execution; neither preflight nor file existence grants that decision.
All correctness judgments remain in the existing three-layer comparator.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import resource
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .packaging import inside, read_json, write_json

ROOT = Path(__file__).resolve().parent.parent
AREA = "benchmark/runs/lite/diagnostics/native-research-phase17"
HISTORY = "benchmark/runs/lite/diagnostics/native-research-phase16/input-binding.json"
HISTORY_SHA = "4b7c33c86e866986f530695c75742f65f8a1bc75e0dfe0f37ab175185938df86"
PREPARATION = (
    "benchmark/runs/lite/diagnostics/text-readback-phase15/native-research-preparation.json"
)
PREPARATION_SHA = "f474d83aa1fbd3561f38d52307aa30621ebf1258f89c0a93bac22dff33cf3f7a"
MATRIX = "benchmark/runs/lite/diagnostics/native-research-phase16/readiness-matrix.json"
MATRIX_SHA = "b7fa13806fe3c450f46b753750e77f63153bdc45f97719e93233861abb39131b"
SELECTIONS = {
    "zhenye-coupon-seals-p001-003": ("S3", "1200694910", [1, 2, 3]),
    "tencent-conditions-entity-payment-definitions-p108-114": (
        "S4",
        "complex-tencent-2025-bond-programme",
        list(range(108, 115)),
    ),
    "huawei-management-toc-p014": ("S6", "complex-huawei-2024-annual", [14]),
}
PIPELINES = tuple(f"P{i:02}" for i in range(1, 9))
LAYERS = ("T", "L", "B")
SCHEMA = "moparse-native-research-freeze/1"
PERMISSIONS = {
    "approval_status": "not_approved",
    "execution_authorized": False,
    "publication_authorized": False,
}
COMPONENTS = {"scope", "inputs", "evaluation", "requirements", "costs", "readiness", "validation"}
DECISIONS = (
    "fixed_research_scope",
    "native_only_entry",
    "exact_scoring_freeze",
    "formal_execution",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(path: Path) -> dict[str, str]:
    return {"path": path.resolve().relative_to(ROOT.resolve()).as_posix(), "sha256": sha256(path)}


def artifact(ref: dict[str, Any], *, suffix: str = ".json") -> Path:
    path = inside(ROOT, ref["path"])
    if (
        suffix not in {".json", ".xml", ".py", ".toml", ".lock", ".txt", ".md", ".sh"}
        or path.suffix != suffix
        or not path.is_file()
        or sha256(path) != ref.get("sha256")
    ):
        raise ValueError("Native freeze artifact missing or changed: " + str(path))
    return path


def _unapproved(record):
    if any(
        record.get(k) != v or type(record.get(k)) is not type(v) for k, v in PERMISSIONS.items()
    ):
        raise ValueError(
            "preparation must remain not_approved, execution_authorized=false, publication_authorized=false"
        )


def _keys(rows):
    keys = [(r["sample_id"], r["pipeline"]) for r in rows]
    if (
        len(keys) != 24
        or len(set(keys)) != 24
        or set(keys) != {(s, p) for s in SELECTIONS for p in PIPELINES}
    ):
        raise ValueError("Native research must retain exactly S3/S4/S6 x P01-P08, 24 combinations")
    return keys


def input_rows(history, preparation):
    """Project Native provenance only; the Final conversion identity is excluded."""
    permissions = {(r["sample_id"], r["pipeline"]): r for r in preparation["records"]}
    fields = (
        "sample_id",
        "document_id",
        "selection_id",
        "pipeline",
        "source_pages",
        "native",
        "observation",
        "selection",
        "producer",
        "configuration",
        "page_bindings",
        "native_run_id",
        "native_software_id",
    )
    return [
        {
            **{k: copy.deepcopy(row[k]) for k in fields},
            "page_branches_views_and_permissions": copy.deepcopy(
                permissions[row["sample_id"], row["pipeline"]][
                    "page_branches_views_and_permissions"
                ]
            ),
        }
        for row in history["records"]
    ]


def verify_input(row):
    """Verify original metadata and whole objects, without reading source media."""
    sid, pipeline = row["sample_id"], row["pipeline"]
    _, document, pages = SELECTIONS[sid]
    if (
        row["selection_id"] != sid
        or row["document_id"] != document
        or row["source_pages"] != pages
        or row["selection"]["id"] != sid
        or row["selection"]["document_id"] != document
        or row["selection"]["source_pages"] != pages
    ):
        raise ValueError("Native selection/page identity differs")
    directory = f"benchmark/runs/lite/artifacts/{pipeline}/measured-quality800-r1/{sid}/"
    for name in ("native", "observation"):
        if row[name]["path"] != directory + name + ".json":
            raise ValueError("candidate must be its own original Native/observation, never Final")
    native = read_json(artifact(row["native"]))
    observation = read_json(artifact(row["observation"]))
    if (
        native["pipeline"] != pipeline
        or observation["pipeline"] != pipeline
        or observation["sample_id"] != sid
        or observation["run_id"] != row["native_run_id"]
        or native["config"] != row["configuration"]
    ):
        raise ValueError("Native producer/configuration/execution identity differs")
    bindings = row["page_bindings"]
    if (
        len(bindings) != len(pages)
        or len(native["pages"]) != len(pages)
        or [p["page"] for p in native["pages"]] != list(range(1, len(pages) + 1))
    ):
        raise ValueError("Native page mapping is incomplete")
    for number, (binding, page, permission) in enumerate(
        zip(bindings, native["pages"], row["page_branches_views_and_permissions"], strict=True)
    ):
        if (
            binding["entry"] != f"#/pages/{number}"
            or binding["input_page"] != page["page"]
            or binding["original_page"] != pages[number]
            or binding["branch"] != page["branch"]
            or permission["existing_page_binding"] != binding
        ):
            raise ValueError("Native page/branch/source permission differs")
    return native, observation


def requirement_inventory(graph):
    """Enumerate the existing comparator's owners, without running a comparison."""
    from .document_ast_comparison import document_order_requirements, navigation_order_requirements
    from .three_layer import canonical

    coverage = graph["comparison_coverage"]
    ids = copy.deepcopy(coverage["retained_semantic_requirements"])
    for i, node in enumerate(graph["source_form_requirements"]):
        ids["L"].append(f"L:content:{i}")
        if node["role"] != "heading":
            ids["B"].append(f"B:content:{i}")
    ids["L"].extend(e["id"] for e in document_order_requirements(graph))
    ids["L"].extend(e["id"] for e in navigation_order_requirements(graph))
    if any(len(x) != len(set(x)) for x in ids.values()):
        raise ValueError("duplicate requirement owner")
    return {
        "requirement_ids": ids,
        "denominators": {
            "T": sum(len(canonical(t["text"])) for t in graph["text"]),
            "L": len(ids["L"]),
            "B": len(ids["B"]),
        },
    }


def _requirements(binding, inputs):
    from .requirement_gate import load_bound_requirement

    index = artifact(binding["index"])
    for ref in binding["reference_files"]:
        artifact(ref, suffix=Path(ref["path"]).suffix)
    historical_path = artifact(binding["historical_independent_acceptance"])
    historical = read_json(historical_path)
    accepted = historical.get("original_61_ids", []) + historical.get("fixed_2_ids", [])
    if (
        type(historical.get("source_oracle_passed")) is not int
        or historical["source_oracle_passed"] != len(accepted)
        or not set(SELECTIONS) <= set(accepted)
        or type(historical.get("source_span_oracle_passed")) is not int
        or historical["source_span_oracle_passed"] < 1
        or historical.get("source_index_sha256") != binding["index"]["sha256"]
    ):
        raise ValueError("historical independent source acceptance missing")
    expected_evidence = [
        {"path": (historical_path.parent / name).relative_to(ROOT).as_posix(), "sha256": digest}
        for name, digest in historical["evidence_sha256"].items()
    ]
    if not expected_evidence or binding["independent_evidence"] != expected_evidence:
        raise ValueError("independent acceptance evidence missing")
    for ref in expected_evidence:
        artifact(ref, suffix=Path(ref["path"]).suffix)
    assertion_refs = [
        {"path": name, "sha256": digest}
        for name, digest in historical.get("handwritten_assertion_identity", {})
        .get("handwritten_assertion_modules_sha256", {})
        .items()
    ]
    if binding.get("independent_assertion_sources", []) != assertion_refs:
        raise ValueError("independent source assertion identity differs")
    for ref in assertion_refs:
        artifact(ref, suffix=".py")
    rows = binding["records"]
    if len(rows) != 3 or {r["sample_id"] for r in rows} != set(SELECTIONS):
        raise ValueError("requirement binding must retain every selection")
    selections = {r["sample_id"]: r["selection"] for r in inputs}
    result = {}
    for row in rows:
        sid = row["sample_id"]
        artifact(row["json"])
        artifact(row["xml"], suffix=".xml")
        graph, projection, index_row, _ = load_bound_requirement(
            index, selections[sid], ROOT / "pdf_sample/parsing/expected"
        )
        if (
            index_row != row["index_record"]
            or requirement_inventory(projection) != row["inventory"]
            or graph["comparison_coverage"]["source_complete"] is not True
            or graph["comparison_coverage"]["responsibility_complete"] is not True
            or graph["comparison_coverage"]["structure_complete"] is not True
        ):
            raise ValueError("missing requirement or blocked Expected responsibility")
        result[sid] = projection
    return result


def load_preparation(path: Path, *, verify_requirements: bool = True):
    """Bind fixed inputs, software and cost evidence; never authorize or grade."""
    from .cli import code_identity
    from .expected_scoring import PROTOCOL

    frozen = read_json(path)
    _unapproved(frozen)
    if frozen.get("schema") != SCHEMA or set(frozen.get("components", {})) != COMPONENTS:
        raise ValueError("incomplete Native research freeze")
    parts = {k: read_json(artifact(v)) for k, v in frozen["components"].items()}
    scope = parts["scope"]
    if (
        scope.get("benchmark") != "native"
        or scope.get("selection_ids") != list(SELECTIONS)
        or scope.get("pipelines") != list(PIPELINES)
        or scope.get("combinations") != 24
        or scope.get("independent_holdout") is not False
        or scope.get("represents_full_lite") is not False
    ):
        raise ValueError("fixed Native research scope differs")
    history = read_json(artifact({"path": HISTORY, "sha256": HISTORY_SHA}))
    preparation = read_json(artifact({"path": PREPARATION, "sha256": PREPARATION_SHA}))
    rows = parts["inputs"]["records"]
    _keys(rows)
    if rows != input_rows(history, preparation):
        raise ValueError(
            "Native inputs differ from the predeclared preparation; no automatic rebinding"
        )
    for row in rows:
        verify_input(row)
    requirements = parts["requirements"]
    if (
        requirements["reference_files"] != history["reference_files"]
        or requirements["index"] != history["requirement_files"][0]
        or [r["json"] for r in requirements["records"]] != history["requirement_files"][1:]
    ):
        raise ValueError("Expected/index/requirement views differ from the existing preparation")
    evaluation = parts["evaluation"]
    live = code_identity()
    if (
        evaluation["software"] != live
        or frozen["software_id"] != live["software_id"]
        or evaluation["protocol"] != PROTOCOL
        or evaluation["python_executable"] != sys.executable
    ):
        raise ValueError("Native freeze software/Python/comparator/contract identity differs")
    for ref in evaluation["environment_files"]:
        artifact(ref, suffix=Path(ref["path"]).suffix)
    matrix = read_json(artifact({"path": MATRIX, "sha256": MATRIX_SHA}))
    readiness = parts["readiness"]["records"]
    _keys(readiness)
    original = {(r["sample_id"], r["pipeline"]): r for r in matrix["records"]}
    for row in readiness:
        previous = original[row["sample_id"], row["pipeline"]]
        for layer in LAYERS:
            expected = previous["layers"][layer]
            if row["layers"][layer] != {
                k: expected[k]
                for k in (
                    "state",
                    "required_records",
                    "fixed_denominator",
                    "not_comparable_requirement_ids",
                    "not_comparable_reasons",
                )
            }:
                raise ValueError("partial/blocked layer responsibility changed")
    costs = parts["costs"]
    if (
        costs["verification"] != preparation["phase16"]["original_cost_verification"]
        or costs["execution_verification"]
        != preparation["phase16"]["original_execution_verification"]
    ):
        raise ValueError("original cost/execution verification identity differs")
    cost_record = read_json(artifact(costs["verification"]))
    execution = read_json(artifact(costs["execution_verification"]))
    if {r["pipeline"] for r in cost_record["records"]} != set(PIPELINES) or {
        r["pipeline"] for r in execution["records"]
    } != set(PIPELINES):
        raise ValueError("missing original cost/configuration record")
    # This is cost provenance only, never additional quality candidates.
    for ref in costs["original_record_bindings"]:
        artifact(ref)
    if costs["original_record_bindings"] != cost_record["original_cost_bindings"]:
        raise ValueError("missing original cost binding")
    validation = parts["validation"]
    if validation["software_id"] != live["software_id"]:
        raise ValueError("independent preflight must use the same software")
    for key in ("source_only", "independent_entry", "native_reading"):
        receipt = read_json(artifact(validation[key]))
        if receipt.get("software_id") != live["software_id"]:
            raise ValueError("mixed independent validation software")
        if key == "source_only":
            if (
                receipt.get("exit_code") != 0
                or receipt.get("collection_only") is not False
                or receipt.get("boundary_violations")
                or receipt.get("software_unchanged") is not True
                or receipt.get("tests_unchanged") is not True
                or not receipt.get("executed_nodeids")
            ):
                raise ValueError("source-only software validation did not pass")
            for relative, digest in receipt["reviewed_files"].items():
                artifact({"path": relative, "sha256": digest}, suffix=Path(relative).suffix)
        elif receipt.get("status") != "passed":
            raise ValueError("independent entry/Native reading validation missing or failed")
        if key == "native_reading":
            _keys(receipt["records"])
            if (
                receipt.get("expected_access") is not False
                or receipt.get("Final_access") is not False
                or receipt.get("boundary_violations")
                or receipt.get("source_masked") is not True
                or receipt.get("network_namespace_isolated") is not True
            ):
                raise ValueError("Native candidate reading was not independently isolated")
            by_key = {(r["sample_id"], r["pipeline"]): r for r in rows}
            for read in receipt["records"]:
                source = by_key[read["sample_id"], read["pipeline"]]
                if read["state"] != "read" or any(
                    read[k] != source[k] for k in ("native", "observation")
                ):
                    raise ValueError("candidate reading is missing or belongs to another input")
                artifact(read["candidate"])
    loaded = _requirements(parts["requirements"], rows) if verify_requirements else {}
    return frozen, parts, loaded


def _output(path: Path, *, execute: bool):
    base = ROOT / ("benchmark/runs/lite/native-only" if execute else AREA)
    resolved = path.resolve()
    if (
        not resolved.is_relative_to(base.resolve())
        or resolved == base.resolve()
        or "current" in resolved.relative_to(base.resolve()).parts
        or resolved.exists()
    ):
        raise ValueError(
            "use a new independent Native research destination; current activation is forbidden"
        )


def require_authorization(path: Path | None, freeze: Path):
    if path is None:
        raise ValueError(
            "execution_authorized=false; explicit scope, entry, exact freeze and execution approval required"
        )
    record = read_json(path)
    if (
        record.get("origin") != "explicit_user_instruction"
        or not record.get("instruction_reference")
        or record.get("freeze") != reference(freeze)
        or record.get("software_id") != read_json(freeze)["software_id"]
        or record.get("approval_status") != "approved"
        or record.get("execution_authorized") is not True
        or any(record.get("decisions", {}).get(k) is not True for k in DECISIONS)
    ):
        raise ValueError(
            "Native research requires separate explicit approvals bound to the exact freeze"
        )
    return record


def limit_resources():
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:8])
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    os.environ["CUDA_VISIBLE_DEVICES"] = ""


def launch_reading(inputs, destination: Path, software_id: str):
    """A fresh namespace gets Native declarations only, never Expected paths."""
    _output(
        destination,
        execute=destination.resolve().is_relative_to(
            (ROOT / "benchmark/runs/lite/native-only").resolve()
        ),
    )
    destination.mkdir(parents=True, exist_ok=False)
    candidate_inputs = copy.deepcopy(inputs)
    for row in candidate_inputs:
        row["selection"] = {k: row["selection"][k] for k in ("id", "document_id", "source_pages")}
    write_json(
        destination / "candidate-input.json",
        {"records": candidate_inputs, "software_id": software_id},
    )
    script = """
set -eu
mount --make-rprivate /
mount --bind "$1" "$1"
mount -o remount,bind,ro "$1"
mount --bind "$2" "$2"
mount -o remount,bind,rw "$2"
for part in pdf_sample datasets data pdf_sample_extra pdf_page_images; do
    if [ -d "$1/$part" ]; then mount -t tmpfs -o ro,size=1m tmpfs "$1/$part"; fi
done
exec "$3" -m moparse_eval.native_candidate --input "$2/candidate-input.json" --output "$2"
"""
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": "",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT),
        "MO_NATIVE_HOST_NETNS": os.readlink("/proc/self/ns/net"),
    }
    subprocess.run(
        [
            "unshare",
            "--mount",
            "--net",
            "bash",
            "-c",
            script,
            "native-read",
            str(ROOT),
            str(destination),
            sys.executable,
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    return destination / "candidate-reading.json"


def preflight(path: Path):
    try:
        frozen, parts, _ = load_preparation(path)
        rows = parts["readiness"]["records"]
        return {
            **PERMISSIONS,
            "preflight_status": "ready_for_authorization",
            "state": "verified",
            "freeze": reference(path),
            "software_id": frozen["software_id"],
            "combinations": len(rows),
            "layer_readiness": {
                layer: dict(Counter(row["layers"][layer]["state"] for row in rows))
                for layer in LAYERS
            },
            "quality_scoring_executed": False,
            "global_gate": "structure_blocked_unchanged",
        }
    except Exception as error:
        return {
            **PERMISSIONS,
            "preflight_status": "blocked",
            "state": "prepared",
            "quality_scoring_executed": False,
            "blockers": [
                {"side": "software_or_binding", "type": type(error).__name__, "message": str(error)}
            ],
        }


def retain_limits(score, readiness, inventory):
    """Withhold unsupported conclusions without changing any comparator or divisor."""
    score = copy.deepcopy(score)
    actual = {
        layer: [r["id"] for r in score["outcomes"] if r["layer"] == layer] for layer in LAYERS
    }
    if any(
        len(actual[layer]) != len(set(actual[layer]))
        or set(actual[layer]) != set(inventory["requirement_ids"][layer])
        or score["layers"][layer]["denominator"] != inventory["denominators"][layer]
        for layer in LAYERS
    ):
        raise ValueError("comparison omitted/changed a fixed requirement or denominator")
    for row in score["outcomes"]:
        limit = readiness["layers"][row["layer"]]["not_comparable_reasons"].get(row["id"])
        if limit:
            row.update(
                comparator_outcome=row["outcome"], outcome="unresolved", research_limitation=limit
            )
    for layer in LAYERS:
        state = readiness["layers"][layer]["state"]
        score["layers"][layer]["research_state"] = state
        if state != "ready" or score["layers"][layer].get("complete") is not True:
            score["layers"][layer].update(numerator=None, score=None, complete=False)
            score["blockers"].append(
                {"side": "research_limit", "layers": [layer], "reason": "frozen_partial_or_blocked"}
            )
    score.update(
        score=None,
        publishable=False,
        benchmark="native",
        scope="S3/S4/S6 development-exposed research",
    )
    # The shared comparator retains its full internal proof. Its nested base
    # aggregates are not independent research scores either.
    base = score.get("document_comparison", {}).get("base_score")
    if isinstance(base, dict):
        base.update(score=None, publishable=False)
        for counts in base.get("layers", {}).values():
            counts.update(score=None, numerator=None)
    return score


def execute_native(freeze: Path, output: Path, authorization: Path | None):
    # Admission precedes all candidate reading, score paths, and directory writes.
    approval = require_authorization(authorization, freeze)
    _output(output, execute=True)
    checked = preflight(freeze)
    if checked["preflight_status"] != "ready_for_authorization":
        raise ValueError("Native execution blocked by preflight: " + repr(checked["blockers"]))
    frozen, parts, requirements = load_preparation(freeze)
    output.mkdir(parents=True, exist_ok=False)
    status = {
        "benchmark": "native",
        "state": "running",
        "freeze": reference(freeze),
        "software_id": frozen["software_id"],
        "formal_execution_authorized": True,
        "publication_authorized": approval.get("publication_authorized") is True,
        "overall_quality_score": None,
        "full_lite_ranking": False,
        "records": [],
    }
    write_json(output / "execution-status.json", status)
    try:
        from .expected_evaluation import _write_compact_score
        from .layer_aggregation import summarize_layers
        from .three_layer import grade_layers
        from .trace_storage import read_score

        # Read again after authorization, before comparing; old diagnostics are
        # never copied into a formal result and are never used as candidate data.
        reading = read_json(
            launch_reading(parts["inputs"]["records"], output / "reading", frozen["software_id"])
        )
        if reading["status"] != "passed" or reading["software_id"] != frozen["software_id"]:
            raise ValueError(
                "Native candidate reader failed; software failure is not candidate zero"
            )
        masks = {(r["sample_id"], r["pipeline"]): r for r in parts["readiness"]["records"]}
        inventories = {r["sample_id"]: r["inventory"] for r in parts["requirements"]["records"]}
        scores = {p: [] for p in PIPELINES}
        _keys(reading["records"])
        for row in reading["records"]:
            sid, pipeline = row["sample_id"], row["pipeline"]
            candidate = read_score(artifact(row["candidate"]))
            score = retain_limits(
                grade_layers(requirements[sid], candidate), masks[sid, pipeline], inventories[sid]
            )
            relative = f"requirements/{pipeline}/{sid}.json"
            _write_compact_score(output / relative, score)
            scores[pipeline].append(score)
            status["records"].append({"sample_id": sid, "pipeline": pipeline, "path": relative})
        # The existing aggregator remains strict. Partial layers never enter it.
        status["aggregation"] = {
            p: summarize_layers(rows)
            if all(r["publishable"] for r in rows)
            else {"state": "partial_or_blocked", "score": None, "all_requirements_retained": True}
            for p, rows in scores.items()
        }
        load_preparation(freeze)  # Input/software drift invalidates the entire run.
        status.update(state="executed_limited_research", published=False)
    except BaseException as error:
        status.update(
            state="software_failure",
            published=False,
            error={"type": type(error).__name__, "message": str(error)},
        )
        raise
    finally:
        write_json(output / "execution-status.json", status)
    write_json(output / "index.json", status)
    return output / "index.json"


def native_command(args):
    limit_resources()
    if args.phase == "execute":
        print(execute_native(args.freeze, args.output, args.authorization))
        return 0
    if args.authorization is not None:
        raise ValueError("read/preflight cannot consume or create an execution approval")
    _output(args.output, execute=False)
    if args.phase == "read":
        frozen = read_json(args.freeze)
        _unapproved(frozen)
        inputs = read_json(artifact(frozen["components"]["inputs"]))["records"]
        history = read_json(artifact({"path": HISTORY, "sha256": HISTORY_SHA}))
        preparation = read_json(artifact({"path": PREPARATION, "sha256": PREPARATION_SHA}))
        _keys(inputs)
        if inputs != input_rows(history, preparation):
            raise ValueError("candidate inputs differ from the fixed Native declaration")
        from .cli import code_identity

        if frozen["software_id"] != code_identity()["software_id"]:
            raise ValueError("candidate reading software differs")
        print(launch_reading(inputs, args.output, frozen["software_id"]))
        return 0
    result = preflight(args.freeze)
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["preflight_status"] == "ready_for_authorization" else 2
