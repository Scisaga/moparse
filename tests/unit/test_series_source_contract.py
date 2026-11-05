"""Independent token-position oracles; repeated digits never select sources."""

from copy import deepcopy

import pytest

from moparse_eval.scalar_evidence import validate_scalar_sources
from moparse_eval.series_requirements import read_series_requirements

TEXT = "Audit services / $m: 2024: 20; 2023:20."


@pytest.mark.parametrize("offset", [0, 40])
def test_repeated_value_twenty_is_bound_to_its_scalar_token_not_the_twenty_in_each_year(offset):
    source = {"path": "<printed-fee-series>", "lines": [7, 7], "text_span": [offset, offset + len(TEXT)]}
    original = deepcopy(source)
    result = read_series_requirements(TEXT, source)
    assert source == original
    assert result["blockers"] == [] and len(result["facts"]) == 2
    for fact, year, scalar_span, period_span in zip(result["facts"], ("2024", "2023"),
            ([27, 29], [36, 38]), ([21, 25], [31, 35]), strict=True):
        assert (fact["attribute"], fact["value"], fact["raw_value"]) == ("Audit services", "20", "20")
        assert fact["source"]["text_span"] == [offset + x for x in scalar_span]
        assert fact["value_source"]["text_span"] == [offset + x for x in scalar_span]
        assert fact["attribute_source"]["text_span"] == [offset, offset + 14]
        assert fact["qualifiers"]["unit"] == "$m"
        assert fact["qualifier_sources"]["unit"]["text_span"] == [offset + 17, offset + 19]
        assert fact["qualifier_sources"]["period"]["text_span"] == [offset + x for x in period_span]
        assert fact["qualifiers"]["period"] == year
    validate_scalar_sources(result["facts"], {"source_fragments": [{"source": source, "text": TEXT}]}, canonicalize=str.strip)


def test_source_guard_rejects_the_same_digits_taken_from_a_year_instead_of_the_scalar_token():
    source = {"path": "<printed-fee-series>", "lines": [7, 7]}
    [first, _second] = read_series_requirements(TEXT, source)["facts"]
    first["value_source"] = {**source, "text_span": [21, 23]}
    with pytest.raises(ValueError, match="source-bound scalar"):
        validate_scalar_sources([first], {"source_fragments": [{"source": source, "text": TEXT}]}, canonicalize=str.strip)


def test_all_annual_numeric_unit_tokens_have_their_own_literal_sources_and_scalar_raw_bounds():
    text = "Revenue:2024:20万元;2023:20万元."
    source = {"path": "<printed-money-series>", "lines": [9, 9]}
    result = read_series_requirements(text, source)
    assert result["blockers"] == []
    for fact, value_span, unit_span in zip(result["facts"], ([13, 15], [23, 25]), ([15, 17], [25, 27]), strict=True):
        assert fact["source"]["text_span"] == [value_span[0], unit_span[1]]
        assert fact["raw_value"] == "20万元" and fact["value"] == "20"
        assert fact["value_source"]["text_span"] == value_span
        assert fact["attribute_source"]["text_span"] == [0, 7]
        assert fact["qualifier_sources"]["unit"]["text_span"] == unit_span
    validate_scalar_sources(result["facts"], {"source_fragments": [{"source": source, "text": text}]}, canonicalize=str.strip)


def test_a_caller_declared_parent_label_keeps_the_callers_actual_source():
    parent = {"path": "<actual-parent-label>", "lines": [2, 2], "text_span": [4, 11]}
    result = read_series_requirements("2024:20;2023:20", {"path": "<annual-values>", "lines": [3, 3]},
                                      attribute="Revenue", attribute_source=parent)
    assert len(result["facts"]) == 2
    assert [fact["attribute_source"] for fact in result["facts"]] == [parent, parent]


@pytest.mark.parametrize("text,values", [
    ("Revenue:2024年20万元;2023年20万元;YoY:5%;Reason:shifted.",
     [("Revenue", "20"), ("Revenue", "20"), ("YoY", "5"), ("Reason", "shifted.")]),
    ("Balance:2024年USD 20;2023年USD 20", [("Balance", "20"), ("Balance", "20")]),
    ("Balance:2024年-万元;2023年(20)万元", [("Balance", "-"), ("Balance", "(20)")]),
])
def test_additional_fields_descriptions_prefix_currency_and_missing_marker_all_keep_precise_own_tokens(text, values):
    source = {"path": "<independent-series-tokens>", "lines": [5, 5]}
    result = read_series_requirements(text, source)
    assert [(fact["attribute"], fact["value"]) for fact in result["facts"]] == values
    for fact in result["facts"]:
        assert text[slice(*fact["source"]["text_span"])] == fact["raw_value"]
        assert text[slice(*fact["value_source"]["text_span"])] == fact["value"]
        assert text[slice(*fact["attribute_source"]["text_span"])] == fact["attribute"]
        for key, proof in fact["qualifier_sources"].items():
            if proof["path"] == source["path"] and key in {"unit", "currency", "period"}:
                assert text[slice(*proof["text_span"])] == fact["qualifiers"][key]
    validate_scalar_sources(result["facts"], {"source_fragments": [{"source": source, "text": text}]}, canonicalize=str.strip)
