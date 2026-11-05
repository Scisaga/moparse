"""Controlled scheduling probes; no saved corpus or parser execution is read."""

from __future__ import annotations

import multiprocessing
import os
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest

from moparse_eval import expected_evaluation as evaluation


def _tasks(samples=173, groups=12):
    return [{"sample_id": f"sample-{sample:03}", "group": f"group-{group:02}"}
            for sample in range(samples) for group in range(groups)]


def test_scheduler_retains_all_2076_tasks_without_overlapping_a_sample_and_fills_sixteen_slots(monkeypatch):
    tasks = _tasks()
    before = deepcopy(tasks)
    lock, first_wave = threading.Lock(), threading.Barrier(16)
    starts, submitted, overlap, active_samples, configuration = [], [], [], set(), []
    active = peak = 0

    def pool(*, max_workers, mp_context):
        configuration.append((max_workers, mp_context.get_start_method()))
        executor = ThreadPoolExecutor(max_workers=max_workers)
        original_submit = executor.submit

        def submit(function, task):
            submitted.append((task["sample_id"], task["group"]))
            return original_submit(function, task)

        executor.submit = submit
        return executor

    def controlled(task):
        nonlocal active, peak
        sample = task["sample_id"]
        with lock:
            if sample in active_samples:
                overlap.append(sample)
            active_samples.add(sample)
            active += 1
            peak = max(peak, active)
            starts.append((sample, task["group"]))
            initial = len(starts) <= 16
        try:
            if initial:
                first_wave.wait(timeout=10)
            time.sleep(0.001)
            return dict(task)
        finally:
            with lock:
                active -= 1
                active_samples.discard(sample)

    monkeypatch.setattr(evaluation, "ProcessPoolExecutor", pool)
    monkeypatch.setattr(evaluation, "_grade_saved_group", controlled)
    records = list(evaluation._grade_tasks(tasks, 16))
    assert configuration == [(16, "spawn")]
    assert len(records) == 2076
    assert Counter((r["sample_id"], r["group"]) for r in records) == Counter(
        (r["sample_id"], r["group"]) for r in tasks)
    assert overlap == []
    assert peak == 16
    # A completed sample rejoins behind every sample already waiting.
    assert len({sample for sample, _ in submitted[:173]}) == 173
    for number in range(173):
        assert [group for sample, group in starts if sample == f"sample-{number:03}"] == [
            f"group-{group:02}" for group in range(12)]
    assert tasks == before


def test_a_failed_future_is_not_retried_or_followed_by_that_samples_next_group(monkeypatch):
    tasks = _tasks(samples=20, groups=3)
    before, calls = deepcopy(tasks), []
    lock = threading.Lock()

    def pool(*, max_workers, mp_context):
        assert max_workers == 16 and mp_context.get_start_method() == "spawn"
        return ThreadPoolExecutor(max_workers=max_workers)

    def controlled(task):
        with lock:
            calls.append((task["sample_id"], task["group"]))
        if task["sample_id"] == "sample-000" and task["group"] == "group-00":
            raise RuntimeError("controlled worker failure")
        time.sleep(0.02)
        return dict(task)

    monkeypatch.setattr(evaluation, "ProcessPoolExecutor", pool)
    monkeypatch.setattr(evaluation, "_grade_saved_group", controlled)
    with pytest.raises(RuntimeError, match="controlled worker failure"):
        list(evaluation._grade_tasks(tasks, 16))
    assert calls.count(("sample-000", "group-00")) == 1
    assert ("sample-000", "group-01") not in calls
    assert ("sample-000", "group-02") not in calls
    assert len(calls) <= 16
    assert tasks == before


def test_serial_analysis_uses_the_same_sample_queue_without_starting_a_pool(monkeypatch):
    def no_pool(**_kwargs):
        raise AssertionError("a single analysis worker should execute inline")

    tasks = _tasks(samples=3, groups=2)
    monkeypatch.setattr(evaluation, "ProcessPoolExecutor", no_pool)
    monkeypatch.setattr(evaluation, "_grade_saved_group", lambda task: dict(task))
    result = list(evaluation._grade_tasks(tasks, 1))
    assert [(r["sample_id"], r["group"]) for r in result] == [
        ("sample-000", "group-00"), ("sample-001", "group-00"), ("sample-002", "group-00"),
        ("sample-000", "group-01"), ("sample-001", "group-01"), ("sample-002", "group-01"),
    ]


