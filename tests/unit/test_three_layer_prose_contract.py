"""Independent public-entry prose identities, fragments, and SDK-reference oracles."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.saved_native import read_saved_native
from moparse_eval.three_layer import (
    compile_markdown,
    grade_layers,
    read_candidate,
    read_candidate_markdown,
)

PAY = "The board shall pay 17 credits only if approved by 4 directors."
NOTICE = "The clerk must publish the notice only if certified by 3 auditors."


def typed(*paragraphs, parent=None):
    blocks = [{"id": "north", "native_path": "#/north", "kind": "section_header", "heading_level": 1,
               "text": "North", "text_format": "plain"},
              {"id": "south", "native_path": "#/south", "kind": "section_header", "heading_level": 1,
               "text": "South", "text_format": "plain"}]
    blocks.extend({"id": f"prose-{i}", "native_path": f"#/prose/{i}", "kind": "text", "text": text,
                   "text_format": "plain"} for i, text in enumerate(paragraphs))
    relations = [{"type": "heading_of", "source": parent, "target": block["id"],
                  "evidence": "typed_native_reference"} for block in blocks[2:]] if parent else []
    return {"sample_id": "synthetic", "pipeline": "invented", "status": "completed",
            "pages": [{"page": 1, "blocks": blocks}], "relations": relations}


def docling(parent):
    # Body order and every printed byte stay fixed. Only the SDK parent changes.
    texts = [{"self_ref": "#/texts/0", "label": "section_header", "text": "North", "level": 1,
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/1", "label": "section_header", "text": "South", "level": 1,
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/2", "label": "text", "text": PAY,
              "parent": {"$ref": "#/texts/0" if parent == "north" else "#/texts/1"}, "prov": [{"page_no": 1}]}]
    document = {"body": {"self_ref": "#/body", "children": [{"$ref": item["self_ref"]} for item in texts]},
                "texts": texts, "tables": [], "pages": {"1": {"size": {"width": 100, "height": 100}}}}
    native = {"documents": [{"document": document}],
              "pages": [{"page": 1, "branch": "docling", "raw": {"native_document": "#/documents/0"}}]}
    base = {"sample_id": "synthetic", "pipeline": "invented", "status": "completed",
            "pages": [{"page": 1, "blocks": []}], "relations": []}
    return read_saved_native(native, base)


def b_rows(score):
    return [row for row in score["outcomes"] if row["layer"] == "B"]


@pytest.mark.parametrize("reader", [lambda parent: typed(PAY, parent=parent), docling], ids=["typed-link", "docling-parent"])
def test_preserving_all_literals_while_changing_only_native_parent_changes_binding(reader):
    requirement = compile_markdown("# North\n\n" + PAY + "\n\n# South")
    assert [(f["subject"], f["attribute"], f["value"], f["role"], f["scope"]) for f in requirement["business"]] == [
        ("the board", "pay", "pay 17 credits", "description", ["North"])]
    first, changed = (reader(parent) for parent in ["north", "south"])
    assert [b["text"] for b in first["pages"][0]["blocks"]] == [b["text"] for b in changed["pages"][0]["blocks"]]
    original = deepcopy(first)
    own, wrong = (read_candidate(observation) for observation in (first, changed))
    assert first == original
    good, bad = (grade_layers(requirement, graph) for graph in (own, wrong))
    assert good["publishable"] is True and bad["publishable"] is True
    assert good["layers"]["T"]["score"] == bad["layers"]["T"]["score"] == 100
    assert good["layers"]["B"]["denominator"] == good["layers"]["B"]["numerator"] == 1
    assert bad["layers"]["B"]["denominator"] == 1 and bad["layers"]["B"]["numerator"] == 0
    assert good["layers"]["L"]["score"] == 100 and bad["layers"]["L"]["numerator"] == 0
    assert own["business"][0]["scope"] == ["North"] and wrong["business"][0]["scope"] == ["South"]
    assert all(hit["decision"] == "rejected" for hit in b_rows(bad)[0]["retrieval"]["candidates"])
    assert all(hit["identity"]["scope"]["correct"] is False for hit in b_rows(bad)[0]["retrieval"]["candidates"])
    validate_evidence(good)
    validate_evidence(bad)


@pytest.mark.parametrize("pieces", [[PAY, NOTICE], [PAY + " " + NOTICE]])
def test_complete_sentence_blocks_and_merged_paragraph_have_the_same_full_requirements(pieces):
    reference = "# North\n\n" + PAY + "\n\n" + NOTICE + "\n\n# South"
    requirement = compile_markdown(reference)
    assert [(f["subject"], f["attribute"], f["role"]) for f in requirement["business"]] == [
        ("the board", "pay", "description"), ("the clerk", "publish", "description")]
    result = grade_layers(requirement, read_candidate(typed(*pieces, parent="north")))
    assert result["publishable"] is True and result["score"] == 100
    assert result["layers"]["B"]["denominator"] == 2
    assert result["layers"]["L"]["denominator"] == 5
    validate_evidence(result)


@pytest.mark.parametrize("pieces", [
    ["The board", "shall pay 17 credits only if approved by 4 directors."],
    ["The board shall pay 17 credits", "only if approved by 4 directors."],
    ["The board shall pay 17 credits only if approved by", "4 directors."],
])
def test_legal_same_scope_sentence_fragments_retain_complete_business_and_original_sources(pieces):
    requirement = compile_markdown("# North\n\n" + PAY + "\n\n# South")
    graph = read_candidate(typed(*pieces, parent="north"))
    result = grade_layers(requirement, graph)
    assert result["publishable"] is True
    assert result["layers"]["T"]["score"] == result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    assert len(graph["business"]) == 1
    [fact] = graph["business"]
    assert fact["value"] == "pay 17 credits" and fact["qualifiers"]["condition"] == "approved by 4 directors"
    fragments = fact["source"].get("joined_fragments", [])
    assert len(fragments) == len(pieces)
    assert [f["source"]["path"] for f in fragments] == [f"#/prose/{i}" for i in range(len(pieces))]
    assert [f["text"] for f in fragments] == pieces
    joined = " ".join(pieces)
    assert all(joined[slice(*f["joined_span"])] == f["text"] for f in fragments)
    validate_evidence(result)


def test_a_boundary_inside_digits_is_not_repaired_into_the_reference_quantity():
    result = grade_layers(compile_markdown("# North\n\n" + PAY + "\n\n# South"), read_candidate(typed(
        "The board shall pay 1", "7 credits only if approved by 4 directors.", parent="north")))
    assert result["layers"]["T"]["score"] < 100
    assert result["layers"]["B"]["numerator"] == 0


@pytest.mark.parametrize("kind,text", [("image", ""), ("section_header", "Other"),
                                        ("text", "Name:Interrupter")])
def test_real_intervening_objects_are_not_skipped_to_complete_a_sentence(kind, text):
    observation = typed("The board shall pay 17 credits", "only if approved by 4 directors.", parent="north")
    observation["pages"][0]["blocks"].insert(3, {"id": "interruption", "native_path": "#/interruption", "kind": kind,
                                                 "heading_level": 1, "text": text, "text_format": "plain"})
    graph = read_candidate(observation)
    assert not any(f["attribute"] == "pay" and f["qualifiers"].get("condition") == "approved by 4 directors"
                   for f in graph["business"])
    result = grade_layers(compile_markdown("# North\n\n" + PAY + "\n\n# South"), graph)
    assert result["publishable"] is False and result["layers"]["B"]["numerator"] == 0


def test_terminal_sentence_punctuation_prevents_reinterpreting_the_next_clause_as_its_condition():
    graph = read_candidate(typed("The board shall pay 17 credits.", "only if approved by 4 directors.", parent="north"))
    assert not any(f["qualifiers"].get("condition") == "approved by 4 directors" for f in graph["business"])
    result = grade_layers(compile_markdown("# North\n\n" + PAY + "\n\n# South"), graph)
    assert result["publishable"] is False and result["layers"]["B"]["numerator"] == 0


def test_explicitly_different_native_parents_prevent_joining_adjacent_sentence_fragments():
    observation = typed("The board shall pay 17 credits", "only if approved by 4 directors.", parent="north")
    observation["relations"][1]["source"] = "south"
    graph = read_candidate(observation)
    assert not any(f["attribute"] == "pay" and f["qualifiers"].get("condition") == "approved by 4 directors"
                   for f in graph["business"])
    result = grade_layers(compile_markdown("# North\n\n" + PAY + "\n\n# South"), graph)
    assert result["publishable"] is False and result["layers"]["B"]["numerator"] == 0


@pytest.mark.parametrize("mutation", ["path", "text", "span", "omit", "repeat", "order"])
def test_report_rejects_forged_joined_prose_even_when_business_trace_agrees_with_it(mutation):
    score = grade_layers(compile_markdown("# North\n\n" + PAY + "\n\n# South"), read_candidate(typed(
        "The board", "shall pay 17 credits only if approved by 4 directors.", parent="north")))
    validate_evidence(score)
    [row] = b_rows(score)
    [hit] = [hit for hit in row["retrieval"]["candidates"] if hit["decision"] == "accepted"]
    source = hit["candidate"]["source"]
    fragments = source["joined_fragments"]
    if mutation == "path":
        fragments[1]["source"]["path"] = "#/invented-fragment"
    elif mutation == "text":
        fragments[1]["text"] = "invented original wording"
    elif mutation == "span":
        fragments[1]["joined_span"] = [99, 100]
    elif mutation == "omit":
        fragments.pop()
    elif mutation == "repeat":
        fragments[1] = deepcopy(fragments[0])
    else:
        fragments.reverse()
    hit["source"] = deepcopy(source)
    hit["context_evidence"]["source"] = deepcopy(source)
    row["actual"] = [deepcopy(hit["candidate"])]
    with pytest.raises(ValueError, match="joined prose"):
        validate_evidence(score)


@pytest.mark.parametrize("before,after", [("17", "18"), ("4 directors", "3 directors"), ("shall pay", "shall not pay")])
def test_content_quantity_condition_and_negation_do_not_change_independent_logical_ownership(before, after):
    reference = "# Policy\n\n" + PAY + "\n\n" + NOTICE
    result = grade_layers(compile_markdown(reference), read_candidate_markdown(reference.replace(before, after, 1)))
    assert result["publishable"] is True
    assert result["layers"]["B"]["numerator"] == 1 and result["layers"]["B"]["denominator"] == 2
    assert result["layers"]["L"]["numerator"] == result["layers"]["L"]["denominator"] == 5
    [pay] = [r for r in b_rows(result) if r["expected"]["attribute"] == "pay"]
    assert "17" not in repr(pay["retrieval"]["query"]) and "4 directors" not in repr(pay["retrieval"]["query"])
    assert pay["retrieval"]["accepted"]
    validate_evidence(result)


def test_different_condition_roles_rebound_to_the_other_action_are_not_same_binding():
    reference = "# Policy\n\n" + PAY + "\n\n" + NOTICE
    requirement = compile_markdown(reference)
    assert [(edge["left"], edge["right"]) for edge in requirement["relations"] if edge["type"] == "condition_scope"] == [
        ({"role": "condition", "lexical_anchor": ["approved", "by", "directors"]},
         {"subject": "the board", "action": "pay", "scope": ["Policy"]}),
        ({"role": "condition", "lexical_anchor": ["certified", "by", "auditors"]},
         {"subject": "the clerk", "action": "publish", "scope": ["Policy"]})]
    moved = reference.replace("approved by 4 directors", "certified by 3 auditors").replace(
        "publish the notice only if certified by 3 auditors", "publish the notice only if approved by 4 directors")
    result = grade_layers(requirement, read_candidate_markdown(moved))
    scope_rows = [r for r in result["outcomes"] if r["layer"] == "L" and r["role"] == "condition_scope"]
    assert len(scope_rows) == 2 and all(r["outcome"] == "incorrect" for r in scope_rows)
    assert result["layers"]["L"]["numerator"] == 3 and result["layers"]["L"]["denominator"] == 5
    assert result["layers"]["B"]["numerator"] == 0 and result["layers"]["B"]["denominator"] == 2
    validate_evidence(result)


@pytest.mark.parametrize("entity,attribute", [("The borrower is Delta.", "borrower"), ("Borrower:Delta", "Borrower"),
                                              ("借款人为Delta", "借款人")])
def test_role_entity_is_an_additional_business_obligation_and_not_only_text(entity, attribute):
    reference = "# Parties\n\nName:Anchor\n\n" + entity
    requirement = compile_markdown(reference)
    assert len(requirement["business"]) == 2
    assert sorted((f["value"], f["role"]) for f in requirement["business"]) == [("Anchor", "identity"), ("Delta", "identity")]
    [fact] = [f for f in requirement["business"] if f["value"] == "Delta"]
    assert fact["attribute"] == attribute and fact["subject"] == ""
    assert entity[slice(*fact["attribute_source"]["text_span"])] == attribute
    assert entity[slice(*fact["value_source"]["text_span"])] == "Delta"
    result = grade_layers(requirement, read_candidate_markdown(reference.replace("Delta", "Kappa")))
    assert result["layers"]["B"]["numerator"] == 1 and result["layers"]["B"]["denominator"] == 2
    assert result["layers"]["L"]["score"] == 100
    assert result["layers"]["T"]["score"] < 100
    [entity_row] = [r for r in b_rows(result) if r["expected"]["value"] == "Delta"]
    assert "Delta" not in repr(entity_row["retrieval"]["query"])


def test_unknown_named_important_role_cannot_publish_with_a_smaller_business_denominator():
    reference = "# Parties\n\nName:Anchor\n\nThe collateral administrator is Delta."
    result = grade_layers(compile_markdown(reference), read_candidate_markdown(reference))
    assert result["publishable"] is False
    assert any("B" in b.get("layers", []) for b in result["blockers"])


@pytest.mark.parametrize("reference,candidate", [("The borrower is Delta.", "Borrower:Delta"),
                                                 ("Borrower:Delta", "The borrower is Delta.")])
def test_only_declared_english_party_role_case_varies_across_source_forms(reference, candidate):
    result = grade_layers(compile_markdown("# Parties\n\n" + reference), read_candidate_markdown("# Parties\n\n" + candidate))
    assert result["publishable"] is True
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["L"]["score"] == 100
    changed = grade_layers(compile_markdown("# Parties\n\n" + reference), read_candidate_markdown(
        "# Parties\n\n" + candidate.replace("Delta", "delta")))
    assert changed["layers"]["B"]["numerator"] == 0
    assert changed["layers"]["L"]["score"] == 100


def test_the_required_to_modal_is_not_reclassified_as_a_party_name():
    text = "# Policy\n\nThe borrower is required to pay 17 credits."
    requirement = compile_markdown(text)
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in requirement["business"]] == [
        ("the borrower", "pay", "pay 17 credits", "description")]
    result = grade_layers(requirement, read_candidate_markdown(text.replace("17", "18")))
    assert result["publishable"] is True
    assert result["layers"]["B"]["numerator"] == 0 and result["layers"]["B"]["denominator"] == 1
    assert result["layers"]["L"]["score"] == 100


@pytest.mark.parametrize("statement,subject,predicate,obj", [
    ("Delta owns Kappa.", "Delta", "own", "Kappa"),
    ("The board approved the dividend.", "The board", "approve", "the dividend"),
    ("Delta invested in new warehouses.", "Delta", "invest", "in new warehouses"),
    ("The company reported higher revenue.", "The company", "report", "higher revenue"),
])
@pytest.mark.parametrize("anchor", ["", "Name:Anchor\n\n"], ids=["sole-business-claim", "independent-identity-also-present"])
def test_important_supported_predicates_supply_an_independent_source_bound_business_requirement(statement, subject, predicate, obj, anchor):
    reference = "# Governance\n\n" + anchor + statement
    requirement = compile_markdown(reference)
    expected_line = 5 if anchor else 3
    [claim] = [f for f in requirement["business"] if f["role"] == "description"]
    assert (claim["subject"], claim["attribute"], claim["value"]) == (subject, predicate, obj)
    assert claim["source"]["path"] == "<markdown>" and claim["source"]["lines"] == [expected_line, expected_line]
    assert len(requirement["business"]) == 1 + bool(anchor)
    for pipeline in ["P01", "P05", "P08"]:
        result = grade_layers(requirement, read_candidate_markdown(reference, pipeline=pipeline))
        assert result["publishable"] is True and result["layers"]["B"]["score"] == 100
        wrong = grade_layers(requirement, read_candidate_markdown(reference.replace(obj, "OtherObject"), pipeline=pipeline))
        [row] = [row for row in b_rows(wrong) if row["expected"]["attribute"] == predicate]
        assert row["outcome"] == "incorrect"


@pytest.mark.parametrize("statement", [
    "本年票面利率为2.4%。派息方案为：每5张债券（面值500元）派息12元。",
    "付息对象为：登记在册的全部债券持有人。当天申请转股及已转股的债券不能获得利息。",
])
def test_a_colon_cannot_disguise_unread_business_assertions_as_one_complete_metric(statement):
    reference = "# Terms\n\nName:Anchor\n\n" + statement
    result = grade_layers(compile_markdown(reference), read_candidate_markdown(reference))
    assert result["publishable"] is False
    assert result["layers"]["B"]["complete"] is False
    assert any("B" in blocker.get("layers", []) and blocker.get("text") == statement
               and blocker["source"].get("lines") == [5, 5] for blocker in result["blockers"])


def test_numbered_identifiers_times_and_urls_are_valid_field_literals_not_hidden_prose_assertions():
    text = "# Records\n\nType17 Revenue:5\n\nDate and time:2028-05-02 9:00\n\nLocation:https://example.test/Room17"
    requirement = compile_markdown(text)
    assert [(f["attribute"], f["value"]) for f in requirement["business"]] == [
        ("Type17 Revenue", "5"), ("Date and time", "2028-05-02 9:00"), ("Location", "https://example.test/Room17")]
    result = grade_layers(requirement, read_candidate_markdown(text))
    assert result["publishable"] is True and result["layers"]["B"]["denominator"] == 3
    validate_evidence(result)


FIELDS = "# Meeting\n\nAdmission: You will need Control.\n\nRefund: You will need Account."
FIELD_HEADINGS = "# Meeting\n\n## Admission\n\nYou will need Control.\n\n## Refund\n\nYou will need Account."
NAMED_ACTIONS = "# Contracts\n\n- Name: Delta\n  - He shall pay 17 credits.\n- Name: Kappa\n  - He shall pay 5 credits."


def test_logical_field_labels_locate_each_assertion_before_its_value_is_compared():
    requirement = compile_markdown(FIELDS)
    assert [(f["scope"], f["subject"], f["attribute"], f["value"], f["role"]) for f in requirement["business"]] == [
        (["Meeting", "Admission"], "you", "need", "need Control", "description"),
        (["Meeting", "Refund"], "you", "need", "need Account", "description")]
    swapped = FIELDS.replace("Control", "swap").replace("Account", "Control").replace("swap", "Account")
    result = grade_layers(requirement, read_candidate_markdown(swapped))
    assert result["publishable"] is True
    assert result["layers"]["B"]["numerator"] == 0 and result["layers"]["B"]["denominator"] == 2
    assert result["layers"]["L"]["score"] == 100
    for row, label, actual in zip(b_rows(result), ["Admission", "Refund"], ["need Account", "need Control"], strict=True):
        assert row["retrieval"]["query"]["scope"] == ["Meeting", label]
        assert "Control" not in repr(row["retrieval"]["query"]) and "Account" not in repr(row["retrieval"]["query"])
        assert [f["value"] for f in row["actual"]] == [actual]
        assert any(h["decision"] == "rejected" and not h["identity"]["scope"]["correct"]
                   for h in row["retrieval"]["candidates"])


@pytest.mark.parametrize("reference,candidate", [(FIELDS, FIELD_HEADINGS), (FIELD_HEADINGS, FIELDS)])
def test_explicit_same_field_label_as_own_heading_preserves_business_and_relation_scope(reference, candidate):
    result = grade_layers(compile_markdown(reference), read_candidate_markdown(candidate))
    assert result["publishable"] is True
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 2
    assert result["layers"]["L"]["score"] == 100


def test_same_actor_action_in_explicit_name_parents_retains_record_position_and_source():
    requirement = compile_markdown(NAMED_ACTIONS)
    assert len(requirement["business"]) == 4
    descriptions = [f for f in requirement["business"] if f["role"] == "description"]
    assert [(f["subject"], f["attribute"], f["value"], f["identity_facets"]) for f in descriptions] == [
        ("he", "pay", "pay 17 credits", {"record": {"Name": "Delta"}}),
        ("he", "pay", "pay 5 credits", {"record": {"Name": "Kappa"}})]
    assert [f["record_evidence"][0]["source"]["lines"] for f in descriptions] == [[3, 3], [5, 5]]
    self_grade = grade_layers(requirement, read_candidate_markdown(NAMED_ACTIONS))
    assert self_grade["publishable"] is True and self_grade["layers"]["B"]["numerator"] == 4
    swapped = NAMED_ACTIONS.replace("17", "swap").replace("5", "17").replace("swap", "5")
    result = grade_layers(requirement, read_candidate_markdown(swapped))
    assert result["publishable"] is True
    assert result["layers"]["T"]["score"] == result["layers"]["L"]["score"] == 100
    assert result["layers"]["B"]["numerator"] == 2 and result["layers"]["B"]["denominator"] == 4
    rows = [r for r in b_rows(result) if r["role"] == "description"]
    for row, name, actual in zip(rows, ["Delta", "Kappa"], ["pay 5 credits", "pay 17 credits"], strict=True):
        query = row["retrieval"]["query"]
        assert query["subject"] == "he" and query["identity_facets"] == {"record": {"Name": name}}
        assert "17" not in repr(query) and "5" not in repr(query)
        assert [f["value"] for f in row["actual"]] == [actual]
    assert all("Delta" not in repr(r["retrieval"]["query"]) and "Kappa" not in repr(r["retrieval"]["query"])
               for r in b_rows(result) if r["role"] == "identity")


def test_field_condition_content_is_compared_after_scope_without_becoming_query_identity():
    text = FIELDS.replace("need Control.", "need Control only if approved by 4 directors.")
    changed = text.replace("4 directors", "3 directors")
    result = grade_layers(compile_markdown(text), read_candidate_markdown(changed))
    assert result["layers"]["B"]["numerator"] == 1 and result["layers"]["B"]["denominator"] == 2
    [row] = [r for r in b_rows(result) if r["expected"].get("printed_label") == "Admission"]
    assert row["retrieval"]["query"]["scope"] == ["Meeting", "Admission"]
    assert "Control" not in repr(row["retrieval"]["query"]) and "4 directors" not in repr(row["retrieval"]["query"])
    assert row["retrieval"]["accepted"]


def _docling_context_texts(texts, roots):
    document = {"body": {"self_ref": "#/body", "children": [{"$ref": f"#/texts/{i}"} for i in roots]},
                "texts": texts, "tables": [], "pages": {"1": {"size": {"width": 100, "height": 100}}}}
    native = {"documents": [{"document": document}],
              "pages": [{"page": 1, "branch": "docling", "raw": {"native_document": "#/documents/0"}}]}
    original = {"sample_id": "synthetic", "pipeline": "invented", "status": "completed",
                "pages": [{"page": 1, "blocks": []}], "relations": []}
    return read_saved_native(native, original)


def test_saved_docling_field_label_scope_is_proved_by_its_actual_text_not_a_missing_heading():
    texts = [{"self_ref": "#/texts/0", "label": "section_header", "level": 1, "text": "Meeting",
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/1", "label": "text", "text": "Admission: You will need Account.",
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/2", "label": "text", "text": "Refund: You will need Control.",
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]}]
    observation = _docling_context_texts(texts, [0, 1, 2])
    graph = read_candidate(observation)
    assert [event["text"] for event in graph["native_context"]["heading_events"]] == ["Meeting"]
    result = grade_layers(compile_markdown(FIELDS), graph)
    assert result["publishable"] is True
    assert result["layers"]["B"]["numerator"] == 0 and result["layers"]["B"]["denominator"] == 2
    assert result["layers"]["L"]["score"] == 100
    for row, cell in zip(b_rows(result), [1, 2], strict=True):
        assert len(row["actual"]) == 1
        own = row["actual"][0]
        assert own["field_label_evidence"]["source"]["path"] == f"#/documents/0/document/texts/{cell}"
        assert own["field_label_evidence"]["source"]["text_span"] == ([0, 9] if cell == 1 else [0, 6])
    validate_evidence(result)


def test_saved_docling_name_parent_references_locate_modal_children_without_pronoun_resolution():
    texts = [{"self_ref": "#/texts/0", "label": "section_header", "level": 1, "text": "Contracts",
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/1", "label": "list_item", "text": "Name: Delta", "children": [{"$ref": "#/texts/2"}],
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/2", "label": "text", "text": "He shall pay 5 credits.",
              "parent": {"$ref": "#/texts/1"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/3", "label": "list_item", "text": "Name: Kappa", "children": [{"$ref": "#/texts/4"}],
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/4", "label": "text", "text": "He shall pay 17 credits.",
              "parent": {"$ref": "#/texts/3"}, "prov": [{"page_no": 1}]}]
    observation = _docling_context_texts(texts, [0, 1, 3])
    assert all("public_list_parents" not in b for b in observation["pages"][0]["blocks"])
    graph = read_candidate(observation)
    result = grade_layers(compile_markdown(NAMED_ACTIONS), graph)
    assert result["publishable"] is True
    assert result["layers"]["B"]["numerator"] == 2 and result["layers"]["B"]["denominator"] == 4
    assert result["layers"]["L"]["score"] == 100
    actions = [r for r in b_rows(result) if r["role"] == "description"]
    for row, name, native_parent in zip(actions, ["Delta", "Kappa"], [1, 3], strict=True):
        assert row["retrieval"]["query"]["identity_facets"] == {"record": {"Name": name}}
        assert len(row["actual"]) == 1 and row["actual"][0]["subject"] == "he"
        assert row["actual"][0]["record_evidence"][0]["source"]["path"] == f"#/documents/0/document/texts/{native_parent}"
    validate_evidence(result)


@pytest.mark.parametrize("candidate", ["# Meeting\n\nRefund: You will need Control.",
                                        "# Meeting\n\nEligibility: You will need Control.",
                                        "# Other\n\nAdmission: You will need Control."])
def test_a_matching_value_never_supplies_a_different_field_or_outer_scope(candidate):
    requirement = compile_markdown("# Meeting\n\nAdmission: You will need Control.")
    result = grade_layers(requirement, read_candidate_markdown(candidate))
    assert result["layers"]["B"]["numerator"] == 0 and result["layers"]["B"]["denominator"] == 1
    [row] = b_rows(result)
    assert not row["retrieval"]["accepted"]
    assert all(hit["decision"] == "rejected" and not hit["identity"]["scope"]["correct"]
               for hit in row["retrieval"]["candidates"])


def _one_docling_field(text):
    return _docling_context_texts([
        {"self_ref": "#/texts/0", "label": "section_header", "level": 1, "text": "Meeting",
         "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
        {"self_ref": "#/texts/1", "label": "text", "text": text,
         "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
    ], [0, 1])


@pytest.mark.parametrize("mutation", ["path", "span"])
def test_report_rejects_forged_field_label_origin_with_otherwise_consistent_trace(mutation):
    text = "Admission: You will need Control."
    score = grade_layers(compile_markdown("# Meeting\n\n" + text), read_candidate(_one_docling_field(text)))
    validate_evidence(score)
    original_text_evidence = deepcopy(score["text_evidence"])
    changed = []

    def mutate(value):
        if isinstance(value, dict):
            if value.get("path") == "#/documents/0/document/texts/1" and value.get("text_span") == [0, 9]:
                if mutation == "path":
                    value["path"] = "#/nonexistent-field-origin"
                else:
                    value["text_span"] = [1, 10]
                changed.append(True)
            for item in value.values():
                mutate(item)
        elif isinstance(value, list):
            for item in value:
                mutate(item)

    # Mutate all repeated candidate proof claims together; source snapshots
    # and literal outcomes remain unchanged, so internal agreement is no proof.
    for row in score["outcomes"]:
        if row["layer"] != "T":
            mutate(row)
    assert changed and score["text_evidence"] == original_text_evidence
    with pytest.raises(ValueError):
        validate_evidence(score)


def test_docling_second_sentence_inherits_the_real_field_source_without_offsetting_it():
    text = "Admission: You will need Control. You must confirm identity."
    graph = read_candidate(_one_docling_field(text))
    facts = [f for f in graph["business"] if f["role"] == "description"]
    assert [(f["attribute"], f["value"], f["scope"]) for f in facts] == [
        ("need", "need Control", ["Meeting", "Admission"]),
        ("confirm", "confirm identity", ["Meeting", "Admission"])]
    second = facts[1]
    assert second["source"]["text_span"] == [34, 59]
    assert second["value_source"]["text_span"] == [43, 59]
    assert text[34:59] == "You must confirm identity"
    assert text[43:59] == "confirm identity"
    assert second["field_label_evidence"]["source"]["path"] == "#/documents/0/document/texts/1"
    assert second["field_label_evidence"]["source"]["text_span"] == [0, 9]
    score = grade_layers(compile_markdown("# Meeting\n\n" + text), graph)
    assert score["publishable"] is True and score["layers"]["B"]["numerator"] == 2
    assert score["layers"]["L"]["score"] == 100
    validate_evidence(score)


def test_same_native_record_name_in_another_outer_context_cannot_supply_the_value():
    reference = "# North\n\n- Name: Delta\n  - He shall pay 17 credits.\n\n# South\n\n- Name: Delta\n  - He shall pay 5 credits."
    texts = []
    for heading, name, action, amount in [(0, 1, 2, "5"), (3, 4, 5, "17")]:
        texts.extend([
            {"self_ref": f"#/texts/{heading}", "label": "section_header", "level": 1,
             "text": "North" if heading == 0 else "South", "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
            {"self_ref": f"#/texts/{name}", "label": "list_item", "text": "Name: Delta",
             "children": [{"$ref": f"#/texts/{action}"}], "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
            {"self_ref": f"#/texts/{action}", "label": "text", "text": f"He shall pay {amount} credits.",
             "parent": {"$ref": f"#/texts/{name}"}, "prov": [{"page_no": 1}]},
        ])
    graph = read_candidate(_docling_context_texts(texts, [0, 1, 3, 4]))
    score = grade_layers(compile_markdown(reference), graph)
    assert score["publishable"] is True
    assert score["layers"]["B"]["numerator"] == 2 and score["layers"]["B"]["denominator"] == 4
    for row, scope, amount in zip([r for r in b_rows(score) if r["role"] == "description"], ["North", "South"],
                                  ["pay 5 credits", "pay 17 credits"], strict=True):
        assert row["retrieval"]["query"]["scope"] == [scope]
        assert [f["value"] for f in row["actual"]] == [amount]
        assert any(hit["decision"] == "rejected" and not hit["identity"]["scope"]["correct"]
                   for hit in row["retrieval"]["candidates"])
    validate_evidence(score)


@pytest.mark.parametrize("text,prefix,actor,items", [
    ("To improve coverage, we are expanding into three operations: freight transport, parcel delivery, and warehousing. "
     "Our capital allocation will exceed prior spending.",
     "To improve coverage, we are expanding into three operations", "we",
     ["freight transport", "parcel delivery", "warehousing"]),
    ("We are prioritizing three projects: solar generation, power storage, and grid control. "
     "The committee shall review funding.",
     "We are prioritizing three projects", "we", ["solar generation", "power storage", "grid control"]),
    ("To reduce exposure, management is directing investment to three regions: North, South, and West. "
     "Management must publish the plan.",
     "To reduce exposure, management is directing investment to three regions", "management", ["North", "South", "West"]),
])
def test_business_preamble_and_enumeration_cannot_become_the_later_statement_field_identity(text, prefix, actor, items):
    reference = "# Plan\n\n" + text
    requirement = compile_markdown(reference)
    score = grade_layers(requirement, read_candidate_markdown(reference))
    assert score["layers"]["T"]["score"] == 100
    assert all(piece in " ".join(atom["text"] for atom in requirement["text"]) for piece in [prefix, *items])
    # The preamble is itself an assertion being tested, not a field identifier
    # by which a later modal sentence can inherit an answer-bearing scope.
    for row in b_rows(score):
        query = row["retrieval"]["query"]
        assert prefix not in repr(query)
        assert all(item not in repr(query) for item in items)
    assert all(f["attribute"] != prefix and prefix not in f["scope"] for f in requirement["business"])
    first_end = text.index(".") + 1
    interpreted = [f for f in requirement["business"] if f["role"] == "description" and f["subject"] == actor
                   and f["scope"] == ["Plan"] and f["source"].get("text_span", [len(text), len(text)])[0] < first_end]
    all_items_interpreted = interpreted and all(any(item in f["value"] for f in interpreted) for item in items)
    if not all_items_interpreted:
        pending = [b for b in requirement["blockers"] if b.get("source", {}).get("path") == "<markdown>"
                   and b["source"].get("lines") == [3, 3] and all(item in b.get("text", "") for item in items)]
        assert pending
        assert {"B", "L"} <= {layer for b in pending for layer in b.get("layers", [])}
        assert score["publishable"] is False


@pytest.mark.parametrize("text,forbidden_subject", [
    ("In 2027, we announced that our investment will exceed prior spending.", ["2027", "announced"]),
    ("The clerk reported that the board shall pay 17 credits.", ["reported", "17"]),
])
def test_reported_modal_subject_cannot_swallow_an_unread_assertion_or_reporting_period(text, forbidden_subject):
    reference = "# Statement\n\n" + text
    requirement = compile_markdown(reference)
    score = grade_layers(requirement, read_candidate_markdown(reference))
    assert score["layers"]["T"]["score"] == 100
    for row in b_rows(score):
        subject = row["retrieval"]["query"]["subject"]
        assert all(part not in subject for part in forbidden_subject)
    pending = [b for b in requirement["blockers"] if b.get("text") == text
               and b.get("source", {}).get("path") == "<markdown>" and b["source"].get("lines") == [3, 3]]
    if text.startswith("The clerk reported") and requirement.get("logical_statements"):
        [fact] = requirement["business"]
        assert fact["subject"] == "the board" and fact["attribute"] == "pay"
        assert fact["qualifiers"]["reporting"] == [{"subject": "The clerk", "attribute": "report", "polarity": "positive", "tense": "past"}]
        assert score["publishable"] is False
        assert any(b["reason"] == "narrative_comparison_features_not_validated" for b in score["blockers"])
    else:
        assert pending
        assert {"B", "L"} <= {layer for b in pending for layer in b.get("layers", [])}
    assert score["publishable"] is False


def test_short_direct_modal_actor_remains_a_complete_supported_assertion():
    text = "# Statement\n\nThe board shall pay 17 credits."
    requirement = compile_markdown(text)
    assert [(f["subject"], f["attribute"], f["value"], f["role"]) for f in requirement["business"]] == [
        ("the board", "pay", "pay 17 credits", "description")]
    score = grade_layers(requirement, read_candidate_markdown(text))
    assert score["publishable"] is True and score["layers"]["B"]["numerator"] == score["layers"]["B"]["denominator"] == 1
    [row] = b_rows(score)
    assert row["retrieval"]["query"]["subject"] == "the board"
    assert "17" not in repr(row["retrieval"]["query"])


@pytest.mark.parametrize("reference,candidate", [
    ("# Meeting\n\nAdmission: You will need Control.", "# Meeting\n\n## Admission\n\nYou will need Control."),
    ("# Meeting\n\n## Admission\n\nYou will need Control.", "# Meeting\n\nAdmission: You will need Control."),
])
def test_short_logical_field_and_own_heading_preserve_all_three_layers_and_38_text_characters(reference, candidate):
    requirement = compile_markdown(reference)
    graph = read_candidate_markdown(candidate)
    score = grade_layers(requirement, graph)
    assert score["publishable"] is True
    assert score["layers"]["T"]["denominator"] == score["layers"]["T"]["numerator"] == 38
    assert all(score["layers"][layer]["score"] == 100 for layer in ["T", "L", "B"])
    for text, own in [(reference, requirement), (candidate, graph)]:
        assert sorted(atom["text"] for atom in own["text"]) == ["Admission", "Meeting", "You will need Control."]
        if "Admission:" in text:
            [label] = [atom for atom in own["text"] if atom["text"] == "Admission"]
            assert label["source"]["lines"] == [3, 3] and label["source"]["text_span"] == [0, 9]
    validate_evidence(score)


def test_two_sentence_docling_field_body_matches_heading_text_without_source_offset_loss():
    raw = "Admission: You will need Control. You must confirm identity."
    reference = "# Meeting\n\n## Admission\n\nYou will need Control. You must confirm identity."
    graph = read_candidate(_one_docling_field(raw))
    score = grade_layers(compile_markdown(reference), graph)
    assert score["publishable"] is True
    assert score["layers"]["T"]["denominator"] == score["layers"]["T"]["numerator"] == 64
    assert all(score["layers"][layer]["score"] == 100 for layer in ["T", "L", "B"])
    [label] = [atom for atom in graph["text"] if atom["text"] == "Admission"]
    assert label["source"]["path"] == "#/documents/0/document/texts/1"
    assert label["source"]["text_span"] == [0, 9]
    body = [atom for atom in graph["text"] if atom["text"] in {"You will need Control.", "You must confirm identity."}]
    assert [(atom["text"], atom["source"]["text_span"]) for atom in body] == [
        ("You will need Control.", [11, 33]), ("You must confirm identity.", [34, 60])]
    [second] = [f for f in graph["business"] if f["attribute"] == "confirm"]
    assert second["source"]["text_span"] == [34, 59]
    assert second["value_source"]["text_span"] == [43, 59]
    assert second["field_label_evidence"]["source"]["text_span"] == [0, 9]
    validate_evidence(score)
