"""Source-only Paddle format projection; group/rank fields grant no parent/read order."""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping

from app.adapters.native_readers import (
    NativeReadError,
    audit_copy,
    html_cells,
    markdown_cells,
    read_paddle,
    resolve_pointer,
)


def paddle_geometry(payload, region):
    """Pixel basis is the producer format, never a guess from numeric range."""
    dimensions = {key: payload.get(key) for key in ("width", "height")}
    dimensions["unit"] = "pixel"
    settings = payload.get("model_settings", {})
    settings = settings if isinstance(settings, Mapping) else {}
    same_frame = settings.get("use_doc_preprocessor") is False or (
        settings.get("use_doc_orientation_classify") is False
        and settings.get("use_doc_unwarping") is False
    )

    def finite(value):
        return type(value) in {int, float} and math.isfinite(value)

    size_known = all(finite(dimensions[k]) and dimensions[k] > 0 for k in ("width", "height"))
    box = region.get("block_bbox")
    box_valid = (
        isinstance(box, (list, tuple))
        and len(box) == 4
        and all(finite(n) for n in box)
        and box[0] < box[2]
        and box[1] < box[3]
        and size_known
        and 0 <= box[0] < box[2] <= dimensions["width"]
        and 0 <= box[1] < box[3] <= dimensions["height"]
    )
    polygon_fields = {
        k: copy.deepcopy(region[k])
        for k in ("block_polygon_points", "block_polygon", "polygon")
        if k in region
    }
    polygon = next(iter(polygon_fields.values()), None)
    points_valid = (
        isinstance(polygon, list)
        and len(polygon) >= 3
        and all(
            isinstance(p, (list, tuple)) and len(p) == 2 and all(finite(n) for n in p)
            for p in polygon
        )
    )
    if isinstance(polygon, list) and points_valid and size_known:
        points_valid = all(
            0 <= x <= dimensions["width"] and 0 <= y <= dimensions["height"] for x, y in polygon
        )
        area = sum(
            a[0] * b[1] - b[0] * a[1]
            for a, b in zip(polygon, [*polygon[1:], polygon[0]], strict=True)
        )
        points_valid = points_valid and area != 0
    return {
        "coordinate_system": "pixel",
        "coordinate_origin": "TOPLEFT",
        "page_dimensions": dimensions,
        "polygon": polygon,
        "native_polygon_fields": polygon_fields,
        "polygon_status": "known"
        if points_valid
        else "unknown"
        if polygon_fields
        else "not_available",
        "geometry_status": "known" if same_frame and box_valid else "unknown",
        "native_bbox_status": "known" if box_valid else "unknown",
        "native_geometry_frame": "frozen_oriented_input"
        if same_frame
        else "paddle_raster_unknown_input_transform",
        "geometry_basis": {
            "format": "paddleocr_vl_pixel_layout",
            "input_transform": "identity" if same_frame else "unknown",
            "original_pdf_transform": "unknown",
            "bbox_polygon_relation": "separate_native_observations",
        },
    }


def paddle_group_identity(page, region):
    """Page-scoped observed grouping, explicitly not a semantic parent."""
    if "group_id" not in region or region["group_id"] is None:
        return None
    return {
        "input_page": page,
        "native_group_id": copy.deepcopy(region["group_id"]),
        "kind": "native_group_value_only",
        "parent_relationship": "unknown",
        "cross_page_relationship": "unknown",
    }


def paddle_execution_states(raw, pointer):
    """Preserve original state only, with batch paths rather than guessed SDK IDs."""
    records = []
    keys = {
        "status",
        "error",
        "errors",
        "warnings",
        "truncated",
        "timed_out",
        "stop_reason",
        "unprocessed_pages",
        "processed",
        "reached_max_new_tokens",
        "ended_with_eos",
            "possible_length_truncation",
            "length_limit_reached",
            "eos_token_observed",
            "stop_reason_scope",
    }

    def add(node, path):
        metadata = {k: audit_copy(node[k]) for k in keys if k in node}
        if metadata:
            records.append(
                {
                    "native_path": path,
                    "metadata": metadata,
                    "scope": "native_page_or_generation_batch; no inferred SDK-region binding",
                }
            )

    add(raw, pointer)
    payload = raw.get("res", raw)
    if isinstance(payload, Mapping) and payload is not raw:
        add(payload, pointer + "/res")

    def visit(node, path):
        if isinstance(node, Mapping):
            add(node, path)
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    visit(value, path + "/" + str(key).replace("~", "~0").replace("/", "~1"))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, path + "/" + str(index))

    runtime = raw.get("research_inference_runtime", {})
    if isinstance(runtime, Mapping):
        visit(
            runtime.get("generation_observations"),
            pointer + "/research_inference_runtime/generation_observations",
        )
    return records


