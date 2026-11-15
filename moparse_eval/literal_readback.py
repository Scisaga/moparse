"""Candidate-only literal views with capacity in the original occurrences.

These are reading alternatives, not additional printed text or business facts.
The original complete units remain available. A view can only consume its own
contiguous interval; using a child prevents reuse of that part by its parent.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter, defaultdict

from rapidfuzz.distance import Levenshtein

from .prose_requirements import _RECORD_IDENTITY, _sentence_spans


def _identity(source):
    return json.dumps({k: source[k] for k in
        ("path", "page", "lines", "block", "block_lines", "cell", "row", "col", "native_path")
        if k in source}, sort_keys=True, ensure_ascii=False)


def _parts(atom):
    sources = atom.get("source_fragments")
    if sources:
        texts = atom.get("source_fragment_texts")
        if texts is None:
            texts = atom.get("strict_text", "").split("\n")
        if len(sources) == len(texts):
            return list(zip(sources, texts, strict=True))
    return [(atom["source"], atom.get("strict_text", atom["text"]))]


def _capacity(atom, source, start, end):
    if atom.get("projection_kind") == "bounded_alias":
        # A printed schema term can have one existing alias per data object.
        key = "alias:" + atom["alias_key"]
        offset = 0
    else:
        key = _identity(source)
        offset = source.get("cell_text_span", source.get("text_span", [0]))[0]
    return {"key": key, "span": [offset + start, offset + end]}


def _boundaries(text, atom, attribute):
    """Cuts depend on the candidate's complete grammar, never a search string."""
    cuts = set(_sentence_spans(text))
    # A whole balanced parenthetical label/value is readable without asserting
    # any field, entity, address, or other B/L interpretation. Keep its brackets.
    pairs = {"(": ")", "（": "）", "[": "]"}
    if text[:1] in pairs and text[-1:] == pairs[text[0]]:
        inner = text[1:-1]
        match = re.fullmatch(r"([^:：=;；\n()（）\[\]]+)[:：=]\s*([^:：=;；\n()（）\[\]]+)", inner)
        if match:
            cuts.update((1 + match.start(n), 1 + match.end(n)) for n in (1, 2))
    # A displayed list record can print a complete row path in its own value.
    # Spaced slashes here are local path boundaries, never ordinary URLs/codes.
    if (atom.get("syntax_kind") == "parent_label" and atom["source"].get("attribute_source")
            and " / " in text and "://" not in text and "@" not in text
            and not _RECORD_IDENTITY.fullmatch(attribute)):
        start = 0
        for match in re.finditer(r" / ", text):
            cuts.add((start, match.start()))
            start = match.end()
        cuts.add((start, len(text)))
    return sorted(cuts)


