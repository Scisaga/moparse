"""Candidate-only matrix evidence from saved cells and explicit declarations.

No reference, document identity, PDF, image or parser call is accepted. Rows,
columns and spans identify already printed cells; they never prove business
roles alone. Untyped grids require an independently expressed measurement
schema and repeated compatible records before any role is exposed.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from typing import Any

from app.utils.measurement import unit_applicable, unit_kind

from .business_labels import is_amount_role
from .measurement_evidence import read_measurement_label, read_measurement_literal, read_unit_token
from .period_evidence import read_period_label

YEAR = re.compile(r"(?<![A-Za-z0-9])((?:19|20)\d{2})(年(?:度|末)?)?(?!\d)")
UNIT = re.compile(r"(?:人民币|人民幣|美元|港元|港币|港幣|欧元|歐元)?[十百千万萬亿億]*元|人民币|人民幣|美元|港元|港币|港幣|欧元|歐元|(?:RMB|CNY|USD|HKD|EUR)\s*(?:millions?|thousands?|billions?)?|[%‰]|人|万股|萬股|股|吨|噸|件", re.I)
CURRENCY = re.compile(r"人民币|人民幣|美元|港元|港币|港幣|欧元|歐元|\b(?:RMB|CNY|USD|HKD|EUR)\b", re.I)
SCALE = re.compile(r"[十百千万萬亿億]+元")
NUMBER = re.compile(r"\s*(?:[+\-−]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:\s*[%‰])?|[—–-]|)\s*$")
MEASUREMENT = re.compile(r"金额|金額|收入|利润|利潤|资产|資產|负债|負債|现金|現金|借款|权益|權益|投资|投資|占|佔|同比|比例|比率|数量|數量|\b(?:amount|revenue|profit|sales|balance|cash|assets?|liabilities|ratio|share|count|margin|change|value)\b", re.I)
IDENTITY = re.compile(r"Name|Entity|Company|Subject|名称|名稱|姓名|主体|主體|公司名称|公司名稱", re.I)
FACET = re.compile(r"Role|Type|Market|Region|Code|Ticker|Identifier|ID|职务|職務|类型|類型|市场|市場|地区|地區|代码|代碼", re.I)
PROPERTY = re.compile(r"Metric|Attribute|Property|Field|指标|指標|项目|項目|属性|屬性|字段", re.I)
VALUE = re.compile(r"Value|Amount|值|数值|數值|金额|金額", re.I)
RECORD = re.compile(r"Item|Record|项目名称|項目名稱|记录|記錄|行名", re.I)
GROUP_HEADER = re.compile(r"Group|Section|分组|分組|组别|組別", re.I)
QUALIFIER = re.compile(r"Units?|Currency|Period|Year|Note|Condition|Exception|Scope|单位|單位|币种|幣種|期间|期間|年度|附注|附註|条件|條件|例外|口径|口徑", re.I)
GROUP = re.compile(r"按[^。；;]{1,24}(?:劃分|划分|分类|分類)[:：]?|(?:Group|Section)\s*[:：]\s*.+", re.I)
BASIS = re.compile(r"截至[^。；;]{1,30}(?:止年度|止期间|止期間)|year\s+ended\s+[^;；]{1,35}", re.I)
PERIOD_END_HEADER = re.compile(
    r"(?:for\s+(?:the\s+)?)?(?:fiscal\s+)?(?:years?|periods?|quarters?|months?|weeks?)\s+ended\b",
    re.I,
)
DATE_LITERAL = re.compile(
    r"(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+"
    r"(?:0?[1-9]|[12]\d|3[01]),?\s+(?:19|20)\d{2}"
    r"|(?:0?[1-9]|[12]\d|3[01])\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?:19|20)\d{2}"
    r"|(?:19|20)\d{2}-(?:0?[1-9]|1[0-2])-(?:0?[1-9]|[12]\d|3[01])"
    r"|(?:19|20)\d{2}年(?:0?[1-9]|1[0-2])月(?:0?[1-9]|[12]\d|3[01])日"
    r")",
    re.I,
)


def _text(cell: dict[str, Any]) -> str:
    text = cell.get("text")
    return re.sub(r"(?<=[\u3400-\u9fff])[^\S\n]*\r?\n\s*(?=[\u3400-\u9fff])", "", text.strip()) if isinstance(text, str) else ""


def _qualifier_key(label: str) -> str:
    for key, pattern in {"unit": r"Units?|单位|單位", "currency": r"Currency|币种|幣種",
                         "period": r"Period|Year|期间|期間|年度", "note": r"Note|附注|附註",
                         "condition": r"Condition|条件|條件", "exception": r"Exception|例外",
                         "scope": r"Scope|口径|口徑"}.items():
        if re.fullmatch(pattern, label, re.I):
            return key
    raise ValueError("unrecognized explicit matrix qualifier")


def _compose_unit(first: str, second: str) -> str | None:
    """Combine only explicitly orthogonal currency and scale declarations."""
    if CURRENCY.fullmatch(first) and SCALE.fullmatch(second):
        return first + second
    if CURRENCY.fullmatch(second) and SCALE.fullmatch(first):
        return second + first
    return None


def _evidence(cell: dict[str, Any], source: dict[str, Any], role: str) -> dict[str, Any]:
    position = cell.get("_original_position", cell)
    return {"id": cell.get("id"), "native_id": cell.get("native_id"),
            "native_attributes": copy.deepcopy(cell.get("_original_declarations", cell).get("native_attributes", {})),
            "source": {**source, "cell": cell.get("id", cell.get("native_path")), "native_path": cell.get("native_path"),
                       "row": position["row"], "col": position["col"]},
            "text": cell.get("text", ""), "role": role,
            "row_span": position.get("row_span", 1), "col_span": position.get("col_span", 1),
            "declarations": cell.get("_original_declarations", {key: cell[key] for key in (
                "is_column_header", "is_row_header", "column_header", "row_header", "row_section",
                "native_header_tag", "native_header_section", "native_attributes") if key in cell})}


def _column_role(cell: dict[str, Any]) -> bool:
    attrs = cell.get("native_attributes", {})
    return bool(cell.get("is_column_header") or cell.get("column_header")
                or cell.get("native_header_section") == "thead" and not _row_role(cell)
                or attrs.get("role") == "columnheader" or attrs.get("scope") in {"col", "colgroup"})


def _row_role(cell: dict[str, Any]) -> bool:
    attrs = cell.get("native_attributes", {})
    return bool(cell.get("is_row_header") or cell.get("row_header")
                or attrs.get("role") == "rowheader" or attrs.get("scope") in {"row", "rowgroup"})


def _group_role(cell: dict[str, Any]) -> bool:
    return bool(cell.get("row_section") or cell.get("native_attributes", {}).get("scope") == "rowgroup")


def _covers(cell: dict[str, Any], col: int) -> bool:
    return cell["col"] <= col < cell["col"] + cell.get("col_span", 1)


def _declared_transpose(cells: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Recognize an explicitly transposed Group/Item schema, not value fit."""
    group_keys = [c for c in cells if _row_role(c) and GROUP_HEADER.fullmatch(_text(c))]
    record_keys = [c for c in cells if _row_role(c) and RECORD.fullmatch(_text(c))]
    if len(group_keys) != 1 or len(record_keys) != 1:
        return None
    if not all(any(_column_role(c) and c["row"] == key["row"] and c["col"] > key["col"] for c in cells)
               for key in [*group_keys, *record_keys]):
        return None
    swapped = []
    role_keys = ("is_column_header", "is_row_header", "column_header", "row_header", "row_section",
                 "native_header_tag", "native_header_section", "native_attributes")
    for raw in cells:
        cell = copy.deepcopy(raw)
        cell["_original_position"] = {key: raw.get(key, 1) for key in ("row", "col", "row_span", "col_span")}
        cell["_original_declarations"] = {key: copy.deepcopy(raw[key]) for key in role_keys if key in raw}
        cell["row"], cell["col"] = raw["col"], raw["row"]
        cell["row_span"], cell["col_span"] = raw.get("col_span", 1), raw.get("row_span", 1)
        cell["is_column_header"], cell["is_row_header"] = _row_role(raw), _column_role(raw)
        cell["column_header"], cell["row_header"] = _row_role(raw), _column_role(raw)
        cell["row_section"] = raw.get("native_attributes", {}).get("scope") == "colgroup"
        cell.pop("native_header_section", None)
        if "native_attributes" in cell:
            attrs = cell["native_attributes"]
            attrs["scope"] = {"col": "row", "row": "col", "rowgroup": "colgroup", "colgroup": "rowgroup"}.get(attrs.get("scope"), attrs.get("scope"))
            if attrs.get("role") in {"columnheader", "rowheader"}:
                attrs["role"] = "rowheader" if attrs["role"] == "columnheader" else "columnheader"
        swapped.append(cell)
    return swapped


