"""External explanation is distinct from an input-dependent requirement."""

import json

from moparse_eval.expected_readback import read_expected
from moparse_eval.three_layer import compile_expected, grade_layers, read_candidate_markdown


def selected(tmp_path, markdown, entries, pages):
    directory = tmp_path / "reference" / "invented"
    directory.mkdir(parents=True)
    (directory / "expected.md").write_text(markdown)
    (directory / "manifest.json").write_text(json.dumps({
        "markdown": {"path": "expected.md"}, "source_map": {"entries": entries},
    }))
    return read_expected({"id": "synthetic", "document_id": "invented", "source_pages": pages}, directory.parent)


def entry(page, start, end):
    return {"source_pages": [page], "markdown_lines": [start, end]}


def test_external_root_is_retained_as_explanation_without_becoming_a_candidate_obligation(tmp_path):
    expected = selected(tmp_path, "# External report\n\n## Results\n\nRevenue: 17\n",
                        [entry(1, 1, 1), entry(2, 3, 5)], [2])
    graph = compile_expected(expected)
    assert graph["business"][0]["scope"] == ["Results"]
    assert graph["business"][0]["qualifiers"] == {}
    assert graph["blockers"] == []
    assert graph["scope_context"][0]["required"] is False
    score = grade_layers(graph, read_candidate_markdown("## Results\n\nRevenue: 17\n"))
    assert score["publishable"] is True
    assert score["layers"]["B"]["score"] == 100


def test_an_unselected_unit_directly_scoping_the_selected_metric_remains_a_blocker(tmp_path):
    expected = selected(tmp_path, "Unit: 万元\n\nRevenue: 17\n",
                        [entry(1, 1, 1), entry(2, 3, 3)], [2])
    graph = compile_expected(expected)
    assert len(graph["business"]) == 1
    assert graph["business"][0]["qualifiers"] == {}
    assert [x["reason"] for x in graph["blockers"]] == ["input_scope_context"]
    assert graph["blockers"][0]["outside_selection"][0]["text"] == "Unit: 万元"


def test_external_unit_before_a_different_table_cannot_cross_an_image_into_a_new_record(tmp_path):
    markdown = "Unit: 万元\n\n| Metric | Value |\n|---|---|\n| Cost | 6 |\n\n![Diagram](asset.png)\n\nRevenue: 17亿元\n"
    expected = selected(tmp_path, markdown, [entry(1, 1, 7), entry(2, 9, 9)], [2])
    [target] = expected["targets"]
    assert target["outside_selection_context"] == []
    graph = compile_expected(expected)
    assert graph["blockers"] == []
    assert graph["business"][0]["qualifiers"] == {"unit": "亿元"}


def test_external_unit_does_not_scope_a_new_prose_paragraph_without_a_data_role(tmp_path):
    expected = selected(tmp_path, "Unit: 万元\n\nA quiet passage.\n",
                        [entry(1, 1, 1), entry(2, 3, 3)], [2])
    assert expected["targets"][0]["outside_selection_context"] == []
    graph = compile_expected(expected)
    assert not [item for item in graph["blockers"] if item["reason"] == "input_scope_context"]
    assert graph["business"] == []
    assert graph["blockers"]
    assert graph["requirement_model"]["dispositions"][0]["layers"]["B"]["status"] == "unresolved"


def test_mixed_input_page_declaration_is_not_dismissed_as_an_external_heading(tmp_path):
    expected = selected(tmp_path, "Revenue: 17\n", [
        {"source_pages": [1, 2], "markdown_lines": [1, 1]},
    ], [2])
    graph = compile_expected(expected)
    assert [x["reason"] for x in graph["blockers"]] == ["input_scope_context"]
    assert graph["blockers"][0]["outside_selection"][0]["kind"] == "mixed_page_selection_declaration"


def test_local_explicit_unit_satisfies_the_requirement_without_an_external_default(tmp_path):
    expected = selected(tmp_path, "Unit: 万元\n\nRevenue: 17亿元\n",
                        [entry(1, 1, 1), entry(2, 3, 3)], [2])
    graph = compile_expected(expected)
    assert graph["blockers"] == []
    assert graph["business"][0]["qualifiers"] == {"unit": "亿元"}


def test_selected_replacement_declaration_ends_the_external_unit_scope(tmp_path):
    expected = selected(tmp_path, "Unit: 万元\n\nUnit: 亿元\n\nRevenue: 17\n",
                        [entry(1, 1, 1), entry(2, 3, 5)], [2])
    graph = compile_expected(expected)
    assert graph["blockers"] == []
    assert graph["business"][0]["qualifiers"] == {"unit": "亿元"}
