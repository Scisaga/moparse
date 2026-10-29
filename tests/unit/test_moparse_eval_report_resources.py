"""Synthetic resource identities distinguish owned memory from resident TTS."""

from __future__ import annotations

import copy

import pytest

from moparse_eval.report_figures import _register_cjk_fonts, _resources
from moparse_eval.report_overview import render_overview
from moparse_eval.reporting import render_appendix


@pytest.fixture(scope="module", autouse=True)
def resource_fonts(tmp_path_factory):
    _register_cjk_fonts(tmp_path_factory.mktemp("synthetic-resource-fonts"))


def report_fixture():
    return {
        "execution": {"run_id": "synthetic-resource-run", "state": "completed",
                      "configurations": [{"pipeline": "P01", "resources": {"gpu_memory_gib": 16}}]},
        "maintenance": {"phase": "restored", "tts_policy": "keep_running",
            "tts_calls": "user_declared_none",
            "tts_identity_condition": {"status": "unchanged",
                "before": {"MainPID": "456", "InvocationID": "synthetic-tts-id"},
                "after": {"MainPID": "456", "InvocationID": "synthetic-tts-id"},
                "changed_keys": [], "scope": "synthetic measurement condition"},
            "tts_no_calls_condition": {"status": "no_observed_activity", "declaration": "user_declared_none",
                "before": {"active_job": False, "persistent_active_jobs": [], "job_count": 7},
                "after": {"active_job": False, "persistent_active_jobs": [], "job_count": 7},
                "observed_new_jobs": 0, "reason": "equal_start_end_counters",
                "limitation": "synthetic start/end observation only"}},
        "runtime_evidence": {"P01": {
            "inference_lifecycle_resources": {
                "path": "artifacts/P01/inference/resources.json",
                "record": {
                    "observed_owned_gpu_peak_memory_mib": 1024,
                    "owned_gpu_memory_scope": "simultaneous named-container aggregate",
                    "owned_gpu_budget_gib": 16,
                    "observed_gpu1_peak_memory_mib": 6144,
                    "tts_resident_baseline_memory_mib": 4096,
                    "observed_tts_gpu_peak_memory_mib": 4608,
                    "observed_gpu1_min_free_memory_mib": 20480,
                    "gpu_budget_exceeded_in_observed_samples": False,
                    "sampling_completeness": {
                        "samples": 3, "owned_gpu_memory_samples": 1,
                        "gpu_memory_samples": 3, "tts_gpu_memory_samples": 1, "status": "partial"},
                    "samples": [{
                        "owned_gpu": {"identities": {"synthetic-glm": {
                            "container_id": "synthetic-container-id", "host_pid": 123,
                            "cgroups": ["/synthetic/container"]}}},
                        "tts_gpu": {"unit_identity": {"MainPID": "456",
                            "ControlGroup": "/synthetic/tts", "InvocationID": "synthetic-tts-id"}},
                    }],
                },
            },
            "worker_lifecycle_resources": None,
        }},
    }


@pytest.mark.parametrize("owned", [None, "missing", float("nan")])
def test_main_resource_chart_never_substitutes_whole_card_when_owned_is_unknown(owned):
    import matplotlib.pyplot as plt

    report = report_fixture()
    record = report["runtime_evidence"]["P01"]["inference_lifecycle_resources"]["record"]
    if owned == "missing":
        record.pop("observed_owned_gpu_peak_memory_mib")
    else:
        record["observed_owned_gpu_peak_memory_mib"] = owned
    before = copy.deepcopy(report)
    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"]}):
        figure, data = _resources(report, plt, ["P01"])
    try:
        assert data["owned_gpu_memory"][0]["gib"] is None
        assert not figure.axes[2].patches
        assert any(text.get_text() == "NA" for text in figure.axes[2].texts)
        assert "自有显存" in figure.axes[2].get_title(loc="left")
        assert data["owned_gpu_memory"][0]["field"] == "observed_owned_gpu_peak_memory_mib"
    finally:
        plt.close(figure)
    assert report == before


