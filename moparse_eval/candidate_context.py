"""Read bounded, printed table scopes without references or source PDFs.

A caption bounds a reading range; it does not merge physical tables. Existing
column labels can qualify an uninterrupted, headerless fragment in that range.
The certificate retains the original header cells and is revoked by a new
caption, heading, paragraph, unit declaration, note or image. Proximity and
equal column counts without a printed scope never produce a certificate.
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from .representations import visible_text

_FURNITURE = {"header", "footer", "page_header", "page_footer", "page_number", "number"}


def _grid(block: dict[str, Any]) -> list[dict[str, Any]]:
    return [cell for cell in block.get("cells", [])
            if type(cell.get("row")) is int and type(cell.get("col")) is int]


def annotate_caption_ranges(observation: dict[str, Any]) -> None:
    """Annotate a derived observation only, never its saved native objects."""
    from .information import business_scope_text
    from .information_reading import (
        _PRINTED_CAPTION,
        _PRINTED_REPORT_TITLE,
        _header_rows,
        _printed_period_caption,
        report_title_transition,
        unit_scope_literal,
    )

    stream = [block for page in observation.get("pages", []) for block in page.get("blocks", [])
              if block.get("kind") != "text_record"]
    by_id = {block.get("id"): block for block in stream}
    report_titles = Counter(business_scope_text(text) for block in stream if not block.get('cells')
        and (text:=visible_text(str(block.get('text','')),block.get('text_format','plain')).strip())
        and _PRINTED_REPORT_TITLE.fullmatch(text))
    stable_report = {key for key,count in report_titles.items() if count>=2} if len(report_titles)==1 else set()
    report_markers = [{'position':index,'text':visible_text(str(block.get('text','')),block.get('text_format','plain')).strip()}
                      for index,block in enumerate(stream) if not block.get('cells')]
    caption = None
    certificate = None
    for index, block in enumerate(stream):
        kind = block.get("kind", "")
        text = visible_text(str(block.get("text", "")), block.get("text_format", "plain")).strip()
        cells = _grid(block)
        if kind in _FURNITURE:
            continue
        if not cells and kind!='doc_title' and business_scope_text(text) in stable_report:
            continue
        if not cells and _PRINTED_REPORT_TITLE.fullmatch(text) and not report_title_transition(text,kind,index,report_markers):
            continue
        references = block.get("native_references", {}).get("captions", []) if cells else []
        linked = [by_id[ref] for ref in references if ref in by_id]
        if linked and len(linked) == len(references):
            caption = {"id": linked[0].get("id"), "native_path": linked[0].get("native_path", linked[0].get("id")),
                       "text": " ".join(visible_text(str(item.get("text", "")), item.get("text_format", "plain")) for item in linked),
                       "kind": "table_caption", "readback_evidence": "native_caption_references",
                       "native_references": list(references)}
            certificate = None
        next_grid = []
        if text and not cells:
            for following in stream[index + 1:]:
                if following.get("kind") in _FURNITURE:
                    continue
                next_grid = _grid(following)
                break
        printed_caption = not cells and text and (
            kind in {"table_caption", "caption"}
            or unit_scope_literal(text)
            or _PRINTED_CAPTION.match(text)
            or next_grid and _printed_period_caption(text, next_grid)
        )
        if printed_caption:
            if caption and block.get("id") in caption.get("native_references", []):
                # A linked caption can follow its table in native tree order.
                # Visiting that same node does not start a second table scope.
                continue
            caption = {"id": block.get("id"), "native_path": block.get("native_path", block.get("id")),
                       "text": text, "kind": "table_caption", "readback_evidence": "printed_caption_range"}
            certificate = None
            continue
        if not cells:
            if text or kind in {"image", "picture", "figure", "chart"}:
                caption = certificate = None
            continue
        if caption:
            for cell in block.get("cells", []):
                contexts = cell.setdefault("information_context", [])
                if not any(item.get("id") == caption["id"] and item.get("text") == caption["text"] for item in contexts):
                    contexts.append(copy.deepcopy(caption))
                cell["information_caption_range"] = copy.deepcopy(caption)
        header_rows = _header_rows(cells)
        headers = [cell for cell in cells if cell["row"] in header_rows and str(cell.get("text", "")).strip()]
        width = max(cell["col"] + cell.get("col_span", 1) for cell in cells)
        if headers:
            paths = {column: sorted([cell for cell in headers
                                     if cell["col"] <= column < cell["col"] + cell.get("col_span", 1)],
                                    key=lambda cell: (cell["row"], cell["col"]))
                     for column in range(width)}
            certificate = ({"scope": copy.deepcopy(caption), "paths": copy.deepcopy(paths),
                            "width": width, "header_body": block.get("id")}
                           if caption and width >= 2 and all(paths.values()) else None)
            continue
        if not caption or not certificate or certificate["scope"]["id"] != caption["id"]:
            certificate = None
            continue
        if width != certificate["width"]:
            certificate = None
            continue
        for cell in cells:
            # No row or column is fabricated or moved; the original cells
            # remain separate, and each inherited label names its real origin.
            columns = range(cell["col"], cell["col"] + cell.get("col_span", 1))
            paths = [certificate["paths"].get(column, []) for column in columns]
            if not paths or any([h["id"] for h in path] != [h["id"] for h in paths[0]] for path in paths):
                continue
            cell["information_inherited_headers"] = copy.deepcopy(paths[0])
            cell["information_header_readback"] = {
                "method": "uninterrupted_printed_caption_range",
                "caption": copy.deepcopy(caption), "header_body": certificate["header_body"],
                "candidate_body": block.get("id"),
            }
