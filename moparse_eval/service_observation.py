"""Read actual MO-Parse final Markdown and its explicit output-owned evidence.

No reference material, source PDF, parser inference or final-answer repair is
available here. Internal cells locate evidence only after its final rendering
is uniquely present; an unrendered IR cell is never a candidate answer.
"""

from __future__ import annotations

import copy
import json
import re
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from typing import Any

from markdown_it import MarkdownIt

from app.models.parse_result import DocumentParseResult
from app.models.table_semantics import CellRef, SemanticRecord, SemanticTableView, TextRef
from app.services.table_semantics_service import (
    _label_separator,
    _literal,
    render_semantic_view,
    retained_table_parts,
)
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    TableSourceView,
    _escape_cell,
)

from .adapters import markdown_cells
from .information_reading import unit_scope_literal
from .native_relations import native_relations
from .representations import visible_text

SERVICE_OBSERVATION_VERSION = "mo-parse-final-output-observation-v7"
FINAL_PAGE_PROVENANCE_VERSION = "mo-parse-final-page-provenance-v1"
FINAL_OBSERVATION_READBACK_VERSION = "mo-parse-final-output-readback-v7"
_METADATA_KEYS = {"run_id", "suite", "phase", "repetition", "timing", "resources", "runtime"}
_IDENTITY_HEADER = re.compile(
    r"(?:名称|名稱|姓名|项目|項目|认购方|認購方|认购对象|認購對象|"
    r"Name|Item|Project|Subscriber|Investor)", re.I,
)


def _printed_unit_scope(text: str) -> bool:
    """An explicit currency-unit caption is a unit, not a business title."""
    return unit_scope_literal(text) or bool(re.fullmatch(
        r"\s*[（(]?\s*(?:货币|貨幣)(?:单位|單位)\s*[:：]\s*[^()（）:：；;]+\s*[)）]?\s*",
        text,
    ))


def _physical_lines(text: str) -> list[str]:
    """Match CommonMark line endings, retaining raw CRLF character offsets."""
    lines = []
    start = 0
    for match in re.finditer(r"\r\n|\r|\n", text):
        lines.append(text[start : match.end()])
        start = match.end()
    if start < len(text):
        lines.append(text[start:])
    return lines


def _inline_text(markdown: str) -> str:
    """Project a declared inline field without reinterpreting block syntax."""

    def read(tokens: Sequence[Any]) -> str:
        pieces = []
        for token in tokens:
            if token.type in {"text", "code_inline"}:
                pieces.append(token.content)
            elif token.type in {"softbreak", "hardbreak"}:
                pieces.append("\n")
            elif token.type == "html_inline":
                pieces.append(visible_text(token.content, "html"))
            elif token.children and token.type != "image":
                pieces.append(read(token.children))
        return "".join(pieces)

    return read(MarkdownIt("commonmark").parseInline(markdown))


def _spans(markdown: str) -> list[tuple[int, int, Any]]:
    offsets = [0]
    for line in _physical_lines(markdown):
        offsets.append(offsets[-1] + len(line))
    result = []
    for token in MarkdownIt("commonmark").enable("table").parse(markdown):
        if token.level == 0 and token.map is not None and token.nesting >= 0:
            start, end = token.map
            result.append((offsets[start], offsets[end], token))
    return result


def _ref_dict(ref: CellRef | TextRef) -> dict[str, Any]:
    if isinstance(ref, TextRef):
        return {"table_id": ref.table_id, "block_id": ref.block_id, "page": ref.page,
                "text_span": [ref.start, ref.end], "scope_rows": list(ref.body_rows),
                "scope_columns": list(ref.columns), "token": ref.token}
    return {"table_id": ref.table_id, "row": ref.row, "column": ref.column, "token": ref.token}


def _record_parts(
    record: SemanticRecord, registry: Mapping[Any, Any]
) -> tuple[str, list[dict[str, Any]]]:
    """Describe the current renderer template, checked against its real output."""
    pieces = ["- "]
    cells: list[dict[str, Any]] = []

    def literal(ref: CellRef | TextRef, role: str, field: int | None = None, blank: bool = False) -> None:
        raw = "（原表留空）" if blank else _literal(registry[ref].text)
        start = sum(map(len, pieces))
        pieces.append(raw)
        cells.append(
            {
                "ref": ref,
                "role": role,
                "field_index": field,
                "span": [start, start + len(raw)],
                "text": "" if blank else _inline_text(raw),
                "value_state": "source_blank" if blank else "literal",
            }
        )

    def labels(refs: Sequence[Any], role: str) -> tuple[Any, ...]:
        unique = tuple(dict.fromkeys(refs))
        for index, ref in enumerate(unique):
            if index:
                pieces.append(" / ")
            literal(ref, role)
        return unique

    if record.scope_refs:
        pieces.append("范围：")
        labels(record.scope_refs, "scope")
        pieces.append("；")
    if record.subject is not None:
        subject_headers = labels(record.subject_headers, "column_header")
        if record.subject_headers:
            pieces.append(_label_separator(" / ".join(_literal(registry[ref].text) for ref in subject_headers)))
        for group in record.row_groups:
            literal(group, "row_header")
            pieces.append(" / ")
        literal(record.subject, "row_header")
    for index, value in enumerate(record.values):
        if index or record.subject is not None:
            pieces.append("；")
        refs = labels(
            value.column_headers if record.subject else value.row_headers,
            "column_header" if record.subject else "row_header",
        )
        pieces.append(_label_separator(" / ".join(_literal(registry[ref].text) for ref in refs)))
        literal(value.value, "value", index, value.value_state == "source_blank")
        emitted = {value.value, *refs, *record.subject_headers, *record.row_groups}
        if record.subject:
            emitted.add(record.subject)
        qualifiers = []
        for name, role, references in (
            ("单位", "unit", value.unit_refs),
            ("期间", "period", value.period_refs),
            ("附注", "note", value.note_refs),
        ):
            pending = tuple(ref for ref in dict.fromkeys(references) if ref not in emitted)
            emitted.update(pending)
            if pending:
                qualifiers.append((name, role, pending))
        if qualifiers:
            pieces.append("（")
            for qualifier_index, (name, role, references) in enumerate(qualifiers):
                if qualifier_index:
                    pieces.append("；")
                pieces.append(name + "：")
                labels(references, role)
            pieces.append("）")
    pieces.append("。")
    return "".join(pieces), cells


