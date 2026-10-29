"""Compose whole declared execution groups; never score or inspect corpus bytes.

Only run/score-index, maintenance, software-inspection and human-operation JSON
are read. Observations, native results, media and historical visual evidence
are hard-linked opaquely, never parsed, hashed or accepted by this helper.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

COMPOSITION_VERSION = "whole-pipeline-composition-1"
PIPELINES = tuple(f"P{number:02}" for number in range(1, 9))
REPLACED = frozenset({"P03", "P04"})
PADDLE_AUTHORIZED_CHANGES = {
    "paddle_execution_mode": "persistent-owner-v1",
    "paddle_use_queues": False,
}


def _relative(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("artifact paths must be nonempty POSIX relative paths")
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise ValueError("artifact path escapes its source run")
    return Path(*path.parts)


def _without_symlinks(path: Path, *, allow_missing: bool = False) -> Path:
    """Check the complete path chain without resolving an outside ancestor."""
    absolute = path.absolute()
    if ".." in absolute.parts:
        raise ValueError("source and destination paths must not contain parent traversal")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if allow_missing:
                return absolute
            raise
        if stat.S_ISLNK(mode):
            raise ValueError("source and destination paths must not contain any symlink ancestor")
    return absolute


def _read_metadata(path: Path) -> dict[str, Any]:
    _without_symlinks(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("run metadata must be an object")
    return value


def _write_json(path: Path, value: Any) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _without_symlinks(path.parent)
    # Stage paths can already contain opaque hard links. Exclusive creation
    # never truncates or changes a shared source inode, even on a later error.
    with path.open("x", encoding="utf-8") as handle:
        handle.write(value)


def _copy_metadata(source: Path, destination: Path) -> None:
    # A new inode prevents a later source latest_scores update changing a saved
    # run snapshot, and prevents final scoring from modifying the source run.
    _without_symlinks(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _without_symlinks(destination.parent)
    with destination.open("xb") as handle:
        handle.write(source.read_bytes())


def _link_file(source: Path, destination: Path) -> None:
    _without_symlinks(source)
    if not stat.S_ISREG(source.lstat().st_mode):
        raise ValueError("only regular execution artifacts can be hard-linked")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _without_symlinks(destination.parent)
    # No copy fallback: cross-filesystem composition fails explicitly without
    # opening any candidate or evidence bytes.
    os.link(source, destination, follow_symlinks=False)


def _link_tree(source: Path, destination: Path) -> None:
    _without_symlinks(source)
    if not source.is_dir():
        raise ValueError("execution artifact tree must be a real directory")
    destination.mkdir(parents=True, exist_ok=False)
    _without_symlinks(destination)
    with os.scandir(source) as entries:
        for entry in entries:
            target = destination / entry.name
            if entry.is_dir(follow_symlinks=False):
                _link_tree(Path(entry.path), target)
            else:
                _link_file(Path(entry.path), target)


def _configurations(session: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = session.get("configurations")
    if not isinstance(values, list):
        raise ValueError("source configuration declarations are missing")
    result = {}
    for config in values:
        name = config.get("pipeline")
        if name in result or name not in PIPELINES:
            raise ValueError("source configurations have duplicate or unknown pipeline identities")
        result[name] = config
    return result


def _fixed_paddle_configuration(value: Any, *, replacement: bool) -> Any:
    """Remove only the two authorized options, validating all new occurrences."""
    if isinstance(value, dict):
        fixed = {}
        for key, item in value.items():
            if key in PADDLE_AUTHORIZED_CHANGES:
                required = PADDLE_AUTHORIZED_CHANGES[key]
                if replacement and (type(item) is not type(required) or item != required):
                    raise ValueError(f"replacement option is not the authorized value: {key}")
            else:
                fixed[key] = _fixed_paddle_configuration(item, replacement=replacement)
        return fixed
    if isinstance(value, list):
        return [_fixed_paddle_configuration(item, replacement=replacement) for item in value]
    return value


def _check_paddle_configuration(base: dict[str, Any], replacement: dict[str, Any]) -> None:
    for key, required in PADDLE_AUTHORIZED_CHANGES.items():
        actual = replacement.get(key)
        if type(actual) is not type(required) or actual != required:
            raise ValueError(f"replacement must declare the authorized option: {key}")
    # Canonical JSON preserves scalar type distinctions such as False versus 0;
    # no package, image, decoding, export or other execution field is exempted.
    fixed = [json.dumps(_fixed_paddle_configuration(config, replacement=is_replacement),
                        sort_keys=True, separators=(",", ":"))
             for config, is_replacement in ((base, False), (replacement, True))]
    if fixed[0] != fixed[1]:
        raise ValueError(f"fixed execution declarations differ: {base['pipeline']}")


def _case_key(case: dict[str, Any]) -> tuple[str, str, str, int]:
    sample, suite, phase, repetition = (case.get(key) for key in (
        "sample_id", "suite", "phase", "repetition",
    ))
    if (not isinstance(sample, str) or not sample or "/" in sample or "\\" in sample or sample in {".", ".."}
            or type(repetition) is not int
            or not isinstance(suite, str) or not isinstance(phase, str)):
        raise ValueError("execution case identities are incomplete")
    if (suite, phase, repetition) not in {
        ("preflight8", "warmup", 1), ("quality800", "measured", 1),
        ("perf80", "measured", 1), ("perf80", "measured", 2), ("perf80", "measured", 3),
    }:
        raise ValueError("composition requires the declared Lite warmup/quality/performance phases")
    return sample, suite, phase, repetition


def _plans(session: dict[str, Any], configurations: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {name: [] for name in configurations}
    seen = set()
    observations = set()
    for case in session.get("cases", []):
        name = case.get("pipeline")
        if name not in result:
            raise ValueError("case refers to an undeclared pipeline")
        key = name, _case_key(case)
        if key in seen:
            raise ValueError("duplicate execution case; no favorable run selection is permitted")
        seen.add(key)
        relative = _relative(case.get("observation"))
        sample, suite, phase, repetition = key[1]
        expected = Path("artifacts") / name / f"{phase}-{suite}-r{repetition}" / sample / "observation.json"
        if relative != expected or relative in observations:
            raise ValueError("observation path must uniquely match its complete declared case identity")
        observations.add(relative)
        result[name].append(case)
    return result


def _declared_plan(plans: dict[str, list[dict[str, Any]]]) -> list[tuple[str, str, str, int]]:
    expected = [_case_key(case) for case in plans["P01"]]
    if not expected or not any(key[1] == "quality800" for key in expected):
        raise ValueError("base execution has no declared quality plan")
    if not any(key[1] == "preflight8" for key in expected):
        raise ValueError("base execution has no declared common warmup plan")
    repetitions = {key[3] for key in expected if key[1] == "perf80"}
    if repetitions != {1, 2, 3}:
        raise ValueError("base execution must declare all three performance repetitions")
    perf = [[key[0] for key in expected if key[1] == "perf80" and key[3] == repetition]
            for repetition in (1, 2, 3)]
    if not perf[0] or perf[0] != perf[1] or perf[0] != perf[2]:
        raise ValueError("performance repetitions have different declared members or order")
    return expected


def _transport_adjudications(record: dict[str, Any], prefix: Path) -> dict[str, Any]:
    if record.get("evidence_base") != "run_directory":
        raise ValueError("only explicit run-directory evidence can be transported")
    transported = copy.deepcopy(record)
    for decision in transported.get("decisions", []):
        evidence = decision.get("evidence")
        if not isinstance(evidence, list):
            raise ValueError("evidence transport requires an explicit list of relative paths")
        decision["evidence"] = [(prefix / _relative(path)).as_posix() for path in evidence]
    # All operation IDs, actions, reasons, scopes and source judgments stay as
    # supplied. Only evidence paths move; no evidence contents are inspected.
    return transported


def _source_metadata(root: Path, session: dict[str, Any], stage: Path, alias: str) -> dict[str, Any]:
    prefix = Path("artifacts/execution-sources") / alias
    snapshot = stage / prefix
    _copy_metadata(root / "run.json", snapshot / "run.json")
    software = _relative(session["software_snapshot"])
    if software != Path("artifacts/software"):
        raise ValueError("software snapshot must use the dedicated artifacts/software namespace")
    _link_tree(root / software, snapshot / software)
    record: dict[str, Any] = {
        "alias": alias, "run_id": session["run_id"], "directory": str(root),
        "run_snapshot": (prefix / "run.json").as_posix(),
        "software_snapshot": (prefix / software).as_posix(), "software": session["software"],
        "created_at": session.get("created_at"), "finished_at": session.get("finished_at"),
        "maintenance_phase": "unknown", "score_index": None,
    }
    for field, relative in (
        ("maintenance", "maintenance.json"),
        ("software_inspection", "artifacts/software-inspection.json"),
        ("service_restoration_verification", "artifacts/service-restoration-verification.json"),
        ("software_freeze_verification", "artifacts/software-freeze-verification.json"),
    ):
        source = root / relative
        if source.is_file():
            value = _read_metadata(source)
            _copy_metadata(source, snapshot / relative)
            record[field] = {
                "path": (prefix / relative).as_posix(), "record": value,
            }
            if relative == "maintenance.json":
                record["maintenance_phase"] = value.get("phase", "unknown")
    if session.get("latest_scores"):
        index_path = _relative(session["latest_scores"])
        index = _read_metadata(root / index_path)
        _copy_metadata(root / index_path, snapshot / index_path)
        record["score_index"] = {"path": (prefix / index_path).as_posix(),
                                 "score_id": index.get("score_id"),
                                 "software": index.get("software"),
                                 "historical_only_not_reused": True}
        operation = (index.get("reference_adjudications") or {}).get("path")
        if operation:
            op = _relative(operation)
            _copy_metadata(root / op, snapshot / op)
            record["adjudications"] = {"path": (prefix / op).as_posix(),
                                      "source_path": op.as_posix()}
    for relative in ("execution-failure-notes.md", "scoring-implementation-notes.md"):
        if (root / relative).is_file():
            _link_file(root / relative, snapshot / relative)
    if (root / "visual-review").is_dir():
        _link_tree(root / "visual-review", snapshot / "visual-review")
    return record


def _source_lines(session: dict[str, Any]) -> list[str]:
    lines = [
        "## 逐管线执行来源", "",
        "本目录按预声明整组选择组合既有测量，没有重新推理、拼接最优样本或合并旧分数。执行软件按管线分别保留，顶层没有共同执行版本；全部所选样本须经同一次评分调用重评。各源run的原始计时、初始化、预热、资源和观察run_id均不改写。原生产物以硬链接保留并视为只读；评分仅新建独立观察、诊断和成绩版本。", "",
        "| 配置 | 原始执行run_id | 原执行软件身份 | 原执行源码快照 | 原配置快照 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, source in sorted(session.get("execution_sources", {}).items()):
        lines.append(f"| {name} | {source['source_run_id']} | {source['software'].get('software_id') or 'NA'} | [{source['software_snapshot']}]({source['software_snapshot']}) | [{source['configuration_snapshot']}]({source['configuration_snapshot']}) |")
    lines.extend([
        "", "### 源维护窗口", "",
        "组合目录没有新维护窗口；以下是各源运行已保存的恢复记录，不将两个窗口伪称同一次恢复。", "",
        "| 源run_id | 已保存恢复状态 | 维护快照 | 服务恢复核实记录 | 软件冻结核实记录 |",
        "| --- | --- | --- | --- | --- |",
    ])
    for source in session.get("source_runs", []):
        paths = [(source.get(field) or {}).get("path") for field in (
            "maintenance", "service_restoration_verification", "software_freeze_verification",
        )]
        links = [f"[{path}]({path})" if path else "NA" for path in paths]
        lines.append(f"| {source['run_id']} | {source['maintenance_phase']} | {' | '.join(links)} |")
    lines.extend([
        "", "旧P03/P04尝试及其失败记录保留于execution-sources/base命名空间；本次成绩使用artifacts/P03与artifacts/P04中的新整组测量。历史人工个案不构成新P03/P04执行或全量图片保全验收。", "",
    ])
    return lines


def composition_markdown(session: dict[str, Any]) -> str:
    return "\n".join(_source_lines(session))


def prepare_composed_run(base_run: Path, rerun: Path, destination: Path) -> Path:
    """Stage metadata and opaque hard links, then publish a fresh run directory."""
    roots = {"base": _without_symlinks(base_run), "rerun": _without_symlinks(rerun)}
    destination = _without_symlinks(destination, allow_missing=True)
    if destination.exists():
        raise FileExistsError("composition destination already exists")
    if (any(left.is_relative_to(right) for left, right in (
            (roots["base"], roots["rerun"]), (roots["rerun"], roots["base"])))
            or any(destination.is_relative_to(root) or root.is_relative_to(destination) for root in roots.values())):
        raise ValueError("composition needs distinct source runs and a separate destination")
    sessions = {alias: _read_metadata(root / "run.json") for alias, root in roots.items()}
    if sessions["base"]["run_id"] == sessions["rerun"]["run_id"]:
        raise ValueError("source run identities must be distinct")
    for session in sessions.values():
        if session.get("state") != "completed" or session.get("formal") is not True or session.get("suite") != "lite":
            raise ValueError("only finished formal Lite execution records can be composed")
        if not session.get("software", {}).get("software_id"):
            raise ValueError("each source execution needs its own saved software identity")
        if not session.get("reference_freeze"):
            raise ValueError("source execution has no saved reference-freeze declaration")
    for key in ("dataset", "dataset_name", "reference_freeze"):
        if sessions["base"].get(key) != sessions["rerun"].get(key):
            raise ValueError(f"source run declarations differ: {key}")
    configurations = {alias: _configurations(session) for alias, session in sessions.items()}
    if set(configurations["base"]) != set(PIPELINES) or set(configurations["rerun"]) != REPLACED:
        raise ValueError("expected all eight base configurations and only P03/P04 replacement configurations")
    for name in REPLACED:
        _check_paddle_configuration(configurations["base"][name], configurations["rerun"][name])
    plans = {alias: _plans(sessions[alias], configurations[alias]) for alias in roots}
    expected = _declared_plan(plans["base"])
    for alias, values in plans.items():
        for name, cases in values.items():
            if [_case_key(case) for case in cases] != expected:
                raise ValueError(f"declared execution schedule differs for {alias}/{name}")
            for case in cases:
                observation = _without_symlinks(roots[alias] / _relative(case["observation"]))
                if not observation.is_file():
                    raise FileNotFoundError("declared execution observation is absent; no placeholder is fabricated")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        sources = {alias: _source_metadata(roots[alias], sessions[alias], stage, alias) for alias in roots}
        selected = {name: "rerun" if name in REPLACED else "base" for name in PIPELINES}
        cases, selected_configurations, execution_sources = [], [], {}
        for name, alias in selected.items():
            _link_tree(roots[alias] / "artifacts" / name, stage / "artifacts" / name)
            source = sources[alias]
            execution_sources[name] = {
                "source_run_id": source["run_id"], "source_run_directory": source["directory"],
                "source_run_snapshot": source["run_snapshot"], "software": copy.deepcopy(source["software"]),
                "software_snapshot": source["software_snapshot"],
                "configuration_snapshot": f"artifacts/{name}/execution-config.json",
                "created_at": source["created_at"], "finished_at": source["finished_at"],
                "maintenance_snapshot": (source.get("maintenance") or {}).get("path"),
            }
            selected_configurations.append(copy.deepcopy(configurations[alias][name]))
            cases.extend({**copy.deepcopy(case), "source_run_id": source["run_id"],
                          "source_observation": case["observation"],
                          "execution_software_id": source["software"]["software_id"]}
                         for case in plans[alias][name])
        # Only the superseded P03/P04 trees are duplicated in the historical
        # namespace. Other original review links resolve through internal
        # aliases to the unchanged six selected base groups.
        for alias in sources:
            prefix = stage / "artifacts/execution-sources" / alias / "artifacts"
            for name in configurations[alias]:
                target = prefix / name
                if alias == "base" and name in REPLACED:
                    _link_tree(roots[alias] / "artifacts" / name, target)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(os.path.relpath(stage / "artifacts" / name, target.parent), target_is_directory=True)
        inspection: dict[str, Any] = {"scope": "composed_saved_immutable_image_metadata_no_new_inspection",
                                      "inspected_at": None, "pipelines": {}, "source_records": []}
        for name, alias in selected.items():
            source_record = sources[alias].get("software_inspection")
            if source_record:
                item = (source_record["record"].get("pipelines") or {}).get(name)
                if item is not None:
                    inspection["pipelines"][name] = {**copy.deepcopy(item),
                        "source_run_id": sources[alias]["run_id"], "source_inspection": source_record["path"]}
        inspection["source_records"] = [{"source_run_id": source["run_id"],
            "path": source["software_inspection"]["path"],
            "inspected_at": source["software_inspection"]["record"].get("inspected_at")}
            for source in sources.values() if source.get("software_inspection")]
        _write_json(stage / "artifacts/software-inspection.json", inspection)
        _write_json(stage / "maintenance.json", {"phase": "not_a_new_maintenance_window",
            "scope": "source_windows_are_reported_individually", "windows": [
                {"source_run_id": source["run_id"], "phase": source["maintenance_phase"],
                 "snapshot": (source.get("maintenance") or {}).get("path")}
                for source in sources.values()]})
        operation = sources["base"].get("adjudications")
        transported_path = None
        if operation:
            original = _read_metadata(roots["base"] / operation["source_path"])
            transported = _transport_adjudications(original, Path("artifacts/execution-sources/base"))
            transported_path = "reference-adjudications.json"
            _write_json(stage / transported_path, transported)
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        session = {
            "run_id": destination.name, "created_at": now, "finished_at": None,
            "dataset": sessions["base"]["dataset"], "dataset_name": sessions["base"]["dataset_name"],
            "reference_freeze": copy.deepcopy(sessions["base"]["reference_freeze"]),
            "suite": "lite", "formal": True, "state": "composed_existing_measurements_for_uniform_rescoring",
            "software": {"kind": "mixed_execution_sources", "software_id": None,
                         "identity_scope": "see_execution_sources_for_each_pipeline"},
            "configurations": selected_configurations, "cases": cases,
            "errors": [{**copy.deepcopy(error), "source_run_id": sessions[alias]["run_id"]}
                       for alias in roots for error in sessions[alias].get("errors", [])
                       if error.get("pipeline") is None or error.get("pipeline") in {
                           name for name, chosen in selected.items() if chosen == alias}],
            "execution_sources": execution_sources, "source_runs": list(sources.values()),
            "composition": {"version": COMPOSITION_VERSION, "method": "opaque_hard_links_no_content_reads",
                            "selected_sources": selected, "requires_uniform_rescoring": True,
                            "historical_scores_reused": False, "adjudications": {
                                "source": operation["path"] if operation else None,
                                "transported": transported_path, "changed_fields": ["decisions[].evidence"] if operation else []}},
        }
        _write_json(stage / "run.json", session)
        score_command = ["python", "-m", "moparse_eval", "score", "--run", str(destination)]
        if transported_path:
            score_command.extend(["--adjudications", str(destination / transported_path)])
        _write_json(stage / "scoring-plan.json", {
            "requires_one_common_scoring_software_identity": True, "commands": [score_command,
                ["python", "-m", "moparse_eval", "report", "--run", str(destination)]],
            "execution": "not_started_by_preparation_helper",
        })
        _write_text(stage / "execution-composition.md", composition_markdown(session))
        _write_text(stage / "execution-failure-notes.md",
            "# 执行来源与历史失败\n\n本目录没有新推理或失败补值；旧P03/P04记录保留在[原执行失败说明](artifacts/execution-sources/base/execution-failure-notes.md)。P03/P04的最终成绩仅引用重跑整组，具体执行状态以各组原始观察和资源记录为准。\n\n详见[逐组执行来源](execution-composition.md)。\n")
        review = stage / "visual-review"
        review.mkdir()
        _write_text(review / "README.md",
            "# 历史人工个案入口\n\n[原运行人工记录](../artifacts/execution-sources/base/visual-review/README.md)及相对证据保留在原run命名空间。它们是原配置的有限历史个案，尤其旧P03/P04记录不构成新重跑执行、质量或全量图片保全验收。冻结参考和裁定判断未改写，运输仅改变裁定证据相对路径。\n")
        stage.rename(destination)
    except BaseException:
        shutil.rmtree(stage)
        raise
    return destination / "run.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--rerun-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(prepare_composed_run(args.base_run, args.rerun_run, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
