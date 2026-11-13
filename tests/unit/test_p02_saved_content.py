"""Invented V2 structures and independent damage; no saved answer or media I/O."""

from copy import deepcopy

import pytest

from app.services.native_content_evidence import NativeContentError, validate_native_content
from tests.unit.test_native_content_status import content_input, finish


def native_table(pipeline="P02"):
    n = content_input(pipeline)
    doc = n["documents"][0]["document"]
    cells = []
    for row, values in enumerate((("Item", "2027 Revenue", "2027 Cost"), ("Alpha", "17", "23"))):
        for col, text in enumerate(values):
            cells.append({"text": text, "start_row_offset_idx": row, "end_row_offset_idx": row+1,
                "start_col_offset_idx": col, "end_col_offset_idx": col+1, "row_span": 1, "col_span": 1,
                "column_header": row == 0, "row_header": False, "row_section": False, "fillable": False})
    doc["body"]["children"].append({"$ref": "#/tables/0"})
    doc["tables"] = [{"self_ref": "#/tables/0", "parent": {"$ref": "#/body"}, "children": [],
        "label": "table", "captions": [], "footnotes": [], "references": [],
        "prov": [{"page_no": 1, "charspan": [0, 0],
                  "bbox": {"l": 10, "t": 50, "r": 110, "b": 100, "coord_origin": "TOPLEFT"}}],
        "data": {"num_rows": 2, "num_cols": 3, "table_cells": cells}}]
    return n


@pytest.mark.asyncio
async def test_v1_v2_share_tree_projection_without_borrowing_configuration_or_cells():
    a, ea = await finish(native_table("P01"))
    b, eb = await finish(native_table("P02"))
    assert a.markdown == b.markdown and ea["semantic_tables"] == eb["semantic_tables"]
    assert a._native_content.artifact.sha256 != b._native_content.artifact.sha256
    assert a.pipeline.primary == "docling-tableformer-v1" and b.pipeline.primary == "docling-tableformer-v2"
    assert "2027 Revenue：17" in b.markdown and "2027 Cost：23" in b.markdown
    assert eb["states"]["conversion"]["status"] == eb["states"]["delivery"]["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["row_section", "fillable", "end_row_offset_idx", "end_col_offset_idx", "column_header"])
async def test_cell_flags_offsets_and_unknown_presence_are_bound_to_the_actual_source(field):
    n = native_table()
    frozen = deepcopy(n)
    result, _ = await finish(n)
    cell = result._native_page_blocks[1][1]["cells"][0]
    cell[field] = not cell[field] if isinstance(cell[field], bool) else 9
    with pytest.raises(NativeContentError, match="offsets/role"):
        validate_native_content(result)
    assert n == frozen


@pytest.mark.asyncio
async def test_unknown_cell_flag_cannot_be_invented_or_replaced_by_false():
    n = native_table()
    del n["documents"][0]["document"]["tables"][0]["data"]["table_cells"][0]["row_section"]
    result, _ = await finish(n)
    cell = result._native_page_blocks[1][1]["cells"][0]
    assert "row_section" not in cell
    cell["row_section"] = False
    with pytest.raises(NativeContentError, match="missing-field"):
        validate_native_content(result)


@pytest.mark.asyncio
async def test_v2_glm_branch_uses_its_own_primary_view_and_branch_identity():
    n = content_input("P02")
    n["pages"][0] = {"page": 1, "branch": "glm", "raw": {
        "json_result": [[{"index": 0, "label": "text", "content": "Own V2 GLM text."}]],
        "raw_json_result": [[{"label": "text", "content": "Forbidden alternate."}]],
        "markdown_result": "Forbidden export."}}
    n["documents"] = []
    result, _ = await finish(n)
    assert "Own V2 GLM text." in result.markdown and "Forbidden" not in result.markdown
    block = result._native_page_blocks[1][0]
    assert block["native_branch"] == "glm" and block["branch_page"] == 0
    assert all(i.branch == "glm" for i in result._native_content.items)
