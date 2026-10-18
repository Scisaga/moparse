"""Real PDF glyph geometry with mocked independent inference; no model calls."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pymupdf
import pytest

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import (
    DocumentParseResult,
    PageDiagnostics,
    PageParseResult,
    PageSourceKind,
    PageStatus,
    ParsePipeline,
    QualityVerdict,
    SelectionStrategy,
    WarningSeverity,
)
from app.models.source import StoredSource
from app.models.source_evidence import SourceRegionEvidence
from app.parsers.base import ParserCancelledError, ParserError
from app.services.export_service import ExportService
from app.services.quality_service import QualityService
from app.services.source_verification_service import (
    SourceVerificationService,
    extract_source_region,
    inspect_character_occurrences,
)
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows


def pdf_source(tmp_path, *, text="ALPHA -0.61 | ``` <literal>", pages=1, rotation=0, crop=False):
    path = tmp_path / "source.pdf"
    with pymupdf.open() as pdf:
        for _ in range(pages):
            page = pdf.new_page(width=600, height=800)
            if text:
                page.insert_text((80, 300), text, fontsize=12)
            if crop:
                page.set_cropbox(pymupdf.Rect(40, 100, 550, 700))
            page.set_rotation(rotation)
        pdf.save(path)
    return StoredSource(
        path=path,
        filename=path.name,
        mime_type="application/pdf",
        size_bytes=path.stat().st_size,
        page_count=pages,
    )


def fragment(ordinal=1, *, text="A", page=1, columns=1, source_kind="mineru"):
    rows = [[text] * columns]
    cells = [TableCellFragment(0, column, 1, 1, text) for column in range(columns)]
    fid = f"mineru_p{page}_t{ordinal}"
    markdown = render_gfm_rows(rows)
    return TableFragment(
        fragment_id=fid,
        page_number=page,
        ordinal=ordinal,
        normalized_bbox=(0.05, 0.1, 0.95, 0.9),
        num_rows=1,
        num_cols=columns,
        rows=rows,
        cells=cells,
        column_boundaries=[],
        markdown=markdown,
        rendered=f"<!-- table-fragment: {fid} -->\n\n{markdown}",
        source_kind=source_kind,
        header_scope_complete=False,
        caption_scope_complete=False,
    )


def document(fragments=(), *, pages=(1,)):
    result = DocumentParseResult(
        document_id="doc_source_test",
        filename="source.pdf",
        mime_type="application/pdf",
        page_count=max(pages),
        processed_pages=len(pages),
        pipeline=ParsePipeline(profile="balanced", primary="test"),
        pages=[
            PageParseResult(
                page_number=page,
                content="Before\n\n"
                + "\n\n".join(f.rendered for f in fragments if f.page_number == page)
                + "\n\nAfter",
            )
            for page in pages
        ],
    )
    result._table_fragments = list(fragments)
    return result


def independent(*, pages=(1,), pictures=True, tables=()):
    result = document(tables, pages=pages)
    result._picture_candidates = (
        [SimpleNamespace(page_number=page, normalized_bbox=(0, 0, 1, 1)) for page in pages]
        if pictures
        else []
    )
    return result


def parser_for(result):
    return SimpleNamespace(
        parse=AsyncMock(return_value=result), initialize=AsyncMock(), close=AsyncMock()
    )


@pytest.mark.parametrize(
    "value,source,review",
    [
        ("555", "5", True),
        ("555", "A", False),
        ("□□---", "□-", False),
        ("1.234", "1,234", False),
        ("AA", "a", False),
        ("ＡＡ", "A", True),
        ("−1", "-1", False),
        ("$A$" * 10, "A", False),
        (r"\Delta" * 10, "Delta", False),
        ("A^1" * 10, "A1", False),
        ("A²" * 10, "A2", False),
        ("", "", False),
    ],
)
def test_character_evidence_is_conservative(value, source, review):
    observation = inspect_character_occurrences(fragment(text=value), source)
    assert observation["review_signal"] is review
    assert observation["within_budget_is_not_correctness_proof"] is True
    assert "raw_source_character_counts" in observation
    assert "raw_model_visible_character_counts" in observation


def test_wide_table_and_signs_are_not_shape_or_normalization_rules():
    observation = inspect_character_occurrences(fragment(text="A", columns=202), "A" * 202)
    assert not observation["review_signal"]
    assert observation["model_character_counts"] == {"A": 202}
    minus = inspect_character_occurrences(fragment(text="-"), "-")
    assert minus["model_character_counts"] == {"-": 1}
    assert inspect_character_occurrences(fragment(text="²①Ⅲ"), "²①Ⅲ")["model_character_counts"] == {
        "²": 1,
        "Ⅲ": 1,
        "①": 1,
    }


async def test_only_exact_conflicted_fragment_changes_and_raw_is_json_serializable(tmp_path):
    source = pdf_source(tmp_path)
    fragments = [fragment(1), fragment(2, text="A" * 200), fragment(3)]
    result = document(fragments)
    result.markdown = "Existing final string must not be edited"
    original = [copy.deepcopy(asdict(f)) for f in fragments]
    result._native_page_blocks = {
        1: [
            {
                "type": "table",
                "content": [
                    {
                        "type": "table_body",
                        "content": f"<table><tr><td>{f.rows[0][0]}</td></tr></table>",
                    }
                ],
            }
            for f in fragments
        ]
    }
    parser = parser_for(independent())
    await SourceVerificationService(parser).apply(result, source, ContentParseOptions())
    assert result.markdown == "Existing final string must not be edited"
    assert [f.fragment_id for f in result._table_fragments] == [
        fragments[0].fragment_id,
        fragments[2].fragment_id,
    ]
    assert [asdict(f) for f in result._table_fragments] == [original[0], original[2]]
    region = result._source_regions[0]
    assert isinstance(region, SourceRegionEvidence)
    assert "ALPHA -0.61 | ``` <literal>" in region.literal_text
    assert "````text\n" in region.rendered
    assert region.raw_model_table_html == result._native_page_blocks[1][1]["content"][0]["content"]
    assert region.original_table == original[1]
    assert region.source_sha256 == hashlib.sha256(source.path.read_bytes()).hexdigest()
    json.dumps(asdict(region))
    assert all(glyph.character_index >= 0 for glyph in region.glyphs)
    candidate = result._picture_candidates[-1]
    assert candidate.source_region_ref == fragments[1].fragment_id
    assert candidate.allow_description is False
    assert parser.parse.call_args.kwargs["document_id"] == result.document_id
    assert parser.parse.call_args.args[1].unit_range == "1"
    parser.initialize.assert_not_called()
    parser.close.assert_not_called()
    md, _ = ExportService().join_document(
        result.pages,
        preserve_page_breaks=True,
        table_fragments=result._table_fragments,
        page_furniture=result._page_furniture,
    )
    assert f"table-source: {fragments[0].fragment_id}" in md
    assert f"table-source: {fragments[2].fragment_id}" in md
    assert f"table-source: {fragments[1].fragment_id}" not in md
    assert region.image_placeholder in md
    assert "Before" in md and "After" in md


@pytest.mark.parametrize("pictures,table_overlap", [(False, False), (True, True)])
async def test_no_type_evidence_or_overlapping_table_keeps_original(
    tmp_path, pictures, table_overlap
):
    source = pdf_source(tmp_path)
    f = fragment(text="A" * 200)
    result = document([f])
    before = copy.deepcopy(asdict(f))
    p = parser_for(
        independent(
            pictures=pictures, tables=[fragment(source_kind="docling")] if table_overlap else []
        )
    )
    await SourceVerificationService(p).apply(result, source, ContentParseOptions())
    assert asdict(result._table_fragments[0]) == before
    assert not result._source_regions
    assert result._source_verification["decisions"][0]["action"].startswith("keep_original")


@pytest.mark.parametrize(
    "text,model,kind",
    [
        ("", "AAAA", "mineru"),
        ("A", "A^1" * 200, "mineru"),
        ("A", "A" * 200, "glm"),
    ],
)
async def test_unknown_evidence_and_non_native_tables_never_request_independent_inference(
    tmp_path, text, model, kind
):
    source = pdf_source(tmp_path, text=text)
    f = fragment(text=model, source_kind=kind)
    result = document([f])
    p = parser_for(independent())
    await SourceVerificationService(p).apply(result, source, ContentParseOptions())
    p.parse.assert_not_called()
    assert result._table_fragments == [f]
    assert not result._source_regions


async def test_duplicate_exact_fragment_location_is_not_guessed(tmp_path):
    source = pdf_source(tmp_path)
    f = fragment(text="A" * 200)
    result = document([f])
    result.pages[0].content = f.rendered + "\n\n" + f.rendered
    before = result.pages[0].content
    await SourceVerificationService(parser_for(independent())).apply(
        result, source, ContentParseOptions()
    )
    assert result.pages[0].content == before
    assert result._table_fragments == [f]
    assert not result._source_regions


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("crop", [False, True])
def test_literal_glyphs_use_rotated_display_and_crop_frame(tmp_path, rotation, crop):
    source = pdf_source(tmp_path, rotation=rotation, crop=crop)
    f = fragment(text="AA")
    with pymupdf.open(source.path) as pdf:
        page = pdf[0]
        words = page.get_text("words")
        bounds = pymupdf.Rect(words[0][:4])
        for word in words[1:]:
            bounds |= pymupdf.Rect(word[:4])
        bounds = bounds * page.rotation_matrix
        bounds = pymupdf.Rect(bounds.x0 - 5, bounds.y0 - 5, bounds.x1 + 5, bounds.y1 + 5)
        f.normalized_bbox = (
            bounds.x0 / page.rect.width,
            bounds.y0 / page.rect.height,
            bounds.x1 / page.rect.width,
            bounds.y1 / page.rect.height,
        )
    region = extract_source_region(
        source,
        f,
        source_sha256="known-input-hash",
        character_observation={},
        independent_evidence={},
    )
    assert "ALPHA -0.61 | ``` <literal>" in region.literal_text
    assert region.rotation_degrees == rotation
    assert region.glyphs
    left, top, right, bottom = f.normalized_bbox
    assert all(
        left <= ((g.bbox_top_left[0] + g.bbox_top_left[2]) / 2) / region.page_width <= right
        and top <= ((g.bbox_top_left[1] + g.bbox_top_left[3]) / 2) / region.page_height <= bottom
        for g in region.glyphs
        if g.literal_text.strip()
    )


async def test_multiple_physical_pages_get_separate_regions(tmp_path):
    source = pdf_source(tmp_path, pages=2)
    fragments = [fragment(1, text="A" * 200, page=page) for page in [1, 2]]
    result = document(fragments, pages=(1, 2))
    p = parser_for(independent(pages=(1, 2)))
    await SourceVerificationService(p).apply(result, source, ContentParseOptions())
    assert [r.page_number for r in result._source_regions] == [1, 2]
    assert len({r.image_placeholder for r in result._source_regions}) == 2
    assert p.parse.call_args.args[1].unit_range == "1-2"


async def test_incomplete_independent_pages_raise_before_any_mutation(tmp_path):
    source = pdf_source(tmp_path)
    f = fragment(text="A" * 200)
    result = document([f])
    p = parser_for(document(pages=(2,)))
    with pytest.raises(ParserError, match="physical page set"):
        await SourceVerificationService(p).apply(result, source, ContentParseOptions())
    assert result._table_fragments == [f]
    assert not result._source_regions


async def test_cancellation_does_not_mutate_or_start_independent_work(tmp_path):
    source = pdf_source(tmp_path)
    event = Event()
    event.set()
    result = document([fragment(text="A" * 200)])
    p = parser_for(independent())
    with pytest.raises(ParserCancelledError):
        await SourceVerificationService(p).apply(
            result, source, ContentParseOptions(), cancel_event=event
        )
    p.parse.assert_not_called()
    assert not result._source_regions


def test_private_source_records_do_not_change_public_result_schema():
    result = document()
    assert not any(name.startswith("_") for name in result.model_dump())
    assert "_source_regions" not in DocumentParseResult.model_json_schema()["properties"]


@pytest.mark.parametrize(
    "kind,strategy",
    [
        (PageSourceKind.SCANNED, SelectionStrategy.MINERU),
        (PageSourceKind.MIXED, SelectionStrategy.MINERU),
        (PageSourceKind.NATIVE, SelectionStrategy.GLM_TABLE),
    ],
)
async def test_page_routing_must_agree_with_native_table_kind(tmp_path, kind, strategy):
    source = pdf_source(tmp_path)
    f = fragment(text="A" * 200)
    result = document([f])
    result.pages[0].diagnostics = PageDiagnostics(source_kind=kind, selected_strategy=strategy)
    p = parser_for(independent())
    await SourceVerificationService(p).apply(result, source, ContentParseOptions())
    p.parse.assert_not_called()
    assert result._table_fragments == [f]
    assert result._source_verification == {}


async def test_unknown_math_warns_info_without_rejecting_table(tmp_path):
    source = pdf_source(tmp_path)
    f = fragment(text="A^1" * 200)
    result = document([f])
    await SourceVerificationService(parser_for(independent())).apply(
        result, source, ContentParseOptions()
    )
    warning = next(w for w in result.warnings if w.code == "source_verification_unknown")
    assert warning.severity == WarningSeverity.INFO
    assert warning.details["unknown_tables"] == 1
    assert result._table_fragments == [f]


@pytest.mark.parametrize("pictures", [False, True])
async def test_real_conflict_warning_prevents_trusted_page(tmp_path, pictures):
    source = pdf_source(tmp_path)
    result = document([fragment(text="A" * 200)])
    result.pages[0].diagnostics = PageDiagnostics(
        source_kind=PageSourceKind.NATIVE, selected_strategy=SelectionStrategy.MINERU
    )
    await SourceVerificationService(parser_for(independent(pictures=pictures))).apply(
        result, source, ContentParseOptions()
    )
    assert any(w.severity == WarningSeverity.WARNING for w in result.pages[0].warnings)
    QualityService().assess(result)
    assert result.pages[0].status == PageStatus.WARNING
    assert result.pages[0].diagnostics.quality_verdict == QualityVerdict.UNTRUSTED


async def test_invalid_bbox_remains_unknown_and_warns(tmp_path):
    source = pdf_source(tmp_path)
    f = fragment(text="A" * 200)
    f.normalized_bbox = (0.8, 0.2, 0.1, 0.3)
    result = document([f])
    p = parser_for(independent())
    await SourceVerificationService(p).apply(result, source, ContentParseOptions())
    p.parse.assert_not_called()
    assert result._table_fragments == [f]
    assert result.warnings[0].code == "source_verification_unknown"
    assert (
        "invalid_native_table_bbox"
        in result._source_verification["observations"][0]["unknown_reasons"]
    )
