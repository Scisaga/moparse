"""Independent six-column oracles through authored expected and final votes."""

import json
from copy import deepcopy

import pytest

from moparse_eval.expected_readback import read_expected
from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.source_obligations import audit_source_obligations
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_represented_feature_production import production

DECLARATION = ("於6月30日，金额单位：人民币千元。各项分别列示2029年金额、占总资产比，"
               "2028年金额、占总资产比，金额同比变动、占总资产比重同比增减。")
ROW = "Cedar：2029年43、29%；2028年37、25%；金额同比变动7%；占总资产比重同比增减4%。"
TEXT = DECLARATION + "\n\n- " + ROW + "\n"
ORACLE = [("金额", "43", "2029年"), ("占总资产比", "29", "2029年"),
          ("金额", "37", "2028年"), ("占总资产比", "25", "2028年"),
          ("金额同比变动", "7", None), ("占总资产比重同比增减", "4", None)]


def review(result):
    if result["publishable"]:
        validate_evidence(result)
    else:
        with pytest.raises(ValueError, match="incomplete software judgments"):
            validate_evidence(result)


@pytest.mark.parametrize("row", [ROW,
    "Cedar：2029年金额：43；2029年占总资产比：29%；2028年金额：37；2028年占总资产比：25%；占总资产比重同比增减：4%；金额同比变动：7%。",
    "Cedar：43、29%、37、25%、7%、4%。",
])
def test_declared_six_columns_survive_labelled_reorder_and_fixed_tuples(tmp_path, row):
    graph, required = production(tmp_path, TEXT)
    assert [(f["attribute"], f["value"], f["qualifiers"].get("period")) for f in required["business"]] == ORACLE
    for index, fact in enumerate(required["business"]):
        q = fact["qualifiers"]
        assert q["period_basis"] == "於6月30日"
        assert q["unit"] == ("人民币千元" if index in {0, 2} else "%")
        assert ("currency" in q) is (index in {0, 2})
        if index >= 4:
            assert (q["from_period"], q["to_period"]) == ("2028年", "2029年")
    actual = read_candidate_markdown(DECLARATION + "\n\n- " + row + "\n", sample_id=required["sample_id"])
    assert len(actual["business"]) == 6
    result = grade_layers(required, actual)
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 6
    assert result["layers"]["L"]["score"] == 100
    assert all(d["status"] != "pending" for d in graph["source_obligation_coverage"]["dispositions"])
    validate_evidence(result)


def test_unprinted_change_units_stay_undeclared_without_losing_the_columns(tmp_path):
    text = TEXT.replace("变动7%", "变动7").replace("增减4%", "增减4")
    _, required = production(tmp_path, text)
    assert len(required["business"]) == 6
    assert all("unit" not in f["qualifiers"] and "currency" not in f["qualifiers"] for f in required["business"][4:])
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    validate_evidence(result)


@pytest.mark.parametrize("count", [4, 5, 6])
def test_four_five_and_six_column_declarations_all_use_the_complete_production_path(tmp_path, count):
    declaration = "列说明：2029年金额（人民币千元）、占总资产比（%）；2028年金额（人民币千元）、占总资产比（%）"
    row = "Cedar：2029年43、29%；2028年37、25%"
    if count >= 5:
        declaration += "；金额同比变动（%）"
        row += "；金额同比变动7%"
    if count == 6:
        declaration += "；占总资产比重同比增减（%）"
        row += "；占总资产比重同比增减4%"
    text = declaration + "。\n\n- " + row + "。\n"
    _, required = production(tmp_path, text)
    assert len(required["business"]) == count
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["numerator"] == count
    assert result["layers"]["L"]["score"] == 100
    validate_evidence(result)


def test_reordered_change_declarations_still_bind_records_by_their_printed_labels(tmp_path):
    swapped = TEXT.replace("金额同比变动、占总资产比重同比增减", "占总资产比重同比增减、金额同比变动")
    _, required = production(tmp_path, TEXT)
    actual = read_candidate_markdown(swapped, sample_id=required["sample_id"])
    assert [(f["attribute"], f["value"]) for f in actual["business"][-2:]] == [("金额同比变动", "7"), ("占总资产比重同比增减", "4")]
    result = grade_layers(required, actual)
    assert result["layers"]["B"]["score"] == result["layers"]["L"]["score"] == 100
    validate_evidence(result)


@pytest.mark.parametrize('connector', ['及', '和', 'and'])
def test_printed_connectors_only_bridge_the_adjacent_declared_columns(tmp_path, connector):
    text = TEXT.replace('金额、占', '金额' + connector + '占')
    _, required = production(tmp_path, text)
    result = grade_layers(required, read_candidate_markdown(TEXT, sample_id=required['sample_id']))
    assert result['layers']['B']['numerator'] == result['layers']['B']['denominator'] == 6
    assert result['layers']['L']['score'] == 100
    validate_evidence(result)


