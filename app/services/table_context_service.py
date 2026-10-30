"""Read native table structure and bounded business scopes without references.

PDF source evidence remains separate. Native structure is an entry point, not
a declaration of table purpose: scalar comparisons or explicit record fields
must support a local header/body association before any row is verbalized.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.parse_result import DocumentParseResult
from app.models.table_semantics import TextRef
from app.services.table_service import TableFragment

_SCALAR = re.compile(r"\(?\s*[$€£¥]?\s*[+\-−]?(?:\d[\d,.]*|\.\d+)\s*[%％‰]?\s*\)?|[—–-]")
_PERIOD = re.compile(r"(?:19|20)\d{2}(?:\s*年(?:度|末)?)?|Year Ended|截至.{1,24}(?:年度|年末)", re.I)
_MEASURE = re.compile(r"金额|金額|收入|成本|比率|比例|占|佔|同比|单位|單位|浓度|濃度|排放|数量|數量|Amount|Revenue|Cost|Change|Rate|Ratio|Balance|Total", re.I)
_FIELD = re.compile(r"^(?:召开日期|召開日期|会议内容|會議內容|重要意见和建议|重要意見和建議|会议决议|會議決議|姓名|名称|名稱|职务|職務|日期|Name|Date|Position)$", re.I)
_UNIT = re.compile(r"(?:人民币|人民幣)?(?:百万元|百萬元|千元|万元|萬元|元)|\$\s*(?:bn|m)|[%％‰]|(?:毫克|千克|公斤|吨|噸)(?:/[^()（）\s]+)?")
_SECTION = re.compile(r"^\s*(?:[（(]\d+[)）]\s*)?((?:19|20)\d{2}\s*年度)[^。；;]{0,32}(?:情况|情況|数据|數據)\s*[:：]$")


def scalar(text: str) -> bool:
    return bool(_SCALAR.fullmatch(text.strip()))


def unit_description(text: str) -> bool:
    literal = re.fullmatch(r"[（(]\s*(.*?)\s*[)）]", text.strip())
    if not literal:
        return False
    payload = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", literal[1])
    amount = (r"(?:人民币|人民幣|美元|港元|港幣|港币|欧元|歐元)?"
              r"(?:万亿元|萬億元|亿元|億元|百万元|百萬元|千元|万元|萬元|元)(?:/[^\s()（）]+)?")
    currency = r"(?:[$€£¥]|USD|EUR|HKD|RMB|CNY)\s*(?:(?:in\s+)?(?:millions?|billions?)|bn|m)?(?:,\s*except\s+per\s+share\s+(?:data|amounts))?"
    return bool(re.fullmatch(amount + "|" + currency + r"|[%％‰]", payload, re.I))


def closes_group(group: str, label: str) -> bool:
    total = re.fullmatch(r"Total\s+(.+)", label.strip(), re.I)
    if total and total[1].casefold() == group.strip(" :：").casefold():
        return True
    sibling = re.compile(r"^([一二三四五六七八九十百]+)([、.])")
    left, right = sibling.match(group.strip()), sibling.match(label.strip())
    return bool(left and right and left[2] == right[2] and left[1] != right[1])


def native_scopes(fragment: TableFragment) -> dict[str, Any]:
    """Classify local relationships from actual native fields, not grid shape."""
    cells = fragment.cells
    evidence: dict[str, Any] = {"source": "native_cells_and_literal_context", "content_kind": "unknown",
                                "header_scopes": [], "row_groups": {}, "structure_readable": False}
    if not fragment.valid or not cells or fragment.source_kind != "mineru":
        return evidence
    occupied: set[tuple[int, int]] = set()
    for c in cells:
        slots = {(r, col) for r in range(c.row, c.row + c.row_span)
                 for col in range(c.column, c.column + c.column_span)}
        if c.row_span < 1 or c.column_span < 1 or occupied & slots or any(
            r < 0 or col < 0 or r >= fragment.num_rows or col >= fragment.num_cols for r, col in slots
        ):
            evidence["structure_readable"] = False
            return evidence
        occupied.update(slots)
    if len(occupied) != fragment.num_rows * fragment.num_cols:
        evidence["structure_readable"] = False
        return evidence
    evidence["structure_readable"] = True
    first_body = None
    header_start = 0
    for row in range(fragment.num_rows):
        band = [c for c in cells if c.row == row]
        if len(band) == 1 and band[0].column_span == fragment.num_cols:
            # A full-width title is context, not a column path.
            if first_body is None and row == header_start:
                header_start = row + band[0].row_span
            continue
        if row <= header_start:
            continue
        values = [c for c in band if c.column > 0 and scalar(c.text)]
        prior = [c for c in cells if header_start <= c.row < row]
        field_header = len(prior) >= 2 and all(_FIELD.fullmatch(c.text.strip()) for c in prior if c.text.strip())
        date_value = any(re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日", c.text.strip()) for c in band)
        stub = next((c for c in band if c.column == 0 and c.text.strip()), None)
        declared = all(c.is_column_header for c in band if c.text.strip())
        dated_subheader = (any(c.column_span > 1 for c in prior)
                           and any(c.column > 0 and re.match(r"(?:19|20)\d{2}", c.text.strip()) for c in band))
        textual_record = (stub is not None and not declared and not dated_subheader
                          and any(c.column > 0 and c.text.strip() for c in band)
                          and not _PERIOD.fullmatch(stub.text.strip()) and not unit_description(stub.text))
        if values or field_header and date_value or textual_record:
            first_body = row
            break
    if first_body is None or first_body - header_start > 8:
        return evidence
    empty_sections = [row for row in range(header_start + 1, first_body)
                      if (band := [c for c in cells if c.row == row])
                      and len([c for c in band if c.text.strip()]) == 1
                      and any(c.column == 0 and c.text.strip() for c in band)]
    if empty_sections:
        first_body = empty_sections[0]
    headers = [c for c in cells if header_start <= c.row < first_body]
    if not headers or any(len(c.text) > 100 or c.row + c.row_span > first_body for c in headers):
        return evidence
    # A leading key/value record is still data. A scalar can identify a
    # column only when its literal is a complete period, never an amount
    # borrowed from the first row to manufacture a measurement schema.
    if any(c.column > 0 and scalar(c.text) and not _PERIOD.fullmatch(c.text.strip()) for c in headers):
        return evidence
    labels = [c.text.strip() for c in headers if c.text.strip()]
    field_header = len(labels) >= 2 and all(_FIELD.fullmatch(t) for t in labels)
    if not field_header and not any(_PERIOD.search(t) or _MEASURE.search(t) or _UNIT.search(t) for t in labels):
        return evidence
    # Row header columns may occupy a merged field label (group + record).
    first = next((c for c in headers if c.column == 0), None)
    row_cols = list(range(first.column_span)) if first else [0]
    if field_header:
        subjects = [c for c in headers if re.fullmatch(r"会议内容|會議內容|姓名|名称|名稱|Name", c.text.strip(), re.I)]
        if len(subjects) == 1 and subjects[0].column_span == 1:
            row_cols = [subjects[0].column]
    if first and re.fullmatch(r"序号|序號|Index|No\.?", first.text.strip(), re.I):
        subjects = [c for c in headers if re.fullmatch(r"项目|項目|项目名称|項目名稱|名称|名稱|姓名|Name|Item", c.text.strip(), re.I)]
        if len(subjects) == 1 and subjects[0].column_span == 1:
            row_cols = [subjects[0].column]
    if len(row_cols) >= fragment.num_cols:
        return evidence
    scope: dict[str, Any] = {"header_rows": list(range(header_start, first_body)),
             "body_rows": list(range(first_body, fragment.num_rows)), "row_header_columns": row_cols,
             "complete": True, "evidence_source": "native_literal_record_schema" if field_header else "native_literal_measurement_headers",
             "evidence": {"explicit_record_fields": field_header, "scalar_body": not field_header}}
    scopes = [scope]
    for row in range(first_body + 1, fragment.num_rows):
        band = [c for c in cells if c.row == row]
        stub = next((c for c in band if c.column == 0), None)
        if (stub and first and stub.text.strip() == first.text.strip()
                and any(_PERIOD.search(c.text) or _MEASURE.search(c.text) for c in band if c.column > 0)
                and all(not scalar(c.text) or _PERIOD.fullmatch(c.text.strip()) for c in band)
                and all(c.row_span == 1 for c in band)):
            scopes[-1]["body_rows"] = [r for r in scopes[-1]["body_rows"] if r < row]
            scopes.append({**scope, "header_rows": [row], "body_rows": list(range(row + 1, fragment.num_rows))})
    evidence.update(content_kind="data_table", header_scopes=scopes)
    operation_rows: list[int] = []
    for current in scopes:
        body = current["body_rows"]
        beginnings = []
        for row in body:
            band = [c for c in cells if c.row == row]
            labels_in_row = [c for c in band if c.column in row_cols and c.text.strip()]
            if (len(labels_in_row) == 1
                    and re.fullmatch(r"(?:加|减|減|Add|Less)\s*[:：]?", labels_in_row[0].text.strip(), re.I)
                    and all(not c.text.strip() for c in band if c.column not in row_cols)):
                beginnings.append(row)
        if beginnings:
            # No arithmetic or typography-based inference supplies an end.
            # Keep this region until the next independently declared header.
            operation_rows.extend(row for row in body if row >= min(beginnings))
    evidence["operation_rows"] = operation_rows
    # A blank value band explicitly introduces a group. Numeric parent rows
    # do not establish indentation that the producer did not preserve.
    group = None
    for row in range(first_body, fragment.num_rows):
        if any(row in s["header_rows"] for s in scopes):
            group = None
            continue
        band = [c for c in cells if c.row == row]
        labels_in_row = [c for c in band if c.column in row_cols and c.text.strip()]
        nonlabels = [c for c in band if c.column not in row_cols]
        title = labels_in_row[0].text.strip() if len(labels_in_row) == 1 else ""
        if (re.fullmatch(r"(?:加|减|減|Add|Less)\s*[:：]?", title, re.I)
                or re.match(r"(?:注|Notes?)\s*[:：]", title, re.I)):
            # Arithmetic instructions remain source text, never entity parents.
            group = None
            continue
        full_width = (len(band) == 1 and band[0].column == 0
                      and band[0].column_span == fragment.num_cols and band[0].row_span == 1)
        if (len(labels_in_row) == 1 and (full_width or nonlabels and all(not c.text.strip() for c in nonlabels))
                and len(title) <= 100 and not re.search(r"[。；;]", title)
                and not re.match(r"(?:注|Notes?)\s*[:：]", title, re.I)):
            group = (labels_in_row[0].row, labels_in_row[0].column)
        elif not labels_in_row:
            group = None
        elif group:
            group_cell = next(c for c in cells if (c.row, c.column) == group)
            closed = closes_group(group_cell.text, labels_in_row[-1].text)
            sibling = bool(re.match(r"^[一二三四五六七八九十百]+[、.]", labels_in_row[-1].text.strip()))
            if not closed or not sibling:
                evidence["row_groups"][str(row)] = list(group)
            if closed:
                group = None
    return evidence


def _text(block: dict[str, Any]) -> str:
    value = block.get("content")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_text(item) for item in value if isinstance(item, dict)]
        return ("\n" if block.get("type") == "list" else "").join(parts)
    return ""


def prepare_native_table_scopes(result: DocumentParseResult) -> None:
    for page, raw_blocks in result._native_page_blocks.items():
        fragments = [f for f in result._table_fragments if isinstance(f, TableFragment) and f.page_number == page]
        tables = [b for b in raw_blocks if isinstance(b, dict) and b.get("type") == "table"]
        # Multiple bodies or malformed tables retain their own existing data;
        # do not assign outside context through a guessed ordinal mapping.
        if len(tables) != len(fragments):
            continue
        section: tuple[int, str, int] | None = None
        table_index = 0
        for position, block in enumerate(raw_blocks):
            if not isinstance(block, dict):
                section = None
                continue
            text = _text(block)
            lines = [line for line in re.finditer(r"[^\r\n]+", text) if line[0].strip()]
            tail = lines[-1] if lines else None
            if tail and _SECTION.fullmatch(tail[0].strip()):
                literal = tail[0].strip()
                section = position, literal, tail.start() + len(tail[0]) - len(tail[0].lstrip())
            elif section and re.match(r"^\s*[（(]\d+[)）]", text):
                section = None
            if block.get("type") != "table":
                continue
            fragment = fragments[table_index]
            table_index += 1
            fragment.native_evidence = native_scopes(fragment)
            scopes = fragment.native_evidence.get("header_scopes", [])
            if not fragment.source_header_scopes and scopes:
                fragment.source_header_scopes = scopes
            body = tuple(r for s in scopes for r in s["body_rows"])
            columns = tuple(range(fragment.num_cols))
            context: list[TextRef] = []

            def add(index: str, value: str, kind: Any, *, start: int = 0, refs: list[TextRef] = context,
                    owner: TableFragment = fragment, number: int = page,
                    rows: tuple[int, ...] = body, cols: tuple[int, ...] = columns) -> None:
                if value.strip():
                    refs.append(TextRef(owner.fragment_id, number, index, value, kind, start, start + len(value), rows, cols))

            if section:
                add(str(section[0]), section[1], "period", start=section[2])
            children = block.get("content", [])
            if isinstance(children, list):
                for child_index, child in enumerate(children):
                    if isinstance(child, dict) and child.get("type") in {"table_caption", "table_footnote"}:
                        add(f"{position}.{child_index}", _text(child), "title" if child["type"] == "table_caption" else "note")
            previous = position - 1
            while previous >= 0:
                prior = raw_blocks[previous]
                if not isinstance(prior, dict):
                    break
                value = _text(prior)
                if not value.strip() and prior.get("type") == "list":
                    previous -= 1
                    continue
                if prior.get("type") == "table_caption":
                    add(str(previous), value, "title")
                elif re.search(r"(?:following\s+table|下表|本表).*(?:percent(?:age)?|单位|單位)|^(?:单位|單位)\s*[:：]", value, re.I):
                    add(str(previous), value, "unit")
                break
            for next_index in range(position + 1, len(raw_blocks)):
                following = raw_blocks[next_index]
                if not isinstance(following, dict):
                    break
                value = _text(following)
                if not value.strip() and following.get("type") == "list":
                    continue
                if following.get("type") != "table_footnote":
                    break
                add(str(next_index), value, "note")
            for cell in fragment.cells:
                if cell.column == 0 and cell.column_span == fragment.num_cols and cell.row < min(body, default=0):
                    add(f"cell.{cell.row}.0", cell.text, "title")
            fragment.context_refs = tuple(dict.fromkeys(context))
