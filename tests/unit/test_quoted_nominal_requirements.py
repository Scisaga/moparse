"""Invented quoted-role semantics, with literal source spans as the oracle."""

from copy import deepcopy

import pytest

from moparse_eval.narrative_requirements import read_narrative


def read(text, *, offset=0):
    return read_narrative(text, {"path": "<quoted-nominal>", "lines": [7, 7],
                                 "text_span": [offset, offset + len(text)]})


@pytest.mark.parametrize("opening,closing", [('"', '"'), ('“', '”'), ('‘', '’')])
def test_one_printed_quoted_name_is_one_object_even_when_it_contains_and(opening, closing):
    label = opening + "Kappa and Sigma" + closing
    text = "Lumen owns " + label + "."
    result = read(text, offset=40)
    assert result["complete"] is True
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "own", label)
    assert fact["value_source"]["text_span"] == [51, 68]
    [quote] = fact["quoted_nominals"]
    assert (quote["role"], quote["text"], quote["content"]) == ("object", label, "Kappa and Sigma")
    assert quote["source"]["text_span"] == [51, 68]
    assert quote["content_source"]["text_span"] == [52, 67]
    assert quote["opening_source"]["text_span"] == [51, 52]
    assert quote["closing_source"]["text_span"] == [67, 68]
    assert "quoted_nominal_scope" in result["required_matcher_features"]
    assert "coordination" not in fact["qualifiers"]
    assert result["text_atoms"][0]["text"] == text


def test_internal_numbers_and_negation_stay_in_the_name_while_outer_not_stays_an_operator():
    text = 'Lumen does not own "Kappa 17 and not Sigma 18".'
    result = read(text)
    assert result["complete"] is True
    [fact] = result["facts"]
    assert fact["value"] == '"Kappa 17 and not Sigma 18"'
    assert fact["qualifiers"]["polarity"] == "negative"
    assert fact["qualifier_sources"]["polarity"]["text_span"] == [11, 14]
    assert len(result["logic"]) == 1
    assert not result["semantic_operands"]


def test_only_the_printed_outer_and_creates_two_objects():
    result = read('Lumen owns "Kappa and Sigma" and "Omega".')
    assert result["complete"] is True
    assert [fact["value"] for fact in result["facts"]] == ['"Kappa and Sigma"', '"Omega"']
    assert all(fact["subject"] == "Lumen" for fact in result["facts"])
    assert result["logic"][0]["operator_spans"] == [[28, 33]]


def test_an_outer_or_keeps_two_alternative_operands_without_using_the_whole_group_as_a_nominal():
    result = read('Lumen owns "Kappa and Sigma" or "Omega".')
    assert result["complete"] is True
    assert len(result["facts"]) == 1 and result["facts"][0]["role"] == "logical_group"
    assert [fact["value"] for fact in result["semantic_operands"]] == ['"Kappa and Sigma"', '"Omega"']
    assert all(len(fact["quoted_nominals"]) == 1 for fact in result["semantic_operands"])


def test_a_quoted_nominal_that_used_to_be_unsupported_is_one_printed_membership_object():
    result = read('Lumen includes "Research and Development".')
    assert result["complete"] is True
    assert [(f["subject"], f["attribute"], f["value"]) for f in result["facts"]] == [
        ("Lumen", "include", '"Research and Development"')]


def test_quoted_actor_is_not_recast_as_two_actors_or_an_object():
    result = read('"Kappa and Sigma" owns Omega.')
    [fact] = result["facts"]
    assert result["complete"] is True
    assert (fact["subject"], fact["attribute"], fact["value"]) == ('"Kappa and Sigma"', "own", "Omega")
    assert fact["subject_source"]["text_span"] == [0, 17]
    assert [item["role"] for item in fact["quoted_nominals"]] == ["subject"]


