"""Bind interpreted statements to their own source-defined enumerations."""

from __future__ import annotations

import copy

from .enumeration_context import (
    enumeration_declaration,
    enumeration_membership,
    plan_enumeration_scopes,
)
from .equivalence import decide_equivalence


def owns_source(outer, inner):
    if outer.get("path") != inner.get("path") or outer.get("cell") != inner.get("cell"):
        return False
    for key in ("block", "block_lines"):
        if key in outer and key in inner and outer[key] != inner[key]:
            return False
    if outer.get("lines") and inner.get("lines"):
        a, b = outer["lines"]
        c, d = inner["lines"]
        if not a <= c <= d <= b:
            return False
    if outer.get("text_span") and inner.get("text_span"):
        a, b = outer["text_span"]
        c, d = inner["text_span"]
        return a <= c <= d <= b
    return True


def plan_from_syntax(syntax):
    """Keep original item boundaries even when a field reader made fragments."""
    blocks, seen = [], set()
    for index, item in enumerate(syntax):
        if item["kind"] == "field_body":
            continue
        evidence = item.get("syntax_evidence", {})
        source = evidence.get("item_source", item["source"])
        key = repr((source, evidence.get("list_stream")))
        if key in seen:
            continue
        seen.add(key)
        blocks.append({"id": f"syntax:{index}", "text": evidence.get("item_text", item["text"]),
            "kind": evidence.get("kind", item["kind"]), "source": copy.deepcopy(source),
            "scope": copy.deepcopy(item.get("scope", [])), "parents": copy.deepcopy(item.get("parents", [])),
            "parent_evidence": copy.deepcopy(item.get("parent_evidence", [])),
            "has_children": evidence.get("has_children", item["kind"] == "parent_label"),
            "list_span": copy.deepcopy(evidence.get("list_span")), "list_stream": evidence.get("list_stream"),
            "list_lines": copy.deepcopy(evidence.get("list_lines"))})
    return plan_enumeration_scopes(blocks)


def member_for_source(plan, source):
    matches = [(context, member) for context in plan["contexts"] for member in context["members"]
               if owns_source(member["source"], source)]
    return matches[0] if len(matches) == 1 else None


def inherit_omitted_subject(result, binding):
    """Only replace an absent subject slot, never a printed child actor."""
    if not binding:
        return
    context, member = binding
    inherited = member["member_context"]
    if (context['declaration'].get('role_contract') != 'printed_untimed_person_collection'
            and any(not fact.get('subject') and not fact.get('subject_source') for fact in result.get('facts', []))):
        def defer_actor():
            result.setdefault('blockers', []).append({'kind': 'enumeration_binding',
                'reason': 'enumeration_member_actor_control_unresolved', 'layers': ['B', 'L'],
                'text': member['text'], 'source': copy.deepcopy(member['source'])})
            result['complete'] = result['semantic_complete'] = False

        if result.get('blockers') or result.get('pending_requirements'):
            defer_actor()
            return
        whole = result
        if result.get('raw_text') != member.get('text'):
            from .proposition_requirements import read_propositions

            whole = read_propositions(member['text'], member['source'], subject=inherited['subject'])
        if not whole.get('complete') or whole.get('blockers'):
            defer_actor()
            return
        # A collection's owner does not replace a participant introduced in
        # the member itself. Local clause control needs its own parser proof.
        if any(fact.get('subject') and fact.get('subject_source', {}).get('text_span', [0, 0])[0]
               < fact.get('subject_source', {}).get('text_span', [0, 0])[1]
               for fact in whole.get('facts', [])):
            defer_actor()
            return
    for fact in result.get("facts", []):
        origin = fact.get("subject_source") or {}
        bounds = origin.get("text_span")
        if not fact.get('subject') and not origin and context['declaration'].get('role_contract') != 'printed_untimed_person_collection':
            controller = copy.deepcopy(inherited['subject_source'])
            proof = {'kind': 'enumeration_subject', 'controller': inherited['subject'], 'controller_source': controller,
                     'introduction_source': copy.deepcopy(context['source']), 'member_source': copy.deepcopy(member['source'])}
            fact.update(subject=inherited['subject'], subject_source=controller, subject_binding_evidence=proof)

            def bind_tree(value, fact=fact, controller=controller, proof=proof):
                if isinstance(value, dict):
                    if (value.get('kind') == 'proposition' and not value.get('subject')
                            and value.get('predicate_source') == fact.get('predicate_source')
                            and value.get('object_source') == fact.get('object_source')):
                        value.update(subject=inherited['subject'], subject_source=copy.deepcopy(controller),
                                     subject_binding_evidence=copy.deepcopy(proof), subject_phrase=None)
                    for child in value.values():
                        bind_tree(child)
                elif isinstance(value, list):
                    for child in value:
                        bind_tree(child)
            bind_tree(result.get('logic', []))
            for edge in result.get('relations', []):
                if edge.get('fact_id') != fact.get('id'):
                    continue
                for end in ('left', 'right'):
                    if isinstance(edge.get(end), dict) and 'subject' in edge[end] and not edge[end]['subject']:
                        edge[end]['subject'] = inherited['subject']
                if 'subject_source' in edge.get('binding_evidence', {}):
                    edge['binding_evidence']['subject_source'] = copy.deepcopy(controller)
            continue
        if bounds and bounds[0] == bounds[1] and fact["subject"] == inherited["subject"]:
            fact["subject_source"] = copy.deepcopy(inherited["subject_source"])
            # Role sources are part of the same source-bound interpretation.
            # Moving the absent actor slot to its printed introduction must
            # also bind the edge to that actor, rather than leaving a phantom
            # empty source behind in the otherwise complete field relation.
            def rebind(value, original=origin):
                if isinstance(value, dict):
                    if value.get("subject_source") == original:
                        value["subject_source"] = copy.deepcopy(inherited["subject_source"])
                    for child in value.values():
                        rebind(child)
                elif isinstance(value, list):
                    for child in value:
                        rebind(child)

            rebind(result.get("relations", []))


