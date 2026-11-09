"""Independently authored semantic oracles for the three-layer measurement.

The literal answers, roles and required counts below were fixed before the
compiler implementation. No expected result is obtained from its own output.
These are software probes over invented text, not corpus review or grades.
"""

from copy import deepcopy

import pytest

from moparse_eval.three_layer import (
    compile_expected,
    compile_markdown,
    grade_layers,
    read_candidate,
    read_candidate_markdown,
)

SERIALIZATIONS = {
    "flat": "- Name: Delta\n- Revenue: 17\n- Profit: 5\n",
    "nested": "- Name: Delta\n  - Revenue: 17\n  - Profit: 5\n",
    "paragraph": "Name: Delta; Revenue: 17; Profit: 5\n",
    "horizontal": "| Name | Revenue | Profit |\n|---|---|---|\n| Delta | 17 | 5 |\n",
    "vertical": "| Attribute | Value |\n|---|---|\n| Name | Delta |\n| Revenue | 17 |\n| Profit | 5 |\n",
}


def score(reference, candidate):
    requirements = compile_markdown(reference)
    graph = read_candidate_markdown(candidate)
    return requirements, grade_layers(requirements, graph)


def layer_outcomes(result, layer):
    return [row for row in result["outcomes"] if row["layer"] == layer]


def business_projection(requirements):
    # The projection is deliberately small: a representation must not change
    # which information is independently required, or its business role.
    return sorted((item["attribute"], item["value"], item["role"])
                  for item in requirements["business"])


@pytest.mark.parametrize("reference", SERIALIZATIONS.values(), ids=SERIALIZATIONS)
def test_business_target_roles_counts_and_sources_are_representation_invariant(reference):
    compiled = compile_markdown(reference)
    assert business_projection(compiled) == [
        ("Name", "Delta", "identity"),
        ("Profit", "5", "metric"),
        ("Revenue", "17", "metric"),
    ]
    assert len(compiled["business"]) == 3
    for item in compiled["business"]:
        assert item["source"], item
        assert item["qualifiers"] == {}, item


@pytest.mark.parametrize("reference", SERIALIZATIONS.values(), ids=SERIALIZATIONS)
@pytest.mark.parametrize("candidate", SERIALIZATIONS.values(), ids=SERIALIZATIONS)
def test_business_equivalence_in_both_directions(reference, candidate):
    _, result = score(reference, candidate)
    rows = layer_outcomes(result, "B")
    assert len(rows) == 3
    assert [row["outcome"] for row in rows].count("correct") == 3
    assert result["layers"]["B"]["denominator"] == 3
    assert result["layers"]["B"]["score"] == 100


@pytest.mark.parametrize("reference", SERIALIZATIONS.values(), ids=SERIALIZATIONS)
def test_fixed_profit_error_changes_one_business_item_under_every_reference(reference):
    _, result = score(reference, "Name: Delta; Revenue: 17; Profit: 6\n")
    rows = layer_outcomes(result, "B")
    assert len(rows) == 3
    assert [row["outcome"] for row in rows].count("incorrect") == 1
    assert result["layers"]["B"]["numerator"] == 2
    assert result["layers"]["B"]["denominator"] == 3


@pytest.mark.parametrize("reference", ["- Revenue: 17; Profit: 5\n", "- Revenue: 17\n- Profit: 5\n"])
@pytest.mark.parametrize("candidate", ["Revenue: 17; Profit: 5\n", "- Revenue: 17\n- Profit: 5\n"])
def test_two_independent_metrics_never_become_parent_and_child(reference, candidate):
    requirements, result = score(reference, candidate)
    assert business_projection(requirements) == [("Profit", "5", "metric"), ("Revenue", "17", "metric")]
    assert len(layer_outcomes(result, "B")) == 2
    assert result["layers"]["B"]["score"] == 100


UNITS = [
    "Unit: 万元\n\n- Revenue: 17\n",
    "| Revenue (万元) |\n|---|\n| 17 |\n",
    "Revenue: 17; Unit: 万元\n",
    "- Revenue: 17万元\n",
]


@pytest.mark.parametrize("reference", UNITS)
def test_unit_placement_is_a_qualifier_and_never_a_second_business_requirement(reference):
    compiled = compile_markdown(reference)
    assert len(compiled["business"]) == 1
    item = compiled["business"][0]
    assert item["attribute"] == "Revenue"
    assert item["value"] == "17"
    assert item["role"] == "metric"
    assert item["qualifiers"]["unit"] == "万元"
    assert item["source"]


