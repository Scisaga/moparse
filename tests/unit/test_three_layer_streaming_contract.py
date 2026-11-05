"""Synthetic saved-score I/O contracts; no corpus or parser execution.

The required JSON is authored here. A shared large trace makes its serialized
size large without first allocating many independent input strings.
"""

import json
import tracemalloc
from copy import deepcopy
from pathlib import Path

import pytest

from moparse_eval import expected_evaluation as evaluation


def score_document():
    trace = {"id": "candidate:0", "source": {"path": 'native/"quoted"/汉字', "lines": [4, 7]},
             "candidate": {"subject": "Delta", "attribute": "Amount", "value": "17"},
             "identity": {"scope": {"correct": False, "actual_path": ["South"]}},
             "decision": "rejected", "reason": "explicit_scope_conflict"}
    return {
        "sample_id": "invented-streaming", "pipeline": "P03", "protocol": {"weights": [1 / 3] * 3},
        "layers": {layer: {"numerator": 7, "denominator": 11, "score": 63.625,
                           "diagnostic_score": 99.25, "complete": False} for layer in ("T", "L", "B")},
        "score": 63.625, "publishable": False,
        "blockers": [{"reason": "synthetic_unsupported", "source": {"path": "reference.md", "lines": [3, 3]}}],
        "outcomes": [{"id": "B:0", "layer": "B", "role": "metric", "outcome": "incorrect",
                      "expected": {"value": "17", "scope": ["North"]}, "actual": [],
                      "retrieval": {"query": {"attribute": "Amount", "scope": ["North"]},
                                    "candidates": [trace], "textual_hits": [], "accepted": []}}],
        "text_evidence": {"required_atoms": [{"text": '汉字 café "quote" \\ slash\nnext'}],
                          "candidate_projection": {"source_fragments": [{"text": "原字", "source": {"path": "#/b"}}]}},
        "scope_evidence": {"contexts": {"events": [{"type": "media", "source": {"block": "image"}}]},
                           "context_labels": [{"text": "Notes:", "source": {"path": "reference.md"}}]},
        "directory_evidence": {"required": None, "candidate": None},
        "pending_requirements": {"expected": [{"reason": "not_interpreted"}], "candidate": []},
        "candidate_issues": [{"reason": "retained_source"}], "reference_interpretation_issues": [],
        "status": "completed", "timing": {"processing_seconds": 1.23456789, "tiny": 1.2e-19, "signed_zero": -0.0},
        "development_exposure": True,
    }


def prepared_task(tmp_path, monkeypatch, score):
    directory = tmp_path / "synthetic-input"
    task = {"group": "P03", "sample_id": "invented-streaming", "expected": {"sample_id": "invented-streaming"},
            "directory": directory, "case": {"observation": "saved.json"}, "output": tmp_path / "diagnostic",
            "software_id": "synthetic-grader", "execution_id": "synthetic-execution", "diagnostic": True}
    observation = {"candidate_source": str((directory / "saved.json").resolve()),
                   "scoring_readback": {"software_id": "synthetic-grader", "readback_seconds": 0.0125}}
    monkeypatch.setattr(evaluation, "native_observation", lambda *args, **kwargs: observation)
    monkeypatch.setattr(evaluation, "grade_expected", lambda *args, **kwargs: score)
    destination = task["output"] / "private/scores/P03/quality800-r1/invented-streaming.json"
    expected = deepcopy(score)
    expected.update(scoring_software_id="synthetic-grader", execution_software_id="synthetic-execution",
                    candidate_source=observation["candidate_source"], diagnostic_only=True,
                    quality_scores_withheld=True, score=None)
    for layer in expected["layers"].values():
        layer.update(score=None, numerator=None)
        layer.pop("diagnostic_score")
    return task, destination, expected


def assert_no_temporary_or_unexpected_files(task, destination, *, exists):
    files = {path for path in task["output"].rglob("*") if path.is_file()}
    assert files == ({destination} if exists else set())


def test_saved_group_writes_the_entire_compact_unicode_record_and_withdraws_all_scores(tmp_path, monkeypatch):
    task, destination, expected = prepared_task(tmp_path, monkeypatch, score_document())
    result = evaluation._grade_saved_group(task)
    raw = destination.read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert "汉字".encode() in raw and b"\\u6c49" not in raw
    assert b'\\"quote\\"' in raw and b'"signed_zero":-0.0' in raw
    assert json.loads(raw) == expected
    assert result["path"] == "private/scores/P03/quality800-r1/invented-streaming.json"
    assert result["readback"] == {"software_id": "synthetic-grader", "readback_seconds": 0.0125}
    assert_no_temporary_or_unexpected_files(task, destination, exists=True)


