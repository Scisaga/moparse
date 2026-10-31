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

_SCALAR = re.compile(r"\(?\s*(?:(?:[<>]=?|[≤≥≧≦])\s*)?[$€£¥]?\s*[+\-−]?(?:\d[\d,.]*|\.\d+)\s*[%％‰]?\s*\)?|[—–-]")
_PERIOD = re.compile(
    r"(?:19|20)\d{2}(?:\s*年(?:度|末)?)?|Year Ended|截至.{1,24}(?:年度|年末)|"
    r"第[一二三四1-4]季度(?:\s*[（(]\s*\d{1,2}\s*[-–—至]\s*\d{1,2}\s*月份?\s*[)）])?|"
    r"(?<![A-Za-z0-9])Q[1-4](?![A-Za-z0-9])", re.I,
)
_MEASURE = re.compile(r"金额|金額|收入|成本|比率|比例|占|佔|同比|增减|增減|单位|單位|浓度|濃度|排放|数量|數量|Amount|Revenue|Cost|Change|Rate|Ratio|Balance|Total", re.I)
_FIELD = re.compile(r"^(?:召开日期|召開日期|会议内容|會議內容|重要意见和建议|重要意見和建議|会议决议|會議決議|姓名|名称|名稱|职务|職務|日期|Name|Date|Position)$", re.I)
_UNIT = re.compile(r"(?:人民币|人民幣)?(?:百万元|百萬元|千元|万元|萬元|元)|\$\s*(?:bn|m)|[%％‰]|(?:毫克|千克|公斤|吨|噸)(?:/[^()（）\s]+)?")
_SECTION = re.compile(r"^\s*(?:[（(]\d+[)）]\s*)?((?:19|20)\d{2}\s*年度)[^。；;]{0,32}(?:情况|情況|数据|數據)\s*[:：]$")
_IDENTITY = re.compile(r"项目|項目|项目名称|項目名稱|名称|名稱|姓名|股东名称|股東名稱|认购方|認購方|认购对象|認購對象|Name|Item|Project|Subscriber|Investor", re.I)
_TABLE_MARKUP = re.compile(r"(?:<|&lt;)\s*/?\s*(?:table|tr|td|th)\b", re.I)


def scalar(text: str) -> bool:
    return bool(_SCALAR.fullmatch(text.strip()))


def identity_header(text: str) -> bool:
    return bool(_IDENTITY.fullmatch(text.strip()))


def unit_description(text: str) -> bool:
    literal = re.fullmatch(r"[（(]\s*(.*?)\s*[)）]", text.strip())
    if not literal:
        return False
    payload = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", literal[1])
    scale = r"[十百千万萬亿億]*"
    amount = (rf"(?:(?:人民币|人民幣|美元|港元|港幣|港币|欧元|歐元)?{scale}元"
              rf"|{scale}(?:美元|港元|港幣|港币|欧元|歐元)|人民币|人民幣)(?:/[^\s()（）]+)?")
    currency = (r"(?:in\s+)?(?:[$€£¥]|USD|EUR|HKD|RMB|CNY)\s*"
                r"(?:(?:in\s+)?(?:thousands?|millions?|billions?)|bn|m)?"
                r"(?:,\s*except\s+per\s+share\s+(?:data|amounts))?")
    shares = r"[十百千万萬亿億]*股"
    physical = rf"{scale}(?:盎司|吨|噸|千克|公斤|毫克)(?:/[^\s()（）]+)?"
    return bool(re.fullmatch(amount + "|" + currency + "|" + shares + "|" + physical + r"|[%％‰]", payload, re.I))


def unit_header(text: str) -> bool:
    return unit_description(text) or unit_description("(" + text.strip() + ")")


def row_unit_description(text: str) -> bool:
    """Read a row's whole unit, including an explicitly labelled count scale."""
    count_label = re.match(r"^(?:number\s+of\b|(?:retails?\s+)?(?:customers|contracts|employees|users|shares)\b)",
                           text.strip(), re.I)
    for part in re.finditer(r"[（(]([^()（）]+)[)）]", text):
        if unit_description(part[0]) or part[1].strip().casefold() in {"days", "times"} or (count_label and re.fullmatch(
                r"(?:in\s+)?(?:thousands?|millions?|billions?|contracts?|persons?|people|employees|users|shares)",
                part[1].strip(), re.I)):
            return True
    return False


