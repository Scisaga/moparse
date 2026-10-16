#!/usr/bin/env python3
"""Render README figures without adding plotting packages to the parser runtime.

Run: uv run --no-project --with matplotlib python scripts/render_readme_charts.py
Requires a Noto Sans CJK font. Values come from the README's comparison table
and measured end-to-end timing paragraph, rather than a second result dataset.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import font_manager  # noqa: E402
from matplotlib import pyplot as plt
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


def quality(rows: list[list[int]], preview: Path | None) -> None:
    figure, panels = plt.subplots(2, 2, figsize=(13.8, 8.2))
    figure.subplots_adjust(left=0.17, right=0.965, top=0.81, bottom=0.18, wspace=0.7, hspace=0.7)
    figure.text(0.04, 0.945, "固定标注集的质量对比", fontsize=22, weight="bold")
    figure.text(
        0.04,
        0.89,
        "10 份原件 · 502 页｜蓝色为本次选定配置｜条长表示该标注集通过比例",
        color="#475569",
    )
    metrics = [
        (0, 209, "核心原值与完整期间"),
        (2, 402, "原值及唯一行"),
        (3, 402, "完整列义 · 读取公开结构"),
        (4, 31, "筹资合并单元格"),
    ]
    for axis, (column, total, title) in zip(panels.flat, metrics, strict=True):
        values = [row[column] for row in rows]
        axis.barh(range(4), [100 * value / total for value in values], height=0.52, color=COLORS)
        axis.set_yticks(range(4), LABELS)
        axis.invert_yaxis()
        axis.set_xlim(0, 119)
        axis.set_xticks([0, 50, 100])
        axis.xaxis.set_major_formatter(PercentFormatter())
        axis.set_title(title, loc="left", fontsize=13, weight="bold", pad=15)
        axis.set_axisbelow(True)
        axis.grid(axis="x", color="#eef2f6", linewidth=0.8)
        axis.tick_params(axis="both", length=0)
        for spine in axis.spines.values():
            spine.set_visible(False)
        for index, value in enumerate(values):
            axis.text(
                100 * value / total + 2,
                index,
                f"{value}/{total}",
                va="center",
                fontsize=10,
                color=COLORS[index],
                weight="bold" if index == 1 else "normal",
            )
    figure.text(
        0.04,
        0.09,
        "原值及唯一行：选定配置 372/402，旧线上 373/402；存在已确认的逐格回退。",
        color="#9a3412",
        fontsize=11,
    )
    figure.text(
        0.04,
        0.045,
        "指定标注集不等于整份文档准确率。列义分数含公开跨度读出收益；全 GLM 取已有实验 Markdown。",
        color="#64748b",
        fontsize=10,
    )
    save(figure, "model-comparison-quality", preview)


def timing(minutes: list[float], preview: Path | None) -> None:
    figure, axis = plt.subplots(figsize=(13.8, 5.2))
    figure.subplots_adjust(left=0.245, right=0.94, top=0.68, bottom=0.27)
    figure.text(0.04, 0.90, "完整 502 页的实际接口耗时", fontsize=22, weight="bold")
    figure.text(0.04, 0.80, "10 份完整 PDF 串行提交 → 取得最终 Markdown｜越短越快", color="#475569")
    axis.barh(range(3), minutes, height=0.52, color=COLORS[:3])
    axis.set_yticks(range(3), LABELS[:3])
    axis.invert_yaxis()
    axis.set_xlim(0, 120)
    axis.set_xticks([0, 30, 60, 90, 120])
    axis.set_xlabel("分钟", loc="right")
    axis.set_axisbelow(True)
    axis.grid(axis="x", color="#eef2f6", linewidth=0.8)
    axis.tick_params(axis="both", length=0)
    for spine in axis.spines.values():
        spine.set_visible(False)
    for index, value in enumerate(minutes):
        axis.text(
            value + 2,
            index,
            f"{value:.2f} 分钟",
            va="center",
            color=COLORS[index],
            fontsize=13,
            weight="bold" if index == 1 else "normal",
        )
    figure.text(
        0.04,
        0.10,
        "各次预热和共享主机负载不同：展示已发生的整批成本，不代表稳定加速倍数。",
        color="#64748b",
        fontsize=11,
    )
    save(figure, "model-comparison-time", preview)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir", type=Path, help="Optional local PNG previews")
    args = parser.parse_args()
    rows, minutes = read_values()
    style()
    quality(rows, args.preview_dir)
    timing(minutes, args.preview_dir)


if __name__ == "__main__":
    main()
