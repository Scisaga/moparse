"""Unsupported source roles discovered during emission remain local pending."""

from copy import deepcopy

import pytest

from moparse_eval.cjk_narrative_requirements import read_cjk_narrative
from moparse_eval.narrative_requirements import _Reader, _Unknown, read_narrative

SOURCE = {"path": "<independent-emission-boundary>", "lines": [1, 1]}


def test_a_cjk_quoted_definition_keeps_literal_and_pending_instead_of_crashing():
    text = "「北辰公司」是指某股份公司"
    result = read_cjk_narrative(text, SOURCE)
    assert result["matched"] and not result["complete"]
    assert result["facts"] == result["relations"] == result["logic"] == []
    assert result["semantic_operands"] == result["semantic_operand_relations"] == []
    assert result["text_atoms"][0]["text"] == text
    assert any(issue["reason"] == "quoted_nominal_lexical_role_unresolved"
               and issue["layers"] == ["B", "L"] for issue in result["pending_requirements"])


def test_a_later_unsupported_quoted_role_keeps_an_independent_valid_neighbor():
    text = "公司批准报告。「北辰公司」是指某股份公司。"
    result = read_cjk_narrative(text, SOURCE)
    assert not result["complete"]
    assert [(fact["subject"], fact["attribute"], fact["value"]) for fact in result["facts"]] == [
        ("公司", "批准", "报告")]
    assert len(result["logic"]) == 1
    assert any("北辰公司" in item["text"] for item in result["pending_requirements"])


@pytest.mark.parametrize("text", ["Board owns Kappa and Sigma.", "Board may own Kappa or Sigma."])
def test_late_role_failure_rolls_back_all_partial_members_without_dropping_previous_sentence(monkeypatch, text):
    original = _Reader.emit

    def fail_after_emitting(self, node, *args, **kwargs):
        result = original(self, node, *args, **kwargs)
        if node.get("object") == "Sigma":
            raise _Unknown("independent_source_role_failure")
        return result

    monkeypatch.setattr(_Reader, "emit", fail_after_emitting)
    source = deepcopy(SOURCE)
    result = read_narrative("Lumen owns Omega. " + text, source)
    assert source == SOURCE
    assert [(fact["subject"], fact["attribute"], fact["value"]) for fact in result["facts"]] == [
        ("Lumen", "own", "Omega")]
    assert len(result["logic"]) == 1
    assert result["semantic_operands"] == result["semantic_operand_relations"] == []
    assert all(edge["right"]["subject"] == "Lumen" for edge in result["relations"])
    assert any(item["reason"] == "independent_source_role_failure" and item["text"] == text
               for item in result["pending_requirements"])
