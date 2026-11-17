"""Source-capacity AST correspondence for the explicit continuous contract.

No reader lives here. Both inputs have already been built independently. The
algorithm compares contiguous groups, keeps original order and consumes every
printed occurrence at most once. Values are masked before selecting a match.
"""

from __future__ import annotations

import copy
import re
from collections import Counter

from rapidfuzz.distance import Levenshtein

METHOD = "document-ast-continuous/1"
RULES = {
    "method": METHOD,
    "minimum_similarity": 0.35,
    "maximum_group": 8,
    "edit_costs": {"S": 1, "D": 1, "I": 1},
    "T": "100*max(0,1-(S+D+I)/N_expected); pool before clipping",
    "L": "equal explicit relation components within each original owner, including row/column/period axes",
    "B": "typed values exact; source clauses length weighted with protected-token gate",
    "retrieval": "value-masked text; scope and identity; original occurrence capacity",
    "ties": "B preserves critical payload/context ties; L may certify invariant relation components with a distinct-occurrence witness",
    "order": "actual serialized AST sequence, never Expected order",
    "limits": "reader errors and score-changing identity ties remain explicit",
    "typography": "B/L identity normalizes quote wrappers and CJK display seams; T stays literal",
    "projection": "candidate-own fragments and repeated printed page/title slots; no reference access",
    "field_identity": "same source-bound row/column/period axes, independent of scalar values",
    "legacy_coverage": "original owners retained; unowned source statements/scalars get fixed source owners",
    "native_grid_readback": "explicit column headers and numeric row syntax expose fields without entity-class prerequisites",
    "unknown_heading_depth": "only contiguous own heading suffixes support context; explicit conflicts remain conflicts",
    "restrictive_context": "added printed conditional/exception/limitation headings require the same owner's explicit support",
    "title_context": "own initial title and complete bilingual script fragments may express combined document ownership; active competing parents are retained",
    "table_context": "own adjacent short table labels provide local scope; original table boundaries and cell source order are retained",
    "identifiers": "phone/code/calendar values stay literal; explicit email tokens allow sentence delimiters, not missing characters",
    "field_views": "both sides derive their own row/column axes; currency locates columns, quantity scale remains a value contract",
}

_NUMBER = re.compile(r"[+\-−]?\d+(?:,\d{3})*(?:\.\d+)?")
_PROTECTED = re.compile(
    r"[+\-−]?\d+(?:,\d{3})*(?:\.\d+)?|[%‰<>≤≥=]"
    r"|人民币|人民幣|百万元|百萬元|亿元|億元|万元|萬元|美元|港元|元"
    r"|不得|不能|没有|沒有|不超过|不超過|至少|至多|以上|以下|不|仅|僅|必须|必須|若|如果|除非"
    r"|\b(?:not|no|unless|except|only|must|shall|may|if|before|after|and|or|USD|RMB|HKD)\b"
    r"|[\"“][^\"”\n]+[\"”]|[√☑☒]\s*(?:是|否|Yes|No)", re.I
)


def protected(text):
    """Printed critical tokens, in order; no business grammar is invented."""
    result = []
    for match in _PROTECTED.finditer(text):
        value = match[0].casefold()
        if value[:1] in {'"', '“'}:
            value = '"' + identity_text(value[1:-1]).strip() + '"'
        result.append(value)
    return result


def identity_text(text):
    """Finite display equivalence for identities only, never T or numbers."""
    from .three_layer import canonical

    text = canonical(text).translate(str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'"}))
    text = re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff\d])|(?<=\d)\s+(?=[\u3400-\u9fff])', '', text)
    return re.sub(r'"\s*([^"\n]*?)\s*"', lambda m: '"' + m[1] + '"', text)


def shape(text):
    text = re.sub(r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:百万元|百萬元|万元|萬元|亿元|億元|美元|港元|元|[%‰])", '#Q', text)
    text = re.sub(r"不得|不能|不超过|不超過|以上|以下|至少|至多|必须|必須|仅|僅|如果|除非|\b(?:not|no|unless|except|only|must|shall|may|if|before|after)\b", '@', text, flags=re.I)
    return _NUMBER.sub("#", text)


def _context(node):
    return (tuple(node.get("scope", [])), tuple(node.get("parents", [])), node.get("identity"))


