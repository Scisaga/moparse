"""Manually fixed prose facts and relation endpoints, without corpus access."""

from __future__ import annotations

import copy

import pytest

from moparse_eval.prose_requirements import (
    prose_endpoint,
    read_prose_requirements,
    read_prose_sequence,
)

SOURCE = {"path": "<printed-policy>", "lines": [7, 7]}
POLICY = "The board shall not pay 17 credits unless approved by 4 directors."


def project(fact):
    return fact["subject"], fact["attribute"], fact["value"], fact["qualifiers"], fact["role"]


def test_negated_conditional_obligation_is_one_complete_business_requirement():
    result = read_prose_requirements(POLICY, SOURCE)
    assert result["matched"] is True and result["blockers"] == []
    assert len(result["facts"]) == 1
    [fact] = result["facts"]
    assert project(fact) == (
        "the board", "pay", "pay 17 credits",
        {"modality": "shall", "polarity": "negative", "condition": "approved by 4 directors", "condition_operator": "unless"},
        "description",
    )
    assert fact["source"]["path"] == SOURCE["path"]
    assert fact["value_source"]["text_span"] == [20, 34]
    assert fact["qualifier_sources"]["condition"]["text_span"] == [42, 65]
    assert fact["qualifier_sources"]["polarity"]["text_span"] == [16, 19]


@pytest.mark.parametrize("before,after,key,wanted", [
    ("17", "18", "value", "pay 18 credits"),
    ("shall not", "shall", "polarity", "positive"),
    ("unless", "if", "condition_operator", "if"),
    ("4 directors", "3 directors", "condition", "approved by 3 directors"),
])
def test_actual_value_negation_and_condition_changes_are_kept_as_own_differences(before, after, key, wanted):
    original = read_prose_requirements(POLICY, SOURCE)["facts"][0]
    changed = read_prose_requirements(POLICY.replace(before, after), SOURCE)["facts"][0]
    assert changed["value"] == wanted if key == "value" else changed["qualifiers"][key] == wanted
    assert project(changed) != project(original)
    assert changed["attribute"] == "pay" and changed["subject"] == "the board"


def test_front_and_post_conditions_keep_the_same_complete_requirement():
    front = "If approved by 4 directors, The board shall pay 17 credits."
    post = "The board shall pay 17 credits if approved by 4 directors."
    before, after = (read_prose_requirements(text, SOURCE) for text in (front, post))
    assert before["blockers"] == after["blockers"] == []
    assert len(before["facts"]) == len(after["facts"]) == 1
    assert project(before["facts"][0]) == project(after["facts"][0])


def test_exception_is_preserved_separately_from_a_condition_or_missing_text():
    result = read_prose_requirements("The board must report every transfer except transfers below 5 credits.", SOURCE)
    assert result["blockers"] == [] and len(result["facts"]) == 1
    assert project(result["facts"][0]) == (
        "the board", "report", "report every transfer",
        {"modality": "must", "polarity": "positive", "exception": "transfers below 5 credits", "exception_operator": "except"},
        "description",
    )
    [relation] = result["relations"]
    assert relation["type"] == "exception_scope"
    assert relation["left"] == {"role": "exception", "lexical_anchor": ["transfers", "below"]}


def test_named_eligibility_field_preserves_the_full_condition_and_date():
    text = "You can attend and vote at the 2027 Meeting if you were a stockholder of record at the close of business on April 28, 2027."
    result = read_prose_requirements(text, SOURCE, label="Record date")
    assert len(result["facts"]) == 1
    assert [blocker["reason"] for blocker in result["blockers"]] == ["coordinated_action_granularity_unsupported"]
    assert result["blockers"][0]["layers"] == ["B"]
    assert result["pending_requirements"][0]["actions"] == ["attend", "vote"]
    assert project(result["facts"][0]) == (
        "you", "attend and vote", "attend and vote at the 2027 Meeting",
        {"modality": "can", "polarity": "positive", "condition": "you were a stockholder of record at the close of business on April 28, 2027", "condition_operator": "if"},
        "description",
    )
    assert result["facts"][0]["printed_label"] == "Record date"


