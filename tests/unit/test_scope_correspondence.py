"""Scope positions are hand-authored; values never choose their boundaries."""

from copy import deepcopy

import pytest

from moparse_eval.context_evidence import read_contexts
from moparse_eval.scope_correspondence import verify_scope

FINANCIAL = [["Financial review"], ["Financial review", "Revenue"], ["Financial review", "Cost"]]
REGIONS = [["North"], ["North", "Revenue"], ["South"], ["South", "Revenue"]]


def b(ident, kind="text", text="", level=None):
    result = {"id": ident, "native_path": "#/" + ident, "kind": kind, "text": text, "text_format": "plain"}
    if level is not None:
        result["level"] = level
    if kind == "table":
        result["cells"] = []
    return result


def h(ident, text, level=1):
    return b(ident, "heading", text, level)


def material(*blocks, relations=()):
    return read_contexts({"pages": [{"page": 1, "blocks": list(blocks)}], "relations": list(relations)})


def fact(contexts, ident, value="17", **metadata):
    return {"id": "fact:" + ident, "subject": "Delta", "attribute": "Amount", "value": value,
            "source": {"path": "#/" + ident, "block": ident, "cell": ident + ":data", "row": 1, "col": 1},
            "scope": contexts["by_block"][ident]["scope"], "context_evidence": contexts["by_block"][ident],
            "identity_facets": {}, **metadata}


def checked(required, contexts, ident="table", paths=FINANCIAL, **metadata):
    return verify_scope(required, fact(contexts, ident, **metadata), paths, contexts=contexts)


@pytest.mark.parametrize("child_level", [1, 2, None])
def test_financial_review_keeps_both_declared_siblings_under_its_printed_parent(child_level):
    data = material(h("root", "Financial review", child_level), h("revenue", "Revenue", child_level),
                    b("revenue-table", "table"), b("body", text="The cost discussion follows."),
                    h("cost", "Cost", child_level), b("cost-table", "table"))
    before = deepcopy(data)
    first = checked(["Financial review", "Revenue"], data, "revenue-table")
    second = checked(["Financial review", "Cost"], data, "cost-table")
    assert first["correct"] is second["correct"] is True
    assert second["actual_path"] == ["Financial review", "Cost"]
    assert [item["source"]["block"] for item in second["actual_sources"]] == ["root", "cost"]
    assert data == before


def test_missing_parent_cannot_be_supplied_from_the_reference_tree():
    data = material(h("cost", "Cost"), b("table", "table"))
    result = checked(["Financial review", "Cost"], data)
    assert result["correct"] is False and result["status"] == "missing"
    assert not any(item["source"]["block"] == "root" for item in result["actual_sources"])


def test_north_and_south_repeated_leaves_keep_their_own_actual_parent_positions():
    data = material(h("north", "North"), h("north-revenue", "Revenue"), b("north-table", "table"),
                    h("south", "South"), h("south-revenue", "Revenue"), b("south-table", "table"))
    assert checked(["North", "Revenue"], data, "north-table", REGIONS)["correct"] is True
    result = checked(["North", "Revenue"], data, "south-table", REGIONS)
    assert result["correct"] is False and result["status"] == "explicit_conflict"
    assert result["actual_path"] == ["South", "Revenue"]
    assert checked(["South", "Revenue"], data, "south-table", REGIONS)["correct"] is True


@pytest.mark.parametrize("barrier", [h("outside", "Unselected external business", 1),
                                      h("outside", "Unknown role-only heading", None),
                                      b("outside", "image"), b("outside", "document_boundary")])
def test_unmodeled_parent_media_or_document_boundary_prevents_flat_parent_borrowing(barrier):
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("first", "table"),
                    barrier, h("cost", "Cost"), b("table", "table"))
    result = checked(["Financial review", "Cost"], data)
    assert result["correct"] is False
    assert any(boundary["source"]["block"] == "outside" for boundary in result["boundaries"])


