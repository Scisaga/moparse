"""Hand-authored position, conflict and repeated-record business oracles."""

from __future__ import annotations

import copy

import pytest

from moparse_eval.business_correspondence import grade_business


def canonical(text):
    return " ".join(text.split())


def fact(identifier, attribute="Revenue", value="17", *, subject="Delta", period=None,
         unit=None, scope=(), facets=None, qualifiers=None, record=None):
    q = dict(qualifiers or {})
    if period is not None:
        q["period"] = period
    if unit is not None:
        q["unit"] = unit
    return {"id": identifier, "subject": subject, "attribute": attribute, "value": value,
            "qualifiers": q, "scope": list(scope), "identity_facets": dict(facets or {}),
            "role": "metric", "record_id": record,
            "source": {"path": f"<actual-{identifier}>", "lines": [1, 1]}}


def five(*, candidate=False):
    return [
        fact("a27", "金額", "17", period="2027年", unit="萬元"),
        fact("s27", "佔總收入比", "60", period="2027年", unit="%"),
        fact("a26", "金額", "11", period="2026年", unit="萬元"),
        fact("s26", "佔總收入比", "55", period="2026年", unit="%"),
        fact("change", "金額同比變動", "5", unit="%", qualifiers={"from_period": "2026年", "to_period": "2027年"}),
    ] if candidate else [
        fact("r-a27", "金額", "17", period="2027年", unit="萬元", scope=["North"], facets={"group": "North"}),
        fact("r-s27", "佔總收入比", "60", period="2027年", unit="%", scope=["North"], facets={"group": "North"}),
        fact("r-a26", "金額", "11", period="2026年", unit="萬元", scope=["North"], facets={"group": "North"}),
        fact("r-s26", "佔總收入比", "55", period="2026年", unit="%", scope=["North"], facets={"group": "North"}),
        fact("r-change", "金額同比變動", "5", unit="%", scope=["North"], facets={"group": "North"},
             qualifiers={"from_period": "2026年", "to_period": "2027年"}),
    ]


def grade(reference, actual, *, literals=None):
    return grade_business(reference, actual, literals=literals or [], canonicalize=canonical)


@pytest.mark.parametrize("dimension", ["condition", "negation", "exception", "note", "modal"])
def test_asserted_logic_is_compared_after_location_and_cannot_hide_a_local_conflict(dimension):
    expected = [fact("requirement", attribute="payment", qualifiers={dimension: "approved by four directors"})]
    exact = fact("a", attribute="payment", qualifiers={dimension: "approved by four directors"})
    conflict = fact("b", attribute="payment", qualifiers={dimension: "approved by three directors"})
    layer, rows = grade(expected, [exact, conflict])
    assert layer["complete"] is True and layer["denominator"] == 1 and layer["numerator"] == 0
    assert rows[0]["retrieval"]["accepted"] == ["a", "b"]
    assert dimension not in rows[0]["retrieval"]["query"]["qualifiers"]
    assert rows[0]["reason"] == "complete_assertion_value_or_qualifier_set_different"


def test_five_positions_accept_group_scope_from_the_candidates_own_declared_axis():
    actual = five(candidate=True)
    for item in actual:
        item["identity_facets"]["group"] = "North"
    layer, rows = grade(five(), actual)
    assert layer["complete"] is True and layer["denominator"] == layer["numerator"] == 5
    assert [row["outcome"] for row in rows] == ["correct"] * 5
    for row in rows:
        assert len(row["retrieval"]["accepted"]) == 1
        selected = next(hit for hit in row["retrieval"]["candidates"] if hit["decision"] == "accepted")
        assert selected["context_evidence"]["candidate_scope"] == []
        assert selected["context_evidence"]["candidate_facets"] == {"group": "North"}


def test_one_year_value_typo_does_not_clear_the_other_years_measurement():
    actual = five(candidate=True)
    for item in actual:
        item["identity_facets"]["group"] = "North"
    actual[0]["value"] = "18"
    layer, rows = grade(five(), actual)
    assert layer["denominator"] == 5 and layer["numerator"] == 4
    assert [(row["expected"]["attribute"], row["expected"]["qualifiers"].get("period"))
            for row in rows if row["outcome"] == "incorrect"] == [("金額", "2027年")]
    assert rows[2]["outcome"] == "correct"


def test_queries_never_include_the_correct_value_and_all_same_attribute_hits_are_retained():
    reference = [fact("r", period="2027年", unit="萬元")]
    actual = [fact("right", period="2027年", unit="萬元"), fact("wrong-year", period="2026年", unit="萬元")]
    layer, [row] = grade(reference, actual)
    assert layer["score"] == 100
    query = row["retrieval"]["query"]
    assert set(query) == {"subject", "attribute", "scope", "identity_facets", "qualifiers"}
    assert "value" not in query and "raw_value" not in query
    assert "17" not in repr(query)
    assert [hit["id"] for hit in row["retrieval"]["candidates"]] == ["right", "wrong-year"]
    rejected = row["retrieval"]["candidates"][1]
    assert rejected["decision"] == "rejected"
    assert rejected["identity"]["qualifiers"]["checks"]["period"] == {
        "required": "2027年", "actual": "2026年", "correct": False, "status": "explicit_conflict"}


