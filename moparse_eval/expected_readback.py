"""Read existing authored expected content for output evaluation only.

No PDF is opened, no reference is changed, and no reference truth or review
status is inferred. Targets are a transient syntax view of the existing text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from app.utils.measurement import unit_applicable

from .adapters import html_cells, markdown_cells
from .information_reading import currencies, metric_units, units
from .metrics import normalize_text
from .packaging import inside, read_json
from .representations import visible_text

MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable("table")
_COLON = re.compile(r"^([^:：\n]{1,512})[:：]\s*(.+)$", re.S)
_YEAR = re.compile(r"^((?:19|20)\d{2}\s*年?)\s*[:：]?\s*(.+)$", re.S)
_SCALAR = re.compile(r"^(?:\(?[$€£¥]?\s*[+\-−]?(?:\d[\d,. ]*|\.\d+)(?:\s*[%‰])?\)?(?:[⁰¹²³⁴⁵⁶⁷⁸⁹˒⁽⁾]+)?|[—–-])$")
_IDENTITY = re.compile(r"[^:：;；]{0,30}(?:名称|名稱|全称|全稱|姓名|类别|類別|品类|品類|种类|種類)|关联方|關聯方|项目|項目|认购方|認購方|会议届次|會議屆次|会议内容|會議內容|Name|Item|(?:[A-Za-z]+\s+)?(?:Category|Type|Name)|Metric|Region|Segment", re.I)


class ExpectedReadError(ValueError):
    """The evaluation reader must be repaired before publishing a grade."""


@dataclass
class Element:
    kind: str
    text: str
    lines: tuple[int, int]
    raw: str
    headings: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    has_children: bool = False
    cells: list[dict[str, Any]] = field(default_factory=list)
    list_span: tuple[int, int] | None = None
    part_index: int | None = None


def inline_text(text: str) -> str:
    return visible_text(text, "markdown").strip()


def elements(markdown: str) -> list[Element]:
    """Read public Markdown syntax with physical lines, without target data."""
    lines = markdown.splitlines(keepends=True)
    tokens = MARKDOWN.parse(markdown)
    result: list[Element] = []
    headings: list[tuple[int, str]] = []
    items: list[dict[str, Any]] = []
    lists: list[tuple[int, int]] = []
    table_depth = 0
    for index, token in enumerate(tokens):
        if token.type == "table_open":
            table_depth += 1
            if token.map is None:
                raise ExpectedReadError("Markdown table has no source location")
            a, b = token.map
            raw = "".join(lines[a:b])
            result.append(Element("table", "", (a + 1, b), raw,
                                  tuple(t for _, t in headings), cells=markdown_cells(raw, f"markdown:L{a + 1}")))
        elif token.type == "table_close":
            table_depth -= 1
        elif table_depth:
            continue
        elif token.type in {"bullet_list_open", "ordered_list_open"}:
            if token.map is None:
                raise ExpectedReadError("Markdown list has no source location")
            lists.append((token.map[0] + 1, token.map[1]))
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            lists.pop()
        elif token.type == "list_item_open":
            if items and items[-1]["element"] is not None:
                items[-1]["element"].has_children = True
            items.append({"element": None})
        elif token.type == "list_item_close":
            items.pop()
        elif token.type == "inline" and token.map:
            previous = tokens[index - 1]
            a, b = token.map
            raw = "".join(lines[a:b])
            text = inline_text(token.content)
            if not text and token.children and any(c.type == "image" for c in token.children):
                text = " ".join(c.content for c in token.children if c.type == "image")
            parents = tuple(item["element"].text for item in items[:-1] if item["element"])
            if previous.type == "heading_open":
                level = int(previous.tag[1:])
                headings = [(n, t) for n, t in headings if n < level]
                element = Element("heading", text, (a + 1, b), raw, tuple(t for _, t in headings))
                headings.append((level, text))
            else:
                image = token.children is not None and bool(token.children) and all(c.type in {"image", "softbreak", "hardbreak"}
                                                       for c in token.children)
                element = Element("image_caption" if image else "item" if items else "text",
                                  text, (a + 1, b), raw, tuple(t for _, t in headings), parents)
                if items and items[-1]["element"] is None:
                    items[-1]["element"] = element
            result.append(element)
            element.list_span = lists[0] if lists else None
        elif token.type in {"fence", "code_block", "html_block"} and token.map:
            a, b = token.map
            raw = "".join(lines[a:b])
            if token.type == "html_block" and re.search(r"<table\b", raw, re.I):
                result.append(Element("table", "", (a + 1, b), raw,
                                      tuple(t for _, t in headings), cells=html_cells(raw, f"markdown:L{a + 1}")))
            elif token.type == "html_block" and re.fullmatch(r"\s*<!--.*?-->\s*", raw, re.S):
                continue
            else:
                text = visible_text(raw, "html") if token.type == "html_block" else token.content
                if text.strip():
                    result.append(Element("text", text.strip(), (a + 1, b), raw,
                                          tuple(t for _, t in headings)))
    expanded: list[Element] = []
    for element in result:
        parts = re.split(r"\u3000+|\t+", element.text)
        if element.kind == "text" and len(parts) > 1 and all(_COLON.fullmatch(part.strip()) for part in parts):
            expanded.extend(replace(element, text=part.strip(), raw=part, part_index=index)
                            for index, part in enumerate(parts))
        else:
            expanded.append(element)
    return expanded


def _label(text: str) -> str:
    match = _COLON.match(text)
    if match and (_IDENTITY.fullmatch(match[1].strip()) or re.fullmatch(
            r"范围|範圍|Scope|分组|分組|Group", match[1].strip(), re.I)):
        return match[2].strip()
    return match[1].strip() if match else text.strip().removesuffix(":").removesuffix("：")


def _parent_labels(parents: tuple[str, ...]) -> list[str]:
    labels: list[str] = []
    for parent in parents:
        match = _COLON.match(parent)
        values = [_label(parent)]
        if (match and values == [match[1].strip()] and len(_parts(parent)) == 1
                and not _SCALAR.fullmatch(match[2].strip()) and not _pairs(match[2])):
            values.append(match[2].strip())
        labels.extend(part.strip() for value in values for part in re.split(r"\s+/\s+", value) if part.strip())
    return labels


def _row_path_units(path: list[str]) -> tuple[list[str], list[str]]:
    labels, found = [], []
    for label in path:
        local = metric_units(label)
        found.extend(local)
        for unit in local:
            pattern = r"\s*[(（]\s*" + re.escape(unit) + r"\s*[)）]\s*$"
            if re.search(pattern, label):
                label = re.sub(pattern, "", label)
                break
        labels.append(label)
    return labels, list(dict.fromkeys(found))


def _parts(text: str) -> list[str]:
    parts, stack, start = [], [], 0
    closing = {"(": ")", "（": "）", "[": "]", "【": "】"}
    for index, char in enumerate(text):
        if char in closing:
            stack.append(closing[char])
        elif stack and char == stack[-1]:
            stack.pop()
        elif char in ";；" and not stack:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def _pair(part: str):
    if re.search(r"[:：]\s*/\s+", part) or re.match(r"[A-Za-z][A-Za-z0-9+.-]*://", part):
        return None
    explicit = re.fullmatch(r"([^:：\n]{1,512})[:：]\s*(.*)", part, re.S)
    if explicit:
        return explicit
    year = _YEAR.match(part)
    if year and all(_SCALAR.fullmatch(piece.strip()) for piece in year[2].split("、")):
        return year
    return re.fullmatch(r"([^\d:：]{1,160}?)([+\-−]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*[%‰]?)", part)


def _field(key: str, value: str) -> dict[str, Any]:
    path = [piece.strip() for piece in re.split(r"\s+/\s+", key)]
    path, printed_units = _row_path_units(path)
    result: dict[str, Any] = {"column_header_path": path, "value": value}
    if len(path) == 1 and _IDENTITY.fullmatch(path[0]):
        result["identity_field"] = True
    if len(printed_units) == 1:
        result["unit"] = printed_units[0]
    qualifier = re.fullmatch(r"(.*?)[（(]((?:单位|單位|期间|期間|附注|附註|币种|幣種|Unit|Period|Note|Currency)\s*[:：].*)[）)]", value, re.S)
    if qualifier:
        pairs = _pairs(qualifier[2], terminal_punctuation=False)
        keys = {"单位": "unit", "單位": "unit", "Unit": "unit", "期间": "period", "期間": "period",
                "Period": "period", "附注": "notes", "附註": "notes", "Note": "notes",
                "币种": "currency", "幣種": "currency", "Currency": "currency"}
        if pairs and all(k in keys for k, _ in pairs):
            result["value"] = qualifier[1].strip()
            for label, literal in pairs:
                result[keys[label]] = [literal] if keys[label] == "notes" else literal
                if keys[label] == "unit":
                    found = units("单位：" + literal)
                    if len(found) == 1:
                        result["unit"] = found[0]
                    currency = currencies(literal)
                    if len(currency) == 1:
                        result["currency"] = currency[0]
    return result


def _pairs(text: str, *, terminal_punctuation: bool = True) -> list[tuple[str, str]] | None:
    pairs: list[tuple[str, str]] = []
    for part in _parts(text):
        part = part.strip()
        if terminal_punctuation:
            part = part.removesuffix("。").removesuffix(".")
        if not part:
            continue
        match = _pair(part)
        if match is None:
            return None
        keys = re.split(r"\s+/\s+", match[1].strip())
        values = re.split(r"\s+/\s+", match[2].strip())
        if len(keys) > 1 and len(keys) == len(values) and all(_IDENTITY.fullmatch(key) for key in keys):
            pairs.extend(zip(keys, values, strict=True))
        else:
            pairs.append((match[1].strip(), match[2].strip()))
    return pairs or None


def _measurement_literal(value: str) -> bool:
    if _SCALAR.fullmatch(value):
        return True
    return any(value.endswith(unit) and _SCALAR.fullmatch(value[:-len(unit)].strip()) for unit in units(value))


def record(element: Element) -> dict[str, Any] | None:
    """Read explicit label/value syntax; no missing relationship is inferred."""
    if element.kind not in {"item", "text"}:
        return None
    if re.match(r"^(?:(?:金额|金額|货币|貨幣)?(?:单位|單位)|Units?)\s*[:：]", element.text, re.I):
        return None
    outer = _COLON.match(element.text)
    parts = _parts(element.text.removesuffix("。").removesuffix("."))
    explicit_fields = [i for i, part in enumerate(parts) if (match := _COLON.match(part))
                       and not re.fullmatch(r"范围|範圍|Scope", match[1], re.I)]
    first_field = min(explicit_fields, default=0)
    bare = [part for i, part in enumerate(parts) if _pair(part) is None
            or i < first_field and _COLON.match(part) is None]
    pairs: list[Any] | None
    subject_assertion: tuple[str, str] | None = None
    if len(parts) > 1 and bare:
        pairs = [_pair(part) for part in parts if part not in bare and _pair(part) is not None]
        scopes = [label.strip() for pair in pairs if re.fullmatch(r"范围|範圍|Scope", pair[1], re.I)
                  for label in re.split(r"\s+/\s+", pair[2]) if label.strip()]
        subjects = [label.strip().rstrip(":：") for part in bare for label in re.split(r"\s+/\s+", part) if label.strip()]
        fields = [_field(pair[1].strip(), pair[2].strip()) for pair in pairs
                  if not re.fullmatch(r"范围|範圍|Scope", pair[1], re.I)]
        if fields:
            return {"row_header_path": [*_parent_labels(element.parents), *scopes, *subjects], "printed_scopes": scopes,
                    "fields": fields}
    # A scope is a caption, even when its literal ends with a colon. It is
    # never an outer subject whose caption should be parsed as field names.
    pairs = (_pairs(outer[2]) if outer and not re.fullmatch(r"范围|範圍|Scope", outer[1].strip(), re.I)
             else None)
    parent_path = _parent_labels(element.parents)
    if outer and pairs:
        path = [*parent_path, outer[1].strip()]
    else:
        pairs = _pairs(element.text)
        if not pairs:
            return None
        if element.parents and len(pairs) == 1 and (
            _SCALAR.fullmatch(pairs[0][1]) or _YEAR.match(pairs[0][0])
        ):
            path = parent_path
        elif len(pairs) > 1:
            identities = [label.strip() for key, value in pairs if _IDENTITY.fullmatch(key)
                          for label in re.split(r"\s+/\s+", value) if label.strip()]
            scopes = [label.strip() for key, value in pairs if re.fullmatch(r"范围|範圍|Scope", key, re.I)
                      for label in re.split(r"\s+/\s+", value) if label.strip()]
            substantive = [(key, value) for key, value in pairs
                           if not re.fullmatch(r"范围|範圍|Scope|单位|單位|Units?|期间|期間|Period|年度|日期|Date", key, re.I)]
            if not identities and not parent_path:
                if substantive and _measurement_literal(_field(*substantive[0])["value"]):
                    key, literal = substantive[0]
                    fields = [_field(k, v) for k, v in pairs]
                    first = fields[pairs.index(substantive[0])]
                    first.update(column_header_path=[], named_value=True)
                    return {"row_header_path": [*scopes, key], "fields": fields,
                            "printed_scopes": scopes, "named_measurements": [
                                {"row_header_path": [*scopes, k], **_field(k, v)}
                                for k, v in substantive if _measurement_literal(_field(k, v)["value"])]}
                if (substantive and substantive[0][1] and not _measurement_literal(substantive[0][1])
                        and not re.fullmatch(r"附注|附註|注释|註釋|备注|備註|说明|說明|Note|Description|Comment", substantive[0][0], re.I)):
                    subject_assertion = substantive[0]
                    identities = [label.strip() for label in re.split(r"\s+/\s+", substantive[0][1]) if label.strip()]
                else:
                    return None
            path = [*parent_path, *scopes, *identities]
        elif outer and (_SCALAR.fullmatch(outer[2].strip().removesuffix("。"))
                        or len(outer[2]) < 80 and not re.search(r"[。！？.!?]", outer[2].removesuffix("。").removesuffix("."))):
            return {"row_header_path": [*parent_path, outer[1].strip()],
                    "fields": [{"column_header_path": [], "named_value": True,
                                "value": outer[2].strip().removesuffix("。")}]}
        else:
            # A prose label with no delimited fields remains complete prose.
            return None
    parsed: dict[str, Any] = {"row_header_path": path,
              "fields": [_field(key, value) for key, value in pairs]}
    for index, (key, value) in enumerate(pairs):
        if subject_assertion == (key, value):
            parsed["fields"][index]["identity_field"] = True
    if subject_assertion:
        parsed["subject_assertion"] = subject_assertion
        parsed["printed_subject_paths"] = [[*path[:-len(identities)], subject_assertion[0], *identities]]
    parsed["printed_scopes"] = [value for key, value in pairs if re.fullmatch(r"范围|範圍|Scope", key, re.I)]
    explicit_units = [value for key, value in pairs if re.fullmatch(r"单位|單位|货币单位|貨幣單位|Units?", key, re.I)]
    explicit_periods = [value for key, value in pairs if re.fullmatch(r"期间|期間|Period|年度|日期|Date", key, re.I)]
    if explicit_units:
        parsed["unit"] = explicit_units[-1]
    if explicit_periods:
        parsed["period"] = explicit_periods[-1]
    return parsed


def _year_columns(text: str) -> dict[str, list[str]]:
    result = {}
    for match in re.finditer(r"((?:19|20)\d{2}年)([^，；;。\d]+)", text):
        body = match[2].rstrip("、 ")
        # "2024年金额及占比、2023年...、同比" declares a paired
        # subheading; the later enumeration is outside that pair.
        if re.search(r"及|和|與|与", body):
            body = body.split("、", 1)[0]
        labels = [part.strip() for part in re.split(r"及|和|與|与|、", body)]
        if len(labels) > 1 and all(labels):
            result[match[1]] = labels
    return result


def _expand_fields(parsed: dict[str, Any], columns: dict[str, list[str]], *, strict: bool = True) -> None:
    expanded = []
    for value in parsed["fields"]:
        pieces = value["value"].split("、")
        key = value["column_header_path"][0] if value["column_header_path"] else ""
        # An explicitly labelled list (for example several security codes)
        # is one list-valued field. Only a year column's compact numeric
        # tuple needs the separately printed subordinate column labels.
        if (len(pieces) > 1 and all(_SCALAR.fullmatch(piece.strip()) for piece in pieces)
                and (key in columns or re.fullmatch(r"(?:19|20)\d{2}年?", key))):
            labels = columns.get(key)
            if labels is None or len(labels) != len(pieces):
                if strict:
                    raise ExpectedReadError("multiple expected values require their explicitly printed column labels")
                expanded.append(value)
                continue
            expanded.extend({"column_header_path": [*value["column_header_path"], label], "value": literal.strip()}
                            for label, literal in zip(labels, pieces, strict=True))
        else:
            expanded.append(value)
    parsed["fields"] = expanded


def declared_scope(sample: dict[str, Any], expected_root: Path) -> tuple[Path, list[dict[str, Any]]]:
    """Consume existing source-map declarations; do not verify their truth."""
    directory = inside(expected_root, str(sample["document_id"]))
    manifest = read_json(directory / "manifest.json")
    source = inside(directory, manifest["markdown"]["path"])
    selected = set(sample["source_pages"])
    scopes = []
    for entry in manifest.get("source_map", {}).get("entries", []):
        pages = set(entry.get("source_pages", [])) & selected
        if pages:
            bounds = entry.get("markdown_lines")
            if not isinstance(bounds, list) or len(bounds) != 2:
                raise ExpectedReadError("declared expected scope has no readable line range")
            scopes.append({"lines": bounds, "pages": [i + 1 for i, p in enumerate(sample["source_pages"]) if p in pages]})
    if not scopes:
        raise ExpectedReadError(f"no declared expected scope for sample {sample['id']}")
    return source, scopes


def qualify_reference_record(parsed: dict[str, Any], caption_units: list[str], caption_periods: list[str],
                             caption_currencies: list[str]) -> None:
    """Apply only explicit authored unit/period/currency syntax to a record."""
    parsed["row_header_path"], local_units = _row_path_units(parsed["row_header_path"])
    amount_units = [u for u in caption_units if u not in {"%", "‰"}]
    inherited = local_units or (amount_units if len(amount_units) == 1 else caption_units)
    if not parsed.get("unit") and len(inherited) == 1:
        parsed["unit"] = inherited[0]
    for value in parsed["fields"]:
        if re.fullmatch(r"[（(]?原表留空[）)]?", value["value"]):
            value.update(authored_value=value["value"], value="", reference_blank=True)
        if (not _SCALAR.fullmatch(value["value"]) and not value.get("reference_blank")) or any(re.fullmatch(r"序号|序號|编号|編號|姓名|名称|名稱|Name|ID", key, re.I)
                                                       for key in value["column_header_path"]):
            value["unit"] = None
        effective_unit = value.get("unit", parsed.get("unit"))
        if effective_unit and not unit_applicable(effective_unit, value["column_header_path"], parsed["row_header_path"]):
            value["unit"] = None
        ratio = bool(re.search(r"[%‰]", value["value"]) or any(re.search(
            r"[%‰]|占|佔|同比|比例|比率|percent|ratio|rate|change", key, re.I)
            for key in value["column_header_path"]))
        per_share = any(re.search(r"per\s+(?:diluted\s+)?share|每股", label, re.I) for label in parsed["row_header_path"])
        symbol = re.match(r"\s*([$€£¥])\s*[+−-]?[\d,.]+\s*$", value["value"])
        if per_share and symbol:
            value["unit"] = symbol[1]
        effective_unit = value.get("unit", parsed.get("unit"))
        generic_currency_unit = isinstance(effective_unit, str) and re.fullmatch(r"[十百千万萬亿億]*元", effective_unit)
        if (len(caption_currencies) == 1 and generic_currency_unit and not ratio
                and (_SCALAR.fullmatch(value["value"]) or value.get("reference_blank"))):
            value.setdefault("currency", caption_currencies[0])
    if len(caption_periods) == 1:
        for value in parsed["fields"]:
            if not any(re.search(r"(?:19|20)\d{2}", key) for key in value["column_header_path"]):
                value["period"] = caption_periods[0]


def read_expected(sample: dict[str, Any], expected_root: Path, *,
                  cache: dict[Path, list[Element]] | None = None) -> dict[str, Any]:
    source, scopes = declared_scope(sample, expected_root)
    if cache is not None and source in cache:
        document = cache[source]
    else:
        document = elements(source.read_text(encoding="utf-8"))
        if cache is not None:
            cache[source] = document
    selected: list[dict[str, Any]] = []
    caption_units: list[str] = []
    caption_currencies: list[str] = []
    caption_periods: list[str] = []
    active_heading: tuple[str, ...] = ()
    columns: dict[str, list[str]] = {}
    for element in document:
        covering = [s for s in scopes if s["lines"][0] <= element.lines[1] and element.lines[0] <= s["lines"][1]]
        # Read enclosing syntax even if the selection starts in its middle.
        # Only selected elements become targets; no unselected answer is added.
        active_heading = element.headings
        if element.kind == "heading":
            active_heading = (*element.headings, element.text)
            caption_units, caption_periods, caption_currencies = [], [], []
            columns = {}
        if element.kind == "text" and re.search(r"(?:单位|單位|Units?)\s*[:：]|expressed\s+in", element.text, re.I):
            caption_units = units(element.text)
        if element.kind == "text":
            columns.update(_year_columns(element.text))
            if currencies(element.text) and re.search(r"(?:币种|幣種|Currency)\s*[:：]", element.text, re.I):
                caption_currencies = currencies(element.text)
        declared_period = (element.kind == "heading" or re.fullmatch(
            r"(?:(?:期间|期間|Period)\s*[:：]\s*)?(?:19|20)\d{2}\s*年(?:度|末)?[。.:：]?", element.text, re.I)
            or re.fullmatch(r"(?:[（(]\d+[)）]\s*)?(?:19|20)\d{2}\s*年度[^。；;]{0,32}(?:情况|情況|数据|數據)\s*[:：]", element.text))
        if declared_period and len(element.text) < 140:
            periods = list(dict.fromkeys(re.findall(r"(?<!\d)(?:19|20)\d{2}\s*年(?:度|末)?", element.text)))
            if periods:
                caption_periods = periods
        if not covering:
            continue
        pages = sorted({p for s in covering for p in s["pages"]})
        suffix = f":part:{element.part_index}" if element.part_index is not None else ""
        target: dict[str, Any] = {"id": f"expected:L{element.lines[0]}-{element.lines[1]}{suffix}", "kind": element.kind,
                  "reference": {"path": str(source), "lines": list(element.lines)},
                  "text": element.text, "pages": pages, "context": list(active_heading),
                  "parents": list(element.parents), "list_span": element.list_span}
        if element.part_index is not None:
            target["reference"]["part_index"] = element.part_index
        if element.kind == "text" and re.match(r"^(?:单位|單位|Units?)\s*[:：]", element.text, re.I):
            target["kind"] = "unit_caption"
            payload = normalize_text(re.sub(r"^(?:单位|單位|Units?)\s*[:：]\s*", "", element.text, flags=re.I)).rstrip("。.").strip(" ()")
            literals = units(element.text)
            if len(literals) == 1 and payload == normalize_text(literals[0]):
                target["text"] = literals[0]
        if element.kind == "image_caption":
            target["kind"] = "image_alt_text"
        # An explicit numbered table caption is context, not a key/value
        # record merely because its printed title contains a colon.
        caption = bool(re.match(r"^(?:Table|附表|图表|圖表|表)\s*\d+(?:[.\-]\d+)*(?:[:：.]|\s)", element.text, re.I))
        parsed = None if caption else record(element)
        if parsed:
            try:
                _expand_fields(parsed, columns)
            except ExpectedReadError as error:
                raise ExpectedReadError(f"{source}:L{element.lines[0]}: {error}") from error
            target["record"] = parsed
            qualify_reference_record(parsed, caption_units, caption_periods, caption_currencies)
        if element.cells:
            target["cells"] = element.cells
            target["raw"] = element.raw
            target["reference_context"] = {"units": caption_units, "periods": caption_periods, "currencies": caption_currencies}
        selected.append(target)
    definitions: dict[tuple[str, ...], dict[str, str]] = {}
    for element in document:
        if not any(s["lines"][0] <= element.lines[0] <= s["lines"][1] for s in scopes):
            continue
        match = re.match(r"\s*([0-9]{1,2})[.)、]\s+", element.raw)
        if match:
            definitions.setdefault(element.headings, {})[match[1]] = element.text
    for target in selected:
        for value in target.get("record", {}).get("fields", []):
            match = re.fullmatch(r"(.*?)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)", value["value"])
            if match and match[2].translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")) in definitions.get(tuple(target["context"]), {}):
                value["value"] = match[1]
                marker = match[2].translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
                value["reference_note_markers"] = [marker]
                value["note_texts"] = [definitions[tuple(target["context"])][marker]]
    if not selected:
        raise ExpectedReadError(f"no expected content read for sample {sample['id']}")
    return {"sample_id": sample["id"], "document_id": sample["document_id"],
            "family_id": sample.get("family_id"), "source_pages": sample["source_pages"],
            "tags": sample.get("tags", []), "development_exposure": sample.get("development_exposure"),
            "source_category": sample.get("source_category"),
            "scope": scopes, "targets": selected, "standard": "expected_only"}


def markdown_observation(markdown: str, *, sample_id: str, pipeline: str, pages: list[int]) -> dict[str, Any]:
    """Read delivered public bytes; no IR, private spans or expected input."""
    blocks = []
    caption_units: list[str] = []
    caption_context: list[dict[str, Any]] = []
    unit_span = None
    pending_units = False
    columns: dict[str, list[str]] = {}
    last_record_container: str | None = None
    for index, element in enumerate(elements(markdown)):
        identifier = f"markdown:L{element.lines[0]}:{index}"
        ordinal = re.match(r"\s*([0-9]{1,2})[.)、]\s+", element.raw)
        block: dict[str, Any] = {"id": identifier, "kind": "image" if element.kind == "image_caption" else "heading" if element.kind == "heading" else "text",
                                 "text": (ordinal[1] + ". " if ordinal else "") + element.text,
                                 "text_format": "plain", "native_path": identifier,
                                 "provenance_pages": pages, "public_lines": list(element.lines)}
        caption = bool(re.match(r"^(?:Table|附表|图表|圖表|表)\s*\d+(?:[.\-]\d+)*(?:[:：.]|\s)", element.text, re.I))
        parsed = None if caption else record(element)
        if caption:
            block["kind"] = "table_caption"
        if element.kind == "heading":
            caption_units = []
            caption_context = []
            pending_units = False
            unit_span = None
            columns = {}
            last_record_container = None
        if parsed:
            if not pending_units and element.list_span != unit_span:
                caption_units = []
                caption_context = []
            pending_units = False
            unit_span = element.list_span
            _expand_fields(parsed, columns, strict=False)
            block["kind"] = "table"
            block["native_table_container"] = (f"markdown:list:{element.list_span}:scope:{parsed.get('printed_scopes', [])}"
                                                if element.list_span else identifier)
            last_record_container = block["native_table_container"]
            parsed["row_header_path"], local_units = _row_path_units(parsed["row_header_path"])
            block["cells"] = [{"id": f"{identifier}:field:{i}", "text": value["value"],
                                "row_header_path": parsed["row_header_path"],
                                "printed_subject_paths": parsed.get("printed_subject_paths", []),
                                "column_header_path": value["column_header_path"],
                                "named_value": bool(value.get("named_value")),
                                "units": [parsed["unit"]] if parsed.get("unit") else local_units or caption_units,
                                "periods": [parsed["period"]] if parsed.get("period") else [],
                                "printed_scope_context": list(caption_context),
                                **{k: value[k] for k in ("unit", "period", "notes", "currency") if k in value},
                                "native_path": identifier, "provenance_pages": pages}
                               for i, value in enumerate(parsed["fields"])]
            # A printed compound subject such as "Instrument: Loan" also
            # explicitly asserts that named value. This view uses only its
            # own words; unrelated values are never alternative row labels.
            pairs = _pairs(element.text) or []
            substantive = [(key, value) for key, value in pairs
                           if not re.fullmatch(r"范围|範圍|Scope|单位|單位|Units?|期间|期間|Period|年度|日期|Date", key, re.I)]
            if substantive and parsed.get("subject_assertion") == substantive[0]:
                key, literal = substantive[0]
                block["cells"].append({"id": identifier + ":subject", "text": literal,
                                        "row_header_path": parsed["printed_subject_paths"][0][
                                            :-len(re.split(r"\s+/\s+", literal))],
                                        "column_header_path": [], "native_path": identifier,
                                        "named_value": True,
                                        "provenance_pages": pages})
            # The entire printed record remains visible evidence for labels,
            # captions and prose. It has no fabricated grid or field paths.
            block["cells"].append({"id": identifier + ":literal", "text": block["text"],
                                    "native_path": identifier, "provenance_pages": pages,
                                    "public_record_literal": True})
            for i, assertion in enumerate(parsed.get("named_measurements", [])):
                block["cells"].append({"id": f"{identifier}:measurement:{i}", "text": assertion["value"],
                    "row_header_path": assertion["row_header_path"], "column_header_path": [],
                    "named_value": True,
                    "native_path": identifier, "provenance_pages": pages,
                    **{key: assertion[key] for key in ("unit", "period", "notes", "currency") if key in assertion}})
        elif element.cells:
            block["kind"], block["cells"] = "table", element.cells
            block["native_table_container"] = identifier
            last_record_container = identifier
        elif ordinal and last_record_container:
            block["kind"], block["parent_id"] = "table_footnote", last_record_container
        elif element.kind != "item":
            last_record_container = None
        if element.kind == "text":
            if re.search(r"单位|單位|Units?\s*[:：]|expressed\s+in", element.text, re.I):
                caption_units = units(element.text)
                caption_context = [{"id": identifier, "text": element.text, "kind": "explicit_table_introduction"}]
                pending_units = True
                unit_span = None
            elif currencies(element.text):
                caption_context.append({"id": identifier, "text": element.text, "kind": "currency_caption"})
                pending_units = True
                unit_span = None
            elif parsed is None:
                caption_units = []
                caption_context = []
                pending_units = False
                unit_span = None
        if element.kind == "text":
            columns.update(_year_columns(element.text))
        blocks.append(block)
    return {"sample_id": sample_id, "pipeline": pipeline, "status": "success",
            "pages": [{"page": pages[0] if len(pages) == 1 else None, "blocks": blocks}],
            "relations": [], "assets": []}
