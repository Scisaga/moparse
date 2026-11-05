"""Independent five-measurement oracles across real matrix format entries.

Answers, business roles, qualifiers and cell positions are authored below.
They are never obtained from the requirements compiler or candidate reader.
These invented software fixtures do not inspect or modify any corpus material.
"""

from copy import deepcopy

import pytest

from moparse_eval.adapters import read_docling, read_glm, read_paddle, read_visual
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate

SAMPLE = "independent-matrix"
SCHEMA = ("列说明：2027年金額（萬元）、佔總收入比（%）；"
          "2026年金額（萬元）、佔總收入比（%）；金額同比變動（%）。")
COMPACT = ("## North\n\n" + SCHEMA + "\n\n"
           "- Delta：2027年：17、60%；2026年：11、55%；金額同比變動：5%。\n")
SPLIT = ("## North\n\n" + SCHEMA + "\n\n- Delta\n"
         "  - 2027年金額：17萬元\n  - 2027年佔總收入比：60%\n"
         "  - 2026年金額：11萬元\n  - 2026年佔總收入比：55%\n"
         "  - 金額同比變動：5%\n")

HORIZONTAL = (
    '<table><tr><th rowspan="2" scope="col">Group</th><th rowspan="2" scope="col">Item</th>'
    '<th id="year27" colspan="2" scope="colgroup">2027年</th>'
    '<th id="year26" colspan="2" scope="colgroup">2026年</th>'
    '<th id="change" rowspan="2" scope="col">金額同比變動（%）</th></tr>'
    '<tr><th id="amount27" scope="col">金額（萬元）</th>'
    '<th id="share27" scope="col">佔總收入比（%）</th>'
    '<th id="amount26" scope="col">金額（萬元）</th>'
    '<th id="share26" scope="col">佔總收入比（%）</th></tr>'
    '<tr><th scope="rowgroup">North</th><th scope="row">Delta</th>'
    '<td id="value-amount27" headers="year27 amount27">17</td>'
    '<td id="value-share27" headers="year27 share27">60</td>'
    '<td id="value-amount26" headers="year26 amount26">11</td>'
    '<td id="value-share26" headers="year26 share26">55</td>'
    '<td id="value-change" headers="change">5</td></tr></table>'
)
TRANSPOSED = (
    '<table><tr><th colspan="2" scope="row">Group</th><th scope="colgroup">North</th></tr>'
    '<tr><th colspan="2" scope="row">Item</th><th scope="col">Delta</th></tr>'
    '<tr><th rowspan="2" scope="rowgroup">2027年</th><th scope="row">金額（萬元）</th><td>17</td></tr>'
    '<tr><th scope="row">佔總收入比（%）</th><td>60</td></tr>'
    '<tr><th rowspan="2" scope="rowgroup">2026年</th><th scope="row">金額（萬元）</th><td>11</td></tr>'
    '<tr><th scope="row">佔總收入比（%）</th><td>55</td></tr>'
    '<tr><th colspan="2" scope="row">金額同比變動（%）</th><td>5</td></tr></table>'
)
GFM = (
    "| Group | Item | 2027年 / 金額（萬元） | 2027年 / 佔總收入比（%） | "
    "2026年 / 金額（萬元） | 2026年 / 佔總收入比（%） | 金額同比變動（%） |\n"
    "|---|---|---|---|---|---|---|\n| North | Delta | 17 | 60 | 11 | 55 | 5 |\n"
)