def test_quoted_modifier_has_own_scope_but_an_external_prepositional_tail_is_not_swallowed():
    text = 'Lumen uses a “user first, AI-driven” strategy.'
    result = read(text)
    assert result["complete"] is True
    [fact] = result["facts"]
    assert fact["value"] == 'a “user first, AI-driven” strategy'
    [quote] = fact["quoted_nominals"]
    assert quote["content"] == "user first, AI-driven"
    assert quote["attachment"] == "nominal_modifier"
    unknown = read(text[:-1] + " for growth.")
    assert unknown["facts"] == []
    assert unknown["complete"] is False
    assert unknown["pending_requirements"][0]["quoted_scopes"][0]["content"] == "user first, AI-driven"
    assert set(unknown["pending_requirements"][0]["layers"]) == {"B", "L"}


@pytest.mark.parametrize("text", [
    'Lumen owns "Kappa owns Sigma".',
    'Lumen owns "Kappa is not solvent".',
    'Lumen reported that "Kappa owns Sigma".',
    'Lumen owns "Kappa dances nightly".',
    'Lumen owns “Kappa and ‘Sigma’”.',
    'Lumen owns "Kappa and Sigma.',
])
def test_quoted_propositions_unknown_forms_and_bad_boundaries_retain_the_whole_requirement(text):
    result = read(text)
    assert result["facts"] == []
    assert result["complete"] is False
    [pending] = result["pending_requirements"]
    assert pending["text"] == text
    assert pending["source"]["text_span"] == [0, len(text)]
    assert set(pending["layers"]) == {"B", "L"}
    assert "quoted_nominal_scope" in result["required_matcher_features"]
    assert result["text_atoms"][0]["text"] == text


def test_possessive_apostrophe_and_ordinary_coordination_keep_their_existing_meaning():
    source = {"path": "<unchanged>", "lines": [1, 1]}
    before = deepcopy(source)
    result = read_narrative("Lumen's division owns Kappa and Sigma.", source)
    assert source == before
    assert result["complete"] is True
    assert [fact["value"] for fact in result["facts"]] == ["Kappa", "Sigma"]
    assert "quoted_nominal_scope" not in result["required_matcher_features"]


@pytest.mark.parametrize("content", [
    "The Board Prohibits Exports", "the board prohibits exports", "THE BOARD PROHIBITS EXPORTS",
    "Kappa Glorps Sigma", "kappa glorps sigma", "The Supplier Glorps", "Kappa Dances",
    "and", "not", "17", "Kappa and", "and Sigma",
])
def test_title_case_and_known_neighboring_nouns_do_not_justify_an_unknown_predicate(content):
    text = f'Lumen owns "{content}".'
    result = read(text, offset=70)
    assert result["facts"] == [] and result["complete"] is False
    [pending] = result["pending_requirements"]
    assert pending["text"] == text
    assert pending["source"]["text_span"] == [70, 70 + len(text)]
    assert set(pending["layers"]) == {"B", "L"}


@pytest.mark.parametrize("content", ["kappa", "Kappa", "KAPPA", "Kappa 17 and not Sigma 18"])
def test_explicit_single_name_atoms_do_not_depend_on_capitalization(content):
    text = f'Lumen owns "{content}".'
    result = read(text)
    assert result["complete"] is True
    [fact] = result["facts"]
    assert fact["value"] == f'"{content}"'
    [quote] = fact["quoted_nominals"]
    assert quote["content"] == content
    assert quote["content_source"]["text_span"] == [12, 12 + len(content)]


def test_quoted_actor_inner_or_and_outer_negative_alternatives_keep_distinct_roles():
    text = '"Kappa and Sigma" does not own "Omega or Vega" or "Tau".'
    result = read(text)
    assert result["complete"] is True
    assert len(result["facts"]) == 1
    assert [item["subject"] for item in result["semantic_operands"]] == ['"Kappa and Sigma"'] * 2
    assert [item["value"] for item in result["semantic_operands"]] == ['"Omega or Vega"', '"Tau"']
    assert all(item["qualifiers"]["polarity"] == "negative" for item in result["semantic_operands"])
    assert [[quote["role"] for quote in item["quoted_nominals"]]
            for item in result["semantic_operands"]] == [["subject", "object"], ["subject", "object"]]
