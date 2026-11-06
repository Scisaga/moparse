"""Plan independently printed field and assertion fragments before interpretation."""

from __future__ import annotations

import copy
import re
from typing import Any

_PAIR = re.compile(r"\s*([^:：=\n]{1,160})\s*[:：=]\s*(.*?)\s*", re.S)
_ATOMIC_ROLE = re.compile(
    r"Name|Entity|Company|Subject|Identifier|ID|Code|Ticker|Role|Type|Market|Region|"
    r"Units?|Currency|Period|Year|Scope|Note|Condition|Exception|"
    r"名称|姓名|主体|公司名称|证券代码|证券简称|类型|职务|市场|地区|"
    r"单位|币种|期间|年度|口径|附注|条件|例外", re.I)
_BODY_ROLE = re.compile(r"Description|Statement|Narrative|Policy|Requirement|"
                        r"描述|说明|說明|陈述|陳述|政策|要求", re.I)
_ASSERTED_LABEL = re.compile(
    r"\b(?:am|is|are|was|were|have|has|had|will|shall|must|should|cannot|owns?|owned|acquired|approved)\b"
    r"|[。！？!?]|(?:我们|本公司|本集团|管理层|董事会)(?:正在|已经|将|拟|计划|决定|宣布)|[为為]$", re.I)


def plan_field_body(text: str, source: dict[str, Any]) -> dict[str, Any] | None:
    """Expose an asserted field body before the scalar field reader sees it.

    An actual narrative parse or a printed narrative role selects this path;
    selection does not certify that the body has been fully interpreted.
    Atomic metadata, calendar values, URLs and their punctuation stay literal.
    """
    from .cjk_narrative_requirements import read_cjk_narrative
    from .explicit_reference_requirements import read_explicit_references
    from .narrative_requirements import read_narrative
    from .proposition_requirements import read_propositions
    from .series_requirements import is_ordinary_scalar_field, read_series_requirements

    match = _PAIR.fullmatch(text)
    if match is None:
        return None
    label, body = match[1].strip(), match[2].strip()
    la = match.start(1) + len(match[1]) - len(match[1].lstrip())
    va = match.start(2) + len(match[2]) - len(match[2].lstrip())
    opening = None
    for marker in ('**', '__'):
        if label.startswith(marker) and body.startswith(marker) and marker not in label[len(marker):]:
            opening = (la, la + len(marker))
            label, la = label[len(marker):], la + len(marker)
            body, va = body[len(marker):].lstrip(), va + len(marker) + len(body[len(marker):]) - len(body[len(marker):].lstrip())
            break
    if body.startswith('//'):
        return None  # A URI scheme colon cannot create a narrative field.
    references = read_explicit_references(body, source)
    reference_body = references["matched"] and bool(references["consumed_spans"] or references["unresolved"])
    if not body or _ATOMIC_ROLE.fullmatch(label) or _ASSERTED_LABEL.search(label) or (is_ordinary_scalar_field(label, body) and not reference_body):
        return None
    # Explicit period/scalar syntax is owned by the series reader even when a
    # printed change direction is also a finite narrative verb. Route by that
    # source schema, never by the vocabulary of a particular direction token.
    if not _BODY_ROLE.fullmatch(label) and read_series_requirements(text, source)["matched"]:
        return None
    # A multi-field record must be split by the balanced sequence planner.
    if re.search(r"[;；]\s*[^:：=;；]+[:：=]", body):
        return None
    if not (_BODY_ROLE.fullmatch(label) or read_propositions(body, source)["matched"]
            or read_narrative(body, source)["logic"] or read_cjk_narrative(body, source)["logic"] or reference_body):
        return None
    offset = source.get("text_span", [0])[0]

    def origin(a, b):
        return {**copy.deepcopy(source), "text_span": [offset + a, offset + b]}

    controls = [{"text": text[la + len(label):va], "source": origin(la + len(label), va),
                 "reason": "explicit_field_delimiter"}]
    if opening:
        controls.insert(0, {'text': text[slice(*opening)], 'source': origin(*opening), 'reason': 'balanced_field_label_emphasis'})
    return {"label": label, "body": body, "label_source": origin(la, la + len(label)),
            "body_source": origin(va, va + len(body)), "rule_id": "printed_compositional_field_body",
            "controls": controls}


def plan_mixed_source(text: str, source: dict[str, Any]) -> dict[str, Any] | None:
    """Split only a proved multi-field sequence, preserving all raw offsets.

    A semicolon in a lone Name, URL, or narrative field is not a record
    delimiter. Quoted and parenthesized material is never split here.
    Unknown unlabelled pieces are retained for interpretation, not discarded.
    """
    spans, separators, start, stack, quote = [], [], 0, [], None
    pairs = {"(": ")", "（": "）", "[": "]", "【": "】"}
    for index, char in enumerate(text):
        if quote:
            if char == quote and (not index or text[index - 1] != "\\"):
                quote = None
            continue
        if char in {'"', '“', '”'}:
            quote = '”' if char == '“' else char
        elif char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                return None
        elif not stack and char in ";；\n":
            spans.append((start, index))
            separators.append((index, index + 1))
            start = index + 1
    if quote or stack or not spans:
        return None
    spans.append((start, len(text)))
    trimmed = [(a + len(text[a:b]) - len(text[a:b].lstrip()), b - len(text[a:b]) + len(text[a:b].rstrip()))
               for a, b in spans if text[a:b].strip()]
    fields = [_PAIR.fullmatch(text[a:b]) for a, b in trimmed]
    # Two independently labelled fields prove a record sequence. This avoids
    # treating ordinary enumerations in a single field as independent facts.
    if not fields or not fields[0]:
        return None
    if sum(match is not None for match in fields) < 2:
        from .proposition_requirements import read_propositions

        if not any(field is None and read_propositions(text[a:b], source)["matched"]
                   for (a, b), field in zip(trimmed, fields, strict=True)):
            return None
    if any(field is None and re.match(r"(?:19|20)\d{2}年?\s*[+\-−(（]?\d", text[a:b])
           for (a, b), field in zip(trimmed, fields, strict=True)):
        return None  # A compact date/value tuple needs its own printed schema.
    if all(fields) and "\n" not in text and not any(
            plan_field_body(text[a:b], source) for a, b in trimmed):
        return None  # The existing single-record field reader owns this case.
    offset = source.get("text_span", [0])[0]

    def origin(a, b):
        return {**copy.deepcopy(source), "text_span": [offset + a, offset + b]}

    return {"rule_id": "explicit_mixed_field_assertion_sequence",
            "fragments": [{"text": text[a:b], "source": origin(a, b),
                           "syntax": "field" if field else "assertion"}
                          for (a, b), field in zip(trimmed, fields, strict=True)],
            "controls": [{"text": text[a:b], "source": origin(a, b), "reason": "explicit_record_sequence_separator"}
                         for a, b in separators]}