@pytest.mark.parametrize("existing", [False, True])
def test_encoder_failure_after_streamed_prefix_preserves_previous_final_and_removes_partial(
        tmp_path, monkeypatch, existing):
    score = score_document()
    score["prelude"] = "x" * 32768
    score["unsupported"] = object()
    task, destination, _ = prepared_task(tmp_path, monkeypatch, score)
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = b'{"previous":"intact"}\n'
    if existing:
        destination.write_bytes(previous)
    observed_partial_sizes = []

    def fail_encoding(self, value):
        observed_partial_sizes.extend(path.stat().st_size for path in destination.parent.glob("*.part"))
        raise TypeError("controlled_encoder_failure")

    monkeypatch.setattr(json.JSONEncoder, "default", fail_encoding)
    with pytest.raises(TypeError, match="controlled_encoder_failure"):
        evaluation._grade_saved_group(task)
    assert observed_partial_sizes and max(observed_partial_sizes) > 0
    assert destination.read_bytes() == previous if existing else not destination.exists()
    assert_no_temporary_or_unexpected_files(task, destination, exists=existing)


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_interrupted_stream_write_never_exposes_partial_json_as_a_final(tmp_path, monkeypatch, existing, failure):
    task, destination, _ = prepared_task(tmp_path, monkeypatch, score_document())
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = b'{"previous":"intact"}\n'
    if existing:
        destination.write_bytes(previous)

    def interrupted_write(value, handle, **kwargs):
        temporary = Path(handle.name)
        assert temporary.parent == destination.parent and temporary.suffix == ".part"
        handle.write('{"partially_written":"汉字')
        handle.flush()
        assert temporary.stat().st_size > 0
        raise failure("controlled_stream_interruption")

    monkeypatch.setattr(evaluation.json, "dump", interrupted_write)
    with pytest.raises(failure, match="controlled_stream_interruption"):
        evaluation._grade_saved_group(task)
    assert destination.read_bytes() == previous if existing else not destination.exists()
    assert_no_temporary_or_unexpected_files(task, destination, exists=existing)


def test_replace_failure_keeps_the_old_complete_final_and_cleans_the_complete_partial(tmp_path, monkeypatch):
    task, destination, expected = prepared_task(tmp_path, monkeypatch, score_document())
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = b'{"previous":"intact"}\n'
    destination.write_bytes(previous)
    attempts = []

    def fail_replace(temporary, target):
        assert Path(target) == destination and temporary.parent == destination.parent
        assert temporary.suffix == ".part"
        with temporary.open() as handle:
            assert json.load(handle) == expected
        attempts.append(temporary)
        raise OSError("controlled_replace_failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="controlled_replace_failure"):
        evaluation._grade_saved_group(task)
    assert len(attempts) == 1 and not attempts[0].exists()
    assert destination.read_bytes() == previous
    assert_no_temporary_or_unexpected_files(task, destination, exists=True)


def test_failed_writer_does_not_remove_another_workers_partial_file(tmp_path, monkeypatch):
    task, destination, _ = prepared_task(tmp_path, monkeypatch, score_document())
    destination.parent.mkdir(parents=True, exist_ok=True)
    neighbor = destination.parent / "other-sample.json.worker.part"
    neighbor.write_bytes(b'{"other_worker":"still writing')

    def interrupted_write(value, handle, **kwargs):
        handle.write('{"this_worker":"interrupted')
        handle.flush()
        raise OSError("controlled_stream_interruption")

    monkeypatch.setattr(evaluation.json, "dump", interrupted_write)
    with pytest.raises(OSError, match="controlled_stream_interruption"):
        evaluation._grade_saved_group(task)
    assert not destination.exists()
    assert neighbor.read_bytes() == b'{"other_worker":"still writing'
    assert {path for path in task["output"].rglob("*") if path.is_file()} == {neighbor}


def test_shared_large_trace_is_streamed_without_materializing_the_serialized_document(tmp_path, monkeypatch):
    score = score_document()
    shared = {"text": "界" * 8192 + ' "quoted" \\ slash\n',
              "source": {"path": "#/synthetic/shared", "lines": [1, 1]}, "float": 1.25}
    score["complete_shared_traces"] = [shared] * 512
    task, destination, expected = prepared_task(tmp_path, monkeypatch, score)
    assert not tracemalloc.is_tracing()
    tracemalloc.start()
    try:
        evaluation._grade_saved_group(task)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # The raw UTF-8 document exceeds 12 MiB, while only bounded encoder chunks
    # may be live. The original json.dumps writer exceeds this 2 MiB budget.
    # Loading the complete comparison happens only after tracing has stopped.
    with destination.open() as handle:
        assert json.load(handle) == expected
    assert destination.stat().st_size > 12 * 1024 * 1024
    assert peak < 2 * 1024 * 1024
    assert_no_temporary_or_unexpected_files(task, destination, exists=True)
