"""Explicit GPU 1 maintenance window with durable restoration state.

Importing this module never changes a service. Only the two MO-Parse inference
containers may be paused. TTS stays resident; GPU 0 is outside this API.
"""

from __future__ import annotations

import asyncio
import csv
import json
import math
import sqlite3
import subprocess
import time
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTAINERS = ("moparse-mineru-vllm", "docling_glm_ocr")
SYSTEMD_UNITS = ("qwen3-tts-openai.service",)
DEFAULT_GPU_BUDGET_GIB = 16
_active_window: ContextVar[tuple[Path, dict[str, Any]] | None] = ContextVar("moparse_eval_window", default=None)


def _unit_state(name: str) -> dict[str, Any]:
    result = _run(["systemctl", "show", name,
        "--property=ActiveState,SubState,MainPID,ControlGroup,InvocationID"], check=False)
    if result.returncode:
        raise RuntimeError(f"systemd identity is unavailable for {name}: {result.stderr}")
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return {"active": values.get("ActiveState") == "active", **values}


def _observe_unit_state(name: str) -> dict[str, Any]:
    """A co-resident service observation never controls MO-Parse admission."""
    try:
        return _unit_state(name)
    except Exception as exc:
        return {"active": None, "observation_status": "unknown",
                "observation_error": f"{type(exc).__name__}: {exc}"}


def _read_process_cgroups(pid: int) -> set[str]:
    """Read host process membership, never document or request contents."""
    paths = {line.split(":", 2)[2] for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines()
             if len(line.split(":", 2)) == 3}
    if not paths:
        raise ValueError(f"no host cgroup membership for PID {pid}")
    return paths


def _container_gpu_identity(name: str, cached: dict[str, Any] | None) -> dict[str, Any]:
    # Reuse the inspected identity while its host init PID remains in the same
    # cgroup. Engine child processes are matched against the full container ID.
    if cached is not None:
        try:
            if _read_process_cgroups(cached["host_pid"]) == set(cached["cgroups"]):
                return cached
        except (OSError, ValueError):
            pass
    result = _run(["docker", "inspect", name], check=False)
    if result.returncode:
        raise RuntimeError(result.stderr or f"container identity unavailable: {name}")
    record = json.loads(result.stdout)[0]
    pid, identifier = int(record["State"].get("Pid", 0)), record["Id"]
    if not record["State"].get("Running") or pid <= 0 or not identifier:
        raise ValueError(f"container is not running: {name}")
    groups = _read_process_cgroups(pid)
    if not any(identifier in group for group in groups):
        raise ValueError(f"container ID is not corroborated by host cgroup: {name}")
    return {"container_id": identifier, "host_pid": pid, "cgroups": sorted(groups)}


