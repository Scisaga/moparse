"""Preserve literal PDF evidence when independent region types disagree.

Occurrence counts are permissive whole-page review observations, not a quality
score. Source-zero characters, punctuation and ambiguous math cannot reject a
table. The original typed table is retained privately if its structure becomes
unknown; no model character, period, value or relationship is repaired.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import math
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, TypeGuard

from markdown_it import MarkdownIt

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import (
    DocumentParseResult,
    PageSourceKind,
    PipelineWarning,
    SelectionStrategy,
    WarningSeverity,
)
from app.models.source import StoredSource
from app.models.source_evidence import (
    SourceGlyph,
    SourceRegionEvidence,
    SourceRegionPictureCandidate,
)
from app.parsers.base import DocumentParser, ParserCancelledError, ParserError
from app.services.table_service import TableFragment
from app.utils.page_range import format_page_range

_MARKDOWN = MarkdownIt("commonmark")
_MATH = (
    re.compile(r"\\(?:[A-Za-z]+|\(|\[|\)|\])"),
    re.compile(r"[\^_]\s*(?:\{|[A-Za-z0-9])"),
    re.compile(r"<\s*(?:math|sup|sub)\b", re.IGNORECASE),
    re.compile("[\u00b2\u00b3\u00b9\u2070-\u209f]"),
    re.compile(r"(?<!\\)\$[^$\n]+(?<!\\)\$"),
)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "br":
            self.parts.append("\n")


def _visible_inline(value: str) -> str:
    parts: list[str] = []

    def visit(tokens: Any) -> None:
        for token in tokens:
            if token.type in {"text", "code_inline"}:
                parts.append(token.content)
            elif token.type == "html_inline":
                parser = _HTMLText()
                parser.feed(token.content)
                parser.close()
                parts.extend(parser.parts)
            elif token.type in {"softbreak", "hardbreak"}:
                parts.append("\n")
            elif token.type != "image" and token.children:
                visit(token.children)

    visit(_MARKDOWN.parseInline(value))
    return "".join(parts)


def _compact(value: str) -> str:
    folded = (chr(ord(char) - 0xFEE0) if 0xFF01 <= ord(char) <= 0xFF5E else char for char in value)
    return "".join(char for char in folded if not char.isspace())


def _counts(counter: Counter[str]) -> dict[str, int]:
    return {char: counter[char] for char in sorted(counter, key=ord)}


def inspect_character_occurrences(fragment: TableFragment, source_text: str) -> dict[str, Any]:
    """Compare one anchor matrix with its whole source page, never a word list."""
    visible = "\n".join("\t".join(_visible_inline(cell) for cell in row) for row in fragment.rows)
    source = Counter(_compact(source_text))
    model = Counter(_compact(visible))
    unknown = []
    if not source:
        unknown.append("source_page_has_no_extracted_text_layer")
    if any(pattern.search(cell) for row in fragment.rows for cell in row for pattern in _MATH):
        unknown.append("ambiguous_math_or_script_markup")
    excess: list[dict[str, Any]] = [
        {
            "character": char,
            "codepoint": f"U+{ord(char):04X}",
            "model_occurrences": count,
            "source_page_occurrences": source[char],
            "excess": count - source[char],
        }
        for char, count in sorted(model.items(), key=lambda item: ord(item[0]))
        if count > source[char]
    ]
    witnessed = [
        item
        for item in excess
        if item["source_page_occurrences"] > 0
        and unicodedata.category(item["character"])[0] in {"L", "N"}
    ]
    return {
        "table_id": fragment.fragment_id,
        "source_page": fragment.page_number,
        "raw_source_character_counts": _counts(Counter(source_text)),
        "raw_model_visible_character_counts": _counts(Counter(visible)),
        "source_page_character_counts": _counts(source),
        "model_character_counts": _counts(model),
        "all_character_excess": excess,
        "witnessed_LN_excess": witnessed,
        "unknown_reasons": unknown,
        "review_signal": bool(witnessed) and not unknown,
        "within_budget_is_not_correctness_proof": True,
        "source_text_layer_completeness_or_font_fidelity_verified": False,
    }


def _check_cancelled(cancel_event: object | None) -> None:
    if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
        raise ParserCancelledError("job was cancelled")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_bbox(value: object) -> TypeGuard[Sequence[float]]:
    return (
        isinstance(value, (tuple, list))
        and len(value) == 4
        and all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in value)
        and value[0] < value[2]
        and value[1] < value[3]
    )


def _overlap(left: Sequence[float], right: Sequence[float]) -> bool:
    return min(left[2], right[2]) > max(left[0], right[0]) and min(left[3], right[3]) > max(
        left[1], right[1]
    )


def independent_region_types(
    fragment: TableFragment, independent: DocumentParseResult
) -> dict[str, Any]:
    """A broad picture is a disagreement, not a precise figure classification."""
    box = fragment.normalized_bbox
    tables = [
        other.fragment_id
        for other in independent._table_fragments
        if isinstance(other, TableFragment)
        and other.page_number == fragment.page_number
        and _valid_bbox(other.normalized_bbox)
        and _overlap(box, other.normalized_bbox)
    ]
    pictures = []
    for picture in independent._picture_candidates:
        other = getattr(picture, "normalized_bbox", None)
        if (
            getattr(picture, "page_number", None) == fragment.page_number
            and _valid_bbox(other)
            and other[0] <= box[0]
            and other[1] <= box[1]
            and other[2] >= box[2]
            and other[3] >= box[3]
        ):
            pictures.append(list(other))
    return {
        "overlapping_independent_table_ids": tables,
        "enclosing_independent_picture_boxes": pictures,
        "type_disagreement_without_table_candidate": bool(pictures) and not tables,
        "precise_region_classification_or_table_correctness_established": False,
    }


def _page_texts(path: Path, pages: list[int], cancel_event: object | None) -> dict[int, str]:
    import pypdfium2 as pdfium
    from docling.utils.locks import pypdfium2_lock

    with pypdfium2_lock, pdfium.PdfDocument(path) as document:
        result = {}
        for number in pages:
            _check_cancelled(cancel_event)
            page = document[number - 1]
            textpage = page.get_textpage()
            try:
                result[number] = textpage.get_text_range()
            finally:
                textpage.close()
                page.close()
    return result


def _raw_table_html(result: DocumentParseResult, fragment: TableFragment) -> str | None:
    ordinal = 0
    for block in result._native_page_blocks.get(fragment.page_number, []):
        if block.get("type") != "table":
            continue
        children = block.get("content")
        if not isinstance(children, list):
            continue
        for child in children:
            if not isinstance(child, dict) or child.get("type") != "table_body":
                continue
            ordinal += 1
            if ordinal == fragment.ordinal:
                value = child.get("content")
                return value if isinstance(value, str) else None
    return None


def extract_source_region(
    source: StoredSource,
    fragment: TableFragment,
    *,
    source_sha256: str,
    character_observation: dict[str, Any],
    independent_evidence: dict[str, Any],
    raw_model_table_html: str | None = None,
    cancel_event: object | None = None,
) -> SourceRegionEvidence:
    """Read literal glyphs in the same displayed crop frame used by assets."""
    import pypdfium2 as pdfium
    from docling.backend.pypdfium2_backend import _rect_to_display_frame, _rect_to_pdf_frame
    from docling.utils.locks import pypdfium2_lock
    from docling_core.types.doc import Size

    if not _valid_bbox(fragment.normalized_bbox):
        raise ValueError("source region bbox is not an observed normalized display rectangle")
    with pypdfium2_lock, pdfium.PdfDocument(source.path) as document:
        _check_cancelled(cancel_event)
        page = document[fragment.page_number - 1]
        textpage = page.get_textpage()
        try:
            width, height = page.get_size()
            rotation = page.get_rotation()
            if rotation not in {0, 90, 180, 270} or width <= 0 or height <= 0:
                raise ValueError("source display geometry is unsupported")
            size = Size(width=width, height=height)
            origin = page.get_bbox()[:2]
            left, top, right, bottom = fragment.normalized_bbox
            displayed = (left * width, (1 - bottom) * height, right * width, (1 - top) * height)
            native = _rect_to_pdf_frame(displayed, rotation, size, origin)
            roundtrip = _rect_to_display_frame(native, rotation, size, origin)
            if not all(math.isclose(a, b) for a, b in zip(displayed, roundtrip, strict=True)):
                raise ValueError("PDF crop-frame transform could not be verified")
            literal = textpage.get_text_bounded(*native)
            if not literal.strip():
                raise ValueError("source region has no literal PDF text to preserve")
            target = (left * width, top * height, right * width, bottom * height)
            glyphs = []
            for index in range(textpage.count_chars()):
                _check_cancelled(cancel_event)
                box = _rect_to_display_frame(textpage.get_charbox(index), rotation, size, origin)
                displayed_glyph = (box[0], height - box[3], box[2], height - box[1])
                if _overlap(displayed_glyph, target):
                    glyphs.append(
                        SourceGlyph(
                            character_index=index,
                            literal_text=textpage.get_text_range(index=index, count=1),
                            bbox_top_left=displayed_glyph,
                        )
                    )
            if not glyphs:
                raise ValueError("source region text has no locatable PDF glyph evidence")
            return SourceRegionEvidence(
                source_ref=fragment.fragment_id,
                page_number=fragment.page_number,
                normalized_bbox=fragment.normalized_bbox,
                literal_text=literal,
                source_sha256=source_sha256,
                glyphs=tuple(glyphs),
                page_width=width,
                page_height=height,
                rotation_degrees=rotation,
                original_table=copy.deepcopy(asdict(fragment)),
                raw_model_table_html=raw_model_table_html,
                character_observation=character_observation,
                independent_evidence=independent_evidence,
            )
        finally:
            textpage.close()
            page.close()


class SourceVerificationService:
    name = "native-source-verifier"

    def __init__(self, independent_parser: DocumentParser) -> None:
        # The caller owns this already loaded parser. Never initialize, close,
        # reload or allocate another Docling converter here.
        self.independent_parser = independent_parser

    async def apply(
        self,
        result: DocumentParseResult,
        source: StoredSource,
        options: ContentParseOptions,
        *,
        cancel_event: object | None = None,
    ) -> None:
        if source.mime_type != "application/pdf":
            return
        _check_cancelled(cancel_event)
        routed = {page.page_number: page.diagnostics for page in result.pages}
        fragments = []
        for item in result._table_fragments:
            if not isinstance(item, TableFragment) or item.source_kind != "mineru":
                continue
            diagnostics = routed.get(item.page_number)
            if diagnostics is not None and (
                diagnostics.source_kind != PageSourceKind.NATIVE
                or diagnostics.selected_strategy != SelectionStrategy.MINERU
            ):
                continue
            fragments.append(item)
        if not fragments:
            return
        pages = sorted({fragment.page_number for fragment in fragments})
        texts = await asyncio.to_thread(_page_texts, source.path, pages, cancel_event)
        observations = [
            inspect_character_occurrences(fragment, texts[fragment.page_number])
            for fragment in fragments
        ]
        for fragment, observation in zip(fragments, observations, strict=True):
            if not _valid_bbox(fragment.normalized_bbox):
                observation["unknown_reasons"].append("invalid_native_table_bbox")
                observation["review_signal"] = False
        result._source_verification = {
            "observations": observations,
            "independent_pages": [],
            "decisions": [],
            "normalization": "whitespace and ASCII width only; no NFKC or casefold",
            "within_budget_is_not_correctness_proof": True,
        }
        candidates = [
            fragment
            for fragment, observation in zip(fragments, observations, strict=True)
            if observation["review_signal"] and _valid_bbox(fragment.normalized_bbox)
        ]
        if not candidates:
            self._warn_unknown(result, observations, [])
            return
        selected = sorted({fragment.page_number for fragment in candidates})
        started = time.perf_counter()
        independent = await self.independent_parser.parse(
            source,
            options.model_copy(update={"unit_range": format_page_range(selected)}),
            document_id=result.document_id,
            progress_callback=None,
            cancel_event=cancel_event,
        )
        returned = [page.page_number for page in independent.pages]
        if len(returned) != len(selected) or set(returned) != set(selected):
            raise ParserError(
                "source verifier returned an incomplete or duplicate physical page set"
            )
        result._source_verification["independent_pages"] = selected
        observed = {item["table_id"]: item for item in observations}
        decisions = []
        preserved = []
        source_sha = await asyncio.to_thread(_file_sha256, source.path)
        page_by_number = {page.page_number: page for page in result.pages}
        new_contents = {number: page.content or "" for number, page in page_by_number.items()}
        for fragment in candidates:
            _check_cancelled(cancel_event)
            types = independent_region_types(fragment, independent)
            decision = {
                "table_id": fragment.fragment_id,
                "page_number": fragment.page_number,
                "independent_evidence": types,
            }
            if not types["type_disagreement_without_table_candidate"]:
                decision["action"] = "keep_original_structure_unknown_evidence"
                decisions.append(decision)
                continue
            content = new_contents.get(fragment.page_number, "")
            if not fragment.rendered or content.count(fragment.rendered) != 1:
                decision["action"] = "keep_original_ambiguous_fragment_location"
                decisions.append(decision)
                continue
            try:
                region = await asyncio.to_thread(
                    extract_source_region,
                    source,
                    fragment,
                    source_sha256=source_sha,
                    character_observation=observed[fragment.fragment_id],
                    independent_evidence=types,
                    raw_model_table_html=_raw_table_html(result, fragment),
                    cancel_event=cancel_event,
                )
            except (OSError, ValueError, RuntimeError) as exc:
                if isinstance(exc, ParserCancelledError):
                    raise
                decision["action"] = "keep_original_source_geometry_or_glyphs_unknown"
                decision["reason"] = str(exc)
                decisions.append(decision)
                continue
            # This is one exact, typed fragment in page.content before document
            # assembly. Never search repeated prose, cells or final Markdown.
            new_contents[fragment.page_number] = content.replace(
                fragment.rendered, region.rendered, 1
            )
            preserved.append(region)
            decision["action"] = "source_region_preserved_structure_unknown"
            decisions.append(decision)
        _check_cancelled(cancel_event)
        replaced = {region.source_ref for region in preserved}
        for page in result.pages:
            if any(region.page_number == page.page_number for region in preserved):
                page.content = new_contents[page.page_number]
                page.plain_text = None
        result._table_fragments = [
            fragment
            for fragment in result._table_fragments
            if not isinstance(fragment, TableFragment) or fragment.fragment_id not in replaced
        ]
        result._source_regions.extend(preserved)
        result._picture_candidates.extend(
            SourceRegionPictureCandidate(
                region.page_number, region.normalized_bbox, region.source_ref
            )
            for region in preserved
        )
        result._source_verification["decisions"] = decisions
        self._warn_unknown(result, observations, decisions)
        result.warnings.append(
            PipelineWarning(
                code="independent_source_verification_used",
                message="source character conflicts received independent region-type verification",
                severity=WarningSeverity.INFO,
                backend=self.name,
                details={
                    "pages": selected,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "review_candidates": len(candidates),
                    "preserved_regions": len(preserved),
                },
            )
        )
        for region in preserved:
            warning = PipelineWarning(
                code="source_region_preserved_unknown",
                message="the source image and literal PDF text are preserved; region structure remains unknown",
                page_number=region.page_number,
                backend=self.name,
                details={
                    "source_ref": region.source_ref,
                    "reason_codes": list(region.reason_codes),
                },
            )
            result.warnings.append(warning)
            page_by_number[region.page_number].warnings.append(warning)

    @staticmethod
    def _warn_unknown(
        result: DocumentParseResult,
        observations: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> None:
        unknown = [item for item in observations if item["unknown_reasons"]]
        unresolved = [item for item in decisions if item["action"].startswith("keep_original")]
        if not unknown and not unresolved:
            return
        result.warnings.append(
            PipelineWarning(
                code="source_verification_unknown",
                message="some native table evidence remains unknown; original source observations are retained",
                severity=WarningSeverity.WARNING if unresolved else WarningSeverity.INFO,
                backend=SourceVerificationService.name,
                details={
                    "unknown_tables": len(unknown),
                    "unresolved_review_candidates": len(unresolved),
                },
            )
        )
        for page in result.pages:
            count = sum(item["page_number"] == page.page_number for item in unresolved)
            if count:
                page.warnings.append(
                    PipelineWarning(
                        code="source_verification_unknown",
                        message="a source character conflict has unresolved region evidence; the original candidate is retained",
                        page_number=page.page_number,
                        backend=SourceVerificationService.name,
                        details={"unresolved_review_candidates": count},
                    )
                )
