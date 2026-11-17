"""Aggregate an independently frozen Native research scope, without grading.

The existing Native-only command owns candidate reading and comparison. This
module consumes its retained four-state outcomes and never calls a comparator,
changes a formal denominator, or activates a score. T uses the existing canonical
character and S/D/I ledger; L/B use their existing requirement identities.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

LAYERS = ("T", "L", "B")
STATES = ("correct", "incorrect", "unresolved", "software_blocked")


def digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def build_common(projections, inventories, *, scoring_method=None):
    """Fix membership from source responsibility, before reading any scores.

    The continuous contract retains every original owner and source-form B.
    None selects the historical, explicitly partial research projection only.
    No pipeline, candidate value or comparison result selects membership.
    """
    from moparse_eval.document_ast_comparison import (
        document_order_requirements,
        navigation_order_requirements,
    )
    from moparse_eval.three_layer import canonical

    rows = []
    for sid, graph in projections.items():
        inventory = inventories[sid]
        coverage = graph["comparison_coverage"]
        complete = coverage['responsibility_complete'] or graph.get('continuous_coverage', {}).get('bounded_responsibility_complete') is True
        if not coverage['source_complete'] or not coverage['structure_complete'] or not complete:
            raise ValueError("reference responsibility is not independently admissible")
        owners = {layer: {} for layer in LAYERS}
        owners["T"] = {r["id"]: r for r in graph["text"]}
        owners["L"] = {r["id"]: r for r in graph["relations"]
                       if r["id"] in coverage["retained_semantic_requirements"]["L"]}
        owners["B"] = {r["id"]: r for r in graph["business"]
                       if r["id"] in coverage["retained_semantic_requirements"]["B"]}
        for i, node in enumerate(graph["source_form_requirements"]):
            owners["L"][f"L:content:{i}"] = node
            if node["role"] != "heading":
                owners["B"][f"B:content:{i}"] = node
        for node in [*document_order_requirements(graph), *navigation_order_requirements(graph)]:
            owners["L"][node["id"]] = node
        for layer in LAYERS:
            if set(owners[layer]) != set(inventory["requirement_ids"][layer]):
                raise ValueError("reference requirement inventory differs")
        cursor = 0
        for layer in LAYERS:
            for rid in inventory["requirement_ids"][layer]:
                node = owners[layer][rid]
                from moparse_eval.ast_alignment import METHOD

                if scoring_method not in (None, METHOD):
                    raise ValueError('unknown Native research method')
                excluded = scoring_method is None and layer == "B" and rid.startswith("B:content:")
                entry = {
                    "sample_id": sid, "layer": layer, "requirement_id": rid,
                    "definition_sha256": digest(node),
                    "source": node.get("source", node.get("sources")),
                    "included": not excluded,
                    "reason": "source_form_business_paraphrase_comparator_unavailable"
                    if excluded else "independently_bound_reference_and_supported_comparison_domain",
                    "exclusion_category": "software_capability" if excluded else None,
                    "weight": len(canonical(node["text"])) if layer == "T" else 1,
                }
                if layer == "T":
                    text = canonical(node["text"])
                    entry.update(canonical_text=text, canonical_interval=[0, len(text)],
                                 selection_character_interval=[cursor, cursor + len(text)])
                    cursor += len(text)
                rows.append(entry)
        if cursor != inventory["denominators"]["T"]:
            raise ValueError("canonical character responsibility differs")
    return {
        "schema": "moparse-native-common-research-set/1",
        "benchmark": "native", "scope": "S3/S4/S6", "research_only": True,
        "full_lite_score": False, "publication_authorized": False,
        "membership_inputs": "independently bound Expected projections and static comparator capabilities only",
        "candidate_results_used_for_membership": False,
        "records": rows,
        "original_denominators": {layer: sum(r["weight"] for r in rows if r["layer"] == layer) for layer in LAYERS},
        "common_denominators": {layer: sum(r["weight"] for r in rows if r["layer"] == layer and r["included"]) for layer in LAYERS},
        "excluded_denominators": {layer: sum(r["weight"] for r in rows if r["layer"] == layer and not r["included"]) for layer in LAYERS},
        "scoring_method": scoring_method,
    }


def classify(row, proof=None):
    """Attribute retained limits without turning unknown correspondence into loss.

    Native parent/order unknown is distinct from missing structure. The saved
    reader supplies no exhaustive negative parent/order proof. A generic
    software_failure flag also denotes four-state correspondence limits, so its
    actual reason must be inspected instead of counting every flag as an error.
    """
    limit = row.get("research_limitation", "")
    reason = limit or row.get("reason", "")
    if reason in {
        "existing_comparison_limit:wording_change_requires_semantic_comparison",
        "wording_change_requires_semantic_comparison",
    } or row.get("software_exception"):
        state, category = "software_blocked", "unsupported_business_expression"
    elif limit:
        state = "unresolved"
        if reason.startswith("existing_comparison_limit:"):
            category = "correspondence_not_proved"
        elif reason in {
            "no_proved_native_parent_chain_for_this_relation",
            "native_parent_or_scope_unproved_for_document_relation",
            "legal_parent_scope_not_provided_by_native_references",
            "native_arrays_or_bbox_do_not_supply_global_reading_order",
            "native_global_order_or_independent_endpoints_unproved",
            "navigation_role_or_unique_navigation_identity_unproved_in_native",
        }:
            category = "native_relation_unknown"
        else:
            category = "correspondence_not_proved"
    elif row["outcome"] == "unresolved":
        state, category = "unresolved", "correspondence_not_proved"
    elif row.get("software_failure"):
        state, category = "software_blocked", "unsupported_comparison"
    elif row["layer"] == "T" and row.get("correspondence", {}).get("status") in {"ambiguous", "unlocated"} and not row.get("correspondence", {}).get("absence_proven"):
        state, category = "unresolved", "correspondence_not_proved"
    else:
        state = row["outcome"]
        category = "independent_comparison"
    if state not in STATES:
        raise ValueError("unknown comparison outcome")
    missing = state == "incorrect" and (
        row.get("correspondence", {}).get("absence_proven") is True
        or bool(proof and proof.get("correspondence_status") == "missing"
                and proof.get("decision", {}).get("status") == "missing"
                and proof.get("decision", {}).get("reason") in {
                    "document_required_scope_empty",
                    "document_scope_exhausted_by_independent_requirements",
                })
    )
    return {"state": state, "category": category, "reason": reason,
            "candidate_missing": missing}


def summarize(records, layer):
    counts = Counter({s: 0 for s in STATES})
    edits = Counter({s: 0 for s in ("S", "D", "I")})
    trusted = 0
    missing = 0
    for row in records:
        weight = row["weight"]
        if type(weight) is not int or weight < 0:
            raise ValueError("invalid statistical weight")
        state = row["state"]
        if state not in STATES:
            raise ValueError("unknown statistical state")
        if layer == "T" and state in {"correct", "incorrect"}:
            trusted += weight
            for key in edits:
                value = row.get("edits", {}).get(key, 0)
                if type(value) is not int or value < 0:
                    raise ValueError("invalid existing character edit ledger")
                edits[key] += value
            if state == "correct" and any(row.get("edits", {}).values()):
                raise ValueError("correct literal has nonzero canonical edits")
        else:
            counts[state] += weight
        if row["candidate_missing"]:
            missing += weight if layer != "T" else row.get("edits", {}).get("D", weight)
    if layer == "T":
        # Same S+D+I debit and floor as the owning T layer, over the fixed
        # trusted character budget. No new per-character alignment is created.
        counts["correct"] = max(0, trusted - sum(edits.values()))
        counts["incorrect"] = trusted - counts["correct"]
    n = sum(row["weight"] for row in records)
    if sum(counts.values()) != n:
        raise ValueError("research denominator changed")
    resolved = counts["correct"] + counts["incorrect"]
    software = counts["software_blocked"]
    return {
        "N_common": n, **dict(counts), "candidate_missing": missing,
        "coverage": resolved / n if n else None,
        "admitted_coverage": (n - software) / n if n else None,
        "lower_bound": counts["correct"] / n if n and not software else None,
        "upper_bound": (counts["correct"] + counts["unresolved"]) / n if n and not software else None,
        "interval_withheld_for_software_block": bool(software),
        "resolved_accuracy_auxiliary": counts["correct"] / resolved if resolved else None,
        **({"trusted_character_budget": trusted, "trusted_edits": dict(edits)} if layer == "T" else {}),
    }


def aggregate(common, scores, inventories):
    """Project one executed full trace onto a frozen study set, losslessly.

    Scores arrive from trace_storage.read_score after native-evaluate execute.
    They are never mutated. Excluded requirements are retained in the detail
    ledger and in each pipeline's separate full-responsibility coverage.
    """
    from moparse_eval.ast_alignment import METHOD

    if common.get('scoring_method') == METHOD:
        return aggregate_continuous(common, scores, inventories)
    if common.get("candidate_results_used_for_membership") is not False:
        raise ValueError("common set was not independently constructed")
    owners = {}
    for r in common["records"]:
        key = (r["sample_id"], r["layer"], r["requirement_id"])
        if key in owners:
            raise ValueError("duplicate frozen requirement")
        owners[key] = r
    expected_keys = {(sid, f"P{p:02}") for sid in inventories for p in range(1, 9)}
    if set(scores) != expected_keys:
        raise ValueError("exactly all 24 Native combinations are required")
    details = []
    for (sid, pipeline), score in scores.items():
        if score["sample_id"] != sid or score.get("pipeline") != pipeline or score.get("benchmark") != "native":
            raise ValueError("Native comparison identity differs")
        seen = {layer: set() for layer in LAYERS}
        proofs = score.get("document_comparison", {}).get("decision", {}).get("proof", {}).get("rows", [])
        for outcome in score["outcomes"]:
            layer, rid = outcome["layer"], outcome["id"]
            if rid in seen[layer]:
                raise ValueError("duplicate executed requirement")
            seen[layer].add(rid)
            owner = owners[(sid, layer, rid)]
            i = outcome.get("document_ast_comparison")
            proof = proofs[i] if type(i) is int and i < len(proofs) else None
            decision = classify(outcome, proof)
            details.append({
                "sample_id": sid, "pipeline": pipeline, "layer": layer,
                "requirement_id": rid, "weight": owner["weight"],
                "included": owner["included"], **decision,
                "raw_outcome": outcome.get("comparator_outcome", outcome["outcome"]),
                "retained_outcome": outcome["outcome"],
                "edits": outcome.get("edits", {}),
                "strict_edits": outcome.get("strict_edits", {}),
                "source": owner["source"],
            })
        for layer in LAYERS:
            if seen[layer] != set(inventories[sid]["requirement_ids"][layer]) or score["layers"][layer]["denominator"] != inventories[sid]["denominators"][layer]:
                raise ValueError("original comparison responsibility changed")
    rows = []
    by_selection = []
    for p in range(1, 9):
        pipeline = f"P{p:02}"
        for layer in LAYERS:
            own = [r for r in details if r["pipeline"] == pipeline and r["layer"] == layer]
            admitted = [r for r in own if r["included"]]
            stats = summarize(admitted, layer)
            if stats["N_common"] != common["common_denominators"][layer]:
                raise ValueError("pipeline-dependent common denominator")
            independent = summarize(own, layer)
            independent["N_original"] = independent.pop("N_common")
            rows.append({"pipeline": pipeline, "layer": layer, **stats,
                         "excluded": sum(r["weight"] for r in own if not r["included"]),
                         "independent_full_responsibility": independent})
            for sid in inventories:
                selected = [r for r in admitted if r["sample_id"] == sid]
                by_selection.append({"pipeline": pipeline, "sample_id": sid, "layer": layer,
                                     **summarize(selected, layer)})
    return {"benchmark": "native", "scope": "S3/S4/S6", "research_only": True,
            "full_lite_score": False, "publication_authorized": False,
            "common_set_content_sha256": digest(common), "combinations": 24,
            "rows": rows, "by_selection": by_selection, "requirement_records": details,
            "total_score": None, "ranking": None}


def aggregate_continuous(common, scores, inventories):
    """Keep every original requirement and credit; never rank or activate it."""
    from moparse_eval.ast_alignment import METHOD
    from moparse_eval.layer_aggregation import continuous_aggregation_record, summarize_layers

    if common['common_denominators'] != common['original_denominators'] or any(not r['included'] for r in common['records']):
        raise ValueError('continuous research cannot exclude source-form responsibility')
    expected = {(sid, f'P{p:02}') for sid in inventories for p in range(1, 9)}
    if set(scores) != expected:
        raise ValueError('exactly all declared Native combinations are required')
    rows, selections, detail = [], [], []
    by_pipeline = {f'P{p:02}': [] for p in range(1, 9)}
    for (sid, pipeline), score in scores.items():
        if score.get('scoring_method') != METHOD or score.get('benchmark') != 'native' or score['sample_id'] != sid or score['pipeline'] != pipeline:
            raise ValueError('continuous Native comparison identity differs')
        indices = {(r['layer'], r['id']): i for i, r in enumerate(score['outcomes'])}
        for layer in LAYERS:
            own = [r for r in score['outcomes'] if r['layer'] == layer]
            if sorted(r['id'] for r in own) != sorted(inventories[sid]['requirement_ids'][layer]) or score['layers'][layer]['denominator'] != inventories[sid]['denominators'][layer]:
                raise ValueError('original continuous responsibility changed')
            for item in own:
                detail.append({'sample_id': sid, 'pipeline': pipeline,
                               **{k: item.get(k) for k in ('id', 'layer', 'role', 'credit', 'outcome', 'reason', 'edits')},
                               'full_evidence': score.get('saved_score_reference'),
                               'outcome_index': indices[layer, item['id']]})
        selections.append({'sample_id': sid, 'pipeline': pipeline,
                           'layers': score['layers'], 'score': score['score'],
                           'blockers': score['blockers']})
        by_pipeline[pipeline].append(continuous_aggregation_record(score))
    for pipeline, records in by_pipeline.items():
        rows.append({'pipeline': pipeline, **summarize_layers(records)})
    return {'benchmark': 'native', 'scope': 'S1-S9' if len(inventories) == 9 else 'S3/S4/S6', 'scoring_method': METHOD,
            'research_only': True, 'full_lite_score': False, 'publication_authorized': False,
            'original_denominators': common['original_denominators'],
            'common_denominators': common['common_denominators'], 'excluded_denominators': common['excluded_denominators'],
            'combinations': len(expected), 'rows': rows, 'by_selection': selections,
            'requirement_records': detail, 'ranking': None}
