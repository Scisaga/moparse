"""Exact instant and explicitly bounded interval roles, without fiscal inference."""

import pytest

from moparse_eval.business_correspondence import grade_business
from moparse_eval.equivalence import decide_equivalence
from moparse_eval.relation_correspondence import grade_relations


@pytest.mark.parametrize("required,actual", [("At", "截至"), ("As of", "As at"),
    ("Year Ended", "止年度"), ("For the year ended", "Year Ended"),
    ("For the six months ended", "止六个月"), ("Six months ended", "止六個月"),
    ("Quarter ended", "For the three months ended")])
def test_only_the_same_explicit_period_role_and_duration_are_equivalent(required, actual):
    decision = decide_equivalence(required, actual, "period_basis")
    assert decision["equivalent"] is True
    assert decision["rule_id"] == "declared_period_basis_equivalence"
    assert decision["proof"]["start_inferred"] is False and decision["proof"]["fiscal_year_inferred"] is False


@pytest.mark.parametrize("required,actual", [("At", "Year ended"), ("Year ended", "Six months ended"),
    ("For the six months ended", "Quarter ended"), ("Period ended", "Year ended"),
    ("截至", "止年度"), ("止六个月", "止年度")])
def test_wrong_duration_or_unknown_period_length_is_not_filled_from_the_other_side(required, actual):
    assert decide_equivalence(required, actual, "period_basis")["equivalent"] is False


def test_business_identity_and_logical_unit_scope_use_the_same_final_basis_rule():
    source = {"path": "<actual-field>"}
    def fact(identifier, basis):
        return {"id": identifier, "subject": "Delta", "attribute": "Revenue", "value": "17", "role": "metric",
                "scope": [], "identity_facets": {}, "source": source,
                "qualifiers": {"period": "2028-03-31", "period_basis": basis}}
    required, actual = fact("r", "For the year ended"), fact("a", "止年度")
    layer, _ = grade_business([required], [actual], literals=[], canonicalize=str.strip)
    assert layer["numerator"] == layer["denominator"] == 1
    def edge(identifier, item):
        endpoint = {key: item[key] for key in ("subject", "attribute", "scope", "identity_facets", "qualifiers")}
        return {"id": identifier, "type": "qualifier_scope", "left": {"type": "period_basis", "text": item["qualifiers"]["period_basis"]},
                "right": endpoint, "source": source}
    layer, rows = grade_relations([edge("r", required)], [edge("a", actual)], canonicalize=str.strip)
    assert layer["numerator"] == layer["denominator"] == 1
    assert rows[0]["retrieval"]["candidates"][0]["equivalence"]["equivalent"] is True
