"""Sentence boundaries retain positions in the original complete paragraph."""

import pytest

from moparse_eval.three_layer import compile_markdown, read_candidate

TEXT = "The board shall pay 17 credits. The clerk must publish the notice."


@pytest.mark.parametrize("native", [False, True])
def test_each_statement_value_source_points_into_its_original_paragraph(native):
    if native:
        graph = read_candidate({"sample_id": "synthetic", "pipeline": "invented", "status": "completed",
            "pages": [{"page": 1, "blocks": [{"id": "body", "kind": "text", "text_format": "plain", "text": TEXT}]}]})
    else:
        graph = compile_markdown(TEXT)
    assert [(f["attribute"], f["value"]) for f in graph["business"]] == [
        ("pay", "pay 17 credits"), ("publish", "publish the notice")]
    assert [f["value_source"]["text_span"] for f in graph["business"]] == [[16, 30], [47, 65]]
    for fact in graph["business"]:
        a, b = fact["value_source"]["text_span"]
        assert TEXT[a:b] == fact["value"]
