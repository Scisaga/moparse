"""Docling table export and conservative cross-page logical-table assembly."""

from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from app.models.parse_result import PageDiagnostics, PageParseResult, PageSourceKind

_MARKDOWN = MarkdownIt("commonmark")
_BLOCK_WRAPPERS = {
    "paragraph_open",
    "paragraph_close",
    "heading_open",
    "heading_close",
    "blockquote_open",
    "blockquote_close",
    "bullet_list_open",
    "bullet_list_close",
    "ordered_list_open",
    "ordered_list_close",
    "list_item_open",
    "list_item_close",
}
_INLINE_WRAPPERS = {
    "em_open",
    "em_close",
    "strong_open",
    "strong_close",
    "link_open",
    "link_close",
}
_INLINE_HTML_WRAPPERS = {
    f"<{closing}{tag}>"
    for tag in ("em", "strong", "b", "i", "code", "u", "s", "del")
    for closing in ("", "/")
}


@dataclass(slots=True)
class TableCellFragment:
    row: int
    column: int
    row_span: int
    column_span: int
    text: str
    normalized_bbox: tuple[float, float, float, float] | None = None
    is_column_header: bool = False
    is_row_header: bool = False


@dataclass(slots=True)
class PageFurnitureFragment:
    """Visible source furniture retained separately from table scope evidence."""

    source_ref: str
    page_number: int
    label: str
    text: str
    rendered: str
    normalized_bbox: tuple[float, float, float, float] | None


@dataclass(slots=True)
class TableFragment:
    fragment_id: str
    page_number: int
    ordinal: int
    normalized_bbox: tuple[float, float, float, float]
    num_rows: int
    num_cols: int
    rows: list[list[str]]
    column_boundaries: list[float]
    markdown: str
    rendered: str
    valid: bool = True
    invalid_reasons: list[str] = field(default_factory=list)
    logical_table_id: str | None = None
    has_column_header: bool = False
    caption: str | None = None
    unit_text: str | None = None
    source_kind: str = "docling"
    cells: list[TableCellFragment] = field(default_factory=list)
    cell_evidence: list[list[dict[str, str | None]]] = field(default_factory=list)
    visual_obstructions: list[tuple[float, float, float, float]] = field(default_factory=list)
    physical_num_rows: int | None = None
    source_row_indices: list[int] = field(default_factory=list)
    header_scope_complete: bool = True
    caption_scope_complete: bool = True
    page_furniture: list[PageFurnitureFragment] = field(default_factory=list)
    header_role_source: str | None = None
    header_verification_required: bool = False
    verified_next_fragments: list[str] = field(default_factory=list)
    _structure_marker: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        # The matrix remains ordinary GFM. Only source-owned structural
        # information is attached as a comment, without coordinates or text.
        if self.markdown and self.rendered.count(self.markdown) == 1:
            self._structure_marker = _table_structure_marker([self], self.fragment_id)
            self.rendered = self.rendered.replace(
                self.markdown, f"{self._structure_marker}\n\n{self.markdown}", 1
            )

    @property
    def header_signature(self) -> str:
        """Complete text signature; structural equality uses cell spans as well."""
        return "\n".join(
            "|".join(_header_text(cell) for cell in self.rows[row])
            for row in self.header_row_indices
        )

    @property
    def header_row_indices(self) -> tuple[int, ...]:
        """Return the complete leading header band only with cell/span evidence.

        A first-row flag cannot establish how many header levels exist. Missing,
        discontinuous or conflicting cell evidence therefore leaves the scope
        unknown and must not authorize cross-page header removal.
        """
        if (
            not self.header_scope_complete
            or not self.valid
            or not self.has_column_header
            or not self.cells
            or not self.rows
        ):
            return ()
        if len(self.rows) != self.num_rows or any(len(row) != self.num_cols for row in self.rows):
            return ()
        header_rows: set[int] = set()
        for cell in self.cells:
            if cell.is_column_header:
                if cell.row < 0 or cell.row_span < 1 or cell.row + cell.row_span > self.num_rows:
                    return ()
                header_rows.update(range(cell.row, cell.row + cell.row_span))
        if not header_rows or header_rows != set(range(max(header_rows) + 1)):
            return ()
        depth = max(header_rows) + 1
        occupied: set[tuple[int, int]] = set()
        for cell in self.cells:
            if cell.row >= depth:
                continue
            if (
                cell.row < 0
                or cell.column < 0
                or cell.row_span < 1
                or cell.column_span < 1
                or cell.row + cell.row_span > depth
                or cell.column + cell.column_span > self.num_cols
                or _header_text(cell.text) != _header_text(self.rows[cell.row][cell.column])
            ):
                return ()
            positions = {
                (row, column)
                for row in range(cell.row, cell.row + cell.row_span)
                for column in range(cell.column, cell.column + cell.column_span)
            }
            if occupied & positions:
                return ()
            if any(
                self.rows[row][column].strip()
                for row, column in positions - {(cell.row, cell.column)}
            ):
                return ()
            occupied.update(positions)
        if occupied != {(row, column) for row in range(depth) for column in range(self.num_cols)}:
            return ()
        return tuple(range(depth))


