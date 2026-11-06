"""Bind recursive statement decisions to existing B/L targets without new votes."""

from __future__ import annotations

import copy
import json
import re

from .equivalence import decide_equivalence
from .represented_feature_comparison import REPRESENTED_INPUT_KEYS, represented_feature_checks
from .requirement_ast import (
    AST_FEATURE_COMPARATORS,
    compare_feature_ast,
    compare_requirement_ast,
    compare_requirement_ast_collections,
)


def _owns(outer, inner):
    if not isinstance(outer, dict) or not isinstance(inner, dict):
        return False
    if outer.get("path") != inner.get("path"):
        return False
    if any(outer.get(key) != inner.get(key) for key in ("cell", "block") if key in outer or key in inner):
        return False
    bounds, local = outer.get("text_span"), inner.get("text_span")
    lines, own_lines = outer.get("lines"), inner.get("lines")
    if lines and own_lines and not lines[0] <= own_lines[0] <= own_lines[1] <= lines[1]:
        return False
    return bool(bounds and local and bounds[0] <= local[0] <= local[1] <= bounds[1])


def _has_unresolved(decision):
    return decision.get("unresolved", False) or any(
        _has_unresolved(child) for child in decision.get("proof", {}).get("children", []))


def _main_assertions(node):
    if not isinstance(node, dict):
        return []
    if node.get("kind") == "proposition":
        return [node]
    if node.get("kind") == "coordination":
        return [leaf for child in node.get("children", []) for leaf in _main_assertions(child)]
    if node.get("kind") == "logical_group":
        return _main_assertions(node.get("tree"))
    return _main_assertions(node.get("child"))


def _role_key(node):
    origins = [node.get(key) for key in ("subject_source", "predicate_source", "object_source")]
    return json.dumps(origins, sort_keys=True, ensure_ascii=False) if all(isinstance(origin, dict) for origin in origins) else None


def _walk_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_nodes(child)


def _tree_complete(graph, tree):
    """A local interpretation gap cannot be repaired by an equal subtree."""
    source = tree.get("source", {})
    return not any(_owns(source, issue.get("source", {})) or _owns(issue.get("source", {}), source)
                   for issue in graph.get("blockers", []))


def _business_responsibility(row, tree, own_tree, context):
    """Transfer one complete assertion after value-independent capacity binding."""
    target, located = row["expected"], row.get("actual", [])
    trace = row.get("retrieval", {})
    if (row.get("software_failure") or len(located) != 1
            or trace.get("capacity", {}).get("required_occurrences") != 1
            or located[0]["id"] not in trace.get("accepted", [])
            or row.get("record_comparison", {}).get("equal", True) is not True):
        return None
    candidate = located[0]
    if not decide_equivalence(target.get("identity_facets", {}), candidate.get("identity_facets", {}),
                              "structure", context=context)["equivalent"]:
        return None
    # Logical OR is one existing business target; other narrative targets own
    # exactly one assertion, never the conditions or purposes around it.
    if target.get("role") == candidate.get("role") == "logical_group":
        if not ((_owns(tree.get("source", {}), target.get("source", {}))
                 or _owns(target.get("source", {}), tree.get("source", {})))
                and (_owns(own_tree.get("source", {}), candidate.get("source", {}))
                     or _owns(candidate.get("source", {}), own_tree.get("source", {})))
                and target.get("logic", {}).get("tree") == tree
                and candidate.get("logic", {}).get("tree") == own_tree):
            return None
    elif target.get("role") == candidate.get("role") == "description":
        leaves = [leaf for leaf in _main_assertions(tree) if _role_key(leaf) == _role_key(target)]
        own_leaves = [leaf for leaf in _main_assertions(own_tree) if _role_key(leaf) == _role_key(candidate)]
        if len(leaves) != 1 or len(own_leaves) != 1:
            return None
        for fact, leaf in ((target, leaves[0]), (candidate, own_leaves[0])):
            if (fact.get("value") != leaf.get("object") or fact.get("object") != leaf.get("object")
                    or fact.get("attribute") != leaf.get("attribute") or fact.get("subject") != leaf.get("subject")):
                return None
        if not compare_requirement_ast(leaves[0], own_leaves[0], context=context)["equivalent"]:
            return None
    else:
        return None  # Scalars keep the exact quantity/value contract.
    if not decide_equivalence(target.get("qualifiers", {}), candidate.get("qualifiers", {}),
                              "structure", context=context)["equivalent"]:
        return None
    return {"owner": "complete_source_bound_statement", "required_id": target["id"],
            "actual_id": candidate["id"], "identity_before_value": True,
            "capacity": copy.deepcopy(trace["capacity"])}


