"""Conservative output localization, independent of evaluated relationships.

Localization never edits native text. Equal alternatives remain ambiguous; no
reading-order, coordinate, or expected-table-header hints break a content tie.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .metrics import normalize_text
from .representations import visible_text

try:
    import edlib as _edlib
except ImportError:
    _edlib = None


_NUMERIC_BODY = r"(?:\d+(?:[.,]\d+)*|\.\d+)(?:[eE][+\-−]?\d+)?[%‰]?"
_NUMERIC_TOKEN = re.compile(
    rf"\(\s*[+\-−]?{_NUMERIC_BODY}\s*\)|[+\-−]?{_NUMERIC_BODY}"
)


def _numeric_reference(text: str) -> bool:
    """Recognize numeric notation only; this does not parse or normalize values."""
    stripped = text.strip()
    return bool(re.search(r"\d", stripped) and (
        _NUMERIC_TOKEN.fullmatch(stripped)
        or re.fullmatch(r"[\s\d.,+%‰\-−()]+", stripped)
    ))


def _whole_numeric_span(text: str, start: int, end: int) -> bool:
    """Reject a strict numeric subspan using only the native visible text.

    Decimal/grouping punctuation joins digits, while a sentence comma or
    full stop does not. Accounting parentheses and complete exponents belong
    to their numeric token. Malformed adjacent digits/signs/percent markers
    are conservatively rejected too, never repaired or trimmed into a value.
    """
    for neighbour in (text[start - 1:start] if start else "", text[end:end + 1]):
        if neighbour and (neighbour.isdigit() or neighbour in "+-−%‰/"):
            return False
    for token in _NUMERIC_TOKEN.finditer(text):
        if token.start() < end and start < token.end():
            if token.start() < start or token.end() > end:
                return False
    return True


def observation_candidates(observation: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose actual native items without flattening tables into prose."""
    result: list[dict[str, Any]] = []
    for page_index, page in enumerate(observation.get("pages", [])):
        for block_index, block in enumerate(page.get("blocks", [])):
            native_id = str(block.get("id", f"page:{page_index}:block:{block_index}"))
            provenance_pages = block.get("provenance_pages") or [page.get("page")]
            sequence = block.get("native_sequence") or [page_index, block_index]
            block_page = block.get("page", page.get("page") if len(provenance_pages) == 1 else None)
            common = {
                "page": block_page,
                "pages": provenance_pages,
                "native_path": block.get("native_path"),
                "native_id": block.get("native_id", native_id),
                "parent_id": block.get("parent_id"),
                "order": (*sequence, -1),
                "block": block,
            }
            cells = block.get("cells") or []
            if cells:
                for cell_index, cell in enumerate(cells):
                    result.append(
                        {
                            **common,
                            "id": str(cell.get("id", f"{native_id}:cell:{cell_index}")),
                            "native_id": str(cell.get("native_id", cell.get("id", f"{native_id}:cell:{cell_index}"))),
                            "native_path": cell.get("native_path", common["native_path"]),
                            "parent_id": native_id,
                            "page": cell.get("page", block_page),
                            "pages": cell.get("provenance_pages", provenance_pages),
                            "kind": "table_cell",
                            "text": str(cell.get("text", "")),
                            "cell": cell,
                            "order": (*sequence, cell_index),
                        }
                    )
                # A display string repeating those cells must not count twice.
                continue
            kind = "image" if block.get("kind") in {"image", "picture", "figure", "image_body", "chart", "chart_body"} else "text"
            result.append(
                {
                    **common,
                    "id": native_id,
                    "kind": kind,
                    "text": visible_text(str(block.get("caption") or block.get("text", "")), block.get("text_format", "plain")),
                    "native_text": str(block.get("caption") or block.get("text", "")),
                    "span_representation": block.get("text_format", "plain") + "_visible_text",
                    "asset": block.get("asset"),
                }
            )
    duplicate_ids = Counter(candidate["id"] for candidate in result)
    for index, candidate in enumerate(result):
        if duplicate_ids[candidate["id"]] > 1:
            candidate["id"] = f"duplicate:{index}:{candidate['id']}"
            candidate["duplicate_native_id"] = True
    return result


def in_page_scope(candidate: dict[str, Any], pages: set[int]) -> bool:
    """Use an explicit native page or intersect its declared provenance range."""
    return not pages or candidate.get("page") in pages or bool(pages.intersection(candidate.get("pages", [])))