def _header_text(value: str | None) -> str:
    # Ignore line wrapping/spacing only. Periods, words, units and punctuation
    # remain source text; financial row labels do not supply header meaning.
    return re.sub(r"\s+", "", value or "")


def _complete_header_signature(fragment: TableFragment) -> tuple[object, ...] | None:
    header_rows = fragment.header_row_indices
    if not header_rows:
        return None
    cells = tuple(
        sorted(
            (
                cell.row,
                cell.column,
                cell.row_span,
                cell.column_span,
                _header_text(cell.text),
                cell.is_column_header,
                cell.is_row_header,
            )
            for cell in fragment.cells
            if cell.row in header_rows
        )
    )
    if not any(_header_text(text) for row in header_rows for text in fragment.rows[row]):
        return None
    return (
        fragment.num_cols,
        tuple(tuple(_header_text(text) for text in fragment.rows[row]) for row in header_rows),
        cells,
        _header_text(fragment.unit_text),
        _header_text(fragment.caption),
    )


def _escape_cell(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ").strip()
    return html.escape(text, quote=False).replace("|", "&#124;")


def render_gfm_rows(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    columns = max(len(row) for row in rows)
    normalized = [row + [""] * (columns - len(row)) for row in rows]
    header = normalized[0]
    body = normalized[1:]
    lines = ["| " + " | ".join(_escape_cell(cell) for cell in header) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(columns)) + " |")
    lines.extend("| " + " | ".join(_escape_cell(cell) for cell in row) + " |" for row in body)
    return "\n".join(lines)


def _structure_geometry_known(fragment: TableFragment) -> bool:
    """Confirm that source spans refer to the emitted anchor-and-blank grid."""
    if (
        not fragment.valid
        or not fragment.cells
        or fragment.num_rows <= 0
        or fragment.num_cols <= 0
        or len(fragment.rows) != fragment.num_rows
        or any(len(row) != fragment.num_cols for row in fragment.rows)
        or fragment.markdown != render_gfm_rows(fragment.rows)
    ):
        return False
    occupied: set[tuple[int, int]] = set()
    for cell in fragment.cells:
        if (
            cell.row < 0
            or cell.column < 0
            or cell.row_span < 1
            or cell.column_span < 1
            or cell.row + cell.row_span > fragment.num_rows
            or cell.column + cell.column_span > fragment.num_cols
            or fragment.rows[cell.row][cell.column] != cell.text
        ):
            return False
        positions = {
            (row, column)
            for row in range(cell.row, cell.row + cell.row_span)
            for column in range(cell.column, cell.column + cell.column_span)
        }
        if occupied & positions or any(
            fragment.rows[row][column].strip()
            for row, column in positions - {(cell.row, cell.column)}
        ):
            return False
        occupied.update(positions)
    return True


def _table_structure_marker(group: list[TableFragment], table_id: str) -> str:
    """Describe observed cell roles/spans in final GFM indices, never infer them."""
    geometry_known = all(_structure_geometry_known(fragment) for fragment in group)
    source_header_rows: set[int] = set()
    spans: list[list[int]] = []
    output_rows = 0
    for index, fragment in enumerate(group):
        skip = len(fragment.header_row_indices) if index else 0
        for cell in fragment.cells:
            if cell.row < skip:
                continue
            logical_row = output_rows + cell.row - skip
            if cell.is_column_header:
                source_header_rows.add(logical_row)
            if cell.row_span > 1 or cell.column_span > 1:
                spans.append([logical_row, cell.column, cell.row_span, cell.column_span])
        output_rows += len(fragment.rows) - skip
    complete_header = (
        group[0].header_row_indices
        if geometry_known and all(fragment.header_row_indices for fragment in group)
        else ()
    )
    metadata = {
        "version": 1,
        "table_id": table_id,
        "source_pages": sorted({fragment.page_number for fragment in group}),
        "num_rows": output_rows,
        "num_cols": group[0].num_cols,
        "encoding": "anchor_and_blanks" if geometry_known else "unknown",
        "structure_valid": geometry_known,
        "header_rows": sorted(source_header_rows) or None,
        "header_scope_rows": list(complete_header) or None,
        "header_scope_complete": bool(complete_header),
        "spans": sorted(spans) if geometry_known else None,
    }
    role_sources = {
        fragment.header_role_source for fragment in group if fragment.header_role_source
    }
    if role_sources:
        metadata["header_role_sources"] = sorted(role_sources)
    return (
        "<!-- table-structure: "
        + json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        + " -->"
    )


def _anchored_rows(table_data: object) -> tuple[list[list[str]], list[str]]:
    rows = int(getattr(table_data, "num_rows", 0) or 0)
    columns = int(getattr(table_data, "num_cols", 0) or 0)
    reasons: list[str] = []
    if rows <= 0 or columns <= 0 or rows > 2_000 or columns > 100:
        return [], ["invalid_dimensions"]
    output = [["" for _ in range(columns)] for _ in range(rows)]
    occupied: set[tuple[int, int]] = set()
    for cell in getattr(table_data, "table_cells", []) or []:
        start_row = int(getattr(cell, "start_row_offset_idx", -1))
        end_row = int(getattr(cell, "end_row_offset_idx", -1))
        start_col = int(getattr(cell, "start_col_offset_idx", -1))
        end_col = int(getattr(cell, "end_col_offset_idx", -1))
        if not (0 <= start_row < end_row <= rows and 0 <= start_col < end_col <= columns):
            reasons.append("cell_out_of_bounds")
            continue
        positions = {
            (row, column)
            for row in range(start_row, end_row)
            for column in range(start_col, end_col)
        }
        if occupied & positions:
            reasons.append("overlapping_cells")
            continue
        occupied.update(positions)
        output[start_row][start_col] = str(getattr(cell, "text", "") or "")
    return output, list(dict.fromkeys(reasons))


def _column_boundaries(item: object, page_width: float, columns: int) -> list[float]:
    estimates: dict[int, list[float]] = {index: [] for index in range(columns + 1)}
    for cell in getattr(getattr(item, "data", None), "table_cells", []) or []:
        bbox = getattr(cell, "bbox", None)
        if bbox is None:
            continue
        start = int(getattr(cell, "start_col_offset_idx", -1))
        end = int(getattr(cell, "end_col_offset_idx", -1))
        if 0 <= start <= columns:
            estimates[start].append(float(getattr(bbox, "l", 0.0)) / page_width)
        if 0 <= end <= columns:
            estimates[end].append(float(getattr(bbox, "r", page_width)) / page_width)
    return [
        round(sum(values) / len(values), 6) if values else round(index / max(1, columns), 6)
        for index, values in estimates.items()
    ]


def _table_cells(
    table_data: object,
    *,
    page_width: float,
    page_height: float,
) -> list[TableCellFragment]:
    result: list[TableCellFragment] = []
    for cell in getattr(table_data, "table_cells", []) or []:
        start_row = int(getattr(cell, "start_row_offset_idx", -1))
        end_row = int(getattr(cell, "end_row_offset_idx", -1))
        start_col = int(getattr(cell, "start_col_offset_idx", -1))
        end_col = int(getattr(cell, "end_col_offset_idx", -1))
        if start_row < 0 or start_col < 0 or end_row <= start_row or end_col <= start_col:
            continue
        normalized_bbox: tuple[float, float, float, float] | None = None
        bbox = getattr(cell, "bbox", None)
        if bbox is not None and page_width > 0 and page_height > 0:
            try:
                top_left = bbox.to_top_left_origin(page_height=page_height)
                normalized_bbox = (
                    max(0.0, min(1.0, float(top_left.l) / page_width)),
                    max(0.0, min(1.0, float(top_left.t) / page_height)),
                    max(0.0, min(1.0, float(top_left.r) / page_width)),
                    max(0.0, min(1.0, float(top_left.b) / page_height)),
                )
            except (AttributeError, TypeError, ValueError):
                normalized_bbox = None
        result.append(
            TableCellFragment(
                row=start_row,
                column=start_col,
                row_span=end_row - start_row,
                column_span=end_col - start_col,
                text=str(getattr(cell, "text", "") or ""),
                normalized_bbox=normalized_bbox,
                is_column_header=bool(getattr(cell, "column_header", False)),
                is_row_header=bool(getattr(cell, "row_header", False)),
            )
        )
    return result


def extract_table_fragments(document: Any, page_group: tuple[int, int]) -> list[TableFragment]:
    iterator = getattr(document, "iterate_items", None)
    pages = getattr(document, "pages", None)
    if not callable(iterator) or not isinstance(pages, dict):
        return []
    try:
        from docling_core.types.doc import ContentLayer, TableItem
    except ImportError:
        return []
    ordinals: dict[int, int] = {}
    fragments: list[TableFragment] = []
    for item, _level in iterator(
        included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE}
    ):
        if not isinstance(item, TableItem) or not item.prov:
            continue
        provenance = item.prov[0]
        page_number = provenance.page_no
        if not isinstance(page_number, int) or not page_group[0] <= page_number <= page_group[1]:
            continue
        ordinal = ordinals.get(page_number, 0) + 1
        ordinals[page_number] = ordinal
        page = pages.get(page_number)
        size = getattr(page, "size", None)
        width = float(getattr(size, "width", 0.0) or 0.0)
        height = float(getattr(size, "height", 0.0) or 0.0)
        if width <= 0 or height <= 0:
            continue
        try:
            bbox = provenance.bbox.to_top_left_origin(page_height=height)
            normalized_bbox = (
                max(0.0, min(1.0, float(bbox.l) / width)),
                max(0.0, min(1.0, float(bbox.t) / height)),
                max(0.0, min(1.0, float(bbox.r) / width)),
                max(0.0, min(1.0, float(bbox.b) / height)),
            )
        except (AttributeError, TypeError, ValueError):
            continue
        rows, reasons = _anchored_rows(item.data)
        markdown = render_gfm_rows(rows)
        if reasons or not markdown:
            try:
                markdown = str(item.export_to_markdown(document) or "")
            except (AttributeError, TypeError, ValueError):
                markdown = ""
        fragment_id = f"p{page_number}_t{ordinal}"
        marker = f"<!-- table-fragment: {fragment_id} -->"
        rendered = f"{marker}\n\n{markdown}" if markdown else marker
        caption_scope_complete = True
        try:
            caption = str(item.caption_text(document) or "").strip() or None
        except (AttributeError, TypeError, ValueError, RuntimeError, IndexError, KeyError):
            caption = None
            caption_scope_complete = False
        if item.captions and not caption:
            caption_scope_complete = False
        fragments.append(
            TableFragment(
                fragment_id=fragment_id,
                page_number=page_number,
                ordinal=ordinal,
                normalized_bbox=normalized_bbox,
                num_rows=int(item.data.num_rows),
                num_cols=int(item.data.num_cols),
                rows=rows,
                column_boundaries=_column_boundaries(item, width, int(item.data.num_cols)),
                markdown=markdown,
                rendered=rendered,
                valid=not reasons,
                invalid_reasons=reasons,
                has_column_header=any(
                    bool(getattr(cell, "column_header", False))
                    and int(getattr(cell, "start_row_offset_idx", -1)) == 0
                    for cell in item.data.table_cells
                ),
                caption=caption,
                caption_scope_complete=caption_scope_complete,
                source_kind="docling",
                cells=_table_cells(item.data, page_width=width, page_height=height),
            )
        )
    return fragments