@pytest.mark.parametrize("dimension,expected,observed", [
    ("period", "2027年", "2028年"), ("unit", "萬元", "千元"), ("currency", "USD", "CNY"),
    ("scope", "excluding tax", "including tax"), ("from_period", "2026年", "2025年"),
    ("to_period", "2027年", "2028年"), ("period_basis", "year ended December", "quarter ended December"),
])
def test_unique_candidate_checks_every_explicit_position_dimension_before_values(dimension, expected, observed):
    wanted = fact("r", qualifiers={dimension: expected})
    candidate = fact("c", qualifiers={dimension: observed})
    layer, [row] = grade([wanted], [candidate])
    assert layer["score"] == 0 and layer["denominator"] == 1
    assert row["actual"] == []
    [hit] = row["retrieval"]["candidates"]
    assert hit["decision"] == "rejected"
    assert hit["identity"]["qualifiers"]["checks"][dimension]["correct"] is False
    assert "conflict" in hit["reason"]


def test_wrong_group_is_not_rescued_by_a_matching_heading_elsewhere():
    wanted = fact("r", scope=["North"], facets={"group": "North"})
    candidate = fact("c", scope=["North"], facets={"group": "South"})
    layer, [row] = grade([wanted], [candidate])
    assert layer["score"] == 0
    [hit] = row["retrieval"]["candidates"]
    assert hit["identity"]["identity_facets"]["checks"]["group"]["actual"] == "South"
    assert hit["identity"]["scope"]["effective_actual"] == ["North", "South"]


def test_required_empty_scope_allows_extra_candidate_context_without_inventing_it():
    wanted = fact("r")
    candidate = fact("c", scope=["Report", "South"], facets={"group": "South"})
    layer, [row] = grade([wanted], [candidate])
    assert layer["score"] == 100
    [hit] = row["retrieval"]["candidates"]
    assert hit["identity"]["scope"]["required"] == []
    assert hit["identity"]["scope"]["actual"] == ["Report", "South"]
    assert hit["context_evidence"]["candidate_facets"]["group"] == "South"


def test_required_group_still_constrains_an_empty_heading_path():
    layer, [row] = grade([fact("r", facets={"group": "North"})], [fact("c", facets={"group": "South"})])
    assert layer["score"] == 0
    assert row["retrieval"]["accepted"] == []


def test_extra_report_ancestor_does_not_remove_a_correct_printed_group():
    layer, [row] = grade([fact("r", scope=["North"], facets={"group": "North"})],
                        [fact("c", scope=["Report", "North"])])
    assert layer["score"] == 100
    assert row["retrieval"]["accepted"] == ["c"]


def test_repeated_leaf_group_in_a_different_explicit_parent_is_not_the_same_scope():
    layer, [row] = grade([fact("r", scope=["East", "North"])], [fact("c", scope=["West", "North"])])
    assert layer["score"] == 0
    assert row["retrieval"]["candidates"][0]["identity"]["scope"]["correct"] is False


@pytest.mark.parametrize("key", ["condition", "exception", "note", "negation"])
def test_condition_note_exception_and_negation_remain_complete_requirements(key):
    layer, [row] = grade([fact("r", qualifiers={key: "only when permitted"})],
                        [fact("c", qualifiers={key: "even when denied"})])
    assert layer["score"] == 0
    assert key not in row["retrieval"]["query"]["qualifiers"]
    assert row["retrieval"]["accepted"] == ["c"]
    assert row["comparisons"][0]["qualifiers"][key]["correct"] is False


def test_known_extra_qualifier_is_a_complete_assertion_difference_not_deleted_or_called_hallucination():
    layer, [row] = grade([fact("r")], [fact("c", qualifiers={"condition": "unless denied"})])
    assert layer["complete"] is True and layer["score"] == 0
    assert row["actual"][0]["qualifiers"] == {"condition": "unless denied"}
    assert row["reason"] == "complete_assertion_value_or_qualifier_set_different"
    assert "hallucination" not in repr(row)


def test_unknown_extra_qualifier_blocks_software_publication_instead_of_becoming_zero():
    layer, [row] = grade([fact("r")], [fact("c", qualifiers={"unclassified_basis": "unknown meaning"})])
    assert layer["complete"] is False and layer["score"] is None and layer["numerator"] is None
    assert layer["denominator"] == 1
    assert layer["blockers"][0]["reason"] == "extra_qualifier_semantics_unsupported"
    assert row["software_failure"] is True


