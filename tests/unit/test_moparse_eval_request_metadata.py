from __future__ import annotations

import json
import time
from types import SimpleNamespace

import httpx
import pytest
import requests

from moparse_eval.request_control import RequestControl


@pytest.mark.parametrize("transport", ["httpx", "requests"])
def test_cached_response_observes_only_generation_metadata(transport):
    payload = {"model": "synthetic", "max_tokens": 4096, "temperature": 0,
               "messages": [{"content": "PRIVATE INPUT"}]}
    result = {"usage": {"completion_tokens": 14}, "choices": [
        {"index": 0, "finish_reason": "stop", "stop_reason": 2,
         "message": {"content": "PRIVATE OUTPUT"}}]}
    if transport == "httpx":
        response = httpx.Response(200, json=result, request=httpx.Request(
            "POST", "http://synthetic/v1/chat/completions", json=payload))
    else:
        response = requests.Response()
        response.status_code = 200
        response.request = requests.Request("POST", "http://synthetic", json=payload).prepare()
        response._content = json.dumps(result).encode()
    control = RequestControl({"observe_request_metadata": True})
    control.start(time.perf_counter() + 60)
    control.response(response)
    assert control.responses == [{"http_status": 200, "received_response": True, "retry": False,
        "request_parameters": {"model": "synthetic", "max_tokens": 4096, "temperature": 0},
        "usage": {"completion_tokens": 14},
        "termination": [{"index": 0, "finish_reason": "stop", "stop_reason": 2}]}]
    assert "PRIVATE" not in json.dumps(control.responses)
    assert not control.events and control.stopped() is None
    control.start(time.perf_counter() + 60)
    assert not control.responses


def test_uncached_response_stream_is_never_consumed():
    class UnreadStream(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("metadata observer must not read the stream")

    response = httpx.Response(200, stream=UnreadStream(), request=httpx.Request("POST", "http://synthetic"))
    control = RequestControl({"observe_request_metadata": True})
    control.response(response)
    assert control.responses[0]["body_observation"] == "not_cached_not_consumed"
    assert not response.is_stream_consumed


def test_metadata_failure_does_not_mask_received_http_failure():
    response = SimpleNamespace(status_code=500, request=None, _content=b"not JSON")
    control = RequestControl({"observe_request_metadata": True})
    control.response(response)
    assert control.responses[0]["metadata_error_type"] == "JSONDecodeError"
    assert control.events == [{"http_status": 500, "received_response": True, "retry": False}]
    assert control.stopped() == "received_failure"


def test_metadata_is_opt_in():
    control = RequestControl({})
    control.response(SimpleNamespace(status_code=200))
    assert not control.responses
