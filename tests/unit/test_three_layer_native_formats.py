"""Independent saved-format contracts using five distinct native schemas.

These fixtures are invented content in the saved SDK field shapes. They test
readback only: no inference, PDFs, reference contents, or image inspection.
Pipeline-label fairness is deliberately a different test from format coverage.
"""

from __future__ import annotations

import copy
import inspect

import pytest

from moparse_eval.native_readback import read_native_relations
from moparse_eval.saved_native import read_saved_native
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate


def _observation(pipeline):
    return {
        "sample_id": "invented-format", "pipeline": pipeline, "status": "completed",
        "pages": [{"page": 1, "blocks": [], "width": 100, "height": 100}],
        "relations": [], "timing": {"processing_seconds": 4.125},
        "resources": {"preserved_original": True},
    }


def _docling():
    names = [("Name", 0, 0), ("Revenue", 0, 1), ("Profit", 0, 2),
             ("Delta", 1, 0), ("17", 1, 1), ("5", 1, 2)]
    table = {
        "self_ref": "#/tables/0", "label": "table", "parent": {"$ref": "#/body"},
        "prov": [{"page_no": 1}],
        "data": {"num_rows": 2, "num_cols": 3, "table_cells": [
            {"text": text, "start_row_offset_idx": row, "end_row_offset_idx": row + 1,
             "start_col_offset_idx": col, "end_col_offset_idx": col + 1,
             "row_span": 1, "col_span": 1, "column_header": row == 0,
             "row_header": False}
            for text, row, col in names
        ]},
    }
    document = {"body": {"self_ref": "#/body", "children": [{"$ref": "#/tables/0"}]},
                "tables": [table], "texts": [], "pages": {"1": {"size": {"width": 100, "height": 100}}}}
    return {"documents": [{"document": document}], "pages": [
        {"page": 1, "branch": "docling", "raw": {"native_document": "#/documents/0"}}
    ]}


def _paddle():
    return {"pages": [{"page": 1, "branch": "paddle", "raw": {"res": {
        "parsing_res_list": [{
            "block_label": "table", "block_id": 3, "block_order": 7,
            "block_content": '<table><thead><tr><th scope="col" id="n">Name</th>'
                '<th scope="col" id="r">Revenue</th><th scope="col" id="p">Profit</th>'
                '</tr></thead><tbody><tr><td headers="n">Delta</td>'
                '<td headers="r">17</td><td headers="p">5</td></tr></tbody></table>',
        }],
    }}}]}


def _glm():
    return {"pages": [{"page": 1, "branch": "glm", "raw": {
        "json_result": [[{"index": 9, "label": "table", "content":
            "| Name | Revenue | Profit |\n| --- | --- | --- |\n| Delta | 17 | 5 |\n"}]],
        "raw_json_result": [[{"index": 9, "label": "table", "content":
            "| Name | Revenue | Profit |\n| --- | --- | --- |\n| Delta | 999 | 999 |\n"}]],
    }}]}


def _mineru():
    return {"pages": [{"page": 1, "branch": "mineru", "raw": {"page_idx": 0, "blocks": [
        {"type": "table", "index": 8, "content": [
            {"type": "table_caption", "content": [{"type": "text", "content": "Results"}]},
            {"type": "table_body", "content": '<table><tr><th scope="col">Name</th>'
                '<th scope="col">Revenue</th><th scope="col">Profit</th></tr>'
                '<tr><td>Delta</td><td>17</td><td>5</td></tr></table>'},
        ], "markdown": "DO NOT READ THIS DISPLAY VIEW AS THE SOURCE TABLE"},
    ]}}]}


def _visual():
    return {"pages": [{"page": 1, "branch": "visual", "raw": [
        {"type": "title", "content": "Results", "bbox": [0, 0, 1, .1], "angle": 0},
        {"type": "table", "content":
            "| Name | Revenue | Profit |\n| --- | --- | --- |\n| Delta | 17 | 5 |\n",
         "bbox": [0, .1, 1, .9], "angle": 0},
        {"type": "image", "content": None, "bbox": [0, .9, 1, 1], "angle": 0},
    ]}]}


@pytest.fixture(params=[("P01", _docling), ("P03", _paddle), ("P05", _glm),
                         ("P07", _mineru), ("P08", _visual)],
                ids=["docling-reference-graph", "paddle-res-regions", "glm-primary-region-pages",
                     "docvortex-typed-container-spans", "visual-content-block-list"])
def native_case(request):
    pipeline, builder = request.param
    return _observation(pipeline), builder()


