"""Build the single Lite report from frozen scores and recorded measurements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import math
import re
import statistics
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moparse_eval.expected_evaluation import (  # noqa: E402
    PIPELINES,
    native_preservation,
    paired_changes,
    summarize,
)
from moparse_eval.expected_report import first_failure_stage, load_complete
from moparse_eval.packaging import read_json, write_json  # noqa: E402


def finite_nonnegative(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def memory_bytes(value: Any) -> float | None:
    """Read Docker's used-memory display, never its limit or a declared quota."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(GiB|MiB|KiB|GB|MB|kB|B)\s*", value.split("/", 1)[0])
    if not match:
        return None
    amount = finite_nonnegative(float(match[1]))
    factor = {"GiB": 2**30, "MiB": 2**20, "KiB": 2**10, "GB": 10**9, "MB": 10**6, "kB": 10**3, "B": 1}[match[2]]
    return amount * factor if amount is not None else None


def summarize_resource_samples(record: dict[str, Any]) -> dict[str, Any]:
    """Aggregate complete sampling rounds; independent component peaks never add."""
    host, owned, whole, tts, stamps = [], [], [], [], []
    names_seen: set[str] = set()
    samples = record.get("samples", [])
    for sample in samples:
        names = set(sample.get("expected_containers", []))
        names_seen.update(names)
        values = {}
        for container in sample.get("containers", []):
            name = container.get("owned_name", container.get("Name"))
            if name in names:
                values[name] = memory_bytes(container.get("MemUsage"))
        if names and names <= values.keys() and all(values[name] is not None for name in names):
            host.append(sum(values[name] for name in names))
        gpu = sample.get("owned_gpu", {})
        attributed = gpu.get("memory_mib_by_container", {})
        if (names and gpu.get("status") == "complete_observed_sample" and names <= attributed.keys()
                and all(finite_nonnegative(attributed[name]) is not None for name in names)):
            owned.append(sum(attributed[name] for name in names))
        for output, value in ((whole, sample.get("gpu1", {}).get("used_memory_mib")),
                              (tts, sample.get("tts_gpu", {}).get("used_memory_mib"))):
            number = finite_nonnegative(value)
            if number is not None:
                output.append(number)
        stamp = finite_nonnegative(sample.get("monotonic_seconds"))
        if stamp is not None:
            stamps.append(stamp)
    gaps = [b - a for a, b in zip(stamps[:-1], stamps[1:], strict=True) if b >= a]
    return {"host_peak_bytes": max(host, default=None), "owned_gpu_peak_mib": max(owned, default=None),
            "whole_gpu_peak_mib": max(whole, default=None), "tts_peak_mib": max(tts, default=None),
            "samples": len(samples), "host_complete_samples": len(host), "gpu_complete_samples": len(owned),
            "tts_memory_observed_samples": len(tts), "whole_gpu_observed_samples": len(whole),
            "container_names": sorted(names_seen),
            "sample_span_seconds": stamps[-1] - stamps[0] if len(stamps) > 1 else None,
            "median_gap_seconds": statistics.median(gaps) if gaps else None,
            "maximum_gap_seconds": max(gaps, default=None),
            "scope": "whole recorded protocol including initialization, warmup, quality800 and perf80; sampled peaks"}


def collect_resource_comparison(index: dict[str, Any]) -> dict[str, Any]:
    root = Path(index['baseline'])
    native, final = {}, {}
    for pipeline in PIPELINES:
        native[pipeline] = {}
        for role, relative in [('worker', 'worker-resources.json'), ('inference', 'inference/resources.json')]:
            path = root / 'artifacts' / pipeline / relative
            record = summarize_resource_samples(read_json(path) if path.is_file() else {})
            record['source_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            native[pipeline][role] = {**record, 'source': str(path)}
    for group, entry in index.get('execution_costs', {}).get('final', {}).items():
        run = read_json(Path(entry['run']) / 'run.json')
        cases = [case for case in run['cases'] if case['phase'] == 'measured' and case['suite'] == 'quality800']
        values = [finite_nonnegative(case.get('resources', {}).get('peak_rss_bytes')) for case in cases]
        measured = [value for value in values if value is not None]
        final[group] = {'quality800_peak_process_rss_bytes': max(measured, default=None),
                        'measured_samples': len(cases), 'memory_samples_available': len(measured),
                        'scope': 'quality800 CPU process RSS sampled within each saved case',
                        'environment': run.get('execution_environment')}
    return {'native': native, 'final_cpu': final,
            'policy': 'native whole protocol sampled peaks; inference-owned GPU only; worker GPU attribution missing, not zero; independent peaks never summed; TTS/whole GPU context only'}


def display(value: Any, digits: int = 2) -> str:
    return f'{value:,.{digits}f}' if finite_nonnegative(value) is not None else '缺测'


def percent(value: Any) -> str:
    return f'{value:.2%}' if finite_nonnegative(value) is not None else '不适用'


def numeric_difference(row: dict[str, Any]) -> bool:
    """Select an already graded, located numeric difference for explanation."""
    return (row['kind'] == 'business_field' and row['outcome'] == 'incorrect'
        and isinstance(row.get('actual'), str) and row.get('candidate', {}).get('status') == 'compared'
        and not row.get('value_and_labels_correct')
        and re.sub(r'[\s,.]', '', row['expected']['value']) != re.sub(r'[\s,.]', '', row['actual'])
        and bool(re.fullmatch(r'[\d\s,.+\-−()%‰$€£¥]+', row['expected']['value'] or ''))
        and bool(re.fullmatch(r'[\d\s,.+\-−()%‰$€£¥]+', row['actual'] or '')))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def text_diagnostics(scores: list[dict[str, Any]]) -> dict[str, Any]:
    from moparse_eval.prose_metrics import summarize_text
    return summarize_text([row for score in scores for row in score['outcomes']])


def printed_literals(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return list(dict.fromkeys(text for item in value for text in printed_literals(item)))
    if isinstance(value, dict):
        return printed_literals(value.get('actual', value.get('text', value.get('source_hits', value.get('literal')))))
    return []


def markdown_excerpt(lines: list[str], identifiers: list[str]) -> str | None:
    excerpts = []
    for identity in identifiers:
        match = re.match(r'markdown:L([0-9]+)(?:/gfm/rows/([0-9]+)/cells/[0-9]+)?', identity)
        if not match or not lines:
            continue
        start = int(match[1]) - 1
        before = [line for line in lines[:start] if line.strip()][-2:]
        if match[2] is not None:
            rows = []
            for line in lines[start:]:
                if not line.lstrip().startswith('|'):
                    break
                cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell) for cell in cells):
                    rows.append(line)
            row = int(match[2])
            if row >= len(rows):
                continue
            excerpts.append('\n'.join([*before, *rows[:1], '…', rows[row]]))
        else:
            excerpts.append('\n'.join([*before, *[line for line in lines[start:] if line.strip()][:6]]))
    return '\n\n'.join(dict.fromkeys(excerpts))[:1600] or None


