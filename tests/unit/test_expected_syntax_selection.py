"""Selection syntax tests use authored miniature documents, never the corpus."""

from __future__ import annotations

import copy
import json

import pytest

from moparse_eval.expected_readback import (
    ExpectedReadError,
    declared_scope,
    elements,
    markdown_observation,
    read_expected,
)


def authored(tmp_path, markdown, declarations, selected):
    root = tmp_path / "reference"
    directory = root / "invented"
    directory.mkdir(parents=True)
    path = directory / "expected.md"
    path.write_text(markdown)
    (directory / "manifest.json").write_text(json.dumps({
        "markdown": {"path": "expected.md"}, "source_map": {"entries": declarations},
    }))
    sample = {"id": "synthetic", "document_id": "invented", "source_pages": selected,
              "family_id": "family", "development_exposure": "invented", "tags": ["synthetic"]}
    return root, path, sample


def declaration(pages, start, end):
    return {"source_pages": pages, "markdown_lines": [start, end]}


def test_expected_entrypoint_preserves_raw_selected_text_without_business_compilation(tmp_path):
    markdown = "# Results\n\nUnit: 万元\n\n- Name: Delta; Revenue: 17; Profit: 5\n"
    root, path, sample = authored(tmp_path, markdown, [declaration([1], 1, 5)], [1])
    original = path.read_bytes()
    result = read_expected(sample, root)
    assert len(result["targets"]) == 3
    assert [row["text"] for row in result["targets"]] == [
        "Results", "Unit: 万元", "Name: Delta; Revenue: 17; Profit: 5"]
    assert [row["raw_text"] for row in result["targets"]] == [row["text"] for row in result["targets"]]
    assert result["targets"][1]["kind"] == "text"
    assert result["targets"][1]["raw"] == "Unit: 万元\n"
    assert all("record" not in row and "reference_context" not in row for row in result["targets"])
    assert all(row["outside_selection_context"] == [] for row in result["targets"])
    assert path.read_bytes() == original


def test_page_two_only_keeps_external_title_unit_and_period_as_input_boundary_evidence(tmp_path):
    markdown = "# Results 2027\n\nUnit: 万元\n\nPeriod: 2027\n\n- Revenue: 17\n"
    root, path, sample = authored(tmp_path, markdown,
                                 [declaration([1], 1, 5), declaration([2], 7, 7)], [2])
    result = read_expected(sample, root)
    assert len(result["targets"]) == 1
    [target] = result["targets"]
    assert target["text"] == "Revenue: 17"
    assert target["reference"] == {"path": str(path), "lines": [7, 7]}
    assert target["pages"] == [1]
    assert target["context"] == ["Results 2027"]
    assert [(item["kind"], item["text"], item["reference"]["lines"])
            for item in target["outside_selection_context"]] == [
                ("heading", "Results 2027", [1, 1]),
                ("explicit_unit_or_period", "Unit: 万元", [3, 3]),
                ("explicit_unit_or_period", "Period: 2027", [5, 5]),
            ]
    assert not {"record", "qualifiers", "reference_context", "unit", "period"} & target.keys()


def test_unselected_named_list_parent_has_an_exact_source(tmp_path):
    markdown = "- Name: Delta\n  - Revenue: 17\n"
    root, path, sample = authored(tmp_path, markdown,
                                 [declaration([1], 1, 1), declaration([2], 2, 2)], [2])
    [target] = read_expected(sample, root)["targets"]
    assert target["parents"] == ["Name: Delta"]
    assert target["outside_selection_context"] == [{
        "kind": "list_parent", "text": "Name: Delta", "raw": "- Name: Delta\n",
        "reference": {"path": str(path), "lines": [1, 1]},
    }]
    assert target["text"] == "Revenue: 17"


def test_partial_multiline_paragraph_uses_only_selected_lines(tmp_path):
    markdown = "The outside first line\nThe selected second line\nThe outside third line\n"
    root, path, sample = authored(tmp_path, markdown, [declaration([2], 2, 2)], [2])
    [target] = read_expected(sample, root)["targets"]
    assert target["text"] == "The selected second line"
    assert target["raw"] == "The selected second line\n"
    assert target["reference"] == {"path": str(path), "lines": [2, 2]}
    assert len(target["outside_selection_context"]) == 1
    assert target["outside_selection_context"][0]["kind"] == "partial_syntax_selection"
    assert target["outside_selection_context"][0]["reference"]["lines"] == [1, 3]


def test_partial_table_selection_does_not_import_its_unselected_header(tmp_path):
    markdown = "| Metric | Amount |\n|---|---|\n| Revenue | 17 |\n| Profit | 5 |\n"
    root, _, sample = authored(tmp_path, markdown, [declaration([2], 3, 4)], [2])
    [target] = read_expected(sample, root)["targets"]
    assert target["cells"] == []
    assert "Amount" not in target["text"]
    assert "Revenue" in target["text"] and "Profit" in target["text"]
    assert target["outside_selection_context"][0]["kind"] == "partial_syntax_selection"


