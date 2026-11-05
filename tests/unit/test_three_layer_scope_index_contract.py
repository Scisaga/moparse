"""Independent public contracts for an index that stores no source evidence.

All required scopes, values, source positions and rejection outcomes below are
hand-authored. No requirements compiler supplies this file's expected answers.
"""

from copy import deepcopy

import pytest

from moparse_eval.context_evidence import read_contexts
from moparse_eval.scope_correspondence import verify_scope
from moparse_eval.three_layer import canonical, grade_layers

REVIEW = [["Review"], ["Review", "Revenue"], ["Review", "Cost"]]
REGIONS = [["North"], ["North", "Revenue"], ["South"], ["South", "Revenue"]]


def block(ident, kind="text", text="", level=None):
    result = {"id": ident, "native_path": "#/" + ident, "kind": kind,
              "text": text, "text_format": "plain"}
    if level is not None:
        result["level"] = level
    if kind == "table":
        result["cells"] = []
    return result


def heading(ident, text, level=1):
    return block(ident, "heading", text, level)


def contexts(*blocks, relations=()):
    return read_contexts({"pages": [{"page": 1, "blocks": list(blocks)}],
                          "relations": list(relations)})


def notes_context(*, media=False, child_level=1):
    middle = [block("image", "image")] if media else []
    note_level = 3 if child_level == 2 else 1
    return contexts(heading("review", "Review"), heading("revenue", "Revenue", child_level),
                    block("first", "table"), heading("notes", "Notes:", note_level), *middle,
                    heading("cost", "Cost", child_level), block("table", "table"))


def declaration(*, line=9, scope=("Review", "Revenue"), role=None, text="Notes:"):
    result = {"text": text, "scope": list(scope),
              "source": {"path": "reference.md", "lines": [line, line]}}
    if role is not None:
        result["role"] = role
    return result


def fact(data, ident="table", *, scope=("Review", "Cost"), value="17", serial="0"):
    return {"id": "B:" + serial, "subject": "Delta", "attribute": "Amount", "value": value,
            "role": "metric", "qualifiers": {}, "identity_facets": {}, "scope": list(scope),
            "source": {"path": "#/" + ident, "block": ident, "cell": ident + ":amount"},
            "context_evidence": deepcopy(data["by_block"][ident])}


def checked(data, labels, *, required=("Review", "Cost"), paths=REVIEW, item=None, normalize=canonical):
    return verify_scope(list(required), item or fact(data), paths, contexts=data,
                        canonicalize=normalize, context_labels=labels)


def binding(item):
    return {"id": "L:" + item["id"], "type": "field_binding",
            "left": {"subject": "Delta", "attribute": "Amount"},
            "right": {"subject": "Delta", "attribute": "Amount", "scope": deepcopy(item["scope"]),
                      "qualifiers": {}, "identity_facets": {}},
            "source": deepcopy(item["source"]),
            "context_evidence": deepcopy(item.get("context_evidence", {}))}


def public_score(data, labels, *, required=("Review", "Cost"), paths=REVIEW, actual=None):
    expected = {"id": "B:required", "subject": "Delta", "attribute": "Amount", "value": "17",
                "role": "metric", "qualifiers": {}, "identity_facets": {}, "scope": list(required),
                "source": {"path": "reference.md", "lines": [20, 20]}}
    required_graph = {"sample_id": "scope-index-contract", "business": [expected],
                      "requirement_ledger": [deepcopy(expected)], "relations": [binding(expected)],
                      "text": [{"id": "T:required", "text": "17", "source": expected["source"]}],
                      "scope_schema": {"paths": deepcopy(paths), "context_labels": labels}, "blockers": []}
    actual = actual or [fact(data)]
    evidence = {"sample_id": "scope-index-contract", "pipeline": "invented",
                "business": actual, "relations": [binding(item) for item in actual],
                "text": [{"id": "T:" + item["id"], "text": item["value"], "source": item["source"]}
                         for item in actual], "native_context": data, "blockers": []}
    before = deepcopy((required_graph, evidence))
    score = grade_layers(required_graph, evidence)
    assert (required_graph, evidence) == before
    return score


def business_row(score):
    [row] = [item for item in score["outcomes"] if item["layer"] == "B"]
    return row


def relation_row(score):
    [row] = [item for item in score["outcomes"] if item["layer"] == "L"]
    return row


def test_same_texts_use_current_source_dicts_after_in_place_and_replacement_changes():
    data = notes_context()
    labels = [declaration()]
    first = checked(data, labels)
    assert first["correct"] is True
    assert first["display_context_sources"][0]["reference_declaration"]["source"] == {
        "path": "reference.md", "lines": [9, 9]}
    labels[0]["source"].update(path="replacement.md", lines=[29, 29])
    second = checked(data, labels)
    assert second["display_context_sources"][0]["reference_declaration"]["source"] == {
        "path": "replacement.md", "lines": [29, 29]}
    labels[0] = declaration(line=39)
    third = checked(data, labels)
    assert third["display_context_sources"][0]["reference_declaration"]["source"]["lines"] == [39, 39]
    assert first["display_context_sources"][0]["reference_declaration"]["source"]["lines"] == [9, 9]


