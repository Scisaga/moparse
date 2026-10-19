"""Conservative source-scoped relations and literal Markdown verbalization.

Only completely bound vector grids are currently eligible. Source styles and header
scopes are a bounded, evaluated association policy, not semantic ground truth.
Unresolved tables keep their existing GFM. No additional model is called.
"""

from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Sequence
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
from app.services.table_service import TableCellFragment, TableFragment, TableSourceView
from app.utils.deadline import remaining_timeout

_ID = re.compile(r"[A-Za-z0-9_.-]{1,240}\Z")
_PERIOD = re.compile(r"报告期|同期|年度|期末|年末|月末|\d{4}\s*年")
_UNIT = re.compile(r"[（(][^()（）]*(?:元|股|%|％)[^()（）]*[）)]")
_NUMBER = re.compile(r"[+\-−]?(?:\d[\d,.]*(?:%|％)?|[—–-])\Z")


def _compact(value: str) -> str:
    return "".join(
        chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in value if not c.isspace()
    )


def _literal(value: str) -> str:
    # Escape source Markdown/HTML rather than letting it become new structure.
    text = html.escape(re.sub(r"\s+", " ", value).strip(), quote=False)
    return re.sub(r"([\\`*_\[\]~|])", r"\\\1", text)


def _ref(fragment: TableFragment, cell: TableCellFragment) -> CellRef:
    return CellRef(fragment.fragment_id, cell.row, cell.column)


def _registry(fragments: Sequence[TableFragment]) -> dict[CellRef, TableCellFragment]:
    return {_ref(f, c): c for f in fragments for c in f.cells}


def _source_cells(fragment: TableFragment) -> dict[tuple[int, int], dict[str, Any]]:
    grid = fragment.pdf_evidence
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
    labels = (*rows, *columns)
    return ValueRelation(
        value=value,
        row_headers=rows,
        column_headers=columns,
        unit_refs=tuple(r for r in labels if _UNIT.search(registry[r].text)),
        period_refs=tuple(r for r in labels if _PERIOD.search(registry[r].text)),
        value_state="literal" if registry[value].text.strip() else "source_blank",
    )


