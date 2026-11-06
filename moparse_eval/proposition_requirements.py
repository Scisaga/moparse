"""Source-bound compositional propositions, independent of candidate answers.

This grammar exposes subjects, predicates, objects and explicit operators. It
does not turn an unknown sentence into an opaque business field, resolve an
unstated subject, or supply a missing value from a reference.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .prose_requirements import _sentence_spans, prose_role_relations

VERBS = {
    "own": "own", "owns": "own", "owned": "own", "hold": "hold", "holds": "hold", "held": "hold",
    "acquire": "acquire", "acquires": "acquire", "acquired": "acquire",
    "approve": "approve", "approves": "approve", "approved": "approve",
    "review": "review", "reviews": "review", "reviewed": "review",
    "pay": "pay", "pays": "pay", "paid": "pay", "publish": "publish", "publishes": "publish",
    "disclose": "disclose", "discloses": "disclose", "submit": "submit", "submits": "submit",
    "invest": "invest", "invests": "invest", "invested": "invest",
    "increase": "increase", "increases": "increase", "increased": "increase",
    "decrease": "decrease", "decreases": "decrease", "decreased": "decrease",
    "report": "report", "reports": "report", "reported": "report",
    "declare": "declare", "declares": "declare", "declared": "declare",
    "require": "require", "requires": "require", "retain": "retain", "retains": "retain",
    "exceed": "exceed", "exceeds": "exceed", "exceeded": "exceed",
    "provide": "provide", "provides": "provide", "repay": "repay", "repays": "repay",
    "guarantee": "guarantee", "guarantees": "guarantee", "sell": "sell", "sells": "sell", "sold": "sell",
}
_VERB = re.compile(r"\b(" + "|".join(sorted(VERBS, key=len, reverse=True)) + r")\b", re.I)
_MODAL = re.compile(r"\b(shall|must|may|can|cannot|will|should)\b", re.I)
_CONDITION = re.compile(r"\b(only if|unless|except(?: when| that| for)?|if)\b", re.I)
_COORDINATOR = re.compile(r"\s+(and|or)\s+", re.I)
_CJK_VERB = re.compile(r"持有|拥有|擁有|收购|收購|批准|审批|審批|审阅|審閱|披露|支付|偿还|償還|投资|投資|增加|减少|減少")
_CJK_MODAL = re.compile(r"必须|必須|应当|應當|应|應|可以|将|將|不得|不能")


def _source(source: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    offset = source.get("text_span", [0, 0])[0]
    return {**copy.deepcopy(source), "text_span": [offset + start, offset + end]}


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and (text[start].isspace() or text[start] in ",，"):
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ".。!?！？,，"):
        end -= 1
    return start, end


def _pending(result, text, source, start, end, reason, **detail):
    pending = {"reason": reason, "kind": "proposition", "text": text[start:end],
               "source": _source(source, start, end), "layers": ["B", "L"], **detail}
    result["pending_requirements"].append(pending)
    result["blockers"].append(copy.deepcopy(pending))


def _conditions(text, source, start, end):
    """Keep each explicitly printed operator and operand, including two ifs."""
    conditions = []
    body_start, body_end = start, end
    leading = _CONDITION.match(text, start)
    if leading:
        comma = re.search(r"[,，]", text[leading.end():end])
        if comma is None:
            return start, end, [], False
        bound = leading.end() + comma.start()
        a, b = _trim(text, leading.end(), bound)
        conditions.append({"operator": leading[0].lower().replace(" ", "_"), "text": text[a:b],
                           "source": _source(source, a, b), "operator_source": _source(source, leading.start(), leading.end())})
        body_start = bound + 1
    trailing = list(_CONDITION.finditer(text, body_start, end))
    if trailing:
        body_end = trailing[0].start()
        for index, match in enumerate(trailing):
            limit = trailing[index + 1].start() if index + 1 < len(trailing) else end
            a, b = _trim(text, match.end(), limit)
            conditions.append({"operator": match[0].lower().replace(" ", "_"), "text": text[a:b],
                               "source": _source(source, a, b), "operator_source": _source(source, match.start(), match.end())})
    return body_start, body_end, conditions, all(c["text"] for c in conditions)


def _coordination_relations(facts, operators, *, mode):
    """Retain each admitted AND token and its complete original member cuts."""
    if not facts or not operators:
        return []
    first = facts[0]
    members = [{"ordinal": index, **{key: copy.deepcopy(fact[key]) for key in (
        "subject_source", "predicate_source", "object_source")}} for index, fact in enumerate(facts)]
    return [{"type": "proposition_coordination_scope",
        "left": {"operator": "and", "mode": mode, "position": index},
        "right": {"subject": first["subject"], "attribute": first["attribute"] if mode == "objects" else "coordinated_actions",
                  "scope": list(first["scope"]), "member_count": len(facts)},
        "source": copy.deepcopy(origin), "operator_source": copy.deepcopy(origin),
        "binding_evidence": {"statement_source": copy.deepcopy(first["source"]), "mode": mode,
            "operator_sources": copy.deepcopy(operators), "members": copy.deepcopy(members)},
        "rule_id": "source_bound_proposition_and_members"}
        for index, origin in enumerate(operators)]


def read_propositions(text: str, source: dict[str, Any], *, scope=(), subject: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"matched": False, "complete": False, "facts": [], "relations": [],
                              "blockers": [], "pending_requirements": [], "issues": [], "clauses": [],
                              "required_matcher_features": []}
    sentences = _sentence_spans(text)
    if not sentences:
        return result
    for sentence_start, sentence_end in sentences:
        start, end = _trim(text, sentence_start, sentence_end)
        fragment = text[start:end]
        # Field declarations, URLs and headings are interpreted by their own
        # typed readers. A colon does not license a proposition subject.
        if re.match(r"[^:：=\n]{1,100}[:：=]", fragment) and not _VERB.search(fragment.split(":", 1)[0]):
            continue
        body_start, body_end, conditions, valid_conditions = _conditions(text, source, start, end)
        year_prefix = re.match(r"\s*(?:In|During)\s+((?:19|20)\d{2})\s*,?\s+", text[body_start:body_end], re.I)
        period_source = None
        if year_prefix:
            period_source = _source(source, body_start + year_prefix.start(1), body_start + year_prefix.end(1))
            body_start += year_prefix.end()
        modal = _MODAL.search(text, body_start, body_end)
        verb = _VERB.search(text, modal.end() if modal else body_start, body_end)
        cjk = False
        if verb is None:
            verb = _CJK_VERB.search(text, body_start, body_end)
            cjk = verb is not None
            modal = _CJK_MODAL.search(text, body_start, verb.start()) if verb else None
        if verb is None:
            continue
        result["matched"] = True
        if not valid_conditions:
            _pending(result, text, source, start, end, "proposition_condition_boundary_unresolved")
            continue
        if len(conditions) > 1:
            _pending(result, text, source, sentence_start, sentence_end,
                     "proposition_multiple_operator_scope_unresolved", fragments=conditions)
            continue
        subject_start, subject_end = _trim(text, body_start, modal.start() if modal else verb.start())
        auxiliary = re.search(r"\s+(?:do|does|did)\s+(?:not|never)\s*$", text[subject_start:subject_end], re.I)
        if auxiliary:
            subject_end = subject_start + auxiliary.start()
        printed_subject = text[subject_start:subject_end] or subject
        if not printed_subject or re.search(r"[;；:：]", printed_subject):
            _pending(result, text, source, start, end, "proposition_subject_unresolved", conditions=conditions)
            continue
        if not cjk and (re.search(r"[,，]|\b(?:to|that|which|who|whose|whom)\b", printed_subject, re.I)
                        or re.match(r"(?:How|Why|When|What|Whether|Under|In|During|After|Before|Since|Until|From|According)\b", printed_subject, re.I)):
            _pending(result, text, source, sentence_start, sentence_end, "proposition_subject_scope_unresolved")
            continue
        if re.search(r'''["'“”‘’「」『』]''', text[verb.end():body_end]) and re.search(r"\b(?:and|or)\b", text[verb.end():body_end], re.I):
            _pending(result, text, source, sentence_start, sentence_end, "proposition_quoted_membership_scope_unresolved")
            continue
        prefix = text[body_start:verb.start()]
        if re.search(r"\b(?:said|announced|believe|believes|reported)\b|宣布|表示|认为|認為", prefix, re.I):
            _pending(result, text, source, sentence_start, sentence_end, "proposition_reported_scope_unresolved", conditions=conditions)
            continue
        if not cjk:
            from .narrative_requirements import _ACTIONS, _Reader

            syntax = _Reader(text, source, scope).syntax
            if any(match[1].lower() in _ACTIONS for match in re.finditer(r"\bto\s+([A-Za-z]+)\b", syntax[verb.end():body_end], re.I)):
                # This finite reader has no control/attachment grammar. A
                # separate owning Narrative AST must interpret the infinitive
                # instead of distributing its words as ordinary AND objects.
                _pending(result, text, source, sentence_start, sentence_end, "proposition_infinitival_scope_unresolved")
                continue
        q: dict[str, Any] = {}
        q_sources = {}
        if year_prefix:
            q["period"] = year_prefix[1]
            q_sources["period"] = period_source
        if modal:
            q["modality"] = modal[0].lower()
            q_sources["modality"] = _source(source, modal.start(), modal.end())
        negation_start = modal.end() if modal else subject_end
        negation = re.search(r"\b(?:not|never)\b|不得|不能|不", text[negation_start:verb.start()], re.I)
        negative_modal = bool(modal and modal[0].lower() in {"cannot", "不得", "不能"})
        negated = bool(negation) or negative_modal
        if negated and re.search(r"\b(?:and|or)\b|并|並|及|和|或", text[verb.end():body_end], re.I):
            _pending(result, text, source, sentence_start, sentence_end,
                     "proposition_negated_coordination_scope_unresolved")
            continue
        q["polarity"] = "negative" if negated else "positive"
        if negation:
            q_sources["polarity"] = _source(source, negation_start + negation.start(), negation_start + negation.end())
        elif negative_modal:
            q_sources["polarity"] = _source(source, modal.start(), modal.end())
        if conditions:
            if len(conditions) == 1:
                key = "exception" if conditions[0]["operator"].startswith("except") else "condition"
                q[key] = conditions[0]["text"]
                q[key + "_operator"] = conditions[0]["operator"]
                q_sources[key] = conditions[0]["source"]
                q_sources[key + "_operator"] = conditions[0]["operator_source"]
            else:
                q["condition"] = [{"operator": c["operator"], "text": c["text"]} for c in conditions]
                q["condition_operator"] = "multiple_explicit_scopes"
        predicates = [(verb, verb.end(), body_end)]
        action_operators = []
        disjunctive_actions = False
        remaining = list((_CJK_VERB if cjk else _VERB).finditer(text, verb.end(), body_end))
        for following in remaining:
            between = text[predicates[-1][0].end():following.start()]
            join = re.search(r"\b(and|or)\s*$|(?:并|並|及|和|或)\s*$", between, re.I)
            if join:
                disjunctive_actions |= join[0].strip().lower() in {"or", "或"}
                previous, value_start, _ = predicates[-1]
                join_start = previous.end() + join.start()
                join_end = previous.end() + join.end()
                while join_start < join_end and text[join_start].isspace():
                    join_start += 1
                while join_end > join_start and text[join_end - 1].isspace():
                    join_end -= 1
                action_operators.append(_source(source, join_start, join_end))
                predicates[-1] = (previous, value_start, previous.end() + join.start())
                predicates.append((following, following.end(), body_end))
        if disjunctive_actions:
            _pending(result, text, source, sentence_start, sentence_end,
                     "proposition_disjunctive_actions_unresolved",
                     actions=[p[0][0] for p in predicates], conditions=conditions)
            continue
        # Two verbs sharing a final object use that object's actual source.
        last_a, last_b = _trim(text, predicates[-1][1], predicates[-1][2])
        action_fact_start = len(result["facts"])
        for current, value_start, value_end in predicates:
            a, b = _trim(text, value_start, value_end)
            if a == b and len(predicates) > 1:
                a, b = last_a, last_b
            if a == b:
                # An intransitive modal action is a complete proposition.
                if not modal:
                    _pending(result, text, source, start, end, "proposition_object_unresolved", conditions=conditions)
                    continue
            object_spans = [(a, b)]
            joins = list(_COORDINATOR.finditer(text, a, b))
            nominal_of = re.search(r"\bof\b", text[a:b], re.I) if not cjk else None
            if nominal_of is not None and any(a + nominal_of.start() < join.start() for join in joins):
                # OF introduces a nominal complement. Its internal AND/OR
                # cannot become additional direct objects of this predicate.
                # This finite reader has no NP attachment tree; the bounded
                # nominal reader must own the full source or retain pending.
                _pending(result, text, source, sentence_start, sentence_end,
                         "proposition_nominal_coordination_attachment_unresolved")
                continue
            if joins and len(predicates) == 1 and not any(_VERB.search(text[m.end():b]) for m in joins):
                object_spans = []
                cursor = a
                for join in joins:
                    object_spans.append(_trim(text, cursor, join.start()))
                    cursor = join.end()
                object_spans.append(_trim(text, cursor, b))
            action = current[0] if cjk else VERBS[current[0].lower()]
            object_fact_start = len(result["facts"])
            for object_start, object_end in object_spans:
                if not cjk and re.match(r"(?:do|does|did|is|are|was|were|may|must|shall|will|can)\s+(?:not\s+)?[A-Za-z]+\b",
                                        text[object_start:object_end], re.I):
                    _pending(result, text, source, object_start, object_end,
                             "proposition_embedded_auxiliary_clause_unresolved")
                    continue
                own_q = copy.deepcopy(q)
                own_q_sources = copy.deepcopy(q_sources)
                if not modal and not cjk:
                    raw_verb = current[0].lower()
                    own_q["tense"] = "past" if raw_verb.endswith("ed") or raw_verb in {"held", "paid", "sold"} else "present"
                    own_q_sources["tense"] = _source(source, current.start(), current.end())
                    if auxiliary:
                        auxiliary_word = re.search(r"\b(?:do|does|did)\b", text[subject_end:verb.start()], re.I)
                        if auxiliary_word:
                            own_q["tense"] = "past" if auxiliary_word[0].lower() == "did" else "present"
                            own_q_sources["tense"] = _source(source, subject_end + auxiliary_word.start(), subject_end + auxiliary_word.end())
                if any(m[1].lower() == "or" for m in joins):
                    # OR must remain a single disjunction, not independent
                    # claims that both objects are asserted.
                    _pending(result, text, source, start, end, "proposition_disjunction_group_unresolved",
                             conditions=conditions, objects=[text[x:y] for x, y in object_spans])
                    break
                fact = {"subject": printed_subject, "predicate": current[0], "object": text[object_start:object_end],
                        "attribute": action, "value": text[object_start:object_end], "role": "description",
                        "qualifiers": own_q, "qualifier_sources": own_q_sources, "identity_facets": {},
                        "scope": list(scope), "source": _source(source, start, end),
                        "subject_source": _source(source, subject_start, subject_end),
                        "attribute_source": _source(source, current.start(), current.end()),
                        "predicate_source": _source(source, current.start(), current.end()),
                        "value_source": _source(source, object_start, object_end),
                        "object_source": _source(source, object_start, object_end),
                        "logic": {"kind": "proposition", "action": action, "conditions": copy.deepcopy(conditions)},
                        "rule_id": "source_bound_subject_predicate_object"}
                result["facts"].append(fact)
                result["relations"].append({"type": "field_binding", "left": {
                    "subject": printed_subject, "attribute": action}, "right": {
                    "subject": printed_subject, "attribute": action, "scope": list(scope),
                    "qualifiers": copy.deepcopy(own_q), "identity_facets": {}},
                    "source": copy.deepcopy(fact["source"]), "rule_id": "explicit_proposition_binding",
                    "binding_evidence": {name: copy.deepcopy(fact[key]) for name, key in (
                        ("statement_source", "source"), ("subject_source", "subject_source"),
                        ("predicate_source", "predicate_source"), ("object_source", "object_source"))}})
                result["relations"].extend(edge for edge in prose_role_relations(fact)
                                           if edge["type"] == "qualifier_scope")
                endpoint = {"subject": printed_subject, "action": action, "scope": list(scope)}
                for condition in conditions:
                    kind = "exception" if condition["operator"].startswith("except") else "condition"
                    result["relations"].append({"type": kind + "_scope",
                        "left": {"role": kind, "operator": condition["operator"]}, "right": copy.deepcopy(endpoint),
                        "source": copy.deepcopy(condition["source"]), "binding_evidence": {
                            "qualifier_text": condition["text"], "qualifier_source": copy.deepcopy(condition["source"]),
                            "statement_source": copy.deepcopy(fact["source"]), "operator_source": copy.deepcopy(condition["operator_source"])}})
                result["clauses"].append({"subject": printed_subject, "predicate": current[0],
                    "object": text[object_start:object_end], "source": copy.deepcopy(fact["source"]),
                    "operator_sources": [copy.deepcopy(c["operator_source"]) for c in conditions]})
            if len(object_spans) > 1 and not any(match[1].lower() == "or" for match in joins):
                operators = [_source(source, *join.span(1)) for join in joins]
                result["relations"].extend(_coordination_relations(
                    result["facts"][object_fact_start:], operators, mode="objects"))
                result["required_matcher_features"] = ["coordination_scope"]
        if len(predicates) > 1:
            result["relations"].extend(_coordination_relations(
                result["facts"][action_fact_start:], action_operators, mode="actions"))
            result["required_matcher_features"] = ["coordination_scope"]
    result["complete"] = result["matched"] and not result["blockers"] and len(result["clauses"]) > 0
    # A successfully read later sentence cannot hide an earlier unhandled one.
    if result["matched"]:
        for a, b in sentences:
            offset = source.get("text_span", [0])[0]
            if any(pending["source"]["text_span"][0] <= offset + _trim(text, a, b)[0]
                   and pending["source"]["text_span"][1] >= offset + _trim(text, a, b)[1]
                   for pending in result["pending_requirements"]):
                continue
            if not any(f["source"]["text_span"][0] <= source.get("text_span", [0])[0] + _trim(text, a, b)[0]
                       and f["source"]["text_span"][1] >= source.get("text_span", [0])[0] + _trim(text, a, b)[1]
                       for f in result["facts"]):
                if text[a:b].strip():
                    _pending(result, text, source, a, b, "proposition_sentence_not_interpreted")
        result["complete"] = not result["blockers"]
    return result


def validate_proposition_coordinations(graph, fields, literal):
    """Rebuild finite AND ownership from source, independent of derived tags."""

    def explicitly_pending(origin):
        # A source rejected by its owning interpretation stays an unknown,
        # rather than being forced through this alternate reader. The full
        # clause must remain a literal-bound B/L obligation. The five input
        # scope declarations cannot excuse an unrelated software omission.
        for issue in graph.get("unresolved", []):
            source = issue.get("source", {})
            if (issue.get("reason") == "input_scope_context" or not {"B", "L"} <= set(issue.get("layers", []))
                    or not isinstance(issue.get("text"), str) or not issue["text"]):
                continue
            if source.get("path") != origin.get("path") or source.get("cell") != origin.get("cell"):
                continue
            a, b = source.get("lines", [0, 0])
            c, d = origin.get("lines", [0, 0])
            bounds, own = source.get("text_span"), origin.get("text_span")
            if (a <= c <= d <= b and (bounds is None or own is not None
                    and bounds[0] <= own[0] <= own[1] <= bounds[1])
                    and literal(source) == issue.get("text")):
                return True
        return False

    seen = set()
    for entry in graph["sources"]:
        for a, b in _sentence_spans(entry["text"]):
            text, origin = entry["text"][a:b], _source(entry["source"], a, b)
            key = (str(origin), text)
            if key in seen:
                continue
            seen.add(key)
            read = read_propositions(text, origin)
            groups = [edge for edge in read["relations"] if edge["type"] == "proposition_coordination_scope"]
            if not read["complete"] or not groups:
                continue
            if literal(origin) != text:
                raise ValueError("proposition coordination differs from its actual source")
            actual_fields = [field for field in fields if any(field.get("source") == fact["source"] for fact in read["facts"])]
            scopes = {tuple(field.get("scope", [])) for field in actual_fields}
            interpreted_edges = [edge for edge in graph["relations"] if edge.get("type") == "proposition_coordination_scope"
                and any(edge.get("binding_evidence", {}).get("statement_source") == fact["source"] for fact in read["facts"])]
            if not actual_fields and not interpreted_edges and explicitly_pending(origin):
                continue
            if not actual_fields or len(scopes) != 1:
                raise ValueError("proposition coordination has no complete source-bound member scope")
            scoped = read_propositions(text, origin, scope=next(iter(scopes)))
            required = [edge for edge in scoped["relations"] if edge["type"] == "proposition_coordination_scope"]
            member_keys = ("subject", "attribute", "predicate", "object", "subject_source", "predicate_source", "object_source")
            if any(not any(all(actual.get(key) == fact[key] for key in member_keys) for actual in actual_fields)
                   for fact in scoped["facts"]):
                raise ValueError("proposition coordination lost an original semantic member")
            if "coordination_scope" not in graph["required_matcher_features"]:
                raise ValueError("proposition coordination lost its comparison dependency")
            for edge in required:
                keys = ("type", "left", "right", "source", "operator_source", "binding_evidence")
                if not any(all(actual.get(key) == edge[key] for key in keys) for actual in graph["relations"]):
                    raise ValueError("proposition coordination lost its actual operator or member source binding")