def text_readback(atoms):
    """Expose whole units and their own bounded fragments before comparison.

    All intervals share the original occurrence capacity. No additional window
    is made across blocks, intervening text, lists, headings, tables, or media.
    """
    views = []
    labels = {json.dumps(atom["source"], sort_keys=True): atom["text"]
              for atom in atoms if atom.get("role") == "label"}
    for atom in atoms:
        attribute = labels.get(json.dumps(atom["source"].get("attribute_source"), sort_keys=True), "")
        parts = _parts(atom)
        capacity = [_capacity(atom, source, 0, len(text)) for source, text in parts]
        views.append({"atom": copy.deepcopy(atom), "capacity": capacity,
                      "parent": atom["id"], "kind": "whole"})
        seen = {json.dumps(capacity, sort_keys=True)}
        serial = 0
        for source, text in parts:
            for start, end in sorted({(0, len(text)), *_boundaries(text, atom, attribute)}):
                while start < end and text[start].isspace():
                    start += 1
                while end > start and text[end - 1].isspace():
                    end -= 1
                if start == end:
                    continue
                if len(parts) == 1 and text[start:end] == atom["text"].strip():
                    # Trimming the outside of one occurrence is not a second
                    # identity. Keep the original unit and its strict spaces.
                    continue
                bounds = [_capacity(atom, source, start, end)]
                key = json.dumps(bounds, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                local_source = copy.deepcopy(source)
                offset = source.get("text_span", [0])[0]
                local_source["text_span"] = [offset + start, offset + end]
                if "cell_text_span" in source:
                    offset = source["cell_text_span"][0]
                    local_source["cell_text_span"] = [offset + start, offset + end]
                own = {key: copy.deepcopy(atom[key]) for key in
                       ("role", "scope", "syntax_kind", "continuity_segment", "list_item_source") if key in atom}
                own.update(id=atom["id"] + ":readback:" + str(serial), text=text[start:end],
                           source=local_source)
                serial += 1
                views.append({"atom": own, "capacity": bounds, "parent": atom["id"],
                              "kind": "own_contiguous_fragment"})
    return {"views": views, "expected_access": False,
            "capacity": "original_occurrence_intervals_and_existing_bounded_aliases"}


def overlaps(left, right):
    return any(a["key"] == b["key"] and max(a["span"][0], b["span"][0]) < min(a["span"][1], b["span"][1])
               for a in left for b in right)


def _order(atom):
    # Physical source order, not the order in which a caller traversed arrays.
    source = atom["source"]
    natural_path = tuple((1, int(part)) if part.isdigit() else (0, part)
                         for part in re.split(r"(\d+)", str(source.get("path", ""))))
    return (source.get("page") if type(source.get("page")) is int else -1,
            tuple(source.get("lines", [])), natural_path,
            tuple(source.get("text_span", [])), str(atom.get("alias_key", atom["id"])))


def match_text(reference, candidate, reading, *, canonicalize, edit):
    """Use the existing exact-first / 0.35 whole-view retrieval policy.

    Partial views are candidate-authored grammar cuts. The threshold is never
    applied to arbitrary reference-selected substrings. Capacity is shared by
    overlapping alternatives and exact matching still precedes fuzzy matching.
    """
    rebuilt = text_readback(candidate)
    if reading != rebuilt:
        raise ValueError("literal readback differs from its candidate-only original occurrences")
    views = reading["views"]
    normalized = [canonicalize(v["atom"]["text"]) for v in views]
    wanted = [canonicalize(r["text"]) for r in reference]
    exact_index = defaultdict(list)
    for j, value in enumerate(normalized):
        exact_index[value].append(j)
    required_counts = Counter(wanted)
    used, matches, ambiguous, retrieval = [], {}, {}, {}
    occupied = defaultdict(list)
    scored = defaultdict(lambda: defaultdict(list))
    required_order = [_order(r) for r in reference]
    candidate_order = [_order(v["atom"]) for v in views]
    indices = sorted(range(len(reference)), key=lambda i: (-len(wanted[i]), required_order[i]))

    def free(j):
        return not any(max(a["span"][0], start) < min(a["span"][1], end)
                       for a in views[j]["capacity"] for start, end in occupied[a["key"]])

    def prefer(i, hits):
        if len(hits) < 2:
            return hits
        item = reference[i]
        # Only break a repeated-text tie using metadata actually printed by
        # both sides. This is a locator preference, never an L/B acceptance.
        for key in ("syntax_kind", "scope"):
            own = [j for j in hits if item.get(key) and views[j]["atom"].get(key) == item[key]]
            if own:
                hits = own
        # Whole/child representations of the very same range are one choice.
        unique = {}
        for j in hits:
            key = json.dumps(views[j]["capacity"], sort_keys=True)
            unique.setdefault(key, j)
        return list(unique.values())

    def take(i, j):
        matches[i] = j
        used.extend(views[j]["capacity"])
        for part in views[j]["capacity"]:
            occupied[part["key"]].append(part["span"])

    for i in indices:
        if i in matches:
            continue
        exact = exact_index[wanted[i]]
        catalogue = [{"id": views[j]["atom"]["id"], "similarity": 1.0,
                      "capacity_available": free(j), "source": views[j]["atom"]["source"]}
                     for j in exact]
        retrieval[i] = catalogue
        hits = prefer(i, [j for j in exact if free(j)])
        if len(hits) == 1:
            take(i, hits[0])
        elif hits:
            # Repeated literals with no surplus of distinct printed occurrences
            # retain the existing source-order capacity assignment and deficit.
            # This proves literal multiplicity only, never unique business IDs.
            repeated = [k for k in indices if wanted[k] == wanted[i] and k not in matches]
            disjoint = (required_counts[wanted[i]] > 1 and len(repeated) >= len(hits)
                        and all(not overlaps(views[a]["capacity"], views[b]["capacity"])
                                for a in hits for b in hits if a != b))
            if disjoint:
                for k, j in zip(sorted(repeated, key=lambda k: required_order[k])[:len(hits)],
                                sorted(hits, key=lambda j: candidate_order[j]), strict=True):
                    retrieval[k] = copy.deepcopy(catalogue)
                    take(k, j)
            else:
                ambiguous[i] = hits

    possibilities = []
    for i in indices:
        if i in matches:
            continue
        hits = []
        for j, value in enumerate(normalized):
            similarity = Levenshtein.normalized_similarity(wanted[i], value)
            if similarity >= 0.35:
                scored[i][-similarity].append(j)
                hits.append({"id": views[j]["atom"]["id"], "similarity": similarity,
                             "capacity_available": free(j), "source": views[j]["atom"]["source"]})
                if free(j):
                    possibilities.append((-similarity, required_order[i], i, j))
        retrieval[i] = hits
    for neg_similarity, _, i, j in sorted(possibilities):
        if i in matches or i in ambiguous or not free(j):
            continue
        tied = prefer(i, [k for k in scored[i][neg_similarity] if free(k)])
        if len(tied) > 1:
            # The owning T contract retains source-order ties for non-exact
            # Levenshtein retrieval. It is not a semantic identity proof.
            if any(views[k]["kind"] != "whole" for k in tied):
                ambiguous[i] = tied
            else:
                take(i, min(tied, key=lambda k: candidate_order[k]))
        elif tied:
            take(i, tied[0])

    rows, totals = [], Counter()
    located = 0
    blockers = []
    for i, item in enumerate(reference):
        view = views[matches[i]] if i in matches else None
        actual = copy.deepcopy(view["atom"]) if view else None
        a, b = wanted[i], canonicalize(actual["text"]) if actual else ""
        edits = edit(a, b)
        strict = edit(item.get("strict_text", item["text"]),
                      actual.get("strict_text", actual["text"]) if actual else "")
        totals.update(edits)
        located += len(a) if actual else 0
        state = "ambiguous" if i in ambiguous and not actual else "located" if actual else "unlocated"
        proof = {"status": state, "absence_proven": False,
                 "method": "candidate_grammar_views_exact_first_capacity_one",
                 "candidates": retrieval.get(i, []),
                 "ambiguous_candidates": [views[j]["atom"] for j in ambiguous.get(i, [])],
                 "consumed_capacity": copy.deepcopy(view["capacity"]) if view else []}
        if state == "ambiguous":
            blockers.append({"reason": "literal_correspondence_ambiguous", "source": item["source"], "layers": ["T"]})
        rows.append({"id": item["id"], "layer": "T", "role": "literal", "expected": copy.deepcopy(item),
                     "actual": actual, "outcome": "unresolved" if state == "ambiguous" else "correct" if a == b else "incorrect",
                     "edits": edits, "strict_edits": strict, "source": copy.deepcopy(item["source"]),
                     "root_cause": "literal:" + item["id"], "correspondence": proof})
    # Retain every unconsumed character, including inserted conditions, numbers,
    # brackets, extra paragraphs and the remainder beside a matched child.
    extras = []
    for atom in candidate:
        for source, text in _parts(atom):
            own = _capacity(atom, source, 0, len(text))
            spans = [(max(own["span"][0], c["span"][0]) - own["span"][0],
                      min(own["span"][1], c["span"][1]) - own["span"][0]) for c in used
                     if c["key"] == own["key"] and overlaps([own], [c])]
            cursor = 0
            for start, end in sorted(spans) + [(len(text), len(text))]:
                if cursor < start and text[cursor:start].strip():
                    extras.append({"id": atom["id"] + ":unconsumed:" + str(cursor), "text": text[cursor:start],
                                   "source": copy.deepcopy(source), "local_span": [cursor, start]})
                cursor = max(cursor, end)
    denominator = sum(map(len, wanted))
    numerator = denominator - sum(totals.values())
    complete = not blockers
    return {"numerator": numerator, "denominator": denominator,
            "score": 100 * max(0, numerator) / denominator if denominator and complete else None,
            "complete": complete, **{key: totals[key] for key in ("S", "D", "I")},
            "located_units": len(matches), "required_units": len(reference), "located_characters": located,
            "unadjudicated_extra_units": extras, "blockers": blockers,
            "full_scope_edit_rate": sum(totals.values()) / denominator if denominator else None}, rows
