"""Private, owned native Paddle inference service for isolated research only."""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import signal
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class _NativePaddleInference:
    def __init__(self, config: dict[str, Any]) -> None:
        import torch

        from .executors import _SDKs
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        self.config = config
        self.sdk = _SDKs(config)
        self.sdk._init_paddle()
        self.observations = self.sdk.paddle_observations
        self.lock = threading.Lock()
        self.requests: dict[str, dict[str, Any]] = {}

    def parse(self, request: dict[str, Any]) -> dict[str, Any]:
        import torch
        from PIL import Image

        from .executors import _Assets, _paddle_page
        ident = str(request["request_id"])
        if not ident or len(ident) > 128:
            raise ValueError("invalid request identity")
        with self.lock:
            if ident in self.requests:
                raise ValueError("request identity is already registered; execution is not replayable")
            for key in list(self.requests):
                if len(self.requests) < 512:
                    break
                if self.requests[key]["state"] in {"completed", "failed"}:
                    del self.requests[key]
            if len(self.requests) >= 512:
                raise RuntimeError("native request ownership capacity exceeded")
            self.requests[ident] = {"state": "running", "request_id": ident}
            self.observations.begin_page(request.get("page"), ident)
            generation_observations = None
            try:
                image = Image.open(io.BytesIO(base64.b64decode(request["image_base64"], validate=True))).convert("RGB")
                assets = _Assets()
                # Both owned containers share this host's CLOCK_MONOTONIC.
                # Close admission at native predictor boundaries without
                # interrupting an already-started generation operation.
                self.sdk.control.start(float(request.get("deadline_monotonic",
                    time.perf_counter() + float(self.config.get("timeout_seconds", 7200)))))
                torch.cuda.reset_peak_memory_stats()
                started = time.perf_counter()
                raw, markdown = _paddle_page(self.sdk, {"page": int(request["page"]), "image": image}, assets)
                native_processing_seconds = time.perf_counter() - started
                observation_started = time.perf_counter()
                generation_observations = self.observations.finish_page()
                generation_observations["page_export_stage"] = {
                    "faithful_markdown_characters": len(markdown),
                    "export_error_count": len(raw.get("research_export_errors", [])),
                    "scope": "SDK page export; character count does not establish truncation"}
                generation_observations["collection_seconds"] = time.perf_counter() - observation_started
                response = {"request_id": ident, "raw": raw, "faithful_markdown": markdown,
                    "media": {name: base64.b64encode(payload).decode("ascii") for name, payload in assets.data.items()},
                    "inference_runtime": {"native_processing_seconds": native_processing_seconds,
                        "generation_observations": generation_observations,
                        "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                        "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                        "cuda_graph_evidence": self.sdk.graph_evidence,
                        "allocation": {"cpus": 4, "host_memory_gib": 20,
                            "gpu_memory_gib": self.config.get("resources", {}).get("gpu_memory_gib", 16)}}}
                self.requests[ident]["state"] = "completed"
                return response
            except BaseException as exc:
                self.requests[ident].update(state="failed", error_type=type(exc).__name__,
                    generation_observations=(generation_observations if generation_observations is not None
                                             else self.observations.finish_page()))
                raise

    def close(self) -> None:
        asyncio.run(self.sdk.close())


class PaddleInference:
    """Keep native initialization, parsing and teardown on one owned thread.

    Torch 2.10 deliberately retains cuDNN execution-plan caches at thread exit.
    A new GPU caller per HTTP request therefore accumulates native host memory.
    The admission lock permits at most one submitted job, while HTTP health and
    request-status handlers remain responsive. Native calls are never cancelled
    or retried, and close waits for the accepted call before joining the owner.
    """

    def __init__(self, config: dict[str, Any], *, native_factory: Any = None) -> None:
        mode = config.get("paddle_execution_mode", "persistent-owner-v1")
        if mode != "persistent-owner-v1":
            raise ValueError("paddle_execution_mode must be persistent-owner-v1")
        self.config = config
        self._admission = threading.Lock()
        self._closed = False
        self._owner = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paddle-native-owner")
        try:
            self._native = self._owner.submit(native_factory or _NativePaddleInference, config).result()
        except BaseException:
            self._owner.shutdown(wait=True, cancel_futures=False)
            raise

    @property
    def requests(self) -> dict[str, dict[str, Any]]:
        return self._native.requests

    def parse(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._admission:
            if self._closed:
                raise RuntimeError("native Paddle owner is closed; execution was not submitted")
            return self._owner.submit(self._native.parse, request).result()

    def close(self) -> None:
        with self._admission:
            if self._closed:
                return
            self._closed = True
            try:
                self._owner.submit(self._native.close).result()
            finally:
                self._owner.shutdown(wait=True, cancel_futures=False)


def handler(inference: Any, model_name: str):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: Any) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/v1/models":
                self._json(200, {"data": [{"id": model_name}], "scope": "initialized; inference acceptance is separate"})
            elif self.path == "/health":
                self._json(200, {"status": "ok"})
            elif self.path.startswith("/requests/"):
                ident = self.path.removeprefix("/requests/")
                record = inference.requests.get(ident)
                self._json(200 if record else 404, record or {"error": "unknown request"})
            else:
                self._json(404, {"error": "unknown route"})

        def do_POST(self) -> None:
            if self.path != "/parse-page":
                self._json(404, {"error": "unknown route"})
                return
            request: Any = None
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 64 * 1024 * 1024:
                    raise ValueError("invalid page request size")
                request = json.loads(self.rfile.read(size))
                self._json(200, inference.parse(request))
            except Exception as exc:
                payload = {"error": type(exc).__name__, "message": str(exc), "retry": False}
                if isinstance(request, dict):
                    record = inference.requests.get(str(request.get("request_id", "")), {})
                    if "generation_observations" in record:
                        payload["generation_observations"] = record["generation_observations"]
                self._json(500, payload)
    return Handler


def serve_owned(factory: Callable[[], Any], model_name: str, address: tuple[str, int]) -> None:
    """Handle PID1 termination, stop admission, then join original handlers.

    HTTPServer.shutdown must run outside its serving thread. Non-daemon
    request threads ensure an issued parse finishes before GPU ownership ends.
    Signals are installed before model initialization too.
    """
    stopping = threading.Event()
    server: ThreadingHTTPServer | None = None
    shutdown_started = False
    received_signal: int | None = None

    def stop(signum: int, _frame: Any) -> None:
        nonlocal shutdown_started, received_signal
        received_signal = signum
        stopping.set()
        if server is not None and not shutdown_started:
            shutdown_started = True
            threading.Thread(target=server.shutdown, name="native-paddle-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    started = time.perf_counter()
    inference = factory()
    print(json.dumps({"state": "initialized", "initialization_seconds": time.perf_counter() - started,
                      "model_name": model_name}), flush=True)
    server = ThreadingHTTPServer(address, handler(inference, model_name))
    server.daemon_threads = False
    server.block_on_close = True
    try:
        if not stopping.is_set():
            server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        inference.close()
        print(json.dumps({"state": "stopped", "received_signal": received_signal,
                          "all_original_request_threads_joined": True}), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    model_name = "PaddleOCR-VL-" + ("1.5" if config["pipeline"] == "P03" else "1.6")
    serve_owned(lambda: PaddleInference(config), model_name, ("0.0.0.0", args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
