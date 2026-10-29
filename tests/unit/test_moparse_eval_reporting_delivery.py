"""Reporting delivery contracts exercised only with invented software records."""

from __future__ import annotations

import copy

import pytest

from moparse_eval import reporting


def _text_counts() -> dict:
    counts = {
        "distance": 1, "substitutions": 1, "deletions": 0, "insertions": 0,
        "reference_chars": 10, "hypothesis_chars": 10,
    }
    return {"units": 1, "strict": dict(counts), "width_equivalent": dict(counts)}


def _result(**changes) -> dict:
    result = {
        "pipeline": "P01", "dataset": "synthetic-lite", "suite": "quality800",
        "sample_id": "synthetic-sample-a", "document_id": "synthetic-doc-a",
        "family_id": "synthetic-family-a", "source_category": "source-unknown",
        "development_exposure": "synthetic-author-read", "tags": ["synthetic-table"],
        "phase": "measured", "repetition": 1, "run_id": "synthetic-run",
        "status": "completed", "scorer_status": "evaluated", "input_page_count": 2,
        "timing": {"processing_seconds": 2.0, "pipeline_initialization_seconds": 1.25},
        "resources": {"worker_cpu_seconds": 0.5},
        "runtime": {
            "versions": {"synthetic-sdk": "runtime-version-111"},
            "model_identity": "synthetic-model-revision",
            "batch_orchestration_seconds": 9876.0,
            "cuda_graphs": {"status": "synthetic_capture_evidence"},
        },
        "coverage": {
            "declared_units": 4, "confirmed_units": 4, "scored_units": 4,
            "localized_units": 3, "text_reference_chars": 10,
            "text_aligned_reference_chars": 10,
        },
        "metrics": {
            "unit_presence": {"tp": 3, "fp": None, "fn": 1},
            "text": _text_counts(),
            "relations": {"tp": 1, "fp": None, "fn": 1, "observable": 1, "unresolved": 1,
                          "by_type": {"before": {"numerator": 1, "denominator": 2,
                                                 "observable": 1, "endpoint_unresolved": 1}}},
            "table_records": {
                "target_records": 1, "located_records": 1, "target_fields": 4,
                "observable_fields": 3,
                "compared_fields": 3, "target_missing_fields": 0, "unresolved_fields": 1,
                "correct_fields": 3, "strict_correct_fields": 2,
                "field_target_correctness": {"numerator": 3, "denominator": 4},
                "field_compared_accuracy": {"numerator": 3, "denominator": 3},
                "field_strict_accuracy": {"numerator": 2, "denominator": 3},
                "field_strict_target_correctness": {"numerator": 2, "denominator": 4},
                "field_comparison_coverage": {"numerator": 3, "denominator": 4},
                "field_text": _text_counts(),
            },
        },
    }
    result.update(changes)
    return result


def _group(report: dict, *, pipeline="P01", suite="quality800") -> dict:
    return next(group for group in report["groups"]
                if group["pipeline"] == pipeline and group["suite"] == suite)


def test_quality_slices_cover_sample_document_family_tag_source_and_exposure():
    result = _result()
    before = copy.deepcopy(result)
    report = reporting.aggregate_reports([result])
    rows = report["quality_slices"]
    expected = {
        ("sample", "synthetic-sample-a"),
        ("document", "synthetic-doc-a"),
        ("family", "synthetic-family-a"),
        ("tag", "synthetic-table"),
        ("source", "source-unknown"),
        ("development_exposure", "synthetic-author-read"),
    }
    assert {(row["scope"], row["scope_key"]) for row in rows} == expected
    assert all((row["pipeline"], row["dataset"], row["suite"])
               == ("P01", "synthetic-lite", "quality800") for row in rows)
    assert isinstance(reporting.QUALITY_SLICE_COLUMNS, tuple)
    assert all(set(reporting.QUALITY_SLICE_COLUMNS) <= set(row) for row in rows)
    expected_counts = {
        "text_reference_chars": 10, "text_aligned_reference_chars": 10,
        "content_targets": 4, "content_located": 3,
        "table_field_targets": 4, "table_field_correct": 3, "table_fields_observable": 3,
        "relation_targets": 2, "relation_correct": 1,
        "relation_observable": 1, "relation_unresolved": 1,
        "declared_units": 4, "confirmed_units": 4, "scored_units": 4, "localized_units": 3,
        "failed_samples": 0, "unscored_samples": 0,
    }
    for row in rows:
        for name, expected_count in expected_counts.items():
            assert row[name] == expected_count
        for name, expected_rate in {
            "strict_cer": 0.1, "strict_edit_similarity": 0.9, "content_recall": 0.75,
            "table_field_target_correctness": 0.75, "relation_recall": 0.5,
        }.items():
            assert row[name] == pytest.approx(expected_rate)
            assert row[f"macro_document_{name}"] == pytest.approx(expected_rate)
            assert row[f"macro_document_{name}_available_documents"] == 1
            assert row[f"macro_document_{name}_total_documents"] == 1
    assert result == before


