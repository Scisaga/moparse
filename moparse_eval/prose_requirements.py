"""Source-only reading of bounded logical prose and independent endpoints.

This is a small grammar, not an unrestricted semantic judge. It keeps complete
conditions, exceptions and negation. Unresolved branching remains explicit;
ordinary text and candidate values never supply their own layout identity.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from typing import Any

from .metrics import normalize_text

_MODAL = re.compile(r"\b(shall|must|may|can|cannot|will|should|(?:is|are) required to)\b", re.I)
_CONNECTOR = re.compile(r"\b(only if|unless|if|except(?: when| that| for)?)\b", re.I)
_PURPOSE = re.compile(r"^To\s+([^,;]+),\s*", re.I)
_NUMBER_WORDS = frozenset("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion".split())
_NEGATION = frozenset({"not", "no", "never", "neither", "nor"})
_QUANTITY = re.compile(r"(?<![A-Za-z0-9])[+\-−]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:\s*(?:人民[幣币]|美元|港元)?(?:百萬|百万|千萬|千万|億|亿|萬|万|百|千)?元|\s*(?:credits?|shares?|people|persons?)|[%‰])?(?![A-Za-z0-9])", re.I)
_WORDS = re.compile(r"[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*(?:['’\-][A-Za-z0-9]+)*|[\u3400-\u9fff]+")
_ORDINAL = re.compile(r"^\s*(?:\((\d+)\)|([0-9]+|[A-Za-z])[.)、])\s+")
_RECORD_PRIMARY = re.compile(r"Name|Entity|Company|Subject|名称|姓名|主体|公司名称", re.I)
_RECORD_IDENTITY = re.compile(r"Role|Type|Code|Identifier|ID|Region|职务|类型|地区|证券代码", re.I)
_RECORD_PAIR = re.compile(r"\s*(?P<attribute>[^:：=\n]+?)\s*[:：=]\s*(?P<value>.*?)\s*$", re.S)


def _result() -> dict[str, Any]:
    return {"matched": False, "facts": [], "relations": [], "text_spans": [],
            "blockers": [], "issues": [], "endpoints": [], "pending_requirements": []}


def _source(source: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    span = source.get("text_span")
    offset = span[0] if isinstance(span, (list, tuple)) and len(span) == 2 and type(span[0]) is int else 0
    return {**copy.deepcopy(source), "text_span": [offset + start, offset + end]}


def _text(value: str) -> str:
    return normalize_text(value, collapse_whitespace=True).strip()


def _subject(value: str) -> str:
    value = _text(value)
    if re.fullmatch(r"you|we|they|i|he|she|it", value, re.I):
        return value.lower()
    return re.sub(r"^The\b", "the", value)


def _unresolved_subject_context(value: str) -> bool:
    """Reject a printed note marker or an unparsed temporal reporting clause.

    These are boundaries of the finite subject grammar, not inferred actors.
    A number in parentheses stays in its original statement; an AS clause
    after a temporal subject and finite past verb is not one nominal subject.
    """
    marker = _ORDINAL.match(value)
    numbered = marker and (marker[1] or marker[2]).isdigit()
    temporal_clause = re.search(r'\b(?:year|quarter|period)\b(?:\s+\d{4})?\s+[a-z]+ed\b.+\bas\b', value)
    return bool(numbered or temporal_clause)


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    result, start = [], 0
    for match in re.finditer(r'''[.!?。！？]["”’」』）)\]]*''', text):
        end = match.end()
        ordinal = _ORDINAL.match(text, start)
        if ordinal and match.start() < ordinal.end():
            continue
        if text[match.start()] in ".!?" and end < len(text) and not text[end].isspace():
            continue
        if _enclosed(text, end):
            continue
        before = text[start:match.start() + 1]
        if re.search(r"(?:[A-Za-z]\.){2,}$|\b(?:Mr|Mrs|Ms|Dr|Prof|Inc|Corp|Ltd)\.$", before):
            continue
        if re.search(r"\b[A-Z][a-z]+\s+[A-Z]\.$", before) and re.match(r"\s+[A-Z][a-z]+", text[end:]):
            continue
        if text[start:end].strip():
            result.append((start, end))
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    if text[start:].strip():
        result.append((start, len(text)))
    return result


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ".!?。！？"):
        end -= 1
    return start, end


def _skeleton(text: str) -> list[str]:
    # Quantities must have their own lexical boundaries. The 17 in Type17 and
    # the 元 in 元器件 remain part of their actual identifiers and words.
    projected = _QUANTITY.sub(" ", text)
    return [match[0] for match in _WORDS.finditer(projected)
            if match[0].lower() not in _NEGATION | _NUMBER_WORDS]


def _action(predicate: str) -> str | None:
    first = re.match(r"([A-Za-z]+)(?:\s+([A-Za-z]+))?", predicate)
    if first is None:
        return None
    action = first[1].lower()
    if action == "also":
        # Additive scope needs its own syntax. It is not the verb governing
        # the following object, even in an otherwise clear modal clause.
        return None
    if action == "be" and first[2]:
        action += " " + first[2].lower()
    following = re.match(r"\s+and\s+([A-Za-z]+)\b", predicate[len(action):], re.I)
    if following:
        action += " and " + following[1].lower()
    return action


def _parent_text(parent) -> str:
    return parent.get("text", "") if isinstance(parent, dict) else parent if isinstance(parent, str) else ""


def _agenda(parents) -> bool:
    return any(re.fullmatch(r"Items of business[:：]?|Agenda[:：]?|議程[:：]?|议程[:：]?", item.strip(), re.I)
               for item in map(_parent_text, parents))


def _record_context(parents, source):
    record, evidence, blockers = {}, [], []
    active = False
    for parent in parents:
        text = _parent_text(parent)
        match = _RECORD_PAIR.fullmatch(text)
        if match is None:
            continue
        attribute, value = match["attribute"].strip(), match["value"].strip()
        primary = bool(_RECORD_PRIMARY.fullmatch(attribute))
        if not primary and not (active and _RECORD_IDENTITY.fullmatch(attribute)):
            continue
        if primary:
            record, evidence, active = {}, [], True
        original = parent.get("source") if isinstance(parent, dict) else None
        if not isinstance(original, dict) or not original.get("path"):
            blockers.append({"reason": "prose_context_parent_source_unavailable", "source": copy.deepcopy(source),
                             "parent": text, "layers": ["B", "L"]})
            continue
        if not value or re.search(r"[;；\n]", value):
            blockers.append({"reason": "prose_context_parent_identity_unsupported", "source": copy.deepcopy(original),
                             "parent": text, "layers": ["B", "L"]})
            continue
        if attribute in record and record[attribute] != value:
            blockers.append({"reason": "prose_context_parent_identity_conflict", "source": copy.deepcopy(original),
                             "parent": text, "layers": ["B", "L"]})
            continue
        record[attribute] = value
        evidence.append({"attribute": attribute, "value": value, "source": copy.deepcopy(original),
                         "attribute_source": _source(original, match.start("attribute"), match.start("attribute") + len(attribute)),
                         "value_source": _source(original, match.start("value"), match.start("value") + len(value))})
    return record, evidence, blockers


def _enclosed(text: str, position: int) -> bool:
    quote = None
    depth = 0
    closes = {"\"": "\"", "'": "'", "“": "”", "‘": "’", "「": "」", "『": "』"}
    for index, character in enumerate(text[:position]):
        if character in {"'", "’"} and index and index + 1 < len(text) and text[index - 1].isalpha() and text[index + 1].isalpha():
            continue
        if quote:
            if character == quote:
                quote = None
        elif character in closes:
            quote = closes[character]
        elif character in "(（[":
            depth += 1
        elif character in ")）]":
            depth = max(0, depth - 1)
    return bool(quote or depth)


def prose_scope_relations(fact: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose qualifier ownership without using its numeric answer as an id."""
    result = []
    for role in ("condition", "exception", "purpose"):
        literal = fact.get("qualifiers", {}).get(role)
        if literal is None:
            continue
        source = copy.deepcopy(fact.get("qualifier_sources", {}).get(role, fact["source"]))
        operator_source = copy.deepcopy(fact.get("qualifier_sources", {}).get(role + "_operator"))
        result.append({"id": f"L:prose_scope:{role}", "type": role + "_scope",
                       "left": {"role": role, "lexical_anchor": _skeleton(literal)},
                       "right": {"subject": fact["subject"], "action": fact["attribute"], "scope": list(fact.get("scope", []))},
                       "source": source,
                       "operator_source": operator_source,
                       "binding_evidence": {"qualifier_text": literal, "qualifier_source": source,
                                            "statement_source": copy.deepcopy(fact["source"]),
                                            "operator_source": operator_source}})
        if fact.get("identity_facets"):
            result[-1]["right"]["identity_facets"] = copy.deepcopy(fact["identity_facets"])
        for key in ("field_label_evidence", "record_evidence"):
            if fact.get(key):
                result[-1][key] = copy.deepcopy(fact[key])
    return result


