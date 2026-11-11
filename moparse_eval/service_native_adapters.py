"""Saved-format service bridges, without parsers, source files or references.

Backend-owned blocks and cells remain in the audit view. The service's smaller
table model is a consumer projection, never the replacement for those objects.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from app.parsers.mineru_native_remote import MinerUPictureCandidate
from app.services.native_content_service import _cell_text, _flag, _table, normalized_box
from app.services.native_text_service import _literal as render_literal
from app.services.table_service import PageFurnitureFragment, TableCellFragment, TableFragment

from .adapters import NativeReadError, read_docling, read_paddle

PIPELINE_BRANCHES = {
    "P01": {"docling", "glm"}, "P02": {"docling", "glm"},
    "P03": {"paddle"}, "P04": {"paddle"}, "P05": {"glm"},
    "P06": {"mineru", "glm"}, "P07": {"mineru", "glm"}, "P08": {"visual"},
}
PIPELINE_BACKENDS = {
    "P01": "docling-tableformer-v1", "P02": "docling-tableformer-v2",
    "P03": "paddleocr-vl-1.5", "P04": "paddleocr-vl-1.6", "P05": "glm-sdk-remote",
    "P06": "mineru-standard-txt", "P07": "mineru-advanced-txt", "P08": "mineru-visual",
}


def branch_capabilities(pipeline: str, branch: str) -> dict[str, Any]:
    if branch not in PIPELINE_BRANCHES.get(pipeline, set()):
        raise ValueError("saved branch is outside its declared pipeline")
    native = branch in {"docling", "mineru"}
    return {"branch": branch, "pdf_text": native, "pdf_vector": native,
            "raster_assets": True, "saved_assets": True, "model_inference": False,
            "references": False, "basis": "declared_saved_pipeline_branch"}


def permitted_pages(bridge: Mapping[str, Any], capability: str) -> set[int]:
    if capability not in {"pdf_text", "pdf_vector", "raster_assets", "saved_assets"}:
        raise ValueError("unknown service source capability")
    return {item["raw_page"] for item in bridge.get("pages", [])
            if type(item.get("raw_page")) is int and item.get("capabilities", {}).get(capability) is True}










def attach_source_tables(fragments: list[TableFragment], blocks: list[dict[str, Any]]) -> None:
    """Attach the matching original table object by structural ordinal only."""
    tables = [block for block in blocks if block.get("kind") in {"table", "table_body"}]
    for fragment in fragments:
        ordinal = fragment.ordinal - 1
        if ordinal >= len(tables):
            continue
        own = tables[ordinal]
        cells = own.get("cells", [])
        fragment.native_evidence.update(native_path=own["native_path"], source_cells=copy.deepcopy(cells),
                                        native_references=copy.deepcopy(own.get("native_references", {})))
        if cells:
            fragment.cells = [TableCellFragment(row=cell["row"], column=cell["col"],
                row_span=cell.get("row_span", 1), column_span=cell.get("col_span", 1),
                text=_cell_text(cell), is_column_header=_flag(cell, "is_column_header", "column_header"),
                is_row_header=_flag(cell, "is_row_header", "row_header")) for cell in cells]
            depth = max((cell.row + cell.row_span for cell in fragment.cells if cell.is_column_header), default=0)
            fragment.has_column_header = bool(depth)
            fragment.header_scope_complete = bool(depth) and all(cell.is_column_header for cell in fragment.cells if cell.row < depth)
        fragment.column_boundaries = []




def render_saved_page(raw: Mapping[str, Any], page: int, branch: str, pointer: str,
                      *, emitted: set[str] | None = None) -> dict[str, Any]:
    """Read Docling/Paddle's own structures; do not invoke a converter."""
    containers: list[dict[str, Any]] = []
    if branch == "docling":
        blocks = read_docling(raw, page, pointer, emitted=emitted, containers=containers)
    elif branch == "paddle":
        payload = raw.get("res", raw)
        dimensions = {"width": payload.get("width"), "height": payload.get("height"), "unit": "pixel"}
        blocks = read_paddle(raw, page, pointer, page_dimensions=dimensions)
    else:
        raise ValueError("this bridge accepts only Docling or Paddle saved objects")
    for block in blocks:
        value: Any = raw
        suffix = block["native_path"][len(pointer):].lstrip("/")
        for token in suffix.split("/") if suffix else []:
            if isinstance(value, Mapping):
                value = value.get(token.replace("~1", "/").replace("~0", "~"))
            elif isinstance(value, list) and token.isdecimal() and int(token) < len(value):
                value = value[int(token)]
            else:
                value = None
                break
        block["native_payload"] = copy.deepcopy(value)
    pieces, fragments, pictures, furniture, errors = [], [], [], [], []
    for block in blocks:
        kind, text = block.get("kind", "unknown"), block.get("text", "")
        original_text = text
        if block.get("read_error") or block.get("read_errors"):
            errors.append({"native_path": block["native_path"], "reason": block.get("read_error", "native_cell_unreadable")})
        try:
            fragment = _table(block, page, len(fragments) + 1, branch)
        except (NativeReadError, ValueError, TypeError, KeyError, IndexError) as error:
            fragment = None
            errors.append({"native_path": block["native_path"], "reason": str(error), "stage": "saved_table_projection"})
            # Retain the actual literal cells and surrounding blocks. This is
            # an unresolved serialization view, never a recovered grid/record.
            if not text:
                text = "\n\n".join(_cell_text(cell) for cell in block.get("cells", []))
        if fragment is None and block.get("text_format") == "plain":
            text = render_literal(text)
        if fragment is not None:
            fragments.append(fragment)
            text = fragment.rendered
        elif kind in {"picture", "image", "chart"}:
            box = normalized_box(block)
            if box is not None:
                caption = block.get("caption")
                pictures.append(MinerUPictureCandidate(page, len(pictures), caption if isinstance(caption, str) else "", box,
                                                       allow_description=False))
            text = "<!-- image -->" + ("\n\n" + text if text else "")
        elif kind in {"section_header", "title", "doc_title", "paragraph_title"} and text:
            level = block.get("level")
            level = level if type(level) is int and 1 <= level <= 6 else 1 if kind == "doc_title" else 2
            text = text if block.get("text_format") != "plain" and text.lstrip().startswith("#") else "#" * level + " " + text
        elif kind == "list_item" and text:
            text = "- " + text
        if kind in {"page_header", "page_footer", "page_number", "header", "footer", "number"} and text:
            furniture.append(PageFurnitureFragment(block["native_path"], page, kind, original_text, text, normalized_box(block)))
        if text:
            pieces.append(text)
        block["service_rendered"] = text
    return {"markdown": "\n\n".join(pieces), "blocks": blocks, "containers": containers,
            "fragments": fragments, "pictures": pictures, "furniture": furniture, "errors": errors,
            "source_envelope": {key: copy.deepcopy(raw[key]) for key in ("status", "errors", "research_group_pages") if key in raw}}