@pytest.mark.parametrize("reference", UNITS)
@pytest.mark.parametrize("candidate", UNITS)
def test_equivalent_unit_scope_is_read_from_the_candidates_own_expression(reference, candidate):
    _, result = score(reference, candidate)
    assert len(layer_outcomes(result, "B")) == 1
    assert result["layers"]["B"]["score"] == 100


@pytest.mark.parametrize("wanted,answer", [("Ready", "incorrect"), ("Blocked", "correct")])
def test_another_column_header_is_not_a_value(wanted, answer):
    requirements, result = score(
        f"- Status: {wanted}\n",
        "| Status | Ready |\n|---|---|\n| Blocked | No |\n",
    )
    assert len(requirements["business"]) == 1
    rows = layer_outcomes(result, "B")
    assert len(rows) == 1
    assert len(rows[0]["actual"]) == 1
    assert rows[0]["actual"][0]["value"] == "Blocked"
    assert rows[0]["outcome"] == answer
    assert rows[0]["retrieval"]


def test_a_value_edit_has_text_and_business_effects_without_erasing_relations():
    reference = "## Results\n\nName: Delta; Revenue: 17; Profit: 5\n"
    _, result = score(reference, reference.replace("17", "18"))
    assert result["layers"]["T"]["score"] < 100
    assert result["layers"]["L"]["denominator"] > 0
    assert result["layers"]["L"]["score"] == 100
    assert result["layers"]["B"]["numerator"] == 2
    assert result["layers"]["B"]["denominator"] == 3


@pytest.mark.parametrize("before,after", [
    ("17", "-17"), ("2027", "2026"), ("万元", "千元"),
    ("USD", "EUR"), ("No dividend", "A dividend"),
    ("unless approved", "when approved"), ("at least 4", "at most 4"),
])
def test_sign_period_unit_currency_negation_exception_and_condition_remain_observable(before, after):
    reference = ("Period: 2027\n\nCurrency: USD\n\nUnit: 万元\n\n"
                 "Name: Delta; Revenue: 17\n\n"
                 "No dividend shall be paid unless approved by at least 4 directors.\n")
    _, result = score(reference, reference.replace(before, after))
    rows = layer_outcomes(result, "B")
    assert len(rows) >= 3
    assert any(row["outcome"] == "incorrect" for row in rows)
    assert result["layers"]["T"]["score"] < 100


def test_internal_number_whitespace_cannot_be_discarded():
    _, result = score("- Code: 12\n", "- Code: 1 2\n")
    assert result["layers"]["T"]["score"] < 100
    assert result["layers"]["B"]["score"] < 100


@pytest.mark.parametrize("candidate", [
    "Only approve may Alice this request.",
    "Only Alice may approvethis request.",
    "Only Alice may not approve this request.",
])
def test_word_bags_arbitrary_concatenation_and_negation_are_not_text_equivalence(candidate):
    _, result = score("Only Alice may approve this request.\n", candidate + "\n")
    assert result["layers"]["T"]["score"] < 100


def test_text_keeps_name_numbers_table_labels_and_values_in_the_same_scope():
    reference = SERIALIZATIONS["horizontal"]
    changed = reference.replace("Delta", "Delto").replace("17", "18").replace("Profit", "Profet")
    _, result = score(reference, changed)
    assert result["layers"]["T"]["denominator"] > 0
    assert result["layers"]["T"]["score"] < 100
    assert len(layer_outcomes(result, "T")) > 0


def test_a_candidate_occurrence_cannot_pay_for_two_required_occurrences():
    reference = "This obligation remains binding.\n\nThis obligation remains binding.\n"
    _, result = score(reference, "This obligation remains binding.\n")
    assert result["layers"]["T"]["score"] < 100
    assert result["layers"]["T"]["denominator"] > 0


def test_total_uses_three_independent_global_layers_with_equal_weights():
    reference = "## Results\n\nName: Delta; Revenue: 17; Profit: 5\n"
    _, result = score(reference, reference.replace("17", "18"))
    layers = result["layers"]
    assert all(layers[key]["denominator"] > 0 for key in ("T", "L", "B"))
    assert result["score"] == pytest.approx(sum(layers[key]["score"] for key in ("T", "L", "B")) / 3)


def test_a_layer_without_requirements_does_not_receive_zero_or_one_hundred():
    _, result = score("A quiet passage.\n", "A quiet passage.\n")
    assert result["layers"]["B"]["denominator"] == 0
    assert result["layers"]["B"]["score"] is None
    assert result["score"] is None


