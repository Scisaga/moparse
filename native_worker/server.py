"""Private PDF-native worker. It never serves public Markdown or owns a GPU.

CPU PDF/text processing uses the reviewed MinerU text-coordinate patch. Visual
layout and tables use a separately managed GPU vLLM endpoint. The public API
continues to own routing, GFM rendering, source references, jobs and storage.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import os
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("MINERU_DEVICE_MODE", "cpu")
os.environ.setdefault("MINERU_TABLE_DEVICE", "cpu")
os.environ.setdefault("MINERU_MODEL_SMALL_BACKEND", "onnx")
os.environ.setdefault("MINERU_MODEL_SOURCE", "local")
os.environ.setdefault("MINERU_PROCESSING_WINDOW_SIZE", "64")

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from native_worker.patch_dependency import verify_patch, verify_resource_patch
from native_worker.request_control import NativeRequest, active_request, install_window_progress

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 200 * 1024 * 1024))
MAX_PAGES = int(os.environ.get("MAX_CONTENT_UNITS", "1000"))
VLM_URL = os.environ.get("MINERU_VLM_BASE_URL", "http://mineru-vllm:8000/").rstrip("/")
VLM_MODEL = os.environ.get("MINERU_VLM_MODEL", "mineru-native")
VLM_CONCURRENCY = int(os.environ.get("MINERU_VLM_CONCURRENCY", "2"))
VLM_TIMEOUT = float(os.environ.get("MINERU_VLM_TIMEOUT_SECONDS", "600"))
_ready = False
_versions: dict[str, str] = {}
_patch: dict[str, str] = {}
_resource_policy: dict[str, str | int | bool] = {}
_document_lock = asyncio.Lock()
_requests: dict[str, NativeRequest] = {}
_tasks: dict[str, asyncio.Task] = {}
_request_control: dict[str, str] = {}


def _initialize() -> None:
    global _versions, _patch, _resource_policy, _request_control
    _patch = verify_patch()
    _resource_policy = verify_resource_patch()
    _request_control = install_window_progress()
    _versions = {
        name: importlib.metadata.version(name)
        for name in ("mineru", "docvortex", "mineru-vl-utils", "onnxruntime", "pypdfium2")
    }
    # This is the same ONNX context used in the measured Advanced/TXT runs.
    from mineru.model.runtime.hybrid import HybridLocalModelContextSingleton

    HybridLocalModelContextSingleton().get_model()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _ready
    await asyncio.to_thread(_initialize)
    _ready = True
    yield
    _ready = False
    from mineru.model.vlm.runtime import shutdown_cached_models

    await asyncio.to_thread(shutdown_cached_models)


app = FastAPI(title="moparse native worker", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    available = False
    detail = None
    if _ready:
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(f"{VLM_URL}/v1/models")
                response.raise_for_status()
                models = response.json().get("data", [])
                available = any(item.get("id") == VLM_MODEL for item in models)
                if not available:
                    detail = "configured model is absent from the VLM endpoint"
        except (httpx.HTTPError, ValueError) as exc:
            detail = type(exc).__name__
    return {
        "ready": _ready and available,
        "backend": "mineru-advanced-txt",
        "versions": _versions,
        "model": VLM_MODEL,
        "max_concurrency": VLM_CONCURRENCY,
        "text_matching": _patch,
        "resource_policy": _resource_policy,
        "request_control": _request_control,
        "active_requests": sum(
            r.state in {"queued", "running", "stopping"} for r in _requests.values()
        ),
        "detail": detail,
    }


def export_source_blocks(page: Any) -> list[dict[str, Any]]:
    """Use the pinned public typed renderer, including page auxiliary content.

    The main process only replaces table HTML with its established GFM grid.
    Rich inline content, lists, code, math and visual descriptions stay under
    the upstream renderer's semantics instead of a second handwritten exporter.
    """
    from docvortex.options import LatexDelimitersConfig
    from docvortex.render.markdown import render_single_block

    exported = []
    for block in page.blocks:
        raw = (
            block.to_dict(exclude_block_fields={"image_base64"})
            if hasattr(block, "to_dict")
            else block.model_dump(mode="json", exclude_defaults=True)
        )
        images: list[dict[str, Any]] = []

        def source_image(parent: Any, _images: list = images) -> str:
            box = getattr(parent, "bbox", None)
            if box is None:
                raise ValueError("rendered source image is missing its original bbox")
            _images.append({"bbox": list(box)})
            return "<!-- image -->"

        try:
            raw["markdown"] = render_single_block(
                block,
                delimiters=LatexDelimitersConfig(),
                asset_base_url="",
                image_renderer=source_image,
            )
            if str(getattr(block, "type", "")) == "table":
                for child, raw_child in zip(block.content, raw["content"], strict=True):
                    if str(getattr(child, "type", "")) == "table_body":
                        body_only = block.model_copy(update={"content": [child]})
                        raw_child["markdown"] = render_single_block(
                            body_only,
                            delimiters=LatexDelimitersConfig(),
                            asset_base_url="",
                            image_renderer=lambda _parent: "<!-- image -->",
                        )
        except (ValueError, TypeError, KeyError) as exc:
            # This is a derived view failure, not a reason to discard the
            # already returned native block or its valid neighbors. Keep the
            # native fields and let the caller expose the unresolved region.
            # Cancellation, deadlines and resource failures must propagate.
            raw["export_error"] = {
                "code": "native_block_export_invalid",
                "exception_type": type(exc).__name__,
            }
        raw["source_images"] = images
        exported.append(raw)
    return exported


async def _parse(path: Path, page_range: str | None) -> dict[str, Any]:
    from docvortex.document.pdf import PDFDocument
    from mineru.config import VlmConfig
    from mineru.parser import parse_async

    with PDFDocument(str(path)) as source:
        count = len(source)
        if count < 1 or count > MAX_PAGES:
            raise ValueError("PDF page count exceeds worker limits")
        dimensions = {index: source.page_size(index) for index in range(count)}
    started = time.perf_counter()
    result = await parse_async(
        str(path),
        tier="advanced",
        ocr_mode="txt",
        image_analysis=False,
        page_range=page_range or None,
        vlm_config=VlmConfig(
            server_url=VLM_URL,
            model=VLM_MODEL,
            max_concurrency=VLM_CONCURRENCY,
            http_timeout=VLM_TIMEOUT,
        ),
    )
    pages = []
    request = active_request.get()
    if request is not None:
        request.update(phase="document.exporting")
    for page in result.pages:
        index = page.page_idx
        if not isinstance(index, int) or not 0 <= index < count:
            raise RuntimeError("MinerU returned an invalid original PDF page index")
        width, height = dimensions[index]
        pages.append(
            {
                "page_number": index + 1,
                "width": width,
                "height": height,
                "blocks": export_source_blocks(page),
            }
        )
    return {
        "schema": "mineru-native/1",
        "page_count": count,
        "pages": pages,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "backend": "mineru-advanced-txt",
        "versions": _versions,
        "text_matching": _patch,
    }


def _register(request_id: str) -> NativeRequest:
    if request_id in _requests:
        request = _requests[request_id]
        if request.state == "cancelled" and request.cancel_requested:
            raise HTTPException(409, "request was cancelled before upload completed")
        raise HTTPException(409, "request ID already exists; parse POST is not replayable")
    # Keep a bounded terminal history; never evict queued/running ownership.
    for key, value in list(_requests.items()):
        if len(_requests) < 512:
            break
        if value.state in {"completed", "cancelled", "failed", "timed_out"}:
            del _requests[key]
    if len(_requests) >= 512:
        raise HTTPException(503, "native request capacity exceeded")
    request = NativeRequest(request_id)
    _requests[request_id] = request
    return request


@app.get("/requests/{request_id}")
async def request_status(request_id: str) -> dict[str, Any]:
    request = _requests.get(request_id)
    if request is None:
        raise HTTPException(404, "request is not registered")
    return request.snapshot()


@app.post("/requests/{request_id}/cancel")
async def cancel_request(request_id: str) -> dict[str, Any]:
    # A cancel may arrive while multipart upload is still being received. Its
    # tombstone prevents the later POST from starting unowned computation.
    if not 1 <= len(request_id) <= 128:
        raise HTTPException(422, "invalid request ID")
    request = _requests.get(request_id)
    if request is None:
        request = _register(request_id)
        request.update(cancel_requested=True, state="cancelled", phase="cancelled.before_start")
    elif request.state in {"queued", "running", "stopping"}:
        request.update(cancel_requested=True, state="stopping", phase="cancellation.cleanup")
        task = _tasks.get(request_id)
        if task is not None and not task.cancelling():
            task.cancel()
    return request.snapshot()


@app.post("/parse")
async def parse_pdf(
    file: Annotated[UploadFile, File()],
    page_range: Annotated[str | None, Form(max_length=2048)] = None,
    request_id: Annotated[str | None, Form(min_length=1, max_length=128)] = None,
    timeout_seconds: Annotated[float, Form(gt=0, le=86400)] = 7200,
) -> dict[str, Any]:
    if not _ready:
        raise HTTPException(503, "native worker is not initialized")
    request_id = request_id or uuid.uuid4().hex
    request = _register(request_id)
    task = asyncio.create_task(_run_request(file, page_range, request, timeout_seconds))
    _tasks[request_id] = task
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        request.update(cancel_requested=True, state="stopping", phase="cancellation.cleanup")
        if not task.done() and not task.cancelling():
            task.cancel()
        # The lock/temp PDF remain owned until MinerU's cancellation cleanup
        # has drained its threads and closed its own outstanding VLM calls.
        while not task.done():
            try:
                await asyncio.shield(task)
            except (asyncio.CancelledError, HTTPException):
                pass
        request.update(state="cancelled", phase="cancelled")
        raise HTTPException(409, "native request cancelled after cleanup") from None
    finally:
        _tasks.pop(request_id, None)


async def _run_request(
    file: UploadFile, page_range: str | None, request: NativeRequest, timeout_seconds: float
) -> dict[str, Any]:
    token = active_request.set(request)
    try:
        async with asyncio.timeout(timeout_seconds):
            async with _document_lock:
                request.update(state="running", phase="document.preparing")
                return await _parse_upload(file, page_range, request)
    except asyncio.CancelledError as exc:
        request.update(state="cancelled", phase="cancelled")
        raise HTTPException(409, "native request cancelled after cleanup") from exc
    except TimeoutError as exc:
        request.update(state="timed_out", phase="timed_out")
        raise HTTPException(408, "native request deadline exceeded; cleanup completed") from exc
    except Exception:
        request.update(state="failed", phase="failed")
        raise
    finally:
        await file.close()
        active_request.reset(token)


async def _parse_upload(
    file: UploadFile, page_range: str | None, request: NativeRequest
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="moparse-native-") as directory:
        path = Path(directory) / "source.pdf"
        total = 0
        with path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "PDF exceeds worker upload limit")
                output.write(chunk)
        await file.close()
        with path.open("rb") as source:
            if source.read(5) != b"%PDF-":
                raise HTTPException(415, "the native worker only accepts PDF bytes")
        try:
            result = await _parse(path, page_range)
            request.update(state="completed", phase="completed")
            return result
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
