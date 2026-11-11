"""Capture actually emitted candidate stages without PDFs, references or inference."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from difflib import SequenceMatcher
from typing import Any

from app.models.parse_result import DocumentParseResult
from app.services.export_service import ExportService

from .service_observation import build_service_observation

STAGE_CAPTURE_VERSION = "mo-parse-service-stage-capture-1"


def capture_stage(
    result: DocumentParseResult,
    *,
    stage: str,
    sample_id: str,
    pages_only: bool = False,
    pipeline: str = "P07",
    applicability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project a stage's visible output now, before mutable service work continues.

    Before document assembly, the normal page exporter supplies a diagnostic
    concatenation. It does not merge tables, reorder pages or change the live
    result. Later stages use their actual document rendering. Hidden IR blocks
    never become candidate text merely because a snapshot is being captured.
    """
    observed = result.model_copy(deep=False)
    if pages_only:
        observed.markdown, observed.plain_text = ExportService().join_pages(
            result.pages, preserve_page_breaks=True, source_regions=result._source_regions,
        )
        observed._table_views = []
        observed._semantic_tables = []
        observed.parse_result = None
    elif result.parse_result is not None:
        observed.markdown = result.parse_result.renderings.markdown
        observed.plain_text = result.parse_result.renderings.plain_text
    # Freeze only the evidence needed by final-output readback. Candidate text
    # and these source-owned tables must not observe later in-place mutations.
    saved: dict[str, Any] = copy.deepcopy({
        "fragments": observed._table_fragments,
        "views": observed._table_views,
        "semantics": observed._semantic_tables,
    })
    observed._table_fragments = saved["fragments"]
    observed._table_views = saved["views"]
    observed._semantic_tables = saved["semantics"]
    observed._native_page_blocks = copy.deepcopy(result._native_page_blocks)
    observed._source_verification = copy.deepcopy(result._source_verification)
    observed._page_furniture = copy.deepcopy(result._page_furniture)
    observed._source_regions = copy.deepcopy(result._source_regions)
    observed._picture_candidates = copy.deepcopy(result._picture_candidates)
    observed._final_text_evidence = copy.deepcopy(result._final_text_evidence)
    observed.pages = [page.model_copy(deep=True) for page in result.pages]
    observed.warnings = copy.deepcopy(result.warnings)
    if observed.parse_result is not None:
        observed.parse_result = observed.parse_result.model_copy(deep=True)
    return {
        "schema": STAGE_CAPTURE_VERSION,
        "stage": stage,
        "scope": ("actual_adapter_page_rendering" if stage == "adapted" else "diagnostic_page_export")
                 if pages_only else "actual_document_rendering",
        "markdown": observed.markdown,
        "candidate": observed,
        "sample_id": sample_id,
        "pipeline": pipeline,
        "applicability": copy.deepcopy(applicability or {"applicable": True, "reason": "actual_emitted_stage"}),
    }


def _json_value(value: Any) -> Any:
    """Copy captured structures only; unsupported objects remain explicit."""
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        if len({str(key) for key in value}) != len(value):
            return {"unsupported_serialization": "colliding_json_keys"}
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(child) for child in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return {"unsupported_serialization": type(value).__module__ + "." + type(value).__qualname__}


def _pointer(parent: str, token: Any) -> str:
    return parent + "/" + str(token).replace("~", "~0").replace("/", "~1")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _stage_audit(snapshot):
    if "_object_audit" not in snapshot:
        if "candidate" not in snapshot:
            snapshot["_object_audit"] = _json_value(snapshot.get("source_audit", {}))
        else:
            observed = snapshot["candidate"]
            snapshot["_object_audit"] = _json_value({
                "capture_identity": {key: snapshot.get(key) for key in ("sample_id", "pipeline")},
                "native_blocks": observed._native_page_blocks,
                "table_fragments": observed._table_fragments,
                "table_views": observed._table_views,
                "semantic_tables": observed._semantic_tables,
                "source_regions": observed._source_regions,
                "page_furniture": observed._page_furniture,
                "picture_candidates": observed._picture_candidates,
                "source_verification": observed._source_verification,
                "final_text_evidence": observed._final_text_evidence,
                "pages": observed.pages,
                "parse_result": observed.parse_result,
            })
    return snapshot["_object_audit"]