def _relation_node(edge, graph, tree, side, resolve):
    """Bind only the two represented nominal edge kinds to their complete AST."""
    from .source_obligations import validate_relation_binding

    fact = next((fact for fact in graph.get("business", []) if fact["id"] == edge.get("fact_id")), None)
    if fact is None or not validate_relation_binding(None, fact, edge)["equivalent"]:
        return None
    leaves = [leaf for leaf in _main_assertions(tree) if _role_key(leaf) == _role_key(fact)]
    if len(leaves) != 1:
        return None
    binding, left = edge.get("binding_evidence", {}), edge.get("left", {})
    nodes = list(_walk_nodes(leaves[0]))
    if edge["type"] == "narrative_prepositional_attachment":
        matches = [node for node in nodes if node.get("kind") == "prepositional_complement"
                   and node.get("preposition_source") == binding.get("preposition_source")
                   and node.get("head_source") == binding.get("head_source")
                   and node.get("complement_source") == binding.get("complement_source")
                   and node.get("preposition") == left.get("preposition")
                   and node.get("attachment") == left.get("attachment")
                   and node.get("semantic_role") == left.get("semantic_role")
                   and edge.get("source") == binding.get("preposition_source")
                   and resolve(side, binding.get("complement_source", {})) == left.get("complement")]
    elif edge["type"] == "narrative_nominal_coordination_scope":
        matches = [node for node in nodes if node.get("kind") == "coordination"
                   and node == binding.get("coordination_logic")
                   and edge.get("source") in node.get("operator_sources", [])
                   and left == {"operator": node.get("operator"), "mode": node.get("mode"),
                                "member_count": len(node.get("children", []))}]
    else:
        return None
    return matches[0] if len(matches) == 1 else None


def _relation_responsibility(row, required, actual, tree, own_tree, context, used, resolve):
    target = row["expected"]
    node = _relation_node(target, required, tree, "required", resolve)
    if node is None:
        return None
    hits = []
    for candidate in actual.get("relations", []):
        if candidate["type"] != target["type"] or candidate["id"] in used:
            continue
        own_node = _relation_node(candidate, actual, own_tree, "actual", resolve)
        if own_node is None:
            continue
        # Establish the assertion owner and scope independently of its value.
        if not decide_equivalence(target["right"], candidate["right"], "structure", context=context)["equivalent"]:
            continue
        # Preposition/attachment name the relation slot. Its complement is
        # the answer and cannot select one of several eligible occurrences.
        if target["type"] == "narrative_prepositional_attachment":
            identity = ("preposition", "semantic_role", "attachment")
            if any(target["left"].get(key) != candidate["left"].get(key) for key in identity):
                continue
        hits.append((candidate, own_node))
    if len(hits) != 1:
        return None
    candidate, own_node = hits[0]
    decision = compare_requirement_ast(node, own_node, context=context)
    if not decision["equivalent"]:
        return None
    used.add(candidate["id"])
    return {"owner": "complete_source_bound_relation", "required_id": target["id"],
            "actual_id": candidate["id"], "identity_before_value": True,
            "capacity": 1, "decision": decision}


