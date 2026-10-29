"""Service handoff regression using authored structures, without a PDF or model."""

from pathlib import Path

import pytest

from app.models import DocumentParseResult, PageParseResult, ParsePipeline, StoredSource
from app.parsers.mineru_native_remote import render_mineru_page
from app.services.export_service import ExportService
from app.services.ir_service import DocumentIRService


@pytest.mark.parametrize("with_broken_region", [False, True])
def test_native_body_survives_table_export_and_structured_handoff(
    tmp_path: Path, with_broken_region: bool
) -> None:
    comparison = "条件为 x < y 且 z > w。"
    grid_prose = "| 审核意见 | 已阅读并签署 |"
    unit = "金额单位：千元"
    note = "注：负值表示流出。"
    table_html = (
        "<table><tr><th>项目</th><th>本期</th></tr><tr><td>净流量</td><td>(12.30)</td></tr></table>"
    )
    blocks = [
        {"type": "text", "markdown": f"{comparison}\n\n{grid_prose}\n\n{unit}"},
        {
            "type": "table",
            "bbox": [0.1, 0.4, 0.9, 0.7],
            "markdown": table_html,
            "content": [
                {
                    "type": "table_body",
                    "bbox": [0.1, 0.4, 0.9, 0.7],
                    "markdown": table_html,
                    "content": table_html,
                }
            ],
        },
        {"type": "text", "markdown": note},
    ]
    if with_broken_region:
        broken_html = '<table><tr><td rowspan="invalid">未能读取表体候选</td></tr></table>'
        blocks.insert(
            2,
            {
                "type": "table",
                "markdown": broken_html,
                "bbox": [0.1, 0.7, 0.9, 0.8],
                "content": [
                    {
                        "type": "table_body",
                        "markdown": broken_html,
                        "content": broken_html,
                        "bbox": [0.1, 0.7, 0.9, 0.8],
                    }
                ],
            },
        )
    markdown, fragments, pictures = render_mineru_page({"page_number": 1, "blocks": blocks})
    pages = [PageParseResult(page_number=1, content=markdown, backend="mineru-native")]
    exported_markdown, exported_text = ExportService().join_document(
        pages, preserve_page_breaks=False, table_fragments=fragments
    )
    source_path = tmp_path / "synthetic.bin"
    source_path.write_bytes(b"authored structures; not a PDF")
    source = StoredSource(
        path=source_path,
        filename=source_path.name,
        mime_type="application/pdf",
        size_bytes=source_path.stat().st_size,
        page_count=1,
    )
    result = DocumentParseResult(
        document_id="doc_handoff",
        filename=source.filename,
        mime_type=source.mime_type,
        page_count=1,
        processed_pages=1,
        pages=pages,
        markdown=exported_markdown,
        plain_text=exported_text,
        pipeline=ParsePipeline(profile="balanced", primary="mineru-native"),
    )
    result._table_fragments = fragments
    result._picture_candidates = pictures
    structured = DocumentIRService().build(result, source, {})

    assert comparison in exported_markdown and comparison in exported_text
    assert grid_prose in exported_markdown
    body = "\n".join(block.text for block in structured.units[0].blocks)
    assert comparison in body and grid_prose in body
    assert unit in body and note in body
    assert "(12.30)" not in body
    assert structured.tables[0].cells[-1].text == "(12.30)"
    if with_broken_region:
        assert "未能读取表体候选" in body
        assert pictures[-1].source_page_ref in exported_markdown


async def test_real_page_join_preserves_second_page_code_and_exact_page_localization(tmp_path: Path):
    from app.models import ContentParseOptions
    from app.services.table_semantics_service import TableSemanticsService
    from moparse_eval.matching import match_units
    from moparse_eval.service_observation import build_service_observation, read_final_observation

    repeated = "Identical sentence."
    pages = [
        PageParseResult(page_number=1, content=repeated),
        PageParseResult(page_number=2, content=repeated + "\n\n    <b>literal</b> &amp;"),
    ]
    markdown, plain = ExportService().join_pages(pages, preserve_page_breaks=True)
    path = tmp_path / "authored.bin"
    path.write_bytes(b"authored handoff; no PDF parsing")
    source = StoredSource(path=path, filename=path.name, mime_type="application/pdf",
                          size_bytes=path.stat().st_size, page_count=2)
    result = DocumentParseResult(
        document_id="doc_multpage_handoff", filename=source.filename, mime_type=source.mime_type,
        page_count=2, processed_pages=2, pages=pages, markdown=markdown, plain_text=plain,
        pipeline=ParsePipeline(profile="balanced", primary="authored-native"),
    )
    result.parse_result = DocumentIRService().build(result, source, {})
    await TableSemanticsService().apply(result, ContentParseOptions())
    result.markdown = result.parse_result.renderings.markdown
    result.plain_text = result.parse_result.renderings.plain_text
    raw = build_service_observation(result, sample_id="authored-multipage")
    raw["input_page_count"] = 2
    derived, _diagnostic = read_final_observation(raw)
    matched = match_units([
        {"id": "one", "kind": "text", "pages": [1], "reference_text": repeated},
        {"id": "two", "kind": "text", "pages": [2], "reference_text": repeated},
    ], derived)

    assert set(matched["matches"]) == {"one", "two"}
    assert result.plain_text.count("<b>literal</b> &amp;") == 1
    assert result.plain_text.count(repeated) == 2
    assert "literal\n    literal" not in result.plain_text
