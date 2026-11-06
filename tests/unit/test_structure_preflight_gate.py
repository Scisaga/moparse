"""Stage order and common-model guards over an entirely invented saved run."""

import pytest
from test_three_layer_orchestration import saved_run, selected_saved_run

from moparse_eval import expected_evaluation as evaluation
from moparse_eval.packaging import read_json, write_json


def test_full_diagnosis_cannot_start_candidates_with_unexplained_expected_semantics(tmp_path, monkeypatch):
    run, _, expected, _ = saved_run(tmp_path, monkeypatch, text="The total gyrated 17.\n")

    def forbidden(*args, **kwargs):
        pytest.fail("source interpretation must finish before broad candidate comparison")

    monkeypatch.setattr(evaluation, "native_observation", forbidden)
    with pytest.raises(ValueError, match="complete expected semantics"):
        evaluation.evaluate_saved(run, tmp_path / "diagnosis", expected_root=expected, diagnostic=True, workers=1)
    status = read_json(tmp_path / "diagnosis/execution-status.json")
    assert status["state"] == "failed" and status["records"] == []
    assert status["expected_comparison_complete"] is False


@pytest.mark.parametrize("mutation", ["absent", "old_software", "no_evidence"])
def test_general_passed_freeze_cannot_replace_the_specific_structure_gate(tmp_path, monkeypatch, mutation):
    run, _, expected, freeze = saved_run(tmp_path, monkeypatch)
    record = read_json(freeze)
    if mutation == "absent":
        record["validation"].pop("expected_structure_gate")
    elif mutation == "old_software":
        record["validation"]["expected_structure_gate"]["software_id"] = "different"
    else:
        record["validation"]["expected_structure_gate"].pop("evidence")
    write_json(freeze, record)
    monkeypatch.setattr(evaluation, "native_observation", lambda *a, **k: pytest.fail("gate did not reject"))
    with pytest.raises(ValueError, match="expected structure gate"):
        evaluation.evaluate_saved(run, tmp_path / "scores", expected_root=expected, freeze=freeze, workers=1)
    assert not (tmp_path / "scores").exists()


def test_a_current_index_cannot_mix_an_old_two_group_execution_with_six_missing_deliveries(tmp_path):
    current = tmp_path / "current"
    write_json(current / "index.json", {"state": "active", "software_id": "new",
        "pipelines": {pipeline: {"run": "unused", "software_id": "new"} for pipeline in ("P07", "P08")}})
    with pytest.raises(ValueError, match="all eight"):
        evaluation._service_inputs(current, "P07", current=True)


def test_expected_is_compiled_once_before_the_eight_group_tasks(tmp_path, monkeypatch):
    from moparse_eval import reference_compiler

    run, expected, _, _ = selected_saved_run(tmp_path, monkeypatch)
    original, calls = reference_compiler.compile_reference_semantics, []

    def count(reference):
        calls.append(reference["sample_id"])
        return original(reference)

    monkeypatch.setattr(reference_compiler, "compile_reference_semantics", count)
    path = evaluation.evaluate_saved(run, tmp_path / "diagnosis", expected_root=expected, diagnostic=True,
                                     sample_ids=["synthetic"], workers=1)
    assert calls == ["synthetic"]
    assert len(read_json(path)["records"]) == 8