def _affected_assertions(tree, decision):
    """Bind each failed path to its grammatical owning assertion(s)."""
    children = decision.get("proof", {}).get("children", [])
    if children:
        return [leaf for child in children for leaf in _affected_assertions(tree, child)]
    if decision.get("status") not in {"conflict", "missing"}:
        return []
    node, chain = tree, []
    for field, index in re.findall(r"\.([A-Za-z_][A-Za-z_0-9]*)|\[(\d+)\]", decision.get("path", "")):
        token = field if field else int(index)
        chain.append((node, token))
        if isinstance(node, dict) and isinstance(token, str) and token in node:
            node = node[token]
        elif isinstance(node, list) and isinstance(token, int) and token < len(node):
            node = node[token]
        else:
            break
    # A condition/restriction/purpose operand qualifies its enclosing main
    # assertion. Its words do not become independent B requirements.
    for owner, field in chain:
        if (isinstance(owner, dict) and owner.get("kind") in {
                "conditions", "condition", "exception", "relative", "restrictive_relative", "reporting",
                "purpose_scope", "controlled_infinitive_scope"} and field != "child"):
            return _main_assertions(owner.get("child"))
    for owner in [node, *[owner for owner, _field in reversed(chain)]]:
        if isinstance(owner, dict) and owner.get("kind") == "proposition":
            return [owner]
    for owner in [node, *[owner for owner, _field in reversed(chain)]]:
        if isinstance(owner, dict) and owner.get("kind"):
            leaves = _main_assertions(owner)
            if leaves:
                return leaves
    return _main_assertions(tree)


def _target_affected(target, layer, affected, required):
    keys = {_role_key(leaf) for leaf in affected} - {None}
    if layer == "B":
        return target.get("role") == "logical_group" or _role_key(target) in keys
    if target.get("type") in {"field_binding", "qualifier_scope"}:
        # These atomic edges already compare their own complete endpoints and
        # qualifiers. A changed enclosing operator cannot erase a separately
        # correct field/neighbor link; its own scope edge carries the loss.
        return False
    fact = next((fact for fact in required.get("business", []) if fact["id"] == target.get("fact_id")), None)
    if fact is not None:
        return fact.get("role") == "logical_group" or _role_key(fact) in keys
    binding = target.get("binding_evidence", {})
    if _role_key(binding) in keys or any(_role_key(member) in keys for member in binding.get("members", [])):
        return True
    if target.get("type") in {"condition_scope", "exception_scope", "purpose_scope"}:
        endpoint = target.get("right", {})
        return any(endpoint.get("subject") == leaf.get("subject")
                   and endpoint.get("attribute", endpoint.get("action")) == leaf.get("attribute") for leaf in affected)
    return False


