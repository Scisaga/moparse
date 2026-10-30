"""Readback contracts using invented native structures and temporary run files."""

from __future__ import annotations

import copy
import inspect
import json
import math
from typing import Any

import pytest

from moparse_eval.native_readback import READBACK_VERSION, read_native_relations
from moparse_eval.native_relations import HEADING_SCOPE_EVIDENCE
from moparse_eval.scoring import score_case


def _table(text, *, index=0, continues_prev=None, cell_merge=None):
    return {
        "type": "table", "index": index, "continues_prev": continues_prev, "cell_merge": cell_merge,
        "content": [{"type": "table_body", "content": f"<table><tr><td>{text}</td></tr></table>"}],
    }


def _observe_table(observation, physical_page, pointer, text):
    body_pointer = pointer + "/content/0"
    observation["native_containers"].append({
        "id": pointer, "native_path": pointer, "kind": "table", "label": "table",
        "native_children": [body_pointer],
    })
    observation["pages"][physical_page - 1]["blocks"].append({
        "id": body_pointer, "native_path": body_pointer, "kind": "table_body",
        "parent_id": pointer, "native_table_container": pointer,
        "cells": [{
            "id": body_pointer + "/cells/0", "row": 0, "col": 0,
            "row_span": 1, "col_span": 1, "text": text,
            "parent_id": pointer, "native_table_container": pointer,
        }],
    })


def _inputs(*documents):
    """Turn only the explicitly supplied toy document pages into fixture views."""
    native: dict[str, Any] = {"documents": [], "pages": []}
    observation: dict[str, Any] = {
        "sample_id": "synthetic", "pipeline": "P06", "status": "completed",
        "pages": [], "native_containers": [], "relations": [],
        "timing": {"processing_seconds": 2.5}, "resources": {"worker_cpu_seconds": 0.25},
        "runtime": {"synthetic_marker": "preserve"}, "errors": [],
    }
    for document_index, pages in enumerate(documents):
        native["documents"].append({"schema": "docvortex.middle", "pages": copy.deepcopy(pages)})
        for page in pages:
            raw_page_index = len(native["pages"])
            physical_page = raw_page_index + 1
            native["pages"].append({
                "page": physical_page, "branch": "mineru", "raw": {
                    "native_document": f"#/documents/{document_index}", "page_idx": page["page_idx"],
                    "blocks": copy.deepcopy(page["blocks"]),
                },
            })
            observation["pages"].append({"page": physical_page, "blocks": []})
            for block_position, block in enumerate(page["blocks"]):
                if block.get("type") != "table":
                    continue
                body = block["content"][0]["content"]
                text = body.removeprefix("<table><tr><td>").removesuffix("</td></tr></table>")
                _observe_table(observation, physical_page,
                               f"#/pages/{raw_page_index}/raw/blocks/{block_position}", text)
    return observation, native


def _read_unchanged(observation, native):
    before = copy.deepcopy((observation, native))
    derived, diagnostics = read_native_relations(observation, native)
    assert (observation, native) == before
    assert derived is not observation and derived["pages"] is not observation["pages"]
    for key, value in observation.items():
        if key != "relations":
            assert derived[key] == value
    assert derived["relations"][:len(observation["relations"])] == observation["relations"]
    assert diagnostics["reader_version"] == READBACK_VERSION
    assert isinstance(diagnostics["records"], list)
    return derived, diagnostics


