#!/usr/bin/env python3
"""Read-only, bounded-memory GPU/container/vLLM runtime sampling.

Device power and energy include EVERY process on that GPU. They are never
attributed to a parser. Container-owned GPU memory and observed process SM are
reported separately, from Docker host PID membership. Missing data stays null.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import ProxyHandler, Request, build_opener

GPU_FIELDS = (
    "index",
    "uuid",
    "name",
    "power.draw",
    "power.limit",
    "memory.used",
    "memory.total",
    "utilization.gpu",
    "utilization.memory",
)
METRICS = re.compile(
    r"^vllm:(?:num_requests_|num_preemptions|prompt_tokens|generation_tokens|"
    r"prefix_cache_|gpu_prefix_cache_|cpu_prefix_cache_|gpu_cache_usage|"
    r"kv_cache_usage|request_success|request_failure|request_tokens|"
    r"request_prompt_tokens_(?:sum|count)|request_generation_tokens_(?:sum|count))"
)
METRIC_LINE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?\s+(\S+)(?:\s+\S+)?$")


def number(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def integer(value: Any) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None and parsed.is_integer() else None


def memory_bytes(value: Any) -> int | None:
    match = re.fullmatch(r"\s*([\d.]+)\s*(B|[KMGTPE]i?B)\s*", str(value), re.IGNORECASE)
    if not match:
        return None
    amount = number(match.group(1))
    unit = match.group(2).upper()
    power = "BKMGTPE".index(unit[0])
    return int(amount * ((1024 if "I" in unit else 1000) ** power)) if amount is not None else None


def command(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=8, check=True)
    return result.stdout


def gpu_devices() -> list[dict[str, Any]]:
    output = command(
        ["nvidia-smi", "--query-gpu=" + ",".join(GPU_FIELDS), "--format=csv,noheader,nounits"]
    )
    import csv

    rows = []
    for values in csv.reader(output.splitlines(), skipinitialspace=True):
        if len(values) != len(GPU_FIELDS):
            raise ValueError("unexpected nvidia-smi device CSV shape")
        raw = dict(zip(GPU_FIELDS, values, strict=True))
        rows.append(
            {
                "index": integer(raw["index"]),
                "uuid": raw["uuid"],
                "name": raw["name"],
                "power_watts_shared_device": number(raw["power.draw"]),
                "power_limit_watts": number(raw["power.limit"]),
                "memory_used_MiB_shared_device": number(raw["memory.used"]),
                "memory_total_MiB": number(raw["memory.total"]),
                "utilization_gpu_pct_shared_device": number(raw["utilization.gpu"]),
                "utilization_memory_pct_shared_device": number(raw["utilization.memory"]),
            }
        )
    return rows


def gpu_processes() -> list[dict[str, Any]]:
    import csv

    output = command(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    rows = []
    for values in csv.reader(output.splitlines(), skipinitialspace=True):
        if len(values) != 4:
            raise ValueError("unexpected nvidia-smi process CSV shape")
        uuid, pid, name, memory = values
        rows.append(
            {"gpu_uuid": uuid, "pid": integer(pid), "name": name, "memory_MiB": number(memory)}
        )
    return rows


def parse_pmon(output: str) -> list[dict[str, Any]]:
    fields = None
    rows = []
    for line in output.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        if parts[0] == "#":
            candidate = parts[1:]
            if "gpu" in candidate and "pid" in candidate and "sm" in candidate:
                fields = candidate
            continue
        if fields is None or len(parts) < len(fields):
            continue
        raw = dict(zip(fields, parts, strict=False))
        pid = integer(raw.get("pid"))
        if pid is None:
            continue
        rows.append(
            {
                "gpu_index": integer(raw.get("gpu")),
                "pid": pid,
                "sm_pct": number(raw.get("sm")),
                "memory_util_pct": number(raw.get("mem")),
                "fb_MiB": number(raw.get("fb")),
            }
        )
    return rows


def container_pids(name: str) -> list[int]:
    output = command(["docker", "top", name, "-eo", "pid,ppid"])
    pids = [integer(line.split()[0]) for line in output.splitlines()[1:] if line.split()]
    return sorted(pid for pid in pids if pid is not None)


def docker_stats(containers: list[str]) -> list[dict[str, Any]]:
    output = command(["docker", "stats", "--no-stream", "--format", "{{json .}}", *containers])
    result = []
    for line in output.splitlines():
        raw = json.loads(line)
        used = str(raw.get("MemUsage", "")).split(" / ", 1)
        result.append(
            {
                "container": raw.get("Name"),
                "cpu_pct_one_core_100": number(raw.get("CPUPerc")),
                "memory_used_bytes": memory_bytes(used[0]),
                "memory_limit_bytes": memory_bytes(used[1]) if len(used) > 1 else None,
                "memory_pct": number(raw.get("MemPerc")),
                "pids": integer(raw.get("PIDs")),
            }
        )
    return result


def parse_metrics(output: str) -> list[dict[str, Any]]:
    rows = []
    for line in output.splitlines():
        match = METRIC_LINE.match(line)
        if match and METRICS.match(match.group(1)):
            rows.append(
                {
                    "name": match.group(1),
                    "labels": match.group(2) or "",
                    "value": number(match.group(3)),
                }
            )
    return rows


def vllm_metrics(url: str) -> list[dict[str, Any]]:
    request = Request(
        url.rstrip("/") + "/metrics", headers={"User-Agent": "moparse-runtime-monitor/1"}
    )
    # Monitoring private endpoints must not traverse host HTTP proxy settings.
    with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
        return parse_metrics(response.read(8 * 1024 * 1024).decode())


def own_gpu_usage(processes, memberships, pmon):
    result = {}
    for name, pids in memberships.items():
        if pids is None:
            result[name] = {
                "membership_available": False,
                "gpu_memory_MiB_by_uuid": None,
                "sm_pct_observed_sum": None,
            }
            continue
        owned = set(pids)
        memories: dict[str, float] = {}
        unknown_memory = set()
        for process in processes or []:
            if process["pid"] not in owned:
                continue
            uuid = process["gpu_uuid"]
            if process["memory_MiB"] is None:
                unknown_memory.add(uuid)
            else:
                memories[uuid] = memories.get(uuid, 0.0) + process["memory_MiB"]
        for uuid in unknown_memory:
            memories[uuid] = None
        sms = [
            row["sm_pct"] for row in pmon or [] if row["pid"] in owned and row["sm_pct"] is not None
        ]
        result[name] = {
            "membership_available": True,
            "gpu_memory_MiB_by_uuid": memories if processes is not None else None,
            "sm_pct_observed_sum": sum(sms) if sms else None,
            "sm_valid_process_samples": len(sms),
        }
    return result


class Summary:
    def __init__(self):
        self.samples = 0
        self.errors: dict[str, int] = {}
        self.devices: dict[str, dict] = {}
        self.containers: dict[str, dict] = {}
        self.metrics: dict[str, dict] = {}

    def add(self, sample):
        self.samples += 1
        for error in sample["errors"]:
            self.errors[error["source"]] = self.errors.get(error["source"], 0) + 1
        observed = set()
        for device in sample.get("devices") or []:
            uuid = device["uuid"]
            observed.add(uuid)
            state = self.devices.setdefault(
                uuid,
                {
                    "index": device["index"],
                    "name": device["name"],
                    "energy_joules_shared_device": 0.0,
                    "energy_intervals_observed": 0,
                    "energy_gaps": 0,
                    "gpu_utilization_samples": 0,
                    "gpu_utilization_sum": 0.0,
                    "memory_used_peak_MiB_shared_device": None,
                    "_previous_power": None,
                },
            )
            power = device["power_watts_shared_device"]
            previous = state["_previous_power"]
            if power is not None and previous is not None:
                state["energy_joules_shared_device"] += (
                    (previous[1] + power) / 2 * (sample["monotonic"] - previous[0])
                )
                state["energy_intervals_observed"] += 1
            elif previous is not None:
                state["energy_gaps"] += 1
            state["_previous_power"] = (sample["monotonic"], power) if power is not None else None
            utilization = device["utilization_gpu_pct_shared_device"]
            if utilization is not None:
                state["gpu_utilization_sum"] += utilization
                state["gpu_utilization_samples"] += 1
            memory = device["memory_used_MiB_shared_device"]
            if memory is not None:
                old = state["memory_used_peak_MiB_shared_device"]
                state["memory_used_peak_MiB_shared_device"] = (
                    memory if old is None else max(old, memory)
                )
        for uuid, state in self.devices.items():
            if uuid not in observed:
                if state["_previous_power"] is not None:
                    state["energy_gaps"] += 1
                state["_previous_power"] = None
        for name, own in sample.get("owned_gpu", {}).items():
            state = self.containers.setdefault(
                name,
                {
                    "gpu_memory_peak_MiB_by_uuid": {},
                    "sm_observed_sum": 0.0,
                    "sm_samples": 0,
                    "cpu_pct_peak_one_core_100": None,
                    "memory_peak_bytes": None,
                },
            )
            for uuid, memory in (own.get("gpu_memory_MiB_by_uuid") or {}).items():
                if memory is not None:
                    state["gpu_memory_peak_MiB_by_uuid"][uuid] = max(
                        state["gpu_memory_peak_MiB_by_uuid"].get(uuid, memory), memory
                    )
            if own.get("sm_pct_observed_sum") is not None:
                state["sm_observed_sum"] += own["sm_pct_observed_sum"]
                state["sm_samples"] += 1
        for stats in sample.get("docker_stats") or []:
            state = self.containers.get(stats["container"])
            if state is None:
                continue
            for current, peak in (
                ("cpu_pct_one_core_100", "cpu_pct_peak_one_core_100"),
                ("memory_used_bytes", "memory_peak_bytes"),
            ):
                value = stats[current]
                if value is not None:
                    old = state[peak]
                    state[peak] = value if old is None else max(old, value)
        for metric in sample.get("vllm_metrics") or []:
            if metric["value"] is None:
                continue
            key = metric["name"] + metric["labels"]
            state = self.metrics.setdefault(
                key,
                {
                    "name": metric["name"],
                    "labels": metric["labels"],
                    "first": metric["value"],
                    "last": metric["value"],
                    "counter_resets": 0,
                    "observed_counter_increase": 0.0 if metric["name"].endswith("_total") else None,
                },
            )
            if metric["name"].endswith("_total"):
                if metric["value"] >= state["last"]:
                    state["observed_counter_increase"] += metric["value"] - state["last"]
                else:
                    state["counter_resets"] += 1
            state["last"] = metric["value"]

    def export(self):
        devices = {}
        for uuid, raw in self.devices.items():
            state = {key: value for key, value in raw.items() if not key.startswith("_")}
            state["gpu_utilization_mean_pct_shared_device"] = (
                raw["gpu_utilization_sum"] / raw["gpu_utilization_samples"]
                if raw["gpu_utilization_samples"]
                else None
            )
            if not raw["energy_intervals_observed"]:
                state["energy_joules_shared_device"] = None
            devices[uuid] = state
        containers = {}
        for name, raw in self.containers.items():
            state = dict(raw)
            state["sm_mean_observed_process_sum_pct"] = (
                raw["sm_observed_sum"] / raw["sm_samples"] if raw["sm_samples"] else None
            )
            containers[name] = state
        return {
            "schema": "moparse-runtime-monitor-summary/1",
            "samples": self.samples,
            "errors_by_source": self.errors,
            "energy_scope": "Shared whole-device measured power integrated only across consecutive valid samples; never parser-owned energy",
            "memory_scope": "Own GPU FB peaks use host PIDs reported by docker top; device utilization includes unrelated processes",
            "sm_scope": "Sum of available owned process SM percentages per pmon sample; missing samples excluded, not replaced by zero",
            "devices": devices,
            "containers": containers,
            "vllm_metrics": list(self.metrics.values()),
        }


def save(path: Path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--containers", required=True, help="Comma-separated Docker names")
    parser.add_argument("--vllm-url", required=True)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    containers = [name.strip() for name in args.containers.split(",") if name.strip()]
    if not containers:
        parser.error("--containers must contain at least one name")
    args.output.mkdir(parents=True, exist_ok=True)
    samples_path = args.output / "samples.jsonl"
    if samples_path.exists() and samples_path.stat().st_size:
        parser.error("output samples already exist; choose a new output directory")
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    summary = Summary()
    save(
        args.output / "manifest.json",
        {
            "schema": "moparse-runtime-monitor/1",
            "started_at": datetime.now(UTC).isoformat(),
            "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "containers": containers,
            "interval_seconds": args.interval,
            "vllm_url": args.vllm_url,
            "device_power_is_shared": True,
            "container_env_read": False,
        },
    )
    with (
        samples_path.open("a", buffering=1) as output,
        ThreadPoolExecutor(max_workers=4 + len(containers)) as pool,
    ):
        while not stop.is_set() and not args.stop_file.exists():
            started = time.monotonic()
            tasks = {
                "devices": pool.submit(gpu_devices),
                "processes": pool.submit(gpu_processes),
                "pmon": pool.submit(
                    lambda: parse_pmon(command(["nvidia-smi", "pmon", "-c", "1", "-s", "um"]))
                ),
                "docker_stats": pool.submit(docker_stats, containers),
                "vllm_metrics": pool.submit(vllm_metrics, args.vllm_url),
            }
            memberships = {name: pool.submit(container_pids, name) for name in containers}
            sample = {"at": datetime.now(UTC).isoformat(), "monotonic": started, "errors": []}
            for source, future in [
                *tasks.items(),
                *[("pids:" + name, future) for name, future in memberships.items()],
            ]:
                try:
                    sample[source] = future.result()
                except Exception as exc:
                    sample[source] = None
                    # No stderr, environment, request headers or URL query values.
                    error = {"source": source, "type": type(exc).__name__}
                    if hasattr(exc, "code") and isinstance(exc.code, int):
                        error["http_status"] = exc.code
                    sample["errors"].append(error)
            sample["owned_gpu"] = own_gpu_usage(
                sample.get("processes"),
                {name: sample.get("pids:" + name) for name in containers},
                sample.get("pmon"),
            )
            sample["collection_seconds"] = time.monotonic() - started
            output.write(json.dumps(sample, ensure_ascii=False) + "\n")
            summary.add(sample)
            save(args.output / "summary.json", summary.export())
            stop.wait(max(0.0, args.interval - (time.monotonic() - started)))
    final = summary.export()
    final["finished_at"] = datetime.now(UTC).isoformat()
    save(args.output / "summary.json", final)


if __name__ == "__main__":
    main()
