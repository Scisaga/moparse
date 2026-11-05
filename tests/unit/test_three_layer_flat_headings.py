"""Display heading levels cannot become the business or logical answer."""

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate


def score(reference, actual):
    return grade_layers(compile_markdown(reference), read_candidate(markdown_observation(
        actual, sample_id="synthetic", pipeline="P01", pages=[1])))


def test_each_actual_parent_and_child_heading_is_proved_despite_flat_display_levels():
    reference = "# Financial review\n\n## Revenue\n\nRevenue: 17\n\n## Cost\n\nCost: 5"
    candidate = "## Financial review\n\n## Revenue\n\nRevenue: 18\n\n## Cost\n\nCost: 5"
    native = read_candidate(markdown_observation(candidate, sample_id="synthetic", pipeline="P01", pages=[1]))
    assert not [edge for edge in native["relations"] if edge["type"] == "heading_parent"]
    assert [event["level"] for event in native["native_context"]["heading_events"]] == [2, 2, 2]
    result = score(reference, candidate)
    assert result["publishable"] is True
    assert result["layers"]["L"]["denominator"] == result["layers"]["L"]["numerator"] == 4
    assert result["layers"]["B"]["denominator"] == 2 and result["layers"]["B"]["numerator"] == 1
    assert result["layers"]["T"]["score"] < 100
    parents = [row for row in result["outcomes"] if row["layer"] == "L" and row["role"] == "heading_parent"]
    assert len(parents) == 2
    assert all(row["actual"]["type"] == "heading_position" and row["retrieval"]["candidates"][0]["scope_verification"]
               for row in parents)


def test_the_missing_parent_is_never_supplied_by_the_reference_tree():
    reference = "# Financial review\n\n## Revenue\n\nRevenue: 17"
    result = score(reference, "## Revenue\n\nRevenue: 17")
    assert result["layers"]["B"]["numerator"] == 0
    assert result["layers"]["L"]["numerator"] == 0


def test_flat_display_cannot_borrow_a_correct_value_from_the_next_declared_parent():
    reference = "# North\n\n## Revenue\n\nRevenue: 17\n\n# South\n\n## Revenue\n\nRevenue: 29"
    candidate = "## North\n\n## Revenue\n\nRevenue: 18\n\n## South\n\n## Revenue\n\nRevenue: 17"
    result = score(reference, candidate)
    assert result["layers"]["B"]["denominator"] == 2 and result["layers"]["B"]["numerator"] == 0
    rows = [r for r in result["outcomes"] if r["layer"] == "B"]
    assert [r["actual"][0]["value"] for r in rows] == ["18", "17"]
