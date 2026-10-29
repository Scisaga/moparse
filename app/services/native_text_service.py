"""Region-owned native prose selection for MO-Parse service delivery.

This service consumes already-read PDF evidence and candidate block geometry.
It does not parse a PDF, call a model, inspect references, infer table roles or
replace a document with a font-based native Markdown rendering.
"""

from __future__ import annotations

import asyncio
import html
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult, PageSourceKind, SelectionStrategy
from app.parsers.base import ParserCancelledError
from app.services.evidence_service import NativeBlock, PageEvidence
from app.services.export_service import ExportService
from app.utils.deadline import remaining_timeout

Box = tuple[float, float, float, float]
_TEXT_ROLES = {"text", "paragraph", "title", "heading", "list", "reference"}
_PREFIX = re.compile(r"^(?P<prefix>[ \t]{0,3}(?:#{1,6}[ \t]+|[-+*][ \t]+|\d+[.)][ \t]+|>[ \t]?))")
_RICH = re.compile(r"[`*_\[\]<>|]|\n[ \t]*(?:#{1,6}\s|[-+*]\s|\d+[.)]\s|>)")
_NUMERIC = re.compile(r"^[\W\d_]+$", re.UNICODE)
_CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]")


@dataclass(frozen=True, slots=True)
class _Region:
    ordinal: int
    box: Box
    markdown: str
    start: int
    end: int


def _box(value: object) -> Box | None:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        return None
    try:
        a, b, c, d = (float(v) for v in value)
    except (ValueError, TypeError):
        return None
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in (a, b, c, d)):
        return None
    return (a, b, c, d) if a < c and b < d else None


def _intersection(a: Box, b: Box) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )


def _area(box: Box) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _same_column(a: Box, b: Box) -> bool:
    overlap = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    # A page-wide caption overlaps every narrow column, but does not belong
    # between its paragraphs. Require comparable horizontal envelopes.
    return overlap >= max(a[2] - a[0], b[2] - b[0]) * 0.8


def _contains(outer: Box, inner: Box) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def _source_box(block: NativeBlock, evidence: PageEvidence) -> Box | None:
    """Retain out-of-page geometry so partial source coverage cannot disappear."""
    if evidence.page_width <= 0 or evidence.page_height <= 0:
        return None
    a, b, c, d = block.bbox
    box = (a / evidence.page_width, b / evidence.page_height,
           c / evidence.page_width, d / evidence.page_height)
    if not all(math.isfinite(value) for value in box) or box[0] >= box[2] or box[1] >= box[3]:
        return None
    return box


def _key(text: str) -> str:
    return "".join(c for c in text if not c.isspace())


def _plain(markdown: str) -> str:
    return ExportService.markdown_to_text(markdown).strip()


def _source_text(blocks: list[NativeBlock]) -> str:
    """Join physical source lines without joining or inventing source words."""
    paragraphs = []
    for block in blocks:
        lines = [line.strip() for line in re.split(r"\r\n|\r|\n", block.text) if line.strip()]
        if not lines:
            continue
        text = lines[0]
        for line in lines[1:]:
            # Soft wrapping does not introduce spaces between Chinese glyphs.
            separator = "" if _CJK.search(text[-1]) or _CJK.search(line[0]) else " "
            text += separator + line
        paragraphs.append(text)
    return "\n\n".join(paragraphs)


def _width_text(text: str) -> str:
    """Apply only the declared ASCII-width equivalence, without rewriting evidence."""
    return "".join(chr(ord(char) - 0xFEE0) if 0xFF01 <= ord(char) <= 0xFF5E
                   else " " if char == "\u3000" else char for char in text)


def _equivalent_text(text: str) -> str:
    return re.sub(r"\s+", " ", _width_text(text)).strip()


