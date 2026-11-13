"""Enumerate immutable visual input independently of adapted regions and IR."""

import re
from collections.abc import Mapping

from app.adapters.native_readers import NativeReadError, audit_copy, html_cells, markdown_cells


def inventory_visual(root, entry, position, add):
    page = entry["page"]
    base = f"#/pages/{position}"
    add(
        "metadata",
        base,
        page,
        "visual",
        None,
        view="visual_page_envelope",
        details={"purpose": "page_identity", "native_page": page, "array_position": position},
    )
    for i, proc in enumerate(root.get("page_processing", [])):
        if isinstance(proc, Mapping) and proc.get("page") == page:
            add(
                "metadata",
                f"#/page_processing/{i}",
                page,
                "visual",
                None,
                view="saved_processing",
                details={
                    "purpose": "saved_dimensions_and_transform_metadata",
                    "payload": audit_copy(proc),
                },
            )
    raw = entry.get("raw")
    if not isinstance(raw, list):
        return {"source_view": "ContentBlock[]", "reading_order": "unknown", "branch_page": None}
    for index, obj in enumerate(raw):
        path = f"{base}/raw/{index}"
        node = obj if isinstance(obj, Mapping) else {}
        role, content = str(node.get("type", "unknown")), node.get("content")
        text = content if isinstance(content, str) else ""
        kind = (
            "table"
            if role == "table"
            else "picture"
            if role in {"image", "picture", "figure", "chart"}
            else "content"
        )
        components = []
        for field in ("content", "description", "caption", "label"):
            value = node.get(field)
            if not isinstance(value, str):
                continue
            description = (
                field == "description"
                or field == "content"
                and role
                in {
                    "image",
                    "picture",
                    "figure",
                    "chart",
                    "description",
                    "model_description",
                    "image_description",
                    "chart_description",
                }
            )
            source_type = (
                "model_description"
                if description
                else "native_region_label"
                if field == "label" or field == "content" and role in {"label", "region_label"}
                else "native_caption"
                if field == "caption" or "caption" in role
                else "native_text"
            )
            component = {
                "native_path": path + "/" + field,
                "field": field,
                "text": value,
                "source_type": source_type,
                "origin": "visual_model_description"
                if description
                else "visual_model_recognition"
                if field == "content"
                else "native_field_declaration",
                "verification": "not_verified_against_original",
                "charspan": None,
            }
            components.append(component)
            add(
                "metadata",
                path + "/" + field,
                page,
                "visual",
                None,
                parent=path,
                text=value,
                view="ContentBlock[]",
                details={"purpose": "native_visual_text_component", **component},
            )
        primary = next((c for c in components if c["field"] == "content"), None)
        fmt = (
            None
            if not isinstance(obj, Mapping)
            else "plain"
            if primary and primary["source_type"] in {"model_description", "native_region_label"}
            else "html"
            if re.search(r"<table\b", text, re.I)
            else "markdown"
        )
        add(
            kind,
            path,
            page,
            "visual",
            None,
            text=text,
            order=(page, index),
            basis="native_array_order_unknown_reading_order",
            view="ContentBlock[]",
            details={
                "label": role,
                "array_position": index,
                "source_kind": "native_visual_region",
                "source_components": components,
                "field_presence": sorted(node),
                "text_format": fmt,
                "native_fields": {k: audit_copy(node[k]) for k in node if k != "content"},
                "requires_read_failure": not isinstance(obj, Mapping)
                or not isinstance(content, (str, type(None)))
                or not isinstance(node.get("type"), str)
                or content is None
                and role
                in {
                    "text",
                    "title",
                    "doc_title",
                    "paragraph_title",
                    "table",
                    "formula",
                    "equation",
                },
            },
        )
        cells = []
        if primary and primary["source_type"] not in {"model_description", "native_region_label"}:
            try:
                cells = (
                    html_cells(text, path + "/content")
                    if re.search(r"<table\b", text, re.I)
                    else markdown_cells(text, path + "/content")
                )
            except (NativeReadError, ValueError):
                pass
        for cell in cells:
            add(
                "cell",
                cell["id"],
                page,
                "visual",
                None,
                parent=path,
                text=cell["text"],
                view="ContentBlock[]",
                details={
                    "source_cell": cell,
                    "source_table": path,
                    "origin": "visual_model_html_projection",
                    "native_independent_ocr_cell": False,
                },
            )
        declared = {
            k: audit_copy(node[k])
            for k in ("research_asset", "research_assets", "asset", "image_path", "uri", "image")
            if k in node
        }
        if kind == "picture" or declared:
            add(
                "media",
                path,
                page,
                "visual",
                None,
                identity=path + ":media",
                parent=path,
                view="ContentBlock[]",
                details={
                    "declaration": declared,
                    "delivery": "not_read_not_verified_not_delivered",
                },
            )
        if kind != "picture" and fmt == "markdown":
            from app.adapters.native_inventory import _inline_media

            for start, end in _inline_media(text):
                add(
                    "media",
                    path,
                    page,
                    "visual",
                    None,
                    identity=f"{path}:media:{start}:{end}",
                    parent=path,
                    view="ContentBlock[]",
                    spans=((start, end),),
                    details={
                        "appearance": "inline_reference",
                        "delivery": "not_read_not_verified_not_delivered",
                    },
                )
    return {
        "source_view": "ContentBlock[]",
        "reading_order": "unknown",
        "branch_page": None,
        "native_page_identity": "saved_page_envelope; no block-local PDF page id",
    }
