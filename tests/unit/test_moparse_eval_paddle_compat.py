"""Synthetic pixels and token fixtures, with no model or corpus access."""

from __future__ import annotations

import base64
import io
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from moparse_eval.paddle_compat import (
    SUPPORTED_VERSIONS,
    install_paddle_compat,
    region_bgr_to_pil,
)


class Tokens:
    def __init__(self, rows):
        self.rows = rows
        self.shape = (len(rows), len(rows[0]))
        self.host_copies = 0

    def detach(self):
        return self

    def cpu(self):
        self.host_copies += 1
        return self

    def tolist(self):
        return self.rows


def predictor_fixture(*, model="PaddleOCR-VL-1.5-0.9B", failure=None):
    class Base:
        def generate(self, model_inputs, generate_kwargs):
            self.calls.append((model_inputs, generate_kwargs))
            if failure == "generate":
                raise self.failure
            return self.outputs

    class Predictor(Base):
        def __init__(self):
            self.model_name = model
            self.calls = []
            self.images = []
            self.failure = RuntimeError("original synthetic failure")
            self.outputs = Tokens([[10, 11, 7, 2], [10, 11, 2, 0]])
            self.infer = SimpleNamespace(generation_config=SimpleNamespace(
                to_dict=lambda: {"eos_token_id": [2, 3], "pad_token_id": 0,
                                 "max_new_tokens": 99, "do_sample": False}))

        def process(self, data, max_new_tokens=None, skip_special_tokens=None, **kwargs):
            self.images = [item["image"] for item in data]
            if failure == "preprocess":
                raise self.failure
            model_inputs = {"input_ids": np.array([[10, 11], [10, 11]])}
            generated = self.generate(model_inputs, {"max_new_tokens": max_new_tokens,
                                                    "use_cache": True, **kwargs})
            return self.postprocess(generated, model_inputs=model_inputs,
                                    skip_special_tokens=skip_special_tokens)

        def postprocess(self, outputs, *, model_inputs, skip_special_tokens, **kwargs):
            if failure == "postprocess":
                raise self.failure
            self.decoded_output_identity = outputs
            return ["synthetic", "fixture"]

    return Base, Predictor


def inputs():
    return [{"image": np.array([[[0, 0, 255], [255, 0, 0]]], dtype=np.uint8),
             "query": "OCR:"},
            {"image": np.array([[[0, 255, 0], [127, 127, 127]]], dtype=np.uint8),
             "query": "Table Recognition:"}]


@pytest.mark.parametrize("channels", [3, 4])
def test_bgr_region_swap_preserves_shape_and_input(channels):
    bgr = np.zeros((2, 3, channels), dtype=np.uint8)
    bgr[..., 0], bgr[..., 2] = 11, 233
    before = bgr.copy()
    result = region_bgr_to_pil(bgr)
    assert result.mode == "RGB" and result.size == (3, 2)
    assert np.asarray(result)[0, 0].tolist() == [233, 0, 11]
    np.testing.assert_array_equal(bgr, before)


def test_pil_is_not_double_converted_and_grayscale_stays_gray():
    image = Image.new("RGB", (3, 2), (31, 59, 79))
    assert region_bgr_to_pil(image) is image
    gray = region_bgr_to_pil(np.array([[7, 29]], dtype=np.uint8))
    assert np.asarray(gray).tolist() == [[[7, 7, 7], [29, 29, 29]]]
    assert region_bgr_to_pil("synthetic.png") == "synthetic.png"


@pytest.mark.parametrize("shape", [(1, 2, 1), (1, 2, 5), (1,), (1, 2, 3, 4)])
def test_unsupported_array_shapes_fail_clearly(shape):
    with pytest.raises(ValueError, match="region must be"):
        region_bgr_to_pil(np.zeros(shape, dtype=np.uint8))


