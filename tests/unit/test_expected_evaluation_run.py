"""End-to-end software evaluation over invented eight-pipeline runs only."""


import pytest

from moparse_eval import cli
from moparse_eval.expected_evaluation import PIPELINES, evaluate_saved
from moparse_eval.expected_readback import markdown_observation
from moparse_eval.expected_report import load_complete, render_expected_report
from moparse_eval.packaging import read_json, write_json


def invented_run(tmp_path, monkeypatch):
    expected = tmp_path / "expected"
    document = expected / "invented-document"
    document.mkdir(parents=True)
    text = "## Results\n\n- Revenue: 2024: 17; 2023: 11.\n"
    (document / "expected.md").write_text(text)
    write_json(document / "manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {
        "entries": [{"source_pages": [1], "markdown_lines": [1, 3]}]}})
    dataset = tmp_path / "dataset"
    write_json(dataset / "manifest.json", {"samples": [{
        "id": "invented", "document_id": "invented-document", "source_pages": [1],
        "family_id": "invented-family", "development_exposure": "synthetic-exposed", "tags": ["prose"],
        "evaluation": "a-stale-answer-file-that-must-not-be-read.json",
    }]})
    baseline = tmp_path / "native"
    cases = []
    for pipeline in PIPELINES:
        relative = f"artifacts/{pipeline}/quality800-r1/invented/observation.json"
        write_json(baseline / relative, markdown_observation(text, sample_id="invented", pipeline=pipeline, pages=[1]))
        cases.append({"pipeline": pipeline, "sample_id": "invented", "suite": "quality800", "phase": "measured",
                      "repetition": 1, "observation": relative})
    write_json(baseline / "run.json", {"run_id": "invented-run", "state": "completed", "dataset": str(dataset),
                                      "development_experiment": True, "experiment_id": "synthetic-only",
                                      "cases": cases, "reference_adjudications": "/must-not-open-legacy-decisions.json"})
    identity = {"software_id": "invented-software"}
    monkeypatch.setattr(cli, "code_identity", lambda: identity)
    monkeypatch.setattr(cli, "snapshot_software", lambda *_: None)
    freeze = tmp_path / "freeze.json"
    write_json(freeze, {"software_id": identity["software_id"], "protocol_id": cli.SCORING_PROTOCOL["id"],
                        "validation": {"status": "passed"}})
    return baseline, dataset, expected, freeze, text


def test_all_eight_saved_groups_are_programmatically_scored(tmp_path, monkeypatch):
    baseline, _, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    index = evaluate_saved(baseline, tmp_path / "scores", expected_root=expected, freeze=freeze)
    record, groups = load_complete(index)
    assert set(groups) == set(PIPELINES)
    assert record["expected_comparison_complete"] is True
    assert all(group[0]["incorrect"] == 0 for group in groups.values())
    report = render_expected_report(index, figures=False)
    assert "P01" in report.read_text() and "P08" in report.read_text()


def test_missing_candidate_retains_identical_targets_and_is_incorrect(tmp_path, monkeypatch):
    baseline, _, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    metadata = read_json(baseline / "run.json")
    (baseline / metadata["cases"][0]["observation"]).unlink()
    index = evaluate_saved(baseline, tmp_path / "scores", expected_root=expected, freeze=freeze)
    _, groups = load_complete(index)
    missing = groups["P01"][0]
    assert missing["targets"] == missing["incorrect"]
    assert missing["targets"] == groups["P08"][0]["targets"]


def test_report_rejects_mixed_software_even_with_the_same_protocol(tmp_path, monkeypatch):
    baseline, _, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    index = evaluate_saved(baseline, tmp_path / "scores", expected_root=expected, freeze=freeze)
    record = read_json(index)
    source = index.parent / record["records"][0]["path"]
    score = read_json(source)
    score["scoring_software_id"] = "different"
    write_json(source, score)
    with pytest.raises(ValueError, match="mixed scoring software"):
        render_expected_report(index, figures=False)


def test_output_cannot_be_written_into_reference_directory(tmp_path, monkeypatch):
    baseline, _, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="outside the read-only expected"):
        evaluate_saved(baseline, expected / "forbidden", expected_root=expected, freeze=freeze)
    assert not (expected / "forbidden").exists()