def _heading_inputs(*, markup="A type-only title", role="title", saved_metadata=None):
    title_path, body_path = "#/pages/0/raw/0", "#/pages/0/raw/1"
    observation = {
        "sample_id": "synthetic-heading", "pipeline": "P08", "status": "completed",
        "pages": [{"page": 1, "blocks": [
            {"id": title_path, "native_path": title_path, "kind": role, "text": markup,
             "text_format": "markdown", "native_sequence": [1, 0]},
            {"id": body_path, "native_path": body_path, "kind": "text", "text": "Unchanged body",
             "text_format": "markdown", "native_sequence": [1, 1]},
        ]}],
        "relations": [], "timing": {"processing_seconds": 2.5},
        "resources": {"synthetic_marker": "preserve"},
    }
    native = {"pages": [{"page": 1, "branch": "visual", "raw": [
        {"type": role, "content": markup, **(saved_metadata or {})},
        {"type": "text", "content": "Unchanged body"},
    ]}]}
    return observation, native


def test_readback_reports_type_only_title_without_manufacturing_a_level_or_content():
    observation, native = _heading_inputs()
    derived, diagnostics = _read_unchanged(observation, native)
    evidence = derived["native_relation_evidence"]
    title = evidence["heading_blocks"][0]
    assert title["id"] == "#/pages/0/raw/0"
    assert title["role"] == "heading"
    assert title["status"] == "role_only_without_level"
    assert title["resolved_level"] is None
    assert not any(edge["type"] == "heading_of" for edge in derived["relations"])
    assert evidence["reader_version"] == READBACK_VERSION
    assert "no_content_repair" in evidence["scope"]
    assert "heading" in diagnostics["scope"] and "continuation" in diagnostics["scope"]


@pytest.mark.parametrize("saved_metadata,status", [
    ({"level": 2}, "declared_level"),
    ({"research_export_markdown": "## Saved SDK title\n\n"}, "markdown_heading"),
])
def test_readback_uses_unique_saved_metadata_without_changing_frozen_pages(saved_metadata, status):
    observation, native = _heading_inputs(saved_metadata=saved_metadata)
    derived, diagnostics = _read_unchanged(observation, native)
    title = derived["native_relation_evidence"]["heading_blocks"][0]
    assert title["status"] == status and title["resolved_level"] == 2
    edges = [edge for edge in derived["relations"] if edge["type"] == "heading_of"]
    assert len(edges) == 1
    assert edges[0]["source"] == "#/pages/0/raw/0"
    assert edges[0]["target"] == "#/pages/0/raw/1"
    assert diagnostics["relation_readback"]["metadata_readback"][0]["fields_added"]
    assert "level" not in derived["pages"][0]["blocks"][0]
    assert "native_export_markdown" not in derived["pages"][0]["blocks"][0]
    again, again_diagnostics = read_native_relations(derived, native)
    assert again["relations"] == derived["relations"]
    assert again["native_relation_evidence"] == derived["native_relation_evidence"]
    assert again_diagnostics["relation_readback"]["added_relations"] == []
    assert again["pages"] == observation["pages"]
    assert again["timing"] == observation["timing"]


def test_ambiguous_native_path_never_selects_one_observed_title_to_receive_a_level():
    observation, native = _heading_inputs(saved_metadata={"level": 2})
    duplicate = copy.deepcopy(observation["pages"][0]["blocks"][0])
    duplicate["id"] = "ambiguous-title"
    observation["pages"][0]["blocks"].append(duplicate)
    derived, diagnostics = _read_unchanged(observation, native)
    assert not any(edge["type"] == "heading_of" for edge in derived["relations"])
    assert all(record["resolved_level"] is None
               for record in derived["native_relation_evidence"]["heading_blocks"])
    metadata = diagnostics["relation_readback"]["metadata_readback"]
    assert len(metadata) == 2
    assert all(row["status"] == "unknown" and row["reason"] == "observation_native_path_not_unique"
               for row in metadata)


