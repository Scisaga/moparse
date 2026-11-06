"""Fixed source roles for a bounded fronted nominal adjunct grammar."""

from copy import deepcopy

import pytest

from moparse_eval.narrative_requirements import read_narrative


def read(text, *, offset=0):
    return read_narrative(text, {"path": "<fronted-context>", "lines": [9, 9],
                                 "text_span": [offset, offset + len(text)]})


@pytest.mark.parametrize("offset", [0, 40])
def test_fronted_strategy_with_a_quoted_comma_has_one_sourced_context_not_an_assertion(offset):
    text = 'Under the “user first, AI-driven” strategy, we sharpened our business focus.'
    result = read(text, offset=offset)
    assert result["complete"] is True
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("we", "sharpen", "our business focus")
    assert fact["qualifiers"]["fronted_contexts"] == [{"preposition": "Under", "operator": "under",
        "role": "context", "text": 'the “user first, AI-driven” strategy'}]
    [proof] = fact["qualifier_sources"]["fronted_contexts"]
    assert proof["preposition_source"]["text_span"] == [offset, offset + 5]
    assert proof["context_source"]["text_span"] == [offset + 6, offset + 42]
    assert proof["separator_source"]["text_span"] == [offset + 42, offset + 43]
    assert fact["subject_source"]["text_span"] == [offset + 44, offset + 46]
    assert fact["predicate_source"]["text_span"] == [offset + 47, offset + 56]
    assert result["logic"][0]["kind"] == "fronted_context"
    assert result["logic"][0]["child"]["kind"] == "proposition"
    assert any(edge["type"] == "narrative_fronted_context_scope" for edge in result["relations"])
    assert not result["semantic_operands"]
    assert {"fronted_nominal_context", "quoted_nominal_scope"} <= set(result["required_matcher_features"])
    assert result["text_atoms"][0]["text"] == text


@pytest.mark.parametrize("preposition", ["In", "in"])
def test_domain_is_bound_only_by_the_printed_domain_head_and_preserves_preposition_case(preposition):
    text = preposition + ' the cloud sector, Lumen supports research.'
    result = read(text)
    assert result["complete"] is True
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"]) == ("Lumen", "support", "research")
    assert fact["qualifiers"]["fronted_contexts"] == [{"preposition": preposition, "operator": "in",
        "role": "domain", "text": "the cloud sector"}]
    assert fact["qualifier_sources"]["fronted_contexts"][0]["context_source"]["text_span"] == [3, 19]
    assert fact["qualifier_sources"]["fronted_contexts"][0]["separator_source"]["text_span"] == [19, 20]


@pytest.mark.parametrize("text", [
    'Under the strategy that Lumen approves, Vega owns Kappa.',
    'Under the policy unless Gate is open, Lumen owns Kappa.',
    'Under the strategy, we flarned our focus.',
    'Under the “user first strategy, we sharpened our focus.',
    'In Paris, Lumen owns Kappa.',
    'Under the framework, in the cloud sector, Lumen owns Kappa.',
])
def test_unknown_scope_or_child_preserves_the_whole_printed_requirement(text):
    result = read(text)
    assert result["complete"] is False and not result["facts"]
    [pending] = result["pending_requirements"]
    assert pending["text"] == text
    assert pending["source"]["text_span"] == [0, len(text)]
    assert set(pending["layers"]) == {"B", "L"}
    assert "fronted_nominal_context" in result["required_matcher_features"]
    assert result["text_atoms"][0]["text"] == text


def test_temporal_in_and_plain_quoted_nominals_keep_their_own_roles_without_input_mutation():
    source = {"path": "<temporal-control>", "lines": [1, 1]}
    before = deepcopy(source)
    result = read_narrative('In April 2028, Lumen owns "Kappa and Sigma".', source)
    assert source == before
    assert result["complete"] is True
    [fact] = result["facts"]
    assert fact["qualifiers"]["period"] == "April 2028"
    assert "fronted_contexts" not in fact["qualifiers"]
    assert "fronted_nominal_context" not in result["required_matcher_features"]
