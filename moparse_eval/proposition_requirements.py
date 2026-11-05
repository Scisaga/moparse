"""Source-bound compositional propositions, independent of candidate answers.

This grammar exposes subjects, predicates, objects and explicit operators. It
does not turn an unknown sentence into an opaque business field, resolve an
unstated subject, or supply a missing value from a reference.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .prose_requirements import _sentence_spans

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


def read_propositions(text: str, source: dict[str, Any], *, scope=(), subject: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"matched": False, "complete": False, "facts": [], "relations": [],
                              "blockers": [], "pending_requirements": [], "issues": [], "clauses": []}
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
        disjunctive_actions = False
        remaining = list((_CJK_VERB if cjk else _VERB).finditer(text, verb.end(), body_end))
        for following in remaining:
            between = text[predicates[-1][0].end():following.start()]
            join = re.search(r"\b(and|or)\s*$|(?:并|並|及|和|或)\s*$", between, re.I)
            if join:
                disjunctive_actions |= join[0].strip().lower() in {"or", "或"}
                previous, value_start, _ = predicates[-1]
                predicates[-1] = (previous, value_start, previous.end() + join.start())
                predicates.append((following, following.end(), body_end))
        if disjunctive_actions:
            _pending(result, text, source, sentence_start, sentence_end,
                     "proposition_disjunctive_actions_unresolved",
                     actions=[p[0][0] for p in predicates], conditions=conditions)
            continue
        # Two verbs sharing a final object use that object's actual source.
        last_a, last_b = _trim(text, predicates[-1][1], predicates[-1][2])
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
            if joins and len(predicates) == 1 and not any(_VERB.search(text[m.end():b]) for m in joins):
                object_spans = []
                cursor = a
                for join in joins:
                    object_spans.append(_trim(text, cursor, join.start()))
                    cursor = join.end()
                object_spans.append(_trim(text, cursor, b))
            action = current[0] if cjk else VERBS[current[0].lower()]
            for object_start, object_end in object_spans:
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
                    "source": copy.deepcopy(fact["source"]), "rule_id": "explicit_proposition_binding"})
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