def native_row_excerpt(observation: dict[str, Any], identifiers: list[str]) -> str | None:
    from moparse_eval.representations import visible_text

    def selected_source(identity):
        return isinstance(identity, str) and any(identifier == identity or identifier.startswith(identity + ':')
            or identifier.startswith(identity + '/') for identifier in identifiers)

    rows = []
    for page in observation.get('pages', []):
        for block in page.get('blocks', []):
            cells = block.get('cells', [])
            selected = [cell for cell in cells if selected_source(cell.get('id'))]
            for cell in selected:
                row = cell.get('row')
                if type(row) is not int:
                    continue
                source = sorted((part for part in cells if part.get('row') == row and type(part.get('col')) is int),
                                key=lambda part: part['col'])
                rows.append(' | '.join(str(part.get('text', '')) for part in source))
            if not cells and selected_source(block.get('id')):
                rows.append(visible_text(str(block.get('text', '')), block.get('text_format', 'plain')))
    return '\n'.join(dict.fromkeys(rows))[:1600] or None


def collect_conversion_examples(groups, pairs):
    """Take before/after excerpts from the actual public Markdown files."""
    examples = []
    for pipeline, delta in pairs.items():
        selected = None
        for gain in delta['gains']:
            if gain['kind'] != 'business_field':
                continue
            snippets = {}
            for version, key in [('baseline', 'before'), ('current', 'after')]:
                score = next(s for s in groups[pipeline + '-' + version]
                             if s['sample_id'] == gain['sample_id'])
                source = Path(score['candidate_source'])
                field = gain[key]['candidate']
                identifiers = ([field['native_id']] if field.get('native_id') else
                    [identity for hit in field['localization']['candidates']
                     for identity in hit['native_ids'] or [hit.get('body', '')]])
                if not source.is_file():
                    raise ValueError('conversion evidence requires the actual saved final.md')
                snippets[key] = {'source': str(source), 'outcome': gain[key]['outcome'],
                    'excerpt_policy': 'actual saved lines; standalone ellipsis marks omitted table rows',
                    'markdown': markdown_excerpt(source.read_text(encoding='utf-8').splitlines(), identifiers)}
            if (snippets['before']['markdown'] and snippets['after']['markdown']
                    and snippets['before']['markdown'] != snippets['after']['markdown']):
                selected = {'pipeline': pipeline, 'sample_id': gain['sample_id'], 'target_id': gain['target'],
                    'query': gain['after']['candidate']['localization']['query'],
                    'expected_value': gain['expected']['value'], **snippets}
                break
        if any(gain['kind'] == 'business_field' for gain in delta['gains']) and selected is None:
            raise ValueError('reported conversion gains need different actual Markdown excerpts')
        if selected:
            examples.append(selected)
    return examples


