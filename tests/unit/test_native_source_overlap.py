"""Native deposition overlap guards using only authored dicts and PDFs."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import (
    DocumentParseResult,
    PageParseResult,
    PageSourceKind,
    ParsePipeline,
)
from app.models.source import StoredSource
from app.services.evidence_service import NativeBlock, PageEvidence, PageEvidenceService
from app.services.native_text_service import NativeTextService


def span(text: str, box=(20, 40, 180, 54), origin=(20, 50)) -> dict:
    return {"text": text, "bbox": box, "origin": origin,
            "font": "Helvetica", "size": 10, "flags": 0}


def line(spans: list[dict], box=(20, 40, 180, 54)) -> dict:
    return {"spans": spans, "bbox": box, "dir": (1, 0)}


def candidate(text: str, box, *, blocks: list[dict] | None = None) -> DocumentParseResult:
    result = DocumentParseResult(
        document_id="authored", filename="authored.pdf", mime_type="application/pdf",
        page_count=1, processed_pages=1, pages=[PageParseResult(page_number=1, content=text)],
        pipeline=ParsePipeline(profile="balanced", primary="authored"),
    )
    result._native_page_blocks[1] = blocks if blocks is not None else [
        {"type": "text", "bbox": list(box), "markdown": text},
    ]
    return result


def test_same_position_spans_inside_one_line_are_flagged_without_rewriting_text():
    raw = {"lines": [line([
        span("Authored 2023 heading"),
        span("Authored 2023 heading", box=(20.1, 40, 180.1, 54), origin=(20.1, 50)),
    ])]}
    before = PageEvidenceService._block_text(raw)[0]
    assert PageEvidenceService._block_overlap_risk(raw)
    assert PageEvidenceService._block_text(raw)[0] == before
    assert before == "Authored 2023 headingAuthored 2023 heading"


def test_same_position_lines_with_different_span_partitioning_are_flagged():
    raw = {"lines": [
        line([span("Authored heading")]),
        line([span("Authored", box=(20.1, 40, 80.1, 54), origin=(20.1, 50)),
              span(" heading", box=(80.1, 40, 180.1, 54), origin=(80.1, 50))],
             box=(20.1, 40, 180.1, 54)),
    ]}
    assert PageEvidenceService._block_overlap_risk(raw)


def test_repeated_wording_in_a_single_span_without_duplicate_geometry_is_not_flagged():
    raw = {"lines": [line([span("The same words, the same words, are deliberately repeated.")])]}
    assert not PageEvidenceService._block_overlap_risk(raw)


def test_repeated_adjacent_and_cross_line_text_is_not_a_same_position_deposition():
    raw = {"lines": [
        line([span("Authored wording", box=(20, 40, 180, 54), origin=(20, 50)),
              span("Authored wording", box=(200, 40, 360, 54), origin=(200, 50))],
             box=(20, 40, 360, 54)),
        line([span("Authored wording", box=(20, 65, 180, 79), origin=(20, 75))],
             box=(20, 65, 180, 79)),
    ]}
    assert not PageEvidenceService._block_overlap_risk(raw)


def test_typographic_neighbor_overlap_without_coincident_origins_is_not_flagged():
    raw = {"lines": [line([
        span("Authored", box=(20, 40, 90, 54), origin=(20, 50)),
        span(" heading", box=(89, 40, 160, 54), origin=(89, 50)),
    ], box=(20, 40, 160, 54))]}
    assert not PageEvidenceService._block_overlap_risk(raw)


def test_distinct_nonempty_text_depositions_at_identical_geometry_are_risky():
    raw = {"lines": [line([span("Visible text"), span("Other source layer")])]}
    assert PageEvidenceService._block_overlap_risk(raw)


@pytest.mark.parametrize("offset", [0.0, 0.1, 0.3])
def test_authored_pdf_faux_bold_inside_one_native_block_retains_raw_bytes_but_blocks_region_replacement(
    tmp_path: Path, offset: float,
):
    heading = "Authored 2023 bold heading."
    body = "The authored single-print paragraph has revenue 120.50 and an unchanged reporting scope."
    path = tmp_path / "authored-overprint.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=400)
        page.insert_text((20, 60), heading, fontsize=10)
        page.insert_text((20 + offset, 60), heading, fontsize=10)
        page.insert_text((20, 110), body, fontsize=8)
        document.save(path)
    source = StoredSource(path=path, filename=path.name, mime_type="application/pdf",
                          size_bytes=path.stat().st_size, page_count=1)
    with pymupdf.open(path) as raw_document:
        untouched_native_text = raw_document[0].get_text("text", sort=True)
    evidence = PageEvidenceService().inspect(source, {1})[1]
    risky = [block for block in evidence.native_blocks if block.source_overlap_risk]
    assert len(risky) == 1 and risky[0].text.count(heading) == 2
    assert evidence.native_text == untouched_native_text
    assert evidence.native_body_text.count(heading) == 2
    normal = next(block for block in evidence.native_blocks if body in block.text)
    assert not normal.source_overlap_risk
    full = (20 / 600, risky[0].bbox[1] / 400,
            max(risky[0].bbox[2], normal.bbox[2]) / 600, normal.bbox[3] / 400)
    parsed = heading + " " + body
    result = candidate(parsed, full)
    receipt = NativeTextService().apply(result, {1: evidence}, ContentParseOptions())
    assert result.pages[0].content == parsed and receipt["replaced_regions"] == 0
    assert "native_source_span_overlap" in {
        source["reason"] for item in receipt["pages"][0]["unresolved"]
        for source in item.get("sources", [])
    }

    # A separate complete body region can still use an unambiguous native block.
    normal_box = tuple(value / (600 if index % 2 == 0 else 400)
                       for index, value in enumerate(normal.bbox))
    result = candidate(body.replace("120.50", "120.5O"), normal_box)
    receipt = NativeTextService().apply(result, {1: evidence}, ContentParseOptions())
    assert result.pages[0].content == body and receipt["replaced_regions"] == 1


def test_authored_pdf_legitimate_repetition_at_other_positions_is_retained_without_risk(tmp_path: Path):
    text = "The authored repeated phrase remains legitimate source content."
    path = tmp_path / "authored-normal-repetition.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=1000, height=400)
        page.insert_text((20, 80), text, fontsize=8)
        page.insert_text((450, 80), text, fontsize=8)
        page.insert_text((20, 120), text, fontsize=8)
        document.save(path)
    source = StoredSource(path=path, filename=path.name, mime_type="application/pdf",
                          size_bytes=path.stat().st_size, page_count=1)
    evidence = PageEvidenceService().inspect(source, {1})[1]
    assert evidence.native_text.count(text) == 3
    assert not any(block.source_overlap_risk for block in evidence.native_blocks)


def test_risky_native_only_paragraph_is_not_inserted_between_valid_anchors():
    first = "The first authored native paragraph provides an independent source anchor."
    last = "The last authored native paragraph provides another independent source anchor."
    risky = "The missing source contains this same-position duplicated text."
    a, b, c = (0.1, 0.1, 0.9, 0.2), (0.1, 0.3, 0.9, 0.4), (0.1, 0.5, 0.9, 0.6)
    content = first + "\n\n" + last
    result = candidate(content, a, blocks=[
        {"type": "text", "bbox": list(a), "markdown": first},
        {"type": "text", "bbox": list(c), "markdown": last},
    ])
    evidence = PageEvidence(page_number=1, source_kind=PageSourceKind.NATIVE,
        page_width=100, page_height=100, native_blocks=[
            NativeBlock(first, (10, 10, 90, 20), 10, False),
            NativeBlock(risky, tuple(value * 100 for value in b), 10, False, source_overlap_risk=True),
            NativeBlock(last, (10, 50, 90, 60), 10, False),
        ])
    receipt = NativeTextService().apply(result, {1: evidence}, ContentParseOptions())
    assert result.pages[0].content == content and receipt["inserted_regions"] == 0
