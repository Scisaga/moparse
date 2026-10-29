"""Comparison reporting keeps newly wrong fields distinct from net gains."""

from moparse_eval.table_context_report import _transitions


def test_information_gains_losses_and_new_errors_are_separate():
    pairs = [{"field_index": n, "baseline": {"information": {"status": a}},
              "final": {"information": {"status": b}}} for n, (a, b) in enumerate([
                  ("unresolved", "correct"), ("correct", "incorrect"),
                  ("correct", "unresolved"), ("unresolved", "incorrect"), ("incorrect", "correct")])]
    result = _transitions(pairs)
    assert result["new_correct"] == 2
    assert result["lost_correct"] == 2
    assert result["new_incorrect"] == 2
    assert len(result["introduced_errors"]) == 2


def test_missing_reference_or_unreadable_output_is_not_zero_quality_gain():
    result = _transitions([{"field_index": 0, "baseline": {"status": "not_scored"},
                            "final": {"status": "unresolved"}}])
    assert result["new_correct"] == result["new_incorrect"] == 0
    assert result["field_state_transitions"] == {"not_scored->unresolved": 1}