def _unit_caption(text: str) -> tuple[str, int] | None:
    wrapper = re.fullmatch(r"\s*[（(]\s*(.*?)\s*[)）]\s*", text, re.S)
    declaration = wrapper[1] if wrapper else text
    offset = wrapper.start(1) if wrapper else 0
    match = re.fullmatch(r"\s*(?:货币单位|貨幣單位|单位|單位|Units?)\s*[:：]\s*(.+?)\s*", declaration, re.I | re.S)
    if match:
        currency = re.fullmatch(
            r"(.+?)\s+(?:币种|幣種|Currency)\s*[:：]\s*"
            r"(?:人民币|人民幣|美元|港元|港币|港幣|欧元|歐元|RMB|CNY|USD|HKD|EUR)", match[1], re.I,
        )
        if unit_description("(" + (currency[1] if currency else match[1]) + ")"):
            return match[1], offset + match.start(1)
    return (text, 0) if unit_description(text) else None


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
                                "header_scopes": [], "row_groups": {}, "retained_row_context": {},
                                "structure_readable": False}
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
        subjects = [c for c in headers if identity_header(c.text)]
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
        repeat = bool(stub and first and stub.text.strip() and stub.text.strip() == first.text.strip()
                and any(_PERIOD.search(c.text) or _MEASURE.search(c.text) for c in band if c.column > 0)
                and all(not scalar(c.text) or _PERIOD.fullmatch(c.text.strip()) for c in band)
                and all(c.row_span == 1 for c in band))
        # A blank corner may introduce a complete new period band. Bare
        # numeric years could also be unnamed values, so require explicit
        # dated labels and the complete original single-row partition.
        dated = re.compile(r"(?:19|20)\d{2}\s*年(?:度|末)")
        changed_period = bool(
            stub and not stub.text.strip() and first_body - header_start == 1
            and len(band) == fragment.num_cols and all(c.row_span == c.column_span == 1 for c in band)
            and all(c.row_span == c.column_span == 1 for c in headers)
            and sum(bool(dated.fullmatch(c.text.strip())) for c in band if c.column > 0) >= 2
            and all(dated.fullmatch(c.text.strip()) or (not scalar(c.text) and len(c.text) <= 60
                    and (_MEASURE.search(c.text) or re.search(r"[%％‰]", c.text))) for c in band if c.column > 0)
        )
        if repeat or changed_period:
            scopes[-1]["body_rows"] = [r for r in scopes[-1]["body_rows"] if r < row]
            scopes.append({**scope, "header_rows": [row], "body_rows": list(range(row + 1, fragment.num_rows)),
                           "evidence": {**scope["evidence"], "explicit_period_switch": changed_period}})
    evidence.update(content_kind="data_table", header_scopes=scopes)
    _row_context(fragment, evidence, scopes)
    return evidence


