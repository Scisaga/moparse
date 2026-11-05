"""Independent arithmetic, publication and pairing probes using invented data."""

from __future__ import annotations

import copy
import inspect
import json
import math

import pytest

from moparse_eval.layer_aggregation import (
    VALIDATION_STAGES,
    paired_layers,
    require_validation,
    summarize_layers,
)


def sample(identifier="one", *, text=(10, 10), logical=(2, 2), business=(3, 3)):
    """Build declared independent decisions, without a compiler or locator."""
    layers = {}
    outcomes = []
    for layer, (numerator, denominator) in zip(("T", "L", "B"), (text, logical, business), strict=True):
        layers[layer] = {
            "numerator": numerator,
            "denominator": denominator,
            "score": 100 * max(0, numerator) / denominator if denominator else None,
            "complete": True,
        }
        for index in range(denominator if layer in {"L", "B"} else int(denominator > 0)):
            outcomes.append({
                "layer": layer,
                "id": f"{identifier}:{layer}:{index}",
                "role": {"T": "required_text", "L": "field_binding", "B": "business_requirement"}[layer],
                "expected": {"assertion": f"independently-authored-{layer}-{index}"},
                "actual": f"printed-{layer}-{index}",
                "outcome": "correct" if (numerator == denominator if layer == "T" else index < numerator) else "incorrect",
                "retrieval": {"query": {"label": f"Metric {index}"}, "hits": []},
            })
    values = [layers[layer]["score"] for layer in ("T", "L", "B")]
    return {
        "sample_id": identifier,
        "layers": layers,
        "outcomes": outcomes,
        "score": sum(values) / 3 if all(value is not None for value in values) else None,
        "publishable": True,
        "blockers": [],
    }


def validation():
    return {
        "status": "passed",
        "known_reader_defects": [],
        **{stage: {"status": "passed", "evidence": [f"synthetic/{stage}.json"]}
           for stage in VALIDATION_STAGES},
    }


def test_three_layers_keep_independent_denominators_and_equal_weight():
    # T=(1+9)/(1+9)=100, L=(1+0)/(1+3)=25,
    # B=(1+8)/(2+8)=90; S=215/3. No shared item denominator.
    values = [sample("short", text=(1, 1), logical=(1, 1), business=(1, 2)),
              sample("long", text=(9, 9), logical=(0, 3), business=(8, 8))]
    result = summarize_layers(values)
    assert result["layers"]["T"]["score"] == 100
    assert result["layers"]["L"]["score"] == 25
    assert result["layers"]["B"]["score"] == 90
    assert result["score"] == pytest.approx(215 / 3)
    assert result["score"] != pytest.approx(100 * 20 / 24)
    assert result["publishable"] is True


def test_text_insertion_errors_are_pooled_before_zero_clipping():
    # The short sample has four errors against one required character.
    # T=max(0, (1-4)+9)/(1+9)=60; clipping before pooling would report90.
    result = summarize_layers([sample("short", text=(-3, 1)), sample("long", text=(9, 9))])
    assert result["layers"]["T"]["numerator"] == 6
    assert result["layers"]["T"]["denominator"] == 10
    assert result["layers"]["T"]["score"] == 60
    assert result["score"] == pytest.approx(260 / 3)


def test_absent_layer_has_na_sample_score_without_reweighting_other_layers():
    value = sample(text=(5, 10), logical=(0, 0), business=(1, 2))
    assert value["score"] is None
    result = summarize_layers([value])
    assert result["layers"]["L"]["score"] is None
    assert result["layers"]["L"]["applicable_samples"] == 0
    assert result["layers"]["L"]["not_applicable_samples"] == 1
    assert result["score"] is None
    assert result["publishable"] is False


def test_globally_applicable_layers_can_pool_samples_with_na_requirements():
    result = summarize_layers([sample("one", logical=(0, 0)), sample("two", logical=(1, 2))])
    assert result["layers"]["L"]["score"] == 50
    assert result["layers"]["L"]["applicable_samples"] == 1
    assert result["layers"]["L"]["not_applicable_samples"] == 1
    assert result["score"] == pytest.approx(250 / 3)


def test_failed_candidate_retains_all_requirements_as_incorrect():
    value = sample(text=(0, 10), logical=(0, 2), business=(0, 3))
    value["status"] = "failed"
    result = summarize_layers([value])
    assert result["score"] == 0
    assert result["layers"]["T"]["denominator"] == 10
    assert result["layers"]["L"]["denominator"] == 2
    assert result["layers"]["B"]["denominator"] == 3
    assert result["publishable"] is True


