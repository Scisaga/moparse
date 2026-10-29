from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import requests
from pydantic import BaseModel

from moparse_eval.glm_observation import apply_page_loader_overrides, observe_ocr_requests


def response(payload=None, *, status=200, raw=None):
    result = requests.Response()
    result.status_code = status
    result._content = raw if raw is not None else json.dumps(payload or {
        "choices": [{"index": 0, "message": {"content": "SDK original content"},
                     "finish_reason": "length", "stop_reason": 8192}],
        "usage": {"prompt_tokens": 14, "completion_tokens": 8192, "total_tokens": 8206},
    }).encode()
    return result


class Session:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class Client:
    def __init__(self, session=None, *, api_key=""):
        self._session = session
        self.api_key = api_key
        self.extra_headers = {}
        self.created = []

    def _make_session(self):
        session = Session(response())
        self.created.append(session)
        return session

    def sdk_process(self, payload):
        if self._session is None:
            self._session = self._make_session()
        result = self._session.post("http://example.test/ocr?api_key=endpoint-secret",
            data=json.dumps(payload), headers={"Authorization": f"Bearer {self.api_key}"})
        if result.status_code == 200:
            # The fixed SDK itself discards all these diagnostic fields.
            return {"choices": [{"message": {"content": result.json()["choices"][0]["message"]["content"].strip()}}]}
        return {"error": "unchanged SDK failure"}


def request_payload():
    return {"messages": [{"role": "user", "content": [
        {"type": "text", "text": "Table Recognition:"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b"synthetic bytes").decode()}}
    ]}], "max_tokens": 8192, "temperature": 0, "top_k": 1, "top_p": 0.00001,
        "repetition_penalty": 1.1}


def test_same_response_and_sdk_output_are_preserved_with_token_stop_evidence(tmp_path):
    original_response = response()
    original_content = original_response.content
    session = Session(original_response)
    client = Client(session)
    payload = request_payload()
    plain_output = client.sdk_process(payload)
    original_method = session.post
    with observe_ocr_requests(client, tmp_path, page_number=7,
                              task_prompt_mapping={"table": "Table Recognition:"}) as observed:
        sdk_output = client.sdk_process(payload)
        returned_response = session.post("http://example.test", json=payload)
        assert returned_response is original_response
        assert sdk_output == plain_output
        assert original_response.content == original_content
        assert observed.summary()["records"][0]["task_candidates_from_exact_prompt"] == ["table"]
    assert session.post == original_method
    assert "post" not in session.__dict__
    assert not hasattr(client, "_moparse_request_observer")
    assert "_make_session" not in client.__dict__
    saved = json.loads((tmp_path / "index.json").read_text())
    assert saved["recording_errors"] == []
    record = saved["records"][0]
    assert record["choice_termination"] == [{"index": 0, "finish_reason": "length", "stop_reason": 8192}]
    assert record["usage"]["completion_tokens"] == 8192
    assert record["sdk_region_id"] is None
    diagnostic_request = json.loads((tmp_path / record["request_file"]).read_text())
    assert diagnostic_request["repetition_penalty"] == 1.1
    assert payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:")
    directory = (tmp_path / record["request_file"]).parent
    assert (directory / record["region_images"][0]["telemetry_asset"]).read_bytes() == b"synthetic bytes"
    assert json.loads((tmp_path / record["response_file"]).read_text()) == original_response.json()


def test_lazy_session_is_observed_without_extra_requests(tmp_path):
    client = Client()
    with observe_ocr_requests(client, tmp_path, page_number=1) as observed:
        client.sdk_process(request_payload())
    assert len(client.created) == 1
    assert len(client.created[0].calls) == 1
    assert len(observed.summary()["records"]) == 1
    assert "post" not in client._session.__dict__


def test_headers_endpoint_and_known_secrets_never_persist(tmp_path):
    secret = "synthetic-credential-12345"
    payload = request_payload()
    payload["nested"] = {"api_key": secret, "Authorization": "Bearer unknown-credential"}
    original = response({"choices": [{"message": {"content": "echo: " + secret}}],
                         "api_key": "response-only-secret", "diagnostic": secret})
    client = Client(Session(original), api_key=secret)
    client.extra_headers = {"X-Api-Key": "extra-header-secret"}
    with observe_ocr_requests(client, tmp_path, page_number=1):
        client.sdk_process(payload)
    for path in tmp_path.rglob("*.json"):
        text = path.read_text()
        assert secret not in text
        assert "response-only-secret" not in text
        assert "unknown-credential" not in text
        assert "extra-header-secret" not in text
        assert "endpoint-secret" not in text
        assert "Bearer " not in text
    assert original.json()["diagnostic"] == secret


