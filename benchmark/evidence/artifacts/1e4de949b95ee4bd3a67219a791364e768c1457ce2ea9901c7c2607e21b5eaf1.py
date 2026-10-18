"""CPU-only export-scope reproduction; never modifies captured HTTP bytes."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import sys
import tarfile

ROOT = Path('/opt/mosaic-parse')
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from benchmark.tools.check_release import load_reader

archive = ROOT/'benchmark/runs/header-v2-http-20261018/frozen-reviewed-source.tar.gz'
with tarfile.open(archive) as tar:
    member = next(item for item in tar.getmembers() if item.name.endswith('app/services/table_service.py'))
    old_source = tar.extractfile(member).read()
old_path = OUT/'v2-table-service-replay-only.py'
old_path.write_bytes(old_source)
spec = importlib.util.spec_from_file_location('old_table_scope_replay', old_path)
old = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = old
spec.loader.exec_module(old)

import app.services.export_service as exporter
spec = importlib.util.spec_from_file_location('new_scope_regression_tests', ROOT/'tests/integration/test_public_table_source_scope.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
current = exporter.assemble_logical_tables
regressions = []
try:
    exporter.assemble_logical_tables = old.assemble_logical_tables
    for name, callback in (
        ('adjacent_standalone_merge_off', lambda: tests.test_adjacent_standalone_tables_have_exact_public_source_scopes(False)),
        ('adjacent_standalone_merge_on', lambda: tests.test_adjacent_standalone_tables_have_exact_public_source_scopes(True)),
        ('logical_followed_by_standalone', tests.test_standalone_after_logical_table_cannot_leak_its_map_into_the_logical_scope),
    ):
        try:
            callback()
        except AssertionError:
            regressions.append({'case': name, 'v2_fails_exact_source_ownership': True})
        else:
            raise AssertionError('Regression test did not catch frozen V2: ' + name)
finally:
    exporter.assemble_logical_tables = current
for callback in (
    lambda: tests.test_adjacent_standalone_tables_have_exact_public_source_scopes(False),
    lambda: tests.test_adjacent_standalone_tables_have_exact_public_source_scopes(True),
    tests.test_standalone_after_logical_table_cannot_leak_its_map_into_the_logical_scope,
):
    callback()

capture = ROOT/'benchmark/runs/header-v2-http-20261018/regression504/cases/1225473526/result.md'
raw = capture.read_text()
reader = load_reader()
pattern = re.compile(r'(?P<source><!-- table-source: (?P<source_id>[^;\s]+);[^\n]* -->)\n\n(?P<fragment><!-- table-fragment: (?P<fragment_id>[^;\s]+) -->)')
changes = []
def reorder(match):
    if match['source_id'] != match['fragment_id']:
        return match[0]
    changes.append(match['source_id'])
    return match['fragment'] + '\n\n' + match['source']
fixed = pattern.sub(reorder, raw)
assert changes
assert re.sub(r'<!--.*?-->', '', raw, flags=re.S) == re.sub(r'<!--.*?-->', '', fixed, flags=re.S)
before = reader.public_tables(raw)
after = reader.public_tables(fixed)
assert [(t['id'],t['meta'],t['rows']) for t in before] == [(t['id'],t['meta'],t['rows']) for t in after]
for table in after:
    if table['id'].startswith('table_'):
        continue
    assert len(table['sources']) == 1
    assert table['sources'][0]['fragment'] == table['id']
    assert table['sources'][0]['page'] == table['meta']['source_pages'][0]
logical = next(t for t in after if t['id']=='table_mineru_p6_t2_mineru_p7_t1')
assert [s['fragment'] for s in logical['sources']] == ['mineru_p6_t2','mineru_p7_t1']
assert [s['logical_rows'] for s in logical['sources']] == ['1-7','8-12']
funding = next(t for t in after if t['id']=='mineru_p7_t2')
assert funding['sources'] == [{'fragment':'mineru_p7_t2','page':7,'source_rows':'1-11','logical_rows':'1-11','repeated_header_rows':0}]
(OUT/'full27-comment-order-diagnostic-not-http.md').write_text(fixed)
report = {
    'scope': 'CPU export-only replay. Old real HTTP bytes stay unchanged. Diagnostic Markdown only reorders standalone source/fragment comments; not a fresh HTTP result or model quality claim.',
    'frozen_reader_sha256': hashlib.sha256(Path(reader.__file__).read_bytes()).hexdigest(),
    'old_frozen_table_service_sha256': hashlib.sha256(old_source).hexdigest(),
    'old_source_sha_matches_v2_freeze': hashlib.sha256(old_source).hexdigest()==json.loads((ROOT/'benchmark/runs/header-verifier-v2-20261018/source-freeze.json').read_text())['files']['app/services/table_service.py'],
    'regression_tests': regressions,
    'v3_passes_all_three_same_tests': True,
    'original_full27_http_sha256': hashlib.sha256(capture.read_bytes()).hexdigest(),
    'standalone_comment_pairs_reordered': changes,
    'all_visible_bytes_after_removing_actual_comments_equal': True,
    'all_table_grid_and_structure_objects_equal': True,
    'all_standalone_source_maps_uniquely_owned': True,
    'normal_continuation_sources_after': logical['sources'],
    'funding_sources_after': funding['sources'],
    'old_map_ownership': {t['id']:t['sources'] for t in before if t['id'] in ('table_mineru_p6_t2_mineru_p7_t1','mineru_p7_t2','mineru_p7_t3')},
}
(OUT/'source-order-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'regression_cases_catch_old_v2': len(regressions),'v3_passes':True,'real27_standalone_scope_diagnostic_correct':True,'reordered_tables':len(changes)},ensure_ascii=False))