def test_a_known_other_parent_closes_the_previous_parent_before_its_cost_leaf():
    paths = [*FINANCIAL, ["Other review"], ["Other review", "Cost"]]
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("first", "table"),
                    h("other", "Other review"), h("cost", "Cost"), b("table", "table"))
    assert checked(["Financial review", "Cost"], data, paths=paths)["correct"] is False
    assert checked(["Other review", "Cost"], data, paths=paths)["correct"] is True


def test_later_repeated_leaf_uses_its_nearest_event_not_an_earlier_same_name():
    data = material(h("root", "Financial review"), h("revenue-1", "Revenue"), b("first", "table"),
                    h("cost", "Cost"), b("cost-table", "table"),
                    h("revenue-2", "Revenue"), b("table", "table"))
    result = checked(["Financial review", "Revenue"], data)
    assert result["correct"] is True
    assert result["actual_sources"][-1]["source"]["block"] == "revenue-2"
    assert any(item["source"]["block"] == "revenue-1" for item in result["rejected"])


def test_parent_direct_facts_stop_at_a_declared_child_while_child_retains_ancestor():
    data = material(h("root", "Financial review"), b("parent-table", "table"),
                    h("revenue", "Revenue"), b("table", "table"))
    assert checked(["Financial review"], data, "parent-table")["correct"] is True
    rejected = checked(["Financial review"], data)
    assert rejected["correct"] is False and rejected["status"] == "explicit_conflict"
    assert checked(["Financial review", "Revenue"], data)["correct"] is True


def test_unknown_deeper_display_heading_does_not_invent_another_business_parent():
    data = material(h("root", "Financial review", 1), h("revenue", "Revenue", 2),
                    h("display", "Presentation detail", 3), b("table", "table"))
    assert checked(["Financial review", "Revenue"], data)["correct"] is True


def test_unknown_reliable_sibling_closes_the_known_leaf_even_inside_a_real_parent():
    data = material(h("root", "Financial review", 1), h("revenue", "Revenue", 2),
                    h("other", "Unselected other child", 2), b("table", "table"))
    assert checked(["Financial review", "Revenue"], data)["correct"] is False


def test_repeated_complete_parent_inside_a_child_preserves_the_current_child():
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("first", "table"),
                    h("repeat", "Financial review", 3), b("table", "table"))
    result = checked(["Financial review", "Revenue"], data)
    assert result["correct"] is True
    assert result["actual_sources"][0]["source"]["block"] == "root"
    assert checked(["Financial review"], data)["correct"] is False


def test_raw_scope_labels_without_actual_heading_sources_cannot_manufacture_a_parent():
    data = material(h("cost", "Cost"), b("table", "table"))
    item = fact(data, "table")
    item["scope"] = ["Financial review", "Cost"]
    item["scope_alternatives"] = [["Financial review", "Cost"]]
    assert verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data)["correct"] is False


def test_scope_evidence_does_not_read_values_or_replace_local_errors_with_remote_correct_values():
    data = material(h("north", "North"), h("north-revenue", "Revenue"), b("wrong", "table"),
                    h("south", "South"), h("south-revenue", "Revenue"), b("right", "table"))
    wrong = fact(data, "wrong", value="18")
    same_position = fact(data, "wrong", value="17")
    wrong_scope = verify_scope(["North", "Revenue"], wrong, REGIONS, contexts=data)
    assert wrong_scope == verify_scope(["North", "Revenue"], same_position, REGIONS, contexts=data)
    assert wrong_scope["correct"] is True
    assert checked(["North", "Revenue"], data, "right", REGIONS)["correct"] is False


def test_a_required_ancestor_printed_only_after_the_fact_does_not_scope_it():
    data = material(h("cost", "Cost"), b("table", "table"), h("root", "Financial review"))
    result = checked(["Financial review", "Cost"], data)
    assert result["correct"] is False
    assert any(item["source"]["block"] == "root" and item["reason"] == "heading_occurs_after_candidate_position"
               for item in result["rejected"])


