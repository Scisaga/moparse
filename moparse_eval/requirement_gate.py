"""Verify generated requirement and independent validation evidence before replay.

Only generated JSON evaluation artifacts are read here. The isolated candidate
receives a digest receipt, never canonical expected or the generated answers.
The receipt is an isolation transport record; the host must revalidate the
underlying artifacts before every execution, not trust the receipt as an oracle.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_DIGEST = re.compile(r"[0-9a-f]{64}")
_EVIDENCE_CATEGORIES = {
    "oracle": {
        "atomic_business", "relation_qualifier", "table_list_transpose", "synonym",
        "business_attribute_conflict", "quantity_unit_conflict", "period_binding_conflict",
        "subject_binding_conflict", "negation_condition", "quoted_name", "direction_magnitude",
    },
    "mutations": {
        "source_deletion", "relation_deletion", "synchronized_derived_fields", "opaque_node_disguise",
    },
    "comparison": {
        "equivalent", "conflict", "insufficient", "unrelated", "composite_ast",
        "candidate_capacity", "candidate_position_without_value", "real_format_e2e",
    },
}
RECEIPT_SCHEMA = "moparse-replay-gate-receipt/1"


def _fail(reason: str) -> None:
    raise ValueError(f"expected structure gate: {reason}")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _passed(record: Any) -> bool:
    return isinstance(record, dict) and record.get("status") == "passed"


def _artifact(reference: Any, *, label: str) -> tuple[Path, dict[str, Any], str]:
    if not isinstance(reference, dict) or not isinstance(reference.get("path"), str):
        _fail(f"{label} requires a generated JSON path and digest")
    path = Path(reference["path"])
    expected_digest = reference.get("sha256")
    if not path.is_absolute() or path.suffix != ".json" or not isinstance(expected_digest, str) or not _DIGEST.fullmatch(expected_digest):
        _fail(f"{label} requires an absolute generated JSON path and SHA-256")
    try:
        data = path.read_bytes()
        actual_digest = hashlib.sha256(data).hexdigest()
        value = json.loads(data)
    except (OSError, ValueError) as error:
        _fail(f"{label} is unavailable or invalid: {type(error).__name__}")
    if expected_digest != actual_digest or not isinstance(value, dict):
        _fail(f"{label} identity changed or is not a JSON object")
    return path, value, actual_digest


def validate_expected_structure_gate(validation: dict[str, Any], software_id: str, *,
                                     scope: set[str] | None = None,
                                     expected_by_sample: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Load same-source, complete requirements and independently recorded cases.

    These checks establish artifact binding and reject known incomplete or stale
    validation. They do not manufacture independent semantic judgments from the
    production graph, case totals, a status flag, or an internal consistency check.
    """
    from .requirement_graph import is_deferred_input_scope, validate_requirement_graph

    gate = validation.get("expected_structure_gate", {})
    if (not isinstance(gate, dict) or not isinstance(software_id, str) or not software_id.strip()
            or gate.get("status") != "passed" or gate.get("software_id") != software_id):
        _fail("the current software must have a passed, independently evidenced gate")
    index_path, index, index_digest = _artifact(gate.get("requirement_index"), label="requirement index")
    if (index.get("purpose") != "expected_output_requirements_not_corpus_review"
            or index.get("software_id") != software_id or index.get("software_unchanged") is not True
            or index.get("semantic_complete") is not True
            or index.get("source_obligation_inventory_complete") is not True
            or not _passed(index.get("inventory_validation"))):
        _fail("requirement index is stale or has incomplete source obligations or semantics")
    records = index.get("records")
    if not isinstance(records, list) or not records or any(not isinstance(row, dict) for row in records):
        _fail("requirement index has no complete declared scope")
    ids = [row.get("sample_id") for row in records]
    if (any(not isinstance(ident, str) or not ident for ident in ids) or len(ids) != len(set(ids))
            or scope is not None and set(ids) != set(scope)):
        _fail("requirement index differs from the complete declared sample scope")
    if expected_by_sample is not None and set(expected_by_sample) != set(ids):
        _fail("read-only canonical expected selections differ from the declared sample scope")
    if expected_by_sample is not None and any(
            not isinstance(value, dict) or value.get("sample_id") != ident
            or not isinstance(value.get("targets"), list) for ident, value in expected_by_sample.items()):
        _fail("canonical source binding requires actual authorized expected selections")
    for row in records:
        if (row.get("semantic_complete") is not True or row.get("source_obligation_inventory_complete") is not True
                or not _passed(row.get("inventory_validation"))):
            _fail("every sample must retain independently validated complete source obligations")
        relative = row.get("json")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            _fail("generated requirement view must be relative to its index")
        graph_path = (index_path.parent / relative).resolve()
        if not graph_path.is_relative_to(index_path.parent.resolve()):
            _fail("generated requirement view escapes its index")
        _, graph, _ = _artifact({"path": str(graph_path), "sha256": row.get("generated_view_sha256")},
                                 label=f"requirement view {row['sample_id']}")
        if graph.get("sample_id") != row["sample_id"] or graph.get("semantic_complete") is not True:
            _fail("requirement view differs from its indexed sample or has pending semantics")
        validate_requirement_graph(graph, expected=expected_by_sample[row["sample_id"]]
                                   if expected_by_sample is not None else None)
        if any(not is_deferred_input_scope(row["sample_id"], issue) for issue in graph.get("unresolved", [])):
            _fail("only the five retained input-scope declarations may remain unresolved")
        coverage = graph.get("source_obligation_coverage", {})
        deferred_ids = {ident for issue in graph.get("unresolved", [])
                        if is_deferred_input_scope(row["sample_id"], issue)
                        for ident in issue.get("source_obligation_ids", [])}
        if not isinstance(coverage, dict) or coverage.get("source_complete") is not True:
            _fail("requirement view has no complete independent source inventory")
        pending = {entry["obligation_id"] for entry in coverage.get("dispositions", [])
                   if entry.get("status") == "pending"}
        if pending - deferred_ids or coverage.get("semantic_complete") is not True and not pending:
            _fail("requirement view retains unexplained software obligations")
    evidence = gate.get("evidence", {})
    if not isinstance(evidence, dict):
        _fail("independent oracle, mutation and comparison artifacts are required")
    for purpose, required_categories in _EVIDENCE_CATEGORIES.items():
        _, record, _ = _artifact(evidence.get(purpose), label=f"independent {purpose} evidence")
        if (record.get("schema") != "moparse-independent-validation/1" or record.get("purpose") != purpose
                or record.get("status") != "passed" or record.get("software_id") != software_id
                or record.get("requirement_index_sha256") != index_digest
                or record.get("oracle_origin") != "hand_authored_source_independent"
                or record.get("known_defects") != []):
            _fail(f"independent {purpose} evidence is stale, self-derived or contains known defects")
        cases = record.get("cases")
        if not isinstance(cases, list) or not cases or any(not isinstance(case, dict) for case in cases):
            _fail(f"independent {purpose} evidence requires actual case observations")
        case_ids = [case.get("case_id") for case in cases]
        if any(not isinstance(ident, str) or not ident for ident in case_ids) or len(set(case_ids)) != len(case_ids):
            _fail(f"independent {purpose} evidence requires unique case identities")
        categories = set()
        for case in cases:
            if (not case.get("input") or not isinstance(case.get("category"), str)
                    or "expected" not in case or "observed" not in case
                    or _digest(case["expected"]) != _digest(case["observed"])):
                _fail(f"independent {purpose} evidence contains an unexecuted or failed case")
            categories.add(case.get("category"))
        if not required_categories <= categories:
            _fail(f"independent {purpose} evidence is missing required semantic counterexamples")
    return index