def test_empty_markdown_heading_withdraws_only_our_stale_generated_edges():
    observation, native = _heading_inputs(markup="#", role="header")
    source, target = (block["id"] for block in observation["pages"][0]["blocks"])
    stale = {"type": "heading_of", "source": source, "target": target,
             "evidence": HEADING_SCOPE_EVIDENCE}
    external = {"type": "heading_of", "source": "external-native-heading", "target": target,
                "evidence": "native_explicit_reference"}
    observation["relations"] = [stale, external]
    before = copy.deepcopy((observation, native))
    derived, diagnostics = read_native_relations(observation, native)
    assert (observation, native) == before
    assert derived["pages"] == observation["pages"]
    assert derived["timing"] == observation["timing"]
    assert stale not in derived["relations"] and external in derived["relations"]
    title = derived["native_relation_evidence"]["heading_blocks"][0]
    assert title["role"] == "page_furniture"
    assert title["status"] == "empty_markdown_heading"
    assert title["resolved_level"] is None
    assert diagnostics["relation_readback"]["withdrawn_relations"] == [
        {**stale, "withdrawal_reason": "empty_markdown_heading"},
    ]


def test_saved_docling_caption_and_parent_references_keep_their_native_direction():
    prefix = "#/documents/0"
    table, caption, value = (prefix + path for path in ("/tables/0", "/texts/0", "/texts/1"))
    observation = {
        "pages": [{"blocks": [
            {"id": table, "native_path": table, "kind": "table", "text": "",
             "native_references": {"footnotes": []}},
            {"id": caption, "native_path": caption, "kind": "caption", "text": "Caption"},
            {"id": value, "native_path": value, "kind": "text", "text": "A record"},
        ]}], "relations": [], "timing": {"processing_seconds": 1.5},
    }
    native = {"documents": [{
        "tables": [{"self_ref": "#/tables/0", "captions": [{"cref": "#/texts/0"}],
                    "children": [{"cref": "#/texts/1"}]}],
        "texts": [{"self_ref": "#/texts/0"},
                  {"self_ref": "#/texts/1", "parent": {"cref": "#/tables/0"}}],
    }]}
    derived, diagnostics = _read_unchanged(observation, native)
    triples = [(edge["type"], edge["source"], edge["target"]) for edge in derived["relations"]]
    assert triples.count(("contains", table, value)) == 1
    assert ("caption_of", caption, table) in triples
    assert ("caption_of", caption, value) not in triples
    assert not any(kind in {"caption_for", "paired_with", "row_header"} for kind, _, _ in triples)
    assert diagnostics["relation_readback"]["metadata_readback"]


def test_missing_native_still_rereads_existing_explicit_markdown_without_inventing_native_metadata():
    observation, _ = _heading_inputs(markup="## Explicit Markdown")
    derived, diagnostics = _read_unchanged(observation, None)
    assert diagnostics["status"] == "native_missing"
    assert diagnostics["relation_readback"]["metadata_readback"] == []
    assert any(edge["type"] == "heading_of" for edge in derived["relations"])
    assert derived["native_relation_evidence"]["heading_blocks"][0]["status"] == "markdown_heading"


def _continuations(observation):
    return [edge for edge in observation.get("relations", []) if edge["type"] == "continues"]


def _declaration(derived, pointer):
    return next(item for item in derived["native_table_declarations"] if item["native_path"] == pointer)


def _relation_reference(*, source="A", target="B", source_page=1, target_page=2):
    return {
        "sample_id": "synthetic", "review_status": "confirmed",
        "units": [
            {"id": "a", "kind": "table_cell", "literal": source, "pages": [source_page], "status": "confirmed"},
            {"id": "b", "kind": "table_cell", "literal": target, "pages": [target_page], "status": "confirmed"},
        ],
        "relations": [
            {"type": "continues", "source": "a", "target": "b", "status": "confirmed"},
            {"type": "separate", "source": "a", "target": "b", "status": "confirmed"},
        ],
    }