def test_final_outputs_are_read_from_markdown_without_private_metadata(tmp_path, monkeypatch):
    baseline, dataset, expected, freeze, text = invented_run(tmp_path, monkeypatch)
    metadata = read_json(baseline / "run.json")
    for label, amount in (("previous", "19"), ("current", "17")):
        for pipeline in ("P07", "P08"):
            directory = tmp_path / label / pipeline.lower()
            final = directory / "candidate/final.md"
            final.parent.mkdir(parents=True)
            final.write_text(text.replace("2024: 17", "2024: " + amount))
            native_case = next(c for c in metadata["cases"] if c["pipeline"] == pipeline)
            case = {**native_case, "final_markdown": "candidate/final.md", "input_pages": 1,
                    "baseline_observation_source": native_case["observation"]}
            write_json(directory / "run.json", {"state": "completed", "baseline_run": str(baseline),
                "dataset": str(dataset), "native_pipeline": {"pipeline": pipeline}, "cases": [case],
                "software": {"software_id": label}, "reference_adjudications": "/must-not-open.json"})
    index = evaluate_saved(baseline, tmp_path / "scores", expected_root=expected, freeze=freeze,
                           previous_root=tmp_path / "previous", current_root=tmp_path / "current",
                           intermediate_root=tmp_path / "previous")
    record, groups = load_complete(index)
    assert len(groups) == 14
    assert record["changes"]["P07"]["new_correct"] == 1
    assert record["changes"]["P08"]["lost_correct"] == 0
    assert record["incremental_changes"]["P07"]["new_correct"] == 1
    assert record["adoption"]["P07"]["no_lost_correct_targets"] is True


def test_report_is_reproducible_with_references_and_dataset_offline(tmp_path, monkeypatch):
    baseline, dataset, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    index = evaluate_saved(baseline, tmp_path / "scores", expected_root=expected, freeze=freeze)
    dataset.rename(tmp_path / "dataset-offline")
    expected.rename(tmp_path / "expected-offline")
    report = render_expected_report(index, figures=False)
    first = report.read_bytes()
    assert render_expected_report(index, figures=False).read_bytes() == first
    summary = read_json(index.parent / "summary.json")
    group = summary["groups"]["P01"]
    assert group["by_family"]["invented-family"]["samples"] == 1
    assert group["development_exposure"] == {"synthetic-exposed": 1}


def test_report_refuses_duplicate_sample_records(tmp_path, monkeypatch):
    baseline, _, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    index = evaluate_saved(baseline, tmp_path / "scores", expected_root=expected, freeze=freeze)
    record = read_json(index)
    record["records"].append(record["records"][0])
    write_json(index, record)
    with pytest.raises(ValueError, match="duplicate"):
        render_expected_report(index, figures=False)


def test_missing_recorded_costs_are_never_filled_with_zero(tmp_path, monkeypatch):
    baseline, _, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    index = evaluate_saved(baseline, tmp_path / "scores", expected_root=expected, freeze=freeze)
    record = read_json(index)
    cost = record["execution_costs"]["native"]["P01"]["quality800"]
    assert cost["rounds"][0]["processing_seconds_including_failures"] is None
    assert cost["rounds"][0]["timing_complete"] is False


@pytest.mark.parametrize("group,native,stage", [
    ("P01", None, "native_output"),
    ("P07-current", "incorrect", "native_output"),
    ("P07-current", "correct", "final_markdown_conversion"),
])
def test_failure_stage_uses_the_paired_native_decision(group, native, stage):
    from moparse_eval.expected_report import first_failure_stage
    assert first_failure_stage(group, {"outcome": "incorrect"}, {"outcome": native} if native else None) == stage


def test_missing_native_decision_cannot_become_an_invented_failure_stage():
    from moparse_eval.expected_report import first_failure_stage
    with pytest.raises(ValueError, match="paired native target"):
        first_failure_stage("P07-current", {"outcome": "incorrect"}, None)


def test_parallel_analysis_produces_identical_target_decisions_and_evidence(tmp_path, monkeypatch):
    baseline, _, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    serial = evaluate_saved(baseline, tmp_path / "serial", expected_root=expected, freeze=freeze)
    parallel = evaluate_saved(baseline, tmp_path / "parallel", expected_root=expected, freeze=freeze, workers=2)
    _, left = load_complete(serial)
    _, right = load_complete(parallel)
    assert {group: [score["outcomes"] for score in scores] for group, scores in left.items()} == {
        group: [score["outcomes"] for score in scores] for group, scores in right.items()}


def test_existing_completed_output_is_never_rewritten_by_a_rejected_retry(tmp_path, monkeypatch):
    baseline, _, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    output = tmp_path / "scores"
    evaluate_saved(baseline, output, expected_root=expected, freeze=freeze)
    prior = (output / "execution-status.json").read_bytes()
    with pytest.raises(FileExistsError):
        evaluate_saved(baseline, output, expected_root=expected, freeze=freeze)
    assert (output / "execution-status.json").read_bytes() == prior


def test_dataset_is_read_only_for_score_output(tmp_path, monkeypatch):
    baseline, dataset, expected, freeze, _ = invented_run(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="read-only dataset"):
        evaluate_saved(baseline, dataset / "forbidden", expected_root=expected, freeze=freeze)
