"""Freeze completed official native-path trial artifacts, without inference."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = Path('/opt/mosaic-parse')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    include = set()
    for directory in ('official-native-standard', 'official-native-advanced',
                      'official-native-harness-attempt-1', 'official-native-environment', 'vllm-native-server'):
        include.update(path for path in (HERE / directory).rglob('*') if path.is_file())
    include.update(HERE / name for name in (
        'run-official-native-standard.py', 'run-official-native-comparison.py', 'summarize-official-native.py',
        'diagnose-official-native-output.py', 'freeze-official-native-evidence.py',
        'official-native-path-investigation.json', 'official-native-comparison-summary.json',
        'official-native-layer-diagnostics.json', 'official-native-comparison-execution.json',
        'official-native-GPU-resource-summary.json', 'official-native-handoff-requested.json',
        'official-native-handoff-ready.json', 'official-native-handoff-complete.json',
        'official-native-handoff-attempt1-observer-error.json',
        'official-native-standard.log', 'official-native-advanced.log'))
    include.update((BASE / 'model-evaluation').glob('official-native-*.json'))
    include.add(BASE / 'model-evaluation' / 'frozen-five-configuration-source-summary.json')
    records = [{'path_relative_to_BASE': str(path.relative_to(BASE)), 'bytes': path.stat().st_size,
                'SHA256': digest(path)} for path in sorted(include) if path.exists()]
    summary = json.loads((HERE / 'official-native-comparison-summary.json').read_text())
    if any(value['status'] != 'completed' for value in summary['tiers'].values()):
        raise RuntimeError('Cannot freeze unfinished official pipeline trial.')
    provenance = []
    for tier in ('standard', 'advanced'):
        manifest = json.loads((HERE / f'official-native-{tier}' / 'run-manifest.json').read_text())
        provenance.append({'tier': tier, 'started_at': manifest['started_at'], 'finished_at': manifest['finished_at'],
                           'completed_original_14': sum(case['cohort'] == 'original_14' and case['status'] == 'completed' for case in manifest['cases']),
                           'completed_additional_p62': sum(case['cohort'] == 'additional_p62' and case['status'] == 'completed' for case in manifest['cases']),
                           'unstarted_cases': manifest['unstarted_cases'],
                           'CPU_initialization_seconds_separate': manifest['CPU_model_initialization']['seconds'],
                           'model_calls_during_this_freeze': 0})
    runtime = [{ 'path': name, 'SHA256': digest(ROOT / name)} for name in (
        'app/services/table_service.py', 'tests/unit/test_docling_source_complete_export.py')]
    result = {
        'schema': 'mosaicparse-official-native-path-evidence-freeze/1',
        'created_UTC': dt.datetime.now(dt.timezone.utc).isoformat(),
        'scope': 'Official MinerU4.0.12 standard+TXT and advanced+TXT; same original14 pages and additional p62, original full-byte PDF inputs with explicit single-page page_range. No app/service/shared environment changes by this experiment.',
        'mineru_commit': 'b7f3dd0c5f6e6d66a298239ffd02b328b873918e',
        'VLM_checkpoint_revision': '08aaea840498d49ce16247b6263196cf02814885',
        'VLM_weight_SHA256': 'abf8681ca63b8dec7b67de257af47b821f179442f72998d0696ae2ed9232a5f0',
        'small_CPU_model_revision': '358310b4f64b95f9fefc372ad899356e4111f376',
        'phase_completion': provenance,
        'timing_evidence': 'mineru-trial/official-native-comparison-summary.json',
        'GPU_scope': 'GPU owner samples cover each complete15-page phase including CPU initialization/intercase work; do not label these original14-only or per-request GPU measurements.',
        'diagnostics': 'mineru-trial/official-native-layer-diagnostics.json',
        'public_output_gap': 'No cell-level source geometry or explicit header-role flags; no production Mosaic table-source adapter or full-document acceptance is claimed.',
        'failed_harness_attempt': 'Attempt1 had CPU observer type error before any chat request. Archived raw records preserved, excluded from model quality/timing results; no completed model cases replayed.',
        'runtime_frozen_readback': runtime,
        'file_count': len(records), 'logical_bytes': sum(item['bytes'] for item in records), 'files': records,
    }
    output = HERE / 'official-native-evidence-index.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'path': str(output), 'SHA256': digest(output), 'file_count': len(records),
                      'logical_bytes': result['logical_bytes']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
