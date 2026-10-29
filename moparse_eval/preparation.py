"""Prepare pinned software and model artifacts; never accepts corpus inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .runtime import OFFICIAL_MODELS


def download_model(repo: str, revision: str, directory: Path) -> dict[str, Any]:
    """Fetch one immutable official software/model revision and record its bytes."""
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import snapshot_download
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo, revision=revision, local_dir=directory,
                      allow_patterns=["*.json", "*.safetensors", "*.py", "*.jinja", "*.model",
                                      "*.txt", "*.yml", "*.yaml", "*.pdiparams"],
                      ignore_patterns=[".eval_results/*"], max_workers=4)
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and ".cache" not in path.parts and path.name != "model-lock.json":
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                    digest.update(block)
            files.append({"path": str(path.relative_to(directory)), "sha256": digest.hexdigest()})
    lock = {"repository": repo, "revision": revision, "files": files,
            "scope": "software_model_artifacts_only"}
    (directory / "model-lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return lock


def build_context(destination: Path, project: Path) -> None:
    """Build context contains these Dockerfiles and dependency patches only."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "patch_dependency.py"):
        target = destination / "native_worker" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project / "native_worker" / name, target)
    shutil.copytree(project / "native_worker" / "patches", destination / "native_worker" / "patches",
                    dirs_exist_ok=True)
    cpu = '''FROM moparse:0.5.1-semantic-v1-20261019
USER root
RUN python -m ensurepip --upgrade && python -m pip install --no-cache-dir mineru==4.0.12 mineru-vl-utils==2.0.7 docvortex==0.5.16 glmocr==0.1.5 onnxruntime==1.31.0 pypdfium2==5.14.0 && python -m pip check
RUN apt-get update && apt-get install -y --no-install-recommends patch && rm -rf /var/lib/apt/lists/*
COPY native_worker /research/native_worker
WORKDIR /research
RUN python -m native_worker.patch_dependency
ENV CUDA_VISIBLE_DEVICES="" MINERU_DEVICE_MODE=cpu MINERU_TABLE_DEVICE=cpu MINERU_MODEL_SMALL_BACKEND=onnx MINERU_MODEL_SOURCE=local MINERU_HOME=/models/mineru-small MINERU_PROCESSING_WINDOW_SIZE=8 MINERU_MALLOC_TRIM=1 MOPARSE_CPU_MFR_BATCH_SIZE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8
HEALTHCHECK NONE
ENTRYPOINT ["python"]
'''
    paddle = '''FROM vllm/vllm-openai:v0.19.1
USER root
RUN python3 -m pip install --no-cache-dir "paddleocr[doc-parser]==3.7.0" "paddlex==3.7.2" "transformers==5.10.2"
RUN python3 -m pip uninstall -y PyGObject && python3 -m pip check
RUN python3 -m pip install --no-cache-dir pymupdf==1.28.2 && python3 -m pip check
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
WORKDIR /research
HEALTHCHECK NONE
ENTRYPOINT ["python3"]
'''
    (destination / "Dockerfile.cpu").write_text(cpu, encoding="utf-8")
    (destination / "Dockerfile.paddle").write_text(paddle, encoding="utf-8")