# (subject, printed attribute, value, period, unit, from_period, to_period,
# explicit group). Delta is the record locator, not a separately printed Name
# assertion. Exactly five independent measurement requirements are mandated.
FIVE = [
    ("Delta", "金額", "17", "2027年", "萬元", None, None, "North"),
    ("Delta", "佔總收入比", "60", "2027年", "%", None, None, "North"),
    ("Delta", "金額", "11", "2026年", "萬元", None, None, "North"),
    ("Delta", "佔總收入比", "55", "2026年", "%", None, None, "North"),
    ("Delta", "金額同比變動", "5", None, "%", "2026年", "2027年", "North"),
]
HORIZONTAL_CELLS = {
    ("金額", "2027年"): (2, 2), ("佔總收入比", "2027年"): (2, 3),
    ("金額", "2026年"): (2, 4), ("佔總收入比", "2026年"): (2, 5),
    ("金額同比變動", None): (2, 6),
}
TRANSPOSED_CELLS = {
    ("金額", "2027年"): (2, 2), ("佔總收入比", "2027年"): (3, 2),
    ("金額", "2026年"): (4, 2), ("佔總收入比", "2026年"): (5, 2),
    ("金額同比變動", None): (6, 2),
}
GFM_CELLS = {
    ("金額", "2027年"): (1, 2), ("佔總收入比", "2027年"): (1, 3),
    ("金額", "2026年"): (1, 4), ("佔總收入比", "2026年"): (1, 5),
    ("金額同比變動", None): (1, 6),
}


def signature(fact):
    q = fact["qualifiers"]
    return (fact["subject"], fact["attribute"], fact["value"], q.get("period"), q.get("unit"),
            q.get("from_period"), q.get("to_period"), fact["identity_facets"].get("group"))


def require_five(facts):
    assert len(facts) == 5
    assert sorted(map(signature, facts), key=repr) == sorted(FIVE, key=repr)
    assert [fact["role"] for fact in facts] == ["metric"] * 5
    for fact in facts:
        assert fact["source"]["path"]


def _docling_blocks():
    # Independently authored Docling SDK cells, not HTML converted to another
    # label. Native row_section, header flags and spans carry the declarations.
    cells = [
        (0, 0, 2, 1, "Group", True, False, False),
        (0, 1, 2, 1, "Item", True, False, False),
        (0, 2, 1, 2, "2027年", True, False, False),
        (0, 4, 1, 2, "2026年", True, False, False),
        (0, 6, 2, 1, "金額同比變動（%）", True, False, False),
        (1, 2, 1, 1, "金額（萬元）", True, False, False),
        (1, 3, 1, 1, "佔總收入比（%）", True, False, False),
        (1, 4, 1, 1, "金額（萬元）", True, False, False),
        (1, 5, 1, 1, "佔總收入比（%）", True, False, False),
        (2, 0, 1, 1, "North", False, True, True),
        (2, 1, 1, 1, "Delta", False, True, False),
        (2, 2, 1, 1, "17", False, False, False),
        (2, 3, 1, 1, "60", False, False, False),
        (2, 4, 1, 1, "11", False, False, False),
        (2, 5, 1, 1, "55", False, False, False),
        (2, 6, 1, 1, "5", False, False, False),
    ]
    native = {"body": {"children": [{"$ref": "#/tables/0"}]}, "tables": [{
        "self_ref": "#/tables/0", "label": "table", "prov": [{"page_no": 1}],
        "data": {"num_rows": 3, "num_cols": 7, "table_cells": [
            {"start_row_offset_idx": r, "end_row_offset_idx": r + rs,
             "start_col_offset_idx": c, "end_col_offset_idx": c + cs,
             "row_span": rs, "col_span": cs, "text": text,
             "column_header": ch, "row_header": rh, "row_section": section}
            for r, c, rs, cs, text, ch, rh, section in cells]}}]}
    return read_docling(native, 1)


def evidence(kind, text=None):
    if kind == "docling":
        blocks = _docling_blocks()
    elif kind == "html":
        blocks = read_paddle({"res": {"parsing_res_list": [
            {"block_label": "table", "block_content": HORIZONTAL if text is None else text}]}}, 1)
    elif kind == "gfm":
        blocks = read_glm({"json_result": [[{"label": "table", "content": GFM if text is None else text}]]}, 1)
    elif kind == "transposed":
        blocks = read_visual([{"type": "table", "content": TRANSPOSED if text is None else text}], 1)
    else:
        raise AssertionError("fixture format must be explicitly selected")
    return read_candidate({"sample_id": SAMPLE, "pipeline": kind, "status": "success",
                           "pages": [{"page": 1, "blocks": blocks}], "relations": []})


