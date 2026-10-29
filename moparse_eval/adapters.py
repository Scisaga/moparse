"""Lossless observations of candidate output; no expected-result access.

These readers expose only fields already returned by a backend. A backend's
``table`` label remains a producer label, not a semantic classification.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any


class NativeReadError(ValueError):
    """The received object cannot be read without inventing information."""


def _docling_reference(value: Any) -> str | None:
    """Read either explicit RefItem serialization, rejecting conflicting aliases."""
    if not isinstance(value, Mapping):
        return None
    refs = [value[key] for key in ("$ref", "cref") if key in value]
    if not refs or any(not isinstance(ref, str) or not ref.startswith("#/") or len(ref) > 8192 for ref in refs):
        return None
    return refs[0] if all(ref == refs[0] for ref in refs) else None


def _docling_reference_content(document: Mapping[str, Any], reference: Any,
                               document_pointer: str) -> dict[str, Any]:
    """Expose a bounded explicit rich-cell graph, never flattening mixed content.

    Each node still identifies the saved native object. A text projection is
    available only for one text leaf and no opaque, missing or cyclic nodes.
    Multiple text leaves retain their individual text without invented joins.
    """
    evidence: dict[str, Any] = {"status": "unknown", "nodes": [], "edges": [],
                                "text_items": [], "errors": []}
    root = _docling_reference(reference)
    if root is None:
        evidence["errors"].append({"reason": "invalid_cell_reference"})
        return evidence
    evidence["root_native_path"] = document_pointer + root[1:]
    visited: set[str] = set()
    active: set[str] = set()
    has_nontext = False
    text_size = 0

    def visit(ref: str, depth: int) -> None:
        nonlocal has_nontext, text_size
        path = document_pointer + ref[1:]
        if depth > 16 or len(visited) >= 256:
            evidence["errors"].append({"native_path": path, "reason": "reference_budget_exceeded"})
            return
        if ref in active or ref in visited:
            evidence["errors"].append({"native_path": path, "reason":
                "cyclic_reference" if ref in active else "repeated_reference"})
            return
        value: Any = document
        for encoded in ref[2:].split("/"):
            token = encoded.replace("~1", "/").replace("~0", "~")
            if isinstance(value, Mapping) and token in value:
                value = value[token]
            elif isinstance(value, list) and token.isdecimal() and str(int(token)) == token and int(token) < len(value):
                value = value[int(token)]
            else:
                evidence["errors"].append({"native_path": path, "reason": "reference_unavailable"})
                return
        if not isinstance(value, Mapping) or value.get("self_ref", ref) != ref:
            evidence["errors"].append({"native_path": path, "reason": "native_identity_unresolved"})
            return
        visited.add(ref)
        active.add(ref)
        node = {"native_path": path, "label": value.get("label"), "native_fields": sorted(value)}
        evidence["nodes"].append(node)
        text = value.get("text")
        if isinstance(text, str):
            text_size += len(text)
            if text_size > 200_000:
                evidence["errors"].append({"native_path": path, "reason": "text_budget_exceeded"})
                active.remove(ref)
                return
            node["text"] = text
        children = value.get("children", [])
        opaque = value.get("label") in {"picture", "figure", "table", "form", "key_value_region"} or any(
            key in value for key in ("image", "data"))
        is_text = ref.startswith("#/texts/") and isinstance(text, str) and not children and not opaque
        is_group = ref.startswith("#/groups/")
        if is_text:
            evidence["text_items"].append({"native_path": path, "text": text})
        elif not is_group or opaque:
            has_nontext = True
            node["content_status"] = "nontext_or_unsupported"
        for field in ("children", "captions", "footnotes", "references"):
            if len(evidence["edges"]) >= 512:
                break
            refs = value.get(field, [])
            if not isinstance(refs, list):
                evidence["errors"].append({"native_path": path + "/" + field,
                                            "reason": "native_references_not_a_list"})
                continue
            for index, child in enumerate(refs):
                if len(evidence["edges"]) >= 512:
                    evidence["errors"].append({"native_path": path, "reason": "reference_budget_exceeded"})
                    break
                target = _docling_reference(child)
                edge = {"native_path": f"{path}/{field}/{index}",
                        "reference": copy.deepcopy(child)}
                evidence["edges"].append(edge)
                if target is None:
                    evidence["errors"].append({"native_path": edge["native_path"],
                                                "reason": "invalid_child_reference"})
                    continue
                edge["target_native_path"] = document_pointer + target[1:]
                visit(target, depth + 1)
        active.remove(ref)

    visit(root, 0)
    if evidence["errors"]:
        evidence["status"] = "unknown"
    elif has_nontext:
        evidence["status"] = "mixed_or_nontext"
    elif len(evidence["text_items"]) == 1:
        evidence["status"] = "text_resolved"
    elif evidence["text_items"]:
        evidence["status"] = "multiple_text_items"
    else:
        evidence["status"] = "empty_reference"
    return evidence


def _docling_cell_fields(cell: Mapping[str, Any], document: Mapping[str, Any],
                         document_pointer: str) -> dict[str, Any]:
    """Supplement explicit cell fields without changing its existing text."""
    fields = {key: copy.deepcopy(cell[key]) for key in (
        "start_row_offset_idx", "end_row_offset_idx", "start_col_offset_idx", "end_col_offset_idx",
        "column_header", "row_header", "row_section", "fillable",
    ) if key in cell}
    for source, target in (("column_header", "is_column_header"), ("row_header", "is_row_header")):
        if source in cell:
            fields[target] = cell[source]
    if "ref" in cell:
        fields["native_cell_ref"] = copy.deepcopy(cell["ref"])
        evidence = _docling_reference_content(document, cell["ref"], document_pointer)
        fields["native_rich_content"] = evidence
        if evidence["status"] == "text_resolved":
            fields["native_rich_text"] = evidence["text_items"][0]["text"]
            fields["native_rich_text_path"] = evidence["text_items"][0]["native_path"] + "/text"
    return fields


class _HTMLCells(HTMLParser):
    def __init__(self, pointer: str) -> None:
        super().__init__(convert_charrefs=True)
        self.pointer = pointer
        self.cells: list[dict[str, Any]] = []
        self.row = -1
        self.col = 0
        self.occupied: set[tuple[int, int]] = set()
        self.current: dict[str, Any] | None = None
        self.parts: list[str] = []
        self.depth = 0
        self.table_count = 0
        self.inline: list[dict[str, Any]] = []
        self.annotation_stack: list[tuple[str, dict[str, Any]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.depth += 1
            self.table_count += 1
            if self.depth > 1:
                raise NativeReadError("nested table: retain HTML without inferred cells")
            if self.table_count > 1:
                raise NativeReadError("multiple native tables cannot become one inferred grid")
        elif tag == "tr":
            if self.current is not None:
                raise NativeReadError("unclosed native HTML cell")
            self.row += 1
            self.col = 0
        elif tag in {"td", "th"}:
            if self.row < 0 or self.current is not None:
                raise NativeReadError("native HTML cell has no unambiguous row")
            values = dict(attrs)
            rs, cs = int(values.get("rowspan") or "1"), int(values.get("colspan") or "1")
            if not 1 <= rs <= 2000 or not 1 <= cs <= 2000:
                raise NativeReadError("unsupported HTML span")
            if len(self.occupied) + rs * cs > 200_000:
                raise NativeReadError("native HTML grid exceeds the bounded reader budget")
            while (self.row, self.col) in self.occupied:
                self.col += 1
            path = f"{self.pointer}::html/cell[{len(self.cells)}]"
            self.current = {"id": path, "native_path": path, "row": self.row,
                            "col": self.col, "row_span": rs, "col_span": cs,
                            "native_tag": tag, "native_attributes": values,
                            "page": None, "text_format": "plain"}
            if values.get("id") is not None:
                self.current["native_id"] = values["id"]
            if tag == "th":
                scope = values.get("scope")
                if scope in {"row", "rowgroup"}:
                    self.current["is_row_header"] = True
                elif scope in {"col", "colgroup"}:
                    self.current["is_column_header"] = True
                self.current["native_header_tag"] = True
            self.parts = []
            self.inline = []
            self.annotation_stack = []
        elif tag == "br" and self.current is not None:
            self.parts.append("\n")
        elif self.current is not None and tag in {"sup", "sub", "a"}:
            line, column = self.getpos()
            annotation: dict[str, Any] = {"type": {"sup": "superscript", "sub": "subscript", "a": "link"}[tag],
                          "span": [sum(map(len, self.parts)), None],
                          "native_path": f"{self.pointer}::html@{line}:{column}/{tag}",
                          "native_attributes": dict(attrs)}
            if tag == "a" and dict(attrs).get("href") is not None:
                annotation["target"] = dict(attrs)["href"]
            self.annotation_stack.append((tag, annotation))

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"sup", "sub", "a"} and self.current is not None:
            if self.annotation_stack and self.annotation_stack[-1][0] == tag:
                _, annotation = self.annotation_stack.pop()
                annotation["span"][1] = sum(map(len, self.parts))
                annotation["text"] = "".join(self.parts)[slice(*annotation["span"])]
                self.inline.append(annotation)
        elif tag in {"td", "th"} and self.current is not None:
            cell = self.current
            cell["text"] = "".join(self.parts)
            if self.inline:
                cell["inline_annotations"] = sorted(self.inline, key=lambda value: value["span"])
            for row in range(cell["row"], cell["row"] + cell["row_span"]):
                for col in range(cell["col"], cell["col"] + cell["col_span"]):
                    if (row, col) in self.occupied:
                        raise NativeReadError("overlapping native HTML cells")
                    self.occupied.add((row, col))
            self.cells.append(cell)
            self.col += cell["col_span"]
            self.current = None
        elif tag == "table":
            self.depth -= 1


def html_cells(html: str, pointer: str = "#/html") -> list[dict[str, Any]]:
    """Read explicit HTML syntax, retaining text and declared spans as received."""
    parser = _HTMLCells(pointer)
    parser.feed(html)
    parser.close()
    if parser.current is not None or parser.depth:
        raise NativeReadError("incomplete native HTML table")
    return parser.cells


def markdown_cells(markdown: str, pointer: str = "#/markdown") -> list[dict[str, Any]]:
    """Read one explicit GFM table; never guess a table from aligned prose."""
    from markdown_it import MarkdownIt

    from .representations import visible_text

    tokens = MarkdownIt("commonmark").enable("table").parse(markdown)
    if not tokens:
        return []
    if len(tokens) == 1 and tokens[0].type == "html_block":
        return html_cells(tokens[0].content, pointer) if "<table" in tokens[0].content.lower() else []
    if tokens[0].type != "table_open" or tokens[-1].type != "table_close":
        return []
    if sum(token.type == "table_open" for token in tokens) != 1:
        return []
    cells: list[dict[str, Any]] = []
    row, col = -1, 0
    current: dict[str, Any] | None = None
    for token in tokens:
        if token.type == "tr_open":
            row, col = row + 1, 0
        elif token.type in {"th_open", "td_open"}:
            current = {"id": f"{pointer}/gfm/rows/{row}/cells/{col}", "native_path": pointer,
                       "native_syntax": {"format": "gfm", "row": row, "column": col},
                       "row": row, "col": col, "row_span": 1, "col_span": 1, "text": "",
                       "is_column_header": token.type == "th_open"}
        elif token.type == "inline" and current is not None:
            current["text"] = visible_text(token.content, "markdown")
        elif token.type in {"th_close", "td_close"} and current is not None:
            cells.append(current)
            current, col = None, col + 1
    return cells


def _block(raw: Mapping[str, Any], ident: str, pointer: str, *, kind: str,
           text: Any, box: Any = None, text_pointer: str | None = None,
           text_format: str = "plain") -> dict[str, Any]:
    block: dict[str, Any] = {"id": ident, "kind": kind,
                             "text": text if isinstance(text, str) else "",
                             "native_path": pointer, "text_format": text_format}
    if box is not None:
        block["bbox"] = box
    for key in ("asset", "caption", "status", "angle", "merge_prev", "coordinate_system",
                "parent", "parent_id", "row_header_path", "column_header_path",
                "inline_annotations", "annotations", "notes", "links", "hyperlink", "formatting", "level"):
        if key in raw:
            block[key] = raw[key]
    if raw.get("research_asset"):
        block["asset"] = raw["research_asset"]
    if raw.get("research_assets"):
        block["assets"] = raw["research_assets"]
    for key in ("research_export_markdown", "markdown"):
        if isinstance(raw.get(key), str):
            block["native_export_markdown"] = raw[key]
            block["native_export_markdown_path"] = pointer + "/" + key
            break
    if text_format in {"html", "markdown"}:
        try:
            syntax_pointer = text_pointer or pointer + "/content"
            cells = (html_cells(block["text"], syntax_pointer) if text_format == "html"
                     else markdown_cells(block["text"], syntax_pointer))
            if cells:
                block["cells"] = cells
        except (NativeReadError, ValueError) as exc:
            block["structure_status"] = "unknown"
            block["read_error"] = str(exc)
            block["read_error_category"] = "candidate_native_structure"
    return block


def _position(block: dict[str, Any], *, system: str, origin: str = "TOPLEFT",
              page: int | None, dimensions: Mapping[str, Any] | None = None) -> None:
    block["coordinate_system"] = system
    block["coordinate_origin"] = origin
    block["page"] = page
    block["provenance_pages"] = [page] if page is not None else []
    if dimensions is not None:
        block["page_dimensions"] = dict(dimensions)
    if page is not None:
        block["provenance"] = [{"page_no": page, "source": "declared_sdk_page_or_image_call",
            "bbox": block.get("bbox"), "coordinate_system": system,
            "coordinate_origin": origin, "page_dimensions": dict(dimensions) if dimensions is not None else None}]
    if block.get("bbox") is not None:
        block["bbox_page"] = page


def _identity(block: dict[str, Any], raw: Mapping[str, Any], pointer: str) -> None:
    block["id"] = pointer
    for key in ("id", "index", "self_ref", "group_id"):
        if key in raw:
            block["native_" + key if key != "self_ref" else key] = raw[key]


def _sequence(block: dict[str, Any], sequence: list[int]) -> None:
    block["native_sequence"] = sequence
    for index, cell in enumerate(block.get("cells", [])):
        cell["parent_id"] = block["id"]
        cell["native_sequence"] = [*sequence, index]
        cell["provenance_pages"] = block.get("provenance_pages", [])


def glm_regions(layout: Any, layout_path: str) -> list[tuple[str, Any]]:
    """Read declared GLM region/page-list wrappers without guessing from item 0.

    This is one submitted image's result. Explicit list wrappers retain their
    native pointers; malformed siblings remain visible rather than determining
    whether valid neighbors are read. No physical-page identities are inferred.
    """
    if isinstance(layout, str):
        try:
            layout = json.loads(layout)
        except json.JSONDecodeError as exc:
            raise NativeReadError(f"GLM layout JSON cannot be decoded: {exc}") from exc
        # A serialized JSON field is identified as a decoded view, not a JSON
        # Pointer falsely claiming its string contents are a native list.
        layout_path += "::decoded"
    if isinstance(layout, Mapping):
        for key in ("pages", "results", "layout_details"):
            if key in layout:
                layout, layout_path = layout[key], layout_path + "/" + key
                break
    if not isinstance(layout, list):
        raise NativeReadError("GLM layout is not a list")
    regions: list[tuple[str, Any]] = []
    for index, item in enumerate(layout):
        path = f"{layout_path}/{index}"
        if isinstance(item, list):
            regions.extend((f"{path}/{child_index}", child) for child_index, child in enumerate(item))
        else:
            regions.append((path, item))
    return regions


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


def read_paddle(raw: Mapping[str, Any], page_number: int,
                pointer: str = "#/paddle", *, page_dimensions: Mapping[str, Any] | None = None,
                **_: Any) -> list[dict[str, Any]]:
    export_pointer = pointer + "/research_region_exports"
    payload = raw.get("res", raw)
    if "res" in raw:
        pointer += "/res"
    if not isinstance(payload, Mapping):
        raise NativeReadError("Paddle result wrapper is not an object")
    regions = payload.get("parsing_res_list")
    if not isinstance(regions, list):
        raise NativeReadError("Paddle result has no parsing_res_list")
    blocks = []
    for index, region in enumerate(regions):
        if not isinstance(region, Mapping):
            blocks.append({"id": f"p{page_number}-paddle-{index}", "kind": "unknown",
                           "text": "", "native_path": f"{pointer}/parsing_res_list/{index}",
                           "read_error": "non-object region", "structure_status": "unknown",
                           "read_error_category": "candidate_native_structure"})
            continue
        block = _block(region, f"p{page_number}-paddle-{index}",
                             f"{pointer}/parsing_res_list/{index}",
                             kind=str(region.get("block_label", "unknown")),
                             text=region.get("block_content", ""), box=region.get("block_bbox"),
                             text_pointer=f"{pointer}/parsing_res_list/{index}/block_content",
                             text_format="html" if region.get("block_label") == "table" else "markdown")
        _identity(block, region, f"{pointer}/parsing_res_list/{index}")
        exported = raw.get("research_region_exports", {}).get(str(index))
        if isinstance(exported, str):
            block["native_export_markdown"] = exported
            block["native_export_markdown_path"] = export_pointer + "/" + str(index)
        _position(block, system="pixel", page=page_number, dimensions=page_dimensions)
        _sequence(block, [page_number, index])
        if raw.get("research_region_media", {}).get(str(index)):
            block["asset"] = raw["research_region_media"][str(index)]
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


def read_docling(raw: Mapping[str, Any], page_number: int,
                 pointer: str = "#/docling", *, emitted: set[str] | None = None,
                 containers: list[dict[str, Any]] | None = None, **_: Any) -> list[dict[str, Any]]:
    """Traverse Docling references in reading-tree order, never array order."""
    document = raw.get("document", raw)
    if "document" in raw:
        pointer += "/document"
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    emitted = emitted if emitted is not None else set()
    container_ids = {value["id"] for value in containers or []}
    reading_order = 0
    group_start = raw.get("research_group_pages", [page_number])[0]

    def dimensions(page: int) -> dict[str, Any] | None:
        record = document.get("pages", {}).get(str(page), document.get("pages", {}).get(page, {}))
        size = record.get("size")
        if isinstance(size, Mapping):
            return {**size, "unit": "pdf_points"}
        return None

    def full_ref(ref: str) -> str:
        return pointer + ref[1:]

    def resolve(ref: str) -> Mapping[str, Any]:
        if not ref.startswith("#/"):
            raise NativeReadError("Docling reference has no native JSON pointer")
        value: Any = document
        for token in ref.removeprefix("#/").split("/"):
            if isinstance(value, list):
                if not token.isdecimal() or int(token) >= len(value):
                    raise NativeReadError("Docling reference array index is unavailable")
                value = value[int(token)]
            elif isinstance(value, Mapping) and token in value:
                value = value[token]
            else:
                raise NativeReadError("Docling reference path is unavailable")
        if not isinstance(value, Mapping):
            raise NativeReadError("Docling reference does not identify an object")
        return value

    def read_error(ref: str, message: str, category: str = "candidate_native_structure") -> None:
        nonlocal reading_order
        blocks.append({"id": full_ref(ref), "native_path": full_ref(ref), "kind": "unknown",
                       "text": "", "page": page_number, "read_error": message,
                       "read_error_category": category,
                       "structure_status": "unknown", "native_sequence": [group_start, reading_order]})
        reading_order += 1

    def refs(item: Mapping[str, Any], field: str, owner: str) -> list[str]:
        values = item.get(field, [])
        if not isinstance(values, list):
            read_error(owner + "/" + field, "native references are not a list")
            return []
        result = []
        for index, child in enumerate(values):
            if isinstance(child, Mapping) and isinstance(child.get("$ref"), str):
                result.append(child["$ref"])
            else:
                read_error(f"{owner}/{field}/{index}", "malformed native reference")
        return result

    def visit(item: Mapping[str, Any], ref: str) -> None:
        nonlocal reading_order
        if ref in seen:
            return
        seen.add(ref)
        order = reading_order
        reading_order += 1
        identity = full_ref(ref)
        child_refs = []
        native_children = refs(item, "children", ref)
        reference_refs = {
            field: refs(item, field, ref)
            for field in ("captions", "footnotes", "references")
        }
        native_references = {field: [full_ref(value) for value in values]
                             for field, values in reference_refs.items()}
        child_refs.extend(native_children)
        for field in ("captions", "footnotes", "references"):
            child_refs.extend(reference_refs[field])
        parent = item.get("parent")
        parent_id = full_ref(parent["$ref"]) if isinstance(parent, Mapping) and parent.get("$ref") else None
        all_provenance = [{**p, "page_dimensions": dimensions(p["page_no"]),
                           "coordinate_system": "pdf_points", "source": "native_prov",
                           "coordinate_origin": (p.get("bbox") or {}).get("coord_origin", "UNKNOWN")}
                          for p in item.get("prov", []) if p.get("page_no") is not None]
        provenance = [p for p in item.get("prov", []) if p.get("page_no") == page_number]
        if (ref.startswith("#/groups/") or ref in {"#/body", "#/furniture"}) and identity not in container_ids:
            if containers is not None:
                container = {"id": identity, "native_path": identity, "label": item.get("label"),
                    "name": item.get("name"), "parent_id": parent_id,
                    "native_children": [full_ref(value) for value in native_children],
                    "native_references": native_references,
                    "reading_order": order, "native_sequence": [group_start, order]}
                _identity(container, item, identity)
                containers.append(container)
                container_ids.add(identity)
        if provenance and identity not in emitted:
            emitted.add(identity)
            block = _block(item, identity, identity,
                           kind=str(item.get("label", "unknown")), text=item.get("text", ""),
                           box=provenance[0].get("bbox"), text_pointer=identity + "/text")
            _identity(block, item, identity)
            box = provenance[0].get("bbox") or {}
            _position(block, system="pdf_points", origin=box.get("coord_origin", "UNKNOWN"),
                      page=page_number, dimensions=dimensions(page_number))
            block.update(provenance=all_provenance,
                         provenance_pages=list(dict.fromkeys(p["page_no"] for p in all_provenance)),
                         parent_id=parent_id, native_parent=parent_id,
                         native_children=[full_ref(value) for value in native_children],
                         native_references=native_references,
                         reading_order=order, native_sequence=[group_start, order])
            if raw.get("research_assets", {}).get(ref):
                block["asset"] = raw["research_assets"][ref]
            if isinstance(item.get("data"), Mapping):
                block["native_table_data"] = {key: copy.deepcopy(item["data"][key])
                    for key in ("num_rows", "num_cols", "orientation") if key in item["data"]}
                cells = []
                for index, cell in enumerate(item["data"].get("table_cells", [])):
                    if not isinstance(cell, Mapping):
                        block.setdefault("read_errors", []).append({"native_path": identity + f"/data/table_cells/{index}",
                            "message": "non-object native table cell", "category": "candidate_native_structure"})
                        block["structure_status"] = "unknown"
                        continue
                    row, col = cell.get("start_row_offset_idx"), cell.get("start_col_offset_idx")
                    if row is None or col is None:
                        continue
                    cell_path = identity + f"/data/table_cells/{index}"
                    cell_page = cell.get("page_no", cell.get("page"))
                    converted = {"id": cell_path, "native_path": cell_path,
                                 "row": row, "col": col,
                                 "row_span": cell.get("row_span", 1),
                                 "col_span": cell.get("col_span", 1), "text": cell.get("text", ""),
                                 "page": cell_page, "parent_id": identity,
                                 "text_format": "plain",
                                 "provenance_pages": block["provenance_pages"],
                                 "native_sequence": [group_start, order, index]}
                    for source, target in (("column_header", "is_column_header"),
                                           ("row_header", "is_row_header")):
                        if source in cell:
                            converted[target] = cell[source]
                    if "bbox" in cell:
                        converted["bbox"] = cell["bbox"]
                        converted["coordinate_system"] = "pdf_points"
                        converted["coordinate_origin"] = cell["bbox"].get("coord_origin", "UNKNOWN") if isinstance(cell["bbox"], Mapping) else "UNKNOWN"
                        converted["bbox_page"] = cell_page
                        if cell_page is not None:
                            converted["page_dimensions"] = dimensions(cell_page)
                    for key in ("id", "inline_annotations", "annotations", "notes", "links", "formatting"):
                        if key in cell:
                            converted["native_id" if key == "id" else key] = cell[key]
                    converted.update(_docling_cell_fields(cell, document, pointer))
                    cells.append(converted)
                block["cells"] = cells
            blocks.append(block)
        for child_ref in child_refs:
            try:
                visit(resolve(child_ref), child_ref)
            except (NativeReadError, KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
                read_error(child_ref, f"{type(exc).__name__}: {exc}",
                           "candidate_native_structure" if isinstance(exc, NativeReadError) else "engineering_failure")

    for tree in ("body", "furniture"):
        if isinstance(document.get(tree), Mapping):
            visit(document[tree], "#/" + tree)
    return blocks


READERS = {"docling": read_docling, "glm": read_glm, "paddle": read_paddle,
           "mineru": read_mineru, "visual": read_visual}