def test_native_readback_has_no_reference_argument_and_preserves_original_fields():
    assert isinstance(READBACK_VERSION, str) and READBACK_VERSION
    assert tuple(inspect.signature(read_native_relations).parameters) == ("observation", "native")
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    observation["relations"].append({"type": "contains", "source": "preserved-parent", "target": "preserved-child"})
    derived, _diagnostics = _read_unchanged(observation, native)
    edges = _continuations(derived)
    assert len(edges) == 1
    assert (edges[0]["source"], edges[0]["target"], edges[0]["evidence"]) == (
        "#/pages/0/raw/blocks/0", "#/pages/1/raw/blocks/0", "docvortex.continues_prev",
    )
    declaration = _declaration(derived, "#/pages/1/raw/blocks/0")
    assert declaration["status"] == "linked"
    assert declaration["continues_prev"] is True
    assert declaration["cell_merge"] is None
    assert declaration["previous_table_id"] == "#/pages/0/raw/blocks/0"
    assert declaration["document_table_path"] == "#/documents/0/pages/1/blocks/0"


def test_continuation_uses_the_nearest_preceding_table_in_the_same_document():
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A", index=0), _table("EarlierNeighbor", index=1)]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    derived, _ = _read_unchanged(observation, native)
    edges = _continuations(derived)
    assert len(edges) == 1
    assert edges[0]["source"] == "#/pages/0/raw/blocks/1"
    assert edges[0]["target"] == "#/pages/1/raw/blocks/0"


@pytest.mark.parametrize("flag", [False, None])
def test_false_or_null_continuation_does_not_create_a_continuation_edge(flag):
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=flag)]},
    ])
    derived, _ = _read_unchanged(observation, native)
    assert _continuations(derived) == []
    declaration = _declaration(derived, "#/pages/1/raw/blocks/0")
    assert declaration["status"] == "not_declared"
    assert declaration["continues_prev"] is flag


def test_true_without_any_predecessor_remains_unknown():
    observation, native = _inputs([{ "page_idx": 0, "blocks": [_table("B", continues_prev=True)]}])
    derived, _ = _read_unchanged(observation, native)
    assert _continuations(derived) == []
    declaration = _declaration(derived, "#/pages/0/raw/blocks/0")
    assert declaration["status"] == "unknown"
    assert declaration["previous_table_id"] is None


def test_tables_in_different_explicit_documents_do_not_gain_a_cross_document_edge():
    observation, native = _inputs(
        [{"page_idx": 0, "blocks": [_table("A")]}],
        [{"page_idx": 0, "blocks": [_table("B", continues_prev=True)]}],
    )
    derived, _ = _read_unchanged(observation, native)
    assert _continuations(derived) == []
    declaration = _declaration(derived, "#/pages/1/raw/blocks/0")
    assert declaration["status"] == "unknown"
    assert declaration["previous_table_id"] is None


def test_nearest_same_page_predecessor_is_not_replaced_with_an_earlier_page_table():
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("SamePage", index=0), _table("B", index=1, continues_prev=True)]},
    ])
    derived, _ = _read_unchanged(observation, native)
    assert _continuations(derived) == []
    declaration = _declaration(derived, "#/pages/1/raw/blocks/1")
    assert declaration["status"] == "unknown"
    assert declaration["previous_table_id"] is None


@pytest.mark.parametrize("ambiguity", ["page_idx", "block_index", "observation_mapping"])
def test_ambiguous_native_identity_never_selects_a_favorable_predecessor(ambiguity):
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    if ambiguity == "page_idx":
        duplicate = copy.deepcopy(native["documents"][0]["pages"][0])
        native["documents"][0]["pages"].insert(1, duplicate)
    elif ambiguity == "block_index":
        for blocks in (native["documents"][0]["pages"][0]["blocks"], native["pages"][0]["raw"]["blocks"]):
            blocks.append(_table("Ambiguous", index=0))
        _observe_table(observation, 1, "#/pages/0/raw/blocks/1", "Ambiguous")
    else:
        duplicate = copy.deepcopy(observation["native_containers"][0])
        duplicate["id"] = "ambiguous-container-with-same-native-path"
        observation["native_containers"].append(duplicate)
    derived, _ = _read_unchanged(observation, native)
    assert _continuations(derived) == []
    declaration = _declaration(derived, "#/pages/1/raw/blocks/0")
    assert declaration["status"] == "unknown"
    assert declaration["previous_table_id"] is None


