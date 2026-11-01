"""Direct processing costs remain independent of scoring and warm-up."""

from moparse_eval.metrics import text_metrics
from moparse_eval.reporting import native_performance, postprocessing_performance
from scripts.render_lite_report import (
    PIPELINES,
    cohort_rows,
    error_category,
    memory_bytes,
    observed_dominates,
    summarize_resource_samples,
    text_diagnostics,
)


def test_native_missing_duration_keeps_round_cost_unavailable():
    result = native_performance([
        {"sample_id": "one", "phase": "measured", "repetition": 1,
         "status": "completed", "input_page_count": 2, "timing": {"processing_seconds": 4}},
        {"sample_id": "two", "phase": "measured", "repetition": 1,
         "status": "failed", "input_page_count": 3, "timing": {}},
    ])
    row = result["rounds"][0]
    assert row["processing_seconds_including_failures"] is None
    assert row["observed_processing_seconds_subtotal"] == 4
    assert row["attempted_input_pages"] == 5
    assert row["completed_input_pages"] == 2
    assert row["timing_complete"] is False


def test_native_warmup_and_initialization_stay_outside_measured_rounds():
    result = native_performance([
        {"sample_id": "warmup", "run_id": "worker", "phase": "warmup", "status": "completed",
         "input_page_count": 1, "timing": {"processing_seconds": 19, "pipeline_initialization_seconds": 11}},
        {"sample_id": "one", "run_id": "worker", "phase": "measured", "repetition": 1,
         "status": "completed", "input_page_count": 2, "timing": {"processing_seconds": 4}},
    ])
    assert result["rounds"][0]["processing_seconds_including_failures"] == 4
    assert result["warmup"][0]["processing_seconds"] == 19
    assert result["initialization"][0]["initialization_seconds"] == 11
    assert result["scheduled_runs"] == 1


def test_postprocessing_requires_all_three_performance_rounds():
    result = postprocessing_performance([
        {"sample_id": "one", "suite": "perf80", "phase": "measured", "repetition": 1,
         "status": "completed", "input_pages": 2, "timing": {"postprocessing_seconds": 4}},
        {"sample_id": "warmup", "suite": "perf80", "phase": "warmup", "repetition": 1,
         "status": "completed", "input_pages": 1, "timing": {"postprocessing_seconds": 19}},
    ], "perf80")
    assert [row["repetition"] for row in result["rounds"]] == [1, 2, 3]
    assert result["rounds"][0]["postprocessing_seconds"] == 4
    assert result["rounds"][1]["postprocessing_seconds"] is None
    assert result["rounds"][2]["postprocessing_seconds"] is None


def test_postprocessing_missing_sample_timing_is_not_zero_cost():
    result = postprocessing_performance([
        {"sample_id": "one", "suite": "quality800", "repetition": 1, "status": "completed",
         "input_pages": 2, "timing": {"postprocessing_seconds": 4}},
        {"sample_id": "two", "suite": "quality800", "repetition": 1, "status": "failed",
         "input_pages": 3, "timing": {}},
    ], "quality800")
    row = result["rounds"][0]
    assert row["postprocessing_seconds"] is None
    assert row["observed_seconds_subtotal"] == 4
    assert row["missing_timing_samples"] == 1


def resource_sample(worker, model, *, gpu=3, tts=5, timestamp=1):
    return {"monotonic_seconds": timestamp, "expected_containers": ["worker", "model"],
            "containers": [{"owned_name": "worker", "MemUsage": worker},
                           {"owned_name": "model", "MemUsage": model}],
            "owned_gpu": {"status": "complete_observed_sample", "used_memory_mib": gpu,
                          "memory_mib_by_container": {"worker": 0, "model": gpu}},
            "tts_gpu": {"used_memory_mib": tts}, "gpu1": {"used_memory_mib": gpu + tts}}


def test_host_memory_uses_same_round_sum_instead_of_sum_of_peaks():
    result = summarize_resource_samples({"samples": [
        resource_sample("8GiB / 20GiB", "1GiB / 20GiB"),
        resource_sample("1GiB / 20GiB", "8GiB / 20GiB", timestamp=4)]})
    assert result["host_peak_bytes"] == 9 * 2**30
    assert result["median_gap_seconds"] == 3
    assert result["host_complete_samples"] == 2


def test_memory_reads_usage_and_units_separately_from_limit():
    assert memory_bytes("1.5GiB / 20GiB") == 1.5 * 2**30
    assert memory_bytes("1.5GB / 20GB") == 1.5 * 10**9
    assert memory_bytes("..GiB / 20GiB") is None
    assert memory_bytes(None) is None


