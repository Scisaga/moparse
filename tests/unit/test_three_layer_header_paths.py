"""Independent final-Markdown oracles for four explicitly headed measurements.

The four answers, roles, qualifiers, raw spans, and weights are hand authored.
No compiler/reader output supplies an expected answer or a source position.
"""

from collections import Counter
from copy import deepcopy

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.expected_report import validate_evidence
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate

SAMPLE = "invented-header-paths"
HEADING = "# Review\n\n## Revenue\n\n"
BASIS = "截至12月31日止年度"
SCHEMA = (BASIS + "。金額單位：人民幣千元。列说明："
          "2027年金額、佔總收入比（%）；2026年金額、佔總收入比（%）。")
COMPACT = HEADING + SCHEMA + "\n\n- North\n  - Delta：2027年17、60%；2026年11、55%\n"
SPLIT = (HEADING + SCHEMA + "\n\n- North\n  - Delta\n"
         "    - 2027年金額：17\n    - 2027年佔總收入比：60%\n"
         "    - 2026年金額：11\n    - 2026年佔總收入比：55%\n")
TABLE_BODY = (
    '<table><tr><th rowspan="3" scope="col">Group</th><th rowspan="3" scope="col">Item</th>'
    '<th id="basis" colspan="4" scope="colgroup">截至12月31日止年度</th></tr>'
    '<tr><th id="y27" colspan="2" scope="colgroup">2027年</th>'
    '<th id="y26" colspan="2" scope="colgroup">2026年</th></tr>'
    '<tr><th id="a27" scope="col">金額人民幣千元</th><th id="s27" scope="col">佔總收入比</th>'
    '<th id="a26" scope="col">金額人民幣千元</th><th id="s26" scope="col">佔總收入比</th></tr>'
    '<tr><th scope="rowgroup">North</th><th scope="row">Delta</th>'
    '<td id="value-a27" headers="basis y27 a27">17</td>'
    '<td id="value-s27" headers="basis y27 s27">60%</td>'
    '<td id="value-a26" headers="basis y26 a26">11</td>'
    '<td id="value-s26" headers="basis y26 s26">55%</td></tr></table>'
)
TABLE = HEADING + TABLE_BODY
FIELDS = [
    BASIS + " / 2027年 / 金額人民幣千元：17",
    BASIS + " / 2027年 / 佔總收入比：60%",
    BASIS + " / 2026年 / 金額人民幣千元：11",
    BASIS + " / 2026年 / 佔總收入比：55%",
]
PATH_BODY = "North: / Delta；" + "；".join(FIELDS)
PATH = HEADING + PATH_BODY
REFERENCES = {"compact": COMPACT, "list": SPLIT, "table": TABLE}

# Each tuple is an independent scalar, not a row-name question or a unit vote.
# subject, attribute, value, period, unit, currency, period basis, group, role.
FOUR = [
    ("Delta", "金額", "17", "2027年", "人民幣千元", "人民幣", BASIS, "North", "metric"),
    ("Delta", "佔總收入比", "60", "2027年", "%", None, BASIS, "North", "metric"),
    ("Delta", "金額", "11", "2026年", "人民幣千元", "人民幣", BASIS, "North", "metric"),
    ("Delta", "佔總收入比", "55", "2026年", "%", None, BASIS, "North", "metric"),
]
RAW_VALUE_SPANS = {("金額", "2027年"): [45, 47], ("佔總收入比", "2027年"): [76, 79],
                   ("金額", "2026年"): [110, 112], ("佔總收入比", "2026年"): [141, 144]}
RAW_VALUES = {("金額", "2027年"): "17", ("佔總收入比", "2027年"): "60%",
              ("金額", "2026年"): "11", ("佔總收入比", "2026年"): "55%"}
WORDS = Counter({"Review": 1, "Revenue": 1, "North": 1, "Delta": 1, BASIS: 4,
                 "2027年": 2, "2026年": 2, "金額": 2, "佔總收入比": 2,
                 "人民幣千元": 2, "%": 2, "17": 1, "60": 1, "11": 1, "55": 1})


def signature(fact):
    q = fact["qualifiers"]
    return (fact["subject"], fact["attribute"], fact["value"], q.get("period"), q.get("unit"),
            q.get("currency"), q.get("period_basis"), fact["identity_facets"].get("group"), fact["role"])


