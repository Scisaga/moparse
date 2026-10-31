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

VERSION = "candidate-information-scopes-2"
_UNIT = re.compile(r"(?:(?:人民币|人民幣|美元|港元|港幣|港币|欧元|歐元)?(?:万亿元|萬億元|千亿元|千億元|百亿元|百億元|十亿元|十億元|亿元|億元|千万元|千萬元|百万元|百萬元|千元|万元|萬元|元)|RMBbn|RMB['’]000|(?:RMB|USD|HKD|CNY)\s+million|in\s+million|\bcontracts?\b|USD|EUR|HKD|CNY|RMB|\$\s*(?:in\s+millions|bn|m)|['’]\s*000\s+(?:contracts|lots)|[个個]?百分点|[个個]?百分點|percentage points?|basis points?|bps|(?:毫克|千克|公斤|(?:千萬|千万|百萬|百万|萬|万|千)?(?:吨|噸))|[%‰$€£¥])(?:/[A-Za-z\u3400-\u9fff0-9³²]+)?")
_PERIOD = re.compile(r"(?:截至[^。；;]{1,30}(?:年度|年末)|(?:19|20)\d{2}\s*年(?:度|末)?|(?<!\d)(?:19|20)\d{2}(?!\d))")
_INTRO = re.compile(r"(?:following\s+table|下表|本表|表中).*(?:percent(?:age)?|单位|單位)|(?:单位|單位|Units?)\s*[:：]", re.I)
_PRINTED_CAPTION = re.compile(r"^(?:Table|图表|圖表|表)[\s\-–—]*\d+(?:[.\-]\d+)*(?:[.:：]\s*|\s+)", re.I)
_PRINTED_REPORT_TITLE = re.compile(
    r"(?:(?:[^\s。；;:：]{1,80}(?:有限公司|股份公司))\s+)?(?:19|20)\d{2}\s*年?\s*年度(?:报告|報告)|"
    r"Annual\s+Report\s+(?:19|20)\d{2}", re.I)
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
    values += [unit for word, unit in (("次数", "次"), ("次數", "次"), ("年限", "年"),
                                      ("人数", "人"), ("人數", "人"), ("股数", "股"), ("股數", "股"))
               if word in text]
    return list(dict.fromkeys(values))


def metric_units(text: str) -> list[str]:
    """Only a metric's unit annotation qualifies its numbers.

    Currency names and scalar conditions within a metric name do not: a
    'USD depreciates 5%' scenario can still report its impact in CNY million.
    """
    text = normalize_text(text, collapse_whitespace=True)
    return [token for token in units(text) if any(
        (match.end() == len(text) or text[match.end():].strip() == ")")
        and (not text[:match.start()].rstrip()[-1:].isdigit())
        for match in re.finditer(re.escape(token), text))
        or any(word in text for word in {"次": ("次数", "次數"), "年": ("年限",),
                                        "人": ("人数", "人數"), "股": ("股数", "股數")}.get(token, ()))]


def period_literals(texts: list[str]) -> list[str]:
    """Read explicit period parts within one already scoped field/header path."""
    result = list(texts)
    years = list(dict.fromkeys(match[0] for text in texts for match in re.finditer(r"(?<!\d)(?:19|20)\d{2}\s*年", text)))
    simple_years = list(dict.fromkeys(view for text in texts for view in label_views({"text": text})
                                    if re.fullmatch(r"(?:19|20)\d{2}", view.strip())))
    for text in texts:
        if len(set(re.findall(r"(?:19|20)\d{2}", text))) == 1:
            result += [match[0] for match in re.finditer(r"(?<!\d)(?:19|20)\d{2}\s*年(?:度|末)?", text)]
        result += [match[0] for match in re.finditer(r"(?:19|20)\d{2}年(?:較|较|比)(?:19|20)\d{2}年|期初|期末|本期|本報告期|本报告期", text)]
    if len(years) == 1:
        year = re.sub(r"\s+", "", years[0])
        for text in texts:
            result += [year + match[0] for match in re.finditer(r"(?<!\d)(?:第?[一二三四1-4]季度|\d{1,2}月\d{1,2}日)", text)
                       if not re.search(r"(?:19|20)\d{2}", text)]
            result += [match[1] + year + match[2] for match in re.finditer(
                r"(截至|於|于)([一二三四五六七八九十\d]{1,3}月[一二三四五六七八九十\d]{1,3}日止年度)", text)]
    if len(simple_years) == 1:
        for text in texts:
            if re.search(r"(?:19|20)\d{2}|[零〇一二三四五六七八九]{4}年", text):
                continue
            result += [match[0].strip() + " " + simple_years[0] for match in re.finditer(
                r"(?:For the year ended|As at)\s+\d{1,2}\s+[A-Za-z]+", text, re.I)]
    return list(dict.fromkeys(result))