def test_pipeline_labels_do_not_change_judgments_or_denominators():
    reference = "## Results\n\nName: Delta; Revenue: 17; Profit: 5\n"
    requirements = compile_markdown(reference)
    results = []
    for pipeline in [f"P{i:02}" for i in range(1, 9)]:
        graph = read_candidate_markdown(reference.replace("17", "18"), pipeline=pipeline)
        result = grade_layers(requirements, graph)
        results.append({"layers": result["layers"], "score": result["score"]})
    assert len(results) == 8
    assert results[1:] == [results[0]] * 7


def test_candidate_reader_cannot_receive_a_reference_answer_argument():
    with pytest.raises(TypeError):
        read_candidate_markdown("Revenue: 18\n", expected="Revenue: 17\n")
    with pytest.raises(TypeError):
        read_candidate({"sample_id": "synthetic", "pages": []}, expected={"business": []})


def test_reference_requirements_are_not_mutated_during_scoring():
    requirements = compile_markdown(SERIALIZATIONS["nested"])
    frozen = deepcopy(requirements)
    grade_layers(requirements, read_candidate_markdown(SERIALIZATIONS["flat"]))
    assert requirements == frozen


def test_selection_cannot_turn_an_unselected_title_or_unit_into_an_answer_requirement():
    compiled = compile_markdown(
        "# Results 2027\n\nUnit: 万元\n\n- Revenue: 17\n",
        selected_lines=[(5, 5)],
    )
    assert len(compiled["business"]) == 1
    fact = compiled["business"][0]
    assert fact["attribute"] == "Revenue"
    assert fact["value"] == "17"
    assert "unit" not in fact["qualifiers"]
    assert "period" not in fact["qualifiers"]
    assert compiled["blockers"]
    result = grade_layers(compiled, read_candidate_markdown("- Revenue: 17\n"))
    assert result["publishable"] is False
    assert result["score"] is None


def test_existing_selected_expected_entry_point_keeps_the_same_input_boundary(tmp_path):
    from moparse_eval.expected_readback import read_expected
    from moparse_eval.packaging import write_json

    doc = tmp_path / "expected" / "invented"
    doc.mkdir(parents=True)
    (doc / "expected.md").write_text("# Results 2027\n\nUnit: 万元\n\n- Revenue: 17\n")
    write_json(doc / "manifest.json", {
        "markdown": {"path": "expected.md"},
        "source_map": {"entries": [
            {"source_pages": [1], "markdown_lines": [1, 3]},
            {"source_pages": [2], "markdown_lines": [5, 5]},
        ]},
    })
    expected = read_expected({"id": "synthetic", "document_id": "invented", "source_pages": [2]}, doc.parent)
    compiled = compile_expected(expected)
    assert len(compiled["business"]) == 1
    assert "unit" not in compiled["business"][0]["qualifiers"]
    assert "period" not in compiled["business"][0]["qualifiers"]
    assert compiled["blockers"]


def test_conflicting_assertions_cannot_be_resolved_by_choosing_the_expected_value():
    reference = "Name: Delta; Revenue: 17\n"
    candidate = "Name: Delta; Revenue: 17\n\nName: Delta; Revenue: 18\n"
    _, result = score(reference, candidate)
    rows = layer_outcomes(result, "B")
    assert len(rows) == 2
    assert any(row["outcome"] == "incorrect" for row in rows)
    assert result["layers"]["B"]["score"] < 100


def test_record_reordering_does_not_change_business_but_cross_record_value_swaps_do():
    reference = "Name: Delta; Revenue: 17\n\nName: Kappa; Revenue: 29\n"
    reordered = "Name: Kappa; Revenue: 29\n\nName: Delta; Revenue: 17\n"
    _, good = score(reference, reordered)
    assert len(layer_outcomes(good, "B")) == 4
    assert good["layers"]["B"]["score"] == 100
    _, bad = score(reference, "Name: Kappa; Revenue: 17\n\nName: Delta; Revenue: 29\n")
    assert bad["layers"]["B"]["denominator"] == 4
    assert bad["layers"]["B"]["numerator"] == 2


def test_unique_label_still_requires_the_correct_explicit_business_context():
    reference = "## North\n\n- Revenue: 17\n\n## South\n\n- Profit: 5\n"
    candidate = "## North\n\n- Profit: 5\n\n## South\n\n- Revenue: 17\n"
    _, result = score(reference, candidate)
    assert result["layers"]["T"]["score"] == 100
    rows = layer_outcomes(result, "B")
    assert len(rows) == 2
    assert [row["outcome"] for row in rows].count("incorrect") == 2
    for row in rows:
        assert row["retrieval"]


