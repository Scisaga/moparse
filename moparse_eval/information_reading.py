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
_UNIT = re.compile(r"(?:(?:人民币|人民幣|美元|港元|港幣|港币|欧元|歐元)?(?:万亿元|萬億元|千亿元|千億元|百亿元|百億元|十亿元|十億元|亿元|億元|千万元|千萬元|百万元|百萬元|千元|万元|萬元|元)|RMBbn|USD|EUR|HKD|CNY|RMB|\$\s*(?:in\s+millions|bn|m)|[个個]?百分点|[个個]?百分點|percentage points?|basis points?|bps|(?:毫克|千克|公斤|(?:千萬|千万|百萬|百万|萬|万|千)?(?:吨|噸))|[%‰])(?:/[A-Za-z\u3400-\u9fff0-9³²]+)?")
_PERIOD = re.compile(r"(?:截至[^。；;]{1,30}(?:年度|年末)|(?:19|20)\d{2}\s*年(?:度|末)?|(?<!\d)(?:19|20)\d{2}(?!\d))")
_INTRO = re.compile(r"(?:following\s+table|下表|本表|表中).*(?:percent(?:age)?|单位|單位)|(?:单位|單位)\s*[:：]", re.I)
_SECTION_PERIOD = re.compile(r"^\s*(?:[（(]\d+[)）]\s*)?((?:19|20)\d{2}\s*年度)[^。；;]{0,32}(?:情况|情況|数据|數據)\s*[:：]$")
_SCALAR = re.compile(r"\(?\s*[$€£¥]?\s*[+\-−]?(?:\d[\d,.]*|\.\d+)\s*[%‰]?\s*\)?|[—–-]")


def units(text: str) -> list[str]:
    text = normalize_text(text)
    explicit = list(re.finditer(r"(?:^|[（(\s])(?:单位|單位)\s*[:：(（]\s*([^()（）,，。;；\n]{1,48})", text))
    known = list(_UNIT.finditer(text))
    values = [re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "",
                     re.split(r"(?:币种|幣種|currency)\s*[:：]", m[1], maxsplit=1, flags=re.I)[0].strip())
              for m in explicit]
    values += [m.group() for m in known
               if not any(a.start(1) <= m.start() and m.end() <= a.end(1) for a in explicit)]
    values += [m.group() for m in re.finditer(r"(?<!\w)(?:人|次|股|台|家|个|個|天|日)(?!\w)", text)
               if not any(a.start(1) <= m.start() and m.end() <= a.end(1) for a in explicit)
               and not any(a.start() <= m.start() and m.end() <= a.end() for a in known)]
    return list(dict.fromkeys(values))


def unit_scope_literal(text: str) -> bool:
    text = normalize_text(text, collapse_whitespace=True)
    unwrapped = text.strip(" ()（）")
    return bool(units(text) and (unwrapped in units(text) or re.search(
        r"(?:^|[（(])\s*(?:单位|單位)\s*[:：（(]", text)
        or re.fullmatch(r"\$\s*in\s+millions(?:,\s*except\s+per\s+share\s+(?:data|amounts))?", unwrapped, re.I)))


def label_text(text: str) -> str:
    """A label may contain a separate unit suffix; never trim business words."""
    text = normalize_text(text, collapse_whitespace=True)
    return text.rstrip(" :：")


def _is_scalar(text: str) -> bool:
    return bool(_SCALAR.fullmatch(normalize_text(text).strip()))


def _scalar_units(text: str) -> list[str]:
    text = normalize_text(text).strip()
    if _is_scalar(text):
        return units(text)
    for match in _UNIT.finditer(text):
        if match.end() == len(text) and _is_scalar(text[:match.start()]):
            return [match.group()]
    return []


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
    bands: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        if type(cell.get("row")) is int:
            bands.setdefault(cell["row"], []).append(cell)
    active: dict[str, Any] | None = None
    for row, band in sorted(bands.items()):
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
            label = left["text"].strip()
            sibling = re.match(r"^([一二三四五六七八九十百]+)([、.])", label)
            prior = re.match(r"^([一二三四五六七八九十百]+)([、.])", active["text"].strip())
            if sibling and prior and sibling[2] == prior[2] and sibling[1] != prior[1]:
                active = None
                continue
            active["information_row_scope"][1] = row
            total = re.fullmatch(r"Total\s+(.+)", label, re.I)
            if total and total[1].casefold() == active["text"].strip(" :：").casefold():
                active = None


