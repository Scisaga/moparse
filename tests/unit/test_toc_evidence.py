"""Independent page-reference and hierarchy contracts in actual saved shapes."""

from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells, markdown_cells
from moparse_eval.saved_native import read_saved_native
from moparse_eval.toc_evidence import project_toc_text, read_toc

SOURCE = {"path": "#/invented/toc", "block": "toc"}
CONTENTS = ({"text": "Contents", "kind": "heading", "source": {"path": "#/contents", "block": "contents"}},)


def pairs(result):
    return [(entry["title"], entry["parent_path"], entry["page"]) for entry in result["entries"]]


def test_page_first_lines_require_their_own_printed_directory_context():
    text = "13 Alpha\n15 2024 Business review"
    result = read_toc(text=text, source=SOURCE, context=CONTENTS)
    assert result["matched"] is True and result["text_projection_complete"] is True
    assert pairs(result) == [("Alpha", [], "13"), ("2024 Business review", [], "15")]
    assert all(entry["parentage"] == "explicit" and entry["root_evidence"][0]["kind"] == "flat_text_entry_schema"
               for entry in result["entries"])
    assert read_toc(text=text, source=SOURCE)["matched"] is False


def test_dot_leaders_and_explicit_page_labels_keep_complete_title_and_page_spans():
    text = "2024 Business review .... 17\nAppendix A: Page A-1\nGovernance .... iv"
    result = read_toc(text=text, source=SOURCE, context=CONTENTS)
    assert pairs(result) == [("2024 Business review", [], "17"), ("Appendix A", [], "A-1"), ("Governance", [], "iv")]
    assert any(control["text"] == " .... " for control in result["controls"])
    assert result["facts"][1]["source"]["attribute_source"] is not None
    assert result["facts"][0]["source"]["attribute_source"] is None
    assert {atom["text"] for atom in result["text_atoms"]} >= {"2024 Business review", "17", "Appendix A", "Page", "A-1"}


@pytest.mark.parametrize("text", ["Revenue 17", "The revenue increased to 17.", "2024 Business review", "North 17\nSouth 23"])
def test_arbitrary_terminal_numbers_without_directory_role_stay_whole_text(text):
    result = read_toc(text=text, source=SOURCE)
    assert result["matched"] is False and result["facts"] == [] and result["entries"] == []
    assert result["unresolved"][0]["text"] == text
    assert result["unresolved"][0]["reason"] == "toc_context_unproven"


def test_markdown_list_parents_are_actual_objects_and_page_values_never_define_identity():
    text = "# Contents\n\n- North: Page 1\n  - Results: Page 17\n- South: Page 2\n  - Results: Page 23\n"
    result = read_toc(text=text, source=SOURCE)
    assert pairs(result) == [("North", [], "1"), ("Results", ["North"], "17"), ("South", [], "2"), ("Results", ["South"], "23")]
    changed = read_toc(text=text.replace("Page 17", "Page 18"), source=SOURCE)
    assert [(entry["id"], entry["title"], entry["parent_path"]) for entry in result["entries"]] == [
        (entry["id"], entry["title"], entry["parent_path"]) for entry in changed["entries"]]
    relations = [edge for edge in result["relations"] if edge["type"] == "toc_entry_page"]
    assert len(relations) == 4
    assert all("text" not in edge["right"] and "value" not in edge["right"] for edge in relations)
    assert [edge["binding_evidence"]["entry_id"] for edge in relations] == [edge["binding_evidence"]["entry_id"] for edge in changed["relations"] if edge["type"] == "toc_entry_page"]
    assert result["facts"][1]["identity_facets"] == {"toc_parent": ["North"]}


def test_wrong_parent_stays_wrong_even_when_another_branch_contains_the_desired_page_value():
    text = "# Contents\n\n- North: Page 1\n  - Results: Page 18\n- South: Page 2\n  - Results: Page 17\n"
    result = read_toc(text=text, source=SOURCE)
    assert pairs(result)[1] == ("Results", ["North"], "18")
    assert pairs(result)[3] == ("Results", ["South"], "17")
    assert result["entries"][1]["parent_evidence"][0]["title"] == "North"


@pytest.mark.parametrize("make_cells", [
    lambda: html_cells('<table><tr><th>Parent</th><th>Title</th><th>Page</th></tr>'
                       '<tr><td>North</td><td>Results</td><td>17</td></tr>'
                       '<tr><td>South</td><td>Results</td><td>23</td></tr></table>', "#/html"),
    lambda: markdown_cells('| Parent | Title | Page |\n|---|---|---|\n| North | Results | 17 |\n| South | Results | 23 |', "#/gfm"),
], ids=["declared-html-cells", "printed-gfm-schema"])
def test_explicit_parent_title_page_cells_prove_both_axes_without_a_directory_name(make_cells):
    cells = make_cells()
    before = deepcopy(cells)
    result = read_toc(cells=cells, source=SOURCE)
    assert result["matched"] is True and result["blockers"] == []
    assert pairs(result) == [("Results", ["North"], "17"), ("Results", ["South"], "23")]
    assert result["facts"][0]["source"]["row"] == 1 and result["facts"][0]["source"]["col"] == 2
    assert result["facts"][0]["data_evidence"]["source"]["cell"] == cells[5]["id"]
    assert cells == before