def repeated_records(*, swapped=False, provenance=True):
    result = [fact("a-r", value="17", record="A"), fact("a-p", "Profit", "5", record="A"),
              fact("b-r", value="11", record="B"), fact("b-p", "Profit", "7", record="B")]
    if swapped:
        result[1]["value"], result[3]["value"] = "7", "5"
    if not provenance:
        for item in result:
            item["record_id"] = None
    return result


def test_whole_repeated_records_can_reorder_without_using_values_to_pick_positions():
    reference = repeated_records()
    actual = copy.deepcopy(reference[2:] + reference[:2])
    for index, item in enumerate(actual):
        item["id"] = f"candidate-{index}"
        item["record_id"] = "actual-B" if index < 2 else "actual-A"
    layer, rows = grade(reference, actual)
    assert layer["score"] == 100 and layer["denominator"] == 4
    assert len(rows) == 4 and [row["outcome"] for row in rows] == ["correct"] * 4
    assert rows[0]["record_comparison"]["equal"] is True
    assert len(rows[0]["record_comparison"]["required_records"]) == 2


def test_cross_record_value_exchange_cannot_pass_independent_field_multisets():
    layer, rows = grade(repeated_records(), repeated_records(swapped=True))
    assert layer["score"] == 0
    assert [row["outcome"] for row in rows] == ["incorrect"] * 4
    assert len({row["root_cause"] for row in rows}) == 1
    assert rows[0]["record_comparison"]["equal"] is False
    assert rows[0]["reason"] == "complete_record_vector_multiset_different"


def test_missing_duplicate_record_provenance_is_a_software_blocker():
    layer, rows = grade(repeated_records(provenance=False), repeated_records(provenance=False))
    assert layer["score"] is None and layer["complete"] is False
    assert layer["denominator"] == 4
    assert layer["blockers"][0]["reason"] == "duplicate_record_provenance_unsupported"
    assert rows[0]["software_failure"] is True


def test_single_field_repetition_uses_the_complete_multiset_without_choosing_a_correct_value():
    reference = [fact("r-one"), fact("r-two", value="11")]
    layer, rows = grade(reference, [fact("c-two", value="11"), fact("c-one")])
    assert layer["score"] == 100 and len(rows) == 2
    layer, rows = grade(reference, [fact("c-two", value="11"), fact("c-one"), fact("conflict", value="18")])
    assert layer["score"] == 0 and len(rows) == 2
    assert len(rows[0]["actual"]) == 3


def test_approximate_label_recall_retains_the_difference_but_does_not_correct_the_candidate():
    candidate = fact("candidate", attribute="Revenuee")
    literals = [{"id": "printed-label", "text": "Revenuee", "role": "label", "source": {"path": "<printed>"}}]
    layer, [row] = grade([fact("r")], [candidate], literals=literals)
    assert layer["score"] == 0
    assert row["retrieval"]["candidates"][0]["recall"] == "approximate_attribute_with_retained_difference"
    assert row["retrieval"]["textual_hits"][0]["text"] == "Revenuee"
    assert row["retrieval"]["accepted"] == []


def test_an_exact_hit_in_the_wrong_scope_does_not_suppress_the_local_approximate_hit():
    reference = fact("r", scope=["North"])
    actual = [fact("other", scope=["South"]), fact("local", attribute="Revenuee", scope=["North"])]
    literals = [{"id": "elsewhere", "text": "Revenue", "role": "label", "scope": ["South"], "source": {"path": "<south>"}},
                {"id": "local", "text": "Revenuee", "role": "label", "scope": ["North"], "source": {"path": "<north>"}}]
    layer, [row] = grade([reference], actual, literals=literals)
    assert layer["score"] == 0
    assert [hit["id"] for hit in row["retrieval"]["candidates"]] == ["other", "local"]
    assert [hit["id"] for hit in row["retrieval"]["textual_hits"]] == ["elsewhere", "local"]
    assert row["retrieval"]["candidates"][0]["identity"]["scope"]["correct"] is False
    assert row["retrieval"]["candidates"][1]["identity"]["attribute"]["correct"] is False


def test_a_plain_literal_label_without_a_data_role_cannot_supply_a_value():
    literal = {"id": "header", "text": "Revenue: 17", "role": "literal", "source": {"path": "<printed>"}}
    layer, [row] = grade([fact("r")], [], literals=[literal])
    assert layer["score"] == 0 and row["actual"] == []
    assert len(row["retrieval"]["textual_hits"]) == 1
    assert row["retrieval"]["textual_hits"][0]["decision"] == "literal_evidence_only"


