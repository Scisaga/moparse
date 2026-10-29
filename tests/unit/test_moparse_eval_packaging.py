from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from moparse_eval.packaging import package_dataset, read_selection


def authored_fixture(root: Path) -> dict:
    source = root / "original.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), "Synthetic original")
        page.set_rotation(90)
        document.new_page().insert_text((40, 40), "Another synthetic page")
        document.save(source)
    reference = root / "reference"
    (reference / "assets").mkdir(parents=True)
    (reference / "assets" / "source.bin").write_bytes(b"unaltered synthetic asset")
    (reference / "expected.md").write_text("# Synthetic reference\n\nA\uff0fB\n")
    (reference / "manifest.json").write_text(
        json.dumps({"source": {"filename": "original.pdf", "pages": 2}})
    )
    return {
        "name": "synthetic-lite",
        "kind": "lite",
        "state": "draft",
        "declared_input_pages": 1,
        "documents": [
            {"document_id": "fixture", "source_pdf": "original.pdf", "reference_dir": "reference"}
        ],
        "samples": [
            {
                "id": "page-one",
                "document_id": "fixture",
                "source_pages": [1],
                "review_status": "pending",
                "evaluation": {"sample_id": "page-one", "units": [], "review_status": "pending"},
            }
        ],
    }


def test_package_retains_pdf_objects_reference_bytes_and_pending_state(tmp_path, monkeypatch):
    selection = authored_fixture(tmp_path)
    source_reference = (tmp_path / "reference" / "expected.md").read_bytes()
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection))

    def forbidden_text_extraction(*args, **kwargs):
        raise AssertionError("packaging must not extract source text")

    monkeypatch.setattr(pymupdf.Page, "get_text", forbidden_text_extraction)
    destination = tmp_path / "portable"
    result = package_dataset(selection_path, destination, source_root=tmp_path)
    assert result["state"] == "draft"
    assert result["samples"][0]["review_status"] == "pending"
    assert result["corpus_acceptance"] == "not_performed_by_packaging"
    assert (destination / "references/fixture/expected.md").read_bytes() == source_reference
    with pymupdf.open(destination / "inputs/page-one.pdf") as materialized:
        assert materialized[0].rotation == 90
    assert (destination / "references/fixture/assets/source.bin").read_bytes() == (
        b"unaltered synthetic asset"
    )


def test_full_is_verbatim_snapshot_not_new_review(tmp_path):
    selection = authored_fixture(tmp_path)
    selection["kind"] = "full"
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection))
    destination = tmp_path / "portable"
    result = package_dataset(selection_path, destination, source_root=tmp_path)
    assert (destination / "inputs/fixture.pdf").read_bytes() == (
        tmp_path / "original.pdf"
    ).read_bytes()
    assert result["samples"][0]["evaluation"] is None
    assert result["samples"][0]["review_status"] == "historical_reference"
    with pytest.raises(FileExistsError):
        package_dataset(selection_path, destination, source_root=tmp_path)


def test_author_selections_are_explicitly_concatenated_without_discovery(tmp_path):
    (tmp_path / "author-a.json").write_text(json.dumps({
        "documents": [{"document_id": "authored"}],
        "samples": [{"id": "first"}], "suites": {"lite": ["first"]},
    }))
    (tmp_path / "author-not-selected.json").write_text("not a declaration to ingest")
    root_selection = tmp_path / "selection.json"
    root_selection.write_text(json.dumps({
        "name": "synthetic", "includes": ["author-a.json"],
        "documents": [], "samples": [], "suites": {"perf80": []},
    }))
    selection = read_selection(root_selection, tmp_path)
    assert selection["samples"] == [{"id": "first"}]
    assert selection["suites"] == {"perf80": [], "lite": ["first"]}