def _cell_registry(
    fragments: Sequence[TableFragment],
) -> tuple[dict[Any, Any], dict[str, int], list[dict[str, Any]]]:
    registry: dict[Any, Any] = {}
    pages = {}
    ambiguous = set()
    for fragment in fragments:
        if fragment.fragment_id in pages:
            ambiguous.add(fragment.fragment_id)
        pages[fragment.fragment_id] = fragment.page_number
        for cell in fragment.cells:
            ref = CellRef(fragment.fragment_id, cell.row, cell.column)
            if ref in registry:
                ambiguous.add(fragment.fragment_id)
            registry[ref] = cell
        for context_ref in fragment.context_refs:
            registry[context_ref] = context_ref
    return (
        {ref: cell for ref, cell in registry.items() if ref.table_id not in ambiguous},
        {identity: page for identity, page in pages.items() if identity not in ambiguous},
        [
            {
                "category": "service_output_readback",
                "reason": "ambiguous_source_table_or_cell_identity",
                "table_id": identity,
            }
            for identity in sorted(ambiguous)
        ],
    )


def _semantic_blocks(
    view: SemanticTableView,
    final: str,
    fragments: Sequence[TableFragment],
    registry: Mapping[CellRef, TableCellFragment],
    source_pages: Mapping[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    state: dict[str, Any] = {
        "view_id": view.view_id,
        "status": view.status,
        "kind": view.kind,
        "reason_codes": list(view.reason_codes),
        "source_tables": list(view.source_tables),
        "source_cell_count": view.source_cell_count,
        "covered_source_cells": view.covered_source_cells,
        "final_evidence": "unknown",
        "records": [],
    }
    if view.status not in {"converted", "partial"}:
        return [], state
    try:
        rendered = render_semantic_view(view, fragments)
    except (KeyError, ValueError) as exc:
        state.update(reason="semantic_rendering_unavailable", error=str(exc))
        return [], state
    if final.count(rendered) != 1:
        state["reason"] = "semantic_rendering_not_uniquely_present"
        return [], state
    start = final.index(rendered)
    state.update(final_evidence=view.status, final_markdown_span=[start, start + len(rendered)])
    blocks = []
    cursor = start
    for index, record in enumerate(view.records):
        try:
            line, emitted = _record_parts(record, registry)
        except KeyError:
            state["records"].append(
                {
                    "index": index,
                    "status": "unknown",
                    "reason": "semantic_cell_reference_unavailable",
                }
            )
            continue
        # The template is diagnostic only: the exact official rendered record
        # must be present in order within the actual output-owned view.
        location = final.find(line, cursor, start + len(rendered))
        if location < 0:
            state["records"].append(
                {"index": index, "status": "unknown", "reason": "record_template_not_present"}
            )
            continue
        cursor = location + len(line)
        block_id = f"service:semantic:{view.view_id}:record:{index}"
        cells = []
        emitted_by_ref = {item["ref"]: item["text"] for item in emitted}
        # Alternate identity fields are named properties printed in this same
        # record. Never use an arbitrary note, an expected label or a hidden IR
        # value as an alias, and preserve every printed business parent.
        groups = [emitted_by_ref[ref] for ref in record.row_groups if ref in emitted_by_ref]
        aliases = []
        if len(groups) == len(record.row_groups):
            for value in record.values:
                if (value.value in emitted_by_ref and len(value.column_headers) == 1
                        and value.column_headers[0] in emitted_by_ref
                        and _IDENTITY_HEADER.fullmatch(emitted_by_ref[value.column_headers[0]].strip())
                        and emitted_by_ref[value.value].strip()):
                    aliases.append([*groups, emitted_by_ref[value.value]])
        for cell_index, item in enumerate(emitted):
            ref = item["ref"]
            a, b = item["span"]
            absolute = [location + a, location + b]
            cell = {
                "id": f"{block_id}:cell:{cell_index}",
                "native_path": f"#/markdown/{absolute[0]}:{absolute[1]}",
                "text": item["text"],
                "text_format": "plain",
                "final_markdown_span": absolute,
                "source_cell_ref": _ref_dict(ref),
                "record_id": block_id,
                "value_state": item["value_state"],
                "page": source_pages.get(ref.table_id),
                "service_evidence_state": "converted",
            }
            if item["role"] == "row_header":
                cell["is_row_header"] = True
                if (aliases and ref == record.subject and record.subject_headers
                        and all(header in emitted_by_ref for header in record.subject_headers)
                        and len(groups) == len(record.row_groups)):
                    cell["column_header_path"] = [emitted_by_ref[header] for header in record.subject_headers]
                    cell["row_header_path"] = [*groups, item["text"]]
            elif item["role"] == "column_header":
                cell["is_column_header"] = True
            if item["field_index"] is not None:
                value = record.values[item["field_index"]]
                for name, refs in (
                    ("row_header_path", value.row_headers),
                    ("column_header_path", value.column_headers),
                ):
                    if refs and all(ref in emitted_by_ref for ref in refs):
                        cell[name] = [emitted_by_ref[ref] for ref in refs]
                for name, refs in (
                    ("unit", value.unit_refs),
                    ("period", value.period_refs),
                    ("note", value.note_refs),
                ):
                    if refs and all(ref in emitted_by_ref for ref in refs):
                        values = [emitted_by_ref[ref] for ref in dict.fromkeys(refs)]
                        cell[name + "s"] = values
                        cell[name + "_refs"] = [_ref_dict(ref) for ref in refs]
                        # A qualifier-bearing label is still a whole header,
                        # e.g. "Revenue (EUR)", not an explicit unit="Revenue
                        # (EUR)" field. Let the common scorer read the actual
                        # located header. Dedicated qualifier text remains an
                        # explicit field and cannot be rescued by another label.
                        header_refs = {*value.row_headers, *value.column_headers}
                        if (len(values) == 1 and name != "note" and not header_refs.intersection(refs)
                                and all(isinstance(ref, CellRef) for ref in refs)
                                and (name != "unit" or not re.search(r"[\s()（）:：]", values[0]))):
                            cell[name] = values[0]
                # These literals are visibly printed in this very record,
                # including source legends rendered as a record title. They
                # are context, never new unit strings inferred from a value.
                printed_scope = [emitted_by_ref[ref] for ref in (*record.subject_headers, *record.scope_refs)
                                 if ref in emitted_by_ref and _printed_unit_scope(emitted_by_ref[ref])]
                if printed_scope:
                    cell["units"] = list(dict.fromkeys([*cell.get("units", []), *printed_scope]))
            if aliases and (item["field_index"] is not None or ref == record.subject):
                cell["printed_record_row_paths"] = aliases
            cells.append(cell)
        pages = sorted(
            {source_pages[ref.table_id] for ref in emitted_by_ref if ref.table_id in source_pages}
        )
        explicit_edges = []
        for value in record.values:
            targets = [
                cell
                for cell in cells
                if cell["source_cell_ref"]["token"] == value.value.token
                and not cell.get("is_row_header")
                and not cell.get("is_column_header")
            ]
            for label in value.row_headers:
                origins = [
                    cell for cell in cells if cell["source_cell_ref"]["token"] == label.token
                ]
                for origin in origins:
                    for target in targets:
                        explicit_edges.append(
                            {
                                "type": "label_value",
                                "source": origin["id"],
                                "target": target["id"],
                                "evidence": "final_rendered_semantic_cellrefs",
                            }
                        )
        blocks.append(
            {
                "id": block_id,
                "kind": "table_body",
                "text": final[location:cursor],
                "text_format": "markdown",
                "cells": cells,
                "parent_id": f"service:table:{view.view_id}",
                "native_table_container": f"service:table:{view.view_id}",
                "native_path": f"#/markdown/{location}:{cursor}",
                "final_markdown_span": [location, cursor],
                "provenance_pages": pages,
                "service_evidence_state": "converted",
                "service_relations": explicit_edges,
            }
        )
        state["records"].append(
            {"index": index, "status": "converted", "final_markdown_span": [location, cursor]}
        )
    if any(record["status"] == "unknown" for record in state["records"]):
        state["final_evidence"] = "partial" if blocks else "unknown"
    return blocks, state


def _partial_grid_blocks(
    view: SemanticTableView, final: str, fragments: Sequence[TableFragment],
    registry: Mapping[CellRef, TableCellFragment], source_pages: Mapping[str, int],
) -> list[dict[str, Any]]:
    """Read only explicitly mapped residual grids actually emitted by a partial view."""
    if view.status != "partial":
        return []
    blocks = []
    for part in retained_table_parts(view, fragments):
        rendered = part["rendered"]
        if final.count(rendered) != 1:
            raise ValueError("partial residual rendering is not uniquely present")
        base = final.index(rendered)
        display_to_source = {display: row for row, display in part["source_to_display_rows"].items()}
        for start, end, token in _spans(rendered):
            if token.type != "table_open":
                continue
            raw = rendered[start:end].rstrip("\r\n")
            absolute = base + start
            lines = _physical_lines(raw)
            offsets = [0]
            for line in lines:
                offsets.append(offsets[-1] + len(line))
            cells = []
            for cell in markdown_cells(raw, f"#/markdown/{absolute}:{absolute + len(raw)}"):
                display = cell["row"]
                if display in part["synthetic_header_rows"]:
                    continue
                row = display_to_source.get(display)
                if row is None:
                    raise ValueError("partial display row has no declared source coordinate")
                line_index = display + int(display > 0)
                line = lines[line_index]
                delimiters = [m.start() for m in re.finditer(r"\|", line)]
                col = cell["col"]
                if len(delimiters) <= col + 1:
                    raise ValueError("partial cell has no final character range")
                a, b = delimiters[col] + 1, delimiters[col + 1]
                a += len(line[a:b]) - len(line[a:b].lstrip())
                b -= len(line[a:b]) - len(line[a:b].rstrip())
                cell.update(row=row, text=_inline_text(line[a:b]),
                            final_markdown_span=[absolute + offsets[line_index] + a,
                                                 absolute + offsets[line_index] + b],
                            service_evidence_state="retained")
                cell.pop("is_column_header", None)
                ref = CellRef(part["table_id"], row, col)
                source = registry.get(ref)
                if source is not None and _inline_text(_escape_cell(source.text)) == cell["text"]:
                    cell.update(source_cell_ref=_ref_dict(ref), page=source_pages.get(ref.table_id),
                                is_column_header=source.is_column_header or row in part["header_rows"],
                                is_row_header=source.is_row_header)
                cells.append(cell)
            for display_row, col, row_span, col_span in part["spans"]:
                row = display_to_source[display_row]
                anchor = next((cell for cell in cells if (cell["row"], cell["col"]) == (row, col)), None)
                covered = [cell for cell in cells
                           if row <= cell["row"] < row + row_span
                           and col <= cell["col"] < col + col_span and cell is not anchor]
                if anchor is not None and all(not cell["text"] for cell in covered):
                    anchor.update(row_span=row_span, col_span=col_span)
                    cells = [cell for cell in cells if cell not in covered]
            if cells:
                fragment = next(f for f in fragments if f.fragment_id == part["table_id"])
                blocks.extend(_scoped_partial_blocks(
                    view, part, cells, fragment, raw, absolute, offsets, source_pages,
                ))
    return blocks


def _unknown_grid_cell(cell: Mapping[str, Any]) -> dict[str, Any]:
    """Keep actual final characters while withholding an unproven relation."""
    result = dict(cell)
    for key in (
        "row", "col", "column", "row_span", "col_span", "column_span",
        "is_column_header", "is_row_header", "row_header_path", "column_header_path",
        "record_id", "unit", "units", "unit_refs", "period", "periods", "period_refs",
        "notes", "note_refs",
    ):
        result.pop(key, None)
    result["service_grid_scope_state"] = "unknown"
    return result


def _isolated_unclassified_grid(part: Mapping[str, Any], fragment: TableFragment) -> bool:
    """Read physical grid geometry outside every explicitly declared scope."""
    rows = part["source_rows"]
    mapping = part["source_to_display_rows"]
    if (not rows or rows != list(range(rows[0], rows[-1] + 1))
            or part["header_rows"] or set(mapping) != set(rows)
            or any(type(value) is not int or value < 1 for value in mapping.values())
            or len(set(mapping.values())) != len(rows)):
        return False
    for scope in fragment.source_header_scopes:
        if not scope.get("complete"):
            continue
        headers, body = scope.get("header_rows", []), scope.get("body_rows", [])
        if (not isinstance(headers, list) or not isinstance(body, list) or not headers
                or any(type(row) is not int or not 0 <= row < fragment.num_rows
                       for row in [*headers, *body])
                or headers != list(range(headers[0], headers[-1] + 1))
                or any(row <= headers[-1] for row in body)):
            return False
        if set(rows).intersection([*headers, *body]):
            return False
    return True


def _unclassified_grid_cell(cell: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the final grid's actual coordinates, without semantic roles."""
    result = _unknown_grid_cell(cell)
    for key in ("row", "col", "row_span", "col_span"):
        if key in cell:
            result[key] = cell[key]
    result["service_grid_scope_state"] = "geometry_only_unclassified"
    return result


def _scoped_partial_blocks(
    view: SemanticTableView, part: Mapping[str, Any], cells: list[dict[str, Any]],
    fragment: TableFragment, raw: str, absolute: int, offsets: list[int],
    source_pages: Mapping[str, int],
) -> list[dict[str, Any]]:
    """Isolate source header scopes without changing the emitted grid or text.

    The residual renderer may keep several internal headers in one GFM table.
    Those headers cannot become interchangeable columns of one scoring body.
    Declared scopes stay isolated. A separate unclassified grid keeps physical
    coordinates without acquiring header roles or inferred semantic paths.
    """
    displayed = part["source_to_display_rows"]
    present = set(part["source_rows"])
    geometry_only = _isolated_unclassified_grid(part, fragment)
    visible_refs = {cell.get("source_cell_ref", {}).get("token") for cell in cells}
    source_by_position = {(cell.row, cell.column): cell for cell in fragment.cells}
    source_by_row: dict[int, list[TableCellFragment]] = {}
    actual_by_row: dict[int, list[dict[str, Any]]] = {}
    for source_cell in fragment.cells:
        source_by_row.setdefault(source_cell.row, []).append(source_cell)
    for actual_cell in cells:
        actual_by_row.setdefault(actual_cell["row"], []).append(actual_cell)
    scopes: list[dict[str, Any]] = []
    for source_scope in fragment.source_header_scopes:
        headers, body = source_scope.get("header_rows", []), source_scope.get("body_rows", [])
        if not source_scope.get("complete") or not headers:
            continue
        if (any(type(row) is not int for row in [*headers, *body])
                or headers != list(range(headers[0], headers[-1] + 1))
                or not set(headers).issubset(present)
                or any(not headers[-1] < row < fragment.num_rows for row in body)):
            continue
        header_cells = [cell for row in headers for cell in source_by_row.get(row, [])]
        visible = bool(header_cells) and all(
            CellRef(fragment.fragment_id, cell.row, cell.column).token in visible_refs
            for cell in header_cells
        )
        scopes.append({"headers": set(headers), "body": set(body),
                       "start_display": displayed[headers[0]], "visible": visible})
    by_row: dict[int, list[int]] = {}
    for index, scope in enumerate(scopes):
        for row in scope["headers"] | scope["body"]:
            by_row.setdefault(row, []).append(index)
    boundaries: dict[int, int | None] = {}
    for index, scope in enumerate(scopes):
        start = scope["start_display"]
        unique = scope["visible"] and all(len(by_row[row]) == 1 for row in scope["headers"])
        boundaries[start] = index if unique and start not in boundaries else None
    rows = sorted((display, row) for row, display in displayed.items())
    runs: list[dict[str, Any]] = []
    active = None
    for display, row in rows:
        if display in boundaries:
            active = boundaries[display]
        if not runs or runs[-1]["scope"] != active:
            runs.append({"scope": active, "display_start": display, "rows": []})
        runs[-1]["rows"].append(row)
    blocks = []
    for index, run in enumerate(runs):
        scope_index = run["scope"]
        selected_scope = scopes[scope_index] if scope_index is not None else None
        selected = []
        for cell in (cell for row in run["rows"] for cell in actual_by_row.get(row, [])):
            source = source_by_position.get((cell["row"], cell["col"]))
            covered = range(cell["row"], cell["row"] + (source.row_span if source else 1))
            known = selected_scope is not None and all(
                by_row.get(row) == [scope_index] and row in run["rows"] for row in covered
            )
            if known and selected_scope is not None:
                retained = dict(cell)
                retained["is_column_header"] = cell["row"] in selected_scope["headers"]
                retained["service_grid_scope_state"] = "known"
                selected.append(retained)
            elif geometry_only:
                selected.append(_unclassified_grid_cell(cell))
            else:
                selected.append(_unknown_grid_cell(cell))
        if not selected:
            continue
        start = 0 if index == 0 else offsets[run["display_start"] + 1]
        stop = (offsets[runs[index + 1]["display_start"] + 1]
                if index + 1 < len(runs) else len(raw))
        block_id = (f"service:partial:{view.view_id}:{part['table_id']}:"
                    f"{part['part_index']}:scope:{index}")
        blocks.append({
            "id": block_id, "kind": "table_body", "text": raw[start:stop], "text_format": "markdown",
            "native_path": f"#/markdown/{absolute + start}:{absolute + stop}",
            "final_markdown_span": [absolute + start, absolute + stop], "cells": selected,
            "parent_id": f"service:table:{view.view_id}",
            "native_table_container": f"service:table:{view.view_id}",
            "provenance_pages": [source_pages[part["table_id"]]],
            "service_evidence_state": "retained",
            "service_header_scope": {"state": "known" if selected_scope else
                                     "geometry_only_unclassified" if geometry_only else "unknown",
                                     "source_header_rows": sorted(selected_scope["headers"]) if selected_scope else [],
                                     "source_body_rows": sorted(selected_scope["body"].intersection(run["rows"])) if selected_scope else []},
        })
    return blocks


def _grid_blocks(
    rendered: str, final: str, fragments: Sequence[TableFragment], owner: str
) -> list[dict[str, Any]]:
    if not rendered or final.count(rendered) != 1:
        return []
    base = final.index(rendered)
    metadata_match = re.search(r"<!-- table-structure: ([^\n]*?) -->", rendered)
    metadata = json.loads(metadata_match[1]) if metadata_match else {}
    source_cells: dict[tuple[int, int], tuple[TableFragment, TableCellFragment]] = {}
    logical_start = 0
    for index, fragment in enumerate(fragments):
        skip = len(fragment.header_row_indices) if index else 0
        for source_cell in fragment.cells:
            if source_cell.row >= skip:
                source_cells[logical_start + source_cell.row - skip, source_cell.column] = (
                    fragment,
                    source_cell,
                )
        logical_start += len(fragment.rows) - skip
    blocks: list[dict[str, Any]] = []
    for start, end, token in _spans(rendered):
        if token.type != "table_open":
            continue
        raw = rendered[start:end].rstrip("\r\n")
        absolute_start = base + start
        path = f"#/markdown/{absolute_start}:{absolute_start + len(raw)}"
        cells = markdown_cells(raw, path)
        segment_matches = list(
            re.finditer(r"<!-- table-view-segment: ([^\n]*?) -->", rendered[:start])
        )
        segment_index = json.loads(segment_matches[-1][1]).get("index") if segment_matches else None
        segment: dict[str, Any] = next(
            (
                item
                for item in metadata.get("gfm", {}).get("segments", [])
                if item.get("index") == segment_index
            ),
            {},
        )
        lines = _physical_lines(raw)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        retained: list[dict[str, Any]] = []
        for cell in cells:
            display_row = cell["row"]
            if display_row in segment.get("synthetic_header_rows", []):
                continue
            line_index = display_row + int(display_row > 0)
            line = lines[line_index]
            delimiters = [match.start() for match in re.finditer(r"\|", line)]
            col = cell["col"]
            if len(delimiters) <= col + 1:
                raise ValueError("owned GFM cell has no explicit final character range")
            a, b = delimiters[col] + 1, delimiters[col + 1]
            a += len(line[a:b]) - len(line[a:b].lstrip())
            b -= len(line[a:b]) - len(line[a:b].rstrip())
            cell.update(
                final_markdown_span=[
                    absolute_start + offsets[line_index] + a,
                    absolute_start + offsets[line_index] + b,
                ],
                service_evidence_state="retained",
            )
            # markdown_cells supplies syntax positions; each cell's actual
            # inline content must not be parsed anew as a standalone block.
            cell["text"] = _inline_text(line[a:b])
            # First display rows can be synthetic; use only the explicit source
            # mapping and roles, never let GFM manufacture a source header.
            cell.pop("is_column_header", None)
            source_row = display_row - segment.get("source_to_rendered_row_offset", 0)
            cell["row"] = source_row if segment else display_row
            mapped = source_cells.get((source_row, col)) if segment else None
            if mapped is not None:
                fragment, source = mapped
                if _inline_text(_escape_cell(source.text)) == cell["text"]:
                    cell.update(
                        source_cell_ref=_ref_dict(
                            CellRef(fragment.fragment_id, source.row, source.column)
                        ),
                        page=fragment.page_number,
                        is_column_header=source.is_column_header,
                        is_row_header=source.is_row_header,
                    )
            retained.append(cell)
        if metadata.get("structure_valid") is True:
            for row, col, row_span, col_span in metadata.get("spans") or []:
                anchor = next(
                    (cell for cell in retained if (cell["row"], cell["col"]) == (row, col)), None
                )
                covered = [
                    cell
                    for cell in retained
                    if row <= cell["row"] < row + row_span
                    and col <= cell["col"] < col + col_span
                    and cell is not anchor
                ]
                if anchor is not None and all(not cell["text"] for cell in covered):
                    anchor.update(row_span=row_span, col_span=col_span)
                    retained = [cell for cell in retained if cell not in covered]
        if not retained:
            continue
        block_id = f"service:retained:{owner}:{len(blocks)}"
        pages = sorted({fragment.page_number for fragment in fragments})
        blocks.append(
            {
                "id": block_id,
                "kind": "table_body",
                "text": raw,
                "text_format": "markdown",
                "native_path": path,
                "final_markdown_span": [absolute_start, absolute_start + len(raw)],
                "cells": retained,
                "parent_id": f"service:table:{owner}",
                "native_table_container": f"service:table:{owner}",
                "provenance_pages": pages,
                "service_evidence_state": "retained",
            }
        )
    return blocks


def build_service_observation(
    result: DocumentParseResult,
    *,
    sample_id: str,
    pipeline: str = "P07+MO-Parse",
    provenance_pages: Sequence[int] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose final output only; preserve unknown/retained conversion evidence.

    ``provenance_pages`` is a declared input range, not a guessed page split.
    Precise source pages are attached only to actual output-owned cell refs.
    Metadata may carry run identity/timing, never replace observed content.
    """
    if not isinstance(result, DocumentParseResult):
        raise TypeError("a real DocumentParseResult is required")
    if set(metadata or {}) - _METADATA_KEYS:
        raise ValueError("metadata cannot replace service output or observation identity")
    if result._final_text_evidence:
        return _read_published_observation(result, sample_id=sample_id, pipeline=pipeline,
                                           provenance_pages=provenance_pages, metadata=metadata)
    final = result.markdown
    fragments = [item for item in result._table_fragments if isinstance(item, TableFragment)]
    pages = (
        list(provenance_pages)
        if provenance_pages is not None
        else list(range(1, result.page_count + 1))
    )
    if (
        len(pages) != result.page_count
        or any(type(page) is not int or page < 1 for page in pages)
        or len(set(pages)) != len(pages)
    ):
        raise ValueError("provenance pages must be unique positive physical pages")
    source_to_physical = dict(zip(range(1, len(pages) + 1), pages, strict=True))
    errors: list[dict[str, Any]] = []
    states = []
    blocks = []
    registry, source_pages, identity_errors = _cell_registry(fragments)
    errors.extend(identity_errors)
    for view in result._semantic_tables:
        produced, state = _semantic_blocks(view, final, fragments, registry, source_pages)
        if state["final_evidence"] == "partial":
            try:
                produced.extend(_partial_grid_blocks(view, final, fragments, registry, source_pages))
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                errors.append({"category": "service_output_readback", "owner": view.view_id,
                               "reason": str(exc)})
        states.append(state)
        blocks.extend(produced)
    owners: list[tuple[str, str, Sequence[TableFragment]]] = []
    for source_view in result._table_views:
        if isinstance(source_view, TableSourceView):
            owners.append((source_view.view_id, source_view.rendered, source_view.fragments))
    owners.extend(
        (fragment.fragment_id, fragment.rendered, [fragment])
        for fragment in fragments
        if not any(fragment in owned for _, _, owned in owners)
    )
    for owner, rendered, owned in owners:
        try:
            produced = _grid_blocks(rendered, final, owned, owner)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            errors.append(
                {"category": "service_output_readback", "owner": owner, "reason": str(exc)}
            )
            produced = []
        blocks.extend(produced)
        identities = {fragment.fragment_id for fragment in owned}
        related = [
            state
            for state in states
            if state["view_id"] == owner or identities.intersection(state.get("source_tables", []))
        ]
        if not related:
            states.append(
                {
                    "view_id": owner,
                    "status": "retained",
                    "kind": "unknown",
                    "source_tables": sorted(identities),
                    "final_evidence": "retained" if produced else "unknown",
                    "reason_codes": [] if produced else ["owned_grid_not_uniquely_present"],
                }
            )
        elif produced:
            for state in related:
                present = set(state.get("retained_source_tables", [])) | identities
                state.update(retained_grid_present=True, retained_source_tables=sorted(present))
                if state["final_evidence"] != "converted":
                    state["final_evidence"] = (
                        "retained"
                        if present.issuperset(state.get("source_tables", []))
                        else "partial"
                    )
    # Never expose overlapping alternatives as two independently usable outputs.
    blocks.sort(key=lambda item: item["final_markdown_span"])
    accepted = []
    end = 0
    for block in blocks:
        a, b = block["final_markdown_span"]
        if a < end:
            errors.append(
                {
                    "category": "service_output_readback",
                    "reason": "overlapping_output_evidence",
                    "id": block["id"],
                }
            )
            continue
        accepted.append(block)
        end = b
    blocks = []
    cursor = 0
    for block in accepted + [{"final_markdown_span": [len(final), len(final)], "sentinel": True}]:
        a, b = block["final_markdown_span"]
        chunk = final[cursor:a]
        for start, stop, token in _spans(chunk):
            raw = chunk[start:stop].rstrip("\r\n")
            if visible_text(raw, "markdown"):
                block_id = f"service:text:{cursor + start}"
                kind = "heading" if token.type == "heading_open" else "text"
                item: dict[str, Any] = {
                    "id": block_id,
                    "kind": kind,
                    "text": raw,
                    "text_format": "markdown",
                    "native_path": f"#/markdown/{cursor + start}:{cursor + start + len(raw)}",
                    "final_markdown_span": [cursor + start, cursor + start + len(raw)],
                    "provenance_pages": pages,
                }
                if kind == "heading":
                    item["level"] = int(token.tag[1:])
                blocks.append(item)
        if not block.get("sentinel"):
            blocks.append(block)
        cursor = b
    containers: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        block["native_sequence"] = [index]
        block.setdefault("provenance_pages", pages)
        if block.get("cells"):
            container = block["native_table_container"]
            if not any(item["id"] == container for item in containers):
                containers.append(
                    {
                        "id": container,
                        "label": "table",
                        "native_path": block["native_path"],
                        "service_evidence_state": block["service_evidence_state"],
                    }
                )
            for cell in block["cells"]:
                if cell.get("page") is not None:
                    cell["page"] = source_to_physical.get(cell["page"])
                    if cell["page"] is not None:
                        cell["provenance_pages"] = [cell["page"]]
        block["provenance_pages"] = [
            source_to_physical.get(page, page) for page in block["provenance_pages"]
        ]
    status = (
        "partial"
        if (
            result.processed_pages < result.page_count
            or any(str(page.status) == "failed" for page in result.pages)
            or (result.parse_result is not None and result.parse_result.status == "partial")
        )
        else "completed"
    )
    observation: dict[str, Any] = {
        "sample_id": sample_id,
        "pipeline": pipeline,
        "status": status,
        "input_page_count": result.page_count,
        "pages": [{"page": None, "blocks": blocks}],
        "native_containers": containers,
        "errors": errors,
        "service_output": {
            "reader_version": SERVICE_OBSERVATION_VERSION,
            "text_source": "DocumentParseResult.markdown",
            "final_markdown": final,
            "semantic_views": states,
            "conversion_summary": {
                "declared_converted_views": sum(state["status"] == "converted" for state in states),
                "declared_retained_views": sum(state["status"] == "retained" for state in states),
                "declared_partial_views": sum(state["status"] == "partial" for state in states),
                **{
                    f"final_{name}_views": sum(state["final_evidence"] == name for state in states)
                    for name in ("converted", "retained", "partial", "unknown")
                },
            },
            "ir_status": result.parse_result.status if result.parse_result is not None else None,
            "page_statuses": [
                {"page": page.page_number, "status": str(page.status)} for page in result.pages
            ],
            "warnings": [warning.model_dump(mode="json") for warning in result.warnings],
            "limitations": [
                "No hidden IR cells are candidate text",
                "Page range is provenance, not a recovered page split",
                "Retained final grids do not establish completed semantic conversion",
                "Field evidence requires actual final emitted references and values",
            ],
        },
    }
    observation.update(copy.deepcopy(dict(metadata or {})))
    observation["relations"] = [
        edge for block in blocks for edge in block.get("service_relations", [])
    ]
    observation["relations"] = native_relations(observation)
    return observation


def _read_published_observation(
    result: DocumentParseResult, *, sample_id: str, pipeline: str,
    provenance_pages: Sequence[int] | None, metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Move producer evidence through its exact edit ledger, never fill text.

    The published text must equal the saved edit result. Removed blocks are
    removed from the observation too; a cell remains evidence only when its
    exact displayed characters survive. Internal ranges cannot supply answers.
    """
    from app.services.final_content_service import apply_text_edits, map_text_offset

    evidence = result._final_text_evidence
    assembly, edits = evidence.get("assembly_markdown"), evidence.get("edits")
    if not isinstance(assembly, str) or not isinstance(edits, list):
        raise ValueError("published output has no exact assembly edit ledger")
    if apply_text_edits(assembly, edits) != result.markdown:
        raise ValueError("published output differs from its assembly edit ledger")
    saved = result.model_copy(deep=False)
    saved.markdown = assembly
    saved._final_text_evidence = {}
    observed = build_service_observation(saved, sample_id=sample_id, pipeline=pipeline,
                                         provenance_pages=provenance_pages, metadata=metadata)
    observed, provenance = read_final_page_provenance(observed)
    final = result.markdown

    def move(item: dict[str, Any], *, cell: bool = False) -> bool:
        span = item.get("final_markdown_span")
        if not isinstance(span, list) or len(span) != 2:
            raise ValueError("published evidence has no declared character span")
        a, b = span
        start = map_text_offset(a, edits)
        end = map_text_offset(b, edits, end=True)
        if cell and assembly[a:b] != final[start:end]:
            return False
        if not cell and not visible_text(final[start:end], "markdown"):
            return False
        item["final_markdown_span"] = [start, end]
        item["native_path"] = f"#/markdown/{start}:{end}"
        if not cell:
            item["text"] = final[start:end]
        return True

    kept_ids = set()
    for page in observed["pages"]:
        kept = []
        for block in page["blocks"]:
            if not move(block):
                continue
            cells = block.get("cells", [])
            if not all(move(cell, cell=True) for cell in cells):
                raise ValueError("published table evidence contains removed or rewritten cell characters")
            kept_ids.add(block["id"])
            kept_ids.update(block[key] for key in ("parent_id", "native_table_container") if key in block)
            kept_ids.update(cell["id"] for cell in cells)
            kept.append(block)
        page["blocks"] = kept
    observed["relations"] = [edge for edge in observed.get("relations", [])
                              if edge.get("source") in kept_ids and edge.get("target") in kept_ids]
    output = observed["service_output"]
    output["final_markdown"] = final

    def move_state(value: Any) -> None:
        if isinstance(value, dict):
            span = value.get("final_markdown_span")
            if isinstance(span, list) and len(span) == 2:
                value["final_markdown_span"] = [map_text_offset(span[0], edits),
                                                 map_text_offset(span[1], edits, end=True)]
            for child in value.values():
                move_state(child)
        elif isinstance(value, list):
            for child in value:
                move_state(child)

    move_state(output["semantic_views"])
    output["published_provenance"] = {
        "status": provenance["status"], "source": "producer_assembly_ranges_and_exact_edit_ledger",
        "removed_text_is_not_candidate_evidence": True,
    }
    output["finalization"] = {key: copy.deepcopy(value) for key, value in evidence.items()
                              if key not in {"assembly_markdown", "edits"}}
    return observed


def read_final_page_provenance(
    observation: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read explicit final page comments into a separate scoring observation.

    This analysis never changes final text, identities, cells, relationships or
    processing time. Missing/duplicate comments and blocks crossing comments
    retain their existing range. A displayed cross-page table can contain cells
    from other source pages, so its existing source evidence is left intact.
    """
    derived = copy.deepcopy(dict(observation))
    diagnostic: dict[str, Any] = {
        "reader_version": FINAL_PAGE_PROVENANCE_VERSION,
        "scope": "analysis_only_explicit_final_markdown_page_comments",
        "status": "unknown",
        "markers": [],
        "blocks": [],
        "updated_blocks": 0,
        "limitations": [
            "No page is inferred from source/reference text or geometry",
            "Incomplete or duplicate page declarations retain the existing range",
            "Explicit table-cell source provenance is not replaced by display-page position",
        ],
    }
    output = derived.get("service_output")
    if isinstance(output, Mapping) and isinstance(output.get("published_provenance"), Mapping):
        diagnostic.update(status=output["published_provenance"]["status"],
                          scope="producer_assembly_ranges_and_exact_edit_ledger",
                          reason="published_ranges_already_read_without_inline_page_markers")
        return derived, diagnostic
    final = output.get("final_markdown") if isinstance(output, Mapping) else None
    count = derived.get("input_page_count")
    if not isinstance(final, str) or type(count) is not int or count < 1:
        diagnostic["reason"] = "final_markdown_or_input_page_count_unavailable"
        return derived, diagnostic
    marker_pattern = re.compile(
        r"[ \t]{0,3}<!--[ \t]*page:[ \t]*([1-9][0-9]*)[ \t]*-->[ \t]*(?:\r\n|\r|\n)?"
    )
    markers: list[dict[str, Any]] = []
    for start, end, token in _spans(final):
        if token.type != "html_block":
            continue
        match = marker_pattern.fullmatch(final[start:end])
        if match is not None:
            markers.append({"page": int(match[1]), "final_markdown_span": [start, end]})
    diagnostic["markers"] = markers
    declared = [marker["page"] for marker in markers]
    # Follow the actual marker sequence, including a producer's reordered
    # pages. Sorting it would repair reading order rather than read evidence.
    if len(declared) != count or set(declared) != set(range(1, count + 1)):
        diagnostic["reason"] = "page_markers_incomplete_duplicated_or_outside_input_range"
        return derived, diagnostic
    marker_ends = [marker["final_markdown_span"][1] for marker in markers]
    unknown = False
    for page in derived.get("pages", []):
        for block in page.get("blocks", []):
            before = copy.deepcopy(block.get("provenance_pages"))
            row: dict[str, Any] = {
                "id": block.get("id"),
                "native_path": block.get("native_path"),
                "before_pages": before,
                "after_pages": copy.deepcopy(before),
            }
            diagnostic["blocks"].append(row)
            if block.get("cells"):
                row.update(status="retained", reason="explicit_table_cell_source_provenance")
                continue
            match = re.fullmatch(r"#/markdown/([0-9]+):([0-9]+)", str(block.get("native_path", "")))
            if match is None:
                row.update(status="unknown", reason="final_character_range_unavailable")
                unknown = True
                continue
            start, end = map(int, match.groups())
            if not 0 <= start < end <= len(final) or block.get(
                "final_markdown_span", [start, end]
            ) != [start, end]:
                row.update(status="unknown", reason="final_character_range_conflict")
                unknown = True
                continue
            if before and (
                not isinstance(before, list)
                or any(type(number) is not int or not 1 <= number <= count for number in before)
            ):
                row.update(status="unknown", reason="existing_page_coordinate_frame_unavailable")
                unknown = True
                continue
            preceding = bisect_right(marker_ends, start) - 1
            if preceding < 0:
                row.update(status="unknown", reason="block_before_first_page_declaration")
                unknown = True
                continue
            if (
                preceding + 1 < len(markers)
                and markers[preceding + 1]["final_markdown_span"][0] < end
            ):
                row.update(status="unknown", reason="block_crosses_page_declarations")
                unknown = True
                continue
            declared_page = markers[preceding]["page"]
            block["provenance_pages"] = [declared_page]
            row.update(
                status="read",
                reason="explicit_final_page_comment",
                after_pages=[declared_page],
                final_markdown_span=[start, end],
            )
            diagnostic["updated_blocks"] += int(before != [declared_page])
    diagnostic["status"] = "partial" if unknown else "completed"
    return derived, diagnostic


def _read_retained_gfm_geometry(observation: dict[str, Any]) -> int:
    """Read retained GFM from printed markup, independently of private spans.

    The same Markdown must not gain or lose business information because an
    internal converter called its scope known or unknown. Native source cells
    supply location provenance only, never hidden header spans or roles.
    """
    final = observation.get("service_output", {}).get("final_markdown")
    if not isinstance(final, str):
        return 0
    pages = observation.get("pages", [])
    restored = 0
    removed_ids: set[str] = set()
    for start, end, token in _spans(final):
        if token.type != "table_open":
            continue
        raw = final[start:end].rstrip("\r\n")
        stop = start + len(raw)
        owned = []
        for page in pages:
            for block in page.get("blocks", []):
                span = block.get("final_markdown_span", [])
                if (block.get("service_evidence_state") == "retained" and block.get("cells")
                        and len(span) == 2 and start <= span[0] < span[1] <= stop):
                    owned.append((page, block))
        if not owned:
            continue
        ranges = sorted(block["final_markdown_span"] for _page, block in owned)
        if any(final[cursor_value:next_value].strip() for cursor_value, next_value in
               [(start, ranges[0][0]), *[(left[1], right[0]) for left, right in zip(ranges, ranges[1:], strict=False)],
                (ranges[-1][1], stop)]):
            continue
        parsed = markdown_cells(raw, f"#/markdown/{start}:{stop}")
        lines = _physical_lines(raw)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        old_by_span: dict[tuple[int, ...], list[dict[str, Any]]] = {}
        for _page, block in owned:
            for cell in block["cells"]:
                old_by_span.setdefault(tuple(cell.get("final_markdown_span", [])), []).append(cell)
        cells = []
        for cell in parsed:
            row, col = cell["row"], cell["col"]
            index = row + int(row > 0)
            if index >= len(lines):
                break
            line = lines[index]
            delimiters = [m.start() for m in re.finditer(r"\|", line)]
            if len(delimiters) <= col + 1:
                break
            left, right = delimiters[col] + 1, delimiters[col + 1]
            left += len(line[left:right]) - len(line[left:right].lstrip())
            right -= len(line[left:right]) - len(line[left:right].rstrip())
            if _inline_text(line[left:right]) != cell["text"]:
                break
            span = [start + offsets[index] + left, start + offsets[index] + right]
            prior = old_by_span.get(tuple(span), [])
            if len(prior) == 1 and prior[0].get("text") == cell["text"]:
                cell["id"] = prior[0]["id"]
                for key in ("page", "provenance_pages", "source_cell_ref"):
                    if key in prior[0]:
                        cell[key] = copy.deepcopy(prior[0][key])
            cell.update(final_markdown_span=span, service_evidence_state="retained",
                        service_grid_scope_state="observed_gfm_geometry")
            cells.append(cell)
        if len(cells) != len(parsed) or not cells:
            continue
        if all(not c["text"] for c in cells if c["row"] == 0):
            for cell in cells:
                cell.pop("is_column_header", None)
        parent_ids = {block.get("parent_id") or block.get("native_table_container") for _page, block in owned}
        parent = next(iter(parent_ids)) if len(parent_ids) == 1 else None
        block_id = owned[0][1]["id"]
        table_id = f"service:observed-gfm:{start}:{stop}"
        provenance = sorted({number for page, block in owned
                             for number in block.get("provenance_pages", [page["page"]])})
        fresh = {"id": block_id, "kind": "table_body", "text": raw, "text_format": "markdown",
                 "cells": cells, "native_path": f"#/markdown/{start}:{stop}",
                 "final_markdown_span": [start, stop], "provenance_pages": provenance,
                 "parent_id": table_id, "native_table_container": table_id,
                 "producer_parent_audit": parent,
                 "service_evidence_state": "retained", "display_geometry_reader": "actual_gfm_only"}
        sequences = [block["native_sequence"] for _page, block in owned if type(block.get("native_sequence")) is int]
        if sequences:
            fresh["native_sequence"] = min(sequences)
        containers = observation.setdefault("native_containers", [])
        if not any(container["id"] == table_id for container in containers):
            containers.append({"id": table_id, "label": "table", "native_path": fresh["native_path"],
                               "evidence": "explicit_final_gfm_syntax"})
        host = owned[0][0]
        for page, block in owned:
            if block["id"] != block_id:
                removed_ids.add(block["id"])
            page["blocks"] = [item for item in page["blocks"] if item["id"] != block["id"]]
        host["blocks"].append(fresh)
        restored += 1
    for page in pages:
        page["blocks"].sort(key=lambda block: block.get("final_markdown_span", [0])[0])
    observation["relations"] = [edge for edge in observation.get("relations", [])
                                if edge.get("source") not in removed_ids and edge.get("target") not in removed_ids]
    return restored


def read_final_observation(
    observation: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read only the currently frozen final-output observation format."""
    output = observation.get("service_output")
    if (not isinstance(output, Mapping)
            or output.get("reader_version") != SERVICE_OBSERVATION_VERSION):
        raise ValueError("final readback requires the current repaired service observation build")
    derived, diagnostic = read_final_page_provenance(observation)
    derived = copy.deepcopy(derived)
    diagnostic["retained_gfm_geometry_blocks"] = _read_retained_gfm_geometry(derived)
    diagnostic.update(
        reader_version=FINAL_OBSERVATION_READBACK_VERSION,
        page_provenance_reader_version=FINAL_PAGE_PROVENANCE_VERSION,
        source_reader_version=SERVICE_OBSERVATION_VERSION,
        source_scope="current_repaired_build_only",
    )
    return derived, diagnostic
