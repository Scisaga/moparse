"""Fixed T spelling/capacity oracles for actual measurement source spans."""

from collections import Counter
from itertools import product

import pytest

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

FORMS = [
    "Revenue:$17",
    "Revenue:17$",
    "Revenue($):17",
    '<table><tr><th scope="col">Revenue</th></tr><tr><td>$17</td></tr></table>',
]


@pytest.mark.parametrize("reference,candidate", list(product(FORMS, repeat=2)))
def test_one_actual_amount_keeps_one_unit_literal_and_one_value_across_prefix_suffix_and_header(reference, candidate):
    required, actual = compile_markdown(reference), read_candidate_markdown(candidate)
    words = Counter({"Revenue": 1, "17": 1, "$": 1})
    assert Counter(atom["text"] for atom in required["text"]) == words
    assert Counter(atom["text"] for atom in actual["text"]) == words
    score = grade_layers(required, actual)
    assert score["blockers"] == []
    assert score["layers"]["T"]["denominator"] == 10 and score["layers"]["T"]["score"] == 100
    assert score["layers"]["B"]["denominator"] == 1 and score["layers"]["B"]["score"] == 100
    assert all("currency" not in fact["qualifiers"] for fact in actual["business"])


def test_a_native_identity_cell_keeps_its_currency_like_letters_as_one_actual_name():
    required = compile_markdown("Name:17美元")
    actual = read_candidate_markdown('<table><tr><th scope="col">Name</th></tr><tr><td>17美元</td></tr></table>')
    assert Counter(atom["text"] for atom in actual["text"]) == Counter({"Name": 1, "17美元": 1})
    assert actual["business"][0]["value"] == "17美元" and actual["business"][0]["qualifiers"] == {}
    score = grade_layers(required, actual)
    assert score["layers"]["T"]["score"] == 100 and score["layers"]["B"]["score"] == 100


@pytest.mark.parametrize("label", ["Revenue(17%)", "Count(17人)"])
def test_a_value_inside_a_metric_label_remains_the_complete_literal_in_both_formats(label):
    required = compile_markdown(f"{label}:5")
    actual = read_candidate_markdown(f'<table><tr><th scope="col">{label}</th></tr><tr><td>5</td></tr></table>')
    assert Counter(atom["text"] for atom in actual["text"]) == Counter({label: 1, "5": 1})
    score = grade_layers(required, actual)
    assert score["layers"]["T"]["score"] == 100 and score["layers"]["B"]["score"] == 100
