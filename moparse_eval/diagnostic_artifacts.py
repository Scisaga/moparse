"""Explicit development-artifact bindings for unpublished, bounded diagnosis.

Candidate reading is a separate phase. It receives no reference path or answer;
the comparison phase consumes its saved readback and existing requirement views.
No processing, activation, formal aggregation or reference compilation lives here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .native_candidate import bind_native_syntax_scopes, expose_native_heading_fields
from .packaging import inside, read_json, write_json


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(root: Path, reference: dict[str, str]) -> Path:
    path = inside(root, reference["path"])
    if path.suffix.lower() not in {".json", ".md"}:
        raise ValueError("diagnostic bindings admit saved JSON and Markdown only")
    if not path.is_file() or sha256(path) != reference["sha256"]:
        raise ValueError("diagnostic artifact missing or checksum differs: " + str(path))
    return path


def load_artifacts(path: Path, *, root: Path, sample_ids: list[str]) -> dict[str, Any]:
    """Validate every explicit pairing; never fall back to another delivery."""
    from .expected_evaluation import PIPELINES

    manifest = read_json(path)
    if (
        manifest.get("diagnostic_only") is not True
        or manifest.get("publishable") is not False
        or manifest.get("quality_scores_withheld") is not True
    ):
        raise ValueError("development artifacts are diagnostic-only and unpublished")
    records = manifest["records"]
    keys = [(r["sample_id"], r["pipeline"]) for r in records]
    samples = set(manifest["sample_ids"])
    documents = {(r["document_id"], r["pipeline"]) for r in records}
    if (
        not samples
        or len(keys) != len(set(keys))
        or set(keys) != {(s, p) for s in samples for p in PIPELINES}
        or len(keys) != manifest["record_count"]
        or len(documents) != manifest["document_pipeline_count"]
        or len({r["document_id"] for r in records}) != manifest["document_count"]
    ):
        raise ValueError("diagnostic selection/pipeline bindings must be complete and unique")
    if not sample_ids or len(sample_ids) != len(set(sample_ids)) or not set(sample_ids) <= samples:
        raise ValueError("diagnostic samples must be distinct explicit manifest selections")
    selections = {}
    used_final_paths = set()
    for row in records:
        if row["selection_id"] != row["sample_id"] or row["software_id"] != manifest["software_id"]:
            raise ValueError("diagnostic selection or execution software differs")
        for field in (
            "native",
            "observation",
            "final",
            "evidence",
            "delivery_state",
            "binding",
            "input_binding",
        ):
            _artifact(root, row[field])
        final_path = inside(root, row["final"]["path"])
        if final_path in used_final_paths:
            raise ValueError("diagnostic final body cannot be borrowed across records")
        used_final_paths.add(final_path)
        binding = read_json(inside(root, row["binding"]["path"]))
        source = read_json(inside(root, row["input_binding"]["path"]))
        for key in ("sample_id", "document_id", "pipeline", "software_id"):
            if binding[key] != row[key]:
                raise ValueError("diagnostic final binding identity differs: " + key)
        if (
            source["selection"]["id"] != row["selection_id"]
            or source["selection"]["document_id"] != row["document_id"]
            or source["selection"]["source_pages"] != row["source_pages"]
            or binding["source_pages"] != row["source_pages"]
            or source["software_id"] != row["software_id"]
        ):
            raise ValueError("diagnostic selection authorization differs")
        selection = source["selection"]
        if selections.setdefault(row["sample_id"], selection) != selection:
            raise ValueError("diagnostic pipelines disagree on selection authorization")
        for field in ("native", "observation"):
            if (
                source[field] != row[field]["path"]
                or source[field + "_sha256"] != row[field]["sha256"]
                or binding[field + "_sha256"] != row[field]["sha256"]
            ):
                raise ValueError("diagnostic native/final pairing differs")
        directory = inside(root, row["binding"]["path"]).parent
        for field in ("final", "evidence", "delivery_state", "input_binding"):
            relative = inside(root, row[field]["path"]).relative_to(directory).as_posix()
            if binding["artifact_sha256"].get(relative) != row[field]["sha256"]:
                raise ValueError("diagnostic delivery is not bound to its execution")
        if inside(root, row["observation"]["path"]).with_name("native.json") != inside(
            root, row["native"]["path"]
        ):
            raise ValueError("diagnostic native reader must consume the explicitly paired input")
    return {
        **manifest,
        "records": [r for r in records if r["sample_id"] in sample_ids],
        "selections": {s: selections[s] for s in sample_ids},
    }


def read_candidates(manifest: dict[str, Any], output: Path, *, root: Path) -> Path:
    """Read Native and delivered Final independently before any Expected access."""
    from .cli import code_identity
    from .expected_evaluation import _write_compact_score, final_observation, native_observation
    from .three_layer import read_candidate

    output.mkdir(parents=True, exist_ok=False)
    identity = code_identity()
    records = []
    for row in manifest["records"]:
        record = {k: row[k] for k in ("sample_id", "document_id", "selection_id", "pipeline")}
        record["sides"] = {}
        for side in ("native", "final"):
            destination = Path("candidates") / row["pipeline"] / row["sample_id"] / (side + ".json")
            try:
                if side == "native":
                    observation = native_observation(
                        root,
                        {
                            "sample_id": row["sample_id"],
                            "pipeline": row["pipeline"],
                            "observation": row["observation"]["path"],
                        },
                    )
                    observation, heading_fields = expose_native_heading_fields(observation)
                else:
                    observation = final_observation(
                        inside(root, row["final"]["path"]),
                        sample_id=row["sample_id"],
                        pipeline=row["pipeline"],
                        pages=list(range(1, len(row["source_pages"]) + 1)),
                    )
                evidence = read_candidate(observation)
                syntax_scopes = bind_native_syntax_scopes(evidence) if side == "native" else []
                from .document_ast_comparison import _candidate_ast

                _candidate_ast(evidence)
                evidence["diagnostic_candidate"] = {
                    "side": side,
                    "artifact": row[side],
                    "observation": row["observation"] if side == "native" else None,
                    "asset_delivery": observation.get("asset_delivery"),
                    "reader_software_id": identity["software_id"],
                    "native_heading_field_readback": heading_fields if side == "native" else [],
                    "native_syntax_scope_readback": syntax_scopes,
                    "execution_software_id": row["software_id"],
                    "expected_access": False,
                    "production_conversion_executed": False,
                }
                _write_compact_score(output / destination, evidence)
                record["sides"][side] = {
                    "state": "read",
                    "path": destination.as_posix(),
                    "sha256": sha256(output / destination),
                }
            except (
                ValueError,
                IndexError,
                KeyError,
                TypeError,
                AttributeError,
                RuntimeError,
                OSError,
            ) as error:
                record["sides"][side] = {
                    "state": "software_blocked",
                    "error": {"type": type(error).__name__, "message": str(error)},
                }
        records.append(record)
        print("candidate read: " + row["pipeline"] + "/" + row["sample_id"], flush=True)
    result = {
        "diagnostic_only": True,
        "publishable": False,
        "quality_scores_withheld": True,
        "expected_access": False,
        "software": identity,
        "execution_software_id": manifest["software_id"],
        "records": records,
    }
    write_json(output / "candidate-reading.json", result)
    return output / "candidate-reading.json"


def run_bound_diagnostic(
    baseline: Path,
    output: Path,
    *,
    manifest_path: Path,
    sample_ids: list[str],
    phase: str,
    expected_root: Path,
    requirements: Path | None,
    candidate_root: Path | None,
) -> Path:
    from .expected_evaluation import ROOT

    manifest = load_artifacts(manifest_path, root=ROOT, sample_ids=sample_ids)
    protected = [
        expected_root,
        baseline / "requirements",
        baseline / "scores/current",
        baseline / "service/current",
    ]
    protected.extend(
        inside(ROOT, row[key]["path"]).parent
        for row in manifest["records"]
        for key in ("native", "final")
    )
    if any(output.resolve().is_relative_to(path.resolve()) for path in protected):
        raise ValueError(
            "diagnostic output must be separate from references and saved/official inputs"
        )
    run = read_json(baseline / "run.json")
    full_scope = {c["sample_id"] for c in run["cases"] if c["suite"] == "quality800"}
    if not set(manifest["sample_ids"]) < full_scope:
        raise ValueError("unfrozen diagnostic artifact scope must be a strict saved-run subset")
    if phase == "read":
        return read_candidates(manifest, output, root=ROOT)
    if requirements is None or candidate_root is None:
        raise ValueError(
            "comparison needs existing requirements and independent candidate readback"
        )
    # Import the comparison orchestrator only after the independent read phase.
    from .diagnostic_comparison import compare_candidates

    return compare_candidates(
        manifest,
        output,
        root=ROOT,
        expected_root=expected_root,
        requirements=requirements,
        candidate_root=candidate_root,
    )