def prose_role_relations(fact: dict[str, Any]) -> list[dict[str, Any]]:
    """Bind admitted modal-clause roles and explicit operators separately.

    The object literal remains audit evidence rather than a location key. A
    value change therefore does not erase a correctly retained logical link.
    Unmarked positive polarity has no invented token or extra scope edge.
    """
    if not fact.get("predicate_source"):
        return []
    endpoint = {"subject": fact["subject"], "attribute": fact["attribute"],
                "scope": list(fact.get("scope", [])), "identity_facets": copy.deepcopy(fact.get("identity_facets", {}))}
    binding = {"statement_source": copy.deepcopy(fact["source"]),
               **{key: copy.deepcopy(fact[key]) for key in ("subject_source", "predicate_source", "object_source")}}
    result = [{"type": "field_binding", "left": {"subject": fact["subject"], "attribute": fact["attribute"]},
               "right": copy.deepcopy(endpoint), "source": copy.deepcopy(fact["predicate_source"]),
               "binding_evidence": copy.deepcopy(binding), "rule_id": "source_bound_modal_prose_binding"}]
    for role in ("modality", "polarity"):
        origin = fact.get("qualifier_sources", {}).get(role)
        value = fact.get("qualifiers", {}).get(role)
        if not origin or value is None:
            continue
        result.append({"type": "qualifier_scope", "left": {"type": role, "text": value},
            "right": copy.deepcopy(endpoint), "source": copy.deepcopy(origin),
            "operator_source": copy.deepcopy(origin),
            "binding_evidence": {**copy.deepcopy(binding), "operator": value, "operator_source": copy.deepcopy(origin)},
            "rule_id": "source_bound_modal_prose_" + role})
    for edge in result:
        for key in ("field_label_evidence", "record_evidence"):
            if fact.get(key):
                edge[key] = copy.deepcopy(fact[key])
    return result


