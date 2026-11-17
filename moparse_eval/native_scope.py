"""The explicitly authorized nine-selection Native scope, using the same entry.

Only admission and source projection differ from the original fixed 24 set.
Candidate readers, three-layer comparison and aggregation remain shared.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .packaging import read_json

SCHEMA = 'moparse-native-nine-selection-freeze/1'
PLAN = 'benchmark/runs/lite/service/development/cross-document-normalization-phase12/input-plan.json'


def same_page_routes(plan, original):
    def route(row):
        locator = row.get('raw_locator', row.get('entry', '') + '/raw')
        return row['input_page'], row['branch'], locator

    return [route(row) for row in plan] == [route(row) for row in original]


def load_nine_inputs(frozen):
    from .native_evaluation import (
        ALL_SCOPE,
        ALL_SELECTIONS,
        PIPELINES,
        _keys,
        artifact,
        verify_input,
    )

    scope = read_json(artifact(frozen['components']['scope']))
    if scope.get('scope_id') != ALL_SCOPE or scope.get('selection_ids') != list(ALL_SELECTIONS) or scope.get('pipelines') != list(PIPELINES):
        raise ValueError('nine-selection scope must retain exactly S1-S9 and all eight pipelines')
    binding = read_json(artifact(frozen['components']['inputs']))
    if binding['original_plan']['path'] != PLAN:
        raise ValueError('nine-selection Native inputs require the existing fixed plan')
    plan = read_json(artifact(binding['original_plan']))
    original = {(r['sample_id'], r['pipeline']): r for r in plan['records']}
    old_bindings = {(r['sample_id'], r['pipeline']): read_json(artifact(r['binding'])) for r in binding['original_bindings']}
    _keys(binding['records'], ALL_SCOPE)
    for row in binding['records']:
        prior = original[row['sample_id'], row['pipeline']]
        for name in ('native', 'observation'):
            if row[name] != {'path': prior[name], 'sha256': prior[name + '_sha256']}:
                raise ValueError('nine-selection candidate differs from its own fixed Native input')
        if row['selection'] != prior['selection'] or row['configuration'] != prior['configuration'] or not same_page_routes(prior['native_page_bindings'], row['page_bindings']):
            raise ValueError('nine-selection authorization/configuration/page mapping differs')
        old = old_bindings[row['sample_id'], row['pipeline']]
        if row['producer'] != old['producer'] or row['configuration'] != old['configuration'] or row['page_bindings'] != old['page_bindings']:
            raise ValueError('nine-selection original producer or binding differs')
        verify_input(row, scope=ALL_SCOPE)
    return binding['records']


def load_nine_preparation(path: Path, *, verify_requirements=True):
    from .ast_alignment import METHOD, RULES
    from .cli import code_identity
    from .continuous_projection import extend_projection
    from .native_evaluation import (
        ALL_SCOPE,
        ALL_SELECTIONS,
        ROOT,
        _keys,
        _unapproved,
        artifact,
        requirement_inventory,
    )
    from .requirement_gate import load_bound_requirement

    frozen = read_json(path)
    _unapproved(frozen)
    if frozen.get('schema') != SCHEMA:
        raise ValueError('unknown nine-selection research schema')
    parts = {k: read_json(artifact(v)) for k, v in frozen['components'].items()}
    inputs = load_nine_inputs(frozen)
    live = code_identity()
    evaluation = parts['evaluation']
    if frozen['software_id'] != live['software_id'] or evaluation['software']['software_id'] != live['software_id'] or evaluation['scoring_method'] != METHOD or evaluation['scoring_rules'] != RULES or evaluation['python_executable'] != sys.executable:
        raise ValueError('nine-selection software/method/rules/Python changed')
    for ref in evaluation['environment_files']:
        artifact(ref, suffix=Path(ref['path']).suffix)
    validation = parts['validation']
    receipt = read_json(artifact(validation['source_only']))
    if validation['software_id'] != live['software_id'] or receipt['software_id'] != live['software_id'] or receipt['exit_code'] != 0 or receipt['boundary_violations'] or not receipt['software_unchanged'] or not receipt['tests_unchanged']:
        raise ValueError('nine-selection source-only validation failed or changed')
    for relative, digest in receipt['reviewed_files'].items():
        artifact({'path': relative, 'sha256': digest}, suffix=Path(relative).suffix)
    reading = read_json(artifact(validation['native_reading']))
    _keys(reading['records'], ALL_SCOPE)
    if reading['software_id'] != live['software_id'] or reading['status'] != 'passed' or reading['expected_access'] is not False or reading['Final_access'] is not False or reading['boundary_violations'] or not reading['source_masked'] or not reading['network_namespace_isolated']:
        raise ValueError('nine-selection independent Native reading failed')
    for row in reading['records']:
        artifact(row['candidate'])
    binding = parts['requirements']
    index = artifact(binding['index'])
    if {r['sample_id'] for r in binding['records']} != set(ALL_SELECTIONS) or len(binding['records']) != 9:
        raise ValueError('nine-selection requirement binding is incomplete')
    selections = {r['sample_id']: r['selection'] for r in inputs}
    loaded = {}
    if verify_requirements:
        for row in binding['records']:
            sid = row['sample_id']
            artifact(row['original_json'])
            for ref in row['reference_files']:
                artifact(ref, suffix=Path(ref['path']).suffix)
            graph, projection, _, _ = load_bound_requirement(index, selections[sid], ROOT / 'pdf_sample/parsing/expected')
            if graph['comparison_coverage']['source_complete'] is not True or graph['comparison_coverage']['structure_complete'] is not True:
                raise ValueError('nine-selection literal source or actual AST structure is incomplete')
            projected = extend_projection(graph, projection)
            if read_json(artifact(row['projection'])) != projected or requirement_inventory(projected) != row['inventory']:
                raise ValueError('nine-selection generated projection/owners changed')
            loaded[sid] = projected
    _keys(parts['readiness']['records'], ALL_SCOPE)
    return frozen, parts, loaded
