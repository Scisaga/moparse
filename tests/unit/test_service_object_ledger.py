"""Independent captured-object lineage oracles; no files or parsers are read."""

import hashlib
import json
from copy import deepcopy

import pytest

from app.models.content_result import ContentParseResult
from app.models.parse_result import (
    DocumentParseResult,
    PageDiagnostics,
    PageParseResult,
    ParsePipeline,
)
from app.parsers.mineru_native_remote import MinerUPictureCandidate
from app.services.table_service import TableCellFragment, TableFragment, TableSourceView
from moparse_eval.service_stages import capture_stage, materialize_stage, stage_edit_ledger


def candidate(markdown="Alpha\n\nBeta", blocks=()):
    result = DocumentParseResult(document_id="invented", filename="unopened.pdf", mime_type="application/pdf",
        page_count=1, processed_pages=1, markdown=markdown,
        pages=[PageParseResult(page_number=1, content=markdown)],
        pipeline=ParsePipeline(profile="balanced", primary="invented"))
    result._native_page_blocks = {1: deepcopy(list(blocks))}
    return result


def block(path, text, **extra):
    return {"native_path": path, "kind": "paragraph", "text": text, "service_rendered": text, **extra}


def capture(result, stage):
    return capture_stage(result, stage=stage, sample_id="invented")


def changes(before, after, family="native_block"):
    [transition] = stage_edit_ledger([before, after])
    return [row for row in transition["object_changes"] if row["family"] == family]


def test_removing_one_object_does_not_pair_or_delete_its_valid_neighbor():
    first = candidate(blocks=[block("#/own/a", "Alpha"), block("#/own/b", "Beta")])
    second = candidate("Alpha", [block("#/own/a", "Alpha")])
    rows = changes(capture(first, "adapted"), capture(second, "final"))
    assert [row["operation"] for row in rows] == ["retained", "unmatched_input"]
    assert rows[0]["input_objects"][0]["pointer"] == rows[0]["output_objects"][0]["pointer"] == "#/native_blocks/1/0"
    assert rows[1]["input_objects"][0]["pointer"] == "#/native_blocks/1/1"
    assert rows[1]["output_objects"] == []
    assert rows[1]["deleted_content"] == [] and rows[1]["text_change_status"] == "unknown"
    assert rows[1]["deleted_structure"][0]["text"] == "Beta"


def test_reordering_uses_declared_native_identity_and_actual_audit_position():
    a, b = block("#/own/a", "Alpha"), block("#/own/b", "Beta")
    rows = changes(capture(candidate(blocks=[a, b]), "adapted"), capture(candidate("Beta\n\nAlpha", [b, a]), "final"))
    assert [row["operation"] for row in rows] == ["reordered", "reordered"]
    assert [(row["input_objects"][0]["pointer"], row["output_objects"][0]["pointer"]) for row in rows] == [
        ("#/native_blocks/1/0", "#/native_blocks/1/1"), ("#/native_blocks/1/1", "#/native_blocks/1/0")]
    assert all(row["deleted_content"] == [] and row["added_structure"] == [] for row in rows)
    assert all(row["reason"]["status"] == "unrecorded" for row in rows)


def test_identical_words_from_different_sources_never_establish_object_correspondence():
    rows = changes(capture(candidate("Same", [block("#/own/a", "Same")]), "adapted"),
                   capture(candidate("Same", [block("#/own/b", "Same")]), "final"))
    assert {row["operation"] for row in rows} == {"unmatched_input", "unmatched_output"}
    assert all(not (row["input_objects"] and row["output_objects"]) for row in rows)


def test_a_metadata_change_does_not_claim_the_unchanged_rendered_text_was_deleted():
    first = capture(candidate("Alpha", [block("#/own/a", "Alpha", status="ready")]), "assets")
    second = capture(candidate("Alpha", [block("#/own/a", "Alpha", status="partial")]), "final")
    [row] = changes(first, second)
    assert row["operation"] == "modified" and row["deleted_content"] == []
    assert row["execution_status"]["output"][0]["state"] == "partial"


def test_the_same_local_native_path_on_another_page_is_not_the_same_source():
    first, second = candidate("Same"), candidate("Same")
    first._native_page_blocks = {1: [block("#/blocks/0", "Same")]}
    second._native_page_blocks = {2: [block("#/blocks/0", "Same")]}
    rows = changes(capture(first, "adapted"), capture(second, "final"))
    assert {row["operation"] for row in rows} == {"unmatched_input", "unmatched_output"}


def fragment(identifier, text, native):
    return TableFragment(fragment_id=identifier, page_number=1, ordinal=1, normalized_bbox=(0, 0, 1, 1),
        num_rows=1, num_cols=1, rows=[[text]], column_boundaries=[], markdown="", rendered=text,
        cells=[TableCellFragment(0, 0, 1, 1, text)], native_evidence={"native_path": native})


