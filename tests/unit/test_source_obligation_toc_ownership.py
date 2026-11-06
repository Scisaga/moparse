"""Independent source ownership oracles for the existing TOC protocol.

All reference text is invented here. Expected answers are hand-written below;
the production compiler supplies only the graph under test. Mutations retain
the original inventory and T literals while updating derived graph indexes.
"""

import json
from copy import deepcopy

import pytest

from moparse_eval.expected_readback import read_expected
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from moparse_eval.source_obligations import audit_source_obligations

LIST = "# Contents\n\n- North\n  - Results: Page 17\n"
FLAT_TABLE = "# Contents\n\n| Title | Page |\n|---|---|\n| Results | 17 |\n"
PARENT_TABLE = "# Contents\n\n| Parent | Title | Page |\n|---|---|---|\n| North | Results | 17 |\n"


def _reference(tmp_path, text):
    directory = tmp_path / "reference" / "invented-toc"
    directory.mkdir(parents=True)
    (directory / "expected.md").write_text(text, encoding="utf-8")
    (directory / "manifest.json").write_text(json.dumps({
        "markdown": {"path": "expected.md"},
        "source_map": {"entries": [{"source_pages": [1], "markdown_lines": [1, len(text.splitlines())]}]},
    }), encoding="utf-8")
    return read_expected({"id": "invented-toc", "document_id": "invented-toc", "source_pages": [1]}, directory.parent)


def _facts(graph):
    by_id = {node["id"]: node for node in graph["nodes"]}
    return [by_id[ident] for ident in graph["projections"]["B"]]


def test_navigation_schema_cannot_waive_an_unrepresented_ordinary_heading(tmp_path):
    reference = _reference(tmp_path, FLAT_TABLE.replace("# Contents", "# North"))
    graph = compile_requirement_graph(reference)
    assert _facts(graph) and all(not fact.get("directory_evidence") for fact in _facts(graph))
    assert graph["semantic_complete"] is False
    heading_ids = {item["id"] for item in graph["source_obligation_inventory"]["obligations"]
                   if item.get("binding_role") == "heading_scope"}
    assert heading_ids and any(row["obligation_id"] in heading_ids and row["status"] == "pending"
                              for row in graph["source_obligation_coverage"]["dispositions"])
    validate_requirement_graph(graph, expected=reference)


def test_flat_explicit_navigation_schema_without_a_heading_remains_supported(tmp_path):
    reference = _reference(tmp_path, FLAT_TABLE.removeprefix("# Contents\n\n"))
    graph = compile_requirement_graph(reference)
    assert graph["semantic_complete"] is True and len(_facts(graph)) == 1
    assert _facts(graph)[0]["identity_facets"] == {"toc_parent": []}
    validate_requirement_graph(graph, expected=reference)


def _complete_graph(tmp_path, text=LIST):
    graph = compile_requirement_graph(_reference(tmp_path, text))
    assert graph["semantic_complete"] is True, "the mutation must start from a proven complete synthetic graph"
    return graph


def _edge(graph, kind):
    return next(edge for edge in graph["relations"] if edge["type"] == kind)


def _literal(graph, source):
    matches = [row for row in graph["source_obligation_inventory"]["sources"]
               if row["source"].get("path") == source.get("path")
               and row["source"].get("lines") == source.get("lines")
               and row["source"].get("cell") == source.get("cell")]
    assert len(matches) == 1, "each source must identify its own original literal"
    text = matches[0]["text"]
    start, end = source.get("text_span", [0, len(text)])
    return text[start:end]


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _drop_edge(graph, kind):
    removed = {edge["id"] for edge in graph["relations"] if edge["type"] == kind}
    graph["relations"] = [edge for edge in graph["relations"] if edge["id"] not in removed]
    graph["projections"]["L"] = [ident for ident in graph["projections"]["L"] if ident not in removed]
    for row in graph["dispositions"]:
        layer = row["layers"]["L"]
        layer["requirements"] = [ident for ident in layer["requirements"] if ident not in removed]
        if layer["status"] == "interpreted" and not layer["requirements"]:
            layer.update(status="not_applicable", rule_id="forged_navigation_labels", reason="mutation synchronized the old indexes")


def _reaudit(graph, *, heading_pending=False):
    inventory = graph["source_obligation_inventory"]
    snapshot = json.dumps(inventory, sort_keys=True)
    graph["source_obligation_coverage"] = audit_source_obligations(inventory, graph)
    coverage = graph["source_obligation_coverage"]
    graph["semantic_complete"] = coverage["semantic_complete"]
    assert json.dumps(inventory, sort_keys=True) == snapshot
    assert coverage["semantic_complete"] is False
    pending = {row["obligation_id"] for row in coverage["dispositions"] if row["status"] == "pending"}
    assert pending
    if heading_pending:
        assert any(row["id"] in pending and row.get("binding_role") == "heading_scope"
                   for row in inventory["obligations"])
    return coverage


