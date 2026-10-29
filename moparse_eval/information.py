"""Locate information in candidate output only, independently of target values."""

from __future__ import annotations

import re
from typing import Any

from .information_reading import label_text, scoped_qualifiers, units
from .metrics import normalize_text


def field_value_text(text: str) -> str:
    """Ignore display spacing beside an existing currency or percent symbol.

    Digits, signs, decimal places, grouping marks and symbols are unchanged.
    Spaces between digits or business words are never removed.
    """
    text = normalize_text(text, collapse_whitespace=True)
    scalar = re.fullmatch(r"([$€£¥]?)\s*([+\-−]?(?:\d+(?:[.,]\d+)*|\.\d+))\s*([%‰]?)", text)
    return "".join(scalar.groups()) if scalar else text


def label_pattern(label: str) -> str:
    left = r"(?<!\w)" if re.match(r"\w", label[0]) else ""
    right = r"(?!\w)" if re.match(r"\w", label[-1]) else ""
    if label[0].isdigit():
        left += r"(?<![+\-−/%‰])(?<!\d[.,])"
    if label[-1].isdigit():
        right += r"(?![+\-−/%‰]|[.,]\d)"
    return left + re.escape(label) + right


def label_in_text(label: str, text: str, collapse_whitespace: bool) -> bool:
    label = normalize_text(label, collapse_whitespace=collapse_whitespace)
    text = normalize_text(text, collapse_whitespace=collapse_whitespace)
    if label and re.search(label_pattern(label), text):
        return True
    # Chinese labels and their attached currency/unit have no word boundary.
    # Only a completely recognized suffix is separable, never another label.
    return bool(label and text.startswith(label) and text[len(label):] in units(text[len(label):]))


def path_locates(labels: list[str], native: Any, collapse_whitespace: bool) -> bool:
    """Allow split/merged adjacent text, while covering every native path item.

    This is a locator, not a statement that the native qualifiers are correct.
    No business level may be skipped and no label occurrence consumed twice.
    """
    if not labels or not isinstance(native, list) or not native or any(
        not isinstance(text, str) or not text.strip() for text in native
    ):
        return False
    labels = [normalize_text(label, collapse_whitespace=collapse_whitespace) for label in labels]
    parts = [normalize_text(text, collapse_whitespace=collapse_whitespace) for text in native]
    if not all(labels):
        return False
    text = " ".join(parts)
    # Only adjacency whitespace may vary between complete labels.
    pattern = r"\s*".join(label_pattern(label) for label in labels)
    offsets = []
    cursor = 0
    for part in parts:
        offsets.append((cursor, cursor + len(part)))
        cursor += len(part) + 1
    return any(all(match.start() < end and start < match.end() for start, end in offsets)
               for match in re.finditer(pattern, text))


def native_range(cell: dict[str, Any], axis: str) -> set[int] | None:
    scope = cell.get("information_row_scope") if axis == "row" else None
    if (isinstance(scope, list) and len(scope) == 2 and all(type(v) is int for v in scope)
            and 0 <= scope[0] <= scope[1] < scope[0] + 2000):
        return set(range(scope[0], scope[1] + 1))
    start, span = cell.get(axis), cell.get(f"{axis}_span", 1)
    if type(start) is not int or type(span) is not int or not 1 <= span <= 10000:
        return None
    return set(range(start, start + span))


