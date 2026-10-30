"""Composition tests use invented execution metadata and opaque dummy bytes."""

from __future__ import annotations

import copy
import errno
import json
import os
from pathlib import Path
from typing import Any

import pytest

from moparse_eval import compose_runs


def _json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def _read(path: Path):
    return json.loads(path.read_text())


def _source(root: Path, *, replacement=False):
    root.mkdir()
    pipelines = ["P03", "P04"] if replacement else list(compose_runs.PIPELINES)
    session: dict[str, Any] = {
        "run_id": root.name, "formal": True, "suite": "lite", "state": "completed",
        "dataset": "/synthetic-never-open-dataset", "dataset_name": "synthetic-lite",
        "reference_freeze": {"frozen_at": "synthetic-freeze", "development_exposure": "synthetic-read"},
        "software": {"software_id": "new-execution" if replacement else "old-execution",
                     "git_head": "synthetic-code-head"},
        "software_snapshot": "artifacts/software", "created_at": "synthetic-start",
        "finished_at": "synthetic-finish", "errors": [], "configurations": [], "cases": [],
    }
    software = root / "artifacts/software/moparse_eval/executors.py"
    software.parent.mkdir(parents=True)
    software.write_text("# synthetic immutable source snapshot\n")
    schedule = [("warm", "preflight8", "warmup", 1),
                ("quality-a", "quality800", "measured", 1),
                ("quality-b", "quality800", "measured", 1),
                *[("perf", "perf80", "measured", repetition) for repetition in (1, 2, 3)]]
    inspection: dict[str, Any] = {"scope": "synthetic_immutable_image_check", "inspected_at": root.name, "pipelines": {}}
    for pipeline in pipelines:
        config = {"pipeline": pipeline, "dpi": 200, "models": {"vlm": "same-synthetic-model"},
                  "revisions": {"vlm": "same-synthetic-revision"},
                  "resources": {"cpus": 4, "memory_gib": 20},
                  "timeout_policy": {"frozen": True, "single_page_seconds": 54.0},
                  "runtime": {"image_id": "same-synthetic-worker-image"},
                  "inference_services": [{"image_id": "same-synthetic-gpu-image",
                                          "decoder": {"temperature": 0.0, "max_tokens": 64}}]}
        if replacement:
            config.update(compose_runs.PADDLE_AUTHORIZED_CHANGES)
        session["configurations"].append(config)
        _json(root / f"artifacts/{pipeline}/execution-config.json", config)
        _json(root / f"artifacts/{pipeline}/inference/inference-ownership.json",
              {"cleanup_confirmed": True, "marker": root.name})
        _json(root / f"artifacts/{pipeline}/inference/resources.json",
              {"observed_gpu1_peak_memory_mib": 1234, "marker": root.name})
        _json(root / f"artifacts/{pipeline}/worker-resources.json", {"marker": root.name})
        _json(root / f"artifacts/{pipeline}/worker-exit.json", {"ExitCode": 0})
        inspection["pipelines"][pipeline] = {"image_id": f"image-{root.name}",
            "versions": {"synthetic-package": root.name}, "inference": [
                {"role": "synthetic-gpu", "image_id": f"gpu-{root.name}",
                 "versions": {"transformers": "synthetic-gpu-version"}}]}
        for sample_id, suite, phase, repetition in schedule:
            relative = f"artifacts/{pipeline}/{phase}-{suite}-r{repetition}/{sample_id}/observation.json"
            session["cases"].append({"pipeline": pipeline, "sample_id": sample_id,
                "suite": suite, "phase": phase, "repetition": repetition, "observation": relative})
            case_dir = (root / relative).parent
            _json(case_dir / "observation.json", {
                "run_id": root.name, "pipeline": pipeline, "sample_id": sample_id,
                "dataset": "synthetic-lite", "suite": suite, "phase": phase,
                "repetition": repetition, "input_page_count": 1,
                "status": "historical-failure" if not replacement and pipeline in {"P03", "P04"} else "completed",
                "timing": {"processing_seconds": 7 if replacement else 3},
                "opaque_text": "invented output; helper must not open this file",
            })
            _json(case_dir / "native.json", {"opaque_native": root.name})
            (case_dir / "assets").mkdir()
            (case_dir / "assets/invented.bin").write_bytes(b"synthetic media, not a corpus asset")
    _json(root / "maintenance.json", {"phase": "restored", "marker": root.name})
    _json(root / "artifacts/service-restoration-verification.json", {"marker": root.name, "restored": True})
    _json(root / "artifacts/software-freeze-verification.json", {"marker": root.name, "unchanged": True})
    _json(root / "artifacts/software-inspection.json", inspection)
    (root / "execution-failure-notes.md").write_text("Synthetic historical facts.\n")
    (root / "visual-review/evidence").mkdir(parents=True)
    (root / "visual-review/README.md").write_text("Synthetic historical review.\n")
    (root / "visual-review/evidence/invented.bin").write_bytes(b"synthetic evidence")
    (root / "visual-review/reviewer.md").write_text("[old fragment](../artifacts/P03/)\n")
    operation = {"id": "synthetic-adjudication", "scope": "all_configurations_and_repetitions",
        "evidence_base": "run_directory", "decisions": [{
            "id": "synthetic-decision", "sample_id": "quality-a", "unit_id": "synthetic-unit",
            "action": "exclude_unit_pending", "reason": "invented pending judgment",
            "reviewers": ["synthetic-only"], "evidence": ["visual-review/evidence/invented.bin",
                                                           "visual-review/reviewer.md"]}]}
    operation_path = "artifacts/scores/historical/reference-adjudications.json"
    _json(root / operation_path, operation)
    session["latest_scores"] = "artifacts/scores/historical/index.json"
    _json(root / session["latest_scores"], {"score_id": "synthetic-old-score", "software": {
        "software_id": "historical-scorer-must-not-be-reused"}, "results": ["must-not-open-score.json"],
        "reference_adjudications": {"path": operation_path}})
    _json(root / "run.json", session)
    return session


