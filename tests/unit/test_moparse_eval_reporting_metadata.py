"""Grouping and absent runtime measurements use invented score records only."""

from moparse_eval.expected_evaluation import summarize


def test_failed_outputs_keep_document_family_and_absent_costs():
    scores = [{"sample_id": name, "document_id": "doc", "family_id": "family", "tags": ["prose"],
               "development_exposure": "exposed", "status": "failed", "timing": {"processing_seconds": None},
               "by_kind": {"text": {"targets": 1, "correct": 0, "incorrect": 1}},
               "outcomes": [{"outcome": "incorrect", "reason": "missing"}]}
              for name in ("known", "previously_unindexed")]
    result = summarize(scores)
    assert result["by_family"]["family"]["samples"] == 2
    assert result["by_document"]["doc"]["samples"] == 2
    assert result["development_exposure"] == {"exposed": 2}
    assert result["by_kind"]["text"]["targets"] == result["by_kind"]["text"]["incorrect"] == 2
    assert result["processing_seconds"] is None
    assert result["observed_processing_seconds_subtotal"] is None
    assert result["missing_processing_samples"] == 2