def test_performance_repetitions_and_warmup_do_not_create_quality_slice_rows():
    quality = _result()
    performance = [
        _result(sample_id="synthetic-perf-only", suite="perf80", repetition=repetition,
                timing={"processing_seconds": float(repetition)})
        for repetition in (1, 2, 3)
    ]
    warmup = _result(sample_id="synthetic-warmup-only", suite="preflight8", phase="warmup")
    report = reporting.aggregate_reports([quality, *performance, warmup])
    rows = report["quality_slices"]
    assert rows and {row["suite"] for row in rows} == {"quality800"}
    sample_keys = {row["scope_key"] for row in rows if row["scope"] == "sample"}
    assert sample_keys == {"synthetic-sample-a"}
    perf = _group(report, suite="perf80")
    assert perf["quality"]["metrics"] is None
    assert perf["performance"]["round_duration_summary"]["n"] == 3
    assert perf["performance"]["round_duration_summary"]["median_seconds"] == 2


def test_duplicate_quality_runs_are_blocked_instead_of_selecting_one_run():
    first = _result()
    duplicate = _result(run_id="different-run", timing={"processing_seconds": 100.0})
    report = reporting.aggregate_reports([first, duplicate])
    assert _group(report)["quality"]["status"] == "duplicate_quality_runs_require_explicit_run_selection"
    assert report["quality_slices"] == []


def test_runtime_records_preserve_identity_without_adding_orchestration_to_cost():
    result = _result()
    report = reporting.aggregate_reports([result])
    group = _group(report)
    assert group["runtime_records"] == [{
        "sample_id": result["sample_id"], "phase": "measured", "repetition": 1,
        "run_id": "synthetic-run", "runtime": result["runtime"],
    }]
    performance = group["performance"]
    assert performance["rounds"][0]["processing_seconds_including_failures"] == 2.0
    assert performance["initialization"][0]["initialization_seconds"] == 1.25
    assert performance["resource_observations"][0]["worker_cpu_seconds"] == 0.5


def test_new_table_ledger_aggregates_equivalent_and_strict_scores_without_zero_filling():
    inputs = [_result(), _result(sample_id="synthetic-second")]
    before = copy.deepcopy(inputs)
    report = reporting.aggregate_reports(inputs)
    table = _group(report)["quality"]["micro"]["table_records"]
    assert {key: table[key] for key in ("target_fields", "compared_fields", "target_missing_fields",
                                       "unresolved_fields", "correct_fields", "strict_correct_fields")} == {
        "target_fields": 8, "compared_fields": 6, "target_missing_fields": 0,
        "unresolved_fields": 2, "correct_fields": 6, "strict_correct_fields": 4,
    }
    assert table["field_target_correctness"]["value"] == 0.75
    assert table["field_compared_accuracy"]["value"] == 1
    assert table["field_strict_accuracy"]["value"] == pytest.approx(2 / 3)
    assert table["field_strict_target_correctness"]["value"] == 0.5
    appendix = reporting.render_appendix(report)
    for name in ("field_compared_accuracy", "field_strict_accuracy", "field_strict_target_correctness",
                 "target_missing_fields", "unresolved_fields"):
        assert f"table_records.{name}" in appendix
    assert "目标格未取到值不证明全输出遗漏" in appendix
    assert inputs == before


@pytest.mark.parametrize("unknown", ["absent", None])
def test_table_ledger_mixed_schema_keeps_missing_counts_and_new_rates_unknown(unknown):
    first, second = _result(), _result(sample_id="synthetic-legacy")
    table = second["metrics"]["table_records"]
    if unknown == "absent":
        table.pop("compared_fields")
    else:
        table["compared_fields"] = None
    result = _group(reporting.aggregate_reports([first, second]))["quality"]["micro"]["table_records"]
    assert result["compared_fields"] is None
    assert result["target_missing_fields"] == 0
    for metric in ("field_target_correctness", "field_compared_accuracy", "field_strict_accuracy"):
        assert result[metric] == {"numerator": None, "denominator": None, "value": None}