def _bind_fragment(
    fragment: TableFragment,
    fragments: dict[str, TableFragment],
    registry: dict[CellRef, TableCellFragment],
) -> tuple[list[SemanticRecord], set[CellRef], str | None]:
    source = _source_cells(fragment)
    if not source:
        return [], set(), "source_grid_not_completely_bound"
    scopes = [s for s in fragment.source_header_scopes if s.get("complete")]
    headers_by_row: dict[int, tuple[TableFragment, list[TableCellFragment]]] = {}
    consumed: set[CellRef] = set()
    header_rows: set[int] = set()
    for scope in scopes:
        rows = scope.get("header_rows", [])
        body = scope.get("body_rows", [])
        if not rows or rows != list(range(rows[0], rows[-1] + 1)):
            return [], set(), "invalid_header_scope"
        headers = [c for c in fragment.cells if c.row in rows]
        if any(c.row + c.row_span > rows[-1] + 1 for c in headers):
            return [], set(), "header_span_crosses_body"
        header_rows.update(rows)
        consumed.update(_ref(fragment, c) for c in headers if not c.text.strip())
        for row in body:
            if row in headers_by_row or not rows[-1] < row < fragment.num_rows:
                return [], set(), "overlapping_header_scopes"
            headers_by_row[row] = fragment, headers

    inherited = fragment.pdf_evidence.get("inherited_header_scope", {})
    inherited_source = fragments.get(inherited.get("source_table_id"))
    inherited_groups = inherited.get("source_column_groups", [])
    if inherited.get("complete") and inherited_source is not None:
        if not _source_cells(inherited_source):
            return [], set(), "inherited_source_not_bound"
        rows = inherited.get("header_rows", [])
        headers = [c for c in inherited_source.cells if c.row in rows]
        if len(inherited_groups) != fragment.num_cols or not rows or not headers:
            return [], set(), "invalid_inherited_scope"
        for row in inherited.get("body_rows", []):
            if row in headers_by_row or not 0 <= row < fragment.num_rows:
                return [], set(), "overlapping_inherited_scope"
            headers_by_row[row] = inherited_source, headers

    records: list[SemanticRecord] = []
    for row in range(fragment.num_rows):
        if row in header_rows:
            continue
        cells = sorted(
            (c for c in fragment.cells if c.row <= row < c.row + c.row_span),
            key=lambda c: c.column,
        )
        if not cells or cells[0].column != 0:
            return [], set(), "row_not_completely_bound"
        if row not in headers_by_row:
            # A shaded label followed by an unshaded value is the current field
            # pattern. An unlabelled extra column or a rowspan is not guessed.
            if len(cells) % 2 or any(c.row_span != 1 for c in cells):
                return [], set(), "unresolved_header_or_field_row"
            values = []
            for label, value in zip(cells[::2], cells[1::2], strict=True):
                if (
                    not label.text.strip()
                    or _NUMBER.fullmatch(_compact(label.text))
                    or not source[label.row, label.column].get("shaded")
                    or source[value.row, value.column].get("shaded")
                ):
                    return [], set(), "unresolved_header_or_field_row"
                values.append(
                    _relation(_ref(fragment, value), (_ref(fragment, label),), (), registry)
                )
            records.append(SemanticRecord(fragment.fragment_id, row, tuple(values)))
            consumed.update(_ref(fragment, c) for c in cells)
            continue

        origin, headers = headers_by_row[row]

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
                probe = TableCellFragment(0, group[0], 1, len(group), "")
                path = _header_path(band, probe)
                if path is None:
                    return None
                paths.append(path)
            return paths[0] if paths and all(p == paths[0] for p in paths) else None

        subject = cells[0]
        if not subject.text.strip() or len(cells) < 2:
            return [], set(), "unresolved_row_subject"
        subject_path = path_for(subject)
        if subject_path is None:
            return [], set(), "subject_crosses_header_columns"
        values = []
        paths_seen: set[tuple[CellRef, ...]] = set()
        for cell in cells[1:]:
            if cell.row != row or cell.row_span != 1:
                return [], set(), "value_span_crosses_records"
            path = path_for(cell)
            if not path:
                return [], set(), "incomplete_column_header_path"
            refs = tuple(_ref(origin, h) for h in path)
            if refs in paths_seen:
                return [], set(), "ambiguous_duplicate_leaf_headers"
            paths_seen.add(refs)
            values.append(
                _relation(_ref(fragment, cell), (_ref(fragment, subject),), refs, registry)
            )
        records.append(
            SemanticRecord(
                fragment.fragment_id,
                row,
                tuple(values),
                _ref(fragment, subject),
                tuple(_ref(origin, h) for h in subject_path),
            )
        )
        consumed.update(_ref(fragment, c) for c in cells)
    for record in records:
        references = set(record.subject_headers)
        for relation in record.values:
            references.update(relation.row_headers)
            references.update(relation.column_headers)
        consumed.update(ref for ref in references if ref.table_id == fragment.fragment_id)
    return records, consumed, None


