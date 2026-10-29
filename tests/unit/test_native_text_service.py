"""Region-owned prose selection with authored structures, no PDF or reference."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import (
    DocumentParseResult,
    PageDiagnostics,
    PageParseResult,
    PageSourceKind,
    ParsePipeline,
    SelectionStrategy,
)
from app.models.source_evidence import SourceRegionEvidence
from app.parsers.base import ParserCancelledError
from app.services.evidence_service import NativeBlock, PageEvidence
from app.services.export_service import ExportService
from app.services.native_text_service import NativeTextService

BOX = (0.1, 0.1, 0.9, 0.2)
OPTIONS = ContentParseOptions()


def native(text: str, box=BOX, *, bold=False) -> NativeBlock:
    return NativeBlock(text, tuple(v * 100 for v in box), 12, bold)


def region(text: str, box=BOX, role="text") -> dict:
    return {"type": role, "bbox": list(box), "markdown": text}


def document(markdown: str, blocks: list[dict], originals: list[NativeBlock],
             *, source_kind=PageSourceKind.NATIVE) -> tuple[DocumentParseResult, PageEvidence]:
    result = DocumentParseResult(
        document_id="authored", filename="authored.pdf", mime_type="application/pdf",
        page_count=1, processed_pages=1, pipeline=ParsePipeline(profile="balanced", primary="authored"),
        pages=[PageParseResult(page_number=1, content=markdown,
                               diagnostics=PageDiagnostics(source_kind=source_kind))],
    )
    result._native_page_blocks[1] = blocks
    evidence = PageEvidence(page_number=1, source_kind=source_kind,
                            native_blocks=originals, page_width=100, page_height=100)
    return result, evidence


def apply(result: DocumentParseResult, evidence: PageEvidence) -> dict:
    return NativeTextService().apply(result, {1: evidence}, OPTIONS)


def test_exact_owned_plain_region_uses_source_glyphs_and_preserves_parser_evidence():
    source = "本期营业收入为120.50万元，公司经营状况保持稳定。"
    parsed = "本期营业收入为120.5O万元，公司经营状况保持稳定。"
    result, evidence = document(parsed, [region(parsed)], [native(source)])
    result._source_verification["preexisting"] = {"saved": True}
    report = apply(result, evidence)

    assert result.pages[0].content == source
    assert result.pages[0].plain_text is None
    assert result.pages[0].diagnostics.selected_strategy == SelectionStrategy.NATIVE_REPAIR
    assert report["replaced_regions"] == 1 and report["inserted_regions"] == 0
    assert report["pages"][0]["actions"][0]["parser_markdown"] == parsed
    assert result._source_verification["preexisting"] == {"saved": True}
    assert result._native_page_blocks[1][0]["markdown"] == parsed


@pytest.mark.parametrize("prefix", ["## ", "- ", "1. ", "> "])
def test_existing_heading_list_and_quote_role_survive(prefix):
    source = "本期营业收入为120.50万元，相关情况保持稳定。"
    parsed = prefix + source.replace("120.50", "120.5O")
    result, evidence = document(parsed, [region(parsed)], [native(source, bold=True)])
    apply(result, evidence)
    assert result.pages[0].content == prefix + source


def test_source_font_does_not_create_a_new_heading():
    source = "Current revenue was 120.50 and the operating scope was unchanged."
    parsed = source.replace("120.50", "120.5O")
    result, evidence = document(parsed, [region(parsed)], [native(source, bold=True)])
    apply(result, evidence)
    assert result.pages[0].content == source
    assert not result.pages[0].content.startswith("#")


def test_existing_rich_inline_structure_is_not_flattened():
    parsed = "营业收入为**120.5O万元**，经营情况保持稳定。"
    source = "营业收入为120.50万元，经营情况保持稳定。"
    result, evidence = document(parsed, [region(parsed)], [native(source)])
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert report["replaced_regions"] == 0
    assert report["pages"][0]["unresolved"][0]["reason"] == "rich_parser_structure_preserved"


def test_same_native_region_cannot_satisfy_two_overlapping_parser_owners():
    first = "The first authored paragraph with a candidate error."
    second = "The second authored paragraph with a different value."
    markdown = first + "\n\n" + second
    result, evidence = document(markdown, [region(first), region(second)], [native(first)])
    report = apply(result, evidence)
    assert result.pages[0].content == markdown
    assert report["replaced_regions"] == report["inserted_regions"] == 0
    assert {r["reason"] for r in report["pages"][0]["unresolved"]} == {"ambiguous_native_region_owner"}


def test_duplicate_markdown_span_is_not_globally_replaced():
    parsed = "Operating revenue is 120.5O under the unchanged scope."
    source = parsed.replace("5O", "50")
    markdown = parsed + "\n\n" + parsed
    result, evidence = document(markdown, [region(parsed)], [native(source)])
    report = apply(result, evidence)
    assert result.pages[0].content == markdown
    assert report["replaced_regions"] == report["inserted_regions"] == 0


@pytest.mark.parametrize("kind", [PageSourceKind.SCANNED, PageSourceKind.MIXED])
def test_scan_or_mixed_text_layer_is_not_used_as_native_prose_authority(kind):
    parsed = "The original candidate paragraph is retained on this scanned page."
    result, evidence = document(parsed, [region(parsed)],
                                [native(parsed.replace("original", "different"))], source_kind=kind)
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert report["pages"] == []


@pytest.mark.parametrize("broken", ["\ufffd", "\ue012", "\x01"])
def test_broken_or_private_native_encoding_never_replaces_candidate(broken):
    parsed = "The native code was readable in the original candidate paragraph."
    result, evidence = document(parsed, [region(parsed)], [native(parsed.replace("readable", broken))])
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert report["replaced_regions"] == 0


def test_large_native_content_conflict_preserves_candidate_and_records_both():
    parsed = "The model returned a completely distinct authored explanation."
    source = "合同签订之后应当按照约定的范围履行各项义务，不作其他变更。"
    result, evidence = document(parsed, [region(parsed)], [native(source)])
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    conflict = report["pages"][0]["unresolved"][0]
    assert conflict["reason"] == "native_parser_content_conflict"
    assert conflict["native_text"] == source and conflict["parser_markdown"] == parsed


@pytest.mark.parametrize("field", ["_table_fragments", "_picture_candidates", "_source_regions", "_page_furniture"])
def test_known_non_prose_regions_are_excluded_without_affecting_neighbor(field):
    good_box = (0.1, 0.5, 0.9, 0.6)
    bad = "A retained table or image region with business value 120.5O."
    good = "The neighboring native paragraph has operating value 45.50."
    parsed = good.replace("45.50", "45.5O")
    markdown = bad + "\n\n" + parsed
    result, evidence = document(markdown, [region(bad), region(parsed, good_box)],
                                [native(bad.replace("5O", "50")), native(good, good_box)])
    setattr(result, field, [SimpleNamespace(page_number=1, normalized_bbox=BOX)])
    report = apply(result, evidence)
    assert result.pages[0].content == bad + "\n\n" + good
    assert report["replaced_regions"] == 1


def test_grid_region_excludes_unclassified_grid_prose_from_body_replacement():
    parsed = "The boxed explanation remains a grid with source value 120.5O."
    result, evidence = document(parsed, [region(parsed)], [native(parsed.replace("5O", "50"))])
    evidence.grid_regions = [BOX]
    apply(result, evidence)
    assert result.pages[0].content == parsed


def test_missing_paragraph_is_inserted_between_independent_same_column_anchors():
    before = "## Existing business heading"
    after = "The final authored paragraph preserves the signed reporting scope."
    missing = "这是原生PDF中实际存在、解析正文遗漏的独立业务段落。"
    first_box, mid_box, last_box = (0.1, 0.1, 0.9, 0.2), (0.1, 0.3, 0.9, 0.4), (0.1, 0.5, 0.9, 0.6)
    result, evidence = document(before + "\n\n" + after,
        [region(before, first_box, "title"), region(after, last_box)],
        [native("Existing business heading", first_box), native(missing, mid_box), native(after, last_box)])
    report = apply(result, evidence)
    content = result.pages[0].content
    assert content.startswith(before)
    assert content.index(before) < content.index(missing) < content.index(after)
    assert content.count(missing) == 1 and report["inserted_regions"] == 1
    assert report["pages"][0]["actions"][0]["action"] == "inserted_native_prose"


def test_missing_prose_uses_the_non_crossing_side_of_a_protected_table():
    before = "The initial paragraph precedes the retained business table."
    after = "The concluding paragraph follows the missing source footnote."
    missing = "The actual source footnote is independent prose after the table."
    first_box, mid_box, last_box = (0.1, 0.1, 0.9, 0.2), (0.1, 0.65, 0.9, 0.72), (0.1, 0.8, 0.9, 0.9)
    table_box = (0.1, 0.3, 0.9, 0.6)
    table = "| Field | Value |\n| --- | --- |\n| Row | 10 |"
    markdown = before + "\n\n" + table + "\n\n" + after
    result, evidence = document(markdown,
        [region(before, first_box), region(table, table_box, "table"), region(after, last_box)],
        [native(before, first_box), native(missing, mid_box), native(after, last_box)])
    result._table_fragments = [SimpleNamespace(page_number=1, normalized_bbox=table_box)]
    report = apply(result, evidence)
    content = result.pages[0].content
    assert content.index(table) < content.index(missing) < content.index(after)
    assert content.count(table) == 1 and report["inserted_regions"] == 1


def test_prose_in_an_unknown_region_is_never_inserted_or_reformatted():
    first = "A leading authored paragraph is already fully recognized."
    last = "A trailing authored paragraph is already fully recognized."
    hidden = "The unknown grid contains this deliberately long narrative."
    first_box, mid_box, last_box = (0.1, 0.1, 0.9, 0.2), (0.1, 0.3, 0.9, 0.4), (0.1, 0.5, 0.9, 0.6)
    markdown = first + "\n\n<!-- source-region-image: unknown -->\n\n" + last
    result, evidence = document(markdown, [region(first, first_box), region(last, last_box)],
                                [native(first, first_box), native(hidden, mid_box), native(last, last_box)])
    result._source_regions = [SimpleNamespace(page_number=1, normalized_bbox=mid_box)]
    apply(result, evidence)
    assert result.pages[0].content == markdown


def test_missing_prose_in_other_column_is_not_appended_to_wrong_column():
    parsed = "The only recognized paragraph belongs to the left source column."
    source = "The omitted paragraph belongs to the separate right source column."
    left, right = (0.05, 0.1, 0.45, 0.2), (0.55, 0.3, 0.95, 0.4)
    result, evidence = document(parsed, [region(parsed, left)], [native(parsed, left), native(source, right)])
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert report["inserted_regions"] == 0


def test_page_wide_caption_cannot_be_inserted_between_narrow_column_paragraphs():
    first = 'The first narrow-column paragraph ends with a clause,'
    last = 'whose continuation belongs in the same column.'
    caption = 'Annual production totals with the original reporting unit'
    left, right, wide = (.1, .1, .35, .2), (.1, .4, .35, .5), (.1, .3, .95, .32)
    markdown = first + '\n\n' + last
    result, evidence = document(markdown, [region(first, left), region(last, right)],
                                [native(first, left), native(caption, wide), native(last, right)])
    report = apply(result, evidence)
    assert result.pages[0].content == markdown
    assert report['inserted_regions'] == 0
    assert 'missing_prose_order_not_uniquely_anchored' in {
        item['reason'] for item in report['pages'][0]['unresolved']}


def test_native_geometry_does_not_reorder_parser_anchors_to_fit_source():
    top, bottom = "The first source paragraph has complete content.", "The last source paragraph has complete content."
    missing = "The unrecognized source paragraph lies physically between them."
    a, b, c = (0.1, 0.1, 0.9, 0.2), (0.1, 0.3, 0.9, 0.4), (0.1, 0.5, 0.9, 0.6)
    markdown = bottom + "\n\n" + top
    result, evidence = document(markdown, [region(bottom, c), region(top, a)],
                                [native(top, a), native(missing, b), native(bottom, c)])
    report = apply(result, evidence)
    assert result.pages[0].content == markdown and report["inserted_regions"] == 0


def test_apparent_markdown_in_inserted_source_is_literal_and_does_not_create_role():
    anchor = "The existing parser paragraph has a complete source anchor."
    missing = "# The literal source text starts with a hash and [brackets]."
    first, second = (0.1, 0.1, 0.9, 0.2), (0.1, 0.3, 0.9, 0.4)
    result, evidence = document(anchor, [region(anchor, first)], [native(anchor, first), native(missing, second)])
    apply(result, evidence)
    content = result.pages[0].content
    assert "&#35; The literal" in content and "&#91;brackets&#93;" in content
    assert missing in ExportService.markdown_to_text(content)


def test_source_line_wrapping_does_not_duplicate_already_recognized_paragraph():
    parsed = "The complete native paragraph was recognized without a physical line break."
    source = "The complete native paragraph was recognized\nwithout a physical line break."
    result, evidence = document(parsed, [region(parsed)], [native(source)])
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert report["replaced_regions"] == report["inserted_regions"] == 0


def test_owned_cjk_blocks_and_physical_lines_do_not_create_paragraphs_or_spaces():
    parsed = "本期营业收入为120.5O万元，公司经营状况保持稳定，相关合同约定没有变化。"
    sources = [native("本期营业收入为120.50万元，\n公司经营状况保持稳定，", (0.1, 0.1, 0.9, 0.14)),
               native("相关合同约定没有变化。", (0.1, 0.15, 0.9, 0.2))]
    result, evidence = document(parsed, [region(parsed)], sources)
    receipt = apply(result, evidence)
    assert result.pages[0].content == parsed.replace("5O", "50")
    action = receipt["pages"][0]["actions"][0]
    assert action["raw_native_text"] == [block.text for block in sources]
    assert "\n\n" in action["physical_native_text"]
    assert action["rendered_replacement"] == result.pages[0].content


def test_owned_english_blocks_preserve_existing_soft_wrap_within_one_paragraph():
    parsed = "The authored operating revenue was 120.5O and\nthe reporting scope remained stable."
    result, evidence = document(parsed, [region(parsed)], [
        native("The authored operating revenue was 120.50 and", (0.1, 0.1, 0.9, 0.14)),
        native("the reporting scope remained stable.", (0.1, 0.15, 0.9, 0.2)),
    ])
    receipt = apply(result, evidence)
    assert result.pages[0].content == parsed.replace("5O", "50")
    assert receipt["replaced_regions"] == 1


def test_font_blocks_splitting_one_english_word_do_not_add_a_space():
    parsed = "The authored paragraph has operating revenue 120.5O under the unchanged scope."
    result, evidence = document(parsed, [region(parsed)], [
        native("The authored para", (0.1, 0.1, 0.4, 0.2)),
        native("graph has operating revenue 120.50 under the unchanged scope.", (0.4, 0.1, 0.9, 0.2)),
    ])
    apply(result, evidence)
    assert result.pages[0].content == parsed.replace("5O", "50")


def test_physical_english_line_break_follows_parser_word_space():
    parsed = "The authored operating revenue was 120.5O and the reporting scope remained stable."
    result, evidence = document(parsed, [region(parsed)], [
        native("The authored operating revenue was 120.50 and\nthe reporting scope remained stable."),
    ])
    apply(result, evidence)
    assert result.pages[0].content == parsed.replace("5O", "50")


def test_explicit_source_space_can_separate_a_physically_split_word_pair():
    parsed = "The authored operating revenue was 120.5O andthe reporting scope remained stable."
    result, evidence = document(parsed, [region(parsed)], [
        native("The authored operating revenue was 120.50 and ", (0.1, 0.1, 0.9, 0.14)),
        native("the reporting scope remained stable.", (0.1, 0.15, 0.9, 0.2)),
    ])
    apply(result, evidence)
    assert result.pages[0].content == parsed.replace("5O", "50").replace("andthe", "and the")


@pytest.mark.parametrize("parts, parsed", [
    (["The source has value 120.5", "0 and a stable reporting scope."],
     "The source has value 120.5O and a stable reporting scope."),
    (["a", "bcXabcYabc"], "abcZabcWabc"),
])
def test_unsupported_or_repeated_boundary_context_keeps_the_original_candidate(parts, parsed):
    sources = [native(parts[0], (0.1, 0.1, 0.9, 0.14)),
               native(parts[1], (0.1, 0.15, 0.9, 0.2))]
    result, evidence = document(parsed, [region(parsed)], sources)
    receipt = apply(result, evidence)
    assert result.pages[0].content == parsed and receipt["replaced_regions"] == 0
    diagnostic = receipt["pages"][0]["unresolved"][0]
    assert diagnostic["reason"] == "native_paragraph_boundary_unresolved"
    assert diagnostic["raw_native_text"] == parts


@pytest.mark.parametrize("split", [False, True])
def test_ascii_width_equivalence_preserves_parser_format_without_an_action(split):
    parsed = "本期营业收入为120.50万元，公司经营状况保持稳定，相关合同约定没有变化。"
    source = parsed.replace("120.50", "１２０.５０")
    sources = ([native(source[:30], (0.1, 0.1, 0.9, 0.14)),
                native(source[30:], (0.1, 0.15, 0.9, 0.2))] if split else [native(source)])
    result, evidence = document(parsed, [region(parsed)], sources)
    receipt = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert receipt["replaced_regions"] == receipt["inserted_regions"] == 0
    assert receipt["preserved_regions"] == 1 and receipt["pages"][0]["actions"] == []
    preserved = receipt["pages"][0]["preserved"][0]
    assert preserved["reason"] == "equivalent_native_region_preserved"
    assert preserved["raw_native_text"] == [block.text for block in sources]
    assert preserved["rendered_native_text"] == source
    assert result.pages[0].diagnostics.selected_strategy != SelectionStrategy.NATIVE_REPAIR


def test_existing_parser_multi_paragraph_envelope_is_not_flattened_before_structural_check():
    first = "The first authored paragraph has operating revenue 120.5O under its original scope."
    last = "The second authored paragraph has operating revenue 220.5O under a separate scope."
    parsed = first + "\n\n" + last
    result, evidence = document(parsed, [region(parsed)], [
        native(first.replace("5O", "50"), (0.1, 0.1, 0.9, 0.14)),
        native(last.replace("5O", "50"), (0.1, 0.15, 0.9, 0.2)),
    ])
    receipt = apply(result, evidence)
    assert result.pages[0].content == parsed and receipt["replaced_regions"] == 0
    assert receipt["pages"][0]["unresolved"][0]["reason"] == "rich_parser_structure_preserved"


def test_independent_parser_paragraph_and_list_boundaries_survive_native_replacement():
    first = "The first authored paragraph has operating revenue 120.5O under its original scope."
    last = "- The independent list item has operating revenue 220.5O under a separate scope."
    parsed = first + "\n\n" + last
    result, evidence = document(parsed, [region(first, (0.1, 0.1, 0.9, 0.14)),
                                         region(last, (0.1, 0.15, 0.9, 0.2), role="list")], [
        native(first.replace("5O", "50"), (0.1, 0.1, 0.9, 0.14)),
        native(last[2:].replace("5O", "50"), (0.1, 0.15, 0.9, 0.2)),
    ])
    receipt = apply(result, evidence)
    assert result.pages[0].content == parsed.replace("5O", "50")
    assert receipt["replaced_regions"] == 2


def test_multiple_list_items_in_one_parser_envelope_remain_structurally_intact():
    parsed = "- The first authored operating value was 120.5O.\n- The second authored value was 220.5O."
    result, evidence = document(parsed, [region(parsed, role="list")], [
        native("The first authored operating value was 120.50.", (0.1, 0.1, 0.9, 0.14)),
        native("The second authored value was 220.50.", (0.1, 0.15, 0.9, 0.2)),
    ])
    receipt = apply(result, evidence)
    assert result.pages[0].content == parsed and receipt["replaced_regions"] == 0
    assert receipt["pages"][0]["unresolved"][0]["reason"] == "rich_parser_structure_preserved"


def test_width_preservation_does_not_apply_general_compatibility_or_sign_normalization():
    parsed = "The authored section 1 has a financial value of -120.50 under the original scope."
    source = parsed.replace("section 1", "section ①").replace("-120.50", "−120.50")
    result, evidence = document(parsed, [region(parsed)], [native(source)])
    receipt = apply(result, evidence)
    assert result.pages[0].content == source and receipt["replaced_regions"] == 1
    assert receipt["preserved_regions"] == 0


def test_authored_pdf_font_and_line_blocks_repair_one_known_parser_paragraph(tmp_path):
    import pymupdf

    from app.models.source import StoredSource
    from app.services.evidence_service import PageEvidenceService

    path = tmp_path / "authored-font-lines.pdf"
    first = "The authored operating revenue was 120.50 and"
    last = "the reporting scope remained stable under the contract."
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=300)
        page.insert_text((20, 60), first, fontname="helv", fontsize=10)
        page.insert_text((20, 78), last, fontname="hebo", fontsize=10)
        pdf.save(path)
    source = StoredSource(path=path, filename=path.name, mime_type="application/pdf",
                          size_bytes=path.stat().st_size, page_count=1)
    evidence = PageEvidenceService().inspect(source, {1})[1]
    assert len(evidence.native_blocks) == 2
    assert [block.bold for block in evidence.native_blocks] == [False, True]
    boxes = [block.bbox for block in evidence.native_blocks]
    box = (min(b[0] for b in boxes) / 600, min(b[1] for b in boxes) / 300,
           max(b[2] for b in boxes) / 600, max(b[3] for b in boxes) / 300)
    parsed = (first + " " + last).replace("120.50", "120.5O")
    result, _ = document(parsed, [region(parsed, box)], [])
    receipt = apply(result, evidence)
    assert result.pages[0].content == first + " " + last
    assert receipt["replaced_regions"] == 1


def test_off_page_native_text_is_not_recovered_as_visible_prose():
    parsed = "The visible parser paragraph is complete and source-owned."
    invisible = "The off-page authored text must not be inserted into the output."
    result, evidence = document(parsed, [region(parsed)], [native(parsed), native(invisible, (0.1, 0.3, 1.2, 0.4))])
    apply(result, evidence)
    assert result.pages[0].content == parsed


def test_second_application_keeps_output_and_original_action_receipt():
    parsed = "Source revenue is 120.5O and the business scope remains unchanged."
    source = parsed.replace("5O", "50")
    result, evidence = document(parsed, [region(parsed)], [native(source)])
    service = NativeTextService()
    report = service.apply(result, {1: evidence}, OPTIONS)
    again = service.apply(result, {1: evidence}, OPTIONS)
    assert again is report and again["replaced_regions"] == 1
    assert result.pages[0].content == source


def test_cancellation_is_observed_without_altering_candidate():
    parsed = "An authored source paragraph remains unchanged during cancellation."
    result, evidence = document(parsed, [region(parsed)], [native(parsed)])
    with pytest.raises(ParserCancelledError):
        NativeTextService().apply(result, {1: evidence}, OPTIONS,
                                  cancel_event=SimpleNamespace(is_set=lambda: True))
    assert result.pages[0].content == parsed and result._source_verification == {}


@pytest.mark.parametrize("field", ["_table_fragments", "_picture_candidates", "_source_regions", "_page_furniture"])
def test_parser_region_crossing_protected_content_cannot_be_replaced_from_remaining_native_subset(field):
    safe = "This authored business paragraph retains the complete operating description and every original contractual qualification."
    protected = "Protected labels: 10 20 30 40."
    parsed = safe + " " + protected
    whole, first, second = (0.1, 0.1, 0.9, 0.6), (0.1, 0.1, 0.9, 0.2), (0.1, 0.4, 0.9, 0.6)
    result, evidence = document(parsed, [region(parsed, whole)],
                                [native(safe, first), native(protected, second)])
    setattr(result, field, [SimpleNamespace(page_number=1, normalized_bbox=second)])
    report = apply(result, evidence)

    assert result.pages[0].content == parsed
    assert protected in result.pages[0].content
    assert report["replaced_regions"] == report["inserted_regions"] == 0
    rejected = report["pages"][0]["unresolved"][0]
    assert rejected["reason"] == "parser_region_crosses_protected_area"
    assert rejected["parser_markdown"] == parsed


def test_parser_region_crossing_unclassified_grid_is_preserved_as_one_original_span():
    safe = "This source prose is outside the grid and contains a complete business explanation."
    protected = "A grid statement with value 20 remains part of this returned region."
    parsed = safe + " " + protected
    whole, first, second = (0.1, 0.1, 0.9, 0.6), (0.1, 0.1, 0.9, 0.2), (0.1, 0.4, 0.9, 0.6)
    result, evidence = document(parsed, [region(parsed, whole)], [native(safe, first), native(protected, second)])
    evidence.grid_regions = [second]
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert report["pages"][0]["unresolved"][0]["reason"] == "parser_region_crosses_protected_area"


@pytest.mark.parametrize("remainder,expected_reason", [
    (native("Unhealthy source text \ufffd preserves the candidate value.", (0.1, 0.4, 0.9, 0.6)), "native_source_text_unhealthy"),
    (native("Out-of-page source text preserves the candidate value.", (0.1, 0.4, 1.2, 0.6)), "native_source_outside_page"),
    (native("A partially shared source block is not a complete region witness.", (0.1, 0.55, 0.9, 0.8)), "native_source_crosses_parser_region"),
])
def test_ineligible_intersecting_native_block_blocks_whole_region_replacement(remainder, expected_reason):
    safe = "This authored business paragraph has a complete description with unchanged financial qualifications."
    preserved = "The original candidate also contains this retained remainder."
    parsed = safe + " " + preserved
    whole, first = (0.1, 0.1, 0.9, 0.6), (0.1, 0.1, 0.9, 0.2)
    result, evidence = document(parsed, [region(parsed, whole)], [native(safe, first), remainder])
    report = apply(result, evidence)

    assert result.pages[0].content == parsed
    assert report["replaced_regions"] == report["inserted_regions"] == 0
    rejected = report["pages"][0]["unresolved"][0]
    assert rejected["reason"] == "incomplete_native_region_coverage"
    assert expected_reason in {item["reason"] for item in rejected["sources"]}
    assert rejected["parser_markdown"] == parsed


def test_mostly_owned_native_block_cannot_add_its_outside_tail_by_replacing_region():
    parsed = "The source paragraph has a financial value of 120.5O and an unchanged business scope."
    source = parsed.replace("5O", "50")
    # More than 80% overlaps, but the source block still crosses its claimed owner.
    result, evidence = document(parsed, [region(parsed, (0.1, 0.1, 0.9, 0.2))],
                                [native(source, (0.1, 0.1, 0.9, 0.21))])
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert report["replaced_regions"] == 0
    assert report["pages"][0]["unresolved"][0]["sources"][0]["reason"] == "native_source_crosses_parser_region"


def test_unhealthy_disjoint_native_block_does_not_block_independent_healthy_region():
    parsed = "The complete source paragraph has an operating value of 120.5O."
    source = parsed.replace("5O", "50")
    result, evidence = document(parsed, [region(parsed)],
        [native(source), native("The separate unknown paragraph \ufffd stays outside.", (0.1, 0.5, 0.9, 0.6))])
    report = apply(result, evidence)
    assert result.pages[0].content == source and report["replaced_regions"] == 1


def test_preserved_incomplete_region_blocks_insertions_inside_or_through_it():
    first = "The first authored paragraph provides a complete source anchor."
    safe = "A second authored paragraph lies before an unknown retained chart."
    protected = "Retained chart text 10 20 30 remains visible in this source region."
    last = "The last authored paragraph provides another complete source anchor."
    missing = "This independent source prose cannot cross the retained middle owner."
    a, whole, b, c, d, e = (0.1, 0.05, 0.9, 0.1), (0.1, 0.2, 0.9, 0.7), (0.1, 0.2, 0.9, 0.3), (0.1, 0.4, 0.9, 0.5), (0.1, 0.6, 0.9, 0.7), (0.1, 0.8, 0.9, 0.9)
    middle = safe + " " + protected
    markdown = first + "\n\n" + middle + "\n\n" + last
    result, evidence = document(markdown, [region(first, a), region(middle, whole), region(last, e)],
        [native(first, a), native(safe, b), native(missing, c), native(protected, d), native(last, e)])
    result._picture_candidates = [SimpleNamespace(page_number=1, normalized_bbox=d)]
    report = apply(result, evidence)
    assert result.pages[0].content == markdown
    assert report["replaced_regions"] == report["inserted_regions"] == 0
    assert "native_prose_overlaps_preserved_region" in {
        item["reason"] for item in report["pages"][0]["unresolved"]
    }


def test_missing_prose_with_overlapping_unhealthy_native_source_is_not_inserted():
    first = "The first authored paragraph supplies an independent source anchor."
    last = "The last authored paragraph supplies another independent source anchor."
    missing = "This missing native paragraph has a spatially overlapping unknown source."
    a, b, c = (0.1, 0.1, 0.9, 0.2), (0.1, 0.3, 0.9, 0.5), (0.1, 0.7, 0.9, 0.8)
    markdown = first + "\n\n" + last
    result, evidence = document(markdown, [region(first, a), region(last, c)],
        [native(first, a), native(missing, b), native("Unreadable native source \ufffd", (0.1, 0.45, 0.9, 0.55)), native(last, c)])
    report = apply(result, evidence)
    assert result.pages[0].content == markdown
    assert report["inserted_regions"] == 0
    assert "overlapping_native_prose_sources" in {
        item["reason"] for item in report["pages"][0]["unresolved"]
    }


def test_missing_prose_cannot_cross_a_disjoint_unhealthy_source_on_both_sides():
    first = "The first complete authored paragraph supplies a source anchor."
    last = "The last complete authored paragraph supplies a source anchor."
    missing = "This missing authored prose is surrounded by unresolved native content."
    a, b, c = (0.1, 0.1, 0.9, 0.2), (0.1, 0.4, 0.9, 0.5), (0.1, 0.7, 0.9, 0.8)
    markdown = first + "\n\n" + last
    result, evidence = document(markdown, [region(first, a), region(last, c)],
        [native(first, a), native("Unknown native \ufffd before", (0.1, 0.25, 0.9, 0.3)),
         native(missing, b), native("Unknown native \ufffd after", (0.1, 0.6, 0.9, 0.65)), native(last, c)])
    report = apply(result, evidence)
    assert result.pages[0].content == markdown
    assert report["inserted_regions"] == 0
    assert "protected_region_between_prose_anchors" in {
        item["reason"] for item in report["pages"][0]["unresolved"]
    }


def test_source_owned_table_rendering_is_immutable_when_text_and_table_boxes_disagree():
    parsed = "The retained business label has an operating value of 120.5O."
    source = parsed.replace("5O", "50")
    table = "| Label | Value |\n| --- | --- |\n| " + parsed + " | 10 |"
    table_box = (0.1, 0.5, 0.9, 0.8)
    result, evidence = document(table,
        [region(parsed, BOX), region(table, table_box, "table")], [native(source)])
    report = apply(result, evidence)
    assert result.pages[0].content == table
    assert report["replaced_regions"] == 0
    assert report["pages"][0]["unresolved"][0]["protected_rendered_spans"]


def test_missing_paragraph_cannot_be_inserted_inside_a_retained_table_cell_rendering():
    anchor = "The retained table cell contains this apparent standalone paragraph."
    missing = "This actual native paragraph may not be injected into the table cell."
    table = "| Label | Value |\n| --- | --- |\n| " + anchor + " | 10 |"
    table_box, below = (0.1, 0.5, 0.9, 0.8), (0.1, 0.3, 0.9, 0.4)
    result, evidence = document(table,
        [region(anchor, BOX), region(table, table_box, "table")],
        [native(anchor), native(missing, below)])
    report = apply(result, evidence)
    assert result.pages[0].content == table
    assert report["inserted_regions"] == 0


def test_malformed_native_block_neighbors_do_not_discard_a_valid_owned_paragraph():
    parsed = "The valid authored paragraph has an operating value of 120.5O."
    source = parsed.replace("5O", "50")
    raw = [None, "unreadable native neighbor", region(parsed), 17, {"type": "unknown_source_region"}]
    result, evidence = document(parsed, raw, [native(source)])
    report = apply(result, evidence)
    assert result.pages[0].content == source
    assert report["replaced_regions"] == 1
    assert result._native_page_blocks[1] == raw


def test_none_native_page_container_preserves_that_page_without_raising():
    parsed = "This original candidate paragraph must remain available."
    result, evidence = document(parsed, [], [native(parsed)])
    result._native_page_blocks[1] = None
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert report["replaced_regions"] == report["inserted_regions"] == 0
    assert report["pages"][0]["unresolved"][0]["reason"] == "native_page_blocks_not_list"


def test_none_and_unknown_source_region_neighbors_preserve_declared_region_and_valid_prose():
    parsed = "The valid business paragraph has a financial value of 120.5O."
    source = parsed.replace("5O", "50")
    unknown = SourceRegionEvidence(
        source_ref="authored-unknown", page_number=1, normalized_bbox=(0.1, 0.5, 0.9, 0.7),
        literal_text="The unresolved grid retains its original value 30.",
        source_sha256="0" * 64, glyphs=(), page_width=100, page_height=100,
        rotation_degrees=0, original_table={},
    )
    markdown = parsed + "\n\n" + unknown.rendered
    result, evidence = document(markdown, [region(parsed)], [native(source)])
    neighbors = [None, object(), {"unknown_source_region": "unreadable"}, unknown]
    result._source_regions = neighbors
    report = apply(result, evidence)
    assert result.pages[0].content == source + "\n\n" + unknown.rendered
    assert report["replaced_regions"] == 1
    assert result._source_regions == neighbors


def test_excluded_native_margin_blocks_protect_a_combined_parser_envelope():
    safe = "The authored business paragraph preserves all of its original reporting and contractual qualifications."
    header = "Authored running header"
    body_box, header_box, combined = (0.1, 0.2, 0.9, 0.3), (0.1, 0.02, 0.9, 0.05), (0.1, 0.02, 0.9, 0.3)
    parsed = header + " " + safe
    result, evidence = document(parsed, [region(parsed, combined)], [native(safe, body_box)])
    evidence.excluded_native_blocks = [native(header, header_box)]
    report = apply(result, evidence)
    assert result.pages[0].content == parsed
    assert report["replaced_regions"] == report["inserted_regions"] == 0
    assert report["pages"][0]["unresolved"][0]["reason"] == "parser_region_crosses_protected_area"


def test_excluded_native_margin_does_not_block_a_disjoint_complete_body_region():
    source = "The authored business paragraph has a financial value of 120.50 under the original scope."
    parsed = source.replace("120.50", "120.5O")
    body_box, header_box = (0.1, 0.2, 0.9, 0.3), (0.1, 0.02, 0.9, 0.05)
    result, evidence = document(parsed, [region(parsed, body_box)], [native(source, body_box)])
    evidence.excluded_native_blocks = [native("Authored running header", header_box)]
    report = apply(result, evidence)
    assert result.pages[0].content == source and report["replaced_regions"] == 1


def test_repeated_margin_evidence_is_retained_and_protects_combined_regions_in_authored_two_page_pdf(tmp_path):
    import pymupdf

    from app.models.source import StoredSource
    from app.services.evidence_service import PageEvidenceService

    header, footer = "Authored running header", "Authored running footer"
    bodies = [
        "The authored body paragraph for page one has value 120.50 under the unchanged scope.",
        "The authored body paragraph for page two has value 220.50 under the unchanged scope.",
    ]
    path = tmp_path / "authored-two-page.pdf"
    with pymupdf.open() as source:
        for body in bodies:
            page = source.new_page(width=500, height=400)
            page.insert_text((20, 15), header, fontsize=6)
            page.insert_text((20, 150), body, fontsize=8)
            page.insert_text((20, 390), footer, fontsize=6)
        source.save(path)
    stored = StoredSource(path=path, filename=path.name, mime_type="application/pdf",
                          size_bytes=path.stat().st_size, page_count=2)
    observed = PageEvidenceService().inspect(stored, {1, 2})
    assert set(observed) == {1, 2}
    for number, evidence in observed.items():
        assert {block.text for block in evidence.excluded_native_blocks} == {header, footer}
        assert header not in evidence.native_body_text and footer not in evidence.native_body_text
        assert bodies[number - 1] in evidence.native_body_text
        body = next(block for block in evidence.native_blocks if bodies[number - 1] in block.text)
        excluded_header = next(block for block in evidence.excluded_native_blocks if block.text == header)
        combined_box = (
            min(body.bbox[0], excluded_header.bbox[0]) / evidence.page_width,
            excluded_header.bbox[1] / evidence.page_height,
            max(body.bbox[2], excluded_header.bbox[2]) / evidence.page_width,
            body.bbox[3] / evidence.page_height,
        )
        parsed = header + " " + bodies[number - 1]
        result, _ = document(parsed, [region(parsed, combined_box)], [])
        result.pages[0].page_number = number
        result.page_count = 2
        result._native_page_blocks = {number: result._native_page_blocks[1]}
        report = NativeTextService().apply(result, {number: evidence}, OPTIONS)
        assert result.pages[0].content == parsed and report["replaced_regions"] == 0
        assert report["pages"][0]["unresolved"][0]["reason"] == "parser_region_crosses_protected_area"

        # The same excluded margins do not disable an independently owned body.
        body_box = tuple(value / (evidence.page_width if index % 2 == 0 else evidence.page_height)
                         for index, value in enumerate(body.bbox))
        parsed_body = bodies[number - 1].replace(".50", ".5O")
        result, _ = document(parsed_body, [region(parsed_body, body_box)], [])
        result.pages[0].page_number = number
        result.page_count = 2
        result._native_page_blocks = {number: result._native_page_blocks[1]}
        report = NativeTextService().apply(result, {number: evidence}, OPTIONS)
        assert result.pages[0].content == bodies[number - 1] and report["replaced_regions"] == 1