def test_missing_full_event_stream_returns_unknown_instead_of_trusting_scope_strings():
    item = {"source": {"block": "table"}, "scope": ["Financial review", "Cost"]}
    result = verify_scope(["Financial review", "Cost"], item, FINANCIAL)
    assert result["correct"] is False and result["status"] == "unknown"


def test_an_explicitly_bound_caption_can_express_the_local_leaf_after_the_table():
    data = material(h("root", "Financial review"), b("table", "table"), b("caption", "table_caption", "Cost"),
                    relations=[{"type": "caption_of", "source": "caption", "target": "table"}])
    result = checked(["Financial review", "Cost"], data)
    assert result["correct"] is True
    assert result["actual_sources"][-1]["source"]["block"] == "caption"


def test_a_proven_row_group_axis_supplies_a_required_suffix_without_a_second_heading():
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("table", "table"))
    evidence = [{"role": "row_group", "text": "North", "source": {"block": "table", "cell": "group:north", "row": 1, "col": 0}}]
    item = fact(data, "table", identity_facets={"group": "North"}, row_evidence=evidence)
    result = verify_scope(["Financial review", "Revenue", "North"], item, FINANCIAL, contexts=data)
    assert result["correct"] is True
    assert result["actual_sources"][-1]["source"]["cell"] == "group:north"
    assert verify_scope(["Financial review", "Revenue", "South"], item, FINANCIAL, contexts=data)["correct"] is False


def test_group_strings_without_a_native_axis_source_do_not_create_scope_evidence():
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("table", "table"))
    item = fact(data, "table", identity_facets={"group": "North"})
    result = verify_scope(["Financial review", "Revenue", "North"], item, FINANCIAL, contexts=data)
    assert result["correct"] is False and result["status"] == "unknown"


def test_a_reference_printed_context_label_can_explain_a_same_level_native_heading():
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("first", "table"),
                    h("notes", "Notes:"), b("notes-body", text="The disclosed figures are rounded."),
                    h("cost", "Cost"), b("table", "table"))
    labels = [{"text": "Notes:", "scope": ["Financial review", "Revenue"],
               "source": {"path": "reference.md", "lines": [9, 9]}}]
    before = deepcopy(labels)
    item = fact(data, "table")
    assert verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data)["correct"] is False
    result = verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data, context_labels=labels)
    assert result["correct"] is True
    assert result["display_context_sources"][0]["source"]["block"] == "notes"
    assert result["display_context_sources"][0]["reference_declaration"]["source"]["lines"] == [9, 9]
    assert labels == before


@pytest.mark.parametrize("actual", ["Notes", "Notes: another business", "Unselected chapter"])
def test_context_label_equivalence_requires_the_complete_printed_literal(actual):
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("first", "table"),
                    h("notes", actual), h("cost", "Cost"), b("table", "table"))
    labels = [{"text": "Notes:", "scope": ["Financial review", "Revenue"], "source": {"path": "reference.md"}}]
    result = verify_scope(["Financial review", "Cost"], fact(data, "table"), FINANCIAL, contexts=data, context_labels=labels)
    assert result["correct"] is False and result["display_context_sources"] == []


def test_a_context_label_declared_under_north_cannot_preserve_a_south_parent():
    data = material(h("south", "South"), h("revenue", "Revenue"), b("first", "table"),
                    h("notes", "Notes:"), h("again", "Revenue"), b("table", "table"))
    labels = [{"text": "Notes:", "scope": ["North", "Revenue"], "source": {"path": "reference.md"}}]
    result = verify_scope(["South", "Revenue"], fact(data, "table"), REGIONS, contexts=data, context_labels=labels)
    assert result["correct"] is False and result["display_context_sources"] == []