def export_page_markdown(document: Any, page_number: int, fragments: list[TableFragment]) -> str:
    iterator = getattr(document, "iterate_items", None)
    if not callable(iterator):
        # Keep legacy lightweight adapter/test documents usable. Real Docling
        # serialization errors must reach the parser's page failure reporting.
        return str(document.export_to_markdown(page_no=page_number) or "")
    from docling_core.types.doc import ContentLayer, DoclingDocument, TableItem

    if not isinstance(document, DoclingDocument):
        return str(document.export_to_markdown(page_no=page_number) or "")
    rendered = {fragment.fragment_id: fragment.rendered for fragment in fragments}
    refs: dict[str, str] = {}
    page_fragments = iter(fragment for fragment in fragments if fragment.page_number == page_number)
    for item, _level in iterator(
        page_no=page_number,
        included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE},
    ):
        if isinstance(item, TableItem):
            fragment = next(page_fragments, None)
            if fragment is not None:
                refs[item.self_ref] = fragment.fragment_id
    from docling_core.transforms.serializer.base import BaseTableSerializer
    from docling_core.transforms.serializer.common import create_ser_result
    from docling_core.transforms.serializer.markdown import (
        MarkdownDocSerializer,
        MarkdownParams,
    )
    from docling_core.types.doc import ContentLayer, DocItem, DocItemLabel, TextItem
    from pydantic import BaseModel, ConfigDict, Field

    page_furniture: list[PageFurnitureFragment] = []
    visible_excluded_cache: dict[str, set[str]] = {}

    class SourceCompleteDocSerializer(MarkdownDocSerializer):
        def get_excluded_refs(self, **kwargs: Any) -> set[str]:
            params = self.params.merge_with_patch(patch=kwargs)
            cache_key = params.model_dump_json()
            if cache_key in visible_excluded_cache:
                return visible_excluded_cache[cache_key]
            excluded = super().get_excluded_refs(**kwargs).copy()
            # Floating-item caption/reference resolution can reach layers
            # omitted from the normal walk. Exclude them explicitly too.
            for source, _ in self.doc.iterate_items(
                traverse_pictures=True,
                included_content_layers=set(ContentLayer),
            ):
                if not isinstance(source, DocItem):
                    continue
                if (
                    source.content_layer not in params.layers
                    or source.label not in params.labels
                    or (
                        params.pages is not None
                        and not any(prov.page_no in params.pages for prov in source.prov)
                    )
                ):
                    excluded.add(source.self_ref)
            visible_excluded_cache[cache_key] = excluded
            return excluded

        def serialize(
            self,
            *,
            item: Any = None,
            visited: set[str] | None = None,
            **kwargs: Any,
        ) -> Any:
            # Docling's generic walker delegates attached footnotes to the
            # floating item's serializer, while its Markdown table writer
            # does not write them. Release them at their original tree
            # position, rather than appending guesses or matching text.
            is_footnote = (
                isinstance(item, TextItem) and item.self_ref in self._footnotes_of_some_item
            )
            if is_footnote:
                if (
                    item.content_layer not in self.params.layers
                    or item.self_ref in self.get_excluded_refs(**kwargs)
                ):
                    return create_ser_result()
                result = self.text_serializer.serialize(
                    item=item,
                    doc_serializer=self,
                    doc=self.doc,
                    visited=visited,
                    **(self.params.model_dump() | kwargs),
                )
            else:
                result = super().serialize(item=item, visited=visited, **kwargs)
            if not isinstance(item, TextItem) or not result.text:
                return result
            if is_footnote:
                source_marker = (
                    f"<!-- source-text: {item.self_ref}; source-page: {page_number}; "
                    "role: footnote -->"
                )
                return create_ser_result(
                    text=f"{source_marker}\n\n{result.text}", span_source=[result]
                )
            if item.content_layer == ContentLayer.FURNITURE and item.label in {
                DocItemLabel.PAGE_HEADER,
                DocItemLabel.PAGE_FOOTER,
            }:
                marker = (
                    f"<!-- source-furniture: {item.self_ref}; source-page: {page_number}; "
                    f"role: {item.label.value} -->"
                )
                rendered_furniture = f"{marker}\n\n{result.text}"
                bbox = None
                if item.prov:
                    page = self.doc.pages.get(page_number)
                    if page is not None and page.size.width > 0 and page.size.height > 0:
                        source_bbox = item.prov[0].bbox.to_top_left_origin(
                            page_height=page.size.height
                        )
                        bbox = (
                            source_bbox.l / page.size.width,
                            source_bbox.t / page.size.height,
                            source_bbox.r / page.size.width,
                            source_bbox.b / page.size.height,
                        )
                page_furniture.append(
                    PageFurnitureFragment(
                        source_ref=item.self_ref,
                        page_number=page_number,
                        label=item.label.value,
                        text=item.text,
                        rendered=rendered_furniture,
                        normalized_bbox=bbox,
                    )
                )
                return create_ser_result(text=rendered_furniture, span_source=[result])
            return result

    class AnchoredTableSerializer(BaseModel, BaseTableSerializer):
        model_config = ConfigDict(arbitrary_types_allowed=True)

        refs: dict[str, str] = Field(default_factory=dict)
        rendered: dict[str, str] = Field(default_factory=dict)

        def serialize(self, *, item: Any, doc_serializer: Any, doc: Any, **kwargs: Any) -> Any:
            parts = []
            caption = doc_serializer.serialize_captions(item=item, **kwargs)
            if caption.text:
                parts.append(caption)
            fragment_id = self.refs.get(item.self_ref)
            text = self.rendered.get(fragment_id or "", "")
            if text:
                parts.append(create_ser_result(text=text, span_source=item))
            return create_ser_result(
                text="\n\n".join(part.text for part in parts), span_source=parts
            )

    serializer = SourceCompleteDocSerializer(
        doc=document,
        params=MarkdownParams(
            pages={page_number}, layers={ContentLayer.BODY, ContentLayer.FURNITURE}
        ),
        table_serializer=AnchoredTableSerializer(refs=refs, rendered=rendered),
    )
    markdown = str(serializer.serialize().text or "")
    for fragment in fragments:
        if fragment.page_number == page_number:
            fragment.page_furniture = page_furniture[:]
    return markdown


