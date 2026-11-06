"""Real spawned compilation of invented sources, with deterministic failures."""

import inspect
import json
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

import pytest

from moparse_eval.cli import code_identity
from moparse_eval.requirement_graph import (
    _compile_saved_requirement_view,
    compile_saved_requirements,
)


def fixture(tmp_path, *, failed_view=False):
    references, dataset, run = tmp_path / "references", tmp_path / "dataset", tmp_path / "saved-native"
    dataset.mkdir()
    run.mkdir()
    samples = []
    for sample_id, text in (("zeta", "Name: Vega; Revenue: 17\n"), ("alpha", "Name: Orion; Profit: 5\n")):
        document = references / ("invented-" + sample_id)
        document.mkdir(parents=True)
        (document / "expected.md").write_text(text)
        (document / "manifest.json").write_text(json.dumps({"markdown": {"path": "expected.md"},
            "source_map": {"entries": [{"source_pages": [1], "markdown_lines": [1, 1]}]}}))
        samples.append({"id": sample_id, "document_id": "invented-" + sample_id, "source_pages": [1]})
    if failed_view:
        # No source exists for this declared identity. Failure must remain in
        # the same full index beside the two successfully written views.
        samples.insert(1, {"id": "missing", "document_id": "invented-missing", "source_pages": [1]})
    (dataset / "manifest.json").write_text(json.dumps({"samples": samples, "suites": {"lite": [s["id"] for s in samples]}}))
    # There are deliberately no candidates, PDFs, observations or costs in
    # this fixture. The compiler is authorized to read source text only.
    (run / "run.json").write_text(json.dumps({"dataset": str(dataset), "cases": [
        {"pipeline": "P01", "sample_id": s["id"], "phase": "measured", "suite": "quality800"} for s in samples]}))
    return references, run


@pytest.mark.parametrize("failed_view", [False, True])
def test_spawned_and_serial_views_are_identical_sorted_and_retain_every_declared_failure(tmp_path, failed_view):
    references, run = fixture(tmp_path, failed_view=failed_view)
    original = {path: path.read_bytes() for path in references.rglob("*") if path.is_file()}
    indexes = []
    outputs = []
    for workers in (1, 2):
        output = run / "requirements" / f"workers-{workers}"
        path = compile_saved_requirements(run, output, expected_root=references, workers=workers)
        index = json.loads(path.read_text())
        assert index.pop("analysis_workers") == workers
        assert index["declared_view_count"] == index["completed_view_count"] == (3 if failed_view else 2)
        assert [row["sample_id"] for row in index["records"]] == (["alpha", "missing", "zeta"] if failed_view else ["alpha", "zeta"])
        assert index["software_unchanged"] is True
        assert all(row["software_id"] == index["software_id"] and row["worker_software_unchanged"] for row in index["records"])
        assert index["candidate_read"] is index["pdf_or_image_read"] is False
        assert index["quality_scores_withheld"] is True
        indexes.append(index)
        outputs.append(output)
    assert indexes[0] == indexes[1]
    for sample_id in ("alpha", "zeta"):
        for suffix in ("json", "xml"):
            assert (outputs[0] / "samples" / f"{sample_id}.{suffix}").read_bytes() == (outputs[1] / "samples" / f"{sample_id}.{suffix}").read_bytes()
    assert {path: path.read_bytes() for path in original} == original
    if failed_view:
        index = indexes[1]
        [failure] = [row for row in index["records"] if row["sample_id"] == "missing"]
        assert failure["semantic_complete"] is False and failure["graph_written"] is False
        assert failure["disposition"] == "software_source_integrity_failure"
        assert failure["error"]["type"] in {"FileNotFoundError", "ExpectedReadError"}
        assert index["unresolved_reasons"]["compiler_source_integrity_failure"] == 1
        assert index["state"] == "structure_blocked"
        assert index["inventory_validation"]["status"] == "not_passed"


def test_each_spawned_worker_rejects_a_different_software_identity_before_source_read(tmp_path):
    output = tmp_path / "requirements"
    job = ({"id": "identity-guard", "document_id": "no-source", "source_pages": [1]},
           tmp_path / "absent-references", output, "not-the-current-software")
    with ProcessPoolExecutor(max_workers=2, mp_context=get_context("spawn")) as pool:
        row, reasons = pool.submit(_compile_saved_requirement_view, job).result(timeout=30)
    assert row["sample_id"] == "identity-guard"
    assert row["semantic_complete"] is False and row["worker_software_unchanged"] is False
    assert row["error"]["message"] == "worker software identity differs from the compilation freeze"
    assert reasons == {"compiler_software_identity_failure": 1}
    assert not output.exists()


def test_parent_identity_change_blocks_the_full_index_without_removing_views(tmp_path, monkeypatch):
    references, run = fixture(tmp_path)
    real_identity = code_identity()
    calls = 0
    def changing_identity():
        nonlocal calls
        calls += 1
        # Parent before + 2 * (worker-before/after) are stable. The final
        # parent identity differs, and must not leave an accepted structure.
        return real_identity if calls <= 5 else {**real_identity, "software_id": "changed-at-end"}
    monkeypatch.setattr("moparse_eval.cli.code_identity", changing_identity)
    path = compile_saved_requirements(run, run / "requirements" / "identity-change", expected_root=references)
    index = json.loads(path.read_text())
    assert len(index["records"]) == index["declared_view_count"] == 2
    assert index["software_unchanged"] is False
    assert index["semantic_complete"] is False and index["state"] == "structure_blocked"
    assert index["unresolved_reasons"]["compiler_software_identity_failure"] == 1


@pytest.mark.parametrize("workers", [0, -1, 17, True, 1.5])
def test_invalid_analysis_parallelism_fails_before_any_source_or_output_access(tmp_path, workers):
    with pytest.raises(ValueError, match="workers"):
        compile_saved_requirements(tmp_path / "missing", tmp_path / "missing" / "requirements" / "view", workers=workers)
    assert not (tmp_path / "missing").exists()


def test_source_compiler_preserves_the_serial_api_default():
    assert inspect.signature(compile_saved_requirements).parameters["workers"].default == 1