def test_an_external_ancestor_repeat_requires_its_prior_actual_candidate_heading():
    labels = [{"text": "Management review", "scope": ["Financial review"], "role": "external_ancestor", "source": {"path": "reference.md"}}]
    data = material(h("report-context", "Management review"), h("root", "Financial review"),
                    h("revenue", "Revenue"), b("first", "table"), h("repeat", "Management review"),
                    h("cost", "Cost"), b("table", "table"))
    result = verify_scope(["Financial review", "Cost"], fact(data, "table"), FINANCIAL, contexts=data, context_labels=labels)
    assert result["correct"] is True
    repeated = result["display_context_sources"][0]
    assert repeated["source"]["block"] == "repeat" and repeated["prior_actual_source"]["block"] == "report-context"
    missing = material(h("root", "Financial review"), h("revenue", "Revenue"), b("first", "table"),
                       h("first-external", "Management review"), h("cost", "Cost"), b("table", "table"))
    assert verify_scope(["Financial review", "Cost"], fact(missing, "table"), FINANCIAL,
                        contexts=missing, context_labels=labels)["correct"] is False


def test_an_external_ancestor_declaration_does_not_require_a_missing_unselected_title():
    labels = [{"text": "Management review", "scope": ["Financial review"], "role": "external_ancestor", "source": {"path": "reference.md"}}]
    data = material(h("root", "Financial review"), h("cost", "Cost"), b("table", "table"))
    result = verify_scope(["Financial review", "Cost"], fact(data, "table"), FINANCIAL, contexts=data, context_labels=labels)
    assert result["correct"] is True and result["display_context_sources"] == []


def test_plain_body_mentions_do_not_establish_a_prior_external_ancestor_anchor():
    labels = [{"text": "Management review", "scope": ["Financial review"], "role": "external_ancestor", "source": {"path": "reference.md"}}]
    data = material(b("mention", text="Management review"), h("root", "Financial review"), h("revenue", "Revenue"),
                    b("first", "table"), h("external", "Management review"), h("cost", "Cost"), b("table", "table"))
    assert verify_scope(["Financial review", "Cost"], fact(data, "table"), FINANCIAL,
                        contexts=data, context_labels=labels)["correct"] is False


def test_an_image_still_stops_flat_ancestry_even_with_all_context_labels_in_the_catalogue():
    labels = [{"text": "Notes:", "scope": ["Financial review", "Revenue"], "source": {"path": "reference.md"}}]
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("first", "table"),
                    h("notes", "Notes:"), b("image", "image"), h("cost", "Cost"), b("table", "table"))
    assert verify_scope(["Financial review", "Cost"], fact(data, "table"), FINANCIAL,
                        contexts=data, context_labels=labels)["correct"] is False


def test_a_group_axis_from_a_neighbor_table_cannot_supply_the_current_record_suffix():
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("table", "table"))
    item = fact(data, "table", identity_facets={"group": "North"},
                row_evidence=[{"role": "row_group", "text": "North", "source": {"block": "neighbor", "cell": "north"}}])
    assert verify_scope(["Financial review", "Revenue", "North"], item, FINANCIAL, contexts=data)["correct"] is False


@pytest.mark.parametrize("literal", ["按行業劃分：", "按行業劃分:", "按行業劃分 ： "])
def test_a_group_label_terminal_colon_is_only_a_display_separator(literal):
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("table", "table"))
    source = {"block": "table", "cell": "group:industries", "row": 1, "col": 0}
    item = fact(data, "table", identity_facets={"group": "按行業劃分"},
                row_evidence=[{"role": "row_group", "text": literal, "source": source}])
    result = verify_scope(["Financial review", "Revenue", "按行業劃分"], item, FINANCIAL, contexts=data)
    assert result["correct"] is True
    assert result["actual_sources"][-1]["text"] == literal
    assert result["actual_sources"][-1]["source"] == source


@pytest.mark.parametrize("literal", ["按行業劃分!", "按行業劃分::", "按行業劃分：17", "按行業劃分其他：", "按 行業劃分："])
def test_group_axis_equivalence_cannot_remove_other_punctuation_words_or_values(literal):
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("table", "table"))
    item = fact(data, "table", identity_facets={"group": "按行業劃分"},
                row_evidence=[{"role": "row_group", "text": literal, "source": {"block": "table", "cell": "group"}}])
    assert verify_scope(["Financial review", "Revenue", "按行業劃分"], item, FINANCIAL, contexts=data)["correct"] is False


