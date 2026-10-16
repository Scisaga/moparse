from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from pydantic import ValidationError

from app.models import (
    ContentParseOptions,
    DocumentParseResult,
    PageParseResult,
    PageSourceKind,
    ParsePipeline,
    ParseProfile,
    ScanPolicy,
    StoredSource,
)
from app.parsers.docling_standard import DoclingStandardParser
from app.services.evidence_service import PageEvidenceService
from app.services.quality_service import QualityService
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    _anchored_rows,
    assemble_logical_tables,
)


def _result(page: PageParseResult) -> DocumentParseResult:
    return DocumentParseResult(
        document_id="docparse_quality",
        filename="quality.pdf",
        mime_type="application/pdf",
        page_count=1,
        processed_pages=1,
        pages=[page],
        pipeline=ParsePipeline(profile="balanced", primary="docling-standard"),
    )


def test_scan_policy_is_the_only_document_visual_routing_option() -> None:
    assert ContentParseOptions().scan_policy == ScanPolicy.AUTO
    assert ContentParseOptions(profile=ParseProfile.ACCURATE).scan_policy == ScanPolicy.AUTO
    assert ContentParseOptions(profile=ParseProfile.BALANCED).scan_policy == ScanPolicy.SKIP
    assert ContentParseOptions(scan_policy=ScanPolicy.SKIP).scan_policy == ScanPolicy.SKIP
    with pytest.raises(ValidationError):
        ContentParseOptions.model_validate({"scan_policy": "ocr_only"})


def test_sparse_evidence_is_measured_and_not_guessed(tmp_path: Path) -> None:
    path = tmp_path / "sparse.pdf"
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 400), "续页。", fontsize=8)
    document.save(path)
    document.close()
    source = StoredSource(
        path=path,
        filename=path.name,
        mime_type="application/pdf",
        size_bytes=path.stat().st_size,
        page_count=1,
    )

    evidence = PageEvidenceService().inspect(source, {1})[1]

    assert evidence.source_kind == PageSourceKind.SPARSE
    assert evidence.native_text_characters is not None
    assert evidence.native_text_characters < 40
    assert evidence.visual_ink_ratio is not None
    assert evidence.visual_ink_ratio < 0.015




def test_wingdings_mapping_requires_font_evidence() -> None:
    mapped = PageEvidenceService._block_text(
        {"lines": [{"spans": [{"text": "\uf052", "font": "Wingdings 2", "size": 10}]}]}
    )
    unmapped = PageEvidenceService._block_text(
        {"lines": [{"spans": [{"text": "\uf052", "font": "Arial", "size": 10}]}]}
    )
    assert mapped[3] == {"\uf052": "☑"}
    assert unmapped[3] == {}






def test_span_export_anchors_merged_value_and_rejects_overlap() -> None:
    cells = [
        SimpleNamespace(
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=0,
            end_col_offset_idx=2,
            text="合并表头",
        ),
        SimpleNamespace(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            text="A",
        ),
        SimpleNamespace(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=1,
            end_col_offset_idx=2,
            text="B",
        ),
    ]
    rows, reasons = _anchored_rows(SimpleNamespace(num_rows=2, num_cols=2, table_cells=cells))
    assert reasons == []
    assert rows == [["合并表头", ""], ["A", "B"]]

    cells.append(cells[-1])
    _rows, reasons = _anchored_rows(SimpleNamespace(num_rows=2, num_cols=2, table_cells=cells))
    assert reasons == ["overlapping_cells"]


def _fragment(
    fragment_id: str,
    page_number: int,
    bbox: tuple[float, float, float, float],
    rows: list[list[str]],
) -> TableFragment:
    markdown = "\n".join(
        [
            "| " + " | ".join(rows[0]) + " |",
            "| " + " | ".join("---" for _ in rows[0]) + " |",
            *("| " + " | ".join(row) + " |" for row in rows[1:]),
        ]
    )
    return TableFragment(
        fragment_id=fragment_id,
        page_number=page_number,
        ordinal=1,
        normalized_bbox=bbox,
        num_rows=len(rows),
        num_cols=len(rows[0]),
        rows=rows,
        column_boundaries=[0.1, 0.5, 0.9],
        markdown=markdown,
        rendered=f"<!-- table-fragment: {fragment_id} -->\n\n{markdown}",
        has_column_header=True,
        cells=[
            TableCellFragment(row_index, column, 1, 1, text, is_column_header=row_index == 0)
            for row_index, row in enumerate(rows)
            for column, text in enumerate(row)
        ],
    )




