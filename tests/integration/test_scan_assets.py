"""Real PDF pixels and HTTP downloads survive OCR-only model responses."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.lifespan import build_runtime
from app.main import create_app
from app.models import (
    BackendState,
    BackendStatus,
    DocumentParseResult,
    PageParseResult,
    PageSourceKind,
    ParsePipeline,
    StoredSource,
)
from app.services.evidence_service import PageEvidenceService
from app.utils.page_range import parse_page_range
from tests.conftest import make_test_settings


class NativeTextFixture:
    """Return source text for native fixture pages without loading table weights."""

    name = "docling-standard"

    def __init__(self):
        self.pages: list[int] = []

    async def initialize(self):
        return None

    async def close(self):
        return None

    async def probe(self, **_kwargs):
        return BackendStatus(name=self.name, state=BackendState.READY)

    async def parse(self, source, options, *, document_id, **_kwargs):
        selected = parse_page_range(options.unit_range, source.page_count)
        self.pages.extend(selected)
        with pymupdf.open(source.path) as document:
            pages = [PageParseResult(page_number=number, backend=self.name,
                                    content=document[number - 1].get_text()) for number in selected]
        return DocumentParseResult(
            document_id=document_id, filename=source.filename, mime_type=source.mime_type,
            page_count=source.page_count, processed_pages=len(pages), pages=pages,
            pipeline=ParsePipeline(profile=options.profile.value, primary=self.name),
        )


@pytest.fixture(params=["scanned-report.pdf", "mixed-report.pdf", "mixed-layer"])
def source_pdf(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    if request.param != "mixed-layer":
        return Path("tests/fixtures") / request.param
    # Reuse the real scan and add an independently searchable text layer. This
    # exercises MIXED page evidence as well as a native+scan multipage document.
    path = tmp_path / "mixed-layer.pdf"
    with pymupdf.open("tests/fixtures/scanned-report.pdf") as document:
        document[0].insert_text((15, 15), "Searchable native header preserved alongside the raster source.",
                                fontsize=8)
        document.save(path)
    return path


def app_with_model_stubs(tmp_path: Path, *, empty_sdk: bool = False, **overrides):
    values = dict(glm_ocr_enabled=True, glm_sdk_enabled=True, glm_sdk_orientation_enabled=False,
                  glm_sdk_url="http://sdk.fixture/glmocr/parse", glm_sdk_max_retries=0)
    values.update(overrides)
    settings = make_test_settings(tmp_path, **values)
    observed = SimpleNamespace(results=[], posts=0, native=NativeTextFixture(), runtime=None)

    async def sdk_response(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "sdk.fixture"
        if request.method == "GET":
            assert request.url.path == "/health"
            return httpx.Response(200, json={"status": "ok"})
        assert request.url.path == "/glmocr/parse"
        observed.posts += 1
        regions = [] if empty_sdk else [
            {"index": 0, "label": "text", "content": "SDK only recognizes printed body text.",
             "bbox_2d": [100, 100, 700, 500]}
        ]
        return httpx.Response(200, json={"layout_details": [regions]})

    def factory(runtime_settings):
        runtime = build_runtime(runtime_settings)
        parser = runtime.parser_service
        parser.standard_parser = observed.native
        parser.glm_sdk_parser._client = httpx.AsyncClient(transport=httpx.MockTransport(sdk_response))
        parser.glm_adapter.recognize_image = AsyncMock(
            side_effect=AssertionError("preserving an already routed page must not run OCR twice")
        )
        original_parse = parser.parse

        async def capture_result(*args, **kwargs):
            result = await original_parse(*args, **kwargs)
            observed.results.append(result)
            return result

        parser.parse = capture_result
        observed.runtime = runtime
        return runtime

    return create_app(settings, runtime_factory=factory), observed


def scan_pages(path: Path) -> tuple[set[int], int]:
    with pymupdf.open(path) as document:
        count = len(document)
    source = StoredSource(path=path, filename=path.name, mime_type="application/pdf",
                          size_bytes=path.stat().st_size, page_count=count)
    evidence = PageEvidenceService().inspect(source, set(range(1, count + 1)))
    return {number for number, item in evidence.items()
            if item.source_kind in {PageSourceKind.SCANNED, PageSourceKind.MIXED}}, count


def assert_download_preserves_page(client: TestClient, asset: dict, source: Path, page_number: int):
    response = client.get(asset["download_url"])
    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == asset["sha256"]
    assert len(response.content) == asset["size_bytes"]
    with pymupdf.open(source) as document:
        pixmap = document[page_number - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        expected_size, expected_pixels = (pixmap.width, pixmap.height), pixmap.samples
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == expected_size
        assert image.convert("RGB").tobytes() == expected_pixels
    return response.content


@pytest.mark.parametrize("scan_policy", ["auto", "skip"])
@pytest.mark.parametrize("describe_images", [False, True])
def test_scan_and_mixed_pdf_source_pixels_remain_downloadable_without_duplicate_ocr(
    tmp_path: Path, source_pdf: Path, scan_policy: str, describe_images: bool,
) -> None:
    target_pages, count = scan_pages(source_pdf)
    assert target_pages
    app, observed = app_with_model_stubs(tmp_path / "service")
    with TestClient(app) as client:
        response = client.post(
            "/v1/content/parse",
            files={"file": (source_pdf.name, source_pdf.read_bytes(), "application/pdf")},
            data={"scan_policy": scan_policy, "describe_images": str(describe_images).lower()},
        )
        assert response.status_code == 200, response.text
        job_id = response.headers["x-content-id"]
        public = client.get(f"/v1/content/jobs/{job_id}/assets")
        assert public.status_code == 200
        assets = public.json()
        assert len(assets) == len(target_pages)
        [parsed] = observed.results
        internal = parsed.parse_result
        assert internal is not None
        assert internal.source.source_sha256 == hashlib.sha256(source_pdf.read_bytes()).hexdigest()
        assert observed.posts == (len(target_pages) if scan_policy == "auto" else 0)
        assert set(observed.native.pages) == set(range(1, count + 1)) - target_pages
        observed.runtime.parser_service.glm_adapter.recognize_image.assert_not_awaited()
        for page_number in target_pages:
            unit = next(unit for unit in internal.units if unit.index == page_number)
            assert len(unit.asset_ids) == 1
            asset_id = unit.asset_ids[0]
            public_asset = next(asset for asset in assets if asset["asset_id"] == asset_id)
            internal_asset = next(asset for asset in internal.assets if asset.asset_id == asset_id)
            location = next(item for item in internal_asset.locations if item.page_number == page_number)
            assert location.unit_id == unit.unit_id
            assert location.bbox.model_dump() == {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
            assert internal_asset.visual_analysis is None
            assert public_asset["download_url"] in response.text
            downloaded = assert_download_preserves_page(client, public_asset, source_pdf, page_number)
            stored = observed.runtime.storage_service.asset_path(job_id, asset_id)
            assert stored.read_bytes() == downloaded


def test_scanned_source_asset_survives_empty_sdk_response(tmp_path: Path) -> None:
    path = Path("tests/fixtures/scanned-report.pdf")
    app, observed = app_with_model_stubs(tmp_path, empty_sdk=True)
    with TestClient(app) as client:
        response = client.post("/v1/content/parse", files={"file": (path.name, path.read_bytes(), "application/pdf")})
        assert response.status_code == 200, response.text
        job_id = response.headers["x-content-id"]
        assets = client.get(f"/v1/content/jobs/{job_id}/assets").json()
        assert len(assets) == 1
        assert_download_preserves_page(client, assets[0], path, 1)
        [parsed] = observed.results
        assert parsed.pages[0].status.value == "failed"
        assert parsed.parse_result.units[0].asset_ids == [assets[0]["asset_id"]]
        assert parsed.parse_result.assets[0].locations[0].page_number == 1
        assert observed.posts == 1
        observed.runtime.parser_service.glm_adapter.recognize_image.assert_not_awaited()


def test_scan_asset_limit_reports_partial_and_keeps_saved_page_downloadable(tmp_path: Path) -> None:
    path = tmp_path / "two-scanned-pages.pdf"
    with pymupdf.open("tests/fixtures/scanned-report.pdf") as original, pymupdf.open() as document:
        document.insert_pdf(original)
        document.insert_pdf(original)
        document[1].draw_rect(pymupdf.Rect(10, 10, 40, 40), color=(1, 0, 0), fill=(1, 0, 0))
        document.save(path)
    app, observed = app_with_model_stubs(tmp_path / "service", max_assets_per_content=1)
    with TestClient(app) as client:
        response = client.post("/v1/content/parse", files={"file": (path.name, path.read_bytes(), "application/pdf")})
        assert response.status_code == 200, response.text
        job_id = response.headers["x-content-id"]
        assets = client.get(f"/v1/content/jobs/{job_id}/assets").json()
        assert len(assets) == 1
        assert_download_preserves_page(client, assets[0], path, 1)
        [parsed] = observed.results
        assert parsed.parse_result.status == "partial"
        assert client.get(f"/v1/content/jobs/{job_id}").json()["status"] == "partial"
        warning = next(item for item in parsed.parse_result.warnings if item.code == "asset_limit_exceeded")
        assert warning.count == 1
        persisted_warnings = json.loads(
            (observed.runtime.storage_service.logs_dir(job_id) / "warnings.json").read_text()
        )
        assert any(item["code"] == "asset_limit_exceeded"
                   for item in persisted_warnings["document_warnings"])
        assert parsed.parse_result.units[0].asset_ids == [assets[0]["asset_id"]]
        assert parsed.parse_result.units[1].asset_ids == []
        assert observed.posts == 2


def test_identical_scans_share_download_but_keep_every_page_under_unique_asset_limit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "repeated-scanned-source.pdf"
    with pymupdf.open("tests/fixtures/scanned-report.pdf") as original, pymupdf.open() as document:
        document.insert_pdf(original)
        document.insert_pdf(original)
        document.save(path)
    app, observed = app_with_model_stubs(tmp_path / "service", max_assets_per_content=1)
    with TestClient(app) as client:
        response = client.post(
            "/v1/content/parse", files={"file": (path.name, path.read_bytes(), "application/pdf")},
            data={"describe_images": "true"},
        )
        assert response.status_code == 200, response.text
        job_id = response.headers["x-content-id"]
        assets = client.get(f"/v1/content/jobs/{job_id}/assets").json()
        assert len(assets) == 1
        assert_download_preserves_page(client, assets[0], path, 1)
        assert_download_preserves_page(client, assets[0], path, 2)
        [parsed] = observed.results
        internal = parsed.parse_result
        assert all(unit.asset_ids == [assets[0]["asset_id"]] for unit in internal.units)
        assert {location.page_number for location in internal.assets[0].locations} == {1, 2}
        assert {location.unit_id for location in internal.assets[0].locations} == {
            unit.unit_id for unit in internal.units
        }
        assert not any(warning.code == "asset_limit_exceeded" for warning in internal.warnings)
        assert observed.posts == 2
        observed.runtime.parser_service.glm_adapter.recognize_image.assert_not_awaited()
