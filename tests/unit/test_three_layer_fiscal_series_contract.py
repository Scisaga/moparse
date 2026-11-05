"""Invented fiscal-label series and controls, with hand-authored requirements."""

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate

SAMPLE = "invented-fiscal-label-series"
FIELDS = [("Year Ended April 5, 2028", "61.0%"),
          ("Year Ended April 6, 2027", "56.0%"), ("Change", "Up 5.0 pts.")]


def graphs(markdown):
    required = compile_markdown(markdown, sample_id=SAMPLE, path="<invented-reference>")
    actual = read_candidate(markdown_observation(markdown, sample_id=SAMPLE, pipeline="P07", pages=[1]))
    return required, actual


def pending_contract(graph, body, metric, fields=FIELDS):
    assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
        ("Name", "Anchor", "identity")]
    [pending] = [item for item in graph.get("pending_requirements", [])
                 if item.get("kind") == "compound_metric_series"]
    assert pending["text"] == body and pending["source"]["lines"] == [5, 5]
    assert pending["source"]["text_span"] == [0, len(body)]
    assert pending["metric"]["text"] == metric
    assert pending["metric"]["source"]["text_span"] == [0, len(metric)]
    assert fields and len(pending["segments"]) == len(fields)
    assert [(part["label"], part["value"]) for part in pending["segments"]] == fields
    for part, (label, value) in zip(pending["segments"], fields, strict=True):
        for field, literal in (("label_source", label), ("value_source", value)):
            expected_start = body.index(literal)
            assert part[field]["text_span"] == [expected_start, expected_start + len(literal)]
            assert part[field]["path"] == pending["source"]["path"]
            assert part[field]["lines"] == [5, 5]
    [original] = [item for item in graph["text_projection"]["source_fragments"] if item["text"] == body]
    assert original["source"]["path"] == pending["source"]["path"]
    blockers = [item for item in graph["blockers"] if item["source"].get("lines") == [5, 5]]
    assert blockers and set().union(*(set(item.get("layers", [])) for item in blockers)) >= {"B", "L"}


@pytest.mark.parametrize("metric,semicolon,colon", [("Utilization", ";", ":"), ("Fill rate", "；", "：")])
def test_dated_measurements_and_change_cannot_become_one_opaque_answer_or_hide_behind_name(
        metric, semicolon, colon):
    body = metric + semicolon + " " + (semicolon + " ").join(label + colon + " " + value for label, value in FIELDS)
    required, actual = graphs("# Results\n\nName:Anchor\n\n- " + body)
    score = grade_layers(required, actual)
    assert score["publishable"] is False and score["score"] is None
    assert score["layers"]["B"]["complete"] is score["layers"]["L"]["complete"] is False
    assert score["layers"]["T"]["score"] == 100
    pending_contract(required, body, metric)
    pending_contract(actual, body, metric)
    [row] = [item for item in score["outcomes"] if item["layer"] == "B"]
    assert row["expected"]["attribute"] == "Name"
    assert "Year Ended" not in repr(row["retrieval"]["query"])


@pytest.mark.parametrize("metric,fields", [
    ("Utilization", [("Year Ended April 5, 2028", "61.0%")]),
    ("Utilization", [("Year Ended April 5, 2028", "61.0%"),
                     ("Year Ended April 6, 2027", "56.0%")]),
    ("Utilization", [("Year Ended April 5, 2028", "61.0%"),
                     ("Year Ended April 6, 2027", "56.0%"),
                     ("Year Ended April 7, 2026", "48.0%"), ("Change", "Up 5.0 pts.")]),
    ("利用率", [("截至2028年4月5日止年度", "61.0%"),
                ("截至2027年4月6日止年度", "56.0%"), ("變動", "上升5.0個百分點。")]),
], ids=["one-period", "two-periods-without-change", "three-periods-and-change", "printed-chinese-fiscal-dates"])
def test_unsupported_fiscal_scope_is_not_special_cased_to_exactly_two_periods_and_change(metric, fields):
    body = metric + "; " + "; ".join(label + ": " + value for label, value in fields)
    required, actual = graphs("# Results\n\nName:Anchor\n\n- " + body)
    score = grade_layers(required, actual)
    assert score["publishable"] is False and score["score"] is None
    assert score["layers"]["B"]["complete"] is score["layers"]["L"]["complete"] is False
    assert score["layers"]["T"]["score"] == 100
    pending_contract(required, body, metric, fields)
    pending_contract(actual, body, metric, fields)


@pytest.mark.parametrize("body,wanted", [
    ("Revenue:17; Profit:5", [("Revenue", "17"), ("Profit", "5")]),
    ("Date and time: 9:00\n\nLocation: https://example.invalid/notice?id=2028",
     [("Date and time", "9:00"), ("Location", "https://example.invalid/notice?id=2028")]),
    ("Narrative: Phase 2; the operator recorded ready status.",
     [("Narrative", "Phase 2; the operator recorded ready status.")]),
])
def test_ordinary_fields_metadata_and_single_complex_values_keep_their_existing_exact_answers(body, wanted):
    for graph in graphs("# Results\n\nName:Anchor\n\n" + body):
        assert graph["blockers"] == [] and graph.get("pending_requirements", []) == []
        assert [(fact["attribute"], fact["value"]) for fact in graph["business"]] == [("Name", "Anchor"), *wanted]
        assert len(graph["business"]) == 1 + len(wanted)
        assert [fact["qualifiers"] for fact in graph["business"]] == [{}] * (1 + len(wanted))


@pytest.mark.parametrize("with_change", [False, True])
def test_explicit_supported_four_and_five_column_schemas_do_not_become_pending(with_change):
    schema = "列说明：2028年金額（萬元）、佔總收入比（%）；2027年金額（萬元）、佔總收入比（%）"
    row = "Delta：2028年17、61%；2027年11、56%"
    wanted = [("Delta", "金額", "17", "2028年", "萬元"),
              ("Delta", "佔總收入比", "61", "2028年", "%"),
              ("Delta", "金額", "11", "2027年", "萬元"),
              ("Delta", "佔總收入比", "56", "2027年", "%")]
    if with_change:
        schema += "；金額同比變動（%）"
        row += "；金額同比變動：5%"
        wanted.append(("Delta", "金額同比變動", "5", None, "%"))
    for graph in graphs("# Results\n\n" + schema + "。\n\n- " + row):
        assert graph["blockers"] == [] and graph.get("pending_requirements", []) == []
        assert [(fact["subject"], fact["attribute"], fact["value"], fact["qualifiers"].get("period"),
                 fact["qualifiers"].get("unit")) for fact in graph["business"]] == wanted
        assert [fact["role"] for fact in graph["business"]] == ["metric"] * len(wanted)
        if with_change:
            assert graph["business"][-1]["qualifiers"] == {
                "unit": "%", "from_period": "2027年", "to_period": "2028年"}