def test_appendix_separates_owned_tts_whole_card_headroom_and_identity():
    report = report_fixture()
    before = copy.deepcopy(report)
    text = render_appendix(report)
    assert "受测管线自有显存采样峰值（MiB）" in text
    owned_row = next(line for line in text.splitlines() if line.startswith("| P01 | 1024.0000"))
    assert "6144" not in owned_row and "4096" not in owned_row
    assert "| P01 | 16.0000 | 6144.0000 | 4096.0000 | 4608.0000 | 20480.0000 | False |" in text
    assert "synthetic-container-id" in text and "host_pid=123" in text
    assert "MainPID=456" in text and "synthetic-tts-id" in text
    assert "1 / 3 / 1 | 3 | partial" in text
    assert "[记录](artifacts/P01/inference/resources.json)" in text
    assert "不通过减去TTS峰值推算" in text
    assert "仍可能漏掉更短峰值" in text
    assert "TTS策略：keep_running；TTS调用条件：user_declared_none" in text
    assert "| restored | keep_running | user_declared_none | unchanged | no_observed_activity |" in text
    assert "| MainPID | 456 | 456 | NA |" in text
    assert "身份变化字段：[]" in text
    assert "synthetic start/end observation only" in text
    assert report == before


def test_appendix_legacy_whole_card_value_is_only_environment_evidence():
    report = report_fixture()
    report["runtime_evidence"]["P01"]["inference_lifecycle_resources"]["record"] = {
        "observed_gpu1_peak_memory_mib": 6144}
    text = render_appendix(report)
    assert "| P01 | NA | NA | NA |" in text
    assert "| P01 | NA | 6144.0000 | NA | NA | NA | NA |" in text
    assert "不回退到整卡字段" in text


def test_overview_records_tts_residency_declared_no_calls_and_owned_budget():
    report = report_fixture()
    before = copy.deepcopy(report)
    text = render_overview(report)
    assert "共享 16 GiB 自有显存（owned）预算" in text
    assert "TTS 策略 `keep_running`，调用条件 `user_declared_none`" in text
    assert "身份观测 `unchanged`，无调用观测 `no_observed_activity`" in text
    assert "并非调用监控结论" in text
    assert "6144" not in text and "20480" not in text
    assert report == before
    legacy = render_overview({})
    assert "共享 NA GiB" in legacy
    assert "TTS 策略 `NA`，调用条件 `NA`" in legacy
    assert "身份观测 `NA`，无调用观测 `NA`" in legacy
    assert "NA或unknown不表示条件满足" in legacy


@pytest.mark.parametrize("identity_status,calls_status", [
    ("changed", "violated"), ("changed", "no_observed_activity"),
    ("unchanged", "violated"), ("unknown", "unknown"),
])
def test_observed_tts_conditions_remain_independent_of_a_healthy_restoration(identity_status, calls_status):
    report = report_fixture()
    maintenance = report["maintenance"]
    identity = maintenance["tts_identity_condition"]
    identity["status"] = identity_status
    if identity_status == "changed":
        identity.update(after={"MainPID": "789", "InvocationID": "synthetic-new-tts"},
            first_changed_after={"MainPID": "789", "InvocationID": "synthetic-new-tts"},
            changed_keys=["MainPID", "InvocationID"])
    calls = maintenance["tts_no_calls_condition"]
    calls["status"] = calls_status
    if calls_status == "violated":
        calls.update(after={"active_job": False, "persistent_active_jobs": [], "job_count": 8},
                     observed_new_jobs=1, reason="active_or_new_jobs")
    before = copy.deepcopy(report)
    overview = render_overview(report)
    appendix = render_appendix(report)
    assert f"身份观测 `{identity_status}`，无调用观测 `{calls_status}`" in overview
    assert f"| restored | keep_running | user_declared_none | {identity_status} | {calls_status} |" in appendix
    assert "`user_declared_none`只是用户声明" in overview
    assert "不能证明全程无调用" in overview
    assert "unknown或NA不能解释为条件满足" in appendix
    assert "恢复为restored、服务健康不能使已违反的性能测量条件重新有效" in appendix
    if identity_status == "changed":
        assert "| MainPID | 456 | 789 | 789 |" in appendix
        assert "| InvocationID | synthetic-tts-id | synthetic-new-tts | synthetic-new-tts |" in appendix
        assert "身份变化字段：MainPID, InvocationID" in appendix
        assert "MainPID" not in overview and "synthetic-new-tts" not in overview
    if calls_status == "violated":
        assert "| job_count | 7 | 8 |" in appendix
        assert "已观测新任务计数差：1" in appendix
    if identity_status == "changed" or calls_status == "violated":
        assert "本轮性能测量不能作为既定共驻条件下的正式比较" in overview
    else:
        assert "TTS实际观测条件已被违反" not in overview
    assert report == before


