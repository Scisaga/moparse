"""Failed saved outputs preserve attribution and unknown cost separately."""

from moparse_eval.layer_aggregation import summarize_layers
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate


def test_failed_outputs_keep_document_family_and_absent_costs():
    scores = []
    for name in ("known", "previously_unindexed"):
        requirements = compile_markdown("Name: Delta; Revenue: 17", sample_id=name)
        requirements.update(document_id="doc", family_id="family", development_exposure="exposed")
        evidence = read_candidate({"sample_id": name, "status": "failed", "pages": [],
                                   "timing": {"processing_seconds": None}})
        score = grade_layers(requirements, evidence)
        assert score["document_id"] == "doc"
        assert score["family_id"] == "family"
        assert score["development_exposure"] == "exposed"
        assert score["timing"]["processing_seconds"] is None
        scores.append(score)
    result = summarize_layers(scores)
    assert result["samples"] == 2
    assert result["layers"]["B"]["denominator"] == 4
    assert result["layers"]["B"]["numerator"] == 0
    assert result["layers"]["B"]["applicable_samples"] == 2
    assert "processing_seconds" not in result
