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


def original_source_cuts(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Project one analysis interval into unchanged, local character ranges.

    Joined coordinates are relative to the first fragment's original start.
    Inserted separators have no source. Whitespace projection can change its
    length, so copying a joined offset into another original is insufficient.
    Literal/source authentication remains the owning graph/evidence check.
    """
    fragments = source.get('joined_fragments')
    if not fragments:
        return [copy.deepcopy(source)]
    if not isinstance(fragments, list) or len(fragments) < 2:
        raise ValueError('joined source requires its complete original fragments')
    first = fragments[0]['source']
    if any(source.get(k) != first.get(k) for k in ('path', 'lines', 'cell', 'block', 'native_path')):
        raise ValueError('joined source differs from its first original identity')
    cursor, previous, layout = 0, '', []
    for fragment in fragments:
        raw = fragment.get('text')
        text = fragment.get('projected_text', raw)
        span = fragment.get('joined_span')
        origin = fragment.get('source', {})
        if not isinstance(raw, str) or not isinstance(text, str) or not text:
            raise ValueError('joined source lacks original and projected wording')
        gap = (0 if re.search(r'[\u3400-\u9fff]$', previous) and re.match(r'[\u3400-\u9fff]', text) else 1) if layout else 0
        if span != [cursor + gap, cursor + gap + len(text)]:
            raise ValueError('joined source has an invalid separator or interval')
        positions = [(i, char) for i, char in enumerate(raw) if not char.isspace()]
        projected = [(i, char) for i, char in enumerate(text) if not char.isspace()]
        if ([char for _, char in positions] != [char for _, char in projected]
                or re.sub(r'\s+', ' ', raw).strip() != re.sub(r'\s+', ' ', text).strip()):
            raise ValueError('joined source changed original non-whitespace content')
        bounds = origin.get('text_span', [0, len(raw)])
        if (len(bounds) != 2 or any(type(n) is not int for n in bounds)
                or bounds[0] < 0 or bounds[1] - bounds[0] != len(raw)):
            raise ValueError('joined original interval differs from its actual wording')
        layout.append((origin, bounds[0], raw, text, span, dict(zip(
            (i for i, _ in projected), (i for i, _ in positions), strict=True))))
        cursor, previous = span[1], text
    base = first.get('text_span', [0])[0]
    cut = source.get('text_span', [base, base + cursor])
    if (len(cut) != 2 or any(type(n) is not int for n in cut)
            or not 0 <= cut[0] - base <= cut[1] - base <= cursor):
        raise ValueError('joined analysis cut lies outside its original expression')
    a, b = cut[0] - base, cut[1] - base
    result = []
    for origin, offset, raw, text, (start, end), points in layout:
        lo, hi = max(start, a) - start, min(end, b) - start
        if lo >= hi:
            continue
        if lo == 0:
            left = 0
        elif text[lo].isspace():
            left = max((v + 1 for k, v in points.items() if k < lo), default=0)
        else:
            left = points[lo]
        if hi == len(text):
            right = len(raw)
        elif text[hi - 1].isspace():
            right = min((v for k, v in points.items() if k >= hi), default=len(raw))
        else:
            right = points[hi - 1] + 1
        result.append({**copy.deepcopy(origin), 'text_span': [offset + left, offset + right]})
    return result


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
    # Printed CJK sentence clauses are not an atomic field value merely
    # because their verbs are outside the bounded semantic reader. Keep the
    # label and the entire body for content preservation and retain analysis
    # limits; this route does not certify a new subject/predicate reading.
    printed_clauses = (bool(re.search(r'[\u3400-\u9fff]', body))
                       and bool(re.search(r'[,，;；]', body))
                       and bool(re.search(r'[。！？][」』”）)]*$', body)))
    if printed_clauses:
        from .compact_requirements import read_compact_schema
        from .field_sequence_requirements import read_labelled_record
        from .series_requirements import _CAUSE

        # An explicit column inventory or a closed scalar record keeps its
        # existing reader. Its separators do not make it narrative prose.
        printed_clauses = not (read_compact_schema(text, source)['matched']
                               or read_labelled_record(text, source)['matched']
                               or _CAUSE.fullmatch(label))
    if not (_BODY_ROLE.fullmatch(label) or printed_clauses or read_propositions(body, source)["matched"]
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
    from .series_requirements import _CAUSE

    if (re.match(r'(?:19|20)\d{2}年', fields[0][2].strip())
            and any(field is not None and _CAUSE.fullmatch(field[1].strip()) for field in fields[1:])):
        return None  # One annual financial series retains its trailing reason.
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
