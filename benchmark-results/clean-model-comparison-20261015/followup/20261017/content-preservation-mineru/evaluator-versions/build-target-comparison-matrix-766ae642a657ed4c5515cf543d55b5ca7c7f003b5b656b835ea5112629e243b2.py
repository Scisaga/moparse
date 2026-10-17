"""Join already completed independent source evaluations by fixed check name."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite evidence")
    directory = HERE / "model-evaluation"
    runs = {}
    input_files = []
    for key, filename, view in [
        ("Docling_component", "docling-component-source-evaluation.json", None),
        ("MinerU_TF_pure_VL", "transformers-source-evaluation.json", None),
        ("MinerU_vLLM_pure_VL", "vllm-source-evaluation.json", None),
        ("MinerU_standard_TXT_FULL", "official-native-standard-source-evaluation.json", "FULL"),
        ("MinerU_advanced_TXT_FULL", "official-native-advanced-source-evaluation.json", "FULL"),
    ]:
        path = directory / filename
        data = json.loads(path.read_text())
        selected = data["views"][view] if view else data
        indexed = {}
        for page in selected["pages"]:
            for check in page["checks"]:
                identity = (page["source"], page["source_page"], check["check"])
                if identity in indexed:
                    raise ValueError(f"Duplicate check: {identity}")
                indexed[identity] = check["status"]
        runs[key] = indexed
        input_files.append(
            {
                "run": key,
                "path": str(path),
                "SHA256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "selected_view": view,
            }
        )
    keys = set(next(iter(runs.values())))
    if len(keys) != 46 or any(set(run) != keys for run in runs.values()):
        raise ValueError("Completed configurations do not share the same 46 fixed conditions")
    rows = [
        {
            "source": source,
            "source_page": page,
            "check": name,
            "configuration_status": {
                run: checks[(source, page, name)] for run, checks in runs.items()
            },
        }
        for source, page, name in sorted(keys)
    ]
    result = {
        "schema": "mosaicparse-fixed-target-comparison-matrix/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "builder_SHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Same fourteen original source pages, forty-six pre-existing targeted conditions. Counts are not whole-document accuracy; p40 contributes twenty conditions. Source mapping/full HTTP acceptance remains separate.",
        "input_evaluations": input_files,
        "page_count": 14,
        "fixed_conditions": 46,
        "counts": {
            run: {
                status: sum(s == status for s in checks.values())
                for status in ["pass", "fail", "unknown"]
            }
            for run, checks in runs.items()
        },
        "rows": rows,
        "specific_failure_qualification": {
            "MinerU_standard_TXT_FULL/p19_entire_long_risk_cell_text_and_span": "Complete long text and original colspan retained; literal comparison fails because official native normalization changes U+201C/U+201D quotes to ASCII. This is not missing tail text.",
            "MinerU_advanced_TXT_FULL/p87_business_footnote": "Table grid/spans correct, but actual native-filled footnote is truncated at both ends: 债权投资公允价值变动源于应收款.",
            "MinerU_vLLM_pure_VL/p74_negative_business_conclusion": "Business negative sentence body recovered; original leading em dash changed into Chinese 一. No other source characters are normalized to hide this.",
        },
        "additional_denominators": "Four additional errors and extra p62 99-position/9-span acceptance are independently reported; not added to 46. Official DEFAULT Markdown omits Office identity even when FULL/raw preserve it.",
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps({"fixed_conditions": 46, "counts": result["counts"], "output": str(args.output)})
    )


if __name__ == "__main__":
    main()
