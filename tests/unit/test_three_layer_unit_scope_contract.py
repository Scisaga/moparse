"""Printed unit declarations must bind with sources or remain explicit pending."""

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.series_requirements import read_series_requirements
from moparse_eval.three_layer import compile_markdown, read_candidate


def graphs(markdown):
    yield compile_markdown(markdown, sample_id="invented-unit-scope")
    yield read_candidate(markdown_observation(markdown, sample_id="invented-unit-scope", pipeline="P07", pages=[1]))


def literal_source(fact, key):
    return fact.get("qualifier_sources", {}).get(key) or fact.get("qualifier_provenance", {}).get(key, {}).get("source", {})


def assert_no_active_money_provenance(fact):
    for key in ("unit", "currency"):
        proof = fact.get("qualifier_provenance", {}).get(key)
        if proof:
            # An explicitly rejected declaration remains useful audit evidence;
            # an unmarked money provenance still claims a Count binding.
            assert proof.get("application") == "shared_amount_role_does_not_qualify_this_non_amount_field"


@pytest.mark.parametrize("declaration,unit,currency,body,attribute", [
    ("Unit: CNY million.", "CNY million", "CNY", "- Revenue\n  - 2028年：17\n  - 2027年：11", "Revenue"),
    ("单位：人民币百万元。", "人民币百万元", "人民币", "- Revenue\n  - Subtotal：2028年17；2027年11", "Subtotal"),
])
def test_parent_label_cannot_silently_erase_a_printed_unit_declaration(
        declaration, unit, currency, body, attribute):
    markdown = "# Results\n\n" + declaration + "\n\n" + body
    for graph in graphs(markdown):
        assert [(fact["attribute"], fact["value"], fact["qualifiers"].get("period")) for fact in graph["business"]] == [
            (attribute, "17", "2028年"), (attribute, "11", "2027年")]
        assert all(fact["qualifiers"].get("unit") not in {"CNY million.", "人民币百万元。"} for fact in graph["business"])
        original = [item for item in graph["text_projection"]["source_fragments"] if item["text"] == declaration]
        assert len(original) == 1 and original[0]["source"]["lines"] == [3, 3]
        unit_start = declaration.index(unit)
        expected_spans = {"unit": [unit_start, unit_start + len(unit)],
                          "currency": [unit_start, unit_start + len(currency)]}
        bound = len(graph["business"]) == 2 and all(
            fact["qualifiers"].get("unit") == unit and fact["qualifiers"].get("currency") == currency
            and all(literal_source(fact, key).get("lines") == [3, 3]
                    and literal_source(fact, key).get("text_span") == span for key, span in expected_spans.items())
            for fact in graph["business"])
        if not bound:
            pending = [item for item in graph.get("pending_requirements", [])
                       if item.get("source", {}).get("lines") == [3, 3]
                       and "unit" in (item.get("kind", "") + item.get("reason", "")).lower()]
            assert pending, "The original Unit scope must remain pending; a leaf group blocker is insufficient"
            assert any(item.get("text") == declaration and item.get("unit") == unit
                       and item.get("currency") == currency for item in pending)
            blockers = [item for item in graph["blockers"] if item.get("source", {}).get("lines") == [3, 3]
                        and "unit" in (item.get("kind", "") + item.get("reason", "")).lower()]
            assert blockers and set().union(*(set(item.get("layers", [])) for item in blockers)) >= {"B", "L"}


def test_shared_amount_unit_does_not_become_the_name_or_count_currency():
    markdown = "# Results\n\nUnit:CNY million\n\nRevenue:17\n\nCount:5\n\nName:Delta"
    for graph in graphs(markdown):
        assert graph["blockers"] == []
        by_attribute = {fact["attribute"]: fact for fact in graph["business"]}
        assert set(by_attribute) == {"Revenue", "Count", "Name"}
        assert by_attribute["Revenue"]["qualifiers"] == {"unit": "CNY million", "currency": "CNY"}
        assert by_attribute["Count"]["qualifiers"] == by_attribute["Name"]["qualifiers"] == {}


