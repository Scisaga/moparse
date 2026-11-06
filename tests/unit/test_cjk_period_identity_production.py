"""Printed periods bind repeated metric sequences before numeric comparison."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_represented_feature_production import production

FIRST = "2028年，工业产值超过137万元，同比增长4.3%。"
SECOND = "2029年，工业产值超过151万元，同比增长2.7%。"
TEXT = FIRST + "\n\n" + SECOND + "\n"


def run(tmp_path, actual=TEXT, required=TEXT):
    # Independent oracle: two metrics per year, one shared printed period for
    # each pair, and one reading-order relation from 2028's block to 2029's.
    oracle = [("2028年", "超过", "137"), ("2028年", "同比增长", "4.3"),
              ("2029年", "超过", "151"), ("2029年", "同比增长", "2.7")]
    graph, expected = production(tmp_path, required)
    if required == TEXT:
        assert [(fact["qualifiers"]["period"], fact["attribute"], fact["value"])
                for fact in expected["business"]] == oracle
    return graph, grade_layers(expected, read_candidate_markdown(actual, sample_id=expected["sample_id"]))


@pytest.mark.parametrize("same_values", [False, True])
def test_two_years_of_one_metric_have_independent_source_period_identity(tmp_path, same_values):
    text = TEXT if not same_values else TEXT.replace("151", "137").replace("2.7", "4.3")
    graph, result = run(tmp_path, text, text)
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"] == 4
    assert result["layers"]["L"]["numerator"] == result["layers"]["L"]["denominator"] == 21
    assert graph["semantic_complete"]
    for layer in ("B", "L"):
        rows = result["semantic_comparison"]["decisions"][layer]["proof"]["rows"]
        assert [row["actual_index"] for row in rows] == [0, 1]
        assert all(not hit["value_used"] for row in rows for hit in row["retrieval"]["candidates"])
        assert rows[0]["retrieval"]["query"]["periods"] == ["2028"]
        assert rows[1]["retrieval"]["query"]["periods"] == ["2029"]
    validate_evidence(result)


def test_reordered_year_blocks_keep_business_answers_but_lose_their_printed_reading_order(tmp_path):
    _, result = run(tmp_path, SECOND + "\n\n" + FIRST + "\n")
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["score"] == 100
    assert result["layers"]["L"]["numerator"] == 20
    assert result["layers"]["L"]["denominator"] == 21
    rows = result["semantic_comparison"]["decisions"]["B"]["proof"]["rows"]
    assert [row["actual_index"] for row in rows] == [1, 0]
    order = [row for row in result["outcomes"] if row["layer"] == "L" and row["role"] == "prose_reading_order"]
    assert len(order) == 1 and order[0]["outcome"] == "incorrect"
    validate_evidence(result)


@pytest.mark.parametrize("actual,correct_business", [
    (TEXT.replace("137", "999"), 3),
    (FIRST.replace("137", "151").replace("4.3", "2.7") + "\n\n" + SECOND.replace("151", "137").replace("2.7", "4.3") + "\n", 0),
])
def test_wrong_or_neighboring_year_values_cannot_choose_different_positions(tmp_path, actual, correct_business):
    _, result = run(tmp_path, actual)
    assert result["publishable"], result["blockers"]
    assert result["layers"]["B"]["numerator"] == correct_business
    assert result["layers"]["B"]["denominator"] == 4
    assert result["layers"]["L"]["score"] == 100
    rows = result["semantic_comparison"]["decisions"]["B"]["proof"]["rows"]
    assert [row["actual_index"] for row in rows] == [0, 1]
    assert all(not hit["value_used"] for row in rows for hit in row["retrieval"]["candidates"])
    validate_evidence(result)


def test_missing_printed_year_stays_in_the_expected_business_and_scope_denominators(tmp_path):
    _, result = run(tmp_path, TEXT.replace("2029年，", ""))
    assert result["layers"]["B"]["denominator"] == 4
    assert result["layers"]["L"]["denominator"] == 21
    assert not result["publishable"] or result["layers"]["B"]["numerator"] < 4
    if result["publishable"]:
        assert result["layers"]["L"]["numerator"] < 21
        validate_evidence(result)


@pytest.mark.parametrize("actual", [TEXT.replace("2029年", "2028年"), TEXT + "\n" + FIRST + "\n"])
def test_duplicate_period_identity_and_repeated_records_stay_unresolved(tmp_path, actual):
    _, result = run(tmp_path, actual)
    assert result["layers"]["B"]["denominator"] == 4
    assert not result["publishable"]
    assert result["layers"]["B"]["score"] is None
    assert result["layers"]["L"]["score"] is None


def test_a_neighbor_period_source_cannot_replace_the_own_printed_year(tmp_path):
    _, expected = production(tmp_path, TEXT)
    candidate = read_candidate_markdown(TEXT, sample_id=expected["sample_id"])
    candidate["logical_statements"][1]["period"]["source"] = deepcopy(candidate["logical_statements"][0]["period"]["source"])
    result = grade_layers(expected, candidate)
    assert not result["publishable"]
    assert result["layers"]["B"]["score"] is None and result["layers"]["L"]["score"] is None


@pytest.mark.parametrize("actual,required", [
    (TEXT.replace("137万元", "137美元"), TEXT),
    ("# South\n\n" + TEXT, "# North\n\n" + TEXT),
])
def test_printed_year_identity_does_not_override_independent_unit_or_heading_conflict(tmp_path, actual, required):
    _, result = run(tmp_path, actual, required)
    assert result["layers"]["B"]["denominator"] == 4
    assert result["layers"]["B"]["numerator"] < 4
    assert result["layers"]["L"]["numerator"] < result["layers"]["L"]["denominator"]
    if result["publishable"]:
        validate_evidence(result)


@pytest.mark.parametrize("span", [[], [0], [-1, 5], [0, "5"]])
def test_malformed_period_identity_sources_fail_closed_without_reader_exception(tmp_path, span):
    _, expected = production(tmp_path, TEXT)
    candidate = read_candidate_markdown(TEXT, sample_id=expected["sample_id"])
    candidate["logical_statements"][1]["period"]["source"]["text_span"] = span
    result = grade_layers(expected, candidate)
    assert not result["publishable"]
    assert result["layers"]["B"]["score"] is None and result["layers"]["L"]["score"] is None
    decisions = result["semantic_comparison"]["decisions"]["B"]["proof"]["rows"]
    assert decisions[1]["decision"]["status"] == "unresolved"