def write_execution_lock(path: Path, project: Path, models_root: Path) -> dict[str, Any]:
    """Prepare actual software identities; runtime preflight must precede freeze."""
    def image_id(tag: str) -> str:
        return subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", tag], text=True).strip()
    cpu_image = image_id("moparse-eval-cpu:20261024")
    paddle_image = image_id("moparse-eval-paddle:20261024")
    glm_image = image_id("vllm/vllm-openai:v0.19.1")
    mineru_image = image_id("moparse-mineru-vllm:0.5.0-header-v4-20261018")
    models_root = models_root.resolve()
    cache = Path("/var/lib/docker/volumes/mosaicparse-huggingface-cache/_data/hub")
    docling = Path("/var/lib/docker/volumes/mosaicparse-docling-models-selected-20261017/_data")
    glm_cache = cache / "models--zai-org--GLM-OCR"
    layout_cache = cache / "models--PaddlePaddle--PP-DocLayoutV3_safetensors"
    mineru_cache = Path("/var/lib/docker/volumes/moparse-mineru-models/_data")
    small = Path("/var/lib/docker/volumes/moparse-mineru-small-models/_data")
    pipelines = {}
    for number in range(1, 9):
        pipeline = f"P{number:02}"
        paddle = number in {3, 4}
        hybrid = number in {1, 2, 6, 7}
        uses_glm = hybrid or number == 5
        uses_mineru = number in {6, 7, 8}
        mounts = {str(models_root / "orientation"): "/models/orientation"}
        model_paths = {"orientation_path": "/models/orientation"}
        revisions = {"orientation": OFFICIAL_MODELS["orientation"][1]}
        if uses_glm:
            mounts[str(layout_cache)] = "/models/glm-layout-cache"
            model_paths["glm_layout_path"] = "/models/glm-layout-cache/snapshots/e4f489dc536556fc1be02b973ba06756e0d4a2ac"
            revisions.update(glm=OFFICIAL_MODELS["glm"][1], glm_layout="e4f489dc536556fc1be02b973ba06756e0d4a2ac")
        if number in {1, 2}:
            for folder in ("docling-project--docling-models", "docling-project--docling-layout-heron"):
                mounts[str(docling / folder)] = "/models/docling/" + folder
            model_paths["docling_path"] = "/models/docling"
            revisions.update(tableformer_v1="fc0f2d45e2218ea24bce5045f58a389aed16dc23",
                             docling_layout="8f39ad3c0b4c58e9c2d2c84a38465abf757272d8")
            if number == 2:
                mounts[str(models_root / "docling" / "docling-project--TableFormerV2")] = "/models/docling/docling-project--TableFormerV2"
                revisions["tableformer_v2"] = OFFICIAL_MODELS["tableformer_v2"][1]
        if number in {6, 7}:
            mounts[str(small)] = "/models/mineru-small"
            model_paths["mineru_small_path"] = "/models/mineru-small"
        if uses_mineru:
            revisions["mineru"] = OFFICIAL_MODELS["mineru"][1]
        if paddle:
            model_key = "paddle15" if number == 3 else "paddle16"
            mounts[str(models_root / model_key)] = "/models/paddle-vlm"
            mounts[str(models_root / "paddle-layout-transformers")] = "/models/paddle-layout"
            model_paths.update(paddle_vlm_path="/models/paddle-vlm", paddle_layout_path="/models/paddle-layout")
            revisions.update(paddle_vlm=OFFICIAL_MODELS[model_key][1],
                             paddle_layout="e4f489dc536556fc1be02b973ba06756e0d4a2ac")
        services = []
        shared = uses_glm and uses_mineru
        if uses_glm:
            services.append({"role": "glm", "family": "glm", "inference_image": glm_image,
                "host_model_path": str(glm_cache), "model_subdir": f"snapshots/{OFFICIAL_MODELS['glm'][1]}",
                "model_name": "zai-org/GLM-OCR", "port": 12541,
                "cpus": 2 if shared else 4, "memory_gib": 10 if shared else 20,
                "gpu_memory_gib": 6 if shared else 16, "rotary_embedding": "native"})
        if uses_mineru:
            services.append({"role": "mineru", "family": "mineru", "inference_image": mineru_image,
                "host_model_path": str(mineru_cache), "model_subdir": f"snapshots/{OFFICIAL_MODELS['mineru'][1]}",
                "model_name": "mineru2.5-pro", "port": 12542,
                "cpus": 2 if shared else 4, "memory_gib": 10 if shared else 20,
                "gpu_memory_gib": 10 if shared else 16})
        config: dict[str, Any] = {"pipeline": pipeline, "dpi": 200, "timeout_seconds": 7200,
            "runtime": {"kind": "docker", "image": cpu_image,
                        "container_python": "python", "network": "host", "mounts": mounts},
            "models": model_paths, "revisions": revisions, "inference_services": services,
            "versions": {"docling": "2.139.0", "docling-core": "2.101.1", "mineru": "4.0.12",
                         "mineru-vl-utils": "2.0.7", "docvortex": "0.5.16", "glmocr": "0.1.5",
                         "paddleocr": "3.7.0", "paddlex": "3.7.2", "transformers": "5.8.1"},
            "resources": {"preprocessing_cpus": 8, "preprocessing_memory_gib": 8,
                          "inference_cpus": 4, "inference_memory_gib": 20, "gpu_device": "1",
                          "gpu_memory_gib": 16, "power_watts": 200,
                          "outer_concurrency": 1, "client_concurrency": 4},
            "graphs": {"status": "pending_bounded_capture_and_inference", "torch_compile": False},
            "retry_max_attempts": 0, "observe_request_metadata": True,
            "co_resident_services": {"qwen3-tts-openai.service": {
                "policy": "keep_running", "observation_policy": "observe_only",
                "inference_during_benchmark": "uncontrolled_observed_only",
                "instruction_date": "2026-10-26"}},
            "execution_repairs": ["rotation-coordinate-space", "native-neighbor-retention",
                                  "region-export-isolation"]}
        if hybrid:
            config["source_policy"] = {"minimum_native_characters": 40, "scan_image_coverage": 0.8,
                                       "mixed_image_coverage": 0.2, "unknown_action": "glm",
                                       "role": "runtime_prediction_only_not_gold"}
        if uses_glm:
            config["execution_repairs"].append("glm-gptj-native-rotary")
            config["glm_configuration"] = "bundled glmocr 0.1.5 YAML; self-hosted CPU layout; retry=0; workers=4"
            config["native_view_policy"] = {"glm": {"primary_scoring_view": "json_result",
                "audit_view": "raw_json_result", "cross_view_order": "unknown",
                "selection": "fixed; no favorable stage selection by answer or sample"}}
        if number in {1, 2}:
            config["docling_export"] = "contiguous native group once; all ContentLayer; native tree order"
        if number in {6, 7}:
            config["runtime"]["writable_runtime_paths"] = [{"path": "/models/mineru-small/models/.locks",
                "kind": "tmpfs", "size_mib": 16, "scope": "advisory locks only; weights remain read-only"}]
        if paddle:
            config["execution_repairs"].extend(["paddle-bgr-rgb", "persistent-native-owner"])
            config.update(paddle_color_policy="bgr-to-rgb-v1", paddle_max_new_tokens=4096,
                          paddle_generation_observation=True)
            # The CPU worker retains its independent 5.8.1 environment. The
            # official native Paddle engine requires the newer HF integration.
            config["versions"]["paddle_transformers"] = "5.10.2"
            config["native_attention"] = {"vlm": "sdpa", "layout": "official default; no unsupported global SDPA",
                "cuda_graphs": "independent bounded capture/replay verification"}
            config["paddle_backend"] = "native-rpc"
            server_config = {key: config[key] for key in ("pipeline", "models", "versions", "graphs", "resources")}
            server_config["paddle_backend"] = "native-transformers"
            server_config["paddle_execution_mode"] = "persistent-owner-v1"
            server_config["paddle_use_queues"] = False
            for key in ("paddle_color_policy", "paddle_max_new_tokens", "paddle_generation_observation"):
                server_config[key] = config[key]
            config["inference_services"] = [{"role": "paddle", "family": "paddle-native",
                "inference_image": paddle_image, "model_name": "PaddleOCR-VL-" + ("1.5" if number == 3 else "1.6"),
                "port": 12543, "cpus": 4, "memory_gib": 20, "gpu_memory_gib": 16,
                "model_mounts": {host: target for host, target in mounts.items() if target.startswith("/models/paddle-")},
                "server_config": server_config}]
            config["resource_isolation"] = {"preprocessing": "CPU worker cgroup: 8 CPU, 8 GiB",
                "native_inference": "separate GPU1 container cgroup: 4 CPU, 20 GiB; includes official layout and VLM",
                "internal_rpc_timing": "included inside direct worker processing clock; never subtracted"}
        pipelines[pipeline] = config
    required = [models_root / folder / "model-lock.json" for folder in
                ("paddle15", "paddle16", "orientation", "paddle-layout-transformers",
                 "docling/docling-project--TableFormerV2")]
    downloaded = all(item.is_file() for item in required)
    lock = {"schema": "moparse-evaluation-execution-v1", "prepared_date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "frozen": False,
            "status": "software_prepared_runtime_trials_pending" if downloaded else "images_prepared_model_download_pending",
            "model_artifacts_prepared": downloaded, "pipelines": pipelines,
            "official_sources": {name: {"repository": repo, "revision": revision,
                                         "url": f"https://huggingface.co/{repo}/tree/{revision}"}
                                 for name, (repo, revision) in OFFICIAL_MODELS.items()},
            "model_cache_policy": "existing GLM/MinerU/Docling caches are mounted read-only",
            "formal_execution": "requires separately frozen references; this software lock is not a quality result"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return lock


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-root", type=Path, default=Path("data/evaluation-models"))
    parser.add_argument("--build-context", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--write-lock", type=Path)
    args = parser.parse_args()
    if args.build_context:
        build_context(args.build_context, Path(__file__).resolve().parent.parent)
    if args.download:
        for name in ("paddle15", "paddle16", "orientation"):
            repo, revision = OFFICIAL_MODELS[name]
            download_model(repo, revision, args.models_root / name)
        repo = "PaddlePaddle/PP-DocLayoutV3_safetensors"
        # This explicit revision is already present in the official model cache.
        download_model(repo, "e4f489dc536556fc1be02b973ba06756e0d4a2ac", args.models_root / "paddle-layout-transformers")
        repo, revision = OFFICIAL_MODELS["tableformer_v2"]
        download_model(repo, revision, args.models_root / "docling" / "docling-project--TableFormerV2")
    if args.write_lock:
        write_execution_lock(args.write_lock, Path(__file__).resolve().parent.parent, args.models_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
