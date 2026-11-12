"""Lossless observations of candidate output; no expected-result access.

These readers expose only fields already returned by a backend. A backend's
``table`` label remains a producer label, not a semantic classification.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.adapters.native_readers import (
    NativeReadError,
    _block,
    _identity,
    _position,
    _sequence,
    glm_regions,
    read_docling,
    read_paddle,
)
from app.adapters.native_readers import (
    _docling_cell_fields as _docling_cell_fields,
)
from app.adapters.native_readers import (
    _docling_reference as _docling_reference,
)
from app.adapters.native_readers import (
    _docling_reference_content as _docling_reference_content,
)
from app.adapters.native_readers import (
    _HTMLCells as _HTMLCells,
)
from app.adapters.native_readers import (
    html_cells as html_cells,
)
from app.adapters.native_readers import (
    markdown_cells as markdown_cells,
)


def read_glm(raw: Mapping[str, Any], page_number: int,
             pointer: str = "#/glm", *, page_dimensions: Mapping[str, Any] | None = None,
             source_view: str = "json_result",
             **_: Any) -> list[dict[str, Any]]:
    layout_key = source_view if source_view in raw else "layout_details"
    regions = glm_regions(raw.get(layout_key, []), f"{pointer}/{layout_key}")
    blocks = []
    for index, (region_path, region) in enumerate(regions):
        if not isinstance(region, Mapping):
            blocks.append({"id": f"p{page_number}-glm-{index}", "kind": "unknown",
                           "text": "", "native_path": region_path,
                           "read_error": "non-object region", "structure_status": "unknown",
                           "read_error_category": "candidate_native_structure"})
            continue
        block = _block(region, f"p{page_number}-glm-{index}",
                       region_path,
                       kind=str(region.get("label", region.get("native_label", "unknown"))),
                       text=region.get("content", ""), box=region.get("bbox_2d"), text_format="markdown")
        _identity(block, region, region_path)
        block["source_view"] = layout_key
        _position(block, system="normalized_1000", page=page_number, dimensions=page_dimensions)
        _sequence(block, [page_number, index])
        if "polygon" in region:
            block["polygon"] = region["polygon"]
        if region.get("image_path"):
            block["native_image_path"] = region["image_path"]
            media = raw.get("image_files", {})
            name = str(region["image_path"])
            if media.get(name) or media.get(name.rsplit("/", 1)[-1]):
                block["asset"] = media.get(name, media.get(name.rsplit("/", 1)[-1]))
        blocks.append(block)
    return blocks


def read_visual(raw: list[dict[str, Any]], page_number: int,
                pointer: str = "#/visual", *, page_dimensions: Mapping[str, Any] | None = None,
                **_: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for index, region in enumerate(raw):
        if not isinstance(region, Mapping):
            blocks.append({"id": f"{pointer}/{index}", "kind": "unknown", "text": "",
                           "native_path": f"{pointer}/{index}", "page": page_number,
                           "native_sequence": [page_number, index], "structure_status": "unknown",
                           "read_error": "non-object native visual region",
                           "read_error_category": "candidate_native_structure"})
            continue
        block = _block(region, f"p{page_number}-visual-{index}", f"{pointer}/{index}",
                       kind=str(region.get("type", "unknown")),
                       text=region.get("content", ""), box=region.get("bbox"), text_format="markdown")
        _identity(block, region, f"{pointer}/{index}")
        _position(block, system="normalized", page=page_number, dimensions=page_dimensions)
        _sequence(block, [page_number, index])
        blocks.append(block)
    return blocks

def read_mineru(raw: Mapping[str, Any], page_number: int,
                pointer: str = "#/mineru", *, page_dimensions: Mapping[str, Any] | None = None,
                containers: list[dict[str, Any]] | None = None, **_: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    def inline_text(spans: list[Any], path: str) -> tuple[str, list[dict[str, Any]]]:
        parts, annotations = [], []
        offset = 0
        for index, span in enumerate(spans):
            if not isinstance(span, Mapping):
                raise NativeReadError("MinerU inline span is not an object")
            span_path = f"{path}/{index}"
            content = span.get("content", "")
            if isinstance(content, list):
                text, children = inline_text(content, span_path + "/content")
                for child in children:
                    child["span"] = [value + offset for value in child["span"]]
                annotations.extend(children)
            elif isinstance(content, str):
                text = content
            else:
                raise NativeReadError("MinerU inline span has unsupported content")
            for style in span.get("styles", []):
                annotations.append({"type": style, "span": [offset, offset + len(text)],
                                    "text": text, "native_path": span_path})
            if span.get("type") == "hyperlink":
                annotations.append({"type": "link", "span": [offset, offset + len(text)],
                                    "text": text, "target": span.get("url"), "native_path": span_path})
            parts.append(text)
            offset += len(text)
        return "".join(parts), annotations

    def visit(items: list[Any], path: str, parent: str | None = None) -> None:
        for index, item in enumerate(items):
            item_path = f"{path}/{index}"
            try:
                visit_one(item, item_path, parent)
            except (NativeReadError, TypeError, ValueError, KeyError, IndexError) as exc:
                blocks.append({"id": item_path, "kind": "unknown", "text": "",
                               "native_path": item_path, "parent_id": parent,
                               "page": page_number, "provenance_pages": [page_number],
                               "native_sequence": [page_number, len(blocks)],
                               "structure_status": "unknown", "read_error": str(exc),
                               "read_error_category": "candidate_native_structure"
                                   if isinstance(exc, NativeReadError) else "engineering_failure"})

    def visit_one(item: Any, item_path: str, parent: str | None) -> None:
        if not isinstance(item, Mapping):
            raise NativeReadError("non-object native MinerU region")
        content = item.get("content")
        if isinstance(content, list) and item.get("type") in {"image", "table", "chart", "code", "list", "index"}:
            container = {"id": item_path, "native_path": item_path,
                "label": item.get("type"), "parent_id": parent,
                "native_children": [f"{item_path}/content/{n}" for n in range(len(content))],
                "native_sequence": [page_number, len(blocks)], "provenance_pages": [page_number]}
            if containers is not None:
                containers.append(container)
            # Read body/caption/footnote at their actual native pointers.
            # The container's rendered Markdown is a display view and may
            # have replaced HTML tables with GFM; never prefer it here.
            visit(content, item_path + "/content", item_path)
            if not content and item.get("markdown"):
                block = _block(item, item_path, item_path, kind=str(item.get("type", "unknown")),
                               text=item["markdown"], box=item.get("bbox"),
                               text_pointer=item_path + "/markdown", text_format="markdown")
                _identity(block, item, item_path)
                _position(block, system="normalized", page=page_number, dimensions=page_dimensions)
                block["parent_id"] = parent
                _sequence(block, [page_number, len(blocks)])
                blocks.append(block)
        else:
            # Native scalar HTML/text precedes the renderer view. Inline
            # typed spans remain available verbatim in native_content.
            inline: list[dict[str, Any]] = []
            if isinstance(content, list):
                text, inline = inline_text(content, item_path + "/content")
            else:
                text = content if isinstance(content, str) else item.get("markdown", "")
            block = _block(item, item_path, item_path, kind=str(item.get("type", "unknown")),
                           text=text, box=item.get("bbox"), text_pointer=item_path + "/content",
                           text_format="html" if item.get("type") == "table_body" else
                               "plain" if isinstance(content, (str, list)) else "markdown")
            _identity(block, item, item_path)
            _position(block, system="normalized", page=page_number, dimensions=page_dimensions)
            block["native_content"] = content
            if inline:
                block["inline_annotations"] = inline
            block["parent_id"] = parent
            _sequence(block, [page_number, len(blocks)])
            if block.get("cells") and parent:
                block["native_table_container"] = parent
            blocks.append(block)
    visit(raw.get("blocks", []), pointer + "/blocks")
    return blocks

READERS = {"docling": read_docling, "glm": read_glm, "paddle": read_paddle,
           "mineru": read_mineru, "visual": read_visual}