def test_explicit_record_tail_unit_and_separate_heading_units_keep_their_supported_bindings():
    for graph in graphs("- Name:Delta\n  - Revenue:17\n  - Unit:CNY million"):
        assert graph["blockers"] == []
        [name, revenue] = graph["business"]
        assert (name["attribute"], name["value"], name["qualifiers"]) == ("Name", "Delta", {})
        assert (revenue["attribute"], revenue["value"], revenue["qualifiers"]) == (
            "Revenue", "17", {"unit": "CNY million", "currency": "CNY"})
        assert revenue["qualifier_provenance"]["unit"]["level"] == "record_explicit"
    markdown = "# North\n\nUnit:CNY million\n\nRevenue:17\n\n# South\n\nUnit:USD million\n\nRevenue:5"
    for graph in graphs(markdown):
        assert graph["blockers"] == []
        assert [(fact["scope"], fact["value"], fact["qualifiers"]) for fact in graph["business"]] == [
            (["North"], "17", {"unit": "CNY million", "currency": "CNY"}),
            (["South"], "5", {"unit": "USD million", "currency": "USD"})]
        assert [literal_source(fact, "unit")["lines"] for fact in graph["business"]] == [[3, 3], [9, 9]]


@pytest.mark.parametrize("markdown,unit_line", [
    ("Unit: CNY million.\n\nName: Delta; Revenue: 17; Count: 5", 1),
    ("Name: Delta; Unit: CNY million.; Revenue: 17; Count: 5", 1),
    ("Name: Delta; Revenue: 17; Count: 5; Unit: CNY million.", 1),
], ids=["caption", "same-record-before", "same-record-after"])
def test_amount_unit_position_keeps_the_same_three_roles_and_never_makes_count_money(markdown, unit_line):
    raw_line = markdown.splitlines()[unit_line - 1]
    unit_start = raw_line.index("CNY million")
    for graph in graphs(markdown):
        assert graph["blockers"] == [] and graph.get("pending_requirements", []) == []
        assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
            ("Name", "Delta", "identity"), ("Revenue", "17", "metric"), ("Count", "5", "metric")]
        name, revenue, count = graph["business"]
        assert name["qualifiers"] == count["qualifiers"] == {}
        assert revenue["qualifiers"] == {"unit": "CNY million", "currency": "CNY"}
        assert literal_source(revenue, "unit")["lines"] == [unit_line, unit_line]
        assert literal_source(revenue, "unit")["text_span"] == [unit_start, unit_start + 11]
        assert literal_source(revenue, "currency")["text_span"] == [unit_start, unit_start + 3]
        assert_no_active_money_provenance(count)
        assert not [edge for edge in graph["relations"] if edge["type"] == "qualifier_scope"
                    and edge["right"].get("attribute") == "Count" and edge["left"].get("type") in {"unit", "currency"}]
        for edge in graph["relations"]:
            if isinstance(edge.get("right"), dict) and edge["right"].get("attribute") == "Count":
                assert edge["right"].get("qualifiers", {}) == {}


@pytest.mark.parametrize("table", [False, True], ids=["record-list", "property-table"])
def test_supported_record_serializations_do_not_bind_shared_money_to_count(table):
    markdown = ("| Property | Value |\n|---|---|\n| Name | Delta |\n| Revenue | 17 |\n"
                "| Count | 5 |\n| Unit | CNY million |") if table else (
                "- Name: Delta\n  - Revenue:17\n  - Count:5\n  - Unit:CNY million.")
    for graph in graphs(markdown):
        assert graph["blockers"] == []
        assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
            ("Name", "Delta", "identity"), ("Revenue", "17", "metric"), ("Count", "5", "metric")]
        name, revenue, count = graph["business"]
        assert name["qualifiers"] == count["qualifiers"] == {}
        assert revenue["qualifiers"] == {"unit": "CNY million", "currency": "CNY"}
        assert_no_active_money_provenance(count)
        for edge in graph["relations"]:
            if isinstance(edge.get("right"), dict) and edge["right"].get("attribute") == "Count":
                assert edge["right"].get("qualifiers", {}) == {}
        if table:
            [proof] = revenue["qualifier_provenance"]["unit"]["sources"]
            assert proof["text"] == "CNY million"
            assert proof["source"]["cell"] == "markdown:L1/gfm/rows/4/cells/1"
        else:
            assert literal_source(revenue, "unit")["lines"] == [4, 4]
            assert literal_source(revenue, "unit")["text_span"] == [5, 16]


