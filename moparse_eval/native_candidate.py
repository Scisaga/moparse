"""Candidate-only saved Native reading, shared by diagnosis and bounded research.

No Expected, Final, IR, Semantic or production conversion input is accepted.
"""

from __future__ import annotations

import copy
import os
import re
import resource
import sys
from pathlib import Path
from typing import Any


def expose_native_heading_fields(
    observation: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Expose already saved, text-identical native heading metadata.

    The common candidate compiler consumes explicit heading fields. Some saved
    regions carry their actual level only in their own SDK Markdown export;
    independent native context already reads that level. Bind those same fields
    before compiling candidates, without adding or changing any primary text.
    """
    from .native_relations import heading_evidence
    from .representations import visible_text
    from .three_layer import canonical

    derived = copy.deepcopy(observation)
    evidence = []
    recognized = {"heading", "section_header", "title", "doc_title"}

    def heading_metadata_text(text):
        # This binds only a level to the same native object. SDK rendering may
        # flatten spaces or serialized line breaks; primary/T text is unchanged.
        return re.sub(r"\\[rn]|\s+", "", canonical(text))

    for page in derived.get("pages", []):
        for block in page.get("blocks", []):
            exported = block.get("native_export_markdown")
            if block.get("cells"):
                continue
            proof = heading_evidence(block)
            level = proof.get("resolved_level")
            if type(level) is not int:
                continue
            primary = visible_text(block.get("text", ""), block.get("text_format", "plain"))
            if proof.get("level_source") == "native_export_markdown" and (
                not isinstance(exported, str)
                or heading_metadata_text(primary)
                != heading_metadata_text(visible_text(exported, "markdown"))
            ):
                continue  # Conflicting native views cannot supply each other's text.
            own = {
                key: value
                for key, value in block.items()
                if key not in {"native_export_markdown", "level", "heading_level"}
            }
            primary_level = heading_evidence(own).get("resolved_level")
            current_level = (
                (block.get("heading_level", block.get("level", 1)) or 1)
                if block.get("kind") in recognized
                else primary_level
            )
            if current_level == level and proof.get("role") == "heading":
                continue
            evidence.append(
                {
                    "native_path": block.get("native_path"),
                    "original_kind": block.get("kind"),
                    "source": (
                        block.get("native_export_markdown_path")
                        if proof.get("level_source") == "native_export_markdown"
                        else block.get("native_path")
                    ),
                    "heading_evidence": proof,
                    "primary_text_unchanged": True,
                    "exposed_level": level,
                    "expected_access": False,
                }
            )
            block.update(kind="heading", heading_level=level, level=level)
    return derived, evidence


def bind_native_syntax_scopes(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Withdraw guessed syntax hierarchy where native evidence says unknown.

    No fact, value, qualifier, parent edge or primary text is added. The separate
    native context is authoritative only for its own recorded source blocks.
    Explicit contradictions and mixed/ambiguous native scopes remain blocked.
    """
    contexts = evidence.get("native_context", {})
    events = {row["id"]: row for row in contexts.get("heading_events", [])}
    own_events = {row["source"].get("block"): row for row in events.values()}
    records = []
    for unit in evidence.get("syntax", []):
        block = unit.get("source", {}).get("block")
        context = contexts.get("by_block", {}).get(block)
        if not context:
            continue
        own = own_events.get(block)
        if unit.get("kind") == "heading" and own and own.get("hierarchy_known") is False:
            if "heading_level" in unit:
                records.append(
                    {
                        "source": unit["source"],
                        "action": "withdraw_inferred_heading_level",
                        "previous_level": unit.pop("heading_level"),
                        "native_level": None,
                        "basis": own["evidence"],
                        "expected_access": False,
                    }
                )
        uncertain = [
            events[ref["event_id"]]
            for ref in context.get("context_evidence", [])
            if ref.get("event_id") in events
            and events[ref["event_id"]].get("hierarchy_known") is False
        ]
        if not uncertain or context.get("conflicts") or context.get("scope_disagreements"):
            continue
        if any(
            row.get("evidence", {}).get("markdown_status") == "mixed_scope" for row in uncertain
        ):
            continue
        paths = [context.get("heading_path", [])]
        paths.extend(
            row["path"]
            for row in context.get("explicit_heading_paths", [])
            if row.get("status") == "bound"
        )
        if unit.get("kind") == "heading":
            paths = [path[:-1] if path[-1:] == [unit.get("text")] else path for path in paths]
        scope = unit.get("scope", [])
        checked = (
            scope[:-1]
            if unit.get("kind") == "heading" and scope[-1:] == [unit.get("text")]
            else scope
        )
        distinct = {tuple(path) for path in paths}
        if checked not in paths and len(distinct) == 1:
            new_scope = list(next(iter(distinct)))
            records.append(
                {
                    "source": unit["source"],
                    "action": "withdraw_unsupported_syntax_scope",
                    "previous_scope": scope,
                    "native_heading_path": new_scope,
                    "unknown_heading_events": [row["id"] for row in uncertain],
                    "basis": "independent_native_context_without_known_hierarchy",
                    "expected_access": False,
                }
            )
            unit["scope"] = new_scope
    return records


def read_native_candidate(row, *, root: Path):
    """The same native reader and candidate compiler used by prior diagnosis."""
    from .document_ast_comparison import _candidate_ast
    from .expected_evaluation import native_observation
    from .three_layer import read_candidate

    observation = native_observation(
        root,
        {
            "sample_id": row["sample_id"],
            "pipeline": row["pipeline"],
            "observation": row["observation"]["path"],
        },
    )
    observation, headings = expose_native_heading_fields(observation)
    evidence = read_candidate(observation)
    scopes = bind_native_syntax_scopes(evidence)
    _candidate_ast(evidence)
    return evidence, {
        "native_heading_field_readback": headings,
        "native_syntax_scope_readback": scopes,
        "asset_delivery": observation.get("asset_delivery"),
    }


def worker(input_path: Path, output: Path):
    """Audit a separate, source-masked, network-disabled Native-only process."""
    from .native_evaluation import ROOT, _keys, limit_resources, reference, verify_input
    from .packaging import read_json, write_json

    manifest = read_json(input_path)
    _keys(manifest["records"])
    limit_resources()
    violations, reads = [], set()
    active = set()
    media = {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
        ".svg",
        ".mp4",
        ".docx",
        ".pptx",
    }

    def reject(detail):
        violations.append(str(detail))
        raise RuntimeError("Native candidate isolation: " + str(detail))

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.path.realpath(os.fsdecode(args[0])))
            if path.suffix.lower() in media or str(path).startswith(("/dev/nvidia", "/dev/dri/")):
                reject(path)
            mode, flags = args[1], args[2]
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int)
                and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            )
            if writing and not path.is_relative_to(output) and path != Path("/dev/null"):
                reject("write outside own reading directory: " + str(path))
            if path.is_relative_to(ROOT):
                relative = path.relative_to(ROOT)
                code = relative.parts[0] in {
                    "moparse_eval",
                    "app",
                    "native_worker",
                    ".venv",
                    ".git",
                }
                if not (code or path.is_relative_to(output) or path in active):
                    reject("not this Native object's own input: " + str(path))
                if not writing:
                    reads.add(relative.as_posix())
        if event in {"socket.connect", "socket.bind", "socket.sendto"}:
            reject("network")
        if event == "subprocess.Popen" and list(args[1]) != ["git", "rev-parse", "HEAD"]:
            reject("subprocess: " + repr(args[1]))
        if event == "import" and args[0].split(".")[0] in {
            "torch",
            "paddle",
            "transformers",
            "vllm",
            "fitz",
            "pymupdf",
            "PIL",
        }:
            reject("model/media import: " + args[0])

    sys.addaudithook(audit)
    from .cli import code_identity
    from .expected_evaluation import _write_compact_score

    identity = code_identity()
    if identity["software_id"] != manifest["software_id"]:
        raise ValueError("candidate worker software differs")
    records = []
    for row in manifest["records"]:
        active.clear()
        active.update((ROOT / row[k]["path"]).resolve() for k in ("native", "observation"))
        entry = {k: row[k] for k in ("sample_id", "pipeline", "native", "observation")}
        try:
            verify_input(row)
            evidence, metadata = read_native_candidate(row, root=ROOT)
            target = output / row["pipeline"] / row["sample_id"] / "native.json"
            _write_compact_score(target, evidence)
            entry.update(state="read", candidate=reference(target), readback_metadata=metadata)
        except Exception as error:
            entry.update(
                state="software_failure",
                error={"type": type(error).__name__, "message": str(error)},
            )
        records.append(entry)
        print(
            "Native read: " + row["pipeline"] + "/" + row["sample_id"] + " " + entry["state"],
            flush=True,
        )
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    mask = any(" /opt/moparse/pdf_sample " in line and " - tmpfs " in line for line in mounts)
    same_software = code_identity()["software_id"] == manifest["software_id"]
    isolated_network = os.readlink("/proc/self/ns/net") != os.environ.get("MO_NATIVE_HOST_NETNS")
    passed = (
        not violations
        and same_software
        and mask
        and isolated_network
        and all(row["state"] == "read" for row in records)
    )
    write_json(
        output / "candidate-reading.json",
        {
            "status": "passed" if passed else "blocked",
            "software_id": identity["software_id"],
            "records": records,
            "expected_access": False,
            "Final_access": False,
            "quality_scoring_executed": False,
            "boundary_violations": violations,
            "repository_file_reads": sorted(reads),
            "source_masked": mask,
            "network_namespace_isolated": isolated_network,
            "cpu_affinity": sorted(os.sched_getaffinity(0)),
            "address_space_limit_bytes": resource.getrlimit(resource.RLIMIT_AS)[0],
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        },
    )
    return 0 if passed else 2


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    raise SystemExit(worker(arguments.input.resolve(), arguments.output.resolve()))
