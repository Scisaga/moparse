"""Shared source-free display projection for decoded native content.

This owns service role/display choices. Native payloads and labels stay intact;
table semantics are established later by the common context service.
"""
from __future__ import annotations

import copy
import hashlib
import html
import math
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any

from app.adapters.native_readers import NativeReadError, audit_copy, code_ranges
from app.services.native_text_service import _literal
from app.services.table_service import PageFurnitureFragment, TableCellFragment, TableFragment

_ROLES = {
    "text": "text",
    "paragraph": "text",
    "caption": "text",
    "footnote": "text",
    "vision_footnote": "text",
    "number": "text",
    "section_header": "title",
    "title": "title",
    "doc_title": "title",
    "paragraph_title": "title",
    "list_item": "list_item",
    "table": "table",
    "picture": "image",
    "image": "image",
    "chart": "image",
    "header_image": "image",
    "footer_image": "image",
    "page_header": "header",
    "page_footer": "footer",
    "page_number": "page_number",
    "header": "header",
    "footer": "footer",
    "reference": "text",
    "checkbox_selected": "text",
    "checkbox_unselected": "text",
    "formula": "formula",
}


def normalized_box(block: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    raw = block.get("bbox")
    if isinstance(raw, Mapping):
        raw = [raw.get(key) for key in ("l", "t", "r", "b")]
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    if not all(type(value) in {int, float} and math.isfinite(value) for value in raw):
        return None
    left, top, right, bottom = map(float, raw)
    system = block.get("coordinate_system")
    if system == "normalized_1000":
        left, top, right, bottom = (value / 1000 for value in (left, top, right, bottom))
    elif system in {"pixel", "pdf_points"}:
        size = block.get("page_dimensions", {})
        width, height = size.get("width"), size.get("height")
        if not width or not height:
            return None
        if str(block.get("coordinate_origin", "")).upper() in {"BOTTOMLEFT", "BOTTOM_LEFT"}:
            top, bottom = height - top, height - bottom
        left, right, top, bottom = left / width, right / width, top / height, bottom / height
    elif system not in {"normalized_1", "normalized"}:
        return None
    if not (0 <= left <= right <= 1 and 0 <= top <= bottom <= 1):
        return None
    return left, top, right, bottom

def _cell_html(cell: Mapping[str, Any]) -> str:
    column = _flag(cell, "is_column_header", "column_header")
    row = _flag(cell, "is_row_header", "row_header")
    tag = "th" if column or row else "td"
    attrs = f' rowspan="{cell.get("row_span", 1)}" colspan="{cell.get("col_span", 1)}"'
    if column != row:
        attrs += ' scope="col"' if column else ' scope="row"'
    attrs += f' data-native-ref="{html.escape(str(cell.get("native_path", cell.get("id", ""))), quote=True)}"'
    return f"<{tag}{attrs}>{html.escape(_cell_text(cell))}</{tag}>"

def _flag(cell: Mapping[str, Any], *names: str) -> bool:
    return any(cell.get(name) is True for name in names)

def _cell_text(cell: Mapping[str, Any]) -> str:
    value = cell.get("text")
    return value if isinstance(value, str) else ""

def _table(block: dict[str, Any], page: int, ordinal: int, branch: str) -> TableFragment | None:
    cells = block.get("cells", [])
    if not cells:
        return None
    if any(type(cell.get(key)) is not int or cell[key] < 0 for cell in cells for key in ("row", "col")):
        raise NativeReadError("saved cell position is unknown")
    if any(type(cell.get(key, 1)) is not int or not 1 <= cell.get(key, 1) <= 2000
           for cell in cells for key in ("row_span", "col_span")):
        raise NativeReadError("saved cell span is unknown or invalid")
    height = max(cell["row"] + cell.get("row_span", 1) for cell in cells)
    width = max(cell["col"] + cell.get("col_span", 1) for cell in cells)
    if height * width > 200_000:
        raise NativeReadError("saved table exceeds service bridge grid budget")
    rows = [[""] * width for _ in range(height)]
    projected = []
    occupied = set()
    for cell in cells:
        for row in range(cell["row"], cell["row"] + cell.get("row_span", 1)):
            for column in range(cell["col"], cell["col"] + cell.get("col_span", 1)):
                if (row, column) in occupied:
                    raise NativeReadError("saved cells overlap")
                occupied.add((row, column))
        rows[cell["row"]][cell["col"]] = _cell_text(cell)
        projected.append(TableCellFragment(
            row=cell["row"], column=cell["col"], row_span=cell.get("row_span", 1),
            column_span=cell.get("col_span", 1), text=_cell_text(cell),
            is_column_header=_flag(cell, "is_column_header", "column_header"),
            is_row_header=_flag(cell, "is_row_header", "row_header"),
        ))
    original = block.get("text", "")
    if block.get("text_format") in {"html", "markdown"} and original:
        rendered = original
    else:
        rendered = "<table>" + "".join("<tr>" + "".join(_cell_html(cell) for cell in cells if cell["row"] == row)
                                       + "</tr>" for row in range(height)) + "</table>"
    ident = f"{branch}_p{page}_t{ordinal}"
    box = normalized_box(block)
    header_depth = max((cell.row + cell.row_span for cell in projected if cell.is_column_header), default=0)
    return TableFragment(
        fragment_id=ident, page_number=page, ordinal=ordinal, normalized_bbox=box or (0, 0, 0, 0),
        num_rows=height, num_cols=width, rows=rows, column_boundaries=[], markdown=rendered,
        rendered=f"<!-- table-fragment: {ident} -->\n\n{rendered}", source_kind=branch,
        cells=projected, has_column_header=bool(header_depth),
        header_scope_complete=bool(header_depth) and all(cell.is_column_header for cell in projected if cell.row < header_depth),
        caption_scope_complete=False,
        native_evidence={"native_path": block["native_path"], "source_cells": copy.deepcopy(cells),
                         "native_references": copy.deepcopy(block.get("native_references", {})),
                         "coordinate_status": "known" if box else "unknown", "display_column_boundaries": "not_inferred"},
    )

def _inline_media(text):
    """Read textual image declarations; never load their targets."""
    protected = code_ranges(text)
    pattern = re.compile(r'!\[([^\]\n]*)\]\(([^()\s]+)(?:\s+"[^"\n]*")?\)')
    occurrences = []
    for match in pattern.finditer(text):
        if any(a <= match.start() < b for a, b in protected):
            continue
        occurrences.append((*match.span(), match[1], match[2]))

    class ImageDeclaration(HTMLParser):
        attributes = None

        def handle_starttag(self, tag, attrs):
            if tag == "img":
                self.attributes = dict(attrs)

    for match in re.finditer(r"<img\b[^>]*>", text, re.I):
        if any(a <= match.start() < b for a, b in protected):
            continue
        declaration = ImageDeclaration()
        declaration.feed(match[0])
        attrs = declaration.attributes or {}
        occurrences.append((*match.span(), attrs.get("alt") or "", attrs.get("src")))
    pieces: list[str] = []
    refs: list[dict[str, Any]] = []
    cursor = 0
    for start, end, alt, reference in sorted(occurrences):
        if start < cursor:
            continue
        pieces.extend((text[cursor:start], "图片未交付。" + _literal(alt)))
        refs.append({"reference": audit_copy(reference), "source_text_span": [start, end]})
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces), refs

