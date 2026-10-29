"""Publish continuous business text, keeping assembly diagnostics out of it.

Only producer-owned markers, explicit pagination and declared continuations
are edited. No reference lookup, inferred fact or model call occurs here.
The edit ledger preserves exact character provenance for internal consumers.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from typing import Any

from markdown_it import MarkdownIt

from app.models.parse_result import DocumentParseResult, PipelineWarning, WarningSeverity
from app.services.export_service import ExportService

_OWNED_COMMENT = re.compile(
    r"<!--\s*(?:/?source-region(?:-image)?|source-page(?:-image)?|source-furniture|source-text|"
    r"table-(?:fragment|source|view-segment|structure)|logical-table|semantic-[a-z-]+|page)\s*:[\s\S]*?-->|<!--\s*image\s*-->"
)
_PAGE = re.compile(r"<!--\s*page:\s*([1-9][0-9]*)\s*-->")
_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_FURNITURE = {"header", "footer", "page_number"}
_PRODUCTION = re.compile(r"^(PATH|DRAFT|USER|MODIFY|TRANSLATE|EDIT(?:\s+EDIT)*\s+TRACE|LAYOUT|PAGE)\s*:")


def apply_text_edits(source: str, edits: list[dict[str, Any]]) -> str:
    """Apply an ordered, nonoverlapping ledger without reinterpreting content."""
    parts: list[str] = []
    cursor = 0
    for edit in edits:
        start, end = edit["start"], edit["end"]
        if type(start) is not int or type(end) is not int or not cursor <= start < end <= len(source):
            raise ValueError("invalid final text edit range")
        if not isinstance(edit["replacement"], str):
            raise ValueError("invalid final text replacement")
        parts.extend((source[cursor:start], edit["replacement"]))
        cursor = end
    parts.append(source[cursor:])
    return "".join(parts)


def map_text_offset(position: int, edits: list[dict[str, Any]], *, end: bool = False) -> int:
    shift = 0
    for edit in edits:
        a, b, text = edit["start"], edit["end"], edit["replacement"]
        if position < a or position == a and not end:
            break
        if position >= b:
            shift += len(text) - (b - a)
        else:
            return a + shift + (len(text) if end else 0)
    return position + shift


def _code_ranges(markdown: str) -> list[tuple[int, int]]:
    offsets = [0, *[m.end() for m in re.finditer(r"\r\n|\r|\n", markdown)]]
    if offsets[-1] != len(markdown):
        offsets.append(len(markdown))
    ranges = [(offsets[t.map[0]], offsets[t.map[1]])
              for t in MarkdownIt("commonmark").parse(markdown)
              if t.type in {"fence", "code_block"} and t.map]
    # Inline code's complete delimiter run must match; never clean its literal
    # example of a page comment as though the producer emitted that comment.
    for match in re.finditer(r"(?<![`\\])(`+)(?!`)", markdown):
        if any(a <= match.start() < b for a, b in ranges):
            continue
        close = re.search(r"(?<!`)" + re.escape(match[1]) + r"(?!`)", markdown[match.end():])
        if close and not re.search(r"\n\s*\n", markdown[match.end():match.end() + close.start()]):
            ranges.append((match.start(), match.end() + close.end()))
    return ranges


def _unique(source: str, text: str, start: int, end: int) -> tuple[int, int] | None:
    if not text:
        return None
    a = source.find(text, start, end)
    if a < 0 or source.find(text, a + 1, end) >= 0:
        return None
    return a, a + len(text)


def _page_ranges(source: str, protected: list[tuple[int, int]]) -> dict[int, tuple[int, int]]:
    markers = [m for m in _PAGE.finditer(source)
               if not any(a <= m.start() < b for a, b in protected)]
    counts = Counter(int(m[1]) for m in markers)
    return {int(m[1]): (m.end(), markers[i + 1].start() if i + 1 < len(markers) else len(source))
            for i, m in enumerate(markers) if counts[int(m[1])] == 1}


def _typed_inline_rendering(block: dict[str, Any]) -> str | None:
    """Render explicit native bold spans without CommonMark flanking ambiguity.

    Only the exact simple typed rendering is eligible. Literal Markdown,
    equations, unknown styles and already modified content remain unchanged.
    """
    children = block.get("content")
    if block.get("type") != "text" or not isinstance(children, list) or not children:
        return None
    old, new = [], []
    bold = False
    for child in children:
        if not isinstance(child, dict) or child.get("type") != "text":
            return None
        text, styles = child.get("content"), child.get("styles", [])
        if (not isinstance(text, str) or styles not in ([], ["bold"])
                or re.search(r"[\\`*_\[\]<>\r\n]", text)):
            return None
        marked = styles == ["bold"]
        bold |= marked
        old.append(f"**{text}**" if marked else text)
        escaped = html.escape(text, quote=False)
        new.append(f"<strong>{escaped}</strong>" if marked else escaped)
    return "".join(new) if bold and "".join(old) == block.get("markdown") else None


class FinalContentService:
    """Last text stage after table and image processing, before persistence."""

    def apply(self, result: DocumentParseResult) -> None:
        if result._final_text_evidence:
            return
        source = result.parse_result.renderings.markdown if result.parse_result else result.markdown
        protected = _code_ranges(source)
        pages = _page_ranges(source, protected)
        edits: list[dict[str, Any]] = []
        # Earlier readers already preserve malformed native bytes and valid
        # neighbors. An unreadable block is a continuation barrier, not a new
        # document failure; keep ordinal positions for source replacements.
        native_blocks = {number: [block if isinstance(block, dict) else {"type": "unknown"}
                                  for block in blocks]
                         for number, blocks in result._native_page_blocks.items()}
        text_processing = result._source_verification.get("native_text_reconstruction", {})
        if not isinstance(text_processing, dict):
            text_processing = {}
        replacements = {(page["page"], action["region"]): action["rendered_replacement"]
                        for page in text_processing.get("pages", []) for action in page.get("actions", [])
                        if action.get("action") == "selected_native_region"
                        and isinstance(action.get("rendered_replacement"), str)}

        def add(a: int, b: int, replacement: str, reason: str) -> None:
            if not a < b or any(a < y and b > x for x, y in protected):
                return
            edits.append({"start": a, "end": b, "replacement": replacement, "reason": reason})

        for marker in _OWNED_COMMENT.finditer(source):
            add(marker.start(), marker.end(), "", "internal_marker")
        for marker in re.finditer("\f", source):
            add(marker.start(), marker.end(), "", "physical_page_control")

        for number, blocks in native_blocks.items():
            for block in blocks:
                inline_rendered = _typed_inline_rendering(block)
                original_markdown = block.get("markdown")
                if inline_rendered is not None and isinstance(original_markdown, str) and number in pages:
                    found = _unique(source, original_markdown, *pages[number])
                    if found:
                        add(*found, inline_rendered, "explicit_native_inline_style")

        # A footer date/signature is business content. Only explicit page_number
        # roles and repeated short, nonnumeric headers are eligible for removal.
        header_seen: set[str] = set()
        furniture = list(result._page_furniture)
        for number, blocks in native_blocks.items():
            if number not in pages:
                continue
            production = {m[1] for block in blocks if block.get("type") == "footer"
                          and (m := _PRODUCTION.match(ExportService.markdown_to_text(str(block.get("markdown", ""))).strip()))}
            for ordinal, block in enumerate(blocks):
                role = block.get("type")
                rendered = replacements.get((number, ordinal), block.get("markdown"))
                if role not in _FURNITURE or not isinstance(rendered, str) or not rendered.strip():
                    continue
                literal = ExportService.markdown_to_text(rendered).strip()
                reason = None
                if role == "page_number" and re.fullmatch(r"[ \t\-–—]*\d{1,5}(?:\s*/\s*\d{1,5})?[ \t\-–—]*", literal):
                    reason = "explicit_page_number"
                elif role == "footer" and len(production) >= 2 and _PRODUCTION.match(
                    ExportService.markdown_to_text(str(block.get("markdown", ""))).strip(),
                ):
                    reason = "explicit_production_footer"
                elif role == "header" and 0 < len(literal) <= 80 and not re.search(r"\d", literal):
                    if literal in header_seen:
                        reason = "repeated_native_header"
                    header_seen.add(literal)
                if reason:
                    owners = [f for f in furniture if getattr(f, "page_number", None) == number
                              and str(getattr(f, "rendered", "")).endswith(rendered)]
                    owned_text = str(getattr(owners[0], "rendered", "")) if len(owners) == 1 else rendered
                    found = _unique(source, owned_text, *pages[number])
                    if found:
                        add(*found, "", reason)
                    elif reason == "explicit_production_footer":
                        # Source supplementation can repeat this typed footer.
                        # Remove exact standalone copies, never inline business text.
                        a, b = pages[number]
                        for occurrence in re.finditer(r"(?m)^" + re.escape(rendered) + r"[ \t]*$", source[a:b]):
                            add(a + occurrence.start(), a + occurrence.end(), "", reason)

        def filtered_gap(a: int, b: int) -> str:
            nested = [dict(e, start=e["start"] - a, end=e["end"] - a)
                      for e in _nonoverlapping(edits) if a <= e["start"] and e["end"] <= b]
            return apply_text_edits(source[a:b], nested)

        previous: tuple[int, dict[str, Any]] | None = None
        joins = []
        pending = []
        for number, blocks in native_blocks.items():
            for ordinal, original in enumerate(blocks):
                block = dict(original)
                if (number, ordinal) in replacements:
                    block["markdown"] = replacements[number, ordinal]
                role = str(block.get("type", ""))
                if role in _FURNITURE:
                    continue
                if role != "text":
                    previous = None
                    continue
                if block.get("continues_prev") is True or block.get("merge_prev") is True:
                    found = None
                    if previous is not None and 0 <= number - previous[0] <= 1:
                        old_number, old_block = previous
                        left = _unique(source, str(old_block.get("markdown") or ""), *pages.get(old_number, (0, 0)))
                        right = _unique(source, str(block.get("markdown") or ""), *pages.get(number, (0, 0)))
                        if left and right and left[1] < right[0] and not filtered_gap(left[1], right[0]).strip():
                            found = (left[1], right[0])
                            left_text = ExportService.markdown_to_text(str(old_block["markdown"]))
                            right_text = ExportService.markdown_to_text(str(block["markdown"]))
                            # Preserve every printed character, including a hyphen.
                            separator = "" if left_text and right_text and (
                                _CJK.search(left_text[-1]) or _CJK.search(right_text[0])
                            ) else " "
                            add(*found, separator, "declared_paragraph_continuation")
                            joins.append({"pages": [old_number, number], "input_range": list(found)})
                    if found is None:
                        pending.append({"page": number, "reason": "declared_continuation_has_no_unique_adjacent_text"})
                previous = (number, block)

        edits = _nonoverlapping(edits)
        final = apply_text_edits(source, edits)
        # Whitespace is kept in this stage so every published range has an exact
        # edit mapping. Paragraph joining edits already remove physical seams.
        result._final_text_evidence = {
            "assembly_markdown": source, "edits": edits,
            "joined_paragraphs": joins, "unresolved_continuations": pending,
            "operation_counts": dict(Counter(e["reason"] for e in edits)),
            "policy": "explicit_native_roles_and_continuations_no_fact_inference",
        }
        result.markdown = final
        result.plain_text = ExportService.markdown_to_text(final, source_regions=[])
        if result.parse_result:
            result.parse_result.renderings.markdown = final
            result.parse_result.renderings.plain_text = result.plain_text
            unresolved = [view for view in result._semantic_tables if view.status != "converted"]
            if unresolved:
                result.parse_result.status = "partial"
                result.warnings.append(PipelineWarning(
                    code="table_semantics_incomplete", backend="mo-parse-final-content",
                    message="some table relations remain unresolved; existing content is retained",
                    severity=WarningSeverity.WARNING,
                    details={"views": [view.view_id for view in unresolved]},
                ))


def _nonoverlapping(edits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A larger owned edit subsumes its nested marker removals."""
    output: list[dict[str, Any]] = []
    for edit in sorted(edits, key=lambda e: (e["start"], -e["end"])):
        if output and edit["start"] < output[-1]["end"]:
            if edit["end"] > output[-1]["end"]:
                raise ValueError("partially overlapping final content edits")
            continue
        output.append(edit)
    return output