def business(result):
    return [item for item in result["outcomes"] if item["layer"] == "B"]


@pytest.mark.parametrize("reference", [COMPACT, SPLIT, HORIZONTAL, TRANSPOSED],
                         ids=["compact", "split", "horizontal", "vertical"])
def test_five_requirements_keep_roles_qualifiers_and_source_across_reference_forms(reference):
    requirements = compile_markdown(reference, sample_id=SAMPLE)
    require_five(requirements["business"])
    assert not requirements["blockers"], requirements["blockers"]


@pytest.mark.parametrize("kind", ["docling", "html", "gfm", "transposed"])
def test_faithful_candidate_matrix_has_five_measurements_and_independent_cell_endpoints(kind):
    graph = evidence(kind)
    require_five(graph["business"])
    expected_cells = {"transposed": TRANSPOSED_CELLS, "gfm": GFM_CELLS}.get(kind, HORIZONTAL_CELLS)
    for fact in graph["business"]:
        assert (fact["source"]["row"], fact["source"]["col"]) == expected_cells[
            (fact["attribute"], fact["qualifiers"].get("period"))]
        assert fact["source"]["cell"]
        assert fact["header_evidence"] and fact["row_evidence"]
    assert not graph["blockers"], graph["blockers"]


@pytest.mark.parametrize("reference", [COMPACT, SPLIT, HORIZONTAL, TRANSPOSED],
                         ids=["compact", "split", "horizontal", "vertical"])
@pytest.mark.parametrize("kind", ["docling", "html", "gfm", "transposed"])
def test_five_business_requirements_compare_correctly_across_actual_format_entries(reference, kind):
    requirements = compile_markdown(reference, sample_id=SAMPLE)
    require_five(requirements["business"])
    result = grade_layers(requirements, evidence(kind))
    rows = business(result)
    assert len(rows) == 5
    assert [row["outcome"] for row in rows] == ["correct"] * 5
    assert result["layers"]["B"]["denominator"] == 5
    assert result["layers"]["B"]["numerator"] == 5
    # Hand-counted independent oracle: North+Delta=10; period labels=20;
    # amount/share/change labels=20; units=7; numerical literals=9.
    assert result["layers"]["T"]["denominator"] == 66
    assert result["layers"]["T"]["numerator"] == 66
    # Five field bindings, four period/unit pairs and three comparison/unit
    # scopes. HTML header ids are evidence, not additional relationship votes.
    assert result["layers"]["L"]["denominator"] == 16
    assert result["layers"]["L"]["numerator"] == 16
    for row in rows:
        assert row["retrieval"]["accepted"]


def test_amount_character_change_does_not_erase_unchanged_logical_bindings():
    requirements = compile_markdown(HORIZONTAL, sample_id=SAMPLE)
    correct = grade_layers(requirements, evidence("html"))
    changed = HORIZONTAL.replace('headers="year27 amount27">17<', 'headers="year27 amount27">18<')
    wrong = grade_layers(requirements, evidence("html", changed))
    assert len(business(wrong)) == 5
    assert [row["outcome"] for row in business(wrong)].count("incorrect") == 1
    assert wrong["layers"]["L"]["denominator"] > 0
    assert wrong["layers"]["L"]["numerator"] == correct["layers"]["L"]["numerator"]
    assert wrong["layers"]["T"]["numerator"] < correct["layers"]["T"]["numerator"]