@pytest.mark.parametrize("mutation", [
    "blocker", "not_publishable", "incomplete_layer", "unsupported",
    "reader_failure", "software_failure", "non_binary", "missing_layer",
])
def test_software_failure_never_becomes_candidate_zero_or_na(mutation):
    value = sample()
    if mutation == "blocker":
        value["blockers"] = [{"reason": "existing representation unsupported"}]
    elif mutation == "not_publishable":
        value["publishable"] = False
    elif mutation == "incomplete_layer":
        value["layers"]["B"]["complete"] = False
    elif mutation == "non_binary":
        value["outcomes"][-1]["outcome"] = "unresolved"
    elif mutation == "missing_layer":
        del value["layers"]["L"]
    else:
        value["outcomes"][-1][mutation] = True
    with pytest.raises(ValueError):
        summarize_layers([value])


@pytest.mark.parametrize("mutation", ["delete_business_records", "omit_requirement", "forge_correct", "duplicate_target"])
def test_independent_decision_accounting_rejects_denominator_mutations(mutation):
    value = sample()
    if mutation == "delete_business_records":
        value["outcomes"] = [row for row in value["outcomes"] if row["layer"] != "B"]
    elif mutation == "omit_requirement":
        value["outcomes"].pop()
    elif mutation == "forge_correct":
        value["outcomes"][-1]["outcome"] = "incorrect"
    else:
        value["outcomes"].append(copy.deepcopy(value["outcomes"][-1]))
    with pytest.raises(ValueError):
        summarize_layers([value])


def test_duplicate_samples_do_not_silently_enlarge_denominators():
    with pytest.raises(ValueError, match="duplicate scored sample"):
        summarize_layers([sample(), sample()])


@pytest.mark.parametrize("number", [math.nan, math.inf, True, "10"])
def test_nonfinite_or_non_numeric_layer_denominators_are_rejected(number):
    value = sample()
    value["layers"]["T"]["denominator"] = number
    with pytest.raises(ValueError, match="finite number"):
        summarize_layers([value])


def test_sample_total_cannot_average_only_the_available_layers():
    value = sample(logical=(0, 0))
    value["score"] = 100
    with pytest.raises(ValueError, match="equal mean"):
        summarize_layers([value])


def test_quality_does_not_include_cost_or_resource_measurements():
    left, right = sample(), sample()
    left.update(timing={"processing_seconds": 0.001}, resources={"gpu": 0})
    right.update(timing={"processing_seconds": 999999}, resources={"gpu": 999999})
    assert summarize_layers([left]) == summarize_layers([right])


def test_pairing_reports_each_layer_and_retains_common_root_cause():
    before = sample(text=(8, 10), logical=(1, 2), business=(1, 3))
    after = sample(text=(9, 10), logical=(2, 2), business=(2, 3))
    # The surviving B error is explicitly linked to the same observed cause.
    after["outcomes"][-1]["root_cause"] = "observed-local-unit-mismatch"
    result = paired_layers([before], [after])
    assert result["layers"]["L"]["new_correct"] == 1
    assert result["layers"]["L"]["lost_correct"] == 0
    assert result["layers"]["B"]["new_correct"] == 1
    assert result["layers"]["B"]["remaining_defects"] == 1
    assert result["layers"]["T"]["before"]["score"] == 80
    assert result["layers"]["T"]["after"]["score"] == 90
    assert result["shared_root_causes"]["observed-local-unit-mismatch"] == [
        {"sample_id": "one", "layer": "B", "id": "one:B:2"}]


@pytest.mark.parametrize("mutation", ["identity", "role", "requirement", "reference", "sample", "denominator"])
def test_pairing_cannot_hide_changed_target_meaning_or_coverage(mutation):
    before, after = sample(), sample()
    if mutation == "identity":
        after["outcomes"][-1]["id"] = "replacement"
    elif mutation == "role":
        after["outcomes"][-1]["role"] = "identity_only"
    elif mutation == "requirement":
        after["outcomes"][-1]["expected"] = {"assertion": "different requirement"}
    elif mutation == "reference":
        after["outcomes"][-1]["reference"] = {"lines": [99, 99]}
    elif mutation == "sample":
        after["sample_id"] = "different"
    else:
        after["layers"]["T"] = {"numerator": 20, "denominator": 20, "score": 100, "complete": True}
    with pytest.raises(ValueError):
        paired_layers([before], [after])