def test_nested_table_flag_is_unknown_while_valid_top_level_neighbors_survive():
    nested = _table("Nested", continues_prev=True)
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [
            _table("B", continues_prev=True), {"type": "paragraph", "index": 1, "content": [nested]},
        ]},
    ])
    nested_pointer = "#/pages/1/raw/blocks/1/content/0"
    _observe_table(observation, 2, nested_pointer, "Nested")
    derived, _ = _read_unchanged(observation, native)
    edges = _continuations(derived)
    assert len(edges) == 1
    assert (edges[0]["source"], edges[0]["target"]) == (
        "#/pages/0/raw/blocks/0", "#/pages/1/raw/blocks/0",
    )
    invalid = _declaration(derived, nested_pointer)
    assert invalid["status"] == "unknown" and invalid["previous_table_id"] is None


def test_cell_merge_is_preserved_without_manufacturing_continuation_or_cell_merges():
    merge = [0, 1]
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", cell_merge=merge)]},
    ])
    derived, _ = _read_unchanged(observation, native)
    assert _continuations(derived) == []
    declaration = _declaration(derived, "#/pages/1/raw/blocks/0")
    assert declaration["cell_merge"] == merge
    assert declaration["status"] == "not_declared"
    assert derived["pages"] == observation["pages"]


def test_ambiguous_table_view_does_not_reward_physical_fragment_separation():
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    duplicate = copy.deepcopy(observation["native_containers"][1])
    duplicate["id"] = "ambiguous-second-table"
    observation["native_containers"].append(duplicate)
    derived, _ = _read_unchanged(observation, native)
    result = score_case(_relation_reference(), derived)
    assert all(not row["correct"] and not row["observable"] for row in result["relations"])


@pytest.mark.parametrize("native_status", ["native_missing", "readback_error"])
def test_unavailable_native_readback_does_not_prove_separate(native_status):
    observation, _ = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    observation["scoring_readback"] = {"native_status": native_status}
    if native_status == "readback_error":
        with pytest.raises(ValueError, match="reader failed"):
            score_case(_relation_reference(), observation)
    else:
        result = score_case(_relation_reference(), observation)
        assert all(not row["correct"] and not row["observable"] for row in result["relations"])


def test_explicit_native_continuation_overrides_distinct_physical_table_ids_in_relation_scoring():
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    derived, _ = _read_unchanged(observation, native)
    scored = score_case(_relation_reference(), derived)
    relations = {row["type"]: row for row in scored["relations"]}
    assert relations["continues"]["observable"] is True and relations["continues"]["correct"] is True
    assert relations["separate"]["observable"] is True and relations["separate"]["correct"] is False
    assert scored["metrics"]["unit_presence"]["recall"] == 1


