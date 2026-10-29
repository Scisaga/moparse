"""Read explicit native references and declared heading syntax without Gold."""

from __future__ import annotations

from typing import Any

_HEADING_ROLES = {"section_header", "heading", "title", "doc_title", "paragraph_title"}
HEADING_SCOPE_EVIDENCE = "declared_native_heading_level_and_sequence"


def heading_evidence(block: dict[str, Any]) -> dict[str, Any]:
    """Describe native heading evidence without assigning levels to type labels."""
    level = block.get("level")
    kind = block.get("kind")
    role = ("heading" if kind in _HEADING_ROLES else
            "page_furniture" if kind in {"header", "footer", "page_header", "page_footer"} else "other")
    result = {
        "id": block.get("id"), "native_path": block.get("native_path"),
        "native_kind": kind, "role": role, "declared_level": level,
        "markdown_heading_level": None, "resolved_level": None,
        "status": "role_only_without_level" if role == "heading" else "not_heading",
        "level_source": None, "markdown_status": "not_declared",
    }
    exported = block.get("native_export_markdown")
    if block.get("text_format") == "markdown" or isinstance(exported, str):
        from markdown_it import MarkdownIt

        from .representations import visible_text

        source = "native_export_markdown" if isinstance(exported, str) else "text"
        tokens = MarkdownIt("commonmark").parse(exported if isinstance(exported, str) else block.get("text", ""))
        result["markdown_status"] = "not_heading"
        if len(tokens) == 3 and tokens[0].type == "heading_open" and tokens[2].type == "heading_close":
            result["markdown_heading_level"] = int(tokens[0].tag[1:])
            if visible_text(tokens[1].content, "markdown").strip():
                result.update(resolved_level=result["markdown_heading_level"],
                              status="markdown_heading", level_source=source,
                              markdown_status="single_heading")
            else:
                result.update(status="empty_markdown_heading", markdown_status="empty_heading")
        elif any(token.type == "heading_open" for token in tokens):
            result["markdown_status"] = "mixed_scope"
    if role == "heading" and type(level) is int and level > 0:
        result.update(resolved_level=level, status="declared_level", level_source="level")
    return result


def _heading_level(block: dict[str, Any]) -> int | None:
    return heading_evidence(block)["resolved_level"]


def native_relations(observation: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only relationships supported by native fields or markup scope.

    No coordinates, string similarity, neighboring-label guesses or reference
    annotations are used. Markdown heading scope follows its actual sequence;
    a title label without a declared level does not manufacture a hierarchy.
    """
    blocks = [block for page in observation.get("pages", []) for block in page.get("blocks", [])]
    items = [*observation.get("native_containers", []), *blocks]
    edges = list(observation.get("relations", []))

    def add(kind: str, source: str, target: str, evidence: str) -> None:
        if source != target:
            edges.append({"type": kind, "source": source, "target": target, "evidence": evidence})

    for item in items:
        identity = item["id"]
        for child in item.get("native_children", []):
            add("contains", identity, child, "native_children")
        if item.get("parent_id"):
            add("contains", item["parent_id"], identity, "native_parent")
        refs = item.get("native_references", {})
        for caption in refs.get("captions", []):
            add("caption_of", caption, identity, "native_caption_reference")
        for note in refs.get("footnotes", []):
            add("footnote_of", note, identity, "native_footnote_reference")
        for reference in refs.get("references", []):
            add("references", identity, reference, "native_reference")
        for cell in item.get("cells", []):
            add("contains", identity, cell["id"], "native_table_cell_structure")
    # Typed nested MinerU objects carry explicit roles inside their container.
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for block in blocks:
        if block.get("parent_id"):
            by_parent.setdefault(block["parent_id"], []).append(block)
    for children in by_parent.values():
        bodies = [item for item in children if item.get("kind") in {"image_body", "table_body", "chart_body"}]
        if len(bodies) == 1:
            for item in children:
                kind = item.get("kind", "")
                if kind in {"image_caption", "table_caption", "chart_caption"}:
                    add("caption_of", item["id"], bodies[0]["id"], "native_typed_caption_in_container")
                elif kind in {"image_footnote", "table_footnote", "chart_footnote"}:
                    add("footnote_of", item["id"], bodies[0]["id"], "native_typed_footnote_in_container")
    headings: list[tuple[int, str]] = []
    for block in sorted(blocks, key=lambda item: item.get("native_sequence", [])):
        level = _heading_level(block)
        if level is not None:
            while headings and headings[-1][0] >= level:
                headings.pop()
        if headings:
            add("heading_of", headings[-1][1], block["id"], HEADING_SCOPE_EVIDENCE)
        if level is not None:
            headings.append((level, block["id"]))
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        unique.setdefault((edge["type"], edge["source"], edge["target"]), edge)
    return list(unique.values())