def _headers_match(left: TableFragment, right: TableFragment) -> bool:
    if not left.caption_scope_complete or not right.caption_scope_complete:
        return False
    signature = _complete_header_signature(left)
    continuation = _complete_header_signature(right)
    if signature is None or continuation is None or signature[:-1] != continuation[:-1]:
        return False
    # A continuation may omit an already established source caption. A new or
    # changed caption cannot establish that its rows belong to the same table.
    return not continuation[-1] or signature[-1] == continuation[-1]


def _has_column_boundaries(fragment: TableFragment) -> bool:
    values = fragment.column_boundaries
    return (
        fragment.num_cols > 0
        and len(values) == fragment.num_cols + 1
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and 0 <= value <= 1
            for value in values
        )
        and all(left < right for left, right in zip(values, values[1:], strict=False))
    )


def _columns_match(left: TableFragment, right: TableFragment) -> bool:
    if (
        left.num_cols != right.num_cols
        or not _has_column_boundaries(left)
        or not _has_column_boundaries(right)
    ):
        return False
    return (
        sum(
            abs(a - b) for a, b in zip(left.column_boundaries, right.column_boundaries, strict=True)
        )
        / len(left.column_boundaries)
        <= 0.02
    )


def _verified_link_allowed(left: TableFragment, right: TableFragment) -> bool:
    return (
        not left.header_verification_required and not right.header_verification_required
    ) or right.fragment_id in left.verified_next_fragments