@pytest.mark.parametrize("unit", ["人", "万元"])
def test_a_count_value_own_unit_is_retained_even_when_its_literal_unit_is_unusual(unit):
    markdown = "Name: Delta; Revenue: 17; Count: 5" + unit + "; Unit: CNY million."
    for graph in graphs(markdown):
        assert graph["blockers"] == []
        assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
            ("Name", "Delta", "identity"), ("Revenue", "17", "metric"), ("Count", "5", "metric")]
        [count] = [fact for fact in graph["business"] if fact["attribute"] == "Count"]
        assert count["qualifiers"] == {"unit": unit}
        proof = count["qualifier_provenance"]["unit"]
        assert proof["level"] == "field_inline" and proof["text"] == unit
        assert proof["source"]["text_span"] == [markdown.index(unit), markdown.index(unit) + len(unit)]


@pytest.mark.parametrize("unit", ["人", "万元"])
def test_a_count_header_own_unit_is_not_replaced_by_the_record_amount_declaration(unit):
    header = "Count(" + unit + ")"
    markdown = "| Name | Revenue | " + header + " | Unit |\n|---|---|---|---|\n| Delta | 17 | 5 | CNY million |"
    for graph in graphs(markdown):
        assert graph["blockers"] == []
        assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
            ("Name", "Delta", "identity"), ("Revenue", "17", "metric"), ("Count", "5", "metric")]
        [count] = [fact for fact in graph["business"] if fact["attribute"] == "Count"]
        # These headers print only the unit. The unrelated shared CNY money
        # declaration must not add Count currency, matching the inline case.
        assert count["qualifiers"] == {"unit": unit}
        proof = count["qualifier_provenance"]["unit"]
        assert proof["text"] == unit
        sources = proof.get("sources", [])
        assert sources and any(source["text"] == header
                               and source["source"].get("cell") == "markdown:L1/gfm/rows/0/cells/2" for source in sources)


def test_revenue_own_inline_money_unit_cannot_be_inherited_by_the_neighboring_count():
    markdown = "Name: Delta; Revenue: 17CNY million; Count: 5"
    for graph in graphs(markdown):
        assert graph["blockers"] == []
        assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
            ("Name", "Delta", "identity"), ("Revenue", "17", "metric"), ("Count", "5", "metric")]
        name, revenue, count = graph["business"]
        assert name["qualifiers"] == count["qualifiers"] == {}
        assert revenue["qualifiers"] == {"unit": "CNY million", "currency": "CNY"}
        assert revenue["qualifier_provenance"]["unit"]["level"] == "field_inline"


@pytest.mark.parametrize("key", ["Unit", "Units", "单位"])
def test_supported_shared_unit_key_spellings_keep_the_same_count_role_policy(key):
    markdown = "Name: Delta; Revenue: 17; Count: 5; " + key + ": CNY million."
    for graph in graphs(markdown):
        assert graph["blockers"] == []
        assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
            ("Name", "Delta", "identity"), ("Revenue", "17", "metric"), ("Count", "5", "metric")]
        name, revenue, count = graph["business"]
        assert name["qualifiers"] == count["qualifiers"] == {}
        assert revenue["qualifiers"] == {"unit": "CNY million", "currency": "CNY"}


