"""Externally authored source mutations cannot be hidden by coherent derived JSON."""

from copy import deepcopy

import pytest
from requirement_gate_fixture import artifact, controlled_evidence
from test_three_layer_orchestration import saved_run

from moparse_eval import expected_evaluation
from moparse_eval.expected_readback import read_expected
from moparse_eval.packaging import read_json, write_json
from moparse_eval.requirement_gate import validate_expected_structure_gate
from moparse_eval.requirement_graph import compile_requirement_graph, write_requirement_graph


@pytest.mark.parametrize("forged_text", [
    "Name: Echo; Revenue: 17; Profit: 5",
    "Name: Delta; Revenue: 17",
])
def test_synchronized_source_and_derived_mutation_is_rejected_against_authorized_expected_before_candidates(
        tmp_path, monkeypatch, forged_text):
    run, dataset, expected_root, freeze = saved_run(tmp_path, monkeypatch)
    canonical_path = expected_root / "invented/expected.md"
    canonical_before = canonical_path.read_bytes()
    sample = read_json(dataset / "manifest.json")["samples"][0]
    forged = deepcopy(read_expected(sample, expected_root))
    [target] = forged["targets"]
    target.update(text=forged_text, raw_text=forged_text, raw=forged_text)
    [raw_segment] = forged["authorized_raw_segments"]
    raw_segment["raw"] = forged_text
    graph = compile_requirement_graph(forged, comparison_contract='document_ast')
    assert graph["semantic_complete"] is True
    index_path = run / "requirements/current/index.json"
    index = read_json(index_path)
    row = index["records"][0]
    view = index_path.parent / row["json"]
    write_requirement_graph(graph, view, view.with_suffix(".xml"))
    row["generated_view_sha256"] = artifact(view)["sha256"]
    from moparse_eval.requirement_gate import _digest
    row['comparison_coverage_sha256'] = _digest(graph['comparison_coverage'])
    row["layers"] = {layer: len(graph["projections"][layer]) for layer in ("T", "L", "B")}
    write_json(index_path, index)
    frozen = read_json(freeze)
    frozen["validation"].update(controlled_evidence(tmp_path / "forged-gate", index_path, frozen["software_id"]))
    write_json(freeze, frozen)
    # Coherent generated JSON and its rebound evidence can validate internally;
    # the separate current canonical source must still defeat this forgery.
    validate_expected_structure_gate(frozen["validation"], frozen["software_id"], scope={"synthetic"})
    monkeypatch.setattr(expected_evaluation, "native_observation", lambda *_a, **_k: pytest.fail("candidate read before source binding"))
    with pytest.raises(ValueError, match="source|semantics"):
        expected_evaluation.evaluate_saved(run, tmp_path / "scores", expected_root=expected_root,
                                           freeze=freeze, workers=1)
    assert canonical_path.read_bytes() == canonical_before
    assert not (tmp_path / "scores").exists()


def test_gate_cannot_select_one_index_while_formal_loading_uses_another_path(tmp_path, monkeypatch):
    run, _, expected_root, freeze = saved_run(tmp_path, monkeypatch)
    original = run / "requirements/current/index.json"
    other = original.with_name("other-index.json")
    other.write_bytes(original.read_bytes())
    monkeypatch.setattr(expected_evaluation, "native_observation", lambda *_a, **_k: pytest.fail("candidate read before index binding"))
    with pytest.raises(ValueError, match="actual requested requirement index"):
        expected_evaluation.evaluate_saved(run, tmp_path / "scores", expected_root=expected_root,
                                           freeze=freeze, requirements=other, workers=1)
    assert not (tmp_path / "scores").exists()
