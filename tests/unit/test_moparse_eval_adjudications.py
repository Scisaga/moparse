"""Historical decision schemas and rejection by current scoring; synthetic inputs only."""

from __future__ import annotations

import copy

import pytest

from moparse_eval.adjudications import reference_exclusions
from moparse_eval.cli import parser, score_run
from moparse_eval.reporting import aggregate_reports, render_appendix
from moparse_eval.scoring import score_case


def human_record():
    return {
        "id": "synthetic-human-review", "scope": "all_configurations_and_repetitions",
        "decisions": [{
            "id": "decision-a", "sample_id": "one", "unit_id": "pending",
            "action": "exclude_unit_pending", "reviewers": ["synthetic-reviewer"],
            "reason": "Synthetic source-backed uncertainty.", "evidence": ["synthetic-source.png"],
        }],
    }


def synthetic_case():
    return {
        "sample_id": "one", "review_status": "confirmed", "units": [
            {"id": "pending", "kind": "text", "literal": "Questionable reference.", "status": "confirmed", "pages": [1]},
            {"id": "stable", "kind": "text", "literal": "Retained statement.", "status": "confirmed", "pages": [1]},
        ],
        "relations": [{"type": "before", "source": "pending", "target": "stable", "status": "confirmed"}],
    }


def test_current_scoring_rejects_exclusions_and_preserves_reference():
    reference = synthetic_case()
    before = copy.deepcopy(reference)
    with pytest.raises(ValueError, match="does not accept reference exclusions"):
        score_case(reference, {"sample_id": "one", "pages": []},
                   reference_exclusions=reference_exclusions(human_record(), "one"))
    assert reference == before


@pytest.mark.parametrize("change", [
    {"pipeline": "P01"}, {"suite": "quality800"}, {"replacement": "Better answer"},
    {"action": "correct_reference"},
])
def test_human_exclusions_cannot_select_favorable_outputs_or_rewrite(change):
    record = human_record()
    record["decisions"][0].update(change)
    with pytest.raises(ValueError):
        reference_exclusions(record, "one")


def test_historical_anchor_exclusion_cannot_remove_current_targets():
    target = synthetic_case()
    actual = {"sample_id": "one", "status": "completed", "pages": []}
    with pytest.raises(ValueError, match="does not accept reference exclusions"):
        score_case(target, actual, reference_exclusions=reference_exclusions(human_record(), "one"))


def test_unknown_exclusion_unit_is_a_scoring_input_error_not_a_corpus_judgment():
    record = human_record()
    record["decisions"][0]["unit_id"] = "pending-TYPO"
    with pytest.raises(ValueError, match="does not accept reference exclusions"):
        score_case(synthetic_case(), {"sample_id": "one"},
                   reference_exclusions=reference_exclusions(record, "one"))


@pytest.mark.parametrize("pipeline", [f"P{i:02}" for i in range(1, 9)])
def test_cli_rejects_old_exclusion_option_without_opening_it(tmp_path, monkeypatch, pipeline):
    from moparse_eval import cli

    def forbidden(*args, **kwargs):
        pytest.fail("no inputs or exclusions may be opened after a rejected option")

    monkeypatch.setattr(cli, "read_json", forbidden)
    args = parser().parse_args(["score", "--run", str(tmp_path / pipeline),
                               "--adjudications", str(tmp_path / "must-not-read.json")])
    with pytest.raises(ValueError, match="does not accept adjudications"):
        score_run(args.run, adjudications=args.adjudications)
    assert not (tmp_path / pipeline).exists()


def test_missing_round_duration_stays_na_and_partial_cost_is_named_subtotal():
    common = {"pipeline": "P01", "dataset": "synthetic", "suite": "quality800", "phase": "measured",
              "repetition": 1, "input_page_count": 1}
    failed = {**common, "sample_id": "failed", "status": "preparation_failed", "timing": {}}
    report = aggregate_reports([failed])
    performance = report["groups"][0]["performance"]
    assert performance["rounds"][0]["processing_seconds_including_failures"] is None
    assert performance["rounds"][0]["observed_processing_seconds_subtotal"] is None
    assert performance["round_duration_summary"]["n"] == 0
    assert "| 1 | 1 | 0 | NA | NA | 1 | NA |" in render_appendix(report)
    partial = aggregate_reports([
        failed, {**common, "sample_id": "completed", "status": "completed", "timing": {"processing_seconds": 2}},
    ])["groups"][0]["performance"]["rounds"][0]
    assert partial["processing_seconds_including_failures"] is None
    assert partial["observed_processing_seconds_subtotal"] == 2
    assert partial["completed_pages_per_second_including_failure_cost"] is None
