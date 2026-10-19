"""Replay captured page failure state and real pixels, without OCR inference."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

from app.lifespan import build_runtime
from app.main import create_app
from app.models import (
    BackendState,
    BackendStatus,
    DocumentParseResult,
    PageParseResult,
    ParsePipeline,
)
from app.models.parse_result import PageStatus, PipelineWarning, RouteSummary
from app.parsers.glm_sdk_remote import GlmSdkRemoteParser
from tests.conftest import make_test_settings
from tests.integration.test_scan_assets import NativeTextFixture

FIXTURE = Path("tests/fixtures/sdk-failed-census-p6")


def test_real_census_failed_state_keeps_page_position_and_source_through_http(tmp_path):
    state = json.loads((FIXTURE / "state.json").read_text())
    pdf = (FIXTURE / "source.pdf").read_bytes()
    png = (FIXTURE / "source-page.png").read_bytes()
    assert hashlib.sha256(pdf).hexdigest() == state["source_sha256"]
    assert hashlib.sha256(png).hexdigest() == state["png_sha256"]
    observed = SimpleNamespace(results=[], runtime=None, sdk_calls=0)
    settings = make_test_settings(tmp_path, glm_ocr_enabled=True, glm_sdk_enabled=True,
        glm_sdk_orientation_enabled=False, max_upload_bytes=2_000_000,
        sync_max_bytes=2_000_000, sync_max_units=20)

    def factory(runtime_settings):
        runtime = build_runtime(runtime_settings)
        coordinator = runtime.parser_service
        coordinator.standard_parser = NativeTextFixture()
        coordinator.glm_adapter.recognize_image = AsyncMock(
            side_effect=AssertionError("source preservation must not run OCR twice"))
        coordinator.glm_sdk_parser.probe = AsyncMock(return_value=BackendStatus(
            name="glm-sdk-remote", state=BackendState.READY))

        async def replay_failure(source, options, *, document_id, **kwargs):
            # Captured page failure state; the original SDK raw response was not saved.
            assert options.unit_range == "6"
            observed.sdk_calls += 1
            return DocumentParseResult(
                document_id=document_id, filename=source.filename, mime_type=source.mime_type,
                page_count=12, processed_pages=0,
                pages=[PageParseResult(page_number=6, status=PageStatus(state["unit"]["status"]),
                    backend="glm-sdk-remote", warnings=[PipelineWarning.model_validate(w)
                    for w in state["unit"]["warnings"]])],
                route_summary=RouteSummary(failed_pages=1),
                pipeline=ParsePipeline(profile=options.profile.value, primary="glm-sdk-remote"))

        coordinator.glm_sdk_parser.parse = replay_failure
        original_parse = coordinator.parse

        async def capture(*args, **kwargs):
            parsed = await original_parse(*args, **kwargs)
            observed.results.append(parsed)
            return parsed

        coordinator.parse = capture
        observed.runtime = runtime
        return runtime

    with TestClient(create_app(settings, runtime_factory=factory)) as client:
        response = client.post("/v1/content/parse",
            files={"file": ("census-samoa-1930.pdf", pdf, "application/pdf")},
            data={"unit_range": "6", "scan_policy": "auto", "describe_images": "false"})
        assert response.status_code == 200, response.text
        job = response.headers["x-content-id"]
        persisted = client.get(f"/v1/content/jobs/{job}/result")
        assert persisted.status_code == 200 and persisted.content == response.content
        assert client.get(f"/v1/content/jobs/{job}").json()["status"] == "partial"
        [parsed] = observed.results
        ir = parsed.parse_result
        assert ir.status == "partial" and ir.source.source_sha256 == state["source_sha256"]
        [unit] = ir.units
        [page] = parsed.pages
        assert unit.index == page.page_number == 6
        assert unit.status == page.status.value == "failed"
        assert page.warnings[0].code == "glm_sdk_unusable_table_structure"
        assert page.warnings[0].severity.value == "error"
        assert unit.table_ids == [] and ir.tables == [] and parsed._source_regions == []
        assert "structure: unknown" in page.content and "source-page-image:" not in response.text
        assert page.content == unit.renderings.markdown
        assert page.content in ir.renderings.markdown == response.text
        assert "<!-- table-fragment:" not in response.text
        assert unit.diagnostics.quality_verdict == "untrusted"
        [unknown] = [region for region in unit.regions if region.region_type.value == "unknown"]
        assert unknown.quality.value == "conflicted"
        [asset] = client.get(f"/v1/content/jobs/{job}/assets").json()
        assert unknown.asset_ids == unit.asset_ids == [asset["asset_id"]]
        location = ir.assets[0].locations[0]
        assert location.page_number == 6 and location.unit_id == unit.unit_id
        assert location.bbox.model_dump() == {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
        assert f"]({asset['download_url']})" in page.content
        downloaded = client.get(asset["download_url"])
        assert downloaded.status_code == 200 and downloaded.content == png
        assert asset["sha256"] == state["png_sha256"] and ir.assets[0].visual_analysis is None
        assert observed.sdk_calls == 1
        observed.runtime.parser_service.glm_adapter.recognize_image.assert_not_awaited()
        assert not (observed.runtime.storage_service.logs_dir(job) / "glm-sdk").exists()


def test_malformed_neighbor_keeps_usable_regions_through_final_http(tmp_path):
    """Real Census pixels/failure context, with an explicitly synthetic bad region."""
    pdf = (FIXTURE / "source.pdf").read_bytes()
    observed = SimpleNamespace(results=[], posts=0)
    payload = {"layout_details": [[
        {"label": "text", "content": "Usable preceding paragraph."},
        {"label": "table", "bbox_2d": [0, 0, 1000, 200],
         "content": "<table><tr><th>Known</th></tr><tr><td>17</td></tr></table>"},
        {"label": "table", "bbox_2d": [0, 200, 1000, 500],
         "content": "<table><tr><td rowspan='0'>Unverified complete words 42</td></tr></table>"},
        {"label": "text", "content": "Usable following paragraph."},
    ]]}

    async def handler(_request):
        observed.posts += 1
        return httpx.Response(200, json=payload)

    settings = make_test_settings(tmp_path, glm_ocr_enabled=True, glm_sdk_enabled=True,
        glm_sdk_orientation_enabled=False, max_upload_bytes=2_000_000,
        sync_max_bytes=2_000_000, sync_max_units=20)

    def factory(runtime_settings):
        runtime = build_runtime(runtime_settings)
        coordinator = runtime.parser_service
        coordinator.standard_parser = NativeTextFixture()
        coordinator.glm_adapter.recognize_image = AsyncMock(
            side_effect=AssertionError("unknown retention must not add another OCR pass"))
        coordinator.glm_sdk_parser = GlmSdkRemoteParser(
            runtime_settings, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        coordinator.glm_sdk_parser.probe = AsyncMock(return_value=BackendStatus(
            name="glm-sdk-remote", state=BackendState.READY))
        original_parse = coordinator.parse

        async def capture(*args, **kwargs):
            parsed = await original_parse(*args, **kwargs)
            observed.results.append(parsed)
            return parsed

        coordinator.parse = capture
        return runtime

    with TestClient(create_app(settings, runtime_factory=factory)) as client:
        response = client.post("/v1/content/parse",
            files={"file": ("census-source-fixture.pdf", pdf, "application/pdf")},
            data={"unit_range": "6", "scan_policy": "auto", "describe_images": "false"})
        assert response.status_code == 200, response.text
        job = response.headers["x-content-id"]
        assert client.get(f"/v1/content/jobs/{job}/result").content == response.content
        assert client.get(f"/v1/content/jobs/{job}").json()["status"] == "partial"
        assert observed.posts == 1
        assert all(text in response.text for text in (
            "Usable preceding paragraph.", "Usable following paragraph.",
            "Unverified complete words 42", "structure: unknown", "sdk_p6_t1", "17"))
        assert "<table" not in response.text
        [parsed] = observed.results
        assert [table.table_id for table in parsed.parse_result.tables] == ["sdk_p6_t1"]
        assert parsed.pages[0].status == PageStatus.FAILED
        assets = client.get(f"/v1/content/jobs/{job}/assets").json()
        assert assets and f"]({assets[0]['download_url']})" in response.text