def test_external_ancestor_declared_only_for_north_cannot_hide_an_unknown_south_peer_heading():
    data = material(h("old-context", "Management review"), h("north", "North"), h("north-leaf", "Revenue"),
                    b("north-table", "table"), h("south", "South"), h("south-leaf", "Revenue"),
                    b("south-table", "table"), h("repeat", "Management review"),
                    h("south-again", "Revenue"), b("table", "table"))
    labels = [{"text": "Management review", "scope": ["North"], "role": "external_ancestor", "source": {"path": "reference.md"}}]
    result = verify_scope(["South", "Revenue"], fact(data, "table"), REGIONS, contexts=data, context_labels=labels)
    assert result["correct"] is False and result["display_context_sources"] == []


def test_external_ancestor_with_an_empty_scope_cannot_erase_every_business_boundary():
    data = material(h("old-context", "Management review"), h("root", "Financial review"),
                    h("revenue", "Revenue"), b("first", "table"), h("repeat", "Management review"),
                    h("cost", "Cost"), b("table", "table"))
    labels = [{"text": "Management review", "scope": [], "role": "external_ancestor", "source": {"path": "reference.md"}}]
    assert verify_scope(["Financial review", "Cost"], fact(data, "table"), FINANCIAL,
                        contexts=data, context_labels=labels)["correct"] is False


def test_reliable_native_hierarchy_keeps_its_explicit_parent_across_an_image():
    data = material(h("root", "Financial review", 1), h("revenue", "Revenue", 2), b("first", "table"),
                    b("image", "image"), h("cost", "Cost", 2), b("table", "table"))
    assert data["by_block"]["table"]["heading_path"] == ["Financial review", "Cost"]
    result = checked(["Financial review", "Cost"], data)
    assert result["correct"] is True
    assert [entry["source"]["block"] for entry in result["actual_sources"]] == ["root", "cost"]
    assert checked(["Financial review"], data)["correct"] is False


def test_flat_display_without_a_native_parent_path_still_cannot_cross_an_image():
    data = material(h("root", "Financial review", 1), h("revenue", "Revenue", 1), b("first", "table"),
                    b("image", "image"), h("cost", "Cost", 1), b("table", "table"))
    assert data["by_block"]["table"]["heading_path"] == ["Cost"]
    assert checked(["Financial review", "Cost"], data)["correct"] is False


def test_native_hierarchy_and_a_local_group_axis_prove_different_scope_components():
    data = material(h("root", "Financial review", 1), b("image", "image"), h("cost", "Cost", 2), b("table", "table"))
    item = fact(data, "table", identity_facets={"group": "North"},
                row_evidence=[{"role": "row_group", "text": "North:", "source": {"block": "table", "cell": "group:north"}}])
    result = verify_scope(["Financial review", "Cost", "North"], item, FINANCIAL, contexts=data)
    assert result["correct"] is True
    assert [entry["source"].get("block") for entry in result["actual_sources"]] == ["root", "cost", "table"]


def test_explicit_prose_heading_reference_wins_over_the_unchanged_display_sequence():
    def build(parent):
        return material(h("north", "North"), h("south", "South"), b("prose", text="The amount is 17."),
                        relations=[{"type": "heading_of", "source": parent, "target": "prose", "evidence": "native_reference"}])
    paths = [["North"], ["South"]]
    original, rewired = build("north"), build("south")
    assert checked(["North"], original, "prose", paths)["correct"] is True
    assert checked(["South"], original, "prose", paths)["correct"] is False
    assert checked(["North"], rewired, "prose", paths)["correct"] is False
    result = checked(["South"], rewired, "prose", paths)
    assert result["correct"] is True and result["actual_sources"][0]["source"]["block"] == "south"


def test_explicit_nested_native_paths_do_not_require_display_levels_or_order():
    root, leaf, prose = h("root", "North", None), h("leaf", "Revenue", None), b("prose", text="The amount is 17.")
    leaf["parent_id"], prose["parent_id"] = "root", "leaf"
    data = material(prose, root, leaf)
    result = checked(["North", "Revenue"], data, "prose", REGIONS)
    assert result["correct"] is True
    assert [entry["source"]["block"] for entry in result["actual_sources"]] == ["root", "leaf"]
    assert checked(["North"], data, "prose", REGIONS)["correct"] is False