def link_cross_page_tables(fragments: list[TableFragment]) -> list[list[TableFragment]]:
    by_page: dict[int, list[TableFragment]] = {}
    for fragment in fragments:
        by_page.setdefault(fragment.page_number, []).append(fragment)
    groups: list[list[TableFragment]] = []
    consumed: set[str] = set()
    for page_number in sorted(by_page):
        previous = sorted(by_page[page_number], key=lambda item: item.ordinal)[-1]
        next_items = sorted(by_page.get(page_number + 1, []), key=lambda item: item.ordinal)
        if not next_items:
            continue
        following = next_items[0]
        group = next(
            (item for item in groups if item[-1].fragment_id == previous.fragment_id), None
        )
        if (
            (previous.fragment_id not in consumed or group is not None)
            and following.fragment_id not in consumed
            and previous.valid
            and following.valid
            and previous.normalized_bbox[3] >= 0.85
            and following.normalized_bbox[1] <= 0.15
            and _verified_link_allowed(previous, following)
            and _columns_match(previous, following)
            and _headers_match(group[0] if group else previous, following)
        ):
            if group is None:
                group = [previous]
                groups.append(group)
            group.append(following)
            consumed.update({previous.fragment_id, following.fragment_id})
    return groups


def _merged_rows(group: list[TableFragment]) -> list[list[str]]:
    rows = [row[:] for row in group[0].rows]
    for fragment in group[1:]:
        continuation = fragment.rows
        if _headers_match(group[0], fragment):
            continuation = continuation[len(fragment.header_row_indices) :]
        rows.extend(row[:] for row in continuation)
    return rows


