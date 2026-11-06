"""Graph integration oracles for independent raw expected transport.

All source files here are invented temporary fixtures outside the corpus. The
tests diagnose a reader dropping authored material; they do not review, accept
or change corpus content and do not read any candidate or PDF.
"""

import json
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import replace

import pytest

from moparse_eval import expected_readback
from moparse_eval.packaging import write_json
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
    write_requirement_graph,
)


def fixture(tmp_path, raw):
    document = tmp_path / "invented"
    document.mkdir()
    (document / "expected.md").write_text(raw, encoding="utf-8")
    write_json(document / "manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {
        "entries": [{"source_pages": [1], "markdown_lines": [1, len(raw.splitlines())]}]}})
    return {"id": "invented-raw-binding", "document_id": "invented", "source_pages": [1]}


def drop_expected_view(monkeypatch, mutation):
    original = expected_readback.elements

    def defective_reader(raw):
        output = []
        for element in original(raw):
            if "Sigma" in element.text:
                if mutation == "whole_target":
                    continue
                element = replace(element, text="Board owns Kappa.")
            output.append(element)
        return output

    monkeypatch.setattr(expected_readback, "elements", defective_reader)


@pytest.mark.parametrize("mutation", ["whole_target", "same_line_clause"])
def test_raw_omission_propagates_through_graph_projection_and_serialized_view(tmp_path, monkeypatch, mutation):
    raw = "Name: Delta\n\nBoard owns Kappa and Sigma.\n"
    sample = fixture(tmp_path, raw)
    drop_expected_view(monkeypatch, mutation)
    authored = expected_readback.read_expected(sample, tmp_path)
    before = deepcopy(authored)
    graph = compile_requirement_graph(authored)
    inventory = graph["source_obligation_inventory"]
    raw_inventory = inventory["authorized_raw_inventory"]
    [missing] = [row for row in raw_inventory["obligations"] if row["status"] == "pending"]
    assert missing["text"] == "Board owns Kappa and Sigma."
    assert missing["source"]["lines"] == [3, 3]
    assert inventory["source_complete"] is False
    assert graph["source_obligation_coverage"]["source_complete"] is False
    assert graph["semantic_complete"] is False and graph["complete"] is False
    blockers = [row for row in graph["unresolved"] if row.get("obligation_id") == missing["id"]
                or missing["id"] in row.get("source_obligation_ids", [])]
    assert blockers and all(set(row["layers"]) == {"T", "L", "B"} for row in blockers)
    projected = evaluation_projection(graph)
    assert any(row.get("obligation_id") == missing["id"] for row in projected["blockers"])
    validate_requirement_graph(graph, expected=authored)
    json_path, xml_path = tmp_path / "view.json", tmp_path / "view.xml"
    write_requirement_graph(graph, json_path, xml_path)
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    validate_requirement_graph(loaded, expected=authored)
    assert loaded["semantic_complete"] is False
    assert ET.parse(xml_path).findtext("semantic_complete") == "False"
    assert authored == before


@pytest.mark.parametrize("raw", ["Name: Delta\n\nRevenue: 17\n", "- Name: Delta\n- Revenue: 17\n- Profit: 5\n"])
def test_regenerated_JSON_and_XML_project_one_model_that_validates_against_a_fresh_external_source(tmp_path, raw):
    sample = fixture(tmp_path, raw)
    authored = expected_readback.read_expected(sample, tmp_path)
    graph = compile_requirement_graph(authored)
    assert graph["semantic_complete"] is True
    assert graph["source_obligation_inventory"]["authorized_raw_inventory"]["canonical_authorized_source_complete"] is True
    json_path, xml_path = tmp_path / "view.json", tmp_path / "view.xml"
    write_requirement_graph(graph, json_path, xml_path)
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    fresh = expected_readback.read_expected(sample, tmp_path)
    validate_requirement_graph(loaded, expected=fresh)
    assert loaded == graph
    xml = ET.parse(xml_path)
    assert xml.findtext("sample_id") == loaded["sample_id"]
    assert xml.findtext("semantic_complete") == "True"
    assert xml.findtext("source_obligation_inventory/authorized_raw_inventory/source_complete") == "True"
    assert (tmp_path / "invented" / "expected.md").read_text(encoding="utf-8") == raw


def test_synchronized_raw_status_and_graph_flags_cannot_launder_a_reader_omission(tmp_path, monkeypatch):
    sample = fixture(tmp_path, "Name: Delta\n\nBoard owns Kappa and Sigma.\n")
    drop_expected_view(monkeypatch, "whole_target")
    authored = expected_readback.read_expected(sample, tmp_path)
    graph = compile_requirement_graph(authored)
    inventory = graph["source_obligation_inventory"]
    raw_inventory = inventory["authorized_raw_inventory"]
    missing_ids = {row["id"] for row in raw_inventory["obligations"] if row["status"] == "pending"}
    assert missing_ids
    for row in raw_inventory["obligations"]:
        if row["id"] in missing_ids:
            row.update(status="explained", reason="fabricated_synchronized_transport_success")
    raw_inventory["source_complete"] = raw_inventory["canonical_authorized_source_complete"] = True
    inventory["source_complete"] = True
    for row in graph["source_obligation_coverage"]["dispositions"]:
        if row["obligation_id"] in missing_ids:
            row.update(status="explained", reason="fabricated_synchronized_transport_success")
    graph["source_obligation_coverage"].update(source_complete=True, semantic_complete=True)
    graph["unresolved"] = []
    graph["complete"] = graph["semantic_complete"] = True
    with pytest.raises(ValueError, match="source|obligation|inventory|raw"):
        validate_requirement_graph(graph, expected=authored)


def test_an_edited_generated_answer_cannot_replace_the_unchanged_external_canonical_source(tmp_path):
    raw = "Revenue: 17\n"
    sample = fixture(tmp_path, raw)
    original = expected_readback.read_expected(sample, tmp_path)
    invented = deepcopy(original)
    invented["authorized_raw_segments"][0]["raw"] = "Revenue: 19\n"
    [item] = invented["targets"]
    item.update(raw="Revenue: 19\n", raw_text="Revenue: 19", text="Revenue: 19")
    forged = compile_requirement_graph(invented)
    assert forged["semantic_complete"] is True
    with pytest.raises(ValueError, match="source|obligation|inventory|semantics"):
        validate_requirement_graph(forged, expected=expected_readback.read_expected(sample, tmp_path))
    assert (tmp_path / "invented" / "expected.md").read_text(encoding="utf-8") == raw
