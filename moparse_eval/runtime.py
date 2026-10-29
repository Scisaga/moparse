"""Owned isolated research workers and preparation-only environment inspection."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class PreparationError(RuntimeError):
    """Execution preparation is incomplete; this is not a parser failure."""


class ExecutionUnknownError(RuntimeError):
    """A worker or remote request may still own execution; do not retry."""


class MemoryObservation:
    """Observe this worker's RSS during a declared phase without reading input."""
    def __init__(self) -> None:
        self.peak_bytes: int | None = None
        self.sample_count = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        while not self._stop.is_set():
            try:
                for line in Path("/proc/self/status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        self.peak_bytes = max(self.peak_bytes or 0, int(line.split()[1]) * 1024)
                        self.sample_count += 1
                        break
            except (OSError, ValueError):
                pass
            self._stop.wait(0.02)

    def __enter__(self) -> MemoryObservation:
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()


def actual_worker_limits() -> dict[str, Any]:
    """Read actual process affinity and cgroup caps, separately from declarations."""
    result: dict[str, Any] = {}
    try:
        result["sched_getaffinity"] = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError) as exc:
        result["sched_getaffinity"] = None
        result["affinity_error"] = str(exc)
    for name in ("cpu.max", "memory.max"):
        try:
            value = Path("/sys/fs/cgroup", name).read_text().strip()
            result[name] = value
            if name == "cpu.max":
                quota, period = value.split()
                result["cpu_quota_cpus"] = int(quota) / int(period) if quota != "max" else None
                result["cpu_quota_status"] = "unlimited" if quota == "max" else "observed"
            else:
                result["memory_hard_limit_bytes"] = int(value) if value != "max" else None
                result["memory_limit_status"] = "unlimited" if value == "max" else "observed"
        except (OSError, ValueError) as exc:
            result[name] = None
            result[name + "_error"] = str(exc)
    return result


def bounded_cuda_graph_trial(function: Any, args: tuple[Any, ...], *,
                             warmups: int = 2, replays: int = 2) -> dict[str, Any]:
    """Capture and replay the supplied real inference operation, when invoked.

    This is an explicit bounded trial, not an import or preparation side effect.
    The caller selects a supported inference boundary and stores returned logs.
    No eager fallback is silently installed after this helper returns.
    """
    if not 1 <= warmups <= 3 or not 1 <= replays <= 3:
        raise ValueError("CUDA Graph trial is bounded to one through three warm-ups/replays")
    import torch
    if not torch.cuda.is_available():
        return {"status": "failed", "reason": "CUDA is unavailable", "graphs_enabled": False}
    started = time.perf_counter()
    try:
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream), torch.inference_mode():
            for _ in range(warmups):
                reference = function(*args)
        torch.cuda.current_stream().wait_stream(stream)
        torch.cuda.synchronize()
        graph = torch.cuda.CUDAGraph()
        with torch.inference_mode(), torch.cuda.graph(graph):
            captured = function(*args)
        for _ in range(replays):
            graph.replay()
        torch.cuda.synchronize()
        from torch.utils._pytree import tree_flatten
        baseline, _ = tree_flatten(reference)
        actual, _ = tree_flatten(captured)
        if len(baseline) != len(actual):
            raise RuntimeError("captured inference changed its output structure")
        for expected, received in zip(baseline, actual, strict=True):
            if torch.is_tensor(expected):
                torch.testing.assert_close(expected, received)
        return {"status": "captured_and_replayed", "graphs_enabled": True,
                "warmups": warmups, "replays": replays,
                "seconds": time.perf_counter() - started,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved()}
    except Exception as exc:
        return {"status": "failed", "graphs_enabled": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "seconds": time.perf_counter() - started,
                "reenable_condition": "resolve the recorded capture failure within the same resource budget"}


OFFICIAL_MODELS = {
    "paddle15": ("PaddlePaddle/PaddleOCR-VL-1.5", "2a4195faa5e7914c12f2fc601d72c81caf8d2da5"),
    "paddle16": ("PaddlePaddle/PaddleOCR-VL-1.6", "c5630abae1d940eafe0697512a0325494b02ab42"),
    "paddle_layout": ("PaddlePaddle/PP-DocLayoutV3", "241f8bdfc77a7c7bee915a5057aaee58c235a8d3"),
    "glm": ("zai-org/GLM-OCR", "2e85a62840ccac27daa451df36c736c4636b8628"),
    "mineru": ("opendatalab/MinerU2.5-Pro-2605-1.2B", "08aaea840498d49ce16247b6263196cf02814885"),
    "orientation": ("PaddlePaddle/PP-LCNet_x1_0_doc_ori_safetensors", "b2716954d2e321dd4436400b37584fab641027ab"),
    "tableformer_v2": ("docling-project/TableFormerV2", "e41ba5da7ef69004f4b329168791c2987abf917c"),
}


