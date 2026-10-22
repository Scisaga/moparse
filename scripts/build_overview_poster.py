#!/usr/bin/env python3
"""Draw the README architecture, keeping the real workspace screenshot separate.

Component facts come from docs/engineering/architecture.md, the current service
code and docs/pipelines/README.md. Dashed modules describe incomplete target
behavior; this figure is neither a deployment inventory nor a benchmark result.
"""

from __future__ import annotations

import base64
import re
from html import escape
from pathlib import Path

import cairosvg

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
LOGO = ROOT / "assets" / "moparse-logo-256.png"
FONT = "'DejaVu Sans', 'Noto Sans CJK SC', sans-serif"
INK = "#21394a"
MUTED = "#697f8e"
BORDER = "#d5e0e7"
ACCENT = "#597e92"
PARTS: list[str] = []


def text(x: float, y: float, value: str, size: int = 24, *, fill: str = INK, weight: int = 400) -> None:
    # CairoSVG needs explicit font selection for each Latin / CJK run.
    spans = []
    for match in re.finditer(r"[\x00-\x7f]+|[^\x00-\x7f]+", value):
        run = match.group()
        family = "DejaVu Sans" if run.isascii() else "Noto Sans CJK SC"
        spans.append(f'<tspan font-family="{family}, sans-serif">{escape(run)}</tspan>')
    PARTS.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}">{"".join(spans)}</text>')


def rect(x: int, y: int, width: int, height: int, *, fill: str = "#ffffff", stroke: str = BORDER, radius: int = 14, dashed: bool = False) -> None:
    dash = ' stroke-dasharray="8 6"' if dashed else ""
    PARTS.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{dash}/>')


def path(d: str, *, color: str = ACCENT, arrow: bool = False, dashed: bool = False, width: float = 2) -> None:
    marker = ' marker-end="url(#arrow)"' if arrow else ""
    dash = ' stroke-dasharray="7 7"' if dashed else ""
    PARTS.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{marker}{dash}/>')


def node(x: int, y: int, width: int, height: int, title: str, lines: list[str], *, target: bool = False, title_size: int = 26) -> None:
    rect(x, y, width, height, dashed=target, stroke="#93a7b4" if target else BORDER)
    compact = height < 90
    text(x + 22, y + (30 if compact else 39), title, title_size, weight=600)
    for index, line in enumerate(lines):
        text(x + 22, y + (66 if compact else 76) + index * 31, line, 22, fill=MUTED)


def section(x: int, label: str, title: str, subtitle: str) -> None:
    text(x + 28, 714, label, 18, fill=ACCENT, weight=600)
    text(x + 66, 718, title, 30, weight=700)
    text(x + 28, 752, subtitle, 21, fill=MUTED)