@pytest.mark.parametrize("version", ["1.5", "1.6"])
@pytest.mark.parametrize("query", ["OCR:", "Table Recognition:", "Formula Recognition:"])
def test_all_native_region_categories_convert_without_modifying_layout_data(version, query):
    _, cls = predictor_fixture(model=f"PaddleOCR-VL-{version}-0.9B")
    collector = install_paddle_compat(versions=SUPPORTED_VERSIONS, predictor_class=cls)
    predictor = cls()
    data = inputs()
    data[0]["query"] = query
    original_image = data[0]["image"]
    collector.begin_page(7, "synthetic")
    result = predictor.process(data)
    assert result == ["synthetic", "fixture"]
    assert predictor.decoded_output_identity is predictor.outputs
    assert data[0]["image"] is original_image
    assert original_image[0, 0].tolist() == [0, 0, 255]
    assert isinstance(predictor.images[0], Image.Image)
    assert np.asarray(predictor.images[0])[0, 0].tolist() == [255, 0, 0]
    assert predictor.calls[0][1] == {"max_new_tokens": 4096, "use_cache": True}
    assert predictor.outputs.host_copies == 0
    observations = collector.finish_page()
    assert predictor.outputs.host_copies == 1
    batch = observations["batches"][0]
    generation = batch["generations"][0]
    assert batch["regions"][0]["query"] == query
    assert generation["decoded_characters_after_prompt_trim"] == [9, 7]
    assert generation["effective_generation_parameters"]["max_new_tokens"] == 4096
    assert generation["regions"][0]["prompt_tokens_removed"] == 2
    assert generation["regions"][0]["generated_tokens_after_prompt_trim"] == 2
    assert generation["regions"][0]["eos_token_observed"] is True
    assert generation["regions"][1]["padding_after_first_eos_tokens"] == 1
    assert generation["regions"][0]["stop_reason"] == "unknown"
    assert all(not key.startswith("_") for key in generation)
    assert collector.finish_page()["batches"] == []


def test_length_limit_does_not_invent_eos_or_claim_certain_content_truncation():
    _, cls = predictor_fixture()
    collector = install_paddle_compat(versions=SUPPORTED_VERSIONS, predictor_class=cls)
    predictor = cls()
    predictor.outputs = Tokens([[10, 11] + [17] * 4096, [10, 11] + [17] * 4096])
    predictor.process(inputs())
    generation = collector.finish_page()["batches"][0]["generations"][0]
    first = generation["regions"][0]
    assert first["length_limit_reached"] is True
    assert first["eos_token_observed"] is False
    assert first["possible_length_truncation"] is True
    assert first["stop_reason"] == "unknown"


def test_unknown_eos_config_remains_unknown():
    _, cls = predictor_fixture()
    collector = install_paddle_compat(versions=SUPPORTED_VERSIONS, predictor_class=cls)
    predictor = cls()
    predictor.infer.generation_config = None
    predictor.process(inputs())
    first = collector.finish_page()["batches"][0]["generations"][0]["regions"][0]
    assert first["eos_token_observed"] is None
    assert first["possible_length_truncation"] is None


@pytest.mark.parametrize("failure", ["preprocess", "generate", "postprocess"])
def test_original_failures_keep_identity_and_are_not_retried(failure):
    _, cls = predictor_fixture(failure=failure)
    collector = install_paddle_compat(versions=SUPPORTED_VERSIONS, predictor_class=cls)
    predictor = cls()
    with pytest.raises(RuntimeError) as caught:
        predictor.process(inputs())
    assert caught.value is predictor.failure
    assert len(predictor.calls) == (0 if failure == "preprocess" else 1)
    batch = collector.finish_page()["batches"][0]
    assert batch["status"] == "failed" and batch["error_type"] == "RuntimeError"


def test_later_base_graph_admission_patch_is_still_called():
    base, cls = predictor_fixture()
    collector = install_paddle_compat(versions=SUPPORTED_VERSIONS, predictor_class=cls)
    original = base.generate
    calls = []

    def graph_hook(instance, model_inputs, kwargs):
        calls.append("base graph admission remains active")
        return original(instance, model_inputs, kwargs)

    base.generate = graph_hook
    cls().process(inputs())
    assert len(calls) == 1
    assert len(collector.finish_page()["batches"][0]["generations"]) == 1


def test_install_is_idempotent_and_uses_new_collector_without_double_swap():
    _, cls = predictor_fixture()
    old = install_paddle_compat(versions=SUPPORTED_VERSIONS, predictor_class=cls)
    current = install_paddle_compat(versions=SUPPORTED_VERSIONS, predictor_class=cls)
    predictor = cls()
    predictor.process(inputs())
    assert old.finish_page()["batches"] == []
    assert len(current.finish_page()["batches"]) == 1
    assert np.asarray(predictor.images[0])[0, 0].tolist() == [255, 0, 0]


