"""Freeze concise source-comparison conclusions from existing evaluation JSONs.

No parser/model execution or raw-result mutation. Fail names and termination
states are read directly from the completed independent evaluations.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIRECTORY = HERE / "model-evaluation"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite frozen summary")
    inputs, configurations = {}, []

    def read(filename):
        path = DIRECTORY / filename
        inputs[filename] = {"path": str(path), "SHA256": sha(path)}
        return json.loads(path.read_text())

    for name, filename, extra_filename in [
        ("Docling_component", "docling-component-source-evaluation.json", None),
        (
            "MinerU_TF_pure_VL",
            "transformers-source-evaluation.json",
            "transformers-additional-source-observations.json",
        ),
        (
            "MinerU_vLLM_pure_VL",
            "vllm-source-evaluation.json",
            "vllm-additional-source-observations.json",
        ),
        ("MinerU_standard_TXT", "official-native-standard-source-evaluation.json", None),
        ("MinerU_advanced_TXT", "official-native-advanced-source-evaluation.json", None),
    ]:
        data = read(filename)
        selected = data["views"]["FULL"] if "views" in data else data
        additional = (
            read(extra_filename)["checks"]
            if extra_filename
            else selected["additional_four_source_observations"]
        )
        fixed = [(p, c) for p in selected["pages"] for c in p["checks"]]
        failed = [
            {
                "source": p["source"],
                "source_page": p["source_page"],
                "check": c["check"],
                "status": c["status"],
            }
            for p, c in fixed
            if c["status"] != "pass"
        ]
        actual = {
            "configuration": name,
            "original_pages": len(selected["pages"]),
            "fixed_conditions": len(fixed),
            "fixed_counts": dict(Counter(c["status"] for _, c in fixed)),
            "fixed_nonpass_checks": failed,
            "additional_four_counts": dict(Counter(c["status"] for c in additional)),
            "additional_nonpass_checks": [
                {key: c.get(key) for key in ["source", "source_page", "check", "status"]}
                for c in additional
                if c["status"] != "pass"
            ],
            "input_evaluation": inputs[filename],
        }
        if "views" in data:
            actual["other_actual_views"] = {
                key: {
                    "fixed_counts": view["fixed_condition_counts"],
                    "additional_four_counts": view["additional_observation_counts"],
                    "fixed_nonpass_checks": [
                        {
                            "source": p["source"],
                            "source_page": p["source_page"],
                            "check": c["check"],
                            "status": c["status"],
                        }
                        for p in view["pages"]
                        for c in p["checks"]
                        if c["status"] != "pass"
                    ],
                }
                for key, view in data["views"].items()
                if key != "FULL"
            }
            actual["private_use_source_character_observations"] = [
                {
                    "source": p["source"],
                    "source_page": p["source_page"],
                    **p["private_use_character_display"],
                }
                for p in selected["pages"]
                if p["private_use_character_display"]["codepoints"]
            ]
        page_integrities = [
            (p["source"], p["source_page"], p["generation_integrity"]) for p in selected["pages"]
        ]
        if name == "MinerU_vLLM_pure_VL":
            p62 = read("vllm-extra-p62-source-acceptance.json")
            actual["extra_p62"] = {
                "status": p62["table_restoration_status"],
                "positions": 99,
                "spans": 9,
                "actual_shapes": p62["comparison"]["actual_shapes"],
            }
            page_integrities.append(("1225475375", 62, p62["generation_integrity"]))
        elif name in {"MinerU_standard_TXT", "MinerU_advanced_TXT"}:
            tier = "standard" if "standard" in name else "advanced"
            actual["extra_p62"] = {}
            for view in ["FULL", "DEFAULT", "raw_model_JSON"]:
                p62 = read(f"official-native-{tier}-extra-p62-{view}-source-acceptance.json")
                actual["extra_p62"][view] = {
                    "status": p62["table_restoration_status"],
                    "positions": 99,
                    "spans": 9,
                    "actual_shapes": p62["comparison"]["actual_shapes"],
                }
                if view == "FULL":
                    page_integrities.append(("1225475375", 62, p62["generation_integrity"]))
        else:
            actual["extra_p62"] = {
                "status": "not_run_in_this_configuration",
                "not_counted_as_fail": True,
            }
        calls = [
            call for _, _, integrity in page_integrities for call in integrity.get("calls", [])
        ]
        http_calls = [call for call in calls if call.get("transport") == "raw model HTTP"]
        token_calls = [call for call in calls if "last_token_id" in call]
        actual["generation_completion"] = {
            "page_status_counts": dict(Counter(i["status"] for _, _, i in page_integrities)),
            "actual_model_HTTP_calls": len(http_calls),
            "all_actual_model_HTTP_200_normal_stop_no_custom_stop": all(
                c["HTTP_status"] == 200
                and c["server_reported_normal_stop"]
                and not c["custom_stop_sequence_configured"]
                for c in http_calls
            )
            if http_calls
            else None,
            "actual_local_TF_generation_calls": len(token_calls),
            "all_local_TF_calls_explicit_EOS_and_no_limit": all(
                c["ended_with_EOS"] and not c["reached_generation_limit"] for c in token_calls
            )
            if token_calls
            else None,
            "raw_HTTP_does_not_expose_token_EOS": bool(http_calls),
            "aborted_or_unstarted_attempts_excluded": True,
        }
        configurations.append(actual)
    dependency = read("final-evaluation-dependency-integrity.json")
    result = {
        "schema": "mosaicparse-source-comparison-frozen-summary/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "builder_SHA256": sha(Path(__file__)),
        "scope": "Five completed configurations on the same fourteen original pages, fixed46 plus separate extra4. Extra p62 separate99/9. These are targeted source conditions, not whole-document accuracy. Native primary view uses official FULL; DEFAULT/raw separately recorded.",
        "configurations": configurations,
        "standard_failure_classification": {
            "official_native_quote_normalization_only": ["p19_entire_long_risk_cell_text_and_span"],
            "actual_structure_or_source_text_failures": [
                c["check"]
                for c in next(
                    x for x in configurations if x["configuration"] == "MinerU_standard_TXT"
                )["fixed_nonpass_checks"]
                if c["check"] != "p19_entire_long_risk_cell_text_and_span"
            ],
            "note": "Source risk tail/span/amount/footnote reference recovered. Curly double quotes become ASCII in DocVortex official native normalization, so the original fixed literal check stays failed without claiming body omission.",
        },
        "native_PUA_qualification": "Source-state semantics and ordinary Markdown font rendering are different. U+F052 is a PDF-font private character; preservation alone does not guarantee a visible checked glyph. The extra4 score is not a font-rendering guarantee.",
        "recorded_dependency_integrity": {
            "pass": dependency["pass"],
            "checked": dependency["checked_count"],
            "missing": dependency["missing_count"],
            **inputs["final-evaluation-dependency-integrity.json"],
        },
        "public_interface_status": "MinerU trials are per-page components; MosaicParse source/table-source/cross-page assembly remains unimplemented/unknown, not fabricated from input metadata.",
        "inputs": inputs,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "configurations": len(configurations),
                "fixed_conditions_each": [c["fixed_conditions"] for c in configurations],
                "dependency_integrity": result["recorded_dependency_integrity"],
            }
        )
    )


if __name__ == "__main__":
    main()