def _gpu_observation(names: list[str], identities: dict[str, dict[str, Any]],
                     tts_unit: dict[str, Any]) -> dict[str, Any]:
    """Sample whole-card headroom and independently attribute compute memory."""
    whole = _run(["nvidia-smi", "-i", "1",
        "--query-gpu=uuid,memory.total,memory.used,memory.free,power.draw,utilization.gpu",
        "--format=csv,noheader,nounits"], check=False)
    if whole.returncode:
        raise RuntimeError(whole.stderr or "GPU 1 observation unavailable")
    gpu_uuid, total, used, free, power, utilization = next(csv.reader(whole.stdout.splitlines()))
    total_mib, used_mib, free_mib = float(total), float(used), float(free)
    if not all(math.isfinite(value) and value >= 0 for value in (total_mib, used_mib, free_mib)):
        raise ValueError("GPU 1 memory observation is not finite")
    gpu = {"uuid": gpu_uuid.strip(), "total_memory_mib": total_mib, "used_memory_mib": used_mib,
           "free_memory_mib": free_mib,
           "free_memory_source": "nvidia-smi memory.free; never estimated as total minus used",
           "scope": "whole GPU 1, including resident TTS, all backends and CUDA/driver overhead"}
    for key, value in (("power_watts", power), ("utilization_percent", utilization)):
        try:
            gpu[key] = float(value)
        except ValueError:
            gpu[key] = None
    errors: list[str] = []
    roots = {}
    for name in names:
        try:
            roots[name] = _container_gpu_identity(name, identities.get(name))
            identities[name] = roots[name]
        except (OSError, ValueError, KeyError, IndexError, RuntimeError) as exc:
            identities.pop(name, None)
            errors.append(f"{name}: {exc}")
    for name in set(identities) - set(names):
        identities.pop(name, None)
    process_result = _run(["nvidia-smi",
        "--query-compute-apps=gpu_uuid,pid,used_gpu_memory", "--format=csv,noheader,nounits"], check=False)
    processes = []
    by_container = {name: 0.0 for name in roots}
    tts_memory = 0.0
    tts_pid = int(tts_unit.get("MainPID") or 0)
    tts_group = tts_unit.get("ControlGroup", "")
    tts_groups = {tts_group} if tts_group not in ("", "/") else set()
    if not tts_groups and tts_pid > 0:
        try:
            tts_groups = _read_process_cgroups(tts_pid) - {"/"}
        except (OSError, ValueError):
            pass
    tts_known = bool(tts_unit.get("active") and (tts_pid > 0 or tts_group not in ("", "/")))
    if process_result.returncode:
        errors.append(process_result.stderr or "GPU compute-process observation unavailable")
    else:
        seen = set()
        for row in csv.reader(process_result.stdout.splitlines()):
            if not row:
                continue
            if len(row) != 3 or not row[0].strip().startswith(("GPU-", "MIG-")):
                errors.append("malformed GPU compute-process observation")
                continue
            if row[0].strip() != gpu["uuid"]:
                continue
            process: dict[str, Any] = {"ownership": "unknown"}
            try:
                if len(row) != 3:
                    raise ValueError("malformed GPU process observation")
                pid, memory = int(row[1]), float(row[2])
                process.update(pid=pid, used_memory_mib=memory)
                if pid in seen or pid <= 0 or not math.isfinite(memory) or memory < 0:
                    raise ValueError("invalid or duplicate GPU process observation")
                seen.add(pid)
                try:
                    groups = _read_process_cgroups(pid)
                except (OSError, ValueError):
                    if pid != tts_pid:
                        raise
                    groups = set()
                owners = [name for name, root in roots.items()
                          if any(root["container_id"] in group for group in groups)]
                if len(owners) == 1:
                    process.update(ownership="owned_container", container=owners[0])
                    by_container[owners[0]] += memory
                elif owners:
                    raise ValueError("GPU process has ambiguous owned-container membership")
                elif pid == tts_pid or any(group == root or group.startswith(root.rstrip("/") + "/")
                                          for root in tts_groups for group in groups):
                    process["ownership"] = "resident_tts"
                    tts_memory += memory
                elif len(roots) != len(names):
                    raise ValueError("a missing container identity prevents excluding owned membership")
                else:
                    process["ownership"] = "other_process"
            except (OSError, ValueError, IndexError) as exc:
                process["error"] = str(exc)
                errors.append(str(exc))
            processes.append(process)
    complete = not errors and len(roots) == len(names)
    return {"gpu1": gpu, "owned_gpu": {
        "status": "complete_observed_sample" if complete and names else "not_started" if complete else "unknown",
        "used_memory_mib": sum(by_container.values()) if complete and names else None,
        "known_memory_lower_bound_mib": sum(by_container.values()),
        "memory_mib_by_container": {name: by_container.get(name) if complete else None for name in names},
        "identities": roots, "errors": errors,
        "scope": "sum of GPU 1 compute allocations attributed to all named containers, including child processes"},
        "tts_gpu": {"used_memory_mib": tts_memory if tts_known and complete else None,
                    "status": "observed" if tts_known and complete else "unknown",
                    "unit_identity": tts_unit}, "gpu_processes": processes}