def require_four(facts):
    assert len(facts) == 4
    assert sorted(map(signature, facts), key=repr) == sorted(FOUR, key=repr)
    for fact in facts:
        q = fact["qualifiers"]
        assert set(q) == ({"period", "unit", "currency", "period_basis"} if fact["attribute"] == "金額"
                          else {"period", "unit", "period_basis"})
        assert fact["identity_facets"] == {"group": "North"}
        assert fact["scope"] == ["Review", "Revenue"]
        assert fact["source"]["path"]


def final_graph(markdown=PATH, pipeline="P07"):
    observation = markdown_observation(markdown, sample_id=SAMPLE, pipeline=pipeline, pages=[1])
    before = deepcopy(observation)
    graph = read_candidate(observation)
    assert observation == before
    return graph


def requirements(markdown=TABLE):
    return compile_markdown(markdown, sample_id=SAMPLE, path="<header-path-reference>")


def business(score):
    return [row for row in score["outcomes"] if row["layer"] == "B"]


@pytest.mark.parametrize("reference", REFERENCES.values(), ids=REFERENCES)
def test_four_requirements_have_fixed_roles_qualifiers_weight_and_no_extra_name_question(reference):
    graph = requirements(reference)
    require_four(graph["business"])
    assert graph["blockers"] == []
    assert Counter(atom["text"] for atom in graph["text"]) == WORDS
    assert sum(len(atom["text"]) for atom in graph["text"]) == 121
    # Four bindings + two amount fields with four qualifiers each, two share
    # fields with three qualifiers each + Review->Revenue heading relation.
    assert Counter(edge["type"] for edge in graph["relations"]) == {
        "field_binding": 4, "qualifier_scope": 14, "heading_parent": 1}


@pytest.mark.parametrize("pipeline", ["P07", "P08"])
def test_final_path_list_reads_four_actual_positions_and_all_printed_text(pipeline):
    graph = final_graph(pipeline=pipeline)
    require_four(graph["business"])
    assert graph["blockers"] == []
    assert Counter(atom["text"] for atom in graph["text"]) == WORDS
    assert sum(len(atom["text"]) for atom in graph["text"]) == 121
    for fact in graph["business"]:
        key = fact["attribute"], fact["qualifiers"]["period"]
        source = fact["source"]
        assert source["path"] == "markdown:L5:2" and source["lines"] == [5, 5]
        assert source["text_span"] == RAW_VALUE_SPANS[key]
        assert PATH_BODY[slice(*source["text_span"])] == RAW_VALUES[key]
    for atom in graph["text"]:
        for origin in atom.get("origins", [atom]):
            source = origin["source"]
            if source.get("lines") == [5, 5]:
                assert PATH_BODY[slice(*source["text_span"])] == origin["text"]


@pytest.mark.parametrize("reference", REFERENCES.values(), ids=REFERENCES)
@pytest.mark.parametrize("pipeline", ["P07", "P08"])
def test_compact_list_and_table_match_final_markdown_paths_with_one_common_four_fact_contract(reference, pipeline):
    expected = requirements(reference)
    require_four(expected["business"])
    actual = final_graph(pipeline=pipeline)
    require_four(actual["business"])
    score = grade_layers(expected, actual)
    assert score["publishable"] is True
    assert score["layers"]["B"]["denominator"] == score["layers"]["B"]["numerator"] == 4
    assert score["layers"]["T"]["denominator"] == score["layers"]["T"]["numerator"] == 121
    assert score["layers"]["L"]["denominator"] == score["layers"]["L"]["numerator"] == 19
    for row in business(score):
        assert len(row["actual"]) == 1
        assert row["retrieval"]["query"]["subject"] == "Delta"
        assert row["retrieval"]["query"]["identity_facets"] == {"group": "North"}
        assert "value" not in row["retrieval"]["query"]
    validate_evidence(score)


@pytest.mark.parametrize("old,new,dimension,correct", [
    ("2027年 / 金額", "2028年 / 金額", "qualifiers", 3),
    ("金額人民幣千元：17", "金額人民幣百萬元：17", "qualifiers", 3),
    ("North: / Delta", "South: / Delta", "identity_facets", 0),
    ("金額人民幣千元：17", "負債人民幣千元：17", "attribute", 3),
    ("截至12月31日止年度 / 2027年 / 金額", "截至6月30日止年度 / 2027年 / 金額", "qualifiers", 3),
])
def test_wrong_path_position_is_excluded_before_comparing_its_correct_numeric_literal(old, new, dimension, correct):
    actual = final_graph(PATH.replace(old, new, 1))
    assert len(actual["business"]) == 4
    score = grade_layers(requirements(), actual)
    assert score["publishable"] is True
    assert score["layers"]["B"]["denominator"] == 4 and score["layers"]["B"]["numerator"] == correct
    rows = business(score)
    target = rows if dimension == "identity_facets" else [r for r in rows if r["expected"]["attribute"] == "金額"
              and r["expected"]["qualifiers"]["period"] == "2027年"]
    assert target and all(not row["retrieval"]["accepted"] for row in target)
    for row in target:
        assert "17" not in repr(row["retrieval"]["query"]) and "11" not in repr(row["retrieval"]["query"])
        for hit in row["retrieval"]["candidates"]:
            assert hit["decision"] == "rejected" and hit["reason"]
        if dimension != "attribute":
            assert any(not hit["identity"][dimension]["correct"] for hit in row["retrieval"]["candidates"])