def test_unresolved_native_predecessor_keeps_continuation_and_separation_unknown():
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A", index=0), _table("Other", index=0)]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    derived, _ = _read_unchanged(observation, native)
    scored = score_case(_relation_reference(), derived)
    assert scored["metrics"]["unit_presence"]["recall"] == 1
    assert all(row["observable"] is False and row["correct"] is False for row in scored["relations"])


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _synthetic_run(tmp_path, monkeypatch, *, native_status="present"):
    from moparse_eval import cli

    monkeypatch.setattr(cli, "code_identity", lambda: {
        "software_id": "synthetic-software", "module_sha256": {}, "support_module_sha256": {},
    })
    monkeypatch.setattr(cli, "snapshot_software", lambda *_args: None)
    dataset = tmp_path / "synthetic-dataset"
    manifest = {
        "name": "synthetic-lite", "kind": "lite", "state": "frozen",
        "samples": [{"id": "synthetic", "document_id": "synthetic-doc", "source_pages": [1, 2],
                     "evaluation": "evaluation.json"}],
    }
    _write_json(dataset / "manifest.json", manifest)
    _write_json(dataset / "evaluation.json", _relation_reference())
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    observation.update(dataset="synthetic-lite", suite="quality800", phase="measured",
                       repetition=1, run_id="synthetic-run", input_page_count=2)
    run = tmp_path / "synthetic-run"
    relative = "artifacts/P06/quality800-r1/synthetic/observation.json"
    source_observation = run / relative
    source_native = source_observation.with_name("native.json")
    _write_json(source_observation, observation)
    if native_status == "present":
        _write_json(source_native, native)
    elif native_status == "malformed":
        source_native.write_text("{synthetic-invalid-json", encoding="utf-8")
    _write_json(run / "run.json", {
        "run_id": "synthetic-run", "dataset": str(dataset), "formal": True, "state": "completed",
        "cases": [{"sample_id": "synthetic", "pipeline": "P06", "suite": "quality800",
                   "phase": "measured", "repetition": 1, "observation": relative}],
    })
    _write_json(run / "maintenance.json", {
        "phase": "restored", "tts_policy": "keep_running",
        "tts_identity_condition": {"status": "unchanged"},
        "tts_no_calls_condition": {"status": "no_observed_activity"},
    })
    untouched = {path: path.read_bytes() for path in (
        source_observation, dataset / "manifest.json", dataset / "evaluation.json",
        *([source_native] if source_native.is_file() else []),
    )}
    return run, source_observation, source_native, untouched


def test_cli_saves_versioned_derived_observation_and_readback_diagnostics_without_rewriting_inputs(
    tmp_path, monkeypatch,
):
    from moparse_eval.cli import score_run

    run, source_observation, source_native, untouched = _synthetic_run(tmp_path, monkeypatch)
    relations_by_run = []
    declarations_by_run = []
    for _ in range(2):
        index_path = score_run(run)
        index = json.loads(index_path.read_text())
        readback = index["native_readback"]
        assert readback["reader_version"] == READBACK_VERSION
        assert len(readback["observations"]) == 1
        item = readback["observations"][0]
        assert item["source_observation"] == str(source_observation.relative_to(run))
        assert item["source_native"] == str(source_native.relative_to(run))
        assert item["software_id"] == "synthetic-software"
        assert math.isfinite(item["readback_seconds"]) and item["readback_seconds"] >= 0
        assert item["observation"].endswith("observations/P06/quality800-r1/synthetic.json")
        assert item["diagnostics"].endswith("observations/P06/quality800-r1/synthetic.readback.json")
        derived = json.loads((run / item["observation"]).read_text())
        diagnostics = json.loads((run / item["diagnostics"]).read_text())
        assert diagnostics["reader_version"] == READBACK_VERSION
        assert _continuations(derived)
        relations_by_run.append(derived["relations"])
        declarations_by_run.append(derived["native_table_declarations"])
        scored = json.loads((run / index["results"][0]).read_text())
        assert scored["timing"]["processing_seconds"] == 2.5
        relations = {row["type"]: row for row in scored["relations"]}
        assert relations["continues"]["correct"] is True
        assert relations["separate"]["correct"] is False
    assert relations_by_run[0] == relations_by_run[1]
    assert declarations_by_run[0] == declarations_by_run[1]
    assert all(path.read_bytes() == payload for path, payload in untouched.items())


