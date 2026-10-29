"""Side-channel observation of one fixed GLM SDK client's region requests.

This module neither interprets inputs nor repairs SDK output.  It wraps only the
selected client's session, returns the very same Response, and never retries.
Request/response headers and URLs are deliberately not persisted.  Known API
secrets and secret-shaped JSON fields are redacted from the diagnostic copies.
"""

from __future__ import annotations

import base64
import json
import math
import threading
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_REDACTED = "[REDACTED]"
_SECRET_KEYS = {"authorization", "proxyauthorization", "apikey", "xapikey", "accesstoken",
                "refreshtoken", "clientsecret", "password", "cookie", "setcookie"}
_LOADER_FIELDS = {"max_tokens", "temperature", "top_p", "top_k", "repetition_penalty",
                  "t_patch_size", "patch_expand_factor", "image_expect_length", "image_format",
                  "min_pixels", "max_pixels", "task_prompt_mapping", "pdf_dpi", "pdf_max_pages",
                  "pdf_verbose"}


def apply_page_loader_overrides(page_loader: Any, overrides: Mapping[str, Any]) -> Any:
    """Return a validated new official PageLoaderConfig with declared overrides.

    The caller must put this returned object into PipelineConfig *before*
    constructing the SDK.  No existing SDK/config object is mutated.
    """
    unknown = set(overrides) - _LOADER_FIELDS
    if unknown:
        raise ValueError(f"unknown GLM page-loader option: {', '.join(sorted(unknown))}")
    fields = getattr(type(page_loader), "model_fields", {})
    if not _LOADER_FIELDS.issuperset(fields) or not set(overrides).issubset(fields):
        raise ValueError("unsupported official GLM PageLoaderConfig fields")
    values = page_loader.model_dump()
    values.update(overrides)
    # Reject NaN and infinities even when an official unconstrained float would
    # accept them; JSON requests cannot faithfully represent those values.
    for key, value in overrides.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"non-finite GLM page-loader option: {key}")
    return type(page_loader).model_validate(values)


def _secret_key(key: Any) -> bool:
    return "".join(character for character in str(key).lower() if character.isalnum()) in _SECRET_KEYS


def _secret_values(headers: Any) -> list[str]:
    values = []
    if isinstance(headers, Mapping):
        for key, value in headers.items():
            if _secret_key(key) and isinstance(value, str) and value:
                values.append(value)
                if value.lower().startswith("bearer ") and value[7:]:
                    values.append(value[7:])
    return values