def test_conflicting_explicit_parent_paths_cannot_be_rescued_by_local_display_or_a_matching_value():
    data = material(h("north", "North"), h("south", "South"), b("prose", text="The amount is 17."),
                    relations=[{"type": "heading_of", "source": "north", "target": "prose"},
                               {"type": "heading_of", "source": "south", "target": "prose"}])
    paths = [["North"], ["South"]]
    for required in [["North"], ["South"]]:
        result = checked(required, data, "prose", paths)
        assert result["correct"] is False and result["status"] == "explicit_conflict"


def test_explicit_heading_reference_cannot_cross_an_actual_document_boundary():
    data = material(h("root", "North"), b("break", "document_boundary"), b("prose", text="The amount is 17."),
                    relations=[{"type": "heading_of", "source": "root", "target": "prose"}])
    assert checked(["North"], data, "prose", [["North"]])["correct"] is False


def test_a_heading_target_adds_its_own_actual_heading_after_its_explicit_parent_path():
    leaf = h("leaf", "Revenue", 2)
    leaf["parent_id"] = "north"
    data = material(h("north", "North"), h("south", "South"), leaf)
    assert data["by_block"]["leaf"]["explicit_heading_paths"][0]["path"] == ["North"]
    result = checked(["North", "Revenue"], data, "leaf", REGIONS)
    assert result["correct"] is True
    assert [entry["source"]["block"] for entry in result["actual_sources"]] == ["north", "leaf"]
    assert checked(["South", "Revenue"], data, "leaf", REGIONS)["correct"] is False


def _context_index_fixture():
    data = material(h("root", "Financial review"), h("revenue", "Revenue"), b("first", "table"),
                    h("notes", "Notes:"), h("cost", "Cost"), b("table", "table"))
    return data, fact(data, "table")


def _fold_context_label(text):
    return text.strip().casefold()


@pytest.mark.parametrize("reverse", [False, True])
def test_normalized_duplicate_declarations_keep_the_first_compatible_original_source(reverse):
    data, item = _context_index_fixture()
    compatible = [
        {"text": " NOTES: ", "scope": ["Financial review", "Revenue"], "source": {"path": "first.md"}},
        {"text": "notes:", "scope": ["Financial review", "Revenue"], "source": {"path": "second.md"}},
    ]
    if reverse:
        compatible.reverse()
    labels = [{"text": "Notes:", "scope": ["South", "Revenue"], "source": {"path": "wrong-scope.md"}},
              *compatible]
    result = verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data,
                          context_labels=labels, canonicalize=_fold_context_label)
    assert result["correct"] is True
    declaration = result["display_context_sources"][0]["reference_declaration"]
    assert declaration["source"] == {"path": "second.md" if reverse else "first.md"}
    assert declaration["text"] == ("notes:" if reverse else " NOTES: ")


@pytest.mark.parametrize("replacement,accepted", [
    ({"source": {"path": "replacement.md", "lines": [19, 19]}}, True),
    ({"scope": ["South", "Revenue"]}, False),
    ({"role": "external_ancestor"}, False),
])
def test_new_declaration_objects_with_the_same_text_read_their_current_source_scope_and_role(replacement, accepted):
    data, item = _context_index_fixture()
    original = {"text": "Notes:", "scope": ["Financial review", "Revenue"],
                "source": {"path": "original.md", "lines": [9, 9]}}
    assert verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data,
                        context_labels=[original])["correct"] is True
    current = {**deepcopy(original), **replacement}
    result = verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data, context_labels=[current])
    assert result["correct"] is accepted
    if accepted:
        assert result["display_context_sources"][0]["reference_declaration"]["source"] == replacement["source"]
    else:
        assert result["display_context_sources"] == []