def test_failed_missing_measurement_keeps_na_and_known_failure_cost_stays_separate():
    missing = _result(sample_id="synthetic-not-started", status="not_started", timing={})
    failed = _result(sample_id="synthetic-failed", status="timed_out",
                     timing={"processing_seconds": 8.0})
    report = reporting.aggregate_reports([missing, failed])
    performance = _group(report)["performance"]
    round_ = performance["rounds"][0]
    assert round_["processing_seconds_including_failures"] is None
    assert round_["observed_processing_seconds_subtotal"] == 8
    assert round_["completed_pages_per_second_including_failure_cost"] is None
    assert performance["failed_runs"] == 2
    assert performance["round_duration_summary"]["n"] == 0
    assert "NA" in reporting.render_appendix(report)


def test_successful_run_cost_is_unknown_when_all_performance_runs_are_unstarted():
    inputs = [
        _result(suite="perf80", repetition=repetition,
                status="not_processed_due_to_unresolved_execution", timing={})
        for repetition in (1, 2, 3)
    ]
    before = copy.deepcopy(inputs)
    performance = _group(reporting.aggregate_reports(inputs), suite="perf80")["performance"]
    assert performance["successful_run_throughput"] == {
        "pages": 0, "processing_seconds": None, "pages_per_second": None, "denominator_runs": 0,
    }
    assert performance["round_duration_summary"]["n"] == 0
    assert all(row["processing_seconds_including_failures"] is None for row in performance["rounds"])
    assert inputs == before


def test_only_measured_failure_cost_does_not_become_successful_run_cost():
    inputs = [_result(status="resource_failed", timing={"processing_seconds": 5.0})]
    before = copy.deepcopy(inputs)
    performance = _group(reporting.aggregate_reports(inputs))["performance"]
    assert performance["successful_run_throughput"] == {
        "pages": 0, "processing_seconds": None, "pages_per_second": None, "denominator_runs": 0,
    }
    assert performance["measured_runs"] == 1
    assert performance["rounds"][0]["processing_seconds_including_failures"] == 5.0
    assert performance["rounds"][0]["observed_processing_seconds_subtotal"] == 5.0
    assert inputs == before


def test_successful_run_cost_keeps_only_actual_successful_measurements():
    inputs = [
        _result(sample_id="synthetic-success", input_page_count=2,
                timing={"processing_seconds": 2.0}),
        _result(sample_id="synthetic-failed", status="resource_failed", input_page_count=3,
                timing={"processing_seconds": 5.0}),
        _result(sample_id="synthetic-unstarted", status="not_started", timing={}),
    ]
    before = copy.deepcopy(inputs)
    performance = _group(reporting.aggregate_reports(inputs))["performance"]
    assert performance["successful_run_throughput"] == {
        "pages": 2, "processing_seconds": 2.0, "pages_per_second": 1.0, "denominator_runs": 1,
    }
    assert performance["rounds"][0]["observed_processing_seconds_subtotal"] == 7.0
    assert performance["rounds"][0]["processing_seconds_including_failures"] is None
    assert inputs == before


def test_quality_comparison_markdown_names_each_scope_and_links_deliverables():
    report = reporting.aggregate_reports([_result()])
    comparisons = reporting.render_quality_slices(report)
    for identity in ("synthetic-sample-a", "synthetic-doc-a", "synthetic-family-a",
                     "synthetic-table", "source-unknown", "synthetic-author-read"):
        assert identity in comparisons
    for label in ("定位", "CER", "相似度", "字段", "阅读顺序", "分母"):
        assert label in comparisons
    assert "0.7500" in comparisons
    assert "0.1000" in comparisons
    assert "0.9000" in comparisons
    assert "0.5000" in comparisons
    rendered = reporting.render_appendix(report)
    assert "quality-slices.csv" in rendered
    assert "group-comparisons.md" in rendered


