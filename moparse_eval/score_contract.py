"""Publication invariants for field retrieval, independent of locator control flow."""

from __future__ import annotations

from typing import Any


def require_retrieval_evidence(outcomes: list[dict[str, Any]]) -> None:
    """Reject missing or internally contradicted identity evidence, not outputs.

    This guard does not establish semantic correctness on its own. Independent
    syntax cases and real-output diagnosis must also validate the reader.
    """
    for row in outcomes:
        if row.get("kind") != "business_field":
            continue
        candidate = row.get("candidate", {})
        if candidate.get("reader_failure"):
            raise ValueError("known scoring reader failure must be repaired before publication")
        trace = candidate.get("localization", {})
        query = trace.get("query")
        hits = trace.get("candidates")
        if not isinstance(query, dict) or not isinstance(hits, list) or "value" in query:
            raise ValueError("business grading requires an answer-independent retrieval trace")
        wanted = {
            key: value
            for key, value in row.get("expected", {}).get("required", {}).items()
            if key not in {"note_markers", "note_texts"}
        }
        if query.get("identity") != wanted:
            raise ValueError("retrieval query omitted or changed a required business identity")
        accepted = [hit for hit in hits if hit.get("decision") == "accepted"]
        for hit in accepted:
            checks = hit.get("identity", {})
            if query.get('identity_assertions') and 'record_type' not in checks:
                raise ValueError('a type identity requires its source key binding evidence')
            if not wanted.keys() <= checks.keys() or any(
                check.get("status") != "correct" for check in checks.values()
            ):
                raise ValueError("a conflicting or unsupported business identity was admitted")
        if candidate.get("status") == "compared":
            identifier = candidate.get("native_id")
            if not identifier or not any(
                identifier in hit.get("native_ids", []) for hit in accepted
            ):
                raise ValueError("compared value is outside the identity-validated candidate set")
            if any(
                check.get("status") != "correct"
                for key, check in candidate.get("information", {}).get("qualifiers", {}).items()
                if key in wanted
            ):
                raise ValueError("scope or identity conflict was misreported as a value comparison")