def _table_surroundings(fragment: TableFragment) -> tuple[str, str] | None:
    if not fragment.markdown or fragment.rendered.count(fragment.markdown) != 1:
        return None
    prefix, _, suffix = fragment.rendered.partition(fragment.markdown)
    prefix = prefix.replace(f"<!-- table-fragment: {fragment.fragment_id} -->", "", 1)
    if fragment._structure_marker:
        prefix = prefix.replace(fragment._structure_marker, "", 1)
    return prefix.strip(), suffix.strip()


def _preceding_content(
    content: str, fragment: TableFragment, fragments: list[TableFragment]
) -> str:
    prefix = content.partition(fragment.rendered)[0]
    # A unit printed before another table is not evidence for this table.
    for previous in fragments:
        if previous.page_number == fragment.page_number and previous.ordinal < fragment.ordinal:
            if previous.rendered and previous.rendered in prefix:
                prefix = prefix.rpartition(previous.rendered)[2]
    return prefix


def _plain_context_line(value: str, *, strip_block_markers: bool = True) -> str:
    """Compare parsed visible text, preserving literals and unknown markup."""
    source = value.strip()
    parsed = _MARKDOWN.parse(source) if strip_block_markers else _MARKDOWN.parseInline(source)
    inline: list[Token] = []
    for token in parsed:
        if token.type == "inline":
            inline.extend(token.children or [])
        elif token.type not in _BLOCK_WRAPPERS:
            # A typed private marker prevents opaque HTML/blocks from becoming
            # equal to escaped literal text. It is never emitted in source GFM.
            return "\x00" + source
    text: list[str] = []
    for token in inline:
        if token.type in {"text", "code_inline"}:
            text.append(token.content)
        elif token.type in {"softbreak", "hardbreak"}:
            text.append("\n")
        elif token.type in _INLINE_WRAPPERS:
            continue
        elif token.type == "html_inline" and token.content.casefold() in _INLINE_HTML_WRAPPERS:
            continue
        else:
            return "\x00" + source
    return "".join(text).strip()