@pytest.mark.parametrize("split", [False, True])
def test_merge_and_split_require_an_exact_partition_of_declared_source_cells(split):
    f1, f2 = fragment("f1", "Alpha", "#/tables/0"), fragment("f2", "Beta", "#/tables/1")
    separate, merged = candidate(), candidate()
    for result in (separate, merged):
        result._table_fragments = [f1, f2]
    separate._table_views = [TableSourceView("v1", (f1,), "Alpha"), TableSourceView("v2", (f2,), "Beta")]
    merged._table_views = [TableSourceView("v12", (f1, f2), "Alpha\n\nBeta")]
    before, after = (merged, separate) if split else (separate, merged)
    [row] = changes(capture(before, "exported"), capture(after, "semantic"), "table_view")
    assert row["operation"] == ("split" if split else "merge")
    assert (len(row["input_objects"]), len(row["output_objects"])) == ((1, 2) if split else (2, 1))
    assert row["provenance"]["status"] == "exact_declared_source_reference_partition"
    assert row["reason"] == {"status": "unrecorded", "codes": []}
    assert row["text_change_status"] == "unknown"


def test_overlapping_source_sets_do_not_authorize_a_merge():
    f1 = fragment("f1", "Alpha", "#/tables/0")
    first, second = candidate("Alpha"), candidate("Alpha")
    first._table_fragments = second._table_fragments = [f1]
    first._table_views = [TableSourceView("a", (f1,), "Alpha"), TableSourceView("b", (f1,), "Alpha")]
    second._table_views = [TableSourceView("c", (f1,), "Alpha")]
    rows = changes(capture(first, "exported"), capture(second, "semantic"), "table_view")
    assert {row["operation"] for row in rows} == {"unmatched_input", "unmatched_output"}
    assert all(row["provenance"]["status"] == "ambiguous" for row in rows)


def test_unknown_sources_and_repeated_renderings_remain_unmatched_and_unlocated():
    first, second = candidate("Same\n\nSame"), candidate("Same\n\nSame")
    first._native_page_blocks = second._native_page_blocks = {1: [{"text": "Same", "service_rendered": "Same"}]}
    rows = changes(capture(first, "adapted"), capture(second, "final"))
    assert {row["operation"] for row in rows} == {"unmatched_input", "unmatched_output"}
    assert all(row["provenance"]["status"] == "unknown" for row in rows)
    assert all(part["status"] == "unknown" for row in rows for part in row["before_spans"] + row["after_spans"])


def test_failed_media_descriptor_is_preserved_without_opening_or_accepting_the_asset():
    image = block("#/images/0", "", kind="image", status="failed", research_asset="unopened.png", read_error="decoder_failed")
    first, second = candidate("![figure](unopened.png)", [image]), candidate("![figure](unopened.png)", [image])
    before, after = capture(first, "assets"), capture(second, "final")
    [row] = changes(before, after)
    assert row["operation"] == "retained"
    assert row["execution_status"]["output"][0]["state"] == "failed"
    assert row["delivery_judgment"] == "unjudged_audit_objects_do_not_prove_final_delivery"