def test_freeze_requires_each_independent_validation_obligation():
    value = validation()
    require_validation(value)
    for stage in VALIDATION_STAGES:
        altered = copy.deepcopy(value)
        del altered[stage]
        with pytest.raises(ValueError, match=stage):
            require_validation(altered)


@pytest.mark.parametrize("status", ["pending", "failed", "not_run"])
def test_unfinished_saved_output_diagnosis_blocks_freeze(status):
    value = validation()
    value["saved_output_diagnosis"]["status"] = status
    with pytest.raises(ValueError, match="saved_output_diagnosis"):
        require_validation(value)


def test_freeze_requires_evidence_not_only_a_passed_flag():
    value = validation()
    value["mutations"] = {"status": "passed"}
    with pytest.raises(ValueError, match="traceable mutations"):
        require_validation(value)


def test_freeze_cli_uses_the_same_guard_and_preserves_its_input(tmp_path):
    from moparse_eval.cli import SCORING_PROTOCOL, read_scoring_freeze

    record = {"software_id": "invented", "protocol_id": SCORING_PROTOCOL["id"], "validation": validation()}
    path = tmp_path / "freeze.json"
    raw = json.dumps(record)
    path.write_text(raw)
    assert read_scoring_freeze(path, {"software_id": "invented"}) == record
    assert path.read_text() == raw
    record["validation"] = {"status": "passed"}
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="independent_counterexamples"):
        read_scoring_freeze(path, {"software_id": "invented"})


def saved_run(tmp_path, monkeypatch, *, text="Name: Delta; Revenue: 17; Profit: 5\n"):
    from moparse_eval import cli
    from moparse_eval.expected_evaluation import PIPELINES
    from moparse_eval.expected_readback import markdown_observation
    from moparse_eval.packaging import write_json

    reference = tmp_path / "expected"
    document = reference / "invented"
    document.mkdir(parents=True)
    (document / "expected.md").write_text(text)
    write_json(document / "manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {
        "entries": [{"source_pages": [1], "markdown_lines": [1, len(text.splitlines())]}]}})
    dataset = tmp_path / "dataset"
    write_json(dataset / "manifest.json", {"samples": [{
        "id": "synthetic", "document_id": "invented", "source_pages": [1], "family_id": "family",
    }]})
    run = tmp_path / "native"
    cases = []
    for pipeline in PIPELINES:
        relative = f"artifacts/{pipeline}/quality800-r1/synthetic/observation.json"
        write_json(run / relative, markdown_observation(text, sample_id="synthetic", pipeline=pipeline, pages=[1]))
        cases.append({"pipeline": pipeline, "sample_id": "synthetic", "suite": "quality800",
                      "phase": "measured", "repetition": 1, "observation": relative})
    write_json(run / "run.json", {"state": "completed", "dataset": str(dataset), "cases": cases,
                                   "development_experiment": True, "experiment_id": "synthetic"})
    identity = {"software_id": "independent-synthetic-version"}
    monkeypatch.setattr(cli, "code_identity", lambda: identity)
    monkeypatch.setattr(cli, "snapshot_software", lambda *_: None)
    freeze = tmp_path / "freeze.json"
    write_json(freeze, {"software_id": identity["software_id"], "protocol_id": cli.SCORING_PROTOCOL["id"],
                        "validation": validation()})
    return run, dataset, reference, freeze


def test_saved_scoring_defaults_to_sixteen_analysis_processes():
    from moparse_eval.expected_evaluation import evaluate_saved

    assert inspect.signature(evaluate_saved).parameters["workers"].default == 16