def test_appendix_relation_denominators_distinguish_output_targets_and_f1_terms():
    result = _result()
    result["metrics"]["relations"] = {"tp": 3, "fp": 1, "fn": 2}
    report = reporting.aggregate_reports([result])
    before = copy.deepcopy(report)
    rendered = reporting.render_appendix(report)
    assert "| relations.precision | 0.7500 | 4 |" in rendered
    assert "| relations.recall | 0.6000 | 5 |" in rendered
    assert "| relations.f1 | 0.6667 | 9 |" in rendered
    assert "precision分母为output_units（TP+FP）" in rendered
    assert "recall分母为target_units（TP+FN）" in rendered
    assert "F1分母为2TP+FP+FN" in rendered
    assert report == before


def test_appendix_nonexhaustive_relations_never_borrow_closed_subset_or_pair_scores():
    closed = _result(sample_id="synthetic-closed-relations")
    closed["metrics"]["relations"] = {"tp": 3, "fp": 1, "fn": 2}
    open_scope = _result(sample_id="synthetic-open-relations")
    open_scope["metrics"]["relations"] = {
        "tp": 1, "fp": None, "fn": 1,
        "by_type": {"reading_order": {
            "numerator": 1, "denominator": 2,
            "pair_classification": {"tp": 1, "fp": 0, "fn": 1},
        }},
    }
    report = reporting.aggregate_reports([closed, open_scope])
    relation = _group(report)["quality"]["micro"]["relations"]
    assert relation["exhaustive_scope_precision"]["value"] == 0.75
    assert relation["by_type"]["reading_order"]["pair_classification"]["precision"] == 1
    before = copy.deepcopy(report)
    rendered = reporting.render_appendix(report)
    assert "| relations.precision | NA | NA |" in rendered
    assert "| relations.recall | 0.5714 | 7 |" in rendered
    assert "| relations.f1 | NA | NA |" in rendered
    assert "非穷尽参考的全局precision和F1保持NA" in rendered
    assert report == before


@pytest.mark.parametrize("tp,fp,fn,expected", [
    (0, 0, 0, (("NA", 0), ("NA", 0), ("NA", 0))),
    (0, 2, 3, (("0.0000", 2), ("0.0000", 3), ("0.0000", 5))),
])
def test_appendix_zero_relation_counts_do_not_turn_unknown_rates_into_zero(tp, fp, fn, expected):
    result = _result()
    result["metrics"]["relations"] = {"tp": tp, "fp": fp, "fn": fn}
    report = reporting.aggregate_reports([result])
    before = copy.deepcopy(report)
    rendered = reporting.render_appendix(report)
    for name, (value, denominator) in zip(("precision", "recall", "f1"), expected, strict=True):
        assert f"| relations.{name} | {value} | {denominator} |" in rendered
    assert "零分母的比率未定义" in rendered
    assert report == before


@pytest.mark.parametrize("missing_key", ["tp", "fp", "fn"])
@pytest.mark.parametrize("unknown", ["absent", None])
def test_appendix_f1_denominator_requires_every_existing_counter(missing_key, unknown):
    report = reporting.aggregate_reports([_result()])
    relation = {
        "tp": 3, "fp": 1, "fn": 2, "output_units": 4, "target_units": 5,
        "precision": 0.75, "recall": 0.6, "f1": None,
    }
    if unknown == "absent":
        relation.pop(missing_key)
    else:
        relation[missing_key] = None
    _group(report)["quality"]["micro"]["relations"] = relation
    before = copy.deepcopy(report)
    rendered = reporting.render_appendix(report)
    assert "| relations.precision | 0.7500 | 4 |" in rendered
    assert "| relations.recall | 0.6000 | 5 |" in rendered
    assert "| relations.f1 | NA | NA |" in rendered
    assert report == before