def _issue(reason, context, member=None, *, layers=("L",), **proof):
    item = member or context["declaration"]["introduction"]
    return {"kind": "enumeration_binding", "reason": reason, "source": copy.deepcopy(item["source"]),
            "text": item["text"], "layers": list(layers), **copy.deepcopy(proof)}


def bind_interpreted_members(data, plan):
    """Retain parent roles, actual child actors and every unresolved member."""
    data["enumeration_contexts"] = copy.deepcopy(plan["contexts"])
    data["required_matcher_features"] = sorted(set(data.get("required_matcher_features", [])) |
        ({"enumeration_context_scope"} if plan["contexts"] else set()))
    for context in plan["contexts"]:
        roles = context["declaration"]["roles"]
        declaration = enumeration_declaration(context)
        declaration["id"] = f"L:{len(data['relations'])}"
        data["relations"].append(declaration)
        for member in context["members"]:
            # A syntactic parent is resolved only by this actual declaration.
            data["blockers"] = [issue for issue in data["blockers"] if not (
                issue.get("reason") == "list_group_scope_interpretation_unsupported"
                and issue.get("parent_source") and owns_source(context["source"], issue["parent_source"])
                and owns_source(member["source"], issue.get("source", {})))]
            facts = [fact for fact in data["business"] if owns_source(member["source"], fact["source"])]
            if not facts:
                data["blockers"].append(_issue("enumeration_member_semantics_unresolved", context, member))
                data["blockers"].append(_issue("enumeration_membership_endpoint_unresolved", context))
                continue
            for fact in facts:
                if fact["role"] == "identity":
                    data["blockers"].append(_issue("enumeration_identity_membership_unresolved", context, member))
                    data["blockers"].append(_issue("enumeration_membership_endpoint_unresolved", context))
                    continue
                own_period = fact.get("qualifiers", {}).get("period")
                period = roles.get('period', {}).get('text')
                if period is not None and own_period is not None and not decide_equivalence(own_period, period, "period")["equivalent"]:
                    data["blockers"].append(_issue("enumeration_member_period_scope_unresolved", context, member,
                        layers=("B", "L"), own_period=own_period, introduction_period=copy.deepcopy(roles["period"])))
                    data["blockers"].append(_issue("enumeration_membership_endpoint_unresolved", context))
                    continue
                previous_subject = fact["subject"]
                if not previous_subject and fact["role"] == "metric":
                    attribute_source = fact.get("attribute_source", fact["source"].get("attribute_source"))
                    if not attribute_source or not owns_source(member["source"], attribute_source):
                        data["blockers"].append(_issue("enumeration_metric_subject_scope_unresolved", context, member,
                                                      layers=("B", "L")))
                        data["blockers"].append(_issue("enumeration_membership_endpoint_unresolved", context))
                        continue
                    fact["subject"] = roles["subject"]["text"]
                    fact["subject_source"] = copy.deepcopy(roles["subject"]["source"])
                effective_period = period if own_period is None else own_period
                if effective_period is not None:
                    fact.setdefault("qualifiers", {})["period"] = effective_period
                if own_period is None and period is not None:
                    fact.setdefault("qualifier_sources", {})["period"] = copy.deepcopy(roles["period"]["source"])
                identity = {key: roles[key]["text"] for key in ("subject", "collection", "domain") if key in roles}
                fact.setdefault("identity_facets", {})["enumeration"] = identity
                fact["enumeration_evidence"] = {"roles": copy.deepcopy(roles),
                    "introduction_source": copy.deepcopy(context["source"]),
                    "member_source": copy.deepcopy(member["source"]), "boundary": copy.deepcopy(context["boundary"])}
                for edge in data["relations"]:
                    if (edge.get('type') in {'enumeration_declaration', 'enumeration_membership'}
                            or edge.get('fact_id') not in {None, fact['id']}):
                        continue
                    right = edge.get("right")
                    if (isinstance(right, dict) and right.get("subject") == previous_subject
                            and right.get("attribute") == fact["attribute"]
                            and owns_source(member["source"], edge.get("source", {}))):
                        right["subject"] = fact["subject"]
                        if isinstance(edge.get("left"), dict) and edge["left"].get("subject") == previous_subject:
                            edge["left"]["subject"] = fact["subject"]
                        if effective_period is not None:
                            right.setdefault("qualifiers", {})["period"] = effective_period
                        right.setdefault("identity_facets", {})["enumeration"] = copy.deepcopy(identity)
                edge = enumeration_membership(context, member, fact)
                edge.update(id=f"L:{len(data['relations'])}", fact_id=fact["id"])
                data["relations"].append(edge)
                if own_period is None and period is not None:
                    data["relations"].append({"id": f"L:{len(data['relations'])}", "type": "qualifier_scope",
                        "left": {"type": "period", "text": period},
                        "right": {key: copy.deepcopy(fact[key]) for key in ("subject", "attribute", "scope", "qualifiers", "identity_facets")},
                        "source": copy.deepcopy(roles["period"]["source"]), "fact_id": fact["id"],
                        "rule_id": "printed_enumeration_period_to_member"})


