"""Uninterpreted assertions cannot disappear beside a supported modal clause."""

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown


def test_a_business_statement_before_a_modal_clause_is_not_silently_removed_without_a_colon():
    text = "We are expanding freight transport and parcel delivery. The committee shall review funding."
    graph = compile_markdown(text)
    result = grade_layers(graph, read_candidate_markdown(text))
    assert result["layers"]["T"]["score"] == 100
    first = [f for f in graph["business"] if f["role"] == "description" and f["subject"].casefold() == "we"
             and f["attribute"] == "expand"]
    if not first:
        pending = [b for b in graph["blockers"] if "freight transport" in b.get("text", "")
                   and "parcel delivery" in b.get("text", "") and "B" in b.get("layers", [])]
        assert pending
        assert result["publishable"] is False
    else:
        assert [fact["value"] for fact in first] == ["freight transport", "parcel delivery"]
        assert [fact["object_source"]["text_span"] for fact in first] == [[17, 34], [39, 54]]
        assert all(fact["qualifiers"]["coordination"] == "and" and fact["qualifiers"]["aspect"] == "progressive"
                   for fact in first)
        assert len(graph["business"]) == 3
        assert result["layers"]["B"]["score"] == 100
        changed = grade_layers(graph, read_candidate_markdown(text.replace("parcel delivery", "road delivery")))
        assert changed["semantic_comparison"]["decisions"]["B"]["conflict"]
        assert changed["layers"]["B"]["numerator"] < 3