@pytest.mark.parametrize("native_status,diagnostic_status", [
    ("missing", "native_missing"),
])
def test_cli_missing_or_malformed_native_keeps_independent_candidate_status_and_known_targets(
    tmp_path, monkeypatch, native_status, diagnostic_status,
):
    from moparse_eval.cli import score_run

    run, source_observation, source_native, untouched = _synthetic_run(
        tmp_path, monkeypatch, native_status=native_status,
    )
    index = json.loads(score_run(run).read_text())
    item = index["native_readback"]["observations"][0]
    assert item["source_native"] == str(source_native.relative_to(run))
    assert "native_status" in item
    derived = json.loads((run / item["observation"]).read_text())
    diagnostics = json.loads((run / item["diagnostics"]).read_text())
    original = json.loads(source_observation.read_text())
    assert diagnostics["status"] == diagnostic_status
    assert derived["status"] == original["status"] == "completed"
    assert derived["pages"] == original["pages"]
    assert derived["timing"] == original["timing"]
    assert _continuations(derived) == []
    scored = json.loads((run / index["results"][0]).read_text())
    assert scored["status"] == "completed"
    assert scored["metrics"]["unit_presence"]["target_units"] == 2
    assert scored["metrics"]["unit_presence"]["recall"] == 1
    assert scored["metrics"]["relations"]["target_units"] == 2
    assert all(path.read_bytes() == payload for path, payload in untouched.items())


def test_cli_does_not_publish_engineering_readback_errors(tmp_path, monkeypatch):
    from moparse_eval.cli import score_run

    run, _, _, untouched = _synthetic_run(tmp_path, monkeypatch, native_status="malformed")
    before = (run / "run.json").read_bytes()
    with pytest.raises(ValueError, match="reader failed; repair readback"):
        score_run(run)
    assert (run / "run.json").read_bytes() == before
    assert all(path.read_bytes() == payload for path, payload in untouched.items())


def _assert_unknown_continuation_pair(derived):
    assert _continuations(derived) == []
    for reference in (
        _relation_reference(),
        _relation_reference(source="B", target="A", source_page=2, target_page=1),
    ):
        scored = score_case(reference, derived)
        assert scored["metrics"]["unit_presence"]["recall"] == 1
        assert all(not row["correct"] and not row["observable"] for row in scored["relations"])


@pytest.mark.parametrize("identity_problem", [
    "missing", "nonexistent_document", "unrecognized_schema", "integer", "list", "mapping",
])
def test_mineru_true_declaration_is_not_hidden_by_unresolved_document_identity(identity_problem):
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    raw = native["pages"][1]["raw"]
    if identity_problem == "missing":
        raw.pop("native_document")
    elif identity_problem == "nonexistent_document":
        raw["native_document"] = "#/documents/999"
    elif identity_problem == "unrecognized_schema":
        native["documents"][0]["schema"] = "synthetic-unrecognized.middle"
    elif identity_problem == "integer":
        raw["native_document"] = 0
    elif identity_problem == "list":
        raw["native_document"] = ["#/documents/0"]
    else:
        raw["native_document"] = {"id": "#/documents/0"}
    derived, diagnostics = _read_unchanged(observation, native)
    declaration = _declaration(derived, "#/pages/1/raw/blocks/0")
    assert declaration["continues_prev"] is True
    assert declaration["status"] == "unknown"
    assert declaration["previous_table_id"] is None
    assert diagnostics["records"]
    _assert_unknown_continuation_pair(derived)


def _replace_second_page_observed_tables(observation, pointer_text_pairs):
    observation["native_containers"] = [
        item for item in observation["native_containers"]
        if not item["native_path"].startswith("#/pages/1/")
    ]
    observation["pages"][1]["blocks"] = []
    for pointer, text in pointer_text_pairs:
        _observe_table(observation, 2, pointer, text)


@pytest.mark.parametrize("shape", ["index_mapping", "wrapper_mapping"])
def test_nonlist_raw_blocks_keeps_visible_true_flag_unknown_instead_of_hiding_it(shape):
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    table = native["pages"][1]["raw"]["blocks"][0]
    key = "0" if shape == "index_mapping" else "wrapped"
    native["pages"][1]["raw"]["blocks"] = {key: table}
    pointer = f"#/pages/1/raw/blocks/{key}"
    _replace_second_page_observed_tables(observation, [(pointer, "B")])
    derived, _ = _read_unchanged(observation, native)
    declaration = _declaration(derived, pointer)
    assert declaration["continues_prev"] is True
    assert declaration["status"] == "unknown"
    assert declaration["previous_table_id"] is None
    _assert_unknown_continuation_pair(derived)


