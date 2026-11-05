"""Independent raw-snapshot proofs; no compiler supplies an answer or span."""

from copy import deepcopy

import pytest

from moparse_eval.scalar_evidence import validate_scalar_sources

SOURCE = {"path": "<original-scalar>", "lines": [7, 7], "block": "scalar-record"}
RAW = "Amount:17%; Other:11%"


def material():
    fact = {"subject": "Delta", "attribute": "Amount", "value": "17", "raw_value": "17%",
            "source": {**SOURCE, "text_span": [7, 10]}, "value_source": {**SOURCE, "text_span": [7, 9]}}
    projection = {"source_fragments": [{"source": deepcopy(SOURCE), "text": RAW}], "source_cells": []}
    return fact, projection


def check(fact, projection):
    validate_scalar_sources([fact], projection, canonicalize=lambda text: text.strip())


def test_full_raw_scalar_and_numeric_subspan_are_both_proved_in_the_actual_fragment():
    fact, projection = material()
    assert RAW[7:10] == "17%" and RAW[7:9] == "17"
    before = deepcopy((fact, projection))
    check(fact, projection)
    assert (fact, projection) == before


@pytest.mark.parametrize("mutation", ["all_sources", "raw_value_also_agrees", "only_value_source", "path", "block", "inner_path"])
def test_consistent_derived_claims_cannot_replace_independent_original_wording(mutation):
    fact, projection = material()
    if mutation in {"all_sources", "raw_value_also_agrees"}:
        fact["source"]["text_span"] = [18, 21]
        fact["value_source"]["text_span"] = [18, 20]
        if mutation == "raw_value_also_agrees":
            fact["raw_value"] = "11%"  # This copy agrees; the asserted value still has no 17 here.
    elif mutation == "only_value_source":
        fact["value_source"]["text_span"] = [18, 20]
    else:
        key = "block" if mutation == "block" else "path"
        fact["value_source"][key] = "<invented-location>"
        if mutation != "inner_path":
            fact["source"][key] = "<invented-location>"
    ledger = deepcopy([fact])
    assert ledger == [fact]
    assert projection["source_fragments"][0]["text"] == RAW
    with pytest.raises(ValueError, match="source-bound scalar"):
        check(fact, projection)


def test_shifted_original_fragment_offsets_are_preserved_without_rebasing_the_claim():
    fact, projection = material()
    projection["source_fragments"][0]["source"]["text_span"] = [40, 61]
    fact["source"]["text_span"] = [47, 50]
    fact["value_source"]["text_span"] = [47, 49]
    check(fact, projection)


def test_native_full_raw_unit_annotation_keeps_the_exact_numeric_subspan():
    source = {"path": "#/native/table", "block": "table", "cell": "cell-17",
              "native_path": "#/native/table/cell-17", "row": 1, "col": 2}
    raw = "17（单位：(人民币百万元)）"
    fact = {"value": "17", "raw_value": raw, "source": deepcopy(source),
            "value_source": {**source, "text_span": [0, 2], "cell_text_span": [0, 2]}}
    projection = {"source_cells": [{"source": deepcopy(source), "text": raw}], "source_fragments": []}
    check(fact, projection)


@pytest.mark.parametrize("span", [[-1, 9], [7, 99], [True, 9], [9, 7]])
def test_invalid_value_ranges_are_not_repaired_or_used_as_partial_evidence(span):
    fact, projection = material()
    fact["value_source"]["text_span"] = span
    with pytest.raises(ValueError, match="source-bound scalar"):
        check(fact, projection)


def test_unbound_prose_has_no_new_numeric_source_contract_imposed_on_it():
    validate_scalar_sources([{"value": "pay 17 credits", "value_source": SOURCE}], {},
                            canonicalize=lambda text: text.strip())