def write_readback_examples(path: Path, examples: list[dict[str, Any]], conversions=None) -> None:
    """Show short program-derived comparisons; never inspect an original page."""
    def escape(value):
        return html.escape(str(value))

    labels = {'business_scope': '业务范围', 'parent_scopes': '父分组', 'period': '期间',
              'unit': '单位', 'currency': '币种', 'entity': '主体', 'record_type': '记录类型',
              'note_markers': '附注编号', 'note_texts': '附注'}
    cards = []
    for example in conversions or []:
        query = example['query']
        label = ' / '.join([*query['row_header_path'], *query['column_header_path']])
        cards.append(f'<article data-group="{escape(example["pipeline"] + "-current")}" data-conversion="true">'
            f'<p class="meta">实际正文前后变化 · {escape(example["pipeline"])}</p><h2>{escape(label)}</h2>'
            f'<p>expected值：{escape(example["expected_value"])}。片段读取两份实际final.md；独立的省略号表示省略表行。数字、列名、单位和多余父路径均可对照。</p>'
            '<table><thead><tr><th>唯一修改前正文 · 此项错误</th><th>当前正文 · 此项正确</th></tr></thead>'
            f'<tbody><tr><td><pre>{escape(example["before"]["markdown"])}</pre></td>'
            f'<td><pre>{escape(example["after"]["markdown"])}</pre></td></tr></tbody></table>'
            f'<p class="meta">{escape(example["sample_id"])} · {escape(example["target_id"])}</p></article>')
    for example in sorted(examples, key=lambda item: (
            item['group'], item['outcome'] == 'correct', item['actual'] is None, item['purpose'])):
        query = example['query']
        identity = '；'.join(f"{labels.get(key, key)}：{' / '.join(printed_literals(value)) or value}"
                            for key, value in query['identity'].items())
        name = ' / '.join([*query['row_header_path'], *query['column_header_path']])
        actual = (example['actual'] or '（空白）') if example['actual'] is not None else '未确定可比较的业务位置，见下方原因'
        correct = example['outcome'] == 'correct'
        explanation = ('值与全部必要关系均符合 expected。' if correct else
                       '值或必要关系未满足 expected；展开查看实际来源与排除理由。')
        if example.get('collection_comparison'):
            explanation += (' 此身份在 expected 中有多条记录；程序先定位完整记录集合，再联合比较每条记录的全部字段。'
                            '交换整条记录不改变事实，跨记录交换金额和比例、漏记录或增加冲突记录均不能通过这项集合比较。')
        decisions = []
        for hit in example['candidate_decisions']:
            checks = '；'.join(f"{labels.get(key, key)}：{ {'correct': '符合', 'incorrect': '不符或缺失'}.get(status, status)}"
                              + ('（候选文字：' + '；'.join(hit['identity_printed'].get(key, [])) + '）'
                                 if hit['identity_printed'].get(key) else '')
                              for key, status in hit['identity_status'].items())
            decisions.append('<tr><td>' + escape('，'.join(hit['native_ids'])) + '</td><td>'
                + ('允许比较' if hit['decision'] == 'accepted' else '排除') + '</td><td>'
                + escape(checks or hit.get('reasons') or '无完整关系') + '</td></tr>')
            if hit.get('printed_source'):
                decisions.append('<tr><td colspan="3"><b>该位置的实际保存文字：</b><pre>'
                    + escape(hit['printed_source']) + '</pre></td></tr>')
        cards.append(f'<article data-group="{escape(example["group"])}"><p class="meta">{escape(example["purpose"])} · {escape(example["group"])}</p>'
            f'<h2>{escape(name)}</h2><p>{escape(identity)}</p>'
            '<table><thead><tr><th>expected 要求</th><th>当前候选</th><th>程序判定</th></tr></thead>'
            f'<tbody><tr><td>{escape(example["expected_value"] or "（应为空白）")}</td><td>{escape(actual)}</td>'
            f'<td class="{"correct" if correct else "incorrect"}">{"正确" if correct else "错误或缺失"}</td></tr></tbody></table>'
            f'<p class="meta">样本：{escape(example["sample_id"])}<br>目标：{escape(example["target_id"])}<br>'
            f'{explanation}<br>程序原因码：{escape(example["reason"])}</p><details><summary>查看全部候选及排除理由</summary>'
            '<table><thead><tr><th>候选来源</th><th>处理</th><th>身份检查</th></tr></thead><tbody>'
            + (''.join(decisions) or '<tr><td colspan="3">没有召回到匹配标签</td></tr>')
            + '</tbody></table></details></article>')
    path.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>MO-Parse 逐项比较示例</title>'
        '<style>@font-face{font-family:"Noto Sans CJK SC";src:url("fonts/NotoSansCJKSC-Regular.otf")} '
        '@font-face{font-family:"Noto Sans CJK SC";font-weight:700;src:url("fonts/NotoSansCJKSC-Bold.otf")} '
        'body{font:16px/1.7 "DejaVu Sans","Noto Sans CJK SC",sans-serif;color:#202833;background:#f1f4f8;'
        'max-width:1100px;margin:auto;padding:24px}article,header{background:white;padding:24px;margin-bottom:20px;'
        'border:1px solid #d9e0e8;border-radius:10px}h1{font-size:26px}h2{font-size:20px}table{border-collapse:collapse;'
        'width:100%;table-layout:fixed}th,td{padding:10px;border:1px solid #d9e0e8;text-align:left;overflow-wrap:anywhere}'
        'th{background:#edf2f8}.meta{font-size:13px;color:#526174}.correct{color:#15703b}.incorrect{color:#a33127}'
        'summary{cursor:pointer}details table{margin-top:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        'a{color:#205c9c}select{font:inherit;padding:6px}</style>'
        '<header><h1>直接看要求与输出</h1><p>每张卡片直接列 expected 的要求、当前候选和共同程序的判定。'
        '线上与线下、年份、父分组等身份不吻合的候选先排除，不把它的数字拿来声称目标数字识别错了。</p>'
        '<p>默认显示P08，先列仍有差异的例子，再列已修复的定位与读取例子。展开卡片可看保存输出的原文。</p>'
        '<p>选择P07-current或P08-current，可直接看真实Markdown的修改前后片段。</p>'
        '<p>这些案例来自冻结后的程序结果，覆盖原生、唯一基线和当前正文。人工文字诊断不改分。'
        '未查看 PDF 或图片，也不认证参考材料。</p><p><label>查看组别：<select id="group"><option value="all">全部组别</option>'
        + ''.join(f'<option value="{escape(group)}"{" selected" if group == "P08" else ""}>{escape(group)}</option>'
                  for group in dict.fromkeys(example['group'] for example in examples))
        + '</select></label></p><a href="report.md">返回唯一正式报告</a></header>'
        + ''.join(cards) + '<script>const select=document.getElementById("group");function filter(){'
        'document.querySelectorAll("article").forEach(card=>card.hidden=select.value!=="all"&&card.dataset.group!==select.value);'
        '}select.addEventListener("change",filter);filter();</script></html>', encoding='utf-8')


def draw_figures(index: dict[str, Any], output: Path) -> dict[str, Any]:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    from moparse_eval.report_figures import PIPELINE_COLORS, _register_cjk_fonts
    _register_cjk_fonts(output)
    plt.rcParams.update({'font.family': ['DejaVu Sans', 'Noto Sans CJK SC', 'sans-serif'],
                         'font.sans-serif': ['DejaVu Sans', 'Noto Sans CJK SC', 'sans-serif'],
                         'mathtext.fontset': 'dejavusans', 'text.usetex': False,
                         'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
                         'svg.hashsalt': index['software']['software_id']})
    folder = output / 'figures'
    folder.mkdir(exist_ok=True)
    labels = [p for p in PIPELINES if p in index['summary']]
    metrics = [('business', 'Complete business information / all targets', [
        (lambda m: m['complete_information_correct'] / m['targets'] if m['targets'] else 0)(index['summary'][p]['business_metrics']) for p in labels]),
        ('characters', 'Preserved expected characters / all target characters', [index['summary'][p]['text_metrics']['character_preservation'] or 0 for p in labels])]
    for name, title, values in metrics:
        fig, ax = plt.subplots(figsize=(9, 4), layout='constrained')
        ax.barh(labels, values, color=[PIPELINE_COLORS[p] for p in labels])
        ax.invert_yaxis()
        ax.set(xlim=(0, 1.12), title=title)
        for number, value in enumerate(values):
            ax.text(value + .01, number, f'{value:.2%}', va='center')
        for suffix in ('png', 'svg', 'pdf'):
            metadata = {'CreationDate': None, 'ModDate': None} if suffix == 'pdf' else {'Date': None} if suffix == 'svg' else None
            fig.savefig(folder / f'{name}.{suffix}', dpi=160, metadata=metadata)
        plt.close(fig)
    verification = {}
    for path in [folder / f'{name}.svg' for name, _, _ in metrics]:
        source = path.read_text()
        if 'sans-serif' not in source or re.search(r'Times|DejaVu Serif|Computer Modern', source):
            raise ValueError('chart SVG font policy failed')
        verification[path.name] = 'sans-serif stack declared'
    for path in [folder / f'{name}.pdf' for name, _, _ in metrics]:
        # Only these newly generated charts are opened, for font metadata.
        # No original PDF or candidate image is opened or rendered here.
        import pymupdf
        with pymupdf.open(path) as document:
            fonts = document.get_page_fonts(0, full=True)
            if not fonts or any(not document.extract_font(font[0])[3]
                                or re.search(r'Times|Serif|CMR', font[3]) for font in fonts):
                raise ValueError('chart PDF font embedding failed')
            verification[path.name] = [{'name': font[3], 'embedded': True} for font in fonts]
    return verification