@pytest.mark.parametrize("headers", [
    '<thead><tr><th>Name</th><th>Revenue</th><th>Profit</th></tr></thead>',
    '<tr><th scope="col">Name</th><th scope="col">Revenue</th><th scope="col">Profit</th></tr>',
    '<tr><td role="columnheader">Name</td><td role="columnheader">Revenue</td>'
    '<td role="columnheader">Profit</td></tr>',
])
def test_explicit_html_header_forms_expose_the_same_business_requirements(headers):
    html = '<table>' + headers + '<tbody><tr><td>Delta</td><td>17</td><td>5</td></tr></tbody></table>'
    requirements, result = score(SERIALIZATIONS["paragraph"], html)
    assert business_projection(requirements) == [
        ("Name", "Delta", "identity"), ("Profit", "5", "metric"), ("Revenue", "17", "metric")]
    rows = layer_outcomes(result, "B")
    assert len(rows) == 3
    assert [row["outcome"] for row in rows].count("correct") == 3


def test_changing_only_explicit_header_references_separates_literal_and_relation_scores():
    html = ('<table><tr><th id="revenue" scope="col">Revenue</th>'
            '<th id="profit" scope="col">Profit</th></tr>'
            '<tr><td id="observationA" headers="revenue">17</td>'
            '<td id="observationB" headers="profit">5</td></tr></table>')
    wrong = html.replace('headers="revenue"', 'headers="temporary"').replace(
        'headers="profit"', 'headers="revenue"').replace('headers="temporary"', 'headers="profit"')
    requirements, good = score(html, html)
    bad = grade_layers(requirements, read_candidate_markdown(wrong))
    assert len(requirements["business"]) == 2
    assert good["layers"]["L"]["denominator"] > 0
    assert good["layers"]["L"]["score"] == 100
    assert bad["layers"]["T"]["score"] == 100
    assert bad["layers"]["L"]["score"] < 100
    assert bad["layers"]["B"]["score"] < 100


def test_data_ids_are_not_required_when_logical_field_roles_are_explicit():
    reference = ('<table><tr><th id="revenue" scope="col">Revenue</th>'
                 '<th id="profit" scope="col">Profit</th></tr>'
                 '<tr><td headers="revenue">17</td><td headers="profit">5</td></tr></table>')
    changed = reference.replace('headers="revenue"', 'headers="temporary"').replace(
        'headers="profit"', 'headers="revenue"').replace('headers="temporary"', 'headers="profit"')
    _, unchanged = score(reference, reference)
    assert unchanged["publishable"] is True
    assert unchanged["layers"]["L"]["denominator"] == 2
    assert unchanged["layers"]["B"]["numerator"] == 2
    _, result = score(reference, changed)
    assert result["layers"]["T"]["score"] == 100
    assert result["layers"]["B"]["numerator"] == 0
    # These source values have no independently retained cross-output object
    # ids. We can report the two changed business values, but cannot infer
    # whether their internal cause was recognition or binding. The preceding
    # controlled test retains ids and independently detects a changed link.
    assert result["layers"]["L"]["numerator"] == 2
    assert result["blockers"] == []


@pytest.mark.parametrize("remove", ["all", "one"])
def test_omitted_compiler_business_requirements_block_publication(remove):
    requirements = compile_markdown(SERIALIZATIONS["paragraph"])
    assert len(requirements["business"]) == 3
    damaged = deepcopy(requirements)
    if remove == "all":
        damaged["business"] = []
    else:
        damaged["business"].pop()
    try:
        result = grade_layers(damaged, read_candidate_markdown(SERIALIZATIONS["paragraph"]))
    except ValueError:
        return
    assert result["publishable"] is False
    assert result["score"] is None


@pytest.mark.parametrize("whole,split", [
    ("The board approves the payment.", "The board approves\n\nthe payment."),
    ("The board approved. Payment follows.", "The board approved.\n\nPayment follows."),
    ("董事会批准付款。", "董事会\n\n批准付款。"),
])
@pytest.mark.parametrize("reverse", [False, True])
def test_legal_consecutive_prose_fragments_keep_all_text_in_both_directions(whole, split, reverse):
    reference, candidate = (split, whole) if reverse else (whole, split)
    _, result = score(reference, candidate)
    assert result["layers"]["T"]["score"] == 100
    assert result["layers"]["T"]["D"] == 0
    assert result["layers"]["T"]["S"] == 0
    assert result["layers"]["T"]["I"] == 0