def _spawn_probe(task):
    """Exclusive sample locks prove real spawned processes never overlap it."""
    lock = Path(task["probe_root"]) / (task["sample_id"] + ".active")
    with lock.open("x", encoding="utf-8"):
        started = time.monotonic_ns()
        try:
            time.sleep(0.005)
            return {**task, "started": started, "finished": time.monotonic_ns(), "pid": os.getpid(),
                    "start_method": multiprocessing.get_start_method()}
        finally:
            lock.unlink()


def test_real_spawned_pool_preserves_sample_exclusion_and_complete_task_identity(tmp_path, monkeypatch):
    tasks = [{**task, "probe_root": str(tmp_path)} for task in _tasks(samples=20, groups=2)]
    monkeypatch.setattr(evaluation, "_grade_saved_group", _spawn_probe)
    records = list(evaluation._grade_tasks(tasks, 16))
    assert len(records) == 40
    assert {(r["sample_id"], r["group"]) for r in records} == {
        (r["sample_id"], r["group"]) for r in tasks}
    assert {r["start_method"] for r in records} == {"spawn"}
    assert len({r["pid"] for r in records}) > 1
    active = peak = 0
    for _, change in sorted([(r["started"], 1) for r in records] + [(r["finished"], -1) for r in records]):
        active += change
        peak = max(peak, active)
    assert 1 < peak <= 16
    assert list(tmp_path.iterdir()) == []


def test_failed_execution_status_keeps_the_declared_analysis_scheduling_policy(tmp_path, monkeypatch):
    from moparse_eval import cli
    from moparse_eval.packaging import read_json, write_json

    expected = tmp_path / "expected"
    document = expected / "invented"
    document.mkdir(parents=True)
    (document / "expected.md").write_text("Revenue: 17\n", encoding="utf-8")
    write_json(document / "manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {
        "entries": [{"source_pages": [1], "markdown_lines": [1, 1]}]}})
    dataset = tmp_path / "dataset"
    write_json(dataset / "manifest.json", {"samples": [{
        "id": "synthetic", "document_id": "invented", "source_pages": [1], "family_id": "family",
    }]})
    run = tmp_path / "native"
    write_json(run / "run.json", {"state": "completed", "dataset": str(dataset),
        "development_experiment": True, "experiment_id": "controlled-scheduler-probe", "cases": [
            {"pipeline": pipeline, "sample_id": "synthetic", "suite": "quality800", "phase": "measured",
             "repetition": 1, "observation": f"unused/{pipeline}.json"} for pipeline in evaluation.PIPELINES]})
    monkeypatch.setattr(cli, "code_identity", lambda: {"software_id": "controlled-scheduler-version"})
    monkeypatch.setattr(cli, "snapshot_software", lambda *_args: None)

    def failed_tasks(_tasks, _workers):
        raise RuntimeError("controlled execution stop")

    monkeypatch.setattr(evaluation, "_grade_tasks", failed_tasks)
    output = tmp_path / "diagnosis"
    with pytest.raises(RuntimeError, match="controlled execution stop"):
        evaluation.evaluate_saved(run, output, expected_root=expected, diagnostic=True, workers=16)
    index, status = read_json(output / "index.json"), read_json(output / "execution-status.json")
    assert index == status
    assert index["state"] == "failed" and index["expected_comparison_complete"] is False
    assert index["analysis_scheduling"] == {
        "policy": "sample_round_robin", "max_active_tasks": 16, "max_active_tasks_per_sample": 1,
        "process_start_method": "spawn", "sample_order": "first_declared_task_occurrence",
        "group_order": "declared_task_order_within_sample", "completed_sample": "append_to_ready_queue_tail",
        "failure_policy": "fail_without_retry", "declared_tasks": 8,
    }
    assert not any(key in index for key in ["summary", "paired", "adoption"])
