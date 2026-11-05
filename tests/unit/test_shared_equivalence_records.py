"""Fixed repeated-record oracles, including cross-record value swaps."""

import pytest

from moparse_eval.business_correspondence import grade_business


def records(actual=False, swapped=False):
    values = [("170000", "50000"), ("110000", "30000")] if actual else [("17", "5"), ("11", "3")]
    result = []
    for index, (revenue, profit) in enumerate(values):
        if swapped:
            profit = values[1 - index][1]
        for attr, value in (("Revene" if actual else "Revenue", revenue), ("Profit", profit)):
            result.append({"id": f'{"a" if actual else "r"}:{index}:{attr}', "subject": "Delta",
                           "attribute": attr, "value": value, "role": "metric", "record_id": f"record:{index}",
                           "scope": ["North"], "identity_facets": {},
                           "qualifiers": {"period": "2027年", "unit": "元" if actual else "万元"},
                           "source": {"path": f"<own-record-{index}-{attr}>"}})
    return result


@pytest.mark.parametrize("swapped", [False, True])
def test_complete_record_vectors_use_final_label_and_exact_quantity_rules_without_picking_values(swapped):
    layer, rows = grade_business(records(), records(actual=True, swapped=swapped), literals=[], canonicalize=str.strip)
    assert layer["complete"] is True and layer["denominator"] == 4
    assert layer["numerator"] == (0 if swapped else 4)
    assert all(row["record_comparison"]["equal"] is (not swapped) for row in rows)
    assert all("value" not in row["retrieval"]["query"] for row in rows)


def test_an_exact_hit_cannot_hide_a_context_proven_one_edit_conflicting_assertion():
    reference = records()[:1]
    exact = {**reference[0], "id": "exact"}
    conflict = {**exact, "id": "conflict", "attribute": "Revenuee", "value": "18"}
    layer, [row] = grade_business(reference, [exact, conflict], literals=[], canonicalize=str.strip)
    assert layer["numerator"] == 0
    assert row["retrieval"]["accepted"] == ["exact", "conflict"]


def test_an_uninterpreted_unit_conversion_remains_software_unresolved_after_other_identity_is_proved():
    required = {**records()[0], "qualifiers": {"period": "2027年", "unit": "unfamiliar-units"}}
    actual = {**required, "id": "actual", "qualifiers": {"period": "2027年", "unit": "different-unfamiliar-units"}}
    layer, [row] = grade_business([required], [actual], literals=[], canonicalize=str.strip)
    assert layer["complete"] is False and layer["score"] is None
    assert any(block["reason"] == "unit_equivalence_unsupported" for block in layer["blockers"])
    assert row["software_failure"] is True
