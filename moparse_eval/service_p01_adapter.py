"""P01's saved Docling/GLM objects, without source or media access.

Native JSON pointers identify received objects. Service roles/renderings are
additional consumer fields; they never replace the received label or text.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any

from app.models.parse_result import (
    DocumentParseResult,
    PageDiagnostics,
    PageParseResult,
    PageSourceKind,
    PageStatus,
    ParsePipeline,
    ParseUsage,
    PipelineWarning,
    QualityVerdict,
    RouteSummary,
    SelectionStrategy,
)
from app.services.final_content_service import _code_ranges
from app.services.native_text_service import _literal
from app.services.table_service import PageFurnitureFragment
from app.utils.page_range import parse_page_range

from .adapters import (
    NativeReadError,
    _block,
    _docling_cell_fields,
    _identity,
    _position,
    _sequence,
    read_docling,
)
from .service_native_adapters import _table, branch_capabilities, normalized_box

_ROLES = {
    "text": "text",
    "paragraph": "text",
    "caption": "text",
    "footnote": "text",
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


def _inline_media(text):
    """Read textual image declarations; never load their targets."""
    protected = _code_ranges(text)
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
    pieces, refs, cursor = [], [], 0
    for start, end, alt, reference in sorted(occurrences):
        if start < cursor:
            continue
        pieces.extend((text[cursor:start], "图片未交付。" + _literal(alt)))
        refs.append({"reference": audit_copy(reference), "source_text_span": [start, end]})
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces), refs


def audit_copy(value: Any) -> Any:
    """Keep media declarations, without decoding or duplicating inline data."""
    if isinstance(value, str) and (value.startswith("data:") or "/data:image/" in value):
        return {"inline_media_declared": True, "access": "not_decoded_or_validated"}
    if isinstance(value, Mapping):
        return {k: audit_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [audit_copy(v) for v in value]
    return copy.deepcopy(value)


def _resolve(root: Any, pointer: str) -> Any:
    from .service_replay_native import _pointer

    return _pointer(root, pointer)


def _box(block: Mapping[str, Any]):
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


def _glm_blocks(raw: Mapping[str, Any], number: int, pointer: str) -> list[dict[str, Any]]:
    if "json_result" not in raw:
        raise NativeReadError("glm_primary_json_result_missing")
    layout, path = raw["json_result"], pointer + "/json_result"
    if isinstance(layout, str):
        try:
            layout = json.loads(layout)
        except json.JSONDecodeError as exc:
            raise NativeReadError("glm_primary_json_invalid") from exc
        path += "::decoded"
    if isinstance(layout, Mapping):
        wrapper = next((k for k in ("pages", "results", "layout_details") if k in layout), None)
        if wrapper is None:
            raise NativeReadError("glm_primary_page_wrapper_unsupported")
        layout, path = layout[wrapper], path + "/" + wrapper
    if not isinstance(layout, list):
        raise NativeReadError("glm_primary_regions_not_a_list")
    local_page: Any = None
    if any(isinstance(item, list) for item in layout):
        if len(layout) != 1 or not isinstance(layout[0], list):
            raise NativeReadError("glm_image_call_has_ambiguous_page_identity")
        layout, path, local_page = layout[0], path + "/0", 0
    elif len(layout) == 1 and isinstance(layout[0], Mapping) and "regions" in layout[0]:
        local_page = layout[0].get("page_no", layout[0].get("page_index"))
        layout, path = layout[0]["regions"], path + "/0/regions"
        if not isinstance(layout, list):
            raise NativeReadError("glm_primary_regions_not_a_list")
    blocks = []
    indexes = [item.get("index") for item in layout if isinstance(item, Mapping)]
    valid_index_order = (
        bool(indexes)
        and all(type(i) is int and i >= 0 for i in indexes)
        and len(set(indexes)) == len(indexes)
    )
    entries = list(enumerate(layout))
    if valid_index_order:
        entries.sort(key=lambda pair: pair[1]["index"] if isinstance(pair[1], Mapping) else pair[0])
    for order, (index, item) in enumerate(entries):
        own = f"{path}/{index}"
        if not isinstance(item, Mapping):
            block = {
                "id": own,
                "native_path": own,
                "kind": "unknown",
                "text": "",
                "read_error": "non_object_glm_region",
                "read_error_category": "candidate_native_structure",
            }
        else:
            label = str(item.get("native_label") or item.get("label") or "unknown").casefold()
            fmt = (
                "html"
                if isinstance(item.get("content"), str)
                and re.search(r"<table\b", item["content"], re.I)
                else "markdown"
            )
            block = _block(
                item,
                own,
                own,
                kind=label,
                text=item.get("content"),
                box=item.get("bbox_2d"),
                text_pointer=own + "/content",
                text_format=fmt,
            )
            _identity(block, item, own)
            block.update(native_label=item.get("native_label"), label=item.get("label"))
            if not isinstance(item.get("content", ""), (str, type(None))):
                block["read_error"] = "glm_region_content_not_text"
            if indexes and not valid_index_order and any(i is not None for i in indexes):
                block["read_error"] = "glm_region_index_conflict"
            # These are HTML cells in a model response, not PDF/Docling cells.
            for cell in block.get("cells", []):
                cell["source_locator"] = {
                    "json_pointer": own + "/content",
                    "syntax_path": cell["native_path"].split("::html", 1)[-1],
                    "kind": "primary_html_projection",
                }
        block.update(
            native_payload=audit_copy(item),
            branch_page=local_page,
            source_view="json_result",
            order_basis="native_index" if valid_index_order else "native_array_order",
        )
        _position(block, system="normalized_1000", page=number)
        _sequence(block, [number, order])
        blocks.append(block)
    return blocks


def _docling_blocks(native, envelope, number, local_page, pointer, page_map, emitted):
    containers: list[dict[str, Any]] = []
    # Each page is traversed independently. Multi-page text is selected by its
    # own charspan rather than suppressing all but the first occurrence.
    blocks = read_docling(envelope, local_page, pointer, containers=containers)
    document = envelope.get("document", envelope)
    base = pointer + "/document" if "document" in envelope else pointer
    known = {b["native_path"] for b in blocks}
    # Unreferenced source nodes are an order gap, not permission to drop them.
    for family in ("texts", "tables", "pictures"):
        for index, item in enumerate(document.get(family, [])):
            own = f"{base}/{family}/{index}"
            if not isinstance(item, Mapping) or own in known:
                continue
            if not any(
                isinstance(p, Mapping) and p.get("page_no") == local_page
                for p in item.get("prov", [])
            ):
                continue
            orphan = {
                "document": {
                    **document,
                    "body": {"children": [{"$ref": f"#/{family}/{index}"}]},
                    "furniture": {"children": []},
                }
            }
            recovered = read_docling(orphan, local_page, pointer)
            for block in recovered:
                if block["native_path"] not in known:
                    block.update(
                        read_error="node_outside_native_reading_tree", order_status="unknown"
                    )
                    blocks.append(block)
                    known.add(block["native_path"])
    output = []
    for block in blocks:
        if block.get("read_error_category") == "engineering_failure":
            raise RuntimeError(
                "P01 Docling reader engineering failure: " + str(block.get("read_error"))
            )
        payload = _resolve(native, block["native_path"])
        block["native_payload"] = audit_copy(payload)
        block.update(branch_page=local_page, page=number)
        if block.get("bbox_page") is not None:
            block["native_bbox_page"] = block["bbox_page"]
            block["bbox_page"] = number
        if block.get("read_error") and isinstance(payload, Mapping):
            if isinstance(payload.get("text"), str) and not block.get("text"):
                block["text"] = payload["text"]
                block["text_format"] = "plain"
            provenance = payload.get("prov")
            if not isinstance(provenance, list) or any(
                not isinstance(p, Mapping) or type(p.get("page_no")) is not int for p in provenance
            ):
                block.update(branch_page=None, page=None)
        for prov in block.get("provenance", []):
            prov["native_page_no"] = prov["page_no"]
            prov["page_no"] = page_map.get(prov["page_no"])
        block["provenance_pages"] = list(
            dict.fromkeys(
                p["page_no"] for p in block.get("provenance", []) if p["page_no"] is not None
            )
        )
        pages = (
            {p.get("page_no") for p in payload["prov"] if isinstance(p, Mapping)}
            if isinstance(payload, Mapping) and isinstance(payload.get("prov"), list)
            else set()
        )
        if len(pages) > 1:
            text = block.get("text", "")
            all_ranges = [p.get("charspan") for p in payload.get("prov", [])]
            valid_ranges = all(
                isinstance(r, (list, tuple))
                and len(r) == 2
                and all(type(x) is int for x in r)
                and 0 <= r[0] < r[1] <= len(text)
                for r in all_ranges
            )
            ordered = sorted(all_ranges) if valid_ranges else []
            partition = (
                bool(ordered)
                and ordered[0][0] == 0
                and ordered[-1][1] == len(text)
                and all(
                    left[1] == right[0] for left, right in zip(ordered, ordered[1:], strict=False)
                )
            )
            ranges = [
                p.get("charspan") for p in payload.get("prov", []) if p.get("page_no") == local_page
            ]
            if (
                text
                and partition
                and pages <= set(page_map)
                and all(
                    isinstance(r, (list, tuple))
                    and len(r) == 2
                    and all(type(x) is int for x in r)
                    and 0 <= r[0] < r[1] <= len(text)
                    for r in ranges
                )
            ):
                block.update(
                    text="".join(text[a:b] for a, b in ranges), text_selection=copy.deepcopy(ranges)
                )
                block["occurrence_id"] = block["id"] + f"@page={number}"
                block["native_node_id"] = block["id"]
                block["id"] = block["occurrence_id"]
            elif block["id"] in emitted:
                continue
            else:
                block["read_error"] = "multipage_node_without_complete_text_partition"
        emitted.add(block["id"])
        if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping):
            original_cells = payload["data"].get("table_cells", [])
            if not isinstance(original_cells, list):
                block["read_error"] = "native_table_cells_not_a_list"
                original_cells = []
            read_paths = {c["native_path"] for c in block.get("cells", [])}
            for index, cell in enumerate(original_cells):
                own = block["native_path"] + f"/data/table_cells/{index}"
                if own not in read_paths:
                    block.setdefault("cells", []).append(
                        {
                            "id": own,
                            "native_path": own,
                            "text": cell.get("text", "") if isinstance(cell, Mapping) else "",
                            "row": cell.get("start_row_offset_idx")
                            if isinstance(cell, Mapping)
                            else None,
                            "col": cell.get("start_col_offset_idx")
                            if isinstance(cell, Mapping)
                            else None,
                            "row_span": cell.get("row_span") if isinstance(cell, Mapping) else None,
                            "col_span": cell.get("col_span") if isinstance(cell, Mapping) else None,
                            "is_column_header": cell.get("column_header")
                            if isinstance(cell, Mapping)
                            else None,
                            "is_row_header": cell.get("row_header")
                            if isinstance(cell, Mapping)
                            else None,
                            **(
                                _docling_cell_fields(cell, document, base)
                                if isinstance(cell, Mapping)
                                else {}
                            ),
                            "native_payload": audit_copy(cell),
                        }
                    )
                    block["read_error"] = "native_table_cell_position_unavailable"
            for cell in block.get("cells", []):
                source_cell = _resolve(native, cell["native_path"])
                if isinstance(source_cell, Mapping):
                    for field in ("row_span", "col_span"):
                        if field not in source_cell:
                            cell[field] = None
                            block["read_error"] = "native_cell_span_unavailable"
                    if not isinstance(source_cell.get("text"), str) and not cell.get(
                        "native_rich_text"
                    ):
                        block["read_error"] = "native_cell_text_unavailable"
                cell_page = cell.get("page")
                if cell_page is None and len(pages) == 1:
                    cell["geometry_page_basis"] = "unique_table_provenance"
                    cell["page_dimensions"] = block.get("page_dimensions")
                    cell["bbox_page"] = number
                elif cell_page is not None:
                    cell["native_page"] = cell_page
                    cell["page"] = page_map.get(cell_page)
                    cell["native_bbox_page"] = cell.get("bbox_page")
                    cell["bbox_page"] = page_map.get(cell_page)
                    if cell_page not in pages:
                        block["read_error"] = "native_cell_page_conflict"
                for axis, span in (("row", "row_span"), ("col", "col_span")):
                    start, end = (
                        cell.get("start_" + axis + "_offset_idx"),
                        cell.get("end_" + axis + "_offset_idx"),
                    )
                    if (
                        type(start) is int
                        and type(cell.get(span)) is int
                        and end is not None
                        and (type(end) is not int or end != start + cell[span])
                    ):
                        block["read_error"] = "native_cell_span_conflict"
        output.append(block)
    for container in containers:
        container["native_payload"] = audit_copy(_resolve(native, container["native_path"]))
    return output, containers


def _render(blocks, number, branch, containers, *, include_source_markers):
    pieces, fragments, furniture, media, issues = [], [], [], [], []
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
                    "pipeline": "P01",
                    "branch": branch,
                    "cell_identity": "native_json_cells"
                    if branch == "docling"
                    else "primary_html_cells",
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
            branch == "glm"
            and role == "text"
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
            geometry_frame="frozen_oriented_input",
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


def adapt_p01(native, source, options, *, document_id, include_source_markers=False):
    """Read each selected physical page once, from its own declared branch."""
    selected = parse_page_range(options.page_range, source.page_count)
    result = DocumentParseResult(
        document_id=document_id,
        filename=source.filename,
        mime_type=source.mime_type,
        page_count=source.page_count,
        processed_pages=0,
        pipeline=ParsePipeline(profile=options.profile.value, primary="docling-tableformer-v1"),
        usage=ParseUsage(input_bytes=source.size_bytes),
    )
    audit = {
        "schema": "offline-service-native-replay/1",
        "pipeline": "P01",
        "pages": [],
        "errors": [],
        "asset_references": [],
        "model_calls": 0,
        "http_calls": 0,
        "source_policy": "saved_p01_json_only_no_source_media_or_reference_access",
    }
    entries = defaultdict(list)
    raw_pages = native.get("pages", [])
    if not isinstance(raw_pages, list):
        audit["errors"].append(
            {"code": "native_pages_not_a_list", "payload": audit_copy(raw_pages)}
        )
        raw_pages = []
    for position, page in enumerate(raw_pages):
        if (
            isinstance(page, Mapping)
            and type(page.get("page")) is int
            and 1 <= page["page"] <= source.page_count
        ):
            entries[page["page"]].append((position, page))
        else:
            audit["errors"].append(
                {
                    "code": "native_page_identity_unavailable",
                    "position": position,
                    "payload": audit_copy(page),
                }
            )
    processing = defaultdict(list)
    processing_items = native.get("page_processing", [])
    if not isinstance(processing_items, list):
        audit["errors"].append(
            {"code": "native_page_processing_not_a_list", "payload": audit_copy(processing_items)}
        )
        processing_items = []
    for p in processing_items:
        if isinstance(p, Mapping) and type(p.get("page")) is int:
            processing[p["page"]].append(p)
    document_maps = defaultdict(dict)
    for number, records in entries.items():
        for _, p in records:
            raw = p.get("raw", {})
            if (
                p.get("branch") == "docling"
                and isinstance(raw, Mapping)
                and isinstance(raw.get("native_document"), str)
                and type(raw.get("source_page", number)) is int
            ):
                document_maps[raw.get("native_document")][raw.get("source_page", number)] = number
    emitted = set()
    for number in sorted(selected):
        detail = {"raw_page": number, "branch": "unknown", "local_read_errors": []}
        warnings = []
        content, blocks, containers = "", [], []
        branch = "unknown"
        try:
            if len(entries[number]) != 1:
                raise NativeReadError(
                    "native_page_missing" if not entries[number] else "native_page_duplicated"
                )
            position, entry = entries[number][0]
            branch = entry.get("branch")
            detail.update(
                branch=branch,
                native_page_position=position,
                native_entry_pointer=f"#/pages/{position}",
            )
            if not isinstance(branch, str) or branch not in {"docling", "glm"}:
                raise NativeReadError("saved_branch_outside_declared_pipeline")
            raw = entry.get("raw")
            if not isinstance(raw, Mapping):
                raise NativeReadError("native_page_payload_not_an_object")
            pointer = f"#/pages/{position}/raw"
            if len(processing[number]) > 1:
                raise NativeReadError("page_processing_identity_duplicated")
            detail["frozen_page_processing"] = (
                audit_copy(processing[number][0]) if processing[number] else None
            )
            detail["capabilities"] = branch_capabilities("P01", branch)
            if branch == "docling":
                pointer = raw.get("native_document")
                detail["native_page_pointer"] = audit_copy(pointer)
                if not isinstance(pointer, str) or not re.fullmatch(r"#/documents/\d+", pointer):
                    raise NativeReadError("docling_document_pointer_outside_branch")
                envelope = _resolve(native, pointer)
                if not isinstance(envelope, Mapping):
                    raise NativeReadError("declared_native_document_unavailable")
                local = raw.get("source_page", number)
                if type(local) is not int or local < 1:
                    raise NativeReadError("docling_source_page_identity_unavailable")
                mapping = document_maps[pointer]
                owners = [
                    p.get("raw", {}).get("source_page", n)
                    for n, records in entries.items()
                    for _, p in records
                    if p.get("branch") == "docling"
                    and isinstance(p.get("raw"), Mapping)
                    and p["raw"].get("native_document") == pointer
                    and type(p["raw"].get("source_page", n)) is int
                ]
                if len(set(owners)) != len(owners):
                    raise NativeReadError("docling_local_page_identity_duplicated")
                group = envelope.get("research_group_pages", list(mapping.values()))
                if (
                    not isinstance(group, list)
                    or any(type(p) is not int or p < 1 for p in group)
                    or len(set(group)) != len(group)
                ):
                    raise NativeReadError("docling_group_page_identity_unavailable")
                if not set(mapping.values()) <= set(group) or any(
                    isinstance(p.get("branch"), str)
                    and (
                        p["branch"] != "docling"
                        or isinstance(p.get("raw"), Mapping)
                        and isinstance(p["raw"].get("native_document"), str)
                        and p["raw"]["native_document"] != pointer
                    )
                    for declared_page in group
                    for _, p in entries.get(declared_page, [])
                ):
                    raise NativeReadError("docling_group_page_ownership_conflict")
                document = envelope.get("document", envelope)
                if not isinstance(document, Mapping) or not isinstance(
                    document.get("body"), Mapping
                ):
                    raise NativeReadError("docling_reading_tree_unavailable")
                detail.update(
                    branch_page=local,
                    native_page_pointer=pointer,
                    source_envelope={
                        k: audit_copy(envelope[k])
                        for k in (
                            "status",
                            "errors",
                            "research_group_pages",
                            "research_export_errors",
                        )
                        if k in envelope
                    },
                )
                blocks, containers = _docling_blocks(
                    native, envelope, number, local, pointer, mapping, emitted
                )
                status = str(envelope.get("status", "")).lower()
                if any(k in status for k in ("partial", "fail", "error")) or envelope.get("errors"):
                    detail["local_read_errors"].append({"code": "saved_native_producer_incomplete"})
            else:
                result.pipeline.ocr = "glm-sdk-remote"
                blocks = _glm_blocks(raw, number, pointer)
                detail.update(
                    native_page_pointer=pointer,
                    primary_view="json_result",
                    audit_view={"present": "raw_json_result" in raw, "used_as_answer": False},
                    markdown_view={"present": "markdown_result" in raw, "used_as_answer": False},
                    image_files={"declared": "image_files" in raw, "bytes_accessed": False},
                    source_envelope={
                        k: audit_copy(raw[k]) for k in ("status", "errors") if k in raw
                    },
                )
                if raw.get("errors") or any(
                    t in str(raw.get("status", "")).lower() for t in ("fail", "error", "partial")
                ):
                    detail["local_read_errors"].append({"code": "saved_native_producer_incomplete"})
            content, fragments, furniture, media, issues = _render(
                blocks, number, branch, containers, include_source_markers=include_source_markers
            )
            result._table_fragments.extend(fragments)
            result._page_furniture.extend(furniture)
            audit["asset_references"].extend(media)
            detail["local_read_errors"].extend(issues)
            detail["native_containers"] = containers
            if not blocks and not detail["local_read_errors"]:
                detail["local_read_errors"].append({"code": "native_page_content_unavailable"})
        except NativeReadError as exc:
            detail["error"] = str(exc)
            detail["local_read_errors"].append(
                {"code": str(exc), "category": "candidate_native_structure"}
            )
        for issue in detail["local_read_errors"]:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,127}", str(issue["code"])):
                issue["reason"], issue["code"] = (
                    issue["code"],
                    "saved_native_local_region_unreadable",
                )
            warnings.append(
                PipelineWarning(
                    code=issue["code"],
                    message="saved native content is incomplete or unresolved; available content is retained",
                    page_number=number,
                    backend=branch if isinstance(branch, str) else "unknown",
                    details=issue,
                )
            )
        if not content and warnings:
            content = "本页内容未完成。"
        failed = bool(detail.get("error"))
        status = (
            PageStatus.FAILED
            if failed
            else PageStatus.WARNING
            if warnings
            else PageStatus.COMPLETED
        )
        page = PageParseResult(
            page_number=number,
            backend={"glm": "glm-sdk-remote", "docling": "docling-tableformer-v1"}.get(
                branch if isinstance(branch, str) else "unknown"
            ),
            content=content,
            status=status,
            warnings=warnings,
            diagnostics=PageDiagnostics(
                source_kind=PageSourceKind.NATIVE
                if branch == "docling"
                else {
                    "scan": PageSourceKind.SCANNED,
                    "mixed": PageSourceKind.MIXED,
                    "native": PageSourceKind.NATIVE,
                    "sparse": PageSourceKind.SPARSE,
                }.get(
                    (detail.get("frozen_page_processing") or {}).get("source_prediction"),
                    PageSourceKind.UNKNOWN,
                ),
                selected_strategy=SelectionStrategy.DOCLING
                if branch == "docling"
                else SelectionStrategy.GLM_TABLE
                if branch == "glm"
                else SelectionStrategy.UNKNOWN,
                quality_verdict=QualityVerdict.UNTRUSTED
                if failed
                else QualityVerdict.DEGRADED
                if warnings
                else QualityVerdict.TRUSTED,
                detected_rotation_degrees=(
                    (detail.get("frozen_page_processing") or {}).get("rotation_clockwise")
                    if (detail.get("frozen_page_processing") or {}).get("rotation_clockwise")
                    in (0, 90, 180, 270)
                    and type((detail.get("frozen_page_processing") or {}).get("rotation_clockwise"))
                    is int
                    else None
                ),
            ),
        )
        result.pages.append(page)
        result._native_page_blocks[number] = blocks
        result.warnings.extend(warnings)
        detail.update(status=status.value, warnings=[w.code for w in warnings])
        audit["pages"].append(detail)
        if warnings:
            audit["errors"].append(copy.deepcopy(detail))
    result.processed_pages = sum(p.status != PageStatus.FAILED for p in result.pages)
    for error in audit["errors"]:
        if error.get("code"):
            result.warnings.append(
                PipelineWarning(
                    code=error["code"],
                    backend="P01",
                    message="saved document contains an unresolved native identity or structure",
                    details=error,
                )
            )
    counts = Counter(p["branch"] for p in audit["pages"] if isinstance(p["branch"], str))
    result.route_summary = RouteSummary(
        native_text_pages=counts["docling"],
        pages_with_ocr=counts["glm"],
        failed_pages=sum(p.status == PageStatus.FAILED for p in result.pages),
    )
    result._source_verification["saved_native_bridge"] = copy.deepcopy(audit)
    result._source_verification["saved_p01"] = {
        "status": "partial" if audit["errors"] else "completed",
        "media": copy.deepcopy(audit["asset_references"]),
        "source_access": "disabled",
    }
    return result, audit
