"""Run only the explicitly reviewed text regression, without parent conftest imports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', action='append', help='Reviewed development subset')
    parser.add_argument('--collect-only', action='store_true')
    parser.add_argument('--output', type=Path, required=True, help='New local evidence prefix')
    args = parser.parse_args()
    os.chdir(ROOT)
    manifest_path = ROOT / 'tests/source_only.json'
    manifest = json.loads(manifest_path.read_text())
    selected = args.module or list(manifest['modules'])
    if not set(selected) <= manifest['modules'].keys():
        parser.error('Every module must belong to the reviewed source-only manifest')
    reviewed = {**manifest['modules'], **manifest['dependencies']}
    for path, digest in reviewed.items():
        if sha(ROOT / path) != digest:
            parser.error('Review changed source-only test/dependency before running: ' + path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    record_path, junit = args.output.with_suffix('.json'), args.output.with_suffix('.xml')
    if record_path.exists() or junit.exists():
        parser.error('Use a new evidence prefix; historical runs are retained')
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    violations = []

    def boundary(event, values):
        if event == 'open' and isinstance(values[0], (str, bytes, os.PathLike)):
            name = os.fsdecode(values[0]).lower()
            if Path(name).suffix in {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp',
                                    '.bmp', '.tif', '.tiff', '.svg', '.mp4', '.docx', '.pptx'}:
                violations.append({'event': event, 'path': name})
                raise RuntimeError('source-only regression forbids media I/O: ' + name)
            path = Path(os.fsdecode(values[0])).absolute()
            forbidden = ('pdf_sample', 'pdf_sample_extra', 'pdf_page_images', 'datasets',
                         'benchmark/reference-decisions')
            if any(path.is_relative_to(ROOT / part) for part in forbidden):
                violations.append({'event': event, 'path': str(path)})
                raise RuntimeError('source-only regression forbids repository corpus I/O: ' + str(path))
        if event in {'socket.connect', 'socket.bind', 'socket.sendto'} and isinstance(values[1], tuple):
            violations.append({'event': event, 'address': repr(values[1])})
            raise RuntimeError('source-only regression forbids network I/O')

    sys.addaudithook(boundary)
    import pytest

    from moparse_eval.cli import code_identity

    identity = code_identity()

    class ExecutedNodes:
        def __init__(self):
            self.collected = []
            self.reports = []

        def pytest_collection_finish(self, session):
            self.collected = [item.nodeid for item in session.items]

        def pytest_runtest_logreport(self, report):
            self.reports.append({'nodeid': report.nodeid, 'phase': report.when,
                                 'outcome': report.outcome})

    nodes = ExecutedNodes()
    command = ['-q', '--noconftest', '-p', 'pytest_asyncio.plugin', *selected,
               '--junitxml=' + str(junit)]
    if args.collect_only:
        command.append('--collect-only')
    started = time.monotonic()
    status = int(pytest.main(command, plugins=[nodes]))
    unchanged = all(sha(ROOT / path) == digest for path, digest in reviewed.items())
    same_software = code_identity()['software_id'] == identity['software_id']
    record = {'purpose': 'source_only_allowed_scope_complete_controlled_regression',
              'software': identity, 'software_id': identity['software_id'],
              'command': [sys.executable, *sys.argv], 'pytest_arguments': command,
              'manifest_sha256': sha(manifest_path), 'reviewed_files': reviewed,
              'executed_modules': selected, 'excluded_modules': manifest['excluded_modules'],
              'collected_nodeids': nodes.collected,
              'executed_nodeids': list(dict.fromkeys(r['nodeid'] for r in nodes.reports)),
              'node_reports': nodes.reports,
              'reviewed_shared_dependencies': manifest['dependencies'],
              'collection_only': args.collect_only, 'pytest_exit_code': status,
              'exit_code': status if unchanged and same_software and not violations else 1,
              'boundary_violations': violations, 'tests_unchanged': unchanged,
              'software_unchanged': same_software, 'junit': str(junit),
              'junit_sha256': sha(junit), 'seconds': time.monotonic() - started,
              'actual_candidate_read': False, 'formal_execution_authorized': False}
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    return record['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
