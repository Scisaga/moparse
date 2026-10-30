"""CPU replay isolation and saved orientation using synthetic files only."""

from pathlib import Path

import pymupdf
import pytest

from moparse_eval.packaging import write_json
from moparse_eval.service_evaluation import (
    docker_command,
    oriented_source,
    paired_native_index,
    require_replay_ready,
    require_shared_scoring,
)


@pytest.mark.parametrize('pipeline', ['P07', 'P08'])
def test_candidate_container_has_neither_references_network_nor_gpu(tmp_path: Path, pipeline: str):
    run = tmp_path / "run"
    run.mkdir()
    write_json(run / "run.json", {
        "baseline_run": str(tmp_path / "baseline"), "dataset": str(tmp_path / "dataset"),
        "execution_environment": {"image": "synthetic-pinned-image"},
        "native_pipeline": {"pipeline": pipeline},
    })
    command = docker_command(run, "measured", "synthetic-owner")
    mounts = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "--volume"]

    assert f"{tmp_path / 'dataset/inputs'}:/inputs:ro" in mounts
    assert f"{tmp_path / 'baseline/artifacts' / pipeline}:/native:ro" in mounts
    assert f"{run / 'candidate'}:/output:rw" in mounts
    assert f"{run}:/output:rw" not in mounts
    assert not any("references" in mount or "expected" in mount for mount in mounts)
    assert command[command.index("--network") + 1] == "none"
    assert "--gpus" not in command and "--device" not in command
    assert "NVIDIA_VISIBLE_DEVICES=void" in command
    assert command[command.index("--memory") + 1] == "8g"


def test_saved_orientation_reuses_the_producer_frame_without_mutating_input(tmp_path: Path):
    source = tmp_path / "synthetic.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=120, height=240)
        page.insert_text((20, 30), "Authored fixture")
        page.set_rotation(90)
        document.save(source)
    before = source.read_bytes()
    target = tmp_path / "oriented.pdf"
    result = oriented_source(source, {"page_processing": [
        {"page": 1, "rotation_clockwise": 90},
    ]}, target)

    assert result == target and source.read_bytes() == before
    with pymupdf.open(result) as document:
        assert document[0].rotation == 180
    assert oriented_source(source, {"page_processing": [
        {"page": 1, "rotation_clockwise": 0},
    ]}, target) == source


@pytest.mark.parametrize("error", [
    {"code": "native_pages_not_a_list"},
    {"error": "mineru_declared_middle_document_unavailable"},
    {"projection_errors": [{"code": "offline_typed_projection_failed"}]},
])
def test_engineering_readback_failure_cannot_be_scored_as_parser_omission(error):
    with pytest.raises(RuntimeError, match="engineering readback"):
        require_replay_ready({"errors": [error]})


def test_received_local_structure_warning_can_retain_valid_neighbors():
    require_replay_ready({"errors": [{"warnings": ["mineru_native_local_region_unreadable"]}]})


def test_final_reader_can_be_fixed_without_changing_shared_scoring_or_execution():
    identity = {"module_sha256": {"scoring.py": "fixed", "service_observation.py": "old"},
                "support_module_sha256": {"app/service.py": "fixed"},
                "python": "fixed-python", "dependencies": {"edlib": "fixed"}}
    revised = {**identity, "module_sha256": {**identity["module_sha256"],
                                            "service_observation.py": "corrected"}}
    require_shared_scoring({"software": identity}, revised)
    with pytest.raises(ValueError, match="shared scoring"):
        require_shared_scoring({"software": identity}, {
            **revised, "module_sha256": {**revised["module_sha256"], "scoring.py": "changed"}})
    require_shared_scoring({"software": identity}, {
        **revised, "module_sha256": {**revised["module_sha256"], "scoring.py": "validated-fix"}},
        paired_native_rescore=True)
    with pytest.raises(ValueError, match="shared scoring"):
        require_shared_scoring({"software": identity}, {
            **revised, "module_sha256": {**revised["module_sha256"], "matching.py": "validated-fix"}})
    require_shared_scoring({"software": identity}, {
        **revised, "module_sha256": {**revised["module_sha256"], "matching.py": "validated-fix"}},
        paired_native_rescore=True)
    with pytest.raises(ValueError, match="shared scoring"):
        require_shared_scoring({"software": identity}, {
            **revised, "module_sha256": {**revised["module_sha256"], "native_readback.py": "changed"}},
            paired_native_rescore=True)
    with pytest.raises(ValueError, match="implementation or scoring dependencies"):
        require_shared_scoring({"software": identity}, {**revised, "dependencies": {"edlib": "changed"}})


def test_paired_native_analysis_uses_current_unified_identity_without_withdrawn_scores(tmp_path: Path):
    write_json(tmp_path / "run.json", {"latest_scores": "current/index.json"})
    index = {"software": {"software_id": "current"}, "unscored": []}
    write_json(tmp_path / "current/index.json", index)
    assert paired_native_index(tmp_path, {"software_id": "current"}) == index
    with pytest.raises(ValueError, match="same current unified software"):
        paired_native_index(tmp_path, {"software_id": "old"})
    write_json(tmp_path / "current/index.json", {**index, "unscored": ["unfinished"]})
    with pytest.raises(ValueError, match="finish unified"):
        paired_native_index(tmp_path, {"software_id": "current"})