@pytest.mark.parametrize("text,parent,edge_types", [
    (LIST, ["North"], ["toc_entry_page", "toc_parent"]),
    (FLAT_TABLE, [], ["toc_entry_page"]),
    (PARENT_TABLE, ["North"], ["toc_entry_page", "toc_parent"]),
], ids=["list-parent", "printed-title-page-schema", "printed-parent-title-page-schema"])
def test_existing_navigation_protocol_proves_original_directory_and_each_entry_owner(tmp_path, text, parent, edge_types):
    expected = _reference(tmp_path, text)
    before = deepcopy(expected)
    graph = compile_requirement_graph(expected)
    assert expected == before
    assert [(fact["subject"], fact["attribute"], fact["value"], fact["identity_facets"])
            for fact in _facts(graph)] == [("Results", "Page", "17", {"toc_parent": parent})]
    assert [edge["type"] for edge in graph["relations"]] == edge_types
    assert all(fact["scope"] == [] for fact in _facts(graph))
    fact = _facts(graph)[0]
    assert _literal(graph, fact["source"]["subject_source"]) == "Results"
    assert _literal(graph, fact["value_source"]) == "17"
    assert _literal(graph, fact["attribute_source"]) == "Page"
    assert _literal(graph, fact["directory_evidence"][0]["source"]) == "Contents"
    for edge in graph["relations"]:
        binding = edge["binding_evidence"]
        assert _literal(graph, binding["entry_source"]) == "Results"
        assert _literal(graph, binding["page_source"]) == "17"
        assert _literal(graph, binding["attribute_source"]) == "Page"
        assert [_literal(graph, source) for source in binding["parent_sources"]] == parent
        assert edge["right"]["title"] == "Results"
        assert edge["right"]["parent_path"] == parent
    assert graph["source_obligation_coverage"]["source_complete"] is True
    assert graph["semantic_complete"] is True
    assert all(row["status"] != "pending" for row in graph["source_obligation_coverage"]["dispositions"])
    source_text = {row["text"] for row in graph["source_obligation_inventory"]["sources"]}
    expected_literals = {"Contents", "17"} if "|" in text else {"Contents", "North", "Results: Page 17"}
    assert expected_literals <= source_text
    validate_requirement_graph(graph, expected=expected)


@pytest.mark.parametrize("kind", ["toc_entry_page", "toc_parent"])
def test_retained_text_and_synchronized_dispositions_cannot_replace_an_actual_toc_edge(tmp_path, kind):
    graph = _complete_graph(tmp_path)
    assert len(_facts(graph)) == 1
    _drop_edge(graph, kind)
    _reaudit(graph, heading_pending=True)


def test_directory_type_labels_cannot_explain_unknown_ordinary_text(tmp_path):
    graph = compile_requirement_graph(_reference(tmp_path, "# Contents\n\nNorth\n"))
    assert graph["semantic_complete"] is False
    source = deepcopy(next(row["source"] for row in graph["source_obligation_inventory"]["sources"] if row["text"] == "North"))
    source["text_span"] = [0, 5]
    heading = next(row for row in graph["source_obligation_inventory"]["sources"] if row["text"] == "Contents")
    graph["nodes"].append({"id": "B:invented-directory-label", "kind": "fact", "subject": "North", "attribute": "Page",
        "value": "North", "scope": [], "role": "metric", "identity_facets": {"toc_parent": []},
        "semantic_type": "toc_page", "source": deepcopy(source), "subject_source": deepcopy(source),
        "value_source": deepcopy(source), "qualifiers": {},
        "directory_evidence": [{"text": "Contents", "source": deepcopy(heading["source"]), "role": "actual_directory_heading"}]})
    graph["projections"]["B"].append("B:invented-directory-label")
    _reaudit(graph, heading_pending=True)


@pytest.mark.parametrize("kind", ["toc_entry_page", "toc_parent"])
def test_source_bound_navigation_edges_must_remain_in_the_layout_projection(tmp_path, kind):
    graph = _complete_graph(tmp_path)
    graph["projections"]["L"].remove(_edge(graph, kind)["id"])
    # Transport validation itself also rejects an edge hidden from L.
    with pytest.raises(ValueError, match="projection"):
        validate_requirement_graph(graph)


def test_synchronized_wrong_parent_identity_cannot_reuse_the_original_north_source(tmp_path):
    graph = _complete_graph(tmp_path)
    _facts(graph)[0]["identity_facets"]["toc_parent"] = ["South"]
    for row in _walk({"nodes": graph["nodes"], "relations": graph["relations"], "toc": graph["context"]["toc_evidence"]}):
        if row.get("title") == "North":
            row["title"] = "South"
        if row.get("parent_path") == ["North"]:
            row["parent_path"] = ["South"]
    _reaudit(graph, heading_pending=True)


