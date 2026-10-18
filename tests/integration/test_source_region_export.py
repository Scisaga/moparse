"""Unknown structure keeps an original crop and literal text through persistence."""

from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.content_result import ElementQuality, RegionType
from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from app.models.source import StoredSource
from app.models.source_evidence import SourceRegionEvidence, SourceRegionPictureCandidate
from app.services.export_service import ExportService
from app.services.ir_service import DocumentIRService
from app.services.multimodal_service import MultimodalService
from app.services.storage_service import StorageService
from tests.conftest import fake_runtime, make_test_settings


@pytest.mark.integration
async def test_unknown_region_literal_text_image_and_private_evidence_survive_export(tmp_path: Path):
    source_path = tmp_path / "source.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=300, height=300)
        page.insert_text((30, 75), "Original text")
        pdf.save(source_path)
    literal = "Original | text\n```\n<literal> &amp; -1.00  \n"
    region = SourceRegionEvidence(
        source_ref="mineru_p1_t2",
        page_number=1,
        normalized_bbox=(0.05, 0.05, 0.95, 0.95),
        literal_text=literal,
        source_sha256="a" * 64,
        glyphs=(),
        page_width=300,
        page_height=300,
        rotation_degrees=0,
        original_table={"fragment_id": "mineru_p1_t2", "rows": [["private model candidate"]]},
        raw_model_table_html="<table><tr><td>private model candidate</td></tr></table>",
    )
    result = DocumentParseResult(
        document_id="job_unknown_region",
        filename="source.pdf",
        mime_type="application/pdf",
        page_count=1,
        processed_pages=1,
        pages=[PageParseResult(page_number=1, content=f"Before\n\n{region.rendered}")],
        pipeline=ParsePipeline(profile="balanced", primary="mineru-advanced-txt"),
    )
    result._source_regions = [region]
    result._picture_candidates = [
        SourceRegionPictureCandidate(1, region.normalized_bbox, region.source_ref)
    ]
    result.markdown, result.plain_text = ExportService().join_document(
        result.pages, preserve_page_breaks=True, source_regions=result._source_regions
    )
    settings = SimpleNamespace(data_dir=tmp_path / "data")
    storage = StorageService(settings)
    source = StoredSource(
        path=source_path,
        filename="source.pdf",
        mime_type="application/pdf",
        size_bytes=source_path.stat().st_size,
        page_count=1,
    )
    ir = DocumentIRService(settings).build(result, source, {})
    result.parse_result = ir
    assert ir.status == "partial"
    unknown = next(region for region in ir.units[0].regions if region.region_type == RegionType.UNKNOWN)
    assert unknown.quality == ElementQuality.CONFLICTED
    block = next(block for block in ir.units[0].blocks if block.region_id == unknown.region_id)
    assert block.text == literal

    multimodal = MultimodalService(settings, storage, SimpleNamespace())
    await multimodal.enrich_page_content(ir, result, source, {}, ContentParseOptions())
    assert len(ir.assets) == 1
    asset = ir.assets[0]
    assert unknown.asset_ids == [asset.asset_id]
    assert f"]({asset.download_url})" in ir.renderings.markdown
    assert "source-region-image:" not in ir.renderings.markdown
    assert literal in ir.renderings.markdown
    assert literal in ir.renderings.plain_text
    assert "````text\n" in ir.renderings.markdown
    assert "structure: unknown" in ir.renderings.markdown
    assert "private model candidate" not in ir.model_dump_json()
    assert "private model candidate" not in result.model_dump_json()

    await storage.write_native_evidence(result.document_id, b'{"raw_model":"private model candidate"}')
    evidence = await storage.write_source_verification_evidence(
        result.document_id, {"source_regions": [asdict(region)]}
    )
    result.markdown = ir.renderings.markdown
    result.plain_text = ir.renderings.plain_text
    paths = await storage.write_result(result.document_id, result)
    assert literal in paths.result.read_text()
    assert "private model candidate" not in paths.result.read_text()
    assert "private model candidate" in evidence.read_text()
    index = (storage.output_dir(result.document_id) / "asset-index.json").read_text()
    assert "private model candidate" not in index
    assert "native-source-verification" not in index
    await storage.delete_job(result.document_id)
    assert not evidence.exists()


@pytest.mark.parametrize("source_newline", ["\n", "\r\n", "\r"])
def test_initial_and_persisted_HTTP_markdown_preserve_literal_line_endings(
    tmp_path: Path, native_pdf: Path, source_newline: str
):
    literal = f"Original  {source_newline}<literal> &amp; -1.00{source_newline}"
    markdown = f"<!-- page: 1 -->\n\n```text\n{literal}```\n"
    expected = markdown.encode("utf-8")

    def factory(settings):
        runtime = fake_runtime(settings)
        original_parse = runtime.parser_service.parse

        async def parse(*args, **kwargs):
            result = await original_parse(*args, **kwargs)
            result.markdown = markdown
            result.parse_result.renderings.markdown = markdown
            return result

        runtime.parser_service.parse = parse
        return runtime

    app = create_app(make_test_settings(tmp_path), runtime_factory=factory)
    with TestClient(app) as client:
        response = client.post(
            "/v1/content/parse",
            files={"file": (native_pdf.name, native_pdf.read_bytes(), "application/pdf")},
        )
        assert response.status_code == 200
        identifier = response.headers["x-content-id"]
        assert response.content == expected
        persisted = client.get(f"/v1/content/jobs/{identifier}/result")
        assert persisted.status_code == 200
        assert persisted.content == response.content
        assert (tmp_path / "jobs" / identifier / "output" / "result.md").read_bytes() == expected