def test_a_note_with_a_prose_enumeration_is_not_an_implicit_numeric_tuple(tmp_path):
    _, required = production(tmp_path, TEXT)
    note = "附注：本项说明包括服务成本、材料成本，管理层将在后续报告中披露。"
    actual = read_candidate_markdown(TEXT + "\n" + note + "\n", sample_id=required["sample_id"])
    assert not any(i["reason"].startswith("compact_") and i.get("source", {}).get("lines", [0])[0] > 3 for i in actual["blockers"])
    assert any(s["text"] == note for s in actual["syntax"])
    # The unresolved note must itself be in the authored acceptance scope.
    # Unrequested extra candidate text is not an expected requirement.
    text = TEXT + "\n" + note + "\n"
    (tmp_path / "invented-document" / "expected.md").write_text(text, encoding="utf-8")
    manifest = tmp_path / "invented-document" / "manifest.json"
    selection = json.loads(manifest.read_text())
    selection["source_map"]["entries"][0]["markdown_lines"] = [1, len(text.splitlines())]
    manifest.write_text(json.dumps(selection), encoding="utf-8")
    selected = read_expected({"id": required["sample_id"], "document_id": "invented-document", "source_pages": [1]}, tmp_path)
    graph = compile_requirement_graph(selected)
    validate_requirement_graph(graph, expected=selected)
    assert not graph["semantic_complete"]
    assert not any(i["reason"].startswith("compact_") and i.get("source", {}).get("lines", [0])[0] > 3 for i in graph["unresolved"])
    result = grade_layers(evaluation_projection(graph), actual)
    assert not result["publishable"]
    review(result)


def test_a_complete_neighbor_cannot_fill_a_partial_split_records_declared_slots(tmp_path):
    fields = ["2029年金额：43", "2029年占总资产比：29%", "2028年金额：37", "2028年占总资产比：25%",
              "金额同比变动：7%", "占总资产比重同比增减：4%"]
    text = DECLARATION + "\n\n" + "\n".join("- " + name + "\n" + "\n".join("  - " + f for f in fields)
                                                for name in ["Cedar", "Willow"]) + "\n"
    _, required = production(tmp_path, text)
    assert len({f["record_id"] for f in required["business"]}) == 2
    changed = text[:text.rfind("  - " + fields[-1])]
    actual = read_candidate_markdown(changed, sample_id=required["sample_id"])
    missing = [i for i in actual["blockers"] if i["reason"] == "compact_declared_columns_missing"]
    assert len(missing) == 1
    assert missing[0]["record_id"] == next(f["record_id"] for f in actual["business"] if f["subject"] == "Willow")
    result = grade_layers(required, actual)
    assert result["layers"]["B"]["denominator"] == 12 and result["layers"]["B"]["numerator"] < 12
    review(result)
    (tmp_path / "invented-document" / "expected.md").write_text(changed, encoding="utf-8")
    manifest = tmp_path / "invented-document" / "manifest.json"
    selection = json.loads(manifest.read_text())
    selection["source_map"]["entries"][0]["markdown_lines"] = [1, len(changed.splitlines())]
    manifest.write_text(json.dumps(selection), encoding="utf-8")
    expected = read_expected({"id": required["sample_id"], "document_id": "invented-document", "source_pages": [1]}, tmp_path)
    graph = compile_requirement_graph(expected)
    validate_requirement_graph(graph, expected=expected)
    assert not graph["semantic_complete"]
    assert any(i["reason"] == "compact_declared_columns_missing" for i in graph["unresolved"])


def six_column_formats():
    declaration = ("列说明：2029年金额（人民币千元）、占总资产比（%）；2028年金额（人民币千元）、占总资产比（%）；"
                   "金额同比变动（%）；占总资产比重同比增减（%）。")
    listed = declaration + "\n\n- North\n  - " + ROW + "\n"
    labels = ["2029年金额（人民币千元）", "2029年占总资产比（%）", "2028年金额（人民币千元）", "2028年占总资产比（%）",
              "金额同比变动（%）", "占总资产比重同比增减（%）"]
    values = ["43", "29", "37", "25", "7", "4"]
    gfm = "| Group | Item |" + "|".join(labels) + "|\n|" + "---|" * 8 + "\n|North|Cedar|" + "|".join(values) + "|\n"
    horizontal = ('<table><tr><th rowspan="2">Group</th><th rowspan="2">Item</th>'
        '<th colspan="2">2029年</th><th colspan="2">2028年</th>'
        '<th rowspan="2">金额同比变动（%）</th><th rowspan="2">占总资产比重同比增减（%）</th></tr>'
        '<tr><th>金额（人民币千元）</th><th>占总资产比（%）</th><th>金额（人民币千元）</th><th>占总资产比（%）</th></tr>'
        '<tr><th scope="rowgroup">North</th><th scope="row">Cedar</th>' + ''.join('<td>' + v + '</td>' for v in values) + '</tr></table>\n')
    transposed = ('<table><tr><th colspan="2" scope="row">Group</th><th scope="colgroup">North</th></tr>'
        '<tr><th colspan="2" scope="row">Item</th><th scope="col">Cedar</th></tr>'
        '<tr><th rowspan="2" scope="rowgroup">2029年</th><th scope="row">金额（人民币千元）</th><td>43</td></tr>'
        '<tr><th scope="row">占总资产比（%）</th><td>29</td></tr>'
        '<tr><th rowspan="2" scope="rowgroup">2028年</th><th scope="row">金额（人民币千元）</th><td>37</td></tr>'
        '<tr><th scope="row">占总资产比（%）</th><td>25</td></tr>'
        '<tr><th colspan="2" scope="row">金额同比变动（%）</th><td>7</td></tr>'
        '<tr><th colspan="2" scope="row">占总资产比重同比增减（%）</th><td>4</td></tr></table>\n')
    return listed, gfm, horizontal, transposed