def test_purpose_and_required_token_are_explicit_in_the_business_requirement():
    result = read_prose_requirements("To participate, you will need the Control Number included on your notice or printed card.", SOURCE)
    assert result["blockers"] == [] and len(result["facts"]) == 1
    assert project(result["facts"][0]) == (
        "you", "need", "need the Control Number included on your notice or printed card",
        {"modality": "will", "polarity": "positive", "purpose": "participate"}, "description",
    )
    assert result["relations"][0]["type"] == "purpose_scope"
    assert result["relations"][0]["left"] == {"role": "purpose", "lexical_anchor": ["participate"]}


def test_the_same_raw_labeled_entry_is_read_without_erasing_label_text_or_losing_source_offsets():
    text = "Admission: To participate, you will need the Control Number."
    result = read_prose_requirements(text, SOURCE, label="Admission")
    assert result["blockers"] == [] and len(result["facts"]) == 1
    [fact] = result["facts"]
    assert fact["attribute"] == "need" and fact["qualifiers"]["purpose"] == "participate"
    assert fact["label_source"]["text_span"] == [0, 11]
    assert result["text_spans"][0]["text"] == text
    start, end = fact["value_source"]["text_span"]
    assert text[start:end] == "need the Control Number"


def test_nested_value_source_keeps_its_existing_offset_in_the_original_printed_field():
    result = read_prose_requirements(POLICY, {**SOURCE, "text_span": [13, 13 + len(POLICY)]})
    assert result["facts"][0]["value_source"]["text_span"] == [33, 47]
    assert result["facts"][0]["qualifier_sources"]["condition"]["text_span"] == [55, 78]


def test_conditional_agenda_item_requires_its_own_declared_agenda_context():
    result = read_prose_requirements("Three stockholder proposals, if properly presented", SOURCE, parents=["Items of business:"])
    assert result["blockers"] == [] and len(result["facts"]) == 1
    assert project(result["facts"][0]) == (
        "", "stockholder proposals", "Three stockholder proposals",
        {"polarity": "positive", "condition": "properly presented", "condition_operator": "if"}, "description",
    )
    unsupported = read_prose_requirements("Three stockholder proposals, if properly presented", SOURCE)
    assert unsupported["facts"] == [] and unsupported["blockers"]


def test_an_inserted_label_between_modal_and_action_is_not_skipped_to_repair_a_sentence():
    result = read_prose_requirements("To participate, you will admission: need the Control Number.", SOURCE)
    assert result["matched"] is True
    assert result["facts"] == []
    assert result["issues"][0]["reason"] == "interrupted_modal_predicate"
    assert "admission:" in result["issues"][0]["text"]


def test_alternative_specific_conditional_scope_is_not_flattened_to_the_whole_permission():
    result = read_prose_requirements("You may vote online or, if you have a paper card, by mailing it.", SOURCE)
    assert result["matched"] is True
    assert result["facts"] == []
    assert result["blockers"][0]["reason"] == "branched_conditional_scope_unsupported"


def unit(identifier, text, *, scope=("Policy",), **extra):
    return {"id": identifier, "kind": "paragraph", "text": text, "scope": list(scope),
            "source": {"path": "<actual-prose>", "lines": [int(identifier[-1]) + 1] * 2}, **extra}


def edges(result):
    return [(edge["type"], edge["left"], edge["right"]) for edge in result["relations"]]


def test_content_changes_do_not_automatically_destroy_proved_prose_order_or_parentage():
    original = [unit("p0", "The board shall pay 17 credits."), unit("p1", "The clerk must publish the notice.")]
    changed = copy.deepcopy(original)
    changed[0]["text"] = "The board shall not pay 18 credits."
    a, b = read_prose_sequence(original), read_prose_sequence(changed)
    assert a["blockers"] == b["blockers"] == []
    assert len(a["endpoints"]) == len(b["endpoints"]) == 2
    assert len(a["relations"]) == len(b["relations"]) == 3
    assert [edge[0] for edge in edges(a)].count("prose_reading_order") == 1
    assert edges(a) == edges(b)


