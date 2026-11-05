"""Invented ordinary-field and printed-superscript routing oracles."""

from copy import deepcopy

import pytest

from moparse_eval.compact_requirements import read_compact_requirements, read_compact_schema
from moparse_eval.series_requirements import read_series_requirements
from moparse_eval.three_layer import compile_markdown

SOURCE = {"path": "<printed-ordinary-field>", "lines": [9, 9], "text_span": [40, 120]}


@pytest.mark.parametrize("text", [
    "8、起息日：2028年3月4日。",
    "Issue date:2028年3月4日",
    "Date:2028年3月44日",
    "Date:2028年3月",
    "DateTime:2028年3月4日 09:00",
    "Timestamp:2028-03-04T09:00:17Z",
    "Time:09:00:17",
    "Code:2028:17",
    "编号：2028年17",
    "URL:https://example.invalid/2028:17",
    "Revenue:2028年3月4日",
])
def test_complete_dates_times_identifiers_and_urls_are_not_annual_amount_fields(text):
    source = deepcopy(SOURCE)
    result = read_series_requirements(text, source)
    assert result["matched"] is False
    assert result["facts"] == result["blockers"] == result["pending_requirements"] == []
    assert source == SOURCE
    compact = read_compact_requirements(text, source)
    assert compact["matched"] is False and compact["facts"] == compact["blockers"] == []


@pytest.mark.parametrize("text,label,value", [
    ("8、起息日：2028年3月4日。", "8、起息日", "2028年3月4日。"),
    ("DateTime:2028年3月4日 09:00", "DateTime", "2028年3月4日 09:00"),
    ("Code:2028:17", "Code", "2028:17"),
    ("Date:2028年3月44日", "Date", "2028年3月44日"),
    ("URL:https://example.invalid/2028:17", "URL", "https://example.invalid/2028:17"),
])
def test_ordinary_field_values_survive_the_public_reader_without_an_invented_period(text, label, value):
    graph = compile_markdown(text, sample_id="invented-ordinary-field")
    [field] = graph["business"]
    assert (field["attribute"], field["value"], field["qualifiers"]) == (label, value, {})
    assert graph["blockers"] == []


def test_a_numeric_superscript_remains_unknown_source_content_without_a_declared_footnote_binding():
    text = "Revenue:2028年17⁴万元；2027年11万元"
    original = deepcopy(SOURCE)
    result = read_series_requirements(text, SOURCE)
    assert SOURCE == original
    assert [(f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("11", {"period": "2027年", "unit": "万元"})]
    [pending] = result["pending_requirements"]
    assert pending["text"] == "17⁴万元"
    assert pending["source"]["text_span"] == [53, 58]
    assert pending["reason"] == "series_scalar_syntax_unsupported"
    assert not any(f["value"] in {"17", "174"} for f in result["facts"])
    assert any(atom["text"] == "17⁴万元" for atom in result["text_atoms"])


@pytest.mark.parametrize("separator", ["年", ":", " "])
def test_an_actual_year_scalar_series_still_uses_its_own_two_complete_positions(separator):
    text = f"Revenue:2028{separator}17万元；2027{separator}11万元"
    result = read_series_requirements(text, SOURCE)
    assert result["matched"] is True and result["blockers"] == []
    assert [(f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("Revenue", "17", {"period": "2028年" if separator == "年" else "2028", "unit": "万元"}),
        ("Revenue", "11", {"period": "2027年" if separator == "年" else "2027", "unit": "万元"})]


def test_explicit_four_column_schema_still_proves_its_own_row_roles():
    declaration = "列说明：2028年金額（万元）、佔總收入比（%）；2027年金額（万元）、佔總收入比（%）。"
    schema = read_compact_schema(declaration, {"path": "<own-printed-schema>", "lines": [3, 3]})["schema"]
    result = read_compact_requirements("Delta：2028年17、60%；2027年11、55%", SOURCE, schema=schema)
    assert result["matched"] is True and result["blockers"] == []
    assert [(f["subject"], f["attribute"], f["value"], f["qualifiers"]) for f in result["facts"]] == [
        ("Delta", "金額", "17", {"period": "2028年", "unit": "万元"}),
        ("Delta", "佔總收入比", "60", {"period": "2028年", "unit": "%"}),
        ("Delta", "金額", "11", {"period": "2027年", "unit": "万元"}),
        ("Delta", "佔總收入比", "55", {"period": "2027年", "unit": "%"})]