def _sanitize(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _REDACTED if _secret_key(key) else _sanitize(item, secrets)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in sorted({secret for secret in secrets if secret}, key=len, reverse=True):
            value = value.replace(secret, _REDACTED)
    return value


def _save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _detach_images(value: Any, directory: Path, images: list[dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        return {key: _detach_images(item, directory, images) for key, item in value.items()}
    if isinstance(value, list):
        return [_detach_images(item, directory, images) for item in value]
    if isinstance(value, str) and value.startswith("data:image/") and ";base64," in value:
        media, _, encoded = value.partition(",")
        mime = media[5:].split(";", 1)[0]
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime, "bin")
        data = base64.b64decode(encoded, validate=True)
        path = directory / f"region-image-{len(images) + 1:03}.{extension}"
        path.write_bytes(data)
        evidence = {"telemetry_asset": path.name, "mime_type": mime,
                    "byte_length": len(data), "request_data_uri_externalized": True}
        images.append(evidence)
        return evidence
    return value


def _prompts(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    output = []
    for message in value.get("messages", []):
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if isinstance(content, str):
            output.append(content)
        elif isinstance(content, list):
            output.extend(item["text"] for item in content if isinstance(item, Mapping)
                          and item.get("type") == "text" and isinstance(item.get("text"), str))
    return output


class GLMRequestObservation:
    """One page's thread-safe diagnostic sink, without a semantic region ID.

    Calls are identified by UUID and actual executing thread.  A task is named
    only when its request prompt exactly matches the declared SDK prompt map;
    no coordinate, output text, or frozen reference is used to infer identity.
    """

    def __init__(self, client: Any, directory: Path, *, page_number: int,
                 task_prompt_mapping: Mapping[str, str] | None = None) -> None:
        self.client = client
        self.directory = Path(directory)
        self.page_number = page_number
        self.task_prompt_mapping = dict(task_prompt_mapping or {})
        self.lock = threading.Lock()
        self.records: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []
        self.sessions: list[tuple[Any, Any, bool]] = []
        self.original_factory: Any = None
        self.factory_was_local = False
        self.entered = False
        self.secrets = _secret_values(getattr(client, "extra_headers", {}))
        api_key = getattr(client, "api_key", None)
        if isinstance(api_key, str) and api_key:
            self.secrets.append(api_key)

    def _error(self, stage: str, exc: Exception) -> None:
        # Exception messages can include credentials, endpoints or complete
        # payloads.  Retain only type and diagnostic stage.
        with self.lock:
            self.errors.append({"stage": stage, "exception_type": type(exc).__name__})

    def _observe_post(self, original: Any, *args: Any, **kwargs: Any) -> Any:
        call_id = uuid.uuid4().hex
        with self.lock:
            ordinal = len(self.records) + 1
            record: dict[str, Any] = {"call_id": call_id, "call_ordinal": ordinal,
                "page_number": self.page_number, "thread_id": threading.get_ident(),
                "sdk_region_id": None, "identity_basis": "observed_call_and_request_prompt_only",
                "state": "started", "retry_performed_by_observer": False}
            self.records.append(record)
        directory = self.directory / f"{ordinal:05}-{call_id}"
        secrets = self.secrets + _secret_values(kwargs.get("headers", {}))
        started = time.perf_counter()
        try:
            directory.mkdir(parents=True, exist_ok=False)
            payload = kwargs.get("json")
            if payload is None:
                payload = json.loads(kwargs.get("data", "null"))
            prompts = _prompts(payload)
            record["task_prompts"] = _sanitize(prompts, secrets)
            record["task_candidates_from_exact_prompt"] = [task for task, prompt in self.task_prompt_mapping.items()
                                                           if prompt in prompts]
            images: list[dict[str, Any]] = []
            diagnostic_payload = _detach_images(_sanitize(payload, secrets), directory, images)
            record["region_images"] = images
            record["request_file"] = f"{directory.name}/request.json"
            _save_json(directory / "request.json", diagnostic_payload)
            _save_json(directory / "event.json", record)
        except Exception as exc:
            self._error("request_recording", exc)
        try:
            response = original(*args, **kwargs)
        except BaseException as exc:
            record.update(state="execution_unknown", exception_type=type(exc).__name__,
                          elapsed_seconds=time.perf_counter() - started)
            try:
                _save_json(directory / "event.json", record)
            except Exception as save_error:
                self._error("exception_recording", save_error)
            raise
        record.update(state="response_received", elapsed_seconds=time.perf_counter() - started,
                      status_code=response.status_code)
        try:
            # requests.Session.post defaults to stream=False.  Reading cached
            # content never consumes a streaming iterator or calls json() on
            # the SDK's Response, and leaves its identity/content unchanged.
            if kwargs.get("stream", False):
                record["response_recording"] = "streaming_not_consumed"
            else:
                raw_bytes = response.content
                try:
                    raw = json.loads(raw_bytes)
                except (ValueError, UnicodeError):
                    raw = {"non_json_response_text": raw_bytes.decode("utf-8", errors="replace")}
                raw = _sanitize(raw, secrets)
                record["response_file"] = f"{directory.name}/response.json"
                _save_json(directory / "response.json", raw)
                if isinstance(raw, Mapping):
                    record["usage"] = raw.get("usage")
                    record["choice_termination"] = [{key: choice.get(key) for key in
                        ("index", "finish_reason", "stop_reason")} for choice in raw.get("choices", [])
                        if isinstance(choice, Mapping)]
            _save_json(directory / "event.json", record)
        except Exception as exc:
            self._error("response_recording", exc)
        return response

    def _attach(self, session: Any) -> Any:
        with self.lock:
            if any(existing is session for existing, _, _ in self.sessions):
                return session
            self.secrets.extend(_secret_values(getattr(session, "headers", {})))
            original = session.post
            local = "post" in getattr(session, "__dict__", {})
            self.sessions.append((session, original, local))
            session.post = lambda *args, **kwargs: self._observe_post(original, *args, **kwargs)
        return session

    def __enter__(self) -> GLMRequestObservation:
        if self.entered:
            raise RuntimeError("GLM request observer cannot be entered twice")
        if getattr(self.client, "_moparse_request_observer", None) is not None:
            raise RuntimeError("selected GLM client already has a request observer")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.entered = True
        self.client._moparse_request_observer = self
        self.original_factory = self.client._make_session
        self.factory_was_local = "_make_session" in getattr(self.client, "__dict__", {})
        self.client._make_session = lambda: self._attach(self.original_factory())
        session = getattr(self.client, "_session", None)
        if session is not None:
            self._attach(session)
        return self

    def __exit__(self, *_: Any) -> None:
        # The surrounding SDK process must have joined its region workers
        # before leaving this context; the observer does not cancel requests.
        if self.factory_was_local:
            self.client._make_session = self.original_factory
        else:
            del self.client._make_session
        for session, original, local in self.sessions:
            if local:
                session.post = original
            else:
                del session.post
        del self.client._moparse_request_observer
        try:
            _save_json(self.directory / "index.json", self.summary())
        except Exception as exc:
            self._error("index_recording", exc)

    def summary(self) -> dict[str, Any]:
        with self.lock:
            return {"schema": "moparse-glm-request-observation-v1", "page_number": self.page_number,
                    "credentials_redacted": True, "headers_and_endpoints_recorded": False,
                    "response_identity_preserved": True, "sdk_output_modified": False,
                    "records": list(self.records), "recording_errors": list(self.errors)}


@contextmanager
def observe_ocr_requests(client: Any, directory: Path, *, page_number: int,
                         task_prompt_mapping: Mapping[str, str] | None = None) -> Iterator[GLMRequestObservation]:
    """Observe only this client's actual region HTTP calls until SDK returns."""
    with GLMRequestObservation(client, directory, page_number=page_number,
                               task_prompt_mapping=task_prompt_mapping) as observer:
        yield observer