def _source_paragraph(blocks: list[NativeBlock], parser_text: str) -> str | None:
    """Keep an existing paragraph's boundaries across physical PDF text seams.

    A source line or font block does not prove a paragraph or a word boundary.
    Only explicit source whitespace or uniquely aligned parser whitespace can
    separate those segments; source glyphs and whitespace within a line stay
    untouched. The caller checks the parser's structural envelope first.
    """
    segments: list[tuple[str, bool]] = []
    previous = ""
    for block in blocks:
        for line in re.split(r"\r\n|\r|\n", block.text):
            if not line.strip():
                continue
            explicit_space = bool(line[:1].isspace() or previous[-1:].isspace())
            segments.append((line.strip(), explicit_space))
            previous = line
    if not segments:
        return None
    source_key = _key(_width_text("".join(text for text, _ in segments)))
    parser_key = _key(_width_text(parser_text))
    parser_positions = [index for index, char in enumerate(parser_text) if not char.isspace()]
    matches = SequenceMatcher(None, source_key, parser_key, autojunk=False).get_matching_blocks()
    output = segments[0][0]
    position = len(_key(_width_text(output)))
    for text, explicit_space in segments[1:]:
        separator = None
        for match in matches:
            if not match.a < position < match.a + match.size:
                continue
            context = source_key[match.a:match.a + match.size]
            # SequenceMatcher chooses a tie deterministically, not uniquely.
            # Repeated contexts cannot authorize a particular parser boundary.
            source_at = source_key.find(context)
            parser_at = parser_key.find(context)
            if (source_key.find(context, source_at + 1) >= 0
                    or parser_key.find(context, parser_at + 1) >= 0):
                continue
            left = match.b + position - match.a - 1
            separator = parser_text[parser_positions[left] + 1:parser_positions[left + 1]]
            break
        if separator is None:
            if not explicit_space:
                return None
            separator = " "
        elif explicit_space and not separator:
            separator = " "
        # The caller must never flatten an existing multi-paragraph envelope.
        if re.search(r"\r?\n[ \t]*\r?\n", separator):
            return None
        output += separator + text
        position += len(_key(_width_text(text)))
    return output


def _healthy(text: str) -> bool:
    return bool(text.strip()) and not any(
        c == "\ufffd" or unicodedata.category(c) in {"Co", "Cs"}
        or (unicodedata.category(c) == "Cc" and c not in "\t\r\n")
        for c in text
    )


def _literal(text: str) -> str:
    text = html.escape(text, quote=False)
    # Entities keep apparent source Markdown literal in both CommonMark and
    # the existing service plaintext exporter, which retains backslash escapes.
    text = re.sub(r"[\\`*_\[\]{}|]", lambda match: f"&#{ord(match[0])};", text)
    # The PDF literal must not create a heading, list or thematic break.
    return re.sub(
        r"(?m)^([ \t]{0,3})([#+\-]|\d+[.)])(?=\s|$)",
        lambda match: match[1] + "".join(f"&#{ord(c)};" for c in match[2]), text,
    )


def _replace_plain(region: _Region, source: str) -> str | None:
    stripped = region.markdown.strip()
    match = _PREFIX.match(stripped)
    prefix = match.group("prefix") if match else ""
    body = stripped[len(prefix):]
    if _RICH.search(body) or "\n\n" in body:
        return None
    # A parser's heading/list/quote role survives; PDF typography adds no role.
    return prefix + _literal(source)


def _page_regions(markdown: str, raw_blocks: list[dict[str, object]]) -> tuple[list[_Region], list[Box]]:
    regions: list[_Region] = []
    excluded = []
    for ordinal, raw in enumerate(raw_blocks):
        if not isinstance(raw, dict):
            # Received malformed SDK neighbors stay in the preserved native
            # artifact, but cannot erase valid dictionaries on this page.
            continue
        box = _box(raw.get("bbox"))
        if box is None:
            continue
        role = str(raw.get("type", ""))
        value = raw.get("markdown")
        if role not in _TEXT_ROLES or raw.get("export_error") is not None:
            excluded.append(box)
            continue
        if not isinstance(value, str) or not value.strip() or markdown.count(value.strip()) != 1:
            # An unowned or duplicate rendering must not be globally replaced.
            excluded.append(box)
            continue
        value = value.strip()
        start = markdown.index(value)
        regions.append(_Region(ordinal, box, value, start, start + len(value)))
    # The same rendered span cannot be owned by two nested envelopes.
    ambiguous = {
        region.ordinal for region in regions for other in regions
        if region.ordinal != other.ordinal
        and max(region.start, other.start) < min(region.end, other.end)
    }
    excluded.extend(region.box for region in regions if region.ordinal in ambiguous)
    return [region for region in regions if region.ordinal not in ambiguous], excluded