def test_five_distinct_saved_schemas_keep_text_roles_and_actual_source_paths(native_case):
    original, native = native_case
    before = copy.deepcopy((original, native))
    read = read_saved_native(native, original)
    assert (original, native) == before
    tables = [block for page in read["pages"] for block in page["blocks"] if block.get("cells")]
    assert len(tables) == 1
    table = tables[0]
    assert [cell["text"] for cell in table["cells"]] == ["Name", "Revenue", "Profit", "Delta", "17", "5"]
    assert [(cell["row"], cell["col"]) for cell in table["cells"]] == [
        (0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
    assert [cell.get("is_column_header", False) for cell in table["cells"]] == [True] * 3 + [False] * 3
    assert len({cell["id"] for cell in table["cells"]}) == 6
    assert all(cell["native_path"].startswith("#/") for cell in table["cells"])
    assert all(cell["parent_id"] == table["id"] for cell in table["cells"])
    assert read["timing"] == {"processing_seconds": 4.125}
    assert read["resources"] == {"preserved_original": True}
    assert read["native_reading"]["audit_views_used_as_answers"] is False


def test_business_binding_end_to_end_across_five_real_format_entries(native_case):
    original, native = native_case
    requirements = compile_markdown("Name: Delta; Revenue: 17; Profit: 5", sample_id="invented-format")
    assert [(f["role"], f["attribute"], f["value"]) for f in requirements["business"]] == [
        ("identity", "Name", "Delta"), ("metric", "Revenue", "17"), ("metric", "Profit", "5")]
    read = read_saved_native(native, original)
    evidence = read_candidate(read)
    assert len(evidence["business"]) == 3
    assert {f["attribute"] for f in evidence["business"]} == {"Name", "Revenue", "Profit"}
    assert all(f["source"]["path"].startswith("#/") for f in evidence["business"])
    result = grade_layers(requirements, evidence)
    assert result["publishable"] is True, result["blockers"]
    assert result["layers"]["B"]["denominator"] == 3
    assert result["layers"]["B"]["numerator"] == 3
    assert result["layers"]["B"]["score"] == 100


def test_wrong_profit_is_rejected_after_each_actual_format_entry(native_case):
    original, native = native_case
    branch = native["pages"][0]["branch"]
    if branch == "docling":
        native["documents"][0]["document"]["tables"][0]["data"]["table_cells"][-1]["text"] = "6"
    elif branch == "paddle":
        region = native["pages"][0]["raw"]["res"]["parsing_res_list"][0]
        region["block_content"] = region["block_content"].replace(">5<", ">6<")
    elif branch == "glm":
        region = native["pages"][0]["raw"]["json_result"][0][0]
        region["content"] = region["content"].replace("| 5 |", "| 6 |")
    elif branch == "mineru":
        region = native["pages"][0]["raw"]["blocks"][0]["content"][1]
        region["content"] = region["content"].replace(">5<", ">6<")
    else:
        region = native["pages"][0]["raw"][1]
        region["content"] = region["content"].replace("| 5 |", "| 6 |")
    requirements = compile_markdown("Name: Delta; Revenue: 17; Profit: 5", sample_id="invented-format")
    evidence = read_candidate(read_saved_native(native, original))
    assert len(evidence["business"]) == 3
    assert [f["value"] for f in evidence["business"] if f["attribute"] == "Profit"] == ["6"]
    result = grade_layers(requirements, evidence)
    business = [row for row in result["outcomes"] if row["layer"] == "B"]
    assert len(business) == 3
    assert {row["expected"]["attribute"]: row["outcome"] for row in business} == {
        "Name": "correct", "Revenue": "correct", "Profit": "incorrect"}
    assert result["layers"]["B"]["denominator"] == 3
    assert result["layers"]["B"]["numerator"] == 2


def test_format_entry_never_accepts_expected_or_selects_a_better_audit_value():
    assert tuple(inspect.signature(read_saved_native).parameters) == ("native", "observation")
    observation = _observation("P05")
    result = read_saved_native(_glm(), observation)
    block = result["pages"][0]["blocks"][0]
    assert block["source_view"] == "json_result"
    assert block["native_path"] == "#/pages/0/raw/json_result/0/0"
    assert [c["text"] for c in block["cells"]][-2:] == ["17", "5"]
    assert "999" not in block["text"]


def test_typed_container_does_not_replace_native_table_with_display_export():
    result = read_saved_native(_mineru(), _observation("P07"))
    blocks = result["pages"][0]["blocks"]
    assert [block["kind"] for block in blocks] == ["table_caption", "table_body"]
    assert blocks[0]["text"] == "Results"
    assert blocks[1]["native_path"] == "#/pages/0/raw/blocks/0/content/1"
    assert blocks[1]["native_table_container"] == "#/pages/0/raw/blocks/0"
    assert result["native_containers"][0]["native_children"] == [
        "#/pages/0/raw/blocks/0/content/0", "#/pages/0/raw/blocks/0/content/1"]


def test_visual_title_role_has_no_invented_level_and_null_image_keeps_neighbors():
    original, native = _observation("P08"), _visual()
    result = read_saved_native(native, original)
    result, _ = read_native_relations(result, native)
    blocks = result["pages"][0]["blocks"]
    assert [block["kind"] for block in blocks] == ["title", "table", "image"]
    assert blocks[0]["text"] == "Results" and "level" not in blocks[0]
    assert blocks[2]["text"] == "" and blocks[2]["native_path"] == "#/pages/0/raw/2"
    assert not any(edge["type"] == "heading_of" for edge in result["relations"])


def test_explicit_headers_and_data_values_remain_distinct_in_paddle_schema():
    native = _paddle()
    native["pages"][0]["raw"]["res"]["parsing_res_list"][0]["block_content"] = (
        '<table><thead><tr><th scope="col" id="status">Status</th>'
        '<th scope="col" id="other">Ready</th></tr></thead><tbody><tr>'
        '<td headers="status">Blocked</td><td headers="other">No</td></tr></tbody></table>')
    cells = read_saved_native(native, _observation("P03"))["pages"][0]["blocks"][0]["cells"]
    assert len(cells) == 4
    assert [(c["text"], c.get("is_column_header", False)) for c in cells] == [
        ("Status", True), ("Ready", True), ("Blocked", False), ("No", False)]
    assert cells[2]["native_attributes"] == {"headers": "status"}
    assert cells[0]["native_id"] == "status"
    evidence = read_candidate(read_saved_native(native, _observation("P03")))
    assert len(evidence["business"]) == 2
    assert [(f["attribute"], f["value"]) for f in evidence["business"]] == [
        ("Status", "Blocked"), ("Ready", "No")]
    for value, correct in [("Ready", 0), ("Blocked", 1)]:
        requirements = compile_markdown(f"Status: {value}", sample_id="invented-format")
        result = grade_layers(requirements, evidence)
        assert result["layers"]["B"]["denominator"] == 1
        assert result["layers"]["B"]["numerator"] == correct


def test_paddle_aria_roles_are_retained_as_source_metadata():
    native = _paddle()
    native["pages"][0]["raw"]["res"]["parsing_res_list"][0]["block_content"] = (
        '<table><tr><td role="columnheader" id="r">Revenue</td></tr>'
        '<tr><td role="cell" headers="r">17</td></tr></table>')
    cells = read_saved_native(native, _observation("P03"))["pages"][0]["blocks"][0]["cells"]
    assert len(cells) == 2
    assert cells[0]["native_attributes"] == {"role": "columnheader", "id": "r"}
    assert cells[1]["native_attributes"] == {"role": "cell", "headers": "r"}
    assert cells[0]["is_column_header"] is True
    assert cells[0]["native_header_declarations"] == ["role:columnheader"]
    evidence = read_candidate(read_saved_native(native, _observation("P03")))
    assert evidence["blockers"] == []
    assert len(evidence["business"]) == 1
    assert (evidence["business"][0]["attribute"], evidence["business"][0]["value"]) == ("Revenue", "17")


@pytest.mark.parametrize("schema", ["thead", "aria", "scope"])
def test_explicit_html_roles_reach_the_common_grader_and_reject_wrong_values(schema):
    if schema == "thead":
        html = '<table><thead><tr><td id="status">Status</td></tr></thead><tbody><tr><td headers="status">Blocked</td></tr></tbody></table>'
    elif schema == "aria":
        html = '<table><tr><td role="columnheader" id="status">Status</td></tr><tr><td role="cell" headers="status">Blocked</td></tr></table>'
    else:
        html = '<table><tr><th scope="col" id="status">Status</th></tr><tr><td headers="status">Blocked</td></tr></table>'
    native = _paddle()
    native["pages"][0]["raw"]["res"]["parsing_res_list"][0]["block_content"] = html
    evidence = read_candidate(read_saved_native(native, _observation("P03")))
    assert evidence["blockers"] == []
    assert len(evidence["business"]) == 1
    assert (evidence["business"][0]["attribute"], evidence["business"][0]["value"]) == ("Status", "Blocked")
    for value, correct in [("Blocked", 1), ("Ready", 0)]:
        result = grade_layers(compile_markdown(f"Status: {value}", sample_id="invented-format"), evidence)
        assert result["publishable"] is True
        assert result["layers"]["B"]["denominator"] == 1
        assert result["layers"]["B"]["numerator"] == correct


def test_first_td_row_is_not_turned_into_headers_without_a_declaration():
    native = _paddle()
    native["pages"][0]["raw"]["res"]["parsing_res_list"][0]["block_content"] = (
        "<table><tr><td>Status</td><td>Ready</td></tr><tr><td>Blocked</td><td>No</td></tr></table>")
    read = read_saved_native(native, _observation("P03"))
    cells = read["pages"][0]["blocks"][0]["cells"]
    assert len(cells) == 4
    assert all(not c.get("is_column_header") and not c.get("is_row_header") for c in cells)
    evidence = read_candidate(read)
    assert evidence["business"] == []
    assert [b["reason"] for b in evidence["blockers"]] == ["untyped_grid_semantics"]


def test_malformed_visual_sibling_does_not_hide_valid_business_text():
    native = {"pages": [{"page": 1, "branch": "visual", "raw": [
        {"type": "text", "content": "Name: Delta; Revenue: 17; Profit: 5"},
        42,
        {"type": "text", "content": "No dividend was approved."},
    ]}]}
    blocks = read_saved_native(native, _observation("P08"))["pages"][0]["blocks"]
    assert len(blocks) == 3
    assert blocks[0]["text"] == "Name: Delta; Revenue: 17; Profit: 5"
    assert blocks[1]["read_error_category"] == "candidate_native_structure"
    assert blocks[2]["text"] == "No dividend was approved."
