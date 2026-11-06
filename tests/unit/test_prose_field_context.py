"""Source-fixed field scopes and named-record identities for logical prose."""

from copy import deepcopy

import pytest

from moparse_eval.prose_requirements import (
    prose_endpoint,
    read_prose_requirements,
    read_prose_sequence,
)

SOURCE = {"path": "<body>", "lines": [12, 12]}
DELTA = {"text": "Name: Delta", "source": {"path": "<body>", "lines": [10, 10]}}
KAPPA = {"text": "Name: Kappa", "source": {"path": "<body>", "lines": [20, 20]}}


def test_actual_printed_field_label_is_business_scope_with_its_own_source():
    text = "Admission: You will need Control only if registered by 4 directors."
    result = read_prose_requirements(text, SOURCE, label="Admission", scope=["Meeting"])
    assert result["blockers"] == [] and len(result["facts"]) == 1
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"], fact["role"]) == (
        "you", "need", "need Control", "description")
    assert fact["scope"] == ["Meeting", "Admission"]
    assert fact["qualifiers"] == {"modality": "will", "polarity": "positive",
                                  "condition": "registered by 4 directors", "condition_operator": "only_if"}
    assert fact["field_label_evidence"] == {"text": "Admission", "source": {**SOURCE, "text_span": [0, 9]},
                                             "role": "printed_field_label"}
    [condition] = [edge for edge in result["relations"] if edge["type"] == "condition_scope"]
    assert condition["left"] == {"role": "condition", "lexical_anchor": ["registered", "by", "directors"]}
    assert condition["right"] == {"subject": "you", "action": "need", "scope": ["Meeting", "Admission"]}
    [binding] = [edge for edge in result["relations"] if edge["type"] == "field_binding"]
    [modal] = [edge for edge in result["relations"] if edge["type"] == "qualifier_scope"]
    assert binding["left"] == {"subject": "you", "attribute": "need"}
    assert binding["right"] == modal["right"] == {
        "subject": "you", "attribute": "need", "scope": ["Meeting", "Admission"], "identity_facets": {}}
    expected_roles = {}
    for role, literal in (("subject", "You"), ("predicate", "need"), ("object", "Control")):
        start = text.index(literal)
        expected_roles[role + "_source"] = {**SOURCE, "text_span": [start, start + len(literal)]}
    statement = {**SOURCE, "text_span": [text.index("You"), len(text.rstrip("."))]}
    assert binding["binding_evidence"] == {"statement_source": statement, **expected_roles}
    assert binding["source"] == expected_roles["predicate_source"]
    start = text.index("will")
    modal_source = {**SOURCE, "text_span": [start, start + len("will")]}
    assert modal["left"] == {"type": "modality", "text": "will"}
    assert modal["source"] == modal["operator_source"] == modal_source
    assert modal["binding_evidence"] == {
        "statement_source": statement, **expected_roles, "operator": "will", "operator_source": modal_source}
    assert all(edge["field_label_evidence"] == {
        "text": "Admission", "source": {**SOURCE, "text_span": [0, 9]}, "role": "printed_field_label"}
        for edge in (condition, binding, modal))
    assert len(result["relations"]) == 3


def test_later_sentence_uses_its_actual_original_field_label_source_without_a_fake_prefix():
    original_label = {"path": "<original-field>", "lines": [10, 10], "text_span": [0, 9]}
    result = read_prose_requirements("You must confirm identity.", SOURCE, label="Admission",
                                     label_source=original_label, scope=["Meeting"])
    assert result["blockers"] == [] and len(result["facts"]) == 1
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("you", "confirm", "confirm identity")
    assert fact["scope"] == ["Meeting", "Admission"]
    assert fact["field_label_evidence"]["source"] == original_label
    assert fact["value_source"]["path"] == "<body>"
    assert fact["field_label_evidence"]["source"]["path"] != fact["value_source"]["path"]
    endpoint = prose_endpoint("You must confirm identity.", SOURCE, label="Admission", label_source=original_label,
                              scope=["Meeting"])
    assert endpoint["scope"] == ["Meeting", "Admission"] and "Admission" not in repr(endpoint["identity"])


@pytest.mark.parametrize("parent", [DELTA, KAPPA])
def test_actor_and_explicit_name_record_are_separate_source_proved_identities(parent):
    before = deepcopy(parent)
    result = read_prose_requirements("He shall pay 17 credits.", SOURCE, parents=[parent], scope=["Contracts"])
    assert result["blockers"] == [] and len(result["facts"]) == 1
    [fact] = result["facts"]
    name = "Delta" if parent == DELTA else "Kappa"
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("he", "pay", "pay 17 credits")
    assert fact["identity_facets"] == {"record": {"Name": name}}
    assert fact["record_evidence"] == [{"attribute": "Name", "value": name,
        "source": parent["source"], "attribute_source": {**parent["source"], "text_span": [0, 4]},
        "value_source": {**parent["source"], "text_span": [6, 11]}}]
    assert parent == before


def test_missing_parent_declaration_source_blocks_instead_of_inventing_leaf_provenance():
    result = read_prose_requirements("He shall pay 17 credits.", SOURCE, parents=["Name: Delta"], scope=["Contracts"])
    assert any(b["reason"] == "prose_context_parent_source_unavailable" for b in result["blockers"])
    assert all(f["identity_facets"].get("record") != {"Name": "Delta"} for f in result["facts"])


def test_same_record_action_endpoint_survives_numeric_and_condition_content_changes():
    first = prose_endpoint("He shall pay 17 credits only if approved by 4 directors.", SOURCE,
                           scope=["Contracts"], parents=[DELTA])
    changed = prose_endpoint("He shall pay 5 credits only if approved by 3 directors.", SOURCE,
                             scope=["Contracts"], parents=[DELTA])
    other = prose_endpoint("He shall pay 17 credits only if approved by 4 directors.", SOURCE,
                           scope=["Contracts"], parents=[KAPPA])
    assert first["identity"] == changed["identity"]
    assert first["identity"] != other["identity"]
    assert first["identity"]["subject"] == "he"
    assert first["identity"]["identity_facets"] == {"record": {"Name": "Delta"}}
    assert "17" not in repr(first["identity"]) and "4 directors" not in repr(first["identity"])


def test_inline_label_and_actual_heading_scope_give_the_same_independent_endpoint():
    inline = prose_endpoint("Admission: You will need Control.", SOURCE, scope=["Meeting"], label="Admission")
    headed = prose_endpoint("You will need Control.", SOURCE, scope=["Meeting", "Admission"])
    assert inline["scope"] == headed["scope"] == ["Meeting", "Admission"]
    assert inline["identity"] == headed["identity"]
    assert "Control" not in repr(inline["identity"])


def test_same_action_in_distinct_named_records_is_not_a_role_collision():
    units = [{"id": "delta-pay", "text": "He shall pay 17 credits.", "source": SOURCE,
              "scope": ["Contracts"], "parents": [DELTA]},
             {"id": "kappa-pay", "text": "He shall pay 5 credits.", "source": {**SOURCE, "lines": [22, 22]},
              "scope": ["Contracts"], "parents": [KAPPA]}]
    result = read_prose_sequence(units)
    assert result["blockers"] == []
    assert [node["identity"]["identity_facets"]["record"] for node in result["endpoints"]] == [
        {"Name": "Delta"}, {"Name": "Kappa"}]
    assert all(edge["type"] != "prose_reading_order" for edge in result["relations"])
