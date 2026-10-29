"""Controlled software/native structures only; no corpus material is opened."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from moparse_eval.adapters import read_docling, read_glm, read_mineru
from moparse_eval.executors import _SDKs
from moparse_eval.request_control import RequestControl, RequestStopped, sample_timeout
from moparse_eval.runtime import PreparationError


def test_html_source_identity_and_superscript_are_preserved_without_gold() -> None:
    blocks = read_glm({"json_result": [[
        {"label": "table", "content": "<table><tr><td>150.1<sup>4</sup></td></tr></table>"},
        {"label": "table", "content": "<table><tr><td>150.14</td></tr></table>"}]]}, 1)
    left, right = [block["cells"][0] for block in blocks]
    assert left["text"] == right["text"] == "150.14"
    assert left["id"] != right["id"]
    assert left["native_path"].startswith(blocks[0]["native_path"] + "/content::html")
    assert left["inline_annotations"][0]["span"] == [5, 6]
    assert left["inline_annotations"][0]["text"] == "4"
    assert left["inline_annotations"][0]["type"] == "superscript"
    assert "inline_annotations" not in right and left["text_format"] == "plain"


def spanning_document() -> dict:
    return {"research_group_pages": [1, 2], "document": {
        "pages": {"1": {"size": {"width": 500, "height": 700}},
                  "2": {"size": {"width": 600, "height": 800}}},
        "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/groups/0"}]},
        "groups": [{"self_ref": "#/groups/0", "label": "list", "parent": {"$ref": "#/body"},
                    "children": [{"$ref": "#/tables/0"}, {"$ref": "#/tables/1"}]}],
        "texts": [{"self_ref": "#/texts/0", "text": "native page two appears first in tree", "label": "text",
                   "prov": [{"page_no": 2, "bbox": {"l": 1, "t": 10, "r": 30, "b": 2, "coord_origin": "BOTTOMLEFT"}}]}],
        "tables": [{"self_ref": "#/tables/0", "parent": {"$ref": "#/groups/0"}, "label": "table",
                    "prov": [{"page_no": 1}, {"page_no": 2}], "data": {"table_cells": [
                        {"text": "cross-page logical cell", "start_row_offset_idx": 0, "start_col_offset_idx": 0,
                         "bbox": {"l": 1, "t": 2, "r": 3, "b": 4, "coord_origin": "TOPLEFT"}}]}},
                   {"self_ref": "#/tables/1", "label": "table", "prov": [{"page_no": 1}],
                    "data": {"table_cells": [{"text": "other", "start_row_offset_idx": 0,
                                               "start_col_offset_idx": 0}]}}]}}


def test_docling_cross_page_objects_once_with_real_hierarchy_and_tree_sequence() -> None:
    emitted, containers = set(), []
    raw = spanning_document()
    first = read_docling(raw, 1, "#/documents/0", emitted=emitted, containers=containers)
    second = read_docling(raw, 2, "#/documents/0", emitted=emitted, containers=containers)
    assert len(first) == 2 and len(second) == 1
    assert first[0]["provenance_pages"] == [1, 2]
    assert first[0]["parent_id"] == "#/documents/0/document/groups/0"
    assert first[0]["cells"][0]["id"] != first[1]["cells"][0]["id"]
    assert first[0]["cells"][0]["page"] is None
    assert first[0]["cells"][0]["coordinate_origin"] == "TOPLEFT"
    assert first[0]["provenance"][1]["page_dimensions"]["width"] == 600
    assert second[0]["page_dimensions"]["width"] == 600
    assert second[0]["native_sequence"] < first[0]["native_sequence"]
    group = next(value for value in containers if value.get("self_ref") == "#/groups/0")
    assert group["label"] == "list" and group["parent_id"] == "#/documents/0/document/body"
    assert group["native_children"][0] == first[0]["id"]


def test_mineru_typed_inline_styles_and_native_table_are_read_separately() -> None:
    blocks = read_mineru({"blocks": [{"type": "text", "content": [
        {"type": "text", "content": "150.1"},
        {"type": "text", "content": "4", "styles": ["superscript"]},
        {"type": "hyperlink", "url": "#note", "content": [{"type": "text", "content": "ref"}]}]}]}, 3)
    assert blocks[0]["text"] == "150.14ref"
    assert blocks[0]["text_format"] == "plain"
    assert blocks[0]["inline_annotations"][0]["span"] == [5, 6]
    assert blocks[0]["inline_annotations"][1]["target"] == "#note"


def test_docling_exports_each_native_group_once_including_furniture() -> None:
    from docling_core.types.doc import ContentLayer

    from moparse_eval.executors import _Assets, _docling_run
    calls = []
    class Document:
        pictures = []
        def export_to_dict(self):
            return {}
        def export_to_markdown(self, **kwargs):
            calls.append(kwargs)
            assert "page_no" not in kwargs
            assert kwargs["included_content_layers"] == set(ContentLayer)
            return "body and native footer"
    conversion = SimpleNamespace(document=Document(), status="success", errors=[])
    sdk = SimpleNamespace(docling=SimpleNamespace(convert=lambda *args, **kwargs: conversion),
                          control=SimpleNamespace(check=lambda: None))
    output = _docling_run(sdk, Path("unused.pdf"), [
        {"page": n, "source_prediction": "mixed" if n == 3 else "native"} for n in range(1, 5)], _Assets())
    assert len(calls) == 2
    assert output[1][1] == output[4][1] == "body and native footer" and output[2][1] == ""
    assert output[1][0] is output[2][0]


def test_formal_deadline_uses_direct_single_page_measurement_and_input_pages() -> None:
    with pytest.raises(PreparationError):
        sample_timeout({}, {"suite": "quality800", "input_page_count": 2})
    policy = {"timeout_policy": {"frozen": True, "single_page_seconds": 80}}
    assert sample_timeout(policy, {"input_page_count": 2}) == 480
    assert sample_timeout(policy, {"input_page_count": 1}) == 300
    assert sample_timeout(policy, {"input_page_count": 100}) == 3600


def test_received_http_failure_closes_admission_without_retry() -> None:
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(500)
    control = RequestControl({"endpoints": {"glm": "http://synthetic.local/v1/chat/completions"}})
    control.install()
    try:
        control.start(time.perf_counter() + 20)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            assert client.post("http://synthetic.local/v1/chat/completions").status_code == 500
            with pytest.raises(RequestStopped):
                client.post("http://synthetic.local/v1/chat/completions")
        assert len(calls) == 1 and control.events[0]["received_response"]
    finally:
        control.close()


def test_transport_unknown_remains_owned_across_samples_without_retry() -> None:
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadError("synthetic lost response")
    control = RequestControl({"endpoints": {"mineru": "http://synthetic.local/v1"}})
    control.install()
    try:
        control.start(time.perf_counter() + 20)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(httpx.ReadError):
                client.post("http://synthetic.local/v1/chat/completions")
            with pytest.raises(RequestStopped):
                client.post("http://synthetic.local/v1/chat/completions")
        with pytest.raises(RequestStopped):
            control.start(time.perf_counter() + 20)
        assert len(calls) == 1 and control.unknown
    finally:
        control.close()


def test_glm_retains_raw_stage_footer_and_official_media_as_independent_views() -> None:
    from PIL import Image

    from moparse_eval.executors import _Assets, _glm_page
    result = SimpleNamespace(json_result=[[{"index": 0, "label": "text", "content": "body"},
        {"index": 1, "label": "image", "content": "", "image_path": "imgs/official.jpg"}]],
        raw_json_result=[[{"index": 0, "label": "text", "content": "body"},
            {"index": 1, "label": "footer", "content": "native footer"}]],
        original_images=[], markdown_result="body\n\n![](imgs/official.jpg)",
        image_files={"official.jpg": Image.new("RGB", (2, 2))})
    sdk = SimpleNamespace(glm=SimpleNamespace(process=lambda request: [result]))
    assets = _Assets()
    raw, faithful = _glm_page(sdk, {"page": 1, "image": Image.new("RGB", (2, 2))}, assets)
    assert "native footer" in faithful
    assert "cross_view_order=unknown" in faithful
    assert raw["json_result"] == result.json_result
    assert raw["raw_json_result"] == result.raw_json_result
    assert raw["research_raw_stage_markdown"] == "body\n\nnative footer"
    assert "![](assets/" in faithful and len(assets.data) == 1


@pytest.mark.asyncio
async def test_issued_request_returns_late_and_blocks_only_new_work() -> None:
    async def handler(request):
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={"native": "late result"})
    control = RequestControl({"endpoints": {"glm": "http://synthetic.local/v1/chat/completions"}})
    control.install()
    try:
        control.start(time.perf_counter() + 0.005)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await client.post("http://synthetic.local/v1/chat/completions")
            assert result.json()["native"] == "late result"
            with pytest.raises(RequestStopped):
                await client.post("http://synthetic.local/v1/chat/completions")
        assert control.stopped() == "timed_out" and not control.unknown
    finally:
        control.close()


@pytest.mark.asyncio
async def test_late_whole_docling_result_is_saved_instead_of_discarded(monkeypatch, tmp_path: Path) -> None:
    import moparse_eval.executors as module
    async def preprocess(*args):
        return Path("unused-oriented.pdf"), [{"page": 1, "source_prediction": "native", "width": 100, "height": 100}]
    def parse(sdk, path, pages, assets, output):
        time.sleep(0.02)
        output[1] = ({"research_group_pages": [1], "document": {
            "body": {"children": [{"$ref": "#/texts/0"}]}, "texts": [
                {"label": "text", "text": "late native", "prov": [{"page_no": 1}]}]}}, "late faithful")
    monkeypatch.setattr(module, "_preprocess", preprocess)
    monkeypatch.setattr(module, "_docling_run", parse)
    sdk = SimpleNamespace(spec={"family": "docling", "hybrid": True}, initialization_seconds=0,
                          control=RequestControl({}), graph_evidence=[])
    result = await module.execute_in_worker(Path("unused.pdf"), {"pipeline": "P01", "timeout_seconds": 0.005},
        sample_id="synthetic", output_dir=tmp_path, _sdks=sdk)
    assert result["status"] == "timed_out" and result["pages"][0]["status"] == "late"
    assert result["pages"][0]["blocks"][0]["text"] == "late native"
    assert (tmp_path / "faithful.md").read_text() == "late faithful"
    assert json.loads((tmp_path / "native.json").read_text())["documents"][0]["document"]["texts"]


@pytest.mark.asyncio
async def test_native_unknown_stops_earlier_glm_page_from_starting(monkeypatch, tmp_path: Path) -> None:
    import moparse_eval.executors as module
    async def preprocess(*args):
        return Path("unused.pdf"), [{"page": n, "source_prediction": "mixed" if n == 1 else "native",
                                    "width": 100, "height": 100} for n in (1, 2)]
    async def parse(*args):
        raise httpx.ReadError("synthetic transport lost response")
    def forbidden(*args):
        pytest.fail("GLM must not start after another backend's execution became unknown")
    monkeypatch.setattr(module, "_preprocess", preprocess)
    monkeypatch.setattr(module, "_mineru_run", parse)
    monkeypatch.setattr(module, "_glm_page", forbidden)
    sdk = SimpleNamespace(spec={"family": "mineru", "hybrid": True}, initialization_seconds=0,
                          control=RequestControl({}), graph_evidence=[])
    result = await module.execute_in_worker(Path("unused.pdf"), {"pipeline": "P06"},
        sample_id="synthetic", output_dir=tmp_path, _sdks=sdk)
    assert result["status"] == "execution_unknown"
    assert [page["status"] for page in result["pages"]] == ["not_processed", "execution_unknown"]


def test_glm_loads_full_official_configuration_without_environment(monkeypatch, tmp_path: Path) -> None:
    import moparse_eval.executors as module
    calls = []
    config = SimpleNamespace(maas=SimpleNamespace(enabled=True), max_workers=32,
        ocr_api=SimpleNamespace(), layout=SimpleNamespace(label_task_mapping={"skip": ["image"]}),
        page_loader=SimpleNamespace(max_pixels=71372800), result_formatter=SimpleNamespace())
    class Root:
        @classmethod
        def from_yaml(cls):
            calls.append("official_yaml")
            return SimpleNamespace(pipeline=config)
    monkeypatch.setitem(sys.modules, "glmocr.config", SimpleNamespace(GlmOcrConfig=Root))
    monkeypatch.setitem(sys.modules, "glmocr", SimpleNamespace(Pipeline=lambda cfg:
        SimpleNamespace(layout_detector=SimpleNamespace(start=lambda: calls.append("layout")))))
    monkeypatch.setattr(module, "_version", lambda *args: None)
    monkeypatch.setattr(module, "_required_model", lambda *args: tmp_path)
    sdk = _SDKs({"pipeline": "P05", "endpoints": {"glm": "http://synthetic.local/v1"}})
    sdk._init_glm()
    assert calls == ["official_yaml", "layout"]
    assert config.layout.label_task_mapping == {"skip": ["image"]}
    assert config.page_loader.max_pixels == 71372800
    assert config.ocr_api.retry_max_attempts == 0 and not config.maas.enabled


def test_glm_declared_decoder_override_reaches_sdk_without_changing_prompt_or_pixel_budget(monkeypatch, tmp_path: Path) -> None:
    from pydantic import BaseModel

    import moparse_eval.executors as module

    class Loader(BaseModel):
        max_tokens: int = 8192
        repetition_penalty: float = 1.1
        pdf_dpi: int = 200
        max_pixels: int = 71372800
        task_prompt_mapping: dict[str, str] = {"table": "Synthetic table prompt"}

    original_loader = Loader()
    config = SimpleNamespace(maas=SimpleNamespace(enabled=True), max_workers=32,
        ocr_api=SimpleNamespace(), layout=SimpleNamespace(),
        page_loader=original_loader, result_formatter=SimpleNamespace())
    captured = []

    class Root:
        @classmethod
        def from_yaml(cls):
            return SimpleNamespace(pipeline=config)

    def pipeline(cfg):
        captured.append(cfg)
        return SimpleNamespace(layout_detector=SimpleNamespace(start=lambda: None))

    monkeypatch.setitem(sys.modules, "glmocr.config", SimpleNamespace(GlmOcrConfig=Root))
    monkeypatch.setitem(sys.modules, "glmocr", SimpleNamespace(Pipeline=pipeline))
    monkeypatch.setattr(module, "_version", lambda *args: None)
    monkeypatch.setattr(module, "_required_model", lambda *args: tmp_path)
    sdk = _SDKs({"pipeline": "P05", "endpoints": {"glm": "http://synthetic.local/v1"},
        "glm_page_loader": {"repetition_penalty": 1.05}})
    sdk._init_glm()
    assert len(captured) == 1
    assert captured[0].page_loader.repetition_penalty == 1.05
    assert captured[0].page_loader.max_tokens == original_loader.max_tokens
    assert captured[0].page_loader.max_pixels == original_loader.max_pixels
    assert captured[0].page_loader.task_prompt_mapping == original_loader.task_prompt_mapping
    assert original_loader.repetition_penalty == 1.1
    assert config.ocr_api.retry_max_attempts == 0


def test_glm_page_telemetry_preserves_native_results_and_captures_original_region_response(tmp_path: Path) -> None:
    import requests
    from PIL import Image

    from moparse_eval.executors import _Assets, _glm_page

    reply = requests.Response()
    reply.status_code = 200
    reply._content = json.dumps({"choices": [{"message": {"content": "native region"},
        "finish_reason": "length", "stop_reason": 8192}], "usage": {"completion_tokens": 8192}}).encode()
    calls = []

    class Session:
        def post(self, *args, **kwargs):
            calls.append(kwargs)
            return reply

    class Client:
        _session = Session()
        api_key = "synthetic-observer-secret"
        extra_headers = {}

        def _make_session(self):
            raise AssertionError("already initialized client must retain its session")

    client = Client()

    def process(request):
        request["messages"][0]["content"].append({"type": "text", "text": "Synthetic table prompt"})
        request.update(max_tokens=8192, repetition_penalty=1.05)
        response = client._session.post("http://synthetic.local/v1", data=json.dumps(request),
            headers={"Authorization": "Bearer synthetic-observer-secret"})
        content = response.json()["choices"][0]["message"]["content"]
        return [SimpleNamespace(json_result=[[{"label": "text", "content": content}]],
            markdown_result=content, raw_json_result=None, original_images=[], image_files={})]

    sdk = SimpleNamespace(glm=SimpleNamespace(ocr_client=client, process=process,
        config=SimpleNamespace(page_loader=SimpleNamespace(task_prompt_mapping={"table": "Synthetic table prompt"}))))
    page = {"page": 2, "image": Image.new("RGB", (2, 2))}
    native_without, markdown_without = _glm_page(sdk, page, _Assets())
    directory = tmp_path / "telemetry" / "p0002-glm"
    native_observed, markdown_observed = _glm_page(sdk, page, _Assets(), directory)
    assert native_without == native_observed
    assert markdown_without == markdown_observed == "native region"
    assert len(calls) == 2
    index = json.loads((directory / "index.json").read_text())
    assert index["page_number"] == 2 and index["recording_errors"] == []
    assert len(index["records"]) == 1
    record = index["records"][0]
    assert record["task_candidates_from_exact_prompt"] == ["table"]
    assert record["choice_termination"][0]["finish_reason"] == "length"
    assert record["usage"]["completion_tokens"] == 8192
    assert json.loads((directory / record["request_file"]).read_text())["repetition_penalty"] == 1.05
    assert json.loads((directory / record["response_file"]).read_text()) == reply.json()


def test_paddle_overrides_only_unsupported_layout_attention(monkeypatch, tmp_path: Path) -> None:
    import moparse_eval.cuda_graphs as graphs
    import moparse_eval.executors as module
    import moparse_eval.paddle_compat as compat
    captured = {}
    official = {"SubModules": {"LayoutDetection": {"model_name": "PP-DocLayoutV3"}}}
    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCRVL=lambda **kwargs: captured.update(kwargs)))
    monkeypatch.setitem(sys.modules, "paddlex.inference", SimpleNamespace(load_pipeline_config=lambda name: official))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True,
        set_per_process_memory_fraction=lambda *args: None,
        get_device_properties=lambda index: SimpleNamespace(total_memory=22 * 1024 ** 3))))
    monkeypatch.setattr(module, "_version", lambda *args: None)
    monkeypatch.setattr(module, "_required_model", lambda *args: tmp_path)
    monkeypatch.setattr(graphs, "install_paddle_trials", lambda evidence, **kwargs: None)
    monkeypatch.setattr(compat, "install_paddle_compat", lambda **kwargs: SimpleNamespace())
    sdk = _SDKs({"pipeline": "P03"})
    sdk._init_paddle()
    assert captured["vl_rec_model_name"] == "PaddleOCR-VL-1.5-0.9B"
    assert captured["engine_config"]["attn_implementation"] == "sdpa"
    assert captured["paddlex_config"]["SubModules"]["LayoutDetection"]["engine_config"]["attn_implementation"] is None
    assert "engine_config" not in official["SubModules"]["LayoutDetection"]
