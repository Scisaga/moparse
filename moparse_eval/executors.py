"""Eight fixed research configurations, separate from the production service.

Only a PDF and frozen execution configuration enter these workers. References,
visual-review records and expected outputs are deliberately outside this API.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import importlib.metadata
import io
import json
import math
import os
import resource
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, MutableMapping
from contextlib import nullcontext
from pathlib import Path
from typing import Any, cast

from .adapters import READERS, NativeReadError, glm_regions
from .glm_observation import apply_page_loader_overrides, observe_ocr_requests
from .request_control import RequestControl, RequestStopped, execution_unknown, sample_timeout
from .runtime import (
    MemoryObservation,
    PreparationError,
    actual_worker_limits,
    inspect_local,
    run_batch_worker,
    run_worker,
    validate_execution_config,
)

PIPELINES: dict[str, dict[str, Any]] = {
    "P01": {"family": "docling", "tableformer": "v1", "hybrid": True},
    "P02": {"family": "docling", "tableformer": "v2", "hybrid": True},
    "P03": {"family": "paddle", "model_version": "1.5", "hybrid": False},
    "P04": {"family": "paddle", "model_version": "1.6", "hybrid": False},
    "P05": {"family": "glm", "hybrid": False},
    "P06": {"family": "mineru", "tier": "standard", "hybrid": True},
    "P07": {"family": "mineru", "tier": "advanced", "hybrid": True},
    "P08": {"family": "visual", "hybrid": False},
}


def prepare(config: Mapping[str, Any], **_: Any) -> dict[str, Any]:
    """Non-inference SDK/model metadata inspection; never inspects a PDF."""
    report = inspect_local(config)
    runtime = config.get("runtime", {})
    if runtime.get("kind", "local") != "docker":
        return report
    image = runtime.get("image")
    try:
        image_id = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", str(image)], text=True).strip()
        packages = ["docling", "docling-core", "mineru", "docvortex", "mineru-vl-utils", "glmocr",
                    "paddleocr", "paddlex", "torch", "transformers", "pymupdf"]
        probe = ("import importlib.metadata as m,json;out={};"
                 "\nfor n in " + repr(packages) + ":"
                 "\n try:out[n]=m.version(n)"
                 "\n except m.PackageNotFoundError:out[n]=None"
                 "\nprint(json.dumps(out))")
        versions = json.loads(subprocess.check_output(["docker", "run", "--rm", "--network", "none",
            "--cpus", "1", "--memory", "512m", "--entrypoint", runtime.get("container_python", "python"),
            image_id, "-c", probe], text=True))
        paths = {}
        for key, model in config.get("models", {}).items():
            if not key.endswith("_path"):
                continue
            matches = []
            for host, container in runtime.get("mounts", {}).items():
                model_path, container_path = Path(model), Path(container)
                if model_path.is_relative_to(container_path):
                    matches.append(Path(host) / model_path.relative_to(container_path))
                elif container_path.is_relative_to(model_path):
                    matches.append(Path(host))
            paths[key] = {"path": model, "host_paths": list(map(str, matches)),
                          "exists": bool(matches) and all(path.is_dir() for path in matches)}
            if key in {"orientation_path", "glm_layout_path", "paddle_vlm_path", "paddle_layout_path"}:
                paths[key]["checkpoint_ready"] = bool(matches) and all(
                    (path / "model.safetensors").is_file() for path in matches)
        report.update(image_id=image_id, versions=versions, models=paths)
        family = PIPELINES[config["pipeline"]]["family"]
        required = {"torch", "transformers", "pymupdf"}
        required.update({"docling", "docling-core"} if family == "docling" else set())
        required.update({"mineru", "docvortex", "mineru-vl-utils"} if family == "mineru" else set())
        required.update({"mineru-vl-utils"} if family == "visual" else set())
        required.update({"paddleocr", "paddlex"} if family == "paddle" and config.get("paddle_backend") != "native-rpc" else set())
        if PIPELINES[config["pipeline"]]["hybrid"] or family == "glm":
            required.add("glmocr")
        report["missing_packages"] = sorted(name for name in required if not versions.get(name))
        report["software_ready"] = not report["missing_packages"] and all(
            value["exists"] and value.get("checkpoint_ready", True) for value in paths.values())
        report["execution_ready"] = False
        report["remaining"] = ["bounded GPU capture/inference and resource trial", "independent reference freeze for formal scoring"]
    except (subprocess.CalledProcessError, ValueError) as exc:
        report["software_ready"] = False
        report["preparation_error"] = str(exc)
    return report


async def execute(pdf_path: Path, config: Mapping[str, Any], *, sample_id: str,
                  output_dir: Path) -> dict[str, Any]:
    return await run_worker(pdf_path, config, sample_id=sample_id, output_dir=output_dir)


async def execute_batch(samples: list[Mapping[str, Any]], config: Mapping[str, Any], *,
                        output_dir: Path, inputs_dir: Path | None = None) -> list[dict[str, Any]]:
    """One SDK/model lifecycle for ordered warm-up, quality and repeated timing."""
    return await run_batch_worker(samples, config, output_dir=output_dir, inputs_dir=inputs_dir)


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return _plain(value.to_dict())
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"unhandled native object: {type(value).__name__}")


def _version(package: str, required: str) -> None:
    try:
        actual = importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError as exc:
        raise PreparationError(f"required SDK is not installed: {package}=={required}") from exc
    if actual != required:
        raise PreparationError(f"requires {package}=={required}; installed {actual}")


def _image_bytes(image: Any) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _uri(image: Any) -> str:
    return "data:image/png;base64," + base64.b64encode(_image_bytes(image)).decode("ascii")


class _Assets:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.errors: list[dict[str, Any]] = []

    def image(self, image: Any, prefix: str) -> str:
        path = f"assets/{prefix}-{len(self.data):05}.png"
        self.data[path] = _image_bytes(image)
        return path

    def error(self, exc: Exception, *, stage: str, native_path: str,
              pages: list[int], category: str | None = None) -> dict[str, Any]:
        """An export/readback defect must never masquerade as a model failure."""
        error = {"stage": stage, "native_path": native_path, "scope_pages": list(pages),
                 "type": type(exc).__name__, "message": str(exc), "retry": False,
                 "category": category or ("candidate_native_structure" if isinstance(exc, NativeReadError)
                                          else "engineering_failure"), "native_preserved": True}
        self.errors.append(error)
        return error

    def received_errors(self, errors: Any, *, page: int) -> None:
        """Carry received RPC diagnostics into this worker without editing raw."""
        if not isinstance(errors, list):
            self.error(TypeError("received export diagnostics are not a list"), stage="RPC_diagnostics",
                       native_path="research_export_errors", pages=[page])
            return
        for item in errors:
            if not isinstance(item, Mapping):
                self.error(TypeError("received export diagnostic is not an object"), stage="RPC_diagnostics",
                           native_path="research_export_errors", pages=[page])
                continue
            diagnostic = dict(item)
            diagnostic.setdefault("scope_pages", [page])
            diagnostic.setdefault("category", "engineering_failure")
            diagnostic.setdefault("native_preserved", True)
            diagnostic.setdefault("retry", False)
            if diagnostic not in self.errors:
                self.errors.append(diagnostic)


def _native_snapshot(value: Any, assets: _Assets, *, pages: list[int], pointer: str) -> Any:
    """Serialize siblings independently; unavailable objects remain explicit."""
    if isinstance(value, Mapping):
        return {str(key): _native_snapshot(item, assets, pages=pages, pointer=f"{pointer}/{key}")
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native_snapshot(item, assets, pages=pages, pointer=f"{pointer}/{index}")
                for index, item in enumerate(value)]
    try:
        return _plain(value)
    except Exception as exc:
        error = assets.error(exc, stage="native_serialization", native_path=pointer, pages=pages)
        error["native_preserved"] = False
        return {"research_unserializable_object": type(value).__name__, "research_error": str(exc)}


def _required_model(config: Mapping[str, Any], key: str) -> Path:
    value = config.get("models", {}).get(key)
    if not value or not Path(value).is_dir():
        raise PreparationError(f"an existing frozen model directory is required: models.{key}")
    return Path(value)


class _SDKs:
    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config
        self.spec = PIPELINES[config["pipeline"]]
        self.docling: Any = None
        self.glm: Any = None
        self.paddle: Any = None
        self.paddle_observations: Any = None
        self.visual: Any = None
        self.orientation: Any = None
        self.last_mineru_document: Any = None
        self.initialization_seconds = 0.0
        self.graph_evidence: list[dict[str, Any]] = []
        self.control = RequestControl(config)

    async def initialize(self) -> None:
        started = time.perf_counter()
        self.control.install()
        try:
            import torch
            torch.set_num_threads(8)
            torch.set_num_interop_threads(1)
            from app.services.orientation_service import DocumentOrientationService
            self.orientation = DocumentOrientationService(
                _required_model(self.config, "orientation_path"), allow_download=False)
            await asyncio.to_thread(self.orientation.initialize)
            family = self.spec["family"]
            if family == "docling":
                self._init_docling()
            if self.spec["hybrid"] or family == "glm":
                self._init_glm()
            if family == "paddle":
                self._init_paddle()
            if family == "mineru":
                self._init_mineru()
            if family == "visual":
                self._init_visual()
        except PreparationError:
            raise
        except Exception as exc:
            raise PreparationError(f"SDK initialization failed: {type(exc).__name__}: {exc}") from exc
        self.initialization_seconds = time.perf_counter() - started

    def _init_docling(self) -> None:
        _version("docling", "2.139.0")
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TableFormerMode,
            TableStructureOptions,
            TableStructureV2Options,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption
        table = (TableStructureOptions(mode=TableFormerMode.ACCURATE, do_cell_matching=False)
                 if self.spec["tableformer"] == "v1" else TableStructureV2Options(do_cell_matching=False))
        options = PdfPipelineOptions(
            do_ocr=False, do_table_structure=True, table_structure_options=table,
            artifacts_path=_required_model(self.config, "docling_path"),
            accelerator_options=AcceleratorOptions(device="cpu", num_threads=8),
            generate_picture_images=True, images_scale=200 / 72,
            do_picture_classification=False, do_picture_description=False,
            do_chart_extraction=False, enable_remote_services=False, allow_external_plugins=False,
            document_timeout=float(self.config.get("timeout_seconds", 7200)),
            layout_batch_size=1, table_batch_size=1, ocr_batch_size=1)
        engine = getattr(options.layout_options, "engine_options", None)
        if engine is not None and hasattr(engine, "compile_model"):
            engine.compile_model = False
        self.docling = DocumentConverter(allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(backend=PyPdfiumDocumentBackend,
                                                            pipeline_options=options)})
        # Load the selected CPU models before the processing clock starts.
        self.docling.initialize_pipeline(InputFormat.PDF)

    def _init_glm(self) -> None:
        _version("glmocr", "0.1.5")
        from glmocr import Pipeline
        from glmocr.config import GlmOcrConfig
        endpoint = self.config.get("endpoints", {}).get("glm")
        if not endpoint:
            raise PreparationError("endpoints.glm is required")
        # The dataclass defaults omit the official label/task and prompt maps.
        # Load the bundled, fixed-version YAML directly, never ambient .env.
        config = GlmOcrConfig.from_yaml().pipeline
        config.maas.enabled = False
        config.max_workers = 4
        config.ocr_api.api_url = endpoint
        config.ocr_api.model = self.config.get("glm_model", "zai-org/GLM-OCR")
        config.ocr_api.retry_max_attempts = 0
        config.ocr_api.connection_pool_size = 4
        config.ocr_api.request_timeout = int(self.config.get("timeout_seconds", 7200))
        config.layout.model_dir = str(_required_model(self.config, "glm_layout_path"))
        config.layout.device = "cpu"
        config.layout.workers = 1
        config.layout.batch_size = 1
        config.page_loader.pdf_dpi = 200
        if self.config.get("glm_page_loader"):
            config.page_loader = apply_page_loader_overrides(config.page_loader, self.config["glm_page_loader"])
        # These are SDK formatting options, shared by every GLM branch.
        for key, value in self.config.get("glm_formatter", {}).items():
            if key not in type(config.result_formatter).model_fields:
                raise PreparationError(f"unknown GLM formatter option: {key}")
            setattr(config.result_formatter, key, value)
        self.glm = Pipeline(config)
        self.glm.layout_detector.start()

    def _init_mineru(self) -> None:
        _version("mineru", "4.0.12")
        _version("mineru-vl-utils", "2.0.7")
        os.environ.update({"MINERU_DEVICE_MODE": "cpu", "MINERU_TABLE_DEVICE": "cpu",
                           "MINERU_MODEL_SMALL_BACKEND": "onnx", "MINERU_MODEL_SOURCE": "local",
                           "MINERU_HOME": str(_required_model(self.config, "mineru_small_path")),
                           "MINERU_INTRA_OP_NUM_THREADS": "8", "MINERU_INTER_OP_NUM_THREADS": "1"})
        # This override is confined to the disposable research process. The SDK
        # otherwise retries received failures by default, without idempotency.
        from mineru.model.vlm import runtime
        original = runtime.ModelSingleton._create_model
        def create_once(instance: Any, *args: Any, **kwargs: Any) -> Any:
            kwargs["max_retries"] = 0
            return original(instance, *args, **kwargs)
        runtime.ModelSingleton._create_model = create_once
        from native_worker.patch_dependency import verify_patch, verify_resource_patch
        verify_patch()
        verify_resource_patch()
        from mineru.model.runtime.hybrid import HybridLocalModelContextSingleton
        HybridLocalModelContextSingleton().get_model()

    def _init_visual(self) -> None:
        _version("mineru-vl-utils", "2.0.7")
        from mineru_vl_utils import MinerUClient
        endpoint = self.config.get("endpoints", {}).get("mineru")
        if not endpoint:
            raise PreparationError("endpoints.mineru is required")
        self.visual = MinerUClient(backend="http-client", server_url=endpoint,
            model_name=self.config.get("mineru_model", "mineru2.5-pro"), max_concurrency=4,
            max_retries=0, image_analysis=False, abandon_paratext=False,
            abandon_list=False, enable_cross_page_table_merge=False,
            http_timeout=int(self.config.get("timeout_seconds", 7200)), use_tqdm=False)

    def _init_paddle(self) -> None:
        if self.config.get("paddle_backend") == "native-rpc":
            endpoint = self.config.get("endpoints", {}).get("paddle")
            if not endpoint:
                raise PreparationError("endpoints.paddle is required for the isolated native inference service")
            self.paddle = endpoint.rstrip("/")
            return
        _version("paddleocr", str(self.config.get("versions", {}).get("paddleocr", "3.7.0")))
        _version("paddlex", str(self.config.get("versions", {}).get("paddlex", "3.7.2")))
        from paddleocr import PaddleOCRVL
        version = self.spec["model_version"]
        backend = self.config.get("paddle_backend", "native-transformers")
        options: dict[str, Any] = dict(pipeline_version=f"v{version}",
            vl_rec_model_name=f"PaddleOCR-VL-{version}-0.9B",
            vl_rec_model_dir=str(_required_model(self.config, "paddle_vlm_path")),
            layout_detection_model_name="PP-DocLayoutV3",
            layout_detection_model_dir=str(_required_model(self.config, "paddle_layout_path")),
            use_doc_orientation_classify=False, use_doc_unwarping=False,
            use_chart_recognition=False, use_ocr_for_image_block=False,
            markdown_ignore_labels=[], merge_layout_blocks=False)
        if backend == "native-transformers":
            _version("transformers", str(self.config.get("versions", {}).get("paddle_transformers", "5.10.2")))
            import torch
            if not torch.cuda.is_available():
                raise PreparationError("native Paddle requires the isolated GPU 1 worker")
            gpu_gib = float(self.config.get("resources", {}).get("gpu_memory_gib", 16))
            torch.cuda.set_per_process_memory_fraction(gpu_gib * 1024 ** 3 / torch.cuda.get_device_properties(0).total_memory)
            options.update(vl_rec_backend="native", engine="transformers", device="gpu:0",
                           engine_config={"dtype": "float16", "trust_remote_code": False,
                                          "attn_implementation": "sdpa"})
            from paddlex.inference import load_pipeline_config
            native_config = copy.deepcopy(load_pipeline_config(f"PaddleOCR-VL-{version}"))
            # HGNetV2Backbone has no SDPA implementation. The official child
            # configuration overrides only this layout attention option;
            # native VLM SDPA and independent CUDA Graph trials remain enabled.
            native_config["SubModules"]["LayoutDetection"].setdefault("engine_config", {})[
                "attn_implementation"] = None
            options["paddlex_config"] = native_config
            from .cuda_graphs import install_paddle_trials
            install_paddle_trials(self.graph_evidence, admission=self.control.check)
            from .paddle_compat import install_paddle_compat
            self.paddle_observations = install_paddle_compat(config=self.config)
        elif backend == "vllm-server":
            endpoint = self.config.get("endpoints", {}).get("paddle")
            if not endpoint:
                raise PreparationError("endpoints.paddle is required")
            options.update(vl_rec_backend="vllm-server", vl_rec_server_url=endpoint,
                           vl_rec_api_model_name=f"PaddleOCR-VL-{version}",
                           vl_rec_max_concurrency=4, device="cpu")
        else:
            raise PreparationError("paddle_backend must explicitly select native-transformers or vllm-server")
        self.paddle = PaddleOCRVL(**options)

    async def close(self) -> None:
        try:
            if self.visual is not None:
                await self.visual.aclose()
            if self.glm is not None:
                await asyncio.to_thread(self.glm.stop)
            if self.spec["family"] == "mineru":
                from mineru.model.vlm.runtime import shutdown_cached_models
                await asyncio.to_thread(shutdown_cached_models)
        finally:
            self.control.close()


def _route(page: Any, policy: Mapping[str, Any]) -> str:
    """Frozen runtime observation, never an annotation or expected-output label."""
    required = {"minimum_native_characters", "scan_image_coverage", "mixed_image_coverage"}
    if not required.issubset(policy):
        raise PreparationError("hybrid configurations require a frozen source_policy with explicit thresholds")
    words = page.get_text("text")
    count = sum(not char.isspace() for char in words)
    # Image rectangles are in unrotated, crop-relative page coordinates.
    # Page.rect alone reflects /Rotate; cropbox alone also includes its offset.
    bounds = page.rect * page.derotation_matrix
    page_area = bounds.width * bounds.height
    # Runtime routing only; these observations never become review labels.
    rectangles = [bounds & box for item in page.get_images(full=True)
                  for box in page.get_image_rects(item[0])]
    rectangles = [box for box in rectangles if not box.is_empty and not box.is_infinite]
    xs = sorted({x for rectangle in rectangles for x in (rectangle.x0, rectangle.x1)})
    union_area = 0.0
    for left, right in zip(xs, xs[1:], strict=False):
        spans = sorted((rect.y0, rect.y1) for rect in rectangles if rect.x0 < right and rect.x1 > left)
        covered, bottom = 0.0, float("-inf")
        for top, end in spans:
            covered += max(0.0, end - max(top, bottom))
            bottom = max(bottom, end)
        union_area += (right - left) * covered
    coverage = min(1.0, union_area / page_area) if page_area else 0.0
    if count < int(policy["minimum_native_characters"]):
        return "scan" if coverage >= float(policy["scan_image_coverage"]) else "unknown"
    return "mixed" if coverage >= float(policy["mixed_image_coverage"]) else "native"


async def _preprocess(pdf_path: Path, config: Mapping[str, Any], sdks: _SDKs,
                      directory: Path) -> tuple[Path, list[dict[str, Any]]]:
    import pymupdf
    from PIL import Image
    source = pymupdf.open(pdf_path)
    pages = []
    try:
        for index in range(source.page_count):
            page = source[index]
            sdks.control.check()
            original_rotation = page.rotation
            original_cropbox = list(page.cropbox)
            route = _route(page, config.get("source_policy", {})) if sdks.spec["hybrid"] else "not_used"
            pixmap = page.get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            uri, rotation, confidence = await asyncio.to_thread(sdks.orientation.orient, _uri(image))
            corrected = Image.open(io.BytesIO(base64.b64decode(uri.partition(",")[2]))).convert("RGB")
            page.set_rotation((original_rotation + rotation) % 360)
            pages.append({"page": index + 1, "source_prediction": route, "rotation_clockwise": rotation,
                          "pdf_original_rotation_clockwise": original_rotation,
                          "pdf_effective_rotation_clockwise": page.rotation,
                          "pdf_original_cropbox": original_cropbox,
                          "orientation_confidence": confidence, "image": corrected,
                          "width": corrected.width, "height": corrected.height})
        path = directory / "oriented.pdf"
        source.save(path)
    finally:
        source.close()
    return path, pages


def _crop(image: Any, bbox: Any) -> Any:
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        raise NativeReadError("native image has no explicit four-coordinate bbox")
    left, top, right, bottom = bbox
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) for value in bbox):
        raise NativeReadError("native image bbox must contain finite numeric coordinates")
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise NativeReadError("native image bbox is outside the normalized input page")
    return image.crop((left * image.width, top * image.height,
                       right * image.width, bottom * image.height))


def _glm_page(sdks: _SDKs, page: dict[str, Any], assets: _Assets,
              telemetry_dir: Path | None = None) -> tuple[dict[str, Any], str]:
    request = {"messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": _uri(page["image"])}}]}]}
    observation = (observe_ocr_requests(sdks.glm.ocr_client, telemetry_dir,
        page_number=page["page"], task_prompt_mapping=sdks.glm.config.page_loader.task_prompt_mapping)
        if telemetry_dir is not None else nullcontext())
    with observation:
        results = list(sdks.glm.process(request))
    if len(results) != 1:
        raise RuntimeError("GLM SDK did not return one result for the submitted page")
    result = results[0]
    raw = {"json_result": _plain(result.json_result), "markdown_result": result.markdown_result,
           "raw_json_result": _plain(result.raw_json_result),
           "original_images": _plain(result.original_images), "image_files": {}}
    markdown = result.markdown_result or ""
    for name, image in (result.image_files or {}).items():
        try:
            path = assets.image(image, f"p{page['page']}-glm")
        except Exception as exc:
            raw.setdefault("research_export_errors", []).append(assets.error(
                exc, stage="media_export", native_path=f"image_files/{name}", pages=[page["page"]]))
            continue
        raw["image_files"][name] = path
        markdown = markdown.replace(f"imgs/{name}", path) if f"imgs/{name}" in markdown else markdown.replace(name, path)
    if raw["raw_json_result"] is not None:
        # Formatter indices are renumbered, and text/formula regions may be
        # merged. There is no explicit cross-view identity contract. Preserve
        # the full raw stage independently instead of deduplicating by text
        # or geometry and accidentally deleting available native content.
        try:
            regions = glm_regions(raw["raw_json_result"], "raw_json_result")
        except NativeReadError as exc:
            raw.setdefault("research_export_errors", []).append(assets.error(
                exc, stage="audit_stage_export", native_path="raw_json_result", pages=[page["page"]]))
            regions = []
        parts = []
        for pointer, region in regions:
            if not isinstance(region, Mapping):
                raw.setdefault("research_export_errors", []).append(assets.error(
                    NativeReadError("non-object native GLM region"), stage="audit_stage_export",
                    native_path=pointer, pages=[page["page"]]))
            elif isinstance(region.get("content"), str):
                parts.append(region["content"])
        raw_markdown = "\n\n".join(parts)
        raw["research_raw_stage_markdown"] = raw_markdown
        raw["research_cross_view_order"] = "unknown; no explicit stable region identity across formatter"
        markdown += ("\n\n<!-- source_view=raw_json_result; independent stage; cross_view_order=unknown -->\n\n"
                     + raw_markdown)
    return raw, markdown


def _docling_markdown(document: Any, native: dict[str, Any], assets: _Assets) -> str:
    from docling_core.types.doc import ContentLayer, ImageRefMode

    options = {"image_mode": ImageRefMode.REFERENCED, "included_content_layers": set(ContentLayer),
               "include_picture_classification": False}
    pages = native["research_group_pages"]

    def error(exc: Exception, pointer: str) -> None:
        native.setdefault("research_export_errors", []).append(assets.error(
            exc, stage="faithful_export", native_path=pointer, pages=pages))

    try:
        return document.export_to_markdown(**options)
    except Exception as exc:
        error(exc, "document")
    # Fixed-version SDK slices use the reading-tree traversal with groups and
    # picture descendants. Bisect only failed export ranges, never reparse or
    # rewrite their content. Successful ranges retain SDK order and formatting.
    try:
        items = list(document.iterate_items(with_groups=True, traverse_pictures=True,
                                           included_content_layers=set(ContentLayer)))
    except Exception as exc:
        error(exc, "document/reading_tree")
        return ""

    def export_range(start: int, stop: int) -> list[str]:
        if start >= stop:
            return []
        try:
            return [document.export_to_markdown(from_element=start, to_element=stop, **options)]
        except Exception as exc:
            if stop - start == 1:
                ref = str(getattr(items[start][0], "self_ref", f"/item/{start}"))
                error(exc, "document" + ref.removeprefix("#"))
                return []
            middle = (start + stop) // 2
            return export_range(start, middle) + export_range(middle, stop)

    return "\n\n".join(part for part in export_range(0, len(items)) if part)


def _docling_run(sdks: _SDKs, path: Path, pages: list[dict[str, Any]],
                  assets: _Assets, output: dict | None = None) -> dict[int, tuple[dict[str, Any], str]]:
    output = output if output is not None else {}
    native_indices = [page["page"] for page in pages if page["source_prediction"] == "native"]
    # Contiguous groups retain the context available to the declared native branch.
    groups: list[list[int]] = []
    for index in native_indices:
        if groups and groups[-1][-1] + 1 == index:
            groups[-1].append(index)
        else:
            groups.append([index])
    for group in groups:
        sdks.control.check()
        conversion = sdks.docling.convert(path, page_range=(group[0], group[-1]), raises_on_error=False)
        document = conversion.document
        try:
            document_snapshot = document.export_to_dict()
        except Exception as exc:
            assets.error(exc, stage="native_serialization", native_path="document", pages=group)
            document_snapshot = _native_snapshot(document, assets, pages=group, pointer="document")
        native = {"document": document_snapshot, "status": str(conversion.status),
                  "errors": _native_snapshot(conversion.errors or [], assets, pages=group,
                                             pointer="errors"), "research_assets": {},
                  "research_group_pages": list(group)}
        # Register the received native object before any media or view export.
        for page in group:
            output[page] = (native, "")
        for index, picture in enumerate(document.pictures or []):
            picture_ref = getattr(picture, "self_ref", f"#/pictures/{index}")
            try:
                image = picture.get_image(document)
                if image is not None:
                    ref = assets.image(image, "docling")
                    native["research_assets"][picture_ref] = ref
                    # Only the live export view changes; native snapshot keeps
                    # original media locations even if URI assignment fails.
                    picture.image.uri = ref
            except Exception as exc:
                native.setdefault("research_export_errors", []).append(assets.error(
                    exc, stage="media_export", native_path="document" + picture_ref.removeprefix("#"),
                    pages=group))
        # A multi-page native object must not be re-exported for each physical
        # provenance page. Export this contiguous native group once in its
        # actual reading-tree order, with all content layers, then interleave
        # whole native groups with their neighboring GLM pages.
        markdown = _docling_markdown(document, native, assets)
        for page in group:
            output[page] = (native, markdown if page == group[0] else "")
    return output


async def _mineru_run(sdks: _SDKs, path: Path, pages: list[dict[str, Any]],
                       assets: _Assets, output: dict | None = None) -> dict[int, tuple[dict[str, Any], str]]:
    from docvortex.options import LatexDelimitersConfig
    from docvortex.render.markdown import render_single_block
    from mineru.config import VlmConfig
    from mineru.parser import parse_async
    selected = [page["page"] for page in pages if page["source_prediction"] == "native"]
    if not selected:
        return {}
    sdks.control.check()
    endpoint = sdks.config.get("endpoints", {}).get("mineru")
    if not endpoint:
        raise PreparationError("endpoints.mineru is required")
    result = await parse_async(path, tier=sdks.spec["tier"], ocr_mode="txt", image_analysis=False,
                              page_range=",".join(map(str, selected)), vlm_config=VlmConfig(
                                  server_url=endpoint, model=sdks.config.get("mineru_model", "mineru2.5-pro"),
                                  max_concurrency=4, http_timeout=int(sdks.config.get("timeout_seconds", 7200))))
    sdks.last_mineru_document = _native_snapshot(result.middle_json, assets, pages=selected,
                                               pointer="middle_json")
    output = output if output is not None else {}
    for native_page in result.pages:
        physical = native_page.page_idx + 1
        image = pages[physical - 1]["image"]
        raw_blocks: list[Any] = []
        markdown_parts = []
        native = {"page_idx": native_page.page_idx, "blocks": raw_blocks}
        output[physical] = (native, "")
        for index, block in enumerate(native_page.blocks):
            pointer = f"blocks/{index}"
            raw = _native_snapshot(block, assets, pages=[physical], pointer=pointer)
            raw_blocks.append(raw)
            if not isinstance(raw, dict):
                assets.error(NativeReadError("native block is not an object"), stage="faithful_export",
                             native_path=pointer, pages=[physical])
                continue
            block_images: list[str] = []
            image_bindings: dict[int, str] = {}
            def render_image(parent: Any, *, image=image, physical=physical,
                             block_images=block_images, image_bindings=image_bindings,
                             raw=raw, pointer=pointer) -> str:
                try:
                    path = assets.image(_crop(image, parent.bbox), f"p{physical}-mineru")
                except Exception as exc:
                    raw.setdefault("research_export_errors", []).append(assets.error(
                        exc, stage="media_export", native_path=pointer, pages=[physical]))
                    return ""
                block_images.append(path)
                image_bindings[id(parent)] = path
                return "![](" + path + ")"

            def render_part(original: Any, view: Any, native_path: str, *,
                            renderer=render_image, physical=physical) -> str:
                try:
                    return render_single_block(original, delimiters=LatexDelimitersConfig(),
                                               asset_base_url="", image_renderer=renderer)
                except Exception as exc:
                    error = assets.error(exc, stage="faithful_export", native_path=native_path,
                                         pages=[physical])
                    if isinstance(view, dict):
                        view.setdefault("research_export_errors", []).append(error)
                    children = getattr(original, "content", None)
                    child_views = view.get("content") if isinstance(view, dict) else None
                    if isinstance(children, list) and isinstance(child_views, list):
                        return "\n\n".join(render_part(child, child_view, f"{native_path}/content/{n}")
                            for n, (child, child_view) in enumerate(zip(children, child_views, strict=False)))
                    return ""

            md = render_part(block, raw, pointer)
            raw["markdown"] = md
            raw["research_assets"] = block_images
            def bind_media(original: Any, view: dict[str, Any], *, image_bindings=image_bindings) -> None:
                if id(original) in image_bindings:
                    view["research_asset"] = image_bindings[id(original)]
                children = getattr(original, "content", None)
                if isinstance(children, list) and isinstance(view.get("content"), list):
                    for child, child_view in zip(children, view["content"], strict=False):
                        if isinstance(child_view, dict):
                            bind_media(child, child_view)
            bind_media(block, raw)
            markdown_parts.append(md)
            output[physical] = (native, "\n\n".join(markdown_parts))
    return output


async def _visual_page(sdks: _SDKs, page: dict[str, Any], assets: _Assets) -> tuple[Any, str]:
    from mineru_vl_utils.post_process.json2markdown import json2md
    result = await sdks.visual.aio_two_step_extract(page["image"], image_analysis=False)
    raw = _native_snapshot(result, assets, pages=[page["page"]], pointer="blocks")
    if not isinstance(raw, list):
        raise TypeError("pure-visual SDK result is not a block sequence")
    export, parts = [], []
    for index, item in enumerate(raw):
        pointer = f"blocks/{index}"
        if not isinstance(item, Mapping):
            assets.error(NativeReadError("native visual region is not an object"), stage="faithful_export",
                         native_path=pointer, pages=[page["page"]])
            continue
        # _native_snapshot materializes received mappings as mutable views.
        item = cast(MutableMapping[str, Any], item)
        block = dict(item)
        if block.get("type") in {"image", "chart"}:
            try:
                ref = assets.image(_crop(page["image"], block.get("bbox")), f"p{page['page']}-visual")
                block["content"] = f"![]({ref})"
                item["research_asset"] = ref
            except Exception as exc:
                item.setdefault("research_export_errors", []).append(assets.error(
                    exc, stage="media_export", native_path=pointer, pages=[page["page"]]))
                # Keep the untouched native location and continue with other blocks.
                continue
        try:
            md = json2md([block])
            item["research_export_markdown"] = md
            parts.append(md)
            export.append(block)
        except Exception as exc:
            item.setdefault("research_export_errors", []).append(assets.error(
                exc, stage="faithful_export", native_path=pointer, pages=[page["page"]]))
    try:
        return raw, json2md(export)
    except Exception as exc:
        assets.error(exc, stage="faithful_export", native_path="blocks", pages=[page["page"]])
        return raw, "\n\n".join(part for part in parts if part)


def _paddle_page(sdks: _SDKs, page: dict[str, Any], assets: _Assets) -> tuple[dict[str, Any], str]:
    if sdks.config.get("paddle_backend") == "native-rpc":
        import httpx
        payload = {"request_id": uuid.uuid4().hex, "page": page["page"],
                   "image_base64": base64.b64encode(_image_bytes(page["image"])).decode("ascii")}
        control = getattr(sdks, "control", None)
        if control is not None and control.deadline is not None:
            payload["deadline_monotonic"] = control.deadline
        with httpx.Client(timeout=float(sdks.config.get("timeout_seconds", 7200)), trust_env=False) as client:
            response = client.post(sdks.paddle + "/parse-page", json=payload)
            if response.status_code >= 400:
                try:
                    failure = response.json()
                except ValueError:
                    failure = {}
                if failure.get("error") == "PreparationError":
                    raise PreparationError(failure.get("message", "native Paddle preparation failed"))
                if failure.get("error") in {"OutOfMemoryError", "MemoryError"}:
                    raise MemoryError(failure.get("message", "native Paddle memory budget exhausted"))
            response.raise_for_status()
            result = response.json()
        if result.get("request_id") != payload["request_id"]:
            raise RuntimeError("native Paddle response lost request ownership")
        raw, markdown = result["raw"], result["faithful_markdown"]
        raw["research_inference_runtime"] = result["inference_runtime"]
        assets.received_errors(raw.get("research_export_errors", []), page=page["page"])
        for name, encoded in result["media"].items():
            try:
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts or not name.startswith("assets/"):
                    raise RuntimeError("native Paddle returned an invalid media path")
                assets.data[name] = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raw.setdefault("research_export_errors", []).append(assets.error(
                    exc, stage="media_export", native_path=f"media/{name}", pages=[page["page"]]))
        return raw, markdown
    import numpy as np
    use_queues = sdks.config.get("paddle_use_queues", False)
    if not isinstance(use_queues, bool):
        raise PreparationError("paddle_use_queues must be a boolean")
    results = sdks.paddle.predict(np.array(page["image"])[:, :, ::-1],
                                 use_doc_orientation_classify=False, use_doc_unwarping=False,
                                 use_chart_recognition=False, markdown_ignore_labels=[],
                                 use_queues=use_queues)
    if len(results) != 1:
        raise RuntimeError("Paddle did not return exactly one result for the submitted image")
    result = results[0]
    raw = _plain(result.json)
    try:
        view = result.markdown
    except Exception as exc:
        raw.setdefault("research_export_errors", []).append(assets.error(
            exc, stage="faithful_export", native_path="markdown", pages=[page["page"]]))
        view = {}
    markdown = view.get("markdown_texts", "")
    media = {}
    for name, image in view.get("markdown_images", {}).items():
        try:
            path = assets.image(image, f"p{page['page']}-paddle")
        except Exception as exc:
            raw.setdefault("research_export_errors", []).append(assets.error(
                exc, stage="media_export", native_path=f"markdown_images/{name}", pages=[page["page"]]))
            continue
        media[name] = path
        markdown = markdown.replace(name, path)
    raw["research_media"] = media
    raw["research_region_media"] = {}
    raw["research_region_exports"] = {}
    # Preserve the fixed SDK's own per-block export, rather than manufacture
    # heading levels from producer labels in the evaluator.
    try:
        handlers = result._build_handle_funcs_dict(pretty=True)
    except Exception as exc:
        raw.setdefault("research_export_errors", []).append(assets.error(
            exc, stage="faithful_export", native_path="region_handlers", pages=[page["page"]]))
        handlers = {}
    region_exports = []
    for index, region in enumerate(result["parsing_res_list"]):
        if not hasattr(region, "label"):
            raw.setdefault("research_export_errors", []).append(assets.error(
                NativeReadError("native Paddle region has no label"), stage="faithful_export",
                native_path=f"parsing_res_list/{index}", pages=[page["page"]]))
            continue
        try:
            if region.label in handlers:
                exported = handlers[region.label](region)
                if isinstance(exported, str):
                    for name, path in media.items():
                        exported = exported.replace(name, path)
                    raw["research_region_exports"][str(index)] = exported
                    region_exports.append(exported)
        except Exception as exc:
            raw.setdefault("research_export_errors", []).append(assets.error(
                exc, stage="faithful_export", native_path=f"parsing_res_list/{index}", pages=[page["page"]]))
        image_info = getattr(region, "image", None)
        if isinstance(image_info, Mapping) and image_info.get("path") in media:
            raw["research_region_media"][str(index)] = media[image_info["path"]]
    return raw, markdown or "\n\n".join(region_exports)


async def _owned_thread(function: Any, *args: Any) -> Any:
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()
            # Keep original execution owned. A cancelled caller never starts a retry.
            continue


async def execute_in_worker(pdf_path: Path, config: Mapping[str, Any], *, sample_id: str,
                            output_dir: Path, _sdks: _SDKs | None = None) -> dict[str, Any]:
    validate_execution_config(config)
    owns_sdks = _sdks is None
    sdks = _sdks or _SDKs(config)
    if owns_sdks:
        await sdks.initialize()
    assets = _Assets()
    native: dict[str, Any] = {"pipeline": config["pipeline"], "config": dict(config), "pages": [], "documents": []}
    document_registry: dict[int, int] = {}
    observation: dict[str, Any] = {"sample_id": sample_id, "pipeline": config["pipeline"],
        "status": "completed", "pages": [], "relations": [], "native_containers": [],
        "assets": [], "timing": {}, "errors": []}
    if sdks.spec["hybrid"] or sdks.spec["family"] == "glm":
        observation["runtime"] = {"native_view_policy": {"glm": {
            "primary_scoring_view": "json_result", "audit_view": "raw_json_result",
            "cross_view_order": "unknown", "audit_view_eligible_for_scoring": False}}}
    emitted_native: set[str] = set()
    markdown_pages: list[str] = []
    stage_files: dict[str, bytes] = {}
    started = time.perf_counter()
    cpu_started = resource.getrusage(resource.RUSAGE_SELF)
    processing_memory = MemoryObservation()
    processing_memory.__enter__()
    if sdks.spec["family"] == "paddle" and config.get("paddle_backend", "native-transformers") == "native-transformers":
        import torch
        torch.cuda.reset_peak_memory_stats()
    deadline = started + float(config.get("timeout_seconds", 7200))
    sdks.control.start(deadline)
    try:
        with tempfile.TemporaryDirectory(prefix="moparse-eval-") as temporary:
            with MemoryObservation() as preprocessing_memory:
                try:
                    path, pages = await _preprocess(pdf_path, config, sdks, Path(temporary))
                except RequestStopped as exc:
                    path, pages = Path(temporary) / "not-produced.pdf", []
                    observation["status"] = sdks.control.stopped() or "cancelled"
                    observation["errors"].append({"stage": "shared_preprocessing", "type": type(exc).__name__,
                        "message": str(exc), "category": "cooperative_deadline_or_cancellation", "retry": False})
                    observation["pages"] = [{"page": page, "status": "not_processed", "blocks": []}
                        for page in range(1, int(config.get("input_page_count", 0)) + 1)]
            if preprocessing_memory.peak_bytes is not None and preprocessing_memory.peak_bytes > 8 * 1024 ** 3:
                sdks.control.reason = "resource_failed"
                observation["status"] = "resource_failed"
                observation["errors"].append({"stage": "shared_preprocessing", "type": "MemoryError",
                    "message": "preprocessing exceeded the declared 8 GiB host-memory budget",
                    "category": "candidate_resource_failure", "retry": False})
            observation["resources"] = {
                "allocation": config.get("actual_allocation", {"stage_isolation": "unverified_local"}),
                "actual_worker_limits": actual_worker_limits(),
                "preprocessing_peak_process_rss_bytes": preprocessing_memory.peak_bytes,
                "preprocessing_memory_observation": "process RSS sampled every 20 ms; not a separate hard cgroup limit",
                "cuda_graphs": config.get("graphs", {"status": "pending_bounded_trial"})}
            native["page_processing"] = [{key: value for key, value in page.items() if key != "image"}
                                         for page in pages]
            family = sdks.spec["family"]
            produced: dict[int, tuple[dict[str, Any], str]] = {}
            native_error = None
            try:
                if pages and family == "docling":
                    await _owned_thread(_docling_run, sdks, path, pages, assets, produced)
                elif pages and family == "mineru":
                    await _mineru_run(sdks, path, pages, assets, produced)
            except PreparationError:
                raise
            except Exception as exc:
                native_error = exc
                observation["status"] = "partial"
                observation["errors"].append({"stage": family, "type": type(exc).__name__,
                    "message": str(exc), "retry": False, "native_preserved": bool(produced),
                    "preserved_pages": sorted(produced), "category":
                        "cooperative_deadline_or_cancellation" if isinstance(exc, RequestStopped) else
                        "remote_execution_unknown" if execution_unknown(exc) else
                        "candidate_resource_failure" if isinstance(exc, MemoryError)
                            or type(exc).__name__ == "OutOfMemoryError" else "candidate_execution_failure"})
                if execution_unknown(exc):
                    sdks.control.failed(exc)
                elif isinstance(exc, MemoryError) or type(exc).__name__ == "OutOfMemoryError":
                    sdks.control.reason = "resource_failed"
            if getattr(sdks, "last_mineru_document", None) is not None:
                native["documents"].append(sdks.last_mineru_document)
                sdks.last_mineru_document = None
            for page in pages:
                number = page["page"]
                branch = family
                if sdks.spec["hybrid"] and page["source_prediction"] != "native":
                    branch = "glm"
                # An expired deadline closes admission, not access to real
                # results already returned by whole-group native parsers.
                stop_reason = sdks.control.stopped()
                has_native = branch in {"docling", "mineru"} and number in produced
                if stop_reason and not has_native:
                    submitted_failure = branch in {"docling", "mineru"} and native_error is not None and not isinstance(native_error, RequestStopped)
                    status = ("execution_unknown" if stop_reason == "execution_unknown" else "failed") if submitted_failure else "not_processed"
                    observation["pages"].append({"page": number, "status": status, "blocks": [],
                        "branch": branch, "stop_reason": stop_reason})
                    continue
                try:
                    if branch == "glm":
                        telemetry = (output_dir / "telemetry" / f"p{number:04}-glm"
                            if config.get("glm_request_observation", False) else None)
                        raw, md = await _owned_thread(_glm_page, sdks, page, assets, telemetry)
                    elif branch == "paddle":
                        raw, md = await _owned_thread(_paddle_page, sdks, page, assets)
                    elif branch == "visual":
                        raw, md = await _visual_page(sdks, page, assets)
                    else:
                        if number not in produced:
                            if native_error is not None:
                                raise native_error
                            raise RuntimeError("native backend did not return the submitted physical page")
                        raw, md = produced[number]
                    artifact_raw = raw
                    pointer = f"#/pages/{len(native['pages'])}/raw"
                    if branch == "docling":
                        key = id(raw)
                        if key not in document_registry:
                            document_registry[key] = len(native["documents"])
                            native["documents"].append(raw)
                        pointer = f"#/documents/{document_registry[key]}"
                        artifact_raw = {"native_document": pointer, "source_page": number}
                    elif branch == "mineru":
                        artifact_raw["native_document"] = "#/documents/0"
                    native["pages"].append({"page": number, "branch": branch, "raw": artifact_raw,
                                            "faithful_markdown": md})
                    if branch == "docling":
                        native["pages"][-1]["faithful_scope_pages"] = raw["research_group_pages"] if md else []
                    if branch == "glm" and raw.get("research_raw_stage_markdown") is not None:
                        stage_path = f"views/p{number:04}-glm-raw.md"
                        stage_files[stage_path] = raw["research_raw_stage_markdown"].encode("utf-8")
                        try:
                            raw_reader = cast(Callable[..., list[dict[str, Any]]], READERS["glm"])
                            raw_blocks = raw_reader(raw, number, pointer, source_view="raw_json_result",
                                page_dimensions={"width": page["width"], "height": page["height"], "unit": "pixel"})
                            observation.setdefault("stage_views", []).append({"source_view": "raw_json_result",
                                "primary_source_view": "json_result", "page": number, "path": stage_path,
                                "cross_view_order": "unknown", "eligible_for_scoring": False, "blocks": raw_blocks})
                        except Exception as exc:
                            observation["errors"].append({"page": number, "stage": "raw_native_readback",
                                "type": type(exc).__name__, "message": str(exc), "retry": False,
                                "category": "candidate_native_structure" if isinstance(exc, NativeReadError)
                                    else "engineering_failure", "native_preserved": True})
                    readback_status = "completed"
                    try:
                        reader = cast(Callable[..., list[dict[str, Any]]], READERS[branch])
                        blocks = reader(raw, number, pointer, emitted=emitted_native,
                            containers=observation["native_containers"],
                            page_dimensions={"width": page["width"], "height": page["height"], "unit": "pixel"})
                    except NativeReadError as exc:
                        blocks = []
                        readback_status = "candidate_partial"
                        if observation["status"] == "completed":
                            observation["status"] = "partial"
                        observation["errors"].append({"page": number, "stage": "native_readback",
                            "type": type(exc).__name__, "message": str(exc), "retry": False,
                            "category": "candidate_native_structure", "native_preserved": True})
                    except Exception as exc:
                        blocks = []
                        readback_status = "readback_failed"
                        observation["status"] = "readback_failed"
                        observation["errors"].append({"page": number, "stage": "native_readback",
                            "type": type(exc).__name__, "message": str(exc), "retry": False,
                            "category": "engineering_failure", "native_preserved": True})
                    if branch == "docling" and any(marker in str(raw.get("status", "")).lower()
                                                    for marker in ("failure", "partial_success")):
                        readback_status = "partial" if blocks else "failed"
                        observation["status"] = "partial"
                        observation["errors"].append({"page": number, "stage": "docling",
                            "category": "candidate_reported_failure", "native_status": raw.get("status"),
                            "native_errors": raw.get("errors", []), "retry": False})
                    reader_errors = []
                    for block in blocks:
                        if block.get("read_error"):
                            reader_errors.append({"category": block.get("read_error_category", "engineering_failure"),
                                "native_path": block.get("native_path"), "message": block["read_error"]})
                        reader_errors.extend(block.get("read_errors", []))
                    if reader_errors:
                        engineering = any(error.get("category") != "candidate_native_structure"
                                          for error in reader_errors)
                        readback_status = "readback_partial" if engineering else "candidate_partial"
                        if engineering:
                            observation["status"] = "readback_failed"
                        elif observation["status"] == "completed":
                            observation["status"] = "partial"
                        observation["errors"].extend({"page": number, "stage": "native_readback",
                            "native_preserved": True, "retry": False, **error} for error in reader_errors)
                    observation["pages"].append({"page": number, "status": readback_status, "branch": branch,
                                                 "blocks": blocks, "width": page["width"], "height": page["height"]})
                    if readback_status == "candidate_partial":
                        observation["pages"][-1]["structure_status"] = "unknown"
                    if time.perf_counter() >= deadline:
                        observation["pages"][-1]["completed_after_deadline"] = True
                        if readback_status == "completed":
                            observation["pages"][-1]["status"] = "late"
                    if branch == "paddle" and isinstance(raw, Mapping) and raw.get("research_inference_runtime"):
                        observation["pages"][-1]["inference_runtime"] = raw["research_inference_runtime"]
                    markdown_pages.append(md)
                except PreparationError:
                    raise
                except Exception as exc:
                    unknown = execution_unknown(exc) or sdks.control.unknown
                    resource_failed = isinstance(exc, MemoryError) or type(exc).__name__ == "OutOfMemoryError"
                    if unknown:
                        sdks.control.failed(exc)
                    elif resource_failed:
                        sdks.control.reason = "resource_failed"
                    observation["status"] = "execution_unknown" if unknown else "resource_failed" if resource_failed else "partial"
                    observation["errors"].append({"page": number, "stage": branch,
                        "type": type(exc).__name__, "message": str(exc), "retry": False,
                        "category": "remote_execution_unknown" if unknown else
                            "candidate_resource_failure" if resource_failed else "candidate_execution_failure"})
                    observation["pages"].append({"page": number,
                        "status": "execution_unknown" if unknown else "failed", "blocks": []})
                if time.perf_counter() >= deadline:
                    observation["status"] = "timed_out"
        stop_reason = sdks.control.stopped()
        if stop_reason == "execution_unknown":
            observation["status"] = "execution_unknown"
            observation["remote_ownership"] = "owned_until_experimental_inference_process_exit"
        elif stop_reason in {"cancelled", "timed_out", "resource_failed"}:
            observation["status"] = stop_reason
        elif stop_reason == "received_failure":
            observation["status"] = "partial"
        if sdks.control.events:
            observation["errors"].extend({"stage": "SDK_http_transport", "category":
                "remote_execution_unknown" if event.get("execution_unknown") else "received_remote_failure", **event}
                for event in sdks.control.events)
        if assets.errors:
            native["research_export_errors"] = list(assets.errors)
            observation["errors"].extend(assets.errors)
            for page in observation["pages"]:
                local = [error for error in assets.errors if page["page"] in error["scope_pages"]]
                if local:
                    engineering = any(error["category"] != "candidate_native_structure" for error in local)
                    page["export_status"] = "partial" if engineering else "native_structure_partial"
                    page["export_errors"] = local
                    if any(error["category"] == "candidate_native_structure" for error in local):
                        page["structure_status"] = "unknown"
                    if page["status"] in {"completed", "candidate_partial"}:
                        page["status"] = "export_partial" if engineering else "candidate_partial"
            engineering = any(error["category"] != "candidate_native_structure" for error in assets.errors)
            if engineering and observation["status"] in {"completed", "partial"}:
                observation["status"] = "export_failed"
            elif observation["status"] == "completed":
                observation["status"] = "partial"
        responses = getattr(sdks.control, "responses", None)
        if responses is not None:
            observation["request_observation"] = list(responses)
        from .native_relations import native_relations
        observation["relations"] = native_relations(observation)
        # JSON encoding, faithful export and asset encoding are required work.
        # Only persistence of these already-ready bytes is outside the clock.
        native_bytes = json.dumps(native, ensure_ascii=False).encode("utf-8")
        markdown_bytes = "\n\n".join(markdown_pages).encode("utf-8")
        processing_memory.__exit__()
        cpu_finished = resource.getrusage(resource.RUSAGE_SELF)
        observation.setdefault("resources", {})["worker_processing_peak_process_rss_bytes"] = processing_memory.peak_bytes
        observation["resources"]["worker_processing_rss_sample_count"] = processing_memory.sample_count
        observation["resources"]["worker_cpu_seconds"] = (
            cpu_finished.ru_utime + cpu_finished.ru_stime - cpu_started.ru_utime - cpu_started.ru_stime)
        peak_file = Path("/sys/fs/cgroup/memory.peak")
        if peak_file.is_file():
            observation["resources"]["worker_cgroup_lifetime_peak_memory_bytes"] = int(peak_file.read_text().strip())
        if sdks.spec["family"] == "paddle" and config.get("paddle_backend", "native-transformers") == "native-transformers":
            import torch
            observation["resources"].update(gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                                             gpu_peak_reserved_bytes=torch.cuda.max_memory_reserved())
            observation["resources"]["cuda_graph_evidence"] = list(sdks.graph_evidence)
        observation["assets"] = [{"path": name, "media_type": "image/png"} for name in assets.data]
        observation["timing"] = {"processing_seconds": time.perf_counter() - started,
                                 "initialization_seconds": sdks.initialization_seconds if owns_sdks else 0.0,
                                 "shared_sdk_lifecycle": not owns_sdks,
                                 "clock": "worker.perf_counter", "warmup": bool(config.get("warmup", False)),
                                 "sample_timeout_seconds": float(config.get("timeout_seconds", 7200)),
                                 "deadline_policy": "stop new requests; drain issued requests and preserve late native output"}
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "native.json").write_bytes(native_bytes)
        (output_dir / "faithful.md").write_bytes(markdown_bytes)
        for name, payload in assets.data.items():
            destination = output_dir / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        for name, payload in stage_files.items():
            destination = output_dir / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        (output_dir / "observation.json").write_text(json.dumps(observation, ensure_ascii=False), encoding="utf-8")
        return observation
    finally:
        processing_memory.__exit__()
        if owns_sdks:
            await sdks.close()


async def execute_batch_in_worker(samples: list[Mapping[str, Any]], config: Mapping[str, Any], *,
                                  output_dir: Path) -> list[dict[str, Any]]:
    """Persistent SDKs: initialization and warm-up survive across all samples."""
    validate_execution_config(config)
    timeouts = [sample_timeout(config, sample) for sample in samples]
    sdks = _SDKs(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    state = {"sdk_initialized": False, "pipeline": config["pipeline"], "current_sample": None,
             "completed_samples": []}
    state_path = output_dir / "worker-state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    await sdks.initialize()
    state.update(sdk_initialized=True, initialization_seconds=sdks.initialization_seconds)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    observations = []
    try:
        for sample_index, sample in enumerate(samples):
            state["current_sample"] = {"sample_id": sample["sample_id"], "phase": sample.get("phase"),
                                       "processing_started_monotonic": time.perf_counter()}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            case_config = dict(config)
            case_config["warmup"] = bool(sample.get("warmup", sample.get("phase") == "warmup"))
            case_config["timeout_seconds"] = timeouts[sample_index]
            if "input_page_count" in sample:
                case_config["input_page_count"] = sample["input_page_count"]
            item = await execute_in_worker(Path(sample["pdf_path"]), case_config,
                sample_id=str(sample["sample_id"]), output_dir=Path(sample["output_dir"]), _sdks=sdks)
            for key in ("suite", "phase", "repetition", "input_page_count"):
                if key in sample:
                    item[key] = sample[key]
            item["timing"]["pipeline_initialization_seconds"] = sdks.initialization_seconds
            # Save metadata without changing processing_seconds or its boundary.
            (Path(sample["output_dir"]) / "observation.json").write_text(
                json.dumps(item, ensure_ascii=False), encoding="utf-8")
            observations.append(item)
            state["completed_samples"].append(sample["sample_id"])
            state["current_sample"] = None
            state_path.write_text(json.dumps(state), encoding="utf-8")
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "batch-observations.json").write_text(
                json.dumps(observations, ensure_ascii=False), encoding="utf-8")
            if item["status"] in {"execution_unknown", "cancelled"}:
                # No further workload enters an endpoint whose old work may
                # still be running. Its owning service context confirms exit.
                for pending in samples[len(observations):]:
                    unprocessed = {"sample_id": pending["sample_id"], "pipeline": config["pipeline"],
                        "status": "not_processed_due_to_unresolved_execution" if item["status"] == "execution_unknown" else "not_started_due_to_cancellation",
                        "pages": [], "relations": [],
                        "assets": [], "timing": {"processing_seconds": None},
                        "errors": [{"category": "remote_execution_unknown" if item["status"] == "execution_unknown" else "cancelled", "retry": False}]}
                    for key in ("suite", "phase", "repetition", "input_page_count"):
                        if key in pending:
                            unprocessed[key] = pending[key]
                    destination = Path(pending["output_dir"])
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / "observation.json").write_text(json.dumps(unprocessed), encoding="utf-8")
                    observations.append(unprocessed)
                (output_dir / "batch-observations.json").write_text(
                    json.dumps(observations, ensure_ascii=False), encoding="utf-8")
                break
        return observations
    finally:
        await sdks.close()