def endpoint_paths(labels: list[str], group: list[dict[str, Any]], axis: str,
                   collapse_whitespace: bool) -> tuple[list[list[dict[str, Any]]], str | None]:
    """Resolve a full label path through existing spans, never through values.

    Duplicate leaves are allowed until their complete paths are considered.
    The bound prevents combinatorial work without choosing a favourable path.
    """
    role = "is_row_header" if axis == "row" else "is_column_header"
    extent_axis, order_axis = ("row", "col") if axis == "row" else ("col", "row")
    options = []
    for label in labels:
        matches = [item for item in group if label_in_text(label, item["text"], collapse_whitespace)]
        if axis == "row":
            matches = [item for item in matches if (
                label_text(item["text"]) == label_text(label)
                or path_locates(labels, [item["text"]], collapse_whitespace)
                and re.sub(r"\s+", "", label_text(item["text"])) == re.sub(r"\s+", "", "".join(labels))
                or item["text"].startswith(label) and item["text"][len(label):].strip(" ()（）") in units(item["text"][len(label):])
            )]
        exact = [item for item in matches if label_text(item["text"]) == label_text(label)]
        if exact:
            matches = exact
        declared = [item for item in matches if item["cell"].get(role) is True]
        matches = declared or matches
        if not matches:
            return [], "native_header_endpoints_unavailable"
        if any(item.get("duplicate_native_id") for item in matches):
            return [], "ambiguous_header_endpoint"
        options.append(matches)
    paths: list[list[dict[str, Any]]] = [[]]
    for depth, matches in enumerate(options):
        extended = []
        for path in paths:
            for item in matches:
                trial = [*path, item]
                extents = [native_range(node["cell"], extent_axis) for node in trial]
                if all(extents) and not set.intersection(*(extent for extent in extents if extent)):
                    continue
                if path:
                    prior = path[-1]
                    if prior["id"] == item["id"]:
                        start = len(path) - 1
                        while start and path[start - 1]["id"] == item["id"]:
                            start -= 1
                        if not path_locates(labels[start:depth + 1], [item["text"]], collapse_whitespace):
                            continue
                    else:
                        before = native_range(prior["cell"], order_axis)
                        after = native_range(item["cell"], order_axis)
                        if before and after and min(after) < min(before):
                            # Explicit HTML ancestry may override physical position.
                            native = item["cell"].get("native_attributes", {})
                            ancestor = prior["cell"].get("native_attributes", {}).get("id")
                            if not ancestor or ancestor not in str(native.get("headers", "")).split():
                                continue
                extended.append(trial)
                if len(extended) > 512:
                    return [], "native_label_path_search_limit"
        paths = extended
        if not paths:
            return [], "native_label_path_scope_conflict"
    return paths, None


def qualifier_evidence(expected: dict[str, Any], cell: dict[str, Any],
                       endpoint_texts: list[str]) -> dict[str, dict[str, Any]]:
    """Read only explicitly scoped metadata or actual located header text."""
    evidence = {}
    scoped = scoped_qualifiers(cell, endpoint_texts)
    for key, value in expected.items():
        if key in cell:
            actual = cell[key]
            if isinstance(value, str) and isinstance(actual, str):
                correct = normalize_text(value, collapse_whitespace=True) == normalize_text(actual, collapse_whitespace=True)
            else:
                correct = value == actual
            evidence[key] = {"status": "correct" if correct else "incorrect", "source": "native_field", "actual": actual}
        elif key in scoped and isinstance(value, str):
            found = scoped[key]
            matching = [item for item in found if label_in_text(value, item["actual"], True)
                        or normalize_text(value, collapse_whitespace=True) == normalize_text(item["actual"], collapse_whitespace=True)
                        or key == "period" and re.fullmatch(r"(?:19|20)\d{2}年?", value)
                        and re.search(r"(?<!\d)" + re.escape(value.rstrip("年")) + r"年(?:度|末)?(?!\d)", item["actual"])]
            evidence[key] = ({"status": "correct", "source": "candidate_scoped_qualifier", "actual": matching}
                             if matching else {"status": "incorrect", "source": "candidate_scoped_qualifier", "actual": found}
                             if key == "unit" and found else
                             {"status": "unresolved", "source": "native_qualifier_scope_unavailable"})
        elif isinstance(value, str) and any(label_in_text(value, text, True) for text in endpoint_texts):
            evidence[key] = {"status": "correct", "source": "located_native_header", "actual": [
                text for text in endpoint_texts if label_in_text(value, text, True)]}
        else:
            evidence[key] = {"status": "unresolved", "source": "native_qualifier_scope_unavailable"}
    return evidence


def information_value_equal(expected: str, actual: str, field: dict[str, Any],
                            evidence: dict[str, dict[str, Any]]) -> bool:
    """Declared expression equivalence, preserving numeric and sign spelling."""
    left, right = field_value_text(expected), field_value_text(actual)
    if left == right:
        return True
    unit = field.get("unit")
    if unit in {"%", "‰"} and evidence.get("unit", {}).get("status") == "correct":
        def separate(text: str) -> str:
            # Parentheses remain around the scalar, including accounting signs.
            return re.sub(re.escape(unit) + r"(?=\)?$)", "", text)
        return separate(left) == separate(right)
    if left in {"—", "–", "-"} and right in {"—", "–", "-"}:
        return True
    if not re.fullmatch(r"[\d\s,.+\-−()%‰$€£¥]+", left):
        def prose(text: str) -> str:
            text = re.sub(r"(?<!\d)((?:19|20)\d{2})[—–-]((?:19|20)\d{2})(?!\d)", r"\1—\2", text)
            return text.rstrip("。.")
        return prose(left) == prose(right)
    return False
