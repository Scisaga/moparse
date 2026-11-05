"""Hand-authored dated introduction roles and structural scope boundaries."""

from copy import deepcopy

import pytest

from moparse_eval.enumeration_context import (
    enumeration_membership,
    plan_enumeration_scopes,
    read_enumeration_intro,
)

INTRO = "2028年，Lumen的合作进展包括："
SOURCE = {"path": "<printed-enumeration>", "lines": [1, 1]}


def block(identifier, text, line, *, kind="item", span=None, parents=(), children=False):
    return {"id": identifier, "text": text, "kind": kind, "source": {**SOURCE, "lines": [line, line]},
            "list_span": span, "parents": list(parents), "has_children": children}


def explicit_blocks():
    return [block("intro", INTRO, 1, span=[1, 4], children=True),
            block("a", "批准Kappa。", 2, span=[1, 4], parents=[INTRO]),
            block("b", "披露Sigma。", 3, span=[1, 4], parents=[INTRO])]


@pytest.mark.parametrize("offset", [0, 40])
def test_explicit_intro_roles_have_exact_own_sources_and_never_an_empty_business_vote(offset):
    origin = {**SOURCE, "text_span": [offset, offset + len(INTRO)]}
    original = deepcopy(origin)
    result = read_enumeration_intro(INTRO, origin)
    assert result["matched"] is True and result["lexical_complete"] is True
    assert result["facts"] == [] and result["blockers"] == []
    wanted = {"period": ("2028年", [0, 5]), "subject": ("Lumen", [6, 11]),
              "collection": ("合作进展", [12, 16]), "operator": ("包括", [16, 18])}
    for key, (text, span) in wanted.items():
        assert result["roles"][key] == {"text": text, "source": {**origin, "text_span": [offset + v for v in span]}}
    assert result["qualifiers"] == {"period": "2028年"}
    assert origin == original


def test_a_printed_domain_and_pronoun_are_roles_without_resolving_the_pronoun_to_a_company():
    text = "2028年，我们在研发方面所取得的关键进展包括："
    result = read_enumeration_intro(text, SOURCE)
    assert result["lexical_complete"] is True
    assert result["roles"]["subject"] == {"text": "我们", "source": {**SOURCE, "text_span": [6, 8]}}
    assert result["roles"]["domain"] == {"text": "研发", "source": {**SOURCE, "text_span": [9, 11]}}
    assert result["roles"]["collection"] == {"text": "关键进展", "source": {**SOURCE, "text_span": [17, 21]}}


@pytest.mark.parametrize("text", ["2028年，合作进展包括：", "2028年，Lumen的合作进展可能包括：",
                                 "如果2028年，Lumen的合作进展包括："])
def test_unknown_introduction_roles_remain_whole_source_pending(text):
    result = read_enumeration_intro(text, SOURCE)
    assert result["matched"] is True and result["lexical_complete"] is False
    assert result["facts"] == [] and any(p["text"] == text for p in result["pending_requirements"])
    assert any(set(p["layers"]) >= {"B", "L"} for p in result["blockers"])


def test_a_colon_or_scalar_year_alone_is_not_an_enumeration_declaration():
    for text in ("Revenue:2028年17万元", "2028年，Lumen的合作进展：", "Name:Lumen"):
        assert read_enumeration_intro(text, SOURCE)["matched"] is False


def test_actual_parent_and_declared_list_end_bind_two_members_and_no_later_plain_field():
    entries = explicit_blocks() + [block("tail", "Name:Vega", 5, kind="text")]
    original = deepcopy(entries)
    result = plan_enumeration_scopes(entries)
    [context] = result["contexts"]
    assert [m["id"] for m in context["members"]] == ["a", "b"]
    assert set(result["by_member"]) == {"a", "b"}
    assert context["boundary"]["kind"] == "non_list_boundary"
    assert context["boundary"]["source"]["lines"] == [5, 5]
    for member in context["members"]:
        inherited = member["member_context"]
        assert inherited["subject"] == "Lumen" and inherited["qualifiers"] == {"period": "2028年"}
        assert inherited["subject_source"]["text_span"] == [6, 11]
        assert inherited["qualifier_sources"]["period"]["text_span"] == [0, 5]
    assert entries == original