def bind_table_view(
    view_id: str,
    group: Sequence[TableFragment],
    all_fragments: Sequence[TableFragment],
) -> SemanticTableView:
    """Return a complete derived view or a retained source view with reasons."""
    ids = tuple(f.fragment_id for f in group)
    count = sum(len(f.cells) for f in group)
    registry = _registry(all_fragments)
    sources = {f.fragment_id: f for f in all_fragments}
    records: list[SemanticRecord] = []
    covered: set[CellRef] = set()
    reason = None
    if (
        not group
        or not _ID.fullmatch(view_id)
        or any(not _ID.fullmatch(i) for i in ids)
        or len(sources) != len(all_fragments)
        or len(set(ids)) != len(ids)
    ):
        reason = "invalid_table_identity"
    else:
        for fragment in group:
            rows, consumed, reason = _bind_fragment(fragment, sources, registry)
            if reason:
                break
            records.extend(rows)
            covered.update(consumed)
    expected = {_ref(f, c) for f in group for c in f.cells}
    if reason is None and (covered != expected or not records):
        reason = "incomplete_source_cell_coverage"
    if reason:
        return SemanticTableView(
            view_id, ids, "retained", "unknown", reason_codes=(reason,), source_cell_count=count
        )
    fields = any(r.subject is None for r in records)
    tabular = any(r.subject is not None for r in records)
    numeric = any(
        _NUMBER.fullmatch(_compact(registry[v.value].text)) for r in records for v in r.values
    )
    kind: SemanticKind = (
        "mixed"
        if fields and tabular
        else "fields"
        if fields
        else "comparison"
        if numeric
        else "records"
    )
    return SemanticTableView(
        view_id,
        ids,
        "converted",
        kind,
        tuple(records),
        source_cell_count=count,
        covered_source_cells=len(covered),
    )


def render_semantic_view(view: SemanticTableView, fragments: Sequence[TableFragment]) -> str:
    """Read all emitted labels/values from source references; never from a model."""
    registry = _registry(fragments)
    marker = (
        f"<!-- semantic-view: id={view.view_id}; "
        f"source-tables={','.join(view.source_tables)}; status={view.status} -->"
    )
    if view.status != "converted":
        return marker + "\n\n> 表格语义关系尚未确定，保留原表。"
    lines = [marker]
    for record in view.records:
        refs = {v.value for v in record.values}
        header_refs: set[CellRef] = set(record.subject_headers)
        if record.subject:
            refs.add(record.subject)
        for value in record.values:
            refs.update(value.row_headers)
            header_refs.update(value.column_headers)
        if any(ref not in registry for ref in refs | header_refs):
            raise ValueError("semantic source reference is absent")
        source = ",".join(ref.token for ref in sorted(refs))
        headers = ",".join(ref.token for ref in sorted(header_refs))
        lines.append(f"<!-- semantic-source: cells={source}; headers={headers} -->")
        parts = []
        if record.subject:
            subject = _literal(registry[record.subject].text)
            label = " / ".join(_literal(registry[r].text) for r in record.subject_headers)
            parts.append(f"{label}：{subject}" if label else subject)
        for value in record.values:
            label_refs = value.column_headers if record.subject else value.row_headers
            label = " / ".join(_literal(registry[r].text) for r in label_refs)
            text = _literal(registry[value.value].text) or "（原表留空）"
            parts.append(f"{label}：{text}")
        lines.append("- " + "；".join(parts) + "。")
    return "\n\n".join(lines)


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
            await asyncio.gather(asyncio.shield(worker), return_exceptions=True)
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
            body = "\n".join(line for line in body.splitlines() if not line.strip().startswith("|"))
            unique = markdown.count(source_view.rendered) == 1
            if view.status == "converted" and (body.strip() or not unique):
                view = SemanticTableView(
                    view.view_id,
                    view.source_tables,
                    "retained",
                    "unknown",
                    reason_codes=("public_view_not_uniquely_owned",),
                    source_cell_count=view.source_cell_count,
                )
            rendered_views.append(view)
            if not unique:
                continue
            rendered = render_semantic_view(view, fragments)
            if view.status == "converted":
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
            retained = {f.fragment_id for f in fragments} - converted
            markdown += (
                f"\n\n<!-- semantic-summary: converted={len(converted)}; "
                f"retained={len(retained)} -->\n\n"
                f"> 表格语义转换：已转换 {len(converted)} 张，保留原表 {len(retained)} 张。"
            )
        result._semantic_tables = rendered_views
        result.parse_result.renderings.markdown = markdown
        result.parse_result.renderings.plain_text = ExportService.markdown_to_text(
            markdown, source_regions=result._source_regions
        )