def _row_context(fragment: TableFragment, evidence: dict[str, Any], scopes: list[dict[str, Any]]) -> None:
    """Keep literal section/list boundaries within a declared column scope."""
    cells = fragment.cells
    row_cols = scopes[-1].get("row_header_columns", [0])
    first_body = min((r for scope in scopes for r in scope["body_rows"]), default=fragment.num_rows)
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
    bulleted_group: bool | None = None
    for row in range(first_body, fragment.num_rows):
        if any(row in s["header_rows"] for s in scopes):
            group = None
            bulleted_group = None
            continue
        band = [c for c in cells if c.row == row]
        labels_in_row = [c for c in band if c.column in row_cols and c.text.strip()]
        nonlabels = [c for c in band if c.column not in row_cols]
        title = labels_in_row[0].text.strip() if len(labels_in_row) == 1 else ""
        if (re.fullmatch(r"(?:加|减|減|Add|Less)\s*[:：]?", title, re.I)
                or re.match(r"(?:注|Notes?)\s*[:：]", title, re.I)):
            # Arithmetic instructions remain source text, never entity parents.
            group = None
            bulleted_group = None
            continue
        full_width = (len(band) == 1 and band[0].column == 0
                      and band[0].column_span == fragment.num_cols and band[0].row_span == 1)
        if (len(labels_in_row) == 1 and (full_width or nonlabels and all(not c.text.strip() for c in nonlabels))
                and len(title) <= 100 and not re.search(r"[。；;]", title)
                and not re.match(r"(?:注|Notes?)\s*[:：]", title, re.I)):
            group = (labels_in_row[0].row, labels_in_row[0].column)
            bulleted_group = None
        elif not labels_in_row:
            if group and nonlabels and any(scalar(c.text) for c in nonlabels):
                # Retaining an unnamed row must not detach its already printed
                # section heading. This does not declare a total or row name.
                evidence["retained_row_context"][str(row)] = list(group)
            group = None
            bulleted_group = None
        elif group:
            group_cell = next(c for c in cells if (c.row, c.column) == group)
            bullet = bool(re.match(r"^[\-–—•]\s+\S", title))
            if bulleted_group and not bullet:
                # A literal child list ends before the next unmarked record.
                # Do not carry its introductory label into totals, balances
                # or unrelated measurements. No business-word normalization
                # or missing indentation is needed for this boundary.
                group = None
                bulleted_group = None
                continue
            if bulleted_group is None:
                bulleted_group = bullet
            closed = closes_group(group_cell.text, labels_in_row[-1].text)
            sibling = bool(re.match(r"^[一二三四五六七八九十百]+[、.]", labels_in_row[-1].text.strip()))
            if not closed or not sibling:
                evidence["row_groups"][str(row)] = list(group)
            if closed:
                group = None
                bulleted_group = None
    _bounded_numbered_groups(fragment, evidence, scopes)


def _bounded_numbered_groups(fragment: TableFragment, evidence: dict[str, Any], scopes: list[dict[str, Any]]) -> None:
    """Read complete literal numbered sections, not lost numeric indentation."""
    by_row: dict[int, list[Any]] = {}
    for cell in fragment.cells:
        by_row.setdefault(cell.row, []).append(cell)

    def measurement(row: int) -> Any:
        cells = by_row.get(row, [])
        stub = next((c for c in cells if c.column == 0 and c.row_span == c.column_span == 1
                     and c.text.strip()), None)
        return stub if stub and any(c.column > 0 and scalar(c.text) for c in cells) else None

    numbered = re.compile(r"^([一二三四五六七八九十百]+)([、.])\s*\S")
    for scope in scopes:
        if scope.get("row_header_columns", [0]) != [0] or scope.get("evidence", {}).get("explicit_record_fields"):
            continue
        rows = scope["body_rows"]
        parents = [(row, stub, match) for row in rows if (stub := measurement(row)) is not None
                   and (match := numbered.match(stub.text.strip()))]
        for (start, parent, opening), (end, _, closing) in zip(parents, parents[1:], strict=False):
            children = [row for row in rows if start < row < end]
            if (opening[1] == closing[1] or opening[2] != closing[2]
                    or not children or children != list(range(start + 1, end))):
                continue
            labels = [measurement(row) for row in children]
            if (any(label is None for label in labels)
                    or not re.match(r"^其中\s*[:：]", labels[0].text.strip())
                    or any(row in evidence.get("operation_rows", []) for row in children)
                    or any(str(row) in evidence["row_groups"] for row in [start, *children])
                    or any(re.match(r"^(?:注|Notes?)\s*[:：]|^(?:合计|合計|总计|總計|小计|小計|Total|Subtotal)(?:\s|$)",
                                    label.text.strip(), re.I) for label in labels)):
                continue
            for row in children:
                evidence["row_groups"][str(row)] = [parent.row, parent.column]


def _text(block: dict[str, Any]) -> str:
    value = block.get("content")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_text(item) for item in value if isinstance(item, dict)]
        return ("\n" if block.get("type") == "list" else "").join(parts)
    return ""