@pytest.mark.parametrize("count", ["absent", None, 0])
def test_appendix_missing_quality_counts_are_na_and_confirmed_zero_stays_zero(count):
    report = reporting.aggregate_reports([_result()])
    quality = _group(report)["quality"]
    known = {} if count == "absent" else {"count": count}
    metric = {"value": None, "recall": None, "cer": None}
    for field in ("target_units", "denominator", "reference_chars"):
        if "count" in known:
            metric[field] = known["count"]
    quality["micro"] = {
        "unit_presence": dict(metric),
        "text": {"strict": dict(metric), "width_equivalent": dict(metric)},
        "table_records": {
            "field_target_correctness": dict(metric),
            "field_text": {"strict": dict(metric), "width_equivalent": dict(metric)},
        },
        "relations": dict(metric),
    }
    quality["coverage"] = {}
    quality.pop("unscored_samples", None)
    if "count" in known:
        quality["unscored_samples"] = known["count"]
        quality["coverage"] = {key: known["count"] for key in (
            "known_image_targets", "image_automatic_identity_targets",
            "image_output_visual_review_targets",
        )}
    before = copy.deepcopy(report)
    rendered = reporting.render_appendix(report)
    expected = "0" if count == 0 else "NA"
    for label in ("unit_presence", "table_records.field_target_correctness"):
        assert f"| {label} | NA | {expected} |" in rendered
    for label in ("text 严格CER", "text 排版等价CER", "table_records 已定位字段严格CER",
                  "table_records 已定位字段排版等价CER"):
        assert f"| {label} | NA | {expected}字符 |" in rendered
    for label in ("无质量评分样本", "已确认图片目标", "可自动对应目标",
                  "纳入统一量化评分的输出视觉保全目标"):
        assert f"{label}：{expected}" in rendered
    assert "| unit_exact | NA | NA |" in rendered
    assert "| relations.precision | NA | NA |" in rendered
    assert f"| relations.recall | NA | {expected} |" in rendered
    assert "| relations.f1 | NA | NA |" in rendered
    assert report == before


def _dataset_declaration() -> dict:
    return {
        "name": "synthetic-lite", "kind": "lite", "state": "frozen",
        "freeze_record": {"reviewer": "synthetic-only"},
        "suites": {"lite": ["synthetic-sample-a", "synthetic-sample-b"],
                   "perf80": ["synthetic-sample-a"], "preflight8": ["synthetic-sample-b"]},
        "sample_metadata": {
            "synthetic-sample-a": {
                "document_id": "synthetic-doc-a", "family_id": "synthetic-family-a",
                "tags": ["synthetic-table"], "source_category": "source-unknown",
                "development_exposure": "synthetic-author-read", "input_page_count": 2,
            },
            "synthetic-sample-b": {
                "document_id": "synthetic-doc-b", "family_id": "synthetic-family-a",
                "tags": ["synthetic-prose"], "source_category": "synthetic-source-known",
                "development_exposure": "unknown", "input_page_count": 1,
            },
        },
    }


def test_declared_dataset_distribution_is_independent_of_eight_result_streams():
    declaration = _dataset_declaration()
    before = copy.deepcopy(declaration)
    report = reporting.aggregate_reports([_result(pipeline=f"P{number:02}") for number in range(1, 9)])
    report["dataset_declaration"] = declaration
    report["execution"] = {"configurations": [{"pipeline": f"P{number:02}"} for number in range(1, 9)]}
    rendered = reporting.render_appendix(report)
    assert declaration == before
    assert "synthetic-lite" in rendered
    assert "source-unknown" in rendered
    assert "synthetic-source-known" in rendered
    assert "synthetic-author-read" in rendered
    assert "unknown" in rendered
    assert "声明" in rendered
    one_configuration = reporting.aggregate_reports([_result()])
    one_configuration["dataset_declaration"] = copy.deepcopy(declaration)
    one_configuration["execution"] = {"configurations": [{"pipeline": "P01"}]}
    rendered_once = reporting.render_appendix(one_configuration)
    for marker in ("synthetic-source-known", "synthetic-author-read"):
        distribution_rows = [line for line in rendered.splitlines() if marker in line]
        assert distribution_rows
        assert distribution_rows == [line for line in rendered_once.splitlines() if marker in line]


def test_frozen_global_exposure_is_shown_without_replacing_unknown_sample_history():
    declaration = _dataset_declaration()
    exposure = "All source documents and families have authoring exposure; Lite is not an unseen split."
    declaration["freeze_record"]["development_exposure"] = exposure
    for metadata in declaration["sample_metadata"].values():
        metadata.pop("development_exposure", None)
    before = copy.deepcopy(declaration)
    report = reporting.aggregate_reports([])
    report["dataset_declaration"] = declaration
    rendered = reporting.render_appendix(report)
    assert f"冻结记录的全局开发暴露声明：{exposure}。" in rendered
    assert "单样本历史暴露unknown不代表未见" in rendered
    assert "| 开发暴露 | unknown | 2 |" in rendered
    assert declaration == before


