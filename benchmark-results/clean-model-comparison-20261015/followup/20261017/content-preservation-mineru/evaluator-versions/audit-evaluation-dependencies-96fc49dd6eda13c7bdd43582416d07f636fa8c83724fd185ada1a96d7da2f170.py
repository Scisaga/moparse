"""Prove recorded final evaluation script/reference hashes still resolve to bytes.

This writes a dependency index, not a comparison report or release manifest.
Historical JSONs and raw results remain unchanged. Exact script versions are
copied by content hash, so later benchmark-reader edits do not erase evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite evidence index")
    versions = HERE / "evaluator-versions"
    versions.mkdir(exist_ok=True)
    for path in HERE.glob("*.py"):
        destination = versions / f"{path.stem}-{sha(path)}.py"
        if not destination.exists():
            destination.write_bytes(path.read_bytes())
    references = [
        HERE / "source-reference.json",
        HERE / "source-reference-p62.json",
        HERE.parent / "selected-pipeline-deployment/source-independent-recheck-20261017.json",
    ]
    candidates = list(HERE.rglob("*.py")) + references
    index = {}
    for path in candidates:
        if path.is_file():
            index.setdefault(sha(path), []).append(str(path))
    evaluations = list((HERE / "model-evaluation").glob("*.json"))
    evaluations += list(HERE.glob("*acceptance*final.json"))
    evaluations += [
        HERE / name
        for name in ["candidate-all-content-source.json", "verifier-self-test-final.json"]
    ]
    checked, missing = [], []
    for path in sorted(evaluations):
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        requirements = {
            key: value
            for key, value in data.items()
            if isinstance(value, str)
            and len(value) == 64
            and any(
                word in key.lower()
                for word in ["evaluator", "verifier", "shared", "reference", "script"]
            )
        }
        if isinstance(data.get("scripts"), dict):
            requirements.update(data["scripts"])
        for key, recorded in requirements.items():
            item = {
                "evaluation": str(path),
                "evaluation_SHA256": sha(path),
                "recorded_field": key,
                "recorded_SHA256": recorded,
                "matching_existing_paths": index.get(recorded, []),
                "pass": recorded in index,
            }
            checked.append(item)
            if not item["pass"]:
                missing.append(item)
    result = {
        "schema": "mosaicparse-evaluation-byte-dependency-audit/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "audit_script_SHA256": sha(Path(__file__)),
        "scope": "Final evaluation top-level script/reference hash fields and scripts maps; raw model/API result hashes are checked by their respective acceptance readers, not reinterpreted here.",
        "historical_recovery": {
            "25ae40c43f97404aa723b04bb717a04add76db558d4d7b9aa47d492e9dc63d75": "Recovered by reversing the later HTTP-termination and raw-pointer patches; recovered full bytes match the pre-existing TF result SHA exactly.",
            "df43f52cbded488c64cbceb25d235f4f920bd463756bb5ce3816ba6514e185b8": "Recovered by reversing later empty-audit/custom-stop guards; recovered full bytes match pre-existing Docling/early-vLLM result SHA exactly.",
        },
        "limitations": "Old evaluations did not consistently hash every imported dependency. This proves recorded hashes, and does not invent missing historical import hashes or alter original timestamps/results.",
        "pass": not missing,
        "checked_count": len(checked),
        "missing_count": len(missing),
        "checks": checked,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pass": result["pass"],
                "checked": len(checked),
                "missing": len(missing),
                "output": str(args.output),
            }
        )
    )
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