def _excluded_boxes(result: DocumentParseResult, page: int, evidence: PageEvidence) -> list[Box]:
    boxes: list[Box] = []
    for value in [*result._table_fragments, *result._picture_candidates,
                  *result._source_regions, *result._page_furniture]:
        if getattr(value, "page_number", None) != page:
            continue
        box = _box(getattr(value, "normalized_bbox", None))
        if box is not None:
            boxes.append(box)
    # A detected grid is excluded from prose even when its purpose is unknown.
    boxes.extend(box for value in evidence.grid_regions if (box := _box(value)) is not None)
    # Evidence collection may exclude repeated margins from its body view.
    # Their source geometry must still protect a parser envelope that combines
    # them with real prose; a body-only subset is not a complete region witness.
    boxes.extend(box for block in evidence.excluded_native_blocks
                 if (box := _source_box(block, evidence)) is not None)
    return boxes


def _protected_spans(
    content: str, raw_blocks: list[dict[str, object]], result: DocumentParseResult, page: int,
) -> list[tuple[int, int]]:
    """Known source-owned renderings remain intact even if boxes disagree."""
    renderings = [raw.get("markdown") for raw in raw_blocks
                  if isinstance(raw, dict) and (
                      str(raw.get("type", "")) not in _TEXT_ROLES or raw.get("export_error") is not None)]
    renderings.extend(getattr(value, "rendered", None)
                      for value in [*result._table_fragments, *result._source_regions, *result._page_furniture]
                      if getattr(value, "page_number", None) == page)
    spans = set()
    for rendering in renderings:
        if not isinstance(rendering, str) or not rendering.strip():
            continue
        position = 0
        while (position := content.find(rendering, position)) >= 0:
            spans.add((position, position + len(rendering)))
            position += len(rendering)
    return sorted(spans)


def _eligible_blocks(evidence: PageEvidence, excluded: list[Box]) -> list[tuple[NativeBlock, Box]]:
    output: list[tuple[NativeBlock, Box]] = []
    if evidence.page_width <= 0 or evidence.page_height <= 0:
        return output
    for block in evidence._blocks_in_reading_order():
        box = _box(_source_box(block, evidence))
        if box is None or any(_intersection(box, banned) > 0 for banned in excluded):
            continue
        if block.source_overlap_risk or not _healthy(block.text):
            continue
        output.append((block, box))
    return output


def _prose(text: str) -> bool:
    content = _key(text)
    if len(content) < 12 or _NUMERIC.fullmatch(content):
        return False
    if "\t" in text or "|" in text:
        return False
    # Dense loose numerical lines are unresolved layout, not prose to flatten.
    return sum(c.isalpha() for c in content) >= len(content) * 0.55