def validate_enumeration_bindings(graph, nodes, source_literal):
    """Replay scope ownership; a repeated year token is not its own proof."""
    stored = graph.get("context", {}).get("enumeration_contexts", [])
    if not stored:
        if any(node.get("enumeration_evidence") for node in nodes.values()):
            raise ValueError("enumeration fact lacks its actual source scope")
        return
    planned = plan_from_syntax(graph["context"].get("syntax", []))
    if planned["contexts"] != stored:
        raise ValueError("enumeration scope differs from its actual syntax and introduction")
    if "enumeration_context_scope" not in graph.get("required_matcher_features", []):
        raise ValueError("enumeration scope lacks its declared comparison dependency")
    for context in stored:
        declaration = context["declaration"]
        if source_literal(context["source"]) != declaration["introduction"]["text"]:
            raise ValueError("enumeration introduction differs from its original source")
        for member in context["members"]:
            if source_literal(member["source"]) != member["text"]:
                raise ValueError("enumeration member differs from its original source")
        required = enumeration_declaration(context)
        if not any(edge.get("type") == "enumeration_declaration" and all(
                edge.get(key) == required[key] for key in ("left", "right", "source", "binding_evidence"))
                for edge in graph["relations"]):
            raise ValueError("enumeration declaration lacks its own source-bound collection relation")
    for ident in graph["projections"]["B"]:
        fact = nodes[ident]
        evidence = fact.get("enumeration_evidence")
        if not evidence:
            continue
        binding = member_for_source(planned, fact["source"])
        if not binding:
            raise ValueError("enumeration fact has no unique actual source member")
        context, member = binding
        roles = context["declaration"]["roles"]
        expected_evidence = {"roles": roles, "introduction_source": context["source"],
                             "member_source": member["source"], "boundary": context["boundary"]}
        if evidence != expected_evidence:
            raise ValueError("enumeration fact borrows a source role from another introduction")
        control = fact.get('subject_binding_evidence', {})
        if control.get('kind') == 'enumeration_subject' and (
                control != {'kind': 'enumeration_subject', 'controller': roles['subject']['text'],
                            'controller_source': roles['subject']['source'], 'introduction_source': context['source'], 'member_source': member['source']}
                or fact.get('subject') != roles['subject']['text'] or fact.get('subject_source') != roles['subject']['source']):
            raise ValueError('omitted actor lost its independently bound collection subject')
        identity = {key: roles[key]["text"] for key in ("subject", "collection", "domain") if key in roles}
        if fact.get("identity_facets", {}).get("enumeration") != identity:
            raise ValueError("enumeration fact identity differs from its source-bound collection")
        period_source = fact.get("qualifier_sources", {}).get("period")
        if 'period' in roles and (not decide_equivalence(fact.get("qualifiers", {}).get("period"), roles["period"]["text"], "period")["equivalent"] or not (
                period_source == roles["period"]["source"] or period_source and owns_source(member["source"], period_source))):
            raise ValueError("enumeration period source belongs to another scope")
        if 'period' not in roles and period_source and not owns_source(member['source'], period_source):
            raise ValueError('untimed collection cannot supply a member period')
        expected = enumeration_membership(context, member, fact)
        if not any(edge.get("type") == "enumeration_membership" and edge.get("fact_id") == ident
                   and all(edge.get(key) == expected[key] for key in ("left", "right", "source", "binding_evidence"))
                   for edge in graph["relations"]):
            raise ValueError("enumeration fact lacks its source-bound membership relation")