@pytest.mark.parametrize("kind", [0, 1, 2, 3], ids=["list", "gfm", "html", "declared-transpose"])
@pytest.mark.parametrize("expected_kind", [0, 1], ids=["authored-list", "authored-gfm"])
def test_one_authored_six_column_oracle_keeps_six_business_votes_in_each_supported_format(tmp_path, kind, expected_kind):
    formats = six_column_formats()
    _, required = production(tmp_path, formats[expected_kind])
    actual = read_candidate_markdown(formats[kind], sample_id=required["sample_id"])
    assert len(required["business"]) == len(actual["business"]) == 6
    assert all(f["identity_facets"] == {"group": "North"} for f in actual["business"])
    result = grade_layers(required, actual)
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 6
    assert result["layers"]["L"]["score"] == 100
    validate_evidence(result)


@pytest.mark.parametrize("changed", [
    TEXT.replace("增减4%", "增减9%"),
    TEXT.replace("增减4%", "增减4个百分点"),
    TEXT.replace("於6月30日", "截至6月30日止年度"),
    TEXT.replace("；占总资产比重同比增减4%", ""),
    TEXT.replace("43、29%", "43、29千元"),
    TEXT.replace("2029年43", "2028年43"),
    TEXT.replace("；金额同比变动7%", "；金额环比变动7%"),
])
def test_changed_values_units_scope_and_lost_columns_affect_final_votes(tmp_path, changed):
    _, required = production(tmp_path, TEXT)
    result = grade_layers(required, read_candidate_markdown(changed, sample_id=required["sample_id"]))
    assert result["layers"]["B"]["denominator"] == 6
    assert result["layers"]["B"]["numerator"] < 6
    if changed == TEXT.replace("增减4%", "增减9%"):
        assert result["layers"]["L"]["score"] == 100
    review(result)


@pytest.mark.parametrize("mutation", ["lost_second_change", "borrowed_column", "borrowed_unit", "short_span", "lost_relation"])
def test_all_retained_text_cannot_hide_missing_or_forged_binding(tmp_path, mutation):
    graph, required = production(tmp_path, TEXT)
    broken = deepcopy(graph)
    last = next(n for n in broken["nodes"] if n["id"] == broken["projections"]["B"][-1])
    neighbor = next(n for n in broken["nodes"] if n["id"] == broken["projections"]["B"][-2])
    if mutation == "lost_second_change":
        broken["projections"]["B"].remove(last["id"])
        broken["nodes"].remove(last)
    elif mutation == "borrowed_column":
        last["attribute_source"] = deepcopy(neighbor["attribute_source"])
        last["attribute"] = neighbor["attribute"]
        last["compact_column"] = deepcopy(neighbor["compact_column"])
    elif mutation == "borrowed_unit":
        last["qualifier_sources"]["unit"] = deepcopy(neighbor["qualifier_sources"]["unit"])
    elif mutation == "short_span":
        last["source"]["text_span"][1] -= 1
    else:
        broken["relations"] = [e for e in broken["relations"] if e.get("fact_id") != last["id"]]
    assert any(d["status"] == "pending" for d in audit_source_obligations(broken["source_obligation_inventory"], broken)["dispositions"])
    with pytest.raises(ValueError):
        validate_requirement_graph(broken)
    actual = read_candidate_markdown(TEXT, sample_id=required["sample_id"])
    if mutation == "lost_second_change":
        actual["business"].pop()
    elif mutation == "lost_relation":
        actual["relations"] = [e for e in actual["relations"] if e.get("fact_id") != actual["business"][-1]["id"]]
    elif mutation == "borrowed_column":
        actual["business"][-1]["attribute"] = actual["business"][-2]["attribute"]
        actual["business"][-1]["attribute_source"] = deepcopy(actual["business"][-2]["attribute_source"])
        actual["business"][-1]["compact_column"] = deepcopy(actual["business"][-2]["compact_column"])
    elif mutation == "borrowed_unit":
        actual["business"][-1]["qualifier_sources"]["unit"] = deepcopy(actual["business"][-2]["qualifier_sources"]["unit"])
    else:
        actual["business"][-1]["source"]["text_span"][1] -= 1
        with pytest.raises(ValueError, match="source-bound scalar"):
            grade_layers(required, actual)
        return
    result = grade_layers(required, actual)
    assert result["layers"]["B" if mutation != "lost_relation" else "L"]["score"] != 100
    review(result)