def _header_scopes(cells: list[dict[str, Any]], leading: set[int]) -> list[tuple[set[int], set[int]]]:
    if not leading:
        return []
    end = max(c.get("row", 0) + c.get("row_span", 1) for c in cells)
    corner = next((c for c in cells if c.get("row") == min(leading) and c.get("col") == 0), None)
    bands = [leading]
    if corner:
        rows: dict[int, list[dict[str, Any]]] = {}
        for cell in cells:
            if type(cell.get("row")) is int:
                rows.setdefault(cell["row"], []).append(cell)
        for row in range(max(leading) + 1, end):
            band = rows.get(row, [])
            stub = next((c for c in band if c.get("col") == 0), None)
            if (stub and stub["text"].strip() == corner["text"].strip()
                    and any(_PERIOD.search(c["text"]) for c in band if c.get("col", 0) > 0)
                    and all(not _is_scalar(c["text"]) or re.fullmatch(r"(?:19|20)\d{2}", c["text"].strip()) for c in band)):
                bands.append({row})
    return [(band, set(range(max(band) + 1, min(bands[i + 1]) if i + 1 < len(bands) else end)))
            for i, band in enumerate(bands)]


def read_information_observation(observation: dict[str, Any]) -> dict[str, Any]:
    derived = copy.deepcopy(observation)
    for page in derived.get("pages", []):
        blocks = page.get("blocks", [])
        section: dict[str, Any] | None = None
        for position, block in enumerate(blocks):
            text = visible_text(str(block.get("text", "")), block.get("text_format", "plain"))
            lines = [line for line in text.splitlines() if line.strip()]
            tail = lines[-1].strip() if lines else ""
            if _SECTION_PERIOD.fullmatch(tail):
                section = {"text": tail, "id": block.get("id"), "kind": "period"}
            elif section is not None and re.match(r"^\s*[（(]\d+[)）]", text):
                section = None
            cells = block.get("cells") or []
            if not cells:
                continue
            contexts: list[dict[str, Any]] = []
            notes: list[dict[str, Any]] = []
            numbered_notes: list[dict[str, Any]] = []
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
                elif kind in {"text", "paragraph", "list"} and not following.get("cells"):
                    lines = [line.strip() for line in value.splitlines() if line.strip()]
                    if not lines or not all(re.match(r"[0-9]{1,2}(?:\s+|[.)、：:])", line) for line in lines):
                        break
                    numbered_notes.extend({"id": following.get("id"), "text": line, "kind": kind} for line in lines)
                else:
                    break
            markers = [int(match[0]) for item in numbered_notes
                       if (match := re.match(r"[0-9]{1,2}", item["text"]))]
            if len(markers) < 2 or markers != list(range(1, len(markers) + 1)):
                numbered_notes = []
            headers = _header_rows(cells)
            scopes = _header_scopes(cells, headers)
            all_headers = set().union(*(band for band, _body in scopes)) if scopes else headers
            for band, body in scopes:
                for cell in cells:
                    if cell.get("row") in band:
                        cell["information_header_body_rows"] = sorted(body)
                        cell["information_scope_switch"] = len(scopes) > 1
            _annotate_groups(cells, all_headers)
            corner = [c for c in cells if c.get("row") in headers and c.get("col") == 0
                      and units(str(c.get("text", "")))]
            table_units = [c["text"] for c in corner]
            headers_by_body: dict[int, list[dict[str, Any]]] = {}
            for band, body in scopes:
                scoped_headers = [c for c in cells if c.get("row") in band]
                headers_by_body.update((r, scoped_headers) for r in body)
            labels_by_row: dict[int, list[str]] = {}
            for label in cells:
                if label.get("col") == 0 and type(label.get("row")) is int:
                    for r in range(label["row"], label["row"] + label.get("row_span", 1)):
                        labels_by_row.setdefault(r, []).append(label["text"])
            for cell in cells:
                row, col = cell.get("row"), cell.get("col")
                column_headers = [c for c in headers_by_body.get(row, []) if type(col) is int and type(c.get("col")) is int
                                  and c["col"] <= col < c["col"] + c.get("col_span", 1)]
                cell["information_context"] = contexts
                cell["information_notes"] = notes
                cell["information_ambiguous_notes"] = numbered_notes
                cell["information_headers"] = [c["text"] for c in column_headers]
                cell["information_row_labels"] = labels_by_row.get(row, [])
                cell["information_table_units"] = table_units
    return derived