def _join(nodes):
    """Join display fragments with explicitly unowned Latin seam whitespace."""
    from .three_layer import canonical

    text, owners, offsets = "", [], []
    for i, node in enumerate(nodes):
        own = canonical(node["text"])
        if text and own and re.search(r"[A-Za-z0-9,;:]$", text) and re.match(r"[A-Za-z0-9]", own):
            text += " "
            owners.append(None)
            offsets.append(None)
        text += own
        owners.extend([i] * len(own))
        offsets.extend(range(len(own)))
    return text, owners, offsets


def _groups(nodes, maximum):
    result = []
    for start, node in enumerate(nodes):
        if node.get("barrier"):
            continue
        for stop in range(start + 1, min(start + maximum, len(nodes)) + 1):
            own = nodes[start:stop]
            headings = all(n.get('role') == 'heading' or n.get('syntax_kind') == 'heading' for n in own)
            if stop > start + 1 and (any(n.get("barrier") for n in own) or not headings and (
                any(n.get('role') == 'heading' for n in own) or any(_context(n) != _context(node) for n in own))):
                break
            text, owners, offsets = _join(own)
            if text:
                result.append({"range": [start, stop], "text": text, "shape": shape(text),
                               "owners": owners, "offsets": offsets})
    return result


def _context_score(left, right):
    a, b = _context(left), _context(right)
    # A wrong parent remains retrievable. Context ranks identical labels; it
    # does not pre-accept the relationship that L will subsequently examine.
    score = sum(x == y for x, y in zip(a[:2], b[:2], strict=True))
    # Partially preserved scope still distinguishes same-label fields. This
    # ranks correspondence only; explicit relationships are graded later.
    left_scope, right_scope = left.get('matching_scope', a[0]), right.get('matching_scope', b[0])
    score += Levenshtein.normalized_similarity(identity_text('|'.join(left_scope)), identity_text('|'.join(right_scope)))
    suffix = 0
    for x, y in zip(reversed(left_scope), reversed(right_scope), strict=False):
        if identity_text(x) != identity_text(y):
            break
        suffix += 1
    score += suffix / max(1, len(left_scope))
    if a[2] is not None or b[2] is not None:
        score += 2 * Levenshtein.normalized_similarity(identity_text(a[2] or ''), identity_text(b[2] or ''))
    score += left.get("role") == right.get("role")
    return score


def _ledger(required, actual):
    left, lo, _ = _join(required)
    right, ro, offsets = _join(actual)
    records = [{"edits": {"S": 0, "D": 0, "I": 0}, "pieces": []} for _ in required]
    positions = [[] for _ in required]
    for op in Levenshtein.opcodes(left, right):
        tag, a, b, x, y = op
        if tag in {"equal", "replace"}:
            pairs = min(b - a, y - x)
            for k in range(pairs):
                owner = lo[a + k]
                if owner is not None:
                    if tag == "replace":
                        records[owner]["edits"]["S"] += 1
                    if ro[x + k] is not None:
                        positions[owner].append(x + k)
                elif tag == "replace" and ro[x + k] is not None:
                    following = next((v for v in lo[a + k:] if v is not None), len(required) - 1)
                    records[following]["edits"]["I"] += 1
                    positions[following].append(x + k)
            a += pairs
            x += pairs
        if tag in {"delete", "replace"}:
            for k in range(a, b):
                if lo[k] is not None:
                    records[lo[k]]["edits"]["D"] += 1
        if tag in {"insert", "replace"}:
            owner = next((v for v in lo[a:] if v is not None), len(required) - 1)
            for k in range(x, y):
                if ro[k] is not None:
                    records[owner]["edits"]["I"] += 1
                    positions[owner].append(k)
    for row, indices in zip(records, positions, strict=True):
        for position in indices:
            index, offset = ro[position], offsets[position]
            if row["pieces"] and row["pieces"][-1]["index"] == index and row["pieces"][-1]["span"][1] == offset:
                row["pieces"][-1]["span"][1] += 1
                row["pieces"][-1]["text"] += right[position]
            else:
                row["pieces"].append({"index": index, "span": [offset, offset + 1],
                                      "text": right[position], "source": actual[index]["source"]})
    return records