def _object_inventory(snapshot):
    """Index actual objects; identity never comes from similar output text."""
    if "_object_inventory" in snapshot:
        return snapshot["_object_inventory"]
    audit = _stage_audit(snapshot)
    objects = []
    stored_identity = audit.get("capture_identity", {})
    namespace = {key: snapshot.get(key) or (stored_identity.get(key) if isinstance(stored_identity, dict) else None)
                 for key in ("sample_id", "pipeline")}
    namespace_known = all(isinstance(value, str) and value for value in namespace.values())
    fragments = defaultdict(list)
    raw_fragments = audit.get("table_fragments", [])
    for index, fragment in enumerate(raw_fragments if isinstance(raw_fragments, list) else []):
        if isinstance(fragment, dict):
            identifier = fragment.get("fragment_id")
            if isinstance(identifier, str):
                fragments[identifier].append((index, fragment))

    def fragment_refs(identifier, *, row=None, column=None):
        found = fragments.get(identifier, []) if isinstance(identifier, str) else []
        if len(found) != 1:
            return [], ["source_fragment_missing_or_ambiguous"]
        index, fragment = found[0]
        native_evidence = fragment.get("native_evidence")
        native = native_evidence.get("native_path") if isinstance(native_evidence, dict) else None
        if not isinstance(native, str) or not native:
            return [], ["source_fragment_native_path_unknown"]
        if type(fragment.get("page_number")) is not int or fragment["page_number"] < 1:
            return [], ["source_fragment_page_unknown"]
        reference = {"native_path": native, "fragment_id": identifier, "page": fragment.get("page_number"),
                     "evidence_pointer": f"#/table_fragments/{index}/native_evidence/native_path"}
        cells = fragment.get("cells", [])
        if not isinstance(cells, list):
            return [], ["source_cells_not_a_list"]
        if row is not None or column is not None:
            if type(row) is not int or type(column) is not int or row < 0 or column < 0:
                return [], ["source_cell_position_unknown"]
            matches = [cell for cell in cells if isinstance(cell, dict)
                       and type(cell.get("row")) is int and type(cell.get("column")) is int
                       and cell["row"] == row and cell["column"] == column]
            if len(matches) != 1:
                return [], ["source_cell_unavailable" if not matches else "source_cell_position_ambiguous"]
            return [{**reference, "row": row, "column": column}], []
        if cells:
            valid = [cell for cell in cells if isinstance(cell, dict) and type(cell.get("row")) is int
                     and type(cell.get("column")) is int and cell["row"] >= 0 and cell["column"] >= 0]
            issues = [] if len(valid) == len(cells) else ["source_cell_position_unknown"]
            if len({(cell["row"], cell["column"]) for cell in valid}) != len(valid):
                issues.append("source_cell_position_ambiguous")
            return [{**reference, "row": cell["row"], "column": cell["column"]} for cell in valid], issues
        return [reference], []

    def anchors(refs):
        return sorted({_digest({key: ref[key] for key in ("native_path", "row", "column", "asset_id", "asset_sha256", "source_ref", "page")
                                if key in ref}) for ref in refs})

    def add(family, payload, pointer, *, identity=None, refs=(), issues=(), visibility="audit_only", supported=True):
        own = payload if isinstance(payload, dict) else {}
        unsupported = any("unsupported_serialization" in part for part in _walk(payload))
        spans = []
        declared = own.get("final_markdown_span")
        text = own.get("service_rendered", own.get("rendered"))
        if isinstance(declared, list) and len(declared) == 2 and all(type(n) is int for n in declared):
            a, b = declared
            if isinstance(text, str) and 0 <= a <= b <= len(snapshot["markdown"]) and snapshot["markdown"][a:b] == text:
                spans = [{"span": [a, b], "basis": "captured_producer_span"}]
        elif isinstance(text, str) and text and snapshot["markdown"].count(text) == 1:
            start = snapshot["markdown"].index(text)
            spans = [{"span": [start, start + len(text)], "basis": "unique_exact_owned_rendering"}]
        status = own.get("status", own.get("quality", "unknown"))
        if own.get("read_error") or own.get("read_errors"):
            status = "failed"
        ref = {"stage": snapshot["stage"], "artifact": "stage_source_audit", "pointer": pointer,
               "sha256": None if unsupported else _digest(payload)}
        issues = [*issues, *([] if namespace_known else ["capture_namespace_unknown"])]
        objects.append({"ref": ref, "family": family, "identity": identity, "payload": payload,
            "source_refs": list(refs), "anchors": anchors(refs), "source_status": "unsupported" if unsupported or not supported else
            "unknown" if issues or not refs else "known", "source_issues": list(issues),
            "rendering_spans": spans, "rendering_status": "located" if spans else "unknown",
            "visibility": visibility, "execution_status": {"state": str(status), "basis": "captured_object_status" if status != "unknown" else "unrecorded"}})

    def items(value, pointer, family):
        if isinstance(value, list):
            return enumerate(value)
        add(family, value, pointer, issues=["captured_collection_not_a_list"], supported=False)
        return []

    native_pages = audit.get("native_blocks", {})
    if not isinstance(native_pages, dict):
        add("native_page_collection", native_pages, "#/native_blocks", issues=["captured_pages_not_a_mapping"], supported=False)
    for page, blocks in native_pages.items() if isinstance(native_pages, dict) else []:
        page_known = isinstance(page, str) and re.fullmatch(r"[1-9][0-9]*", page) is not None
        for index, block in items(blocks, _pointer("#/native_blocks", page), "native_block_collection"):
            pointer = _pointer(_pointer("#/native_blocks", page), index)
            if not isinstance(block, dict):
                add("native_block", block, pointer, issues=["captured_block_not_an_object"], supported=False)
                continue
            native = block.get("native_path")
            refs = [{"native_path": native, "page": page, "evidence_pointer": pointer + "/native_path"}] if page_known and isinstance(native, str) and native else []
            add("native_block", block, pointer, identity=native, refs=refs,
                issues=[] if page_known else ["native_page_identity_unknown"])
            for cell_index, cell in items(block.get("cells", []), pointer + "/cells", "native_cell_collection"):
                if not isinstance(cell, dict):
                    add("native_cell", cell, pointer + f"/cells/{cell_index}", issues=["captured_cell_not_an_object"], supported=False)
                    continue
                cell_refs = [{**ref, "row": cell.get("row"), "column": cell.get("col", cell.get("column"))} for ref in refs]
                if any(type(ref[key]) is not int or ref[key] < 0 for ref in cell_refs for key in ("row", "column")):
                    cell_refs = []
                add("native_cell", cell, pointer + f"/cells/{cell_index}", refs=cell_refs)
    for index, fragment in items(raw_fragments, "#/table_fragments", "table_fragment_collection"):
        if not isinstance(fragment, dict):
            add("table_fragment", fragment, f"#/table_fragments/{index}", issues=["captured_fragment_not_an_object"], supported=False)
            continue
        refs, issues = fragment_refs(fragment.get("fragment_id"))
        add("table_fragment", fragment, f"#/table_fragments/{index}", identity=fragment.get("fragment_id"), refs=refs, issues=issues)
        for cell_index, cell in items(fragment.get("cells", []), f"#/table_fragments/{index}/cells", "fragment_cell_collection"):
            if not isinstance(cell, dict):
                add("fragment_cell", cell, f"#/table_fragments/{index}/cells/{cell_index}", issues=["captured_cell_not_an_object"], supported=False)
                continue
            refs, issues = fragment_refs(fragment.get("fragment_id"), row=cell.get("row"), column=cell.get("column"))
            add("fragment_cell", cell, f"#/table_fragments/{index}/cells/{cell_index}", refs=refs, issues=issues)
    for family, collection in (("table_view", "table_views"), ("semantic_view", "semantic_tables")):
        for index, view in items(audit.get(collection, []), f"#/{collection}", family + "_collection"):
            if not isinstance(view, dict):
                add(family, view, f"#/{collection}/{index}", issues=["captured_view_not_an_object"], supported=False)
                continue
            refs, issues = [], []
            cell_refs = [part for part in _walk(view) if "table_id" in part and "row" in part and "column" in part]
            if any("table_id" in part and "block_id" in part and "start" in part and "end" in part for part in _walk(view)):
                issues.append("captured_text_reference_binding_unsupported")
            if family == "semantic_view":
                identifiers = view.get("source_tables", [])
            else:
                raw = view.get("fragments", [])
                identifiers = [part.get("fragment_id") for part in raw if isinstance(part, dict)] if isinstance(raw, list) else None
                if not isinstance(raw, list) or len(identifiers) != len(raw):
                    issues.append("captured_view_fragments_unsupported")
            if not isinstance(identifiers, list):
                identifiers = []
                issues.append("captured_source_tables_unsupported")
            declared_refs = []
            for identifier in identifiers:
                own, unknown = fragment_refs(identifier)
                declared_refs.extend(own)
                issues.extend(unknown)
            for cell in cell_refs:
                if cell["table_id"] not in identifiers:
                    issues.append("source_cell_table_not_declared_by_view")
                own, unknown = fragment_refs(cell["table_id"], row=cell["row"], column=cell["column"])
                refs.extend(own)
                issues.extend(unknown)
            if not cell_refs:
                refs.extend(declared_refs)
            add(family, view, f"#/{collection}/{index}", identity=view.get("view_id"), refs=refs, issues=issues)
    for collection, family in (("source_regions", "source_region"), ("page_furniture", "page_furniture"),
                               ("picture_candidates", "picture_candidate")):
        for index, item in items(audit.get(collection, []), f"#/{collection}", family + "_collection"):
            if not isinstance(item, dict):
                add(family, item, f"#/{collection}/{index}", issues=["captured_object_not_a_mapping"], supported=False)
                continue
            source_ref = item.get("source_ref", item.get("source_page_ref", item.get("source_region_ref")))
            page_known = type(item.get("page_number")) is int and item["page_number"] > 0
            refs = [{"source_ref": source_ref, "page": item.get("page_number"),
                     "evidence_pointer": f"#/{collection}/{index}"}] if page_known and isinstance(source_ref, str) and source_ref else []
            add(family, item, f"#/{collection}/{index}", identity=source_ref, refs=refs,
                issues=[] if page_known else ["source_page_identity_unknown"])
    parsed = audit.get("parse_result") or {}
    if not isinstance(parsed, dict):
        add("ir_document", parsed, "#/parse_result", issues=["captured_document_not_an_object"], supported=False)
        parsed = {}
    for index, asset in items(parsed.get("assets", []), "#/parse_result/assets", "asset_collection"):
        pointer = f"#/parse_result/assets/{index}"
        valid = (isinstance(asset, dict) and isinstance(asset.get("asset_id"), str) and bool(asset["asset_id"])
                 and isinstance(asset.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]) is not None)
        refs = [{"asset_id": asset["asset_id"], "asset_sha256": asset["sha256"], "evidence_pointer": pointer}] if valid else []
        add("asset", asset, pointer, identity=asset.get("asset_id") if isinstance(asset, dict) else None, refs=refs,
            visibility="captured_asset_descriptor_not_file_verification", supported=valid,
            issues=[] if valid else ["captured_asset_identity_or_digest_unknown"])
    for index, table in items(parsed.get("tables", []), "#/parse_result/tables", "ir_table_collection"):
        if not isinstance(table, dict):
            add("ir_table", table, f"#/parse_result/tables/{index}", issues=["captured_table_not_an_object"], supported=False)
            continue
        refs, issues = fragment_refs(table.get("table_id"))
        add("ir_table", table, f"#/parse_result/tables/{index}", identity=table.get("table_id"), refs=refs, issues=issues)
    for unit_index, unit in items(parsed.get("units", []), "#/parse_result/units", "ir_unit_collection"):
        pointer = f"#/parse_result/units/{unit_index}"
        if not isinstance(unit, dict):
            add("ir_unit", unit, pointer, issues=["captured_unit_not_an_object"], supported=False)
            continue
        for block_index, block in items(unit.get("blocks", []), pointer + "/blocks", "ir_block_collection"):
            add("ir_block", block, pointer + f"/blocks/{block_index}",
                identity=block.get("block_id") if isinstance(block, dict) else None,
                supported=isinstance(block, dict), issues=[] if isinstance(block, dict) else ["captured_block_not_an_object"])
    snapshot["_object_inventory"] = {"objects": objects,
        "correspondence_policy": "declared_source_identity_only_no_text_matching",
        "delivery_policy": "audit_retention_is_not_final_delivery_or_quality_acceptance"}
    return snapshot["_object_inventory"]


