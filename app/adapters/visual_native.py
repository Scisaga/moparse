"""Saved visual SDK regions; no source, OCR, model, media or geometry inference."""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping

from app.adapters.native_readers import NativeReadError, audit_copy, html_cells, read_visual

STATE_FIELDS = (
    "status",
    "error",
    "errors",
    "warnings",
    "timed_out",
    "truncated",
    "stop_reason",
    "unprocessed_pages",
    "processed",
    "length_limit_reached",
    "possible_length_truncation",
    "research_export_errors",
)
MEDIA_FIELDS = ("research_asset", "research_assets", "asset", "image_path", "uri", "image")
RELATION_FIELDS = (
    "parent",
    "parent_id",
    "children",
    "group",
    "group_id",
    "reading_order",
    "index",
    "merge_prev",
    "continues_prev",
    "references",
)
DESCRIPTION_ROLES = {
    "image",
    "picture",
    "figure",
    "chart",
    "description",
    "model_description",
    "image_description",
    "chart_description",
}


def text_components(node, path):
    """String field offsets are not document charspans or OCR verification."""
    output = []
    for field in ("content", "description", "caption", "label"):
        if not isinstance(node.get(field), str):
            continue
        kind = (
            "model_description"
            if field == "description"
            or field == "content"
            and node.get("type") in DESCRIPTION_ROLES
            else "native_region_label"
            if field == "label"
            or field == "content"
            and node.get("type") in {"label", "region_label"}
            else "native_caption"
            if field == "caption" or "caption" in str(node.get("type", ""))
            else "native_text"
        )
        output.append(
            {
                "native_path": path + "/" + field,
                "field": field,
                "text": node[field],
                "source_type": kind,
                "origin": "visual_model_description"
                if kind == "model_description"
                else "visual_model_recognition"
                if field == "content"
                else "native_field_declaration",
                "verification": "not_verified_against_original",
                "charspan": None,
            }
        )
    return output


def visual_geometry(root, entry, node):
    """Only a fixed SDK contract or explicit fields establish coordinate units."""
    config = root.get("config", {})
    versions = config.get("versions", {}) if isinstance(config, Mapping) else {}
    fixed = isinstance(versions, Mapping) and versions.get("mineru-vl-utils") == "2.0.7"
    system = node.get("coordinate_system", "normalized" if fixed else "unknown")
    origin = node.get("coordinate_origin", "TOPLEFT" if fixed else "UNKNOWN")
    processing = [
        p
        for p in root.get("page_processing", [])
        if isinstance(p, Mapping) and p.get("page") == entry["page"]
    ]
    proc = processing[0] if len(processing) == 1 else {}
    dimensions = {k: proc.get(k) for k in ("width", "height")}
    dimensions["unit"] = "pixel" if proc else "unknown"
    box = node.get("bbox")
    valid = (
        isinstance(box, (list, tuple))
        and len(box) == 4
        and all(type(v) in {int, float} and math.isfinite(v) for v in box)
        and 0 <= box[0] < box[2] <= 1
        and 0 <= box[1] < box[3] <= 1
    )
    known = valid and system in {"normalized", "normalized_1"} and origin == "TOPLEFT"
    # Never derive polygon vertices or a PDF transform from a bbox.
    polygons = {k: audit_copy(node[k]) for k in ("polygon", "coordinates") if k in node}
    return {
        "bbox": copy.deepcopy(box),
        "coordinate_system": system,
        "coordinate_origin": origin,
        "page_dimensions": dimensions,
        "native_polygon_fields": polygons,
        "polygon": copy.deepcopy(node.get("polygon")),
        "polygon_status": "unknown" if polygons else "not_available",
        "native_bbox_status": "known" if known else "unknown",
        "geometry_status": "known" if known else "unknown",
        "native_geometry_frame": "frozen_oriented_input"
        if proc
        else "visual_input_unknown_transform",
        "geometry_basis": {
            "format": "mineru_vl_utils.ContentBlock",
            "coordinate_basis": "explicit_native_fields"
            if "coordinate_system" in node
            else "fixed_sdk_2.0.7_contract"
            if fixed
            else "unknown",
            "input_transform": "saved_oriented_input" if proc else "unknown",
            "original_pdf_transform": "unknown",
            "saved_page_processing": audit_copy(proc),
            "block_angle": audit_copy(node.get("angle")),
            "bbox_polygon_relation": "not_inferred",
        },
    }