def test_only_explicit_header_references_change_while_all_visible_characters_remain():
    requirements = compile_markdown(HORIZONTAL, sample_id=SAMPLE)
    changed = HORIZONTAL.replace('headers="year27 amount27"', 'headers="temporary"').replace(
        'headers="year26 amount26"', 'headers="year27 amount27"').replace(
        'headers="temporary"', 'headers="year26 amount26"')
    correct = grade_layers(requirements, evidence("html"))
    wrong = grade_layers(requirements, evidence("html", changed))
    assert wrong["layers"]["T"]["numerator"] == correct["layers"]["T"]["numerator"]
    assert wrong["layers"]["L"]["numerator"] < correct["layers"]["L"]["numerator"]
    assert [row["outcome"] for row in business(wrong)].count("incorrect") == 2


def _has_independent_conflict(checks, field, required, actual):
    if isinstance(checks, dict):
        if checks.get("correct") is False:
            wanted, found = checks.get("required"), checks.get("actual")
            if wanted == required and found == actual:
                return True
            if isinstance(wanted, dict) and isinstance(found, dict):
                if wanted.get(field) == required and found.get(field) == actual:
                    return True
        return any(_has_independent_conflict(value, field, required, actual) for value in checks.values())
    if isinstance(checks, list):
        return any(_has_independent_conflict(value, field, required, actual) for value in checks)
    return False


@pytest.mark.parametrize("old,new,field", [
    ("2027年", "2028年", "period"), ("萬元", "千元", "unit"), ("North", "South", "group"),
])
def test_explicit_period_scale_and_group_conflicts_are_rejected_before_value_comparison(old, new, field):
    requirements = compile_markdown(COMPACT, sample_id=SAMPLE)
    result = grade_layers(requirements, evidence("html", HORIZONTAL.replace(old, new)))
    rows = business(result)
    assert len(rows) == 5
    assert any(row["outcome"] == "incorrect" for row in rows)
    rejections = [hit for row in rows for hit in row["retrieval"]["candidates"] if hit["decision"] == "rejected"]
    assert rejections
    assert any("conflict" in hit["reason"] and _has_independent_conflict(hit["identity"], field, old, new)
               for hit in rejections)


def test_layout_grid_does_not_acquire_data_roles_from_its_shape_or_single_other_cell():
    layout = '<table><tr><td>审核意见</td><td>已阅读并签署</td></tr><tr><td>说明</td><td>待批准</td></tr></table>'
    graph = evidence("html", layout)
    assert graph["business"] == []
    assert graph["blockers"]
    assert {item["text"] for item in graph["text"]} == {"审核意见", "已阅读并签署", "说明", "待批准"}


def test_native_matrix_reading_is_reference_independent_and_does_not_mutate_supplied_structures():
    blocks = _docling_blocks()
    observed = {"sample_id": SAMPLE, "pipeline": "P01", "pages": [{"page": 1, "blocks": blocks}]}
    before = deepcopy(observed)
    require_five(read_candidate(observed)["business"])
    assert observed == before
    with pytest.raises(TypeError):
        read_candidate(observed, expected={"correct_value": "17"})


def _flat_docling(events):
    texts, tables, children = [], [], []
    for event in events:
        if event[0] == "heading":
            index = len(texts)
            children.append({"$ref": f"#/texts/{index}"})
            texts.append({"self_ref": f"#/texts/{index}", "label": "section_header", "level": 1,
                          "text": event[1], "prov": [{"page_no": 1}]})
        else:
            index = len(tables)
            children.append({"$ref": f"#/tables/{index}"})
            tables.append({"self_ref": f"#/tables/{index}", "label": "table", "prov": [{"page_no": 1}],
                           "data": {"num_rows": 2, "num_cols": 2, "table_cells": [
                               {"start_row_offset_idx": row, "start_col_offset_idx": col,
                                "end_row_offset_idx": row + 1, "end_col_offset_idx": col + 1,
                                "row_span": 1, "col_span": 1, "column_header": row == 0,
                                "row_header": False, "text": text}
                               for row, col, text in [(0, 0, "Metric"), (0, 1, "Value"),
                                                       (1, 0, "Amount"), (1, 1, event[1])]]}})
    raw = {"body": {"children": children}, "texts": texts, "tables": tables}
    return read_candidate({"sample_id": SAMPLE, "pipeline": "P01", "status": "success",
                           "pages": [{"page": 1, "blocks": read_docling(raw, 1)}], "relations": []})