def materialize_stage(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Read a frozen candidate stage after the primary processing timer stops."""
    observed = snapshot["candidate"]
    audit = _stage_audit(snapshot)
    inventory = _object_inventory(snapshot)
    observation = build_service_observation(
        observed, sample_id=snapshot["sample_id"], pipeline=f"{snapshot['pipeline']}+MO-Parse:{snapshot['stage']}",
    )
    return {key: snapshot[key] for key in ("schema", "stage", "scope", "markdown", "applicability")} | {
        "sample_id": snapshot.get("sample_id"), "pipeline": snapshot.get("pipeline"),
        "observation": observation,
        "source_audit": {**audit, "object_inventory": {**inventory, "objects": [
            {key: value for key, value in item.items() if key not in {"payload", "anchors"}}
            for item in inventory["objects"]]}},
    }


def _object_changes(before, after, *, namespace_known):
    inputs, outputs = _object_inventory(before)["objects"], _object_inventory(after)["objects"]
    remaining_in, remaining_out = set(range(len(inputs))), set(range(len(outputs)))
    changes = []

    def record(old, new, operation, proof):
        old_objects, new_objects = [inputs[index] for index in old], [outputs[index] for index in new]
        changed = len(old_objects) != 1 or len(new_objects) != 1 or old_objects[0]["ref"]["sha256"] != new_objects[0]["ref"]["sha256"]
        deleted = []
        text_status = "unknown"
        if len(old_objects) == len(new_objects) == 1 and old_objects[0]["rendering_spans"] and new_objects[0]["rendering_spans"]:
            a, b = old_objects[0]["rendering_spans"][0]["span"]
            c, d = new_objects[0]["rendering_spans"][0]["span"]
            prior, current = before["markdown"][a:b], after["markdown"][c:d]
            deleted = [prior[i:j] for tag, i, j, _k, _stop in SequenceMatcher(None, prior, current, autojunk=False).get_opcodes()
                       if tag in {"delete", "replace"}]
            text_status = "compared_source_bound_owned_renderings"
        changes.append({"stage": after["stage"], "operation": operation,
            "input_objects": [copy.deepcopy(item["ref"]) for item in old_objects],
            "output_objects": [copy.deepcopy(item["ref"]) for item in new_objects],
            "family": (old_objects or new_objects)[0]["family"],
            "reason": {"status": "unrecorded", "codes": []},
            "provenance": {"status": proof, "input": [copy.deepcopy(item["source_refs"]) for item in old_objects],
                           "output": [copy.deepcopy(item["source_refs"]) for item in new_objects],
                           "issues": [issue for item in [*old_objects, *new_objects] for issue in item["source_issues"]]
                           + ([] if namespace_known else ["capture_namespace_unknown"])},
            "before_spans": [{"object": copy.deepcopy(item["ref"]), "spans": copy.deepcopy(item["rendering_spans"]),
                              "status": item["rendering_status"]} for item in old_objects],
            "after_spans": [{"object": copy.deepcopy(item["ref"]), "spans": copy.deepcopy(item["rendering_spans"]),
                             "status": item["rendering_status"]} for item in new_objects],
            "deleted_content": deleted, "text_change_status": text_status,
            "deleted_structure": [copy.deepcopy(item["payload"]) for item in old_objects] if changed else [],
            "added_structure": [copy.deepcopy(item["payload"]) for item in new_objects] if changed else [],
            "execution_status": {"input": [copy.deepcopy(item["execution_status"]) for item in old_objects],
                                 "output": [copy.deepcopy(item["execution_status"]) for item in new_objects],
                                 "observation": "captured_objects_only"},
            "delivery_judgment": "unjudged_audit_objects_do_not_prove_final_delivery"})
        remaining_in.difference_update(old)
        remaining_out.difference_update(new)

    indexes = []
    for collection in (inputs, outputs):
        index = defaultdict(list)
        for position, item in enumerate(collection):
            if namespace_known and item["source_status"] == "known":
                index[(item["family"], str(item["identity"]), tuple(item["anchors"]))].append(position)
        indexes.append(index)
    for key, old in indexes[0].items():
        new = indexes[1].get(key, [])
        if len(old) == len(new) == 1:
            first, second = inputs[old[0]], outputs[new[0]]
            operation = "modified" if first["ref"]["sha256"] != second["ref"]["sha256"] else (
                "reordered" if first["ref"]["pointer"] != second["ref"]["pointer"] else "retained")
            record(old, new, operation, "unique_declared_identity_and_sources")

    # A changed grouping is established only by an exact partition of existing
    # source references. Content similarity never creates an edge. Ambiguous
    # overlaps and many-to-many changes stay unmatched.
    while True:
        eligible = [index for index in sorted(remaining_in) if namespace_known and inputs[index]["source_status"] == "known"]
        if not eligible:
            break
        start = eligible[0]
        old, new = {start}, set()
        changed = True
        while changed:
            changed = False
            for index in sorted(remaining_out - new):
                item = outputs[index]
                if item["source_status"] == "known" and any(item["family"] == inputs[prior]["family"]
                        and set(item["anchors"]) & set(inputs[prior]["anchors"]) for prior in old):
                    new.add(index)
                    changed = True
            for index in sorted(remaining_in - old):
                item = inputs[index]
                if item["source_status"] == "known" and any(item["family"] == outputs[current]["family"]
                        and set(item["anchors"]) & set(outputs[current]["anchors"]) for current in new):
                    old.add(index)
                    changed = True
        old_sets, new_sets = [set(inputs[index]["anchors"]) for index in old], [set(outputs[index]["anchors"]) for index in new]
        exact = bool(new_sets) and set.union(*old_sets) == set.union(*new_sets)
        partition = (sum(map(len, old_sets)) == len(set.union(*old_sets))
                     and bool(new_sets) and sum(map(len, new_sets)) == len(set.union(*new_sets)))
        if exact and partition and (len(old) == 1 or len(new) == 1):
            operation = "split" if len(new) > 1 else "merge" if len(old) > 1 else "modified"
            record(sorted(old), sorted(new), operation, "exact_declared_source_reference_partition")
        else:
            for index in sorted(old):
                record([index], [], "unmatched_input", "ambiguous" if new else "unmatched")
            for index in sorted(new):
                record([], [index], "unmatched_output", "ambiguous")
    for index in sorted(remaining_in):
        record([index], [], "unmatched_input", inputs[index]["source_status"] if namespace_known else "unknown")
    for index in sorted(remaining_out):
        record([], [index], "unmatched_output", outputs[index]["source_status"] if namespace_known else "unknown")
    return changes


def _producer_edits(before, after):
    """Use recorded reasons only after exact literal text/span mapping replays."""
    from app.services.final_content_service import apply_text_edits, map_text_offset

    semantic = _stage_audit(after).get("source_verification", {}).get("saved_" + after.get("stage", "") + "_edits", {})
    if after.get("stage") in {"semantic", "exported"} and semantic.get("input") == before["markdown"]:
        edits = sorted(semantic.get("edits", []), key=lambda e: e["before_span"])
        parts, cursor, operations = [], 0, []
        for edit in edits:
            a, b = edit["before_span"]
            c, d = edit["after_span"]
            if (not cursor <= a <= b <= len(before["markdown"])
                    or before["markdown"][a:b] != edit["before"]
                    or after["markdown"][c:d] != edit["after"]):
                return {"status": "conflict", "operations": []}
            parts.extend((before["markdown"][cursor:a], edit["after"]))
            cursor = b
            operations.append({**copy.deepcopy(edit), "stage": after["stage"],
                               "source_status": "known" if edit["source_refs"] else "internal_control",
                               "execution_status": "exact_producer_edit_replayed"})
        parts.append(before["markdown"][cursor:])
        if "".join(parts) != after["markdown"] or semantic.get("output") != after["markdown"]:
            return {"status": "conflict", "operations": []}
        return {"status": "verified", "operations": operations}

    if before["markdown"] == after["markdown"] and not _stage_audit(after).get("final_text_evidence"):
        applicability = after.get("applicability", {})
        return {"status": "not_applicable" if applicability.get("applicable") is False else "verified_no_text_change",
                "reason": applicability.get("reason", "actual_stage_emitted_same_text"), "operations": []}

    evidence = _stage_audit(after).get("final_text_evidence", {})
    if not isinstance(evidence, dict):
        return {"status": "unsupported", "operations": []}
    edits = evidence.get("edits")
    if not isinstance(edits, list) or evidence.get("assembly_markdown") != before["markdown"]:
        return {"status": "unavailable", "operations": []}
    try:
        if apply_text_edits(before["markdown"], edits) != after["markdown"]:
            return {"status": "conflict", "operations": []}
    except (ValueError, KeyError, TypeError):
        return {"status": "unsupported", "operations": []}
    operations = []
    for index, edit in enumerate(edits):
        a, b = edit["start"], edit["end"]
        c, d = map_text_offset(a, edits), map_text_offset(b, edits, end=True)
        operations.append({"stage": after["stage"], "operation": "producer_text_edit",
            "input_objects": [{"stage": before["stage"], "artifact": "stage_markdown", "pointer": "#",
                               "sha256": hashlib.sha256(before["markdown"].encode()).hexdigest()}],
            "output_objects": [{"stage": after["stage"], "artifact": "stage_markdown", "pointer": "#",
                                "sha256": hashlib.sha256(after["markdown"].encode()).hexdigest()}],
            "before_span": [a, b], "after_span": [c, d],
            "deleted_content": before["markdown"][a:b], "inserted_content": after["markdown"][c:d],
            "added_structure": [], "source_refs": edit.get("source_refs", []),
            "source_status": "known" if edit.get("source_refs") else "internal_control" if edit.get("reason") in {"internal_marker", "physical_page_control", "internal_layout_spacing"} else "unknown",
            "producer_evidence": {"stage": after["stage"], "artifact": "stage_source_audit",
                                  "pointer": f"#/final_text_evidence/edits/{index}", "sha256": _digest(edit)},
            "reason": {"status": "recorded" if isinstance(edit.get("reason"), str) and edit["reason"] else "unrecorded",
                       "code": edit.get("reason")},
            "execution_status": "exact_producer_edit_replayed"})
    return {"status": "verified", "operations": operations}


def stage_edit_ledger(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain string edits and independently bound captured-object changes."""
    ledger = []
    for before, after in zip(snapshots, snapshots[1:], strict=False):
        identities = []
        for snapshot in (before, after):
            stored = _stage_audit(snapshot).get("capture_identity", {})
            for key in ("sample_id", "pipeline"):
                if (snapshot.get(key) is not None and isinstance(stored, dict) and stored.get(key) is not None
                        and snapshot[key] != stored[key]):
                    raise ValueError("stage capture namespace differs from its audit: " + key)
            identities.append({key: snapshot.get(key) or (stored.get(key) if isinstance(stored, dict) else None)
                               for key in ("sample_id", "pipeline")})
        for key in ("sample_id", "pipeline"):
            if identities[0][key] is not None and identities[1][key] is not None and identities[0][key] != identities[1][key]:
                raise ValueError("stage capture namespace differs: " + key)
        namespace_known = all(isinstance(identity[key], str) and identity[key] for identity in identities for key in ("sample_id", "pipeline"))
        edits = []
        prior, current = before["markdown"].splitlines(keepends=True), after["markdown"].splitlines(keepends=True)
        prior_offsets, current_offsets = [0], [0]
        for line in prior:
            prior_offsets.append(prior_offsets[-1] + len(line))
        for line in current:
            current_offsets.append(current_offsets[-1] + len(line))
        for operation, i, j, k, stop in SequenceMatcher(None, prior, current, autojunk=False).get_opcodes():
            if operation != "equal":
                a, b, c, d = prior_offsets[i], prior_offsets[j], current_offsets[k], current_offsets[stop]
                edits.append({"operation": operation, "before_span": [a, b], "after_span": [c, d],
                              "before": before["markdown"][a:b], "after": after["markdown"][c:d]})
        ledger.append({"from_stage": before["stage"], "to_stage": after["stage"],
                       "from_scope": before["scope"], "to_scope": after["scope"],
                       "applicability": copy.deepcopy(after["applicability"]), "edits": edits,
                       "capture_identity": {"input": identities[0], "output": identities[1],
                                            "status": "known" if namespace_known else "unknown"},
                       "object_changes": _object_changes(before, after, namespace_known=namespace_known),
                       "producer_edits": _producer_edits(before, after),
                       "judgment": "unjudged_actual_string_changes"})
    return ledger