@pytest.fixture
def runs(tmp_path):
    base, rerun, output = tmp_path / "base-run", tmp_path / "replacement-run", tmp_path / "final-run"
    _source(base)
    _source(rerun, replacement=True)
    return base, rerun, output


def test_composition_selects_whole_groups_and_keeps_original_ids_costs_and_versions(runs):
    base, rerun, output = runs
    before = {path: (path / "run.json").read_bytes() for path in (base, rerun)}
    assert compose_runs.prepare_composed_run(base, rerun, output) == output / "run.json"
    session = _read(output / "run.json")
    assert session["software"]["software_id"] is None
    assert session["software"]["kind"] == "mixed_execution_sources"
    assert "latest_scores" not in session and "software_snapshot" not in session
    assert len(session["cases"]) == 8 * 6
    assert {case["phase"] for case in session["cases"]} == {"warmup", "measured"}
    assert {case["repetition"] for case in session["cases"] if case["suite"] == "perf80"} == {1, 2, 3}
    for name in compose_runs.PIPELINES:
        selected = rerun if name in {"P03", "P04"} else base
        origin = session["execution_sources"][name]
        assert origin["source_run_id"] == selected.name
        assert origin["software"]["software_id"] == ("new-execution" if selected == rerun else "old-execution")
        case = next(item for item in session["cases"] if item["pipeline"] == name and item["sample_id"] == "quality-a")
        assert case["source_run_id"] == selected.name
        assert (output / case["observation"]).read_bytes() == (selected / case["observation"]).read_bytes()
        observation = _read(output / case["observation"])
        assert observation["run_id"] == selected.name
        assert observation["timing"]["processing_seconds"] == (7 if selected == rerun else 3)
        assert os.path.samefile(output / case["observation"], selected / case["observation"])
    for source, original in before.items():
        assert (source / "run.json").read_bytes() == original
        assert not os.path.samefile(output / "run.json", source / "run.json")
    # A future latest_scores update is confined to the new run metadata.
    session["latest_scores"] = "future-uniform-score-index.json"
    _json(output / "run.json", session)
    assert all((source / "run.json").read_bytes() == original for source, original in before.items())


