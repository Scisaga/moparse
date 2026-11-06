"""Authored collection roles remain distinct from unknown member meanings."""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.source_obligations import audit_source_obligations
from tests.unit.test_requirement_graph_enumeration_scope import expected, facts, target

INTRO = "2029年，Vega在研发合作方面所取得的重点进展包括："
UNKNOWN = "设置尚不支持的跨域方案。"


def authored(*, all_unknown=False):
    return expected(
        target(INTRO, 2, kind="text"),
        target(UNKNOWN, 4, list_span=[4, 6]),
        target("构造未解释的联合安排。" if all_unknown else "批准Omega。", 5, list_span=[4, 6]),
    )


def introduction_dispositions(graph, coverage=None):
    obligations = [
        row
        for row in graph["source_obligation_inventory"]["obligations"]
        if row.get("source", {}).get("lines") == [2, 2]
        and row["interpretation_rule"]
        in {"each_printed_semantic_fragment", "each_semantic_fragment_requires_its_own_binding"}
    ]
    assert len(obligations) == 2
    coverage = coverage or graph["source_obligation_coverage"]
    return [
        row
        for row in coverage["dispositions"]
        if row["obligation_id"] in {item["id"] for item in obligations}
    ]


@pytest.mark.parametrize("all_unknown", [False, True])
def test_positive_collection_roles_and_scope_are_interpreted_without_accepting_unread_members(
    all_unknown,
):
    material = authored(all_unknown=all_unknown)
    original = deepcopy(material)
    graph = compile_requirement_graph(material)
    validate_requirement_graph(graph, expected=material)
    assert material == original
    [declaration] = [row for row in graph["relations"] if row["type"] == "enumeration_declaration"]
    assert declaration["left"] == {
        "subject": "Vega",
        "attribute": "重点进展",
        "domain": "研发合作",
        "scope": [],
        "qualifiers": {"period": "2029年"},
    }
    assert declaration["right"]["role"] == "declared_collection_scope"
    assert declaration["right"]["operator"] == "包括"
    assert [
        (row["ordinal"], row["text"], row["source"]["lines"])
        for row in declaration["right"]["members"]
    ] == [(0, UNKNOWN, [4, 4]), (1, material["targets"][2]["text"], [5, 5])]
    for role, literal in (
        ("period", "2029年"),
        ("subject", "Vega"),
        ("domain", "研发合作"),
        ("collection", "重点进展"),
        ("operator", "包括"),
    ):
        item = declaration["binding_evidence"]["roles"][role]
        start = INTRO.index(literal)
        assert item["text"] == literal
        assert item["source"]["lines"] == [2, 2]
        assert item["source"]["text_span"] == [start, start + len(literal)]
    assert [(row["subject"], row["attribute"], row["value"]) for row in facts(graph)] == (
        [] if all_unknown else [("Vega", "批准", "Omega")]
    )
    assert all(row["status"] == "explained" for row in introduction_dispositions(graph))
    # The declaration does not decide the unknown member's business endpoint.
    assert graph["semantic_complete"] is False
    assert any(
        row["reason"] == "enumeration_membership_endpoint_unresolved"
        and row["source"]["lines"] == [2, 2]
        for row in graph["unresolved"]
    )
    assert any(
        row["source"].get("lines") == [4, 4] and "B" in row["layers"] for row in graph["unresolved"]
    )
    assert any(
        node["text"] == UNKNOWN
        for node in graph["nodes"]
        if node["id"] in graph["projections"]["T"]
    )
    assert len(
        [edge for edge in graph["relations"] if edge["type"] == "enumeration_membership"]
    ) == (0 if all_unknown else 1)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_edge",
        "left_subject",
        "collection",
        "period",
        "domain",
        "role_source",
        "member_delete",
        "member_reorder",
        "direction",
        "boundary",
        "source",
    ],
)
def test_declaration_audit_cannot_borrow_roles_or_lose_original_raw_members(mutation):
    graph = compile_requirement_graph(authored())
    [declaration] = [row for row in graph["relations"] if row["type"] == "enumeration_declaration"]
    if mutation == "missing_edge":
        graph["relations"].remove(declaration)
    elif mutation == "left_subject":
        declaration["left"]["subject"] = "Orion"
    elif mutation == "collection":
        declaration["left"]["attribute"] = "其他进展"
    elif mutation == "period":
        declaration["left"]["qualifiers"]["period"] = "2028年"
    elif mutation == "domain":
        declaration["left"]["domain"] = "业务合作"
    elif mutation == "role_source":
        declaration["binding_evidence"]["roles"]["subject"]["source"] = deepcopy(
            declaration["right"]["members"][0]["source"]
        )
    elif mutation == "member_delete":
        declaration["right"]["members"].pop(0)
    elif mutation == "member_reorder":
        declaration["right"]["members"].reverse()
    elif mutation == "direction":
        declaration["left"], declaration["right"] = declaration["right"], declaration["left"]
    elif mutation == "boundary":
        declaration["binding_evidence"]["end_boundary"] = {
            "kind": "invented_end",
            "natural_end_proved": True,
        }
    else:
        declaration["source"] = deepcopy(declaration["right"]["members"][0]["source"])
    coverage = audit_source_obligations(graph["source_obligation_inventory"], graph)
    assert any(row["status"] == "pending" for row in introduction_dispositions(graph, coverage))
    with pytest.raises(
        ValueError, match="source|enumeration|declaration|relation|obligation|projection"
    ):
        validate_requirement_graph(graph)


def test_synchronized_index_deletion_cannot_erase_the_collection_declaration_requirement():
    graph = compile_requirement_graph(authored())
    [declaration] = [row for row in graph["relations"] if row["type"] == "enumeration_declaration"]
    graph["relations"].remove(declaration)
    graph["projections"]["L"].remove(declaration["id"])
    for row in graph["dispositions"]:
        row["layers"]["L"]["requirements"] = [
            ident for ident in row["layers"]["L"]["requirements"] if ident != declaration["id"]
        ]
    with pytest.raises(ValueError, match="source|enumeration|declaration|relation|obligation"):
        validate_requirement_graph(graph)
