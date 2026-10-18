#!/usr/bin/env python3
"""Render the fixed 502-page HTTP comparison from existing, hashed evidence.

This tool only reads judgments and measured time boundaries. It never scores
Markdown, parses sources, runs a model or guesses missing measurements.
Run after all three evidence records exist:
  uv run --frozen python benchmark/tools/plot_full_http.py --check
  uv run --frozen python benchmark/tools/plot_full_http.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
METRICS = {
    "core209": 209,
    "period209": 209,
    "unique_row402": 402,
    "column_meaning402": 402,
    "funding31": 31,
}
COLORS = ("#64748b", "#a08bbd", "#2563eb")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    result = json.loads(path.read_text())
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object: " + str(path))
    return result


def resolve(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Chart sources must remain inside the repository")
    return path


def artifact(root: Path, path: Path) -> dict:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": digest(path),
        "bytes": path.stat().st_size,
    }


def number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("Missing numeric measurement: " + name)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Invalid numeric measurement: " + name)
    return float(value)


def metric(value: dict, total: int) -> dict:
    if value.get("total") != total or type(value.get("total")) is not int:
        raise ValueError(f"Fixed denominator must be {total}")
    count, unknown = value.get("pass"), value.get("unknown", 0)
    if any(type(item) is not int for item in (count, unknown)):
        raise ValueError("Counts must be integers, not unknown or assumed zero")
    if not 0 <= count <= total or not 0 <= unknown <= total - count:
        raise ValueError("Invalid pass/unknown counts")
    for key in ("gold_fingerprint", "reader_fingerprint"):
        if not re.fullmatch("[a-f0-9]{64}", str(value.get(key, ""))):
            raise ValueError("Missing metric identity: " + key)
    return {**value, "unknown": unknown}


def evidence(root: Path, name: str, method: str | None = None) -> dict:
    value = read(resolve(root, name))
    if value.get("schema") != "moparse-evidence/1":
        raise ValueError("Only formal evidence records may supply chart scores")
    if method is not None and value.get("method_id") != method:
        raise ValueError("Supplementary evidence belongs to a different method")
    if value.get("output_stage") != "public-HTTP-GFM":
        raise ValueError("Component/private output cannot replace public HTTP results")
    return value


def snapshot(root: Path, record: dict, schema: str) -> tuple[dict, dict]:
    matches = {}
    for item in record.get("provenance", []):
        if not item.get("path", "").endswith(".json"):
            continue
        path = resolve(root, item["path"])
        if digest(path) != item.get("sha256"):
            raise ValueError("Evidence artifact SHA256 mismatch: " + item["path"])
        value = read(path)
        if value.get("schema") == schema:
            matches[item["sha256"]] = (value, item)
    if len(matches) != 1:
        raise ValueError("Expected one unambiguous evidence snapshot: " + schema)
    return next(iter(matches.values()))


def source_checks(root: Path, record: dict, pdf_ids: set, office_ids: set) -> tuple[dict, dict]:
    """Split already judged checks; never use the combined 46 as a PDF score."""
    combined = metric(record.get("quality", {}).get("fixed46", {}), 46)
    evaluated, proof = snapshot(root, record, "moparse-content14-evaluation/1")
    checks = evaluated.get("fixed_checks", [])
    if len(checks) != 46 or len({(x["document_id"], x["page"], x["check"]) for x in checks}) != 46:
        raise ValueError("Expected 46 distinct frozen source checks")
    if any(x.get("status") not in {"pass", "fail", "unknown"} for x in checks):
        raise ValueError("Unrecognized source judgment")
    if any(x["document_id"] not in pdf_ids | office_ids for x in checks):
        raise ValueError("Source judgments include a document outside these cohorts")
    if (
        sum(x["status"] == "pass" for x in checks) != combined["pass"]
        or sum(x["status"] == "unknown" for x in checks) != combined["unknown"]
    ):
        raise ValueError("Content evidence count disagrees with its frozen evaluation")

    def subset(ids, total):
        selected = [x for x in checks if x["document_id"] in ids]
        if len(selected) != total:
            raise ValueError("PDF40/Office6 source-check scope has changed")
        return {
            **combined,
            "pass": sum(x["status"] == "pass" for x in selected),
            "total": total,
            "unknown": sum(x["status"] == "unknown" for x in selected),
            "source_evaluation": proof,
            "document_ids": sorted(ids),
        }

    return subset(pdf_ids, 40), subset(office_ids, 6)


def pdf_timing(root: Path, record: dict, documents: dict, pdf_ids: set) -> dict:
    """Sum upload→saved-MD case intervals; assets and Office are never included."""
    if record.get("cohort_id") == "regression-502" and record.get("origin") == "historical_reuse":
        timing, proof = snapshot(root, record, "selected-pipeline-performance-summary/1")
        values = timing.get("timing", {}).get("submit_to_saved_MD_s", {})
        if (
            timing.get("status") != "complete"
            or timing.get("expected_pages") != 502
            or timing.get("finished_capture_pages") != 502
            or timing.get("expected_documents") != len(pdf_ids)
            or values.get("known_case_count") != len(pdf_ids)
            or values.get("unknown_case_count") != 0
        ):
            raise ValueError("Historical timing is not the complete 502-page MD boundary")
        seconds = number(values.get("total_s"), "historical upload→saved MD")
        if not math.isclose(
            seconds,
            number(record["performance"].get("seconds"), "historical evidence seconds"),
            abs_tol=1e-6,
        ):
            raise ValueError("Historical timing proof differs from recorded evidence")
        return {
            "seconds": seconds,
            "minutes": seconds / 60,
            "scope_pages": 502,
            "document_ids": sorted(pdf_ids),
            "excluded_case_ids": [],
            "proof": proof,
            "boundary": "sum of per-document HTTP upload start → saved final Markdown; assets excluded",
        }

    run, proof = snapshot(root, record, "moparse-http-run/1")
    if (
        run.get("status") != "completed"
        or run.get("method_id") != record.get("method_id")
        or run.get("cohort_id") != record.get("cohort_id")
    ):
        raise ValueError("Timing run identity or completion differs from the evidence")
    cases = run.get("cases", [])
    by_id = {x["id"]: x for x in cases}
    if len(by_id) != len(cases) or not pdf_ids <= set(by_id):
        raise ValueError("Timing requires all ten unique full PDF cases")
    policy = run.get("request_policy", {})
    if policy != {"scan_policy": "auto", "unit_range": "omitted", "full_document": True}:
        raise ValueError("Timing requires complete-document scan_policy=auto requests")
    selected = [by_id[name] for name in sorted(pdf_ids)]
    if (
        any(
            x.get("status") != "completed"
            or x.get("page_count") != documents[x["id"]]["page_count"]
            for x in selected
        )
        or sum(x["page_count"] for x in selected) != 502
    ):
        raise ValueError("Timing case coverage is not the original full 502 pages")
    durations = {
        x["id"]: number(x.get("submit_to_saved_MD_seconds"), "case saved-MD time") for x in selected
    }
    seconds = sum(durations.values())
    return {
        "seconds": seconds,
        "minutes": seconds / 60,
        "scope_pages": 502,
        "document_ids": sorted(pdf_ids),
        "excluded_case_ids": sorted(set(by_id) - pdf_ids),
        "per_case_saved_MD_seconds": durations,
        "proof": proof,
        "boundary": "sum of per-document HTTP upload start → saved final Markdown; Office/assets excluded",
    }


def collect(config: dict, root: Path = ROOT) -> dict:
    if config.get("schema") != "moparse-full-http-chart-plan/1":
        raise ValueError("Unsupported chart plan")
    dataset_path = resolve(root, config["dataset"])
    dataset = read(dataset_path)
    cohorts = {x["id"]: x for x in dataset["cohorts"]}
    pdf_ids, office_ids = (
        set(cohorts[name]["document_ids"]) for name in ("regression-502", "regression-office2")
    )
    manifest = dataset_path.parent / dataset["documents"]
    documents = {
        x["id"]: x for line in manifest.read_text().splitlines() if line for x in [json.loads(line)]
    }
    if (
        len(pdf_ids) != 10
        or sum(documents[x]["page_count"] for x in pdf_ids) != 502
        or sum(documents[x]["page_count"] for x in office_ids) != 2
        or pdf_ids & office_ids
    ):
        raise ValueError("Expected distinct original 502-page PDF and two-page Office cohorts")
    rows = []
    plans = config.get("rows", [])
    if [x.get("id") for x in plans] != ["docling", "primary", "header"]:
        raise ValueError("Chart requires Docling, primary and header rows in that order")
    for plan in plans:
        record = evidence(root, plan["evidence"])
        if record.get("cohort_id") not in {"regression-502", "regression-504"}:
            raise ValueError("Quality must come from the complete regression HTTP cohort")
        if record.get("qualification", {}).get("full_HTTP") is not True:
            raise ValueError("A component observation is not a full HTTP run")
        quality = {
            key: metric(record.get("quality", {}).get(key, {}), total)
            for key, total in METRICS.items()
        }
        sources = [artifact(root, resolve(root, plan["evidence"]))]
        if plan.get("content_evidence"):
            content = evidence(root, plan["content_evidence"], record["method_id"])
            quality["content40"] = metric(content["quality"].get("content14_pdf40", {}), 40)
            sources.append(artifact(root, resolve(root, plan["content_evidence"])))
        else:
            quality["content40"], quality["office6"] = source_checks(
                root, record, pdf_ids, office_ids
            )
        office_record = record
        if plan.get("office_evidence"):
            office = evidence(root, plan["office_evidence"], record["method_id"])
            if office.get("cohort_id") != "regression-office2":
                raise ValueError("Office6 must come from the separate Office cohort")
            quality["office6"] = metric(office["quality"].get("office_source6", {}), 6)
            office_record = office
            sources.append(artifact(root, resolve(root, plan["office_evidence"])))
        if "office6" not in quality:
            raise ValueError("Office6 evidence is missing; it cannot be assumed zero")
        office_power = office_record.get("performance", {}).get("power_limit_W")
        quality["office6"].update(
            source_origin=office_record["origin"],
            source_evidence_id=office_record["id"],
            source_power_limit_W=None
            if office_power is None
            else number(office_power, "Office power limit"),
        )
        timing = pdf_timing(root, record, documents, pdf_ids)
        excluded = set(timing["excluded_case_ids"])
        if excluded - office_ids:
            raise ValueError("Unexpected documents in the full HTTP timing proof")
        perf = record.get("performance", {})
        resources = {
            key: None if perf.get(key) is None else number(perf[key], key)
            for key in ("own_GPU_peak_MiB", "shared_GPU_energy_Wh")
        }
        rows.append(
            {
                "id": plan["id"],
                "label": plan["label"],
                "short_label": plan.get("short_label", ("Docling", "TXT", "TXT+验头")[len(rows)]),
                "method_id": record["method_id"],
                "evidence_id": record["id"],
                "origin": record["origin"],
                "power_limit_W": number(perf.get("power_limit_W"), "observed GPU power limit"),
                "quality": quality,
                "timing": timing,
                "resources": resources,
                "resource_scope": "Original evidence window; shared card energy is not exclusive model or PDF502-only energy",
                "provenance": sources,
            }
        )
    for key in (*METRICS, "content40", "office6"):
        identities = {
            (row["quality"][key]["gold_fingerprint"], row["quality"][key]["reader_fingerprint"])
            for row in rows
        }
        if len(identities) != 1:
            raise ValueError("Different gold/readers must be plotted separately: " + key)
    if len({row["method_id"] for row in rows}) != 3:
        raise ValueError("Three distinct observed methods are required")
    return {
        "schema": "moparse-full-http-chart-source/1",
        "rows": rows,
        "dataset": artifact(root, dataset_path),
        "document_manifest": artifact(root, manifest),
        "overlapping_denominators_never_summed": True,
        "no_model_inference": True,
        "quality_scope": "Fixed exposed source judgments, not whole-document accuracy or an aggregate score",
        "timing_scope": "Same 10 complete PDFs/502 pages: upload→saved Markdown, excluding Office and asset download",
        "resource_limit": "Observed power limits and shared loads differ; not a controlled speedup or exclusive-energy experiment",
    }


def render(data: dict) -> str:
    rows, width, height = data["rows"], 1440, 1320
    short_labels = [row.get("short_label", label) for row, label in zip(
        rows, ("Docling", "TXT", "TXT+验头"), strict=True)]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-labelledby="title desc">',
        '<title id="title">完整 HTTP：502 页质量与耗时对比</title>',
        '<desc id="desc">独立固定分母、通过与未知分列；Office单独展示。'
        "耗时为上传至保存Markdown，不含Office及资产下载。历史与本轮功率不同。</desc>",
        '<defs><pattern id="unknown" width="6" height="6" patternUnits="userSpaceOnUse">'
        '<rect width="6" height="6" fill="#fef3c7"/>'
        '<path d="M0 6L6 0" stroke="#d97706" stroke-width="1"/></pattern></defs>',
        f'<rect width="{width}" height="{height}" fill="#fff"/>',
        '<g font-family="Noto Sans CJK SC,Noto Sans CJK,sans-serif" fill="#172033">',
    ]

    def text(x, y, value, size=17, color="#172033", weight="400", anchor="start"):
        parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>'
        )

    text(36, 48, "完整 HTTP：质量与 502 页实际耗时", 30, weight="700")
    text(36, 82, "10 份完整 PDF · 各标注集分别比较 · Office 两页的 6 项另列", 18, "#556177")
    for index, row in enumerate(rows):
        x = 36 + index * 468
        parts.append(
            f'<rect x="{x}" y="110" width="14" height="14" rx="2" fill="{COLORS[index]}"/>'
        )
        historical = "历史" if row["origin"] == "historical_reuse" else "本轮"
        text(x + 24, 123, row["label"], 17)
        text(x + 24, 146, f"{historical} · {row['power_limit_W']:g} W", 14, "#64748b")

    panels = [
        ("content40", "正文及结构 / 40", "仅 PDF 原件的既有检查，不含 Office 6 项"),
        ("core209", "核心原值 / 209", "条长为原值；完整期间分数在方法名下单列"),
        ("unique_row402", "原值及唯一行 / 402 · 严格原字", "标签全半角也会失分；保留冻结判分"),
        ("column_meaning402", "完整列义 / 402 · 严格原字", "核对公开表头、跨度与列义；保留字宽差异失分"),
        ("funding31", "筹资独立源格 / 31", "合并单元格内容及其绑定"),
        ("time", "502 页上传 → Markdown · 分钟", "越短越快；排除 Office、资产下载"),
        ("office6", "Office 衍生两页 / 6 · 单列", "来源分别标注；与 PDF 40 项互不合并"),
    ]
    time_max = max(row["timing"]["minutes"] for row in rows)
    time_max = max(1, math.ceil(time_max / 5) * 5)
    for index, (key, title, subtitle) in enumerate(panels):
        x, y = 36 + (index % 2) * 702, 166 + (index // 2) * 262
        parts.append(
            f'<rect x="{x}" y="{y}" width="666" height="236" rx="10" fill="#fff" stroke="#e2e8f0"/>'
        )
        text(x + 18, y + 30, title, 21, weight="700")
        text(x + 18, y + 56, subtitle, 14, "#64748b")
        plot_x, plot_w = x + 120, 410
        for tick in (0, 0.5, 1):
            tx = plot_x + tick * plot_w
            parts.append(f'<path d="M{tx} {y + 69}V{y + 199}" stroke="#edf1f6"/>')
            text(
                tx,
                y + 222,
                f"{tick * time_max:g}" if key == "time" else f"{tick * 100:g}%",
                13,
                "#64748b",
                anchor="middle",
            )
        for row_index, row in enumerate(rows):
            cy, color = y + 83 + row_index * 43, COLORS[row_index]
            text(x + 106, cy + 10, short_labels[row_index], 16, anchor="end")
            if key == "core209":
                period = row["quality"]["period209"]
                label = f"期间 {period['pass']}/{period['total']}"
                if period["unknown"]:
                    label += f" · ?{period['unknown']}"
                text(x + 106, cy + 26, label, 11, "#64748b", anchor="end")
            if key == "office6":
                score = row["quality"][key]
                origin = "历史" if score["source_origin"] == "historical_reuse" else "本轮"
                power = score["source_power_limit_W"]
                label = f"{origin} · 功率未记录" if power is None else f"{origin} · {power:g} W"
                text(x + 106, cy + 26, label, 11, "#64748b", anchor="end")
            parts.append(
                f'<rect x="{plot_x}" y="{cy - 8}" width="{plot_w}" height="23" fill="#f1f5f9"/>'
            )
            if key == "time":
                fraction, value = (
                    row["timing"]["minutes"] / time_max,
                    f"{row['timing']['minutes']:.2f} 分",
                )
                unknown = 0
            else:
                score = row["quality"][key]
                fraction, value = (
                    score["pass"] / score["total"],
                    f"{score['pass']}/{score['total']}",
                )
                unknown = score["unknown"]
                if unknown:
                    parts.append(
                        f'<rect x="{plot_x + fraction * plot_w:.2f}" y="{cy - 8}" '
                        f'width="{unknown / score["total"] * plot_w:.2f}" height="23" fill="url(#unknown)"/>'
                    )
            parts.append(
                f'<rect x="{plot_x}" y="{cy - 8}" width="{fraction * plot_w:.2f}" height="23" fill="{color}"/>'
            )
            text(x + 648, cy + 10, value, 17, color, "700", "end")
            if unknown:
                text(x + 648, cy + 26, f"未知 {unknown}", 11, "#b45309", anchor="end")

    x, y = 738, 952
    text(x + 18, y + 30, "资源观测 · 原记录窗口", 21, weight="700")
    text(x + 18, y + 58, "缺测保留“未测”；共享整卡能耗不归因给单模型", 14, "#64748b")
    for index, row in enumerate(rows):
        resource = row["resources"]
        peak = (
            "未测"
            if resource["own_GPU_peak_MiB"] is None
            else f"{resource['own_GPU_peak_MiB']:g} MiB"
        )
        energy = (
            "未测"
            if resource["shared_GPU_energy_Wh"] is None
            else f"{resource['shared_GPU_energy_Wh']:.2f} Wh（共享）"
        )
        text(
            x + 18,
            y + 90 + index * 42,
            f"{short_labels[index]}：专属峰值 {peak}；整卡能耗 {energy}",
            16,
            COLORS[index],
        )
    text(
        36,
        1234,
        "质量：各固定分母分别展示；条长为通过比例，斜线为未知；指定标注集不等于整份文档准确率。",
        16,
        "#556177",
    )
    powers = "／".join(
        f"{name} {row['power_limit_W']:g} W"
        for name, row in zip(short_labels, rows, strict=True)
    )
    text(
        36,
        1265,
        f"耗时：{powers}，预热及共享负载不同；展示实际服务成本，不推算受控加速倍数。",
        16,
        "#556177",
    )
    text(
        36,
        1296,
        "资源：按原记录窗口披露，可能含 Office 与其他任务；不是 PDF 502 页的独享显存或能耗。",
        15,
        "#64748b",
    )
    parts.append("</g></svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "benchmark/assets/full-http-comparison.template.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "benchmark/assets/full-http-comparison.svg"
    )
    parser.add_argument(
        "--sources", type=Path, default=ROOT / "benchmark/assets/full-http-comparison.sources.json"
    )
    parser.add_argument(
        "--check", action="store_true", help="Validate all evidence without writing a chart"
    )
    args = parser.parse_args()
    try:
        data = collect(read(args.config))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    if args.check:
        print(json.dumps({"valid": True, "rows": [x["evidence_id"] for x in data["rows"]]}))
        return
    svg = render(data)
    data.update(
        {
            "SVG_sha256": hashlib.sha256(svg.encode()).hexdigest(),
            "chart_tool": artifact(ROOT, Path(__file__).resolve()),
            "chart_plan": artifact(ROOT, args.config.resolve()),
        }
    )
    for path in (args.output, args.sources):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg)
    args.sources.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"chart": str(args.output), "sources": str(args.sources)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