def validate_execution_config(config: Mapping[str, Any]) -> None:
    pipeline = config.get("pipeline")
    if pipeline not in {f"P{n:02}" for n in range(1, 9)}:
        raise PreparationError("pipeline must be one of P01 through P08")
    resources = config.get("resources", {})
    for key, upper in (("preprocessing_cpus", 8), ("inference_cpus", 4),
                       ("preprocessing_memory_gib", 8), ("inference_memory_gib", 20),
                       ("gpu_memory_gib", 16), ("client_concurrency", 4),
                       ("outer_concurrency", 1), ("power_watts", 200)):
        value = resources.get(key, upper)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= upper:
            raise PreparationError(f"{key} must be within the declared budget ({upper})")
    if str(resources.get("gpu_device", "1")) != "1":
        raise PreparationError("research execution is authorized only on GPU 1")
    if config.get("dpi", 200) != 200:
        raise PreparationError("the fixed configurations require 200 DPI")
    if config.get("expected") is not None or config.get("reference") is not None:
        raise PreparationError("expected material must not enter the candidate worker")
    if config.get("retry_max_attempts", 0) != 0:
        raise PreparationError("remote parsing retries require a verified idempotency contract")


def package_versions(names: list[str]) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def inspect_local(config: Mapping[str, Any]) -> dict[str, Any]:
    """Inspect only explicitly configured SDK/model paths, never input material."""
    validate_execution_config(config)
    models = config.get("models", {})
    paths = {key: {"path": str(value), "exists": Path(value).is_dir()}
             for key, value in models.items() if key.endswith("_path")}
    return {"pipeline": config["pipeline"], "status": "inspected_without_inference",
            "versions": package_versions(["docling", "docling-core", "mineru", "docvortex",
                                           "mineru-vl-utils", "glmocr", "paddleocr", "paddlex"]),
            "models": paths, "official_models": OFFICIAL_MODELS,
            "cuda_graphs": "pending_bounded_capture_and_inference", "execution_ready": False}


async def _confirm_worker_exit(name: str) -> dict[str, Any]:
    from .maintenance import record_owner
    while True:
        inspected = await asyncio.to_thread(subprocess.run, ["docker", "inspect", name],
                                             capture_output=True, text=True)
        if inspected.returncode:
            if "No such" in inspected.stderr:
                record_owner(name, "stopped")
                return {"container_removed": True}
            record_owner(name, "execution_unknown")
            raise ExecutionUnknownError("Docker could not confirm original worker process exit")
        if not json.loads(inspected.stdout)[0]["State"]["Running"]:
            record_owner(name, "stopped")
            return json.loads(inspected.stdout)[0]["State"]
        await asyncio.sleep(0.5)


async def run_worker(pdf_path: Path, config: Mapping[str, Any], *, sample_id: str,
                     output_dir: Path) -> dict[str, Any]:
    observations = await run_batch_worker([{"sample_id": sample_id, "pdf_path": str(pdf_path),
                                            "output_dir": str(output_dir.resolve())}], config,
                                           output_dir=output_dir)
    return observations[0]