def test_historical_failures_review_links_and_only_evidence_paths_are_transported(runs):
    base, rerun, output = runs
    source_path = "artifacts/scores/historical/reference-adjudications.json"
    original_bytes = (base / source_path).read_bytes()
    original = _read(base / source_path)
    compose_runs.prepare_composed_run(base, rerun, output)
    prefix = Path("artifacts/execution-sources/base")
    assert (output / prefix / source_path).read_bytes() == original_bytes
    assert (base / source_path).read_bytes() == original_bytes
    transported = _read(output / "reference-adjudications.json")
    expected = copy.deepcopy(original)
    for decision in expected["decisions"]:
        decision["evidence"] = [(prefix / path).as_posix() for path in decision["evidence"]]
    assert transported == expected
    for evidence in transported["decisions"][0]["evidence"]:
        assert (output / evidence).is_file()
    for name in ["P03", "P04"]:
        relative = f"artifacts/{name}/measured-quality800-r1/quality-a/observation.json"
        assert _read(output / prefix / relative)["status"] == "historical-failure"
        assert _read(output / relative)["status"] == "completed"
        assert not (output / prefix / "artifacts" / name).is_symlink()
    assert (output / prefix / "artifacts/P01").is_symlink()
    assert (output / prefix / "artifacts/P01").resolve() == output / "artifacts/P01"
    assert "不构成新重跑" in (output / "visual-review/README.md").read_text()


def test_two_maintenance_windows_and_selected_image_inspection_are_distinct(runs):
    base, rerun, output = runs
    compose_runs.prepare_composed_run(base, rerun, output)
    maintenance = _read(output / "maintenance.json")
    assert maintenance["phase"] == "not_a_new_maintenance_window"
    assert [window["source_run_id"] for window in maintenance["windows"]] == [base.name, rerun.name]
    assert all(window["phase"] == "restored" for window in maintenance["windows"])
    inspection = _read(output / "artifacts/software-inspection.json")
    assert inspection["inspected_at"] is None
    assert "no_new_inspection" in inspection["scope"]
    assert inspection["pipelines"]["P01"]["image_id"] == "image-base-run"
    assert inspection["pipelines"]["P03"]["image_id"] == "image-replacement-run"
    assert len(inspection["source_records"]) == 2
    plan = _read(output / "scoring-plan.json")
    assert plan["requires_one_common_scoring_software_identity"] is True
    assert len(plan["commands"]) == 2 and plan["commands"][0][3] == "score"
    assert plan["commands"][0][-1] == str(output / "reference-adjudications.json")
    assert plan["execution"] == "not_started_by_preparation_helper"
    assert not (output / "artifacts/scores").exists()


def test_preparation_never_reads_candidate_media_visual_evidence_or_dataset_bytes(runs, monkeypatch):
    base, rerun, output = runs
    read_text, read_bytes = Path.read_text, Path.read_bytes
    allowed = {"run.json", "maintenance.json", "software-inspection.json", "index.json",
               "reference-adjudications.json", "service-restoration-verification.json",
               "software-freeze-verification.json"}

    def guarded_text(path, *args, **kwargs):
        assert path.name in allowed, f"unexpected content read: {path}"
        return read_text(path, *args, **kwargs)

    def guarded_bytes(path, *args, **kwargs):
        assert path.name in allowed, f"unexpected content read: {path}"
        return read_bytes(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_text)
    monkeypatch.setattr(Path, "read_bytes", guarded_bytes)
    compose_runs.prepare_composed_run(base, rerun, output)


@pytest.mark.parametrize("mutation", ["running", "different-freeze", "different-model", "missing-case",
                                      "duplicate-case", "extra-quality-repetition", "wrong-observation-root"])
def test_incompatible_execution_metadata_is_not_silently_composed(runs, mutation):
    base, rerun, output = runs
    session = _read(rerun / "run.json")
    if mutation == "running":
        session["state"] = "running"
    elif mutation == "different-freeze":
        session["reference_freeze"]["frozen_at"] = "another-declaration"
    elif mutation == "different-model":
        session["configurations"][0]["revisions"]["vlm"] = "changed-model"
    elif mutation == "missing-case":
        session["cases"].pop()
    elif mutation == "duplicate-case":
        session["cases"].append(copy.deepcopy(session["cases"][0]))
    elif mutation == "extra-quality-repetition":
        session["cases"][1]["repetition"] = 2
    else:
        session["cases"][0]["observation"] = "../outside/observation.json"
    _json(rerun / "run.json", session)
    with pytest.raises(ValueError):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert not output.exists()


def test_missing_inspection_is_unknown_and_does_not_borrow_base_versions(runs):
    base, rerun, output = runs
    (rerun / "artifacts/software-inspection.json").unlink()
    compose_runs.prepare_composed_run(base, rerun, output)
    inspection = _read(output / "artifacts/software-inspection.json")
    assert "P01" in inspection["pipelines"]
    assert "P03" not in inspection["pipelines"] and "P04" not in inspection["pipelines"]