def test_year_label_equivalence_retains_both_original_spellings_in_the_trace():
    layer, [row] = grade([fact("r", period="2027年")], [fact("c", period="2027")])
    assert layer["score"] == 100
    check = row["retrieval"]["candidates"][0]["identity"]["qualifiers"]["checks"]["period"]
    assert check["required"] == "2027年" and check["actual"] == "2027"


def test_readback_and_correspondence_do_not_mutate_the_source_fact_collections():
    reference, actual = five(), five(candidate=True)
    original = copy.deepcopy((reference, actual))
    grade(reference, actual)
    assert (reference, actual) == original


def test_report_guard_rechecks_the_unique_hits_position_and_own_context():
    from moparse_eval.expected_report import _business_trace

    _, [row] = grade([fact("r", period="2027年", scope=["North"])],
                     [fact("c", period="2027年", scope=["North"])])
    _business_trace(row, {})
    altered = copy.deepcopy(row)
    altered["retrieval"]["candidates"][0]["identity"]["subject"]["actual"] = "Other entity"
    with pytest.raises(ValueError, match="inconsistent identity"):
        _business_trace(altered, {})
    altered = copy.deepcopy(row)
    altered["retrieval"]["query"]["qualifiers"] = {}
    with pytest.raises(ValueError, match="complete identity query"):
        _business_trace(altered, {})
    altered = copy.deepcopy(row)
    altered["retrieval"]["candidates"][0]["context_evidence"]["candidate_scope"] = ["invented"]
    with pytest.raises(ValueError, match="candidate's own"):
        _business_trace(altered, {})


def test_report_guard_cannot_accept_a_value_outside_its_original_recalled_fact():
    from moparse_eval.expected_report import _business_trace

    _, [row] = grade([fact("r")], [fact("c")])
    row["actual"][0]["value"] = "18"
    with pytest.raises(ValueError, match="actual recalled candidate"):
        _business_trace(row, {})


def test_report_guard_rechecks_record_vectors_instead_of_trusting_the_equal_flag():
    from moparse_eval.expected_report import _record_trace

    _, rows = grade(repeated_records(), repeated_records())
    assert _record_trace(rows[0]) is True
    rows[0]["record_comparison"]["actual_records"][0]["fields"][0]["value"] = "18"
    with pytest.raises(ValueError, match="record-vector comparison differs"):
        _record_trace(rows[0])


def relation_row(*, changed_header=False, typo=False):
    expected = {"id": "L-required", "type": "field_binding", "left": {"attribute": "Revenue"},
                "right": {"subject": "Delta", "attribute": "Revenue", "scope": [], "identity_facets": {}},
                "object_anchor": "independent-data-A", "header_anchors": ["independent-header-Revenue"],
                "row_anchors": ["independent-row-Delta"], "source": {"path": "<expected-link>"}}
    actual = copy.deepcopy(expected)
    actual.update(id="L-actual", source={"path": "<actual-link>"})
    if changed_header:
        actual["header_anchors"] = ["independent-header-Profit"]
        actual["left"]["attribute"] = actual["right"]["attribute"] = "Profit"
    if typo:
        actual["left"]["attribute"] = actual["right"]["attribute"] = "Reveneu"
    correct = not changed_header
    return {"id": "L-required", "layer": "L", "role": "field_binding", "expected": expected, "actual": actual,
            "outcome": "correct" if correct else "incorrect", "root_cause": "declared-link",
            "retrieval": {"method": "independent_object_anchor", "candidates": [{
                "id": actual["id"], "source": actual["source"], "evidence": copy.deepcopy(actual),
                "scope_verification": None, "correct": correct,
                "reason": "same_independent_objects_and_links" if correct else "explicit_binding_conflict"}],
                "selected": actual["id"] if correct else None}}


def test_relation_report_guard_preserves_proved_links_despite_a_label_typo():
    from moparse_eval.expected_report import _relation_trace

    row = relation_row(typo=True)
    used = set()
    _relation_trace(row, used, {})
    assert used == {"L-actual"}


def test_relation_report_guard_allows_an_incorrect_but_located_independent_object():
    from moparse_eval.expected_report import _relation_trace

    row = relation_row(changed_header=True)
    used = set()
    _relation_trace(row, used, {})
    assert row["actual"] is not None and row["outcome"] == "incorrect"
    assert used == {"L-actual"}
    with pytest.raises(ValueError, match="one candidate relation"):
        _relation_trace(copy.deepcopy(row), used, {})


def test_relation_report_guard_cannot_turn_existing_actual_into_automatic_correctness():
    from moparse_eval.expected_report import _relation_trace

    row = relation_row(changed_header=True)
    row["outcome"] = "correct"
    row["retrieval"]["candidates"][0]["correct"] = True
    row["retrieval"]["selected"] = "L-actual"
    with pytest.raises(ValueError, match="scope and endpoint proof"):
        _relation_trace(row, set(), {})