def _printed_qualifiers(text: str) -> tuple[dict[str, str], str, list[str]]:
    """Read explicit qualifier atoms; never strip units inside business words."""
    q: dict[str, str] = {}
    conflicts = []
    label = text.strip()
    complete_period = read_period_label(label)
    if complete_period["matched"]:
        return complete_period["qualifiers"], complete_period["label"], []
    bases = list(dict.fromkeys(BASIS.findall(label)))
    if len(bases) == 1:
        q["period_basis"] = bases[0]
        label = label.replace(bases[0], "", 1)
    period_prefix = re.match(r"(?:Period|Year|期间|期間|年度)\s*[:：]\s*", label, re.I)
    if period_prefix:
        label = label[period_prefix.end():]
    period_matches = []
    for match in YEAR.finditer(label):
        before = label[:match.start()].strip(" \t\r\n/,:：，（）()")
        after = label[match.end():].strip(" \t\r\n/,:：，（）()")
        if ((not before and not after)
                or (not before and (MEASUREMENT.search(after) or read_unit_token(after)["matched"]))
                or (not after and (MEASUREMENT.search(before) or read_unit_token(before)["matched"]))):
            period_matches.append(match)
    periods = list(dict.fromkeys(m[1] + (m[2] or "年") for m in period_matches))
    if len(periods) == 1:
        q["period"] = periods[0]
    elif len(periods) > 1:
        conflicts.append("multiple_periods_in_one_header")
    for match in reversed(period_matches):
        label = label[:match.start()] + label[match.end():]
    units, spans = [], []
    for bracket in re.finditer(r"[（(]([^()（）]+)[)）]", label):
        literal = bracket[1].strip()
        if read_unit_token(literal)["matched"]:
            units.append(literal)
            spans.append(bracket.span())
    for start, end in reversed(spans):
        label = label[:start] + label[end:]
    unit_prefix = re.match(r"(?:(?:金额|金額|货币|貨幣)?(?:单位|單位)|Units?|Currency|币种|幣種)\s*[:：]\s*", label, re.I)
    if unit_prefix:
        label = label[unit_prefix.end():]
    # A unit-only declaration may carry a stray display wrapper. Recognize
    # the complete remaining token before consuming it; opaque metric labels
    # keep every parenthesis below.
    unit_body = label.strip(" \t\r\n（）()")
    if read_unit_token(unit_body)["matched"]:
        units.append(unit_body)
        label = ""
    elif len(list(UNIT.finditer(label))) > 1 and not UNIT.sub("", label).strip(" \t\r\n/,:：，（）()"):
        units.extend(match[0] for match in UNIT.finditer(label))
        label = ""
    else:
        # A printed suffix is a unit only with a delimiter or an independently
        # recognizable measurement label. 元器件收入 and 人工成本 stay intact.
        for start in range(len(label)):
            printed_unit = read_unit_token(label[start:])
            before = label[:start]
            if (printed_unit["matched"] and before.strip() and not re.search(r"\d\s*$", before)
                    and (before[-1:].isspace() or before[-1:] in "/,，:：" or MEASUREMENT.search(before))):
                units.append(printed_unit["unit"])
                label = before
                break
    units = list(dict.fromkeys(units))
    if len(units) == 2 and (composed := _compose_unit(units[0], units[1])):
        units = [composed]
    if len(units) == 1:
        q["unit"] = units[0]
    elif len(units) > 1:
        conflicts.append("multiple_units_in_one_header")
    currencies = list(dict.fromkeys(currency for unit in units if (currency := read_unit_token(unit)["currency"])))
    if len(currencies) == 1:
        q["currency"] = currencies[0]
    elif len(currencies) > 1:
        conflicts.append("multiple_currencies_in_one_header")
    label = re.sub(r"[（(]\s*[)）]", "", label)
    return q, label.strip(" \t\r\n,，:：/"), conflicts