@pytest.mark.parametrize("change", ["worker-image", "gpu-image", "decoder", "package", "attention", "export", "retry"])
def test_all_other_paddle_configuration_changes_are_rejected(runs, change):
    base, rerun, output = runs
    session = _read(rerun / "run.json")
    config = session["configurations"][0]
    if change == "worker-image":
        config["runtime"]["image_id"] = "changed-worker"
    elif change == "gpu-image":
        config["inference_services"][0]["image_id"] = "changed-gpu"
    elif change == "decoder":
        config["inference_services"][0]["decoder"]["max_tokens"] = 128
    else:
        config[change] = {"unauthorized": "changed"}
    _json(rerun / "run.json", session)
    with pytest.raises(ValueError, match="fixed execution declarations differ"):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert not output.exists()


@pytest.mark.parametrize("field, value", [
    ("paddle_execution_mode", "fresh-thread"), ("paddle_execution_mode", None),
    ("paddle_use_queues", True), ("paddle_use_queues", 0),
])
def test_replacement_paddle_options_require_the_exact_authorized_values(runs, field, value):
    base, rerun, output = runs
    session = _read(rerun / "run.json")
    session["configurations"][0][field] = value
    _json(rerun / "run.json", session)
    with pytest.raises(ValueError, match="replacement must declare the authorized option"):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert not output.exists()


def test_authorized_paddle_changes_are_recursive_and_preserved_in_selected_configuration(runs):
    base, rerun, output = runs
    old, new = _read(base / "run.json"), _read(rerun / "run.json")
    for config in old["configurations"]:
        if config["pipeline"] in {"P03", "P04"}:
            config["inference_services"][0].update({"paddle_execution_mode": "fresh", "paddle_use_queues": True})
    for config in new["configurations"]:
        config["inference_services"][0].update(compose_runs.PADDLE_AUTHORIZED_CHANGES)
    _json(base / "run.json", old)
    _json(rerun / "run.json", new)
    compose_runs.prepare_composed_run(base, rerun, output)
    selected = _read(output / "run.json")["configurations"]
    assert [item for item in selected if item["pipeline"] in {"P03", "P04"}] == new["configurations"]


def test_nested_authorized_option_cannot_hide_an_unauthorized_new_value(runs):
    base, rerun, output = runs
    session = _read(rerun / "run.json")
    session["configurations"][0]["inference_services"][0]["paddle_use_queues"] = True
    _json(rerun / "run.json", session)
    with pytest.raises(ValueError, match="replacement option is not the authorized value"):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert not output.exists()


def test_restoration_and_software_freeze_metadata_are_independent_source_snapshots(runs):
    base, rerun, output = runs
    compose_runs.prepare_composed_run(base, rerun, output)
    session = _read(output / "run.json")
    for source in session["source_runs"]:
        original = base if source["alias"] == "base" else rerun
        for field, name in (("service_restoration_verification", "service-restoration-verification.json"),
                            ("software_freeze_verification", "software-freeze-verification.json")):
            path = output / source[field]["path"]
            source_path = original / "artifacts" / name
            assert path.read_bytes() == source_path.read_bytes()
            assert not os.path.samefile(path, source_path)
            assert source[field]["record"]["marker"] == original.name


def test_missing_optional_verification_records_stay_missing_without_fabrication(runs):
    base, rerun, output = runs
    (base / "artifacts/service-restoration-verification.json").unlink()
    (rerun / "artifacts/software-freeze-verification.json").unlink()
    compose_runs.prepare_composed_run(base, rerun, output)
    sources = {source["alias"]: source for source in _read(output / "run.json")["source_runs"]}
    assert "service_restoration_verification" not in sources["base"]
    assert "software_freeze_verification" not in sources["rerun"]
    markdown = (output / "execution-composition.md").read_text()
    assert "服务恢复核实记录" in markdown and "软件冻结核实记录" in markdown


def test_cross_filesystem_error_has_no_copy_fallback_and_rolls_back_only_new_stage(runs, monkeypatch):
    base, rerun, output = runs
    original = (base / "run.json").read_bytes()

    def exdev(*args, **kwargs):
        raise OSError(errno.EXDEV, "synthetic cross-filesystem link")

    monkeypatch.setattr(compose_runs.os, "link", exdev)
    with pytest.raises(OSError) as caught:
        compose_runs.prepare_composed_run(base, rerun, output)
    assert caught.value.errno == errno.EXDEV
    assert not output.exists()
    assert list(output.parent.glob(f".{output.name}-*")) == []
    assert (base / "run.json").read_bytes() == original


