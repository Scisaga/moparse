"""Orchestrate existing T/L/B comparisons without compiling or publishing answers."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from .diagnostic_artifacts import sha256
from .packaging import inside, read_json, write_json


@contextmanager
def candidate_slice_cache():
    """Reuse pure candidate slices within one serial diagnostic comparison.

    The existing comparator makes the same source cuts for many requirements.
    This cache receives only actual blocks/cut bounds, never required answers.
    It is cleared and the original function restored after every comparison.
    """
    from . import requirement_ast

    original = requirement_ast._document_slice
    inputs = {}

    @lru_cache(maxsize=8192)
    def cached(key, start, end):
        parts, leaves, resolver = inputs[key]
        return original(parts, leaves, start, end, resolver)

    def slice_once(parts, leaves, start, end, resolver):
        key = (tuple((index, id(block)) for index, block in parts), id(resolver))
        inputs.setdefault(key, (parts, leaves, resolver))
        return cached(key, start, end)

    requirement_ast._document_slice = slice_once
    try:
        yield cached.cache_info
    finally:
        requirement_ast._document_slice = original
        cached.cache_clear()
        inputs.clear()


def withhold(score: dict[str, Any]) -> None:
    """Keep the complete comparison trace, with all quality results withheld."""
    score.update(diagnostic_only=True, publishable=False, quality_scores_withheld=True, score=None)
    for layer in score.get("layers", {}).values():
        layer.update(score=None, numerator=None)
        layer.pop("diagnostic_score", None)
        layer.pop("full_scope_edit_rate", None)
    base = score.get("document_comparison", {}).get("base_score")
    if isinstance(base, dict):
        withhold(base)


def _sources(value):
    """Retain original locators, including nested/cell/AST proof sources."""
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and any(
            k in value for k in ("lines", "page", "block", "text_span", "cell")
        ):
            yield value
        for key, part in value.items():
            if key not in {"retrieval", "candidates"}:
                yield from _sources(part)
    elif isinstance(value, list):
        for part in value:
            yield from _sources(part)


def _overlaps(left, right):
    if left.get("path") != right.get("path"):
        return False
    for key in ("cell", "row", "col", "block"):
        if key in left and key in right and left[key] != right[key]:
            return False
    for key in ("lines", "text_span"):
        if left.get(key) and right.get(key):
            a, b = left[key], right[key]
            if len(a) == len(b) == 2 and (
                max(a[0], b[0]) > min(a[1], b[1])
                or key == "text_span"
                and max(a[0], b[0]) == min(a[1], b[1])
            ):
                return False
    return True


def responsibility_blockers(graph):
    """Expose existing missing responsibilities; create no new requirements."""
    obligations = {row["id"]: row for row in graph["source_obligation_inventory"]["obligations"]}
    issues = {row["id"]: row for row in graph["unresolved"]}
    result = []
    for row in graph["comparison_coverage"]["obligations"]:
        if row["status"] in {"blocking", "deferred_input_scope"}:
            obligation = obligations[row["obligation_id"]]
            result.append(
                {
                    "id": row["obligation_id"],
                    "kind": "existing_source_obligation",
                    "layers": obligation["layers"],
                    "source": row["source"],
                    "status": "blocked" if row["status"] == "blocking" else "unresolved",
                    "reason": "comparison_responsibility_incomplete"
                    if row["status"] == "blocking"
                    else "input_scope_pending",
                    "coverage": row,
                }
            )
    for row in graph["comparison_coverage"]["analysis_limitations"]:
        if row["status"] in {"blocking", "deferred_input_scope"}:
            issue = issues[row["issue_id"]]
            result.append(
                {
                    "id": row["issue_id"],
                    "kind": "existing_analysis_limitation",
                    "layers": issue["layers"],
                    "source": row["source"],
                    "status": "blocked" if row["status"] == "blocking" else "unresolved",
                    "reason": issue["reason"],
                    "coverage": row,
                }
            )
    return result


def diagnostic_outcomes(score, *, graph, trace, artifact):
    """Annotate responsibility dependencies without changing core judgments."""
    blockers = responsibility_blockers(graph)
    result = []
    for index, row in enumerate(score["outcomes"]):
        sources = list(_sources(row.get("expected", {})))
        if isinstance(row.get("source"), dict):
            sources.append(row["source"])
        dependencies = [
            blocker
            for blocker in blockers
            if row["layer"] in blocker["layers"]
            and any(_overlaps(source, blocker["source"]) for source in sources)
        ]
        state = "blocked" if dependencies else row["outcome"]
        result.append(
            {
                "requirement_id": row["id"],
                "layer": row["layer"],
                "role": row["role"],
                "requirement_status": "blocked" if dependencies else "accepted",
                "status": state,
                "comparator_status": row["outcome"],
                "requirement_evidence": sources,
                "candidate_evidence": list(_sources(row.get("actual"))),
                "trace": {"path": trace, "json_pointer": "#/outcomes/" + str(index)},
                "candidate_artifact": artifact,
                "blocker": dependencies,
                "software_failure": row.get("software_failure", False),
                "publishable": False,
            }
        )
    return result


def load_requirements(index_path: Path, sample, expected_root: Path):
    """Read an existing view and bind its selected raw source; never recompile it."""
    from .expected_readback import read_expected
    from .requirement_graph import evaluation_projection, validate_requirement_graph

    index = read_json(index_path)
    rows = [row for row in index["records"] if row["sample_id"] == sample["id"]]
    if len(rows) != 1:
        raise ValueError("selected requirement view missing or duplicated")
    row = rows[0]
    path = inside(index_path.parent, row["json"])
    if sha256(path) != row["generated_view_sha256"]:
        raise ValueError("existing requirement view checksum differs")
    graph = read_json(path)
    # No expected= argument: that formal validation path recompiles a graph.
    validate_requirement_graph(graph)
    expected = read_expected(sample, expected_root, selection_only=True)
    saved = graph["source_obligation_inventory"]["selection"]
    for key in ("sample_id", "document_id", "source_pages", "scope", "authorized_raw_segments"):
        if saved[key] != expected[key]:
            raise ValueError("existing requirement source binding differs: " + key)
    return graph, evaluation_projection(graph), row, expected


def compare_candidates(
    manifest,
    output: Path,
    *,
    root: Path,
    expected_root: Path,
    requirements: Path,
    candidate_root: Path,
) -> Path:
    from .cli import code_identity
    from .expected_evaluation import _write_compact_score
    from .three_layer import grade_layers
    from .trace_storage import read_score

    output.mkdir(parents=True, exist_ok=False)
    identity = code_identity()
    reading = read_json(candidate_root / "candidate-reading.json")
    reads = {(r["sample_id"], r["pipeline"]): r for r in reading["records"]}
    if (
        reading.get("expected_access") is not False
        or reading["execution_software_id"] != manifest["software_id"]
    ):
        raise ValueError("comparison requires independent candidate reading of this execution")
    expected_keys = {(r["sample_id"], r["pipeline"]) for r in manifest["records"]}
    if not expected_keys <= reads.keys() or len(reads) != len(reading["records"]):
        raise ValueError("candidate read phase missing or duplicates explicit records")
    records, blockers = [], []
    loaded = {}
    for sample_id, sample in manifest["selections"].items():
        try:
            graph, projection, index_row, expected = load_requirements(
                requirements, sample, expected_root
            )
            loaded[sample_id] = (graph, projection)
            write_json(
                output / "selected-expected" / (sample_id + ".json"),
                {
                    "diagnostic_only": True,
                    "publishable": False,
                    "canonical_selection": expected,
                    "existing_requirement_index": str(requirements),
                    "existing_index_record": index_row,
                    "comparison_responsibility": graph["comparison_coverage"],
                    "responsibility_blockers": responsibility_blockers(graph),
                },
            )
        except (
            ValueError,
            IndexError,
            KeyError,
            TypeError,
            AttributeError,
            RuntimeError,
            OSError,
        ) as error:
            blockers.append(
                {
                    "sample_id": sample_id,
                    "side": "expected",
                    "reason": "expected_reader_or_requirement_binding_failure",
                    "error": {"type": type(error).__name__, "message": str(error)},
                }
            )
    for binding in manifest["records"]:
        sample_id, pipeline = binding["sample_id"], binding["pipeline"]
        record = {k: binding[k] for k in ("sample_id", "document_id", "selection_id", "pipeline")}
        record["sides"] = {}
        for side in ("native", "final"):
            entry = reads[sample_id, pipeline]["sides"][side]
            source = inside(candidate_root, entry["path"]) if entry.get("path") else None
            expected_error = next((b for b in blockers if b["sample_id"] == sample_id), None)
            try:
                if expected_error:
                    raise ValueError(str(expected_error))
                if entry["state"] != "read" or source is None or sha256(source) != entry["sha256"]:
                    raise ValueError(
                        "independent candidate readback blocked or checksum differs: " + str(entry)
                    )
                graph, projection = loaded[sample_id]
                evidence = read_score(source)
                provenance = evidence["diagnostic_candidate"]
                if (
                    provenance["artifact"] != binding[side]
                    or provenance["side"] != side
                    or provenance["expected_access"] is not False
                ):
                    raise ValueError("saved candidate readback belongs to another artifact or side")
                with candidate_slice_cache():
                    score = grade_layers(projection, evidence)
                withhold(score)
                score.update(
                    diagnostic_execution_software_id=identity["software_id"],
                    delivery_execution_software_id=binding["software_id"],
                    candidate_source=binding[side],
                    existing_requirement_index_record=next(
                        r for r in read_json(requirements)["records"] if r["sample_id"] == sample_id
                    ),
                )
                relative = Path("traces") / pipeline / sample_id / (side + ".json")
                _write_compact_score(output / relative, score)
                outcomes = diagnostic_outcomes(
                    score, graph=graph, trace=relative.as_posix(), artifact=binding[side]
                )
                outcome_relative = Path("outcomes") / pipeline / sample_id / (side + ".json")
                write_json(
                    output / outcome_relative,
                    {
                        "diagnostic_only": True,
                        "publishable": False,
                        "quality_scores_withheld": True,
                        "records": outcomes,
                    },
                )
                record["sides"][side] = {
                    "state": "diagnosed",
                    "trace": relative.as_posix(),
                    "trace_sha256": sha256(output / relative),
                    "outcomes": outcome_relative.as_posix(),
                    "status_counts": dict(Counter(r["status"] for r in outcomes)),
                    "layer_status_counts": {
                        layer: dict(Counter(r["status"] for r in outcomes if r["layer"] == layer))
                        for layer in ("T", "L", "B")
                    },
                    "comparison_blockers": score["blockers"],
                    "candidate_issues": score.get("candidate_issues", []),
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
                blocker = {
                    "side": "software",
                    "reason": side + "_comparison_failure",
                    "error": {"type": type(error).__name__, "message": str(error)},
                }
                record["sides"][side] = {"state": "software_blocked", "blocker": blocker}
            print(
                "comparison: "
                + pipeline
                + "/"
                + sample_id
                + "/"
                + side
                + ": "
                + record["sides"][side]["state"],
                flush=True,
            )
        records.append(record)
        write_json(
            output / "execution-progress.json",
            {
                "diagnostic_only": True,
                "publishable": False,
                "records": records,
                "expected_blockers": blockers,
            },
        )
    result = {
        "diagnostic_only": True,
        "publishable": False,
        "quality_scores_withheld": True,
        "software": identity,
        "delivery_software_id": manifest["software_id"],
        "existing_requirement_state": read_json(requirements)["state"],
        "candidate_reading": str(candidate_root / "candidate-reading.json"),
        "expected_blockers": blockers,
        "records": records,
    }
    write_json(output / "diagnostic-execution.json", result)
    return output / "diagnostic-execution.json"
