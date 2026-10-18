"""Render the maintained comparison with detailed evidence collapsed for reading.

Uses the frozen comparison/render implementation; changes Markdown presentation
only. Model settings, captured outputs, gold, readers and metric records stay
unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark import moparse_benchmark as bench

OPEN = '<details>\n<summary>展开逐项质量、时间资源分组与可追溯证据</summary>\n\n'
CLOSE = '\n</details>\n'


def collapse_details(markdown: str) -> str:
    marker = '\n## 质量\n'
    if OPEN in markdown:
        return markdown
    if markdown.count(marker) != 1:
        raise ValueError('Expected one generated quality section; cannot locate detailed evidence')
    lead, details = markdown.split(marker, 1)
    return lead + '\n' + OPEN + '## 质量\n' + details.rstrip() + '\n' + CLOSE


def label_historical_concurrency(chart: Path) -> None:
    """Clarify a historical component chart without changing any measurements."""
    if not chart.is_file():
        return
    source = chart.with_suffix(".sources.json")
    metadata = bench.read(source)
    original = chart.read_text()
    if metadata["SVG_sha256"] != bench.digest(chart):
        raise ValueError("Concurrency chart source identity mismatch")
    replacements = {
        'font-family="sans-serif"': 'font-family="Noto Sans CJK SC,Noto Sans CJK,sans-serif"',
        "Advanced＋TXT：并发、时间与整卡能耗": "历史组件实验：Advanced＋TXT 并发、时间与整卡能耗",
        "既有 TXT 脚注遗漏尚在。": "该历史输出仍有 TXT 脚注遗漏。",
    }
    rendered = original
    for before, after in replacements.items():
        if rendered.count(before) != 1:
            raise ValueError("Historical chart label changed; review presentation formatter")
        rendered = rendered.replace(before, after)
    chart.write_text(rendered)
    metadata["presentation"] = {
        "formatter_sha256": bench.digest(Path(__file__)),
        "original_generated_SVG_sha256": metadata["SVG_sha256"],
        "change": "Historical component scope labels and CJK font family only; source records and all numeric measurements unchanged",
    }
    metadata["SVG_sha256"] = bench.digest(chart)
    bench.save(source, metadata, overwrite=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=bench.DEFAULT_DATASET)
    parser.add_argument('--evidence', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, default=bench.BENCH / 'report.md')
    args = parser.parse_args()
    paths = args.evidence or sorted((bench.BENCH / 'evidence').glob('*.json'))
    comparison = bench.compare(paths)
    if comparison['rejected']:
        print(json.dumps({'rejected': comparison['rejected']}, ensure_ascii=False))
        return 1
    result = bench.render_report(comparison, args.dataset, args.output)
    label_historical_concurrency(bench.BENCH / "assets/concurrency.svg")
    expanded = args.output.read_text()
    if args.dataset.resolve() == bench.DEFAULT_DATASET.resolve():
        # The main manifest is immutable. Its original held-out39 is now
        # exposed; make current prose explicit without rewriting source bytes.
        expanded = expanded.replace("数据版本：", "主清单数据版本：", 1)
        expanded = expanded.replace(
            "独立封存测试文件：3。",
            "原封存 39 页已暴露；另加 3 份／7 页附录，候选首次测试边界见正文。",
            1,
        )
    folded = collapse_details(expanded)
    # Preserve every byte after the explicit scope-label clarification above.
    # Notes may contain their own explicitly collapsed failure history. Remove
    # only the wrapper added here when proving presentation leaves bytes intact.
    unwrapped = folded.replace(OPEN, '', 1)
    assert unwrapped.endswith(CLOSE)
    assert unwrapped[:-len(CLOSE)].strip() == expanded.strip()
    args.output.write_text(folded)
    print(json.dumps({**result, 'details_collapsed': True,
        'gold_or_scoring_predicates_changed': False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
