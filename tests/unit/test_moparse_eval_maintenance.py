"""Controlled service/process observations; never call Docker, systemd or a GPU."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from moparse_eval import maintenance


def _result(stdout="", *, returncode=0, stderr=""):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _snapshot():
    return {"phase": "snapshot", "containers": {name: {
        "running": True, "container_id": name + "-id", "image_id": "image-id",
        "device_requests": [{"DeviceIDs": ["1"]}],
    } for name in maintenance.CONTAINERS}, "systemd_units": {maintenance.SYSTEMD_UNITS[0]: {
        "active": True, "ActiveState": "active", "MainPID": "50", "InvocationID": "tts-invocation",
        "ControlGroup": "/system.slice/qwen3-tts-openai.service",
    }}}


@pytest.mark.parametrize("fail_in_window", [False, True])
@pytest.mark.parametrize("final_job_count", [7, 8])
def test_window_preserves_tts_and_restores_only_its_container_pauses(
    monkeypatch, tmp_path, fail_in_window, final_job_count,
):
    initial = _snapshot()
    running = {name: True for name in maintenance.CONTAINERS}
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[0] != "systemctl", "TTS must never be stopped or restarted by this window"
        name = command[-1]
        if command[:2] == ["docker", "stop"]:
            running[name] = False
        elif command[:2] == ["docker", "start"]:
            running[name] = True
        elif command[:2] == ["docker", "inspect"]:
            return _result(json.dumps([{"Id": name + "-id", "Image": "image-id", "State": {
                "Running": running[name], "ExitCode": 0, "Health": {"Status": "healthy"}}}]))
        return _result()

    activity = {"active_job": False, "persistent_active_jobs": [], "job_count": 7}
    monkeypatch.setattr(maintenance, "_run", run)
    monkeypatch.setattr(maintenance, "snapshot", lambda: copy.deepcopy(initial))
    monkeypatch.setattr(maintenance, "drain_evidence", lambda: {"idle": True, "tts_activity": activity})
    monkeypatch.setattr(maintenance, "_tts_activity", lambda: {**activity, "job_count": final_job_count})
    monkeypatch.setattr(maintenance, "_tts_settings", lambda: (1, tmp_path))
    monkeypatch.setattr(maintenance, "_http", lambda url: {
        "service": "qwen3-tts-openai", "inference_ready": True})
    monkeypatch.setattr(maintenance.time, "sleep", lambda seconds: None)
    path = tmp_path / "maintenance.json"

    def enter():
        with maintenance.gpu1_window(path) as state:
            assert not any(running.values())
            assert state["tts_policy"] == "keep_running"
            assert state["tts_calls"] == "uncontrolled_observed_only"
            assert state["tts_observation_policy"] == "observe_only"
            assert state["user_instruction_date"] == "2026-10-26"
            assert state["kept_tts"][maintenance.SYSTEMD_UNITS[0]]["MainPID"] == "50"
            assert state["paused_containers"] == list(maintenance.CONTAINERS)
            assert state["stopped_systemd_units"] == []
            if fail_in_window:
                raise ValueError("synthetic worker failure")

    if fail_in_window:
        with pytest.raises(ValueError, match="synthetic worker failure"):
            enter()
    else:
        enter()
    final = json.loads(path.read_text())
    assert final["phase"] == "restored"
    assert all(running.values())
    assert final["tts_identity_condition"]["status"] == "unchanged"
    assert final["tts_no_calls_condition"]["status"] == ("no_observed_activity" if final_job_count == 7 else "observed_activity")
    assert final["tts_no_calls_condition"]["declaration"] == "uncontrolled_observed_only"
    assert len([call for call in calls if call[:2] == ["docker", "start"]]) == 2


@pytest.mark.parametrize("legacy_owned_stop", [False, True])
def test_restore_does_not_infer_an_owned_tts_stop_from_a_legacy_active_snapshot(
    monkeypatch, tmp_path, legacy_owned_stop,
):
    initial = _snapshot()
    if legacy_owned_stop:
        initial["stopped_systemd_units"] = [maintenance.SYSTEMD_UNITS[0]]
    path = tmp_path / "maintenance.json"
    path.write_text(json.dumps(initial))
    after = copy.deepcopy(initial)
    after["systemd_units"][maintenance.SYSTEMD_UNITS[0]]["active"] = False
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "inspect"]:
            return _result(json.dumps([{"Id": command[-1] + "-id", "Image": "image-id", "State": {
                "Running": True, "Health": {"Status": "healthy"}}}]))
        raise AssertionError(f"unexpected mutating service action: {command}")

    monkeypatch.setattr(maintenance, "_run", run)
    monkeypatch.setattr(maintenance, "snapshot", lambda: after)
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("synthetic unavailable TTS query")

    monkeypatch.setattr(maintenance, "_tts_settings", unavailable)
    monkeypatch.setattr(maintenance, "_tts_activity", unavailable)
    maintenance.restore(path)
    final = json.loads(path.read_text())
    assert final["phase"] == "restored"
    assert final["restoration_errors"] == []
    assert final["tts_readiness_observation"]["status"] == "unknown"
    assert final["tts_no_calls_condition"]["status"] == "unknown"
    assert set(final["recovery_checks"]) == set(maintenance.CONTAINERS)
    assert not any(call[0] == "systemctl" for call in calls)


def test_external_tts_identity_change_does_not_interrupt_mo_container_health_recovery(monkeypatch, tmp_path):
    initial = _snapshot()
    initial.update(tts_policy="keep_running", paused_containers=list(maintenance.CONTAINERS),
                   tts_activity_before={"active_job": False, "persistent_active_jobs": [], "job_count": 7})
    path = tmp_path / "maintenance.json"
    path.write_text(json.dumps(initial))
    after = copy.deepcopy(initial)
    after["systemd_units"][maintenance.SYSTEMD_UNITS[0]].update(MainPID="60", InvocationID="external-invocation")
    probe_round = 0
    calls = []

    def snapshot():
        nonlocal probe_round
        probe_round += 1
        return copy.deepcopy(after)

    def run(command, **kwargs):
        calls.append(command)
        assert command[0] != "systemctl", "an external TTS restart never authorizes a TTS action"
        if command[:2] == ["docker", "inspect"]:
            health = "healthy" if probe_round >= 2 else "starting"
            return _result(json.dumps([{"Id": command[-1] + "-id", "Image": "image-id", "State": {
                "Running": True, "Health": {"Status": health}}}]))
        raise AssertionError(command)

    monkeypatch.setattr(maintenance, "snapshot", snapshot)
    monkeypatch.setattr(maintenance, "_run", run)
    monkeypatch.setattr(maintenance, "_tts_settings", lambda: (1, tmp_path))
    monkeypatch.setattr(maintenance, "_http", lambda url: {"service": "qwen3-tts-openai", "inference_ready": True})
    monkeypatch.setattr(maintenance, "_tts_activity", lambda: {
        "active_job": False, "persistent_active_jobs": [], "job_count": 8})
    monkeypatch.setattr(maintenance.time, "sleep", lambda seconds: None)
    final = maintenance.restore(path)
    assert probe_round == 2, "MO containers must be allowed to reach healthy after the identity change"
    assert final["phase"] == "restored"
    assert final["restoration_errors"] == []
    assert all(final["recovery_checks"][name] for name in maintenance.CONTAINERS)
    condition = final["tts_identity_condition"]
    assert condition["status"] == "changed"
    assert condition["before"] == {"MainPID": "50", "InvocationID": "tts-invocation"}
    assert condition["after"] == {"MainPID": "60", "InvocationID": "external-invocation"}
    assert condition["changed_keys"] == ["InvocationID", "MainPID"]
    assert final["tts_no_calls_condition"]["status"] == "violated"
    assert not any(call[0] == "systemctl" for call in calls)


def test_observed_tts_identity_change_stays_changed_if_a_later_probe_matches_the_original():
    before = {"MainPID": "50", "InvocationID": "original"}
    changed = maintenance._tts_identity_condition(before, {"MainPID": "60", "InvocationID": "external"})
    later = maintenance._tts_identity_condition(before, before, changed)
    assert later["status"] == "changed"
    assert later["after"] == before
    assert later["first_changed_after"] == {"MainPID": "60", "InvocationID": "external"}


def test_no_call_condition_detects_a_completed_job_between_idle_probes():
    before = {"active_job": False, "persistent_active_jobs": [], "job_count": 7}
    after = {**before, "job_count": 8}
    assert maintenance._tts_call_condition(before, after)["status"] == "violated"
    assert maintenance._tts_call_condition(None, before)["status"] == "unknown"
    reduced = maintenance._tts_call_condition(before, {**before, "job_count": 6})
    assert reduced["status"] == "unknown"
    assert reduced["reason"] == "counter_retention_changed"
    assert reduced["observed_new_jobs"] is None


@pytest.mark.parametrize("unavailable", [False, True])
def test_tts_activity_or_query_failure_never_blocks_mo_drain(monkeypatch, unavailable):
    def http(url, **_kwargs):
        if url.endswith("/health"):
            return {"queue": {"active": 0}}
        if url.endswith("/ready"):
            return {"active_requests": 0}
        return 'vllm:num_requests_running{model="synthetic"} 0\nvllm:num_requests_waiting{model="synthetic"} 0\n'

    def activity():
        if unavailable:
            raise RuntimeError("synthetic TTS query unavailable")
        return {"active_job": True, "persistent_active_jobs": [["running", 2]], "job_count": 8}

    monkeypatch.setattr(maintenance, "_http", http)
    monkeypatch.setattr(maintenance, "_run", lambda *_args, **_kwargs: _result("[]"))
    monkeypatch.setattr(maintenance, "_tts_activity", activity)
    result = maintenance.drain_evidence()
    assert result["idle"] is True
    if unavailable:
        assert result["tts_activity"]["status"] == "unknown"
    else:
        assert result["tts_activity"]["active_job"] is True


def test_tts_unit_query_failure_is_unknown_observation(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("synthetic systemd query failed")

    monkeypatch.setattr(maintenance, "_unit_state", unavailable)
    observed = maintenance._observe_unit_state(maintenance.SYSTEMD_UNITS[0])
    assert observed["active"] is None and observed["observation_status"] == "unknown"


def _gpu_responses(monkeypatch, *, inaccessible_pid=None):
    identifiers = {"glm": "a" * 64, "mineru": "b" * 64}
    groups = {10: {"/docker/" + identifiers["glm"]}, 11: {"/docker/" + identifiers["glm"]},
        20: {"/docker/" + identifiers["mineru"]}, 21: {"/docker/" + identifiers["mineru"] + "/engine"},
        50: {"/system.slice/qwen3-tts-openai.service"}, 51: {"/system.slice/qwen3-tts-openai.service"}}
    calls = []

    def cgroups(pid):
        if pid == inaccessible_pid:
            raise PermissionError("synthetic inaccessible cgroup")
        return groups[pid]

    def run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "inspect"]:
            name = command[-1]
            return _result(json.dumps([{"Id": identifiers[name], "State": {
                "Running": True, "Pid": 10 if name == "glm" else 20}}]))
        if any(arg.startswith("--query-gpu=") for arg in command):
            return _result("GPU-one, 22528, 18000, 4000, 100, 50\n")
        if any(arg.startswith("--query-compute-apps=") for arg in command):
            return _result("GPU-one, 11, 6000\nGPU-one, 21, 7000\nGPU-one, 51, 4900\nGPU-other, 999, 20000\n")
        raise AssertionError(command)

    monkeypatch.setattr(maintenance, "_run", run)
    monkeypatch.setattr(maintenance, "_read_process_cgroups", cgroups)
    return calls


def test_gpu_ownership_includes_engine_children_excludes_tts_and_caches_inspection(monkeypatch):
    calls = _gpu_responses(monkeypatch)
    unit = {"active": True, "MainPID": "50", "ControlGroup": "/system.slice/qwen3-tts-openai.service"}
    cache = {}
    first = maintenance._gpu_observation(["glm", "mineru"], cache, unit)
    second = maintenance._gpu_observation(["glm", "mineru"], cache, unit)
    assert first["gpu1"]["used_memory_mib"] == 18000
    assert first["gpu1"]["free_memory_mib"] == 4000
    assert first["gpu1"]["free_memory_mib"] != first["gpu1"]["total_memory_mib"] - first["gpu1"]["used_memory_mib"]
    assert first["owned_gpu"]["used_memory_mib"] == 13000
    assert first["owned_gpu"]["memory_mib_by_container"] == {"glm": 6000, "mineru": 7000}
    assert first["tts_gpu"]["used_memory_mib"] == 4900
    assert second["owned_gpu"] == first["owned_gpu"]
    assert len([call for call in calls if call[:2] == ["docker", "inspect"]]) == 2
    assert {process["pid"] for process in first["gpu_processes"]} == {11, 21, 51}


def test_unattributable_gpu_process_stays_unknown_instead_of_zero(monkeypatch):
    _gpu_responses(monkeypatch, inaccessible_pid=21)
    sample = maintenance._gpu_observation(["glm", "mineru"], {}, {"active": True, "MainPID": "50"})
    assert sample["gpu1"]["used_memory_mib"] == 18000
    assert sample["owned_gpu"]["status"] == "unknown"
    assert sample["owned_gpu"]["used_memory_mib"] is None
    assert sample["owned_gpu"]["known_memory_lower_bound_mib"] == 6000
    assert sample["owned_gpu"]["memory_mib_by_container"] == {"glm": None, "mineru": None}


@pytest.mark.asyncio
async def test_sampled_budget_uses_owned_aggregate_and_keeps_whole_card_headroom(tmp_path):
    sampler = maintenance.ContainerSampler(["glm", "mineru"], tmp_path / "resources.json", gpu=True,
                                           gpu_budget_gib=16)
    sampler.samples = [{"expected_containers": ["glm", "mineru"], "containers": [
        {"Name": name, "MemUsage": "1GiB / 20GiB"} for name in ("glm", "mineru")],
        "gpu1": {"used_memory_mib": whole, "free_memory_mib": 22001 - whole},
        "owned_gpu": {"used_memory_mib": owned}, "tts_gpu": {"used_memory_mib": 4900},
    } for whole, owned in ((18000, 13000), (19000, 14000), (19500, None))]
    summary = await sampler.close()
    assert summary["observed_gpu1_peak_memory_mib"] == 19500
    assert summary["observed_owned_gpu_peak_memory_mib"] == 14000
    assert summary["observed_gpu1_min_free_memory_mib"] == 2501
    assert summary["tts_resident_baseline_memory_mib"] == 4900
    assert summary["gpu_budget_exceeded_in_observed_samples"] is False
    assert summary["sampling_completeness"]["owned_gpu_memory_samples"] == 2
    assert summary["sampling_completeness"]["status"] == "partial"


@pytest.mark.asyncio
async def test_known_owned_lower_bound_can_prove_budget_exceeded_despite_an_unknown_process(tmp_path):
    sampler = maintenance.ContainerSampler(["glm"], tmp_path / "resources.json", gpu=True,
                                           gpu_budget_gib=16)
    sampler.samples = [{"containers": [], "owned_gpu": {
        "used_memory_mib": None, "known_memory_lower_bound_mib": 17000}}]
    summary = await sampler.close()
    assert summary["observed_owned_gpu_peak_memory_mib"] is None
    assert summary["observed_owned_gpu_memory_lower_bound_peak_mib"] == 17000
    assert summary["gpu_budget_exceeded_in_observed_samples"] is True


@pytest.mark.asyncio
async def test_shared_service_gpu_shares_are_checked_against_the_declared_common_budget(tmp_path):
    config = {"pipeline": "P07", "resources": {"gpu_memory_gib": 16}, "inference_services": [
        {"cpus": 1, "memory_gib": 5, "gpu_memory_gib": 7},
        {"cpus": 3, "memory_gib": 15, "gpu_memory_gib": 10}]}
    with pytest.raises(ValueError, match="shared gpu_memory_gib"):
        async with maintenance.inference_services(config, tmp_path):
            pytest.fail("oversubscribed services must not start")
    assert not tmp_path.joinpath("inference-ownership.json").exists()