def _note_definitions(cell: dict[str, Any], *, ambiguous: bool = False) -> set[str]:
    note_texts = [*(item["text"] for item in cell.get("information_notes", [])), *cell.get("notes", [])]
    if ambiguous:
        note_texts += [item["text"] for item in cell.get("information_ambiguous_notes", [])]
    return {match.group(1) for text in note_texts for line in text.splitlines()
            if (match := re.match(r"\s*([0-9]{1,2}|[*†‡])(?:\s+|[.)、：:])", line))}


def ambiguous_note_scalar(cell: dict[str, Any]) -> bool:
    """A bare caret with a matching scoped note lacks explicit type evidence."""
    match = re.fullmatch(r"\s*(.*?)\s*\^\s*(?:\{([0-9]{1,2}|[*†‡])\}|([0-9]{1,2}|[*†‡]))\s*",
                         str(cell.get("text", "")))
    return bool(match and _is_scalar(match[1]) and (match[2] or match[3]) in _note_definitions(cell, ambiguous=True))


def scalar_notes(cell: dict[str, Any]) -> tuple[str, list[str] | None]:
    """Separate a superscript only with an actual scoped note definition.

    Scientific notation and exponents without a note remain mathematical text.
    """
    text = str(cell.get("text", ""))
    notes = cell.get("note_markers")
    definitions = _note_definitions(cell)
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
    column_texts = [*cell.get("column_header_path", []), *cell.get("information_headers", [])]
    if not column_texts:
        column_texts = endpoint_texts
    contexts = cell.get("information_context", [])
    numeric, _notes = scalar_notes(cell)
    own_units = _scalar_units(numeric)
    row_units = [u for text in [*cell.get("row_header_path", []), *cell.get("information_row_labels", [])] for u in units(text)]
    ratio = any(re.search(r"同比|佔|占|比例|比率|percent|change|rate|ratio", text, re.I) for text in column_texts)
    column_units = [u for text in [*column_texts, *cell.get("units", [])] for u in units(text)]
    if ratio:
        column_units = [u for u in column_units if re.fullmatch(
            r"[%‰]|[个個]?百分[点點]|percentage points?|basis points?|bps", u, re.I)]
        row_units = []
    if any(re.search(r"expressed\s+as\s+a\s+percentage", text, re.I) for text in cell.get("units", [])):
        column_units.append("%")
    actual_units = own_units or column_units or row_units
    row_labels = [*cell.get("row_header_path", []), *cell.get("information_row_labels", [])]
    legends = [*direct, *cell.get("units", []), *(item["text"] for item in contexts)]
    currency = re.match(r"\(?\s*([$€£¥])", numeric) if _is_scalar(numeric) else None
    if (currency and any(re.search(r"per\s+(?:diluted\s+)?share|每股", label, re.I) for label in row_labels)
            and any(re.search(r"except\s+per\s+share\s+(?:data|amounts)|每股.{0,8}除外", text, re.I) for text in legends)):
        actual_units = [currency[1] + " per share"]
    if not actual_units:
        # A shared currency never qualifies an explicit ratio/change column.
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
    # A declared single-year section introduction contains an explicit
    # period even when its business description has no separating space.
    # Do not collapse ranges or multi-year descriptions to one endpoint.
    period_texts += [match[1] for text in period_texts
                     if (match := _SECTION_PERIOD.fullmatch(text))
                     and len(re.findall(r"(?:19|20)\d{2}", text)) == 1]
    result["period"] = [{"actual": text, "source": "candidate_scoped_period"} for text in dict.fromkeys(period_texts)]
    return result
