"""Paired service reporting reads invented score/run artifacts only."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import pytest

from moparse_eval.scoring import score_case
from moparse_eval.service_report import REPORT_VERSION, render_service_report


def _json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_information_coverage_loss_includes_a_field_that_becomes_unresolved():
    from moparse_eval.service_report import _changes
    before = {'index': 0, 'status': 'compared', 'content_exact': True,
              'information': {'status': 'correct'}}
    after = {'index': 0, 'status': 'unresolved', 'content_exact': None}
    changes = _changes(before, after, is_field=True)
    assert changes['information_target_success'] == {'delta': -1, 'transition': 'loss'}


def _score(sample: str, *, good: bool):
    reference = {
        "sample_id": sample, "document_id": "invented-document-" + sample,
        "family_id": "invented-family", "review_status": "confirmed", "relations": [],
        "units": [
            {"id": "sentence", "kind": "text", "status": "confirmed", "pages": [1],
             "literal": "An invented ordinary sentence."},
            {"id": "record", "kind": "table_record", "status": "confirmed", "pages": [1],
             "literal": "Revenue Current 13.25", "table": {
                 "row_header_path": ["Revenue"],
                 "fields": [{"column_header_path": ["Current"], "value": "13.25"}],
             }},
        ],
    }
    observation = {
        "sample_id": sample, "pipeline": "P07", "status": "completed", "relations": [],
        "suite": "quality800", "phase": "measured", "repetition": 1, "input_page_count": 1,
        "pages": [{"page": 1, "blocks": [
            {"id": "text", "kind": "text", "text": "An invented ordinary sentence." if good else "An invented ordinary sentenxe."},
            {"id": "table", "kind": "table", "cells": [
                {"id": "header", "row": 0, "col": 1, "text": "Current"},
                {"id": "label", "row": 1, "col": 0, "text": "Revenue"},
                {"id": "value", "row": 1, "col": 1, "text": "13.25" if good else "-13.25"},
            ]},
        ]}],
    }
    return score_case(reference, observation)


@pytest.fixture
def service_run(tmp_path):
    directory = tmp_path / "service-run"
    entries, cases = [], []
    for index, sample in enumerate(("gain", "loss")):
        baseline = _score(sample, good=index == 1)
        final = _score(sample, good=index == 0)
        # Deliberately make the old native time very large. It is not a new
        # service/end-to-end observation and must never be added to timings.
        baseline["timing"] = {"processing_seconds": 1000000}
        paths = {side + "_score": f"scores/{sample}-{side}.json" for side in ("baseline", "final")}
        for side, score in (("baseline", baseline), ("final", final)):
            _json(directory / paths[side + "_score"], score)
        common = {"case_id": sample, "sample_id": sample, "suite": "quality800", "phase": "measured", "repetition": 1}
        entries.append({**common, **paths})
        cases.append({**common, "input_pages": 1, "document_id": baseline["document_id"],
                      "family_id": baseline["family_id"], "status": "completed", "observation": f"output/{sample}.json",
                      "timing": {"postprocessing_seconds": index + 1.25},
                      "conversion": {"converted": 1 - index, "retained": index, "unknown": index}})
    for repetition, seconds in enumerate((0.5, 0.75, 1.0), 1):
        cases.append({"case_id": f"perf-r{repetition}", "sample_id": "perf",
                      "suite": "perf80", "phase": "measured", "repetition": repetition,
                      "input_pages": 1, "status": "completed", "timing": {"postprocessing_seconds": seconds}})
    cases.append({"case_id": "warm", "sample_id": "warm", "suite": "preflight8", "phase": "warmup",
                  "repetition": 1, "input_pages": 1, "timing": {"postprocessing_seconds": 100}})
    _json(directory / "run.json", {
        "run_id": "invented-service-run", "report_version": "service-v1", "cases": cases,
        "render_figures": False, "baseline_run": "existing-native-run",
        "reference_adjudications": {"path": "/never-open/expected/reference.json"},
        "execution_environment": {"deployment_status": "not_deployed", "network": "none", "gpu": "none"},
        "service_config": {"semantic_table_output_enabled": True, "api_key": "invented-secret"},
    })
    _json(directory / "scores/index.json", {"schema": "moparse-service-scores/1", "score_id": "invented-score", "results": entries})
    return directory


def test_report_uses_equal_scope_pairs_denominators_and_preserves_all_inputs(service_run):
    inputs = [service_run / "run.json", service_run / "scores/index.json", *sorted((service_run / "scores").glob("*-*.json"))]
    before = {path: path.read_bytes() for path in inputs}
    destination = render_service_report(service_run)
    summary = _read(service_run / "summary.json")
    assert destination == service_run / "report.md"
    assert {path: path.read_bytes() for path in inputs} == before
    quality = summary["quality"]
    assert quality["declared_cases"] == quality["paired_cases"] == 2
    assert quality["declared_pages"] == quality["paired_pages"] == 2
    assert quality["baseline"]["micro"]["table_records"]["target_fields"] == 2
    assert quality["final"]["micro"]["table_records"]["field_target_correctness"]["value"] == 0.5
    assert summary["metadata"]["service_config"]["api_key"] == "[redacted]"
    assert summary["unit_transitions"]["content_exact"] == {"gain": 1, "loss": 1}
    assert summary["unit_transitions"]["field_target_success"] == {"gain": 1, "loss": 1}
    assert len(summary["by_document"]) == 2 and len(summary["by_family"]) == 1
    assert summary["conversion"]["converted"]["count"] == 1
    assert summary["performance"]["quality800"]["complete_timing_rounds"] == 1
    assert summary["performance"]["quality800"]["median_postprocessing_seconds"] == 3.5
    assert summary["performance"]["perf80"]["complete_timing_rounds"] == 3
    assert summary["performance"]["perf80"]["median_postprocessing_seconds"] == 0.75
    text = destination.read_text(encoding="utf-8")
    assert "service-v1" in text and REPORT_VERSION in text and "尚未部署" in text
    assert "(1 / 2)" in text and "1000000" not in text and "invented-secret" not in text
    assert "不含" not in summary["reproduction_command"]
    assert str(service_run / "run.json") in summary["reproduction_command"]
    assert "CER 差" in (service_run / "appendix.md").read_text()
    with (service_run / "paired-units.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6 and {row["sample_id"] for row in rows} == {"gain", "loss"}


def test_stage_quality_uses_the_same_reference_scope_and_keeps_timing_separate(service_run):
    path = service_run / "scores/index.json"
    index = _read(path)
    names = ("bridge_pages", "source_pages", "native_pages", "exported", "assets", "final")
    for entry in index["results"]:
        entry["stage_scores"] = [{
            "stage": name, "score": entry["baseline_score"] if i < 2 else entry["final_score"],
            "scope": "diagnostic_page_export" if i < 3 else "actual_document_rendering",
        } for i, name in enumerate(names)]
    _json(path, index)
    render_service_report(service_run)
    summary = _read(service_run / "summary.json")
    assert [stage["stage"] for stage in summary["stage_quality"]] == list(names)
    assert all(stage["complete"] and stage["scored_cases"] == 2 for stage in summary["stage_quality"])
    assert summary["stage_quality"][0]["quality"]["micro"] == summary["quality"]["baseline"]["micro"]
    assert summary["stage_quality"][-1]["quality"]["micro"] == summary["quality"]["final"]["micro"]
    assert summary["performance"]["quality800"]["median_postprocessing_seconds"] == 3.5
    assert "不是独立消融实验" in (service_run / "report.md").read_text()


def test_incomplete_stage_is_unknown_instead_of_a_score_on_a_smaller_easier_scope(service_run):
    path = service_run / "scores/index.json"
    index = _read(path)
    index["results"][0]["stage_scores"] = [{
        "stage": "native_pages", "score": index["results"][0]["final_score"],
        "scope": "diagnostic_page_export",
    }]
    _json(path, index)
    render_service_report(service_run)
    stages = _read(service_run / "summary.json")["stage_quality"]
    native = next(stage for stage in stages if stage["stage"] == "native_pages")
    assert native["scored_cases"] == 1 and native["declared_cases"] == 2
    assert not native["complete"] and native["quality"] == {}


def test_primary_scoring_checkpoint_cannot_be_published_as_a_completed_report(service_run):
    path = service_run / "scores/index.json"
    index = _read(path)
    index["state"] = "primary_complete_stages_pending"
    _json(path, index)
    with pytest.raises(ValueError, match="stage scoring is still pending"):
        render_service_report(service_run)


def test_missing_final_score_remains_declared_unpaired_and_does_not_look_perfect(service_run):
    (service_run / "scores/loss-final.json").unlink()
    render_service_report(service_run)
    summary = _read(service_run / "summary.json")
    assert summary["quality"]["declared_pages"] == 2 and summary["quality"]["paired_pages"] == 1
    assert summary["quality"]["pair_status_counts"] == {"paired": 1, "missing_or_invalid_score": 1}
    units = _read(service_run / "paired-units.json")["pairs"]
    missing = [row for row in units if row["sample_id"] == "loss"]
    assert missing and all(row["pair_status"] == "missing_final" and not row["changes"] for row in missing)
    assert summary["samples"][1]["delta"]["strict_cer"] is None


def test_different_reference_scope_is_never_interpreted_as_a_quality_gain(service_run):
    path = service_run / "scores/gain-final.json"
    score = _read(path)
    score["metrics"]["text"]["strict"]["reference_chars"] += 1
    _json(path, score)
    render_service_report(service_run)
    summary = _read(service_run / "summary.json")
    assert summary["quality"]["pair_status_counts"]["reference_scope_mismatch"] == 1
    assert summary["samples"][0]["delta"]["strict_cer"] is None
    units = _read(service_run / "paired-units.json")["pairs"]
    assert all(not row["changes"] for row in units if row["sample_id"] == "gain")


def test_unit_pairing_uses_ids_and_field_indices_not_text_or_list_order(service_run):
    path = service_run / "scores/gain-final.json"
    score = _read(path)
    score["units"].reverse()
    _json(path, score)
    render_service_report(service_run)
    fields = [row for row in _read(service_run / "paired-units.json")["pairs"]
              if row["sample_id"] == "gain" and row["field_index"] == 0]
    assert len(fields) == 1 and fields[0]["unit_id"] == "record"
    assert fields[0]["changes"]["content_exact"]["transition"] == "gain"


def test_failed_scored_case_and_partial_performance_keep_cost_and_quality_denominators(service_run):
    path = service_run / "scores/loss-final.json"
    score = _read(path)
    score["status"] = "failed"
    _json(path, score)
    path = service_run / "run.json"
    run = _read(path)
    run["cases"][1]["status"] = "failed"
    run["cases"][3]["status"] = "partial"
    _json(path, run)
    render_service_report(service_run)
    summary = _read(service_run / "summary.json")
    assert summary["quality"]["paired_cases"] == 2
    assert summary["quality"]["final"]["failed_samples"] == 1
    assert summary["quality"]["final"]["micro"]["table_records"]["target_fields"] == 2
    assert summary["performance"]["perf80"]["complete_timing_rounds"] == 3
    assert summary["performance"]["perf80"]["rounds"][1]["status_counts"] == {"partial": 1}


def test_missing_performance_measurement_is_na_and_not_zero_cost(service_run):
    path = service_run / "run.json"
    run = _read(path)
    run["cases"][3]["timing"] = {}
    _json(path, run)
    render_service_report(service_run)
    performance = _read(service_run / "summary.json")["performance"]["perf80"]
    assert performance["complete_timing_rounds"] == 2
    assert performance["rounds"][1]["postprocessing_seconds"] is None
    assert performance["rounds"][1]["observed_seconds_subtotal"] is None


def test_report_only_opens_declared_run_score_files_not_observations_or_references(service_run, monkeypatch):
    original = Path.read_text
    allowed = {"run.json", "index.json", "gain-baseline.json", "gain-final.json", "loss-baseline.json", "loss-final.json"}

    def guarded(path, *args, **kwargs):
        assert path.name in allowed, f"unexpected report input: {path}"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    render_service_report(service_run)


def test_duplicate_case_or_score_identity_is_not_silently_selected(service_run):
    path = service_run / "scores/index.json"
    index = _read(path)
    index["results"].append(copy.deepcopy(index["results"][0]))
    _json(path, index)
    with pytest.raises(ValueError, match="duplicate paired score"):
        render_service_report(service_run)


def test_report_cannot_overwrite_a_declared_score_input(service_run):
    index_path = service_run / "scores/index.json"
    index = _read(index_path)
    original = (service_run / "scores/gain-baseline.json").read_bytes()
    collision = service_run / "summary.json"
    collision.write_bytes(original)
    index["results"][0]["baseline_score"] = "summary.json"
    _json(index_path, index)
    with pytest.raises(ValueError, match="overwrite"):
        render_service_report(service_run)
    assert collision.read_bytes() == original


def test_figures_are_generated_only_from_new_synthetic_summary_with_font_rules(service_run):
    path = service_run / "run.json"
    run = _read(path)
    run["render_figures"] = True
    _json(path, run)
    render_service_report(service_run)
    summary = _read(service_run / "summary.json")
    assert len(summary["figures"]) == 2
    for entry in summary["figures"]:
        for extension in ("png", "svg", "pdf"):
            assert (service_run / entry[extension]).is_file()
        svg = (service_run / entry["svg"]).read_text()
        assert "DejaVu Sans" in svg and "Noto Sans CJK SC" in svg and "sans-serif" in svg
    import pymupdf

    with pymupdf.open(service_run / summary["figures"][0]["pdf"]) as document:
        fonts = [font[3] for page in document for font in page.get_fonts()]
    assert fonts and all("Times" not in name for name in fonts)


def test_field_transition_ledger_excludes_unresolved_text_and_unscoped_fields(tmp_path):
    reference = {
        "sample_id": "scope-proof", "review_status": "confirmed", "relations": [],
        "units": [
            {"id": "ordinary", "kind": "text", "status": "confirmed", "pages": [1], "literal": "7"},
            {"id": "record", "kind": "table_record", "status": "confirmed", "pages": [1],
             "literal": "Revenue Current 13.25", "table": {
                 "row_header_path": ["Revenue"],
                 "fields": [{"column_header_path": ["Current"], "value": "13.25"}],
             }},
            {"id": "unscoped", "kind": "table_record", "status": "confirmed", "pages": [1],
             "literal": "Unknown Current 42", "table": {
                 "row_header_path": ["Unknown"], "row_binding": {"status": "unknown"},
                 "fields": [{"column_header_path": ["Current"], "value": "42"}],
             }},
        ],
    }
    observation = {
        "sample_id": "scope-proof", "pipeline": "P07", "status": "completed", "relations": [],
        "pages": [{"page": 1, "blocks": [
            {"id": "number", "kind": "text", "text": "7"},
            {"id": "table", "kind": "table", "cells": [
                {"id": "label", "row": 1, "col": 0, "text": "Revenue"},
                {"id": "value", "row": 1, "col": 1, "text": "13.25"},
            ]},
        ]}],
    }
    score = score_case(reference, observation)
    assert next(unit for unit in score["units"] if unit["id"] == "ordinary")["status"] == "unresolved"
    assert score["metrics"]["table_records"]["target_fields"] == 1
    assert score["metrics"]["table_records"]["source_unscoped_fields"] == 1
    directory = tmp_path / "scope-proof"
    _json(directory / "run.json", {"run_id": "scope-proof", "render_figures": False, "cases": [
        {"case_id": "scope-proof", "sample_id": "scope-proof", "suite": "quality800", "phase": "measured",
         "repetition": 1, "input_pages": 1, "timing": {"postprocessing_seconds": 1}, "status": "completed"},
    ]})
    for side in ("baseline", "final"):
        _json(directory / f"scores/{side}.json", score)
    _json(directory / "scores/index.json", {"results": [
        {"case_id": "scope-proof", "baseline_score": "scores/baseline.json", "final_score": "scores/final.json"},
    ]})
    render_service_report(directory)
    summary = _read(directory / "summary.json")
    assert summary["unit_transitions"]["field_target_success"] == {"unchanged": 1}
    assert summary["report_generator"]["version"] == "moparse-service-paired-report-6"
    assert summary["report_generator"]["source_sha256"]
    pairs = _read(directory / "paired-units.json")["pairs"]
    assert all("field_target_success" not in row["changes"] for row in pairs if row["field_index"] is None)
    assert all("field_target_success" not in row["changes"] for row in pairs if row["unit_id"] == "unscoped")


def test_all_na_quality_can_render_figures_before_scores_exist(service_run):
    path = service_run / "run.json"
    run = _read(path)
    run["render_figures"] = True
    _json(path, run)
    _json(service_run / "scores/index.json", {"score_id": "pending", "results": []})
    render_service_report(service_run)
    summary = _read(service_run / "summary.json")
    assert summary["quality"]["declared_cases"] == 2
    assert summary["quality"]["paired_cases"] == 0
    assert summary["quality"]["pair_status_counts"] == {"missing_or_invalid_score": 2}
    assert all(value is None for value in summary["quality"]["delta"].values())
    assert len(summary["figures"]) == 2
    assert "NA" in (service_run / "report.md").read_text()


def test_withdrawn_service_scores_cannot_regenerate_an_obsolete_report(service_run):
    path = service_run / "run.json"
    run = _read(path)
    run["scoring_status"] = "withdrawn"
    _json(path, run)
    with pytest.raises(ValueError, match="scores were withdrawn"):
        render_service_report(service_run)