def test_missing_frozen_global_exposure_stays_unknown_without_inferring_from_samples():
    declaration = _dataset_declaration()
    before = copy.deepcopy(declaration)
    report = reporting.aggregate_reports([])
    report["dataset_declaration"] = declaration
    rendered = reporting.render_appendix(report)
    assert "冻结记录的全局开发暴露声明：unknown。" in rendered
    assert "单样本历史暴露unknown不代表未见" in rendered
    assert "| 开发暴露 | synthetic-author-read | 1 |" in rendered
    assert "| 开发暴露 | unknown | 1 |" in rendered
    assert declaration == before


def test_actual_worker_and_gpu_role_versions_are_rendered_separately_as_post_run_metadata():
    report = reporting.aggregate_reports([_result()])
    report["software_inspection"] = {
        "path": "artifacts/synthetic-software-inspection.json",
        "record": {
            "inspected_at": "2026-10-24T12:34:56+08:00",
            "scope": "post_run_immutable_image_metadata_no_inference",
            "pipelines": {"P01": {
                "image_id": "sha256:synthetic-worker-image",
                "versions": {"synthetic-sdk": "worker-version-111"},
                "inference": [
                    {"role": "paddle", "image_id": "sha256:synthetic-paddle-image",
                     "versions": {"synthetic-sdk": "paddle-version-222"},
                     "model_name": "synthetic-paddle-model"},
                    {"role": "glm", "image_id": "sha256:synthetic-glm-image",
                     "versions": {"synthetic-sdk": "glm-version-333"},
                     "model_name": "synthetic-glm-model"},
                ],
            }},
        },
    }
    rendered = reporting.render_appendix(report)
    for value in ("worker-version-111", "paddle-version-222", "glm-version-333",
                  "sha256:synthetic-worker-image", "sha256:synthetic-paddle-image",
                  "sha256:synthetic-glm-image", "synthetic-paddle-model", "synthetic-glm-model"):
        assert value in rendered
    worker_row = next(line for line in rendered.splitlines() if "worker-version-111" in line)
    paddle_row = next(line for line in rendered.splitlines() if "paddle-version-222" in line)
    glm_row = next(line for line in rendered.splitlines() if "glm-version-333" in line)
    assert len({worker_row, paddle_row, glm_row}) == 3
    assert "paddle" in paddle_row and "glm" in glm_row
    assert "paddle-version-222" not in worker_row and "glm-version-333" not in worker_row
    assert "后验" in rendered


def test_service_readiness_loading_cost_is_visible_but_not_added_to_processing():
    report = reporting.aggregate_reports([_result()])
    report["runtime_evidence"] = {"P01": {
        "inference_lifecycle": {"path": "artifacts/synthetic-inference-ownership.json", "record": {
            "initialization_status": "ready", "initialization_to_readiness_host_seconds": 123.25,
            "containers": [{
                "name": "synthetic-paddle-container", "role": "paddle",
                "ready_at": "2026-10-24T12:35:00+08:00",
                "initialization_status": "ready", "initialization_to_readiness_host_seconds": 122.5,
            }],
        }},
    }}
    before = copy.deepcopy(report)
    rendered = reporting.render_appendix(report)
    assert "123.2500" in rendered
    loading_row = next(line for line in rendered.splitlines() if "123.2500" in line)
    assert "P01" in loading_row
    assert "1.2500" in loading_row
    assert _group(report)["performance"]["rounds"][0]["processing_seconds_including_failures"] == 2.0
    assert report == before


@pytest.mark.parametrize("status", ["resource_failed", "not_started", "execution_unknown"])
def test_failure_rows_do_not_acquire_zero_cost_when_runtime_metadata_exists(status):
    report = reporting.aggregate_reports([_result(status=status, timing={})])
    group = _group(report)
    assert group["runtime_records"][0]["runtime"]["batch_orchestration_seconds"] == 9876.0
    assert group["performance"]["round_duration_summary"]["median_seconds"] is None
    assert group["performance"]["rounds"][0]["processing_seconds_including_failures"] is None
    assert group["performance"]["failed_runs"] == 1


SLICE_COST_COLUMNS = (
    "observed_processing_seconds_subtotal", "processing_seconds_including_failures",
    "observed_processing_samples", "missing_processing_samples", "timing_complete",
    "completed_input_pages", "seconds_per_attempted_input_page",
    "completed_pages_per_second_including_failure_cost",
)