def read_paddle_blocks(native, raw, number, pointer):
    payload = raw.get("res", raw)
    if not isinstance(payload, Mapping):
        raise NativeReadError("paddle_page_wrapper_not_an_object")
    blocks = copy.deepcopy(read_paddle(raw, number, pointer))
    local = payload.get("page_index")
    local = local if type(local) is int and local >= 0 else None
    for ordinal, block in enumerate(blocks):
        own = block["native_path"]
        node = resolve_pointer(native, own)
        block.update(
            id=own,
            native_payload=audit_copy(node),
            branch_page=local,
            page=number,
            source_view="res.parsing_res_list" if "res" in raw else "parsing_res_list",
            order_basis="native_array_order_unknown_reading_order",
            parent_id=None,
            native_array_position=ordinal,
        )
        uncertainties = ["native_reading_order_unverified"]
        if isinstance(node, Mapping):
            block.update(
                native_block_id=copy.deepcopy(node.get("block_id")),
                native_block_order=copy.deepcopy(node.get("block_order")),
                native_group_id=copy.deepcopy(node.get("group_id")),
                group_identity=paddle_group_identity(number, node),
                native_field_presence={
                    k: k in node
                    for k in ("block_id", "block_order", "group_id", "block_polygon_points")
                },
            )
            geometry = paddle_geometry(payload, node)
            block.update(geometry)
            block["provenance"] = [
                {
                    "page_no": number,
                    "source": "declared_paddle_image_call",
                    "bbox": copy.deepcopy(node.get("block_bbox")),
                    "coordinate_system": "pixel",
                    "coordinate_origin": "TOPLEFT",
                    "page_dimensions": geometry["page_dimensions"],
                    "input_transform": geometry["geometry_basis"]["input_transform"],
                }
            ]
            if geometry["geometry_status"] != "known":
                uncertainties.append("native_geometry_transform_unknown")
            if geometry["polygon_status"] == "unknown":
                uncertainties.append("native_polygon_unresolved")
            if "group_id" in node and node["group_id"] is not None:
                uncertainties.append("native_group_semantics_unknown")
            if not isinstance(node.get("block_content", ""), (str, type(None))):
                block["read_error"] = "paddle_region_content_not_text"
            if re.search(r"<table\b", block["text"], re.I) and block.get("text_format") != "html":
                block["text_format"] = "html"
                try:
                    block["cells"] = html_cells(block["text"], own + "/block_content")
                except (NativeReadError, ValueError) as exc:
                    block["read_error"] = str(exc)
            # Research readback policy is unchanged. This service projection
            # decodes explicit Markdown cells when the primary body is GFM.
            if block["kind"] == "table" and not re.search(r"<table\b", block["text"], re.I):
                block["text_format"] = "markdown"
                block["cells"] = markdown_cells(block["text"], own + "/block_content")
                if block["cells"] and isinstance(node.get("block_content"), str):
                    # The inherited HTML syntax attempt is superseded by a
                    # successful GFM parse of this same primary literal.
                    block.pop("read_error", None)
                    block.pop("read_error_category", None)
            for cell in block.get("cells", []):
                cell["source_locator"] = {
                    "json_pointer": own + "/block_content",
                    "syntax_path": cell["native_path"].split("::html", 1)[-1],
                    "kind": "primary_html_projection"
                    if block["text_format"] == "html"
                    else "primary_gfm_projection",
                }
        else:
            block["source_view"] = "res.parsing_res_list" if "res" in raw else "parsing_res_list"
        block["source_uncertainties"] = uncertainties
    return blocks
