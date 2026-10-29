"""Adapt saved official MinerU visual blocks for MO-Parse content processing.

No PDF text, auxiliary parser, inference or reference material is used. Role
headings are display boundaries, not a recovered hierarchy of business facts.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.parsers.mineru_native_remote import render_mineru_page_evidence


def project_visual_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    output = []
    for position, raw in enumerate(blocks):
        if not isinstance(raw, dict) or (raw.get("content") is not None and not isinstance(raw.get("content"), str)):
            output.append({"type": "unknown", "export_error": "invalid_visual_block",
                           "content": raw, "index": position})
            continue
        block = copy.deepcopy(raw)
        # The fixed SDK declares Optional[str]; layout-only list containers and
        # image regions legitimately have no recognized text. Preserve that
        # native value while making the display projection explicitly empty.
        role, content = block.get("type", "text"), block.get("content") or ""
        block["index"] = position
        block["markdown"] = content
        if role in {"title", "doc_title", "paragraph_title"} and content.strip():
            if not re.match(r"^\s{0,3}#{1,6}\s", content):
                block["markdown"] = ("# " if role == "doc_title" else "## ") + content
        elif role == "table":
            block["content"] = [{"type": "table_body", "content": content,
                                 "markdown": content, "bbox": block.get("bbox")}]
        elif role in {"image", "figure", "chart"}:
            block["source_images"] = [{"bbox": block.get("bbox")}]
            block["markdown"] = "<!-- image -->" + ("\n\n" + content if content.strip() else "")
        output.append(block)
    return output


def render_visual_page(blocks: list[Any], page: int, *, warnings: list[Any]) -> tuple[Any, ...]:
    projected = project_visual_blocks(blocks)
    rendered = render_mineru_page_evidence({"page_number": page, "blocks": projected}, warnings=warnings)
    return (*rendered, projected)