def test_formal_saved_evaluation_needs_a_validated_freeze(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import evaluate_saved

    run, _, expected, _ = saved_run(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="four-stage scoring freeze"):
        evaluate_saved(run, tmp_path / "scores", expected_root=expected, workers=1)
    assert not (tmp_path / "scores").exists()


def test_all_native_groups_share_fully_scored_requirements(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import PIPELINES, evaluate_saved
    from moparse_eval.packaging import read_json

    run, _, expected, freeze = saved_run(tmp_path, monkeypatch)
    original = (run / "run.json").read_bytes()
    index = read_json(evaluate_saved(run, tmp_path / "scores", expected_root=expected, freeze=freeze, workers=1))
    assert index["state"] == "completed"
    assert index["expected_comparison_complete"] is True
    assert set(index["summary"]) == set(PIPELINES)
    assert len(index["records"]) == 8
    assert index["coverage"][0]["layers"]["B"]["denominator"] == 3
    assert all(index["summary"][pipeline]["score"] == 100 for pipeline in PIPELINES)
    assert index["comparisons"]["native"] == list(PIPELINES)
    assert (run / "run.json").read_bytes() == original


def test_candidate_missing_output_preserves_the_same_denominators(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import evaluate_saved
    from moparse_eval.packaging import read_json

    run, _, expected, freeze = saved_run(tmp_path, monkeypatch)
    (run / "artifacts/P01/quality800-r1/synthetic/observation.json").unlink()
    index_path = evaluate_saved(run, tmp_path / "scores", expected_root=expected, freeze=freeze, workers=1)
    index = read_json(index_path)
    assert index["state"] == "completed"
    assert index["summary"]["P01"]["score"] == 0
    assert {layer: item["denominator"] for layer, item in index["summary"]["P01"]["layers"].items()} == {
        layer: item["denominator"] for layer, item in index["summary"]["P08"]["layers"].items()}
    assert index["summary"]["P01"]["layers"]["B"]["denominator"] == 3


def test_formal_software_blockers_withhold_the_entire_result_set(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import evaluate_saved
    from moparse_eval.packaging import read_json

    run, _, expected, freeze = saved_run(tmp_path, monkeypatch, text="The total is 17.\n")
    index = read_json(evaluate_saved(run, tmp_path / "scores", expected_root=expected, freeze=freeze, workers=1))
    assert index["state"] == "blocked"
    assert index["expected_comparison_complete"] is False
    assert len(index["records"]) == 8
    assert index["blockers"]
    assert not {"summary", "paired", "adoption"} & index.keys()
    assert index["blocker_counts"]["unclassified_business_prose"] >= 8
    for record in index["records"]:
        score = read_json(tmp_path / "scores" / record["path"])
        assert score["quality_scores_withheld"] is True
        assert all(layer["score"] is None and layer["numerator"] is None and "diagnostic_score" not in layer
                   for layer in score["layers"].values())


@pytest.mark.parametrize("supported", [True, False])
def test_diagnostic_traversal_needs_no_freeze_and_never_publishes_scores(tmp_path, monkeypatch, supported):
    from moparse_eval.expected_evaluation import evaluate_saved
    from moparse_eval.packaging import read_json

    text = "Name: Delta; Revenue: 17; Profit: 5\n" if supported else "The total is 17.\n"
    run, _, expected, _ = saved_run(tmp_path, monkeypatch, text=text)
    index_path = evaluate_saved(run, tmp_path / "diagnosis", expected_root=expected, diagnostic=True, workers=1)
    index = read_json(index_path)
    assert index["state"] == ("diagnostic_completed" if supported else "blocked")
    assert index["diagnostic_only"] is True
    assert index["expected_comparison_complete"] is False
    assert "summary" not in index and "adoption" not in index
    assert len(index["records"]) == 8
    for record in index["records"]:
        score = read_json(index_path.parent / record["path"])
        assert score["score"] is None
        assert score["quality_scores_withheld"] is True
        assert all(layer["score"] is None and layer["numerator"] is None for layer in score["layers"].values())
        assert all("diagnostic_score" not in layer for layer in score["layers"].values())


@pytest.mark.parametrize("diagnostic", [True, False])
def test_debug_diagnostic_scores_never_escape_saved_blocked_records(tmp_path, monkeypatch, diagnostic):
    from moparse_eval import expected_evaluation
    from moparse_eval.packaging import read_json

    run, _, expected, freeze = saved_run(tmp_path, monkeypatch)
    original = expected_evaluation.grade_expected

    def unsupported(requirements, observation):
        score = original(requirements, observation)
        score.update(publishable=False, blockers=[{"reason": "injected_unsupported_expression"}])
        for layer in score["layers"].values():
            layer.update(complete=False, diagnostic_score=layer["score"])
        return score

    monkeypatch.setattr(expected_evaluation, "grade_expected", unsupported)
    index_path = expected_evaluation.evaluate_saved(run, tmp_path / "scores", expected_root=expected,
        freeze=freeze, diagnostic=diagnostic, workers=1)
    index = read_json(index_path)
    assert index["state"] == "blocked"
    assert "summary" not in index
    for record in index["records"]:
        score = read_json(index_path.parent / record["path"])
        assert score["score"] is None and score["quality_scores_withheld"] is True
        assert all(layer["score"] is None and layer["numerator"] is None and "diagnostic_score" not in layer
                   for layer in score["layers"].values())


def test_missing_expected_syntax_blocks_without_becoming_candidate_zero(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import evaluate_saved
    from moparse_eval.packaging import read_json

    run, _, expected, _ = saved_run(tmp_path, monkeypatch)
    (expected / "invented/expected.md").unlink()
    index_path = evaluate_saved(run, tmp_path / "diagnosis", expected_root=expected, diagnostic=True, workers=1)
    index = read_json(index_path)
    assert index["state"] == "blocked"
    assert len(index["records"]) == 8
    assert {item["reason"] for item in index["blockers"]} == {"selected_expected_reader_failure"}
    score = read_json(index_path.parent / index["records"][0]["path"])
    assert score["layers"]["T"]["denominator"] is None
    assert score["status"] == "software_failure"


def test_grader_exception_is_retained_as_an_explicit_software_blocker(tmp_path, monkeypatch):
    from moparse_eval import expected_evaluation
    from moparse_eval.packaging import read_json

    run, _, expected, freeze = saved_run(tmp_path, monkeypatch)

    def broken(*_args):
        raise ValueError("independently injected reader failure")

    monkeypatch.setattr(expected_evaluation, "grade_expected", broken)
    index_path = expected_evaluation.evaluate_saved(run, tmp_path / "scores", expected_root=expected, freeze=freeze, workers=1)
    index = read_json(index_path)
    assert index["state"] == "blocked"
    assert "summary" not in index
    assert len(index["blockers"]) == 8
    score = read_json(index_path.parent / index["records"][0]["path"])
    assert "independently injected" in score["blockers"][0]["error"]["message"]
    assert all(layer["numerator"] is None and layer["denominator"] is None for layer in score["layers"].values())


def test_pipeline_specific_requirement_mutation_blocks_all_formal_scores(tmp_path, monkeypatch):
    from moparse_eval import expected_evaluation
    from moparse_eval.packaging import read_json

    run, _, expected, freeze = saved_run(tmp_path, monkeypatch)
    original = expected_evaluation.grade_expected

    def mutated(requirements, observation):
        score = original(requirements, observation)
        if observation["pipeline"] == "P08":
            score["outcomes"] = [row for row in score["outcomes"] if not (row["layer"] == "B" and row["expected"]["attribute"] == "Profit")]
            score["layers"]["B"]["numerator"] -= 1
            score["layers"]["B"]["denominator"] -= 1
        return score

    monkeypatch.setattr(expected_evaluation, "grade_expected", mutated)
    index = read_json(expected_evaluation.evaluate_saved(run, tmp_path / "scores", expected_root=expected, freeze=freeze, workers=1))
    assert index["state"] == "blocked"
    assert "summary" not in index
    assert index["blockers"][0]["reason"] == "unequal_requirements_between_groups"


def test_changed_analysis_software_blocks_formal_summary(tmp_path, monkeypatch):
    from moparse_eval import cli
    from moparse_eval.expected_evaluation import evaluate_saved
    from moparse_eval.packaging import read_json

    run, _, expected, freeze = saved_run(tmp_path, monkeypatch)
    identities = iter([{"software_id": "independent-synthetic-version"}, {"software_id": "changed"}])
    monkeypatch.setattr(cli, "code_identity", lambda: next(identities))
    index = read_json(evaluate_saved(run, tmp_path / "scores", expected_root=expected, freeze=freeze, workers=1))
    assert index["state"] == "blocked"
    assert "summary" not in index
    assert index["blockers"][-1]["reason"] == "software_changed_during_analysis"


def test_sixteen_processes_match_serial_decisions_without_changing_original_costs(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import evaluate_saved
    from moparse_eval.packaging import read_json

    run, _, expected, freeze = saved_run(tmp_path, monkeypatch)
    serial_path = evaluate_saved(run, tmp_path / "serial", expected_root=expected, freeze=freeze, workers=1)
    parallel_path = evaluate_saved(run, tmp_path / "parallel", expected_root=expected, freeze=freeze, workers=16)
    serial, parallel = read_json(serial_path), read_json(parallel_path)
    assert parallel["analysis_workers"] == 16
    assert serial["summary"] == parallel["summary"]
    assert serial["execution_costs"] == parallel["execution_costs"]
    for left, right in zip(serial["records"], parallel["records"], strict=True):
        assert read_json(serial_path.parent / left["path"])["outcomes"] == read_json(parallel_path.parent / right["path"])["outcomes"]


def test_actual_baseline_and_current_texts_pair_with_their_own_native_group(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import PIPELINES, evaluate_saved
    from moparse_eval.packaging import read_json, write_json

    run, dataset, expected, freeze = saved_run(tmp_path, monkeypatch)
    native = read_json(run / "run.json")
    originals = {}
    for label, revenue in (("baseline", "19"), ("current", "17")):
        for pipeline in ("P07", "P08"):
            directory = tmp_path / label / pipeline.lower()
            final = directory / "candidate/final.md"
            final.parent.mkdir(parents=True)
            final.write_text(f"Name: Delta; Revenue: {revenue}; Profit: 5\n")
            source = next(case for case in native["cases"] if case["pipeline"] == pipeline)
            case = {**source, "final_markdown": "candidate/final.md", "input_pages": 1,
                    "baseline_observation_source": source["observation"], "status": "success",
                    "private_ir": {"Revenue": "17"}, "timing": {"processing_seconds": 0.25}}
            write_json(directory / "run.json", {"state": "completed", "baseline_run": str(run),
                "dataset": str(dataset), "native_pipeline": {"pipeline": pipeline}, "cases": [case],
                "software": {"software_id": f"original-{pipeline}-{label}"}})
            originals[final] = final.read_bytes()
            originals[directory / "run.json"] = (directory / "run.json").read_bytes()
    index_path = evaluate_saved(run, tmp_path / "scores", expected_root=expected, freeze=freeze,
        service_baseline_root=tmp_path / "baseline", current_root=tmp_path / "current", workers=1)
    index = read_json(index_path)
    assert index["state"] == "completed"
    assert len(index["records"]) == 12
    assert index["comparisons"]["native"] == list(PIPELINES)
    assert set(index["comparisons"]["service_pairs"]) == {"P07", "P08"}
    for pipeline in ("P07", "P08"):
        assert index["paired"][pipeline]["baseline_to_current"]["B"]["new_correct"] == 1
        assert index["paired"][pipeline]["baseline_to_current"]["B"]["lost_correct"] == 0
        assert index["paired"][pipeline]["native_to_baseline"]["B"]["lost_correct"] == 1
        assert index["paired"][pipeline]["native_to_current"]["B"]["lost_correct"] == 0
        assert index["summary"][pipeline]["layers"]["B"]["score"] == 100
        assert index["summary"][pipeline + "-baseline"]["layers"]["B"]["score"] == pytest.approx(200 / 3)
        record = next(row for row in index["records"] if row["group"] == pipeline + "-baseline")
        score = read_json(index_path.parent / record["path"])
        assert score["candidate_source"].endswith("candidate/final.md")
        assert score["execution_software_id"] == f"original-{pipeline}-baseline"
    assert "adoption" not in index
    assert all(path.read_bytes() == content for path, content in originals.items())


@pytest.mark.parametrize("selection", [[], ["synthetic"], ["unrecognized"]])
def test_formal_selection_is_rejected_before_reading_any_material(tmp_path, monkeypatch, selection):
    from moparse_eval import cli, expected_evaluation

    def forbidden(*_args, **_kwargs):
        pytest.fail("formal subset rejection must precede software identity or material reads")

    monkeypatch.setattr(cli, "code_identity", forbidden)
    monkeypatch.setattr(expected_evaluation, "read_json", forbidden)
    with pytest.raises(ValueError, match="diagnostic-only.*full declared scope"):
        expected_evaluation.evaluate_saved(tmp_path / "native", tmp_path / "output",
            expected_root=tmp_path / "expected", sample_ids=selection)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("selection", [[], ["synthetic", "synthetic"], [""], [1]])
def test_diagnostic_selection_requires_nonempty_distinct_explicit_identities(tmp_path, monkeypatch, selection):
    from moparse_eval import cli, expected_evaluation

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid diagnostic selection must not read any material")

    monkeypatch.setattr(cli, "code_identity", forbidden)
    monkeypatch.setattr(expected_evaluation, "read_json", forbidden)
    with pytest.raises(ValueError, match="nonempty distinct"):
        expected_evaluation.evaluate_saved(tmp_path / "native", tmp_path / "output",
            expected_root=tmp_path / "expected", sample_ids=selection, diagnostic=True)


def selected_saved_run(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import PIPELINES
    from moparse_eval.expected_readback import markdown_observation
    from moparse_eval.packaging import read_json, write_json

    run, dataset, expected, freeze = saved_run(tmp_path, monkeypatch)
    session, manifest = read_json(run / "run.json"), read_json(dataset / "manifest.json")
    bodies = {"synthetic": "Name: Delta; Revenue: 17; Profit: 5\n",
              "second": "Name: Echo; Revenue: 29; Profit: 7\n",
              "third": "Name: Theta; Revenue: 31; Profit: 9\n"}
    input_paths = [expected / "invented/expected.md"]
    for sample_id in ("second", "third"):
        document = expected / sample_id
        document.mkdir()
        (document / "expected.md").write_text(bodies[sample_id])
        write_json(document / "manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {
            "entries": [{"source_pages": [1], "markdown_lines": [1, 1]}]}})
        input_paths.append(document / "expected.md")
        manifest["samples"].append({"id": sample_id, "document_id": sample_id, "source_pages": [1]})
        for pipeline in PIPELINES:
            relative = f"artifacts/{pipeline}/quality800-r1/{sample_id}/observation.json"
            write_json(run / relative, markdown_observation(bodies[sample_id], sample_id=sample_id, pipeline=pipeline, pages=[1]))
            session["cases"].append({"pipeline": pipeline, "sample_id": sample_id, "suite": "quality800",
                "phase": "measured", "repetition": 1, "observation": relative})
    write_json(run / "run.json", session)
    write_json(dataset / "manifest.json", manifest)
    input_paths.extend([run / "run.json", dataset / "manifest.json"])
    input_paths.extend(run / case["observation"] for case in session["cases"])
    for label in ("baseline", "current"):
        for pipeline in ("P07", "P08"):
            directory = tmp_path / label / pipeline.lower()
            cases = []
            for source in (case for case in session["cases"] if case["pipeline"] == pipeline):
                final_relative = f"candidate/{source['sample_id']}/final.md"
                final = directory / final_relative
                final.parent.mkdir(parents=True)
                final.write_text(bodies[source["sample_id"]])
                input_paths.append(final)
                cases.append({**source, "final_markdown": final_relative, "input_pages": 1,
                    "baseline_observation_source": source["observation"], "status": "success"})
            write_json(directory / "run.json", {"state": "completed", "baseline_run": str(run),
                "dataset": str(dataset), "native_pipeline": {"pipeline": pipeline}, "cases": cases,
                "software": {"software_id": f"original-{pipeline}-{label}"}})
            input_paths.append(directory / "run.json")
    return run, expected, freeze, {path: path.read_bytes() for path in input_paths}


def test_unknown_diagnostic_sample_is_rejected_before_candidate_or_reference_reading(tmp_path, monkeypatch):
    from moparse_eval import expected_evaluation

    run, _, expected, _ = saved_run(tmp_path, monkeypatch)

    def forbidden(*_args, **_kwargs):
        pytest.fail("unknown selection cannot read expected or candidate content")

    monkeypatch.setattr(expected_evaluation, "read_expected", forbidden)
    monkeypatch.setattr(expected_evaluation, "native_observation", forbidden)
    with pytest.raises(ValueError, match="unknown declared sample: absent"):
        expected_evaluation.evaluate_saved(run, tmp_path / "output", expected_root=expected,
            diagnostic=True, sample_ids=["absent"])
    assert not (tmp_path / "output").exists()


def test_selected_diagnostic_uses_the_same_two_sample_scopes_across_all_twelve_groups(tmp_path, monkeypatch):
    from moparse_eval import expected_evaluation
    from moparse_eval.packaging import read_json

    run, expected, _, originals = selected_saved_run(tmp_path, monkeypatch)
    original_read, original_expected = expected_evaluation.read_json, expected_evaluation.read_expected
    seen_expected = []

    def read_selected_content_only(path):
        assert not (path.name == "observation.json" and "third" in path.parts), "unselected candidate body was read"
        return original_read(path)

    def selected_expected(sample, *args, **kwargs):
        assert sample["id"] in {"synthetic", "second"}
        seen_expected.append(sample["id"])
        return original_expected(sample, *args, **kwargs)

    monkeypatch.setattr(expected_evaluation, "read_json", read_selected_content_only)
    monkeypatch.setattr(expected_evaluation, "read_expected", selected_expected)
    selection = ["synthetic", "second"]
    index_path = expected_evaluation.evaluate_saved(run, tmp_path / "diagnosis", expected_root=expected,
        service_baseline_root=tmp_path / "baseline", current_root=tmp_path / "current",
        diagnostic=True, sample_ids=selection, workers=1)
    index = read_json(index_path)
    assert selection == ["synthetic", "second"]
    assert sorted(seen_expected) == ["second", "synthetic"]
    assert index["full_declared_samples"] == 3
    assert index["diagnostic_selected_samples"] == ["second", "synthetic"]
    assert index["full_scope_traversed"] is False
    assert index["expected_comparison_complete"] is False
    assert len(index["groups"]) == 12 and len(index["records"]) == 24
    assert "summary" not in index and "paired" not in index
    assert index["execution_costs"]["status"] == "not_aggregated_in_selected_diagnosis"
    for sample_id in selection:
        records = [record for record in index["records"] if record["sample_id"] == sample_id]
        assert len(records) == 12
        requirement_sets = []
        for record in records:
            score = read_json(index_path.parent / record["path"])
            assert score["score"] is None
            assert all(layer["score"] is None and layer["numerator"] is None for layer in score["layers"].values())
            requirement_sets.append([(row["layer"], row["id"], row["expected"]) for row in score["outcomes"]])
        assert requirement_sets[0]
        assert all(items == requirement_sets[0] for items in requirement_sets)
    assert all(path.read_bytes() == original for path, original in originals.items())


def test_diagnostic_default_still_traverses_the_entire_declared_scope(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import evaluate_saved
    from moparse_eval.packaging import read_json

    run, _, expected, _ = saved_run(tmp_path, monkeypatch)
    index = read_json(evaluate_saved(run, tmp_path / "diagnosis", expected_root=expected, diagnostic=True, workers=1))
    assert index["full_declared_samples"] == 1
    assert index["diagnostic_selected_samples"] == ["synthetic"]
    assert index["full_scope_traversed"] is True
    assert index["expected_comparison_complete"] is False
    assert index["diagnostic_selection_requested"] is False
    assert "summary" not in index


def test_selected_diagnostic_cannot_bypass_a_declared_group_scope_mismatch(tmp_path, monkeypatch):
    from moparse_eval.expected_evaluation import evaluate_saved
    from moparse_eval.packaging import read_json, write_json

    run, expected, _, _ = selected_saved_run(tmp_path, monkeypatch)
    path = tmp_path / "current/p08/run.json"
    execution = read_json(path)
    execution["cases"] = [case for case in execution["cases"] if case["sample_id"] != "third"]
    write_json(path, execution)
    with pytest.raises(ValueError, match="same quality samples"):
        evaluate_saved(run, tmp_path / "diagnosis", expected_root=expected,
            service_baseline_root=tmp_path / "baseline", current_root=tmp_path / "current",
            diagnostic=True, sample_ids=["synthetic", "second"], workers=1)
    assert not (tmp_path / "diagnosis").exists()


def test_cli_sample_selection_is_diagnostic_only_before_execution(tmp_path, monkeypatch):
    from moparse_eval import expected_evaluation

    def forbidden(*_args, **_kwargs):
        pytest.fail("formal --sample must fail before saved execution")

    monkeypatch.setattr(expected_evaluation, "evaluate_saved", forbidden)
    monkeypatch.setattr("sys.argv", ["expected_evaluation", "--baseline", str(tmp_path / "native"),
        "--output", str(tmp_path / "output"), "--sample", "synthetic"])
    with pytest.raises(SystemExit) as error:
        expected_evaluation.main()
    assert error.value.code == 2


def test_cli_repeated_sample_arguments_reach_only_diagnostic_traversal(tmp_path, monkeypatch):
    from moparse_eval import expected_evaluation
    from moparse_eval.packaging import write_json

    calls = []

    def saved_diagnosis(_baseline, output, **kwargs):
        calls.append(kwargs)
        write_json(output / "index.json", {"state": "diagnostic_completed"})
        return output / "index.json"

    monkeypatch.setattr(expected_evaluation, "evaluate_saved", saved_diagnosis)
    monkeypatch.setattr("sys.argv", ["expected_evaluation", "--baseline", str(tmp_path / "native"),
        "--output", str(tmp_path / "diagnosis"), "--diagnostic", "--sample", "first", "--sample", "second"])
    assert expected_evaluation.main() == 0
    assert len(calls) == 1
    assert calls[0]["diagnostic"] is True
    assert calls[0]["sample_ids"] == ["first", "second"]
    assert calls[0]["workers"] == 16
