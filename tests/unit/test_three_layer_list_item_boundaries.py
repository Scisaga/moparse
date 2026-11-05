"""Independent item boundaries through authored and delivered public syntax."""

from collections import Counter

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.three_layer import compile_markdown, read_candidate

PATH = "<invented-independent-list-items>"
MARKDOWN = "# Scope\n\n- Lumen批准Kappa\n- Vega披露Sigma"


def expected(items):
    targets = [{"id": "printed:1", "kind": "heading", "text": "Scope", "raw_text": "Scope", "raw": "# Scope",
        "reference": {"path": PATH, "lines": [1, 1]}, "cells": [], "parents": [], "has_children": False,
        "context": [], "selected_heading_context": [], "outside_selection_context": [], "pages": [1], "heading_level": 1}]
    for line, text in enumerate(items, 3):
        targets.append({"id": f"printed:{line}", "kind": "item", "text": text, "raw_text": text, "raw": "- " + text,
            "reference": {"path": PATH, "lines": [line, line]}, "cells": [], "parents": [], "has_children": False,
            "context": ["Scope"], "selected_heading_context": [{"text": "Scope", "reference": {"path": PATH, "lines": [1, 1]}}],
            "outside_selection_context": [], "pages": [1], "list_span": [3, 2 + len(items)], "heading_level": None})
    return {"sample_id": "invented-independent-list-items", "document_id": "invented-document",
        "source_pages": [1], "standard": "expected_only", "targets": targets,
        "scope": [{"lines": [1, 2 + len(items)], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]}


def read(carrier, items):
    markdown = "# Scope\n\n" + "\n".join("- " + text for text in items)
    if carrier == "reference":
        graph = compile_requirement_graph(expected(items))
        validate_requirement_graph(graph)
        assert graph["semantic_complete"] is True and not graph["unresolved"]
        nodes = {node["id"]: node for node in graph["nodes"]}
        return [nodes[ident] for ident in graph["projections"]["B"]], [nodes[ident] for ident in graph["projections"]["T"]]
    if carrier == "direct-markdown":
        graph = compile_markdown(markdown)
    else:
        observation = markdown_observation(markdown, sample_id="invented-independent-list-items", pipeline="invented", pages=[1])
        graph = read_candidate(observation)
    assert not graph["blockers"]
    return graph["business"], graph["text"]


@pytest.mark.parametrize("carrier", ["reference", "direct-markdown", "delivered-markdown"])
def test_unpunctuated_neighboring_list_items_remain_two_assertions_with_separate_sources(carrier):
    facts, atoms = read(carrier, ["Lumen批准Kappa", "Vega披露Sigma"])
    assert [(f["subject"], f["attribute"], f["value"]) for f in facts] == [
        ("Lumen", "批准", "Kappa"), ("Vega", "披露", "Sigma")]
    for line, fact, subject_span, verb_span, value_span in zip((3, 4), facts,
            ([0, 5], [0, 4]), ([5, 7], [4, 6]), ([7, 12], [6, 11]), strict=True):
        assert fact["scope"] == ["Scope"]
        for key, span in (("subject_source", subject_span), ("predicate_source", verb_span), ("value_source", value_span)):
            assert fact[key]["lines"] == [line, line]
            assert fact[key]["text_span"] == span
        assert not fact["source"].get("joined_fragments")
        if carrier == "delivered-markdown":
            assert fact["value_source"]["path"] == f"markdown:L{line}:{line - 2}"
        elif carrier == "reference":
            assert fact["value_source"]["path"] == PATH
    assert Counter("".join(atom["text"] for atom in atoms)) == Counter("ScopeLumen批准KappaVega披露Sigma")
    assert not any("Lumen" in atom["text"] and "Vega" in atom["text"] for atom in atoms)


@pytest.mark.parametrize("carrier", ["reference", "delivered-markdown"])
def test_two_complete_sentences_in_one_item_keep_offsets_into_the_same_real_item(carrier):
    facts, atoms = read(carrier, ["Lumen批准Kappa。Vega披露Sigma。"])
    assert [(f["subject"], f["attribute"], f["value"]) for f in facts] == [
        ("Lumen", "批准", "Kappa"), ("Vega", "披露", "Sigma")]
    assert [fact["subject_source"]["text_span"] for fact in facts] == [[0, 5], [13, 17]]
    assert [fact["predicate_source"]["text_span"] for fact in facts] == [[5, 7], [17, 19]]
    assert [fact["value_source"]["text_span"] for fact in facts] == [[7, 12], [19, 24]]
    assert all(fact["value_source"]["lines"] == [3, 3] for fact in facts)
    assert Counter("".join(atom["text"] for atom in atoms)) == Counter("ScopeLumen批准Kappa。Vega披露Sigma。")


def test_ordinary_same_scope_paragraph_fragments_still_join_with_original_block_sources():
    observation = {"sample_id": "invented-paragraph-fragments", "pipeline": "invented", "status": "success",
        "pages": [{"page": 1, "blocks": [
            {"id": "first", "native_path": "#/paragraph/0", "kind": "text", "text_format": "plain", "text": "Lumen owns"},
            {"id": "second", "native_path": "#/paragraph/1", "kind": "text", "text_format": "plain", "text": "Kappa."}]}],
        "relations": [], "assets": []}
    graph = read_candidate(observation)
    [fact] = graph["business"]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "own", "Kappa")
    assert graph["blockers"] == []
    fragments = fact["source"]["joined_fragments"]
    assert [(fragment["source"]["path"], fragment["text"], fragment["joined_span"]) for fragment in fragments] == [
        ("#/paragraph/0", "Lumen owns", [0, 10]), ("#/paragraph/1", "Kappa.", [11, 17])]
    assert "".join(atom["text"] for atom in graph["text"]) == "Lumen owns Kappa."