def _literal_table_captions(blocks: list[Any], position: int) -> list[tuple[int, str]]:
    """Read an adjacent literal table number/name, without a producer role tag."""
    run: list[tuple[int, str]] = []
    for index in range(position - 1, max(-1, position - 5), -1):
        block = blocks[index]
        if not isinstance(block, dict) or block.get("type") not in {
                "text", "paragraph", "title", "paragraph_title", "table_caption"}:
            break
        text = _text(block).strip()
        if not text or _TABLE_MARKUP.search(text):
            break
        run.insert(0, (index, _text(block)))
        if re.fullmatch(r"\s*(?:附?表|Table)\s*[A-Z]?\d+(?:[.\-]\d+)*\s*", text, re.I):
            if len(run) < 2:
                return []
            title = run[1][1].strip()
            if (len(title) > 80 or re.search(r"[。；;：:\n]|\bsee\b|\brefer\b", title, re.I)
                    or _unit_caption(title) or re.fullmatch(r"[（(].*[)）]", title)):
                return []
            if all(_unit_caption(value) or (re.fullmatch(r"\s*[（(][^()（）\n]{1,40}[)）]\s*", value)
                       and not re.search(r"[=\\$<>]", value)) for _, value in run[2:]):
                return run
            return []
    return []


def _refine_source_header_scopes(fragment: TableFragment, scopes: list[dict[str, Any]]) -> None:
    """Refine a coarser bound role range using its complete literal subranges."""
    if (not fragment.pdf_evidence.get("bound") or len(fragment.source_header_scopes) != 1 or len(scopes) < 2
            or not fragment.native_evidence.get("structure_readable")):
        return
    original = fragment.source_header_scopes[0]
    if (not original.get("complete") or original.get("header_rows") != scopes[0].get("header_rows")
            or any(not scope.get("evidence", {}).get("explicit_period_switch") for scope in scopes[1:])
            or any(not scope.get("complete") or scope.get("evidence_source") != "native_literal_measurement_headers"
                   or scope.get("row_header_columns", [0]) != original.get("row_header_columns", [0]) for scope in scopes)):
        return
    declared = [row for scope in scopes for row in (*scope["header_rows"], *scope["body_rows"])]
    source_rows = [*original.get("header_rows", []), *original.get("body_rows", [])]
    if len(declared) != len(set(declared)) or sorted(declared) != sorted(source_rows):
        return
    fragment.native_evidence["header_scope_refinement"] = {"original_scope": original,
                                                          "reason": "complete_literal_subranges_of_bound_source_scope"}
    fragment.source_header_scopes = scopes


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
            else:
                _refine_source_header_scopes(fragment, scopes)
            # A PDF-bound scope may already identify headers such as Q1/Q2
            # which the narrower native classifier does not recognize. Its
            # actual body still owns the adjacent caption; an empty native
            # proposal must not erase those declared relationships.
            body = tuple(dict.fromkeys(r for s in fragment.source_header_scopes
                                       if s.get("complete") for r in s.get("body_rows", [])))
            columns = tuple(range(fragment.num_cols))
            context: list[TextRef] = []

            def add(index: str, value: str, kind: Any, *, start: int = 0, refs: list[TextRef] = context,
                    owner: TableFragment = fragment, number: int = page,
                    rows: tuple[int, ...] = body, cols: tuple[int, ...] = columns) -> None:
                if value.strip():
                    refs.append(TextRef(owner.fragment_id, number, index, value, kind, start, start + len(value), rows, cols))

            def caption(index: str, value: str) -> None:
                # A malformed native caption can contain its complete table.
                # Preserve that original body elsewhere, but never repeat its
                # cells as a unit or title on neighboring business records.
                if _TABLE_MARKUP.search(value):
                    return
                if re.fullmatch(r"\s*(?:[□☐☑✓√]\s*(?:不适用|不適用|适用|適用|是|否)\s*)+", value):
                    # Keep the printed answer in its original body, without
                    # turning a checkbox response into every record's title.
                    return
                unit = _unit_caption(value)
                if unit is not None:
                    add(index, unit[0], "unit", start=unit[1])
                else:
                    add(index, value, "title")

            if section:
                add(str(section[0]), section[1], "period", start=section[2])
            children = block.get("content", [])
            if isinstance(children, list):
                for child_index, child in enumerate(children):
                    if isinstance(child, dict) and child.get("type") in {"table_caption", "table_footnote"}:
                        if child["type"] == "table_caption":
                            caption(f"{position}.{child_index}", _text(child))
                        else:
                            add(f"{position}.{child_index}", _text(child), "note")
            literal_captions = _literal_table_captions(raw_blocks, position) if body else []
            for index, value in literal_captions:
                caption(str(index), value)
            previous = -1 if literal_captions else position - 1
            preceding: list[tuple[int, str, str]] = []
            numbered_caption = False
            while previous >= 0:
                prior = raw_blocks[previous]
                if not isinstance(prior, dict):
                    break
                value = _text(prior)
                if not value.strip() and prior.get("type") == "list":
                    previous -= 1
                    continue
                if prior.get("type") == "table_caption":
                    if (_TABLE_MARKUP.search(value) or re.search(
                            r"参见|參見|见表|見表|\bsee\s+(?:also\s+)?(?:table|appendix)\b|\brefer\s+to\b", value, re.I)):
                        break
                    if re.match(r"^\s*(?:附?表|Table|Appendix)\s*[A-Z]?\d+", value, re.I):
                        if numbered_caption:
                            break
                        numbered_caption = True
                    preceding.append((previous, value, "caption"))
                    previous -= 1
                    continue
                elif (preceding and prior.get("type") in {"text", "paragraph"}
                      and re.fullmatch(r"\s*[（(][^()（）\n]{1,40}[)）]\s*", value)
                      and not re.search(r"[=\\$<>]", value)
                      and previous > 0 and isinstance(raw_blocks[previous - 1], dict)
                      and raw_blocks[previous - 1].get("type") == "table_caption"):
                    preceding.append((previous, value, "caption"))
                    previous -= 1
                    continue
                elif (prior.get("type") in {"text", "paragraph", "list"}
                      and not _TABLE_MARKUP.search(value)
                      and (_unit_caption(value) is not None or re.search(
                          r"(?:following\s+table|下表|本表).*(?:percent(?:age)?|单位|單位)", value, re.I))):
                    preceding.append((previous, value, "unit"))
                elif (prior.get("type") in {"text", "paragraph", "list"} and not _TABLE_MARKUP.search(value)
                      and value.rstrip().endswith((":", "："))
                      and re.search(r"\bfollowing\b|如下|下表|本表", value, re.I)):
                    preceding.append((previous, value, "title"))
                elif (body and prior.get("type") in {"title", "paragraph_title"}
                      and re.search(r"分季度[^。；;\n]{0,40}(?:数据|數據|指标|指標)\s*$", value)
                      and not _TABLE_MARKUP.search(value)):
                    preceding.append((previous, value, "title"))
                break
            for index, value, kind in reversed(preceding):
                if kind == "caption":
                    caption(str(index), value)
                elif kind == "unit":
                    unit = _unit_caption(value)
                    add(str(index), unit[0] if unit else value, "unit", start=unit[1] if unit else 0)
                else:
                    add(str(index), value, "title")
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
                    caption(f"cell.{cell.row}.0", cell.text)
            fragment.context_refs = tuple(dict.fromkeys(context))
    _prepare_native_continuations(result)


