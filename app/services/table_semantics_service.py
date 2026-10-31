"""Conservative source-scoped relations and literal Markdown verbalization.

Source-bound grids and explicitly scoped relationships are handled independently.
Unresolved rows retain their source text without erasing supported neighbors.
No additional model is called.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult
from app.models.table_semantics import (
    CellRef,
    SemanticKind,
    SemanticRecord,
    SemanticTableView,
    ValueRelation,
)
from app.parsers.base import ParserCancelledError
from app.services.export_service import ExportService
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    TableSourceView,
    render_source_rows,
    table_view,
)
from app.utils.deadline import remaining_timeout

_ID = re.compile(r"[A-Za-z0-9_.-]{1,240}\Z")
_PERIOD = re.compile(r"报告期|同期|年度|期末|年末|月末|\d{4}\s*年|(?<!\d)(?:19|20)\d{2}(?!\d)")
_NUMBER = re.compile(r"[+\-−]?(?:\d[\d,.]*(?:%|％)?|[—–-])\Z")
_RATIO_HEADER = re.compile(r"[%％‰]|同比|增减率|增減率|比上年(?:末|同期)?增[减減]|佔|占|比例|比率|percent|change|ratio|rate", re.I)
_AMOUNT_HEADER = re.compile(r"金额|金額|余额|餘額|额度|額度|\bAmount\b|\bBalance\b", re.I)
_REFERENCE_HEADER = re.compile(
    r"附注|附註|注释|註釋|备注|備註|序号|序號|编号|編號|代码|代碼|"
    r"Notes?|Note\s+references?|References?|Ref\.?|Index|No\.?|ID|Code", re.I,
)


def _compact(value: str) -> str:
    return "".join(
        chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in value if not c.isspace()
    )


def _literal(value: str) -> str:
    # Escape source Markdown/HTML rather than letting it become new structure.
    text = html.escape(re.sub(r"\s+", " ", value).strip(), quote=False)
    return re.sub(r"([\\`*_\[\]~|])", r"\\\1", text)


def _label_separator(rendered_label: str) -> str:
    return "" if rendered_label.rstrip().endswith((":", "：")) else "："


def _record_literal_parts(
    record: SemanticRecord, reference: Any, registry: Mapping[Any, Any],
) -> tuple[str, str]:
    """Print a label's explicitly linked note without leaking TeX wrappers.

    Only textual math labels with an actual scoped note definition qualify.
    Values, bare carets, equations and labels without that definition retain
    their exact literal rendering. The note marker remains visible in prose.
    """
    text = registry[reference].text
    labels = {*record.row_groups, *record.subject_headers}
    if record.subject is not None:
        labels.add(record.subject)
    for value in record.values:
        labels.update((*value.row_headers, *value.column_headers))
    if reference not in labels or any(value.value == reference for value in record.values):
        return _literal(text), ""
    notes = {
        match[1] for value in record.values for ref in value.note_refs
        if reference in (*value.row_headers, *value.column_headers, record.subject, *record.row_groups)
        if (match := re.match(r"^\s*([0-9]{1,2}|[*†‡])(?:\s+|[.)、：:])", registry[ref].text))
    }

    markers = []

    def render_note(match: re.Match[str]) -> str:
        marker = match[2] or match[3]
        if marker not in notes:
            return match[0]
        # A matching note number does not turn a variable's exponent into a
        # footnote. Limit this display change to complete multiword text labels;
        # standalone words, variables and unit/formula labels remain literal.
        label = match[1].replace(r"\ ", " ").strip()
        plain_label = (text[:match.start()] + label + text[match.end():]).strip()
        if not re.fullmatch(r"[A-Za-z]{2,}(?:\s+[A-Za-z]{2,})+", plain_label):
            return match[0]
        markers.append(marker)
        return label

    text = re.sub(
        r"\\\(\s*([A-Za-z](?:[A-Za-z\s]|\\ )*?)\s*\^\s*"
        r"(?:\{([0-9]{1,2}|[*†‡])\}|([0-9]|[*†‡]))\s*\\\)",
        render_note, text,
    )
    suffix = "（附注标记：" + "、".join(dict.fromkeys(markers)) + "）" if markers else ""
    return _literal(text), suffix


def _record_literal(record: SemanticRecord, reference: Any, registry: Mapping[Any, Any]) -> str:
    return "".join(_record_literal_parts(record, reference, registry))


def _per_share_currency(labels: Sequence[str], value: str) -> bool:
    return (any(re.search(r"per\s+share\b|每股", label, re.I) for label in labels)
            and bool(re.fullmatch(r"\s*[$€£¥]\s*[+−-]?(?:\d[\d,.]*|\.\d+)\s*", value)))


def _currency_column_label(text: str) -> tuple[str, str, str] | None:
    """Read a literal currency suffix; its calling path must own a period."""
    from app.services.table_context_service import unit_header

    short = re.fullmatch(r"(.+?)(\$\s*(?:bn|m))", text.strip(), re.I)
    if short is not None:
        return short[1], short[2], ""
    match = re.fullmatch(
        r"((?:19|20)\d{2}(?:\s*年(?:度|末)?|\s*[〇零一二三四五六七八九]{4}年)?)\s*(.+?)"
        r"((?:\s*[（(](?:Restated|經重述|经重述)[)）])*)", text.strip(), re.I,
    )
    if match is None:
        return None
    unit = match[2]
    bilingual_thousands = re.fullmatch(r"(?:RMB|CNY)\s*['’]000(?:\s*(?:人民币|人民幣)千元)?", unit, re.I)
    if not bilingual_thousands and (not unit_header(unit) or not re.search(
            r"元|幣|币|[$€£¥]|\b(?:USD|EUR|HKD|RMB|CNY)\b", unit, re.I)):
        return None
    return match[1], unit, match[3]


def _column_literal_parts(
    record: SemanticRecord, value: ValueRelation, reference: Any, registry: Mapping[Any, Any],
) -> tuple[str, str]:
    """Keep a column's identity while a printed row/value overrides its unit.

    An embedded amount suffix is redundant for an explicit row unit, a printed
    percentage, or a currency value explicitly labelled per share. A currency
    symbol alone does not override a column's million/billion scale.
    """
    from app.services.table_context_service import row_unit_description

    rendered, note = _record_literal_parts(record, reference, registry)
    parts = _currency_column_label(registry[reference].text)
    if parts is None or not any(_PERIOD.search(registry[ref].text) for ref in value.column_headers):
        return rendered, note
    period, unit, qualifier = parts
    for other in record.values:
        if other.value == value.value:
            continue
        for header in other.column_headers:
            other_parts = _currency_column_label(registry[header].text)
            if other_parts and other_parts[0] == period and other_parts[1] != unit:
                # Repeated labels need currency/scale to distinguish columns,
                # even when this row measures a ratio.
                return rendered, note
    row_labels = [registry[ref].text for ref in value.row_headers]
    explicit_unit = any(row_unit_description(label) for label in row_labels)
    printed_value = registry[value.value].text
    printed_ratio = bool(re.search(r"[%％‰]", printed_value))
    per_share = _per_share_currency(row_labels, printed_value)
    if (explicit_unit or printed_ratio or per_share) and rendered == _literal(registry[reference].text):
        return _literal(period + qualifier), note
    return rendered, note


def _ref(fragment: TableFragment, cell: TableCellFragment) -> CellRef:
    return CellRef(fragment.fragment_id, cell.row, cell.column)


def _registry(fragments: Sequence[TableFragment]) -> dict[Any, Any]:
    return {**{_ref(f, c): c for f in fragments for c in f.cells},
            **{ref: ref for f in fragments for ref in f.context_refs}}


def _source_cells(fragment: TableFragment) -> dict[tuple[int, int], dict[str, Any]]:
    grid = fragment.pdf_evidence
    conflicts = {grid.get("reason"), grid.get("cell_box_attempt_reason")}
    if any(reason and re.search(r"disagree|conflict|ownership_ambiguous", str(reason)) for reason in conflicts):
        return {}
    if not grid.get("bound") and fragment.native_evidence.get("structure_readable"):
        grid = {"bound": True, "source_cells": [
            {"row": c.row, "column": c.column, "row_span": c.row_span,
             "column_span": c.column_span, "text": c.text} for c in fragment.cells]}
    if (
        not fragment.valid
        or not grid.get("bound")
        or not fragment.cells
        or not 0 < fragment.num_rows <= 2_000
        or not 0 < fragment.num_cols <= 100
        or len(fragment.rows) != fragment.num_rows
        or any(len(row) != fragment.num_cols for row in fragment.rows)
    ):
        return {}
    sources = grid.get("source_cells", [])
    if len(sources) != len(fragment.cells):
        return {}
    indexed = {(c["row"], c["column"]): c for c in sources}
    occupied: set[tuple[int, int]] = set()
    for cell in fragment.cells:
        source = indexed.get((cell.row, cell.column))
        if (
            source is None
            or cell.row_span < 1
            or cell.column_span < 1
            or source.get("row_span") != cell.row_span
            or source.get("column_span") != cell.column_span
            or _compact(source.get("text", "")) != _compact(cell.text)
        ):
            return {}
        slots = {
            (r, c)
            for r in range(cell.row, cell.row + cell.row_span)
            for c in range(cell.column, cell.column + cell.column_span)
        }
        if occupied & slots or any(
            not (0 <= r < fragment.num_rows and 0 <= c < fragment.num_cols) for r, c in slots
        ):
            return {}
        occupied.update(slots)
        if fragment.rows[cell.row][cell.column] != cell.text:
            return {}
        if any(fragment.rows[r][c].strip() for r, c in slots - {(cell.row, cell.column)}):
            return {}
    if occupied != {(r, c) for r in range(fragment.num_rows) for c in range(fragment.num_cols)}:
        return {}
    return indexed


def _header_path(
    headers: Sequence[TableCellFragment], cell: TableCellFragment
) -> tuple[TableCellFragment, ...] | None:
    selected = []
    for header in headers:
        lo, hi = header.column, header.column + header.column_span
        if hi <= cell.column or lo >= cell.column + cell.column_span:
            continue
        if lo > cell.column or hi < cell.column + cell.column_span:
            return None
        if header.text.strip():
            selected.append(header)
    return tuple(sorted(selected, key=lambda c: (c.row, c.column)))


def _relation(
    value: CellRef,
    rows: tuple[CellRef, ...],
    columns: tuple[CellRef, ...],
    registry: dict[CellRef, TableCellFragment],
) -> ValueRelation:
    from app.services.table_context_service import row_unit_description, unit_description

    labels = (*rows, *columns)
    row_units = tuple(r for r in rows if row_unit_description(registry[r].text))
    return ValueRelation(
        value=value,
        row_headers=rows,
        column_headers=columns,
        unit_refs=row_units[-1:] or tuple(r for r in columns if any(
            unit_description(part[0]) for part in re.finditer(r"[（(][^()（）]+[)）]", registry[r].text))),
        period_refs=tuple(r for r in labels if _PERIOD.search(registry[r].text)),
        # A bound grid and empty parser text do not independently declare a
        # source blank. Preserve the literal, including an empty one.
        value_state="literal",
    )


@dataclass(slots=True)
class _FragmentBinding:
    records: list[SemanticRecord]
    consumed: set[CellRef]
    issues: list[tuple[int, str]]


def _record_refs(record: SemanticRecord) -> set[CellRef]:
    references: set[Any] = {*record.subject_headers, *record.row_groups}
    if record.subject:
        references.add(record.subject)
    for value in record.values:
        references.update((value.value, *value.row_headers, *value.column_headers,
                           *value.unit_refs, *value.period_refs, *value.note_refs))
    return {ref for ref in references if isinstance(ref, CellRef)}


def _consumed_cells(fragment: TableFragment, records: Sequence[SemanticRecord]) -> set[CellRef]:
    """Cover literal references and only their explicitly empty source anchors."""
    consumed = {ref for record in records for ref in _record_refs(record)
                if ref.table_id == fragment.fragment_id}
    group_rows = {ref.row for record in records for ref in record.row_groups
                  if ref.table_id == fragment.fragment_id}
    for record in records:
        subject = record.subject
        if (record.source_table_id == fragment.fragment_id and subject is not None
                and fragment.native_evidence.get("retained_row_context", {}).get(str(record.source_row))
                == [subject.row, subject.column]):
            group_rows.add(subject.row)
            consumed.update(_ref(fragment, c) for c in fragment.cells
                            if c.row == record.source_row and c.column == subject.column and not c.text.strip())
    consumed.update(_ref(fragment, c) for c in fragment.cells if c.row in group_rows and not c.text.strip())
    for scope in fragment.source_header_scopes:
        rows = scope.get("header_rows", [])
        if scope.get("complete") and any(ref.row in rows for ref in consumed):
            consumed.update(_ref(fragment, c) for c in fragment.cells if c.row in rows and not c.text.strip())
    consumed.update(_ref(fragment, cell) for cell in _unit_context_cells(fragment, records))
    return consumed


def _unit_context_cells(fragment: TableFragment, records: Sequence[SemanticRecord]) -> list[TableCellFragment]:
    from app.services.table_context_service import unit_header

    converted = {record.source_row for record in records if record.source_table_id == fragment.fragment_id}
    rows = {row for scope in fragment.source_header_scopes if scope.get("complete")
            and converted.intersection(scope.get("body_rows", [])) for row in scope.get("header_rows", [])}
    return [cell for cell in fragment.cells if cell.row in rows and cell.column == 0 and unit_header(cell.text)]


def _qualify_relation(fragment: TableFragment, relation: ValueRelation,
                      registry: dict[Any, Any]) -> ValueRelation:
    from app.services.table_context_service import scalar, unit_header
    cell = registry[relation.value]
    labels = [registry[r].text for r in relation.column_headers]
    reference_field = any(_REFERENCE_HEADER.fullmatch(text.strip().rstrip(":：")) for text in labels)
    amount_slot = not reference_field and (scalar(cell.text) or (
        not cell.text.strip() and any(_AMOUNT_HEADER.search(text) for text in labels)
    ))
    # A numeric note reference, index or code is not a monetary measurement,
    # even beneath a shared currency band. Its literal and column label stay.
    unit_refs = [] if reference_field else list(relation.unit_refs)
    period_refs = list(relation.period_refs)
    notes = []
    ratio = any(_RATIO_HEADER.search(text) for text in labels)
    own_unit = re.search(r"[%％‰]", cell.text)
    own_per_share = _per_share_currency([registry[r].text for r in relation.row_headers], cell.text)
    if ratio or own_unit:
        unit_refs = [ref for ref in unit_refs if re.search(r"[%％‰]", registry[ref].text)]
    if amount_slot and not own_unit and not own_per_share and not ratio and not unit_refs:
        active_headers = {r for scope in fragment.source_header_scopes if cell.row in scope.get("body_rows", [])
                          for r in scope.get("header_rows", [])}
        header_table = fragment.fragment_id
        inherited = (fragment.pdf_evidence.get("inherited_header_scope")
                     or fragment.native_evidence.get("inherited_header_scope", {}))
        if inherited.get("complete") and cell.row in inherited.get("body_rows", []):
            active_headers = set(inherited.get("header_rows", []))
            header_table = inherited.get("source_table_id", "")
        corner = next((ref for ref, c in registry.items()
                       if isinstance(ref, CellRef) and ref.table_id == header_table and ref.column == 0
                       and ref.row in active_headers and unit_header(c.text)), None)
        if corner is not None:
            unit_refs.append(corner)
    for ref in fragment.context_refs:
        if cell.row not in ref.body_rows or cell.column not in ref.columns:
            continue
        if ref.kind == "unit" and amount_slot and not own_unit and not own_per_share and not unit_refs and not ratio:
            unit_refs.append(ref)
        elif ref.kind == "period" and not period_refs:
            period_refs.append(ref)
        elif ref.kind == "note":
            marker = re.match(r"^\s*([0-9]{1,2}|[*†‡])(?:\s+|[.)、：:])", ref.text)
            if marker and any(re.search(r"(?:\^\s*\{?|<sup>)" + re.escape(marker[1]) + r"(?:\}|</sup>|\b)", registry[r].text)
                              for r in (relation.value, *relation.row_headers)):
                notes.append(ref)
    return replace(relation, unit_refs=tuple(unit_refs), period_refs=tuple(period_refs), note_refs=tuple(notes))


def _field_record(
    fragment: TableFragment,
    row: int,
    cells: Sequence[TableCellFragment],
    registry: dict[CellRef, TableCellFragment],
) -> SemanticRecord | None:
    # A field relation may be declared by independently bound source evidence.
    # Mere adjacency, a backend table label or equal glyphs never creates one.
    explicit = [scope for scope in fragment.pdf_evidence.get("field_scopes", [])
                if scope.get("complete") and row in scope.get("body_rows", [])]
    if len(explicit) != 1:
        return None
    pairs = []
    if explicit:
        evidence = explicit[0].get("evidence", {})
        if not (explicit[0].get("evidence_source") and (
            evidence.get("explicit_label_delimiters") or
            evidence.get("source_style_contrast") and (
                evidence.get("numeric_value_evidence") or evidence.get("explicit_field_label_type")
            )
        )):
            return None
        by_position = {(c.row, c.column): c for c in cells}
        claimed: set[tuple[int, int]] = set()
        for pair in explicit[0].get("pairs", []):
            label_pos, value_pos = tuple(pair.get("label", [])), tuple(pair.get("value", []))
            if (len(label_pos) != 2 or len(value_pos) != 2 or label_pos in claimed
                    or value_pos in claimed or label_pos == value_pos):
                return None
            label, value = by_position.get(label_pos), by_position.get(value_pos)
            if label is None or value is None:
                return None
            pairs.append((label, value))
            claimed.update((label_pos, value_pos))
        if claimed != set(by_position):
            return None
    if not pairs or any(not label.text.strip() or _NUMBER.fullmatch(_compact(label.text))
                        or label.row != row or value.row != row
                        or label.row_span != 1 or value.row_span != 1 for label, value in pairs):
        return None
    return SemanticRecord(fragment.fragment_id, row, tuple(
        _relation(_ref(fragment, value), (_ref(fragment, label),), (), registry)
        for label, value in pairs
    ))


def _bind_fragment(
    fragment: TableFragment,
    fragments: dict[str, TableFragment],
    registry: dict[CellRef, TableCellFragment],
) -> _FragmentBinding:
    source = _source_cells(fragment)
    if not source:
        return _FragmentBinding([], set(), [(r, "source_grid_not_completely_bound")
                                           for r in range(fragment.num_rows)])
    if fragment.pdf_evidence.get("content_kind") in {"layout", "layout_grid", "grid_prose"}:
        return _FragmentBinding([], set(), [(r, "layout_grid_not_semantic_table")
                                           for r in range(fragment.num_rows)])
    # Each row keeps its own scope and failure. Invalid later scopes do not
    # erase unrelated earlier records or authorize inherited headers.
    headers_by_row: dict[int, tuple[TableFragment, list[TableCellFragment], dict[str, Any]]] = {}
    blocked: dict[int, str] = {}
    header_rows: set[int] = set()
    for scope in fragment.source_header_scopes:
        if not scope.get("complete"):
            continue
        rows, body = scope.get("header_rows", []), scope.get("body_rows", [])
        valid = (isinstance(rows, list) and bool(rows)
                 and all(type(r) is int and 0 <= r < fragment.num_rows for r in rows)
                 and rows == list(range(rows[0], rows[-1] + 1)))
        if not valid:
            for row in body:
                if type(row) is int and 0 <= row < fragment.num_rows:
                    blocked[row] = "invalid_header_scope"
            continue
        headers = [c for c in fragment.cells if c.row in rows]
        header_rows.update(rows)
        if any(c.row + c.row_span > rows[-1] + 1 for c in headers):
            blocked.update((r, "header_span_crosses_body") for r in body)
            continue
        for row in body:
            if type(row) is not int or not rows[-1] < row < fragment.num_rows:
                if type(row) is int:
                    blocked[row] = "overlapping_header_scopes"
                continue
            if row in headers_by_row:
                blocked[row] = "overlapping_header_scopes"
                continue
            headers_by_row[row] = fragment, headers, scope

    inherited = (fragment.pdf_evidence.get("inherited_header_scope")
                 or fragment.native_evidence.get("inherited_header_scope", {}))
    inherited_source = fragments.get(inherited.get("source_table_id"))
    inherited_groups = inherited.get("source_column_groups", [])
    if inherited.get("complete") and inherited_source is not None:
        rows = inherited.get("header_rows", [])
        headers = [c for c in inherited_source.cells if c.row in rows]
        valid = (bool(_source_cells(inherited_source)) and bool(rows) and bool(headers)
                 and len(inherited_groups) == fragment.num_cols)
        for row in inherited.get("body_rows", []):
            if type(row) is not int or not 0 <= row < fragment.num_rows:
                continue
            if not valid:
                blocked[row] = "invalid_inherited_scope"
            elif row in headers_by_row:
                blocked[row] = "overlapping_inherited_scope"
            else:
                headers_by_row[row] = inherited_source, headers, inherited

    records: list[SemanticRecord] = []
    issues: list[tuple[int, str]] = []
    for row in range(fragment.num_rows):
        if row in header_rows:
            continue
        if row in blocked:
            issues.append((row, blocked[row]))
            continue
        if row in fragment.native_evidence.get("operation_rows", []):
            issues.append((row, "arithmetic_scope_boundary_unavailable"))
            continue
        cells = sorted((c for c in fragment.cells if c.row <= row < c.row + c.row_span),
                       key=lambda c: c.column)
        if not cells or cells[0].column != 0:
            issues.append((row, "row_not_completely_bound"))
            continue
        if row not in headers_by_row:
            field = _field_record(fragment, row, cells, registry)
            if field:
                records.append(field)
            else:
                issues.append((row, "unresolved_header_or_field_row"))
            continue
        origin, headers, scope = headers_by_row[row]
        native_scope = str(scope.get("evidence_source", "")).startswith("native_literal_")
        # Section headings with explicitly empty value bands are context, not
        # blank-valued facts. Keep them in the retained source region.
        if native_scope and all(not c.text.strip() for c in cells if c.column not in scope.get("row_header_columns", [0])):
            issues.append((row, "native_section_heading_retained"))
            continue
        if native_scope and not scope.get("evidence", {}).get("explicit_record_fields"):
            from app.services.table_context_service import scalar
            if not any(scalar(c.text) for c in cells if c.column not in scope.get("row_header_columns", [0])):
                issues.append((row, "native_nonrecord_region_retained"))
                continue

        def path_for(
            cell: TableCellFragment,
            source_table: TableFragment = origin,
            band: Sequence[TableCellFragment] = tuple(headers),
        ) -> tuple[TableCellFragment, ...] | None:
            if source_table is fragment:
                return _header_path(band, cell)
            paths = []
            for col in range(cell.column, cell.column + cell.column_span):
                group = inherited_groups[col]
                if not group or group != list(range(group[0], group[-1] + 1)):
                    return None
                path = _header_path(band, TableCellFragment(0, group[0], 1, len(group), ""))
                if path is None:
                    return None
                paths.append(path)
            return paths[0] if paths and all(p == paths[0] for p in paths) else None

        row_columns = scope.get("row_header_columns", [0])
        if origin is fragment and any(h.column == 0 and re.fullmatch(r"序号|序號|Index|No\.?", h.text.strip(), re.I) for h in headers):
            preferred = next((s.get("row_header_columns") for s in fragment.native_evidence.get("header_scopes", [])
                              if row in s.get("body_rows", [])), None)
            if isinstance(preferred, list) and len(preferred) == 1 and preferred != [0]:
                row_columns = preferred
        if (not isinstance(row_columns, list) or not row_columns
                or any(type(col) is not int or not 0 <= col < fragment.num_cols for col in row_columns)
                or row_columns != sorted(set(row_columns))
                or len(row_columns) >= fragment.num_cols):
            issues.append((row, "invalid_row_header_scope"))
            continue
        labels = [c for c in cells if set(range(c.column, c.column + c.column_span)).intersection(row_columns)]
        contextual_subject = False
        context = fragment.native_evidence.get("retained_row_context", {}).get(str(row))
        if (fragment.native_evidence.get("content_kind") == "data_table" and row_columns == [0]
                and len(labels) == 1 and not labels[0].text.strip()
                and labels[0].row == row and labels[0].row_span == labels[0].column_span == 1
                and isinstance(context, list) and len(context) == 2):
            parent = registry.get(CellRef(fragment.fragment_id, *context))
            if parent is not None and parent.row < row and parent.text.strip() and parent.column == 0:
                # The printed section owns these otherwise unnamed values.
                # Repeat its exact label without inventing Total/Subtotal,
                # calculating an answer or borrowing another table's name.
                labels = [parent]
                contextual_subject = True
        from app.services.table_context_service import identity_header
        summary_stub = (
            fragment.native_evidence.get("content_kind") == "data_table" and row_columns == [1]
            and len(labels) == 1 and labels[0].column == 0 and labels[0].column_span == 2
            and labels[0].row == row and labels[0].row_span == 1
            and bool(re.fullmatch(r"合计|合計|总计|總計|小计|小計|Total|Subtotal", labels[0].text.strip(), re.I))
            and any(h.column == 0 and h.column_span == 1
                    and re.fullmatch(r"序号|序號|Index|No\.?", h.text.strip(), re.I) for h in headers)
            and any(h.column == 1 and h.column_span == 1 and identity_header(h.text) for h in headers)
        )
        if summary_stub:
            # The printed total spans the ordinal and name fields, not a
            # measurement. It is a summary label, never a person's name.
            row_columns = [0, 1]
        if not contextual_subject and (not labels or any(not c.text.strip() for c in labels)
                or any(not set(range(c.column, c.column + c.column_span)).issubset(row_columns) for c in labels)
                or {col for c in labels for col in range(c.column, c.column + c.column_span)} != set(row_columns)):
            issues.append((row, "unresolved_row_subject"))
            continue
        subject, groups = labels[-1], labels[:-1]
        label_paths = [] if summary_stub or contextual_subject else [path_for(label) for label in labels]
        if any(path is None for path in label_paths):
            issues.append((row, "subject_crosses_header_columns"))
            continue
        subject_path = tuple({(h.row, h.column): h for path in label_paths if path for h in path}.values())
        from app.services.table_context_service import unit_header
        subject_path = tuple(h for h in subject_path if not unit_header(h.text))
        values = []
        paths_seen: set[tuple[CellRef, ...]] = set()
        reason = None
        from app.services.table_context_service import unit_description
        field_paths = {(c.row, c.column): path_for(c) for c in cells if c not in labels}
        path_counts: dict[tuple[str, ...], int] = {}
        for candidate_path in field_paths.values():
            if candidate_path:
                key = tuple(h.text.strip() for h in candidate_path if not unit_description(h.text))
                path_counts[key] = path_counts.get(key, 0) + 1
        for cell in cells:
            if cell in labels or contextual_subject and cell.column in row_columns:
                continue
            if (cell.row != row or cell.row_span != 1) and not native_scope:
                reason = "value_span_crosses_records"
                break
            path = field_paths[(cell.row, cell.column)]
            if not path:
                reason = "incomplete_column_header_path"
                break
            from app.services.table_context_service import scalar, unit_description
            unit_headers = tuple(_ref(origin, h) for h in path if unit_description(h.text))
            header_labels = tuple(_ref(origin, h) for h in path if not unit_description(h.text))
            refs = header_labels or tuple(_ref(origin, h) for h in path)
            key = tuple(h.text.strip() for h in path if not unit_description(h.text))
            if unit_headers and path_counts[key] > 1:
                # A unit/currency band can distinguish columns sharing a year,
                # even for ratio rows. Preserve that column identity without
                # assigning an amount unit to the ratio itself.
                refs = tuple(_ref(origin, h) for h in path)
            if refs in paths_seen:
                reason = "ambiguous_duplicate_leaf_headers"
                break
            paths_seen.add(refs)
            relation = _relation(_ref(fragment, cell), tuple(_ref(fragment, label) for label in labels), refs, registry)
            ratio = bool(re.search(r"[%％‰]", cell.text) or any(
                _RATIO_HEADER.search(registry[r].text) for r in refs))
            if ratio:
                amount_units = {ref for ref in unit_headers if not re.search(r"[%％‰]", registry[ref].text)}
                relation = replace(relation, unit_refs=tuple(ref for ref in relation.unit_refs if ref not in amount_units))
            if (unit_headers and not relation.unit_refs and scalar(cell.text) and not re.search(r"[%％‰]", cell.text)
                    and not any(_RATIO_HEADER.search(registry[r].text) for r in refs)):
                relation = replace(relation, unit_refs=tuple(dict.fromkeys((*relation.unit_refs, *unit_headers))))
            values.append(_qualify_relation(fragment, relation, registry))
        if reason or not values:
            issues.append((row, reason or "unresolved_row_subject"))
            continue
        extra_group = fragment.native_evidence.get("row_groups", {}).get(str(row))
        row_groups = tuple(_ref(fragment, group) for group in groups)
        if extra_group:
            extra_ref = CellRef(fragment.fragment_id, *extra_group)
            row_groups = tuple(dict.fromkeys((extra_ref, *row_groups)))
            values = [replace(value, row_headers=tuple(dict.fromkeys((extra_ref, *value.row_headers)))) for value in values]
        records.append(SemanticRecord(
            fragment.fragment_id, row, tuple(values), _ref(fragment, subject),
            tuple(_ref(origin, h) for h in subject_path),
            row_groups,
            tuple(ref for ref in fragment.context_refs if ref.kind == "title"),
        ))
    # Do not cut a shared source cell across converted and retained rows. This
    # includes shared labels: unresolved rows must retain their real context.
    while True:
        converted_rows = {record.source_row for record in records}
        unsafe = set()
        for cell in fragment.cells:
            if cell.row_span > 1 and cell.row not in header_rows:
                span = set(range(cell.row, cell.row + cell.row_span))
                if span & converted_rows and span - converted_rows:
                    unsafe.update(span & converted_rows)
        if not unsafe:
            break
        records = [record for record in records if record.source_row not in unsafe]
        issues.extend((r, "row_span_crosses_unresolved_region") for r in sorted(unsafe))
    consumed = _consumed_cells(fragment, records)
    return _FragmentBinding(records, consumed, issues)


def bind_table_view(
    view_id: str,
    group: Sequence[TableFragment],
    all_fragments: Sequence[TableFragment],
) -> SemanticTableView:
    """Bind supported rows and retain every unresolved source region."""
    ids = tuple(f.fragment_id for f in group)
    count = sum(len(f.cells) for f in group)
    sources = {f.fragment_id: f for f in all_fragments}
    if (not group or not _ID.fullmatch(view_id) or any(not _ID.fullmatch(i) for i in ids)
            or len(sources) != len(all_fragments) or len(set(ids)) != len(ids)):
        return SemanticTableView(view_id, ids, "retained", "unknown",
                                 reason_codes=("invalid_table_identity",), source_cell_count=count)
    registry = _registry(all_fragments)
    records: list[SemanticRecord] = []
    covered: set[CellRef] = set()
    issues: list[tuple[str, int, str]] = []
    for fragment in group:
        bound = _bind_fragment(fragment, sources, registry)
        records.extend(bound.records)
        covered.update(bound.consumed)
        issues.extend((fragment.fragment_id, row, reason) for row, reason in bound.issues)
    expected = {_ref(f, c) for f in group for c in f.cells}
    reasons = tuple(dict.fromkeys(reason for _, _, reason in issues))
    header_positions = {
        (fragment.fragment_id, row) for fragment in group
        for scope in fragment.source_header_scopes if scope.get("complete")
        for row in scope.get("header_rows", []) if type(row) is int
    }
    header_positions.update((f.fragment_id, int(position[0])) for f in group
                            for position in f.native_evidence.get("row_groups", {}).values())
    header_positions.update((f.fragment_id, int(position[0])) for f in group
                            for position in f.native_evidence.get("retained_row_context", {}).values())
    while True:
        missing = expected - covered
        retained_rows = {(ref.table_id, row) for ref in missing
                         for row in range(ref.row, ref.row + registry[ref].row_span)}
        # Labels from a source header may recur as context. No data, subject,
        # group or qualifier cell can be rendered in both a record and grid.
        unsafe = {
            (record.source_table_id, record.source_row) for record in records
            if any((ref.table_id, ref.row) not in header_positions
                   and any((ref.table_id, row) in retained_rows for row in range(
                       ref.row, ref.row + registry[ref].row_span))
                   for ref in _record_refs(record) if ref in expected)
        }
        if not unsafe:
            break
        records = [record for record in records
                   if (record.source_table_id, record.source_row) not in unsafe]
        covered = {ref for fragment in group for ref in _consumed_cells(fragment, records) if ref in expected}
        issues.extend((identity, row, "shared_reference_crosses_unresolved_region")
                      for identity, row in sorted(unsafe))
        reasons = tuple(dict.fromkeys((*reasons, "incomplete_source_cell_coverage")))
    if missing and not reasons:
        reasons = ("incomplete_source_cell_coverage",)
    if not records:
        return SemanticTableView(
            view_id, ids, "retained", "unknown", reason_codes=reasons,
            source_cell_count=count, retained_cells=tuple(sorted(expected)),
            retained_rows=tuple((f.fragment_id, r) for f in group for r in range(f.num_rows)),
            row_issues=tuple(issues),
        )
    fields = any(r.subject is None for r in records)
    tabular = any(r.subject is not None for r in records)
    numeric = any(_NUMBER.fullmatch(_compact(registry[v.value].text))
                  for r in records for v in r.values)
    kind: SemanticKind = ("mixed" if fields and tabular else "fields" if fields
                          else "comparison" if numeric else "records")
    return SemanticTableView(
        view_id, ids, "partial" if missing else "converted", kind, tuple(records),
        reason_codes=reasons, source_cell_count=count, covered_source_cells=len(covered),
        retained_cells=tuple(sorted(missing)), retained_rows=tuple(sorted(retained_rows)),
        row_issues=tuple(issues),
    )


def retained_table_parts(
    view: SemanticTableView, fragments: Sequence[TableFragment]
) -> list[dict[str, Any]]:
    """Render residual source rows with exact display-to-source coordinates.

    A synthetic all-empty display header has no source identity. Existing
    header labels may be repeated as context; converted data rows never are.
    """
    retained = set(view.retained_rows)
    parts: list[dict[str, Any]] = []
    for fragment in fragments:
        if fragment.fragment_id not in view.source_tables:
            continue
        rows = sorted(row for identity, row in retained if identity == fragment.fragment_id)
        if not rows:
            continue
        chunks: list[list[int]] = []
        for row in rows:
            if not chunks or row != chunks[-1][-1] + 1:
                chunks.append([row])
            else:
                chunks[-1].append(row)
        for index, chunk in enumerate(chunks):
            context = set()
            for scope in fragment.source_header_scopes:
                headers = scope.get("header_rows", [])
                if (scope.get("complete") and headers
                        and all(type(row) is int and 0 <= row < len(fragment.rows) for row in headers)
                        and headers == list(range(headers[0], headers[-1] + 1))
                        and set(chunk).intersection(scope.get("body_rows", []))):
                    context.update(headers)
            row_context = {
                declaration[0]
                for row in chunk
                if (declaration := fragment.native_evidence.get("retained_row_context", {}).get(str(row)))
                and len(declaration) == 2 and type(declaration[0]) is int
            }
            selected = sorted(context | row_context | set(chunk))
            if any(type(row) is not int or not 0 <= row < len(fragment.rows) for row in selected):
                raise ValueError("retained source row is unavailable")
            display = {row: i + 1 for i, row in enumerate(selected)}
            spans = []
            for cell in fragment.cells:
                if cell.row not in display:
                    continue
                covered = list(range(cell.row, cell.row + cell.row_span))
                if any(row not in display for row in covered):
                    raise ValueError("retained table cuts a source rowspan")
                if [display[r] for r in covered] != list(range(display[cell.row], display[cell.row] + cell.row_span)):
                    raise ValueError("retained table compresses a source rowspan")
                if cell.row_span > 1 or cell.column_span > 1:
                    spans.append([display[cell.row], cell.column, cell.row_span, cell.column_span])
            metadata = {
                "table_id": fragment.fragment_id, "part_index": index,
                "source_rows": selected, "header_rows": sorted(context),
                "context_rows": sorted(row_context),
                "synthetic_header_rows": [0], "source_to_display_rows": display,
                "spans": spans, "start_row": chunk[0],
            }
            marker = "<!-- semantic-retained: " + json.dumps(metadata, separators=(",", ":")) + " -->"
            rendered = marker + "\n\n" + render_source_rows(
                [[""] * fragment.num_cols, *[fragment.rows[row] for row in selected]], spans,
            )
            parts.append({**metadata, "rendered": rendered})
    return parts


def _render_record(record: SemanticRecord, registry: dict[Any, Any]) -> str:
    references = _record_refs(record)
    if any(ref not in registry for ref in references):
        raise ValueError("semantic source reference is absent")
    refs: set[Any] = {v.value for v in record.values}
    header_refs: set[CellRef] = set(record.subject_headers)
    if record.subject:
        refs.add(record.subject)
    refs.update(record.row_groups)
    for value in record.values:
        refs.update(value.row_headers)
        refs.update((*value.unit_refs, *value.period_refs, *value.note_refs))
        header_refs.update(value.column_headers)
    source = ",".join(ref.token for ref in sorted(r for r in refs if isinstance(r, CellRef)))
    headers = ",".join(ref.token for ref in sorted(header_refs))
    marker = f"<!-- semantic-source: cells={source}; headers={headers} -->"
    def literal(ref: Any) -> str:
        return _record_literal(record, ref, registry)

    parts = ["范围：" + " / ".join(_literal(ref.text) for ref in record.scope_refs)] if record.scope_refs else []
    if record.subject:
        subject = " / ".join(literal(ref)
                             for ref in (*record.row_groups, record.subject))
        label = " / ".join(literal(r) for r in dict.fromkeys(record.subject_headers))
        parts.append(f"{label}{_label_separator(label)}{subject}" if label else subject)
    for value in record.values:
        label_refs = value.column_headers if record.subject else value.row_headers
        label_refs = tuple(dict.fromkeys(label_refs))
        label = " / ".join("".join(_column_literal_parts(record, value, r, registry))
                           if record.subject else literal(r) for r in label_refs)
        text = _literal(registry[value.value].text)
        if value.value_state == "source_blank":
            if text:
                raise ValueError("source-blank relation conflicts with a nonempty literal")
            text = "（原表留空）"
        elif value.value_state != "literal":
            raise ValueError("unsupported semantic value state")
        part = f"{label}{_label_separator(label)}{text}"
        emitted: set[Any] = {value.value, *label_refs, *record.subject_headers, *record.row_groups}
        if record.subject:
            emitted.add(record.subject)
        qualifiers = []
        for qualifier, qualifier_refs in (("单位", value.unit_refs), ("期间", value.period_refs),
                                           ("附注", value.note_refs)):
            pending = []
            for reference in qualifier_refs:
                if reference not in emitted:
                    pending.append(_literal(registry[reference].text))
                    emitted.add(reference)
            if pending:
                qualifiers.append(f"{qualifier}：" + " / ".join(pending))
        if qualifiers:
            part += "（" + "；".join(qualifiers) + "）"
        parts.append(part)
    return marker + "\n\n- " + "；".join(parts) + "。"


def render_semantic_view(view: SemanticTableView, fragments: Sequence[TableFragment]) -> str:
    """Render supported relations and exact remaining rows in source order."""
    marker = (f"<!-- semantic-view: id={view.view_id}; "
              f"source-tables={','.join(view.source_tables)}; status={view.status} -->")
    if view.status == "retained":
        return marker
    registry = _registry(fragments)
    counts: dict[CellRef, int] = {}
    for fragment in fragments:
        for cell in fragment.cells:
            ref = _ref(fragment, cell)
            counts[ref] = counts.get(ref, 0) + 1
    if any(counts.get(ref, 0) > 1 for record in view.records for ref in _record_refs(record)):
        raise ValueError("semantic source reference is ambiguous")
    sequence = {identity: index for index, identity in enumerate(view.source_tables)}
    output = [((sequence[record.source_table_id], record.source_row, 1),
               _render_record(record, registry)) for record in view.records]
    for fragment in fragments:
        if fragment.fragment_id not in sequence:
            continue
        for cell in _unit_context_cells(fragment, view.records):
            ref = _ref(fragment, cell)
            output.append(((sequence[fragment.fragment_id], cell.row, 0),
                           f"<!-- semantic-source: cells={ref.token}; headers={ref.token} -->\n\n{_literal(cell.text)}"))
    if view.status == "partial":
        output.extend(((sequence[part["table_id"]], part["start_row"], 0), part["rendered"])
                      for part in retained_table_parts(view, fragments))
    return "\n\n".join([marker, *[text for _, text in sorted(output, key=lambda item: item[0])]])


class TableSemanticsService:
    async def apply(
        self,
        result: DocumentParseResult,
        options: ContentParseOptions,
        *,
        cancel_event: Any = None,
    ) -> None:
        worker = asyncio.create_task(
            asyncio.to_thread(self._apply_owned, result, options, cancel_event)
        )
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except BaseException:
                    break
            if not worker.cancelled():
                worker.exception()
            raise

    @staticmethod
    def _apply_owned(
        result: DocumentParseResult, options: ContentParseOptions, cancel_event: Any
    ) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ParserCancelledError("table semantic rendering cancelled")
        remaining_timeout(options)
        if result._semantic_tables:
            return
        if result.parse_result is None:
            raise ValueError("semantic rendering requires the preserved source IR")
        fragments = [f for f in result._table_fragments if isinstance(f, TableFragment)]
        from app.services.table_context_service import prepare_native_table_scopes
        prepare_native_table_scopes(result)
        markdown = result.parse_result.renderings.markdown
        result._source_markdown = markdown
        rendered_views = []
        for source_view in result._table_views:
            if cancel_event is not None and cancel_event.is_set():
                raise ParserCancelledError("table semantic rendering cancelled")
            remaining_timeout(options)
            if not isinstance(source_view, TableSourceView):
                continue
            view = bind_table_view(source_view.view_id, source_view.fragments, fragments)
            # Only replace an exact source-owned span. Rich unknown neighbors
            # and asset substitutions must never be inferred from a regex.
            body = source_view.rendered
            for material in (source_view.prefix, source_view.suffix):
                if material:
                    body = body.replace(material, "", 1)
            body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
            # Accept only the exact producer projection. Unknown HTML neighbors
            # and repeated public occurrences must retain their existing bytes.
            if len(source_view.fragments) == 1:
                _, owned_grid = table_view(source_view.fragments[0])
                if owned_grid.startswith("<table>") and body.strip() == owned_grid:
                    body = ""
            body = "\n".join(line for line in body.splitlines() if not line.strip().startswith("|"))
            unique = markdown.count(source_view.rendered) == 1
            if view.status in {"converted", "partial"} and (body.strip() or not unique):
                view = SemanticTableView(
                    view.view_id,
                    view.source_tables,
                    "retained",
                    "unknown",
                    reason_codes=("public_view_not_uniquely_owned",),
                    source_cell_count=view.source_cell_count,
                )
            if not unique:
                rendered_views.append(view)
                continue
            try:
                rendered = render_semantic_view(view, fragments)
            except (KeyError, ValueError, IndexError, TypeError):
                view = replace(
                    view, status="retained", kind="unknown", records=(),
                    reason_codes=tuple(dict.fromkeys((*view.reason_codes, "semantic_projection_unavailable"))),
                    covered_source_cells=0,
                )
                rendered = render_semantic_view(view, fragments)
            rendered_views.append(view)
            if view.status in {"converted", "partial"}:
                replacement = "\n\n".join(
                    p for p in (source_view.prefix, rendered, source_view.suffix) if p
                )
            else:
                replacement = source_view.rendered + "\n\n" + rendered
            markdown = markdown.replace(source_view.rendered, replacement, 1)
        owned = {source for view in rendered_views for source in view.source_tables}
        for fragment in fragments:
            if fragment.fragment_id not in owned:
                rendered_views.append(
                    SemanticTableView(
                        fragment.fragment_id,
                        (fragment.fragment_id,),
                        "retained",
                        "unknown",
                        reason_codes=("source_view_unavailable",),
                        source_cell_count=len(fragment.cells),
                    )
                )
        if fragments:
            converted = {
                source
                for view in rendered_views
                if view.status == "converted"
                for source in view.source_tables
            }
            partial = {
                source for view in rendered_views if view.status == "partial"
                for source in view.source_tables
            }
            retained = {f.fragment_id for f in fragments} - converted - partial
            markdown += (
                f"\n\n<!-- semantic-summary: converted={len(converted)}; "
                f"partial={len(partial)}; retained={len(retained)} -->"
            )
        result._semantic_tables = rendered_views
        result.parse_result.renderings.markdown = markdown
        result.parse_result.renderings.plain_text = ExportService.markdown_to_text(
            markdown, source_regions=result._source_regions
        )
