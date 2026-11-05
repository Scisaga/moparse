"""One unknown prefixed sequence cannot masquerade as an opaque field."""

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate


def graphs(body):
    markdown = "Name:Anchor\n\n" + body
    required = compile_markdown(markdown, sample_id="invented-prefixed-sequence")
    actual = read_candidate(markdown_observation(markdown, sample_id="invented-prefixed-sequence",
                                               pipeline="P07", pages=[1]))
    return required, actual


def test_unknown_prefix_and_multiple_fields_remain_source_bound_pending_not_an_opaque_answer():
    body = "Container; Type A: Ready; Type B: Blocked"
    required, actual = graphs(body)
    score = grade_layers(required, actual)
    assert score["publishable"] is False and score["score"] is None
    assert score["layers"]["B"]["complete"] is score["layers"]["L"]["complete"] is False
    assert score["layers"]["T"]["score"] == 100
    for graph in (required, actual):
        assert [(fact["attribute"], fact["value"]) for fact in graph["business"]] == [("Name", "Anchor")]
        [pending] = [item for item in graph.get("pending_requirements", []) if item.get("text") == body]
        assert pending["source"]["lines"] == [3, 3]
        assert pending["source"]["text_span"] == [0, len(body)]
        assert pending["prefix"]["text"] == "Container"
        assert pending["prefix"]["source"]["text_span"] == [0, 9]
        assert len(pending["segments"]) == 2
        wanted = [("Type A", "Ready"), ("Type B", "Blocked")]
        assert [(part["label"], part["value"]) for part in pending["segments"]] == wanted
        for part, (label, value) in zip(pending["segments"], wanted, strict=True):
            for field, literal in (("label_source", label), ("value_source", value)):
                start = body.index(literal)
                assert part[field]["text_span"] == [start, start + len(literal)]
                assert part[field]["path"] == pending["source"]["path"]
                assert part[field]["lines"] == [3, 3]
        blockers = [item for item in graph["blockers"] if item.get("source", {}).get("lines") == [3, 3]]
        assert blockers and set().union(*(set(item.get("layers", [])) for item in blockers)) >= {"B", "L"}


@pytest.mark.parametrize("body,wanted", [
    ("Date and time: 9:00\n\nLocation: https://example.invalid/notice?id=2028",
     [("Date and time", "9:00"), ("Location", "https://example.invalid/notice?id=2028")]),
])
def test_a_semicolon_inside_one_legitimate_value_and_metadata_are_not_prefixed_sequences(body, wanted):
    for graph in graphs(body):
        assert graph["blockers"] == [] and graph.get("pending_requirements", []) == []
        assert [(fact["attribute"], fact["value"]) for fact in graph["business"]] == [("Name", "Anchor"), *wanted]


def test_narrative_enumeration_does_not_gain_an_uninterpreted_opaque_business_vote():
    for graph in graphs("Narrative: Alpha; Beta"):
        assert [(fact["attribute"], fact["value"]) for fact in graph["business"]] == [("Name", "Anchor")]
        assert any("B" in item.get("layers", []) for item in graph["blockers"])
        assert "Alpha; Beta" in " ".join(item["text"] for item in graph["text"])
        assert not any(item.get("reason", "").startswith("field_sequence_") for item in graph["blockers"])