def test_caption_amount_unit_cannot_silently_turn_supported_annual_counts_into_money():
    markdown = "Unit:CNY million.\n\nRevenue:17\n\nCount:2028年5；2027年4"
    for graph in graphs(markdown):
        assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
            ("Revenue", "17", "metric"), ("Count", "5", "metric"), ("Count", "4", "metric")]
        revenue, *counts = graph["business"]
        assert revenue["qualifiers"] == {"unit": "CNY million", "currency": "CNY"}
        assert [fact["qualifiers"].get("period") for fact in counts] == ["2028年", "2027年"]
        filtered = [fact["qualifiers"] for fact in counts] == [{"period": "2028年"}, {"period": "2027年"}]
        if filtered:
            for count in counts:
                assert_no_active_money_provenance(count)
            for edge in graph["relations"]:
                if isinstance(edge.get("right"), dict) and edge["right"].get("attribute") == "Count":
                    assert not ({"unit", "currency"} & edge["right"].get("qualifiers", {}).keys())
        else:
            pending = [item for item in graph.get("pending_requirements", [])
                       if item.get("source", {}).get("lines") == [1, 1]
                       and "unit" in (item.get("kind", "") + item.get("reason", "")).lower()]
            assert pending, "Inherited caption money on Count needs an explicit original-Unit scope blocker"
            blockers = [item for item in graph["blockers"] if item.get("source", {}).get("lines") == [1, 1]
                        and "unit" in (item.get("kind", "") + item.get("reason", "")).lower()]
            assert blockers and set().union(*(set(item.get("layers", [])) for item in blockers)) >= {"B", "L"}


@pytest.mark.parametrize("unit", ["人", "万元"])
@pytest.mark.parametrize("placement", ["header", "inline"])
def test_annual_count_own_header_or_inline_unit_is_not_filtered_as_caption_money(unit, placement):
    row = "Count(" + unit + "):2028年5；2027年4" if placement == "header" else (
        "Count:2028年5" + unit + "；2027年4" + unit)
    for graph in graphs("Unit:CNY million.\n\nRevenue:17\n\n" + row):
        assert graph["blockers"] == []
        assert [(fact["attribute"], fact["value"], fact["qualifiers"]) for fact in graph["business"]] == [
            ("Revenue", "17", {"unit": "CNY million", "currency": "CNY"}),
            ("Count", "5", {"unit": unit, "period": "2028年"}),
            ("Count", "4", {"unit": unit, "period": "2027年"})]


def test_series_callers_explicit_own_qualifier_is_not_reinterpreted_as_shared_caption_money():
    for unit in ("人", "万元"):
        own_source = {"path": "<explicit-count-header>", "lines": [3, 3], "text_span": [6, 6 + len(unit)]}
        result = read_series_requirements("Count:2028年5；2027年4", {"path": "<count-values>", "lines": [4, 4]},
                                          qualifiers={"unit": unit}, qualifier_sources={"unit": own_source})
        assert result["blockers"] == []
        assert [(fact["attribute"], fact["value"], fact["qualifiers"]) for fact in result["facts"]] == [
            ("Count", "5", {"unit": unit, "period": "2028年"}),
            ("Count", "4", {"unit": unit, "period": "2027年"})]
        assert [fact["source"]["qualifier_sources"]["unit"] for fact in result["facts"]] == [own_source, own_source]


@pytest.mark.parametrize("unit", ["人", "万元"])
def test_property_table_count_own_label_unit_and_its_source_override_shared_money(unit):
    header = "Count(" + unit + ")"
    markdown = ("| Property | Value |\n|---|---|\n| Name | Delta |\n| Revenue | 17 |\n| "
                + header + " | 5 |\n| Unit | CNY million |")
    for graph in graphs(markdown):
        assert graph["blockers"] == [] and graph.get("pending_requirements", []) == []
        assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
            ("Name", "Delta", "identity"), ("Revenue", "17", "metric"), ("Count", "5", "metric")]
        name, revenue, count = graph["business"]
        assert name["qualifiers"] == {}
        assert revenue["qualifiers"] == {"unit": "CNY million", "currency": "CNY"}
        assert count["qualifiers"] == {"unit": unit}
        proof = count["qualifier_provenance"]["unit"]
        assert proof["text"] == unit
        sources = proof.get("sources", [])
        assert sources and any(source["text"] == header
                               and source["source"].get("cell") == "markdown:L1/gfm/rows/3/cells/0"
                               for source in sources)
