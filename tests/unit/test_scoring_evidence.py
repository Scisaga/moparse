"""Controlled semantics, complete traces and bounded snapshot memory."""

import json
import tracemalloc
from copy import deepcopy

import pytest

from moparse_eval.business_correspondence import grade_business, identity_checks, query_for
from moparse_eval.relation_correspondence import grade_relations, signature
from moparse_eval.scoring_evidence import evidence_session, snapshot_copy


def _canonical(text):
    return " ".join(text.split())


def _context(size):
    return {"status": "bound", "source": {"path": "<context>", "block": "north"}, "conflicts": [],
            "events": [{"position": i, "kind": "ordinary_content", "text": f"context-{i}",
                        "source": {"path": f"<context:{i}>", "lines": [i + 1, i + 1]},
                        "headings": [{"text": "North", "level": 1}]} for i in range(size)]}


def _fact(identifier, *, value="17", scope=("North",), context=None):
    result = {"id": identifier, "subject": "Delta", "attribute": "Revenue", "value": value, "role": "metric",
              "scope": list(scope), "qualifiers": {}, "identity_facets": {},
              "source": {"path": f"<fact:{identifier}>", "lines": [1, 1]}, "record_id": None}
    if context is not None:
        result["context_evidence"] = context
    return result


def _business(reference, candidates):
    return grade_business(reference, candidates, literals=[], canonicalize=_canonical)


def _edge(identifier, *, context=None):
    result = {"id": identifier, "type": "field_binding", "left": {"subject": "Delta", "attribute": "Revenue"},
              "right": {"subject": "Delta", "attribute": "Revenue", "scope": ["North"], "qualifiers": {}},
              "source": {"path": f"<edge:{identifier}>", "lines": [1, 1]}}
    if context is not None:
        result["context_evidence"] = context
    return result


def test_nested_session_reuses_one_snapshot_but_next_grade_has_an_independent_copy():
    source = {"events": [{"text": "original"}]}
    with evidence_session():
        first = snapshot_copy(source)
        with evidence_session():
            assert snapshot_copy(source) is first
            assert snapshot_copy({"already_snapshotted": first})["already_snapshotted"] is first
    source["events"][0]["text"] = "changed"
    with evidence_session():
        second = snapshot_copy(source)
    assert first == {"events": [{"text": "original"}]}
    assert second == source and second is not first


def test_snapshot_scope_resets_on_exception_and_outside_scope_copy_is_isolated():
    source = {"x": [1]}
    with pytest.raises(RuntimeError):
        with evidence_session():
            abandoned = snapshot_copy(source)
            raise RuntimeError("controlled")
    outside = snapshot_copy(source)
    assert outside == abandoned and outside is not abandoned and outside is not source
    source["x"].append(2)
    assert outside == abandoned == {"x": [1]}


def test_complete_business_json_is_unchanged_and_conflicting_hits_are_not_dropped():
    context = _context(4)
    reference = [_fact("required")]
    actual = [_fact("correct", context=context), _fact("conflict", value="18", context=context),
              _fact("other-scope", scope=["South"], context=context)]
    original = deepcopy((reference, actual))
    baseline = _business(reference, actual)
    with evidence_session():
        optimized = _business(reference, actual)
    assert json.dumps(optimized, ensure_ascii=False, sort_keys=True) == json.dumps(baseline, ensure_ascii=False, sort_keys=True)
    layer, [row] = optimized
    assert layer["denominator"] == 1 and layer["numerator"] == 0
    assert [hit["id"] for hit in row["retrieval"]["candidates"]] == ["correct", "conflict", "other-scope"]
    assert row["retrieval"]["accepted"] == ["correct", "conflict"]
    assert (reference, actual) == original


def test_working_effective_facets_are_not_memoized_or_shared_between_identity_checks():
    fact = _fact("actual", context=_context(2))
    required_group = _fact("group")
    required_group["identity_facets"] = {"group": "North"}
    with evidence_session():
        first = identity_checks(query_for(required_group), fact, _canonical)
        second = identity_checks(query_for(_fact("plain")), fact, _canonical)
    assert first["identity_facets"]["actual"] == {"group": ["North"]}
    assert second["identity_facets"]["actual"] == {}
    assert fact["identity_facets"] == {}


