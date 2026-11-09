"""Invented gate-transport artifacts; never evidence for a real replay grant."""

import hashlib

from moparse_eval.packaging import write_json
from moparse_eval.requirement_gate import _EVIDENCE_CATEGORIES
from moparse_eval.requirement_graph import compile_requirement_graph, write_requirement_graph


def artifact(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def controlled_expected(sample_id="fixture"):
    target = {"id": "expected:L1:text", "kind": "text", "text": "Name: Delta; Revenue: 17",
              "raw_text": "Name: Delta; Revenue: 17", "raw": "Name: Delta; Revenue: 17",
              "reference": {"path": "<invented-gate-source>", "lines": [1, 1]},
              "pages": [1], "cells": [], "parents": [], "has_children": False,
              "context": [], "selected_heading_context": [], "outside_selection_context": []}
    return {"sample_id": sample_id, "document_id": "invented-document", "source_pages": [1],
                "standard": "expected_only", "targets": [target], "scope": [
                    {"lines": [1, 1], "pages": [1], "declared_source_pages": [1], "outside_source_pages": []}]}


def controlled_source_run(root, sample_id="fixture"):
    """Only authorization metadata; no candidate, source PDF or model output."""
    dataset, baseline = root / "dataset", root / "baseline"
    write_json(dataset / "manifest.json", {"samples": [
        {"id": sample_id, "document_id": "invented-document", "source_pages": [1]}]})
    write_json(baseline / "run.json", {"dataset": str(dataset), "cases": [
        {"sample_id": sample_id, "suite": "quality800", "phase": "measured"}]})
    return baseline


def controlled_gate(root, software_id="controlled-source", sample_id="fixture"):
    expected = controlled_expected(sample_id)
    graph = compile_requirement_graph(expected)
    assert graph["semantic_complete"] is True
    view = root / "samples" / f"{sample_id}.json"
    write_requirement_graph(graph, view, view.with_suffix(".xml"))
    row = {"sample_id": sample_id, "json": str(view.relative_to(root)),
           "software_id": software_id, "worker_software_unchanged": True,
           "comparison_contract": "semantic", "comparison_contract_version": "semantic/1",
           "generated_view_sha256": artifact(view)["sha256"], "semantic_complete": True,
           "source_obligation_inventory_complete": True, "inventory_validation": {"status": "passed"}}
    index = root / "index.json"
    write_json(index, {"purpose": "expected_output_requirements_not_corpus_review", "software_id": software_id,
                      "comparison_contract": "semantic", "comparison_contract_version": "semantic/1",
                      "software_unchanged": True, "semantic_complete": True,
                      "source_obligation_inventory_complete": True, "inventory_validation": {"status": "passed"},
                      "records": [row]})
    return controlled_evidence(root, index, software_id)


def controlled_evidence(root, index, software_id):
    """Bind invented validation observations to an existing generated index."""
    gate = {"status": "passed", "software_id": software_id,
            "requirement_index": artifact(index), "evidence": {}}
    import json
    declared = json.loads(index.read_text())
    gate.update({key: declared[key] for key in ('comparison_contract', 'comparison_contract_version')})
    # These observations are invented transport fixtures. Actual validation
    # artifacts must carry observations made by independently executed cases.
    for purpose, categories in _EVIDENCE_CATEGORIES.items():
        evidence = root / f"{purpose}.json"
        write_json(evidence, {"schema": "moparse-independent-validation/1", "purpose": purpose,
            "software_id": software_id, "status": "passed", "requirement_index_sha256": artifact(index)["sha256"],
            "oracle_origin": "hand_authored_source_independent", "known_defects": [],
            "cases": [{"case_id": f"controlled-{category}", "category": category,
                       "input": {"fixture": category}, "expected": {"accepted": False}, "observed": {"accepted": False}}
                      for category in sorted(categories)]})
        gate["evidence"][purpose] = artifact(evidence)
    if declared['comparison_contract'] == 'document_ast':
        from moparse_eval.packaging import read_json
        from moparse_eval.requirement_gate import _digest

        samples, capabilities = [], set()
        for row in declared['records']:
            graph = read_json(index.parent / row['json'])
            coverage = graph['comparison_coverage']
            capabilities.update(coverage['required_capabilities'])
            samples.append({'sample_id': row['sample_id'], 'status': 'passed',
                'comparison_contract_version': 'document_ast/1',
                'generated_view_sha256': row['generated_view_sha256'],
                'comparison_coverage_sha256': _digest(coverage),
                'requirement_ids': sorted(set(coverage['content_requirement_ids'] + coverage['mixed_order_requirement_ids']).union(
                    *map(set, coverage['retained_semantic_requirements'].values()))),
                'obligation_ids': [r['obligation_id'] for r in coverage['obligations']],
                'analysis_limitation_ids': [r['issue_id'] for r in coverage['analysis_limitations']]})
        for purpose in _EVIDENCE_CATEGORIES:
            path = root / f'{purpose}.json'
            evidence = read_json(path)
            evidence.update(comparison_contract='document_ast', comparison_contract_version='document_ast/1')
            if purpose == 'oracle':
                for sample in samples:
                    case_id = 'controlled-sample-' + sample['sample_id']
                    sample['case_ids'] = [case_id]
                    # Transport fixture only. This invented observation never
                    # serves as independent acceptance of repository sources.
                    assertion = {'source_assertions': [{'fixture': 'invented-source-observation'}]}
                    evidence['cases'].append({'case_id': case_id, 'category': 'sample_source_assertions',
                        'input': {'sample_id': sample['sample_id']}, 'expected': assertion, 'observed': assertion,
                        **{key: sample[key] for key in ('requirement_ids', 'obligation_ids', 'analysis_limitation_ids')}})
                evidence['samples'] = samples
            if purpose == 'comparison':
                evidence['capabilities'] = {name: [f'controlled-{name}'] for name in capabilities}
                evidence['cases'].extend({'case_id': f'controlled-{name}', 'category': name,
                    'input': {'fixture': name}, 'expected': {'accepted': False}, 'observed': {'accepted': False}}
                    for name in sorted(capabilities))
            write_json(path, evidence)
            gate['evidence'][purpose] = artifact(path)
    return {"status": "passed", "expected_structure_gate": gate}