def align_nodes(required, actual, *, maximum=None, preserve_identity_ambiguity=True):
    """Select reproducible 1:N/N:1/N:M groups without value-based selection.

    All proposed matches above the fixed threshold survive in the trace. No
    alignment can omit an interior node. Missing nodes are edit deletions under
    this contract, not a claim that every possible paraphrase was disproved.
    """
    from .three_layer import canonical

    maximum = maximum or RULES["maximum_group"]
    left, right = _groups(required, maximum), _groups(actual, maximum)
    proposals = []
    for a in left:
        for b in right:
            na, nb = a["range"][1] - a["range"][0], b["range"][1] - b["range"][0]
            # Multi-to-multi is necessary only where both sides have differing
            # boundaries. Identical boundaries are covered by smaller groups.
            if na > 1 and nb > 1 and na == nb:
                continue
            ar, br = required[a["range"][0]], actual[b["range"][0]]
            if ar.get("identity") and br.get("identity") and Levenshtein.normalized_similarity(
                identity_text(ar['identity']), identity_text(br['identity'])) < RULES['minimum_similarity']:
                continue
            similarity = Levenshtein.normalized_similarity(a["shape"], b["shape"], score_cutoff=RULES["minimum_similarity"])
            if similarity < RULES["minimum_similarity"]:
                continue
            context = _context_score(ar, br)
            # Context breaks label ties before content values can enter. Larger
            # exact groups beat their partial fragments, preserving split text.
            rank = (round(similarity, 12), context, min(len(a["shape"]), len(b["shape"])))
            proposals.append({"required": a["range"], "actual": b["range"],
                              "similarity": similarity, "context": context,
                              "rank": rank, "selected": False, "value_used": False})
    proposals.sort(key=lambda p: (tuple(-v for v in p["rank"]), p["required"], p["actual"]))
    used_r, used_a, ambiguous = set(), set(), {}
    tie_index = {}
    for proposal in proposals:
        tie_index.setdefault((tuple(proposal['required']), proposal['rank']), []).append(proposal)
    rows = [{"required_index": i, "actual_pieces": [], "status": "deleted",
             "edits": {"S": 0, "D": len(canonical(n["text"])), "I": 0}}
            for i, n in enumerate(required)]
    repeated = Counter((shape(canonical(n["text"])), _context(n)) for n in required)
    for proposal in proposals:
        a, b = proposal["required"], proposal["actual"]
        if any(i in used_r for i in range(*a)) or any(i in used_a for i in range(*b)):
            proposal["rejected"] = "original_occurrence_capacity"
            continue
        # Same-score positions with different critical payload or business
        # context are real ambiguities. Equal printed duplicates can be paired
        # in stable source order, with occurrence capacity still conserved.
        ties = [p for p in tie_index[tuple(a), proposal['rank']]
                if not any(i in used_a for i in range(*p["actual"]))]
        signatures = {(tuple(protected(_join(actual[slice(*p["actual"])])[0])),
                       _context(actual[p["actual"][0]]),
                       repr(actual[p['actual'][0]].get('payload', {}).get('value')))
                      for p in ties}
        if preserve_identity_ambiguity and len(signatures) > 1 and repeated[shape(canonical(required[a[0]]["text"])), _context(required[a[0]])] == 1:
            for i in range(*a):
                ambiguous[i] = [p["actual"] for p in ties]
            proposal["rejected"] = "score_changing_identity_tie"
            continue
        if any(i in ambiguous for i in range(*a)):
            continue
        ledger = _ledger(required[slice(*a)], actual[slice(*b)])
        for index, item in enumerate(ledger, a[0]):
            pieces = [{**piece, "index": piece["index"] + b[0]} for piece in item["pieces"]]
            rows[index].update(status="matched" if pieces else "deleted", actual_pieces=pieces, edits=item["edits"],
                               group={"required": a, "actual": b},
                               basis={k: proposal[k] for k in ("similarity", "context", "value_used")})
        used_r.update(range(*a))
        used_a.update(range(*b))
        proposal["selected"] = True
    for i, ties in ambiguous.items():
        if i not in used_r:
            rows[i].update(status="ambiguous", alternatives=ties)
    extras = [{"index": i, "text": n["text"], "source": n["source"],
               "I": len(canonical(n["text"]))} for i, n in enumerate(actual)
              if i not in used_a and not n.get("barrier")]
    return {"rows": rows, "insertions": extras, "retrieval": proposals,
            "required_nodes": copy.deepcopy(required), "actual_nodes": copy.deepcopy(actual),
            "method": METHOD, "capacity": "each original node consumed once; pieces disjoint inside groups"}
