"""Fixed saved Docling/GLM development inputs: native JSON to actual final service text.

This is format/conversion evidence, not expected comparison, formal replay or
quality scoring. Its inputs contain no reference answer or source byte reader.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.models.parse_options import ContentParseOptions
from app.models.source import StoredSource
from app.services.saved_content_service import SavedContentService

from .service_observation import build_service_observation
from .service_replay_native import replay_native
from .service_source_policy import apply_source_stages
from .service_stages import capture_stage, materialize_stage, stage_edit_ledger


def format_readback_checks(native, result):
    """Check present native fields against the adapter, without any answer input."""
    from .service_p01_adapter import audit_copy
    from .service_replay_native import _pointer

    checks = []
    for blocks in result._native_page_blocks.values():
        for block in blocks:
            raw = _pointer(native, block["native_path"])
            checks.append(
                {
                    "native_path": block["native_path"],
                    "field": "native_payload",
                    "equal": audit_copy(raw) == block.get("native_payload"),
                }
            )
            if not isinstance(raw, dict):
                continue
            field = {'docling': 'text', 'glm': 'content', 'mineru': 'content', 'paddle': 'block_content'}[block['native_branch']]
            if isinstance(raw.get(field), str) and block.get("read_status") == "read":
                value = raw[field]
                if block.get("text_selection"):
                    value = "".join(value[a:b] for a, b in block["text_selection"])
                checks.append(
                    {
                        "native_path": block["native_path"] + "/" + field,
                        "field": "visible_source_text",
                        "equal": block.get("text") == value,
                    }
                )
            if block["native_branch"] == "docling":
                for cell in block.get("cells", []):
                    original = _pointer(native, cell["native_path"])
                    if not isinstance(original, dict):
                        continue
                    fields = {
                        "start_row_offset_idx": "row",
                        "start_col_offset_idx": "col",
                        "row_span": "row_span",
                        "col_span": "col_span",
                        "text": "text",
                        "column_header": "is_column_header",
                        "row_header": "is_row_header",
                    }
                    for key, destination in fields.items():
                        if key in original:
                            checks.append(
                                {
                                    "native_path": cell["native_path"] + "/" + key,
                                    "field": key,
                                    "equal": cell.get(destination) == original[key],
                                }
                            )
    return checks


def content_dispositions(result, observation):
    """Account for actual native content using located final spans and refs."""
    from app.services.final_content_service import map_text_offset

    emitted = {}
    for page in observation["pages"]:
        for block in page["blocks"]:
            for cell in block.get("cells", []):
                ref = cell.get("source_cell_ref", {})
                if ref.get("token") and cell.get("final_markdown_span") is not None:
                    emitted.setdefault(ref["token"], []).append(cell["final_markdown_span"])
    final_evidence = result._final_text_evidence
    assembly, edits = final_evidence["assembly_markdown"], final_evidence["edits"]
    semantics = {ident: view for view in result._semantic_tables for ident in view.source_tables}
    records = []
    for page, blocks in result._native_page_blocks.items():
        for block in blocks:
            record = {
                "native_path": block["native_path"],
                "page": page,
                "branch": block["native_branch"],
                "original_pdf_page": block.get("original_pdf_page"),
                "native_label": block["kind"],
                "classification": block["type"],
                "raw_text": block.get("text"),
                "read_status": block["read_status"],
                "occurrence_id": block.get("occurrence_id", block["id"]),
                "source_text_selection": block.get("text_selection"),
                "final_spans": [],
                "cells": [],
            }
            fragment = block.get("service_fragment_id")
            view = semantics.get(fragment)
            if view is not None:
                record.update(
                    classification="data_table" if view.records else "unknown_grid",
                    disposition="converted"
                    if view.status == "converted"
                    else "unresolved_retained",
                    source_evidence={
                        "semantic_view": view.view_id,
                        "reasons": list(view.reason_codes),
                    },
                )
                for cell in block.get("cells", []):
                    token = f"{fragment}.r{cell['row']}c{cell['col']}"
                    spans = emitted.get(token, [])
                    empty = not cell.get("text", "").strip()
                    record["cells"].append(
                        {
                            "native_path": cell["native_path"],
                            "native_cell_id": cell['id'],
                            "raw_text": cell.get("text", ""),
                            "source_locator": cell.get("source_locator"),
                            "source_cell_ref": token,
                            "disposition": "empty_literal_not_filled"
                            if empty
                            else "located_in_final"
                            if spans
                            else "unresolved_final_location",
                            "final_spans": spans,
                            "actual_renderings": [result.markdown[a:b] for a, b in spans],
                        }
                    )
                record["final_spans"] = [
                    span for cell in record["cells"] for span in cell["final_spans"]
                ]
            else:
                marker = block.get("service_marker")
                text = str(block.get("markdown", "")).replace("\r\n", "\n").replace("\r", "\n")
                location = assembly.find(marker) if marker else -1
                start = location - len(text)
                if location >= 0 and start >= 0 and assembly[start:location] == text:
                    a, b = map_text_offset(start, edits), map_text_offset(location, edits, end=True)
                    actual = result.markdown[a:b]
                    record.update(
                        disposition="unresolved_media_delivery"
                        if block["type"] == "image" or block.get("inline_media_references")
                        else "explicitly_excluded_furniture"
                        if not actual
                        else "unresolved_retained"
                        if block["read_status"] == "unresolved"
                        else "retained",
                        final_spans=[[a, b]],
                        actual_rendering=actual,
                        assembly_span=[start, location],
                        edit_reasons=[
                            e["reason"] for e in edits if e["start"] < location and start < e["end"]
                        ],
                    )
                elif not text:
                    record["disposition"] = "unresolved_native_node_without_text"
                else:
                    record["disposition"] = "unresolved_final_location"
            records.append(record)
    return records


async def close_saved_document(
    native: dict[str, Any],
    source: StoredSource,
    *,
    sample_id: str,
    declared_source_sha256: str,
    source_pages: list[int] | None = None,
    options: ContentParseOptions | None = None,
    artifact=None, original_observation=None, observation_identity=None, observation_bytes=None,
):
    from app.adapters.native_config import CONFIGURATIONS
    if native.get("pipeline") not in CONFIGURATIONS:
        raise ValueError("this development entry accepts declared source-free native configurations only")
    pipeline = native["pipeline"]
    if source_pages is not None and (
        len(source_pages) != source.page_count
        or any(type(p) is not int or p < 1 for p in source_pages)
        or len(set(source_pages)) != len(source_pages)
    ):
        raise ValueError("declared original source pages must uniquely map the input")
    options = options or ContentParseOptions()
    result, bridge = replay_native(
        native, source, options, document_id=sample_id, include_source_markers=True,
        artifact=artifact, original_observation=original_observation, observation_identity=observation_identity,
        observation_bytes=observation_bytes, source_pages=source_pages
    )
    for page in bridge["pages"]:
        number = page["raw_page"]
        original = source_pages[number - 1] if source_pages is not None else None
        page["original_pdf_page"] = original
        for block in result._native_page_blocks[number]:
            block["original_pdf_page"] = original if block.get("page") is not None else None
            block["page_processing"] = page.get("frozen_page_processing")
    result._source_verification["saved_native_bridge"] = bridge
    snapshots = []

    def capture(name, *, pages_only=False, applicability=None):
        snapshots.append(
            capture_stage(
                result,
                stage=name,
                sample_id=sample_id,
                pipeline=pipeline,
                pages_only=pages_only,
                applicability=applicability,
            )
        )

    capture("adapted", pages_only=True)
    await apply_source_stages(
        result,
        bridge,
        source,
        options,
        None,
        allow_source_reads=False,
        on_stage=lambda name, detail: capture(name, pages_only=True, applicability=detail),
    )
    await SavedContentService().finalize(
        result,
        source,
        options,
        declared_source_sha256=declared_source_sha256,
        on_stage=lambda name: capture(
            name,
            applicability=(
                {"applicable": True, "reason": "saved_media_delivery_status_only_no_media_io"}
                if name == "assets"
                else None
            ),
        ),
    )
    from app.services.native_content_evidence import validate_native_content
    validate_native_content(result)
    ledger = stage_edit_ledger(snapshots)
    if any(e["producer_edits"]["status"] in {"conflict", "unsupported", "unavailable"} for e in ledger):
        raise ValueError("actual stage edits failed exact replay")
    observed = build_service_observation(
        result, sample_id=sample_id, pipeline=pipeline + "+MO-Parse", provenance_pages=source_pages
    )
    readback = format_readback_checks(native, result)
    if any(check["equal"] is False for check in readback):
        raise ValueError("saved adapter changed a present native source field")
    evidence = {
        "purpose": "single_document_saved_native_format_and_service_conversion_validation",
        "sample_id": sample_id,
        "pipeline": pipeline,
        "formal_quality_evaluation": False,
        "expected_access": False,
        "source_byte_access": False,
        "media_byte_access": False,
        "model_calls": 0,
        "network_calls": 0,
        "bridge": bridge,
        "classification_counts": dict(
            Counter(b["type"] for blocks in result._native_page_blocks.values() for b in blocks)
        ),
        "semantic_tables": [asdict(v) for v in result._semantic_tables],
        "table_fragments": [asdict(f) for f in result._table_fragments],
        "native_blocks": result._native_page_blocks,
        "final_text_evidence": result._final_text_evidence,
        "stages": [materialize_stage(s) for s in snapshots],
        "stage_edit_ledger": ledger,
        "observation": observed,
        "status": result.parse_result.status,
        "warnings": [w.model_dump(mode="json") for w in result.warnings],
        "content_dispositions": content_dispositions(result, observed),
        "format_readback_checks": readback,
    }
    from .saved_content_coverage import native_destinations
    evidence["contract"] = result._native_content.audit()
    evidence["states"] = result._source_verification["native_content"]
    evidence["ir_handoff"] = result._source_verification["native_ir_handoff"]
    evidence["relation_checks"] = result._source_verification.get("native_relation_checks", [])
    evidence["native_destinations"] = native_destinations(result, evidence["content_dispositions"])
    return result, evidence


def main() -> int:
    """Write one development result; never activate a formal service index."""
    import argparse
    import asyncio
    import hashlib
    import json
    import os
    import resource
    import sys
    from types import SimpleNamespace

    from app.models.native_content import NativeArtifact
    from app.services.storage_service import StorageService

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--observation", required=True, type=Path)
    parser.add_argument("--source-metadata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("use a new development output directory")
    if any(p.suffix != ".json" for p in (args.native, args.observation, args.source_metadata)):
        parser.error("only saved JSON and declared JSON metadata are accepted")
    violations = []

    def boundary(event, values):
        if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(values[0]))
            if path.suffix.lower() in {
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
            } or {"expected", "references", "reference-decisions"}.intersection(path.parts):
                violations.append({"event": event, "path": str(path)})
                raise RuntimeError("saved-content development entry forbids source/media/reference I/O")
        if event in {"socket.connect", "socket.bind", "socket.sendto"}:
            violations.append({"event": event})
            raise RuntimeError("saved-content development entry forbids network I/O")

    sys.addaudithook(boundary)
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    available = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, available[:8])
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    received = args.native.read_bytes()
    native = json.loads(received)
    observed_bytes = args.observation.read_bytes()
    original_observation = json.loads(observed_bytes)
    metadata_bytes = args.source_metadata.read_bytes()
    meta = json.loads(metadata_bytes)
    source = StoredSource(
        path=Path("/not-mounted") / meta["filename"],
        filename=meta["filename"],
        mime_type="application/pdf",
        size_bytes=meta["size_bytes"],
        page_count=len(meta["source_pages"]),
    )

    async def run():
        from .cli import code_identity

        identity = code_identity()
        import time
        started = time.monotonic()
        result, evidence = await close_saved_document(
            native,
            source,
            sample_id=meta["sample_id"],
            declared_source_sha256=meta["sha256"],
            source_pages=meta["source_pages"],
            artifact=NativeArtifact(str(args.native), received),
            original_observation=original_observation, observation_identity=str(args.observation),
            observation_bytes=observed_bytes,
        )
        evidence["development_conversion_seconds"] = time.monotonic() - started
        if code_identity()["software_id"] != identity["software_id"]:
            raise ValueError("software changed during saved native validation")
        evidence["software"] = identity
        args.output.mkdir(parents=True, exist_ok=False)
        storage = StorageService(SimpleNamespace(data_dir=args.output / "persistence"))
        stored = await storage.write_result(result.document_id, result)
        actual = evidence["stages"][-1]["markdown"]
        final_bytes = actual.encode('utf-8')
        if (result.parse_result is None or result.markdown.encode('utf-8') != final_bytes
                or result.parse_result.renderings.markdown.encode('utf-8') != final_bytes
                or stored.result.read_bytes() != final_bytes):
            raise ValueError("actual final stage, online rendering and persisted text differ")
        # This is the newly emitted final stage, never a historical final.md.
        (args.output / "final.md").write_text(actual, encoding="utf-8")
        unchanged = args.native.read_bytes() == received and args.observation.read_bytes() == observed_bytes
        evidence.update(
            native_input=str(args.native),
            observation_input=str(args.observation),
            observation_sha256=hashlib.sha256(observed_bytes).hexdigest(),
            source_metadata=meta,
            source_metadata_input=str(args.source_metadata),
            source_metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(),
            native_sha256=hashlib.sha256(received).hexdigest(),
            final_sha256=hashlib.sha256(actual.encode()).hexdigest(),
            native_unchanged=unchanged,
            persisted_equals_final=True,
            final_byte_equality={'encoding': 'utf-8', 'final_snapshot': True,
                'result_markdown': True, 'parse_result_renderings': True, 'storage_result': True},
            boundary_violations=violations,
            execution_resources={
                "purpose": "serial_development_validation_not_performance_measurement",
                "cpu_affinity": sorted(os.sched_getaffinity(0)),
                "address_space_limit_bytes": 8 * 1024**3,
                "outer_concurrency": 1,
                "gpu_visibility": "disabled",
                "network": "audit_hook_rejects_socket_operations",
            },
        )
        (args.output / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "status": evidence["status"],
                    "native_unchanged": unchanged,
                    "boundary_violations": violations,
                    "classification_counts": evidence["classification_counts"],
                    "warnings": dict(Counter(w.code for w in result.warnings)),
                },
                ensure_ascii=False,
            )
        )
        return 0 if unchanged and not violations else 1

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
