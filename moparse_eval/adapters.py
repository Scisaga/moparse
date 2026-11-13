"""Lossless observations of candidate output; no expected-result access.

These readers expose only fields already returned by a backend. A backend's
``table`` label remains a producer label, not a semantic classification.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.adapters.native_readers import (
    NativeReadError as NativeReadError,
)
from app.adapters.native_readers import (
    _block,
    _identity,
    _position,
    _sequence,
    glm_regions,
    read_docling,
    read_mineru,
    read_paddle,
    read_visual,
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




READERS = {"docling": read_docling, "glm": read_glm, "paddle": read_paddle,
           "mineru": read_mineru, "visual": read_visual}