@pytest.mark.parametrize("before,after", [("17", "18"), ("4 directors", "3 directors"), ("not pay", "pay")])
def test_condition_attachment_keeps_its_independently_identified_roles_when_content_changes(before, after):
    a = read_prose_requirements(POLICY, SOURCE)
    b = read_prose_requirements(POLICY.replace(before, after), SOURCE)
    assert len(a["relations"]) == len(b["relations"]) == 1
    assert edges(a) == edges(b)
    [relation] = a["relations"]
    assert relation["left"] == {"role": "condition", "lexical_anchor": ["approved", "by", "directors"]}
    assert relation["right"] == {"subject": "the board", "action": "pay", "scope": []}
    assert "17" not in repr(relation["left"]) + repr(relation["right"])
    assert "4" not in repr(relation["left"]) + repr(relation["right"])
    assert relation["binding_evidence"]["qualifier_text"] == "approved by 4 directors"


def test_swapping_only_the_printed_condition_bindings_changes_the_logical_scope_edges():
    first = "The board shall pay 17 credits if approved. The clerk must publish the notice if registered."
    second = "The board shall pay 17 credits if registered. The clerk must publish the notice if approved."
    a, b = read_prose_requirements(first, SOURCE), read_prose_requirements(second, SOURCE)
    assert a["blockers"] == b["blockers"] == []
    assert len(a["relations"]) == len(b["relations"]) == 2
    assert edges(a) != edges(b)
    assert a["relations"][0]["left"]["lexical_anchor"] == ["approved"]
    assert b["relations"][0]["left"]["lexical_anchor"] == ["registered"]


def test_reordering_two_distinct_prose_actions_changes_only_its_order_relation():
    first, second = unit("p0", "The board shall pay 17 credits."), unit("p1", "The clerk must publish the notice.")
    a, b = read_prose_sequence([first, second]), read_prose_sequence([second, first])
    assert a["blockers"] == b["blockers"] == []
    before = next(edge for edge in a["relations"] if edge["type"] == "prose_reading_order")
    after = next(edge for edge in b["relations"] if edge["type"] == "prose_reading_order")
    assert before["left"] == after["right"] and before["right"] == after["left"]


def test_parent_reference_change_preserves_all_words_but_changes_the_parent_relation():
    units = [
        {"id": "north", "kind": "heading", "text": "North", "source": {"path": "<headings>", "lines": [1, 1]}},
        {"id": "south", "kind": "heading", "text": "South", "source": {"path": "<headings>", "lines": [2, 2]}},
        unit("p0", "The board shall pay 17 credits.", parent_id="north", scope=()),
    ]
    changed = copy.deepcopy(units)
    changed[-1]["parent_id"] = "south"
    a, b = read_prose_sequence(units), read_prose_sequence(changed)
    assert a["blockers"] == b["blockers"] == []
    assert [item["text"] for item in units] == [item["text"] for item in changed]
    assert edges(a) != edges(b)
    assert a["endpoints"][0]["scope"] == ["North"] and b["endpoints"][0]["scope"] == ["South"]


def test_same_role_endpoints_without_an_independent_ordinal_are_not_located_by_correct_numbers():
    result = read_prose_sequence([unit("p0", "The board shall pay 17 credits."), unit("p1", "The board shall pay 18 credits.")])
    assert result["blockers"][0]["reason"] == "prose_endpoint_role_collision"
    assert len(result["endpoints"]) == 2


def test_explicit_printed_ordinals_can_distinguish_the_same_action_without_using_its_amount():
    result = read_prose_sequence([unit("p0", "1. The board shall pay 17 credits."),
                                  unit("p1", "2. The board shall pay 18 credits.")])
    assert result["blockers"] == []
    assert [node["identity"]["ordinal"] for node in result["endpoints"]] == ["1", "2"]


