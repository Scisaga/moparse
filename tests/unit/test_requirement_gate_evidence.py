"""Independent source/evidence binding mutations over controlled generated JSON."""

from copy import deepcopy

import pytest
from requirement_gate_fixture import artifact, controlled_gate

from moparse_eval.packaging import read_json, write_json
from moparse_eval.requirement_gate import (
    replay_gate_receipt,
    validate_expected_structure_gate,
    validate_replay_gate_receipt,
)


def test_bare_status_cannot_start_a_replay():
    with pytest.raises(ValueError, match="requirement index"):
        validate_expected_structure_gate({"expected_structure_gate": {"status": "passed", "software_id": "current"}}, "current")


def test_complete_controlled_artifacts_are_bound_without_candidate_or_pdf_reads(tmp_path):
    validation = controlled_gate(tmp_path)
    index = validate_expected_structure_gate(validation, "controlled-source", scope={"fixture"})
    assert [row["sample_id"] for row in index["records"]] == ["fixture"]
    receipt = replay_gate_receipt(validation, "controlled-source", scope={"fixture"})
    validate_replay_gate_receipt(receipt, "controlled-source", scope={"fixture"})
    assert "path" not in repr(receipt) and "Name" not in repr(receipt) and "Revenue" not in repr(receipt)


@pytest.mark.parametrize("source", [None, {"sample_id": "another", "targets": []}, {"sample_id": "fixture"}])
def test_invalid_external_source_map_cannot_silently_disable_canonical_binding(tmp_path, source):
    validation = controlled_gate(tmp_path)
    with pytest.raises(ValueError, match="actual authorized expected"):
        validate_expected_structure_gate(validation, "controlled-source", expected_by_sample={"fixture": source})


@pytest.mark.parametrize("mutation", ["missing", "wrong_digest", "old_source", "different_scope", "pending", "missing_inventory"])
def test_missing_stale_or_incomplete_requirement_manifest_fails_closed(tmp_path, mutation):
    validation = controlled_gate(tmp_path)
    gate = validation["expected_structure_gate"]
    if mutation == "missing":
        (tmp_path / "index.json").unlink()
    elif mutation == "wrong_digest":
        gate["requirement_index"]["sha256"] = "0" * 64
    elif mutation == "different_scope":
        with pytest.raises(ValueError, match="sample scope"):
            validate_expected_structure_gate(validation, "controlled-source", scope={"another"})
        return
    else:
        index = read_json(tmp_path / "index.json")
        if mutation == "old_source":
            index["software_id"] = "old"
        elif mutation == "pending":
            index["semantic_complete"] = False
        else:
            index.pop("source_obligation_inventory_complete")
        write_json(tmp_path / "index.json", index)
        gate["requirement_index"] = artifact(tmp_path / "index.json")
    with pytest.raises(ValueError, match="expected structure gate"):
        validate_expected_structure_gate(validation, "controlled-source")


@pytest.mark.parametrize("purpose", ["oracle", "mutations", "comparison"])
@pytest.mark.parametrize("mutation", ["absent", "changed", "old_index", "self_derived", "known_defect", "missing_category", "mismatch", "no_input", "duplicate_case"])
def test_independent_evidence_cannot_be_replaced_by_flags_totals_or_partial_observations(tmp_path, purpose, mutation):
    validation = controlled_gate(tmp_path)
    gate = validation["expected_structure_gate"]
    path = tmp_path / f"{purpose}.json"
    if mutation == "absent":
        gate["evidence"].pop(purpose)
    elif mutation == "changed":
        path.write_text(path.read_text() + "\n")
    else:
        record = read_json(path)
        if mutation == "old_index":
            record["requirement_index_sha256"] = "0" * 64
        elif mutation == "self_derived":
            record["oracle_origin"] = "production_compiler"
        elif mutation == "known_defect":
            record["known_defects"] = ["false acceptance"]
        elif mutation == "missing_category":
            record["cases"].pop()
        elif mutation == "mismatch":
            record["cases"][0]["observed"] = {"accepted": True}
        elif mutation == "no_input":
            record["cases"][0].pop("input")
        else:
            record["cases"].append(deepcopy(record["cases"][0]))
        write_json(path, record)
        gate["evidence"][purpose] = artifact(path)
    with pytest.raises(ValueError, match="expected structure gate"):
        validate_expected_structure_gate(validation, "controlled-source")


def test_changed_generated_view_fails_even_if_the_manifest_is_still_unchanged(tmp_path):
    validation = controlled_gate(tmp_path)
    view = tmp_path / "samples/fixture.json"
    view.write_text(view.read_text() + "\n")
    with pytest.raises(ValueError, match="requirement view"):
        validate_expected_structure_gate(validation, "controlled-source")


@pytest.mark.parametrize("mutation", ["software", "scope", "digest", "extra_path"])
def test_worker_receipt_cannot_drift_or_carry_reference_locations(tmp_path, mutation):
    validation = controlled_gate(tmp_path)
    receipt = replay_gate_receipt(validation, "controlled-source")
    if mutation == "software":
        receipt["software_id"] = "old"
    elif mutation == "scope":
        receipt["sample_ids"] = ["another"]
    elif mutation == "digest":
        receipt["evidence_sha256"]["oracle"] = "0" * 64
    else:
        receipt["expected_path"] = "/forbidden"
    with pytest.raises(ValueError, match="expected structure gate"):
        validate_replay_gate_receipt(receipt, "controlled-source", scope={"fixture"})
