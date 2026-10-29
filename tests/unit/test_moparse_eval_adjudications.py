"""Synthetic scoring exclusions; never inspect repository corpus materials."""

from __future__ import annotations

import copy
import json

import pytest

from moparse_eval.adjudications import reference_exclusions
from moparse_eval.cli import parser, report_run, score_run
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


def test_exclusion_preserves_frozen_status_and_removes_dependent_relation():
    reference = synthetic_case()
    before = copy.deepcopy(reference)
    actual = {"sample_id": "one", "status": "completed", "pages": [{"page": 1, "blocks": [
        {"id": "b", "kind": "text", "text": "Retained statement."},
    ]}]}
    result = score_case(reference, actual, reference_exclusions=reference_exclusions(human_record(), "one"))
    assert reference == before
    pending = result["units"][0]
    assert pending["reason"] == "human_reference_pending"
    assert pending["reference_status_at_freeze"] == "confirmed"
    assert result["coverage"]["excluded_units"] == {"human_reference_pending": 1}
    assert result["coverage"]["reference_unavailable_relations"] == 1
    assert result["metrics"]["text"]["strict"]["distance"] == 0
    assert result["metrics"]["relations"]["target_units"] == 0


@pytest.mark.parametrize("change", [
    {"pipeline": "P01"}, {"suite": "quality800"}, {"replacement": "Better answer"},
    {"action": "correct_reference"},
])
def test_human_exclusions_cannot_select_favorable_outputs_or_rewrite(change):
    record = human_record()
    record["decisions"][0].update(change)
    with pytest.raises(ValueError):
        reference_exclusions(record, "one")


def test_pending_localization_anchor_excludes_dependent_fields_but_keeps_independent_prose():
    target = {
        "sample_id": "one", "review_status": "confirmed", "units": [
            {"id": "pending", "kind": "text", "literal": "Annual revenue", "status": "confirmed", "pages": [1],
             "localization_scope": "label_only"},
            {"id": "value", "kind": "field", "literal": "100", "status": "confirmed", "pages": [1],
             "field_scope": {"scope_kind": "visual_label_value_pair", "label_unit": "pending"}},
            {"id": "body", "kind": "text", "parent": "pending", "status": "confirmed", "pages": [1],
             "literal": "Independent paragraph with a complete source-backed narrative."},
        ],
    }
    actual = {"sample_id": "one", "status": "completed", "pages": [{"page": 1, "blocks": [
        {"id": "native-field", "kind": "text", "text": "Annual revenue: 100"},
        {"id": "native-body", "kind": "text", "text": target["units"][2]["literal"]},
    ]}]}
    baseline = score_case(target, actual)
    assert baseline["metrics"]["field_exact"]["value"] == 1
    assert baseline["metrics"]["field_pair_binding"]["value"] == 1
    result = score_case(target, actual, reference_exclusions=reference_exclusions(human_record(), "one"))
    assert result["metrics"]["field_exact"]["denominator"] == 0
    assert result["metrics"]["field_pair_binding"]["denominator"] == 0
    assert result["metrics"]["field_text"]["strict"]["reference_chars"] == 0
    assert result["metrics"]["text"]["strict"]["reference_chars"] == len(target["units"][2]["literal"])
    assert result["metrics"]["text"]["strict"]["distance"] == 0
    assert result["coverage"]["reference_unavailable_field_pair_bindings"] == 1
    assert result["units"][1]["reason"] == "reference_localization_dependency_unavailable"
    # Explicit localization chains are propagated without looking at predictions.
    target["units"].append({"id": "child-value", "kind": "field", "literal": "10", "parent": "value",
                            "status": "confirmed", "pages": [1]})
    chained = score_case(target, actual, reference_exclusions=reference_exclusions(human_record(), "one"))
    assert chained["units"][3]["reason"] == "reference_localization_dependency_unavailable"
    assert chained["metrics"]["field_exact"]["denominator"] == 0


