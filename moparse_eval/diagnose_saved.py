"""Run the complete grader on declared saved samples for software diagnosis.

No model, PDF, corpus checker or report publication is involved. The outputs
are engineering evidence, including every candidate trace, not a Lite score.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from .cli import code_identity
from .expected_evaluation import PIPELINES, _grade_tasks, quality_cases
from .expected_readback import read_expected
from .expected_scoring import require_paired_targets
from .packaging import read_json, write_json


def diagnose(
    run: Path,
    output: Path,
    sample_ids: list[str],
    *,
    expected_root: Path,
    service_baseline: Path | None = None,
    service_current: Path | None = None,
    workers: int = 4,
) -> Path:
    run, output = run.resolve(), output.resolve()
    expected_root = expected_root.resolve()
    service_baseline = service_baseline.resolve() if service_baseline else None
    if not sample_ids or len(set(sample_ids)) != len(sample_ids):
        raise ValueError("declare distinct saved samples for diagnosis")
    if not 1 <= workers <= 16:
        raise ValueError("diagnostic CPU workers must be between one and sixteen")
    if output.resolve().is_relative_to(expected_root.resolve()):
        raise ValueError("diagnosis cannot write inside references")
    session = read_json(run / "run.json")
    dataset = Path(session["dataset"])
    if output.resolve().is_relative_to(dataset.resolve()):
        raise ValueError("diagnosis cannot write inside the dataset")
    manifest = read_json(dataset / "manifest.json")
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    native = {(case["pipeline"], case["sample_id"]): (run, case) for case in quality_cases(session)}
    service: dict[tuple[str, str], Any] = {}
    service_groups = []
    for label, service_root in (("baseline", service_baseline), ("current", service_current)):
        if service_root is None:
            continue
        for pipeline in ("P07", "P08"):
            directory = service_root.resolve() / pipeline.lower()
            execution = read_json(directory / "run.json")
            if execution["state"] != "completed":
                raise ValueError("saved final outputs must have completed CPU execution")
            service_groups.append(pipeline + "-" + label)
            service.update(
                {
                    (pipeline + "-" + label, case["sample_id"]): (directory, case)
                    for case in quality_cases(execution)
                }
            )
    identity = code_identity()
    groups = [*PIPELINES, *service_groups]
    tasks = []
    selection = []
    cache = {}
    for sample_id in sample_ids:
        sample = samples[sample_id]
        expected = read_expected(sample, expected_root, cache=cache)
        selection.append(
            {
                "sample_id": sample_id,
                "tags": sample.get("tags", []),
                "document_id": sample["document_id"],
                "expected_scope": expected["scope"],
            }
        )
        for group in groups:
            directory, case = (native if group in PIPELINES else service)[group, sample_id]
            tasks.append(
                {
                    "group": group,
                    "sample_id": sample_id,
                    "expected": expected,
                    "directory": directory,
                    "case": case,
                    "output": output,
                    "software_id": identity["software_id"],
                }
            )
    output.mkdir(parents=True, exist_ok=False)
    write_json(
        output / "selection.json",
        {
            "purpose": "software_diagnosis_not_quality_publication",
            "software_id": identity["software_id"],
            "samples": selection,
            "groups": groups,
        },
    )
    records = []
    compared = {sample_id: [] for sample_id in sample_ids}
    reasons = Counter()
    for record in _grade_tasks(tasks, workers):
        score = read_json(output / record["path"])
        compared[record["sample_id"]].append(score)
        reasons.update(row["reason"] for row in score["outcomes"] if row["outcome"] == "incorrect")
        records.append({key: record[key] for key in ("group", "sample_id", "path")})
        print(f"diagnosed {record['group']}/{record['sample_id']}", flush=True)
    for group in compared.values():
        require_paired_targets(group)
    if code_identity()["software_id"] != identity["software_id"]:
        raise ValueError("software changed during diagnosis; results cannot validate this version")
    path = output / "diagnosis.json"
    write_json(
        path,
        {
            "state": "diagnosis_complete",
            "purpose": "software_diagnosis_not_quality_publication",
            "software_id": identity["software_id"],
            "selection": "selection.json",
            "records": records,
            "incorrect_reason_counts": dict(reasons),
            "reader_review": "pending_text_diagnosis",
            "scope": "execution complete; not a passed semantic validation or a parsing-quality result",
        },
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample", action="append", required=True)
    parser.add_argument(
        "--expected-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "pdf_sample/parsing/expected",
    )
    parser.add_argument("--service-baseline", type=Path)
    parser.add_argument("--service-current", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    print(
        diagnose(
            args.run,
            args.output,
            args.sample,
            expected_root=args.expected_root,
            service_baseline=args.service_baseline,
            service_current=args.service_current,
            workers=args.workers,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