def _unread_date_axis(headers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect an explicit period-end/date chain without interpreting its date.

    Header membership has already followed the candidate's own references or
    declared spans. Dates alone, ordinary labels and calendar-year axes do not
    activate this guard. The returned evidence is never a normalized period.
    """
    ranges, dates = [], []
    for header in headers:
        text = _text(header)
        declared_range = PERIOD_END_HEADER.match(text)
        if declared_range:
            remainder = text[declared_range.end():].strip(" \t\r\n:：")
            if not remainder or DATE_LITERAL.fullmatch(remainder):
                ranges.append(header)
        date_text = text[declared_range.end():].strip(" \t\r\n:：") if declared_range else text
        if DATE_LITERAL.fullmatch(date_text) and not _printed_qualifiers(text)[0].get("period"):
            dates.append(header)
    return [header for header in headers if header in ranges or header in dates] if ranges and dates else []


def _untyped_schema(cells: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Require printed period/unit or property/value schema plus repeated data.

    Scalar appearance is corroboration, never the sole evidence. Ambiguous
    Status/Ready grids and layouts containing prose are rejected.
    """
    rows = defaultdict(list)
    for cell in cells:
        rows[cell["row"]].append(cell)
    property_row = next((r for r, band in rows.items()
                         if any(PROPERTY.fullmatch(_text(c)) for c in band)
                         and any(VALUE.fullmatch(_text(c)) for c in band)), None)
    if property_row is not None:
        header = rows[property_row]
        key_col = next(c["col"] for c in header if PROPERTY.fullmatch(_text(c)))
        value_col = next(c["col"] for c in header if VALUE.fullmatch(_text(c)))
        data = [band for r, band in rows.items() if r > property_row]
        if len(data) >= 2 and all(
            len([c for c in band if c["col"] == key_col and MEASUREMENT.search(_text(c))]) == 1
            and len([c for c in band if c["col"] == value_col and NUMBER.fullmatch(_text(c))]) == 1
            for band in data):
            return header, [c for band in data for c in band if c["col"] == key_col], [], "printed_property_value_schema_and_repeated_measurements"
    # Identify a complete prefix band by explicit period/unit or metric labels,
    # followed by at least two independently named quantitative records.
    candidates = []
    for row, band in sorted(rows.items()):
        nonempty = [c for c in band if _text(c)]
        numeric = [c for c in nonempty if NUMBER.fullmatch(_text(c))]
        labels = [c for c in nonempty if not NUMBER.fullmatch(_text(c))]
        if len(numeric) >= 2 and len(labels) == 1 and labels[0]["col"] == min(c["col"] for c in band):
            candidates.append((row, labels[0]))
    if len(candidates) < 2:
        return [], [], [], None
    first = candidates[0][0]
    header = [c for c in cells if c["row"] < first and _text(c)]
    years = {m[1] for c in header for m in YEAR.finditer(_text(c))}
    metric_headers = [c for c in header if MEASUREMENT.search(_text(c))]
    has_unit = any(UNIT.search(_text(c)) for c in header)
    row_metrics = sum(bool(MEASUREMENT.search(_text(c))) for _, c in candidates) >= 2
    if not ((len(years) >= 2 and has_unit and row_metrics) or
            (len(years) >= 2 and len(metric_headers) >= 2 and has_unit)):
        return [], [], [], None
    # An unlabeled numerical record before the first named record is not an
    # extra header tier. Preserve that unknown row instead of borrowing its
    # values as schema labels for the good records below it.
    opaque_header_rows = set()
    for header_cell in header:
        text = _text(header_cell)
        q, label, conflicts = _printed_qualifiers(text)
        # A header with two explicit unit literals still proves a measurement
        # role; the assignment is preserved as a local qualifier ambiguity.
        qualifier_ambiguity = conflicts and not label and all(
            conflict in {"multiple_units_in_one_header", "multiple_currencies_in_one_header"} for conflict in conflicts)
        if (conflicts and not qualifier_ambiguity) or (not q and not qualifier_ambiguity and not MEASUREMENT.search(label)
                and not PROPERTY.fullmatch(label) and not VALUE.fullmatch(label)):
            opaque_header_rows.add(header_cell["row"])
    header = [c for c in header if c["row"] not in opaque_header_rows]
    if not header:
        return [], [], [], None
    groups = [c for c in cells if c["row"] >= first and GROUP.fullmatch(_text(c))]
    group_rows = {c["row"] for c in groups}
    data_rows = {row for row, _ in candidates}
    for row, band in rows.items():
        if row < first or row in group_rows:
            continue
        if row not in data_rows or any(_text(c) and not NUMBER.fullmatch(_text(c)) and c["col"] != 0 for c in band):
            return [], [], [], None
    return header, [c for _, c in candidates], groups, "printed_period_unit_measurement_schema_and_repeated_records"


def read_matrix(cells: list[dict[str, Any]], *, source: dict[str, Any],
                context: tuple[dict[str, Any], ...] | list[dict[str, Any]] = ()) -> dict[str, Any]:
    """Read one physical candidate matrix, never join another table or fill a gap."""
    result: dict[str, Any] = {"facts": [], "relations": [], "issues": [], "blockers": [], "roles": [], "unresolved_cells": [],
                              "pending_requirements": [], "complete": False,
                              "source": copy.deepcopy(source), "reader": "candidate_matrix_evidence"}

    def block(reason: str, *, category: str = "software_unsupported",
              affected_data_sources: list[dict[str, Any]] | None = None,
              header_ids: list[str] | None = None, **detail: Any) -> dict[str, Any]:
        if category not in {"software_unsupported", "candidate_ambiguity", "unadjudicated_extra_content"}:
            raise ValueError("unknown matrix issue category")
        if affected_data_sources is None:
            affected_data_sources = [{**source, "cell": c.get("id", c.get("native_path")),
                                      "row": c.get("_original_position", c).get("row"),
                                      "col": c.get("_original_position", c).get("col")}
                                     for c in cells if isinstance(c, dict)]
        if header_ids is None:
            header_ids = [c.get("id") for c in cells if isinstance(c, dict) and any(
                c.get(key) for key in ("is_column_header", "column_header", "native_header_tag"))]
        issue = {"id": f"matrix-issue:{len(result['issues'])}", "category": category,
                 "reason": reason, "source": copy.deepcopy(source),
                 "affected_data_sources": copy.deepcopy(affected_data_sources),
                 "header_ids": list(header_ids), **detail}
        result["issues"].append(issue)
        if category == "software_unsupported":
            result["blockers"].append(issue)
        return issue

    if not cells:
        block("matrix_has_no_readable_cells")
        return result
    if any(not isinstance(cell, dict) for cell in cells):
        block("matrix_cell_is_not_an_object")
        return result
    if any(type(cell.get(key)) is not int or cell[key] < 0 for cell in cells for key in ("row", "col")):
        block("matrix_cell_position_unavailable")
        return result
    if not any("_original_position" in cell for cell in cells):
        transposed = _declared_transpose(cells)
        if transposed is not None:
            result = read_matrix(transposed, source=source, context=context)
            result["orientation"] = "explicit_transposed_group_item_schema"
            return result
    ordered = sorted(copy.deepcopy(cells), key=lambda c: (c.get("row", -1), c.get("col", -1)))
    occupied = {}
    for index, cell in enumerate(ordered):
        if cell.get("text") is not None and not isinstance(cell["text"], str):
            block("matrix_nonliteral_cell_text", cell=cell.get("id"))
            return result
        if any(type(cell.get(key)) is not int or cell[key] < 0 for key in ("row", "col")):
            block("matrix_cell_position_unavailable", cell=cell.get("id"))
            return result
        for key in ("row_span", "col_span"):
            if type(cell.get(key, 1)) is not int or not 1 <= cell.get(key, 1) <= 2000:
                block("matrix_cell_span_invalid", cell=cell.get("id"))
                return result
        if len(occupied) + cell.get("row_span", 1) * cell.get("col_span", 1) > 200_000:
            block("matrix_grid_exceeds_reader_budget", cell=cell.get("id"))
            return result
        for row in range(cell["row"], cell["row"] + cell.get("row_span", 1)):
            for col in range(cell["col"], cell["col"] + cell.get("col_span", 1)):
                if (row, col) in occupied:
                    block("matrix_cells_overlap", cells=[occupied[row, col], cell.get("id")])
                    return result
                occupied[row, col] = cell.get("id", index)
        if cell.get("native_header_role_conflict"):
            block("matrix_explicit_roles_conflict", cell=cell.get("id"))
    ids = defaultdict(list)
    # HTML's th is an explicit header declaration even without scope/thead.
    # A leading contiguous all-header band supplies the column direction;
    # td-only rows do not acquire this role from their position.
    leading_headers = True
    for row_number in sorted({c["row"] for c in ordered}):
        band = [c for c in ordered if c["row"] == row_number and _text(c)]
        if leading_headers and band and all(
                _column_role(c) or ((c.get("native_header_tag") or c.get("native_tag") == "th") and not _row_role(c))
                for c in band):
            for header in band:
                if not _row_role(header):
                    header["is_column_header"] = True
                    header["header_role_evidence"] = "native_th_in_leading_header_band"
        else:
            leading_headers = False
    for cell in ordered:
        if cell.get("native_id"):
            ids[str(cell["native_id"])].append(cell)
    if any(len(matches) != 1 for matches in ids.values()):
        block("matrix_duplicate_native_ids", ids=[key for key, values in ids.items() if len(values) != 1])
        return result
    columns = [c for c in ordered if _column_role(c)]
    rows = [c for c in ordered if _row_role(c) and not _group_role(c)]
    groups = [c for c in ordered if _group_role(c) and _text(c)]
    role_basis = "explicit_candidate_header_declarations"
    if not columns:
        columns, rows, groups, inferred = _untyped_schema(ordered)
        if inferred is None:
            result["unresolved_cells"] = [_evidence(c, source, "unresolved_role") for c in ordered]
            block("matrix_data_roles_unproven", unresolved_cell_ids=[c.get("id") for c in ordered])
            return result
        role_basis = inferred
    column_ids = {id(c) for c in columns}
    row_ids = {id(c) for c in rows}
    group_ids = {id(c) for c in groups}
    group_rows = {c["row"] for c in groups}
    section_rows = {row for row in group_rows if not any(c["row"] == row and _text(c)
        and id(c) not in group_ids and not _column_role(c) for c in ordered)}
    header_bottom = max(c["row"] + c.get("row_span", 1) for c in columns)
    result["role_basis"] = role_basis
    result["roles"] = [_evidence(c, source, "column_header") for c in columns]
    result["roles"].extend(_evidence(c, source, "row_header") for c in rows)
    result["roles"].extend(_evidence(c, source, "row_group") for c in groups)
    role_ids = column_ids | row_ids | group_ids
    opaque_prefix = [c for c in ordered if c["row"] < header_bottom and id(c) not in role_ids and _text(c)]
    if opaque_prefix:
        result["unresolved_cells"].extend(_evidence(c, source, "unresolved_prefix_role") for c in opaque_prefix)
        numeric_prefix = all(NUMBER.fullmatch(_text(c)) for c in opaque_prefix)
        block("matrix_prefix_roles_unproven", category="unadjudicated_extra_content" if numeric_prefix else "software_unsupported",
              affected_data_sources=[_evidence(c, source, "unbound_prefix_value")["source"] for c in opaque_prefix],
              header_ids=[c.get("id") for c in columns],
              unresolved_cell_ids=[c.get("id") for c in opaque_prefix],
              binding_scope={"role_basis": role_basis, "named_record_sources": [_evidence(c, source, "row_header")["source"] for c in rows],
                             "observation": "prefix_has_no_record_binding"})
    properties = [c for c in columns if PROPERTY.fullmatch(_text(c))]
    value_headers = [c for c in columns if VALUE.fullmatch(_text(c))]
    vertical = len(properties) == len(value_headers) == 1 and len(columns) == 2
    annual_axis = (len(properties) == 1 and len(columns) > 1 and not value_headers
                   and all(_printed_qualifiers(_text(header))[0].get("period")
                           and not _printed_qualifiers(_text(header))[1]
                           for header in columns if header is not properties[0]))
    if annual_axis:
        metric_rows = [cell for cell in ordered if cell["col"] == properties[0]["col"]
                       and cell["row"] >= header_bottom and cell not in columns]
        rows.extend(cell for cell in metric_rows if cell not in rows)
        row_ids.update(id(cell) for cell in metric_rows)
        result["roles"].extend(_evidence(cell, source, "row_header") for cell in metric_rows)
    if vertical:
        for key_cell in ordered:
            if key_cell["col"] == properties[0]["col"] and key_cell["row"] >= header_bottom:
                qualifier = bool(QUALIFIER.fullmatch(_text(key_cell)))
                result["roles"].append(_evidence(key_cell, source, "qualifier_label" if qualifier else "row_header"))
                if qualifier:
                    literals = [c for c in ordered if c["row"] == key_cell["row"] and c["col"] == value_headers[0]["col"]]
                    result["roles"].extend(_evidence(c, source, "qualifier_value") for c in literals)
    identity_headers = [c for c in columns if IDENTITY.fullmatch(_text(c))]
    facet_headers = [c for c in columns if FACET.fullmatch(_text(c))]
    record_headers = [c for c in columns if RECORD.fullmatch(_text(c))]
    group_headers = [c for c in columns if GROUP_HEADER.fullmatch(_text(c))]
    qualifier_headers = [c for c in columns if QUALIFIER.fullmatch(_text(c))]
    explicit_years = list(dict.fromkeys(m[1] + (m[2] or "年") for c in columns for m in YEAR.finditer(_text(c))))
    contexts = []
    for item in context:
        if not isinstance(item, dict) or not isinstance(item.get("source"), dict):
            block("matrix_context_has_no_candidate_source")
            continue
        q, _, conflicts = _printed_qualifiers(item.get("text", ""))
        if conflicts:
            block("matrix_context_qualifier_conflict", conflicts=conflicts)
        contexts.append((q, item))
    data_cells = [c for c in ordered if id(c) not in column_ids | row_ids | group_ids and c["row"] >= header_bottom and c["row"] not in section_rows]
    for cell in data_cells:
        record_anchor = None
        vertical_facets = []
        local_issues = []
        ambiguous_qualifiers = {}
        unit_components = []
        if any(_covers(header, cell["col"]) for header in [*record_headers, *group_headers, *qualifier_headers]):
            continue
        # An identity/facet column is an actual named record field. It is not
        # a second arbitrary label for another column's numerical value.
        own_rows = [r for r in rows if r["row"] <= cell["row"] < r["row"] + r.get("row_span", 1)]
        own_rows.sort(key=lambda c: c["col"])
        explicit = str(cell.get("native_attributes", {}).get("headers", "")).split()
        if explicit:
            if any(key not in ids for key in explicit):
                block("matrix_header_reference_unavailable", cell=cell.get("id"), references=explicit)
                continue
            selected = [ids[key][0] for key in explicit]
            if any(c not in columns and c not in rows and c not in groups for c in selected):
                block("matrix_reference_target_not_a_header", cell=cell.get("id"), references=explicit)
                continue
            own_rows = [r for r in selected if r in rows] or own_rows
            headers = [h for h in selected if h in columns]
            # Explicit leaf references retain their own declared ancestor
            # bands, including after a deliberate column-reference change.
            leaves = list(headers)
            headers.extend(h for h in columns if h not in headers and any(
                h["row"] < leaf["row"] and h["col"] <= leaf["col"]
                and leaf["col"] + leaf.get("col_span", 1) <= h["col"] + h.get("col_span", 1)
                for leaf in leaves))
        else:
            headers = [h for h in columns if h["row"] < cell["row"] and _covers(h, cell["col"])]
        headers.sort(key=lambda c: (c["row"], c["col"]))
        if vertical:
            if cell["col"] != value_headers[0]["col"]:
                continue
            own_rows = [c for c in ordered if c["row"] == cell["row"] and c["col"] == properties[0]["col"]]
            headers = []
            if len(own_rows) == 1 and QUALIFIER.fullmatch(_text(own_rows[0])):
                continue
        if not headers and not vertical:
            if _text(cell):
                block("matrix_value_column_role_unavailable", cell=cell.get("id"))
            continue
        identity_values = [(h, occupied.get((cell["row"], h["col"]))) for h in identity_headers]
        identity_cells = [c for h, _ in identity_values for c in ordered
                          if c["row"] <= cell["row"] < c["row"] + c.get("row_span", 1)
                          and c["col"] == h["col"] and c not in columns]
        if not own_rows:
            own_rows = [c for header in record_headers for c in ordered if c["row"] == cell["row"]
                        and c["col"] == header["col"] and c not in columns]
        unread_dates = _unread_date_axis(headers)
        if unread_dates:
            data_evidence = _evidence(cell, source, "data_value")
            header_evidence = [_evidence(header, source, "unresolved_period_axis") for header in unread_dates]
            issue = block("matrix_date_period_axis_unsupported", layers=["L", "B"],
                          affected_data_sources=[data_evidence["source"]],
                          header_ids=[header.get("id") for header in unread_dates],
                          cell=cell.get("id"), header_evidence=copy.deepcopy(header_evidence))
            local_issues.append(issue)
            result["pending_requirements"].append({
                "reason": issue["reason"], "category": "software_unsupported", "layers": ["L", "B"],
                "source": copy.deepcopy(data_evidence["source"]), "text": cell.get("text", ""),
                "data_evidence": copy.deepcopy(data_evidence), "header_evidence": header_evidence,
                "affected_data_sources": copy.deepcopy(issue["affected_data_sources"]),
                "header_ids": list(issue["header_ids"]),
            })
            for header in unread_dates:
                if not any(entry.get("id") == header.get("id") for entry in result["unresolved_cells"]):
                    result["unresolved_cells"].append(_evidence(header, source, "unresolved_period_axis"))
        q, labels, evidence = {}, [], []
        for header in headers:
            found, label, conflicts = _printed_qualifiers(_text(header))
            if conflicts:
                unit_alternatives = list(dict.fromkeys(UNIT.findall(_text(header))))
                currency_alternatives = list(dict.fromkeys(CURRENCY.findall(_text(header))))
                alternatives = {key: values for key, values in (("unit", unit_alternatives), ("currency", currency_alternatives)) if len(values) > 1}
                issue = block("matrix_header_qualifier_ambiguous", category="candidate_ambiguity",
                    affected_data_sources=[_evidence(cell, source, "data_value")["source"]],
                    header_ids=[header.get("id")], cell=cell.get("id"), header=header.get("id"),
                    conflicts=conflicts, alternatives=alternatives,
                    observation="multiple_printed_qualifiers_have_no_independent_column_assignment")
                local_issues.append(issue)
                ambiguous_qualifiers.update(alternatives)
                if not any(e.get("id") == header.get("id") for e in result["unresolved_cells"]):
                    result["unresolved_cells"].append(_evidence(header, source, "ambiguous_qualifier"))
            for key, value in found.items():
                if key == "unit":
                    unit_components.append({"literal": value, "source": _evidence(header, source, "unit_declaration")["source"]})
                if key == "unit" and key in q and (composed := _compose_unit(q[key], value)):
                    q[key] = composed
                    continue
                if key in q and q[key] != value:
                    block("matrix_conflicting_header_qualifiers", cell=cell.get("id"), key=key, values=[q[key], value])
                q[key] = value
            if label:
                labels.append(label)
            evidence.append(_evidence(header, source, "column_header"))
        field_units = [header for header in headers
                       if (printed := _printed_qualifiers(_text(header)))[0].get("unit") and printed[1]]
        header_unit = q.get("unit") if field_units else None
        for defaults, item in contexts:
            for key, value in defaults.items():
                if key == "unit" and key in q and (composed := _compose_unit(q[key], value)):
                    q[key] = composed
                    unit_components.append({"literal": value, "source": item["source"]})
                    evidence.append({"text": item.get("text", ""), "source": item["source"], "role": "printed_context"})
                    continue
                if key not in q:
                    q[key] = value
                    evidence.append({"text": item.get("text", ""), "source": item["source"], "role": "printed_context"})
        for header in qualifier_headers:
            literals = [c for c in ordered if c["row"] == cell["row"] and c["col"] == header["col"] and c not in columns]
            if len(literals) == 1:
                dimension = _qualifier_key(_text(header))
                proof = {**_evidence(literals[0], source, "record_qualifier"), "qualifier": dimension}
                if dimension == "unit" and header_unit:
                    proof.update(status="not_applied", application="field_explicit_unit_takes_precedence_over_record_default")
                else:
                    q[dimension] = _text(literals[0])
                evidence.append(proof)
        group = [g for g in groups if g["row"] <= cell["row"] < g["row"] + g.get("row_span", 1)]
        if not group:
            preceding = [g for g in groups if g["row"] < cell["row"]]
            group = [max(preceding, key=lambda g: g["row"])] if preceding else []
        row_labels = [_text(c) for c in own_rows if _text(c)]
        attribute = " / ".join(labels)
        subject = " / ".join(_text(c) for c in identity_cells) or " / ".join(row_labels)
        role = "metric"
        if not labels and row_labels:
            # A matrix of only periods/units declares row metrics, rather
            # than entities with a fictional empty property.
            attribute, subject = " / ".join(row_labels), ""
        if vertical:
            attribute, subject = " / ".join(row_labels), ""
            name_keys = [c for c in ordered if c["col"] == properties[0]["col"] and IDENTITY.fullmatch(_text(c))
                         and c["row"] < cell["row"] and c not in columns]
            current_name = max(name_keys, key=lambda c: c["row"]) if name_keys else None
            next_names = [c for c in ordered if c["col"] == properties[0]["col"] and IDENTITY.fullmatch(_text(c))
                          and c["row"] > (current_name["row"] if current_name else cell["row"]) and c not in columns]
            limit = min((c["row"] for c in next_names), default=float("inf"))
            start = current_name["row"] if current_name else cell["row"]
            all_names = [c for c in ordered if c["col"] == properties[0]["col"] and IDENTITY.fullmatch(_text(c)) and c not in columns]
            if not all_names:
                start, limit = header_bottom, float("inf")
            if IDENTITY.fullmatch(attribute):
                start = cell["row"]
                limit = min((c["row"] for c in next_names if c["row"] > start), default=float("inf"))
                record_anchor = own_rows[0] if own_rows else None
            elif current_name:
                record_anchor = current_name
            if current_name:
                names = [c for c in ordered if c["row"] == current_name["row"] and c["col"] == value_headers[0]["col"]]
                if len(names) == 1:
                    subject = _text(names[0])
                    identity_cells = [*identity_cells, names[0]]
            for key_cell in ordered:
                global_prefix = bool(all_names and key_cell["row"] < min(c["row"] for c in all_names))
                if key_cell["col"] == properties[0]["col"] and (start <= key_cell["row"] < limit or global_prefix) and QUALIFIER.fullmatch(_text(key_cell)):
                    literals = [c for c in ordered if c["row"] == key_cell["row"] and c["col"] == value_headers[0]["col"]]
                    if len(literals) == 1:
                        dimension = _qualifier_key(_text(key_cell))
                        q[dimension] = _text(literals[0])
                        evidence.append({**_evidence(literals[0], source, "record_qualifier"), "qualifier": dimension})
                if key_cell["col"] == properties[0]["col"] and start <= key_cell["row"] < limit and FACET.fullmatch(_text(key_cell)):
                    literals = [c for c in ordered if c["row"] == key_cell["row"] and c["col"] == value_headers[0]["col"]]
                    if len(literals) == 1:
                        vertical_facets.append((_text(key_cell), literals[0]))
        if not attribute:
            block("matrix_metric_or_record_role_unavailable", cell=cell.get("id"))
            continue
        if IDENTITY.fullmatch(attribute):
            role, subject = "identity", ""
        elif FACET.fullmatch(attribute):
            role = "identity"
        if not vertical and (subject or identity_cells):
            record_anchor = (identity_cells or own_rows or [None])[0]
        if not subject and not own_rows and not identity_cells and len(data_cells) > 1 and not IDENTITY.fullmatch(attribute):
            # A plain column schema can be one anonymous record, but multiple
            # anonymous rows need an independently named record role.
            row_numbers = {c["row"] for c in data_cells}
            if len(row_numbers) > 1:
                if not _text(cell):
                    result["unresolved_cells"].append(_evidence(cell, source, "unbound_empty_slot"))
                    continue
                named_rows = [c["row"] for c in rows if _text(c)]
                row_atoms = [_text(c) for c in ordered if c["row"] == cell["row"] and c not in columns and _text(c)]
                extra_prefix = bool(named_rows and cell["row"] < min(named_rows)
                                    and row_atoms and all(NUMBER.fullmatch(atom) for atom in row_atoms))
                block("matrix_record_identity_unavailable",
                      category="unadjudicated_extra_content" if extra_prefix else "software_unsupported",
                      affected_data_sources=[_evidence(cell, source, "unbound_record_value")["source"]],
                      header_ids=[c.get("id") for c in headers], cell=cell.get("id"),
                      binding_scope={"role_basis": role_basis, "named_record_sources": [_evidence(c, source, "row_header")["source"] for c in rows],
                                     "observation": "prefix_has_no_record_binding" if extra_prefix else "record_identity_not_established"})
                result["unresolved_cells"].append(_evidence(cell, source, "unresolved_record_value"))
                continue
        value = _text(cell)
        record_units = [proof for proof in evidence if proof.get("role") == "record_qualifier" and proof.get("qualifier") == "unit"]
        if vertical and len(own_rows) == 1:
            declared = read_measurement_label(attribute, _evidence(own_rows[0], source, "unit_declaration")["source"])
            if declared["matched"]:
                attribute, q["unit"] = declared["label"], declared["unit"]
                if declared["currency"]:
                    q["currency"] = declared["currency"]
                field_units.append(own_rows[0])
                for proof in record_units:
                    proof.update(status="not_applied", application="field_explicit_unit_takes_precedence_over_record_default")
        unit_level = "header_explicit" if field_units else "record_explicit" if record_units else "caption_shared"
        if q.get("unit") and (role == "identity" or unit_level == "caption_shared" and
                               (not NUMBER.fullmatch(value) or not unit_applicable(q["unit"], [attribute], [subject]))):
            q.pop("unit")
        value_position = cell.get("_original_position", cell)
        value_source = {**source, "cell": cell.get("id", cell.get("native_path")),
                        "native_path": cell.get("native_path"), "row": value_position["row"], "col": value_position["col"]}
        raw_measurement = cell.get("text", "")
        if not isinstance(raw_measurement, str):
            raw_measurement = value
        printed_value = read_measurement_literal(raw_measurement, value_source) if role != "identity" else None
        if printed_value and not printed_value["matched"] and (missing := re.fullmatch(r"\s*([—–-])\s*(.+?)\s*", raw_measurement)):
            parent_span = value_source.get("text_span")
            offset = parent_span[0] if isinstance(parent_span, (list, tuple)) and len(parent_span) == 2 and type(parent_span[0]) is int else 0
            printed_unit = read_unit_token(missing[2], {**value_source, "text_span": [offset + missing.start(2), offset + missing.end(2)]})
            if printed_unit["matched"]:
                printed_value.update(matched=True, value=missing[1], value_span=list(missing.span(1)), unit=printed_unit["unit"], currency=printed_unit["currency"])
                for key in ("unit", "currency"):
                    printed_value[key + "_span"] = [missing.start(2) + a for a in printed_unit[key + "_span"]] if printed_unit[key + "_span"] else None
                printed_value["sources"] = {"value": {**value_source, "text_span": [offset + missing.start(1), offset + missing.end(1)]}, **printed_unit["sources"]}
        if printed_value and printed_value["matched"]:
            value = printed_value["value"]
        if printed_value and printed_value["matched"] and printed_value["unit"]:
            q["unit"] = printed_value["unit"]
            unit_level = "field_inline"
            printed_currency = printed_value["currency"]
            if printed_currency:
                q["currency"] = printed_currency
        if q.get("unit") in {"%", "‰"} and q.get("currency"):
            q["column_currency"] = q.pop("currency")
        if re.search(r"同比|\byoy\b|year.over.year", attribute, re.I):
            if len(explicit_years) == 2 and int(explicit_years[0][:4]) - int(explicit_years[1][:4]) == 1:
                # Interpretation of the explicitly printed YoY relation and
                # its two consecutive periods, never a calculation of values.
                q["from_period"], q["to_period"] = explicit_years[1], explicit_years[0]
                evidence.extend(_evidence(h, source, "comparison_period") for h in columns if YEAR.search(_text(h))
                                and h not in headers)
                period_nodes = [h for h in columns if _printed_qualifiers(_text(h))[0].get("period") in explicit_years]
                basis_sets = []
                basis_sources = []
                for period_node in period_nodes:
                    ancestors = [h for h in columns if h["row"] < period_node["row"]
                                 and h["col"] <= period_node["col"]
                                 and period_node["col"] + period_node.get("col_span", 1) <= h["col"] + h.get("col_span", 1)]
                    declared = [(h, _printed_qualifiers(_text(h))[0].get("period_basis")) for h in [period_node, *ancestors]]
                    basis_sets.append({basis for _, basis in declared if basis})
                    basis_sources.extend(h for h, basis in declared if basis)
                common_basis = set.intersection(*basis_sets) if basis_sets else set()
                if len(common_basis) == 1 and "period_basis" not in q:
                    q["period_basis"] = next(iter(common_basis))
                    for basis_node in basis_sources:
                        if not any(item.get("id") == basis_node.get("id") for item in evidence):
                            evidence.append(_evidence(basis_node, source, "comparison_period_basis"))
            else:
                block("matrix_yoy_period_relation_unavailable", cell=cell.get("id"), periods=explicit_years)
        facets = {"group": _text(group[0]).rstrip(":：")} if group else {}
        facet_sources = []
        for header in group_headers:
            printed = [c for c in ordered if c["row"] == cell["row"] and c["col"] == header["col"] and c not in columns]
            if len(printed) == 1 and _text(printed[0]):
                facets["group"] = _text(printed[0])
                facet_sources.append(_evidence(printed[0], source, "row_group_value"))
        if role != "identity":
            for header in facet_headers:
                printed = [c for c in ordered if c["row"] == cell["row"] and c["col"] == header["col"] and c not in columns]
                if len(printed) == 1:
                    facets[_text(header)] = _text(printed[0])
                    facet_sources.append(_evidence(printed[0], source, "identity_facet"))
            for key, printed in vertical_facets:
                facets[key] = _text(printed)
                facet_sources.append(_evidence(printed, source, "identity_facet"))
        row_evidence = [_evidence(r, source, "row_header") for r in own_rows]
        row_evidence.extend(_evidence(g, source, "row_group") for g in group)
        row_evidence.extend(_evidence(c, source, "identity_value") for c in identity_cells)
        row_evidence.extend(facet_sources)
        position = cell.get("_original_position", cell)
        table_key = f"{source.get('path')}:{source.get('block', source.get('lines', []))}"
        record_key = record_anchor.get("id", record_anchor.get("native_path")) if record_anchor else "anonymous"
        fact = {"id": f"matrix:{len(result['facts'])}", "subject": subject, "attribute": attribute,
                "value": value, "raw_value": cell.get("text", ""), "role": role, "qualifiers": q,
                "qualifier_provenance": {"unit": {"level": unit_level, "text": q["unit"],
                    "sources": copy.deepcopy([_evidence(h, source, "unit_declaration") for h in field_units]
                                             if field_units else record_units)}}
                if q.get("unit") else {},
                "record_id": f"{table_key}::record:{record_key}",
                "issue_ids": [issue["id"] for issue in local_issues],
                "ambiguous_qualifiers": ambiguous_qualifiers,
                "qualifier_compositions": {"unit": {"value": q["unit"], "components": unit_components}}
                if len(unit_components) > 1 and q.get("unit") and any(CURRENCY.fullmatch(c["literal"]) for c in unit_components)
                and any(SCALE.fullmatch(c["literal"]) for c in unit_components) else {},
                "source": {**source, "cell": cell.get("id", cell.get("native_path")), "native_path": cell.get("native_path"),
                           "row": position["row"], "col": position["col"]},
                "header_evidence": evidence, "row_evidence": row_evidence,
                "data_evidence": _evidence(cell, source, "data_value"),
                "identity_facets": facets, "row_path": row_labels,
                "column_path": [_text(h) for h in headers], "role_basis": role_basis}
        fact["qualifier_sources"] = {}
        for header in headers:
            header_origin = _evidence(header, source, "column_header")["source"]
            period = read_period_label(header.get("text", ""), header_origin)
            if period["matched"]:
                for key, literal in period["qualifiers"].items():
                    if q.get(key) == literal:
                        fact["qualifier_sources"][key] = copy.deepcopy(period["qualifier_sources"][key])
                        fact["qualifier_provenance"].setdefault(key, {
                            "level": "header_explicit", "text": literal,
                            "source": copy.deepcopy(period["qualifier_sources"][key])})
        # Combined metric/year headers and comparison columns retain the
        # actual year token, rather than an unsourced normalized period.
        for header in evidence:
            header_origin, header_text = header["source"], header.get("text", "")
            locations = list(re.finditer(re.escape(attribute), header_text)) if attribute else []
            if len(locations) == 1 and "attribute_source" not in fact and header.get("role") in {"column_header", "row_header"}:
                match = locations[0]
                offset = header_origin.get("text_span", [0])[0]
                fact["attribute_source"] = {**copy.deepcopy(header_origin),
                    "text_span": [offset + match.start(), offset + match.end()]}
            for match in YEAR.finditer(header_text):
                period = match[1] + (match[2] or "年")
                for key in ("period", "from_period", "to_period"):
                    if q.get(key) != period or key in fact["qualifier_sources"]:
                        continue
                    if key != "period" and header.get("role") != "comparison_period":
                        continue
                    offset = header_origin.get("text_span", [0])[0]
                    fact["qualifier_sources"][key] = {**copy.deepcopy(header_origin),
                        "text_span": [offset + match.start(), offset + match.end()]}
            labelled = read_measurement_label(header_text, header_origin)
            if labelled["matched"]:
                for key in ("unit", "currency"):
                    if labelled[key] and q.get(key) == labelled[key] and key not in fact["qualifier_sources"]:
                        fact["qualifier_sources"][key] = copy.deepcopy(labelled["sources"][key])
        if printed_value and printed_value["matched"]:
            fact["value_source"] = {**copy.deepcopy(printed_value["sources"]["value"]),
                                    "cell_text_span": list(printed_value["value_span"])}
            fact["qualifier_sources"].update({key: {**copy.deepcopy(printed_value["sources"][key]),
                                               "cell_text_span": list(printed_value[key + "_span"])}
                                         for key in ("unit", "currency") if key in printed_value["sources"]})
        result["facts"].append(fact)
        for issue in local_issues:
            issue.setdefault("affected_fact_ids", []).append(fact["id"])
        for item in [*evidence, *row_evidence]:
            result["relations"].append({"type": "matrix_header_binding", "source": item["source"],
                "target": fact["source"], "endpoint": {"subject": subject, "attribute": attribute,
                                                       "identity_facets": facets}, "evidence": item})
    amount_records = {fact["record_id"] for fact in result["facts"] if is_amount_role(fact["attribute"])}
    for fact in result["facts"]:
        unit = fact["qualifiers"].get("unit")
        proof = fact.get("qualifier_provenance", {}).get("unit", {})
        if (unit and unit_kind(unit) == "money" and fact["record_id"] in amount_records
                and proof.get("level") == "record_explicit" and not unit_applicable(unit, [fact["attribute"]])):
            fact["qualifiers"].pop("unit")
            proof["application"] = "shared_amount_role_does_not_qualify_this_non_amount_field"
            proof["status"] = "not_applied"
    result["complete"] = not result["blockers"]
    result["has_candidate_ambiguity"] = any(issue["category"] == "candidate_ambiguity" for issue in result["issues"])
    return result
