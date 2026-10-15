"""Restore omitted merged cells from native PDF text and drawn table grids."""

from __future__ import annotations

import logging
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows

logger = logging.getLogger(__name__)
_EDGE_TOLERANCE = 0.75  # PDF points, for coincident vector edges only.
_NATIVE_GRID_LOCK = threading.Lock()


@dataclass(frozen=True)
class _GridCell:
    row: int
    column: int
    row_span: int
    column_span: int
    bbox: tuple[float, float, float, float]
    text: str

    @property
    def positions(self) -> set[tuple[int, int]]:
        return {
            (row, column)
            for row in range(self.row, self.row + self.row_span)
            for column in range(self.column, self.column + self.column_span)
        }


def _text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _edges(values: list[float]) -> list[float]:
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and value - groups[-1][0] <= _EDGE_TOLERANCE:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _grid_cells(table: Any) -> list[_GridCell]:
    rectangles = list(dict.fromkeys(tuple(rect) for rect in table.cells if rect is not None))
    xs = _edges([rect[index] for rect in rectangles for index in (0, 2)])
    ys = _edges([rect[index] for rect in rectangles for index in (1, 3)])
    if len(xs) != table.col_count + 1 or len(ys) != table.row_count + 1:
        return []
    rows = table.extract()
    cells: list[_GridCell] = []
    occupied: set[tuple[int, int]] = set()
    for rect in rectangles:
        column = min(range(len(xs)), key=lambda index: abs(xs[index] - rect[0]))
        end_column = min(range(len(xs)), key=lambda index: abs(xs[index] - rect[2]))
        row = min(range(len(ys)), key=lambda index: abs(ys[index] - rect[1]))
        end_row = min(range(len(ys)), key=lambda index: abs(ys[index] - rect[3]))
        if not (row < end_row and column < end_column):
            return []
        cell = _GridCell(
            row, column, end_row - row, end_column - column, rect, rows[row][column] or ""
        )
        if occupied & cell.positions:
            return []
        occupied.update(cell.positions)
        cells.append(cell)
    if occupied != {
        (row, column) for row in range(table.row_count) for column in range(table.col_count)
    }:
        return []
    return cells


