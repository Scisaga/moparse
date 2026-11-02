"""Build the single Lite report from frozen scores and recorded measurements."""

from __future__ import annotations

import argparse
import csv
import hashlib
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
    write_json(data / 'results.json', summary)
    write_json(data / 'resources.json', resources)
    execution = {**index.get('execution_costs', {})}
    execution['native'] = {p: {suite: {key: value for key, value in record.items() if key != 'resource_observations'}
        for suite, record in suites.items()} for p, suites in execution.get('native', {}).items()}
    execution['raw_runtime_evidence'] = {'index': str(index_path.resolve()),
        'meaning': 'original observations and detailed inference telemetry remain local; recorded times are copied unchanged'}
    write_json(data / 'execution.json', execution)
    public_coverage = [{**row, 'content_coverage': {key: value for key, value in row['content_coverage'].items() if key != 'ranges'},
        'range_evidence': [{key: value for key, value in evidence.items() if key != 'text'} |
            {'ranges': [{key: value for key, value in part.items() if key != 'literal'} for part in evidence['ranges']]}
            for evidence in row['content_coverage']['ranges']]} for row in index['coverage']]
    write_json(data / 'coverage.json', public_coverage)
    write_json(data / 'provenance.json', {'index': str(index_path.resolve()), 'software': index['software'],
        'protocol': index['protocol'], 'development_exposure': index.get('development_exposure'),
        'report_generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    rows = []
    numeric_examples = {}
    for group, scores in groups.items():
        native = {score['sample_id']: {row['id']: row for row in score['outcomes']} for score in groups.get(group.split('-')[0], [])}
        for score in scores:
            for row in score['outcomes']:
                if row['outcome'] == 'correct':
                    continue
                if (group in PIPELINES and group not in numeric_examples and row['kind'] == 'business_field'
                        and isinstance(row.get('actual'), str) and row.get('candidate', {}).get('status') == 'compared'
                        and not row.get('value_and_labels_correct')
                        and re.sub(r'[\s,.]', '', row['expected']['value']) != re.sub(r'[\s,.]', '', row['actual'])
                        and re.fullmatch(r'[\d\s,.+\-−()%‰$€£¥]+', row['expected']['value'] or '')
                        and re.fullmatch(r'[\d\s,.+\-−()%‰$€£¥]+', row['actual'] or '')):
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
    pairs = {}
    for pipeline in ('P07', 'P08'):
        if pipeline + '-current' in groups and pipeline + '-baseline' in groups:
            pairs[pipeline] = paired_changes(groups[pipeline + '-baseline'], groups[pipeline + '-current'])
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
    report += ['', '正文评分只读实际final.md。评分读取修复对所有原生与正文共同生效，不能计为交付收益；旧评分已删除，无合法旧分数可计算“补读增益”。原生到正文的失败是可观察阶段定位，不冒充已证实的识别或适配内部根因。', '',
        'CPU回放与原生历史耗时分列于[执行明细](data/execution.json)，不相加伪造新端到端成本。图片资产及引用交付见[分项数据](data/results.json)，不提供图片内容或语义正确性成绩。', '',
        '## 范围、剩余错误和复现', '',
        "共同程序对声明选段中的文字范围及明确业务要求逐项比较。提取和范围追溯见[覆盖明细](data/coverage.json)，全部错误的expected范围、候选路径、限定状态及最早可见失败阶段见[错误索引](data/errors.json)，完整字面与判定证据在其指向的本地评分JSON中。各组剩余错误不退出分母。", '',
        '文档、家族和已有类别的配对数据见[文档与家族](data/documents-families.csv)、[类别](data/cohorts.csv)及[逐组配对差](data/paired-dimensions.csv)。类别可重叠，性能重复不增加这些独立对象。Lite参考语法及候选已用于开发，不能称为独立未见集。程序范围核对不重新认证参考材料，也不证明所有输出正确。', '',
        '本轮不重跑模型，不调用视觉或OCR，不操作GPU、TTS及在线服务，不部署。完整方法、对齐限制和复现命令见[附录](appendix.md)。']
    report += ['', '## 剩余缺陷', '',
        '| 原生组 | 值或标签错误/缺失 | 值与标签正确但限定不完整 | 未定位文字目标 | 已定位但未完整正确的文字目标 |',
        '| --- | ---: | ---: | ---: | ---: |']
    diagnostic_counts = {}
    for p in PIPELINES:
        if p not in groups:
            continue
        rows = [row for score in groups[p] for row in score['outcomes']]
        b, t = summary[p]['business_metrics'], summary[p]['text_metrics']
        located_errors = sum(row['kind'] not in {'business_field', 'image_alt_text'} and row.get('candidate') is not None
                             and row['outcome'] == 'incorrect' for row in rows)
        report.append(f"| {p} | {b['targets'] - b['value_and_labels_correct']} | {b['value_and_labels_correct'] - b['complete_information_correct']} | {t['missing_targets']} | {located_errors} |")
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
        '```bash', f'.venv/bin/python scripts/render_lite_report.py --index {index_path} --output benchmark/reports/lite', '```', '',
        '保存原生候选、实际正文、运行和逐项目标明细在本地benchmark/runs/lite/；完整配对文字在报告private/目录。公开data仅保留汇总及文字范围、候选路径索引，不复制整套参考或大型候选，它们不随报告提交。原件、expected、标注、映射、资产和数据包均未改写。']
    appendix += ['', '## 原始资源采样窗口与覆盖', '',
        '| 管线/侧 | 样本数 | 内存完整样本 | GPU归属完整样本 | 跨度秒 | 中位间隔秒 | 最大间隔秒 | TTS峰MiB | 整卡峰MiB |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for pipeline, record in resources['native'].items():
        for side, sample in record.items():
            appendix.append(f"| {pipeline}/{side} | {sample['samples']} | {sample['host_complete_samples']} | {sample['gpu_complete_samples']} | {display(sample['sample_span_seconds'])} | {display(sample['median_gap_seconds'])} | {display(sample['maximum_gap_seconds'])} | {display(sample['tts_peak_mib'])} | {display(sample['whole_gpu_peak_mib'])} |")
    appendix += ['', 'TTS和整卡峰值仅为共驻环境观察；工作进程GPU归属缺测，不据预算、CPU角色或推理侧峰值推算其GPU占用。原始文件路径、身份及完整采样分母见resources.json。', '',
        '## CPU后处理原始成本', '', '| 保存正文组 | quality800秒 | perf80三轮秒 | quality800过程RSS采样峰GiB |', '| --- | ---: | --- | ---: |']
    for group, cost in index.get('execution_costs', {}).get('final', {}).items():
        quality = cost['quality800']['rounds']
        elapsed = quality[0].get('postprocessing_seconds') if len(quality) == 1 else None
        perf = ', '.join(display(row.get('postprocessing_seconds')) for row in cost['perf80']['rounds'])
        peak = resources['final_cpu'][group]['quality800_peak_process_rss_bytes']
        appendix.append(f"| {group} | {display(elapsed)} | {perf} | {display(peak / 2**30) if peak is not None else '缺测'} |")
    appendix += ['', '这些是各正文原执行记录，预热单列于execution.json；仅改评分程序时不重新运行候选，也不修改这些历史耗时。']
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