def test_synchronized_wrong_title_cannot_borrow_the_printed_page_label(tmp_path):
    graph = _complete_graph(tmp_path)
    fact = _facts(graph)[0]
    label = deepcopy(fact["attribute_source"])
    fact["subject"] = "Page"
    fact["subject_source"] = deepcopy(label)
    fact["source"]["subject_source"] = deepcopy(label)
    fact["value_source"]["subject_source"] = deepcopy(label)
    fact["row_evidence"][0].update(text="Page", raw_text="Page", source=deepcopy(label))
    for edge in graph["relations"]:
        for endpoint in (edge["left"], edge["right"]):
            if endpoint.get("title") == "Results":
                endpoint["title"] = "Page"
        edge["binding_evidence"]["entry_source"] = deepcopy(label)
        edge["binding_evidence"]["objects"]["entry"]["source"] = deepcopy(label)
        if edge["type"] == "toc_parent":
            edge["source"] = deepcopy(label)
    entry = graph["context"]["toc_evidence"]["entries"][0]
    entry.update(title="Page", title_evidence={"text": "Page", "source": deepcopy(label), "role": "toc_title"})
    _reaudit(graph, heading_pending=True)


def test_synchronized_page_binding_cannot_use_the_parent_label_as_page_data(tmp_path):
    graph = _complete_graph(tmp_path)
    fact = _facts(graph)[0]
    north = deepcopy(fact["row_evidence"][1]["source"])
    north["text_span"] = [0, 5]
    fact.update(value="North", raw_value="North", source=deepcopy(north), value_source=deepcopy(north))
    fact["data_evidence"].update(text="North", raw_text="North", source=deepcopy(north))
    for edge in graph["relations"]:
        edge["binding_evidence"]["page_source"] = deepcopy(north)
        edge["binding_evidence"]["objects"]["page"]["source"] = deepcopy(north)
        if edge["type"] == "toc_entry_page":
            edge["source"] = deepcopy(north)
    entry = graph["context"]["toc_evidence"]["entries"][0]
    entry.update(page="North", source=deepcopy(north))
    entry["page_evidence"].update(text="North", raw_text="North", source=deepcopy(north))
    _reaudit(graph, heading_pending=True)


def test_identical_title_and_page_in_another_branch_cannot_supply_this_entrys_source(tmp_path):
    graph = _complete_graph(tmp_path, LIST + "- South\n  - Results: Page 17\n")
    first, second = _facts(graph)
    other_title = deepcopy(second["source"]["subject_source"])
    first["source"]["subject_source"] = deepcopy(other_title)
    first["value_source"]["subject_source"] = deepcopy(other_title)
    first["row_evidence"][0]["source"] = deepcopy(other_title)
    for edge in graph["relations"]:
        if edge["right"].get("parent_path") != ["North"]:
            continue
        edge["binding_evidence"]["entry_source"] = deepcopy(other_title)
        edge["binding_evidence"]["objects"]["entry"]["source"] = deepcopy(other_title)
        if edge["type"] == "toc_parent":
            edge["source"] = deepcopy(other_title)
    graph["context"]["toc_evidence"]["entries"][0]["title_evidence"]["source"] = deepcopy(other_title)
    coverage = _reaudit(graph, heading_pending=True)
    pending = {row["obligation_id"] for row in coverage["dispositions"] if row["status"] == "pending"}
    assert any(row["id"] in pending and row.get("binding_role") == "heading_scope"
               and row["source"]["lines"] == [4, 4]
               for row in graph["source_obligation_inventory"]["obligations"])


@pytest.mark.parametrize("mutation", ["missing", "foreign-path", "foreign-line"])
def test_directory_evidence_needs_the_actual_selected_heading_source(tmp_path, mutation):
    graph = _complete_graph(tmp_path)
    for owner in [*_facts(graph), *graph["context"]["toc_evidence"]["entries"]]:
        if mutation == "missing":
            owner["directory_evidence"] = []
        elif mutation == "foreign-path":
            owner["directory_evidence"][0]["source"]["path"] = "<fabricated-directory>"
        else:
            owner["directory_evidence"][0]["source"]["lines"] = [99, 99]
    _reaudit(graph, heading_pending=True)


@pytest.mark.parametrize("text", [LIST, FLAT_TABLE], ids=["printed-label", "printed-header"])
def test_synchronized_attribute_evidence_cannot_borrow_the_title_literal(tmp_path, text):
    graph = _complete_graph(tmp_path, text)
    fact = _facts(graph)[0]
    title = deepcopy(fact["source"]["subject_source"])
    fact["attribute_source"] = deepcopy(title)
    fact["source"]["attribute_source"] = deepcopy(title)
    fact["value_source"]["attribute_source"] = deepcopy(title)
    fact["header_evidence"][0]["source"] = deepcopy(title)
    for edge in graph["relations"]:
        edge["binding_evidence"]["attribute_source"] = deepcopy(title)
    _reaudit(graph, heading_pending=True)


@pytest.mark.parametrize("text", [FLAT_TABLE, PARENT_TABLE], ids=["flat-schema", "parent-schema"])
def test_printed_table_schema_and_values_do_not_substitute_for_a_removed_page_binding(tmp_path, text):
    graph = _complete_graph(tmp_path, text)
    _drop_edge(graph, "toc_entry_page")
    assert {cell["text"] for cell in graph["context"]["text_projection"]["source_cells"]} >= {"Title", "Page", "Results", "17"}
    _reaudit(graph, heading_pending=True)