def _fact_ast_consistency(graph, side, resolve):
    """Audit own fact roles/qualifiers against original text and AST owners."""
    from .narrative_requirements import _Reader
    from .prose_requirements import _subject
    from .requirement_graph import _semantic_token_matches

    expectations = {}

    def walk(node, qualifiers=None):
        if not isinstance(node, dict):
            return
        q = copy.deepcopy(qualifiers or {"polarity": "positive"})
        kind = node.get("kind")
        if kind == "modality":
            q.update(modality=node["operator"], modal_polarity=node["polarity"])
        elif kind == "negation":
            q["polarity"] = "negative"
        elif kind == "active_aspect":
            q.update(aspect=node["aspect"], tense=node["tense"])
        elif kind == "temporal_scope":
            q.update(node.get("qualifiers", {}))
        elif kind == "conditions":
            q["conditions"] = [{"operator": binding["operator"], "operand": _Reader.summary(binding["operand"])}
                               for binding in node.get("bindings", [])]
        elif kind == "relative":
            q["subject_restriction"] = _Reader.summary(node["restriction"])
        elif kind == "reporting":
            q.setdefault("reporting", []).append({"subject": node["speaker"], "attribute": node["attribute"],
                                                  "polarity": node["polarity"], "tense": node["tense"]})
        if kind == "proposition":
            if node.get("tense") is not None:
                q["tense"] = node["tense"]
            expectations[_role_key(node)] = q
        elif kind == "coordination":
            for child in node.get("children", []):
                walk(child, q)
        elif kind == "logical_group":
            walk(node.get("tree"), q)
        else:
            walk(node.get("child"), q)

    for tree in graph.get("logical_statements", []):
        walk(tree)
    errors = []
    for fact in graph.get("business", []):
        if not fact.get("predicate"):
            continue
        value_literal = resolve(side, fact.get("value_source", {}))
        if fact.get("role") == "description" and value_literal != fact.get("value"):
            errors.append({"fact_id": fact["id"], "dimension": "value", "claimed": fact.get("value"),
                           "source_literal": value_literal, "status": "conflict"})
        for name in ("subject", "predicate", "object"):
            origin = fact.get(name + "_source")
            if not isinstance(origin, dict):
                continue
            raw = resolve(side, origin)
            value = fact.get(name)
            if raw != value and not (name == "subject" and isinstance(raw, str) and _subject(raw) == value):
                errors.append({"fact_id": fact["id"], "dimension": name, "source": copy.deepcopy(origin),
                               "claimed": value, "source_literal": raw, "status": "conflict"})
        q = fact.get("qualifiers", {})
        sources = fact.get("qualifier_sources", {})
        for dimension in ("modality", "polarity", "modal_polarity", "tense", "aspect", "condition_operator", "exception_operator"):
            if dimension not in q:
                continue
            origin = sources.get(dimension) or fact.get("qualifier_provenance", {}).get(dimension, {}).get("source")
            if origin is None and q[dimension] == "negative" and dimension in {"polarity", "modal_polarity"}:
                origin = sources.get("modality")
            if origin is None:
                continue
            raw = resolve(side, origin)
            if not isinstance(raw, str) or not _semantic_token_matches(dimension, q[dimension], raw):
                errors.append({"fact_id": fact["id"], "dimension": dimension, "source": copy.deepcopy(origin),
                               "claimed": q[dimension], "source_literal": raw, "status": "conflict"})
        expected = expectations.get(_role_key(fact), {})
        for dimension, value in expected.items():
            if dimension == "conditions" and "conditions" not in q and ({"condition", "exception"} & q.keys()):
                continue  # The finite modal reader retains its literal operand.
            actual = q.get(dimension, "positive" if dimension in {"polarity", "modal_polarity"} else None)
            # The finite modal reader represents CANNOT as negative polarity;
            # the full AST separately retains the negative modal operator.
            legacy_cannot = (fact.get("logic", {}).get("kind") == "modal_assertion"
                and resolve(side, sources.get("modality", {})) == "cannot" and q.get("polarity") == "negative")
            if legacy_cannot and dimension in {"polarity", "modal_polarity"}:
                continue
            if actual != value:
                errors.append({"fact_id": fact["id"], "dimension": dimension, "claimed": actual,
                               "ast_owned": copy.deepcopy(value), "status": "missing" if actual is None else "conflict"})
    return errors


