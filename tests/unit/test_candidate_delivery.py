"""Delivery checks over invented candidate files, without images or references."""

from moparse_eval.candidate_delivery import final_delivery, native_delivery
from moparse_eval.packaging import write_json


def test_native_asset_delivery_reads_only_the_declared_candidate_package(tmp_path):
    source = tmp_path / "observation.json"
    (tmp_path / "asset.bin").write_bytes(b"opaque candidate bytes")
    result = native_delivery(source, {"assets": [{"path": "asset.bin"}, {"path": "missing.bin"},
                                                {"path": "../outside.bin"}]})
    assert result["declared_files"] == 3 and result["files_present"] == 1


def test_public_image_reference_requires_a_saved_file_not_just_a_manifest_entry(tmp_path):
    candidate = tmp_path / "candidate"
    source = candidate / "artifacts/case/final.md"
    source.parent.mkdir(parents=True)
    url = "/v1/content/jobs/job/assets/image"
    markdown = f"![Opaque alt]({url})"
    write_json(source.with_name("final.json"), {"assets": [{"asset_id": "image", "filename": "test.bin", "download_url": url}],
                                              "renderings": {"markdown": "This hidden text cannot supply an answer."}})
    before = final_delivery(source, markdown, {"job_id": "job"})
    assert before["references_without_file"] == 1
    asset = candidate / "data/jobs/job/assets/original/image__test.bin"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"opaque candidate bytes")
    after = final_delivery(source, markdown, {"job_id": "job"})
    assert after["files_present"] == after["references_with_file"] == 1
