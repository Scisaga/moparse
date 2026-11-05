"""Finite, source-only active perfect/progressive clauses.

Only declared verb forms are recognized. There is no stem guessing, passive
conversion, omitted actor, answer lookup, or interpretation of unbound PP,
purpose or relative-clause text as an opaque object.
"""

from __future__ import annotations

import re

_AUXILIARY = re.compile(r"\b(?:have|has|had|am|is|are|was|were)\b", re.I)
_WORD = re.compile(r"[A-Za-z]+\b")
_JOIN = re.compile(r"\s+(?P<operator>and|or)\s+(?P<next>[A-Za-z]+)\b", re.I)
_EMBEDDED = re.compile(r"\b(?:in|on|at|for|from|with|within|under|by|about|into|over|through|against|"
                       r"between|among|toward|towards|during|before|after|as|of|to|that|which|who|"
                       r"because|although|whereas|while|whether)\b|[:：;；]", re.I)
# General lexical declarations, not source-document or answer substitutions.
_EXTRA_FORMS = {
    "make": ("made", "making"), "invest": ("invested", "investing"),
    "sharpen": ("sharpened", "sharpening"), "strengthen": ("strengthened", "strengthening"),
    "expand": ("expanded", "expanding"), "improve": ("improved", "improving"),
    "reduce": ("reduced", "reducing"), "increase": ("increased", "increasing"),
    "implement": ("implemented", "implementing"), "complete": ("completed", "completing"),
    "prepare": ("prepared", "preparing"), "perform": ("performed", "performing"),
    "retain": ("retained", "retaining"), "obtain": ("obtained", "obtaining"),
    "achieve": ("achieved", "achieving"), "run": ("run", "running"),
}


def active_forms():
    """Return fixed verb forms shared with the ordinary narrative vocabulary."""
    from .narrative_requirements import _ACTIONS, _PAST

    perfect = {word: base for word, base in _ACTIONS.items() if word in _PAST and base not in {"be", "have"}}
    progressive = {}
    for base in set(_ACTIONS.values()) - {"be", "have"}:
        printed = base[:-2] + "ying" if base.endswith("ie") else base[:-1] + "ing" if base.endswith("e") and not base.endswith("ee") else base + "ing"
        progressive[printed] = base
    for base, (participle, ing) in _EXTRA_FORMS.items():
        perfect[participle], progressive[ing] = base, base
    return perfect, progressive


def read_active_aspect_clause(reader, start, end, actor=None):
    """Read this caller's original text using its ordinary nominal boundaries.

    ``None`` leaves lexical HAVE and ordinary copulas with their existing
    reader. A recognized but unsupported construction raises that reader's
    normal unknown result and preserves the original whole source.
    """
    from .narrative_requirements import _PRIMARY, _VERB, _Unknown

    text = reader.text
    auxiliary = _AUXILIARY.search(text, start, end) if actor is None else _AUXILIARY.match(text, start, end)
    if auxiliary is None:
        return None
    if actor is None:
        finite = [match for expression in (_PRIMARY, _VERB) if (match := expression.search(text, start, end))]
        if finite and min(match.start() for match in finite) < auxiliary.start():
            return None
    cursor = auxiliary.end()
    while cursor < end and text[cursor].isspace():
        cursor += 1
    negation = re.match(r"(?:not|never)\b\s*", text[cursor:end], re.I)
    negative_span = [cursor, cursor + len(negation[0].rstrip())] if negation else None
    if negation:
        cursor += negation.end()
    first = _WORD.match(text, cursor, end)
    if first is None:
        return None
    perfect, progressive = active_forms()
    aux, printed = auxiliary[0].casefold(), first[0].casefold()
    aspect = "perfect" if aux in {"have", "has", "had"} else "progressive"
    forms = perfect if aspect == "perfect" else progressive
    if printed not in forms:
        if aux in {"am", "is", "are", "was", "were"} and printed in perfect:
            raise _Unknown("active_aspect_passive_or_adjectival_participle_unresolved")
        unknown_form = re.search(r"(?:ed|en|ing)$" if aspect == "perfect" else r"ing$", printed)
        if printed in perfect or printed in progressive or unknown_form:
            raise _Unknown("active_aspect_participle_form_unresolved")
        if printed.endswith("ly") and re.search(r"\b(?:" + "|".join(perfect) + r")\b", text[first.end():end], re.I):
            raise _Unknown("active_aspect_adverb_attachment_unresolved")
        return None
    if aux not in {"have", "has", "is", "are"}:
        raise _Unknown("active_aspect_auxiliary_tense_unresolved")
    reader.features.add("active_aspect_scope")
    if actor is None:
        actor = reader.nominal(start, auxiliary.start(), actor=True)
    joins = []
    for join in _JOIN.finditer(text, cursor, end):
        following = join["next"].casefold()
        looks_active = following in perfect or following in progressive or bool(re.search(r"(?:ed|en|ing)$", following))
        if not looks_active:
            continue
        if following not in forms:
            raise _Unknown("active_aspect_coordinated_form_unresolved")
        if join["operator"].casefold() != "and":
            raise _Unknown("active_aspect_action_disjunction_unresolved")
        joins.append(join)
    if joins and negative_span:
        raise _Unknown("active_aspect_negated_coordination_unresolved")
    chunks, previous = [], cursor
    for join in joins:
        chunks.append((previous, join.start()))
        previous = join.start("next")
    chunks.append((previous, end))

    def predicate(a, b, shared=None):
        a, b = reader.trim(a, b)
        word = _WORD.match(text, a, b)
        if word is None or word[0].casefold() not in forms:
            raise _Unknown("active_aspect_participle_form_unresolved")
        lo, hi = reader.trim(word.end(), b)
        if lo == hi and shared is not None:
            lo, hi = shared
        if lo == hi:
            raise _Unknown("active_aspect_object_unresolved")
        if _EMBEDDED.search(text[lo:hi]) or _AUXILIARY.search(text, lo, hi):
            raise _Unknown("active_aspect_embedded_scope_unresolved")
        spans, operator, separators = reader.objects(lo, hi)
        if operator == "or" or (negative_span and operator):
            raise _Unknown("active_aspect_object_coordination_unresolved")
        children = []
        for x, y in spans:
            reader.nominal(x, y)
            children.append({"kind": "proposition", "subject": text[slice(*actor)], "subject_span": list(actor),
                "predicate": word[0], "predicate_span": [word.start(), word.end()], "attribute": forms[word[0].casefold()],
                "object": text[x:y], "object_span": [x, y], "role": "description", "span": [min(actor[0], a), max(b, y)]})
        return children[0] if len(children) == 1 else {"kind": "coordination", "operator": "and", "mode": "objects",
            "children": children, "operator_spans": separators, "span": [a, b]}

    last = predicate(*chunks[-1])
    shared = last["object_span"] if last["kind"] == "proposition" else None
    children = [predicate(a, b, shared) for a, b in chunks[:-1]] + [last]
    child = children[0] if len(children) == 1 else {"kind": "coordination", "operator": "and", "mode": "actions",
        "children": children, "operator_spans": [[join.start(), join.start("next")] for join in joins], "span": [cursor, end]}
    if negative_span:
        child = {"kind": "negation", "operator_span": negative_span, "child": child, "span": [start, end]}
    return {"kind": "active_aspect", "aspect": aspect, "tense": "present", "auxiliary": auxiliary[0],
            "aspect_span": [auxiliary.start(), auxiliary.end()], "tense_span": [auxiliary.start(), auxiliary.end()],
            "child": child, "span": [start, end]}