def visual_execution_states(root):
    records = []
    for pi, entry in enumerate(root.get("pages", [])):
        if not isinstance(entry, Mapping) or entry.get("branch") != "visual":
            continue
        nodes = [(f"#/pages/{pi}", entry)]
        raw = entry.get("raw")
        if isinstance(raw, list):
            nodes.extend(
                (f"#/pages/{pi}/raw/{i}", n) for i, n in enumerate(raw) if isinstance(n, Mapping)
            )
        for path, node in nodes:
            metadata = {k: audit_copy(node[k]) for k in STATE_FIELDS if k in node}
            if metadata:
                records.append(
                    {
                        "native_path": path,
                        "input_pages": [entry.get("page")],
                        "scope": "native_visual_execution",
                        "metadata": metadata,
                    }
                )
    return records


def read_visual_page(root, entry, position):
    raw = entry.get("raw")
    if not isinstance(raw, list):
        raise NativeReadError("visual_primary_blocks_not_a_list")
    path = f"#/pages/{position}/raw"
    # Share the existing syntax reader, retaining its research default policy.
    blocks = copy.deepcopy(read_visual(raw, entry["page"], path))
    for index, block in enumerate(blocks):
        obj = raw[index]
        node = obj if isinstance(obj, Mapping) else {}
        own = f"{path}/{index}"
        block.update(
            native_payload=audit_copy(obj),
            source_view="ContentBlock[]",
            branch_page=None,
            page=entry["page"],
            parent_id=None,
            native_array_position=index,
            native_sequence=[entry["page"], index],
            order_basis="native_array_order_unknown_reading_order",
            source_kind="native_visual_region",
            source_components=text_components(node, own),
            native_relations={k: audit_copy(node[k]) for k in RELATION_FIELDS if k in node},
            native_fields={k: audit_copy(node[k]) for k in node if k != "content"},
            native_content=audit_copy(node.get("content")),
            native_media_declaration={k: audit_copy(node[k]) for k in MEDIA_FIELDS if k in node},
            native_execution_state={k: audit_copy(node[k]) for k in STATE_FIELDS if k in node},
            character_provenance="not_available",
            ocr_verification="not_available",
        )
        block.update(visual_geometry(root, entry, node))
        if isinstance(obj, Mapping):
            block["text_format"] = (
                "html" if re.search(r"<table\b", block["text"], re.I) else "markdown"
            )
            if block["text_format"] == "html":
                try:
                    block["cells"] = html_cells(block["text"], own + "/content")
                except (NativeReadError, ValueError) as exc:
                    block["read_error"] = str(exc)
            if not isinstance(node.get("content"), (str, type(None))) or not isinstance(
                node.get("type"), str
            ):
                block["read_error"] = "malformed_visual_region"
            if node.get("content") is None and node.get("type") in {
                "text",
                "title",
                "doc_title",
                "paragraph_title",
                "table",
                "formula",
                "equation",
            }:
                block["read_error"] = "visual_recognized_content_unavailable"
        # Description strings never become a table/grid source.
        primary = next((c for c in block["source_components"] if c["field"] == "content"), None)
        if primary and primary["source_type"] in {"model_description", "native_region_label"}:
            block.pop("cells", None)
            block["text_format"] = "plain"
            block.pop("read_error", None)
            block.pop("read_error_category", None)
    return blocks
