"""Invented execution/score/telemetry records only; no reference corpus reads."""

from __future__ import annotations

import json

import pytest

from moparse_eval.p05_optimization_report import generate_p05_optimization_report


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def text(distance):
    counts = {"distance": distance, "substitutions": distance, "insertions": 0, "deletions": 0,
              "reference_chars": 100, "hypothesis_chars": 100}
    return {"strict": dict(counts), "width_equivalent": dict(counts), "units": 1}


def experiment(tmp_path):
    root = tmp_path / "experiment"
    save(root / "experiment.json", {"state": "completed", "development_experiment": True})
    for arm in ("baseline", "native"):
        run = root / arm
        cases = []
        results = []
        metadata = {name: {"input_page_count": 1 if name == "a" else 2,
                           "document_id": "doc-" + name, "family_id": "family-" + name}
                    for name in ("a", "b")}
        for repetition in (1, 2, 3):
            for name in ("a", "b"):
                case = {"pipeline": "P05", "sample_id": name, "suite": "perf80", "phase": "measured",
                    "repetition": repetition,
                    "observation": f"artifacts/P05/measured-perf80-r{repetition}/{name}/observation.json"}
                observed = {**case, **metadata[name], "dataset": "synthetic", "run_id": arm,
                    "status": "completed", "timing": {"processing_seconds": float(repetition + (name == "b")),
                                                        "pipeline_initialization_seconds": 7.5}}
                save(run / case["observation"], observed)
                # Deliberately awful later-round quality must not contaminate
                # the preselected first round.
                score = {**observed, "scorer_status": "evaluated", "coverage": {
                    "scored_units": 1, "text_reference_chars": 100, "text_aligned_reference_chars": 100},
                    "metrics": {"text": text((10 if arm == "baseline" else 2) if repetition == 1 else 100),
                                "unit_presence": {"tp": 1, "fn": 0, "fp": None}}}
                relative = f"scores/r{repetition}-{name}.json"
                save(run / relative, score)
                results.append(relative)
                cases.append(case)
                telemetry = (run / case["observation"]).parent / "telemetry" / "p0001-glm"
                save(telemetry / "c1/request.json", {"max_tokens": 8192, "repetition_penalty": 1.1})
                save(telemetry / "index.json", {"records": [{"call_id": "call-" + name,
                    "state": "response_received", "status_code": 200,
                    "request_file": "c1/request.json", "usage": {"prompt_tokens": 10,
                        "completion_tokens": 8192, "total_tokens": 8202},
                    "choice_termination": [{"finish_reason": "length", "stop_reason": 8192}]}],
                    "recording_errors": []})
        warmup = {"pipeline": "P05", "sample_id": "warm", "suite": "preflight8", "phase": "warmup",
            "repetition": 1, "observation": "artifacts/P05/warmup-preflight8-r1/warm/observation.json"}
        save(run / warmup["observation"], {**warmup, "input_page_count": 1, "status": "completed",
            "timing": {"processing_seconds": 500.0, "pipeline_initialization_seconds": 7.5}})
        cases.append(warmup)
        save(run / "scores/index.json", {"results": results, "software": {"software_id": "scorer"},
            "reference_freeze": {"id": "synthetic-frozen-v1"},
            "dataset_declaration": {"sample_metadata": metadata}, "unscored": []})
        service = {"role": "glm", "inference_image": "vllm:v0.19.1", "model_name": "GLM-OCR"}
        if arm == "native":
            service["rotary_embedding"] = "native"
        save(run / "run.json", {"run_id": arm, "formal": False, "development_experiment": True,
            "experiment_arm": arm, "suite": "perf80", "cases": cases, "latest_scores": "scores/index.json",
            "software": {"software_id": "execution"}, "state": "completed", "configurations": [{
                "pipeline": "P05", "versions": {"glmocr": "0.1.5"}, "inference_services": [service]}]})
        save(run / "artifacts/P05/inference/inference-ownership.json", {
            "initialization_to_readiness_host_seconds": 123.0})
    return root


def summary(root):
    path = generate_p05_optimization_report(root)
    return json.loads((root / "optimization-summary.json").read_text()), path.read_text()


def test_first_round_quality_three_real_duration_rounds_and_deduplicated_initialization(tmp_path):
    root = experiment(tmp_path)
    result, markdown = summary(root)
    assert result["paired_first_round_membership"] is True
    baseline = result["arms"]["baseline"]
    native = result["arms"]["native"]
    assert baseline["quality"]["micro"]["text"]["strict"]["cer"] == pytest.approx(0.1)
    assert native["quality"]["micro"]["text"]["strict"]["cer"] == pytest.approx(0.02)
    assert baseline["quality"]["samples"] == 2
    assert [item["processing_seconds_including_failures"] for item in baseline["performance_rounds"]] == [3, 5, 7]
    assert baseline["performance_summary"]["median_seconds"] == 5
    assert baseline["warmup"]["processing_seconds_including_failures"] == 500
    assert baseline["initialization"]["sdk_initialization_seconds"] == 7.5
    assert result["configuration_difference_paths"] == ["inference_services[0].rotary_embedding"]
    assert result["comparison_identity"]["quality_attribution_ready"] is True
    assert baseline["performance_rounds"][0]["telemetry"]["finish_reason_length_choices"] == 2
    assert baseline["performance_rounds"][0]["telemetry"]["usage"]["completion_tokens"]["observed_sum"] == 16384
    assert "0.1.5" in markdown and "vllm:v0.19.1" in markdown and "123.0000" in markdown
    assert result["weighted_total_score"] is None
    assert generate_p05_optimization_report(root).read_text() == markdown


