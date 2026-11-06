"""Hand-authored occurrence-capacity oracle independent of compiler outputs."""

from copy import deepcopy

import pytest

from moparse_eval.business_correspondence import grade_business
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


def test_one_actual_business_occurrence_cannot_satisfy_multiple_fuzzy_requirement_groups():
    # Two explicitly printed assertions require two occurrences. One candidate
    # assertion cannot be spent once for its literal label and again for a typo.
    required = compile_markdown(
        "Period: 2027年\n\nName: Delta; Revenue: 17万元; Revene: 17万元", sample_id="capacity-oracle")
    actual = read_candidate_markdown(
        "Period: 2027年\n\nName: Delta; Revenue: 17万元", sample_id="capacity-oracle")
    score = grade_layers(required, actual)
    metrics = [row for row in score["outcomes"] if row["layer"] == "B" and row["expected"]["role"] == "metric"]
    assert len(metrics) == 2
    assert sum(row["outcome"] == "correct" for row in metrics) <= 1
    assert score["layers"]["B"]["numerator"] <= 2


def fact(ident, attribute, value, *, scope=()):
    # Hand-authored roles and contexts are the independent oracle; no expected
    # or candidate reader supplies these source-bound business objects.
    return {"id": ident, "role": "metric", "subject": "Invented entity", "attribute": attribute,
            "value": value, "scope": list(scope), "identity_facets": {},
            "qualifiers": {"period": "2027", "unit": "元"}, "source": {"path": f"<{ident}>"}}


def direct(required, actual):
    before = deepcopy((required, actual))
    layer, rows = grade_business(required, actual, literals=[], canonicalize=lambda text: text.casefold())
    assert (required, actual) == before
    return layer, {row["id"]: row for row in rows}


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_identity_owns_its_occurrence_independently_of_requirement_order(reverse):
    required = [fact("r1", "Revenue", "17"), fact("r2", "Revene", "5")]
    actual = [fact("a1", "Revenue", "17"), fact("a2", "Revene", "5")]
    if reverse:
        required.reverse()
        actual.reverse()
    layer, rows = direct(required, actual)
    assert layer["numerator"] == layer["denominator"] == 2
    assert rows["r1"]["retrieval"]["accepted"] == ["a1"]
    assert rows["r2"]["retrieval"]["accepted"] == ["a2"]
    assert all(proof["values_used"] is False for row in rows.values()
               for proof in row["retrieval"]["capacity"]["evidence"])


def test_correct_values_cannot_swap_two_distinct_candidate_positions():
    layer, rows = direct([fact("r1", "Revenue", "17"), fact("r2", "Revene", "5")],
                         [fact("a1", "Revenue", "5"), fact("a2", "Revene", "17")])
    assert layer["numerator"] == 0
    assert rows["r1"]["retrieval"]["accepted"] == ["a1"]
    assert rows["r2"]["retrieval"]["accepted"] == ["a2"]
    assert all(row["outcome"] == "incorrect" for row in rows.values())


@pytest.mark.parametrize("reverse", [False, True])
def test_ambiguous_fuzzy_identity_remains_insufficient_without_arbitrary_ownership(reverse):
    required = [fact("r1", "Revenue", "17"), fact("r2", "Revene", "5")]
    if reverse:
        required.reverse()
    layer, rows = direct(required, [fact("a1", "Revenxe", "17")])
    assert layer["numerator"] == 0 and layer["complete"] is True
    assert all(row["retrieval"]["accepted"] == [] for row in rows.values())
    assert all(row["retrieval"]["capacity"]["evidence"][0]["status"] == "insufficient" for row in rows.values())
    assert all(row["retrieval"]["capacity"]["evidence"][0]["owner_requirement_group"] is None for row in rows.values())


@pytest.mark.parametrize("actual_count,correct", [(1, False), (2, True)])
def test_repeated_identical_requirements_still_need_actual_occurrence_multiplicity(actual_count, correct):
    required = [fact("r1", "Revenue", "17"), fact("r2", "Revenue", "17")]
    actual = [fact(f"a{number}", "Revenue", "17") for number in range(actual_count)]
    layer, rows = direct(required, actual)
    assert layer["numerator"] == (2 if correct else 0)
    assert all((row["outcome"] == "correct") is correct for row in rows.values())
    assert all(row["retrieval"]["capacity"]["required_occurrences"] == 2 for row in rows.values())


def test_more_specific_printed_scope_owns_one_occurrence_without_reusing_it_for_broader_scope():
    layer, rows = direct([fact("broad", "Revenue", "17"), fact("retail", "Revenue", "17", scope=["Retail"])],
                         [fact("actual", "Revenue", "17", scope=["Retail"])])
    assert layer["numerator"] == 1
    assert rows["broad"]["outcome"] == "incorrect"
    assert rows["retail"]["outcome"] == "correct"
    assert rows["retail"]["retrieval"]["accepted"] == ["actual"]
