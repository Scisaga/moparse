"""CPU-only source PDF table evidence and source-owned display updates.

PDF evidence can add a role only after the entire native cell grid binds to
original glyphs and vector boundaries. Missing evidence remains unknown.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pymupdf

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult, PageParseResult
from app.models.source import StoredSource
from app.parsers.base import ParserCancelledError
from app.services.table_service import PageFurnitureFragment, TableFragment, refresh_table_views
from app.utils.deadline import remaining_timeout


class PDFTableEvidenceService:
    def __init__(self, settings: object) -> None:
        self.settings = settings

    async def apply(
        self,
        result: DocumentParseResult,
        source: StoredSource,
        options: ContentParseOptions,
        *,
        cancel_event: Any = None,
    ) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ParserCancelledError("PDF table evidence cancelled")
        fragments = [item for item in result._table_fragments if isinstance(item, TableFragment)]
        if source.mime_type == "application/pdf" and fragments:
            worker = asyncio.create_task(
                asyncio.to_thread(
                    inspect_pdf_tables,
                    source.path,
                    fragments,
                    cancel_event=cancel_event,
                    options=options,
                    pages=result.pages,
                    page_furniture=result._page_furniture,
                )
            )
            try:
                observations = await asyncio.shield(worker)
            except asyncio.CancelledError:
                # A cancelled coroutine cannot relinquish ownership while its
                # CPU thread still owns source handles or mutable fragments.
                await asyncio.gather(asyncio.shield(worker), return_exceptions=True)
                raise
            result._source_verification["pdf_table_evidence"] = {
                "policy": "vector-grid-glyph-binding",
                "observations": observations,
            }
        if cancel_event is not None and cancel_event.is_set():
            raise ParserCancelledError("PDF table evidence cancelled before projection")
        remaining_timeout(options)
        refresh_table_views(result.pages, fragments)


def inspect_pdf_tables(
    path: Path,
    fragments: list[TableFragment],
    *,
    cancel_event: Any = None,
    options: ContentParseOptions | None = None,
    pages: list[PageParseResult] | None = None,
    page_furniture: list[object] | None = None,
) -> list[dict[str, Any]]:
    """Measure original PDF cells; bind every role to a complete source grid."""
    observations: list[dict[str, Any]] = []
    try:
        document = pymupdf.open(path)
    except (OSError, RuntimeError, ValueError) as exc:
        return [{"bound": False, "reason": "source_pdf_unreadable", "detail": str(exc)}]
    with document:
        for fragment in fragments:
            if cancel_event is not None and cancel_event.is_set():
                raise ParserCancelledError("PDF table evidence cancelled at source-page boundary")
            if options is not None:
                remaining_timeout(options)
            if fragment.source_kind != "mineru" or not fragment.valid:
                continue
            if not 1 <= fragment.page_number <= len(document):
                continue
            observation = _source_grid(document[fragment.page_number - 1], fragment)
            observation.update(table_id=fragment.fragment_id, source_page=fragment.page_number)
            fragment.pdf_evidence = observation
            if observation["bound"]:
                _apply_bound_grid(fragment, observation)
            observations.append(observation)
    if pages is not None:
        page_contents = {page.page_number: page.content or "" for page in pages}
        for fragment in fragments:
            grid = fragment.pdf_evidence
            if not grid.get("bound"):
                continue
            content = _compact(
                re.sub(
                    r"[*_#]",
                    "",
                    re.sub(
                        r"<!--.*?-->",
                        "",
                        page_contents.get(fragment.page_number, ""),
                        flags=re.DOTALL,
                    ),
                )
            )
            above = grid.get("nearby_source_lines_above", [])
            missing = [line for line in above if _compact(line["text"]) not in content]
            grid["unbound_nearby_source_lines"] = missing
            # This proves the local source caption zone; global continuity still
            # requires every existing non-table context and unit predicate.
            fragment.caption_scope_complete = not missing
    _verify_numbered_continuations(fragments, pages, page_furniture)
    _bind_header_scope_continuations(fragments, pages, page_furniture)
    return observations


def _compact(value: str) -> str:
    """Explicit ASCII width/whitespace policy, with no semantic substitutions."""
    return "".join(
        chr(ord(char) - 0xFEE0) if 0xFF01 <= ord(char) <= 0xFF5E else char
        for char in value
        if not char.isspace()
    )


def _cluster(values: list[float]) -> list[float]:
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and abs(value - sum(groups[-1]) / len(groups[-1])) < 0.7:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _coverage(intervals: list[tuple[float, float]], start: float, end: float) -> bool:
    cursor = start
    for left, right in sorted(intervals):
        if right < start or left > end:
            continue
        if left > cursor + 0.8:
            return False
        cursor = max(cursor, right)
    return cursor >= end - 0.8


def _source_grid(page: Any, fragment: TableFragment) -> dict[str, Any]:
    """Reconstruct rectangular cells from original axis-aligned vector rules."""
    width, height = page.rect.width, page.rect.height
    x0, y0, x1, y1 = fragment.normalized_bbox
    roi = (x0 * width - 4, y0 * height - 4, x1 * width + 4, y1 * height + 4)
    vertical: list[tuple[float, float, float]] = []
    horizontal: list[tuple[float, float, float]] = []
    fills: list[tuple[float, float, float, float]] = []
    rules: list[tuple[float, float, float, float]] = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.x0 < roi[0] or rect.y0 < roi[1] or rect.x1 > roi[2] or rect.y1 > roi[3]:
            continue
        fill = drawing.get("fill")
        if fill is not None and max(fill) - min(fill) < 0.03 and 0.1 < min(fill) < 0.95:
            if rect.width > 2 and rect.height > 2:
                fills.append(tuple(rect))
        dark_fill = fill is not None and max(fill) < 0.15
        if dark_fill and min(rect.width, rect.height) < 2:
            rules.append(tuple(rect))
        if dark_fill and rect.width < 2 and rect.height > 2:
            vertical.append(((rect.x0 + rect.x1) / 2, rect.y0, rect.y1))
        elif dark_fill and rect.height < 2 and rect.width > 2:
            horizontal.append(((rect.y0 + rect.y1) / 2, rect.x0, rect.x1))
        color = drawing.get("color")
        if color is not None and max(color) < 0.15 and drawing.get("width", 1) < 1:
            for item in drawing.get("items", []):
                if item[0] != "l":
                    continue
                a, b = item[1:3]
                if abs(a.x - b.x) < 0.2 and abs(a.y - b.y) > 2:
                    vertical.append(((a.x + b.x) / 2, min(a.y, b.y), max(a.y, b.y)))
                elif abs(a.y - b.y) < 0.2 and abs(a.x - b.x) > 2:
                    horizontal.append(((a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x)))
    xs = _cluster([line[0] for line in vertical])
    ys = _cluster([line[0] for line in horizontal])
    if len(xs) < 2 or len(ys) < 2 or len(xs) > 101 or len(ys) > 2001:
        return {"bound": False, "reason": "no_complete_source_vector_grid"}
    nx, ny = len(xs) - 1, len(ys) - 1
    if (ny, nx) != (fragment.num_rows, fragment.num_cols):
        return {
            "bound": False,
            "reason": "source_grid_dimensions_disagree",
            "source_shape": [ny, nx],
        }

    def vborder(x: float, top: float, bottom: float) -> bool:
        return _coverage(
            [(a, b) for coordinate, a, b in vertical if abs(x - coordinate) < 0.7]
            + [(b, d) for a, b, c, d in rules if a - 0.1 <= x <= c + 0.1 and c - a < 2],
            top,
            bottom,
        )

    def hborder(y: float, left: float, right: float) -> bool:
        return _coverage(
            [(a, b) for coordinate, a, b in horizontal if abs(y - coordinate) < 0.7]
            + [(a, c) for a, b, c, d in rules if b - 0.1 <= y <= d + 0.1 and d - b < 2],
            left,
            right,
        )

    if not all(
        (
            vborder(xs[0], ys[0], ys[-1]),
            vborder(xs[-1], ys[0], ys[-1]),
            hborder(ys[0], xs[0], xs[-1]),
            hborder(ys[-1], xs[0], xs[-1]),
        )
    ):
        return {
            "bound": False,
            "reason": "source_outer_border_incomplete",
            "x_grid": xs,
            "y_grid": ys,
            "borders": [
                vborder(xs[0], ys[0], ys[-1]),
                vborder(xs[-1], ys[0], ys[-1]),
                hborder(ys[0], xs[0], xs[-1]),
                hborder(ys[-1], xs[0], xs[-1]),
            ],
        }
    parent = list(range(nx * ny))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    for row in range(ny):
        for column in range(nx):
            slot = row * nx + column
            if column + 1 < nx and not vborder(xs[column + 1], ys[row], ys[row + 1]):
                union(slot, slot + 1)
            if row + 1 < ny and not hborder(ys[row + 1], xs[column], xs[column + 1]):
                union(slot, slot + nx)
    groups: dict[int, list[tuple[int, int]]] = {}
    for row in range(ny):
        for column in range(nx):
            groups.setdefault(find(row * nx + column), []).append((row, column))
    glyphs = []
    for block in page.get_text("rawdict", sort=True)["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for char in span.get("chars", []):
                    glyphs.append(
                        {
                            "c": char["c"],
                            "bbox": list(char["bbox"]),
                            "font": span["font"],
                            "size": span["size"],
                            "flags": span["flags"],
                        }
                    )
    cells: list[dict[str, Any]] = []
    for slots in groups.values():
        top, left = min(r for r, _ in slots), min(c for _, c in slots)
        bottom, right = max(r for r, _ in slots) + 1, max(c for _, c in slots) + 1
        if set(slots) != {(r, c) for r in range(top, bottom) for c in range(left, right)}:
            return {"bound": False, "reason": "ambiguous_nonrectangular_source_cell"}
        bbox = (xs[left], ys[top], xs[right], ys[bottom])
        if not (
            vborder(bbox[0], bbox[1], bbox[3])
            and vborder(bbox[2], bbox[1], bbox[3])
            and hborder(bbox[1], bbox[0], bbox[2])
            and hborder(bbox[3], bbox[0], bbox[2])
        ):
            return {"bound": False, "reason": "source_cell_border_incomplete"}
        found = [
            g
            for g in glyphs
            if bbox[0] < (g["bbox"][0] + g["bbox"][2]) / 2 < bbox[2]
            and bbox[1] < (g["bbox"][1] + g["bbox"][3]) / 2 < bbox[3]
        ]
        literal = "".join(g["c"] for g in found)
        nonblank = [g for g in found if not g["c"].isspace()]
        text_bbox = (
            [
                min(g["bbox"][0] for g in nonblank),
                min(g["bbox"][1] for g in nonblank),
                max(g["bbox"][2] for g in nonblank),
                max(g["bbox"][3] for g in nonblank),
            ]
            if nonblank
            else None
        )
        centered = bool(
            text_bbox
            and abs((text_bbox[0] + text_bbox[2]) / 2 - (bbox[0] + bbox[2]) / 2)
            <= max(2, (bbox[2] - bbox[0]) * 0.10)
        )
        shade_slices = sorted(
            {
                bbox[1] + 1,
                bbox[3] - 1,
                *(
                    y
                    for _, top, _, bottom in fills
                    for y in (top, bottom)
                    if bbox[1] + 1 < y < bbox[3] - 1
                ),
            }
        )
        shaded = all(
            _coverage(
                [(a, c) for a, b, c, d in fills if b <= (lo + hi) / 2 <= d],
                bbox[0] + 1,
                bbox[2] - 1,
            )
            for lo, hi in zip(shade_slices, shade_slices[1:], strict=False)
        )
        cells.append(
            {
                "row": top,
                "column": left,
                "row_span": bottom - top,
                "column_span": right - left,
                "bbox": list(bbox),
                "text": literal,
                "glyphs": found,
                "centered": centered,
                "shaded": shaded,
                "fonts": sorted({g["font"] for g in nonblank}),
            }
        )
    cells.sort(key=lambda c: (c["row"], c["column"]))
    native = {(cell.row, cell.column): cell for cell in fragment.cells}
    mismatches = []
    for cell in cells:
        other = native.get((cell["row"], cell["column"]))
        if (
            other is None
            or (other.row_span, other.column_span) != (cell["row_span"], cell["column_span"])
            or _compact(other.text) != _compact(cell["text"])
        ):
            mismatches.append(
                {
                    "row": cell["row"],
                    "column": cell["column"],
                    "source": cell["text"],
                    "native": other.text if other else None,
                }
            )
    if len(native) != len(cells) or mismatches:
        return {
            "bound": False,
            "reason": "source_cell_text_or_spans_disagree",
            "mismatches": mismatches,
            "source_cells": cells,
        }
    nearby_lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            a, b, c, d = line["bbox"]
            if xs[0] - 2 <= a and c <= xs[-1] + 2 and ys[0] - 36 <= b and d <= ys[0] + 1:
                nearby_lines.append(
                    {
                        "text": "".join(span["text"] for span in line["spans"]),
                        "bbox": list(line["bbox"]),
                    }
                )
    return {
        "bound": True,
        "nearby_source_lines_above": nearby_lines,
        "reason": "complete_source_vector_grid_and_glyphs_match_native",
        "x_grid": xs,
        "y_grid": ys,
        "source_cells": cells,
        "page_size": [width, height],
    }


_NUMERIC = re.compile(r"[+\-−]?(?:\d[\d,.]*(?:%|％)?|[—–-])\Z")


def _numeric(value: str) -> bool:
    return bool(_NUMERIC.fullmatch(_compact(value)))


def _header_candidates(grid: dict[str, Any], num_rows: int, num_cols: int) -> list[dict[str, Any]]:
    """Require source style contrast plus column value evidence, not a lexicon.

    Centering alone, equal text, boldness, shading and a native first-row flag
    are each insufficient. A complete band must precede a different body style
    within the same physically closed, exactly bound source grid.
    """
    cells = grid["source_cells"]
    candidates: list[dict[str, Any]] = []
    for row in range(num_rows - 1):
        band = [cell for cell in cells if cell["row"] == row]
        visible = [cell for cell in band if _compact(cell["text"])]
        if len(visible) < 2 or any(cell["row_span"] != 1 for cell in band):
            continue
        if sum(cell["column_span"] for cell in band) != num_cols:
            continue
        if not all(cell["centered"] for cell in visible) or any(
            _numeric(cell["text"]) for cell in visible
        ):
            continue
        body = [cell for cell in cells if cell["row"] == row + 1 and _compact(cell["text"])]
        if not body or all(cell["centered"] and not _numeric(cell["text"]) for cell in body):
            continue
        shaded_band = all(cell["shaded"] for cell in visible)
        shade_contrast = shaded_band and any(not cell["shaded"] for cell in body)
        numeric_columns = {cell["column"] for cell in body if _numeric(cell["text"])}
        # Unshaded headers require at least two value-bearing columns with
        # source alignment contrast, avoiding centered prose and key/value rows.
        numeric_contrast = len(numeric_columns) >= 2 and any(
            not cell["centered"] and _numeric(cell["text"]) for cell in body
        )
        if not shade_contrast and not numeric_contrast:
            continue
        candidates.append(
            {
                "header_rows": [row],
                "body_rows": [],
                "complete": True,
                "evidence_source": "pdf_vector_glyph_style",
                "evidence": {
                    "entire_grid_cell_text_and_spans_bound": True,
                    "all_nonempty_header_cells_centered": True,
                    "source_shading_contrast": shade_contrast,
                    "source_numeric_column_alignment_contrast": numeric_contrast,
                },
            }
        )
    for index, scope in enumerate(candidates):
        start = scope["header_rows"][-1] + 1
        end = candidates[index + 1]["header_rows"][0] if index + 1 < len(candidates) else num_rows
        scope["body_rows"] = list(range(start, end))
    return candidates


def _apply_bound_grid(fragment: TableFragment, grid: dict[str, Any]) -> None:
    width, height = grid["page_size"]
    native = {(cell.row, cell.column): cell for cell in fragment.cells}
    for source in grid["source_cells"]:
        cell = native[(source["row"], source["column"])]
        a, b, c, d = source["bbox"]
        cell.normalized_bbox = (a / width, b / height, c / width, d / height)
    fragment.column_boundaries = [coordinate / width for coordinate in grid["x_grid"]]
    scopes = _header_candidates(grid, fragment.num_rows, fragment.num_cols)
    grid["source_header_scopes"] = scopes
    if not scopes:
        return
    fragment.source_header_scopes = scopes
    for scope in scopes:
        for cell in fragment.cells:
            if cell.row in scope["header_rows"]:
                cell.is_column_header = True
    fragment.has_column_header = True
    fragment.header_scope_complete = any(scope["header_rows"][0] == 0 for scope in scopes)
    fragment.header_role_source = "pdf_vector_glyph_style"
    # Inferred source roles do not themselves authorize a continuation. Every
    # merge must additionally consume an explicitly corroborated scope edge.
    fragment.header_verification_required = True


def _verify_numbered_continuations(
    fragments: list[TableFragment],
    pages: list[PageParseResult] | None,
    page_furniture: list[object] | None,
) -> None:
    """Add a link only with bound complete roles and a printed ordinal chain.

    Existing full header/unit/caption/column/context predicates still decide
    whether assembly is legal. Matching visual layout or header text alone does
    not satisfy this additional continuation witness.
    """
    from app.services.table_service import (
        _columns_match,
        _complete_header_signature,
        _context_evidence,
        _continuous_table_context,
    )

    ordered = sorted(fragments, key=lambda fragment: (fragment.page_number, fragment.ordinal))
    for left, right in zip(ordered, ordered[1:], strict=False):
        if right.page_number != left.page_number + 1:
            continue
        if right.source_continues_prev is not True:
            continue
        if not left.pdf_evidence.get("bound") or not right.pdf_evidence.get("bound"):
            continue
        signature = _complete_header_signature(left)
        right_signature = _complete_header_signature(right)
        if signature is None or right_signature is None or not _columns_match(left, right):
            continue
        if signature[:-2] != right_signature[:-2]:
            continue
        left_values = [row[0].strip() for row in left.rows[len(left.header_row_indices) :]]
        right_values = [row[0].strip() for row in right.rows[len(right.header_row_indices) :]]
        if not left_values or not right_values:
            continue
        if not all(re.fullmatch(r"[0-9]+", value) for value in left_values):
            continue
        prefix = []
        for value in right_values:
            if not re.fullmatch(r"[0-9]+", value):
                break
            prefix.append(int(value))
        first = [int(value) for value in left_values]
        if (
            not prefix
            or first != list(range(first[0], first[0] + len(first)))
            or prefix != list(range(first[-1] + 1, first[-1] + 1 + len(prefix)))
        ):
            continue
        original_caption = right.caption
        original_links = list(left.verified_next_fragments)
        if signature != right_signature:
            # A source-printed unit immediately above the first fragment can
            # scope an explicitly numbered continuation. General captions and
            # conflicting/missing source declarations cannot be inherited.
            declarations, other = _context_evidence(left.caption or "")
            above = left.pdf_evidence.get("nearby_source_lines_above", [])
            source_witness = any(
                _compact(line["text"]) == _compact(left.caption or "") for line in above
            )
            right_above = "\n".join(
                line["text"] for line in right.pdf_evidence.get("nearby_source_lines_above", [])
            )
            right_units, _ = _context_evidence(right_above)
            if (
                not declarations
                or other
                or not source_witness
                or right.caption
                or left.unit_text != right.unit_text
                or (right_units and right_units != declarations)
            ):
                continue
            right.pdf_evidence["inherited_unit_scope"] = {
                "source_table_id": left.fragment_id,
                "source_page": left.page_number,
                "literal_unit": left.caption,
                "source_lines": above,
                "evidence": "source_printed_unit_complete_headers_and_ordinal_chain",
                "requires_assembly_context_guard": True,
            }
        if right.fragment_id not in left.verified_next_fragments:
            left.verified_next_fragments.append(right.fragment_id)
        if pages is None or not _continuous_table_context(
            [left, right],
            {page.page_number: page.content or "" for page in pages},
            fragments,
            [item for item in page_furniture or [] if isinstance(item, PageFurnitureFragment)],
        ):
            right.caption = original_caption
            left.verified_next_fragments = original_links
            right.pdf_evidence.pop("inherited_unit_scope", None)
            continue
        left.pdf_evidence["continuation"] = {
            "next_table_id": right.fragment_id,
            "evidence": "complete_bound_headers_columns_and_source_printed_ordinal_chain",
            "left_last_ordinal": first[-1],
            "right_first_ordinal": prefix[0],
            "native_continues_prev": True,
            "assembly_still_requires_full_context": True,
        }


def _bind_header_scope_continuations(
    fragments: list[TableFragment],
    pages: list[PageParseResult] | None,
    page_furniture: list[object] | None,
) -> None:
    """Bind a split physical grid to a source header without rewriting its rows.

    A model continuation hint is corroborated by actual source column-cell
    boundaries, full glyph/span binding, source style roles and empty intervening
    context. This is a scope edge, not permission to merge incompatible grids.
    """
    from app.services.table_service import (
        _context_evidence,
        _preceding_content,
        _table_context_pages,
    )

    if pages is None:
        return
    ordered = sorted(fragments, key=lambda fragment: (fragment.page_number, fragment.ordinal))
    contents = {page.page_number: page.content or "" for page in pages}
    furniture = [item for item in page_furniture or [] if isinstance(item, PageFurnitureFragment)]
    for left, right in zip(ordered, ordered[1:], strict=False):
        if right.page_number != left.page_number + 1 or right.source_continues_prev is not True:
            continue
        if not left.pdf_evidence.get("bound") or not right.pdf_evidence.get("bound"):
            continue
        if (
            right.header_row_indices
            or right.source_header_scopes
            or left.normalized_bbox[3] < 0.85
            or right.normalized_bbox[1] > 0.18
        ):
            continue
        scopes = [scope for scope in left.source_header_scopes if scope.get("complete")]
        if not scopes:
            continue
        scope = scopes[-1]
        rows = scope["header_rows"]
        if len(rows) != 1 or scope["body_rows"][-1:] != [left.num_rows - 1]:
            continue
        header_cells = [
            cell for cell in left.pdf_evidence["source_cells"] if cell["row"] == rows[0]
        ]
        if len(header_cells) != right.num_cols:
            continue
        # Header cells may span several atomic source columns. Compare the
        # actual group boundaries, preserving the two grids' distinct spans.
        header_x = [header_cells[0]["bbox"][0], *(cell["bbox"][2] for cell in header_cells)]
        source_x = right.pdf_evidence["x_grid"]
        if len(header_x) != len(source_x) or any(
            abs(a - b) > 1 for a, b in zip(header_x, source_x, strict=True)
        ):
            continue
        context = _table_context_pages([left, right], contents, fragments, furniture)
        left_tail = context[left.page_number].partition(left.rendered)[2]
        right_prefix = _preceding_content(context[right.page_number], right, fragments)
        if any(_context_evidence(text) != ({}, ()) for text in (left_tail, right_prefix)):
            continue
        # A new physical row style or its own unit/caption opens a fresh scope.
        if right.caption or right.unit_text:
            continue
        body_cells = right.pdf_evidence["source_cells"]
        if any(cell["row_span"] != 1 for cell in body_cells):
            continue
        if not all(
            any(cell["shaded"] for cell in body_cells if cell["row"] == row)
            and any(not cell["shaded"] for cell in body_cells if cell["row"] == row)
            for row in range(right.num_rows)
        ):
            continue
        groups = [
            list(range(cell["column"], cell["column"] + cell["column_span"]))
            for cell in header_cells
        ]
        binding = {
            "complete": True,
            "source_table_id": left.fragment_id,
            "source_page": left.page_number,
            "header_rows": rows,
            "source_column_groups": groups,
            "body_rows": list(range(right.num_rows)),
            "body_columns": list(range(right.num_cols)),
            "evidence_source": "pdf_vector_glyph_style_and_native_continuation",
        }
        right.pdf_evidence["inherited_header_scope"] = binding
        scope["continued_bodies"] = [
            {
                "table_id": right.fragment_id,
                "source_page": right.page_number,
                "body_rows": list(range(right.num_rows)),
                "source_column_groups": groups,
            }
        ]