class ContainerSampler:
    """Observed resource peaks, explicitly sampled rather than exact maxima."""
    def __init__(self, names: list[str], path: Path, *, gpu: bool = False,
                 gpu_budget_gib: float = DEFAULT_GPU_BUDGET_GIB) -> None:
        self.names, self.path, self.gpu = names, path, gpu
        self.gpu_budget_gib = gpu_budget_gib
        self._gpu_identities: dict[str, dict[str, Any]] = {}
        window = _active_window.get()
        self._tts_unit: dict[str, Any] | None = None
        if window is not None:
            unit = window[1].get("systemd_units", {}).get(SYSTEMD_UNITS[0])
            if isinstance(unit, dict):
                self._tts_unit = unit
        self.stopping = False
        self.task: asyncio.Task | None = None
        self.samples: list[dict[str, Any]] = []

    async def _loop(self) -> None:
        while not self.stopping:
            sample: dict[str, Any] = {"monotonic_seconds": time.perf_counter(), "containers": [],
                "expected_containers": list(self.names), "probe_errors": []}
            for name in sample["expected_containers"]:
                result = await asyncio.to_thread(_run, ["docker", "stats", "--no-stream",
                    "--format", "{{json .}}", name], check=False)
                if not result.returncode and result.stdout.strip():
                    try:
                        record = json.loads(result.stdout.strip())
                        record["owned_name"] = name
                        sample["containers"].append(record)
                    except (ValueError, TypeError) as exc:
                        sample["probe_errors"].append({"container": name, "error": str(exc)})
                else:
                    sample["probe_errors"].append({"container": name, "returncode": result.returncode,
                                                    "error": result.stderr or "missing docker stats output"})
            if self.gpu:
                try:
                    tts_unit = self._tts_unit
                    if tts_unit is None:
                        tts_unit = await asyncio.to_thread(_observe_unit_state, SYSTEMD_UNITS[0])
                        self._tts_unit = tts_unit
                    sample.update(await asyncio.to_thread(_gpu_observation, sample["expected_containers"],
                        self._gpu_identities, tts_unit))
                except (OSError, ValueError, IndexError, RuntimeError) as exc:
                    sample["probe_errors"].append({"probe": "gpu1", "error": str(exc)})
            self.samples.append(sample)
            await asyncio.sleep(0.25)

    def start(self) -> None:
        self.task = asyncio.create_task(self._loop())

    async def close(self) -> dict[str, Any]:
        self.stopping = True
        if self.task:
            await self.task
        def memory_bytes(value: Any) -> float | None:
            if not isinstance(value, str):
                return None
            used = value.split("/", 1)[0].strip()
            for unit, factor in (("GiB", 1024 ** 3), ("MiB", 1024 ** 2), ("KiB", 1024),
                                 ("GB", 1000 ** 3), ("MB", 1000 ** 2), ("kB", 1000), ("B", 1)):
                if used.endswith(unit):
                    try:
                        amount = float(used[:-len(unit)].strip()) * factor
                        return amount if math.isfinite(amount) and amount >= 0 else None
                    except ValueError:
                        return None
            return None
        host_peaks: dict[str, float | None] = {name: None for name in self.names}
        shared_peak: float | None = None
        complete_samples = 0
        parse_failures = []
        for sample_index, sample in enumerate(self.samples):
            shared = 0.0
            observed = set()
            for container in sample["containers"]:
                used = memory_bytes(container.get("MemUsage"))
                name = container.get("owned_name", container.get("Name", container.get("Container", "unknown")))
                host_peaks.setdefault(name, None)
                if used is None:
                    parse_failures.append({"sample": sample_index, "container": name, "MemUsage": container.get("MemUsage")})
                    continue
                host_peaks[name] = max(host_peaks.get(name) or 0.0, used)
                shared += used
                observed.add(name)
            expected = set(sample.get("expected_containers", self.names))
            if expected and expected <= observed:
                complete_samples += 1
                shared_peak = max(shared_peak or 0.0, shared)
        gpu_values = [sample["gpu1"]["used_memory_mib"] for sample in self.samples
                      if sample.get("gpu1", {}).get("used_memory_mib") is not None]
        owned_values = [sample["owned_gpu"]["used_memory_mib"] for sample in self.samples
                        if sample.get("owned_gpu", {}).get("used_memory_mib") is not None]
        owned_lower_bounds = [sample["owned_gpu"]["known_memory_lower_bound_mib"] for sample in self.samples
                              if sample.get("owned_gpu", {}).get("known_memory_lower_bound_mib") is not None]
        tts_values = [sample["tts_gpu"]["used_memory_mib"] for sample in self.samples
                      if sample.get("tts_gpu", {}).get("used_memory_mib") is not None]
        headroom_values = [sample["gpu1"]["free_memory_mib"] for sample in self.samples
                          if sample.get("gpu1", {}).get("free_memory_mib") is not None]
        summary = {"scope": "observed samples, may miss shorter peaks",
            "sampling": "sequential docker stats, whole GPU1 and compute-process nvidia-smi; 0.25-second inter-sample delay",
            "observed_host_memory_peak_bytes_by_container": host_peaks,
            "observed_shared_host_memory_peak_bytes": shared_peak,
            # Retained for readback compatibility; never use this whole-card
            # value to enforce the owned-container budget while TTS resides.
            "observed_gpu1_peak_memory_mib": max(gpu_values, default=None),
            "gpu1_memory_scope": "whole GPU 1 including TTS and unrelated allocations; headroom only",
            "observed_gpu1_min_free_memory_mib": min(headroom_values, default=None),
            "observed_owned_gpu_peak_memory_mib": max(owned_values, default=None),
            "observed_owned_gpu_memory_lower_bound_peak_mib": max(owned_lower_bounds, default=None),
            "owned_gpu_memory_scope": "simultaneous aggregate of attributed named-container compute processes",
            "owned_gpu_budget_gib": self.gpu_budget_gib,
            "tts_resident_baseline_memory_mib": next(iter(tts_values), None),
            "observed_tts_gpu_peak_memory_mib": max(tts_values, default=None),
            "tts_workload_condition": "TTS is co-resident and uncontrolled; activity and identity are observations only",
            "tts_observation_policy": "observe_only",
            "sampling_completeness": {"samples": len(self.samples), "complete_container_memory_samples": complete_samples,
                "gpu_memory_samples": len(gpu_values), "owned_gpu_memory_samples": len(owned_values),
                "tts_gpu_memory_samples": len(tts_values), "memory_parse_failures": parse_failures,
                "status": "unknown" if not self.samples else "partial" if complete_samples != len(self.samples)
                    or (self.gpu and (len(gpu_values) != len(self.samples)
                                     or len(owned_values) != len(self.samples))) else "complete_observed_samples"},
            "samples": self.samples}
        budget_exceeded = any(value > self.gpu_budget_gib * 1024 for value in owned_values + owned_lower_bounds)
        summary["gpu_budget_exceeded_in_observed_samples"] = True if budget_exceeded else False if owned_values else None
        summary["gpu_budget_comparison_scope"] = "owned containers only; whole GPU and resident TTS excluded"
        _save(self.path, summary)
        return summary


def record_owner(name: str, status: str) -> None:
    current = _active_window.get()
    if current is not None:
        path, state = current
        state.setdefault("research_owners", {})[name] = status
        _save(path, state)


def _run(arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, text=True, capture_output=True, check=check)