def test_completed_traces_survive_input_mutation_and_grades_do_not_share_snapshots():
    context = _context(3)
    reference, actual = [_fact("required")], [_fact("candidate", context=context)]
    with evidence_session():
        first = _business(reference, actual)
    saved_json = json.dumps(first, sort_keys=True)
    context["events"][0]["text"] = "later change"
    actual[0]["source"]["path"] = "<later-source>"
    reference[0]["value"] = "19"
    assert json.dumps(first, sort_keys=True) == saved_json
    with evidence_session():
        second = _business(reference, actual)
    assert first[1][0]["retrieval"]["candidates"][0]["candidate"] is not second[1][0]["retrieval"]["candidates"][0]["candidate"]
    assert second[1][0]["retrieval"]["candidates"][0]["candidate"]["context_evidence"]["events"][0]["text"] == "later change"


def test_relation_json_and_all_hits_stay_identical_and_returned_sources_are_snapshots():
    context = _context(3)
    reference = [_edge("required")]
    first, second = _edge("first", context=context), _edge("second", context=context)
    second["right"]["scope"] = ["South"]
    actual = [first, second]
    baseline = grade_relations(reference, actual, canonicalize=_canonical)
    with evidence_session():
        optimized = grade_relations(reference, actual, canonicalize=_canonical)
    assert json.dumps(optimized, sort_keys=True) == json.dumps(baseline, sort_keys=True)
    layer, [row] = optimized
    assert layer["numerator"] == layer["denominator"] == 1
    assert [hit["id"] for hit in row["retrieval"]["candidates"]] == ["first", "second"]
    assert row["retrieval"]["selected"] == "first"
    frozen = json.dumps(optimized, sort_keys=True)
    first["source"]["path"] = "<mutated>"
    reference[0]["left"]["attribute"] = "Profit"
    context["events"][0]["text"] = "mutated"
    assert json.dumps(optimized, sort_keys=True) == frozen


def test_relation_working_endpoints_do_not_mutate_input_facets_or_signatures():
    edge = _edge("same")
    edge["right"]["identity_facets"] = {"group": "North", "role": "Owner"}
    original = deepcopy(edge)
    with evidence_session():
        first, second = signature(edge, _canonical), signature(edge, _canonical)
    assert first == second and edge == original


def test_public_grade_layers_snapshots_all_layers_and_authority_payloads_between_grades():
    from moparse_eval.expected_readback import markdown_observation
    from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate

    text = "# North\n\nName: Delta; Revenue: 17; Profit: 5"
    required = compile_markdown(text, sample_id="invented-public-snapshots")
    actual = read_candidate(markdown_observation(text, sample_id="invented-public-snapshots", pipeline="test", pages=[1]))
    first = grade_layers(required, actual)
    second = grade_layers(required, actual)
    assert first["publishable"] is True and second["publishable"] is True
    frozen = json.dumps(first, sort_keys=True)
    assert json.dumps(second, sort_keys=True) == frozen
    for layer in ("T", "L", "B"):
        [old] = [row for row in first["outcomes"] if row["layer"] == layer][:1]
        [new] = [row for row in second["outcomes"] if row["layer"] == layer][:1]
        assert old["expected"] is not new["expected"]
        assert old["actual"] is not new["actual"]
    assert first["protocol"] is not second["protocol"]
    assert first["text_evidence"] is not second["text_evidence"]
    assert first["scope_evidence"] is not second["scope_evidence"]
    for source in (required, actual):
        source["text"][0]["text"] = "post-grade text mutation"
        source["text"][0]["source"]["path"] = "<post-grade-path>"
        source["business"][0]["value"] = "post-grade value mutation"
        source["relations"][0]["source"]["path"] = "<post-grade-relation>"
    actual["native_context"]["events"][0]["text"] = "post-grade heading mutation"
    assert json.dumps(first, sort_keys=True) == frozen
    assert json.dumps(second, sort_keys=True) == frozen


def test_many_complete_hits_share_large_context_without_truncation_or_quadratic_copy_memory():
    context = _context(640)
    reference = [_fact(f"required-{i}") for i in range(8)]
    actual = [_fact(f"candidate-{i}", context=context) for i in range(8)]
    tracemalloc.start()
    try:
        with evidence_session():
            layer, rows = _business(reference, actual)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert layer["numerator"] == layer["denominator"] == 8
    assert len(rows) == 8
    assert all(len(row["retrieval"]["candidates"]) == len(row["actual"]) == 8 for row in rows)
    assert all(len(hit["candidate"]["context_evidence"]["events"]) == 640
               and len(hit["identity"]["scope"]["context_evidence"]["events"]) == 640
               for row in rows for hit in row["retrieval"]["candidates"])
    assert peak < 12 * 1024 * 1024, f"per-hit context deepcopies retained {peak} bytes"
