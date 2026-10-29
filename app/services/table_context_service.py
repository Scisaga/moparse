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

_SCALAR = re.compile(r"\(?\s*[$€£¥]?[+\-−]?(?:\d[\d,.]*|\.\d+)\s*[%％‰]?\s*\)?|[—–-]")
_PERIOD = re.compile(r"(?:19|20)\d{2}(?:\s*年(?:度|末)?)?|Year Ended|截至.{1,24}(?:年度|年末)", re.I)
_MEASURE = re.compile(r"金额|金額|收入|成本|比率|比例|占|佔|同比|单位|單位|浓度|濃度|排放|数量|數量|Amount|Revenue|Cost|Change|Rate|Ratio|Balance|Total", re.I)
_FIELD = re.compile(r"^(?:召开日期|召開日期|会议内容|會議內容|重要意见和建议|重要意見和建議|会议决议|會議決議|姓名|名称|名稱|职务|職務|日期|Name|Date|Position)$", re.I)
_UNIT = re.compile(r"(?:人民币|人民幣)?(?:百万元|百萬元|千元|万元|萬元|元)|\$\s*(?:bn|m)|[%％‰]|(?:毫克|千克|公斤|吨|噸)(?:/[^()（）\s]+)?")
_SECTION = re.compile(r"^\s*(?:[（(]\d+[)）]\s*)?((?:19|20)\d{2}\s*年度)[^。；;]{0,32}(?:情况|情況|数据|數據)\s*[:：]$")


def scalar(text: str) -> bool:
    return bool(_SCALAR.fullmatch(text.strip()))


def native_scopes(fragment: TableFragment) -> dict[str, Any]:
    """Classify local relationships from actual native fields, not grid shape."""
    cells = fragment.cells
    evidence: dict[str, Any] = {"source": "native_cells_and_literal_context", "content_kind": "unknown",
                                "header_scopes": [], "row_groups": {}, "structure_readable": bool(fragment.valid and cells)}
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
    first_body = None
    header_start = 0
    for row in range(fragment.num_rows):
        band = [c for c in cells if c.row == row]
        if len(band) == 1 and band[0].column_span == fragment.num_cols:
            # A full-width title is context, not a column path.
            if first_body is None:
                header_start = row + band[0].row_span
            continue
        if row <= header_start:
            continue
        values = [c for c in band if c.column > 0 and scalar(c.text)]
        prior = [c for c in cells if header_start <= c.row < row]
        field_header = len(prior) >= 2 and all(_FIELD.fullmatch(c.text.strip()) for c in prior if c.text.strip())
        date_value = any(re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日", c.text.strip()) for c in band)
        if values or field_header and date_value:
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
    labels = [c.text.strip() for c in headers if c.text.strip()]
    field_header = len(labels) >= 2 and all(_FIELD.fullmatch(t) for t in labels)
    if not field_header and not any(_PERIOD.search(t) or _MEASURE.search(t) or _UNIT.search(t) for t in labels):
        return evidence
    # Row header columns may occupy a merged field label (group + record).
    first = next((c for c in headers if c.column == 0), None)
    row_cols = list(range(first.column_span)) if first else [0]
    if len(row_cols) >= fragment.num_cols:
        return evidence
    scope = {"header_rows": list(range(header_start, first_body)),
             "body_rows": list(range(first_body, fragment.num_rows)), "row_header_columns": row_cols,
             "complete": True, "evidence_source": "native_literal_record_schema" if field_header else "native_literal_measurement_headers",
             "evidence": {"explicit_record_fields": field_header, "scalar_body": not field_header}}
    evidence.update(content_kind="data_table", header_scopes=[scope])
    # A blank value band explicitly introduces a group. Numeric parent rows
    # do not establish indentation that the producer did not preserve.
    group = None
    for row in range(first_body, fragment.num_rows):
        band = [c for c in cells if c.row == row]
        labels_in_row = [c for c in band if c.column in row_cols and c.text.strip()]
        nonlabels = [c for c in band if c.column not in row_cols]
        if len(labels_in_row) == 1 and nonlabels and all(not c.text.strip() for c in nonlabels):
            group = (labels_in_row[0].row, labels_in_row[0].column)
        elif not labels_in_row:
            group = None
        elif group:
            evidence["row_groups"][str(row)] = list(group)
    return evidence


def _text(block: dict[str, Any]) -> str:
    value = block.get("content")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(item.get("content", "")) for item in value if isinstance(item, dict) and isinstance(item.get("content"), str))
    return ""


def prepare_native_table_scopes(result: DocumentParseResult) -> None:
    for page, raw_blocks in result._native_page_blocks.items():
        fragments = [f for f in result._table_fragments if isinstance(f, TableFragment) and f.page_number == page]
        tables = [b for b in raw_blocks if isinstance(b, dict) and b.get("type") == "table"]
        # Multiple bodies or malformed tables retain their own existing data;
        # do not assign outside context through a guessed ordinal mapping.
        if len(tables) != len(fragments):
            continue
        section: tuple[int, str] | None = None
        table_index = 0
        for position, block in enumerate(raw_blocks):
            if not isinstance(block, dict):
                section = None
                continue
            text = _text(block)
            if _SECTION.fullmatch(text):
                section = position, text
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

            def add(index: str, value: str, kind: Any, *, refs: list[TextRef] = context,
                    owner: TableFragment = fragment, number: int = page,
                    rows: tuple[int, ...] = body, cols: tuple[int, ...] = columns) -> None:
                if value.strip():
                    refs.append(TextRef(owner.fragment_id, number, index, value, kind, 0, len(value), rows, cols))

            if section:
                add(str(section[0]), section[1], "period")
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
