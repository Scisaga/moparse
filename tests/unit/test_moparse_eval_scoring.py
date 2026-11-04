"""Independent literal metric tests over invented text only."""

import pytest

from moparse_eval.metrics import edit_counts, normalize_text, precision_recall_f1, text_metrics


def test_width_policy_keeps_strict_diagnostics_and_does_not_use_nfkc():
    assert normalize_text("Ａ１，\u3000−①ﬁ") == "A1, −①ﬁ"
    metrics = text_metrics("Ａ１", "A1")
    assert metrics["strict"]["distance"] == 2
    assert metrics["width_equivalent"]["distance"] == 0
    assert text_metrics("-100", "100")["width_equivalent"]["distance"] == 1


def test_cer_can_exceed_one_and_zero_denominators_stay_na():
    metrics = text_metrics("a", "abcdef")["strict"]
    assert metrics["cer"] == 5
    assert metrics["normalized_edit_distance"] == pytest.approx(5 / 6)
    assert metrics["similarity"] == pytest.approx(1 / 6)
    assert text_metrics("", "")["strict"]["cer"] is None
    assert precision_recall_f1(0, None, 0)["recall"] is None


def test_edit_counts_preserve_substitution_deletion_and_insertion():
    assert edit_counts("abc", "axc")["substitutions"] == 1
    assert edit_counts("abc", "ac")["deletions"] == 1
    assert edit_counts("ac", "abc")["insertions"] == 1
