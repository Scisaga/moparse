"""Independent qualifier-span contracts for already supported compact syntax."""

from copy import deepcopy

import pytest

from moparse_eval.compact_requirements import read_compact_requirements, read_compact_schema
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.text_projection import combine_text_projections, project_compact_text

PATH = "<invented-compact-qualifier-source>"


def source(line, offset=0):
    return {"path": PATH, "lines": [line, line], "text_span": [offset, offset + 200]}


def expected(*texts):
    targets = []
    for line, (text, parents) in enumerate(texts, 1):
        targets.append({"id": f"printed:{line}", "kind": "item" if parents else "text", "text": text,
            "raw_text": text, "raw": text, "reference": {"path": PATH, "lines": [line, line]},
            "cells": [], "parents": parents, "has_children": line < len(texts) and bool(texts[line][1]),
            "context": [], "selected_heading_context": [], "outside_selection_context": [], "pages": [1]})
    return {"sample_id": "invented-compact-qualifier-source", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": targets,
        "scope": [{"lines": [1, len(texts)], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]}


def business(graph):
    by_id = {node["id"]: node for node in graph["nodes"]}
    return [by_id[ident] for ident in graph["projections"]["B"]]


@pytest.mark.parametrize("offset", [0, 40])
def test_single_annual_leaf_keeps_its_printed_period_unit_currency_and_exact_sources(offset):
    text = "2028年，美元百万元：17"
    result = read_compact_requirements(text, source(2, offset),
        parents=[{"text": "Revenue", "source": source(1)}])
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"], fact["role"]) == ("", "Revenue", "17", "metric")
    assert fact["qualifiers"] == {"period": "2028年", "unit": "美元百万元", "currency": "美元"}
    assert fact["value_source"]["text_span"] == [offset + 12, offset + 14]
    for key, span in {"period": [0, 5], "unit": [6, 11], "currency": [6, 8]}.items():
        assert fact["qualifier_sources"][key] == {**source(2, offset), "text_span": [offset + n for n in span]}
        assert fact["source"]["qualifier_sources"][key] == fact["qualifier_sources"][key]


def test_year_only_leaf_graph_is_valid_and_its_period_source_cannot_disappear():
    graph = compile_requirement_graph(expected(("Revenue", []), ("2028年：17", ["Revenue"])))
    [fact] = business(graph)
    assert (fact["attribute"], fact["value"], fact["qualifiers"]) == ("Revenue", "17", {"period": "2028年"})
    assert fact["qualifier_sources"]["period"] == {"path": PATH, "lines": [2, 2], "text_span": [0, 5]}
    validate_requirement_graph(graph)
    for container in (fact, fact["source"]):
        container.get("qualifier_sources", {}).pop("period", None)
    fact.get("qualifier_provenance", {}).pop("period", None)
    with pytest.raises(ValueError, match="source.*period|qualifier period"):
        validate_requirement_graph(graph)


SCHEMA = "金额单位：人民币千元。列说明：2028年金额、占比（%）；2027年金额、占比（%）。"
ROW = "Delta：2028年17、60%；2027年11、55%"


@pytest.mark.parametrize("offset", [0, 40])
def test_declared_columns_preserve_currency_as_own_subspan_of_actual_unit(offset):
    original_source = source(3, offset)
    schema = read_compact_schema(SCHEMA, original_source)
    before = deepcopy(schema)
    result = read_compact_requirements(ROW, source(7), schema=schema)
    assert schema == before
    assert [(f["attribute"], f["value"], f["qualifiers"]["period"]) for f in result["facts"]] == [
        ("金额", "17", "2028年"), ("占比", "60", "2028年"), ("金额", "11", "2027年"), ("占比", "55", "2027年")]
    for fact in result["facts"][::2]:
        assert fact["qualifiers"]["currency"] == "人民币"
        assert fact["qualifier_sources"]["unit"] == {**original_source, "text_span": [offset + 5, offset + 10]}
        assert fact["qualifier_sources"]["currency"] == {**original_source, "text_span": [offset + 5, offset + 8]}
    for fact in result["facts"][1::2]:
        assert "currency" not in fact["qualifiers"]
        assert "currency" not in fact["qualifier_sources"]
        # Inline % owns its source; another object's header cannot supply it.
        assert fact["qualifier_sources"]["unit"]["lines"] == [7, 7]


def test_declared_comparison_and_currency_graph_qualifiers_all_have_original_evidence():
    declaration = SCHEMA[:-1] + "金額同比變動（%）。"
    row = ROW + "；金額同比變動：5%"
    graph = compile_requirement_graph(expected((declaration, []), (row, [])))
    facts = business(graph)
    assert len(facts) == 5
    assert facts[-1]["qualifiers"] == {"from_period": "2027年", "to_period": "2028年", "unit": "%"}
    assert facts[-1]["qualifier_sources"]["to_period"] == {"path": PATH, "lines": [1, 1], "text_span": [15, 20]}
    assert facts[-1]["qualifier_sources"]["from_period"] == {"path": PATH, "lines": [1, 1], "text_span": [29, 34]}
    validate_requirement_graph(graph)
    amount = facts[0]
    amount["qualifier_sources"]["currency"]["text_span"] = [8, 10]  # 千元 is not 人民币.
    amount.get("qualifier_provenance", {}).pop("currency", None)
    with pytest.raises(ValueError, match="source|currency|qualifier"):
        validate_requirement_graph(graph)


def test_schema_percent_and_inline_percent_have_finite_aliases_but_wrong_unit_does_not():
    schema = read_compact_schema(SCHEMA, source(3))
    valid = read_compact_requirements(ROW, source(7), schema=schema)
    wrong = read_compact_requirements(ROW.replace("60%", "60‰"), source(7), schema=schema)
    for result, unit, alias_count in ((valid, "%", 1), (wrong, "‰", 0)):
        fact = result["facts"][1]
        assert fact["qualifiers"]["unit"] == unit
        assert len(fact["qualifier_aliases"]) == alias_count
        projection = combine_text_projections([
            project_compact_text(schema, schema["schema"], source(3), raw_text=SCHEMA),
            project_compact_text(result, schema["schema"], source(7), raw_text=ROW if unit == "%" else ROW.replace("60%", "60‰")),
        ])
        endpoint = fact["source"]["text_span"]
        origins = [alias["origin"] for alias in projection["aliases"]
            if alias["data_object"]["source"]["text_span"] == endpoint
            and alias["origin"]["role"] == "unit"]
        assert any(origin["text"] == unit and origin["source"]["lines"] == [7, 7] for origin in origins)
        assert any(origin["text"] == "%" and origin["source"]["lines"] == [3, 3] for origin in origins) is (unit == "%")
    # A forged alias cannot fold a mismatching printed unit into this object.
    wrong["facts"][1]["qualifier_aliases"] = deepcopy(valid["facts"][1]["qualifier_aliases"])
    projection = project_compact_text(wrong, schema["schema"], source(7))
    endpoint = wrong["facts"][1]["source"]["text_span"]
    assert not any(alias["origin"]["text"] == "%" and alias["origin"]["source"]["lines"] == [3, 3]
        and alias["data_object"]["source"]["text_span"] == endpoint for alias in projection["aliases"])