def test_same_texts_changed_scope_cannot_keep_the_old_business_parent_in_either_layer():
    data = notes_context()
    labels = [declaration()]
    good = public_score(data, labels)
    assert business_row(good)["outcome"] == relation_row(good)["outcome"] == "correct"
    labels[0]["scope"] = ["South", "Revenue"]
    bad = public_score(data, labels)
    assert business_row(bad)["outcome"] == relation_row(bad)["outcome"] == "incorrect"
    [hit] = business_row(bad)["retrieval"]["candidates"]
    assert hit["identity"]["scope"]["correct"] is False
    assert hit["identity"]["scope"]["verification"]["display_context_sources"] == []


def test_same_texts_changed_role_cannot_reuse_external_ancestor_authority():
    data = contexts(heading("external", "Review document"), heading("review", "Review"),
                    heading("revenue", "Revenue"), block("first", "table"),
                    heading("repeat", "Review document"), heading("cost", "Cost"), block("table", "table"))
    labels = [declaration(scope=("Review",), role="external_ancestor", text="Review document")]
    accepted = checked(data, labels)
    assert accepted["correct"] is True
    assert accepted["display_context_sources"][0]["prior_actual_source"]["block"] == "external"
    labels[0]["role"] = "ordinary_context_label"
    rejected = checked(data, labels)
    assert rejected["correct"] is False and rejected["display_context_sources"] == []


def test_duplicate_labels_keep_current_order_and_first_eligible_source():
    data = notes_context()
    labels = [declaration(line=7, scope=("South", "Revenue")), declaration(line=11), declaration(line=13)]
    first = checked(data, labels)
    assert first["correct"] is True
    assert first["display_context_sources"][0]["reference_declaration"]["source"]["lines"] == [11, 11]
    labels[:] = [labels[2], labels[0], labels[1]]
    before = deepcopy((data, labels, REVIEW))
    reordered = checked(data, labels)
    assert reordered["correct"] is True
    assert reordered["display_context_sources"][0]["reference_declaration"]["source"]["lines"] == [13, 13]
    assert (data, labels, REVIEW) == before


@pytest.mark.parametrize("fold_first", [False, True])
def test_identical_label_texts_do_not_reuse_another_canonical_policy(fold_first):
    data = notes_context()
    labels = [declaration(text="NOTES:")]

    def folded(value):
        return canonical(value).casefold()

    policies = [folded, canonical] if fold_first else [canonical, folded]
    for policy in policies:
        result = checked(data, labels, normalize=policy)
        assert result["correct"] is (policy is folded)


@pytest.mark.parametrize("child_level,accepted", [(1, False), (2, True)])
def test_media_remains_a_flat_scope_barrier_but_explicit_hierarchy_has_its_own_proof(child_level, accepted):
    data = notes_context(media=True, child_level=child_level)
    result = checked(data, [declaration()])
    assert result["correct"] is accepted
    if accepted:
        assert [item["source"]["block"] for item in result["actual_sources"]] == ["review", "cost"]
    else:
        assert any(item["source"]["block"] == "image" and item["terminates"] for item in result["boundaries"])


def test_north_position_is_checked_before_values_and_cannot_borrow_south_answer():
    data = contexts(heading("north", "North"), heading("north-revenue", "Revenue"),
                    block("north-table", "table"), heading("south", "South"),
                    heading("south-revenue", "Revenue"), block("south-table", "table"))
    actual = [fact(data, "north-table", scope=("North", "Revenue"), value="18", serial="north"),
              fact(data, "south-table", scope=("South", "Revenue"), value="17", serial="south")]
    score = public_score(data, [declaration()], required=("North", "Revenue"), paths=REGIONS, actual=actual)
    row = business_row(score)
    assert row["outcome"] == "incorrect"
    assert [item["id"] for item in row["actual"]] == ["B:north"]
    assert "value" not in row["retrieval"]["query"]
    [south] = [hit for hit in row["retrieval"]["candidates"] if hit["id"] == "B:south"]
    assert south["decision"] == "rejected" and south["identity"]["scope"]["correct"] is False
    assert south["identity"]["scope"]["verification"]["actual_path"] == ["South", "Revenue"]
    assert relation_row(score)["outcome"] == "correct"
    assert score["layers"]["T"]["numerator"] == score["layers"]["T"]["denominator"] == 2


def test_only_explicit_parent_reference_changes_and_full_public_scope_result_follows_it():
    paths = [["North"], ["South"]]
    labels = [declaration(text="Supplement", scope=("North",))]
    for parent, accepted in [("north", True), ("south", False), ("north", True)]:
        data = contexts(heading("north", "North"), heading("south", "South"), block("table", "table"),
                        relations=[{"type": "heading_of", "source": parent, "target": "table",
                                    "evidence": "explicit_native_reference"}])
        actual = [fact(data, scope=("South",))]
        score = public_score(data, labels, required=("North",), paths=paths, actual=actual)
        row = business_row(score)
        assert (row["outcome"] == "correct") is accepted
        assert (relation_row(score)["outcome"] == "correct") is accepted
        [hit] = row["retrieval"]["candidates"]
        proof = hit["identity"]["scope"]["verification"]
        assert proof["method"] == "explicit_native_heading_reference_path"
        assert proof["actual_path"] == (["North"] if accepted else ["South"])
        assert proof["actual_sources"][0]["source"]["block"] == parent