def _slice(report: dict, *, scope="family", key="synthetic-family-a", pipeline="P01") -> dict:
    return next(row for row in report["quality_slices"]
                if row["scope"] == scope and row["scope_key"] == key and row["pipeline"] == pipeline)


def _paired_cost_results() -> list[dict]:
    return [
        _result(sample_id="synthetic-success", input_page_count=2, timing={"processing_seconds": 2.0}),
        _result(sample_id="synthetic-failed", status="timed_out", input_page_count=3,
                timing={"processing_seconds": 5.0}),
    ]


def test_quality_slice_cost_includes_measured_failure_time_for_every_shared_scope():
    inputs = _paired_cost_results()
    before = copy.deepcopy(inputs)
    report = reporting.aggregate_reports(inputs)
    assert set(SLICE_COST_COLUMNS) <= set(reporting.QUALITY_SLICE_COLUMNS)
    shared_rows = [row for row in report["quality_slices"] if row["scope"] != "sample"]
    assert {row["scope"] for row in shared_rows} == {
        "document", "family", "tag", "source", "development_exposure",
    }
    for row in shared_rows:
        assert row["input_pages"] == 5
        assert row["observed_processing_seconds_subtotal"] == 7
        assert row["processing_seconds_including_failures"] == 7
        assert row["observed_processing_samples"] == 2
        assert row["missing_processing_samples"] == 0
        assert row["timing_complete"] is True
        assert row["completed_input_pages"] == 2
        assert row["seconds_per_attempted_input_page"] == pytest.approx(1.4)
        assert row["completed_pages_per_second_including_failure_cost"] == pytest.approx(2 / 7)
    success = _slice(report, scope="sample", key="synthetic-success")
    assert success["processing_seconds_including_failures"] == 2
    assert success["completed_input_pages"] == 2
    assert success["seconds_per_attempted_input_page"] == 1
    failed = _slice(report, scope="sample", key="synthetic-failed")
    assert failed["processing_seconds_including_failures"] == 5
    assert failed["completed_input_pages"] == 0
    assert failed["seconds_per_attempted_input_page"] == pytest.approx(5 / 3)
    assert failed["completed_pages_per_second_including_failure_cost"] == 0
    rendered = reporting.render_quality_slices(report)
    assert "7.0000" in rendered and "1.4000" in rendered and "0.2857" in rendered
    assert inputs == before


def test_unstarted_sample_keeps_slice_subtotal_but_blocks_complete_cost_and_rates():
    inputs = [*_paired_cost_results(),
              _result(sample_id="synthetic-unstarted", status="not_started", input_page_count=4, timing={})]
    report = reporting.aggregate_reports(inputs)
    row = _slice(report)
    assert row["input_pages"] == 9
    assert row["observed_processing_seconds_subtotal"] == 7
    assert row["processing_seconds_including_failures"] is None
    assert row["observed_processing_samples"] == 2
    assert row["missing_processing_samples"] == 1
    assert row["timing_complete"] is False
    assert row["completed_input_pages"] == 2
    assert row["seconds_per_attempted_input_page"] is None
    assert row["completed_pages_per_second_including_failure_cost"] is None
    pending = _slice(report, scope="sample", key="synthetic-unstarted")
    assert pending["observed_processing_seconds_subtotal"] is None
    assert pending["processing_seconds_including_failures"] is None
    assert "7.0000" in reporting.render_quality_slices(report)


def test_slice_with_only_missing_durations_has_no_zero_cost_subtotal():
    report = reporting.aggregate_reports([
        _result(sample_id="synthetic-failed", status="resource_failed", input_page_count=3, timing={}),
        _result(sample_id="synthetic-unstarted", status="not_started", input_page_count=4,
                timing={"processing_seconds": None}),
    ])
    row = _slice(report)
    assert row["input_pages"] == 7
    assert row["observed_processing_seconds_subtotal"] is None
    assert row["processing_seconds_including_failures"] is None
    assert row["observed_processing_samples"] == 0
    assert row["missing_processing_samples"] == 2
    assert row["timing_complete"] is False
    assert row["completed_input_pages"] == 0
    assert row["seconds_per_attempted_input_page"] is None
    assert row["completed_pages_per_second_including_failure_cost"] is None


