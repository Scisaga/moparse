"""Hand-authored SDK/HTML/GFM inputs reach final B/L without source rewriting."""

from copy import deepcopy

import pytest

from moparse_eval.adapters import read_docling, read_glm, read_paddle, read_visual
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate

REFERENCE = "| Name | Revenue(万元) | Profit(万元) | Period |\n|---|---|---|---|\n| Delta | 17 | 5 | 2027年 |"


def native(kind, wrong):
    revenue = "170001" if wrong else "170000"
    headers = ["Name", "Revene(元)", "Profit(元)", "Period"]
    values = ["Delta", revenue, "50000", "2027年"]
    html = "<table><tr>" + "".join("<th>" + x + "</th>" for x in headers) + "</tr><tr>" + "".join(
        "<td>" + x + "</td>" for x in values) + "</tr></table>"
    gfm = "|" + "|".join(headers) + "|\n|---|---|---|---|\n|" + "|".join(values) + "|"
    if kind == "docling":
        raw = {"body": {"children": [{"$ref": "#/tables/0"}]}, "tables": [{"self_ref": "#/tables/0",
               "label": "table", "prov": [{"page_no": 1}], "data": {"num_rows": 2, "num_cols": 4,
               "table_cells": [{"text": value, "start_row_offset_idx": row, "end_row_offset_idx": row + 1,
                                "start_col_offset_idx": col, "end_col_offset_idx": col + 1,
                                "column_header": row == 0, "row_header": False, "row_span": 1, "col_span": 1}
                               for row, texts in enumerate((headers, values)) for col, value in enumerate(texts)]}}]}
        reader = read_docling
    elif kind == "paddle":
        raw, reader = {"res": {"parsing_res_list": [{"block_label": "table", "block_content": html}]}}, read_paddle
    elif kind == "glm":
        raw, reader = {"json_result": [[{"label": "table", "content": gfm}]]}, read_glm
    else:
        raw, reader = [{"type": "table", "content": html}], read_visual
    before = deepcopy(raw)
    blocks = reader(raw, 1)
    assert raw == before
    observation = {"sample_id": "invented-native-equivalence", "pipeline": kind, "status": "completed",
                   "pages": [{"page": 1, "blocks": blocks}], "relations": []}
    original = deepcopy(observation)
    graph = read_candidate(observation)
    assert observation == original
    return graph


@pytest.mark.parametrize("kind", ["docling", "paddle", "glm", "visual"])
@pytest.mark.parametrize("wrong", [False, True])
def test_real_format_readers_preserve_raw_numbers_and_reach_the_same_exact_final_decisions(kind, wrong):
    actual = native(kind, wrong)
    required = compile_markdown(REFERENCE, sample_id="invented-native-equivalence")
    assert [(f["attribute"], f["value"], f["qualifiers"].get("unit")) for f in actual["business"]] == [
        ("Name", "Delta", None), ("Revene", "170001" if wrong else "170000", "元"), ("Profit", "50000", "元")]
    score = grade_layers(required, actual)
    assert score["publishable"] is True, score["blockers"]
    assert score["layers"]["B"]["denominator"] == 3
    assert score["layers"]["B"]["numerator"] == (2 if wrong else 3)
    assert score["layers"]["L"]["numerator"] == score["layers"]["L"]["denominator"]
    assert score["layers"]["T"]["score"] < 100
    [row] = [r for r in score["outcomes"] if r["layer"] == "B" and r["expected"]["attribute"] == "Revenue"]
    assert row["retrieval"]["candidates"][0]["identity"]["attribute"]["equivalence"]["equivalent"] is True
    assert row["comparisons"][0]["value"]["equivalence"]["equivalent"] is (not wrong)