def test_typed_rowgroup_bounds_duplicate_leaves_and_does_not_delete_a_real_empty_page():
    cells = html_cells('<table><thead><tr><th>Title</th><th>Page</th></tr></thead>'
                       '<tr><th scope="rowgroup" colspan="2">North</th></tr><tr><td>Results</td><td>17</td></tr>'
                       '<tr><th scope="rowgroup" colspan="2">South</th></tr><tr><td>Results</td><td></td></tr></table>', "#/table")
    result = read_toc(cells=cells, source=SOURCE)
    assert pairs(result) == [("Results", ["North"], "17"), ("Results", ["South"], "")]
    assert result["entries"][1]["page_evidence"]["source"]["row"] == 4


def test_an_untyped_spanned_label_does_not_become_a_parent_or_disappear():
    cells = html_cells('<table><tr><th>Title</th><th>Page</th></tr><tr><td colspan="2">North</td></tr>'
                       '<tr><td>Results</td><td>17</td></tr></table>', "#/table")
    result = read_toc(cells=cells, source=SOURCE)
    assert pairs(result) == [("Results", [], "17")]
    assert any(item["text"] == "North" for item in result["unresolved"])
    assert any(atom["text"] == "North" for atom in result["text_atoms"])


def test_a_wrong_nonnumeric_value_under_an_explicit_page_column_is_preserved_for_comparison():
    cells = markdown_cells('| Title | Page |\n|---|---|\n| Results | TBD |', "#/gfm")
    assert pairs(read_toc(cells=cells, source=SOURCE)) == [("Results", [], "TBD")]


def test_a_numeric_layout_with_no_title_axis_remains_ambiguous_even_under_contents():
    cells = html_cells('<table><tr><td>17</td><td>23</td></tr><tr><td>18</td><td>24</td></tr></table>', "#/layout")
    result = read_toc(cells=cells, source=SOURCE, context=CONTENTS)
    assert result["entries"] == []
    assert result["issues"][0]["category"] == "candidate_ambiguity"
    assert result["blockers"] == []


@pytest.mark.parametrize("interruption", [{"id": "image", "kind": "image", "text": ""},
                                           {"id": "body", "kind": "text", "text": "The business generated revenue in 2024."},
                                           {"id": "document", "kind": "document_boundary", "text": ""}])
def test_directory_context_cannot_cross_media_new_documents_or_business_prose(interruption):
    blocks = [{"id": "contents", "kind": "title", "text": "Contents"},
              {"id": "first", "kind": "text", "text": "17 Results"}, interruption,
              {"id": "second", "kind": "text", "text": "23 Results"}]
    result = read_toc(blocks=blocks, source=SOURCE)
    assert pairs(result) == [("Results", [], "17")]
    assert any(item["source"].get("block") == "second" for item in result["unresolved"])


def test_management_heading_and_repeated_prefix_digits_do_not_manufacture_a_toc_role():
    result = read_toc(blocks=[{"id": "title", "kind": "heading", "text": "Management review"},
                              {"id": "entries", "kind": "text", "text": "13 Strategy\n15 Business review\n16 Infrastructure"}], source=SOURCE)
    assert result["matched"] is False and result["entries"] == []
    assert result["unresolved"][-1]["text"].endswith("16 Infrastructure")


