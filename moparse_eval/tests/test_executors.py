"""Synthetic SDK objects only. These tests never read corpus materials."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from pathlib import Path

import pytest

from moparse_eval.adapters import (
    html_cells,
    read_docling,
    read_glm,
    read_mineru,
    read_paddle,
    read_visual,
)
from moparse_eval.executors import PIPELINES, _owned_thread
from moparse_eval.runtime import PreparationError, validate_execution_config


def test_html_spans_keep_empty_source_cells_and_explicit_header_roles() -> None:
    cells = html_cells('<table><tr><th scope="row" rowspan="2">甲</th><th scope="col">期间</th></tr>'
                       '<tr><td></td></tr></table>')
    assert [(c["row"], c["col"], c["row_span"], c["text"]) for c in cells] == [
        (0, 0, 2, "甲"), (0, 1, 1, "期间"), (1, 1, 1, "")]
    assert cells[0]["is_row_header"] is True
    assert cells[1]["is_column_header"] is True
    assert "is_column_header" not in cells[2]


def test_ambiguous_html_does_not_discard_neighboring_glm_regions() -> None:
    raw = {"json_result": [[{"label": "text", "content": "前文"},
                            {"label": "table", "content": "<table><tr><td>断裂"},
                            {"label": "text", "content": "后文"}]]}
    blocks = read_glm(raw, 2)
    assert [b["text"] for b in blocks] == ["前文", "<table><tr><td>断裂", "后文"]
    assert blocks[1]["structure_status"] == "unknown"
    assert "cells" not in blocks[1]
    assert blocks[2]["native_path"] == "#/glm/json_result/0/2"


def test_serialized_glm_layout_pointer_declares_decode() -> None:
    blocks = read_glm({"json_result": json.dumps([[{"label": "text", "content": "１２.3"}]])}, 1)
    assert blocks[0]["text"] == "１２.3"
    assert "::decoded/0/0" in blocks[0]["native_path"]


def test_docling_uses_reading_tree_and_furniture_without_guessing_headers() -> None:
    raw = {"document": {"body": {"children": [{"$ref": "#/texts/1"}, {"$ref": "#/tables/0"},
                                              {"$ref": "#/texts/0"}]},
            "furniture": {"children": [{"$ref": "#/texts/2"}]},
            "texts": [{"text": "后段", "label": "text", "prov": [{"page_no": 3}]},
                      {"text": "前段", "label": "text", "prov": [{"page_no": 3}]},
                      {"text": "页脚", "label": "page_footer", "prov": [{"page_no": 3}]}],
            "tables": [{"label": "table", "prov": [{"page_no": 3}], "data": {"table_cells": [
                {"text": "首行仍是数据", "start_row_offset_idx": 0, "start_col_offset_idx": 0,
                 "row_span": 1, "col_span": 2, "column_header": False}]}}]}}
    blocks = read_docling(raw, 3)
    assert [b["text"] for b in blocks] == ["前段", "", "后段", "页脚"]
    assert blocks[1]["cells"][0]["is_column_header"] is False
    assert blocks[0]["native_path"] == "#/docling/document/texts/1"


def test_visual_reader_never_fills_blank_image_content_or_infers_relations() -> None:
    raw = [{"type": "image", "bbox": [0.1, 0.2, 0.4, 0.5], "content": None},
           {"type": "table", "bbox": [0.1, 0.5, 0.8, 0.9],
            "content": "<table><tr><td>-0.25%</td></tr></table>"}]
    blocks = read_visual(raw, 4)
    assert blocks[0]["text"] == ""
    assert blocks[1]["cells"][0]["text"] == "-0.25%"
    assert blocks[0]["coordinate_system"] == "normalized"
    assert blocks[0]["coordinate_origin"] == "TOPLEFT"
    assert not any("header_path" in key for block in blocks for key in block)


def test_paddle_wrapper_retains_native_order_and_grid() -> None:
    blocks = read_paddle({"res": {"parsing_res_list": [
        {"block_label": "footer", "block_content": "页脚", "block_bbox": [0, 50, 30, 60]},
        {"block_label": "table", "block_content": "<table><tr><td>A</td></tr></table>"}]}}, 2)
    assert blocks[0]["text"] == "页脚"
    assert blocks[1]["cells"][0]["col"] == 0
    assert blocks[0]["native_path"].startswith("#/paddle/res/")


def test_mineru_container_export_preserves_captions_and_html() -> None:
    raw = {"blocks": [{"type": "table", "content": [
        {"type": "table_caption", "content": [{"type": "text", "content": "题"}]},
        {"type": "table_body", "content": "<table><tr><td>8</td></tr></table>"},
        {"type": "table_footnote", "content": [{"type": "text", "content": "注"}]}],
        "markdown": "题\n\n|8|\n|---|\n\n注"}]}
    blocks = read_mineru(raw, 1)
    assert [block["kind"] for block in blocks] == ["table_caption", "table_body", "table_footnote"]
    assert blocks[1]["cells"][0]["text"] == "8"
    assert blocks[0]["text"] == "题" and blocks[2]["text"] == "注"
    assert blocks[1]["cells"][0]["native_path"].startswith("#/mineru/blocks/0/content/1/content::html")


@pytest.mark.parametrize("override", [
    {"pipeline": "P09"}, {"expected": "forbidden.json"}, {"reference": {}},
    {"resources": {"gpu_device": "0"}}, {"resources": {"client_concurrency": 5}},
    {"resources": {"gpu_memory_gib": 21}}, {"retry_max_attempts": 1}, {"dpi": 300},
])
def test_config_rejects_oracle_inputs_and_resource_or_retry_drift(override: dict) -> None:
    with pytest.raises(PreparationError):
        validate_execution_config({"pipeline": "P01", **override})


def test_all_eight_specs_select_real_distinct_configurations() -> None:
    assert set(PIPELINES) == {f"P{i:02}" for i in range(1, 9)}
    assert PIPELINES["P01"]["tableformer"] != PIPELINES["P02"]["tableformer"]
    assert PIPELINES["P06"]["tier"] == "standard"
    assert PIPELINES["P07"]["tier"] == "advanced"
    assert PIPELINES["P03"]["model_version"] == "1.5"
    assert PIPELINES["P04"]["model_version"] == "1.6"
    assert PIPELINES["P08"]["hybrid"] is False


@pytest.mark.asyncio
async def test_cancellation_keeps_original_thread_owned_until_completion() -> None:
    finished = []
    def work() -> str:
        time.sleep(0.03)
        finished.append(True)
        return "original-response"
    task = asyncio.create_task(_owned_thread(work))
    await asyncio.sleep(0.005)
    task.cancel()
    result = await task
    assert result == "original-response" and finished == [True]


@pytest.mark.asyncio
async def test_persistent_batch_keeps_warmup_models_resident(monkeypatch, tmp_path: Path) -> None:
    import moparse_eval.executors as executors
    events = []
    class SDK:
        initialization_seconds = 1.25
        def __init__(self, config):
            self.state = 0
        async def initialize(self):
            events.append("initialize")
        async def close(self):
            events.append("close")
    async def case(pdf_path, config, *, sample_id, output_dir, _sdks):
        _sdks.state += 1
        events.append((sample_id, _sdks.state, config["warmup"]))
        output_dir.mkdir(parents=True)
        return {"sample_id": sample_id, "status": "completed", "timing": {"processing_seconds": 0.5}}
    monkeypatch.setattr(executors, "_SDKs", SDK)
    monkeypatch.setattr(executors, "execute_in_worker", case)
    result = await executors.execute_batch_in_worker([
        {"sample_id": "warm", "pdf_path": "unused.pdf", "output_dir": str(tmp_path / "warm"), "phase": "warmup", "input_page_count": 1},
        {"sample_id": "measure", "pdf_path": "unused.pdf", "output_dir": str(tmp_path / "measure"), "phase": "quality", "input_page_count": 1},
    ], {"pipeline": "P05", "timeout_policy": {"frozen": True, "single_page_seconds": 1.0}}, output_dir=tmp_path)
    assert events == ["initialize", ("warm", 1, True), ("measure", 2, False), "close"]
    assert [r["timing"]["processing_seconds"] for r in result] == [0.5, 0.5]


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["P05", "P06"])
async def test_worker_mounts_inputs_without_gold_or_whole_repository(monkeypatch, tmp_path: Path, pipeline: str) -> None:
    from types import SimpleNamespace

    import moparse_eval.maintenance as maintenance
    import moparse_eval.runtime as runtime
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    pdf = inputs / "synthetic.pdf"
    pdf.write_bytes(b"synthetic job path, never parsed")
    output = tmp_path / "output"
    commands = []
    class Process:
        async def wait(self):
            (output / "batch-observations.json").write_text(json.dumps([
                {"sample_id": "synthetic", "status": "completed", "timing": {}}]))
            return 0
    async def start(*command, **kwargs):
        commands.append(command)
        return Process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    async def confirmed(name):
        return None
    monkeypatch.setattr(runtime, "_confirm_worker_exit", confirmed)
    class Sampler:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            pass
        async def close(self):
            return {}
    monkeypatch.setattr(maintenance, "ContainerSampler", Sampler)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    config = {"pipeline": pipeline, "runtime": {"kind": "docker", "image": "synthetic-image"}}
    if pipeline == "P06":
        config["models"] = {"mineru_small_path": "/models/mineru-small"}
        config["runtime"]["mounts"] = {str(tmp_path / "weights"): "/models/mineru-small"}
    await runtime.run_batch_worker([{"sample_id": "synthetic", "pdf_path": str(pdf)}], config,
        output_dir=output, inputs_dir=inputs)
    command = commands[0]
    mounts = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "--mount"]
    assert any("dst=/research/moparse_eval," in mount for mount in mounts)
    assert any("dst=/input," in mount for mount in mounts)
    assert not any("dst=/research," in mount or "expected" in mount or "references" in mount for mount in mounts)
    if pipeline == "P06":
        assert command[command.index("--tmpfs") + 1] == "/models/mineru-small/models/.locks:rw,noexec,nosuid,size=16m"
        assert any("dst=/models/mineru-small,readonly" in mount for mount in mounts)
    job = json.loads(next(output.glob(".job-*.json")).read_text())
    assert job["samples"][0]["pdf_path"] == "/input/synthetic.pdf"


def test_native_paddle_rpc_preserves_raw_markup_and_real_media_without_retry() -> None:
    from http.server import ThreadingHTTPServer
    from types import SimpleNamespace

    from PIL import Image

    from moparse_eval.executors import _Assets, _paddle_page
    from moparse_eval.paddle_server import handler
    calls = []
    class Inference:
        requests = {}
        def parse(self, request):
            calls.append(request)
            assert base64.b64decode(request["image_base64"]).startswith(b"\x89PNG")
            return {"request_id": request["request_id"],
                "raw": {"res": {"parsing_res_list": [{"block_label": "table",
                    "block_content": "<table><tr><td>-0.5%</td></tr></table>"}]}},
                "faithful_markdown": "![](assets/native.png)\n\n-0.5%",
                "media": {"assets/native.png": base64.b64encode(b"retained-image-bytes").decode()},
                "inference_runtime": {"native_processing_seconds": 0.25, "cuda_graph_evidence": []}}
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(Inference(), "synthetic-native"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sdk = SimpleNamespace(config={"paddle_backend": "native-rpc", "timeout_seconds": 5},
            paddle=f"http://127.0.0.1:{server.server_address[1]}")
        assets = _Assets()
        raw, markdown = _paddle_page(sdk, {"page": 7, "image": Image.new("RGB", (4, 4))}, assets)
        assert len(calls) == 1 and calls[0]["page"] == 7
        assert raw["res"]["parsing_res_list"][0]["block_content"].endswith("</table>")
        assert "-0.5%" in markdown and assets.data["assets/native.png"] == b"retained-image-bytes"
        assert raw["research_inference_runtime"]["native_processing_seconds"] == 0.25
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_native_paddle_server_command_separates_cpu_worker_and_inference_budget(tmp_path: Path) -> None:
    from moparse_eval.maintenance import native_paddle_command
    command = native_paddle_command({"port": 12543, "inference_image": "synthetic-image",
        "model_mounts": {str(tmp_path / "weights"): "/models/paddle-vlm"}},
        tmp_path / "software-config.json", "moparse-eval-synthetic")
    assert command[command.index("--cpus") + 1] == "4"
    assert command[command.index("--memory") + 1] == "20g"
    assert command[command.index("--gpus") + 1] == "device=1"
    assert "moparse_eval.paddle_server" in command
    assert not any("references" in item or "pdf_sample" in item for item in command)
