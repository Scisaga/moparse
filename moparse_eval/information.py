"""Locate information in candidate output only, independently of target values."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from app.utils.measurement import unit_applicable

from .information_reading import (
    _SECTION_PERIOD,
    label_text,
    label_views,
    scoped_qualifiers,
    unit_scope_literal,
    units,
)
from .metrics import normalize_text


def unit_text(text: str) -> str:
    text = normalize_text(text, collapse_whitespace=True)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.translate(str.maketrans("幣萬億個點噸", "币万亿个点吨"))
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    text = re.sub(r"\s*/\s*", "/", text)
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)


def period_text(text: str) -> str:
    """Ignore display spacing before the existing Chinese year suffix only."""
    text = normalize_text(text, collapse_whitespace=True)
    section = _SECTION_PERIOD.fullmatch(text)
    if section and len(set(re.findall(r"(?:19|20)\d{2}", text))) == 1:
        text = section[1]
    return re.sub(r"(?<=截至)\s+(?=\d)|(?<=\d)\s+(?=[年月日])|(?<=[年月])\s+(?=\d)|(?<=年)\s+(?=[度末])", "", text)


def business_scope_text(text: str) -> str:
    """Read explicit scope-path separators as heading layout, retaining words and IDs."""
    text = label_text(normalize_text(text, collapse_whitespace=True))
    text = re.sub(r"\s+/\s+", " ", text)
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff\d(])|(?<=[\d)])\s+(?=[\u3400-\u9fff(])", "", text)


def field_value_text(text: str) -> str:
    """Ignore display spacing beside an existing currency or percent symbol.

    Digits, signs, decimal places, grouping marks and symbols are unchanged.
    Spaces between digits or business words are never removed.
    """
    text = normalize_text(text, collapse_whitespace=True)
    scalar = re.fullmatch(r"([$€£¥]?)\s*([+\-−]?(?:\d+(?:[.,]\d+)*|\.\d+))\s*([%‰]?)", text)
    return "".join(scalar.groups()) if scalar else text


@lru_cache(maxsize=8192)
def label_pattern(label: str) -> str:
    left = r"(?<!\w)" if re.match(r"\w", label[0]) else ""
    right = r"(?!\w)" if re.match(r"\w", label[-1]) else ""
    if label[0].isdigit():
        left += r"(?<![+\-−/%‰^])(?<!\d[.,])"
    if label[-1].isdigit():
        right += r"(?![+\-−/%‰^]|[.,]\d)"
    return left + re.escape(label) + right


@lru_cache(maxsize=65536)
def label_in_text(label: str, text: str, collapse_whitespace: bool) -> bool:
    label = label_text(normalize_text(label, collapse_whitespace=collapse_whitespace))
    text = label_text(normalize_text(text, collapse_whitespace=collapse_whitespace))
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
    labels = [label_text(normalize_text(label, collapse_whitespace=collapse_whitespace)) for label in labels]
    parts = [label_text(normalize_text(text, collapse_whitespace=collapse_whitespace)) for text in native]
    if not all(labels):
        return False
    text = " ".join(parts)
    # Only adjacency whitespace may vary between complete labels.
    first, last = label_pattern(labels[0]), label_pattern(labels[-1])
    left = first[:first.index(re.escape(labels[0]))]
    right = last[last.index(re.escape(labels[-1])) + len(re.escape(labels[-1])):]
    pattern = left
    for index, label in enumerate(labels):
        if index:
            pattern += r"\s*[-:：/]?\s*" if all(re.search(r"[^\W\d_]", item) for item in labels[index - 1:index + 1]) else r"\s*"
        pattern += re.escape(label)
    pattern += right
    offsets = []
    cursor = 0
    for part in parts:
        offsets.append((cursor, cursor + len(part)))
        cursor += len(part) + 1
    return any(all(match.start() < end and start < match.end() for start, end in offsets)
               for match in re.finditer(pattern, text))


def row_path_locates(labels: list[str], native: Any, collapse_whitespace: bool, *,
                     require_leaf: bool = False) -> bool:
    """Keep the complete requested path within actual, contiguous labels.

    Uniqueness is resolved over all actual candidate records by the caller.
    Additional context outside it is not an extra prediction requirement.
    The optional leaf probe distinguishes a separately expressed valued row
    from its repetition as a child's parent; it does not reinterpret aliases.
    A missing requested parent, an intervening business level, or a conflicting parent
    cannot be filled from the reference or from the expected value.
    """
    if (not isinstance(native, list) or not native or len(native) > 12
            or any(not isinstance(part, str) or not part.strip() for part in native)):
        return False
    return _row_path_locates_cached(tuple(labels), tuple(native), collapse_whitespace, require_leaf=require_leaf)


@lru_cache(maxsize=32768)
def _row_path_locates_cached(labels: tuple[str, ...], native: tuple[str, ...], collapse_whitespace: bool, *,
                              require_leaf: bool = False) -> bool:
    """Memoize the same immutable label-path calculation, without values or IDs."""
    wanted = [label_text(normalize_text(label, collapse_whitespace=collapse_whitespace)) for label in labels]
    if not wanted or not all(wanted):
        return False
    pattern = ""
    for index, label in enumerate(wanted):
        if index:
            pattern += r"\s*[-:：/]?\s*" if all(re.search(r"[^\W\d_]", item) for item in wanted[index - 1:index + 1]) else r"\s*"
        pattern += re.escape(label)
    views: list[list[str]] = [[]]
    for raw in native:
        part = label_text(normalize_text(raw, collapse_whitespace=collapse_whitespace))
        variants: list[str | None] = [part]
        if require_leaf and (unit_scope_literal(part) or part.strip(" ()（）") in units(part)):
            variants.append(None)
        for token in units(part):
            if part.endswith("(" + token + ")"):
                prefix = part[:-len(token) - 2].rstrip()
            elif part.endswith(token):
                prefix = part[:-len(token)].rstrip(" (（")
            else:
                continue
            if prefix:
                variants.append(prefix)
        views = [([*view, option] if option is not None else view)
                 for view in views for option in dict.fromkeys(variants)]
        if len(views) > 512:
            return False
    return any(re.fullmatch(pattern, " ".join(view[start:end])) is not None
               for view in views for start in range(len(view))
               for end in ([len(view)] if require_leaf else range(start + 1, len(view) + 1)))


def column_path_locates(labels: list[str], native: Any, collapse_whitespace: bool,
                        unit_literals: list[str] | None = None,
                        period_literals: list[str] | None = None, *, allow_prefix: bool = False) -> bool:
    """Read explicit column labels with independently visible qualifier text.

    Unit legends and generic period descriptors may be expressed beside a
    label. Numeric years and business/group labels remain mandatory. No value
    or reference qualifier is used to construct these candidate-only views.
    """
    if path_locates(labels, native, collapse_whitespace):
        return True
    if not isinstance(native, list) or len(native) > 12 or any(not isinstance(p, str) for p in native):
        return False
    if allow_prefix and not any(re.search(r"(?:19|20)\d{2}", part) for part in native) and row_path_locates(
            labels, native, collapse_whitespace, require_leaf=True):
        # The resolver still retains every candidate and checks ambiguity
        # and required scope. A shorter authored leaf never deletes an
        # explicitly requested parent or a dated qualification.
        return True
    views: list[list[str]] = [[]]
    for raw in native:
        part = label_text(raw)
        tokens = units(part)
        unwrapped = part.strip(" ()（）")
        optional = (unwrapped in tokens or unit_scope_literal(part) or bool(re.fullmatch(
            r"Year Ended|截至[^。；;]{1,30}(?:年度|年末)|[于於]\s*\d{1,2}月\d{1,2}日", unwrapped, re.I))
            and not re.search(r"(?:19|20)\d{2}", unwrapped))
        optional |= bool(re.match(r"^截至[^。；;]{1,60}(?:年度|年末)", unwrapped)
                         and not re.search(r"(?:19|20)\d{2}", unwrapped))
        optional |= bool(re.fullmatch(r"(?:19|20)\d{2}\s*年?(?:度|末)?", unwrapped))
        variants: list[str | None] = [label_text(text) for text in label_views({"text": raw})]
        optional |= (bool(re.match(r"^(?:For the year ended|As at)\s+\d{1,2}\s+[A-Za-z]+", unwrapped, re.I))
                     and not re.search(r"(?:19|20)\d{2}", unwrapped))
        if optional:
            variants.append(None)
        for token in tokens:
            if part.endswith(token) and part != token:
                prefix = part[:-len(token)].rstrip(" (（")
                if prefix:
                    variants.append(prefix)
                    if re.fullmatch(r"(?:19|20)\d{2}\s*年?(?:度|末)?", prefix):
                        variants.append(None)
        views = [([*view, option] if option is not None else view)
                 for view in views for option in dict.fromkeys(variants)]
        if len(views) > 512:
            return False
    qualifiers = [text for text in dict.fromkeys(unit_literals or []) if unit_scope_literal(text)]
    qualifiers += [text for text in dict.fromkeys(period_literals or []) if isinstance(text, str) and text.strip()]
    if len(qualifiers) > 12:
        return False
    remaining = [label for label in labels if not any(
        label_text(label) == label_text(qualifier) for qualifier in qualifiers)]
    if remaining and len(remaining) < len(labels) and any(
        path_locates(remaining, view, collapse_whitespace) for view in views if view
    ):
        return True
    return any(path_locates(labels, candidate, collapse_whitespace)
               for view in views if view
               for candidate in [view, *([*view, q] for q in qualifiers), *([q, *view] for q in qualifiers)])


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
    for depth, label in enumerate(labels):
        matches = [item for item in group if any(
            label_in_text(label, view, collapse_whitespace)
            or any(path_locates(labels[start:end], [view], collapse_whitespace)
                   for start in range(depth + 1) for end in range(depth + 1, len(labels) + 1))
            for view in label_views(item["cell"]))]
        if axis == "row":
            if re.fullmatch(r"\d+(?:[.,]\d+)*", label):
                matches = [item for item in matches if item["cell"].get("col") == 0
                           or item["cell"].get("is_row_header") is True
                           or any(re.fullmatch(r"No\.?|Year|Rank|ID|序号|编号|年份|年度", text.strip(), re.I)
                                  for text in item["cell"].get("information_headers", []))]
            matches = [item for item in matches if (
                any(label_text(view) == label_text(label)
                    or path_locates(labels, [view], collapse_whitespace)
                    and re.sub(r"[\s:：/\-]+", "", label_text(view)) == re.sub(r"[\s:：/\-]+", "", "".join(labels))
                    or view.startswith(label) and view[len(label):].strip(" ()（）") in units(view[len(label):])
                    for view in label_views(item["cell"]))
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
    evidence: dict[str, dict[str, Any]] = {}
    scoped = scoped_qualifiers(cell, endpoint_texts)
    explicit_unit = cell.get("unit")
    if isinstance(explicit_unit, str) and not unit_applicable(
            explicit_unit, cell.get("column_header_path", []) or cell.get("information_headers", []),
            cell.get("row_header_path", []) or endpoint_texts):
        evidence["unit_applicability"] = {"status": "incorrect", "source": "printed_field_unit",
                                           "actual": explicit_unit}
    for key, value in expected.items():
        if key in cell:
            actual = cell[key]
            if key == "note_texts" and isinstance(value, list) and isinstance(actual, list):
                correct = {normalize_text(v, collapse_whitespace=True) for v in value} == {
                    normalize_text(v, collapse_whitespace=True) for v in actual}
            elif isinstance(value, str) and isinstance(actual, str):
                wanted = normalize_text(value, collapse_whitespace=True)
                found_literal = normalize_text(actual, collapse_whitespace=True)
                if key in {"unit", "currency"}:
                    # Outer legend parentheses are presentation, not an
                    # accounting sign or a change to the unit's multiplier.
                    wanted = unit_text(wanted)
                    found_literal = unit_text(found_literal)
                elif key == "period":
                    wanted, found_literal = period_text(wanted), period_text(found_literal)
                elif key == "business_scope":
                    wanted, found_literal = business_scope_text(wanted), business_scope_text(found_literal)
                correct = wanted == found_literal
            else:
                correct = value == actual
            evidence[key] = {"status": "correct" if correct else "incorrect", "source": "native_field", "actual": actual}
        elif key in scoped and isinstance(value, str):
            found = scoped[key]
            matching = [item for item in found if not (
                key == "period" and re.fullmatch(r"(?:19|20)\d{2}(?:年(?:度|末)?)?", value)
                and len(set(re.findall(r"(?:19|20)\d{2}", item["actual"]))) > 1
            ) and ((key not in {"unit", "period", "business_scope"} and label_in_text(value, item["actual"], True))
                        or key == "business_scope" and label_in_text(business_scope_text(value), business_scope_text(item["actual"]), True)
                        or key == "period" and label_in_text(period_text(value), period_text(item["actual"]), True)
                        or key == "unit" and unit_text(value) == unit_text(item["actual"])
                        or normalize_text(value, collapse_whitespace=True) == normalize_text(item["actual"], collapse_whitespace=True)
                        or key == "period" and re.fullmatch(r"(?:19|20)\d{2}年?", value)
                        and re.search(r"(?<!\d)" + re.escape(value.rstrip("年")) + r"年(?:度|末)?(?!\d)", period_text(item["actual"])))]
            evidence[key] = ({"status": "correct", "source": "candidate_scoped_qualifier", "actual": matching}
                             if matching else {"status": "incorrect", "source": "candidate_scoped_qualifier", "actual": found}
                             if found else
                             {"status": "incorrect", "source": "required_candidate_qualifier_not_expressed"})
        elif isinstance(value, str) and any(label_in_text(value, text, True) for text in endpoint_texts):
            evidence[key] = {"status": "correct", "source": "located_native_header", "actual": [
                text for text in endpoint_texts if label_in_text(value, text, True)]}
        else:
            evidence[key] = {"status": "incorrect", "source": "required_candidate_qualifier_not_expressed"}
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
    if isinstance(unit, str) and evidence.get("unit", {}).get("status") == "correct":
        def measure(text: str) -> str:
            for token in units(text):
                if unit_text(token) == unit_text(unit):
                    text = re.sub(re.escape(token) + r"(?=\)?$)", "", text)
            symbol = ("$" if unit.startswith(("$", "USD", "HKD", "美元", "港元", "港币", "港幣")) else
                      "¥" if unit.startswith(("¥", "CNY", "RMB", "人民币", "人民幣", "日元")) or unit == "元" else
                      "€" if unit.startswith(("€", "EUR", "欧元", "歐元")) else
                      "£" if unit.startswith(("£", "GBP", "英镑", "英鎊")) else None)
            if symbol:
                text = re.sub(r"^(\(?)\s*" + re.escape(symbol) + r"\s*(?=[+\-−]?\d|\()", r"\1", text)
            return text
        a, b = measure(left), measure(right)
        numeric = r"\(?[+\-−]?(?:\d+(?:[.,]\d+)*|\.\d+)\)?"
        if (re.fullmatch(numeric, a) and re.fullmatch(numeric, b)
                and a.startswith("(") == a.endswith(")") and b.startswith("(") == b.endswith(")")):
            return a == b
    if left in {"—", "–", "-"} and right in {"—", "–", "-"}:
        return True
    if not re.fullmatch(r"[\d\s,.+\-−()%‰$€£¥]+", left):
        def prose(text: str) -> str:
            text = re.sub(r"(?<!\d)((?:19|20)\d{2})[—–-]((?:19|20)\d{2})(?!\d)", r"\1—\2", text)
            return text.rstrip("。.")
        return prose(left) == prose(right)
    return False