def test_amount_literal_typo_does_not_erase_the_complete_path_bindings():
    score = grade_layers(requirements(), final_graph(PATH.replace("元：17", "元：18", 1)))
    assert score["publishable"] is True
    assert score["layers"]["B"]["denominator"] == 4 and score["layers"]["B"]["numerator"] == 3
    assert score["layers"]["L"]["denominator"] == 19 and score["layers"]["L"]["score"] == 100
    assert score["layers"]["T"]["score"] < 100


def test_exchanging_two_amount_literals_retains_text_and_relations_but_fails_each_annual_amount():
    swapped = PATH.replace("元：17", "元：swap", 1).replace("元：11", "元：17", 1).replace("元：swap", "元：11", 1)
    score = grade_layers(requirements(), final_graph(swapped))
    assert score["publishable"] is True
    assert score["layers"]["T"]["score"] == score["layers"]["L"]["score"] == 100
    assert score["layers"]["B"]["denominator"] == 4 and score["layers"]["B"]["numerator"] == 2


def test_explicit_table_header_reference_swap_changes_binding_while_visible_text_is_intact():
    wrong = TABLE.replace('headers="basis y27 a27">17', 'headers="basis y26 a26">17').replace(
        'headers="basis y26 a26">11', 'headers="basis y27 a27">11')
    score = grade_layers(requirements(), final_graph(wrong))
    assert score["publishable"] is True
    assert score["layers"]["T"]["score"] == 100
    assert score["layers"]["B"]["denominator"] == 4 and score["layers"]["B"]["numerator"] == 2
    assert score["layers"]["L"]["score"] < 100


@pytest.mark.parametrize("mutation", ["value_span", "source_path"])
def test_forged_path_value_source_cannot_publish_even_if_the_candidate_ledger_agrees(mutation):
    graph = final_graph()
    require_four(graph["business"])
    fact = next(f for f in graph["business"] if f["attribute"] == "金額" and f["qualifiers"]["period"] == "2027年")
    fact["source"] = deepcopy(fact["source"])
    if mutation == "value_span":
        fact["source"]["text_span"] = [110, 112]  # Actual delivered literal is 11, not this fact's 17.
    else:
        fact["source"]["path"] = "<absent-delivered-path>"
    if "requirement_ledger" in graph:
        graph["requirement_ledger"] = deepcopy(graph["business"])
    try:
        score = grade_layers(requirements(), graph)
    except ValueError:
        return
    if not score["publishable"]:
        assert score["blockers"]
        return
    with pytest.raises(ValueError):
        validate_evidence(score)


def test_unscoped_yoy_retains_four_proven_scalars_and_its_own_pending_comparison():
    graph = final_graph(PATH + "；金額同比變動：5%")
    scalars = [f for f in graph["business"] if f["attribute"] in {"金額", "佔總收入比"}]
    require_four(scalars)
    assert graph["blockers"] and any("B" in b.get("layers", []) for b in graph["blockers"])
    changes = [f for f in [*graph["business"], *graph.get("pending_requirements", [])]
               if f.get("attribute") == "金額同比變動"]
    assert changes
    assert all(not f.get("qualifiers", {}).get("from_period") and not f.get("qualifiers", {}).get("to_period")
               for f in changes)
    score = grade_layers(requirements(), graph)
    assert score["publishable"] is False


def test_path_delimiters_do_not_globally_split_plain_field_values_urls_or_times():
    text = "Label: A / B\n\nLink: https://example.test/Room17\n\nTime: 9:00"
    graph = final_graph(text)
    assert graph["blockers"] == []
    assert [(f["attribute"], f["value"]) for f in graph["business"]] == [
        ("Label", "A / B"), ("Link", "https://example.test/Room17"), ("Time", "9:00")]
    assert any(atom["text"] == "A / B" for atom in graph["text"])
