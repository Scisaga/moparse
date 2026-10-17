"""Exercise the independent HTTP reader using temporary capture copies only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=HERE / 'http-source-reader-validation.json')
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f'Refusing to overwrite evidence: {args.output}')
    spec = importlib.util.spec_from_file_location('independent_http_source_reader', HERE / 'verify-http-source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source_summary = json.loads((args.input / 'summary.json').read_text())
    stems = ('1225474693', '1225473526')
    original = {stem: (args.input / 'cases' / stem / 'result.md').read_bytes() for stem in stems}
    source_reference_bytes = module.REFERENCE.read_bytes()
    tests = [
        ('received_actual_capture', None, None, None, 'pass_with_known_character_defect'),
        ('fully_source_exact_parenthesis', '1225474693', '稀释每股收益（元／股 |', '稀释每股收益（元／股） |', 'pass'),
        ('reject_changed_numeric_literal', '1225474693', '21,467,154,275.58', '21,467,154,275.59', 'failed'),
        ('reject_changed_complete_header', '1225474693', '|  | 本报告期 | 上年同期 |', '|  | 本报告期末 | 上年同期 |', 'failed'),
        ('reject_wrong_source_page', '1225474693', '"source_pages":[3],"num_rows":9', '"source_pages":[2],"num_rows":9', 'failed'),
        ('reject_funding_span_loss', '1225473526', '[1,0,8,1]', '[1,0,7,1]', 'failed'),
        ('reject_funding_row_amount_change', '1225473526', '|  | 2020 年 | 非公开发行 | 99,092.46 |', '|  | 2020 年 | 非公开发行 | 99,092.47 |', 'failed'),
        ('reject_funding_label_loss', '1225473526', '| 历次筹资情况 | 时间 |', '| 历次筹资 | 时间 |', 'failed'),
        ('reject_continuation_source_rows', '1225473526', 'source-rows: 2-6; logical-rows: 8-12', 'source-rows: 1-5; logical-rows: 8-12', 'failed'),
        ('reject_continuation_body_missing', '1225473526', '| 7 | 全国社保基金一零二组合 | 14,818,700 | 1.42% | - |\n', '', 'failed'),
        ('reject_other_EPS_label_damage', '1225474693', '稀释每股收益（元／股 |', '稀释每股收益（元／ |', 'failed'),
        ('reject_share_unit_loss', '1225473526', '单位 ： 股', '单位 ： 元', 'failed'),
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix='mosaic-http-source-reader-') as temporary:
        temp = Path(temporary)
        (temp / 'run-plan.json').write_bytes((args.input / 'run-plan.json').read_bytes())
        for stem in stems:
            (temp / 'cases' / stem).mkdir(parents=True)
        for name, stem, old, new, expected in tests:
            changed = dict(original)
            if stem is not None:
                content = changed[stem].decode()
                assert old in content, f'Self-test mutation absent: {name}'
                changed[stem] = content.replace(old, new, 1).encode()
            summary = json.loads(json.dumps(source_summary))
            for key, payload in changed.items():
                (temp / 'cases' / key / 'result.md').write_bytes(payload)
                item = next(v for v in summary if v['source'] == key)
                # Refresh the synthetic transport hashes deliberately so the
                # negative test exercises source content, not SHA rejection.
                item['MD_SHA256'] = hashlib.sha256(payload).hexdigest()
                item['MD_bytes'] = len(payload)
            (temp / 'summary.json').write_text(json.dumps(summary))
            result = module.verify(SimpleNamespace(input=temp, reference=module.REFERENCE))
            assert result['status'] == expected, (name, result)
            results.append({'name': name, 'expected_status': expected,
                            'actual_status': result['status'], 'passed': True})
    assert all((args.input / 'cases' / stem / 'result.md').read_bytes() == payload
               for stem, payload in original.items())
    assert module.REFERENCE.read_bytes() == source_reference_bytes
    payload = {'schema': 'independent-HTTP-source-reader-validation/1', 'status': 'pass',
               'source_capture': str(args.input.resolve()), 'checks': results,
               'actual_capture_and_source_reference_modified': False,
               'temporary_copies_only': True, 'HTTP_requests': 0, 'model_calls': 0,
               'reader_SHA256': hashlib.sha256((HERE / 'verify-http-source.py').read_bytes()).hexdigest(),
               'validation_script_SHA256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'pass', 'checks': len(results), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