def test_failed_first_round_remains_in_quality_denominator_and_processing_cost(tmp_path):
    root = experiment(tmp_path)
    run = root / "native"
    observation_path = run / "artifacts/P05/measured-perf80-r1/b/observation.json"
    observed = json.loads(observation_path.read_text())
    observed.update(status="resource_failed", timing={"processing_seconds": 10.0})
    save(observation_path, observed)
    score_path = run / "scores/r1-b.json"
    score = json.loads(score_path.read_text())
    score.update(status="resource_failed")
    score["metrics"]["unit_presence"].update(tp=0, fn=1)
    score["metrics"]["text"] = text(100)
    save(score_path, score)
    result, _ = summary(root)
    arm = result["arms"]["native"]
    assert arm["quality"]["micro"]["unit_presence"]["recall"] == 0.5
    assert arm["quality"]["failed_samples"] == 1
    assert arm["performance_rounds"][0]["planned_input_pages"] == 3
    assert arm["performance_rounds"][0]["processing_seconds_including_failures"] == 11
    assert arm["performance_rounds"][0]["completed_input_pages"] == 1


def test_missing_score_and_duration_remain_unknown_instead_of_filtered_out(tmp_path):
    root = experiment(tmp_path)
    run = root / "native"
    index_path = run / "scores/index.json"
    index = json.loads(index_path.read_text())
    index["results"].remove("scores/r1-b.json")
    save(index_path, index)
    observed_path = run / "artifacts/P05/measured-perf80-r3/b/observation.json"
    observed = json.loads(observed_path.read_text())
    observed.update(status="not_started", timing={})
    save(observed_path, observed)
    result, markdown = summary(root)
    arm = result["arms"]["native"]
    assert arm["quality"]["target_denominator_complete"] is False
    assert arm["quality"]["micro"] is None
    assert arm["quality"]["planned_samples"] == 2
    assert arm["quality"]["unscored_samples"] == 1
    third = arm["performance_rounds"][2]
    assert third["processing_seconds_including_failures"] is None
    assert third["observed_processing_seconds_subtotal"] == 3
    assert third["planned_input_pages"] == 3
    assert arm["performance_summary"]["median_seconds"] is None
    assert "NA" in markdown


def test_missing_round_member_is_retained_as_planned_unknown(tmp_path):
    root = experiment(tmp_path)
    run_path = root / "native/run.json"
    run = json.loads(run_path.read_text())
    run["cases"] = [case for case in run["cases"] if not (case["phase"] == "measured"
                     and case["repetition"] == 3 and case["sample_id"] == "b")]
    save(run_path, run)
    result, _ = summary(root)
    third = result["arms"]["native"]["performance_rounds"][2]
    assert third["planned_samples"] == 2
    assert third["missing_first_round_members"] == ["b"]
    assert third["timing_complete"] is False
    assert third["processing_seconds_including_failures"] is None


def test_missing_telemetry_usage_or_request_file_does_not_mean_zero_tokens(tmp_path):
    root = experiment(tmp_path)
    telemetry = root / "native/artifacts/P05/measured-perf80-r1/b/telemetry/p0001-glm"
    index = json.loads((telemetry / "index.json").read_text())
    index["records"][0].pop("usage")
    save(telemetry / "index.json", index)
    (telemetry / "c1/request.json").unlink()
    result, _ = summary(root)
    telemetry_summary = result["arms"]["native"]["performance_rounds"][0]["telemetry"]
    usage = telemetry_summary["usage"]["completion_tokens"]
    assert usage["observed_sum"] == 8192
    assert usage["available_calls"] == 1 and usage["total_calls"] == 2 and not usage["complete"]
    assert telemetry_summary["token_cap_observable_calls"] == 1
    assert telemetry_summary["calls"][1]["request_record_available"] is False


def test_formal_run_and_external_paths_rejected_without_reading_dataset(tmp_path):
    root = experiment(tmp_path)
    run_path = root / "native/run.json"
    run = json.loads(run_path.read_text())
    run["formal"] = True
    save(run_path, run)
    with pytest.raises(ValueError, match="nonformal"):
        generate_p05_optimization_report(root)
    run["formal"] = False
    run["latest_scores"] = "../outside.json"
    save(run_path, run)
    with pytest.raises(ValueError, match="escapes"):
        generate_p05_optimization_report(root)


@pytest.mark.parametrize("change", [{"software": {"software_id": "different-scorer"}},
                                  {"reference_freeze": {"id": "different-reference"}},
                                  {"reference_freeze": None}])
def test_mismatched_or_unknown_scoring_identity_blocks_quality_attribution(tmp_path, change):
    root = experiment(tmp_path)
    path = root / "native/scores/index.json"
    index = json.loads(path.read_text())
    index.update(change)
    save(path, index)
    result, markdown = summary(root)
    assert result["comparison_identity"]["quality_attribution_ready"] is False
    assert result["arms"]["native"]["quality"]["micro"]["text"]["strict"]["cer"] == pytest.approx(0.02)
    assert "不能据此宣称优化改善" in markdown