def test_endpoint_roles_keep_company_identifiers_and_words_containing_unit_characters():
    endpoint = prose_endpoint("Type17 Bank shall pay 9 credits.", SOURCE)
    assert endpoint["identity"]["subject"] == "Type17 Bank"
    chinese = prose_endpoint("元器件收入為17萬元。", SOURCE)
    assert "元器件收入為" in chinese["identity"]["lexical_anchor"]
    assert "17" not in repr(chinese["identity"])


def test_unknown_parent_reference_and_records_do_not_gain_invented_prose_relations():
    unknown = read_prose_sequence([unit("p0", "The board shall pay 17 credits.", parent_id="missing")])
    assert unknown["blockers"][0]["reason"] == "prose_parent_reference_unresolved"
    records = read_prose_sequence([{**unit("p0", "Name: Delta; Revenue: 17"), "kind": "record"},
                                   {**unit("p1", "Name: Echo; Revenue: 29"), "kind": "record"}])
    assert records["endpoints"] == [] and records["relations"] == []


@pytest.mark.parametrize("interruption", ["image", "table", "record", "heading"])
def test_prose_continuity_never_jumps_over_another_declared_kind(interruption):
    first, second = unit("p0", "The board shall pay 17 credits."), unit("p1", "The clerk must publish the notice.")
    boundary = {"id": "boundary", "kind": interruption, "text": "Other content", "source": {"path": "<boundary>"}}
    result = read_prose_sequence([first, boundary, second])
    assert len(result["endpoints"]) == 2
    assert not any(edge["type"] == "prose_reading_order" for edge in result["relations"])


def test_an_inserted_standalone_negative_block_cannot_be_skipped_as_empty_or_repeated_syntax():
    original = [unit("p0", "The board shall pay 17 credits."), unit("p1", "The clerk must publish the notice.")]
    interrupted = [original[0], unit("p2", "No"), original[1]]
    required = read_prose_sequence(original)
    actual = read_prose_sequence(interrupted)
    wanted = next(edge for edge in required["relations"] if edge["type"] == "prose_reading_order")
    assert len(actual["endpoints"]) == 3
    assert not any(edge["left"] == wanted["left"] and edge["right"] == wanted["right"]
                   for edge in actual["relations"] if edge["type"] == "prose_reading_order")


def test_sentence_abbreviations_and_unknown_compounds_are_retained_without_guessing():
    result = read_prose_requirements("We shall meet at 9:00 a.m. Pacific Time. You must register.", SOURCE)
    assert result["blockers"] == [] and len(result["facts"]) == 2
    assert result["facts"][0]["value"] == "meet at 9:00 a.m. Pacific Time"
    unsupported = read_prose_requirements("The board shall pay and the clerk must approve unless denied.", SOURCE)
    assert unsupported["facts"] == [] and unsupported["blockers"]


@pytest.mark.parametrize("text,reason", [
    ("The notice states 'the board shall pay 17 credits'.", "quoted_or_parenthetic_logic_scope_unsupported"),
    ('The notice states “the board shall pay 17 credits”.', "quoted_or_parenthetic_logic_scope_unsupported"),
    ("The board shall pay 17 credits (unless approved).", "quoted_or_parenthetic_logic_scope_unsupported"),
    ("Neither Alice nor Bob shall pay 17 credits.", "quantified_subject_scope_unsupported"),
    ("The board shall not not pay 17 credits.", "nested_negation_scope_unsupported"),
])
def test_unproved_scope_is_not_converted_into_a_different_simple_obligation(text, reason):
    result = read_prose_requirements(text, SOURCE)
    assert result["matched"] is True and result["facts"] == []
    assert result["blockers"][0]["reason"] == reason
    assert result["blockers"][0]["layers"] == ["B"]
    assert result["text_spans"][0]["text"] == text


def test_possessive_apostrophe_does_not_become_a_quotation_boundary():
    result = read_prose_requirements("The board's secretary must report the result.", SOURCE)
    assert result["blockers"] == [] and len(result["facts"]) == 1
    assert result["facts"][0]["subject"] == "the board's secretary"
