"""Direct processing costs remain independent of scoring and warm-up."""

from moparse_eval.reporting import native_performance, postprocessing_performance


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