def replay_gate_receipt(validation: dict[str, Any], software_id: str, *,
                        scope: set[str] | None = None,
                        expected_by_sample: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Create a source-free receipt only after host-side artifact validation."""
    index = validate_expected_structure_gate(validation, software_id, scope=scope,
                                             expected_by_sample=expected_by_sample)
    gate = validation["expected_structure_gate"]
    material = {"schema": RECEIPT_SCHEMA, "software_id": software_id,
                "requirement_index_sha256": gate["requirement_index"]["sha256"],
                "evidence_sha256": {purpose: gate["evidence"][purpose]["sha256"] for purpose in _EVIDENCE_CATEGORIES},
                "sample_ids": sorted(row["sample_id"] for row in index["records"])}
    return {**material, "receipt_sha256": _digest(material)}


def validate_replay_gate_receipt(receipt: Any, software_id: str, *, scope: set[str] | None = None) -> None:
    """Check the host-validated receipt without giving a candidate any answers."""
    if not isinstance(receipt, dict) or set(receipt) != {
            "schema", "software_id", "requirement_index_sha256", "evidence_sha256", "sample_ids", "receipt_sha256"}:
        _fail("candidate replay requires a complete source-free host receipt")
    material = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if (receipt["schema"] != RECEIPT_SCHEMA or receipt["software_id"] != software_id
            or not isinstance(software_id, str) or not software_id.strip()
            or receipt["receipt_sha256"] != _digest(material)):
        _fail("candidate replay receipt differs from its host-validated identity")
    digests = receipt["evidence_sha256"]
    ids = receipt["sample_ids"]
    if (not isinstance(digests, dict) or set(digests) != set(_EVIDENCE_CATEGORIES)
            or any(not isinstance(value, str) or not _DIGEST.fullmatch(value)
                   for value in [receipt["requirement_index_sha256"], *digests.values()])
            or not isinstance(ids, list) or not ids
            or any(not isinstance(ident, str) or not ident for ident in ids)
            or ids != sorted(set(ids)) or scope is not None and set(ids) != set(scope)):
        _fail("candidate replay receipt lacks current evidence identities or complete sample scope")