@pytest.mark.parametrize("invalid_seconds", [None, 0, -1, float("nan"), float("inf"), True, "2"])
def test_slice_known_time_requires_a_direct_finite_positive_number(invalid_seconds):
    report = reporting.aggregate_reports([
        _result(status="resource_failed", timing={"processing_seconds": invalid_seconds}),
    ])
    row = _slice(report)
    assert row["observed_processing_seconds_subtotal"] is None
    assert row["processing_seconds_including_failures"] is None
    assert row["observed_processing_samples"] == 0
    assert row["missing_processing_samples"] == 1
    assert row["timing_complete"] is False
    assert row["seconds_per_attempted_input_page"] is None
    assert row["completed_pages_per_second_including_failure_cost"] is None


def test_success_with_unknown_page_count_blocks_both_slice_page_rates():
    report = reporting.aggregate_reports([
        _result(sample_id="synthetic-known", input_page_count=2, timing={"processing_seconds": 2}),
        _result(sample_id="synthetic-unknown", input_page_count=None, timing={"processing_seconds": 5}),
    ])
    row = _slice(report)
    assert row["timing_complete"] is True
    assert row["processing_seconds_including_failures"] == 7
    assert row["input_pages"] is None
    assert row["completed_input_pages"] is None
    assert row["seconds_per_attempted_input_page"] is None
    assert row["completed_pages_per_second_including_failure_cost"] is None


def test_failed_unknown_page_count_does_not_hide_known_completed_pages_or_throughput():
    report = reporting.aggregate_reports([
        _result(sample_id="synthetic-success", input_page_count=2, timing={"processing_seconds": 2}),
        _result(sample_id="synthetic-failed", status="timed_out", input_page_count=None,
                timing={"processing_seconds": 5}),
    ])
    row = _slice(report)
    assert row["timing_complete"] is True
    assert row["processing_seconds_including_failures"] == 7
    assert row["input_pages"] is None
    assert row["completed_input_pages"] == 2
    assert row["seconds_per_attempted_input_page"] is None
    assert row["completed_pages_per_second_including_failure_cost"] == pytest.approx(2 / 7)


def test_quality_slice_cost_excludes_perf_rounds_warmup_initialization_and_orchestration():
    quality = _result()
    quality["timing"]["pipeline_initialization_seconds"] = 9999
    inputs = [quality,
              _result(phase="warmup", timing={"processing_seconds": 10000}),
              *[_result(suite="perf80", repetition=repetition,
                        timing={"processing_seconds": 100 * repetition}) for repetition in (1, 2, 3)]]
    report = reporting.aggregate_reports(inputs)
    assert report["quality_slices"]
    assert {row["suite"] for row in report["quality_slices"]} == {"quality800"}
    for row in report["quality_slices"]:
        assert row["observed_processing_seconds_subtotal"] == 2
        assert row["processing_seconds_including_failures"] == 2
        assert row["observed_processing_samples"] == 1
        assert row["missing_processing_samples"] == 0
        assert row["completed_input_pages"] == 2
    perf = _group(report, suite="perf80")["performance"]
    assert perf["round_duration_summary"]["n"] == 3
    assert perf["round_duration_summary"]["median_seconds"] == 200


def test_duplicate_quality_cost_does_not_bypass_blocked_slice_comparison():
    report = reporting.aggregate_reports([
        _result(), _result(run_id="other-run", timing={"processing_seconds": 500}),
    ])
    assert report["quality_slices"] == []
    assert _group(report)["quality"]["status"] == "duplicate_quality_runs_require_explicit_run_selection"


def test_group_comparison_keeps_eight_configurations_adjacent_for_each_source_group():
    inputs = [
        _result(pipeline=f"P{number:02}", sample_id=f"synthetic-sample-{suffix}",
                source_category=f"synthetic-source-{suffix}")
        for number in range(8, 0, -1) for suffix in ("beta", "alpha")
    ]
    report = reporting.aggregate_reports(inputs)
    rendered = reporting.render_quality_slices(report)
    source_ids = {"synthetic-source-alpha", "synthetic-source-beta"}
    rows = [[cell.strip() for cell in line.strip("|").split("|")]
            for line in rendered.splitlines() if line.startswith("|")]
    actual = [(cells[0], cells[2]) for cells in rows if cells and cells[0] in source_ids]
    expected = [(source, f"P{number:02}") for source in sorted(source_ids) for number in range(1, 9)]
    assert actual == expected
