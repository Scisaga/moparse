"""Read final measurements and independent source checks; never rerun models."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUTS = []


def read(name):
    path = HERE / name
    raw = path.read_bytes()
    INPUTS.append({"path": name, "SHA256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    return json.loads(raw)


def row(identifier, label, quality, extra, seconds, time_group, time_label, scope):
    assert quality["pass"] + quality["fail"] + quality.get("unknown", 0) == 46
    assert extra["pass"] + extra["fail"] + extra.get("unknown", 0) == 4
    return {
        "id": identifier,
        "label": label,
        "condition_pass": quality["pass"],
        "condition_total": 46,
        "additional_pass": extra["pass"],
        "additional_total": 4,
        "component_seconds": seconds,
        "time_group": time_group,
        "time_label": time_label,
        "time_scope": scope,
    }


def main():
    docling = read("docling-target14-component/run-manifest.json")
    docling_quality = read("model-evaluation/docling-component-source-evaluation.json")
    assert docling["status"] == "complete" and len(docling["pages"]) == 14
    rows = [
        row(
            "docling",
            "Docling V1 · 当前出口",
            docling_quality["fixed_condition_counts"],
            docling_quality["additional_observation_counts"],
            docling["convert_plus_export_seconds_total"],
            "pdf",
            "Docling V1\nCPU 4 核",
            "Original PDF convert plus current export; excludes model initialization and file persistence",
        )
    ]
    for name, label, short in [
        ("transformers", "MinerU · 纯视觉 TF", "Transformers"),
        ("vllm", "MinerU · 纯视觉 vLLM", "vLLM"),
    ]:
        quality = read(f"model-evaluation/{name}-source-evaluation.json")
        additional = read(f"model-evaluation/{name}-additional-source-observations.json")
        measurement = read(
            "mineru-trial/" + ("tf" if name == "transformers" else name) + "-official-summary.json"
        )
        assert len(quality["pages"]) == measurement["source_pages"] == 14
        rows.append(
            row(
                name,
                label,
                quality["counts"],
                additional["counts"],
                measurement["client_seconds_sum"],
                "sdk",
                short + "\nGPU",
                "Official two_step_extract only; PDF render, JSON-to-Markdown and persistence not timed",
            )
        )
    native = read("mineru-trial/official-native-comparison-summary.json")
    for tier, label in [
        ("standard", "MinerU · Standard＋TXT"),
        ("advanced", "MinerU · Advanced＋TXT"),
    ]:
        quality = read(f"model-evaluation/official-native-{tier}-source-evaluation.json")
        view = quality["views"]["FULL"]
        measurement = native["tiers"][tier]["cohorts"]["original_14"]
        assert measurement["completed_cases"] == len(view["pages"]) == 14
        rows.append(
            row(
                tier,
                label,
                view["fixed_condition_counts"],
                view["additional_observation_counts"],
                measurement["PDF_to_FULL_MD_component_seconds_sum"],
                "pdf",
                tier.capitalize() + "＋TXT\nCPU＋GPU",
                "Official PDF parse plus FULL Markdown; CPU initialization, file writes and separate extra p62 excluded",
            )
        )
    value = {
        "schema": "mosaicparse-content-component-comparison/1",
        "source_pages": 14,
        "original_documents": 6,
        "additional_p62_is_separate": True,
        "scope": "Fixed difficult source conditions; not full-document accuracy or MosaicParse model-interface acceptance.",
        "timing": "Two different entry groups retained. Do not calculate a cross-entry speedup. Shared host, differing CPU/GPU resources.",
        "native_PUA_display": "Four additional checks cover source characters/state; native private-use glyph ordinary-font readability is separately unknown.",
        "configurations": rows,
        "inputs": INPUTS,
        "builder_SHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (HERE / "component-comparison.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
