"""Quoted terminal punctuation is a source boundary, not an invitation to join."""

import pytest

from moparse_eval.three_layer import read_candidate


@pytest.mark.parametrize("citation", ['See also “Risk overview.”', 'See also "Risk overview."', '参见“风险概览。”'])
def test_terminal_quote_does_not_attach_another_paragraph_to_the_reference(citation):
    following = "The board shall pay 17 credits."
    observation = {"sample_id": "quoted-boundary", "pipeline": "test", "status": "completed",
        "pages": [{"page": 1, "blocks": [
            {"id": "reference", "native_path": "#/reference", "kind": "text", "text": citation, "text_format": "plain"},
            {"id": "following", "native_path": "#/following", "kind": "text", "text": following, "text_format": "plain"},
        ]}]}
    result = read_candidate(observation)
    assert [node["text"] for node in result["text"]] == [citation, following]
    assert not any(node.get("source_fragments") for node in result["text"])
    [claim] = result["business"]
    assert claim["subject"].lower() == "the board" and claim["value"] == "pay 17 credits"
    assert claim["source"]["path"] == "#/following"