def read_prose_requirements(text: str, source: dict[str, Any], *, label: str | None = None,
                            label_source: dict[str, Any] | None = None,
                            parents=(), scope: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """Expose supported logical clauses; do not rewrite candidate sentences."""
    result = _result()
    label_prefix = re.match(r"\s*" + re.escape(label) + r"\s*[:：]\s*", text) if label else None
    for sentence_start, sentence_end in _sentence_spans(text):
        start, end = _trim(text, sentence_start, sentence_end)
        if label_prefix and start < label_prefix.end():
            start = label_prefix.end()
        fragment = text[start:end]
        modals = list(_MODAL.finditer(fragment))
        connectors = list(_CONNECTOR.finditer(fragment))
        if any(_enclosed(fragment, match.start()) for match in [*modals, *connectors]):
            result["matched"] = True
            result["blockers"].append({"reason": "quoted_or_parenthetic_logic_scope_unsupported", "source": _source(source, start, end), "text": fragment})
            continue
        if not modals:
            if connectors and _agenda(parents) and len(connectors) == 1:
                connector = connectors[0]
                noun_end = start + connector.start()
                while noun_end > start and text[noun_end - 1] in " ,":
                    noun_end -= 1
                noun = text[start:noun_end]
                action = " ".join(_skeleton(noun)).lower()
                condition_start = start + connector.end()
                while condition_start < end and text[condition_start].isspace():
                    condition_start += 1
                q = {"polarity": "positive", "condition": text[condition_start:end], "condition_operator": connector[0].lower().replace(" ", "_")}
                result["facts"].append({"subject": "", "attribute": action, "value": noun, "role": "description",
                    "qualifiers": q, "identity_facets": {}, "scope": list(scope), "source": _source(source, start, end),
                    "value_source": _source(source, start, noun_end),
                    "qualifier_sources": {"condition": _source(source, condition_start, end),
                        "condition_operator": _source(source, start + connector.start(), start + connector.end())},
                    "printed_label": label, "logic": {"kind": "conditional_agenda_item", "operator": q["condition_operator"]}})
                result["matched"] = True
            elif connectors:
                result["matched"] = True
                result["blockers"].append({"reason": "conditional_prose_context_unsupported", "source": _source(source, start, end), "text": fragment})
            elif _MODAL.search(text):
                result["blockers"].append({"reason": "prose_clause_semantics_unsupported", "source": _source(source, start, end), "text": fragment})
            continue
        result["matched"] = True
        if len(modals) != 1:
            result["blockers"].append({"reason": "compound_modal_statement_unsupported", "source": _source(source, start, end), "text": fragment})
            continue
        modal = modals[0]
        body_start = start
        q, q_sources = {}, {}
        purpose = _PURPOSE.match(fragment)
        leading = _CONNECTOR.match(fragment)
        if purpose:
            q["purpose"] = purpose[1].strip()
            q_sources["purpose"] = _source(source, start + purpose.start(1), start + purpose.end(1))
            q_sources["purpose_operator"] = _source(source, start + purpose.start(), start + purpose.start() + 2)
            body_start = start + purpose.end()
        elif leading:
            comma = text.rfind(",", start + leading.end(), start + modal.start())
            if comma < 0:
                result["blockers"].append({"reason": "front_condition_boundary_unsupported", "source": _source(source, start, end), "text": fragment})
                continue
            condition_start = start + leading.end()
            while condition_start < comma and text[condition_start].isspace():
                condition_start += 1
            front_kind = "exception" if leading[0].lower().startswith("except") else "condition"
            q[front_kind] = text[condition_start:comma].strip()
            q[front_kind + "_operator"] = leading[0].lower().replace(" ", "_")
            q_sources[front_kind] = _source(source, condition_start, comma)
            q_sources[front_kind + "_operator"] = _source(source, start + leading.start(), start + leading.end())
            body_start = comma + 1
        subject_start, subject_end = body_start, start + modal.start()
        while subject_start < subject_end and text[subject_start].isspace():
            subject_start += 1
        while subject_end > subject_start and text[subject_end - 1].isspace():
            subject_end -= 1
        printed_subject = text[subject_start:subject_end]
        if _unresolved_subject_context(printed_subject):
            pending = {'kind': 'proposition', 'comparison_domain': 'sentence_interpretation',
                'reason': 'prose_subject_boundary_unsupported', 'source': _source(source, sentence_start, sentence_end),
                'text': text[sentence_start:sentence_end], 'subject_source': _source(source, subject_start, subject_end),
                'layers': ['B', 'L']}
            result['blockers'].append(pending)
            result['pending_requirements'].append(copy.deepcopy(pending))
            continue
        if not printed_subject or re.search(r"[:：;\n]", printed_subject):
            result["blockers"].append({"reason": "prose_subject_boundary_unsupported", "source": _source(source, subject_start, subject_end), "text": printed_subject})
            continue
        if (re.search(r"\b(?:announced|reported|stated|declared|said|believes?)\b", printed_subject, re.I)
                or re.match(r"(?:In|During|For|As of)\b.*\b(?:19|20)\d{2}\b", printed_subject, re.I)):
            pending = {"reason": "reported_or_temporal_subject_scope_unsupported",
                       "source": _source(source, sentence_start, sentence_end),
                       "text": text[sentence_start:sentence_end].strip(), "layers": ["B", "L"],
                       "subject_source": _source(source, subject_start, subject_end)}
            result["blockers"].append(pending)
            result["pending_requirements"].append(copy.deepcopy(pending))
            continue
        polarity = "positive"
        no_subject = re.match(r"No\s+", printed_subject, re.I)
        if no_subject:
            polarity = "negative"
            q_sources["polarity"] = _source(source, subject_start, subject_start + no_subject.end() - 1)
            subject_start += no_subject.end()
            printed_subject = text[subject_start:subject_end]
        elif re.search(r"\b(?:neither|nor|nobody|nothing)\b", printed_subject, re.I):
            result["blockers"].append({"reason": "quantified_subject_scope_unsupported", "source": _source(source, subject_start, subject_end), "text": printed_subject})
            continue
        printed_modal = modal[0]
        if printed_modal.lower() == "cannot":
            polarity, printed_modal = "negative", "can"
            q_sources["polarity"] = _source(source, start + modal.start(), start + modal.end())
        q.update(modality=printed_modal.lower(), polarity=polarity)
        q_sources["modality"] = _source(source, start + modal.start(), start + modal.end())
        predicate_start = start + modal.end()
        while predicate_start < end and text[predicate_start].isspace():
            predicate_start += 1
        negative = re.match(r"(?:not|never)\b\s*", text[predicate_start:end], re.I)
        if negative:
            q["polarity"] = "negative"
            q_sources["polarity"] = _source(source, predicate_start, predicate_start + len(negative[0].rstrip()))
            predicate_start += negative.end()
            if re.match(r"(?:not|never)\b", text[predicate_start:end], re.I):
                result["blockers"].append({"reason": "nested_negation_scope_unsupported", "source": _source(source, predicate_start, end), "text": text[predicate_start:end]})
                continue
        if re.match(r"[A-Za-z]+\s*[:：]", text[predicate_start:end]):
            result["issues"].append({"reason": "interrupted_modal_predicate", "source": _source(source, predicate_start, end), "text": text[predicate_start:end]})
            continue
        remaining = list(_CONNECTOR.finditer(text[predicate_start:end]))
        if remaining and (leading or len(remaining) > 1 or re.search(
                r"\b(?:and|or)\s*,?\s*$", text[predicate_start:predicate_start + remaining[0].start()], re.I)):
            fragments = []
            if leading:
                fragments.append({"kind": front_kind, "operator": leading[0].lower(), "text": q[front_kind],
                                  "source": copy.deepcopy(q_sources[front_kind]),
                                  "operator_source": copy.deepcopy(q_sources[front_kind + "_operator"])})
            for index, connector in enumerate(remaining):
                operand_start = predicate_start + connector.end()
                operand_end = predicate_start + remaining[index + 1].start() if index + 1 < len(remaining) else end
                while operand_start < operand_end and text[operand_start].isspace():
                    operand_start += 1
                while operand_end > operand_start and text[operand_end - 1] in " ,":
                    operand_end -= 1
                fragments.append({"kind": "exception" if connector[0].lower().startswith("except") else "condition",
                                  "operator": connector[0].lower(), "text": text[operand_start:operand_end],
                                  "source": _source(source, operand_start, operand_end),
                                  "operator_source": _source(source, predicate_start + connector.start(),
                                                             predicate_start + connector.end())})
            pending = {"kind": "compound_logical_scope", "reason": "branched_conditional_scope_unsupported",
                       "text": text[sentence_start:sentence_end], "source": _source(source, sentence_start, sentence_end),
                       "fragments": fragments, "layers": ["B", "L"]}
            result["blockers"].append(copy.deepcopy(pending))
            result["pending_requirements"].append(pending)
            continue
        predicate_end = end
        if remaining:
            connector = remaining[0]
            predicate_end = predicate_start + connector.start()
            while predicate_end > predicate_start and text[predicate_end - 1] in " ,":
                predicate_end -= 1
            operand_start = predicate_start + connector.end()
            while operand_start < end and text[operand_start].isspace():
                operand_start += 1
            kind = "exception" if connector[0].lower().startswith("except") else "condition"
            q[kind] = text[operand_start:end]
            q[kind + "_operator"] = connector[0].lower().replace(" ", "_")
            q_sources[kind] = _source(source, operand_start, end)
            q_sources[kind + "_operator"] = _source(source, predicate_start + connector.start(), predicate_start + connector.end())
        predicate = text[predicate_start:predicate_end].strip()
        action = _action(predicate)
        if action is None:
            result["blockers"].append({"reason": "prose_predicate_role_unsupported", "source": _source(source, predicate_start, predicate_end), "text": predicate})
            continue
        action_match = re.match(r"\s+".join(re.escape(word) for word in action.split()) + r"\b", predicate, re.I)
        if action_match is None:
            result["blockers"].append({"reason": "prose_predicate_source_unsupported",
                "source": _source(source, predicate_start, predicate_end), "text": predicate})
            continue
        action_end = predicate_start + action_match.end()
        object_start = action_end
        while object_start < predicate_end and text[object_start].isspace():
            object_start += 1
        fact = {"subject": _subject(printed_subject), "attribute": action, "value": predicate, "role": "description",
                "qualifiers": q, "identity_facets": {}, "scope": list(scope), "source": _source(source, start, end),
                "value_source": _source(source, predicate_start, predicate_end), "qualifier_sources": q_sources,
                "subject_source": _source(source, subject_start, subject_end), "printed_label": label,
                "predicate": text[predicate_start:action_end],
                "predicate_source": _source(source, predicate_start, action_end),
                "attribute_source": _source(source, predicate_start, action_end),
                "object": text[object_start:predicate_end], "object_source": _source(source, object_start, predicate_end),
                "logic": {"kind": "modal_assertion", "action": action,
                          "coordination": "and" if " and " in action else None}}
        result["facts"].append(fact)
        if fact["logic"]["coordination"]:
            result["pending_requirements"].append({"kind": "coordinated_modal_actions", "operator": "and",
                "subject": fact["subject"], "actions": action.split(" and "), "predicate": predicate,
                "qualifiers": copy.deepcopy(q), "source": copy.deepcopy(fact["source"])})
            result["blockers"].append({"reason": "coordinated_action_granularity_unsupported",
                                       "source": copy.deepcopy(fact["source"]), "layers": ["B"]})
    for blocker in result["blockers"]:
        blocker.setdefault("layers", ["B"])
    record, record_evidence, context_blockers = _record_context(parents, source)
    if result["matched"]:
        result["blockers"].extend(context_blockers)
    field_source = None
    if label_prefix:
        start = text.find(label, label_prefix.start(), label_prefix.end())
        field_source = _source(source, start, start + len(label))
    elif label and isinstance(label_source, dict) and label_source.get("path"):
        field_source = copy.deepcopy(label_source)
    for fact in result["facts"]:
        if label_prefix:
            fact["label_source"] = _source(source, label_prefix.start(), label_prefix.end())
        elif field_source:
            fact["label_source"] = copy.deepcopy(field_source)
        if field_source:
            fact["field_label_evidence"] = {"text": label, "source": copy.deepcopy(field_source),
                                             "role": "printed_field_label"}
            if not fact["scope"] or fact["scope"][-1] != label:
                fact["scope"].append(label)
        if record:
            fact["identity_facets"]["record"] = copy.deepcopy(record)
            fact["record_evidence"] = copy.deepcopy(record_evidence)
        for relation in [*prose_scope_relations(fact), *prose_role_relations(fact)]:
            relation["id"] = f"L:prose_scope:{len(result['relations'])}"
            result["relations"].append(relation)
    result["text_spans"] = [{"text": text, "span": [0, len(text)], "role": "original_prose", "source": _source(source, 0, len(text))}]
    return result


def prose_endpoint(text: str, source: dict[str, Any], *, scope: tuple[str, ...] | list[str] = (),
                   identifier: str | None = None, label: str | None = None,
                   label_source: dict[str, Any] | None = None, parents=()) -> dict[str, Any]:
    """Locate a prose object using its roles, never the amount being tested."""
    ordinal = _ORDINAL.match(text)
    body = text[ordinal.end():] if ordinal else text
    body_source = _source(source, ordinal.end(), len(text)) if ordinal else source
    parsed = read_prose_requirements(body, body_source, scope=scope, label=label, label_source=label_source, parents=parents)
    facts = parsed["facts"]
    if len(facts) == 1:
        item = facts[0]
        identity = {"subject": item["subject"], "action": item["attribute"],
                    "modal": item["qualifiers"].get("modality"), "ordinal": (ordinal[1] or ordinal[2]) if ordinal else None}
        if item.get("identity_facets"):
            identity["identity_facets"] = copy.deepcopy(item["identity_facets"])
        scope = item["scope"]
    else:
        identity = {"lexical_anchor": _skeleton(body), "ordinal": (ordinal[1] or ordinal[2]) if ordinal else None}
    # The finite measurement reader already binds the printed period to all
    # clauses in this one sequence. Removing every numeral for a prose anchor
    # erased that independent identity and collided across different years.
    # Reuse its complete local interpretation; tested quantities and units do
    # not choose a prose endpoint or enter this identity.
    from .cjk_measurement_requirements import read_cjk_measurements

    measurements = read_cjk_measurements(body, body_source, scope=scope)
    if not measurements['complete']:
        from .cjk_circumstances import trailing_cause

        cause = trailing_cause(body)
        if cause and (cause['marker'] in {'归因于', '歸因於'} or body[cause.start()] == '。'):
            prefix = read_cjk_measurements(body[:cause.start()], _source(body_source, 0, cause.start()), scope=scope)
            if prefix['complete']:
                measurements = prefix
    period_evidence = None
    if measurements["complete"] and (period := measurements["logic"][0].get("period")):
        identity = {"metric_roles": [
            {"subject": clause["subject"], "predicate_kind": clause["kind"]}
            for clause in measurements["logic"][0]["clauses"]],
            "period": period["text"], "ordinal": (ordinal[1] or ordinal[2]) if ordinal else None}
        period_evidence = copy.deepcopy(period)
    elif not measurements['complete']:
        from .temporal_prose_requirements import read_cjk_temporal

        temporal = read_cjk_temporal(body, body_source, 0, len(body))
        if temporal and 'period' in temporal['qualifiers']:
            identity['period'] = temporal['qualifiers']['period']
            period_evidence = {'text': temporal['qualifiers']['period'],
                               'source': temporal['qualifier_sources']['period']}
    return {"id": identifier, "identity": identity, "scope": list(scope), "text": text,
            "source": copy.deepcopy(source), "content_slots": [{"span": [match.start() + (ordinal.end() if ordinal else 0), match.end() + (ordinal.end() if ordinal else 0)],
                                                                 "text": match[0], "source": _source(body_source, match.start(), match.end())}
                                                                 for match in _QUANTITY.finditer(body)],
            "context_blockers": [copy.deepcopy(item) for item in parsed["blockers"] if item["reason"].startswith("prose_context_")],
            **({"period_identity_evidence": period_evidence} if period_evidence else {}),
            **{key: copy.deepcopy(facts[0][key]) for key in ("field_label_evidence", "record_evidence")
               if len(facts) == 1 and key in facts[0]}}


def read_prose_sequence(units: list[dict[str, Any]], *, scope: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """Read ordinary prose sequence and explicit parent references in place."""
    from .explicit_reference_requirements import read_explicit_references

    result = _result()
    result.update(references=[], semantic_roles=[], source_dispositions=[], required_matcher_features=[])
    headings = {unit["id"]: unit for unit in units if unit.get("kind") == "heading" and unit.get("id")}
    previous = {}
    for index, unit in enumerate(units):
        if unit.get('kind') == 'image_caption':
            # Captions keep their printed owner and occurrence capacity.
            # They cannot become an ordinary prose sentence or bridge two
            # paragraphs. No image content is inspected or interpreted.
            own_scope = list(unit.get('scope', scope))
            node = prose_endpoint(unit['text'], unit['source'], scope=own_scope, identifier=unit.get('id', f'caption:{index}'))
            node['kind'] = 'image_caption'
            node['identity'] = {'role': 'image_caption', 'caption': unit['text']}
            result['endpoints'].append(node)
            if own_scope:
                result['relations'].append({'id': f"L:prose:{len(result['relations'])}", 'type': 'prose_heading_membership',
                    'left': own_scope, 'right': {'identity': copy.deepcopy(node['identity']), 'scope': own_scope},
                    'source': copy.deepcopy(unit['source']), 'scope_evidence': {'kind': 'unit_declared_scope', 'scope': own_scope,
                        'sources': copy.deepcopy(unit.get('scope_sources', [unit['source']]))}})
            previous.clear()
            continue
        if unit.get("kind", "paragraph") not in {"paragraph", "prose", "text"}:
            previous.clear()
            continue
        if not unit.get("text", "").strip():
            previous.clear()
            continue
        own_scope = list(unit.get("scope", scope))
        parent = unit.get("parent_id")
        if parent is not None:
            if parent not in headings:
                result["blockers"].append({"reason": "prose_parent_reference_unresolved", "source": copy.deepcopy(unit["source"]), "parent_id": parent, "layers": ["L"]})
                previous.clear()
                continue
            heading = headings[parent]
            own_scope = [*heading.get("scope", []), heading["text"]]
        node = prose_endpoint(unit["text"], unit["source"], scope=own_scope, identifier=unit.get("id", f"prose:{index}"),
                              label=unit.get("label", unit.get("printed_label")), label_source=unit.get("label_source"),
                              parents=unit.get("parents", ()))
        own_scope = node["scope"]
        reference_owner = unit.get("reference_owner")
        reference_owner_evidence = unit.get("reference_owner_evidence", ())
        label = unit.get("label", unit.get("printed_label"))
        label_source = unit.get("label_source")
        if reference_owner is None and label and isinstance(label_source, dict):
            reference_owner = {"identity": {"role": "printed_field", "attribute": label}, "scope": list(own_scope)}
            reference_owner_evidence = [{"kind": "printed_field_label", "text": label, "source": copy.deepcopy(label_source)}]
        references = read_explicit_references(unit["text"], unit["source"], scope=own_scope,
                                              owner=reference_owner, owner_evidence=reference_owner_evidence)
        if references["matched"]:
            result["references"].extend(copy.deepcopy(references["references"]))
            result["semantic_roles"].extend(copy.deepcopy(references["semantic_roles"]))
            result["source_dispositions"].extend(copy.deepcopy(references["source_dispositions"]))
            result["blockers"].extend(copy.deepcopy(references["blockers"]))
            result["pending_requirements"].extend(copy.deepcopy(references["pending_requirements"]))
            result["required_matcher_features"] = sorted(set(result["required_matcher_features"]) | set(references["required_matcher_features"]))
            for relation in references["relations"]:
                result["relations"].append({"id": f"L:prose_reference:{len(result['relations'])}", **copy.deepcopy(relation)})
            spans = [reference["source"]["text_span"] for reference in references["references"]]
            node["content_slots"] = [slot for slot in node["content_slots"]
                                     if not any(a <= slot["source"]["text_span"][0] and slot["source"]["text_span"][1] <= b
                                                for a, b in spans)]
            if not references["residual_spans"]:
                node["identity"] = {"role": "reference_directive",
                                    "directive_kinds": [reference["directive_kind"] for reference in references["references"]]}
                proofs = [reference["owner_proof"] for reference in references["references"]]
                if proofs and all(proof and proof["owner"] == proofs[0]["owner"] for proof in proofs):
                    node["identity"]["owner"] = copy.deepcopy(proofs[0]["owner"])
            elif "lexical_anchor" in node["identity"]:
                node["identity"]["lexical_anchor"] = _skeleton(" ".join(part["text"] for part in references["residual_spans"]))
        result["blockers"].extend(copy.deepcopy(node["context_blockers"]))
        result["endpoints"].append(node)
        endpoint = {"identity": copy.deepcopy(node["identity"]), "scope": own_scope}
        scope_evidence = ({"kind": "explicit_parent_reference", "parent_id": parent,
                           "text": headings[parent]["text"], "source": copy.deepcopy(headings[parent]["source"])} if parent is not None
                          else {"kind": "unit_declared_scope", "scope": own_scope,
                                "sources": copy.deepcopy(unit.get("scope_sources", [unit["source"]]))})
        if own_scope:
            result["relations"].append({"id": f"L:prose:{len(result['relations'])}", "type": "prose_heading_membership",
                                         "left": own_scope, "right": endpoint, "source": copy.deepcopy(unit["source"]),
                                         "scope_evidence": scope_evidence})
            for key in ("field_label_evidence", "record_evidence"):
                if node.get(key):
                    result["relations"][-1][key] = copy.deepcopy(node[key])
        key = (tuple(own_scope), repr(node["identity"].get("identity_facets", {})))
        if previous and key not in previous:
            previous.clear()
        if key in previous:
            result["relations"].append({"id": f"L:prose:{len(result['relations'])}", "type": "prose_reading_order",
                                         "left": previous[key], "right": endpoint, "source": copy.deepcopy(unit["source"])})
            for context_key in ("field_label_evidence", "record_evidence"):
                if node.get(context_key):
                    result["relations"][-1][context_key] = copy.deepcopy(node[context_key])
        previous[key] = endpoint
    counts = Counter(repr((node["identity"], node["scope"])) for node in result["endpoints"] if node.get('kind') != 'image_caption')
    for node in result["endpoints"]:
        if node.get('kind') != 'image_caption' and counts[repr((node["identity"], node["scope"]))] > 1:
            result["blockers"].append({"reason": "prose_endpoint_role_collision", "source": node["source"], "identity": node["identity"]})
    for blocker in result["blockers"]:
        blocker.setdefault("layers", ["L"])
    result["matched"] = bool(result["endpoints"])
    return result