def test_concurrent_region_calls_have_unique_identity_and_intact_responses(tmp_path):
    session = Session(response())
    client = Client(session)
    with observe_ocr_requests(client, tmp_path, page_number=3) as observed:
        with ThreadPoolExecutor(max_workers=4) as executor:
            outputs = list(executor.map(lambda _: client.sdk_process(request_payload()), range(16)))
    assert outputs == [outputs[0]] * 16
    records = observed.summary()["records"]
    assert len(records) == 16
    assert len({item["call_id"] for item in records}) == 16
    assert {item["call_ordinal"] for item in records} == set(range(1, 17))
    assert all(item["state"] == "response_received" for item in records)
    assert all((tmp_path / item["response_file"]).is_file() for item in records)
    assert observed.errors == []


def test_execution_unknown_is_not_retried_and_exception_is_unchanged(tmp_path):
    error = requests.Timeout("error embeds synthetic-secret and an endpoint")
    session = Session(error)
    client = Client(session)
    with observe_ocr_requests(client, tmp_path, page_number=1) as observed:
        with pytest.raises(requests.Timeout) as caught:
            client.sdk_process(request_payload())
    assert caught.value is error
    assert len(session.calls) == 1
    record = observed.summary()["records"][0]
    assert record["state"] == "execution_unknown"
    assert record["exception_type"] == "Timeout"
    assert record["retry_performed_by_observer"] is False
    assert "synthetic-secret" not in (tmp_path / "index.json").read_text()


def test_bad_http_response_preserved_with_non_json_body(tmp_path):
    original = response(status=503, raw=b"temporarily unavailable")
    session = Session(original)
    with observe_ocr_requests(Client(session), tmp_path, page_number=1) as observed:
        assert session.post("http://example.test", json=request_payload()) is original
    record = observed.summary()["records"][0]
    assert record["status_code"] == 503
    assert record["state"] == "response_received"
    assert json.loads((tmp_path / record["response_file"]).read_text()) == {
        "non_json_response_text": "temporarily unavailable"}
    assert len(session.calls) == 1


def test_recording_failure_does_not_change_sdk_response_or_retry(tmp_path, monkeypatch):
    def fail_save(*args):
        raise OSError("secret in IO message")
    monkeypatch.setattr("moparse_eval.glm_observation._save_json", fail_save)
    session = Session(response())
    with observe_ocr_requests(Client(session), tmp_path, page_number=1) as observed:
        assert session.post("http://example.test", json=request_payload()) is session.result
    assert len(session.calls) == 1
    assert {item["stage"] for item in observed.errors} == {
        "request_recording", "response_recording", "index_recording"}
    assert all(set(item) == {"stage", "exception_type"} for item in observed.errors)


def test_streaming_response_is_not_consumed(tmp_path):
    original = SimpleNamespace(status_code=200)
    session = Session(original)
    with observe_ocr_requests(Client(session), tmp_path, page_number=1) as observed:
        assert session.post("http://example.test", json=request_payload(), stream=True) is original
    assert observed.summary()["records"][0]["response_recording"] == "streaming_not_consumed"
    assert observed.errors == []


def test_nested_observation_rejected_without_mutating_original_owner(tmp_path):
    client = Client(Session(response()))
    with observe_ocr_requests(client, tmp_path, page_number=1) as outer:
        with pytest.raises(RuntimeError, match="already has"):
            with observe_ocr_requests(client, tmp_path / "inner", page_number=1):
                pass
        client.sdk_process(request_payload())
    assert len(outer.records) == 1


class LoaderConfig(BaseModel):
    max_tokens: int = 8192
    repetition_penalty: float = 1.1
    task_prompt_mapping: dict[str, str] = {"table": "Table Recognition:"}


def test_official_page_loader_overrides_are_explicit_validated_and_non_mutating():
    original = LoaderConfig()
    changed = apply_page_loader_overrides(original, {"repetition_penalty": 1.05, "max_tokens": 16384})
    assert original.repetition_penalty == 1.1
    assert changed.repetition_penalty == 1.05
    assert changed.max_tokens == 16384
    assert changed.task_prompt_mapping == original.task_prompt_mapping
    with pytest.raises(ValueError, match="unknown GLM"):
        apply_page_loader_overrides(original, {"repair_output": True})
    with pytest.raises(ValueError, match="non-finite"):
        apply_page_loader_overrides(original, {"repetition_penalty": float("nan")})
    with pytest.raises(ValueError):
        apply_page_loader_overrides(original, {"max_tokens": "invalid"})