def test_output_collision_and_source_symlink_are_rejected_without_overwrite(runs):
    base, rerun, output = runs
    output.mkdir()
    sentinel = output / "unrelated.txt"
    sentinel.write_text("preserve")
    with pytest.raises(FileExistsError):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert sentinel.read_text() == "preserve"
    sentinel.unlink()
    output.rmdir()
    (base / "artifacts/P01/unsafe-link").symlink_to("/synthetic-never-open-dataset")
    with pytest.raises(ValueError, match="symlink"):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert not output.exists()


def test_historical_run_errors_are_not_relabelled_as_new_pipeline_failures(runs):
    base, rerun, output = runs
    old, new = _read(base / "run.json"), _read(rerun / "run.json")
    old["errors"] = [{"pipeline": "P03", "type": "historical-only"},
                     {"pipeline": "P01", "type": "selected-old-group"}, {"type": "old-window"}]
    new["errors"] = [{"pipeline": "P04", "type": "selected-new-group"}]
    _json(base / "run.json", old)
    _json(rerun / "run.json", new)
    compose_runs.prepare_composed_run(base, rerun, output)
    session = _read(output / "run.json")
    assert {error["type"] for error in session["errors"]} == {"selected-old-group", "old-window", "selected-new-group"}
    assert _read(output / "artifacts/execution-sources/base/run.json")["errors"] == old["errors"]


def test_composed_report_keeps_per_pipeline_sources_and_both_windows_without_scoring(runs):
    from moparse_eval.cli import report_run

    base, rerun, output = runs
    compose_runs.prepare_composed_run(base, rerun, output)
    session = _read(output / "run.json")
    index_path = "artifacts/scores/synthetic-common/index.json"
    # These are synthetic unscored placeholders, not a call to score_run or a
    # result sampled from a real run. report_run must never open a dataset here.
    _json(output / index_path, {"score_id": "synthetic-common", "software": {
        "software_id": "one-common-synthetic-scorer"}, "results": [], "unscored": [],
        "dataset_declaration": {"name": "synthetic-lite", "sample_metadata": {}}})
    session["latest_scores"] = index_path
    # This exercises rendering synthetic compositions, not formal admission.
    session.update(formal=False, development_experiment=True, experiment_id="synthetic-report-only")
    _json(output / "run.json", session)
    with pytest.raises(ValueError, match="target grading incomplete"):
        report_run(output)
    # This execution-only fixture declares no authored targets. Missing scores
    # for real admitted targets cannot be disguised as an empty comparison.
    index = _read(output / index_path)
    index["unscored"] = [{**case, "reason": "no_authored_scoring_reference"}
                         for case in session["cases"] if case["phase"] == "measured"]
    _json(output / index_path, index)
    assert report_run(output) == output / "report.md"
    report = _read(output / "summary.json")
    assert report["execution"]["execution_sources"] == session["execution_sources"]
    assert report["execution"]["source_runs"] == session["source_runs"]
    assert report["execution"]["composition"] == session["composition"]
    assert "appendix.md" in (output / "report.md").read_text()
    markdown = (output / "appendix.md").read_text()
    assert "| P01 | base-run | old-execution |" in markdown
    assert "| P03 | replacement-run | new-execution |" in markdown
    assert "| base-run | restored |" in markdown
    assert "| replacement-run | restored |" in markdown
    assert "统一评分软件身份：one-common-synthetic-scorer" in markdown
    assert "执行软件身份：None" not in markdown
    assert "维护恢复状态：not_a_new_maintenance_window" not in markdown
    assert report["groups"]


def test_regular_report_preserves_single_execution_identity_and_window():
    from moparse_eval.reporting import render_appendix

    markdown = render_appendix({"execution": {"run_id": "single", "state": "completed", "formal": True,
        "software": {"software_id": "one-execution"}}, "groups": [],
        "score_index": "synthetic/index.json", "scoring_software": {"software_id": "one-scorer"},
        "maintenance": {"phase": "restored"}})
    assert "执行软件身份：one-execution；评分软件身份：one-scorer" in markdown
    assert "维护恢复状态：restored" in markdown
    assert "逐管线执行来源" not in markdown