def test_unknown_exclusion_unit_is_a_scoring_input_error_not_a_corpus_judgment():
    record = human_record()
    record["decisions"][0]["unit_id"] = "pending-TYPO"
    with pytest.raises(ValueError, match="no unit in this scoring case"):
        score_case(synthetic_case(), {"sample_id": "one"},
                   reference_exclusions=reference_exclusions(record, "one"))


@pytest.mark.parametrize("excluded_sample", ["one", "other"])
def test_cli_uses_same_human_exclusion_for_all_eight_and_all_rounds(tmp_path, excluded_sample):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    frozen = dataset / "reference.json"
    frozen.write_text(json.dumps(synthetic_case()))
    manifest = dataset / "manifest.json"
    manifest.write_text(json.dumps({"samples": [{"id": "one", "evaluation": "reference.json"}]}))
    before = (frozen.read_bytes(), manifest.read_bytes())
    run = tmp_path / "run"
    (run / "artifacts").mkdir(parents=True)
    cases = []
    for pipeline in (f"P{value:02}" for value in range(1, 9)):
        for suite, repetition in [("quality800", 1), ("perf80", 1), ("perf80", 2), ("perf80", 3)]:
            relative = f"artifacts/{pipeline}-{suite}-{repetition}.json"
            observation = {
                "sample_id": "one", "pipeline": pipeline, "suite": suite, "phase": "measured",
                "repetition": repetition, "status": "completed", "input_page_count": 1,
                "timing": {"processing_seconds": 1 if suite == "quality800" else 2 * repetition},
                "pages": [{"page": 1, "blocks": [{"id": "b", "kind": "text", "text": "Retained statement."}]}],
            }
            (run / relative).write_text(json.dumps(observation))
            cases.append({**{key: observation[key] for key in (
                "sample_id", "pipeline", "suite", "phase", "repetition",
            )}, "observation": relative})
    (run / "run.json").write_text(json.dumps({
        "run_id": "synthetic", "dataset": str(dataset), "formal": True, "state": "completed", "cases": cases,
    }))
    (run / "maintenance.json").write_text(json.dumps({
        "phase": "restored", "tts_policy": "keep_running",
        "tts_identity_condition": {"status": "unchanged"},
        "tts_no_calls_condition": {"status": "no_observed_activity"},
    }))
    decisions = tmp_path / "human.json"
    record = human_record()
    record["decisions"][0]["sample_id"] = excluded_sample
    decisions.write_text(json.dumps(record))
    args = parser().parse_args(["score", "--run", str(run), "--adjudications", str(decisions)])
    index = json.loads(score_run(args.run, adjudications=args.adjudications).read_text())
    assert len(index["results"]) == 32
    for relative in index["results"]:
        result = json.loads((run / relative).read_text())
        assert result["coverage"]["excluded_units"].get("human_reference_pending", 0) == int(excluded_sample == "one")
    assert json.loads((run / index["reference_adjudications"]["path"]).read_text()) == record
    audit = index["reference_adjudications"]
    assert audit["applied_score_cases"] == (32 if excluded_sample == "one" else 0)
    assert audit["applied_decision_ids"] == (["decision-a"] if excluded_sample == "one" else [])
    assert audit["unmatched_decision_ids"] == ([] if excluded_sample == "one" else ["decision-a"])
    report = report_run(run)
    rendered = report.read_text()
    summary = json.loads((run / "summary.json").read_text())
    assert summary["scoring_software"]["software_id"] == index["software"]["software_id"]
    assert summary["score_index"].endswith("index.json")
    appendix = (run / "appendix.md").read_text()
    assert "appendix.md" in rendered
    assert "提交1条来源直接目读支持的参考待判排除" in appendix
    assert f"实际生效{int(excluded_sample == 'one')}条" in appendix
    assert "质量与成本对照" in rendered
    assert "| P08 | 1/1 |" in appendix
    assert "1.0000 / 1 | 4.0000 / 3" in appendix
    assert report_run(run).read_text() == rendered
    assert (frozen.read_bytes(), manifest.read_bytes()) == before


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