def test_partial_memory_sample_does_not_hide_missing_container():
    sample = resource_sample("1GiB / 20GiB", "unavailable")
    result = summarize_resource_samples({"samples": [sample]})
    assert result["host_peak_bytes"] is None
    assert result["samples"] == 1
    assert result["host_complete_samples"] == 0


def test_gpu_uses_attributed_named_processes_without_tts_or_whole_card():
    sample = resource_sample("1GiB / 20GiB", "2GiB / 20GiB", gpu=3072, tts=5120)
    sample["owned_gpu"]["used_memory_mib"] = 8192
    sample["owned_gpu"]["memory_mib_by_container"]["unrelated-tts"] = 5120
    result = summarize_resource_samples({"samples": [sample]})
    assert result["owned_gpu_peak_mib"] == 3072
    assert result["tts_peak_mib"] == 5120
    assert result["whole_gpu_peak_mib"] == 8192


def test_unknown_gpu_attribution_is_not_zero_consumption():
    sample = resource_sample("1GiB / 20GiB", "2GiB / 20GiB")
    sample["owned_gpu"]["status"] = "unknown"
    result = summarize_resource_samples({"samples": [sample]})
    assert result["owned_gpu_peak_mib"] is None
    assert result["gpu_complete_samples"] == 0


def vector(*, quality=0.8, seconds=10, worker=2, inference=3, gpu=4):
    return {"qualities": {"business_field": quality, "text": quality},
            "costs": {"processing_seconds": seconds, "worker_host_bytes": worker,
                      "inference_host_bytes": inference, "owned_gpu_mib": gpu}}


def test_faster_and_more_accurate_is_not_dominance_with_more_gpu_memory():
    faster = vector(quality=0.9, seconds=5, gpu=8)
    smaller = vector(quality=0.8, seconds=10, gpu=3)
    assert observed_dominates(faster, smaller) is False
    assert observed_dominates(smaller, faster) is False


def test_all_reported_dimensions_must_improve_or_tie_with_one_strict_gain():
    assert observed_dominates(vector(seconds=5), vector(seconds=10)) is True
    assert observed_dominates(vector(), vector()) is False
    different = vector(seconds=5)
    different["qualities"]["text"] = 0.1
    assert observed_dominates(different, vector()) is False


def test_missing_dimension_cannot_create_a_dominance_claim():
    assert observed_dominates(vector(gpu=None), vector()) is None
    assert observed_dominates(vector(), vector(gpu=None)) is None
    missing_quality = vector()
    missing_quality["qualities"].pop("text")
    assert observed_dominates(missing_quality, vector()) is None


def test_cohort_totals_use_all_targets_of_tagged_samples_and_allow_overlap():
    tagged = {"tags": ["data-table", "mixed-units"], "by_kind": {
        "business_field": {"correct": 2, "targets": 5}, "text": {"correct": 1, "targets": 3}}}
    other = {"tags": ["ordinary-prose"], "by_kind": {
        "business_field": {"correct": 7, "targets": 9}, "text": {"correct": 3, "targets": 4}}}
    rows = cohort_rows({p: [tagged, other] for p in PIPELINES})
    selected = [r for r in rows if r["pipeline"] == "P01" and r["tag"] in {"data-table", "mixed-units"} and r["kind"] == "business_field"]
    assert len(selected) == 2
    assert all((r["samples"], r["correct"], r["targets"], r["correctness"]) == (1, 2, 5, 0.4) for r in selected)
    empty = next(r for r in rows if r["pipeline"] == "P01" and r["tag"] == "multi-column")
    assert empty["targets"] == 0
    assert empty["correctness"] is None


def test_strict_character_diagnostics_separate_missing_text_from_located_text():
    result = text_diagnostics([{"outcomes": [
        {"kind": "text", "candidate": "abX", "text": text_metrics("abc", "abX")},
        {"kind": "heading", "candidate": None, "text": text_metrics("missing", "")},
        {"kind": "business_field", "candidate": "999"},
    ]}])
    assert result["targets"] == 2
    assert result["missing"] == 1
    assert result["located_reference_characters"] == 3
    assert result["strict_edit_distance"] == 1
    assert result["located_strict_cer"] == 1 / 3
    assert text_diagnostics([])["located_strict_cer"] is None


def test_error_categories_keep_unrecognized_reasons_visible():
    assert error_category("native_header_endpoints_unavailable") == "定位或表头范围"
    assert error_category("native_label_path_scope_conflict") == "范围或位置歧义"
    assert error_category("required_qualifier_incorrect:period") == "限定不符"
    assert error_category("future_reason") == "其他"