@pytest.mark.parametrize("field", ["source", "scope", "role", "text"])
def test_mutating_the_existing_declaration_list_cannot_reuse_old_metadata_or_labels(field):
    data, item = _context_index_fixture()
    labels = [{"text": "Notes:", "scope": ["Financial review", "Revenue"],
               "source": {"path": "reference.md", "lines": [9, 9]}}]
    assert verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data,
                        context_labels=labels)["correct"] is True
    if field == "source":
        labels[0]["source"]["lines"][:] = [21, 21]
    elif field == "scope":
        labels[0]["scope"][:] = ["South", "Revenue"]
    elif field == "role":
        labels[0]["role"] = "external_ancestor"
    else:
        labels[0]["text"] = "Other notes:"
    result = verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data, context_labels=labels)
    assert result["correct"] is (field == "source")
    if field == "source":
        assert result["display_context_sources"][0]["reference_declaration"]["source"]["lines"] == [21, 21]
    else:
        assert result["display_context_sources"] == []


def test_context_label_index_is_separate_for_each_canonicalization_policy():
    data, item = _context_index_fixture()
    labels = [{"text": " notes: ", "scope": ["Financial review", "Revenue"], "source": {"path": "reference.md"}}]
    for policy, accepted in [(_fold_context_label, True), (str.strip, False), (_fold_context_label, True)]:
        result = verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data,
                              context_labels=labels, canonicalize=policy)
        assert result["correct"] is accepted
        assert bool(result["display_context_sources"]) is accepted


def test_unhashable_callable_policy_preserves_the_same_scope_evidence_and_inputs():
    class UnhashablePolicy:
        __hash__ = None

        def __call__(self, text):
            return text.strip().casefold()

    data, item = _context_index_fixture()
    labels = [{"text": " notes: ", "scope": ["Financial review", "Revenue"], "source": {"path": "reference.md"}}]
    before = deepcopy((data, item, labels, FINANCIAL))
    result = verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data,
                          context_labels=labels, canonicalize=UnhashablePolicy())
    assert result["correct"] is True
    assert result["display_context_sources"][0]["reference_declaration"]["source"] == {"path": "reference.md"}
    assert (data, item, labels, FINANCIAL) == before


def test_repeated_scope_queries_do_not_recanonicalize_the_whole_label_catalogue():
    data, item = _context_index_fixture()
    labels = [{"text": f"Catalog entry {index}", "scope": ["South"], "source": {"path": "reference.md"}}
              for index in range(80)]
    labels.append({"text": "Notes:", "scope": ["Financial review", "Revenue"], "source": {"path": "reference.md"}})
    calls = []

    def count_catalogue(text):
        if text.startswith("Catalog entry "):
            calls.append(text)
        return text.strip()

    before = deepcopy((data, item, labels, FINANCIAL))
    for _ in range(2):
        result = verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data,
                              context_labels=labels, canonicalize=count_catalogue)
        assert result["correct"] is True
        assert result["actual_path"] == ["Financial review", "Cost"]
    assert len(calls) == 80
    assert (data, item, labels, FINANCIAL) == before


def test_a_canonicalizer_type_error_is_propagated_without_retrying_the_builder():
    data, item = _context_index_fixture()
    labels = [{"text": "Bad declaration", "scope": ["Financial review", "Revenue"],
               "source": {"path": "reference.md"}}]
    calls = []

    def reject_declaration(text):
        if text == "Bad declaration":
            calls.append(text)
            raise TypeError("invalid canonicalization policy input")
        return text.strip()

    with pytest.raises(TypeError, match="invalid canonicalization policy input"):
        verify_scope(["Financial review", "Cost"], item, FINANCIAL, contexts=data,
                     context_labels=labels, canonicalize=reject_declaration)
    assert calls == ["Bad declaration"]


def test_a_prose_target_cannot_append_its_text_as_a_missing_heading_leaf():
    prose = b("prose", text="Revenue")
    prose["parent_id"] = "north"
    data = material(h("north", "North"), prose)
    assert checked(["North", "Revenue"], data, "prose", REGIONS)["correct"] is False