def test_cross_page_table_merges_only_canonical_content() -> None:
    header = ["项目", "金额"]
    first = _fragment("p1_t1", 1, (0.1, 0.7, 0.9, 0.96), [header, ["甲", "1"]])
    second = _fragment("p2_t1", 2, (0.1, 0.03, 0.9, 0.4), [header, ["乙", "2"]])
    pages = [
        PageParseResult(page_number=1, content=first.rendered),
        PageParseResult(page_number=2, content=second.rendered),
    ]

    canonical = assemble_logical_tables(pages, [first, second], enabled=True)

    assert "logical-table" in canonical[1]
    assert canonical[1].count("| 项目 | 金额 |") == 1
    assert "| 乙 | 2 |" in canonical[1]
    assert canonical[2] == ""
    assert pages[0].content == first.rendered
    assert pages[1].content == second.rendered
    assert pages[0].diagnostics is not None
    assert pages[0].diagnostics.logical_table_ids == ["table_p1_t1_p2_t1"]


def test_cross_page_continuation_keeps_unproven_blank_column_shape() -> None:
    first = _fragment(
        "p1_t1",
        1,
        (0.15, 0.7, 0.85, 0.96),
        [["项目", "", "序号", "金额"], ["投入", "", "A", "1"]],
    )
    first.column_boundaries = [0.15, 0.32, 0.46, 0.70, 0.84]
    second = _fragment(
        "p2_t1",
        2,
        (0.15, 0.03, 0.84, 0.2),
        [["项", "序号", "金额"], ["差异", "G=E-F", "30,000.00"]],
    )
    second.has_column_header = False
    second.column_boundaries = [0.16, 0.38, 0.68, 0.82]
    pages = [
        PageParseResult(page_number=1, content=first.rendered),
        PageParseResult(page_number=2, content=second.rendered),
    ]

    canonical = assemble_logical_tables(pages, [first, second], enabled=True)

    assert "logical-table" not in canonical[1]
    assert canonical[2] == second.rendered
    assert second.num_cols == 3
    assert "| 差异 | G=E-F | 30,000.00 |" in (pages[1].content or "")










def test_repeated_url_prefix_is_not_repeated_text_corruption() -> None:
    rows = "\n".join(
        f"| 公告 {index} | 巨潮资讯网（http://www.cninfo.com.cn） |" for index in range(8)
    )
    page = PageParseResult(
        page_number=1,
        content=f"| 项目 | 链接 |\n| --- | --- |\n{rows}",
    )

    codes = {warning.code for warning in QualityService().inspect_page(page)}

    assert "repeated_text" not in codes
    assert "unanchored_table_numbers" not in codes


def test_repeated_image_placeholders_are_not_text_corruption() -> None:
    page = PageParseResult(
        page_number=1,
        content="\n\n".join(["签章视觉证据", *(["<!-- image -->"] * 6)]),
    )

    codes = {warning.code for warning in QualityService().inspect_page(page)}

    assert "repeated_text" not in codes


def test_repeated_not_applicable_cells_are_not_header_propagation() -> None:
    page = PageParseResult(
        page_number=1,
        content=(
            "| 项目 | A | B | C | D | E |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| 项目二 | 不适用 | 不适用 | 不适用 | 不适用 | 不适用 |"
        ),
    )

    codes = {warning.code for warning in QualityService().inspect_page(page)}

    assert "table_header_propagation" not in codes


def test_repeated_financial_values_are_not_header_propagation() -> None:
    page = PageParseResult(
        page_number=1,
        content=(
            "| 项目 | 承诺 | 调整 | 实际 | 差额 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 补充流动资金 | 250,000,000.00 | 250,000,000.00 | "
            "250,000,000.00 | 0.00 |"
        ),
    )

    codes = {warning.code for warning in QualityService().inspect_page(page)}

    assert "table_header_propagation" not in codes


def test_overlapping_ocr_dedup_requires_same_text_and_iou() -> None:
    def item(text: str, bbox: tuple[int, int, int, int]) -> SimpleNamespace:
        return SimpleNamespace(
            text=text,
            prov=[
                SimpleNamespace(
                    page_no=1,
                    bbox=SimpleNamespace(l=bbox[0], t=bbox[1], r=bbox[2], b=bbox[3]),
                )
            ],
        )

    items = [
        item("张三", (0, 0, 10, 10)),
        item("张三", (0, 0, 10, 10)),
        item("张三", (30, 30, 40, 40)),
        item("李四", (0, 0, 10, 10)),
    ]
    document = SimpleNamespace(iterate_items=lambda: ((value, 0) for value in items))
    duplicates = DoclingStandardParser._overlapping_text_duplicate_counts(document, (1, 1))
    assert duplicates == {1: Counter({"张三": 1})}
    assert (
        DoclingStandardParser._remove_overlapping_text_duplicates(
            "张三\n张三\n张三\n李四", duplicates[1]
        )
        == "张三\n张三\n李四"
    )