def _normalized_positions(text: str, collapse_whitespace: bool) -> tuple[str, list[tuple[int, int]]]:
    normalized = normalize_text(text)
    if not collapse_whitespace:
        return normalized, [(index, index + 1) for index in range(len(text))]
    pieces: list[str] = []
    positions: list[tuple[int, int]] = []
    for match in re.finditer(r"\s+|\S", normalized):
        is_space = match.group().isspace()
        if is_space and not pieces:
            continue
        pieces.append(" " if is_space else match.group())
        positions.append((match.start(), match.end()))
    if pieces and pieces[-1] == " ":
        pieces.pop()
        positions.pop()
    return "".join(pieces), positions


def _approximate_spans(reference: str, text: str, threshold: float) -> list[tuple[int, int, float]]:
    """Locate minimum-Levenshtein infixes, then apply the frozen similarity gate.

    Non-query characters may share an unmatched code: their mutual equality is
    irrelevant when aligning against the query. This keeps Chinese paragraphs
    within Edlib's alphabet limit without changing edit costs or text positions.
    """
    if not reference or not text:
        return []
    alphabet = {char: index for index, char in enumerate(dict.fromkeys(reference))}
    if _edlib is not None and len(alphabet) <= 255:
        unmatched = len(alphabet)
        result = _edlib.align(
            bytes(alphabet[char] for char in reference),
            bytes(alphabet.get(char, unmatched) for char in text),
            mode="HW", task="locations",
            k=math.ceil(len(reference) * (1 - threshold) / threshold),
        )
        distance = result["editDistance"]
        if distance < 0:
            return []
        locations = [(start, end + 1) for start, end in result["locations"]]
        return [
            (start, end, similarity)
            for start, end in locations if start is not None and start < end
            if (similarity := 1 - distance / max(len(reference), end - start)) + 1e-12 >= threshold
        ]
    previous = [(0, index) for index in range(len(text) + 1)]
    for row, char in enumerate(reference, 1):
        current = [(row, 0)]
        for column, output_char in enumerate(text, 1):
            diagonal, above, left = previous[column - 1], previous[column], current[column - 1]
            options = [
                (diagonal[0] + (char != output_char), diagonal[1]),
                (above[0] + 1, above[1]),
                (left[0] + 1, left[1]),
            ]
            current.append(min(options, key=lambda item: item[0]))
        previous = current
    found: list[tuple[int, int, float]] = []
    minimum_distance = min(distance for distance, _start in previous)
    for end, (distance, start) in enumerate(previous):
        if start >= end or distance != minimum_distance:
            continue
        similarity = 1 - distance / max(len(reference), end - start)
        if similarity + 1e-12 < threshold:
            continue
        found.append((start, end, similarity))
    # Adjacent endpoint alternatives of the same physical span remain ambiguous.
    return list(dict.fromkeys(found))


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_claims = left.get("claims", [left])
    right_claims = right.get("claims", [right])
    return any(
        first["candidate_id"] == second["candidate_id"]
        and first["span"][0] < second["span"][1]
        and second["span"][0] < first["span"][1]
        for first in left_claims for second in right_claims
    )


def _text_streams(
    candidates: list[dict[str, Any]], pages: set[int]
) -> list[dict[str, Any]]:
    """Offer adjacent native text as a localization view, preserving every item.

    Tables/images interrupt a stream. A stream is never an additional output
    unit and cannot be used to claim its component character spans twice.
    Native block boundaries become display line breaks, not source facts.
    """
    streams: list[dict[str, Any]] = []
    group: list[dict[str, Any]] = []

    def finish() -> None:
        if len(group) < 2:
            group.clear()
            return
        pieces: list[str] = []
        components = []
        offset = 0
        for item in group:
            if pieces:
                pieces.append("\n")
                offset += 1
            components.append({"candidate_id": item["id"], "start": offset,
                               "end": offset + len(item["text"])})
            pieces.append(item["text"])
            offset += len(item["text"])
        first, last = group[0], group[-1]
        streams.append({
            **first, "id": f"stream:{first['id']}:{last['id']}",
            "kind": "text", "text": "".join(pieces), "components": components,
            "pages": sorted({page for item in group for page in item.get("pages", []) if page is not None}),
            "virtual": True,
        })
        group.clear()

    # Some native reading trees visit a later physical page before an earlier
    # one. Follow that actual order; a page-sorted stream would repair the
    # parser's reading sequence before we evaluate it.
    previous_group = None
    for candidate in sorted(candidates, key=lambda item: item["order"]):
        current_group = (candidate["kind"], candidate.get("parent_id") if candidate["kind"] == "table_cell" else None)
        if current_group != previous_group:
            finish()
        previous_group = current_group
        if candidate["kind"] not in {"text", "table_cell"} or not in_page_scope(candidate, pages):
            finish()
        else:
            group.append(candidate)
    finish()
    return streams