def test_flat_list_span_owns_explicitly_different_actors_and_stops_at_a_caption():
    entries = [block("intro", INTRO, 1, kind="text"), block("a", "Vega批准Kappa。", 3, span=[3, 8]),
               block("b", "Lumen披露Sigma。", 7, span=[3, 8]), block("end", "照片", 9, kind="image_caption"),
               block("tail", "Kappa批准Omega。", 11, kind="text")]
    result = plan_enumeration_scopes(entries)
    [context] = result["contexts"]
    assert [m["id"] for m in context["members"]] == ["a", "b"]
    assert context["boundary"]["source"]["lines"] == [9, 9]
    assert "tail" not in result["by_member"]
    assert context["declaration"]["roles"]["subject"]["text"] == "Lumen"


def test_the_declared_blank_end_and_an_authorized_mid_list_selection_are_different_boundaries():
    complete = plan_enumeration_scopes(explicit_blocks())["contexts"][0]
    assert complete["boundary"]["kind"] == "declared_list_span_end"
    assert complete["boundary"]["natural_end_proved"] is True
    partial = explicit_blocks()
    for item in partial:
        item["list_span"] = [1, 20]
    result = plan_enumeration_scopes(partial, selection_end={"kind": "selected_input_end", "source": partial[-1]["source"]})
    [context] = result["contexts"]
    assert context["boundary"]["kind"] == "selected_input_end"
    assert context["boundary"]["natural_end_proved"] is False
    assert [m["id"] for m in context["members"]] == ["a", "b"]


def test_a_heading_or_different_list_does_not_continue_the_old_scope():
    for tail in (block("end", "Other", 4, kind="heading", span=[1, 10]),
                 block("end", "批准Omega。", 5, span=[5, 6])):
        result = plan_enumeration_scopes(explicit_blocks()[:2] + [tail])
        [context] = result["contexts"]
        assert [m["id"] for m in context["members"]] == ["a"]
        assert "end" not in result["by_member"]


def test_an_unprinted_parent_string_cannot_supply_a_subject_or_a_year():
    result = plan_enumeration_scopes(explicit_blocks()[1:])
    assert result["contexts"] == [] and result["by_member"] == {}
    assert any(p["source"]["lines"] == [2, 2] for p in result["pending_requirements"])


def test_membership_keeps_the_real_child_actor_and_binds_only_an_actual_member_source():
    context = plan_enumeration_scopes(explicit_blocks())["contexts"][0]
    member = context["members"][0]
    fact = {"subject": "Vega", "attribute": "批准", "value": "Kappa", "scope": [], "identity_facets": {},
            "qualifiers": {"period": "2028年"}, "source": {**member["source"], "text_span": [2, 7]}}
    original = deepcopy(fact)
    edge = enumeration_membership(context, member, fact)
    assert edge["type"] == "enumeration_membership"
    assert edge["right"]["subject"] == "Vega" and edge["right"]["attribute"] == "批准"
    assert edge["binding_evidence"]["introduction_source"] == {**SOURCE, "text_span": [0, len(INTRO)]}
    assert edge["binding_evidence"]["member_source"] == {**member["source"], "text_span": [0, 8]}
    assert fact == original
    fact["source"]["lines"] = [99, 99]
    with pytest.raises(ValueError, match="member|source|scope"):
        enumeration_membership(context, member, fact)


def test_an_actual_stream_id_binds_different_block_paths_but_a_different_stream_cannot_borrow():
    entries = explicit_blocks()
    for index, entry in enumerate(entries):
        entry["source"]["path"] = f"<delivered-block:{index}>"
        entry["list_stream"] = "<one-actual-markdown-stream>"
        entry["public_lines"] = entry["source"]["lines"]
        entry["source"]["lines"] = [1, 1]  # Native local lines are not public lines.
    result = plan_enumeration_scopes(entries)
    assert [m["id"] for m in result["contexts"][0]["members"]] == ["a", "b"]
    assert result["contexts"][0]["boundary"]["kind"] == "declared_list_span_end"
    entries[1]["list_stream"] = entries[2]["list_stream"] = "<different-actual-stream>"
    rejected = plan_enumeration_scopes(entries)
    assert rejected["by_member"] == {} and rejected["contexts"] == []


def test_domain_is_a_separate_sourced_membership_identity_instead_of_disappearing_into_collection():
    intro = "2028年，我们在研发方面所取得的关键进展包括："
    entries = [block("intro", intro, 1, span=[1, 3], children=True),
               block("a", "批准Kappa。", 2, span=[1, 3], parents=[intro])]
    [context] = plan_enumeration_scopes(entries)["contexts"]
    [member] = context["members"]
    edge = enumeration_membership(context, member, {"subject": "Vega", "attribute": "批准", "source": member["source"]})
    assert edge["left"]["domain"] == "研发"
    assert edge["left"]["attribute"] == "关键进展"
    assert edge["binding_evidence"]["domain_source"] == {**SOURCE, "text_span": [9, 11]}
