"""Synthetic metadata/reporting checks without reading repository corpus."""

from __future__ import annotations

import csv
import json

from moparse_eval.cli import report_run, score_run


def test_unscored_cases_keep_frozen_grouping_and_reports_need_no_live_dataset(tmp_path):
    dataset = tmp_path / "synthetic-dataset"
    dataset.mkdir()
    reference = {
        "sample_id": "known", "review_status": "confirmed", "units": [
            {"id": "text", "kind": "text", "status": "confirmed", "pages": [1],
             "literal": "A complete synthetic target paragraph."},
        ],
    }
    (dataset / "reference.json").write_text(json.dumps(reference))
    (dataset / "manifest.json").write_text(json.dumps({
        "name": "synthetic", "kind": "lite", "state": "frozen",
        "suites": {"lite": ["known", "unscored"], "perf80": [], "preflight8": []},
        "documents": [{"document_id": "doc", "family_id": "family", "tags": ["prose"]}],
        "samples": [
            {"id": "known", "document_id": "doc", "evaluation": "reference.json", "source_pages": [1],
             "source_category": "source-unknown", "development_exposure": "exposed"},
            {"id": "unscored", "document_id": "doc", "source_pages": [2],
             "source_category": "source-unknown", "development_exposure": "exposed"},
        ],
    }))
    run = tmp_path / "run"
    run.mkdir()
    cases = []
    for sample_id in ("known", "unscored"):
        observation = {
            "sample_id": sample_id, "pipeline": "P03", "dataset": "synthetic",
            "suite": "quality800", "phase": "measured", "repetition": 1,
            "status": "not_processed_due_to_unresolved_execution", "pages": [],
            "input_page_count": 1, "timing": {"processing_seconds": None},
            "runtime": {"sdk_initialization": "once_per_persistent_pipeline_worker"},
        }
        (run / f"{sample_id}.json").write_text(json.dumps(observation))
        cases.append({**{key: observation[key] for key in (
            "sample_id", "pipeline", "suite", "phase", "repetition",
        )}, "observation": f"{sample_id}.json"})
    (run / "run.json").write_text(json.dumps({
        "run_id": "synthetic", "dataset": str(dataset), "dataset_name": "synthetic",
        "formal": True, "state": "completed", "cases": cases,
    }))
    (run / "maintenance.json").write_text(json.dumps({
        "phase": "restored", "tts_policy": "keep_running",
        "tts_identity_condition": {"status": "unchanged"},
        "tts_no_calls_condition": {"status": "no_observed_activity"},
    }))
    index = json.loads(score_run(run).read_text())
    assert index["unscored"][0]["family_id"] == "family"
    assert index["unscored"][0]["development_exposure"] == "exposed"
    scored = json.loads((run / index["results"][0]).read_text())
    assert scored["metrics"]["unit_presence"]["target_units"] == 1
    assert scored["metrics"]["unit_presence"]["fn"] == 1
    assert scored["status"] == "not_processed_due_to_unresolved_execution"
    dataset.rename(tmp_path / "dataset-offline")
    rendered = report_run(run).read_text()
    summary = json.loads((run / "summary.json").read_text())
    group = summary["groups"][0]
    assert group["quality"]["by_family"]["family"]["samples"] == 2
    assert group["quality"]["by_tag"]["prose"]["input_pages"] == 2
    assert group["quality"]["unscored_samples"] == 1
    assert group["performance"]["round_duration_summary"]["median_seconds"] is None
    assert len(group["runtime_records"]) == 2
    with (run / "quality-slices.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert any(row["scope"] == "family" and row["scope_key"] == "family" for row in rows)
    csv_before = (run / "quality-slices.csv").read_bytes()
    comparison_before = (run / "group-comparisons.md").read_bytes()
    assert report_run(run).read_text() == rendered
    assert (run / "quality-slices.csv").read_bytes() == csv_before
    assert (run / "group-comparisons.md").read_bytes() == comparison_before