def main() -> int:
    PARTS.clear()
    PARTS.extend([
        '<svg xmlns="http://www.w3.org/2000/svg" width="2200" height="1620" viewBox="0 0 2200 1620" role="img" aria-labelledby="title desc">',
        '<title id="title">MO-Parse 文档解析与语义交付架构</title>',
        '<desc id="desc">Web、API 和 MCP 通过原件校验与任务调度进入选定解析配置。原生内容及扫描分支保存各自结果，MO-Parse 按实际原生格式适配，再分类处理数据表、布局正文和图片，组装 Markdown 与媒体并交付下游。SQLite 与文件存储保存任务、原件、来源证据及结果。虚线模块表示目标能力仍需补齐，独立解析研究与服务转换分别验证。</desc>',
        '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M1 1l6 3.5L1 8" fill="none" stroke="#597e92" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>',
        f'<g font-family="{FONT}">',
        '<rect width="2200" height="1620" fill="#ffffff"/>',
    ])
    # Embed the actual robot logo so the SVG remains self-contained offline.
    logo = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    PARTS.append(f'<image x="52" y="60" width="88" height="88" preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{logo}"><title>MO-Parse document-terminal robot logo</title></image>')
    text(154, 124, "MO-Parse", 44, weight=700)
    text(430, 124, "文档解析与语义交付架构", 52, weight=700)
    text(66, 200, "从原文件到正文与图片：解析执行、服务转换、来源证据与交付各有边界", 27, fill=MUTED)
    rect(1628, 74, 508, 55, fill="#f6f9fb", radius=9)
    text(1650, 111, "自托管 · 消费级 GPU + CPU", 25, fill=ACCENT, weight=600)
    path("M1660 162h44")
    text(1718, 171, "已有组件", 22, fill=MUTED)
    path("M1885 162h44", dashed=True)
    text(1943, 171, "目标 / 待补齐", 22, fill=MUTED)
    path("M64 250H2136", color=BORDER, width=1)

    # Access and the control plane are separate from parser execution.
    text(64, 292, "接入与控制", 24, fill=ACCENT, weight=600)
    node(64, 320, 400, 106, "Web 工作台", ["上传 · 原件预览 · 结果与媒体"])
    node(490, 320, 400, 106, "HTTP API", ["同步解析 · 异步 Job · 下载"])
    node(916, 320, 400, 106, "MCP", ["工具调用 · 任务查询 · 结果读取"])
    node(1370, 320, 766, 106, "输入原件", ["PDF · Office · 图片 · 视频     上传文件 / URL"])
    for center in (264, 690, 1116, 1753):
        path(f"M{center} 426v42", arrow=True)
    rect(64, 470, 2072, 130, fill="#f5f8fa", radius=14)
    controls = [
        (92, "原件接收与校验", "SourceService · 上传 / URL / 原件保存"),
        (610, "任务与容量控制", "JobService · 同步槽位 / 进程内队列"),
        (1128, "进度与生命周期", "SSE · 取消 · 超时 · 按状态重试"),
        (1646, "状态与结果访问", "查询 / 下载 / 清理 · StorageService"),
    ]
    for index, (x, title, subtitle) in enumerate(controls):
        text(x, 514, title, 27, weight=600)
        text(x, 558, subtitle, 22, fill=MUTED)
        if index:
            path(f"M{x - 28} 495v80", color=BORDER, width=1)
    path("M394 600v72", arrow=True)
    text(420, 646, "任务执行与取消信号", 21, fill=MUTED)
    # State writes use a dedicated perimeter route to avoid crossing data flow.
    path("M2136 535h28v696H2140", dashed=True, color="#a1b1bc", arrow=True)
    text(1810, 640, "状态与来源读写：虚线连线", 21, fill=MUTED)

    # Main architecture: three grouped components, with native data retained.
    rect(64, 675, 660, 510, fill="#f9fbfc", radius=18)
    rect(780, 675, 852, 510, fill="#f9fbfc", radius=18)
    rect(1690, 675, 446, 510, fill="#f9fbfc", radius=18)
    section(64, "A", "解析执行", "按声明配置运行，保留分支身份与页序")
    section(780, "B", "MO-Parse 内容处理", "按组适配与原件补证分开，逐项记录缺失与失败")
    section(1690, "C", "公开交付与下游", "目标格式约束服务最终结果")
    path("M725 718h53", arrow=True, width=2.4)
    path("M1633 718h55", arrow=True, width=2.4)

    # Existing parser branches are shown explicitly; unimplemented research
    # configurations are kept in the separate research strip below.
    rect(92, 780, 604, 54, fill="#edf3f6", radius=9)
    text(114, 815, "服务端配置与来源观测 → 选定分支", 24, fill=ACCENT, weight=600)
    path("M394 834v16M237 850h314M237 850v21M551 850v21", arrow=True)
    node(92, 875, 290, 164, "原生内容分支", ["PDF：Docling / MinerU", "Office：Docling", "文字、布局及已有表格"])
    node(406, 875, 290, 164, "扫描与混合页", ["GLM-OCR SDK", "旋正 · 布局 · 区域识字", "识别内容与来源页关联"])
    path("M237 1039v17h157M551 1039v17H394v16", arrow=True)
    rect(92, 1076, 604, 70, fill="#edf3f6", radius=9)
    text(114, 1102, "原生产物：文字 · 结构 · 媒体 · 状态", 22, weight=600)
    text(114, 1135, "JSON / Markdown / SDK 结构，按本组实际输出", 19, fill=MUTED)
    text(92, 1171, "CPU 工作进程 + 独立 GPU 推理服务，按配置协作", 20, fill=MUTED)

    # The target transformation is a branching content treatment, rather than
    # a single opaque 'semantic conversion' box.
    node(808, 780, 796, 80, "原生结果适配", ["忠实读取文字、顺序、源格、坐标、媒体及失败"], target=True, title_size=25)
    path("M1206 860v14M932 874h548")
    for center in (932, 1206, 1480):
        path(f"M{center} 874v10", arrow=True)
    node(808, 888, 248, 152, "确认的数据表", ["完整表头与源格", "单位、期间及附注", "跨页范围与语义描述"], target=True, title_size=24)
    node(1082, 888, 248, 152, "布局正文", ["网格用途与阅读顺序", "段落、标题与列表", "清理页码与页眉页脚"], target=True, title_size=24)
    node(1356, 888, 248, 152, "图片与图题", ["原图或区域图保全", "正文引用与资产关联", "可选 OCR 仅识字"], target=True, title_size=24)
    path("M932 1040v14h548v-14M1206 1040v14")
    path("M1206 1054v16", arrow=True)
    node(808, 1074, 796, 80, "共同组装：正文 + 图片引用 + 未解决状态", [], target=True, title_size=25)
    text(830, 1140, "统一阅读顺序、覆盖状态与资产引用，保持响应和持久结果一致", 20, fill=MUTED)

    # The file contract is deliberately a target, with current gaps named.
    rect(1718, 780, 390, 206, dashed=True, stroke="#93a7b4", radius=12)
    text(1740, 819, "MO-Parse 输出包", 26, weight=600)
    path("M1741 842h344", color=BORDER, width=1)
    for y, filename, note in [
        (878, "result.md", "连续正文"),
        (919, "assets/", "关联图片"),
        (960, "manifest.json", "来源映射可选"),
    ]:
        text(1740, y, filename, 25, weight=500)
        text(1956, y, note, 20, fill=MUTED)
    text(1740, 1018, "完整 ZIP 与最终正文仍需补齐", 22, fill=MUTED)
    path("M1913 1031v25", arrow=True)
    rect(1718, 1062, 390, 94, fill="#edf3f6", radius=10)
    text(1740, 1099, "大模型理解与信息抽取", 26, weight=600)
    text(1740, 1133, "实体 / 指标归一 · 索引与问答在下游", 20, fill=MUTED)

    # Persistence and evidence are a shared supporting layer, not intermediate
    # GFM or a purported mandatory shared parser schema.
    path("M394 1186v51", color="#a1b1bc", dashed=True, arrow=True)
    path("M1206 1186v51", color="#a1b1bc", dashed=True, arrow=True)
    path("M1913 1186v51", color="#a1b1bc", dashed=True, arrow=True)
    text(64, 1230, "持久化与来源证据", 24, fill=ACCENT, weight=600)
    rect(64, 1252, 2072, 136, fill="#f5f8fa", radius=14)
    stores = [
        (92, "任务状态", "JobRepository · SQLite · jobs.db", "状态持久化；执行队列仍在进程内"),
        (610, "原件与原生产物", "原文件 · 管线结果 · 原始媒体", "保留可用原生信息，不先强制转 GFM"),
        (1128, "来源与审计", "源格 · 跨度 · 物理页 · 关系证据", "直接原件证据支持表格绑定与核对"),
        (1646, "正文与资产", "result.md · 图片 · 资产索引", "持久正文、引用和下载结果相互核对"),
    ]
    for index, (x, title, line1, line2) in enumerate(stores):
        text(x, 1290, title, 26, weight=600)
        text(x, 1330, line1, 23)
        text(x, 1365, line2, 21, fill=MUTED)
        if index:
            path(f"M{x - 28} 1276v89", color=BORDER, width=1)

    # Independent research is shown as a distinct plane, not a runtime router.
    path("M64 1432H2136", color=BORDER, width=1)
    text(64, 1477, "独立解析研究", 27, weight=600)
    text(320, 1477, "P01–P08：Docling · PaddleOCR-VL · GLM-OCR · MinerU", 27)
    text(320, 1517, "比较声明配置的原始解析质量与直接处理成本；服务适配、转换与打包另行验证和计时。", 24, fill=MUTED)
    text(64, 1580, "组件与目标职责见架构文档；虚线模块尚未完成整体覆盖，不代表部署验收或八组适配已实现。", 22, fill=MUTED)
    text(1900, 1580, "MO-Parse / 2026", 21, fill="#8295a1")
    PARTS.extend(['</g>', '</svg>'])
    svg = "\n".join(PARTS) + "\n"
    target = ASSETS / "mo-parse-overview-poster.svg"
    target.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(target.with_suffix(".png")))
    print(f"Wrote {target.relative_to(ROOT)} and PNG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