@pytest.mark.parametrize("record", [None, {}, {"status": ""}, {"status": None}, "malformed"])
def test_absent_or_malformed_tts_observation_never_inherits_the_no_call_declaration(record):
    report = report_fixture()
    report["maintenance"].update(tts_identity_condition=record, tts_no_calls_condition=record)
    overview = render_overview(report)
    appendix = render_appendix(report)
    assert "调用条件 `user_declared_none`" in overview
    assert "身份观测 `NA`，无调用观测 `NA`" in overview
    assert "| restored | keep_running | user_declared_none | NA | NA |" in appendix
    assert "| MainPID | NA | NA | NA |" in appendix
    assert "| job_count | NA | NA |" in appendix
    assert "已观测新任务计数差：NA" in appendix
    assert "no_observed_activity" not in overview and "unchanged" not in overview


def test_sticky_changed_status_is_not_recomputed_from_equal_start_end_identities():
    report = report_fixture()
    report["maintenance"]["tts_identity_condition"].update(status="changed",
        changed_keys=["MainPID", "InvocationID"],
        first_changed_after={"MainPID": "789", "InvocationID": "synthetic-new-tts"})
    overview, appendix = render_overview(report), render_appendix(report)
    assert "身份观测 `changed`" in overview
    assert "本轮性能测量不能作为既定共驻条件下的正式比较" in overview
    assert "| MainPID | 456 | 456 | 789 |" in appendix
    assert "即使后续回到原身份也仍保留changed" in appendix


@pytest.mark.parametrize("identity_status,calls_status", [
    ("changed", "observed_activity"), ("changed", "no_observed_activity"),
    ("unchanged", "observed_activity"), ("unknown", "unknown"), (None, None),
])
def test_observe_only_reports_actual_co_residency_without_invalidating_tts_observations(identity_status, calls_status):
    report = report_fixture()
    maintenance = report["maintenance"]
    maintenance.update(tts_observation_policy="observe_only", tts_calls="not_controlled")
    if identity_status is None:
        maintenance.pop("tts_identity_condition")
        maintenance.pop("tts_no_calls_condition")
    else:
        maintenance["tts_identity_condition"]["status"] = identity_status
        maintenance["tts_no_calls_condition"]["status"] = calls_status
    before = copy.deepcopy(report)
    overview, appendix = render_overview(report), render_appendix(report)
    assert "共享 16 GiB 自有显存（owned）预算" in overview
    assert "`observe_only`策略下TTS保持运行，评测不控制其活动，性能反映实际共驻条件" in overview
    assert f"身份观测 `{identity_status or 'NA'}`，活动观测 `{calls_status or 'NA'}`" in overview
    assert "不代表GPU独占或确定无调用" in overview
    assert "本轮性能测量不能作为既定共驻条件下的正式比较" not in overview
    assert "TTS实际观测条件已被违反" not in overview
    assert "TTS观测政策：observe_only" in appendix
    assert f"| restored | keep_running | not_controlled | {identity_status or 'NA'} | {calls_status or 'NA'} |" in appendix
    assert "身份变化、已观测调用和unknown只作披露，不自动判性能无效或阻止报告" in appendix
    assert "已违反的性能测量条件重新有效" not in appendix
    if identity_status == "changed" or calls_status == "observed_activity":
        assert "可能干扰本轮耗时和资源读数" in overview
    assert report == before


def test_observe_only_cost_tables_do_not_generate_an_exclusive_speed_ranking():
    report = report_fixture()
    report["maintenance"]["tts_observation_policy"] = "observe_only"
    report["groups"] = [{
        "pipeline": name, "dataset": "synthetic-lite", "suite": "quality800",
        "quality": {"status": "evaluated", "input_pages": 1, "samples": 1,
                    "documents": 1, "families": 1, "failed_samples": 0, "unscored_samples": 0},
        "performance": {"round_duration_summary": {"n": 1, "median_seconds": seconds},
            "rounds": [{"attempted_input_pages": 1, "completed_input_pages": 1,
                        "all_samples_completed": True, "timing_complete": True}]},
    } for name, seconds in (("P01", 60), ("P02", 120))]
    observe_only = render_overview(report)
    assert "| P01 | 1 / 1 | 1.00 / 1 |" in observe_only
    assert "| P02 | 1 / 1 | 2.00 / 1 |" in observe_only
    assert "处理时间最短" not in observe_only
    report["maintenance"]["tts_observation_policy"] = "strict"
    assert "P01 的正式集处理时间最短" in render_overview(report)