@pytest.mark.parametrize("candidate", [
    "The board approves\n\nnot the payment.",
    "The board appro\n\nves the payment.",
    "The board approves\n\nUnrelated intervening material.\n\nthe payment.",
    "the payment.\n\nThe board approves",
    "The board approves\n\n# Separate section\n\nthe payment.",
])
def test_fragment_reading_never_skips_negation_intervening_content_or_internal_word_boundaries(candidate):
    _, result = score("The board approves the payment.", candidate)
    assert result["layers"]["T"]["score"] < 100


DIRECTORY = "## Contents\n\n- North\n  - Summary: 3\n- South\n  - Summary: 8\n"


@pytest.mark.parametrize("candidate", [
    DIRECTORY,
    "## Contents\n\n- North\n  - Summary: 8\n- South\n  - Summary: 3\n",
    "| Entry | Page |\n|---|---|\n| North / Summary | 3 |\n| South / Summary | 8 |\n",
])
def test_directory_bindings_judge_own_parent_page_slots_without_value_selection(candidate):
    requirements, result = score(DIRECTORY, candidate)
    assert requirements["text"]
    assert result['publishable'], result['blockers']
    assert result['layers']['B']['denominator'] == 2
    assert result['layers']['L']['denominator'] == 4
    if candidate == DIRECTORY:
        assert result['layers']['B']['score'] == result['layers']['L']['score'] == 100
    elif 'North / Summary' in candidate:
        assert result['layers']['B']['numerator'] == result['layers']['L']['numerator'] == 0
    else:
        assert result['layers']['B']['numerator'] == 0
        assert result['layers']['L']['score'] == 100


GROUPED_MATRIX = ("- North\n  - Name: Delta\n    - Revenue: 17\n"
                  "- South\n  - Name: Delta\n    - Revenue: 29\n")


@pytest.mark.parametrize("candidate", [
    GROUPED_MATRIX,
    "- North\n  - Name: Delta\n    - Revenue: 29\n- South\n  - Name: Delta\n    - Revenue: 17\n",
    '<table><tr><th scope="col">Group</th><th scope="col">Name</th><th scope="col">Revenue</th></tr>'
    '<tr><th scope="rowgroup">North</th><td>Delta</td><td>17</td></tr>'
    '<tr><th scope="rowgroup">South</th><td>Delta</td><td>29</td></tr></table>',
])
def test_unsupported_group_record_column_axes_cannot_collapse_to_a_business_value_multiset(candidate):
    requirements, result = score(GROUPED_MATRIX, candidate)
    assert requirements["text"]
    assert result["publishable"] is False
    assert result["score"] is None
    assert result["blockers"]


@pytest.mark.parametrize("declaration", ["Table continued.", "续表"])
def test_unimplemented_expected_continuation_requirement_blocks_publication(declaration):
    reference = ("| Metric | Value |\n|---|---|\n| Revenue | 17 |\n\n" + declaration +
                 "\n\n| Metric | Value |\n|---|---|\n| Profit | 5 |\n")
    _, result = score(reference, reference)
    assert result["publishable"] is False
    assert result["score"] is None
    assert result["blockers"]


@pytest.mark.parametrize("linked", [False, True])
def test_unsupported_native_continuation_does_not_infer_missing_headers_from_adjacency(linked):
    from moparse_eval.adapters import html_cells

    first = '<table><tr><th>Metric</th><th>Value</th></tr><tr><td>Revenue</td><td>17</td></tr></table>'
    second = '<table><tr><td>Profit</td><td>5</td></tr></table>'
    observation = {
        "sample_id": "synthetic", "pipeline": "P06", "status": "success",
        "pages": [
            {"page": 1, "blocks": [{"id": "first", "native_path": "#/pages/0/table", "kind": "table", "cells": html_cells(first)}]},
            {"page": 2, "blocks": [{"id": "second", "native_path": "#/pages/1/table", "kind": "table", "cells": html_cells(second)}]},
        ],
        "relations": ([{"type": "continues", "source": "first", "target": "second",
                         "evidence": "docvortex.continues_prev"}] if linked else []),
    }
    requirements = compile_markdown("- Revenue: 17\n- Profit: 5\n")
    graph = read_candidate(observation)
    assert not any(item["attribute"] == "Profit" and item["value"] == "5" for item in graph["business"])
    result = grade_layers(requirements, graph)
    assert result["publishable"] is False
    assert result["score"] is None
    assert any(item["source"].get("page") == 2 for item in result["blockers"])