@pytest.mark.parametrize("order_problem", ["reversed_indices", "duplicate_indices", "missing_index"])
def test_invalid_order_in_raw_view_cannot_borrow_valid_canonical_document_order(order_problem):
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [
            _table("B", index=0, continues_prev=True), _table("Other", index=1),
        ]},
    ])
    blocks = native["pages"][1]["raw"]["blocks"]
    if order_problem == "reversed_indices":
        blocks.reverse()
        pointer = "#/pages/1/raw/blocks/1"
        _replace_second_page_observed_tables(observation, [
            ("#/pages/1/raw/blocks/0", "Other"), (pointer, "B"),
        ])
    else:
        pointer = "#/pages/1/raw/blocks/0"
        if order_problem == "duplicate_indices":
            blocks[1]["index"] = 0
        else:
            blocks[0].pop("index")
    derived, _ = _read_unchanged(observation, native)
    declaration = _declaration(derived, pointer)
    assert declaration["continues_prev"] is True
    assert declaration["status"] == "unknown"
    assert declaration["previous_table_id"] is None
    _assert_unknown_continuation_pair(derived)


@pytest.mark.parametrize("branch", ["glm", "paddle"])
def test_other_native_schema_is_not_treated_as_missing_mineru_document_identity(branch):
    observation = {
        "sample_id": "synthetic", "pipeline": "P-other", "status": "completed",
        "pages": [{"page": 1, "blocks": [{"id": "body", "kind": "text", "text": "Ordinary output."}]}],
        "native_containers": [], "relations": [], "timing": {"processing_seconds": 1},
    }
    native = {
        "documents": [],
        "pages": [{"page": 1, "branch": branch, "raw": {
            "schema": f"synthetic-{branch}.native",
            "payload": {"blocks": [_table("OpaqueBackendPayload", continues_prev=True)]},
        }}],
    }
    derived, diagnostics = _read_unchanged(observation, native)
    assert diagnostics["status"] == "not_applicable"
    assert diagnostics["records"] == []
    assert derived.get("native_table_declarations", []) == []
    assert derived["pages"] == observation["pages"]


def test_continuation_and_separation_score_the_unordered_pair_when_endpoints_are_reversed():
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    derived, _ = _read_unchanged(observation, native)
    reference = _relation_reference(source="B", target="A", source_page=2, target_page=1)
    scored = score_case(reference, derived)
    assert scored["metrics"]["unit_presence"]["recall"] == 1
    relations = {row["type"]: row for row in scored["relations"]}
    assert relations["continues"]["observable"] is True and relations["continues"]["correct"] is True
    assert relations["separate"]["observable"] is True and relations["separate"]["correct"] is False


def test_malformed_wrapper_path_does_not_turn_an_old_observation_pointer_into_separation_evidence():
    observation, native = _inputs([
        {"page_idx": 0, "blocks": [_table("A")]},
        {"page_idx": 1, "blocks": [_table("B", continues_prev=True)]},
    ])
    table = native["pages"][1]["raw"]["blocks"][0]
    native["pages"][1]["raw"]["blocks"] = {"wrapped": table}
    derived, _ = _read_unchanged(observation, native)
    declaration = _declaration(derived, "#/pages/1/raw/blocks/wrapped")
    assert declaration["status"] == "unknown"
    assert declaration["table_id"] is None
    assert declaration["previous_table_id"] is None
    assert declaration["unresolved_observation_table_ids"] == ["#/pages/1/raw/blocks/0"]
    _assert_unknown_continuation_pair(derived)