def _http(url: str, *, text: bool = False) -> Any:
    # Local service probes must never use the host's outbound HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=5) as response:
        data = response.read().decode("utf-8")
    return data if text else json.loads(data)


def _tts_settings() -> tuple[int, Path]:
    values = {}
    base = Path("/opt/qwen3-tts-openai")
    for path in (base / ".env", base / ".tools/service-network.env"):
        if path.is_file():
            for line in path.read_text().splitlines():
                key, separator, value = line.partition("=")
                if separator and key in {"PORT", "DATA_DIR"}:
                    values[key] = value.strip().strip("\"'")
    data = Path(values.get("DATA_DIR", "data"))
    return int(values.get("PORT", "12302")), (data if data.is_absolute() else base / data)


def _tts_activity() -> dict[str, Any]:
    """Observe TTS health and job counters without submitting a request."""
    port, data = _tts_settings()
    tts = _http(f"http://127.0.0.1:{port}/health")
    if tts.get("service") != "qwen3-tts-openai":
        raise RuntimeError("TTS endpoint identity is not the authorized service")
    with sqlite3.connect(f"file:{data / 'metadata.sqlite3'}?mode=ro", uri=True) as db:
        jobs = db.execute(
            "SELECT state,count(*) FROM jobs WHERE state IN ('queued','running') GROUP BY state").fetchall()
        count = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
    return {"active_job": bool(tts.get("active_job_id")), "persistent_active_jobs": jobs, "job_count": count}


def _tts_call_condition(before: dict[str, Any] | None, after: dict[str, Any], *,
                        declaration: str = "user_declared_none") -> dict[str, Any]:
    active = bool(after.get("active_job") or after.get("persistent_active_jobs"))
    before_count = before.get("job_count") if before is not None else None
    after_count = after.get("job_count")
    new_jobs = after_count - before_count if isinstance(before_count, int) and isinstance(after_count, int) else None
    counts_known = new_jobs is not None
    retention_changed = new_jobs is not None and new_jobs < 0
    return {"declaration": declaration, "before": before, "after": after,
        "status": ("observed_activity" if declaration == "uncontrolled_observed_only" else "violated")
            if active or (new_jobs is not None and new_jobs > 0) else
            "no_observed_activity" if counts_known and not retention_changed else "unknown",
        "observed_new_jobs": new_jobs if new_jobs is not None and new_jobs >= 0 else None,
        "reason": "counter_retention_changed" if retention_changed else
            "active_or_new_jobs" if active or (new_jobs is not None and new_jobs > 0) else
            "equal_start_end_counters" if counts_known else "counter_baseline_unavailable",
        "limitation": "start/end health and persistent-job counters are not atomic admission control; short calls without a persistent job may be unobserved"}


def drain_evidence() -> dict[str, Any]:
    """Read runtime queue states only, never document/job request contents."""
    evidence: dict[str, Any] = {}
    moparse = _http("http://127.0.0.1:12303/health")
    native = _http("http://127.0.0.1:12432/ready")
    evidence["moparse_queue"] = moparse["queue"]
    evidence["native_active_requests"] = native["active_requests"]
    jobs_code = ("import sqlite3,json;db=sqlite3.connect('file:/data/jobs.db?mode=ro',uri=True);"
                 "print(json.dumps(db.execute(\"SELECT status,count(*) FROM jobs WHERE status IN ('queued','running') GROUP BY status\").fetchall()))")
    evidence["moparse_persistent_active_jobs"] = json.loads(_run(["docker", "exec", "moparse", "python", "-c", jobs_code]).stdout)
    evidence["inference_engine_queues"] = {}
    for name, port in (("docling_glm_ocr", 8001), ("moparse-mineru-vllm", 12431)):
        metrics = _http(f"http://127.0.0.1:{port}/metrics", text=True)
        values = [float(line.rsplit(" ", 1)[1]) for line in metrics.splitlines()
                  if line.startswith(("vllm:num_requests_running{", "vllm:num_requests_waiting{"))]
        if len(values) < 2:
            raise RuntimeError(f"remote engine queue evidence is unavailable for {name}")
        evidence["inference_engine_queues"][name] = values
    try:
        tts = _tts_activity()
        evidence["tts_active_job"] = tts["active_job"]
        evidence["tts_persistent_active_jobs"] = tts["persistent_active_jobs"]
        evidence["tts_activity"] = tts
    except Exception as exc:
        evidence["tts_activity"] = {"status": "unknown", "error": f"{type(exc).__name__}: {exc}"}
    evidence["idle"] = (moparse["queue"]["active"] == 0 and native["active_requests"] == 0
        and not evidence["moparse_persistent_active_jobs"]
        and all(value == 0 for values in evidence["inference_engine_queues"].values() for value in values))
    evidence["limitation"] = "MO-Parse drains through graceful shutdown; co-resident TTS is observed, not controlled or awaited"
    return evidence