class NativeTextService:
    """Select native prose only inside source-owned service regions."""

    async def apply_async(
        self,
        result: DocumentParseResult,
        evidence_by_page: Mapping[int, PageEvidence],
        options: ContentParseOptions,
        *,
        cancel_event: Any = None,
    ) -> dict[str, Any]:
        worker = asyncio.create_task(asyncio.to_thread(
            self.apply, result, evidence_by_page, options, cancel_event=cancel_event,
        ))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            # Repeated caller cancellation must not release ownership of a
            # thread that can still mutate this request's result. A subsequent
            # cancel may interrupt a shield await, but never the owned worker.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    # A received worker error also confirms its completion;
                    # cancellation remains the caller's primary outcome.
                    break
            if not worker.cancelled():
                worker.exception()
            raise

    def apply(
        self,
        result: DocumentParseResult,
        evidence_by_page: Mapping[int, PageEvidence],
        options: ContentParseOptions,
        *,
        cancel_event: Any = None,
    ) -> dict[str, Any]:
        if cancel_event is not None and cancel_event.is_set():
            raise ParserCancelledError("native prose selection cancelled before processing")
        existing = result._source_verification.get("native_text_reconstruction")
        if isinstance(existing, dict) and existing.get("policy") == "region-owned-native-prose":
            return existing
        report: dict[str, Any] = {
            "policy": "region-owned-native-prose", "pages": [],
            "replaced_regions": 0, "inserted_regions": 0, "preserved_regions": 0,
        }
        for page in result.pages:
            if cancel_event is not None and cancel_event.is_set():
                raise ParserCancelledError("native prose selection cancelled at page boundary")
            remaining_timeout(options)
            evidence = evidence_by_page.get(page.page_number)
            if evidence is None or evidence.source_kind not in {PageSourceKind.NATIVE, PageSourceKind.SPARSE}:
                continue
            raw = result._native_page_blocks.get(page.page_number, [])
            raw_container_unknown = not isinstance(raw, list)
            if raw_container_unknown:
                raw = []
            content = page.content or ""
            regions, excluded = _page_regions(content, raw)
            excluded.extend(_excluded_boxes(result, page.page_number, evidence))
            protected_spans = _protected_spans(content, raw, result, page.page_number)
            blocks = _eligible_blocks(evidence, excluded)
            all_native = [(block, _source_box(block, evidence))
                          for block in [*evidence.native_blocks, *evidence.excluded_native_blocks]]
            record: dict[str, Any] = {"page": page.page_number, "actions": [], "unresolved": [],
                                      "preserved": []}
            if raw_container_unknown:
                record["unresolved"].append({"reason": "native_page_blocks_not_list"})
            edits: list[tuple[int, int, str]] = []
            consumed: set[int] = set()
            anchors: list[_Region] = []
            insertion_exclusions = list(excluded)
            eligible_ids = {id(block) for block, _ in blocks}
            insertion_exclusions.extend(box for block, box in all_native
                                        if box is not None and id(block) not in eligible_ids)
            for region in regions:
                protected = [banned for banned in excluded if _intersection(region.box, banned) > 0]
                protected_renderings = [(start, end) for start, end in protected_spans
                                        if max(region.start, start) < min(region.end, end)]
                if protected or protected_renderings:
                    record["unresolved"].append({"region": region.ordinal,
                        "reason": "parser_region_crosses_protected_area",
                        "parser_markdown": region.markdown,
                        "normalized_bbox": list(region.box),
                        "protected_bboxes": [list(box) for box in protected],
                        "protected_rendered_spans": [list(span) for span in protected_renderings]})
                    insertion_exclusions.append(region.box)
                    continue
                owned = [index for index, (_, box) in enumerate(blocks)
                         if _intersection(box, region.box) >= _area(box) * 0.8]
                owned_ids = {id(blocks[index][0]) for index in owned}
                incomplete = []
                for source_index, (block, source_box) in enumerate(all_native):
                    if source_box is None:
                        incomplete.append({"native_block": source_index, "reason": "native_source_geometry_unavailable"})
                        continue
                    if _intersection(source_box, region.box) <= 0:
                        continue
                    if block.source_overlap_risk:
                        reason = "native_source_span_overlap"
                    elif not _healthy(block.text):
                        reason = "native_source_text_unhealthy"
                    elif _box(source_box) is None:
                        reason = "native_source_outside_page"
                    elif not _contains(region.box, source_box):
                        reason = "native_source_crosses_parser_region"
                    elif id(block) not in owned_ids:
                        reason = "native_source_not_eligible_for_region"
                    else:
                        continue
                    incomplete.append({"native_block": source_index, "reason": reason,
                                       "normalized_bbox": list(source_box)})
                if incomplete:
                    record["unresolved"].append({"region": region.ordinal,
                        "reason": "incomplete_native_region_coverage",
                        "parser_markdown": region.markdown, "sources": incomplete})
                    insertion_exclusions.append(region.box)
                    consumed.update(owned)
                    continue
                if not owned:
                    insertion_exclusions.append(region.box)
                    continue
                if any(index in consumed or sum(
                    _intersection(blocks[index][1], other.box) >= _area(blocks[index][1]) * 0.8
                    for other in regions
                ) != 1 for index in owned):
                    record["unresolved"].append({"region": region.ordinal, "reason": "ambiguous_native_region_owner"})
                    insertion_exclusions.append(region.box)
                    continue
                source_blocks = [blocks[index][0] for index in owned]
                source = _source_text(source_blocks)
                native_key, parser_key = _key(source), _key(_plain(region.markdown))
                if native_key == parser_key:
                    consumed.update(owned)
                    anchors.append(region)
                    continue
                # Geometry is necessary but insufficient for changing text.
                similarity = SequenceMatcher(None, parser_key, native_key, autojunk=False).ratio()
                if min(len(parser_key), len(native_key)) < 8 or similarity < 0.72:
                    record["unresolved"].append({"region": region.ordinal,
                        "reason": "native_parser_content_conflict", "native_text": source,
                        "parser_markdown": region.markdown, "similarity": similarity})
                    consumed.update(owned)
                    insertion_exclusions.append(region.box)
                    continue
                replacement = _replace_plain(region, source)
                if replacement is None:
                    record["unresolved"].append({"region": region.ordinal, "reason": "rich_parser_structure_preserved"})
                    consumed.update(owned)
                    anchors.append(region)
                    continue
                source_paragraph = _source_paragraph(source_blocks, _plain(region.markdown))
                source_diagnostic = {"raw_native_text": [block.text for block in source_blocks],
                                     "native_text": source,
                                     "parser_markdown": region.markdown}
                if source_paragraph is None:
                    record["unresolved"].append({"region": region.ordinal,
                        "reason": "native_paragraph_boundary_unresolved", **source_diagnostic})
                    consumed.update(owned)
                    insertion_exclusions.append(region.box)
                    continue
                if _equivalent_text(source_paragraph) == _equivalent_text(_plain(region.markdown)):
                    record["preserved"].append({"region": region.ordinal,
                        "reason": "equivalent_native_region_preserved", **source_diagnostic,
                        "rendered_native_text": source_paragraph})
                    report["preserved_regions"] += 1
                    consumed.update(owned)
                    anchors.append(region)
                    continue
                replacement = _replace_plain(region, source_paragraph)
                assert replacement is not None  # Structural preflight above used the same region.
                edits.append((region.start, region.end, replacement))
                consumed.update(owned)
                anchors.append(region)
                record["actions"].append({"action": "selected_native_region", "region": region.ordinal,
                    "normalized_bbox": list(region.box), "native_text": source_paragraph,
                    "raw_native_text": source_diagnostic["raw_native_text"],
                    "physical_native_text": source,
                    "rendered_replacement": replacement, "parser_markdown": region.markdown})
                report["replaced_regions"] += 1

            inserted: dict[int, list[str]] = {}
            visible = _key(_plain(content))
            for index, (block, box) in enumerate(blocks):
                source = _source_text([block])
                if index in consumed or not _prose(source) or _key(source) in visible:
                    continue
                if any(other_box is None for _, other_box in all_native):
                    record["unresolved"].append({"native_block": index,
                        "reason": "native_prose_source_geometry_unavailable"})
                    continue
                if any(other is not block and other_box is not None
                       and _intersection(box, other_box) > 0 for other, other_box in all_native):
                    record["unresolved"].append({"native_block": index,
                        "reason": "overlapping_native_prose_sources"})
                    continue
                if any(_intersection(box, banned) > 0 for banned in insertion_exclusions):
                    record["unresolved"].append({"native_block": index,
                        "reason": "native_prose_overlaps_preserved_region"})
                    continue
                same = [r for r in anchors if _same_column(box, r.box)]
                before = [r for r in same if r.box[3] <= box[1] + 0.003]
                after = [r for r in same if box[3] <= r.box[1] + 0.003]
                left = max(before, key=lambda r: r.box[3], default=None)
                right = min(after, key=lambda r: r.box[1], default=None)
                choices: list[tuple[int, Box]] = []
                if left is not None and right is not None and left.end <= right.start:
                    choices = [
                        (left.end, (box[0], left.box[3], box[2], box[3])),
                        (right.start, (box[0], box[1], box[2], right.box[1])),
                    ]
                elif len(anchors) == len(regions) == 1 and left is not None:
                    choices = [(left.end, (box[0], left.box[3], box[2], box[3]))]
                elif len(anchors) == len(regions) == 1 and right is not None:
                    choices = [(right.start, (box[0], box[1], box[2], right.box[1]))]
                if not choices:
                    record["unresolved"].append({"native_block": index, "reason": "missing_prose_order_not_uniquely_anchored"})
                    continue
                # Never insert prose through an intervening protected region.
                position = next((position for position, gap in choices
                                 if not any(_intersection(gap, banned) > 0 for banned in insertion_exclusions)
                                 and not any(start < position < end for start, end in protected_spans)), None)
                if position is None:
                    record["unresolved"].append({"native_block": index, "reason": "protected_region_between_prose_anchors"})
                    continue
                inserted.setdefault(position, []).append(_literal(source))
                visible += _key(source)
                record["actions"].append({"action": "inserted_native_prose", "native_block": index,
                    "normalized_bbox": list(box), "native_text": source})
                report["inserted_regions"] += 1
            edits.extend((position, position, "\n\n" + "\n\n".join(values) + "\n\n")
                         for position, values in inserted.items())
            # End/start insertions survive an adjacent exact-span replacement.
            for start, end, replacement in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
                content = content[:start] + replacement + content[end:]
            if edits:
                page.content = content
                page.plain_text = None
                if page.diagnostics is not None:
                    page.diagnostics.selected_strategy = SelectionStrategy.NATIVE_REPAIR
            report["pages"].append(record)
        result._source_verification["native_text_reconstruction"] = report
        return report
