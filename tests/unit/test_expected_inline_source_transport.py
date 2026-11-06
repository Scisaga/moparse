"""Independent literal and role oracles for expected inline source transport."""

from copy import deepcopy

import pytest

from moparse_eval.authorized_source_inventory import plan_authorized_source_inventory
from moparse_eval.expected_readback import elements, inline_text, read_expected
from moparse_eval.packaging import write_json


@pytest.mark.parametrize("raw,wanted", [
    ("1. Introduction", "1. Introduction"),
    ("01. 引领商业成功", "01. 引领商业成功"),
    ("**1. Revenue**", "1. Revenue"),
    ("`1. value`", "1. value"),
    ("Name: 1. Delta; Revenue: 17", "Name: 1. Delta; Revenue: 17"),
    ("**Metric:**2027", "**Metric:**2027"),
    ("A < B; C > D; $$x+1$$", "A < B; C > D; $$x+1$$"),
    ("委托签字：________", "委托签字：________"),
])
def test_inline_payload_is_never_reparsed_as_an_independent_document(raw, wanted):
    assert inline_text(raw) == wanted


def test_numbered_heading_and_gfm_field_values_keep_literal_numbering():
    raw = "### 1. Introduction\n\n| Attribute | Value |\n|---|---|\n| Clause | 1. Dividend approval |\n"
    heading, table = elements(raw)
    assert heading.text == "1. Introduction" and heading.native_heading_level == 3
    assert [cell["text"] for cell in table.cells] == ["Attribute", "Value", "Clause", "1. Dividend approval"]
    assert heading.raw == "### 1. Introduction\n"


def test_soft_and_hard_breaks_retain_their_actual_inline_text():
    [part] = elements("Director\\\n*Chair*\\\n2027\n")
    assert part.text == "Director\nChair\n2027"
    [last] = elements("Literal final backslash\\\n")
    assert last.text == "Literal final backslash\\"


def test_reference_destinations_and_captions_are_exposed_as_syntax_fields_without_asset_reads():
    [part] = elements("![Own **caption**](assets/first.png \"Printed title\") and [Policy](policy.md)\n")
    assert part.text == "Own caption and Policy"
    assert part.inline_references == [
        {"kind": "image", "destination": "assets/first.png", "text": "Own caption", "title": "Printed title"},
        {"kind": "link", "destination": "policy.md", "text": "Policy", "title": None},
    ]


def test_expected_source_spans_retain_numbered_headings_and_inline_reference_metadata(tmp_path):
    document = tmp_path / "invented"
    document.mkdir()
    raw = "## 1. Introduction\n\n![Caption](assets/a.png)\n"
    path = document / "expected.md"
    path.write_text(raw)
    write_json(document / "manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {
        "entries": [{"source_pages": [1], "markdown_lines": [1, 3]}]}})
    expected = read_expected({"id": "fixture", "document_id": "invented", "source_pages": [1]}, tmp_path)
    heading, image = expected["targets"]
    assert heading["raw_text"] == "1. Introduction"
    assert heading["reference"] == {"path": str(path), "lines": [1, 1]}
    assert image["inline_references"] == [{"kind": "image", "destination": "assets/a.png", "text": "Caption", "title": None}]
    inventory = plan_authorized_source_inventory(expected["authorized_raw_segments"], expected["targets"])
    assert inventory["source_complete"] is True
    changed = deepcopy(expected["targets"])
    changed[0]["raw_text"] = changed[0]["text"] = "Introduction"
    assert plan_authorized_source_inventory(expected["authorized_raw_segments"], changed)["source_complete"] is False
    assert path.read_text() == raw