def _native_case(branch):
    html = '<table><tr><th>Parent</th><th>Title</th><th>Page</th></tr><tr><td>North</td><td>Results</td><td>17</td></tr></table>'
    if branch == "docling":
        words = [("Parent", 0, 0), ("Title", 0, 1), ("Page", 0, 2), ("North", 1, 0), ("Results", 1, 1), ("17", 1, 2)]
        table = {"self_ref": "#/tables/0", "label": "document_index", "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}],
                 "data": {"num_rows": 2, "num_cols": 3, "table_cells": [
                     {"text": text, "start_row_offset_idx": row, "end_row_offset_idx": row + 1,
                      "start_col_offset_idx": col, "end_col_offset_idx": col + 1,
                      "row_span": 1, "col_span": 1, "column_header": row == 0} for text, row, col in words]}}
        doc = {"body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]}, "tables": [table], "texts": []}
        return {"documents": [{"document": doc}], "pages": [{"page": 1, "branch": branch, "raw": {"native_document": "#/documents/0"}}]}
    if branch == "paddle":
        raw = {"res": {"parsing_res_list": [{"block_label": "table", "block_id": 7, "block_order": 2, "block_content": html}]}}
    elif branch == "glm":
        raw = {"json_result": [[{"index": 7, "label": "table", "content": '| Parent | Title | Page |\n|---|---|---|\n| North | Results | 17 |'}]]}
    else:
        raw = [{"type": "title", "content": "Contents"}, {"type": "text", "content": "17 Results"}]
    return {"pages": [{"page": 1, "branch": branch, "raw": raw}]}


@pytest.mark.parametrize("branch", ["docling", "paddle", "glm", "visual"])
def test_four_actual_sdk_shapes_expose_their_own_navigation_objects(branch):
    native = _native_case(branch)
    original = {"sample_id": "navigation", "pipeline": "not-an-answer", "status": "completed", "pages": [{"page": 1, "blocks": []}]}
    observation = read_saved_native(native, original)
    before = deepcopy(observation)
    result = read_toc(blocks=[block for page in observation["pages"] for block in page["blocks"]], source=SOURCE)
    wanted_parent = [] if branch == "visual" else ["North"]
    assert pairs(result) == [("Results", wanted_parent, "17")]
    assert result["facts"][0]["source"].get("block", "").startswith("#/")
    assert result["facts"][0]["data_evidence"]["source"]
    assert result["blockers"] == [] and observation == before


def test_multiline_native_contents_heading_and_printed_page_axis_are_read_without_rewriting():
    title = "Acme Corporation\nTable of Contents"
    blocks = [{"id": "title", "kind": "paragraph_title", "text": title},
              {"id": "table", "kind": "table", "cells": html_cells('<table><tr><td></td><td>Page</td></tr>'
                  '<tr><td>DEFINITIONS</td><td>3</td></tr></table>', "#/table")}]
    result = read_toc(blocks=blocks, source=SOURCE)
    assert pairs(result) == [("DEFINITIONS", [], "3")]
    assert any(atom["text"] == title for atom in result["text_atoms"])
    assert result["facts"][0]["source"]["attribute_source"]["cell"].endswith("cell[1]")


def test_independent_page_caption_has_a_finite_alias_for_each_real_entry_object():
    blocks = [{"id": "contents", "kind": "title", "text": "Contents"},
              {"id": "page-caption", "kind": "table_caption", "text": "Page"},
              {"id": "table", "kind": "table", "cells": html_cells('<table><tr><td>North</td><td>17</td></tr>'
                  '<tr><td>South</td><td>23</td></tr></table>', "#/table")}]
    result = read_toc(blocks=blocks, source=SOURCE)
    assert pairs(result) == [("North", [], "17"), ("South", [], "23")]
    assert all(fact["source"]["attribute_source"]["block"] == "page-caption" for fact in result["facts"])
    [page] = [atom for atom in result["text_atoms"] if atom["text"] == "Page"]
    assert len(page["aliases"]) == 2
    assert len({alias["data_source"]["cell"] for alias in page["aliases"]}) == 2
    assert all(alias["origin"]["block"] == "page-caption" for alias in page["aliases"])


def test_explicit_container_caption_can_appear_after_its_table_without_being_borrowed_by_a_neighbor():
    blocks = [{"id": "contents", "kind": "title", "text": "Contents"},
              {"id": "table", "kind": "table_body", "parent_id": "container", "cells": html_cells(
                  '<table><tr><td>North</td><td>17</td></tr></table>', "#/table")},
              {"id": "page-caption", "kind": "table_caption", "parent_id": "container", "text": "Page"},
              {"id": "neighbor", "kind": "table", "cells": html_cells('<table><tr><td>South</td><td>23</td></tr></table>', "#/neighbor")}]
    result = read_toc(blocks=blocks, source=SOURCE)
    assert result["facts"][0]["source"]["attribute_source"]["block"] == "page-caption"
    assert result["facts"][1]["source"]["attribute_source"] is None
    [page] = [atom for atom in result["text_atoms"] if atom["text"] == "Page"]
    assert len(page["aliases"]) == 1 and page["aliases"][0]["data_source"]["block"] == "table"


def test_whole_markdown_preserves_contents_and_business_text_before_and_after_its_table():
    text = '# Contents\n\n| Title | Page |\n|---|---|\n| Results | 17 |\n\nFollowing business prose is required too.'
    result = read_toc(text=text, source=SOURCE)
    assert pairs(result) == [("Results", [], "17")]
    assert result["text_projection_complete"] is True
    literal = [atom["text"] for atom in result["text_atoms"]]
    assert "Contents" in literal and "Following business prose is required too." in literal
    assert result["unresolved"][-1]["text"] == "Following business prose is required too."


def test_explicit_native_parent_swaps_parentage_without_changing_text_or_reading_order():
    def candidate(parent):
        return [{"id": "contents", "kind": "title", "text": "Contents", "level": 1},
                {"id": "north", "kind": "heading", "text": "North", "level": 2},
                {"id": "south", "kind": "heading", "text": "South", "level": 2},
                {"id": "entry", "kind": "toc_entry", "text": "Results: Page 17", "parent_id": parent}]
    first, changed = (read_toc(blocks=candidate(parent), source=SOURCE) for parent in ["north", "south"])
    assert pairs(first) == [("Results", ["North"], "17")]
    assert pairs(changed) == [("Results", ["South"], "17")]
    assert first["entries"][0]["parent_evidence"][0]["source"]["block"] == "north"


def test_native_parent_entry_page_changes_do_not_change_a_childs_actual_parent_identity():
    blocks = [{"id": "contents", "kind": "title", "text": "Contents"},
              {"id": "north", "kind": "toc_entry", "text": "North: Page 1"},
              {"id": "child", "kind": "toc_entry", "text": "Results: Page 17", "parent_id": "north"}]
    result = read_toc(blocks=blocks, source=SOURCE)
    blocks[1]["text"] = "North: Page 99"
    changed = read_toc(blocks=blocks, source=SOURCE)
    assert pairs(result)[1] == pairs(changed)[1] == ("Results", ["North"], "17")


def test_text_sources_point_at_actual_heading_and_entry_literals_in_the_whole_markdown():
    text = '# Contents\n\n17 Results\n'
    result = read_toc(text=text, source=SOURCE)
    assert pairs(result) == [("Results", [], "17")]
    for atom in result["text_atoms"]:
        assert text[slice(*atom["source"]["text_span"])] == atom["text"]
    assert any(control["text"] == "# " for control in result["controls"])


def test_cell_spans_are_relative_to_the_actual_cell_text_not_the_entire_markdown_container():
    text = '# Contents\n\n| Title | Page |\n|---|---|\n| Results | 17 |'
    result = read_toc(text=text, source=SOURCE)
    page = result["entries"][0]["page_evidence"]["source"]
    assert page["text_span"] == [0, 2]
    assert page["text_span_basis"] == "native_cell_text"
    assert "| Title | Page |" in text[slice(*page["container_text_span"])]


def test_unmatched_table_text_is_preserved_once_per_original_cell():
    result = read_toc(cells=html_cells('<table><tr><td>Alpha</td><td>Beta</td></tr></table>', "#/layout"), source=SOURCE)
    assert result["matched"] is False
    assert [atom["text"] for atom in result["text_atoms"]] == ["Alpha", "Beta"]


def test_html_caption_directory_title_is_preserved_with_its_actual_navigation_table():
    text = '<table><caption>Contents</caption><tr><th>Title</th><th>Page</th></tr>'
    text += '<tr><td>Results</td><td>17</td></tr></table>'
    result = read_toc(text=text, source=SOURCE, text_format="html")
    assert pairs(result) == [("Results", [], "17")]
    assert "Contents" in [atom["text"] for atom in result["text_atoms"]]


def test_one_explicit_native_entry_does_not_turn_later_business_text_into_a_directory():
    result = read_toc(blocks=[{"id": "native-entry", "kind": "toc_entry", "text": "Results: Page 17"},
                              {"id": "business", "kind": "text", "text": "23 Revenue"}], source=SOURCE)
    assert pairs(result) == [("Results", [], "17")]
    assert result["unresolved"][-1]["source"]["block"] == "business"


def test_existing_media_caption_text_is_preserved_without_reading_an_image_or_extending_toc_scope():
    result = read_toc(blocks=[{"id": "contents", "kind": "title", "text": "Contents"},
                              {"id": "image", "kind": "image", "text": "Printed image caption"},
                              {"id": "later", "kind": "text", "text": "23 Revenue"}], source=SOURCE)
    assert result["entries"] == []
    assert "Printed image caption" in [atom["text"] for atom in result["text_atoms"]]


def test_filenames_and_pipeline_metadata_do_not_supply_missing_navigation_roles():
    text = "13 Strategy\n15 Business review"
    result = read_toc(text=text, source={"path": "Acme/Contents/Page/native.json", "pipeline": "TOC"})
    assert result["matched"] is False and result["entries"] == []


def logical_relations(result):
    import json

    return sorted(json.dumps({key: edge[key] for key in ["type", "left", "right"]}, sort_keys=True)
                  for edge in result["relations"])


def test_five_actual_toc_forms_have_the_same_four_source_free_logical_relations():
    forms = [
        read_toc(text='# Contents\n\n## North\n\nResults .... 17\n\n## South\n\nResults .... 23', source=SOURCE),
        read_toc(text='# Contents\n\n- North\n  - Results: Page 17\n- South\n  - Results: Page 23', source=SOURCE),
        read_toc(cells=html_cells('<table><tr><th>Title</th><th>Page</th></tr>'
            '<tr><th scope="rowgroup" colspan="2">North</th></tr><tr><td>Results</td><td>17</td></tr>'
            '<tr><th scope="rowgroup" colspan="2">South</th></tr><tr><td>Results</td><td>23</td></tr></table>', "#/table"), source=SOURCE),
        read_toc(cells=markdown_cells('| Parent | Title | Page |\n|---|---|---|\n| North | Results | 17 |\n| South | Results | 23 |', "#/gfm"), source=SOURCE),
    ]
    native = _native_case("docling")
    document = native["documents"][0]["document"]
    cells = document["tables"][0]["data"]["table_cells"]
    for cell in deepcopy(cells[3:]):
        cell["text"] = {"North": "South", "17": "23"}.get(cell["text"], cell["text"])
        cell["start_row_offset_idx"], cell["end_row_offset_idx"] = 2, 3
        cells.append(cell)
    document["tables"][0]["data"]["num_rows"] = 3
    observation = read_saved_native(native, {"pages": [{"page": 1, "blocks": []}]})
    forms.append(read_toc(blocks=observation["pages"][0]["blocks"], source=SOURCE))
    assert all(pairs(result) == [("Results", ["North"], "17"), ("Results", ["South"], "23")] for result in forms)
    for result in forms:
        assert len(result["relations"]) == 4
        assert [edge["type"] for edge in result["relations"]].count("toc_entry_page") == 2
        assert [edge["type"] for edge in result["relations"]].count("toc_parent") == 2
        assert logical_relations(result) == logical_relations(forms[0])
        for edge in result["relations"]:
            assert "source" not in edge["left"] and "source" not in edge["right"]
            assert "entry_id" not in edge["left"] and "entry_id" not in edge["right"]
            assert edge["binding_evidence"]["entry_id"]
            assert edge["object_anchor"] is None
            assert edge["binding_evidence"]["objects"]["entry"]["source"]


def test_page_changes_leave_logical_binding_unchanged_and_parent_changes_do_change_it():
    text = '# Contents\n\n- North\n  - Results: Page 17\n- South\n  - Results: Page 23'
    result = read_toc(text=text, source=SOURCE)
    wrong_page = read_toc(text=text.replace('Page 17', 'Page 170'), source=SOURCE)
    wrong_parent = read_toc(text=text.replace('- North', '- West'), source=SOURCE)
    assert logical_relations(result) == logical_relations(wrong_page)
    assert logical_relations(result) != logical_relations(wrong_parent)


def test_three_levels_emit_only_direct_parent_edges_without_extra_transitive_votes():
    result = read_toc(text='# Contents\n\n- North: Page 1\n  - Division: Page 2\n    - Results: Page 17', source=SOURCE)
    assert pairs(result)[-1] == ('Results', ['North', 'Division'], '17')
    assert len(result['relations']) == 5
    parent = [edge for edge in result['relations'] if edge['type'] == 'toc_parent']
    assert len(parent) == 2
    assert parent[-1]['left'] == {'type': 'toc_entry_parent', 'title': 'Division', 'parent_path': ['North']}


def test_bulk_handled_ids_exclude_inactive_business_blocks_and_preserve_actual_snapshots():
    blocks = [{"id": "before", "kind": "text", "text": "Ordinary business before."},
              {"id": "contents", "kind": "title", "text": "Contents"},
              {"id": "page", "kind": "table_caption", "text": "Page"},
              {"id": "entry", "kind": "text", "text": "17 Results"},
              {"id": "after", "kind": "text", "text": "Ordinary business after."}]
    result = read_toc(blocks=blocks, source=SOURCE)
    assert set(result["handled_block_ids"]) == {"contents", "page", "entry"}
    assert {fragment["source"]["block"]: fragment["text"] for fragment in result["source_fragments"]} == {
        block["id"]: block["text"] for block in blocks}
    projection = project_toc_text(result)
    assert {atom["text"] for atom in projection["atoms"]} == {"Contents", "Page", "17", "Results"}


def test_explicit_block_source_dictionary_preserves_real_reference_path_and_lines():
    blocks = [{"id": "contents", "kind": "title", "text": "Contents", "source": {"path": "reference.md", "lines": [10, 10]}},
              {"id": "entry", "kind": "text", "text": "Results: Page 17", "source": {"path": "reference.md", "lines": [12, 12]}}]
    result = read_toc(blocks=blocks, source={"path": "not-the-real-source"})
    assert result["facts"][0]["source"]["path"] == "reference.md"
    assert result["facts"][0]["source"]["lines"] == [12, 12]
    assert result["facts"][0]["scope"] == []
    assert result["entries"][0]["directory_evidence"][0]["source"]["lines"] == [10, 10]


def test_projector_uses_exact_printed_page_label_and_finite_actual_data_objects():
    result = read_toc(cells=html_cells('<table><tr><th>Title</th><th>页码</th></tr>'
        '<tr><td>North</td><td>17</td></tr><tr><td>South</td><td>23</td></tr></table>', "#/table"), source=SOURCE)
    projection = project_toc_text(result)
    aliases = [atom for atom in projection["atoms"] if atom.get("projection_kind") == "bounded_alias"]
    assert [atom["text"] for atom in aliases] == ["页码", "页码"]
    assert not any(atom["text"] == "Page" for atom in projection["atoms"])
    assert len({atom["data_object"]["source"]["cell"] for atom in aliases}) == 2
    assert len(projection["source_cells"]) == 6
    from moparse_eval.expected_report import _origin_literal, _text_sources

    cells, fragments = _text_sources(projection)
    for origin in projection["origins"]:
        _origin_literal(origin, cells, fragments)


def test_projector_preserves_the_source_snapshot_and_refuses_an_invented_alias_literal():
    result = read_toc(cells=markdown_cells('| Title | Page |\n|---|---|\n| Results | 17 |', "#/table"), source=SOURCE)
    corrupted = deepcopy(result)
    next(atom for atom in corrupted["text_atoms"] if atom.get("aliases"))["aliases"][0]["text"] = "Invented"
    projection = project_toc_text(corrupted)
    assert projection["complete"] is False and projection["blockers"]


def test_multiple_directory_identities_are_explicitly_unresolved_until_the_caller_binds_them():
    result = read_toc(blocks=[{"id": "a", "kind": "title", "text": "North Table of Contents"},
                              {"id": "a-entry", "kind": "text", "text": "17 Results"},
                              {"id": "b", "kind": "title", "text": "South Table of Contents"},
                              {"id": "b-entry", "kind": "text", "text": "23 Results"}], source=SOURCE)
    assert [entry["directory_evidence"][0]["text"] for entry in result["entries"]] == ["North Table of Contents", "South Table of Contents"]
    assert any(blocker["reason"] == "toc_multiple_directory_scope_alignment_unsupported" for blocker in result["blockers"])


@pytest.mark.parametrize("references", [('t', 'p'), ('p', 't')], ids=['valid-own-references', 'references-only-swap'])
def test_explicit_headers_are_not_silently_replaced_by_geometric_fallback(references):
    title_ref, page_ref = references
    html = '<table><tr><th id="t">Title</th><th id="p">Page</th></tr>'
    html += f'<tr><td headers="{title_ref}">Results</td><td headers="{page_ref}">17</td></tr>'
    html += '<tr><td>Other</td><td>23</td></tr></table>'
    result = read_toc(cells=html_cells(html, "#/table"), source=SOURCE)
    assert pairs(result) == [('Other', [], '23')]
    assert result['complete'] is False
    [issue] = [item for item in result['blockers'] if item['reason'] == 'toc_explicit_header_reference_interpretation_unsupported']
    assert issue['category'] == 'software_unsupported'
    assert {source['row'] for source in issue['affected_data_sources']} == {1}
    assert set(issue['header_ids']) == {'t', 'p'}
    assert {atom['text'] for atom in result['text_atoms']} >= {'Results', '17', 'Other', '23'}


def test_empty_cell_carrier_does_not_swallow_existing_native_literal_text():
    result = read_toc(blocks=[{'id': 'contents', 'kind': 'title', 'text': 'Contents'},
                              {'id': 'empty-grid', 'kind': 'table', 'cells': [], 'text': 'Existing required words'}], source=SOURCE)
    assert 'Existing required words' in [atom['text'] for atom in result['text_atoms']]


def test_active_unpaged_toc_group_keeps_its_real_label_source_and_allows_its_referenced_child():
    blocks = [{'id': 'contents', 'kind': 'heading', 'text': 'Contents', 'heading_level': 1,
               'source': {'path': 'reference.md', 'lines': [10, 10]}},
              {'id': 'north', 'kind': 'toc_group', 'text': 'North', 'source': {'path': 'reference.md', 'lines': [12, 12]}},
              {'id': 'leaf', 'kind': 'text', 'text': 'Results: Page 17', 'parent_id': 'north',
               'source': {'path': 'reference.md', 'lines': [13, 13]}}]
    result = read_toc(blocks=blocks, source={'path': '<selected-syntax>'})
    assert pairs(result) == [('Results', ['North'], '17')]
    assert set(result['handled_block_ids']) == {'contents', 'north', 'leaf'}
    assert result['entries'][0]['parent_evidence'][0]['source']['lines'] == [12, 12]
    projection = project_toc_text(result)
    from moparse_eval.expected_report import _origin_literal, _text_sources

    cells, fragments = _text_sources(projection)
    for origin in projection['origins']:
        _origin_literal(origin, cells, fragments)
    assert {atom['text'] for atom in projection['atoms']} == {'Contents', 'North', 'Results', 'Page', '17'}


def test_an_inactive_unpaged_group_does_not_activate_navigation_for_an_ordinary_child():
    result = read_toc(blocks=[{'id': 'group', 'kind': 'toc_group', 'text': 'North'},
                              {'id': 'leaf', 'kind': 'text', 'text': 'Results: Page 17', 'parent_id': 'group'}], source=SOURCE)
    assert result['matched'] is False and result['entries'] == []
    assert result['handled_block_ids'] == []


@pytest.mark.parametrize('parent_first', [True, False])
def test_paged_toc_group_keeps_its_own_page_fact_and_uses_only_its_title_as_child_parent(parent_first):
    parent = {'id': 'north', 'kind': 'toc_group', 'text': 'North: Page 1'}
    leaf = {'id': 'leaf', 'kind': 'text', 'text': 'Results: Page 17', 'parent_id': 'north'}
    items = [parent, leaf] if parent_first else [leaf, parent]
    result = read_toc(blocks=[{'id': 'contents', 'kind': 'heading', 'text': 'Contents'}, *items], source=SOURCE)
    assert sorted(pairs(result)) == [('North', [], '1'), ('Results', ['North'], '17')]
    assert len(result['facts']) == 2
    assert len(result['relations']) == 3


def test_public_expected_unpaged_parents_and_real_gfm_candidate_keep_two_business_and_four_logical_targets(tmp_path):
    import json

    from moparse_eval.expected_readback import markdown_observation, read_expected
    from moparse_eval.three_layer import compile_expected, grade_layers, read_candidate

    directory = tmp_path / 'reference' / 'controlled-toc'
    directory.mkdir(parents=True)
    text = '# Contents\n\n- North\n  - Results: Page 17\n- South\n  - Results: Page 23\n'
    (directory / 'expected.md').write_text(text)
    (directory / 'manifest.json').write_text(json.dumps({'markdown': {'path': 'expected.md'}, 'source_map': {'entries': [
        {'source_pages': [1], 'markdown_lines': [1, len(text.splitlines())]}]}}))
    expected = read_expected({'id': 'controlled-toc', 'document_id': 'controlled-toc', 'source_pages': [1]}, directory.parent)
    requirements = compile_expected(expected)
    assert len(requirements['business']) == 2
    assert {edge['type'] for edge in requirements['relations']} == {'toc_entry_page', 'toc_parent'}
    assert len(requirements['relations']) == 4
    candidate = '# Contents\n\n| Parent | Title | Page |\n|---|---|---|\n| North | Results | 17 |\n| South | Results | 23 |\n'
    observation = markdown_observation(candidate, sample_id='controlled-toc', pipeline='controlled', pages=[1])
    graph = read_candidate(observation)
    score = grade_layers(requirements, graph)
    assert score['publishable'] is True
    assert score['layers']['B']['score'] == score['layers']['L']['score'] == 100
    assert score['layers']['B']['denominator'] == 2 and score['layers']['L']['denominator'] == 4
    from moparse_eval.expected_report import validate_evidence

    validate_evidence(score)


def test_generated_entry_ordinals_never_override_logical_matching_after_complete_record_reordering():
    from moparse_eval.relation_correspondence import grade_relations
    from moparse_eval.three_layer import canonical

    before = '# Contents\n\n- North\n  - Results: Page 17\n- South\n  - Results: Page 23'
    after = '# Contents\n\n- South\n  - Results: Page 23\n- North\n  - Results: Page 17'
    reference, candidate = (read_toc(text=text, source=SOURCE) for text in [before, after])
    assert all(edge['object_anchor'] is None for result in [reference, candidate] for edge in result['relations'])
    for result in [reference, candidate]:
        for index, edge in enumerate(result['relations']):
            edge['id'] = f'L:{index}'
    layer, outcomes = grade_relations(reference['relations'], candidate['relations'], canonicalize=canonical)
    assert layer['denominator'] == layer['numerator'] == 4
    assert len(outcomes) == 4 and all(outcome['outcome'] == 'correct' for outcome in outcomes)


def test_only_declared_native_data_ids_can_supply_independent_relation_anchors():
    cells = html_cells('<table><tr><th>Title</th><th>Page</th></tr><tr><td id="title-object">Results</td>'
                       '<td id="page-object">17</td></tr></table>', '#/table')
    result = read_toc(cells=cells, source=SOURCE)
    assert result['relations'][0]['object_anchor'] == 'page-object'
    assert result['relations'][0]['binding_evidence']['entry_id'] != 'page-object'


def test_bulk_cells_do_not_swallow_their_own_html_caption_or_page_declaration():
    html = '<table><caption>Page</caption><tr><td>Results</td><td>17</td></tr></table>'
    result = read_toc(blocks=[{'id': 'contents', 'kind': 'title', 'text': 'Contents'},
                              {'id': 'table', 'kind': 'table', 'cells': html_cells(html, '#/table'),
                               'text': html, 'text_format': 'html'}], source=SOURCE)
    assert pairs(result) == [('Results', [], '17')]
    assert result['facts'][0]['source']['attribute_source']['block'] == 'table'
    [page] = [atom for atom in result['text_atoms'] if atom['text'] == 'Page']
    assert len(page['aliases']) == 1
    assert html[slice(*page['source']['text_span'])] == 'Page'
    projection = project_toc_text(result)
    from moparse_eval.expected_report import _origin_literal, _text_sources

    cells, fragments = _text_sources(projection)
    for origin in projection['origins']:
        _origin_literal(origin, cells, fragments)


def test_toc_schema_keys_are_controls_but_identically_named_data_titles_remain_literals():
    result = read_toc(cells=markdown_cells('| Parent | Title | Page |\n|---|---|---|\n| North | Title | 17 |\n| South | Parent | 23 |', '#/table'), source=SOURCE)
    assert pairs(result) == [('Title', ['North'], '17'), ('Parent', ['South'], '23')]
    controls = [control for control in result['controls'] if control['reason'] == 'explicit_toc_title_parent_schema']
    assert {control['text'] for control in controls} == {'Parent', 'Title'}
    assert all(control['source']['row'] == 0 for control in controls)
    literal = [atom for atom in project_toc_text(result)['atoms'] if atom.get('projection_kind') == 'literal']
    assert [atom['text'] for atom in literal].count('Title') == 1
    assert [atom['text'] for atom in literal].count('Parent') == 1


def test_root_and_explicit_child_entries_always_declare_their_own_parent_identity_facet():
    root = read_toc(text='# Contents\n\n- Results: Page 17', source=SOURCE)
    child = read_toc(text='# Contents\n\n- North\n  - Results: Page 17', source=SOURCE)
    assert root['facts'][0]['identity_facets'] == {'toc_parent': []}
    assert child['facts'][0]['identity_facets'] == {'toc_parent': ['North']}
    flat = read_toc(cells=markdown_cells('| Title | Page |\n|---|---|\n| Results | 17 |', '#/table'), source=SOURCE)
    assert flat['facts'][0]['identity_facets'] == {'toc_parent': []}
    assert flat['entries'][0]['parentage'] == 'explicit'
    assert flat['entries'][0]['root_evidence'][0]['kind'] == 'flat_title_page_schema'


@pytest.mark.parametrize('expected_child', [True, False], ids=['child-required-flat-candidate', 'root-required-child-candidate'])
def test_public_same_leaf_and_page_cannot_cross_root_and_explicit_parent_identity(tmp_path, expected_child):
    import json

    from moparse_eval.expected_readback import markdown_observation, read_expected
    from moparse_eval.three_layer import compile_expected, grade_layers, read_candidate

    child = '# Contents\n\n- North\n  - Results: Page 17\n'
    root = '# Contents\n\n| Title | Page |\n|---|---|\n| Results | 17 |\n\nNorth\n'
    reference, candidate = (child, root) if expected_child else (root, child)
    directory = tmp_path / 'reference' / 'controlled-toc'
    directory.mkdir(parents=True)
    (directory / 'expected.md').write_text(reference)
    (directory / 'manifest.json').write_text(json.dumps({'markdown': {'path': 'expected.md'}, 'source_map': {'entries': [
        {'source_pages': [1], 'markdown_lines': [1, len(reference.splitlines())]}]}}))
    expected = read_expected({'id': 'root-child', 'document_id': 'controlled-toc', 'source_pages': [1]}, directory.parent)
    requirements = compile_expected(expected)
    graph = read_candidate(markdown_observation(candidate, sample_id='root-child', pipeline='controlled', pages=[1]))
    assert len(requirements['business']) == len(graph['business']) == 1
    score = grade_layers(requirements, graph)
    assert score['publishable'] is True
    assert score['layers']['B']['denominator'] == 1 and score['layers']['B']['numerator'] == 0
    assert score['layers']['T']['denominator'] == score['layers']['T']['numerator'] == 26
    from moparse_eval.expected_report import validate_evidence

    validate_evidence(score)