def test_flat_native_levels_can_preserve_their_printed_direct_business_scope():
    reference = "# 財務回顧\n\n## 營業收入\n\n- Amount: 17\n"
    graph = _flat_docling([("heading", "管理層討論與分析"), ("heading", "財務回顧"),
                          ("heading", "營業收入"), ("table", "17")])
    result = grade_layers(compile_markdown(reference, sample_id=SAMPLE), graph)
    rows = business(result)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "correct"
    assert rows[0]["retrieval"]["accepted"]
    assert rows[0]["actual"][0]["context_evidence"]


def test_a_foreign_parent_cannot_supply_the_correct_value_to_a_local_wrong_record():
    reference = "# North\n\n## Revenue\n\n- Amount: 17\n\n# South\n\n## Revenue\n\n- Amount: 29\n"
    graph = _flat_docling([("heading", "North"), ("heading", "Revenue"), ("table", "18"),
                          ("heading", "South"), ("heading", "Revenue"), ("table", "17")])
    result = grade_layers(compile_markdown(reference, sample_id=SAMPLE), graph)
    rows = business(result)
    assert len(rows) == 2
    assert [row["outcome"] for row in rows] == ["incorrect", "incorrect"]
    north = rows[0]
    assert [item["value"] for item in north["actual"]] == ["18"]
    assert any(hit["decision"] == "rejected" for hit in north["retrieval"]["candidates"])


@pytest.mark.parametrize("events", [
    [("heading", "Revenue"), ("table", "17")],
    [("heading", "North"), ("heading", "West"), ("heading", "Revenue"), ("table", "17")],
])
def test_an_absent_parent_or_unknown_intervening_peer_cannot_be_completed_from_expected(events):
    reference = "# North\n\n## Revenue\n\n- Amount: 17\n"
    result = grade_layers(compile_markdown(reference, sample_id=SAMPLE), _flat_docling(events))
    rows = business(result)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "incorrect"
    assert rows[0]["retrieval"]["accepted"] == []


def test_a_declared_child_does_not_supply_its_parents_direct_business_record():
    reference = "# North\n\n- Amount: 17\n\n## Division\n\n- Amount: 29\n"
    graph = _flat_docling([("heading", "North"), ("table", "18"),
                          ("heading", "North"), ("heading", "Division"), ("table", "17")])
    result = grade_layers(compile_markdown(reference, sample_id=SAMPLE), graph)
    rows = business(result)
    assert len(rows) == 2
    assert [row["outcome"] for row in rows] == ["incorrect", "incorrect"]
    assert [item["value"] for item in rows[0]["actual"]] == ["18"]


@pytest.mark.parametrize("wanted,actual", [
    ("佔總收入比", "占营业收入比"),
    ("金額同比變動", "金额环比变动"),
    ("金額（不含稅）", "金额（含税）"),
])
def test_complete_role_spelling_equivalence_cannot_change_denominators_period_relations_or_conditions(wanted, actual):
    from moparse_eval.business_labels import role_label
    from moparse_eval.three_layer import read_candidate_markdown

    assert role_label(wanted) != role_label(actual)
    result = grade_layers(compile_markdown(wanted + ": 17", sample_id=SAMPLE),
                          read_candidate_markdown(actual + ": 17", sample_id=SAMPLE))
    rows = business(result)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "incorrect"
    assert rows[0]["retrieval"]["accepted"] == []
