"""CPU-only PDF structure binding and independently evidenced field scopes.

Cell geometry and glyph identity establish source structure, not table purpose.
Header and field association policies must separately support each conversion.
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
            result._source_verification["pdf_table_evidence"] = {
                "policy": "source-structure-glyph-binding",
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
            if not fragment.valid:
                continue
            if not 1 <= fragment.page_number <= len(document):
                continue
            page = document[fragment.page_number - 1]
            observation = _source_grid(page, fragment)
            if not observation["bound"]:
                alternate = _cell_box_grid(page, fragment)
                if alternate["bound"]:
                    alternate["vector_attempt_reason"] = observation.get("reason")
                    observation = alternate
                else:
                    observation["cell_box_attempt_reason"] = alternate.get("reason")
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

    def add_line(ax: float, ay: float, bx: float, by: float) -> None:
        # A PDF path may contain the entire page. Keep its actual intersecting
        # segments; clipping never creates a new edge at the ROI boundary.
        if abs(ax - bx) < 0.2 and roi[0] <= ax <= roi[2]:
            top, bottom = max(min(ay, by), roi[1]), min(max(ay, by), roi[3])
            if bottom - top > 2:
                vertical.append(((ax + bx) / 2, top, bottom))
        elif abs(ay - by) < 0.2 and roi[1] <= ay <= roi[3]:
            left, right = max(min(ax, bx), roi[0]), min(max(ax, bx), roi[2])
            if right - left > 2:
                horizontal.append(((ay + by) / 2, left, right))

    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.x1 < roi[0] or rect.y1 < roi[1] or rect.x0 > roi[2] or rect.y0 > roi[3]:
            continue
        clipped = (max(rect.x0, roi[0]), max(rect.y0, roi[1]),
                   min(rect.x1, roi[2]), min(rect.y1, roi[3]))
        fill = drawing.get("fill")
        if fill is not None and max(fill) - min(fill) < 0.03 and 0.1 < min(fill) < 0.95:
            if rect.width > 2 and rect.height > 2:
                fills.append(clipped)
        dark_fill = fill is not None and max(fill) < 0.15
        if dark_fill and min(rect.width, rect.height) < 2:
            rules.append(clipped)
        if dark_fill and rect.width < 2 and rect.height > 2:
            add_line((rect.x0 + rect.x1) / 2, rect.y0, (rect.x0 + rect.x1) / 2, rect.y1)
        elif dark_fill and rect.height < 2 and rect.width > 2:
            add_line(rect.x0, (rect.y0 + rect.y1) / 2, rect.x1, (rect.y0 + rect.y1) / 2)
        color = drawing.get("color")
        if color is not None and max(color) < 0.85 and drawing.get("width", 1) <= 2:
            for item in drawing.get("items", []):
                if item[0] == "l":
                    a, b = item[1:3]
                    add_line(a.x, a.y, b.x, b.y)
                elif item[0] == "re":
                    box = item[1]
                    add_line(box.x0, box.y0, box.x1, box.y0)
                    add_line(box.x1, box.y0, box.x1, box.y1)
                    add_line(box.x1, box.y1, box.x0, box.y1)
                    add_line(box.x0, box.y1, box.x0, box.y0)
    xs = _cluster([line[0] for line in vertical])
    ys = _cluster([line[0] for line in horizontal])
    if len(xs) < 2 or len(ys) < 2 or len(xs) > 101 or len(ys) > 2001:
        return {"bound": False, "reason": "no_complete_source_vector_grid"}
    nx, ny = len(xs) - 1, len(ys) - 1

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
    # Partial rules do not establish a source partition to disagree with the
    # native structure. Preserve real size conflicts only after the detected
    # partition has a complete outer boundary.
    if (ny, nx) != (fragment.num_rows, fragment.num_cols):
        return {
            "bound": False,
            "reason": "source_grid_dimensions_disagree",
            "source_shape": [ny, nx],
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
                "bold": bool(nonblank) and sum(bool(g["flags"] & 16) for g in nonblank) > len(nonblank) / 2,
                "max_font_size": max((g["size"] for g in nonblank), default=0),
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
        "binding_method": "vector_grid",
        "x_grid": xs,
        "y_grid": ys,
        "source_cells": cells,
        "page_size": [width, height],
    }


def _cell_box_grid(page: Any, fragment: TableFragment) -> dict[str, Any]:
    """Bind an explicit rectangular native cell partition to all PDF glyphs.

    A successful partition is structural evidence only. The caller still needs
    independent field/header association before any semantic conversion.
    """
    if not fragment.cells or not (0 < fragment.num_rows <= 2_000 and 0 < fragment.num_cols <= 100):
        return {"bound": False, "reason": "native_cell_boxes_unavailable"}
    width, height = page.rect.width, page.rect.height
    columns: dict[int, list[float]] = {}
    rows: dict[int, list[float]] = {}
    occupied: set[tuple[int, int]] = set()
    boxes: dict[tuple[int, int], tuple[float, float, float, float]] = {}
    for cell in fragment.cells:
        if cell.normalized_bbox is None:
            return {"bound": False, "reason": "native_cell_boxes_unavailable"}
        a, b, c, d = cell.normalized_bbox
        if not (0 <= a < c <= 1 and 0 <= b < d <= 1):
            return {"bound": False, "reason": "native_cell_box_invalid"}
        if not (0 <= cell.row < cell.row + cell.row_span <= fragment.num_rows
                and 0 <= cell.column < cell.column + cell.column_span <= fragment.num_cols):
            return {"bound": False, "reason": "native_cell_span_invalid"}
        slots = {(r, col) for r in range(cell.row, cell.row + cell.row_span)
                 for col in range(cell.column, cell.column + cell.column_span)}
        if occupied & slots:
            return {"bound": False, "reason": "native_cell_boxes_overlap"}
        occupied.update(slots)
        box = (a * width, b * height, c * width, d * height)
        boxes[cell.row, cell.column] = box
        columns.setdefault(cell.column, []).append(box[0])
        columns.setdefault(cell.column + cell.column_span, []).append(box[2])
        rows.setdefault(cell.row, []).append(box[1])
        rows.setdefault(cell.row + cell.row_span, []).append(box[3])
    if occupied != {(r, c) for r in range(fragment.num_rows) for c in range(fragment.num_cols)}:
        return {"bound": False, "reason": "native_cell_partition_incomplete"}
    if set(columns) != set(range(fragment.num_cols + 1)) or set(rows) != set(range(fragment.num_rows + 1)):
        return {"bound": False, "reason": "native_cell_boundaries_incomplete"}
    if any(max(values) - min(values) > 2 for values in (*columns.values(), *rows.values())):
        return {"bound": False, "reason": "native_cell_boundaries_disagree"}
    xs = [sum(columns[i]) / len(columns[i]) for i in range(fragment.num_cols + 1)]
    ys = [sum(rows[i]) / len(rows[i]) for i in range(fragment.num_rows + 1)]
    if any(b <= a for a, b in zip(xs, xs[1:], strict=False)) or any(
        b <= a for a, b in zip(ys, ys[1:], strict=False)
    ):
        return {"bound": False, "reason": "native_cell_boundaries_not_ordered"}
    fx0, fy0, fx1, fy1 = fragment.normalized_bbox
    if any(abs(a - b) > 4 for a, b in zip(
        (xs[0], ys[0], xs[-1], ys[-1]), (fx0 * width, fy0 * height, fx1 * width, fy1 * height), strict=True
    )):
        return {"bound": False, "reason": "native_cell_partition_does_not_cover_table"}
    glyphs = []
    for block in page.get_text("rawdict", sort=True)["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for char in span.get("chars", []):
                    glyphs.append({"c": char["c"], "bbox": list(char["bbox"]),
                                   "font": span["font"], "size": span["size"], "flags": span["flags"]})
    assignment: dict[tuple[int, int], list[dict[str, Any]]] = {key: [] for key in boxes}
    for glyph in glyphs:
        a, b, c, d = glyph["bbox"]
        x, y = (a + c) / 2, (b + d) / 2
        if not (xs[0] < x < xs[-1] and ys[0] < y < ys[-1]):
            continue
        owners = [key for key, box in boxes.items() if box[0] <= x < box[2] and box[1] <= y < box[3]]
        if len(owners) != 1:
            if glyph["c"].strip():
                return {"bound": False, "reason": "source_glyph_cell_ownership_ambiguous"}
            continue
        assignment[owners[0]].append(glyph)
    fills = [tuple(drawing["rect"]) for drawing in page.get_drawings()
             if drawing.get("fill") is not None and max(drawing["fill"]) - min(drawing["fill"]) < 0.03
             and 0.1 < min(drawing["fill"]) < 0.95]
    source_cells = []
    for cell in fragment.cells:
        box = boxes[cell.row, cell.column]
        found = assignment[cell.row, cell.column]
        literal = "".join(g["c"] for g in found)
        if _compact(literal) != _compact(cell.text):
            return {"bound": False, "reason": "source_cell_box_text_disagrees"}
        nonblank = [g for g in found if g["c"].strip()]
        centered = bool(nonblank) and abs(
            (min(g["bbox"][0] for g in nonblank) + max(g["bbox"][2] for g in nonblank)) / 2
            - (box[0] + box[2]) / 2
        ) <= max(2, (box[2] - box[0]) * 0.10)
        shaded = any(a <= box[0] + 1 and b <= box[1] + 1 and c >= box[2] - 1 and d >= box[3] - 1
                     for a, b, c, d in fills)
        source_cells.append({"row": cell.row, "column": cell.column,
                             "row_span": cell.row_span, "column_span": cell.column_span,
                             "bbox": list(box), "text": literal, "glyphs": found,
                             "centered": centered, "shaded": shaded,
                             "bold": bool(nonblank) and sum(bool(g["flags"] & 16) for g in nonblank) > len(nonblank) / 2,
                             "max_font_size": max((g["size"] for g in nonblank), default=0),
                             "fonts": sorted({g["font"] for g in nonblank})})
    nearby = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            a, b, c, d = line["bbox"]
            if xs[0] - 2 <= a and c <= xs[-1] + 2 and ys[0] - 36 <= b and d <= ys[0] + 1:
                nearby.append({"text": "".join(span["text"] for span in line["spans"]), "bbox": list(line["bbox"])})
    return {"bound": True, "reason": "explicit_native_cell_partition_and_glyphs_match",
            "binding_method": "native_cell_boxes", "content_kind": "unknown",
            "x_grid": xs, "y_grid": ys, "source_cells": source_cells,
            "page_size": [width, height], "nearby_source_lines_above": nearby}


_NUMERIC = re.compile(r"[+\-−]?(?:\d[\d,.]*(?:%|％)?|[—–-])\Z")


def _numeric(value: str) -> bool:
    return bool(_NUMERIC.fullmatch(_compact(value)))


_PERIOD_LABEL = re.compile(
    r"本期|上期|本年|上年|报告期|同期|期末|年末|月末|年度|"
    r"current|prior|previous|reporting\s+period|year\s+ended|as\s+(?:at|of)", re.I
)
_YEAR_TOKEN = re.compile(r"(?<![\d.,+\-−])(?:19|20)\d{2}(?![\d.,%％])")
_PERIOD_LITERAL = re.compile(
    r"(?:(?:FY|fiscalyear|截至|于))?(?:19|20)\d{2}"
    r"(?:年度|年(?:\d{1,2}(?:[-–—至]\d{1,2})?月(?:\d{1,2}日)?)?(?:度|末|初)?|[-/]\d{1,2}(?:[-/]\d{1,2})?|Q[1-4])?\Z",
    re.I,
)
_STUB_LABEL = re.compile(r"(?:项目|指标|科目|名称|类别|分类|分组|事项|item|metric|name|description|category|group)\Z", re.I)
_SCALAR_LABEL = re.compile(r"金额|数量|比率|比例|数值|余额|amount|value|rate|quantity|balance|number", re.I)
_MEASURE_LABEL = re.compile(
    r"(?:[\u3400-\u9fff]{0,24}(?:金额|数量|余额|限额|数值|发生额|总额|净额|"
    r"比率|比例|比重|占比|份额|增减|变动|变化|损益|利润|收入|成本|费用|排名|标准值)|"
    r"(?:(?:current|prior|previous|total|net|gross|average|annual|relative|market|"
    r"operating|financial|book|fair|percentage|percent|yearonyear))*"
    r"(?:amount|value|rate|ratio|quantity|balance|number|count|share|rank|percentage|"
    r"change|growth|increase|decrease|difference|revenue|income|profit|loss|cost|expense|"
    r"assets|liabilities|equity|margin|total))\Z", re.I,
)
_FIELD_LABEL = re.compile(
    r"(?:[\u3400-\u9fff]{0,8}(?:姓名|名称|联系人|职务|职位|电话|地址|邮箱|日期|期间|单位|代码|编号)|"
    r"(?:(?:company|registered|office|postal|contact)\s*)?"
    r"(?:name|contact|position|role|phone|telephone|address|email|date|period|unit|code|identifier))\Z", re.I
)
_GROUP_LABEL = re.compile(r"(?:分组|类别|分类|地区|区域|业务分部|group|category|region|segment)\Z", re.I)
_ORDINAL_LABEL = re.compile(r"(?:序号|编号|index|no\.?|number|#)\Z", re.I)
_SUBJECT_LABEL = re.compile(r"(?:主体|关联方|交易对方|公司名称|企业名称|机构名称|客户名称|供应商名称|"
                            r"entity|counterparty|party|companyname|customername|suppliername)\Z", re.I)


def _period_label(value: str) -> bool:
    text = value.strip()
    if len(text) > 64:
        return False
    compact = _compact(text)
    if _numeric(compact):
        # An amount containing a year-shaped substring is not a period.
        return bool(re.fullmatch(r"(?:19|20)\d{2}", compact))
    if not re.search(r"\d", text):
        return bool(_PERIOD_LABEL.search(text))
    if any(len(number) > 4 for number in re.findall(r"\d+", text)):
        return False
    if _PERIOD_LITERAL.fullmatch(compact):
        return True
    # Period wording may qualify a bounded year, but may not borrow four
    # digits from a decimal, signed amount, percentage or longer identifier.
    return bool(_PERIOD_LABEL.search(text) and _YEAR_TOKEN.search(text))


def _measure_label(value: str) -> bool:
    """Recognize a complete quantity/change label, not an amount-like value.

    Parenthetical units and an explicit percentage suffix qualify a label;
    their original text remains untouched. Digits outside unit annotations,
    prose punctuation and arbitrary keyword substrings do not supply a role.
    """
    text = _compact(value)
    if not text or len(text) > 64 or re.search(r"[。；;!?]", text):
        return False
    label = re.sub(r"\([^()]*\)|（[^（）]*）", "", text).rstrip("%％")
    if re.search(r"[\d()（）]", label):
        return False
    return bool(_MEASURE_LABEL.fullmatch(label))


def _bound_band(cells: list[dict[str, Any]], start: int, end: int, columns: int) -> list[dict[str, Any]]:
    band = [cell for cell in cells if start <= cell["row"] < end]
    occupied: set[tuple[int, int]] = set()
    for cell in band:
        if cell["row"] + cell["row_span"] > end:
            return []
        slots = {(r, c) for r in range(cell["row"], cell["row"] + cell["row_span"])
                 for c in range(cell["column"], cell["column"] + cell["column_span"])}
        if occupied & slots:
            return []
        occupied.update(slots)
    return band if occupied == {(r, c) for r in range(start, end) for c in range(columns)} else []


def _header_candidates(grid: dict[str, Any], num_rows: int, num_cols: int) -> list[dict[str, Any]]:
    """Associate source header bands with actual numeric record columns.

    A bound grid or backend header flag alone never supplies these relations.
    Multirow source spans, style contrast, and explicit period/stub wording are
    independent observations; numeric values remain body data unless a complete
    header band and a distinct record row are both supported.
    """
    cells = grid["source_cells"]
    candidates: list[dict[str, Any]] = []
    next_start = 0
    for start in range(num_rows - 1):
        if start < next_start:
            continue
        accepted: list[dict[str, Any]] = []
        for end in range(start + 1, min(num_rows, start + 5)):
            band = _bound_band(cells, start, end, num_cols)
            visible = [cell for cell in band if _compact(cell["text"])]
            if len(visible) < 2 or any(_numeric(cell["text"]) and not _period_label(cell["text"]) for cell in visible):
                continue
            if any(cell["column"] == 0 and _numeric(cell["text"]) for cell in visible):
                continue
            body = [cell for cell in cells if cell["row"] == end and _compact(cell["text"])]
            if not body:
                continue
            numeric_columns = {cell["column"] for cell in body if _numeric(cell["text"])}
            subjects = [cell for cell in body if cell["column"] == 0 and not _numeric(cell["text"])]
            ordinal_labels = [cell for cell in visible if cell["column"] == 0 and cell["column_span"] == 1
                              and _ORDINAL_LABEL.fullmatch(_compact(cell["text"]))]
            ordinal_record = bool(ordinal_labels and any(
                cell["column"] == 0 and re.fullmatch(r"\d+", _compact(cell["text"])) for cell in body
            ) and any(cell["column"] == 1 and not _numeric(cell["text"]) for cell in body))
            if ordinal_record:
                numeric_columns.discard(0)
            if (not subjects and not ordinal_record) or not numeric_columns or 0 in numeric_columns:
                continue
            if any(cell["column"] == 0 and cell["column_span"] > 1 for cell in visible):
                # A full-width caption or row group is not a column header.
                continue
            if end - start > 1 and any(not any(
                cell["row"] == row and cell["column"] > 0 for cell in visible
            ) for row in range(start, end)):
                continue
            paths = []
            for column in sorted(numeric_columns):
                path = tuple(_compact(cell["text"]) for cell in sorted(visible, key=lambda c: (c["row"], c["column"]))
                             if cell["column"] <= column < cell["column"] + cell["column_span"])
                paths.append(path)
            if any(not path for path in paths) or len(set(paths)) != len(paths):
                continue
            stub = [cell for cell in visible if cell["column"] == 0 and cell["column_span"] == 1]
            explicit_stub = any(_STUB_LABEL.fullmatch(_compact(cell["text"]).rstrip(":：")) for cell in stub)
            periods = [cell for cell in visible if cell["column"] > 0 and _period_label(cell["text"])]
            period_columns = {column for cell in periods for column in range(cell["column"], cell["column"] + cell["column_span"])}
            period_matrix = bool(explicit_stub and numeric_columns <= period_columns)
            measures = [cell for cell in visible if cell["column"] > 0 and _measure_label(cell["text"])]
            measure_columns = {column for cell in measures
                               for column in range(cell["column"], cell["column"] + cell["column_span"])}
            typed_measure_matrix = bool(
                explicit_stub and numeric_columns & measure_columns
                and numeric_columns <= period_columns | measure_columns
                and (numeric_columns & period_columns or len(numeric_columns) >= 2)
            )
            shade_contrast = all(cell.get("shaded", False) for cell in visible) and any(not cell.get("shaded", False) for cell in body)
            bold_contrast = all(cell.get("bold", False) for cell in visible) and any(not cell.get("bold", False) for cell in body)
            centered = all(cell.get("centered", False) for cell in visible)
            alignment_contrast = centered and any(not cell.get("centered", False) and _numeric(cell["text"]) for cell in body)
            multirow_spans = end - start > 1 and any(cell["row_span"] > 1 or cell["column_span"] > 1 for cell in band)
            same_band_style = len({(bool(cell.get("bold")), bool(cell.get("shaded"))) for cell in visible}) == 1
            if end - start > 1 and not (
                multirow_spans or shade_contrast or bold_contrast or (alignment_contrast and same_band_style)
            ):
                # Year-valued body data alone cannot deepen an existing band.
                continue
            if candidates and periods and not explicit_stub and not (
                shade_contrast or bold_contrast or multirow_spans
            ):
                # A centered record whose values happen to be years is not an
                # internal header switch without new independent role evidence.
                continue
            named_scalar = any(cell["column"] in numeric_columns and _SCALAR_LABEL.search(cell["text"])
                               for cell in visible)
            if len(numeric_columns) < 2 and not (
                period_matrix or (explicit_stub and named_scalar and (shade_contrast or bold_contrast))
                or (ordinal_record and named_scalar and (shade_contrast or bold_contrast or alignment_contrast))
            ):
                continue
            if not (shade_contrast or bold_contrast or alignment_contrast or period_matrix
                    or typed_measure_matrix or multirow_spans):
                continue
            accepted.append({
                "header_rows": list(range(start, end)), "body_rows": [], "complete": True,
                "evidence_source": "pdf_glyph_structure_association",
                "evidence": {
                    "entire_grid_cell_text_and_spans_bound": True,
                    "all_nonempty_header_cells_centered": centered,
                    "source_shading_contrast": shade_contrast,
                    "source_bold_contrast": bold_contrast,
                    "source_numeric_column_alignment_contrast": alignment_contrast,
                    "numeric_body_columns": sorted(numeric_columns),
                    "source_period_and_stub_scope": period_matrix,
                    "source_typed_measure_scope": typed_measure_matrix,
                    "typed_measure_columns": sorted(numeric_columns & measure_columns),
                    "source_multirow_span_scope": multirow_spans,
                    "source_ordinal_record_role": ordinal_record,
                },
            })
        if accepted:
            # Prefer the complete deepest source band, never split a rowspan.
            scope = accepted[-1]
            candidates.append(scope)
            next_start = scope["header_rows"][-1] + 1
    for index, scope in enumerate(candidates):
        start = scope["header_rows"][-1] + 1
        end = candidates[index + 1]["header_rows"][0] if index + 1 < len(candidates) else num_rows
        scope["body_rows"] = list(range(start, end))
    return candidates


def _field_candidates(grid: dict[str, Any], num_rows: int) -> list[dict[str, Any]]:
    """Read explicit label delimiters or styled scalar fields, not prose grids."""
    fields = []
    for row in range(num_rows):
        cells = sorted((cell for cell in grid["source_cells"] if cell["row"] == row), key=lambda c: c["column"])
        if not cells or len(cells) % 2 or any(cell["row_span"] != 1 for cell in cells):
            continue
        pairs = list(zip(cells[::2], cells[1::2], strict=True))
        labels = [label["text"].strip() for label, _ in pairs]
        if any(not label or len(label) > 40 or _numeric(label) or re.search(r"[。；;!?]", label) for label in labels):
            continue
        explicit = all(label.endswith((":", "：")) for label in labels)
        styled = all((label.get("bold", False) and not value.get("bold", False))
                     or (label.get("shaded", False) and not value.get("shaded", False)) for label, value in pairs)
        scalar = any(_numeric(value["text"]) for _, value in pairs)
        typed_labels = all(_FIELD_LABEL.fullmatch(label.rstrip(":：")) for label in labels)
        prose_values = any(len(_compact(value["text"])) > 120 or len(value["text"].split()) >= 12
                           or re.search(r"[。!?]", value["text"])
                           for _, value in pairs)
        if prose_values or (not explicit and not (styled and (scalar or typed_labels))):
            continue
        fields.append({
            "body_rows": [row], "pairs": [
                {"label": [label["row"], label["column"]], "value": [value["row"], value["column"]]}
                for label, value in pairs
            ], "complete": True, "evidence_source": "pdf_field_delimiter_or_style",
            "evidence": {"explicit_label_delimiters": explicit, "source_style_contrast": styled,
                         "numeric_value_evidence": scalar, "explicit_field_label_type": typed_labels},
        })
    return fields


def _row_group_columns(grid: dict[str, Any], scope: dict[str, Any]) -> list[int]:
    """Recognize source row groups only with typed column roles and rowspans."""
    cells = grid["source_cells"]
    headers = [cell for cell in cells if cell["row"] in scope["header_rows"] and cell["text"].strip()]
    group_headers = [cell for cell in headers if cell["column"] == 0 and cell["column_span"] == 1]
    leaf_headers = [cell for cell in headers if cell["column"] == 1 and cell["column_span"] == 1]
    if not group_headers or not leaf_headers or not all(
        _GROUP_LABEL.fullmatch(_compact(cell["text"]).rstrip(":：")) for cell in group_headers
    ) or not any(_STUB_LABEL.fullmatch(_compact(cell["text"]).rstrip(":：")) for cell in leaf_headers):
        return []
    body_rows = scope["body_rows"]
    if not any(cell["column"] == 0 and cell["column_span"] == 1 and cell["row_span"] > 1
               and cell["row"] in body_rows for cell in cells):
        return []
    for row in body_rows:
        group = [cell for cell in cells if cell["column"] == 0 and cell["column_span"] == 1
                 and cell["row"] <= row < cell["row"] + cell["row_span"]]
        leaf = [cell for cell in cells if cell["column"] == 1 and cell["column_span"] == 1
                and cell["row"] == row and cell["row_span"] == 1]
        values = [cell for cell in cells if cell["row"] == row and cell["column"] >= 2]
        if len(group) != 1 or len(leaf) != 1 or not values or not any(_numeric(cell["text"]) for cell in values):
            return []
        labels = [group[0]["text"], leaf[0]["text"]]
        if any(not label.strip() or _numeric(label) or len(_compact(label)) > 40
               or re.search(r"[。；;!?]", label) for label in labels):
            return []
    return [0, 1]


def _named_subject_column(grid: dict[str, Any], scope: dict[str, Any]) -> int | None:
    """Use a uniquely named entity column within an already bound data scope.

    This does not classify a grid. The metric/category and named entity jointly
    identify a record; neither may disappear from the value's source context.
    """
    cells = grid["source_cells"]
    headers = [cell for cell in cells if cell["row"] in scope["header_rows"] and cell["text"].strip()]
    candidates = {cell["column"] for cell in headers if cell["column_span"] == 1
                  and _SUBJECT_LABEL.fullmatch(_compact(cell["text"]).rstrip(":："))}
    if len(candidates) != 1:
        return None
    column = next(iter(candidates))
    if column == 0 or not any(cell["column"] == 0 and cell["column_span"] == 1
                             and _STUB_LABEL.fullmatch(_compact(cell["text"]).rstrip(":："))
                             for cell in headers):
        return None
    for row in scope["body_rows"]:
        owned = [cell for cell in cells if cell["row"] == row and cell["column"] == column
                 and cell["column_span"] == cell["row_span"] == 1]
        if len(owned) != 1:
            return None
        label = _compact(owned[0]["text"])
        if not label or _numeric(label) or len(label) > 100 or re.search(r"[。；;!?]", label):
            return None
    return column


def _apply_bound_grid(fragment: TableFragment, grid: dict[str, Any]) -> None:
    width, height = grid["page_size"]
    native = {(cell.row, cell.column): cell for cell in fragment.cells}
    for source in grid["source_cells"]:
        cell = native[(source["row"], source["column"])]
        a, b, c, d = source["bbox"]
        cell.normalized_bbox = (a / width, b / height, c / width, d / height)
    fragment.column_boundaries = [coordinate / width for coordinate in grid["x_grid"]]
    scopes = _header_candidates(grid, fragment.num_rows, fragment.num_cols)
    for scope in scopes:
        row_columns = _row_group_columns(grid, scope)
        if row_columns:
            scope["row_header_columns"] = row_columns
            scope["evidence"]["source_typed_row_group_span"] = True
        elif (subject_column := _named_subject_column(grid, scope)) is not None:
            scope["row_header_columns"] = [0, subject_column]
            scope["evidence"]["source_named_subject_column"] = subject_column
        elif scope["evidence"].get("source_ordinal_record_role") and any(
            cell["row"] in scope["header_rows"] and cell["column"] == 1 and cell["column_span"] == 1
            and _STUB_LABEL.fullmatch(_compact(cell["text"]).rstrip(":："))
            for cell in grid["source_cells"]
        ):
            scope["row_header_columns"] = [1]
            scope["evidence"]["source_named_subject_column"] = 1
    grid["source_header_scopes"] = scopes
    fields = _field_candidates(grid, fragment.num_rows)
    grid["field_scopes"] = fields
    grid["content_kind"] = "data_table" if scopes else "mixed" if fields else "unknown"
    grid["association_evidence"] = {
        "header_scopes": len(scopes), "field_scopes": len(fields),
        "structure_alone_does_not_establish_table_purpose": True,
    }
    if not scopes:
        return
    fragment.source_header_scopes = scopes
    for scope in scopes:
        for cell in fragment.cells:
            if cell.row in scope["header_rows"]:
                cell.is_column_header = True
    fragment.has_column_header = True
    fragment.header_scope_complete = any(scope["header_rows"][0] == 0 for scope in scopes)
    fragment.header_role_source = "pdf_glyph_structure_association"
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
        if any(f.pdf_evidence.get("binding_method") == "native_cell_boxes" for f in (left, right)):
            # The new cell-partition route does not expand cross-page evidence.
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
        if any(f.pdf_evidence.get("binding_method") == "native_cell_boxes" for f in (left, right)):
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
