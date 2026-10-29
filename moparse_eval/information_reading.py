"""Candidate-only table scopes. No reference, PDF or service semantics access.

These are bounded observations of explicit captions, section introductions,
header spans, empty section rows and note definitions, not corpus judgments.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .metrics import normalize_text
from .representations import visible_text

VERSION = "candidate-information-scopes-1"
_UNIT = re.compile(r"(?:人民币|人民幣)?(?:百万元|百萬元|千元|万元|萬元|元)|RMBbn|USD|EUR|HKD|CNY|RMB|\$\s*(?:in\s+millions|bn|m)|(?:毫克|千克|公斤|吨|噸)(?:/[^()（）\s]+)?|[%‰]")
_PERIOD = re.compile(r"(?:截至[^。；;]{1,30}(?:年度|年末)|(?:19|20)\d{2}\s*年(?:度|末)?|(?<!\d)(?:19|20)\d{2}(?!\d))")
_INTRO = re.compile(r"(?:following\s+table|下表|本表|表中).*(?:percent(?:age)?|单位|單位)|(?:单位|單位)\s*[:：]", re.I)
_SECTION_PERIOD = re.compile(r"^\s*(?:[（(]\d+[)）]\s*)?((?:19|20)\d{2}\s*年度)[^。；;]{0,32}(?:情况|情況|数据|數據)\s*[:：]$")
_SCALAR = re.compile(r"\(?\s*[$€£¥]?[+\-−]?(?:\d[\d,.]*|\.\d+)\s*[%‰]?\s*\)?|[—–-]")


def units(text: str) -> list[str]:
    return list(dict.fromkeys(match.group() for match in _UNIT.finditer(normalize_text(text))))


def label_text(text: str) -> str:
    """A label may contain a separate unit suffix; never trim business words."""
    text = normalize_text(text, collapse_whitespace=True)
    return text.rstrip(" :：")


def _is_scalar(text: str) -> bool:
    return bool(_SCALAR.fullmatch(normalize_text(text).strip()))


def _header_rows(cells: list[dict[str, Any]]) -> set[int]:
    rows: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        if type(cell.get("row")) is int:
            rows.setdefault(cell["row"], []).append(cell)
    header: set[int] = set()
    for row, band in sorted(rows.items()):
        nonempty = [c for c in band if str(c.get("text", "")).strip()]
        if header and len(nonempty) == 1 and nonempty[0].get("col") == 0 and len(band) > 1:
            break
        # Dates in the first row are header observations; a labeled row with
        # actual scalar data ends the leading header band.
        scalars = [c for c in band if c.get("col", 0) > 0 and _is_scalar(str(c.get("text", "")))
                   and not re.fullmatch(r"(?:19|20)\d{2}", str(c.get("text", "")).strip())]
        if scalars:
            break
        if any(len(str(c.get("text", ""))) > 160 for c in band):
            break
        header.add(row)
        if len(header) > 12:
            return set()
    return header


def _annotate_groups(cells: list[dict[str, Any]], headers: set[int]) -> None:
    rows = sorted({c["row"] for c in cells if type(c.get("row")) is int})
    active: dict[str, Any] | None = None
    for row in rows:
        band = [c for c in cells if c.get("row") == row]
        nonempty = [c for c in band if str(c.get("text", "")).strip()]
        left = next((c for c in band if c.get("col") == 0), None)
        if row in headers or not left or not str(left.get("text", "")).strip():
            active = None
            continue
        if len(nonempty) == 1 and nonempty[0] is left and not _is_scalar(left["text"]):
            # Empty section row, bounded by the next section or unlabeled
            # subtotal. It cannot recover styling lost from a numeric row.
            active = left
            active["information_row_scope"] = [row, row]
        elif active is not None:
            active["information_row_scope"][1] = row


def read_information_observation(observation: dict[str, Any]) -> dict[str, Any]:
    derived = copy.deepcopy(observation)
    for page in derived.get("pages", []):
        blocks = page.get("blocks", [])
        section: dict[str, Any] | None = None
        for position, block in enumerate(blocks):
            text = visible_text(str(block.get("text", "")), block.get("text_format", "plain"))
            if _SECTION_PERIOD.fullmatch(text):
                section = {"text": text, "id": block.get("id"), "kind": "period"}
            elif section is not None and re.match(r"^\s*[（(]\d+[)）]", text):
                section = None
            cells = block.get("cells") or []
            if not cells:
                continue
            contexts: list[dict[str, Any]] = []
            notes: list[dict[str, Any]] = []
            parent = block.get("native_table_container") or block.get("parent_id")
            if section:
                contexts.append(section)
            # Explicit parent-owned captions/notes take precedence over
            # adjacency; parent identity never crosses to a sibling table.
            for other in blocks:
                if parent and other.get("parent_id") == parent and other is not block:
                    kind = other.get("kind", "")
                    if kind in {"table_caption", "table_footnote"}:
                        item = {"id": other.get("id"), "text": visible_text(str(other.get("text", "")),
                                other.get("text_format", "plain")), "kind": kind}
                        (notes if kind == "table_footnote" else contexts).append(item)
            for prior in reversed(blocks[:position]):
                kind = prior.get("kind", "")
                value = visible_text(str(prior.get("text", "")), prior.get("text_format", "plain"))
                if not value.strip() and not prior.get("cells"):
                    continue
                if kind == "table_caption" and not prior.get("cells"):
                    contexts.append({"id": prior.get("id"), "text": value, "kind": "table_caption"})
                    continue
                if not prior.get("cells") and _INTRO.search(value):
                    contexts.append({"id": prior.get("id"), "text": value, "kind": "explicit_table_introduction"})
                break
            for following in blocks[position + 1:]:
                kind = following.get("kind", "")
                value = visible_text(str(following.get("text", "")), following.get("text_format", "plain"))
                if not value.strip() and not following.get("cells"):
                    continue
                if kind == "table_footnote" and not following.get("cells"):
                    notes.append({"id": following.get("id"), "text": value, "kind": kind})
                else:
                    break
            headers = _header_rows(cells)
            _annotate_groups(cells, headers)
            corner = [c for c in cells if c.get("row") in headers and c.get("col") == 0
                      and units(str(c.get("text", "")))]
            for cell in cells:
                row, col = cell.get("row"), cell.get("col")
                column_headers = [c for c in cells if c.get("row") in headers
                                  and type(col) is int and type(c.get("col")) is int
                                  and c["col"] <= col < c["col"] + c.get("col_span", 1)]
                row_labels = [c for c in cells if c.get("col") == 0 and type(row) is int
                              and c.get("row", -1) <= row < c.get("row", -1) + c.get("row_span", 1)]
                cell["information_context"] = copy.deepcopy(contexts)
                cell["information_notes"] = copy.deepcopy(notes)
                cell["information_headers"] = [c["text"] for c in column_headers]
                cell["information_row_labels"] = [c["text"] for c in row_labels]
                cell["information_table_units"] = [c["text"] for c in corner]
    return derived


def scalar_notes(cell: dict[str, Any]) -> tuple[str, list[str] | None]:
    """Separate a superscript only with an actual scoped note definition.

    Scientific notation and exponents without a note remain mathematical text.
    """
    text = str(cell.get("text", ""))
    notes = cell.get("note_markers")
    definitions = {match.group(1) for item in cell.get("information_notes", [])
                   if (match := re.match(r"\s*([0-9]{1,2}|[*†‡])(?:\s+|[.)、：:])", item["text"]))}
    annotations = [a for a in cell.get("inline_annotations", []) if a.get("type") == "superscript"]
    if annotations and all(a.get("text") in definitions for a in annotations):
        spans = sorted(a.get("span", []) for a in annotations)
        if all(len(s) == 2 and all(type(v) is int for v in s) and 0 <= s[0] < s[1] <= len(text) for s in spans):
            if all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False)):
                body = text
                for start, end in reversed(spans):
                    body = body[:start] + body[end:]
                if _is_scalar(body):
                    return body, [text[a:b] for a, b in spans]
    latex = re.fullmatch(r"\s*\\\(\s*([+\-−]?(?:\d[\d,.]*|\.\d+))\s*\^\s*\{?([0-9]{1,2}|[*†‡])\}?\s*\\\)\s*", text)
    if latex and latex[2] in definitions:
        return latex[1], [latex[2]]
    return text, notes


def scoped_qualifiers(cell: dict[str, Any], endpoint_texts: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Read qualifiers independent of the expected qualifier or value."""
    result: dict[str, list[dict[str, Any]]] = {"unit": [], "period": []}
    direct = [*endpoint_texts, *cell.get("information_headers", [])]
    contexts = cell.get("information_context", [])
    numeric, _notes = scalar_notes(cell)
    own_units = units(numeric) if _is_scalar(numeric) else []
    row_units = [u for text in cell.get("information_row_labels", []) for u in units(text)]
    column_units = [u for text in [*direct, *cell.get("units", [])] for u in units(text)]
    if any(re.search(r"expressed\s+as\s+a\s+percentage", text, re.I) for text in cell.get("units", [])):
        column_units.append("%")
    actual_units = own_units or column_units or row_units
    if not actual_units:
        # A shared currency never qualifies an explicit ratio/change column.
        ratio = any(re.search(r"同比|佔|占|比例|比率|percent|change|rate|ratio", text, re.I) for text in direct)
        if not ratio:
            actual_units = [u for text in cell.get("information_table_units", []) for u in units(text)]
            for item in contexts:
                text = item["text"]
                if re.search(r"(?:expressed\s+as\s+a\s+percentage|占收入百分比)", text, re.I):
                    actual_units.append("%")
                elif _INTRO.search(text):
                    actual_units.extend(units(text))
    for unit in dict.fromkeys(actual_units):
        result["unit"].append({"actual": unit, "source": "candidate_scoped_unit"})
    # Keep whole literal labels as period evidence: e.g. an English date is
    # meaningful without attempting date conversion.
    period_texts = [*direct, *cell.get("periods", []), *(item["text"] for item in contexts if item["kind"] == "period")]
    result["period"] = [{"actual": text, "source": "candidate_scoped_period"} for text in dict.fromkeys(period_texts)]
    return result