def _prepare_native_continuations(result: DocumentParseResult) -> None:
    """Use an explicit producer continuation with complete local source paths.

    Physical tables and their cell identities stay separate. Missing declarations,
    conflicting source evidence, local headers, intervening content and changed
    column partitions block inheritance rather than borrow a nearby table.
    """
    from dataclasses import replace

    from app.services.table_service import (
        PageFurnitureFragment,
        _context_evidence,
        _table_context_pages,
    )

    fragments = sorted((f for f in result._table_fragments if isinstance(f, TableFragment)),
                       key=lambda f: (f.page_number, f.ordinal))
    contents = {page.page_number: page.content or "" for page in result.pages}
    furniture = [f for f in result._page_furniture if isinstance(f, PageFurnitureFragment)]
    for left, right in zip(fragments, fragments[1:], strict=False):
        def blocked(reason: str, *, owner: TableFragment = right, source: str = left.fragment_id,
                    **details: Any) -> None:
            owner.native_evidence["continuation_scope_guard"] = {
                "source_table_id": source, "reason": reason, **details,
            }

        if right.source_continues_prev is not True:
            continue
        if (right.page_number != left.page_number + 1
                or left.source_kind != "mineru" or right.source_kind != "mineru"
                or left.num_cols != right.num_cols or right.source_header_scopes or right.header_row_indices
                or not all(f.valid and f.native_evidence.get("structure_readable") for f in (left, right))
                or right.pdf_evidence.get("inherited_header_scope")
                or right.caption or right.unit_text or any(ref.kind != "note" for ref in right.context_refs)):
            blocked("incompatible_native_structure_or_existing_scope")
            continue
        if any(re.search(r"disagree|conflict|ownership_ambiguous", str(f.pdf_evidence.get(key, "")))
               for f in (left, right) for key in ("reason", "cell_box_attempt_reason")):
            blocked("source_conflict")
            continue
        scopes = [s for s in left.source_header_scopes if s.get("complete")]
        if not scopes:
            blocked("missing_complete_preceding_headers")
            continue
        scope = scopes[-1]
        rows = scope.get("header_rows")
        if (not isinstance(rows, list) or not rows
                or any(type(row) is not int or not 0 <= row < left.num_rows for row in rows)
                or rows != list(range(rows[0], rows[-1] + 1))
                or not isinstance(scope.get("body_rows"), list)
                or not (scope["body_rows"][-1:] == [left.num_rows - 1]
                        or not scope["body_rows"] and rows[-1] == left.num_rows - 1)
                or left.num_rows - 1 in left.native_evidence.get("operation_rows", [])):
            blocked("preceding_scope_does_not_reach_continuation")
            continue
        # Each field must keep the same complete column partition. A native
        # continuation flag never authorizes splitting a value across fields.
        row_cols = scope.get("row_header_columns", [0])
        if row_cols != [0] or any(
            c.column_span != 1 and not (c.column == 0 and c.column_span == right.num_cols)
            for c in right.cells
        ) or any(c.row_span != 1 for c in right.cells):
            blocked("incompatible_column_partitions")
            continue
        if any(contents.get(f.page_number, "").count(f.rendered) != 1 for f in (left, right)):
            blocked("physical_table_not_uniquely_located")
            continue
        context = _table_context_pages([left, right], contents, fragments, furniture)
        tail = context[left.page_number].partition(left.rendered)[2]
        prefix = context[right.page_number].partition(right.rendered)[0]
        if any(_context_evidence(text) != ({}, ()) for text in (tail, prefix)):
            blocked("intervening_content", left_tail=_context_evidence(tail), right_prefix=_context_evidence(prefix))
            continue
        # Complete nonempty measurement paths must exist for every value
        # column; headers crossing the body or spanning incompatible fields
        # remain unresolved. No header is synthesized from a data row.
        headers = [c for c in left.cells if c.row in rows]
        if not headers or any(c.row + c.row_span > rows[-1] + 1 for c in headers):
            blocked("header_spans_cross_body")
            continue
        if any(not any(c.text.strip() and c.column <= col < c.column + c.column_span for c in headers)
               for col in range(1, right.num_cols)):
            blocked("missing_column_header_path")
            continue
        body = list(range(right.num_rows))
        inherited = {"complete": True, "source_table_id": left.fragment_id,
                     "source_page": left.page_number, "header_rows": list(rows),
                     "source_column_groups": [[col] for col in range(right.num_cols)],
                     "body_rows": body, "body_columns": list(range(right.num_cols)), "row_header_columns": row_cols,
                     "evidence_source": "native_literal_declared_continuation",
                     "evidence": {"explicit_record_fields": scope.get("evidence", {}).get("explicit_record_fields", False)}}
        right.native_evidence["inherited_header_scope"] = inherited
        right.native_evidence["continuation_scope_guard"] = {"source_table_id": left.fragment_id, "reason": "bound"}
        right.native_evidence["content_kind"] = "data_table"
        _row_context(right, right.native_evidence, [{**inherited, "header_rows": []}])
        own_notes = tuple(replace(ref, body_rows=tuple(body)) for ref in right.context_refs)
        inherited_context = tuple(replace(ref, table_id=right.fragment_id,
                                           block_id=f"continuation.{left.fragment_id}.{ref.block_id}",
                                           body_rows=tuple(body)) for ref in left.context_refs if ref.kind != "note")
        right.context_refs = (*own_notes, *inherited_context)