def reference_parent_scope(
    unit: dict[str, Any], *, collapse_whitespace: bool = False,
) -> tuple[str | None, bool, bool]:
    """Read declared localization dependencies without using candidate answers."""
    text = normalize_text(unit.get("reference_text", ""), collapse_whitespace=collapse_whitespace)
    bare_number = _numeric_reference(text)
    short_label = unit.get("kind", "text") == "field" and len(text) <= 8
    field_scope = unit.get("field_scope", {})
    parent = unit.get("parent") or field_scope.get("label_unit")
    needs_scope = bool(
        bare_number or short_label or unit.get("requires_parent_scope", False)
        or field_scope.get("label_unit")
    )
    return parent, needs_scope, bare_number


def match_units(
    units: list[dict[str, Any]],
    observation: dict[str, Any],
    *,
    threshold: float = 0.8,
    collapse_whitespace: bool = False,
) -> dict[str, Any]:
    """Match units containing resolved ``reference_text`` fields conservatively.

    Numeric literals and short labels require a separately localized parent scope. Long
    paragraph content does not require a predicted heading edge: that relation
    is evaluated independently after localization, never used to hide its text.
    """
    if not 0 < threshold <= 1:
        raise ValueError("locator threshold must be within (0, 1]")
    candidates = observation_candidates(observation)
    candidate_map = {candidate["id"]: candidate for candidate in candidates}
    normalized = {
        candidate["id"]: _normalized_positions(candidate["text"], collapse_whitespace)
        for candidate in candidates
    }
    children: dict[str, set[str]] = {}
    containers = {item["id"]: item for item in observation.get("native_containers", [])}
    native_blocks = {item["id"]: item for page in observation.get("pages", []) for item in page.get("blocks", [])}
    for identifier, item in containers.items():
        children.setdefault(identifier, set()).update(item.get("native_children", []))
    for candidate in candidates:
        if candidate.get("parent_id"):
            children.setdefault(str(candidate["parent_id"]), set()).add(candidate["id"])
    for edge in observation.get("relations", []):
        if edge.get("type") in {"contains", "parent_of", "has_child"}:
            children.setdefault(str(edge.get("source")), set()).add(str(edge.get("target")))
        elif edge.get("type") in {"belongs_to", "child_of"}:
            children.setdefault(str(edge.get("target")), set()).add(str(edge.get("source")))
    matches: dict[str, dict[str, Any]] = {}
    diagnostics: dict[str, dict[str, Any]] = {}
    by_id = {unit["id"]: unit for unit in units}
    streams_by_pages: dict[tuple[int, ...], list[dict[str, Any]]] = {}

    def scoped_candidates(unit: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        pages = set(unit.get("pages", []))
        pool = [candidate for candidate in candidates if in_page_scope(candidate, pages)]
        kind = unit.get("kind", "text")
        pool = [candidate for candidate in pool if (candidate["kind"] == "image") == (kind == "image")]
        if kind == "table_cell":
            pool = [candidate for candidate in pool if candidate["kind"] == "table_cell"]
        if kind == "text":
            # A parser may put grid-layout prose into native cells. Its text
            # remains readable without accepting any data-table semantics.
            pool = [candidate for candidate in pool if candidate["kind"] in {"text", "table_cell"}]
            key = tuple(sorted(pages))
            if key not in streams_by_pages:
                streams_by_pages[key] = _text_streams(candidates, pages)
                for stream in streams_by_pages[key]:
                    candidate_map[stream["id"]] = stream
                    normalized[stream["id"]] = _normalized_positions(
                        stream["text"], collapse_whitespace
                    )
            pool += streams_by_pages[key]
        parent, needs_scope, bare_number = reference_parent_scope(unit, collapse_whitespace=collapse_whitespace)
        field_scope = unit.get("field_scope", {})
        if parent and needs_scope:
            if parent not in matches:
                return [], "parent_unresolved"
            anchor = matches[parent]["candidate_id"]
            claims = matches[parent].get("claims", [{"candidate_id": anchor}])
            allowed = {claim["candidate_id"] for claim in claims}
            if field_scope.get("scope_kind") == "visual_label_value_pair":
                for identifier in list(allowed):
                    native_parent = candidate_map[identifier].get("parent_id")
                    container = containers.get(native_parent, native_blocks.get(native_parent, {}))
                    if container and container.get("label", container.get("kind")) not in {
                        None, "root", "document", "page", "body", "furniture", "unspecified",
                    }:
                        allowed.add(native_parent)
            pending = list(allowed)
            while pending:
                for child in children.get(pending.pop(), set()) - allowed:
                    allowed.add(child)
                    pending.append(child)
            pool = [candidate for candidate in pool if candidate["id"] in allowed]
        if not parent and needs_scope:
            return [], "short_number_without_parent_scope" if bare_number else "short_label_without_parent_scope"
        return pool, None

    def locate(unit: dict[str, Any], *, fuzzy: bool) -> tuple[list[dict[str, Any]], str | None]:
        pool, reason = scoped_candidates(unit)
        if reason:
            return [], reason
        reference = normalize_text(unit.get("reference_text", ""), collapse_whitespace=collapse_whitespace)
        if not reference:
            return [], "empty_reference_not_localizable"
        proposals: list[dict[str, Any]] = []
        numeric_reference = _numeric_reference(reference)
        for candidate in pool:
            text, positions = normalized[candidate["id"]]
            if len(text) < len(reference) * threshold:
                continue
            spans: list[tuple[int, int, float]] = []
            if fuzzy:
                if numeric_reference or len(reference) < 5:
                    continue
                spans = _approximate_spans(reference, text, threshold)
            else:
                start = text.find(reference)
                while start != -1:
                    end = start + len(reference)
                    if not numeric_reference or _whole_numeric_span(text, start, end):
                        spans.append((start, end, 1.0))
                    start = text.find(reference, start + 1)
            for start, end, similarity in spans:
                original_span = [positions[start][0], positions[end - 1][1]]
                if candidate.get("components"):
                    claims = [
                        {"candidate_id": component["candidate_id"],
                         "span": [max(original_span[0], component["start"]) - component["start"],
                                  min(original_span[1], component["end"]) - component["start"]]}
                        for component in candidate["components"]
                        if original_span[0] < component["end"] and component["start"] < original_span[1]
                    ]
                else:
                    claims = [{"candidate_id": candidate["id"], "span": original_span}]
                proposal = {
                    "candidate_id": candidate["id"],
                    "native_id": candidate["native_id"],
                    "native_path": candidate["native_path"],
                    "page": candidate["page"],
                    "provenance_pages": candidate.get("pages", []),
                    "physical_page_known": candidate["page"] is not None,
                    "span_representation": candidate.get("span_representation", "plain_visible_text"),
                    "span": original_span,
                    "hypothesis": candidate["text"][original_span[0] : original_span[1]],
                    "method": "approximate" if fuzzy else "exact",
                    "locator_similarity": similarity,
                    "claims": claims,
                }
                if not any(_overlaps(proposal, other) for other in matches.values()):
                    proposals.append(proposal)
        # The same physical spans seen alone or in a stream are one proposal.
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for proposal in proposals:
            signature = tuple(
                (claim["candidate_id"], *claim["span"]) for claim in proposal["claims"]
            )
            unique.setdefault(signature, proposal)
        proposals = list(unique.values())
        if fuzzy and proposals:
            best = max(proposal["locator_similarity"] for proposal in proposals)
            proposals = [
                proposal for proposal in proposals
                if abs(proposal["locator_similarity"] - best) < 1e-12
            ]
        return proposals, None

    # Resolve unique exact content first; tied references never win by iteration order.
    for fuzzy in (False, True):
        while True:
            proposals_by_unit: dict[str, list[dict[str, Any]]] = {}
            for unit_id, unit in by_id.items():
                if unit_id in matches:
                    continue
                if fuzzy:
                    exact, _ = locate(unit, fuzzy=False)
                    if exact:
                        diagnostics[unit_id] = {"status": "ambiguous", "alternatives": len(exact)}
                        continue
                proposals, reason = locate(unit, fuzzy=fuzzy)
                if reason:
                    diagnostics[unit_id] = {"status": "unresolved", "reason": reason}
                elif len(proposals) > 1:
                    diagnostics[unit_id] = {"status": "ambiguous", "alternatives": len(proposals)}
                elif not proposals:
                    # A parent can resolve in an earlier pass of this loop.
                    # With a valid scope and no value proposal, do not retain
                    # the obsolete parent_unresolved diagnosis.
                    if diagnostics.get(unit_id, {}).get("reason") == "parent_unresolved":
                        diagnostics[unit_id] = {"status": "not_localized"}
                    else:
                        diagnostics.setdefault(unit_id, {"status": "not_localized"})
                proposals_by_unit[unit_id] = proposals
            unique = {key: value[0] for key, value in proposals_by_unit.items() if len(value) == 1}
            selected: dict[str, dict[str, Any]] = {}
            for unit_id, proposal in unique.items():
                conflicts = [
                    other_id for other_id, other in unique.items()
                    if other_id != unit_id and _overlaps(proposal, other)
                ]
                if conflicts:
                    diagnostics[unit_id] = {"status": "ambiguous", "reason": "competing_reference_spans"}
                else:
                    selected[unit_id] = proposal
            if not selected:
                break
            matches.update(selected)
            for unit_id in selected:
                diagnostics[unit_id] = {"status": "localized"}
    return {
        "matches": matches,
        "diagnostics": diagnostics,
        "candidates": candidates,
        "candidate_map": candidate_map,
    }
