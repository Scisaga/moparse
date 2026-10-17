#!/usr/bin/env python3
"""Render README figures without adding plotting packages to the parser runtime.

Run: uv run --no-project --with matplotlib python scripts/render_readme_charts.py
Requires a Noto Sans CJK font. Historical values come from the README table.
--content-components reads the separately sealed component-comparison.json.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import font_manager  # noqa: E402
from matplotlib import pyplot as plt
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COLORS = ["#64748b", "#2563eb", "#0d9488", "#9473c4"]
LABELS = ["升级前线上", "本次选定配置", "Paddle 1.6 + GLM", "全 GLM（实验 MD）"]


def read_values() -> tuple[list[list[int]], list[float]]:
    text = (ROOT / "README.md").read_text()
    prefixes = [
        "升级前线上：",
        "**本次发布前完整 HTTP 回归：",
        "Paddle 1.6 原生方向",
        "全 GLM＋方向",
    ]
    rows = []
    for prefix in prefixes:
        matches = [line for line in text.splitlines() if line.startswith("| " + prefix)]
        if len(matches) != 1:
            raise ValueError(f"Expected one README comparison row for {prefix}")
        cells = [cell.strip().replace("**", "") for cell in matches[0].split("|")[2:-1]]
        values = [int(cell) for cell in cells]
        if len(values) != 5 or values[0] != values[1]:
            raise ValueError("Chart layout expects five scores with equal core/period scores")
        rows.append(values)
    timing_patterns = [
        r"旧线上 ([\d.]+) 分钟",
        r"本次选定配置 ([\d.]+) 分钟取得 Markdown",
        r"Paddle 组合 ([\d.]+) 分钟",
    ]
    minutes = []
    for pattern in timing_patterns:
        match = re.search(pattern, text)
        if match is None:
            raise ValueError(f"Missing measured README timing: {pattern}")
        minutes.append(float(match[1]))
    return rows, minutes


def style() -> None:
    path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if path.is_file():
        font_manager.fontManager.addfont(path)
        family = font_manager.FontProperties(fname=path).get_name()
    else:
        family = "Noto Sans CJK SC"
        font_manager.findfont(family, fallback_to_default=False)
    plt.rcParams.update(
        {
            "font.family": family,
            "font.size": 11,
            "axes.unicode_minus": False,
            "axes.edgecolor": "#e2e8f0",
            "axes.labelcolor": "#475569",
            "text.color": "#0f172a",
            "xtick.color": "#64748b",
            "ytick.color": "#334155",
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "svg.fonttype": "path",
            "svg.hashsalt": "mosaicparse-readme-model-comparison-20261017",
        }
    )


def save(figure: plt.Figure, name: str, preview: Path | None) -> None:
    output = ROOT / "docs/assets" / f"{name}.svg"
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, metadata={"Date": None, "Creator": "MosaicParse README charts"})
    output.write_text("\n".join(line.rstrip() for line in output.read_text().splitlines()) + "\n")
    if preview:
        preview.mkdir(parents=True, exist_ok=True)
        figure.savefig(preview / f"{name}.png", dpi=140)
    plt.close(figure)
    print(output.relative_to(ROOT))


def clean_axes(axis: plt.Axes) -> None:
    axis.set_axisbelow(True)
    axis.grid(axis="y", color="#e9eef5", linewidth=0.8)
    axis.tick_params(axis="both", length=0, labelsize=13)
    for name, spine in axis.spines.items():
        spine.set_visible(name == "bottom")


def time_bars(axis: plt.Axes, minutes: list[float]) -> None:
    axis.bar(range(3), minutes, width=0.53, color=COLORS[:3], zorder=3)
    axis.set_xticks(
        range(4),
        [
            "升级前线上\nDocling 2.119",
            "本次选定配置\nDocling 2.139",
            "Paddle 1.6\n＋GLM",
            "全 GLM\n（实验 MD）",
        ],
    )
    axis.set_xlim(-0.65, 3.65)
    axis.set_ylim(0, 123)
    axis.set_yticks([0, 30, 60, 90, 120])
    axis.set_ylabel("分钟", fontsize=13)
    clean_axes(axis)
    for index, value in enumerate(minutes):
        axis.text(
            index,
            value + 3,
            f"{value:.2f} 分钟",
            ha="center",
            va="bottom",
            color=COLORS[index],
            fontsize=15,
            weight="bold",
        )
    axis.text(
        3,
        40,
        "未测完整 HTTP",
        ha="center",
        va="center",
        fontsize=13,
        color=COLORS[3],
        bbox={"boxstyle": "round,pad=0.6", "facecolor": "#faf5ff", "edgecolor": "#ddd6fe"},
    )


def comparison(rows: list[list[int]], minutes: list[float], preview: Path | None) -> None:
    figure = plt.figure(figsize=(14.4, 10.8))
    figure.text(0.065, 0.95, "模型组合：质量与整批耗时", fontsize=24, weight="bold")
    figure.text(
        0.065, 0.905, "同一批 10 份原件 · 502 页｜蓝色为本次选定配置", color="#475569", fontsize=13
    )
    figure.legend(
        handles=[
            Patch(facecolor=color, label=label) for color, label in zip(COLORS, LABELS, strict=True)
        ],
        loc="upper left",
        bbox_to_anchor=(0.055, 0.883),
        ncol=4,
        frameon=False,
        fontsize=12.5,
        columnspacing=2.0,
        handlelength=1.1,
    )
    axis = figure.add_axes((0.09, 0.51, 0.86, 0.28))
    axis.set_title(
        "质量｜柱越高越好；柱顶为通过项数", loc="left", fontsize=16, weight="bold", pad=18
    )
    metrics = [
        (0, 209, "核心原值／完整期间\n各 209 项"),
        (2, 402, "原值及唯一行\n402 项"),
        (3, 402, "完整列义 · 公开结构\n402 项"),
        (4, 31, "筹资独立源格\n31 项"),
    ]
    centers = [index * 1.2 for index in range(len(metrics))]
    width = 0.20
    for series, (row, color) in enumerate(zip(rows, COLORS, strict=True)):
        positions = [center + (series - 1.5) * width for center in centers]
        heights = [100 * row[column] / total for column, total, _ in metrics]
        axis.bar(positions, heights, width=width * 0.88, color=color, zorder=3)
        for position, height, (column, _, _) in zip(positions, heights, metrics, strict=True):
            axis.text(
                position,
                height + 2,
                str(row[column]),
                ha="center",
                va="bottom",
                fontsize=12.5,
                color=color,
                weight="bold" if series == 1 else "normal",
            )
    axis.set_xticks(centers, [title for _, _, title in metrics])
    axis.set_ylim(0, 114)
    axis.set_yticks([0, 25, 50, 75, 100])
    axis.yaxis.set_major_formatter(PercentFormatter())
    axis.set_ylabel("标注集通过比例", fontsize=13)
    clean_axes(axis)
    time_axis = figure.add_axes((0.09, 0.155, 0.86, 0.215))
    time_axis.set_title(
        "耗时｜柱越低越快；完整 PDF → 最终 Markdown（不含资产下载）",
        loc="left",
        fontsize=16,
        weight="bold",
        pad=18,
    )
    time_bars(time_axis, minutes)
    figure.text(
        0.065,
        0.065,
        "质量：指定标注集不等于整份文档准确率；列义分数含公开跨度读出收益；全 GLM 取已有实验 MD。",
        fontsize=10.8,
        color="#64748b",
    )
    figure.text(
        0.065,
        0.03,
        "耗时：全 GLM 缺少同口径完整 HTTP 计时；各次预热与共享主机负载不同。原始数据及已知回退见正文。",
        fontsize=10.8,
        color="#64748b",
    )
    save(figure, "model-comparison-quality", preview)


def timing(minutes: list[float], preview: Path | None) -> None:
    figure, axis = plt.subplots(figsize=(13.8, 6.4))
    figure.subplots_adjust(left=0.09, right=0.96, top=0.70, bottom=0.25)
    figure.text(0.04, 0.90, "完整 502 页的实际接口耗时", fontsize=22, weight="bold")
    figure.text(0.04, 0.80, "10 份完整 PDF 串行提交 → 取得最终 Markdown｜越短越快", color="#475569")
    time_bars(axis, minutes)
    figure.text(
        0.04,
        0.10,
        "各次预热和共享主机负载不同：展示已发生的整批成本，不代表稳定加速倍数。",
        color="#64748b",
        fontsize=11,
    )
    save(figure, "model-comparison-time", preview)


def content_components(preview: Path | None) -> None:
    """Keep the immutable 502-page figures separate from the new component trial."""
    source = (
        ROOT
        / "benchmark-results/clean-model-comparison-20261015/followup/20261017"
        / "content-preservation-mineru/component-comparison.json"
    )
    data = json.loads(source.read_text())
    rows = data["configurations"]
    if data["source_pages"] != 14 or not rows:
        raise ValueError("Expected the fixed fourteen-page experiment")
    if any(row["condition_total"] != 46 or row["additional_total"] != 4 for row in rows):
        raise ValueError("Source check denominators changed")
    figure = plt.figure(figsize=(14.4, 12.0))
    figure.text(0.075, 0.954, "原生 PDF 难例：解析路径与处理成本", fontsize=23, weight="bold")
    figure.text(
        0.075,
        0.914,
        "同一组 14 页 · 6 份原件｜指定内容/结构检查与额外字符/状态检查分列",
        color="#475569",
        fontsize=13,
    )
    axis = figure.add_axes((0.285, 0.48, 0.64, 0.36))
    for index, row in enumerate(rows):
        for offset, value, total, color in (
            (-0.17, row["condition_pass"], 46, "#2563eb"),
            (0.17, row["additional_pass"], 4, "#d97706"),
        ):
            y = index + offset
            axis.barh(y, 100 * value / total, height=0.27, color=color, zorder=3)
            axis.text(
                100 * value / total + 1.2,
                y,
                f"{value}/{total}",
                va="center",
                color=color,
                fontsize=12,
                weight="bold",
            )
    axis.set_yticks(range(len(rows)), [row["label"] for row in rows], fontsize=13)
    axis.invert_yaxis()
    axis.set_xlim(0, 115)
    axis.set_xticks([0, 25, 50, 75, 100])
    axis.xaxis.set_major_formatter(PercentFormatter())
    axis.set_axisbelow(True)
    axis.grid(axis="x", color="#e9eef5")
    axis.tick_params(length=0)
    for spine in axis.spines.values():
        spine.set_visible(False)
    figure.legend(
        handles=[
            Patch(facecolor="#2563eb", label="指定内容与结构 · 46 项"),
            Patch(facecolor="#d97706", label="额外源字符与状态 · 4 项"),
        ],
        loc="upper left",
        bbox_to_anchor=(0.276, 0.892),
        ncol=2,
        frameon=False,
        fontsize=12,
    )
    for group, bounds, title in (
        ("pdf", (0.09, 0.16, 0.40, 0.20), "PDF 转换组件 · 秒"),
        ("sdk", (0.59, 0.16, 0.34, 0.20), "图片 SDK 调用组件 · 秒"),
    ):
        values = [row for row in rows if row["time_group"] == group]
        if not values or any(row["component_seconds"] is None for row in values):
            raise ValueError(f"Missing completed timing for {group}")
        timing_axis = figure.add_axes(bounds)
        heights = [row["component_seconds"] for row in values]
        colors = ["#64748b" if row["id"] == "docling" else "#0d9488" for row in values]
        timing_axis.bar(range(len(values)), heights, width=0.55, color=colors, zorder=3)
        timing_axis.set_xticks(range(len(values)), [row["time_label"] for row in values])
        timing_axis.set_ylim(0, max(heights) * 1.25)
        timing_axis.set_title(
            title + "（越低越快）", loc="left", fontsize=14, weight="bold", pad=15
        )
        clean_axes(timing_axis)
        for position, (height, color) in enumerate(zip(heights, colors, strict=True)):
            timing_axis.text(
                position,
                height + max(heights) * 0.025,
                f"{height:.2f}",
                ha="center",
                color=color,
                fontsize=13,
                weight="bold",
            )
    figure.text(
        0.075,
        0.069,
        "时间按入口分组：PDF 组为转换/解析及输出；SDK 组仅 two_step_extract，不含 PDF 渲染和导出。",
        fontsize=10.5,
        color="#475569",
    )
    figure.text(
        0.075,
        0.038,
        "各组均不含模型装载；CPU/GPU 与主机负载不同，不跨组计算加速比。难例通过数不等于整份文档准确率。",
        fontsize=10.5,
        color="#64748b",
    )
    figure.text(
        0.075,
        0.01,
        "原生路径保留的私用字形按源状态核对；普通 Markdown 字体能否正确显示另列，未计为显示修复。",
        fontsize=10.5,
        color="#64748b",
    )
    save(figure, "native-model-component-comparison", preview)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir", type=Path, help="Optional local PNG previews")
    parser.add_argument(
        "--content-components", action="store_true", help="Render the separate fourteen-page trial"
    )
    args = parser.parse_args()
    if args.content_components:
        style()
        content_components(args.preview_dir)
        return
    rows, minutes = read_values()
    style()
    comparison(rows, minutes, args.preview_dir)
    timing(minutes, args.preview_dir)


if __name__ == "__main__":
    main()
