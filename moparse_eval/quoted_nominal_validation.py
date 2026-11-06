"""Validate quoted roles against literal source cuts and their scope edges."""

from __future__ import annotations

from .quoted_nominal import quoted_role_evidence, scan_quoted_nominals


def validate_quoted_nominals(graph, fields, literal):
    edges = [*graph["relations"], *graph.get("operand_relations", [])]
    for field in fields:
        expected = []
        for role in ("subject", "object"):
            # A logical group's object is its whole proposition. Its quoted
            # object roles belong to the independently validated operands.
            if role == "object" and field.get("role") == "logical_group":
                continue
            value = field.get(role, "")
            origin = field.get(role + "_source")
            if not value or not origin:
                continue
            printed = literal(origin)
            if printed is None:
                raise ValueError("quoted nominal role has no literal source")
            scan = scan_quoted_nominals(printed, origin)
            if not scan["matched"] and not scan_quoted_nominals(value, origin)["matched"]:
                continue
            if printed != value:
                raise ValueError("quoted nominal role differs from its literal source")
            proof, reason = quoted_role_evidence(printed, 0, len(printed), scan, role=role)
            if scan["errors"] or reason:
                raise ValueError("interpreted quoted nominal has unresolved source syntax")
            expected.extend(proof)
        if field.get("quoted_nominals", []) != expected:
            raise ValueError("quoted nominal proof omits or changes its actual source role")
        if expected and "quoted_nominal_scope" not in graph["required_matcher_features"]:
            raise ValueError("quoted nominal comparison capability is not declared")
        for proof in expected:
            if not any(edge.get("type") == "narrative_quoted_nominal_scope"
                       and edge.get("binding_evidence", {}).get("quoted_nominal") == proof
                       and edge.get("binding_evidence", {}).get("statement_source") == field["source"]
                       and edge.get("right", {}).get("subject") == field["subject"]
                       and edge.get("right", {}).get("attribute") == field["attribute"]
                       for edge in edges):
                raise ValueError("quoted nominal lacks its source-bound scope relation")