@pytest.mark.parametrize("config", [
    {"paddle_max_new_tokens": 8192}, {"paddle_color_policy": "unknown"},
    {"paddle_generation_observation": False},
])
def test_incompatible_declared_config_fails_before_patching(config):
    _, cls = predictor_fixture()
    with pytest.raises(ValueError, match="Paddle native"):
        install_paddle_compat(config=config, versions=SUPPORTED_VERSIONS, predictor_class=cls)
    assert "_moparse_paddle_compat" not in cls.__dict__


def test_incompatible_software_version_is_not_silently_patched():
    _, cls = predictor_fixture()
    with pytest.raises(ValueError, match="compatibility requires"):
        install_paddle_compat(versions={**SUPPORTED_VERSIONS, "paddlex": "3.8.0"},
                              predictor_class=cls)
    assert "_moparse_paddle_compat" not in cls.__dict__


def test_runtime_length_override_is_rejected_before_generation():
    _, cls = predictor_fixture()
    collector = install_paddle_compat(versions=SUPPORTED_VERSIONS, predictor_class=cls)
    predictor = cls()
    with pytest.raises(ValueError, match="frozen 4096"):
        predictor.process(inputs(), max_new_tokens=8192)
    assert predictor.calls == []
    assert collector.finish_page()["batches"][0]["status"] == "failed"


def native_server_fixture(monkeypatch, *, failure=None):
    from moparse_eval import executors, paddle_server

    events = []

    class Observer:
        def begin_page(self, page, request_id):
            events.append(("begin", page, request_id))

        def finish_page(self):
            events.append(("finish",))
            return {"batches": [{"status": "synthetic"}]}

    observer = Observer()

    class SDK:
        def __init__(self, _config):
            self.control = SimpleNamespace(start=lambda _deadline: None)
            self.graph_evidence = []

        def _init_paddle(self):
            self.paddle_observations = observer

    fake_cuda = SimpleNamespace(reset_peak_memory_stats=lambda: None,
                                max_memory_allocated=lambda: 17,
                                max_memory_reserved=lambda: 31)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        set_num_threads=lambda _: None, set_num_interop_threads=lambda _: None, cuda=fake_cuda))
    monkeypatch.setattr(executors, "_SDKs", SDK)
    raw = {"native": "preserved", "research_export_errors": [{"region": 2}]}

    def parse_page(_sdk, _page, _assets):
        events.append(("parse",))
        if failure is not None:
            raise failure
        return raw, "synthetic markdown"

    counter = iter(range(1, 20))
    monkeypatch.setattr(paddle_server, "time", SimpleNamespace(perf_counter=lambda: next(counter)))
    monkeypatch.setattr(executors, "_paddle_page", parse_page)
    service = paddle_server._NativePaddleInference({})
    stream = io.BytesIO()
    Image.new("RGB", (2, 2)).save(stream, format="PNG")
    request = {"request_id": "synthetic-one", "page": 7,
               "image_base64": base64.b64encode(stream.getvalue()).decode("ascii")}
    return service, request, raw, events


def test_native_server_observation_is_outside_processing_clock_and_keeps_partial_export(monkeypatch):
    service, request, raw, events = native_server_fixture(monkeypatch)
    response = service.parse(request)
    assert response["raw"] is raw
    assert response["inference_runtime"]["native_processing_seconds"] == 1
    observation = response["inference_runtime"]["generation_observations"]
    assert observation["collection_seconds"] == 1
    assert observation["page_export_stage"]["export_error_count"] == 1
    assert observation["page_export_stage"]["faithful_markdown_characters"] == 18
    assert events == [("begin", 7, "synthetic-one"), ("parse",), ("finish",)]
    assert service.requests["synthetic-one"]["state"] == "completed"


def test_native_server_preserves_original_failure_and_failed_region_evidence(monkeypatch):
    failure = RuntimeError("synthetic SDK failure")
    service, request, _raw, events = native_server_fixture(monkeypatch, failure=failure)
    with pytest.raises(RuntimeError) as caught:
        service.parse(request)
    assert caught.value is failure
    assert events == [("begin", 7, "synthetic-one"), ("parse",), ("finish",)]
    record = service.requests["synthetic-one"]
    assert record["state"] == "failed"
    assert record["generation_observations"]["batches"] == [{"status": "synthetic"}]