def _year_end_comparison(headers: list[str], peers: list[str], contexts: list[dict[str, Any]]) -> str | None:
    """Read 'this year end versus last year end' inside an explicit annual frame."""
    if not any(re.search(r"本年末比上年末", text) for text in headers):
        return None
    scope = [item["text"] for item in contexts if item.get("kind") in {"period", "table_caption"}]
    annual_years = {match[1] for text in scope for match in re.finditer(r"(?<!\d)((?:19|20)\d{2})\s*年\s*度", text)}
    scope_years = {year for text in scope for year in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text)}
    if len(annual_years) != 1 or scope_years != annual_years:
        return None
    current = next(iter(annual_years))
    previous = str(int(current) - 1)
    printed_ends = {match[1] for text in peers
                    if (match := re.fullmatch(r"\s*((?:19|20)\d{2})\s*年\s*末\s*", text))}
    if {current, previous} <= printed_ends:
        return current + "年末比" + previous + "年末"
    return None


def _numbered_record_labels(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read an adjacent printed record number and name as one label view."""
    extra = []
    for number in cells:
        if number.get("col") != 0 or not re.fullmatch(r"\d{1,3}", str(number.get("text", ""))):
            continue
        names = [cell for cell in cells if cell.get("row") == number.get("row")
                 and cell.get("col") == 1 and cell.get("row_span", 1) == number.get("row_span", 1)
                 and str(cell.get("text", "")).strip() and not _is_scalar(str(cell["text"]))]
        if len(names) != 1:
            continue
        name = names[0]
        extra.append({**number, "id": str(number.get("id")) + ":record_label", "col_span": 1 + name.get("col_span", 1),
                      "text": str(number["text"]) + " " + str(name["text"]),
                      "readback_evidence": "adjacent_printed_number_and_name",
                      "native_components": [number.get("id"), name.get("id")]})
    return extra


def unit_scope_literal(text: str) -> bool:
    text = normalize_text(text, collapse_whitespace=True)
    unwrapped = text.strip(" ()（）")
    in_clause = re.fullmatch(r"in\s+(.+)", unwrapped, re.I)
    return bool(units(text) and (unwrapped in units(text) or re.search(
        r"(?:^|[（(])\s*(?:单位|單位)\s*[:：（(]", text)
        or in_clause and in_clause[1] in units(in_clause[1])
        or re.fullmatch(r"\$\s*in\s+millions(?:,\s*except\s+per\s+share\s+(?:data|amounts))?", unwrapped, re.I)))


def label_text(text: str) -> str:
    """A label may contain a separate unit suffix; never trim business words."""
    text = normalize_text(text, collapse_whitespace=True)
    # Read typography in labels only. Values keep their original signs,
    # exponents, footnote spelling and strict-character diagnostics.
    text = text.translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉˒", "01234567890123456789,"))
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"(?<=\d)\s+(?=年|月|日)", "", text)
    text = re.sub(r"^[-–—•]\s*(?=[^\W\d_])", "", text)
    text = re.sub(r"(January|February|March|April|May|June|July|August|September|October|November|December)(?=\d)", r"\1 ", text)
    text = re.sub(r"^其中\s*[:：]\s*", "", text)
    text = re.sub(r"\s*(?:\.{3,}|…{2,})$", "", text)
    return text.rstrip(" :：")


def label_views(cell: dict[str, Any]) -> list[str]:
    """Read a textual label's explicit note formatting, retaining its raw view."""
    cached = cell.get("information_label_views")
    if isinstance(cached, list) and all(isinstance(text, str) for text in cached):
        return cached
    text = str(cell.get("text", ""))
    definitions = _note_definitions(cell)
    def note(match: re.Match[str]) -> str:
        word, marker = match[1], match[2]
        return word.replace(r"\ ", " ").strip() if marker in definitions else match[0]
    projected = re.sub(r"\\\(\s*([A-Za-z][A-Za-z\s\\]{1,80})\s*\^\s*\{?([0-9]{1,2})\}?\s*\\\)", note, text)
    label_notes = _note_definitions(cell, ambiguous=True)
    spaced = re.sub(r"(?<=[A-Za-z)])\s+([0-9]{1,2})(?=\s*[(,]|$)",
                    lambda match: match[1] if match[1] in label_notes else match[0], text)
    bilingual = re.match(r"\s*((?:19|20)\d{2})\s*([零〇一二三四五六七八九]{4})年", text)
    years = []
    if bilingual and bilingual[2].translate(str.maketrans("零〇一二三四五六七八九", "00123456789")) == bilingual[1]:
        years = [bilingual[1], bilingual[1] + "年"]
    return list(dict.fromkeys([text, projected, spaced, *years]))


def _is_scalar(text: str) -> bool:
    return bool(_SCALAR.fullmatch(normalize_text(text).strip()))


def _value_expression(text: str) -> bool:
    """Recognize a data expression without interpreting its value or notes."""
    text = normalize_text(text).strip()
    return (_is_scalar(text) or bool(_scalar_units(text)) or bool(re.fullmatch(
        r"(?:\\\(\s*)?[+\-−]?(?:\d[\d,.]*|\.\d+)\s*\^\s*(?:\{\s*\d+\s*\}|\d+)(?:\s*\\\))?", text))
        or bool(re.fullmatch(r"[+\-−]?[\d,.]+[%‰][\d,.]+", text)))


def _header_year(text: str) -> bool:
    text = normalize_text(text, collapse_whitespace=True)
    if re.fullmatch(r"(?:19|20)\d{2}(?:年(?:度|末)?)?", text):
        return True
    match = re.match(r"(?:19|20)\d{2}(?:年)?", text)
    return bool(match and text[match.end():].strip() in units(text[match.end():]))


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
    first_stub = ""
    for row, band in sorted(rows.items()):
        nonempty = [c for c in band if str(c.get("text", "")).strip()]
        if not nonempty:
            continue
        if len(nonempty) == 1 and nonempty[0].get("col") == 0:
            left = nonempty[0]
            if (len(band) > 1 or left.get("col_span", 1) > 1) and not (
                _PERIOD.fullmatch(str(left.get("text", "")).strip())
                or unit_scope_literal(str(left.get("text", "")))
            ):
                break
        # Dates in the first row are header observations; a labeled row with
        # actual scalar data ends the leading header band.
        scalars = [c for c in band if c.get("col", 0) > 0 and _is_scalar(str(c.get("text", "")))
                   and not _header_year(str(c.get("text", "")))]
        if scalars:
            break
        if any(c.get("col", 0) > 0 and _value_expression(str(c.get("text", "")))
               and not _header_year(str(c.get("text", ""))) for c in band):
            break
        stub = next((str(c.get("text", "")).strip() for c in band if c.get("col") == 0), "")
        declared = nonempty and all(c.get("is_column_header") or c.get("native_tag") == "th"
                                    and c.get("native_attributes", {}).get("scope") != "row" for c in nonempty)
        dated_subheader = (any(c.get("row") in header and c.get("col_span", 1) > 1 for c in cells)
                           and any(c.get("col", 0) > 0 and _header_year(str(c.get("text", ""))) for c in band))
        if header and stub and stub != first_stub and not declared and not dated_subheader and not unit_scope_literal(stub):
            if not first_stub or not unit_scope_literal(first_stub):
                break
        if any(len(str(c.get("text", ""))) > 160 for c in band):
            break
        header.add(row)
        if not first_stub:
            first_stub = stub
        if len(header) > 12:
            return set()
    return header


def _printed_period_caption(text: str, cells: list[dict[str, Any]]) -> bool:
    """Read a short year-leading title that names an actual table header."""
    text = normalize_text(text, collapse_whitespace=True).strip()
    if (len(text) > 120 or re.search(r"[\r\n。；;!?！？]", text)
            or not re.match(r"(?:19|20)\d{2}(?:\s*年|\s+)", text)
            or len(set(re.findall(r"(?:19|20)\d{2}", text))) != 1):
        return False
    headers = _header_rows(cells)
    return any(2 <= len(label := str(cell.get("text", "")).strip()) <= 48
               and not _is_scalar(label) and label in text
               for cell in cells if cell.get("row") in headers)


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


def _prose_fields(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Read explicitly delimited record assertions from the candidate itself.

    These are a scoring view of printed text, never a replacement native
    table or a business inference. Free text is retained as free text.
    """
    if block.get("cells") or block.get("kind") not in {"text", "paragraph", "list"}:
        return []
    text = visible_text(str(block.get("text", "")), block.get("text_format", "plain"))
    records = []
    for number, line in enumerate(text.splitlines()):
        parts = [part.strip() for part in re.split(r"[；;]", line) if part.strip()]
        pairs = []
        subjects: list[str] = []
        for index, part in enumerate(parts):
            match = re.fullmatch(r"([^:：]{1,160})\s*[:：]\s*(.{1,512})", part)
            if match:
                pairs.append((match[1].strip(), match[2].removesuffix("。")))
            elif index == 0 and len(parts) > 1:
                subjects.extend(label.strip() for label in re.split(r"\s+/\s+|\s*>\s*", part) if label.strip())
        if not pairs or not (subjects or len(pairs) > 1):
            continue
        identities = [*subjects, *(value for _key, value in pairs)]
        unit_subjects = [(key, value) for key, value in pairs
                         if unit_scope_literal(key) and not _is_scalar(value)]
        periods = [value for key, value in pairs if re.fullmatch(r"期间|期間|年度|日期|Period|Date|Year", key, re.I)]
        context = [{"id": block.get("id"), "kind": "period", "text": value} for value in periods]
        context += [{"id": block.get("id"), "kind": "explicit_table_introduction", "text": key + ":" + value}
                    for key, value in pairs if re.fullmatch(r"单位|單位|Units?", key, re.I)]
        context += [{"id": block.get("id"), "kind": "explicit_table_introduction", "text": "Unit:" + key}
                    for key, _value in unit_subjects]
        scopes = [{"id": block.get("id"), "kind": "table_caption", "text": value}
                  for key, value in pairs if re.fullmatch(r"范围|範圍|Scope", key, re.I)]
        identity = f"{block.get('id', 'text')}:record:{number}"
        cells = [{"id": f"{identity}:field:{index}", "text": value,
                  "column_header_path": [key], "information_record_labels": identities,
                  "information_row_labels": [*subjects, *(value for _key, value in unit_subjects)],
                  "information_context": [*context, *(scopes if not any(re.search(r"(?:19|20)\d{2}", text)
                      for text in [key, *periods]) else [])], "periods": periods, "text_format": "plain",
                  "native_path": block.get("native_path"), "information_prose_record": True}
                 for index, (key, value) in enumerate(pairs)]
        records.append({**block, "id": identity, "text": "", "cells": cells,
                        "kind": "text_record", "readback_evidence": "printed_key_value_record"})
    return records


def read_information_observation(observation: dict[str, Any]) -> dict[str, Any]:
    derived = copy.deepcopy(observation)
    annual = [block for page in derived.get("pages", []) for block in page.get("blocks", [])
              if (block.get("kind") in {"header", "title", "heading"}
                  or block.get("kind") in {"text", "paragraph"}
                  and _PRINTED_REPORT_TITLE.fullmatch(visible_text(str(block.get("text", "")),
                      block.get("text_format", "plain")).strip()))
              and re.search(r"(?:19|20)\d{2}\s*年?\s*年度报告|Annual\s+Report\s+(?:19|20)\d{2}", str(block.get("text", "")), re.I)]
    annual_years = {year for block in annual for year in re.findall(r"(?:19|20)\d{2}", str(block.get("text", "")))}
    report_period = ({"id": annual[0].get("id"), "text": annual[0]["text"], "kind": "period"}
                     if len(annual_years) == 1 else None)
    for page in derived.get("pages", []):
        blocks = page.get("blocks", [])
        prose = [record for block in blocks for record in _prose_fields(block)]
        if report_period:
            for record in prose:
                for cell in record["cells"]:
                    if not any(re.search(r"(?:19|20)\d{2}", text) for text in [
                        *cell["column_header_path"], *cell.get("periods", []),
                        *(item["text"] for item in cell["information_context"]),
                    ]):
                        cell["information_context"].append(report_period)
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
            for cell in cells:
                cell.pop("information_label_views", None)
            if not cells:
                continue
            # Read printed qualifiers without creating competing value or
            # identity assertions over already structured cells.
            printed = _prose_fields({**block, "cells": [], "kind": "paragraph"})
            printed_contexts: dict[str, list[dict[str, Any]]] = {}
            if len(printed) == 1:
                for field in printed[0]["cells"]:
                    key = normalize_text(field["column_header_path"][0], collapse_whitespace=True)
                    if key in printed_contexts:
                        printed_contexts[key] = []
                    else:
                        printed_contexts[key] = field["information_context"]
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
                if (kind == "table_caption" or _PRINTED_CAPTION.match(value)
                        or _printed_period_caption(value, cells)) and not prior.get("cells"):
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
                printed_path = cell.get("column_header_path", [])
                printed_key = normalize_text(" / ".join(printed_path), collapse_whitespace=True) if (
                    isinstance(printed_path, list) and all(isinstance(p, str) for p in printed_path)) else ""
                cell["information_context"] = [*contexts, *printed_contexts.get(printed_key, [])]
                cell["information_notes"] = notes
                cell["information_ambiguous_notes"] = numbered_notes
                cell["information_headers"] = [c["text"] for c in column_headers]
                all_column_headers = headers_by_body.get(row, [])
                if any(re.search(r"同比|本年.*上年|[Cc]hange", text) for text in cell["information_headers"]):
                    header_years = {year for header in all_column_headers for year in re.findall(r"(?:19|20)\d{2}", header["text"])}
                    if len(header_years) >= 2:
                        cell["information_comparison_periods"] = [header["text"] for header in all_column_headers
                            if re.search(r"(?:截至|於|于)[一二三四五六七八九十\d]{1,3}月[一二三四五六七八九十\d]{1,3}日止年度", header["text"])]
                cell["information_row_labels"] = labels_by_row.get(row, [])
                cell["information_table_units"] = table_units
                path = cell.get("column_header_path", [])
                if any(re.search(r"同比|[Cc]hange", text) for text in path):
                    # Other explicitly printed measures in this very record
                    # establish the comparison's annual frame, just as the
                    # active headers do in a table. Never inherit money units.
                    record_headers = [text for other in cells for text in other.get("column_header_path", [])]
                    if len({year for text in record_headers for year in re.findall(r"(?:19|20)\d{2}", text)}) >= 2:
                        cell["information_comparison_periods"] = [text for text in record_headers
                            if re.search(r"(?:截至|於|于)[一二三四五六七八九十\d]{1,3}月[一二三四五六七八九十\d]{1,3}日止年度", text)]
                if report_period and not any(re.search(r"(?:19|20)\d{2}|[二零〇一三四五六七八九]{4}年", text)
                        for text in [*cell["information_headers"], *cell.get("column_header_path", []),
                                     *cell.get("periods", []),
                                     *(item["text"] for item in cell["information_context"])]):
                    cell["information_context"] = [*cell["information_context"], report_period]
                # Only the active grid header band or this very printed
                # record can supply endpoints. Other rows and tables cannot.
                relative_headers = [*cell["information_headers"], *cell.get("column_header_path", [])]
                if any(re.search(r"本年末比上年末", text) for text in relative_headers):
                    record_headers = [text for other in cells
                        if (cell.get("record_id") and other.get("record_id") == cell["record_id"]
                            or not cell.get("record_id") and cell.get("row_header_path")
                            and other.get("row_header_path") == cell["row_header_path"])
                        for text in other.get("column_header_path", [])]
                    comparison = _year_end_comparison(
                        relative_headers, [header["text"] for header in all_column_headers] + record_headers,
                        cell["information_context"],
                    )
                    if comparison is not None:
                        cell["information_comparison_periods"] = [
                            *cell.get("information_comparison_periods", []), comparison,
                        ]
            block["cells"] = [*cells, *_numbered_record_labels(cells)]
            for cell in block["cells"]:
                cell["information_label_views"] = label_views(cell)
        page["blocks"] = [*blocks, *prose]
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
    column_texts = [*cell.get("column_header_path", []), *cell.get("information_headers", [])]
    direct = [*endpoint_texts, *column_texts]
    if not column_texts:
        column_texts = endpoint_texts
    contexts = cell.get("information_context", [])
    numeric, _notes = scalar_notes(cell)
    own_units = [unit for unit in _scalar_units(numeric) if unit not in {"$", "€", "£", "¥"}]
    row_units = [u for text in [*cell.get("row_header_path", []), *cell.get("information_row_labels", [])] for u in metric_units(text)]
    ratio = any(re.search(r"[%％‰]|同比|佔|占|比例|比率|percent|change|rate|ratio", text, re.I)
                for text in column_texts)
    column_units = [u for text in [*column_texts, *cell.get("units", [])] for u in units(text)]
    if ratio:
        column_units = [u for u in column_units if re.fullmatch(
            r"[%‰]|[个個]?百分[点點]|percentage points?|basis points?|bps", u, re.I)]
        row_units = []
    if any(re.search(r"expressed\s+as\s+a\s+percentage", text, re.I) for text in cell.get("units", [])):
        column_units.append("%")
    actual_units = own_units or row_units or column_units
    row_labels = [*cell.get("row_header_path", []), *cell.get("information_row_labels", [])]
    currency = re.match(r"\(?\s*([$€£¥])", numeric) if _is_scalar(numeric) else None
    if (currency and any(re.search(r"per\s+(?:diluted\s+)?share|每股", label, re.I) for label in row_labels)):
        actual_units = [currency[1], currency[1] + " per share"]
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
    if currency and not actual_units:
        actual_units = [currency[1]]
    for unit in dict.fromkeys(actual_units):
        result["unit"].append({"actual": unit, "source": "candidate_scoped_unit"})
    # Keep whole literal labels as period evidence: e.g. an English date is
    # meaningful without attempting date conversion.
    period_texts = [*direct, *cell.get("periods", []), *cell.get("information_comparison_periods", []), *(item["text"] for item in contexts
                    if item["kind"] in {"period", "table_caption"})]
    # A declared single-year section introduction contains an explicit
    # period even when its business description has no separating space.
    # Do not collapse ranges or multi-year descriptions to one endpoint.
    period_texts += [match[1] for text in period_texts
                     if (match := _SECTION_PERIOD.fullmatch(text))
                     and len(re.findall(r"(?:19|20)\d{2}", text)) == 1]
    period_texts += [match[0] for text in period_texts
                     if len(set(re.findall(r"(?:19|20)\d{2}", text))) == 1
                     for match in re.finditer(r"截至\s*(?:19|20)\d{2}\s*年\s*\d{1,2}\s*月末", text)]
    result["period"] = [{"actual": text, "source": "candidate_scoped_period"} for text in period_literals(period_texts)]
    return result