def test_source_artifacts_symlink_ancestor_is_rejected_without_reading_outside(runs):
    base, rerun, output = runs
    outside = rerun.parent / "outside-artifacts"
    (rerun / "artifacts").rename(outside)
    (rerun / "artifacts").symlink_to(outside, target_is_directory=True)
    before = (outside / "software-inspection.json").read_bytes()
    with pytest.raises(ValueError, match="symlink ancestor"):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert not output.exists()
    assert (outside / "software-inspection.json").read_bytes() == before


def test_source_score_metadata_symlink_ancestor_is_rejected_before_outside_read(runs, monkeypatch):
    base, rerun, output = runs
    outside = base.parent / "outside-scores"
    (base / "artifacts/scores").rename(outside)
    (base / "artifacts/scores").symlink_to(outside, target_is_directory=True)
    read_text = Path.read_text

    def guarded(path, *args, **kwargs):
        assert not path.is_relative_to(outside)
        assert not path.is_relative_to(base / "artifacts/scores")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    with pytest.raises(ValueError, match="symlink ancestor"):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert not output.exists()


@pytest.mark.parametrize("target", ["source-root", "source-parent", "destination-parent"])
def test_root_and_parent_symlink_paths_are_rejected(runs, target):
    base, rerun, output = runs
    if target == "source-root":
        alias = base.parent / "source-alias"
        alias.symlink_to(base, target_is_directory=True)
        base = alias
    elif target == "source-parent":
        alias = base.parent / "parent-alias"
        alias.symlink_to(base.parent, target_is_directory=True)
        rerun = alias / rerun.name
    else:
        alias = base.parent / "destination-alias"
        alias.symlink_to(base.parent, target_is_directory=True)
        output = alias / output.name
    with pytest.raises(ValueError, match="symlink ancestor"):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert not output.exists()


def test_source_and_destination_ancestor_overlap_is_rejected(runs):
    base, rerun, output = runs
    with pytest.raises((ValueError, FileExistsError)):
        compose_runs.prepare_composed_run(base, rerun, base.parent)
    with pytest.raises(ValueError, match="separate destination"):
        compose_runs.prepare_composed_run(base, rerun, base / "nested-destination")
    # An overlapping source root is rejected before inspecting its metadata.
    with pytest.raises(ValueError, match="separate destination"):
        compose_runs.prepare_composed_run(base.parent, rerun, output)
    assert not output.exists()


def test_wrong_software_snapshot_namespace_cannot_mutate_any_source_metadata(runs):
    base, rerun, output = runs
    session = _read(base / "run.json")
    session["software_snapshot"] = "artifacts"
    _json(base / "run.json", session)
    source = base / "artifacts/software-inspection.json"
    os.utime(source, ns=(1_000_000_000, 1_000_000_000))
    before_bytes, before_stat = source.read_bytes(), source.stat()
    with pytest.raises(ValueError, match="dedicated artifacts/software namespace"):
        compose_runs.prepare_composed_run(base, rerun, output)
    after_stat = source.stat()
    assert source.read_bytes() == before_bytes
    assert (after_stat.st_ino, after_stat.st_size, after_stat.st_mtime_ns) == (
        before_stat.st_ino, before_stat.st_size, before_stat.st_mtime_ns)
    assert not output.exists()


@pytest.mark.parametrize("writer", ["json", "text", "copy"])
def test_stage_metadata_writers_never_truncate_existing_hard_links(tmp_path, writer):
    source, target = tmp_path / "source.json", tmp_path / "stage.json"
    source.write_bytes(b'{"synthetic":"original"}\n')
    os.link(source, target)
    os.utime(source, ns=(1_000_000_000, 1_000_000_000))
    before_bytes, before_stat = source.read_bytes(), source.stat()
    with pytest.raises(FileExistsError):
        if writer == "json":
            compose_runs._write_json(target, {"synthetic": "changed"})
        elif writer == "text":
            compose_runs._write_text(target, "changed")
        else:
            compose_runs._copy_metadata(source, target)
    assert source.read_bytes() == before_bytes
    assert source.stat().st_mtime_ns == before_stat.st_mtime_ns


def test_case_identity_cannot_reuse_another_cases_observation(runs):
    base, rerun, output = runs
    session = _read(rerun / "run.json")
    first, second = [case for case in session["cases"]
                     if case["pipeline"] == "P03" and case["suite"] == "quality800"]
    first["observation"] = second["observation"]
    _json(rerun / "run.json", session)
    with pytest.raises(ValueError, match="uniquely match its complete declared case identity"):
        compose_runs.prepare_composed_run(base, rerun, output)
    assert not output.exists()