def _iou(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    union = (left[2] - left[0]) * (left[3] - left[1]) + (right[2] - right[0]) * (
        right[3] - right[1]
    ) - intersection
    return intersection / union if union > 0 else 0.0


def _contains(rect: tuple[float, ...], word: tuple[Any, ...]) -> bool:
    return (
        rect[0] - _EDGE_TOLERANCE <= word[0]
        and rect[1] - _EDGE_TOLERANCE <= word[1]
        and word[2] <= rect[2] + _EDGE_TOLERANCE
        and word[3] <= rect[3] + _EDGE_TOLERANCE
    )


def _owned_text(cell: _GridCell, grid: list[_GridCell], words: list[Any]) -> bool:
    owned: list[Any] = []
    for word in words:
        if not _contains(cell.bbox, word):
            continue
        if sum(_contains(other.bbox, word) for other in grid) != 1:
            return False
        owned.append(word)
    # Native extraction and the complete cell rectangle must agree. Do not
    # borrow neighboring words or place a centered label at its vertical row.
    owned.sort(key=lambda word: (word[5], word[6], word[7]))
    return bool(owned) and _text("".join(word[4] for word in owned)) == _text(cell.text)


def _positions(cell: TableCellFragment) -> set[tuple[int, int]]:
    return {
        (row, column)
        for row in range(cell.row, cell.row + cell.row_span)
        for column in range(cell.column, cell.column + cell.column_span)
    }


def _facts(text: str) -> Counter[str]:
    # An omission in a label is different from a different signed amount,
    # decimal precision, percentage or accounting-negative expression.
    number = r"\d[\d,]*(?:\s*\.\s*\d+)*(?:\s*[%％])?"
    pattern = rf"[(（]\s*[+−－-]?\s*{number}\s*[)）]|[+−－-]\s*{number}|{number}"
    typography = str.maketrans({"（": "(", "）": ")", "−": "-", "－": "-", "％": "%"})
    return Counter(_text(value).translate(typography) for value in re.findall(pattern, text))


def _completion(previous: str, source: str) -> bool:
    old, full = _text(previous), _text(source)
    if not old:
        return True
    if _facts(previous) != _facts(source):
        return False
    iterator = iter(full)
    return all(any(character == observed for observed in iterator) for character in old)


def _cell_bbox(cell: TableCellFragment, width: float, height: float) -> tuple[float, ...] | None:
    if cell.normalized_bbox is None:
        return None
    left, top, right, bottom = cell.normalized_bbox
    return left * width, top * height, right * width, bottom * height


def _misanchored_cell(
    fragment: TableFragment, grid: list[_GridCell], width: float, height: float
) -> bool:
    """Require reconciliation when logical scope contradicts source text or geometry."""
    for cell in fragment.cells:
        bbox = _cell_bbox(cell, width, height)
        if not cell.text.strip():
            continue
        scopes = [source for source in grid if _positions(cell) <= source.positions]
        if len(scopes) != 1:
            return True
        source = scopes[0]
        if not source.text.strip() or (bbox is not None and not _contains(source.bbox, bbox)):
            # Filling a correct anchor while retaining recognition in a source
            # blank can duplicate a financial value. Rebuild only after the
            # complete _regrid proof; otherwise preserve the original table.
            return True
    return False


def _put_cell(
    fragment: TableFragment,
    source: _GridCell,
    old_cells: list[TableCellFragment],
    previous: str | None,
    width: float,
    height: float,
) -> None:
    anchor = next(
        (cell for cell in old_cells if (cell.row, cell.column) == (source.row, source.column)),
        old_cells[0] if old_cells else None,
    )
    contributors = [
        cell for cell in old_cells
        if cell.text.strip() or cell.is_column_header or cell.is_row_header
    ]
    column_header = (
        all(cell.is_column_header for cell in contributors) if contributors
        else bool(anchor and anchor.is_column_header)
    )
    row_header = (
        all(cell.is_row_header for cell in contributors) if contributors
        else bool(anchor and anchor.is_row_header)
    )
    if any(cell.is_column_header for cell in contributors) and not column_header:
        fragment.header_scope_complete = False
    fragment.cells = [cell for cell in fragment.cells if cell not in old_cells]
    for row, column in source.positions:
        fragment.rows[row][column] = ""
    fragment.rows[source.row][source.column] = source.text
    fragment.cells.append(
        TableCellFragment(
            source.row, source.column, source.row_span, source.column_span, source.text,
            (source.bbox[0] / width, source.bbox[1] / height,
             source.bbox[2] / width, source.bbox[3] / height),
            column_header,
            row_header,
        )
    )
    while len(fragment.cell_evidence) < fragment.num_rows:
        fragment.cell_evidence.append([])
    for evidence_row in fragment.cell_evidence:
        while len(evidence_row) < fragment.num_cols:
            evidence_row.append({})
    for row, column in source.positions - {(source.row, source.column)}:
        # Keep recognition candidates, but the final logical view has one
        # anchor for this proved source rectangle.
        evidence = fragment.cell_evidence[row][column]
        evidence["native"] = ""
        evidence["final"] = ""
    fragment.cell_evidence[source.row][source.column] = {
        "docling": previous, "native": source.text, "final": source.text
    }


def _repair_cells(
    fragment: TableFragment, grid: list[_GridCell], words: list[Any], width: float, height: float
) -> tuple[int, list[str]]:
    changed = 0
    conflicts: list[str] = []
    for source in grid:
        if not source.text.strip():
            continue
        old_cells = [cell for cell in fragment.cells if _positions(cell) & source.positions]
        if (
            len(old_cells) == 1
            and _positions(old_cells[0]) == source.positions
            and _text(old_cells[0].text) == _text(source.text)
            and _text(fragment.rows[old_cells[0].row][old_cells[0].column]) == _text(source.text)
            and all(
                not fragment.rows[row][column].strip()
                for row, column in source.positions
                if (row, column) != (old_cells[0].row, old_cells[0].column)
            )
        ):
            continue
        if "\ufffd" in source.text or not _owned_text(source, grid, words):
            conflicts.append("native_text_ownership_unproved")
            continue
        if any(not _positions(cell) <= source.positions for cell in old_cells):
            conflicts.append("native_cell_scope_conflict")
            continue
        if any(
            (bbox := _cell_bbox(cell, width, height)) is not None
            and not _contains(source.bbox, bbox)
            for cell in old_cells
        ):
            conflicts.append("native_cell_geometry_conflict")
            continue
        # Include bare matrix anchors too: no nonempty recognition can silently
        # disappear just because the backend omitted its explicit cell object.
        previous_parts: list[str] = []
        covered: set[tuple[int, int]] = set()
        for cell in sorted(old_cells, key=lambda cell: (cell.row, cell.column)):
            if covered & _positions(cell):
                break
            covered.update(_positions(cell))
            if _text(cell.text) != _text(fragment.rows[cell.row][cell.column]):
                break
            previous_parts.append(cell.text)
        else:
            explicit_anchors = {(cell.row, cell.column) for cell in old_cells}
            previous_parts.extend(
                fragment.rows[row][column]
                for row, column in sorted(source.positions - explicit_anchors)
                if fragment.rows[row][column]
            )
            previous = "\n".join(previous_parts) if previous_parts else None
            nonempty_cells = [cell for cell in old_cells if cell.text.strip()]
            duplicate_source_text = (
                len(nonempty_cells) > 1
                and all(_text(cell.text) == _text(source.text) for cell in nonempty_cells)
                and all(
                    (bbox := _cell_bbox(cell, width, height)) is not None
                    and all(_contains(bbox, word) for word in words if _contains(source.bbox, word))
                    for cell in nonempty_cells
                )
                and all(
                    not fragment.rows[row][column].strip()
                    for row, column in source.positions - explicit_anchors
                )
            )
            if not duplicate_source_text and not _completion(previous or "", source.text):
                conflicts.append("native_cell_text_conflict")
                continue
            same = (
                len(old_cells) == 1
                and _positions(old_cells[0]) == source.positions
                and _text(previous or "") == _text(source.text)
            )
            if not same:
                _put_cell(fragment, source, old_cells, previous, width, height)
                changed += 1
            continue
        conflicts.append("native_cell_evidence_conflict")
    return changed, conflicts


def _native_characters(page: Any) -> list[tuple[str, tuple[float, ...], tuple[int, int, int]]]:
    return [
        (character["c"], tuple(character["bbox"]), (block_index, line_index, span_index))
        for block_index, block in enumerate(page.get_text("rawdict")["blocks"])
        for line_index, line in enumerate(block.get("lines", []))
        for span_index, span in enumerate(line["spans"])
        for character in span.get("chars", [])
    ]


def _observed_text(
    bbox: tuple[float, ...], characters: list[tuple[str, tuple[float, ...], tuple[int, int, int]]]
) -> str:
    groups: dict[tuple[int, int, int], list[str]] = {}
    for text, rectangle, group in characters:
        # Backend text boxes use a tighter font-height estimate than the native
        # glyph boxes. Their centers establish recognition ownership; full word
        # containment is still required independently in the source grid.
        x = (rectangle[0] + rectangle[2]) / 2
        y = (rectangle[1] + rectangle[3]) / 2
        if (bbox[0] - _EDGE_TOLERANCE <= x <= bbox[2] + _EDGE_TOLERANCE
                and bbox[1] - _EDGE_TOLERANCE <= y <= bbox[3] + _EDGE_TOLERANCE):
            groups.setdefault(group, []).append(text)
    return " ".join("".join(parts) for parts in groups.values())


def _covers_characters(
    bbox: tuple[float, ...],
    characters: list[tuple[str, tuple[float, ...], tuple[int, int, int]]],
    *, complete: bool,
) -> bool:
    if not characters:
        return False
    owned = [
        bbox[0] - _EDGE_TOLERANCE <= (rect[0] + rect[2]) / 2 <= bbox[2] + _EDGE_TOLERANCE
        and bbox[1] - _EDGE_TOLERANCE <= (rect[1] + rect[3]) / 2 <= bbox[3] + _EDGE_TOLERANCE
        for _, rect, _ in characters
    ]
    return all(owned) if complete else any(owned)


def _regrid(
    fragment: TableFragment, grid: list[_GridCell], words: list[Any], page: Any
) -> bool:
    """Reconcile a mis-split grid only if every recognized value has source ownership."""
    if any(cell.text and not _owned_text(cell, grid, words) for cell in grid):
        return False
    characters = [
        character for character in _native_characters(page)
        if sum(
            bool(source.text.strip()) and _contains(source.bbox, character[1])
            for source in grid
        ) == 1
    ]
    grid_bbox = (
        min(cell.bbox[0] for cell in grid), min(cell.bbox[1] for cell in grid),
        max(cell.bbox[2] for cell in grid), max(cell.bbox[3] for cell in grid),
    )
    originals = list(fragment.cells)
    mapped_column_headers: set[int] = set()
    quotes = str.maketrans({character: "'" for character in "‘’“”＇"})
    for cell in originals:
        if not cell.text.strip():
            continue
        bbox = _cell_bbox(cell, page.rect.width, page.rect.height)
        if bbox is None or not _contains(grid_bbox, bbox):
            return False
        observed = _observed_text(bbox, characters)
        # The backend normalizes typographic quotation marks. This is a text
        # encoding equivalence, not fuzzy label or financial-value matching.
        old, full = _text(cell.text).translate(quotes), _text(observed).translate(quotes)
        iterator = iter(full)
        ordered = all(any(character == value for value in iterator) for character in old)
        if not ordered or _facts(cell.text) - _facts(observed):
            return False
    # Require all nonempty matrix anchors to have participated in the proof.
    anchors = {(cell.row, cell.column) for cell in originals}
    if any(
        text.strip() and (row, column) not in anchors
        for row, values in enumerate(fragment.rows) for column, text in enumerate(values)
    ):
        return False
    if any(
        text.strip() and not any(
            (cell.row, cell.column) == (row, column) and _text(cell.text) == _text(text)
            for cell in originals
        )
        for row, values in enumerate(fragment.rows) for column, text in enumerate(values)
    ):
        return False
    fragment.num_rows = max(cell.row + cell.row_span for cell in grid)
    fragment.num_cols = max(cell.column + cell.column_span for cell in grid)
    fragment.rows = [["" for _ in range(fragment.num_cols)] for _ in range(fragment.num_rows)]
    fragment.cells = []
    fragment.cell_evidence = []
    fragment.source_row_indices = list(range(fragment.num_rows))
    fragment.physical_num_rows = fragment.num_rows
    fragment.valid = True
    fragment.invalid_reasons = []
    fragment.column_boundaries = sorted({
        edge / page.rect.width for cell in grid for edge in (cell.bbox[0], cell.bbox[2])
    })
    for source in grid:
        source_characters = [
            character for character in characters
            if character[0].strip() and _contains(source.bbox, character[1])
        ]

        matched = [
            cell for cell in originals
            if (bbox := _cell_bbox(cell, page.rect.width, page.rect.height)) is not None
            and (
                _contains(source.bbox, bbox)
                or (
                    _covers_characters(bbox, source_characters, complete=True)
                    and _text(source.text).translate(quotes) in _text(cell.text).translate(quotes)
                    and not (_facts(source.text) - _facts(cell.text))
                )
            )
        ]
        previous = "\n".join(cell.text for cell in matched) if matched else None
        _put_cell(fragment, source, matched, previous, page.rect.width, page.rect.height)
        contributors = [
            cell for cell in originals
            if (cell.text.strip() or cell.is_column_header or cell.is_row_header)
            and (
                cell in matched or (
                    (bbox := _cell_bbox(cell, page.rect.width, page.rect.height)) is not None
                    and _covers_characters(bbox, source_characters, complete=False)
                )
            )
        ]
        # Splitting a proved merged header must preserve its role and original
        # candidate. A partial or conflicting role scope remains unknown.
        if contributors:
            fragment.cells[-1].is_column_header = bool(matched) and all(
                cell.is_column_header for cell in contributors
            )
            fragment.cells[-1].is_row_header = bool(matched) and all(
                cell.is_row_header for cell in contributors
            )
            if (
                any(cell.is_column_header for cell in contributors)
                and not fragment.cells[-1].is_column_header
            ):
                # Losing an uncertain lower level must never make the remaining
                # top level look like a complete header for cross-page dedup.
                fragment.header_scope_complete = False
            if fragment.cells[-1].is_column_header:
                mapped_column_headers.update(id(cell) for cell in contributors if cell.is_column_header)
    if any(cell.is_column_header and id(cell) not in mapped_column_headers for cell in originals):
        fragment.header_scope_complete = False
    return True


def restore_missing_native_merged_cells(
    source_path: Path, fragments: list[TableFragment],
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Audit source-owned cell text and spans; repair proved omissions and mis-splits.

    Labels, headers, units and ordinary cells use the same evidence rules. No
    business vocabulary, expected value or period is supplied by this layer.
    Conflicts remain unchanged and are reported independently of safe repairs.
    """
    import pymupdf

    eligible: list[TableFragment] = []
    for fragment in fragments:
        if (
            fragment.source_kind != "docling"
            or (not fragment.valid and set(fragment.invalid_reasons) - {
                "overlapping_cells", "cell_out_of_bounds", "invalid_dimensions"
            })
            or len(fragment.rows) != fragment.num_rows
            or any(len(row) != fragment.num_cols for row in fragment.rows)
        ):
            continue
        eligible.append(fragment)
    if not eligible:
        return {}
    repaired: dict[str, int] = {}
    try:
        # PyMuPDF's table finder uses process-global extraction scratch state.
        with _NATIVE_GRID_LOCK, pymupdf.open(source_path) as document:
            if not document.is_pdf:
                return {}
            for page_number in sorted({fragment.page_number for fragment in eligible}):
                page = document[page_number - 1]
                words = page.get_text("words")
                if not words or page.rotation:
                    continue
                tables = page.find_tables(strategy="lines_strict").tables
                for fragment in eligible:
                    if fragment.page_number != page_number:
                        continue
                    left, top, right, bottom = fragment.normalized_bbox
                    bbox = (
                        left * page.rect.width,
                        top * page.rect.height,
                        right * page.rect.width,
                        bottom * page.rect.height,
                    )
                    matches = [
                        table
                        for table in tables
                        if _iou(bbox, table.bbox) >= 0.90
                    ]
                    if len(matches) != 1:
                        continue
                    grid = _grid_cells(matches[0])
                    if not grid or fragment.rendered.count(fragment.markdown) != 1:
                        continue
                    old_markdown = fragment.markdown
                    dimensions_match = (matches[0].row_count, matches[0].col_count) == (
                        fragment.num_rows, fragment.num_cols
                    )
                    crosses_source_cells = any(
                        cell.text.strip()
                        and sum(bool(_positions(cell) & source.positions) for source in grid) > 1
                        for cell in fragment.cells
                    )
                    if (
                        dimensions_match and fragment.valid and not crosses_source_cells
                        and not _misanchored_cell(fragment, grid, page.rect.width, page.rect.height)
                    ):
                        changed, conflicts = _repair_cells(
                            fragment, grid, words, page.rect.width, page.rect.height
                        )
                    else:
                        changed = len(grid) if _regrid(fragment, grid, words, page) else 0
                        conflicts = [] if changed else ["native_grid_alignment_unproved"]
                    if not fragment.header_scope_complete:
                        conflicts.append("native_header_scope_unproved")
                    if changed:
                        fragment.markdown = render_gfm_rows(fragment.rows)
                        fragment.rendered = fragment.rendered.replace(
                            old_markdown, fragment.markdown, 1
                        )
                        repaired[fragment.fragment_id] = changed
                    if diagnostics is not None and conflicts:
                        diagnostics.append({
                            "fragment_id": fragment.fragment_id,
                            "page_number": fragment.page_number,
                            "unresolved_cells": len(conflicts),
                            "reasons": sorted(set(conflicts)),
                        })
    except (OSError, ValueError, RuntimeError) as exc:
        logger.info("native drawn-grid recovery unavailable: %s", type(exc).__name__)
    return repaired