def resolve(document, pointer):
    value = document
    for token in pointer[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def test_every_object_reference_and_digest_resolves_to_the_actual_persistable_stage_audit():
    before = capture(candidate("Alpha", [block("#/a~b/c", "Alpha")]), "adapted")
    after = capture(candidate("Alphx", [block("#/a~b/c", "Alphx")]), "final")
    [row] = changes(before, after)
    audits = {snapshot["stage"]: json.loads(json.dumps(materialize_stage(snapshot)["source_audit"])) for snapshot in (before, after)}
    for ref in row["input_objects"] + row["output_objects"]:
        payload = resolve(audits[ref["stage"]], ref["pointer"])
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        assert ref["sha256"] == digest
    assert row["deleted_content"] == ["a"]
    assert row["added_structure"][0]["text"] == "Alphx"


def test_runtime_reason_is_consumed_only_from_an_exactly_replayed_producer_edit():
    before = capture(candidate("Alpha  Beta"), "semantic")
    result = candidate("Alpha Beta")
    result._final_text_evidence = {"assembly_markdown": "Alpha  Beta", "edits": [
        {"start": 5, "end": 7, "replacement": " ", "reason": "declared_paragraph_continuation"}]}
    [transition] = stage_edit_ledger([before, capture(result, "final")])
    assert transition["edits"], "the existing string-edit interface is retained"
    [edit] = transition["producer_edits"]["operations"]
    assert transition["producer_edits"]["status"] == "verified"
    assert edit["reason"] == {"status": "recorded", "code": "declared_paragraph_continuation"}
    assert edit["before_span"] == [5, 7] and edit["after_span"] == [5, 6]
    assert edit["source_status"] == "unknown"
    broken = capture(candidate("Unexpected"), "final")
    broken["candidate"]._final_text_evidence = result._final_text_evidence
    assert stage_edit_ledger([before, broken])[0]["producer_edits"]["status"] == "conflict"


@pytest.mark.parametrize("malformed", [None, "bad", [None, {"row": None, "text": "unknown"}]])
def test_malformed_cells_are_preserved_and_cannot_erase_valid_neighbor_objects(malformed):
    result = candidate("Alpha", [block("#/good", "Alpha"), {"native_path": "#/bad", "cells": malformed}])
    before, after = capture(result, "adapted"), capture(result, "final")
    [transition] = stage_edit_ledger([before, after])
    good = [row for row in transition["object_changes"] if row["family"] == "native_block"
            and row["input_objects"] and row["input_objects"][0]["pointer"].endswith("/0")]
    assert len(good) == 1 and good[0]["operation"] == "retained"
    assert any(row["family"] in {"native_cell", "native_cell_collection"} and row["operation"].startswith("unmatched")
               for row in transition["object_changes"])


def test_malformed_fragment_and_asset_structures_keep_original_payloads_and_valid_neighbors():
    audit = {"native_blocks": {"1": [block("#/good", "Alpha")]},
        "table_fragments": [{"fragment_id": "bad", "page_number": 1, "native_evidence": None, "cells": [None, {"row": None}]}],
        "parse_result": {"assets": [None, {"filename": "unopened.png"}, {"asset_id": "known", "sha256": "a" * 64, "status": "failed"}]}}
    snapshots = [{"stage": stage, "scope": "actual_document_rendering", "markdown": "Alpha", "sample_id": "invented", "pipeline": "P07",
                  "applicability": {"applicable": True}, "source_audit": deepcopy(audit)} for stage in ("assets", "final")]
    [transition] = stage_edit_ledger(snapshots)
    assert any(row["family"] == "native_block" and row["operation"] == "retained" for row in transition["object_changes"])
    invalid_assets = [row for row in transition["object_changes"] if row["family"] == "asset" and row["operation"] == "unmatched_input"]
    assert len(invalid_assets) == 2
    assert [row["deleted_structure"][0] for row in invalid_assets] == [None, {"filename": "unopened.png"}]
    assert all(row["provenance"]["status"] == "unsupported" for row in invalid_assets)
    assert any(row["family"] == "asset" and row["operation"] == "retained"
               and row["execution_status"]["output"][0]["state"] == "failed" for row in transition["object_changes"])


def test_capture_freezes_mutable_ir_media_native_cells_and_page_diagnostics():
    result = candidate("Alpha", [block("#/own/a", "Alpha", cells=[{"row": 0, "col": 0, "text": "17"}])])
    result.pages[0].diagnostics = PageDiagnostics(source_kind="native", logical_table_ids=["original"])
    result._picture_candidates = [MinerUPictureCandidate(1, 0, "Original caption", (0, 0, 1, 1), "saved-page", False)]
    result.parse_result = ContentParseResult.model_validate({
        "source": {"content_id": "invented", "source_sha256": "a" * 64, "filename": "unopened.pdf", "mime_type": "application/pdf",
                   "kind": "pdf", "size_bytes": 0, "unit_count": 1},
        "units": [], "assets": [{"asset_id": "asset", "kind": "image", "role": "source", "mime_type": "image/png", "sha256": "b" * 64,
            "size_bytes": 0, "filename": "unopened.png", "download_url": "/unopened.png", "warning_codes": ["original"]}],
        "renderings": {"markdown": "Alpha"},
        "runtime": {"profile": "balanced", "primary_backend": "invented", "parser_version": "invented"},
        "links": {name: "/unopened" for name in ("job", "events", "result", "assets", "bundle")}})
    snapshot = capture(result, "assets")
    result.parse_result.assets[0].warning_codes.append("later")
    result._picture_candidates[0] = MinerUPictureCandidate(1, 0, "Later caption", (0, 0, 1, 1), "saved-page", False)
    result.pages[0].diagnostics.logical_table_ids.append("later")
    result._native_page_blocks[1][0]["cells"][0]["text"] = "18"
    saved = materialize_stage(snapshot)["source_audit"]
    assert saved["parse_result"]["assets"][0]["warning_codes"] == ["original"]
    assert saved["picture_candidates"][0]["caption"] == "Original caption"
    assert saved["native_blocks"]["1"][0]["cells"][0]["text"] == "17"
    assert saved["pages"][0]["diagnostics"]["logical_table_ids"] == ["original"]


@pytest.mark.parametrize("page", ["unknown", "0", "-1", "01", "True"])
def test_invalid_native_page_identity_cannot_become_known_from_a_valid_local_path(page):
    raw = {"native_blocks": {page: [block("#/blocks/0", "Alpha")], "1": [block("#/valid", "Beta")]}}
    snapshots = [{"stage": name, "scope": "actual_document_rendering", "markdown": "Alpha\n\nBeta", "sample_id": "invented", "pipeline": "P07",
                  "applicability": {"applicable": True}, "source_audit": deepcopy(raw)} for name in ("adapted", "final")]
    [transition] = stage_edit_ledger(snapshots)
    rows = [row for row in transition["object_changes"] if row["family"] == "native_block"]
    assert len([row for row in rows if row["operation"] == "retained"]) == 1
    assert {row["operation"] for row in rows if row["provenance"]["status"] == "unknown"} == {"unmatched_input", "unmatched_output"}


@pytest.mark.parametrize("page", [None, False, 0, "1"])
def test_region_reference_without_a_valid_actual_page_is_not_a_known_source(page):
    raw = {"source_regions": [{"source_ref": "region:0", "page_number": page, "literal_text": "Alpha"}]}
    snapshots = [{"stage": name, "scope": "actual_document_rendering", "markdown": "Alpha", "sample_id": "invented", "pipeline": "P07",
                  "applicability": {"applicable": True}, "source_audit": deepcopy(raw)} for name in ("assets", "final")]
    rows = changes(*snapshots, family="source_region")
    assert {row["operation"] for row in rows} == {"unmatched_input", "unmatched_output"}
    assert all(row["provenance"]["status"] == "unknown" for row in rows)


@pytest.mark.parametrize("defect", ["undeclared_source_missing", "boolean_position", "duplicate_position"])
def test_a_partially_valid_cell_reference_cannot_hide_invalid_declared_view_sources(defect):
    cells = [{"row": 0, "column": 0, "text": "17"}]
    tables = ["f1"]
    if defect == "undeclared_source_missing":
        tables.append("missing")
    elif defect == "boolean_position":
        cells[0]["row"] = False
    else:
        cells.append({"row": 0, "column": 0, "text": "different"})
    fragment_payload = {"fragment_id": "f1", "page_number": 1, "native_evidence": {"native_path": "#/table/0"}, "cells": cells}
    view = {"view_id": "v", "source_tables": tables, "fact": {"table_id": "f1", "row": 0, "column": 0}}
    raw = {"native_blocks": {"1": [block("#/valid", "Alpha")]},
           "table_fragments": [fragment_payload], "semantic_tables": [view]}
    snapshots = [{"stage": name, "scope": "actual_document_rendering", "markdown": "Alpha", "sample_id": "invented", "pipeline": "P07",
                  "applicability": {"applicable": True}, "source_audit": deepcopy(raw)} for name in ("semantic", "final")]
    rows = changes(*snapshots, family="semantic_view")
    assert {row["operation"] for row in rows} == {"unmatched_input", "unmatched_output"}
    assert all(row["provenance"]["status"] == "unknown" for row in rows)
    assert rows[0]["deleted_structure"] == [view]
    assert any(row["operation"] == "retained" for row in changes(*snapshots))


@pytest.mark.parametrize("field,value", [("sample_id", "other-document"), ("pipeline", "P08")])
def test_equal_local_native_paths_cannot_cross_explicit_capture_namespaces(field, value):
    first = capture(candidate("Same", [block("#/blocks/0", "Same")]), "adapted")
    after = capture_stage(candidate("Same", [block("#/blocks/0", "Same")]), stage="final",
                          sample_id=value if field == "sample_id" else "invented",
                          pipeline=value if field == "pipeline" else "P07")
    with pytest.raises(ValueError, match="capture namespace"):
        stage_edit_ledger([first, after])


def test_missing_capture_namespace_remains_unknown_and_preserves_string_edits():
    raw = {"native_blocks": {"1": [block("#/blocks/0", "Same")]}}
    snapshots = [{"stage": name, "scope": "actual_document_rendering", "markdown": text,
                  "applicability": {"applicable": True}, "source_audit": deepcopy(raw)}
                 for name, text in (("adapted", "Same"), ("final", "Changed"))]
    [transition] = stage_edit_ledger(snapshots)
    assert transition["edits"] and transition["capture_identity"]["status"] == "unknown"
    assert {row["operation"] for row in transition["object_changes"]} == {"unmatched_input", "unmatched_output"}
    assert all(row["provenance"]["status"] == "unknown" for row in transition["object_changes"])
