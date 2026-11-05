"""Independent final-report acceptance and proof-mutation oracles."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


def score(repeated=False):
    required = "Period:2027年\n\nName:Delta;Revenue:17万元;Profit:5万元"
    actual = "Period:2027年\n\nName:Delta;Revenuee:170000元;Profit:50000元"
    if repeated:
        required += "\n\nName:Delta;Revenue:11万元;Profit:3万元"
        actual += "\n\nName:Delta;Revenuee:110000元;Profit:30000元"
    result = grade_layers(compile_markdown(required, sample_id="invented-equivalence-report"),
                         read_candidate_markdown(actual, sample_id="invented-equivalence-report"))
    assert result["publishable"] is True
    assert result["layers"]["B"]["numerator"] == result["layers"]["B"]["denominator"]
    assert result["layers"]["L"]["numerator"] == result["layers"]["L"]["denominator"]
    return result


@pytest.mark.parametrize("repeated", [False, True])
def test_valid_final_scale_label_and_complete_record_equivalence_is_accepted_by_report(repeated):
    validate_evidence(score(repeated))


@pytest.mark.parametrize("mutation", ["quantity_flag", "quantity_ratio", "quantity_rule", "relation_flag", "relation_canonical"])
def test_derived_equivalence_claims_are_replayed_instead_of_trusted(mutation):
    material = score()
    before = deepcopy(material)
    if mutation.startswith("quantity"):
        [row] = [r for r in material["outcomes"] if r["layer"] == "B" and r["expected"]["attribute"] == "Revenue"]
        proof = row["comparisons"][0]["value"]["equivalence"]
        if mutation == "quantity_flag":
            proof["equivalent"] = False
        elif mutation == "quantity_ratio":
            proof["canonical"]["actual"]["value"]["numerator"] += 1
        else:
            proof["rule_id"] = "candidate_claims_an_undeclared_rule"
    else:
        row = next(r for r in material["outcomes"] if r["layer"] == "L" and r["retrieval"]["selected"])
        proof = next(h for h in row["retrieval"]["candidates"] if h["id"] == row["retrieval"]["selected"])["equivalence"]
        if mutation == "relation_flag":
            proof["equivalent"] = False
        else:
            proof["canonical"]["actual"] = "a different endpoint"
    assert material != before
    with pytest.raises(ValueError, match="equivalence|comparison"):
        validate_evidence(material)


def test_a_record_field_label_mapping_cannot_be_reassigned_even_when_the_claimed_record_pass_is_unchanged():
    material = score(repeated=True)
    for row in material["outcomes"]:
        if row["layer"] == "B" and row.get("record_comparison"):
            row["record_comparison"]["field_equivalence"][0]["required_attribute"] = "Profit"
    with pytest.raises(ValueError, match="equivalence|record"):
        validate_evidence(material)


def test_a_complete_required_record_contract_cannot_be_deleted_from_every_row():
    material = score(repeated=True)
    for row in material["outcomes"]:
        if row["layer"] == "B":
            row.pop("record_comparison", None)
    with pytest.raises(ValueError, match="record"):
        validate_evidence(material)


@pytest.mark.parametrize("wrong_duration", [False, True])
def test_whole_date_basis_and_symbol_scale_rules_survive_the_public_reader_and_report(wrong_duration):
    required = "Revenue; Year Ended March 31, 2028 ($m): 17; Year Ended March 31, 2027 ($m): 11"
    suffix = "止六个月" if wrong_duration else "止年度"
    actual = (f"Revenue; 截至二〇二八年三月三十一日{suffix}（$）: 17000000; "
              f"截至二〇二七年三月三十一日{suffix}（$）: 11000000")
    material = grade_layers(compile_markdown(required, sample_id="invented-period-report"),
                            read_candidate_markdown(actual, sample_id="invented-period-report"))
    assert material["publishable"] is True
    assert material["layers"]["B"]["denominator"] == 2
    assert material["layers"]["B"]["numerator"] == (0 if wrong_duration else 2)
    if not wrong_duration:
        assert material["layers"]["L"]["numerator"] == material["layers"]["L"]["denominator"] == 8
    assert material["layers"]["T"]["numerator"] < material["layers"]["T"]["denominator"]
    validate_evidence(material)