def compare_semantic_layers(required, actual, rows, layers, *, canonicalize, scope_options):
    """Assign existing votes to complete source-bound comparison owners.

    Scalar, identity, scope and capacity checks remain independent prerequisites.
    A complete AST may resolve a surface-only mismatch for its own requirement.
    """
    from .requirement_graph import _semantic_literal

    banks = {}
    for side, graph in (("required", required), ("actual", actual)):
        projection = graph.get("text_projection", {})
        banks[side] = [*projection.get("source_fragments", []), *projection.get("source_cells", [])]

    def resolve(side, source):
        return _semantic_literal(banks[side], source)

    context = {"canonicalize": canonicalize, "source_resolver": resolve, **scope_options}
    blockers, unsupported, checks = [], {}, {}
    for side, graph, own in (("expected", required, "required"), ("candidate", actual, "actual")):
        inconsistent = _fact_ast_consistency(graph, own, resolve)
        if inconsistent:
            blockers.append({"side": side, "reason": "semantic_fact_ast_evidence_inconsistent", "layers": ["B", "L"],
                             "evidence": inconsistent})
    for side, graph in (("expected", required), ("candidate", actual)):
        trees = graph.get("logical_statements", [])
        missing_features = []
        resolver_side = "required" if side == "expected" else "actual"
        represented = represented_feature_checks(graph, lambda source: resolve(resolver_side, source))
        checks[side] = represented["checks"]
        features = set(graph.get("required_matcher_features", [])) | set(represented["features"])
        for feature in sorted(features - {"finite_tense"}):
            if feature in represented["checks"]:
                if not represented["checks"][feature]["equivalent"]:
                    missing_features.append(feature)
                continue
            if feature not in AST_FEATURE_COMPARATORS or not trees:
                missing_features.append(feature)
                continue
            # This is a runtime availability check, not the independent
            # oracle that establishes a comparator's semantic correctness.
            decision = compare_feature_ast(feature, trees, trees, context={
                "canonicalize": canonicalize,
                "source_resolver": lambda _side, source, own=resolver_side: resolve(own, source)})
            checks[side][feature] = decision
            if not decision["equivalent"]:
                missing_features.append(feature)
        unsupported[side] = missing_features
        if missing_features:
            blockers.append({"side": side, "reason": "narrative_comparison_features_not_validated", "layers": ["B", "L"],
                             "required_features": missing_features})

    decisions = {}
    used_relations = {row["actual"]["id"] for row in rows
                      if row["layer"] == "L" and row.get("actual") is not None}
    trees = required.get("logical_statements", [])
    if trees:
        for row in rows:
            if row["layer"] in {"B", "L"}:
                row["flat_outcome"] = row["outcome"]
        for layer in ("B", "L"):
            result = compare_requirement_ast_collections(trees, actual.get("logical_statements", []),
                                                         context={**context, "layer": layer})
            decisions[layer] = result
            if _has_unresolved(result) or any(_has_unresolved(item["decision"]) for item in result["proof"]["rows"]):
                blockers.append({"side": "comparison", "reason": "narrative_ast_comparison_unresolved", "layers": [layer],
                                 "decision": copy.deepcopy(result)})
            for item in result["proof"]["rows"]:
                decision = item["decision"]
                tree = trees[item["required_index"]]
                affected = _affected_assertions(tree, decision)
                for row in rows:
                    if row["layer"] != layer:
                        continue
                    target = row["expected"]
                    origin = target.get("binding_evidence", {}).get("statement_source",
                        target.get("statement_source", target.get("source", {})))
                    if not (_owns(tree.get("source", {}), origin) or _owns(origin, tree.get("source", {}))):
                        continue
                    row.setdefault("ast_comparisons", []).append(copy.deepcopy(item))
                    if decision["status"] in {"conflict", "missing"} and _target_affected(target, layer, affected, required):
                        row.update(outcome="incorrect", semantic_comparison_status=decision["status"])
                    elif decision["equivalent"] and not blockers:
                        own_tree = actual.get("logical_statements", [])[item["actual_index"]]
                        if not (_tree_complete(required, tree) and _tree_complete(actual, own_tree)):
                            continue
                        responsibility = None
                        if layer == "B":
                            responsibility = _business_responsibility(row, tree, own_tree, context)
                        elif row["outcome"] != "correct":
                            responsibility = _relation_responsibility(
                                row, required, actual, tree, own_tree, context, used_relations, resolve)
                        if responsibility is not None:
                            row.update(outcome="correct", semantic_comparison_status="equivalent",
                                       semantic_responsibility=responsibility)
            layers[layer]["numerator"] = sum(row["outcome"] == "correct" for row in rows if row["layer"] == layer)
            denominator = layers[layer]["denominator"]
            layers[layer]["score"] = 100 * layers[layer]["numerator"] / denominator if denominator else None
    return {"decisions": decisions, "feature_checks": checks, "unsupported_features": unsupported,
            "blockers": blockers, "denominators_changed": False,
            "inputs": {side: {key: copy.deepcopy(graph.get(key, [] if key != "text_projection" else {}))
                              for key in dict.fromkeys(("logical_statements", "required_matcher_features", "text_projection", "business", "relations", "blockers", *REPRESENTED_INPUT_KEYS))}
                       for side, graph in (("required", required), ("actual", actual))}}
