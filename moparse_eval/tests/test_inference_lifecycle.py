"""Synthetic Docker/HTTP responses only; no GPU process is started."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("ready", [True, False])
@pytest.mark.parametrize("gpu_shares", [(16,), (6, 10)])
async def test_initialization_lifecycle_and_graceful_confirmed_cleanup(
    monkeypatch, tmp_path: Path, ready: bool, gpu_shares: tuple[int, ...],
) -> None:
    import moparse_eval.maintenance as maintenance
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "run"]:
            return SimpleNamespace(stdout="synthetic-container-id", stderr="", returncode=0)
        if command[:2] == ["docker", "inspect"]:
            return SimpleNamespace(stdout=json.dumps([{"State": {"Running": False, "ExitCode": 0}}]),
                                   stderr="", returncode=0)
        return SimpleNamespace(stdout="graceful shutdown complete", stderr="", returncode=0)
    def http(url):
        if not ready:
            raise RuntimeError("synthetic initialization failure")
        return {"data": [{"id": "synthetic-model"}]}
    class Sampler:
        def __init__(self, names, path, **kwargs):
            self.names, self.path = names, path
        def start(self):
            pass
        async def close(self):
            return {"scope": "observed service lifetime, not per sample"}
    monkeypatch.setattr(maintenance, "_run", run)
    monkeypatch.setattr(maintenance, "_http", http)
    monkeypatch.setattr(maintenance, "ContainerSampler", Sampler)
    config = {"pipeline": "P05", "resources": {"gpu_memory_gib": 16}, "inference_services": [
        {"role": "glm" if index == 0 else "mineru", "family": "glm" if index == 0 else "mineru",
        "inference_image": "synthetic-image", "host_model_path": str(tmp_path / "weights"),
        "model_name": "synthetic-model", "port": 12541 + index,
        "cpus": 4 / len(gpu_shares), "memory_gib": 20 / len(gpu_shares), "gpu_memory_gib": share}
        for index, share in enumerate(gpu_shares)]}
    async def use_service():
        async with maintenance.inference_services(config, tmp_path) as live:
            assert live["endpoints"]["glm"].endswith("/v1/chat/completions")
    if ready:
        await use_service()
    else:
        with pytest.raises(RuntimeError, match="exited before readiness"):
            await use_service()
    state = json.loads((tmp_path / "inference-ownership.json").read_text())
    record = state["containers"][0]
    assert state["phase"] == "stopped" and state["cleanup_confirmed"]
    assert record["initialization_started_at"] and record["initialization_ended_at"] and record["ended_at"]
    assert record["initialization_status"] == ("ready" if ready else "failed_before_readiness")
    if ready:
        assert record["initialization_to_readiness_host_seconds"] >= 0
    assert any(command[:4] == ["docker", "stop", "--time", "-1"] for command in calls)
    assert (tmp_path / (record["name"] + ".log")).read_text() == "graceful shutdown complete"


@pytest.mark.asyncio
@pytest.mark.parametrize("samples", [[], [{"containers": [{"Name": "synthetic", "MemUsage": "unreadable"}]}]])
async def test_missing_resource_samples_remain_unknown_not_zero(tmp_path: Path, samples: list) -> None:
    from moparse_eval.maintenance import ContainerSampler
    sampler = ContainerSampler(["synthetic"], tmp_path / "resources.json", gpu=True)
    sampler.samples = samples
    summary = await sampler.close()
    assert summary["observed_host_memory_peak_bytes_by_container"]["synthetic"] is None
    assert summary["observed_shared_host_memory_peak_bytes"] is None
    assert summary["observed_gpu1_peak_memory_mib"] is None
    assert summary["gpu_budget_exceeded_in_observed_samples"] is None
    assert summary["sampling_completeness"]["status"] in {"unknown", "partial"}


def test_actual_affinity_and_cgroup_caps_are_not_filled_from_declared_limits(monkeypatch) -> None:
    import moparse_eval.runtime as runtime
    monkeypatch.setattr(runtime.os, "sched_getaffinity", lambda pid: {2, 4})
    monkeypatch.setattr(runtime.Path, "read_text", lambda path: "400000 100000" if path.name == "cpu.max" else "8589934592")
    actual = runtime.actual_worker_limits()
    assert actual["sched_getaffinity"] == [2, 4]
    assert actual["cpu_quota_cpus"] == 4
    assert actual["memory_hard_limit_bytes"] == 8 * 1024 ** 3
