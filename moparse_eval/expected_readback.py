"""Read existing authored expected content for output evaluation only.

No PDF is opened, no reference is changed, and no reference truth or review
status is inferred. Targets are a transient syntax view of the existing text.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from .adapters import html_cells, markdown_cells
from .packaging import inside, read_json
from .representations import visible_text

MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable("table")



class ExpectedReadError(ValueError):
    """The evaluation reader must be repaired before publishing a grade."""


@dataclass
class Element:
    kind: str
    text: str
    lines: tuple[int, int]
    raw: str
    headings: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    has_children: bool = False
    cells: list[dict[str, Any]] = field(default_factory=list)
    list_span: tuple[int, int] | None = None
    part_index: int | None = None
    native_heading_level: int | None = None


def inline_text(text: str) -> str:
    return visible_text(text, "markdown").strip()


def elements(markdown: str) -> list[Element]:
    """Read public Markdown syntax with physical lines, without target data."""
    lines = markdown.splitlines(keepends=True)
    tokens = MARKDOWN.parse(markdown)
    result: list[Element] = []
    headings: list[tuple[int, str]] = []
    items: list[dict[str, Any]] = []
    lists: list[tuple[int, int]] = []
    table_depth = 0
    for index, token in enumerate(tokens):
        if token.type == "table_open":
            table_depth += 1
            if token.map is None:
                raise ExpectedReadError("Markdown table has no source location")
            a, b = token.map
            raw = "".join(lines[a:b])
            result.append(Element("table", "", (a + 1, b), raw,
                                  tuple(t for _, t in headings), cells=markdown_cells(raw, f"markdown:L{a + 1}")))
        elif token.type == "table_close":
            table_depth -= 1
        elif table_depth:
            continue
        elif token.type in {"bullet_list_open", "ordered_list_open"}:
            if token.map is None:
                raise ExpectedReadError("Markdown list has no source location")
            lists.append((token.map[0] + 1, token.map[1]))
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            lists.pop()
        elif token.type == "list_item_open":
            if items and items[-1]["element"] is not None:
                items[-1]["element"].has_children = True
            items.append({"element": None})
        elif token.type == "list_item_close":
            items.pop()
        elif token.type == "inline" and token.map:
            previous = tokens[index - 1]
            a, b = token.map
            raw = "".join(lines[a:b])
            text = inline_text(token.content)
            if not text and token.children and any(c.type == "image" for c in token.children):
                text = " ".join(c.content for c in token.children if c.type == "image")
            parents = tuple(item["element"].text for item in items[:-1] if item["element"])
            if previous.type == "heading_open":
                level = int(previous.tag[1:])
                headings = [(n, t) for n, t in headings if n < level]
                element = Element("heading", text, (a + 1, b), raw, tuple(t for _, t in headings), native_heading_level=level)
                headings.append((level, text))
            else:
                image = token.children is not None and bool(token.children) and all(c.type in {"image", "softbreak", "hardbreak"}
                                                       for c in token.children)
                element = Element("image_caption" if image else "item" if items else "text",
                                  text, (a + 1, b), raw, tuple(t for _, t in headings), parents)
                if items and items[-1]["element"] is None:
                    items[-1]["element"] = element
            result.append(element)
            element.list_span = lists[0] if lists else None
        elif token.type in {"fence", "code_block", "html_block"} and token.map:
            a, b = token.map
            raw = "".join(lines[a:b])
            if token.type == "html_block" and re.search(r"<table\b", raw, re.I):
                result.append(Element("table", "", (a + 1, b), raw,
                                      tuple(t for _, t in headings), cells=html_cells(raw, f"markdown:L{a + 1}")))
            elif token.type == "html_block" and re.fullmatch(r"\s*<!--.*?-->\s*", raw, re.S):
                continue
            else:
                text = visible_text(raw, "html") if token.type == "html_block" else token.content
                if text.strip():
                    result.append(Element("text", text.strip(), (a + 1, b), raw,
                                          tuple(t for _, t in headings)))
    return result


def declared_scope(sample: dict[str, Any], expected_root: Path) -> tuple[Path, list[dict[str, Any]]]:
    """Consume existing selection declarations; do not validate corpus truth."""
    directory = inside(expected_root, str(sample["document_id"]))
    manifest = read_json(directory / "manifest.json")
    source = inside(directory, manifest["markdown"]["path"])
    selected = set(sample["source_pages"])
    scopes = []
    for entry in manifest.get("source_map", {}).get("entries", []):
        declared_pages = set(entry.get("source_pages", []))
        pages = declared_pages & selected
        if not pages:
            continue
        bounds = entry.get("markdown_lines")
        if (not isinstance(bounds, list) or len(bounds) != 2
                or any(type(value) is not int for value in bounds)
                or bounds[0] < 1 or bounds[1] < bounds[0]):
            raise ExpectedReadError("declared expected scope has no readable line range")
        scopes.append({
            "lines": list(bounds),
            "pages": [i + 1 for i, page in enumerate(sample["source_pages"]) if page in pages],
            "declared_source_pages": sorted(declared_pages),
            "outside_source_pages": sorted(declared_pages - selected),
        })
    if not scopes:
        raise ExpectedReadError(f"no declared expected scope for sample {sample['id']}")
    return source, scopes


def _intervals(bounds: tuple[int, int], scopes: list[dict[str, Any]]) -> list[tuple[int, int]]:
    intervals = sorted((max(bounds[0], item["lines"][0]), min(bounds[1], item["lines"][1]))
                       for item in scopes if item["lines"][0] <= bounds[1] and bounds[0] <= item["lines"][1])
    result: list[tuple[int, int]] = []
    for start, end in intervals:
        if result and start <= result[-1][1] + 1:
            result[-1] = result[-1][0], max(result[-1][1], end)
        else:
            result.append((start, end))
    return result


def _source_context(element: Element, source: Path, kind: str) -> dict[str, Any]:
    return {"kind": kind, "text": element.text, "raw": element.raw,
            "reference": {"path": str(source), "lines": list(element.lines)}}


def _explicit_context(text: str) -> bool:
    """Recognize printed context declarations without assigning their scope."""
    return bool(re.match(r"^(?:单位|單位|Units?|币种|幣種|Currency|期间|期間|Period|Year|年度)\s*[:：=]", text, re.I)
                or re.fullmatch(r"(?:19|20)\d{2}\s*年(?:度|末)?[。.]?", text.strip())
                or re.match(r"^expressed\s+in\b", text, re.I))


def _context_continues(element: Element) -> bool:
    """A printed unit cannot jump across an image or unrelated prose.

    Tables, list records and explicitly labelled records may still be in the
    declaration's local scope. This does not assert their business meaning.
    """
    return (element.kind in {"table", "item"} or _explicit_context(element.text)
            or element.kind == "text" and bool(re.match(r"^[^:：=\n]{1,100}[:：=]\s*\S", element.text)))


def _context_kind(text: str) -> str:
    key = re.split(r"[:：=]", text, maxsplit=1)[0].strip().casefold()
    if re.fullmatch(r"units?|单位|單位|expressed\s+in.*", key):
        return "unit"
    if re.fullmatch(r"currency|币种|幣種", key):
        return "currency"
    return "period"


def read_expected(sample: dict[str, Any], expected_root: Path, *,
                  cache: dict[Path, list[Element]] | None = None) -> dict[str, Any]:
    """Expose selected authored syntax, without compiling business answers.

    Ancestors and explicit context outside the selection are retained as
    evidence of a possible input boundary. They are never injected as units,
    periods, identities or other candidate obligations by this syntax reader.
    """
    source, scopes = declared_scope(sample, expected_root)
    content = source.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    if any(scope["lines"][1] > len(lines) for scope in scopes):
        raise ExpectedReadError("declared expected line range cannot be read")
    if cache is not None and source in cache:
        document = cache[source]
    else:
        document = elements(content)
        if cache is not None:
            cache[source] = document
    selected: list[dict[str, Any]] = []
    heading_stack: list[Element] = []
    prior_context: list[Element] = []
    seen_items: list[Element] = []
    for element in document:
        if element.kind == "heading":
            level = element.native_heading_level or 1
            heading_stack = [heading for heading in heading_stack
                             if (heading.native_heading_level or 1) < level]
            heading_stack.append(element)
            prior_context = []
        if not _context_continues(element):
            prior_context = []
        if _explicit_context(element.text):
            prior_context = [old for old in prior_context if _context_kind(old.text) != _context_kind(element.text)]
        intervals = _intervals(element.lines, scopes)
        if not intervals:
            if _explicit_context(element.text):
                prior_context.append(element)
            if element.kind == "item":
                seen_items.append(element)
            continue
        external = [_source_context(heading, source, "heading") for heading in heading_stack
                    if not _intervals(heading.lines, scopes)]
        external.extend(_source_context(context, source, "explicit_unit_or_period")
                        for context in prior_context if not _intervals(context.lines, scopes))
        for depth, parent in enumerate(element.parents):
            matches = [item for item in seen_items if item.text == parent
                       and len(item.parents) == depth and item.list_span == element.list_span]
            if matches and not _intervals(matches[-1].lines, scopes):
                external.append(_source_context(matches[-1], source, "list_parent"))
        for scope in scopes:
            if scope["outside_source_pages"] and _intervals(element.lines, [scope]):
                external.append({"kind": "mixed_page_selection_declaration",
                                 "reference": {"path": str(source), "lines": scope["lines"]},
                                 "declared_source_pages": scope["declared_source_pages"],
                                 "outside_source_pages": scope["outside_source_pages"]})
        parts: list[Element] = []
        if intervals == [element.lines]:
            parts.append(element)
        else:
            external.append(_source_context(element, source, "partial_syntax_selection"))
            for start, end in intervals:
                fragment = "".join(lines[start - 1:end])
                for part in elements(fragment):
                    part.lines = (part.lines[0] + start - 1, part.lines[1] + start - 1)
                    part.headings = element.headings
                    part.parents = element.parents
                    parts.append(part)
        for part in parts:
            covering = [scope for scope in scopes if _intervals(part.lines, [scope])]
            reference = {"path": str(source), "lines": list(part.lines)}
            target: dict[str, Any] = {
                "id": f"expected:L{part.lines[0]}-{part.lines[1]}:{len(selected)}",
                "kind": part.kind, "text": part.text, "raw_text": part.text, "raw": part.raw,
                "cells": copy.deepcopy(part.cells), "reference": reference,
                "pages": sorted({page for scope in covering for page in scope["pages"]}),
                "context": [*part.headings, part.text] if part.kind == "heading" else list(part.headings),
                "selected_heading_context": [
                    {"text": heading.text, "reference": {"path": str(source), "lines": list(heading.lines)}}
                    for heading in heading_stack if _intervals(heading.lines, scopes)
                ],
                "parents": list(part.parents), "list_span": part.list_span,
                "has_children": part.has_children,
                "heading_level": part.native_heading_level if part.kind == "heading" else None,
                "outside_selection_context": copy.deepcopy(external),
            }
            selected.append(target)
        if _explicit_context(element.text):
            prior_context.append(element)
        if element.kind == "item":
            seen_items.append(element)
    if not selected:
        raise ExpectedReadError(f"no expected content read for sample {sample['id']}")
    return {"sample_id": sample["id"], "document_id": sample["document_id"],
            **{key: copy.deepcopy(sample.get(key)) for key in (
                "family_id", "source_pages", "tags", "development_exposure", "source_category")},
            "scope": scopes, "targets": selected, "standard": "expected_only"}


def markdown_observation(markdown: str, *, sample_id: str, pipeline: str, pages: list[int]) -> dict[str, Any]:
    """Read delivered syntax only, without expected, hidden IR or record repair."""
    blocks = []
    for index, element in enumerate(elements(markdown)):
        identifier = f"markdown:L{element.lines[0]}:{index}"
        kind = ("table" if element.kind == "table" else "image" if element.kind == "image_caption"
                else "heading" if element.kind == "heading" else "text")
        block: dict[str, Any] = {
            "id": identifier, "kind": kind, "text": element.text, "text_format": "plain",
            "native_path": identifier, "provenance_pages": list(pages),
            "public_lines": list(element.lines), "public_raw": element.raw,
            "public_syntax_kind": element.kind, "public_has_children": element.has_children,
            "public_list_parents": list(element.parents),
        }
        if element.list_span:
            block["public_list_span"] = list(element.list_span)
        if element.kind == "heading":
            block["heading_level"] = element.native_heading_level
        if element.kind == "table":
            block["cells"] = copy.deepcopy(element.cells)
        blocks.append(block)
    return {"sample_id": sample_id, "pipeline": pipeline, "status": "success",
            "pages": [{"page": pages[0] if len(pages) == 1 else None, "blocks": blocks}],
            "relations": [], "assets": []}
