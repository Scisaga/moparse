"""Fixed arithmetic and bounded-memory contracts without real score access."""

import gc
import json
import tracemalloc
import weakref
from copy import deepcopy

import pytest

from moparse_eval.streaming_aggregation import aggregate_score_files


def _score(sample="toy", *, size=4, edits=0, layout=(True, True), business=(True, True)):
    outcomes = [{"id": "T:0", "layer": "T", "role": "literal", "expected": {"text": "x" * size},
                 "outcome": "correct" if edits == 0 else "incorrect"}]
    for layer, decisions in (("L", layout), ("B", business)):
        for i, correct in enumerate(decisions):
            expected = {"subject": "Delta", "attribute": ("Revenue", "Profit")[i],
                        "value": ("17", "5")[i], "scope": ["North"], "qualifiers": {"unit": "万元"}}
            outcomes.append({"id": f"{layer}:{i}", "layer": layer, "role": "field_binding" if layer == "L" else "metric",
                             "expected": expected, "reference": {"path": "<fixed-required>", "lines": [i + 1, i + 1]},
                             "outcome": "correct" if correct else "incorrect", "root_cause": f"record:{i}"})
    layers = {"T": {"numerator": size - edits, "denominator": size,
                     "score": 100 * max(0, size - edits) / size, "complete": True}}
    for layer, decisions in (("L", layout), ("B", business)):
        layers[layer] = {"numerator": sum(decisions), "denominator": len(decisions),
                         "score": 100 * sum(decisions) / len(decisions), "complete": True}
    return {"sample_id": sample, "publishable": True, "blockers": [], "layers": layers,
            "score": sum(row["score"] for row in layers.values()) / 3, "outcomes": outcomes}


def _records(scores):
    return [{"sample_id": score["sample_id"], "group": group, "path": f"{group}/{score['sample_id']}.json"}
            for group, score in scores]


def _run(scores, *, groups=None, **kwargs):
    records = _records(scores)
    by_path = {record["path"]: score for record, (_, score) in zip(records, scores, strict=True)}
    return aggregate_score_files(iter(records), groups=groups or list(dict.fromkeys(group for group, _ in scores)),
                                 base_dir=".", reader=lambda path: by_path[path.as_posix().removeprefix("./")], **kwargs)


def test_pool_layer_counts_before_text_clipping_and_average_three_pooled_layers():
    result = _run([("P01", _score("short", size=2, edits=7, layout=(True, False), business=(True, False))),
                   ("P01", _score("long", size=8, layout=(True, True), business=(False, False)))],
                  expected_sample_ids={"short", "long"})
    summary = result["summary"]["P01"]
    assert summary["samples"] == 2
    assert summary["layers"]["T"] == {"numerator": 3, "denominator": 10, "score": 30.0, "complete": True,
                                        "applicable_samples": 2, "not_applicable_samples": 0}
    assert summary["layers"]["L"]["score"] == 75
    assert summary["layers"]["B"]["score"] == 25
    assert summary["score"] == pytest.approx(130 / 3)
    assert result["publishable"] is True


def test_actual_target_changes_keep_all_references_without_copying_target_payloads():
    before = _score(edits=1, layout=(True, False), business=(False, False))
    after = _score(layout=(False, True), business=(True, False))
    result = _run([("P01", before), ("P01-current", after)])
    pair = result["paired_details"]["P01"]["native_to_current"]
    assert result["paired"]["P01"]["native_to_current"] == {
        "T": {"new_correct": 1, "lost_correct": 0, "remaining_incorrect": 0, "required_units": 4},
        "L": {"new_correct": 1, "lost_correct": 1, "remaining_incorrect": 1, "required_units": 2},
        "B": {"new_correct": 1, "lost_correct": 0, "remaining_incorrect": 1, "required_units": 2}}
    assert pair["layers"]["L"]["losses"] == [
        {"sample_id": "toy", "layer": "L", "id": "L:0",
         "before": {"path": "P01/toy.json", "outcome_id": "L:0"},
         "after": {"path": "P01-current/toy.json", "outcome_id": "L:0"}}]
    for layer in ("T", "L", "B"):
        for kind in ("gains", "losses", "remaining_incorrect"):
            for item in pair["layers"][layer][kind]:
                assert set(item) == {"sample_id", "layer", "id", "before", "after"}
                assert set(item["before"]) == set(item["after"]) == {"path", "outcome_id"}
    assert pair["shared_root_causes"]["record:0"] == [{"sample_id": "toy", "layer": "L", "id": "L:0"}]


