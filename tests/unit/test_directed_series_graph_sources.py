"""Direction token admission through the complete source-bound graph path.

The printed years, scalar values, units and direction meanings below are
hand-authored finite fixtures, independent of either reader's vocabulary.
No saved execution, candidate, corpus file or PDF is read.
"""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph

PATH = "<invented-directed-series-graph>"
CONTEXT = "本年：2028年；上年：2027年。"
DIRECTIONS = [
    ("增长", "increase", "0.35", "%", "40.14", "40"),
    ("增長", "increase", "0.35", "pp", "40.35", "40"),
    ("增加", "increase", "0.35", "个百分点", "40.35", "40"),
    ("上升", "increase", "35", "bp", "40.35", "40"),
    ("下降", "decrease", "0.35", "個百分點", "39.65", "40"),
    ("减少", "decrease", "35", "基点", "39.65", "40"),
    ("減少", "decrease", "35", "基點", "39.65", "40"),
]


def authored(text):
    targets = [{"id": f"printed:{line}", "kind": "text", "text": value, "raw_text": value, "raw": value,
        "reference": {"path": PATH, "lines": [line, line]}, "cells": [], "parents": [],
        "has_children": False, "context": [], "selected_heading_context": [],
        "outside_selection_context": [], "pages": [1], "heading_level": None}
        for line, value in ((1, CONTEXT), (2, text))]
    return {"sample_id": "invented-directed-series-graph", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": targets,
        "scope": [{"lines": [1, 2], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]}


@pytest.mark.parametrize("direction,meaning,magnitude,unit,current,previous", DIRECTIONS,
                         ids=[row[0] for row in DIRECTIONS])
def test_every_admitted_direction_passes_graph_source_validation_and_rejects_the_opposite_meaning(
        direction, meaning, magnitude, unit, current, previous):
    text = f"Margin：2028年{current}%；2027年{previous}%；同比變動{direction}{magnitude}{unit}。"
    expected = authored(text)
    before = deepcopy(expected)
    graph = compile_requirement_graph(expected)
    by_id = {node["id"]: node for node in graph["nodes"]}
    facts = [by_id[ident] for ident in graph["projections"]["B"]]
    assert [(fact["attribute"], fact["value"]) for fact in facts] == [
        ("Margin", current), ("Margin", previous), ("同比變動", magnitude)]
    change = facts[-1]
    assert change["subject"] == "Margin"
    assert change["qualifiers"] == {"unit": unit, "change_direction": meaning,
                                    "from_period": "2027年", "to_period": "2028年"}
    start = text.index(direction)
    direction_source = {"path": PATH, "lines": [2, 2], "text_span": [start, start + len(direction)]}
    assert change["qualifier_sources"]["change_direction"] == direction_source
    assert change["value_source"]["text_span"] == [start + len(direction), start + len(direction) + len(magnitude)]
    assert change["qualifier_sources"]["unit"]["text_span"] == [
        start + len(direction) + len(magnitude), start + len(direction) + len(magnitude) + len(unit)]
    assert change["qualifier_sources"]["from_period"] == {"path": PATH, "lines": [1, 1], "text_span": [12, 17]}
    assert change["qualifier_sources"]["to_period"] == {"path": PATH, "lines": [1, 1], "text_span": [3, 8]}
    [edge] = [edge for edge in graph["relations"] if edge["type"] == "qualifier_scope"
              and edge.get("fact_id") == change["id"] and edge["left"].get("type") == "change_direction"]
    assert edge["source"] == direction_source and edge["left"]["text"] == meaning
    validate_requirement_graph(graph, expected=expected)
    assert expected == before

    opposite = "decrease" if meaning == "increase" else "increase"
    change["qualifiers"]["change_direction"] = opposite
    change.get("qualifier_provenance", {}).get("change_direction", {})["text"] = opposite
    for relation in graph["relations"]:
        if relation.get("fact_id") == change["id"]:
            relation.get("right", {}).get("qualifiers", {})["change_direction"] = opposite
            if relation["type"] == "qualifier_scope" and relation["left"].get("type") == "change_direction":
                relation["left"]["text"] = opposite
    with pytest.raises(ValueError, match="change_direction"):
        validate_requirement_graph(graph)