def test_full_table_preserves_declared_cells_without_record_projections(tmp_path):
    markdown = "| Name | Revenue | Profit |\n|---|---|---|\n| Delta | 17 | 5 |\n"
    root, _, sample = authored(tmp_path, markdown, [declaration([1], 1, 3)], [1])
    [target] = read_expected(sample, root)["targets"]
    assert target["kind"] == "table"
    assert [cell["text"] for cell in target["cells"]] == ["Name", "Revenue", "Profit", "Delta", "17", "5"]
    assert "record" not in target
    assert target["raw"] == markdown
    assert target["raw_text"] == target["text"] == ""


def test_overlapping_selection_declarations_do_not_duplicate_authored_elements(tmp_path):
    root, _, sample = authored(tmp_path, "- Revenue: 17\n",
                                 [declaration([1], 1, 1), declaration([2], 1, 1)], [1, 2])
    result = read_expected(sample, root)
    assert len(result["targets"]) == 1
    assert result["targets"][0]["pages"] == [1, 2]


def test_mixed_selected_and_unselected_page_mapping_is_not_silent_input_support(tmp_path):
    root, path, sample = authored(tmp_path, "- Revenue: 17\n", [declaration([1, 2], 1, 1)], [2])
    _, scopes = declared_scope(sample, root)
    assert scopes[0]["declared_source_pages"] == [1, 2]
    assert scopes[0]["outside_source_pages"] == [1]
    [target] = read_expected(sample, root)["targets"]
    assert target["text"] == "Revenue: 17"
    assert target["outside_selection_context"] == [{
        "kind": "mixed_page_selection_declaration", "reference": {"path": str(path), "lines": [1, 1]},
        "declared_source_pages": [1, 2], "outside_source_pages": [1],
    }]


def test_cached_syntax_is_not_mutated_or_shaped_by_a_different_selection(tmp_path):
    root, _, sample = authored(tmp_path, "# Results\n\n- Revenue: 17\n",
                                 [declaration([1], 1, 1), declaration([2], 3, 3)], [1])
    cache = {}
    first = read_expected(sample, root, cache=cache)
    saved = copy.deepcopy(cache)
    second = read_expected({**sample, "source_pages": [2]}, root, cache=cache)
    assert cache == saved
    assert len(first["targets"]) == len(second["targets"]) == 1
    assert first["targets"][0]["text"] == "Results"
    assert second["targets"][0]["text"] == "Revenue: 17"
    assert second["targets"][0]["outside_selection_context"][0]["text"] == "Results"


@pytest.mark.parametrize("bounds", [[0, 1], [3, 1], [True, 2], [1], [1, 99]])
def test_unreadable_selection_declarations_are_software_errors_not_candidate_scores(tmp_path, bounds):
    root, _, sample = authored(tmp_path, "- Revenue: 17\n", [{"source_pages": [1], "markdown_lines": bounds}], [1])
    with pytest.raises(ExpectedReadError):
        read_expected(sample, root)


def test_public_list_reading_never_fabricates_tables_or_hidden_field_cells():
    observation = markdown_observation("# Results\n\n- Name: Delta\n  - Revenue: 17; Profit: 5\n",
                                       sample_id="synthetic", pipeline="P08", pages=[1])
    blocks = observation["pages"][0]["blocks"]
    assert len(blocks) == 3
    assert blocks[0]["heading_level"] == 1
    assert blocks[1]["text"] == "Name: Delta"
    assert blocks[1]["public_has_children"] is True
    assert blocks[2]["public_list_parents"] == ["Name: Delta"]
    assert blocks[2]["public_lines"] == [4, 4]
    assert blocks[2]["public_raw"] == "  - Revenue: 17; Profit: 5\n"
    assert all("cells" not in block and "native_table_container" not in block for block in blocks)


def test_public_grid_header_roles_come_only_from_actual_table_syntax():
    markdown = "| Status | Ready |\n|---|---|\n| Blocked | No |\n"
    observation = markdown_observation(markdown, sample_id="synthetic", pipeline="P08", pages=[1])
    [block] = observation["pages"][0]["blocks"]
    assert block["kind"] == "table"
    assert [cell["text"] for cell in block["cells"]] == ["Status", "Ready", "Blocked", "No"]
    assert [cell["is_column_header"] for cell in block["cells"]] == [True, True, False, False]
    assert block["public_raw"] == markdown


def test_tabs_inside_an_ordinary_paragraph_do_not_create_semantic_record_fragments():
    result = elements("Revenue: 17\tProfit: 5\n")
    assert len(result) == 1
    assert result[0].text == "Revenue: 17\tProfit: 5"
    assert result[0].part_index is None