def test_all_eight_native_current_pairs_and_two_existing_baseline_triples_are_retained():
    groups = [f"P{i:02}" for i in range(1, 9)] + [f"P{i:02}-current" for i in range(1, 9)] + ["P07-baseline", "P08-baseline"]
    result = _run([(group, _score()) for group in groups], groups=groups)
    assert set(result["paired"]) == {f"P{i:02}" for i in range(1, 9)}
    assert set(result["paired"]["P01"]) == {"native_to_current"}
    assert set(result["paired"]["P07"]) == set(result["paired"]["P08"]) == {
        "native_to_baseline", "native_to_current", "baseline_to_current"}
    assert len(result["summary"]) == 18 and result["records_processed"] == 18


@pytest.mark.parametrize("mutation", ["expected_value", "scope", "role", "reference", "identity"])
def test_matching_ids_and_denominators_cannot_mask_changed_target_meaning(mutation):
    before, after = _score(), _score()
    target = after["outcomes"][-1]
    if mutation == "expected_value":
        target["expected"]["value"] = "6"
    elif mutation == "scope":
        target["expected"]["scope"] = ["South"]
    elif mutation == "role":
        target["role"] = "identity"
    elif mutation == "reference":
        target["reference"]["lines"] = [9, 9]
    else:
        target["id"] = "B:other"
    with pytest.raises(ValueError, match="requirement|target|scope"):
        _run([("P01", before), ("P01-current", after)])


@pytest.mark.parametrize("mutation", ["sample_formula", "layer_formula", "binary_count", "duplicate_target", "software_failure", "withheld"])
def test_invalid_or_withheld_judgments_never_become_zero_or_a_partial_summary(mutation):
    score = _score()
    if mutation == "sample_formula":
        score["score"] = 0
    elif mutation == "layer_formula":
        score["layers"]["T"]["numerator"] = 0
    elif mutation == "binary_count":
        score["layers"]["B"]["denominator"] = 3
    elif mutation == "duplicate_target":
        score["outcomes"].append(deepcopy(score["outcomes"][-1]))
    elif mutation == "software_failure":
        score["outcomes"][0]["software_failure"] = True
    else:
        score["publishable"] = False
        score["layers"]["T"].update(numerator=None, score=None)
        score["score"] = None
    with pytest.raises(ValueError):
        _run([("P01", score)])


@pytest.mark.parametrize("case", ["duplicate_group", "missing_group", "sample_reentry", "wrong_metadata_sample", "unknown_group", "missing_sample"])
def test_scope_and_duplicate_failures_are_detected_in_the_one_shot_stream(case):
    groups = ["P01", "P01-current"]
    scores = [(group, _score(sample)) for sample in ("a", "b") for group in groups]
    records = _records(scores)
    by_path = {r["path"]: score for r, (_, score) in zip(records, scores, strict=True)}
    if case == "duplicate_group":
        records.insert(1, records[0])
    elif case == "missing_group":
        records.pop()
    elif case == "sample_reentry":
        records = records[:2] + records[2:] + records[:2]
    elif case == "wrong_metadata_sample":
        records[0] = {**records[0], "sample_id": "wrong"}
    elif case == "unknown_group":
        records[0] = {**records[0], "group": "P09"}
    else:
        records = records[:2]
    with pytest.raises(ValueError):
        aggregate_score_files(iter(records), groups=groups, expected_sample_ids={"a", "b"}, base_dir=".",
                              reader=lambda p: by_path[p.as_posix()])