def snapshot() -> dict[str, Any]:
    containers = {}
    for name in CONTAINERS:
        record = json.loads(_run(["docker", "inspect", name]).stdout)[0]
        containers[name] = {"running": bool(record["State"]["Running"]),
                            "image_id": record["Image"], "container_id": record["Id"],
                            "device_requests": record["HostConfig"].get("DeviceRequests", [])}
    units = {}
    for name in SYSTEMD_UNITS:
        units[name] = _observe_unit_state(name)
    gpu = _run(["nvidia-smi", "--query-gpu=index,uuid,memory.total,memory.used,power.limit",
                "--format=csv,noheader"]).stdout.splitlines()
    return {"containers": containers, "systemd_units": units, "gpus": gpu,
            "phase": "snapshot", "authorized_gpu": "1"}


def _save(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _tts_identity_condition(before: dict[str, Any], after: dict[str, Any],
                            previous: dict[str, Any] | None = None) -> dict[str, Any]:
    keys = ("MainPID", "InvocationID")
    before_identity = {key: before.get(key) for key in keys}
    after_identity = {key: after.get(key) for key in keys}
    changed = [key for key in keys if before_identity[key] not in (None, "")
               and after_identity[key] not in (None, "")
               and str(before_identity[key]) != str(after_identity[key])]
    previous = previous or {}
    changed_keys = sorted(set(changed) | set(previous.get("changed_keys", [])))
    complete = all(before_identity[key] not in (None, "") and after_identity[key] not in (None, "") for key in keys)
    condition = {"status": "changed" if changed_keys else "unchanged" if complete else "unknown",
        "before": before_identity, "after": after_identity, "changed_keys": changed_keys,
        "scope": "measurement condition, independent of service health and MO-Parse restoration"}
    if changed_keys:
        condition["first_changed_after"] = previous.get("first_changed_after", after_identity)
    return condition


def restore(path: Path) -> dict[str, Any]:
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("remote_ownership") == "unresolved" or any(
            status != "stopped" for status in state.get("research_owners", {}).values()):
        raise RuntimeError("remote execution ownership is unresolved; acknowledge cleanup before restoration")
    failures = []
    state["restoration_actions"] = []
    # New windows own only explicitly attempted container pauses. Older records
    # lack that list; inspect their originally running containers as before.
    paused = (set(state.get("pause_attempted_containers", [])) | set(state.get("paused_containers", []))
              if state.get("tts_policy") == "keep_running" else set(CONTAINERS))
    for name in CONTAINERS:
        before = state.get("containers", {}).get(name, {})
        if before.get("running") and name in paused:
            try:
                current = json.loads(_run(["docker", "inspect", name]).stdout)[0]
                if current["Id"] != before["container_id"] or current["Image"] != before["image_id"]:
                    raise RuntimeError("container identity changed during maintenance")
                if not current["State"]["Running"]:
                    _run(["docker", "start", name])
                    state["restoration_actions"].append({"service": name, "action": "start_owned_pause"})
            except Exception as exc:
                failures.append({"service": name, "error": str(exc)})
    for name in SYSTEMD_UNITS:
        # The current user instruction forbids changing TTS even if an older
        # record claimed an owned stop. Observe its health; never restart it.
        state["restoration_actions"].append({"service": name, "action": "keep_state_no_owned_stop"})
    state["phase"] = "restoration_failed" if failures else "restored"
    state["restoration_errors"] = failures
    if not failures:
        deadline = time.monotonic() + 900
        while True:
            try:
                after = snapshot()
                checks = {}
                for name in CONTAINERS:
                    if state["containers"][name]["running"]:
                        live = json.loads(_run(["docker", "inspect", name]).stdout)[0]
                        checks[name] = live["State"].get("Health", {}).get("Status") == "healthy"
                before_tts = state.get("systemd_units", {}).get(SYSTEMD_UNITS[0], {})
                after_tts = after.get("systemd_units", {}).get(SYSTEMD_UNITS[0], {})
                state["tts_identity_condition"] = _tts_identity_condition(
                    before_tts, after_tts, state.get("tts_identity_condition"))
                # TTS is managed externally. Readiness/activity changes and
                # query failures cannot block recovery of our MO-Parse owners.
                try:
                    port, _ = _tts_settings()
                    tts = _http(f"http://127.0.0.1:{port}/ready")
                    state["tts_readiness_observation"] = {"status": "observed", "ready":
                        tts.get("service") == "qwen3-tts-openai" and tts.get("inference_ready") is True}
                except Exception as exc:
                    state["tts_readiness_observation"] = {"status": "unknown", "error": str(exc)}
                try:
                    activity = _tts_activity()
                    state["tts_no_calls_condition"] = _tts_call_condition(state.get("tts_activity_before"), activity,
                        declaration=state.get("tts_calls", "user_declared_none"))
                except Exception as exc:
                    state["tts_no_calls_condition"] = {"declaration": state.get("tts_calls", "unknown"), "status": "unknown",
                        "reason": "activity_observation_unavailable", "error": str(exc)}
                if all(checks.values()):
                    state["recovery_checks"] = checks
                    state["after"] = after
                    break
            except Exception as exc:
                state["last_recovery_probe_error"] = str(exc)
            if time.monotonic() >= deadline:
                failures.append({"service": "recovery", "error": "health/readiness did not recover within 900 seconds"})
                state["phase"] = "restoration_failed"
                break
            time.sleep(1)
    _save(path, state)
    if failures:
        raise RuntimeError(f"service restoration incomplete; inspect {path}")
    return state


@contextmanager
def gpu1_window(state_path: Path) -> Iterator[dict[str, Any]]:
    """Pause MO-Parse inference containers, keep TTS resident, restore in finally.

    The caller must close all research inference services and drain their owned
    requests before leaving this context. No workload is started here.
    """
    if state_path.exists():
        old = json.loads(state_path.read_text(encoding="utf-8"))
        if old.get("phase") != "restored":
            raise RuntimeError(f"an unfinished maintenance record exists: {state_path}")
    state = snapshot()
    state.update(tts_policy="keep_running", tts_calls="uncontrolled_observed_only",
        tts_observation_policy="observe_only", user_instruction_date="2026-10-26",
        kept_tts={name: state["systemd_units"].get(name, {}) for name in SYSTEMD_UNITS},
        paused_containers=[], pause_attempted_containers=[], stopped_systemd_units=[])
    _save(state_path, state)
    token = _active_window.set((state_path, state))
    try:
        state["drain_observations"] = []
        for _ in range(2):
            evidence = drain_evidence()
            state["drain_observations"].append(evidence)
            if "tts_activity" in evidence and "tts_activity_before" not in state:
                state["tts_activity_before"] = evidence["tts_activity"]
            _save(state_path, state)
            if not evidence["idle"]:
                raise RuntimeError("production work is still in flight; maintenance was not entered")
            time.sleep(1)
        for name in CONTAINERS:
            if state["containers"][name]["running"]:
                requests = state["containers"][name]["device_requests"]
                devices = [device for request in requests for device in (request.get("DeviceIDs") or [])]
                if "1" not in devices or "0" in devices:
                    raise RuntimeError(f"authorized service {name} is not pinned exclusively to GPU 1")
                # Infinite grace avoids converting a newly accepted request
                # into a forced termination during the admission-race window.
                state["pause_attempted_containers"].append(name)
                _save(state_path, state)
                _run(["docker", "stop", "--time", "-1", name])
                stopped = json.loads(_run(["docker", "inspect", name]).stdout)[0]["State"]
                logs = _run(["docker", "logs", "--tail", "120", name], check=False)
                state.setdefault("graceful_shutdown", {})[name] = {"state": stopped,
                    "terminal_logs": logs.stdout + logs.stderr}
                _save(state_path, state)
                if stopped["Running"] or stopped.get("ExitCode") == 137:
                    raise RuntimeError(f"graceful termination is not confirmed for {name}")
                state["paused_containers"].append(name)
        state["phase"] = "maintenance"
        _save(state_path, state)
        yield state
    finally:
        _save(state_path, state)
        try:
            restore(state_path)
        finally:
            _active_window.reset(token)


def inference_command(config: dict[str, Any], *, model_path: Path, model_name: str,
                      port: int, name: str) -> list[str]:
    """Build, but do not execute, a constrained vLLM inference container."""
    image = config.get("inference_image")
    if not image:
        raise ValueError("inference_image must identify a prepared fixed image")
    if not name.startswith("moparse-eval-"):
        raise ValueError("research inference container names must start with moparse-eval-")
    compilation: dict[str, Any] = {"mode": 0, "cudagraph_mode": "FULL_DECODE_ONLY",
                   "cudagraph_capture_sizes": [1, 2, 3, 4], "max_cudagraph_capture_size": 4}
    cpus, memory = config.get("cpus", 4), config.get("memory_gib", 20)
    gpu_budget = config.get("gpu_memory_gib", DEFAULT_GPU_BUDGET_GIB)
    glm = config.get("family") == "glm"
    rotary = config.get("rotary_embedding")
    if rotary is not None:
        if not glm or rotary != "native":
            raise ValueError("rotary_embedding supports only the explicit GLM native experiment")
        # vLLM 0.19.1's MRoPE CUDA kernel ignores GLM's GPT-J pairing.
        # Keep decode CUDA Graphs and all other custom ops; change only RoPE.
        compilation["custom_ops"] = ["all", "-rotary_embedding"]
    command = ["docker", "run", "--detach", "--name", name, "--gpus", "device=1",
               "--cpus", str(cpus), "--memory", f"{memory}g", "--memory-swap", f"{memory}g",
               "--shm-size", "2g", "--publish", f"127.0.0.1:{port}:8000",
               "--mount", f"type=bind,src={model_path.resolve()},dst=/model,readonly",
               "--env", "HF_HUB_OFFLINE=1", "--env", "TRANSFORMERS_OFFLINE=1",
               "--env", "VLLM_NO_USAGE_STATS=1", "--env", f"OMP_NUM_THREADS={cpus}",
               image, str(Path("/model") / config.get("model_subdir", "")), "--served-model-name", model_name,
               "--dtype", "half", "--max-num-seqs", "4", "--max-model-len", "16384" if glm else "8192",
               "--max-num-batched-tokens", "8192" if glm else "2048", "--kv-cache-memory-bytes", "1073741824" if glm else "134217728",
               "--gpu-memory-utilization", str(gpu_budget * 1024 / 22528),
               "--compilation-config", json.dumps(compilation, separators=(",", ":")), "--cudagraph-metrics"]
    if config.get("family") == "mineru":
        command += ["--logits-processors", "mineru_vl_utils:MinerULogitsProcessor",
                    "--limit-mm-per-prompt", '{"image":1,"video":0}']
    return command


def native_paddle_command(service: dict[str, Any], config_path: Path, name: str) -> list[str]:
    project = Path(__file__).resolve().parent.parent
    command = ["docker", "run", "--detach", "--name", name, "--gpus", "device=1",
        "--cpus", "4", "--memory", "20g", "--memory-swap", "20g", "--shm-size", "2g",
        "--publish", f"127.0.0.1:{service['port']}:8000",
        "--mount", f"type=bind,src={project / 'moparse_eval'},dst=/research/moparse_eval,readonly",
        "--mount", f"type=bind,src={config_path.resolve()},dst=/research-config.json,readonly",
        "--workdir", "/research", "--env", "PYTHONPATH=/research",
        "--env", "CUDA_VISIBLE_DEVICES=0", "--env", "HF_HUB_OFFLINE=1",
        "--env", "TRANSFORMERS_OFFLINE=1", "--env", "OMP_NUM_THREADS=4",
        "--env", "OPENBLAS_NUM_THREADS=4", "--env", "MKL_NUM_THREADS=4", "--entrypoint", "python3"]
    for host, destination in service["model_mounts"].items():
        if not str(destination).startswith("/models/"):
            raise ValueError("native model mounts must stay under /models")
        command += ["--mount", f"type=bind,src={Path(host).resolve()},dst={destination},readonly"]
    return command + [service["inference_image"], "-m", "moparse_eval.paddle_server",
                      "--config", "/research-config.json", "--port", "8000"]


@asynccontextmanager
async def inference_services(config: dict[str, Any], artifacts_dir: Path):
    """Own experimental inference containers through confirmed process exit.

    The enclosing GPU 1 maintenance window is controlled by the caller. This
    context does not stop any production service. Hybrid backends share the
    aggregate inference budget; resource exhaustion is never a model substitute.
    """
    services = config.get("inference_services", [])
    gpu_budget = float(config.get("resources", {}).get("gpu_memory_gib", DEFAULT_GPU_BUDGET_GIB))
    if not math.isfinite(gpu_budget) or not 0 < gpu_budget <= DEFAULT_GPU_BUDGET_GIB:
        raise ValueError("shared GPU budget must be positive and at most 16 GiB while TTS stays resident")
    for key, limit in (("cpus", 4), ("memory_gib", 20), ("gpu_memory_gib", gpu_budget)):
        shares = [float(service.get(key, limit)) for service in services]
        if any(not math.isfinite(share) or share <= 0 for share in shares) or sum(shares) > limit:
            raise ValueError(f"inference services exceed the shared {key} budget")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    state_path = artifacts_dir / "inference-ownership.json"
    lifecycle_started = time.monotonic()
    state: dict[str, Any] = {"phase": "starting", "containers": [], "cleanup_confirmed": False,
        "initialization_started_at": datetime.now(UTC).isoformat(),
        "timing_scope": "owned inference service initialization/readiness and lifetime; separate from worker processing",
        "resource_scope": "sampled lifecycle peaks including initialization and Graph capture; not per-sample peaks",
        "tts_policy": "keep_running", "tts_calls": "uncontrolled_observed_only",
        "tts_observation_policy": "observe_only", "user_instruction_date": "2026-10-26",
        "owned_gpu_budget_gib": gpu_budget}
    _save(state_path, state)
    live_config = dict(config)
    live_config["endpoints"] = dict(config.get("endpoints", {}))
    owned: list[tuple[str, dict[str, Any]]] = []
    sampler = ContainerSampler([], artifacts_dir / "resources.json", gpu=bool(services),
                               gpu_budget_gib=gpu_budget)
    sampler.start()
    try:
        for service in services:
            service = dict(service)
            service.setdefault("gpu_memory_gib", gpu_budget)
            name = f"moparse-eval-{config['pipeline'].lower()}-{service['role']}-{uuid.uuid4().hex[:10]}"
            if service.get("family") == "paddle-native":
                server_config = artifacts_dir / f"{name}-config.json"
                _save(server_config, service["server_config"])
                command = native_paddle_command(service, server_config, name)
            else:
                command = inference_command(service, model_path=Path(service["host_model_path"]),
                    model_name=service["model_name"], port=int(service["port"]), name=name)
            service_started = time.monotonic()
            record = {"name": name, "command": command, "role": service["role"],
                "initialization_started_at": datetime.now(UTC).isoformat(),
                "initialization_started_monotonic": service_started,
                "resource_budget": {key: service.get(key) for key in ("cpus", "memory_gib", "gpu_memory_gib")}}
            state["containers"].append(record)
            owned.append((name, service))
            sampler.names.append(name)
            record_owner(name, "starting")
            _save(state_path, state)
            launch = asyncio.create_task(asyncio.to_thread(_run, command))
            launch_cancelled = False
            while not launch.done():
                try:
                    await asyncio.shield(launch)
                except asyncio.CancelledError:
                    launch_cancelled = True
            result = launch.result()
            record.update(id=result.stdout.strip(), container_created_at=datetime.now(UTC).isoformat())
            record_owner(name, "running")
            _save(state_path, state)
            if launch_cancelled:
                raise asyncio.CancelledError
            endpoint = f"http://127.0.0.1:{service['port']}"
            deadline = time.monotonic() + float(service.get("startup_timeout_seconds", 900))
            while True:
                try:
                    response = await asyncio.to_thread(_http, endpoint + "/v1/models")
                    if any(model.get("id") == service["model_name"] for model in response.get("data", [])):
                        record.update(ready_at=datetime.now(UTC).isoformat(),
                            initialization_ended_at=datetime.now(UTC).isoformat(),
                            initialization_to_readiness_host_seconds=time.monotonic() - service_started,
                            initialization_status="ready", readiness_evidence=response)
                        break
                except Exception:
                    pass
                inspected = await asyncio.to_thread(_run, ["docker", "inspect", name], check=False)
                if inspected.returncode or not json.loads(inspected.stdout)[0]["State"]["Running"]:
                    raise RuntimeError(f"research inference service exited before readiness: {name}")
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"research inference service startup timeout: {name}")
                await asyncio.sleep(0.5)
            live_config["endpoints"][service["role"]] = (
                endpoint + "/v1/chat/completions" if service["role"] == "glm" else endpoint)
        state["phase"] = "ready_for_bounded_trial"
        state["ready_at"] = datetime.now(UTC).isoformat()
        state["initialization_status"] = "ready"
        state["initialization_ended_at"] = state["ready_at"]
        state["initialization_to_readiness_host_seconds"] = time.monotonic() - lifecycle_started
        state["graphs"] = "startup logs alone do not establish inference correctness"
        live_config["inference_resource_log"] = str(sampler.path)
        _save(state_path, state)
        yield live_config
    finally:
        async def cleanup() -> None:
            errors = []
            for name, _service in reversed(owned):
                record = next(value for value in state["containers"] if value["name"] == name)
                if _service.get("family") in {"glm", "mineru"} and "ready_at" in record:
                    try:
                        metrics = await asyncio.to_thread(_http,
                            f"http://127.0.0.1:{_service['port']}/metrics", text=True)
                        metrics_path = artifacts_dir / f"{name}-metrics.prom"
                        metrics_path.write_text(metrics, encoding="utf-8")
                        record["final_engine_metrics"] = metrics_path.name
                    except Exception as exc:
                        record["final_engine_metrics_error"] = type(exc).__name__
                record["shutdown_started_at"] = datetime.now(UTC).isoformat()
                _save(state_path, state)
                stopped = await asyncio.to_thread(_run, ["docker", "stop", "--time", "-1", name], check=False)
                inspected = await asyncio.to_thread(_run, ["docker", "inspect", name], check=False)
                logs = await asyncio.to_thread(_run, ["docker", "logs", name], check=False)
                (artifacts_dir / f"{name}.log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
                if inspected.returncode and "No such" not in inspected.stderr:
                    errors.append({"container": name, "error": inspected.stderr})
                elif not inspected.returncode and json.loads(inspected.stdout)[0]["State"]["Running"]:
                    errors.append({"container": name, "error": stopped.stderr or "process is still running"})
                else:
                    record["ended_at"] = datetime.now(UTC).isoformat()
                    record["lifecycle_host_seconds"] = time.monotonic() - record["initialization_started_monotonic"]
                    if not inspected.returncode:
                        record["terminal_state"] = json.loads(inspected.stdout)[0]["State"]
                    if "ready_at" not in record:
                        record.update(initialization_status="failed_before_readiness",
                            initialization_ended_at=record["ended_at"],
                            initialization_to_failure_host_seconds=record["lifecycle_host_seconds"])
                    record_owner(name, "stopped")
                    await asyncio.to_thread(_run, ["docker", "rm", name], check=False)
            live_config["inference_observed_resources"] = await sampler.close()
            state["phase"] = "cleanup_failed" if errors else "stopped"
            state["cleanup_confirmed"] = not errors
            state["cleanup_errors"] = errors
            state["ended_at"] = datetime.now(UTC).isoformat()
            state["lifecycle_host_seconds"] = time.monotonic() - lifecycle_started
            if "ready_at" not in state:
                state["initialization_status"] = "failed_before_readiness"
                state["initialization_ended_at"] = state["ended_at"]
                state["initialization_to_failure_host_seconds"] = state["lifecycle_host_seconds"]
            _save(state_path, state)
            if errors:
                raise RuntimeError(f"experimental inference processes still own execution; see {state_path}")
            if live_config["inference_observed_resources"].get("gpu_budget_exceeded_in_observed_samples") is True:
                raise RuntimeError(f"owned inference containers exceeded their shared GPU memory budget; see {sampler.path}")
        cleanup_task = asyncio.create_task(cleanup())
        while not cleanup_task.done():
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                continue
        cleanup_task.result()