def render(index_path: Path, output: Path, *, figures: bool = True) -> list[str]:
    index, groups = load_complete(index_path)
    output.mkdir(parents=True, exist_ok=True)
    data = output / 'data'
    data.mkdir(exist_ok=True)
    resources = collect_resource_comparison(index)
    summary = index['summary']
    pairs = {pipeline: paired_changes(groups[pipeline + '-baseline'], groups[pipeline + '-current'])
             for pipeline in ('P07', 'P08') if pipeline + '-current' in groups and pipeline + '-baseline' in groups}
    conversions = collect_conversion_examples(groups, pairs)
    write_json(data / 'results.json', summary)
    write_json(data / 'resources.json', resources)
    execution = {**index.get('execution_costs', {})}
    execution['native'] = {p: {suite: {key: value for key, value in record.items() if key != 'resource_observations'}
        for suite, record in suites.items()} for p, suites in execution.get('native', {}).items()}
    execution['raw_runtime_evidence'] = {'index': str(index_path.resolve()),
        'meaning': 'original observations and detailed inference telemetry remain local; recorded times are copied unchanged'}
    for entry in execution.get('final', {}).values():
        run = read_json(Path(entry['run']) / 'run.json')
        entry['quality800_case_status_counts'] = dict(Counter(case.get('status', 'unknown') for case in run['cases']
            if case['phase'] == 'measured' and case['suite'] == 'quality800'))
    execution['status_policy'] = 'native summary status uses original execution; final summary status is Markdown readability; original CPU partial/warning/failure counts are retained separately'
    write_json(data / 'execution.json', execution)
    public_coverage = [{**row, 'content_coverage': {key: value for key, value in row['content_coverage'].items() if key != 'ranges'},
        'range_evidence': [{key: value for key, value in evidence.items() if key != 'text'} |
            {'ranges': [{key: value for key, value in part.items() if key != 'literal'} for part in evidence['ranges']]}
            for evidence in row['content_coverage']['ranges']]} for row in index['coverage']]
    write_json(data / 'coverage.json', public_coverage)
    write_json(data / 'provenance.json', {'index': str(index_path.resolve()), 'software': index['software'],
        'protocol': index['protocol'], 'development_exposure': index.get('development_exposure'),
        'report_generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    write_json(data / 'scoring-validation.json', index.get('validation', {}))
    retrieval = {}
    examples = []
    selected_examples = index.get('validation', {}).get('real_readback', {}).get('examples', [])
    for group, scores in groups.items():
        fields = [row for score in scores for row in score['outcomes'] if row['kind'] == 'business_field']
        hits = [hit for row in fields for hit in row['candidate']['localization']['candidates']]
        retrieval[group] = {'targets': len(fields),
            'targets_with_recalled_candidates': sum(bool(row['candidate']['localization']['candidates']) for row in fields),
            'targets_with_identity_valid_candidates': sum(any(hit['decision'] == 'accepted'
                for hit in row['candidate']['localization']['candidates']) for row in fields),
            'candidate_decisions': dict(Counter(hit['decision'] for hit in hits)),
            'rejected_identity_requirements': dict(Counter(key for hit in hits if hit['decision'] == 'rejected'
                for key, check in hit.get('identity', {}).items() if check.get('status') != 'correct'))}
        group_examples = list(selected_examples)
        if group in PIPELINES:
            for category, purpose in [('value', '仍存在的原生值字面差异'),
                                       ('binding', '仍存在的原生关系或定位缺失')]:
                found = next(((score, row) for score in scores for row in score['outcomes']
                    if row['kind'] == 'business_field' and row['outcome'] == 'incorrect'
                    and (numeric_difference(row)
                         if category == 'value' else row.get('actual') is None)), None)
                if found is None and category == 'value':
                    found = next(((score,row) for score in scores for row in score['outcomes']
                        if row['kind']=='business_field' and row['outcome']=='incorrect'
                        and row.get('actual') is not None and not row.get('value_and_labels_correct')),None)
                if found:
                    score, row = found
                    group_examples.append({'sample_id': score['sample_id'], 'target_id': row['id'], 'purpose': purpose})
        for selected in group_examples:
            score = next((score for score in scores if score['sample_id'] == selected['sample_id']), None)
            row = next((row for row in score['outcomes'] if row['id'] == selected['target_id']), None) if score else None
            if row and row['kind'] == 'business_field':
                trace = row['candidate']['localization']
                source_path = Path(score['candidate_source'])
                lines = (source_path.read_text(encoding='utf-8').splitlines()
                         if group not in PIPELINES and source_path.is_file() else [])
                readback_path = index_path.parent / 'private/observations' / group / 'quality800-r1' / (score['sample_id'] + '.json')
                observation = read_json(readback_path) if group in PIPELINES and readback_path.is_file() else {}
                examples.append({'group': group, **selected, 'outcome': row['outcome'], 'actual': row.get('actual'),
                    'expected_value': row['expected']['value'], 'reason': row['reason'],
                    'query': trace['query'], 'selected_native_id': row['candidate'].get('native_id'),
                    'collection_comparison': trace.get('collection_comparison'),
                    'candidate_decisions': [{'native_ids': hit['native_ids'], 'body': hit.get('body'),
                        'decision': hit['decision'], 'reasons': hit.get('reasons'),
                        'printed_source': (markdown_excerpt(lines, hit['native_ids'] or [hit.get('body', '')]) if lines
                                           else native_row_excerpt(observation, hit['native_ids'])),
                        'identity_printed': {key: printed_literals(check.get('actual'))
                                             for key, check in hit.get('identity', {}).items()},
                        'identity_status': {key: check['status'] for key, check in hit.get('identity', {}).items()}}
                        for hit in trace['candidates']],
                    'details': next(record['path'] for record in index['records']
                                    if record['group'] == group and record['sample_id'] == selected['sample_id'])})
    write_json(data / 'retrieval.json', {'summary': retrieval, 'examples': examples,
        'meaning': 'candidate recall and rejection diagnostics; these counts alone do not establish semantic correctness'})
    write_json(data / 'conversion-examples.json', conversions)
    write_readback_examples(output / 'examples.html', examples, conversions)
    rows = []
    numeric_examples = {}
    for group, scores in groups.items():
        native = {score['sample_id']: {row['id']: row for row in score['outcomes']} for score in groups.get(group.split('-')[0], [])}
        for score in scores:
            for row in score['outcomes']:
                if row['outcome'] == 'correct':
                    continue
                if group in PIPELINES and group not in numeric_examples and numeric_difference(row):
                    numeric_examples[group] = {'sample': score['sample_id'], 'target': row['id'],
                        'row': row.get('row_header_path'), 'column': row['expected'].get('column_header_path'),
                        'expected': row['expected']['value'], 'actual': row['actual']}
                evidence = row.get('candidate') or {}
                rows.append({'group': group, 'sample_id': score['sample_id'], 'target_id': row['id'],
                    'kind': row['kind'], 'reference': row['reference'], 'reason': row['reason'],
                    'candidate_path': evidence.get('native_path'), 'candidate_span': evidence.get('span'),
                    'candidate_qualifier_status': {key: value.get('status') for key, value in evidence.get('information', {}).get('qualifiers', {}).items()},
                    'first_observed_failure': first_failure_stage(group, row, native.get(score['sample_id'], {}).get(row['id'])),
                    'details': next(record['path'] for record in index['records'] if record['group'] == group and record['sample_id'] == score['sample_id'])})
    write_json(data / 'errors.json', rows)
    private = output / 'private'
    private.mkdir(exist_ok=True)
    write_json(private / 'paired.json', pairs)
    write_json(data / 'paired.json', {p: {**{key: value for key, value in delta.items() if key not in {'gains','losses','raw_literal_gains','raw_literal_losses'}},
        'details': 'private/paired.json'} for p, delta in pairs.items()})
    baseline_preservation = {p: native_preservation(groups[p], groups[p + '-baseline'])
        for p in ('P07', 'P08') if p + '-baseline' in groups}
    baseline_changes = {p: paired_changes(groups[p], groups[p + '-baseline']) for p in baseline_preservation}
    write_json(private / 'native-to-baseline.json', baseline_changes)
    write_json(data / 'native-to-baseline.json', {p: {key: value for key, value in delta.items()
        if key not in {'gains','losses','raw_literal_gains','raw_literal_losses'}} |
        {'details': 'private/native-to-baseline.json'} for p, delta in baseline_changes.items()})
    write_json(private / 'baseline-preservation.json', baseline_preservation)
    write_json(data / 'baseline-preservation.json', {p: {key: value for key, value in gate.items() if key != 'losses'} |
        {'details': 'private/baseline-preservation.json'} for p, gate in baseline_preservation.items()})
    native_rows, document_rows = [], []
    for p in PIPELINES:
        if p not in summary:
            continue
        s = summary[p]
        b, t = s['business_metrics'], s['text_metrics']
        native_rows.append({'pipeline': p, **b, **{key: t[key] for key in ['reference_characters', 'location_coverage', 'character_location_coverage', 'character_preservation', 'aligned_strict_cer']}})
    for group, s in summary.items():
        for dimension in ['document', 'family']:
            for name, row in s.get('by_' + dimension, {}).items():
                document_rows.append({'group': group, 'dimension': dimension, 'name': name, **row['business_metrics'],
                                      'character_preservation': row['text_metrics']['character_preservation'],
                                      'aligned_strict_cer': row['text_metrics']['aligned_strict_cer']})
    write_csv(data / 'native.csv', native_rows)
    write_csv(data / 'documents-families.csv', document_rows)
    cohorts = []
    for group, scores in groups.items():
        tags = sorted({tag for score in scores for tag in score.get('tags', [])})
        for tag in tags:
            s = summarize([score for score in scores if tag in score.get('tags', [])], grouped=False)
            cohorts.append({'group': group, 'tag': tag, 'samples': s['samples'], **s['business_metrics'],
                            'character_preservation': s['text_metrics']['character_preservation'],
                            'aligned_strict_cer': s['text_metrics']['aligned_strict_cer']})
    write_csv(data / 'cohorts.csv', cohorts)
    dimensions = {}
    for row in document_rows + [{**row, 'dimension': 'category', 'name': row['tag']} for row in cohorts]:
        dimensions.setdefault((row['dimension'], row['name']), {})[row['group']] = row
    dimension_pairs = []
    for (dimension, name), members in sorted(dimensions.items()):
        comparisons = list(combinations([p for p in PIPELINES if p in members], 2))
        comparisons += [(p, p + '-baseline') for p in ('P07', 'P08') if p + '-baseline' in members]
        comparisons += [(p + '-baseline', p + '-current') for p in ('P07', 'P08') if p + '-current' in members]
        for left, right in comparisons:
            a, b = members[left], members[right]
            if a['targets'] != b['targets']:
                raise ValueError('paired dimension denominators differ')
            dimension_pairs.append({'dimension': dimension, 'name': name, 'left': left, 'right': right,
                'business_targets': a['targets'],
                'value_labels_correct_difference_right_minus_left': b['value_and_labels_correct'] - a['value_and_labels_correct'],
                'complete_information_correct_difference_right_minus_left': b['complete_information_correct'] - a['complete_information_correct'],
                'character_preservation_difference_right_minus_left': b['character_preservation'] - a['character_preservation']
                    if a['character_preservation'] is not None and b['character_preservation'] is not None else None})
    write_csv(data / 'paired-dimensions.csv', dimension_pairs)
    write_json(data / 'font-verification.json', draw_figures(index, output) if figures else {'generated': False})
    first = next(iter(summary.values()))
    pages = sum(len(score['source_pages']) for score in next(iter(groups.values())))
    report = ['# MO-Parse Lite：原生信息保全与正文转换', '',
        f"保存的 {pages} 页、{first['samples']} 个样本、{first['documents']} 份文档、{len(first.get('by_family', {}))} 个家族。共同比较 {first['text_metrics']['targets']} 个文字目标、{first['text_metrics']['reference_characters']:,} 个expected字符及 {first['business_metrics']['targets']} 个业务字段；图片alt字面诊断另列。唯一答案是 canonical expected 的现有声明选段。评分协议 `{index['protocol']['id']}`，代码与依赖身份 `{index['software']['software_id']}`。", '',
        '## 八组原生输出', '',
        '值与标签、完整业务信息均以全部业务目标为分母；字符指标以完整普通文字目标为分母。已对齐 CER 只描述已定位范围，整段完全匹配仅保留在诊断数据中。', '',
        '| 管线 | 值与标签正确/全部 | 完整信息正确/全部 | 文字定位覆盖 | 字符定位覆盖 | 字符保全 | 对齐严格CER |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in native_rows:
        p = row['pipeline']
        b = summary[p]['business_metrics']
        t = summary[p]['text_metrics']
        report.append(f"| {p} | {b['value_and_labels_correct']}/{b['targets']} | {b['complete_information_correct']}/{b['targets']} | {percent(t['location_coverage'])} | {percent(t['character_location_coverage'])} | {percent(t['character_preservation'])} | {percent(t['aligned_strict_cer'])} |")
    if 'P08' in summary:
        business, text = summary['P08']['business_metrics'], summary['P08']['text_metrics']
        report += ['', f"P08距离expected的缺口：{business['targets'] - business['complete_information_correct']} 个业务字段未满足完整要求，其中 {business['targets'] - business['readable']} 个未定位到满足身份与关系要求的值，{business['readable'] - business['value_and_labels_correct']} 个已定位但值字面不同，另有 {business['value_and_labels_correct'] - business['complete_information_correct']} 个值与标签正确但附加限定不完整。未定位项保留具体身份、单位、表头和范围原因，不直接称为数字识别错误。普通文字有 {text['missing_targets']} 个目标未定位，已定位范围的严格CER为 {percent(text['aligned_strict_cer'])}。这些缺口保留在全部目标分母中。"]
        example = numeric_examples.get('P08')
        if example:
            label = ' / '.join([*example['row'], *example['column']]).replace('|', r'\|').replace('\n', ' ')
            wanted, actual = (re.sub(r'[\r\n]+', ' ', example[key]) for key in ('expected', 'actual'))
            report += ['', f"一条仍存在的P08数值差异：{label}，expected为 `{wanted}`，保存原生输出为 `{actual}`。样本 `{example['sample']}`、目标 `{example['target']}`；身份和候选原文见[直白案例页](examples.html)，完整错误索引保留其逐项证据。"]
        else:
            literal = next((item for item in examples if item['group'] == 'P08'
                and item['outcome'] == 'incorrect' and item['actual'] is not None
                and item['expected_value'] != item['actual']), None)
            if literal:
                wanted, actual = (re.sub(r'[\r\n]+', ' ', literal[key]) for key in ('expected_value', 'actual'))
                report += ['', f"一条已定位的P08文字型业务差异：expected为“{wanted}”，保存原生输出为“{actual}”。样本 `{literal['sample_id']}`、目标 `{literal['target_id']}`；[直白案例页](examples.html)保留该字段的实际来源与身份检查。这是两段文字的差异，不据此推断数字识别错误。"]
    if figures:
        report += ['', '![原生完整业务信息](figures/business.svg)', '', '![普通文字字符保全](figures/characters.svg)']
    report += ['', '## 原始成本与失败', '',
        '| 管线 | quality800秒 | perf80三轮秒 | 工作内存GiB | 推理内存GiB | 推理侧归属显存GiB | 输出状态 |',
        '| --- | ---: | --- | ---: | ---: | ---: | --- |']
    for p in PIPELINES:
        cost = index.get('execution_costs', {}).get('native', {}).get(p)
        if not cost:
            continue
        q, perf = cost['quality800']['rounds'], cost['perf80']['rounds']
        worker, infer = resources['native'][p]['worker'], resources['native'][p]['inference']
        def gib(value, divisor):
            return display(value / divisor) if value is not None else '缺测'
        report.append(f"| {p} | {display(q[0].get('processing_seconds_including_failures')) if len(q) == 1 else '缺测'} | " + ', '.join(display(r.get('processing_seconds_including_failures')) for r in perf) + f" | {gib(worker['host_peak_bytes'],2**30)} | {gib(infer['host_peak_bytes'],2**30)} | {gib(infer['owned_gpu_peak_mib'],1024)} | {summary[p]['status_counts']} |")
    report += ['', '800页为一轮质量运行，80页三次性能重复不增加独立文档数。初始化及预热见[执行明细](data/execution.json)。内存和显存是原协议全程采样峰值，涵盖初始化、预热及全部轮次；独立峰值不相加，不称为quality800专属峰值。工作进程GPU归属缺测，不当作零，也不把推理侧峰值改称管线总峰值。TTS共驻且负载不受控，整卡与TTS显存均不归给管线；观测窗口、间隔和缺失见[资源明细](data/resources.json)。', '',
        '## P07/P08原生、唯一基线与当前正文', '',
        '| 组别 | 值与标签正确/全部 | 完整信息正确/全部 | 字符保全 | 对齐严格CER |', '| --- | ---: | ---: | ---: | ---: |']
    for p in ('P07', 'P08'):
        for group in (p, p + '-baseline', p + '-current'):
            if group not in summary:
                continue
            b, t = summary[group]['business_metrics'], summary[group]['text_metrics']
            report.append(f"| {group} | {b['value_and_labels_correct']}/{b['targets']} | {b['complete_information_correct']}/{b['targets']} | {percent(t['character_preservation'])} | {percent(t['aligned_strict_cer'])} |")
    if not pairs and baseline_preservation:
        report += ['', '本轮当前正文沿用唯一基线，没有生成新正文；实际交付文字新增正确0项、损失0项，二者是同一批保存字节。这个事实不代替原生到正文的保全检查：', '',
                   '| 管线 | 原生正确内容目标 | 转换新增正确 | 基线丢失 | 其中业务目标丢失 |', '| --- | ---: | ---: | ---: | ---: |']
        for p, gate in baseline_preservation.items():
            report.append(f"| {p} | {gate['native_correct_targets']} | {baseline_changes[p]['new_correct']} | {gate['lost_correct_targets']} | {gate['lost_correct_business_targets']} |")
        report += ['', '“转换新增正确”描述既有保存正文相对原生的差异，并非本轮修改收益。[原生到基线差异](data/native-to-baseline.json)与[保全证据](data/baseline-preservation.json)使用同一冻结程序。存在真实转换损失时必须继续修复，不能以正文未变或评分器修复代替处理。']
    for p, delta in pairs.items():
        gate = index['adoption'][p]
        report += ['', f"{p}：实际正文新增正确 {delta['new_correct']} 项，原正确损失 {delta['lost_correct']} 项。原生正确内容在当前正文丢失 {gate['native_to_final_content_losses']} 项，其中业务信息 {gate['native_to_final_business_losses']} 项。采用门槛：{'通过' if gate['adoptable'] else '未通过'}。逐项前后文字与判定位于本地private/paired.json，[配对索引](data/paired.json)保留计数和路径。"]
    if conversions:
        report += ['', '### 实际Markdown前后片段', '',
            '以下内容读取唯一基线与当前final.md，保留相邻原文及目标所在行，独立的省略号表示省略表行；不是从内部IR重建的示意文本。相同数值的已有表头、单位与归属被实际打印，才构成交付改善。完整片段及来源见[正文变化](data/conversion-examples.json)，HTML中选择对应current组可并列查看。']
        for example in conversions:
            name = ' / '.join([*example['query']['row_header_path'], *example['query']['column_header_path']])
            report += ['', f"**{example['pipeline']}：{name}，expected值 `{example['expected_value']}`**", '',
                f"样本 `{example['sample_id']}`，目标 `{example['target_id']}`。修改前：", '', '```markdown',
                example['before']['markdown'], '```', '', '修改后：', '', '```markdown', example['after']['markdown'], '```']
    report += ['', '正文评分只读实际final.md。评分读取修复对所有原生与正文共同生效，不能计为交付收益；旧评分已删除，无合法旧分数可计算“补读增益”。原生到正文的失败是可观察阶段定位，不冒充已证实的识别或适配内部根因。[直白案例页](examples.html)并列expected、当前候选及全部候选的排除理由。', '',
        'CPU回放与原生历史耗时分列于[执行明细](data/execution.json)，不相加伪造新端到端成本。图片资产及引用交付见[分项数据](data/results.json)，不提供图片内容或语义正确性成绩。', '',
        '## 范围、剩余错误和复现', '',
        "共同程序对声明选段中的文字范围及明确业务要求逐项比较。提取和范围追溯见[覆盖明细](data/coverage.json)，全部错误的expected范围、候选路径、限定状态及最早可见失败阶段见[错误索引](data/errors.json)，完整字面与判定证据在其指向的本地评分JSON中。各组剩余错误不退出分母。", '',
        '文档、家族和已有类别的配对数据见[文档与家族](data/documents-families.csv)、[类别](data/cohorts.csv)及[逐组配对差](data/paired-dimensions.csv)。类别可重叠，性能重复不增加这些独立对象。Lite参考语法及候选已用于开发，不能称为独立未见集。程序范围核对不重新认证参考材料，也不证明所有输出正确。', '',
        '本轮不重跑模型，不调用视觉或OCR，不操作GPU、TTS及在线服务，不部署。完整方法、对齐限制和复现命令见[附录](appendix.md)。']
    report += ['', '## 剩余缺陷', '',
        '| 原生组 | 未定位可比较业务值 | 已定位业务值字面不同 | 值与标签正确但限定不完整 | 未定位文字目标 | 已定位但未完整正确的文字目标 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    diagnostic_counts = {}
    for p in PIPELINES:
        if p not in groups:
            continue
        rows = [row for score in groups[p] for row in score['outcomes']]
        b, t = summary[p]['business_metrics'], summary[p]['text_metrics']
        located_errors = sum(row['kind'] not in {'business_field', 'image_alt_text'} and row.get('candidate') is not None
                             and row['outcome'] == 'incorrect' for row in rows)
        report.append(f"| {p} | {b['targets'] - b['readable']} | {b['readable'] - b['value_and_labels_correct']} | {b['value_and_labels_correct'] - b['complete_information_correct']} | {t['missing_targets']} | {located_errors} |")
        diagnostic_counts[p] = {'incorrect_reasons': dict(Counter(row['reason'] for row in rows if row['outcome'] == 'incorrect')),
            'changed_character_spans': dict(Counter(span['sensitive'] for row in rows for span in row.get('differences', [])))}
    write_json(data / 'remaining-defects.json', diagnostic_counts)
    report += ['', '这些是当前保存原生输出与expected的程序差异，涵盖值/标签、限定、文字缺失与文字或归属错误，不等同于已证实的识别内部根因。具体数字字面差异见[附录示例](appendix.md#原生数值字面差异示例)，数字/符号、名称字面与否定条件的字符差异片段另见[缺陷诊断计数](data/remaining-defects.json)及错误索引。后续需按这些错误继续改进解析和转换，不能由执行成功推定内容合格。']
    (output / 'report.md').write_text('\n'.join(report) + '\n')
    appendix = ['# Lite 方法与证据附录', '',
        '评分定义唯一维护于[评测任务](../../evaluation-tasks.md)，原生格式由[逐组说明](../../../docs/pipelines/README.md)维护。', '',
        'expected选段读取现有manifest/source-map。每个可见文字范围按完整正文或明确业务要求展开；记录残余文字继续比较。覆盖文件追溯文字范围到目标，不以元素编号或目标数量证明内容完整。候选读取只读自己的保存结构，最终正文只读final.md。', '',
        '普通文字先连续定位，再计算严格最小编辑S/D/I。换行和重复空白仅折叠为一个空格；不删除数字之间的空格。定位阈值及缺失范围影响已对齐CER的分母，字符保全和字符定位覆盖同时展示。未定位按删除处理的目标CER仅为诊断，详见results.json中text_metrics。数字、名称、否定和限定的字符差异逐项保存在本地评分JSON，不等同于业务事实全对。', '',
        '业务主结果分别统计值与完整业务标签、以及包含全部明确限定的完整信息。候选自己的表头、跨度、列表和说明用于定位，不要求私有关系字段。先定位业务身份后比较值，不跨表借值，不从矛盾陈述择优。失败和真实缺失计错，软件读取缺陷阻止发布。', '',
        '资源只使用原记录。采样峰值可能漏掉短峰，独立工作与推理峰值不相加。resources.json列采样起止跨度、样本数、有效归属样本、TTS/整卡显存可观测样本数、间隔与缺失；缺失不当零或预算。TTS显存观察不证明没有请求，身份与活动的原记录在execution.json的historical_native_conditions中，未观察到的活动保持未知。', '',
        '统一重评所有受影响组，评分依赖及代码身份见provenance.json。报告入口重新核对逐项、汇总、范围与配对门槛；报告复现仅证明再现，判分有效性由独立反例和真实格式读取验证另行约束。', '',
        '## 检索修复及独立验证', '',
        '字符串召回保留全部候选，唯一命中也核对完整业务身份。父标题、同名市场、局部期间与单位按候选实际文字和边界检查；范围不满足时拒绝比较该值，不回退到另一表。表内明确年份优先于外层年度，默认显示级别不能截断expected明确归属的细标题。查询不携带expected数值。每个字段的完整候选、来源、接受与排除理由保存在本地评分JSON的candidate.localization。', '',
        '独立正反例和真实保存样本的文字诊断范围见[软件验证记录](data/scoring-validation.json)，检索召回与排除分布及已报告错误案例的逐组判定见[检索证据](data/retrieval.json)。这些诊断用于发现软件缺陷；正式成绩来自同一冻结程序，人工阅读不提供改分。评分器补读、实际正文变化和剩余解析错误分别报告，旧错误成绩不提供收益基线。', '',
        '```bash', f'.venv/bin/python scripts/render_lite_report.py --index {index_path} --output benchmark/reports/lite', '```', '',
        '保存原生候选、实际正文、运行和逐项目标明细在本地benchmark/runs/lite/；完整配对文字在报告private/目录。公开data仅保留汇总及文字范围、候选路径索引，不复制整套参考或大型候选，它们不随报告提交。原件、expected、标注、映射、资产和数据包均未改写。']
    appendix += ['', '## 原始资源采样窗口与覆盖', '',
        '| 管线/侧 | 样本数 | 内存完整样本 | GPU归属完整样本 | 跨度秒 | 中位间隔秒 | 最大间隔秒 | TTS峰MiB | 整卡峰MiB |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for pipeline, record in resources['native'].items():
        for side, sample in record.items():
            appendix.append(f"| {pipeline}/{side} | {sample['samples']} | {sample['host_complete_samples']} | {sample['gpu_complete_samples']} | {display(sample['sample_span_seconds'])} | {display(sample['median_gap_seconds'])} | {display(sample['maximum_gap_seconds'])} | {display(sample['tts_peak_mib'])} | {display(sample['whole_gpu_peak_mib'])} |")
    appendix += ['', 'TTS和整卡峰值仅为共驻环境观察；工作进程GPU归属缺测，不据预算、CPU角色或推理侧峰值推算其GPU占用。原始文件路径、身份及完整采样分母见resources.json。', '',
        '## CPU后处理原始成本', '', '| 保存正文组 | quality800秒 | perf80三轮秒 | quality800过程RSS采样峰GiB | 原CPU输出状态 |', '| --- | ---: | --- | ---: | --- |']
    for group, cost in index.get('execution_costs', {}).get('final', {}).items():
        quality = cost['quality800']['rounds']
        elapsed = quality[0].get('postprocessing_seconds') if len(quality) == 1 else None
        perf = ', '.join(display(row.get('postprocessing_seconds')) for row in cost['perf80']['rounds'])
        peak = resources['final_cpu'][group]['quality800_peak_process_rss_bytes']
        states = ', '.join(f'{key}:{value}' for key,value in execution['final'][group]['quality800_case_status_counts'].items())
        appendix.append(f"| {group} | {display(elapsed)} | {perf} | {display(peak / 2**30) if peak is not None else '缺测'} | {states} |")
    appendix += ['', '这些是各正文原执行记录，预热单列于execution.json；仅改评分程序时不重新运行候选，也不修改这些历史耗时。原生组状态沿用原运行，正文组的读取状态表示final.md可读取性，原CPU的partial和警告等状态另在本表及execution.json保留。CPU回放按8核、8 GiB容器配额串行执行，没有专用物理核隔离；本轮工程检查曾同时使用宿主资源，时长保留共享主机条件。']
    appendix += ['', '## 原生数值字面差异示例', '', '程序对存在已定位数值差异的组各选一例，避开只有分隔标点或空白差异的例子；其余错误完整保留在错误索引。这里只展示现有判定，不提供人工改分。', '',
        '| 管线 | 样本 | 目标 | expected值 | 实际值 |', '| --- | --- | --- | --- | --- |']
    for p, example in numeric_examples.items():
        left, right = (re.sub(r'[\r\n]+', ' ', example[key]) for key in ('expected', 'actual'))
        appendix.append(f"| {p} | {example['sample']} | {example['target']} | {left} | {right} |")
    write_json(data / 'numeric-examples.json', numeric_examples)
    (output / 'appendix.md').write_text('\n'.join(appendix) + '\n')
    return [str(output / 'report.md')]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('benchmark/reports/lite'))
    args = parser.parse_args()
    for path in render(args.index, args.output):
        print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