def _box(block: Mapping[str, Any]):
    if block.get('geometry_status') == 'unknown':
        return None
    if block.get("coordinate_system") in {"pdf_points", "pixel"}:
        dimensions = block.get("page_dimensions")
        if not isinstance(dimensions, Mapping) or any(
            type(dimensions.get(k)) not in {int, float}
            or not math.isfinite(dimensions[k])
            or dimensions[k] <= 0
            for k in ("width", "height")
        ):
            return None
    if block.get("coordinate_system") == "pdf_points" and block.get("coordinate_origin") not in {
        "TOPLEFT",
        "TOP_LEFT",
        "BOTTOMLEFT",
        "BOTTOM_LEFT",
    }:
        return None
    return normalized_box(block)

def render_native_blocks(blocks, number, branch, containers, *, include_source_markers):
    pieces: list[str] = []
    fragments: list[TableFragment] = []
    furniture: list[PageFurnitureFragment] = []
    media: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    parents = {b["id"]: b for b in [*containers, *blocks]}
    table_captions = {
        ref
        for b in blocks
        if b.get("kind") == "table"
        for ref in b.get("native_references", {}).get("captions", [])
    }
    table_notes = {
        ref
        for b in blocks
        if b.get("kind") == "table"
        for ref in b.get("native_references", {}).get("footnotes", [])
    }
    offset = 0
    for block in blocks:
        payload = block.get("native_payload")
        payload = payload if isinstance(payload, Mapping) else {}
        kind = block.get("kind", "unknown")
        role = _ROLES.get(kind, "unknown")
        if block["id"] in table_captions:
            role = "table_caption"
        elif block["id"] in table_notes:
            role = "table_footnote"
        if block.get("read_error"):
            issues.append({"native_path": block["native_path"], "code": block["read_error"]})
        if role == "unknown":
            issues.append(
                {
                    "native_path": block["native_path"],
                    "code": "unsupported_native_role",
                    "native_label": kind,
                }
            )
        text = block.get("text", "")
        if not isinstance(text, str):
            raise TypeError("reader returned non-text service content")
        rendered = _literal(text) if block.get("text_format", "plain") == "plain" else text
        inline_media = []
        if block.get("text_format") == "markdown":
            rendered, inline_media = _inline_media(rendered)
            if inline_media and role != "image":
                for reference in inline_media:
                    media.append(
                        {
                            **reference,
                            "native_path": block["native_path"],
                            "page": number,
                            "branch": branch,
                            "status": "unverified_not_delivered",
                            "bytes_accessed": False,
                        }
                    )
                issues.append(
                    {"native_path": block["native_path"], "code": "saved_native_media_unverified"}
                )
        if not rendered and role == "unknown":
            rendered = "此处内容未完成。"
        fragment = None
        if role == "table":
            if any(
                c.get("native_rich_content") and c.get("native_rich_text") != c.get("text")
                for c in block.get("cells", [])
            ):
                block["read_error"] = "rich_cell_reference_requires_projection"
                issues.append({"native_path": block["native_path"], "code": block["read_error"]})
            if not block.get("read_error"):
                try:
                    fragment = _table(block, number, len(fragments) + 1, branch)
                except NativeReadError as exc:
                    issues.append(
                        {
                            "native_path": block["native_path"],
                            "code": "native_table_projection_gap",
                            "reason": str(exc),
                        }
                    )
            if fragment is not None and branch == "docling":
                declared = block.get("native_table_data", {})
                if any(type(declared.get(k)) is not int for k in ("num_rows", "num_cols")) or (
                    declared.get("num_rows"),
                    declared.get("num_cols"),
                ) != (
                    fragment.num_rows,
                    fragment.num_cols,
                ):
                    fragment = None
                    issues.append(
                        {
                            "native_path": block["native_path"],
                            "code": "native_table_dimension_conflict",
                        }
                    )
            if fragment is not None:
                fragment.native_evidence["saved_structure"] = {
                    "format_family": branch,
                    "branch": branch,
                    "cell_identity": "native_json_cells"
                    if branch == "docling"
                    else "primary_html_cells" if block.get('text_format') == 'html' else 'primary_gfm_cells',
                }
                fragment.native_evidence["coordinate_status"] = (
                    "known" if _box(block) else "unknown"
                )
                for source, cell in zip(block["cells"], fragment.cells, strict=True):
                    cell.normalized_bbox = _box(source)
                fragment.normalized_bbox = _box(block) or (0, 0, 0, 0)
                block["service_fragment_id"] = fragment.fragment_id
                fragments.append(fragment)
                rendered = fragment.rendered
            else:
                role = "unknown"
                if not text:
                    text = "\n\n".join(
                        value
                        for c in block.get("cells", [])
                        for value in dict.fromkeys(
                            v
                            for v in (c.get("text"), c.get("native_rich_text"))
                            if isinstance(v, str) and v
                        )
                    )
                rendered = _literal(text)
                if not rendered:
                    rendered = "此处表格内容未完成。"
                issues.append(
                    {"native_path": block["native_path"], "code": "table_structure_unresolved"}
                )
        elif (
            role == "text"
            and block.get("cells")
            and not any(
                c.get("is_column_header") or c.get("is_row_header") or c.get("native_header_tag")
                for c in block["cells"]
            )
        ):
            # The primary region declares prose. DOM order is available; no
            # field/value relationship is inferred from this layout grid.
            role = "grid_layout"
            rendered = "\n\n".join(_literal(c["text"]) for c in block["cells"] if c.get("text"))
            block["layout_order_basis"] = "primary_text_role_and_html_dom_order"
        elif role == "title" and text:
            level = payload.get("level", 1 if kind == "doc_title" else 2)
            if type(level) is not int or not 1 <= level <= 6:
                level = 2
            if not rendered.lstrip().startswith("#"):
                rendered = "#" * level + " " + rendered
        elif role == "list_item" and text:
            marker = payload.get("marker")
            if isinstance(marker, str) and marker and marker not in {"-", "*", "+", "•"}:
                printed_prefix = r"^\s*" + r"\s*".join(re.escape(char) for char in marker)
                if not re.match(printed_prefix, text):
                    rendered = _literal(marker) + " " + rendered
            chain, seen = [], set()
            parent = block.get("parent_id")
            while parent in parents and parent not in seen:
                seen.add(parent)
                chain.append(parents[parent])
                parent = parents[parent].get("parent_id")
            depth = max(
                0, sum(p.get("label", p.get("kind")) in {"list", "ordered_list"} for p in chain) - 1
            )
            block["list_depth"] = depth
            rendered = (
                " " * (4 * depth) + "- " + rendered.replace("\n", "\n" + " " * (4 * depth + 2))
            )
        elif role == "image":
            reference = block.get("asset") or payload.get("image_path")
            if not reference and inline_media:
                reference = inline_media[0]["reference"]
            image = payload.get("image", {})
            if not reference and isinstance(image, Mapping):
                reference = image.get("uri")
            declared = {
                "native_path": block["native_path"],
                "page": number,
                "branch": branch,
                "reference": reference,
                "status": "unverified_not_delivered",
                "bytes_accessed": False,
                "bbox": _box(block),
                "inline_references": inline_media,
            }
            if isinstance(block.get('geometry_basis'), Mapping):
                # A producer-raster declaration is not a source crop target.
                # Keep this geometry even when its input transform is unknown.
                declared['native_geometry'] = {
                    'normalized_bbox': normalized_box(block) if block.get('native_bbox_status') == 'known' else None,
                    'frame': 'producer_output_raster',
                    'input_transform': block['geometry_basis'].get('input_transform', 'unknown'),
                    'original_pdf_transform': block['geometry_basis'].get('original_pdf_transform', 'unknown'),
                }
            media.append(declared)
            block["media"] = declared
            if not inline_media:
                rendered = "\n\n".join(p for p in ("图片未交付。", rendered) if p)
            issues.append(
                {"native_path": block["native_path"], "code": "saved_native_media_unverified"}
            )
        if role in {"header", "footer", "page_number"} and rendered:
            furniture.append(
                PageFurnitureFragment(
                    block["native_path"], number, role, text, rendered, _box(block)
                )
            )
        if block.get("bbox") is not None and _box(block) is None:
            issues.append(
                {
                    "native_path": block["native_path"],
                    "code": "native_geometry_unknown_or_conflicting",
                }
            )
        block.update(
            type=role,
            content=text,
            markdown=rendered,
            service_rendered=rendered,
            native_branch=branch,
            service_bbox=_box(block),
            geometry_frame=block.get('native_geometry_frame', "frozen_oriented_input"),
            inline_media_references=inline_media,
            native_text_span=[0, len(block.get("text", ""))],
            read_status="unresolved" if block.get("read_error") or role == "unknown" else "read",
        )
        if rendered and include_source_markers:
            marker_id = hashlib.sha256(
                f"{number}:{block.get('occurrence_id', block['id'])}".encode()
            ).hexdigest()
            marker = f"<!-- source-text: {marker_id} -->"
            block["service_marker"] = marker
            block["service_rendered"] = rendered + marker
            if pieces:
                offset += 2
            block["adapted_span"] = [offset, offset + len(rendered) + len(marker)]
            pieces.append(rendered + marker)
            offset += len(rendered) + len(marker)
        elif rendered:
            if pieces:
                offset += 2
            block["adapted_span"] = [offset, offset + len(rendered)]
            pieces.append(rendered)
            offset += len(rendered)
    return "\n\n".join(pieces), fragments, furniture, media, issues