async def run_batch_worker(samples: list[Mapping[str, Any]], config: Mapping[str, Any], *,
                           output_dir: Path, inputs_dir: Path | None = None) -> list[dict[str, Any]]:
    """Own a worker until it exits, even when its caller is cancelled.

    A cancelled task writes a cooperative stop marker and drains the original
    worker. It never kills an execution-unknown remote request or starts a retry.
    Container logs and exit code are engineering evidence, not quality scores.
    """
    validate_execution_config(config)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    worker_name = f"moparse-eval-worker-{token}"
    job_path = output_dir / f".job-{token}.json"
    cancel_path = output_dir / f".cancel-{token}"
    runtime = config.get("runtime", {})
    worker_config = dict(config)
    worker_config.pop("runtime", None)
    worker_config["cancel_path"] = str(cancel_path)
    job_samples = []
    for index, sample in enumerate(samples):
        destination = Path(sample.get("output_dir", Path("cases") / f"{index:05}"))
        if not destination.is_absolute():
            destination = output_dir / destination
        destination = destination.resolve()
        if not destination.is_relative_to(output_dir):
            raise PreparationError("every case output directory must be inside the run output root")
        item = {key: sample[key] for key in ("sample_id", "suite", "phase", "repetition", "warmup", "input_page_count") if key in sample}
        item.update(pdf_path=str(Path(sample["pdf_path"]).resolve()), output_dir=str(destination))
        job_samples.append(item)
    if not job_samples:
        raise PreparationError("a batch requires at least one PDF")
    job = {"samples": job_samples, "output_dir": str(output_dir), "config": worker_config}
    root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(root), "OMP_NUM_THREADS": "8", "OPENBLAS_NUM_THREADS": "8",
                "MKL_NUM_THREADS": "8", "MINERU_INTRA_OP_NUM_THREADS": "8",
                "MINERU_INTER_OP_NUM_THREADS": "1", "PYTHONUNBUFFERED": "1"})
    if runtime.get("kind", "local") == "docker":
        image = runtime.get("image")
        if not image:
            raise PreparationError("a fixed worker image is required")
        # Mount only code, the declared inputs, output and model directories.
        job["output_dir"] = "/output"
        worker_config["cancel_path"] = f"/output/{cancel_path.name}"
        native_paddle = config["pipeline"] in {"P03", "P04"} and config.get("paddle_backend", "native-transformers") == "native-transformers"
        cpu_limit, memory_limit = ("4", "20g") if native_paddle else ("8", "8g")
        command = ["docker", "run", "--name", worker_name,
                   "--cpus", cpu_limit, "--memory", memory_limit, "--memory-swap", memory_limit,
                   "--network", runtime.get("network", "host"),
                   "--mount", f"type=bind,src={root / 'moparse_eval'},dst=/research/moparse_eval,readonly",
                   "--mount", f"type=bind,src={root / 'app'},dst=/research/app,readonly",
                   "--mount", f"type=bind,src={root / 'native_worker'},dst=/research/native_worker,readonly",
                   "--mount", f"type=bind,src={output_dir},dst=/output",
                   "--workdir", "/research", "--entrypoint", runtime.get("container_python", "python"),
                   "--env", "PYTHONPATH=/research", "--env", "OMP_NUM_THREADS=8",
                   "--env", "OPENBLAS_NUM_THREADS=8", "--env", "MKL_NUM_THREADS=8",
                   "--env", f"CUDA_VISIBLE_DEVICES={'0' if native_paddle else ''}", "--env", "MINERU_DEVICE_MODE=cpu",
                   "--env", "MINERU_MODEL_SMALL_BACKEND=onnx",
                   "--env", "MINERU_INTRA_OP_NUM_THREADS=8", "--env", "MINERU_INTER_OP_NUM_THREADS=1"]
        if native_paddle:
            command += ["--gpus", "device=1"]
        if config["pipeline"] in {"P06", "P07"}:
            # MinerU takes a FileLock even for already-ready local models.
            # Overlay only that lock directory; immutable weights stay read-only.
            lock_root = str(Path(config["models"]["mineru_small_path"]) / "models" / ".locks")
            command += ["--tmpfs", lock_root + ":rw,noexec,nosuid,size=16m"]
            worker_config["writable_model_runtime_paths"] = [
                {"path": lock_root, "kind": "tmpfs", "scope": "SDK advisory locks only", "size_mib": 16}]
        worker_config["actual_allocation"] = {"worker_cpus": int(cpu_limit), "worker_memory": memory_limit,
            "gpu_device": "1" if native_paddle else None,
            "stage_isolation": "combined_paddle_process" if native_paddle else "cpu_worker_remote_gpu",
            "preprocessing_hard_memory_limit_separate": not native_paddle}
        if inputs_dir is not None:
            inputs_dir = inputs_dir.resolve()
            if inputs_dir.name != "inputs":
                raise PreparationError("inputs_dir must be the package inputs directory, excluding references")
            command += ["--mount", f"type=bind,src={inputs_dir},dst=/input,readonly"]
        for index, item in enumerate(job_samples):
            source_path = Path(item["pdf_path"])
            if inputs_dir is not None:
                if not source_path.is_relative_to(inputs_dir):
                    raise PreparationError("a candidate PDF is outside the declared inputs directory")
                item["pdf_path"] = str(Path("/input") / source_path.relative_to(inputs_dir))
            else:
                item["pdf_path"] = f"/input/{index:05}.pdf"
                command += ["--mount", f"type=bind,src={source_path},dst={item['pdf_path']},readonly"]
            item["output_dir"] = str(Path("/output") / Path(item["output_dir"]).relative_to(output_dir))
        for host, container in runtime.get("mounts", {}).items():
            if not str(container).startswith(("/models/", "/cache/")):
                raise PreparationError("explicit model mounts must be under /models or /cache")
            command += ["--mount", f"type=bind,src={Path(host).resolve()},dst={container},readonly"]
        command += [image, "-m", "moparse_eval.runtime", "--job", f"/output/{job_path.name}"]
    else:
        env["CUDA_VISIBLE_DEVICES"] = ""
        command = [runtime.get("python", sys.executable), "-m", "moparse_eval.runtime",
                   "--job", str(job_path)]
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    log_path = output_dir / "worker.log"
    started = time.perf_counter()
    with log_path.open("wb") as log:
        from .maintenance import ContainerSampler, record_owner
        if runtime.get("kind", "local") == "docker":
            record_owner(worker_name, "starting")
        process = await asyncio.create_subprocess_exec(*command, stdout=log, stderr=log, env=env)
        sampler = None
        if runtime.get("kind", "local") == "docker":
            sampler = ContainerSampler([worker_name], output_dir / "worker-resources.json", gpu=native_paddle)
            sampler.start()
        completion = asyncio.create_task(process.wait())
        cancelled = False
        while not completion.done():
            try:
                await asyncio.shield(completion)
            except asyncio.CancelledError:
                cancelled = True
                cancel_path.touch()
        exit_code = completion.result()
    worker_exit_state = {}
    if runtime.get("kind", "local") == "docker":
        confirmation = asyncio.create_task(_confirm_worker_exit(worker_name))
        while not confirmation.done():
            try:
                await asyncio.shield(confirmation)
            except asyncio.CancelledError:
                cancelled = True
                cancel_path.touch()
        worker_exit_state = confirmation.result() or {}
        if sampler:
            await sampler.close()
        subprocess.run(["docker", "rm", worker_name], capture_output=True, text=True)
        (output_dir / "worker-exit.json").write_text(json.dumps(worker_exit_state), encoding="utf-8")
    envelope_path = output_dir / "batch-observations.json"
    state_path = output_dir / "worker-state.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    if worker_exit_state.get("OOMKilled") or (exit_code and state.get("sdk_initialized") and state.get("current_sample")):
        existing = json.loads(envelope_path.read_text()) if envelope_path.is_file() else []
        for sample in samples[len(existing):]:
            started_sample = state.get("sdk_initialized") and (state.get("current_sample") or {}).get("sample_id") == sample["sample_id"]
            record = {"sample_id": sample["sample_id"], "pipeline": config["pipeline"],
                "status": ("resource_failed" if worker_exit_state.get("OOMKilled") else "execution_failed") if started_sample else "not_started",
                "pages": [], "relations": [], "assets": [], "timing": {"processing_seconds": None},
                "errors": [{"category": ("candidate_resource_failure" if worker_exit_state.get("OOMKilled") else "candidate_execution_failure")
                    if started_sample else "engineering_preparation_failure",
                    "type": "worker_oom" if worker_exit_state.get("OOMKilled") else "worker_exit_after_sample_start",
                    "worker_exit_state": worker_exit_state, "started_evidence": state,
                    "retry": False}]}
            existing.append(record)
        envelope_path.write_text(json.dumps(existing), encoding="utf-8")
    if not envelope_path.is_file():
        raise PreparationError(f"worker exited {exit_code} before producing an observation; see {log_path}")
    observations = json.loads(envelope_path.read_text(encoding="utf-8"))
    for observation in observations:
        observation.setdefault("runtime", {}).update({"worker_exit_code": exit_code,
            "batch_orchestration_seconds": time.perf_counter() - started,
            "sdk_initialization": "once_per_persistent_pipeline_worker"})
    if cancelled:
        raise asyncio.CancelledError
    for observation in observations:
        if observation.get("status") == "preparation_failed":
            raise PreparationError(observation.get("errors", [{}])[0].get("message", "worker preparation failed"))
    return observations


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    # This file was authored by the runner and includes no expected material.
    job = json.loads(args.job.read_text(encoding="utf-8"))
    from .executors import execute_batch_in_worker
    try:
        asyncio.run(execute_batch_in_worker(job["samples"], job["config"], output_dir=Path(job["output_dir"])))
        return 0
    except PreparationError as exc:
        path = Path(job["output_dir"]) / "batch-observations.json"
        existing = json.loads(path.read_text()) if path.is_file() else []
        existing.extend({"sample_id": sample["sample_id"], "pipeline": job["config"]["pipeline"],
                                    "status": "preparation_failed", "pages": [], "relations": [],
                                    "assets": [], "timing": {}, "errors": [{"message": str(exc)}]}
                                   for sample in job["samples"][len(existing):])
        path.write_text(json.dumps(existing), encoding="utf-8")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
