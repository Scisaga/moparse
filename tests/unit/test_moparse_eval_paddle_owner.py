"""Synthetic native resources exercise thread affinity and cleanup ownership."""

from __future__ import annotations

import gc
import threading
import weakref
from types import SimpleNamespace

import pytest
from PIL import Image

from moparse_eval.paddle_server import PaddleInference


def test_native_initialization_calls_and_close_share_one_long_lived_thread():
    events = []
    responses = []

    class Native:
        requests = {}

        def __init__(self, config):
            events.append(("init", threading.current_thread()))
            assert config["pipeline"] == "P03"

        def parse(self, request):
            events.append((request["request_id"], threading.current_thread()))
            return {"request_id": request["request_id"], "raw": {"native": True}}

        def close(self):
            events.append(("close", threading.current_thread()))

    inference = PaddleInference({"pipeline": "P03"}, native_factory=Native)
    callers = [threading.Thread(target=lambda i=i: responses.append(
        inference.parse({"request_id": str(i)}))) for i in range(5)]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join(timeout=2)
        assert not caller.is_alive()
    inference.close()
    inference.close()
    owner = events[0][1]
    assert len(events) == 7 and events[-1][0] == "close"
    assert all(thread is owner for _, thread in events)
    assert owner not in callers and owner is not threading.current_thread()
    assert not owner.daemon and not owner.is_alive()
    assert {result["request_id"] for result in responses} == set(map(str, range(5)))


def test_idle_owner_does_not_retain_last_request_or_response():
    class Payload:
        pass

    class Response(dict):
        pass

    class Native:
        requests = {}

        def __init__(self, _config):
            pass

        def parse(self, request):
            return Response(request_id=request["request_id"])

        def close(self):
            pass

    inference = PaddleInference({}, native_factory=Native)
    try:
        payload = Payload()
        request = {"request_id": "one", "image": payload}
        response = inference.parse(request)
        payload_ref, response_ref = weakref.ref(payload), weakref.ref(response)
        del payload, request, response
        gc.collect()
        assert payload_ref() is None and response_ref() is None
    finally:
        inference.close()


def test_close_waits_for_accepted_call_and_status_remains_readable():
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    finished = []

    class Native:
        def __init__(self, _config):
            self.requests = {}

        def parse(self, request):
            self.requests["owned"] = {"state": "running"}
            entered.set()
            assert release.wait(2)
            self.requests["owned"]["state"] = "completed"
            finished.append("parse")
            return {"request_id": request["request_id"]}

        def close(self):
            finished.append("close")
            closed.set()

    inference = PaddleInference({}, native_factory=Native)
    caller = threading.Thread(target=lambda: inference.parse({"request_id": "owned"}))
    closer = threading.Thread(target=inference.close)
    caller.start()
    assert entered.wait(2)
    closer.start()
    try:
        assert inference.requests["owned"]["state"] == "running"
        assert not closed.wait(0.02)
    finally:
        release.set()
        caller.join(timeout=2)
        closer.join(timeout=2)
    assert not caller.is_alive() and not closer.is_alive()
    assert finished == ["parse", "close"]
    assert inference.requests["owned"]["state"] == "completed"
    with pytest.raises(RuntimeError, match="not submitted"):
        inference.parse({"request_id": "late"})


def test_native_failure_is_not_replayed_and_does_not_poison_next_call():
    calls = []
    failure = ValueError("synthetic native failure")

    class Native:
        requests = {}

        def __init__(self, _config):
            pass

        def parse(self, request):
            calls.append(request["request_id"])
            if request["request_id"] == "bad":
                raise failure
            return request

        def close(self):
            pass

    inference = PaddleInference({}, native_factory=Native)
    try:
        with pytest.raises(ValueError) as error:
            inference.parse({"request_id": "bad"})
        assert error.value is failure
        request = {"request_id": "good", "raw": {"untouched": [1, 2]}}
        assert inference.parse(request) is request
        assert calls == ["bad", "good"]
    finally:
        inference.close()


@pytest.mark.parametrize("phase", ["initialization", "close"])
def test_native_lifecycle_failure_propagates_after_owner_thread_is_joined(phase):
    threads = []

    class Native:
        requests = {}

        def __init__(self, _config):
            threads.append(threading.current_thread())
            if phase == "initialization":
                raise ValueError("synthetic initialization failure")

        def close(self):
            raise ValueError("synthetic close failure")

    with pytest.raises(ValueError, match=f"synthetic {phase} failure"):
        inference = PaddleInference({}, native_factory=Native)
        inference.close()
    assert len(threads) == 1 and not threads[0].is_alive()


@pytest.mark.parametrize("config, expected", [({}, False), ({"paddle_use_queues": True}, True)])
def test_page_executor_declares_sdk_queue_mode_without_changing_native_result(config, expected):
    from moparse_eval.executors import _Assets, _paddle_page

    class Result(dict):
        json = {"native": "preserved"}
        markdown = {"markdown_texts": "Synthetic content", "markdown_images": {}}

        def _build_handle_funcs_dict(self, **_kwargs):
            return {}

    calls = []

    def predict(image, **options):
        calls.append((image, options))
        return [Result(parsing_res_list=[])]

    sdks = SimpleNamespace(config=config, paddle=SimpleNamespace(predict=predict))
    with Image.new("RGB", (2, 3), (10, 20, 30)) as image:
        raw, markdown = _paddle_page(sdks, {"image": image, "page": 7}, _Assets())
    assert calls[0][1]["use_queues"] is expected
    assert calls[0][0].shape == (3, 2, 3)
    assert calls[0][0][0, 0].tolist() == [30, 20, 10]
    assert raw["native"] == "preserved" and markdown == "Synthetic content"


def test_invalid_queue_mode_fails_before_native_submission():
    from moparse_eval.executors import _Assets, _paddle_page
    from moparse_eval.runtime import PreparationError

    sdks = SimpleNamespace(config={"paddle_use_queues": "false"}, paddle=None)
    with pytest.raises(PreparationError, match="boolean"):
        _paddle_page(sdks, {"image": None, "page": 1}, _Assets())


def test_unknown_owner_mode_is_rejected_before_resource_initialization():
    with pytest.raises(ValueError, match="persistent-owner-v1"):
        PaddleInference({"paddle_execution_mode": "unsupported"})