def test_optional_present_software_identity_must_not_mix_versions():
    before, after = _score(), _score()
    before["scoring_software_id"], after["scoring_software_id"] = "frozen-one", "frozen-two"
    with pytest.raises(ValueError, match="software|version"):
        _run([("P01", before), ("P01-current", after)])


def test_changed_text_denominator_cannot_hide_behind_identical_targets_and_valid_percentages():
    before, after = _score(), _score()
    after["layers"]["T"].update(numerator=5, denominator=5)
    with pytest.raises(ValueError, match="denominator"):
        _run([("P01", before), ("P01-current", after)])


def test_a_globally_inapplicable_layer_keeps_none_and_prevents_three_layer_publication():
    score = _score()
    score["outcomes"] = [row for row in score["outcomes"] if row["layer"] != "B"]
    score["layers"]["B"].update(numerator=0, denominator=0, score=None)
    score["score"] = None
    result = _run([("P01", score)])
    assert result["summary"]["P01"]["layers"]["B"]["score"] is None
    assert result["summary"]["P01"]["score"] is None
    assert result["publishable"] is False


def test_missing_measurement_is_not_filled_as_zero():
    score = _score()
    score["layers"]["T"]["numerator"] = None
    with pytest.raises(ValueError, match="finite"):
        _run([("P01", score)])


def test_requirement_fingerprints_stream_json_without_dumps_and_leave_input_unchanged(monkeypatch):
    import moparse_eval.streaming_aggregation as streaming

    before, after = _score(), _score()
    original = deepcopy((before, after))

    def forbidden(*args, **kwargs):
        raise AssertionError("requirement fingerprint materialized a full JSON string")

    monkeypatch.setattr(streaming.json, "dumps", forbidden)
    result = _run([("P01", before), ("P01-current", after)])
    assert result["summary"]["P01"]["score"] == 100
    assert (before, after) == original


def test_default_reader_expands_complete_shared_json_and_preserves_inputs(tmp_path):
    from moparse_eval.trace_storage import share_evidence

    score = _score()
    score["trace"] = ["子公司 \"quoted\" \n" * 80] * 2
    raw = json.dumps(share_evidence(score), ensure_ascii=False)
    path = tmp_path / "score.json"
    path.write_text(raw, encoding="utf-8")
    result = aggregate_score_files(iter([{"group": "P01", "sample_id": "toy", "path": "score.json"}]),
                                   groups=["P01"], base_dir=tmp_path)
    assert result["summary"]["P01"]["score"] == 100
    assert path.read_text(encoding="utf-8") == raw


def test_read_failure_propagates_without_retry_or_returning_a_partial_result():
    calls = []

    def reader(path):
        calls.append(path)
        raise OSError("controlled unreadable score")

    with pytest.raises(OSError, match="controlled unreadable"):
        aggregate_score_files(iter([{"group": "P01", "sample_id": "toy", "path": "bad.json"}]),
                              groups=["P01"], base_dir=".", reader=reader)
    assert len(calls) == 1


def test_one_shot_stream_releases_full_traces_before_reading_next_file():
    class OneShot:
        used = False

        def __iter__(self):
            assert not self.used, "the records iterator must not be replayed"
            self.used = True
            for i in range(24):
                yield {"group": "P01", "sample_id": str(i), "path": f"{i}.json"}

    class TrackedScore(dict):
        pass

    references = []
    payload_bytes = 8 * 1024 * 1024

    def reader(path):
        assert not references or references[-1]() is None, "a previous full score is still resident"
        score = TrackedScore(_score(path.stem))
        score["outcomes"][0]["actual"] = {"trace": "x" * payload_bytes}
        references.append(weakref.ref(score))
        return score

    gc.collect()
    tracemalloc.start()
    try:
        result = aggregate_score_files(OneShot(), groups=["P01"], base_dir=".", reader=reader)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result["summary"]["P01"]["samples"] == 24
    assert all(reference() is None for reference in references)
    assert peak < 20 * 1024 * 1024, f"full trace retention: {peak} bytes"