def _context_evidence(content: str) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Separate explicit unit declarations from other observed table prelude text."""
    units: dict[str, list[str]] = {}
    other: list[str] = []
    for line in content.splitlines():
        if re.fullmatch(r"\s*<!-- page: \d+ -->\s*", line):
            continue
        plain = _plain_context_line(line)
        if not plain:
            continue
        declarations = list(re.finditer(r"(金额单位|单位|币种|Unit)\s*[：:]", plain, re.IGNORECASE))
        if not declarations or declarations[0].start() != 0:
            # Numbered or quoted source context can establish a new scope;
            # retain those block markers instead of treating them as decoration.
            comparison = _plain_context_line(line, strip_block_markers=False)
            other.append(comparison if comparison.startswith("\x00") else _header_text(comparison))
            continue
        for index, declaration in enumerate(declarations):
            dimension = "币种" if declaration[1] == "币种" else "单位"
            end = declarations[index + 1].start() if index + 1 < len(declarations) else len(plain)
            value = plain[declaration.end() : end].strip()
            if index + 1 < len(declarations):
                value = value.rstrip(",，;； ")
            # Retain every declaration in source order; an empty or conflicting
            # value must remain visible to the merge guard rather than disappear.
            units.setdefault(dimension, []).append(_header_text(value))
    return {dimension: tuple(values) for dimension, values in units.items()}, tuple(other)


def _units_are_consistent(units: dict[str, tuple[str, ...]]) -> bool:
    return all(all(values) and len(set(values)) == 1 for values in units.values())


def _table_context_pages(
    group: list[TableFragment],
    content_by_page: dict[int, str],
    fragments: list[TableFragment],
    page_furniture: list[PageFurnitureFragment] | None = None,
) -> dict[int, str]:
    """Ignore only source-proven repeated furniture for continuity checks.

    This is a view for the merge guard. The public Markdown always keeps every
    furniture item. Classification alone cannot turn a new title, unit or
    business paragraph into decoration.
    """
    context = content_by_page.copy()
    first = group[0]
    # Keep document furniture independently of whether a physical page has a
    # table. Identical objects referenced by fragments are counted only once.
    sources = list(page_furniture or [])
    sources.extend(source for fragment in fragments for source in fragment.page_furniture)
    distinct = {
        (
            source.source_ref,
            source.page_number,
            source.label,
            source.text,
            source.rendered,
            source.normalized_bbox,
        ): source
        for source in sources
    }
    all_furniture = list(distinct.values())
    for candidate in (
        source for source in all_furniture if source.page_number == first.page_number
    ):
        candidate_units, _ = _context_evidence(candidate.text)
        # A repeated source classification does not remove an explicit unit
        # declaration from the table's scope or hide conflicting declarations.
        if candidate.normalized_bbox is None or candidate_units:
            continue
        repeated: list[PageFurnitureFragment] = []
        for fragment in group:
            matches = [
                source
                for source in all_furniture
                if source.page_number == fragment.page_number
                and source.label == candidate.label
                and source.normalized_bbox is not None
                and max(
                    abs(a - b)
                    for a, b in zip(source.normalized_bbox, candidate.normalized_bbox, strict=True)
                )
                <= 0.01
            ]
            if len(matches) != 1:
                break
            repeated.append(matches[0])
        if len(repeated) != len(group):
            continue
        exact_repeat = all(source.text == candidate.text for source in repeated)

        # Printed page numbering is allowed only with the source footer label,
        # the same bottom-page position and a consistent offset from physical
        # page numbers across all adjacent pages. Arbitrary footer numbers and
        # unit/period declarations do not satisfy that evidence.
        def pagination_id(source: PageFurnitureFragment) -> tuple[tuple[str, ...], int] | None:
            if not re.fullmatch(r"\s*[0-9]+(?:\s*[-–—]\s*[0-9]+)*\s*", source.text):
                return None
            components = tuple(re.split(r"\s*[-–—]\s*", source.text.strip()))
            return components[:-1], int(components[-1]) - source.page_number

        identity = pagination_id(candidate)
        pagination = (
            candidate.label == "page_footer"
            and candidate.normalized_bbox[1] >= 0.9
            and identity is not None
            and all(pagination_id(source) == identity for source in repeated)
        )
        if pagination and identity is not None and identity[0]:
            # Hierarchical printed page IDs need an additional consecutive
            # source page as corroboration. Two arbitrary hyphenated numbers
            # alone do not establish a document pagination scheme.
            evidence_pages = {
                source.page_number
                for source in all_furniture
                if source.label == candidate.label
                and source.normalized_bbox is not None
                and max(
                    abs(a - b)
                    for a, b in zip(source.normalized_bbox, candidate.normalized_bbox, strict=True)
                )
                <= 0.01
                and pagination_id(source) == identity
            }
            pagination = any(
                {page, page + 1, page + 2} <= evidence_pages for page in evidence_pages
            )
        if not exact_repeat and not pagination:
            continue
        for source in repeated:
            page_content = context[source.page_number]
            if page_content.count(source.rendered) == 1:
                context[source.page_number] = page_content.replace(source.rendered, "", 1)
    return context


def _continuous_table_context(
    group: list[TableFragment],
    content_by_page: dict[int, str],
    fragments: list[TableFragment],
    page_furniture: list[PageFurnitureFragment] | None = None,
) -> bool:
    content_by_page = _table_context_pages(group, content_by_page, fragments, page_furniture)
    first = group[0]
    known_units, known_context = _context_evidence(
        _preceding_content(content_by_page[first.page_number], first, fragments)
    )
    if not _units_are_consistent(known_units):
        return False
    _, known_caption = _context_evidence(first.caption or "")
    for left, right in zip(group, group[1:], strict=False):
        # Recheck the first fragment's complete scope immediately before any
        # repeated header is removed, including captions omitted on middle pages.
        if not _verified_link_allowed(left, right) or not _headers_match(first, right):
            return False
        right_units, right_context = _context_evidence(
            _preceding_content(content_by_page[right.page_number], right, fragments)
        )
        if not _units_are_consistent(right_units) or any(
            dimension not in known_units or known_units[dimension][0] != values[0]
            for dimension, values in right_units.items()
        ):
            return False
        if right_context and right_context not in (known_context, known_caption):
            return False
        known_units.update(right_units)
        left_tail = content_by_page[left.page_number].partition(left.rendered)[2]
        tail_units, tail_context = _context_evidence(left_tail)
        if tail_units or tail_context:
            return False
    return True


def _source_row_marker(fragment: TableFragment, logical_start: int, skip: int) -> str:
    indices = fragment.source_row_indices
    if len(indices) != len(fragment.rows):
        indices = list(range(len(fragment.rows)))
    emitted_indices = indices[skip:]
    source_rows = ",".join(str(index + 1) for index in emitted_indices) or "none"
    if len(emitted_indices) > 1 and emitted_indices == list(
        range(emitted_indices[0], emitted_indices[-1] + 1)
    ):
        source_rows = f"{emitted_indices[0] + 1}-{emitted_indices[-1] + 1}"
    count = len(fragment.rows) - skip
    logical_rows = f"{logical_start}-{logical_start + count - 1}" if count else "none"
    return (
        f"<!-- table-source: {fragment.fragment_id}; source-page: {fragment.page_number}; "
        f"source-rows: {source_rows}; logical-rows: {logical_rows}; "
        f"repeated-header-rows: {skip} -->"
    )


def assemble_logical_tables(
    pages: list[PageParseResult],
    fragments: list[TableFragment],
    *,
    enabled: bool,
    page_furniture: list[PageFurnitureFragment] | None = None,
) -> dict[int, str]:
    content_by_page = {page.page_number: page.content or "" for page in pages}
    page_models = {page.page_number: page for page in pages}
    if not fragments:
        return content_by_page
    for fragment in fragments:
        page = page_models.get(fragment.page_number)
        if page is not None:
            page.diagnostics = page.diagnostics or PageDiagnostics(source_kind=PageSourceKind.MIXED)
            if fragment.fragment_id not in page.diagnostics.logical_table_ids:
                page.diagnostics.logical_table_ids.append(fragment.fragment_id)
    merged_fragments: set[str] = set()
    for group in link_cross_page_tables(fragments) if enabled else []:
        # Never remove a continuation unless every original rendering can be
        # replaced exactly once and all non-table material remains in scope.
        if any(
            not fragment.rendered
            or content_by_page.get(fragment.page_number, "").count(fragment.rendered) != 1
            for fragment in group
        ):
            continue
        surroundings = _table_surroundings(group[0])
        if surroundings is None or any(
            _table_surroundings(fragment) != surroundings for fragment in group[1:]
        ):
            continue
        if not _continuous_table_context(group, content_by_page, fragments, page_furniture):
            continue
        logical_id = f"table_{group[0].fragment_id}_{group[-1].fragment_id}"
        source_pages = sorted({fragment.page_number for fragment in group})
        merged = render_gfm_rows(_merged_rows(group))
        source_markers: list[str] = []
        logical_start = 1
        for index, fragment in enumerate(group):
            skip = len(fragment.header_row_indices) if index else 0
            source_markers.append(_source_row_marker(fragment, logical_start, skip))
            logical_start += len(fragment.rows) - skip
        logical = "\n\n".join(
            part
            for part in [
                f"<!-- logical-table: {logical_id}; source-pages: {','.join(map(str, source_pages))} -->",
                "\n".join(source_markers),
                surroundings[0],
                _table_structure_marker(group, logical_id),
                merged,
                surroundings[1],
            ]
            if part
        )
        first = group[0]
        content_by_page[first.page_number] = content_by_page[first.page_number].replace(
            first.rendered, logical, 1
        )
        for fragment in group:
            merged_fragments.add(fragment.fragment_id)
            fragment.logical_table_id = logical_id
            page = page_models.get(fragment.page_number)
            if page and page.diagnostics:
                page.diagnostics.logical_table_ids = [
                    logical_id if item == fragment.fragment_id else item
                    for item in page.diagnostics.logical_table_ids
                ]
        for fragment in group[1:]:
            content_by_page[fragment.page_number] = content_by_page[fragment.page_number].replace(
                fragment.rendered, "", 1
            )
    # Every standalone physical table has a complete row-to-source map too.
    # Header uncertainty or disabled merging must not remove provenance.
    for fragment in fragments:
        if fragment.fragment_id in merged_fragments:
            continue
        content = content_by_page.get(fragment.page_number, "")
        marker = _source_row_marker(fragment, logical_start=1, skip=0)
        if marker not in content and content.count(fragment.rendered) == 1:
            # The fragment marker opens the public metadata scope. Its source
            # map must follow it, or a streaming reader binds this map to the
            # preceding table instead of this physical fragment.
            fragment_marker = f"<!-- table-fragment: {fragment.fragment_id} -->"
            standalone = fragment.rendered.replace(
                fragment_marker, f"{fragment_marker}\n\n{marker}", 1
            )
            if standalone == fragment.rendered:
                standalone = f"{fragment_marker}\n\n{marker}\n\n{fragment.rendered}"
            content_by_page[fragment.page_number] = content.replace(
                fragment.rendered, standalone, 1
            )
    return content_by_page
