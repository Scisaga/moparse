"""Cooperative per-sample admission gates for isolated SDK HTTP transports.

Already-issued requests are drained, never cancelled or retried by this layer.
An unknown remote execution permanently closes this worker's admission gate.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class RequestStopped(RuntimeError):
    """No new work may enter the current sample's inference endpoints."""


def execution_unknown(error: BaseException | None) -> bool:
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        # SDKs use requests, httpx, aiohttp and OpenAI wrappers. A transport
        # failure is conservatively unknown, even if connection failed early.
        name = type(error).__name__
        if name in {"ReadTimeout", "WriteTimeout", "PoolTimeout", "ConnectTimeout", "Timeout",
                    "TimeoutError", "ConnectionError", "ConnectError", "ReadError", "WriteError",
                    "RemoteProtocolError", "LocalProtocolError", "ProtocolError", "ConnectionResetError",
                    "ServerDisconnectedError", "ClientConnectionError", "APITimeoutError", "APIConnectionError"}:
            return True
        error = error.__cause__ or error.__context__
    return False


def sample_timeout(config: Mapping[str, Any], sample: Mapping[str, Any]) -> float:
    from .runtime import PreparationError
    policy = config.get("timeout_policy", {})
    formal = sample.get("suite") in {"quality800", "perf80"} or sample.get("phase") in {"quality", "performance"}
    if not policy.get("frozen"):
        if formal:
            raise PreparationError("formal execution requires a frozen direct single-page timeout_policy")
        return float(config.get("timeout_seconds", 7200))
    pages = sample.get("input_page_count")
    seconds = policy.get("single_page_seconds")
    if isinstance(pages, bool) or not isinstance(pages, int) or pages <= 0:
        raise PreparationError("frozen sample deadlines require explicit positive input_page_count")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        raise PreparationError("single_page_seconds must be a directly measured positive duration")
    if (policy.get("minimum_seconds", 300), policy.get("multiplier", 3), policy.get("maximum_seconds", 3600)) != (300, 3, 3600):
        raise PreparationError("timeout_policy changed the declared common deadline formula")
    return min(3600.0, max(300.0, 3.0 * seconds * pages))


class RequestControl:
    def __init__(self, config: Mapping[str, Any]) -> None:
        self.origins = {urlsplit(value).netloc for value in config.get("endpoints", {}).values() if isinstance(value, str)}
        self.cancel = Path(config["cancel_path"]) if config.get("cancel_path") else None
        self.deadline: float | None = None
        self.unknown = False
        self.reason: str | None = None
        self.events: list[dict[str, Any]] = []
        self.observe_metadata = bool(config.get("observe_request_metadata", False))
        self.responses: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.patches: list[tuple[Any, str, Any]] = []

    def start(self, deadline: float) -> None:
        if self.unknown:
            raise RequestStopped("original remote execution remains unknown")
        self.deadline, self.reason, self.events = deadline, None, []
        self.responses = []

    def stopped(self) -> str | None:
        with self.lock:
            if self.unknown:
                self.reason = "execution_unknown"
            elif self.cancel is not None and self.cancel.exists():
                self.reason = "cancelled"
            elif self.deadline is not None and time.perf_counter() >= self.deadline:
                self.reason = "timed_out"
            return self.reason

    def check(self) -> None:
        reason = self.stopped()
        if reason:
            raise RequestStopped(reason)

    def owns(self, url: Any) -> bool:
        return self.deadline is not None and urlsplit(str(url)).netloc in self.origins

    def failed(self, error: BaseException) -> None:
        with self.lock:
            unknown = execution_unknown(error)
            self.unknown |= unknown
            self.reason = "execution_unknown" if self.unknown else "received_failure"
            self.events.append({"type": type(error).__name__, "message": str(error),
                                "execution_unknown": unknown, "retry": False})

    def response(self, response: Any) -> None:
        if self.observe_metadata:
            self._response_metadata(response)
        if response.status_code >= 400:
            with self.lock:
                self.reason = "received_failure"
                self.events.append({"http_status": response.status_code, "received_response": True, "retry": False})

    def _response_metadata(self, response: Any) -> None:
        """Observe cached bytes only: no text/images persisted, IO or retries."""
        record: dict[str, Any] = {"http_status": response.status_code,
                                 "received_response": True, "retry": False}
        try:
            request = getattr(response, "request", None)
            encoded = getattr(request, "_content", None)
            if encoded is None:
                encoded = getattr(request, "body", None)
            if isinstance(encoded, (str, bytes)) and encoded and len(encoded) <= 16 * 1024 ** 2:
                payload = json.loads(encoded)
                if isinstance(payload, Mapping):
                    record["request_parameters"] = {key: payload[key] for key in (
                        "model", "max_tokens", "max_completion_tokens", "max_new_tokens",
                        "temperature", "top_p", "top_k", "repetition_penalty", "stream",
                    ) if key in payload}
            body = getattr(response, "_content", None)
            if isinstance(body, bytes):
                payload = json.loads(body)
                if isinstance(payload, Mapping):
                    record["usage"] = payload.get("usage")
                    record["termination"] = [{key: choice.get(key) for key in (
                        "index", "finish_reason", "stop_reason",
                    )} for choice in payload.get("choices", []) if isinstance(choice, Mapping)]
            else:
                record["body_observation"] = "not_cached_not_consumed"
        except Exception as exc:
            record["metadata_error_type"] = type(exc).__name__
        with self.lock:
            self.responses.append(record)

    def install(self) -> None:
        control = self
        import httpx
        import requests

        def patch(cls: Any, asynchronous: bool) -> None:
            original = cls.send
            if asynchronous:
                async def send_async(instance: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
                    if not control.owns(request.url):
                        return await original(instance, request, *args, **kwargs)
                    control.check()
                    try:
                        response = await original(instance, request, *args, **kwargs)
                    except Exception as exc:
                        control.failed(exc)
                        raise
                    control.response(response)
                    return response
            else:
                def send(instance: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
                    if not control.owns(request.url):
                        return original(instance, request, *args, **kwargs)
                    control.check()
                    try:
                        response = original(instance, request, *args, **kwargs)
                    except Exception as exc:
                        control.failed(exc)
                        raise
                    control.response(response)
                    return response
            self.patches.append((cls, "send", original))
            cls.send = send_async if asynchronous else send
        patch(requests.Session, False)
        patch(httpx.Client, False)
        patch(httpx.AsyncClient, True)

    def close(self) -> None:
        for owner, name, value in reversed(self.patches):
            setattr(owner, name, value)
        self.patches.clear()
