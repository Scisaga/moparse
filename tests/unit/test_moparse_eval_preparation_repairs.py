"""Prepared configurations use invented image identities and absent model roots."""

import pytest

from moparse_eval.preparation import write_execution_lock
from moparse_eval.runtime import PreparationError, validate_execution_config


def test_runtime_enforces_current_gpu_budget():
    validate_execution_config({"pipeline": "P01", "resources": {"gpu_memory_gib": 16}})
    with pytest.raises(PreparationError, match="gpu_memory_gib"):
        validate_execution_config({"pipeline": "P01", "resources": {"gpu_memory_gib": 20}})


def test_new_preparation_keeps_tts_and_shares_sixteen_gib(tmp_path, monkeypatch):
    monkeypatch.setattr("moparse_eval.preparation.subprocess.check_output", lambda *a, **k: "sha256:invented\n")
    lock = write_execution_lock(tmp_path / "prepared.json", tmp_path, tmp_path / "models")
    assert lock["frozen"] is False
    for config in lock["pipelines"].values():
        assert config["resources"]["gpu_memory_gib"] == 16
        assert sum(service["gpu_memory_gib"] for service in config["inference_services"]) == 16
        assert config["co_resident_services"]["qwen3-tts-openai.service"] == {
            "policy": "keep_running", "observation_policy": "observe_only",
            "inference_during_benchmark": "uncontrolled_observed_only",
            "instruction_date": "2026-10-26"}
        assert config["retry_max_attempts"] == 0 and config["observe_request_metadata"]
        assert "glm_request_observation" not in config
        for service in config["inference_services"]:
            if service["family"] == "glm":
                assert service["rotary_embedding"] == "native"
    for pipeline in ("P03", "P04"):
        config = lock["pipelines"][pipeline]
        native = config["inference_services"][0]["server_config"]
        assert native["resources"]["gpu_memory_gib"] == 16
        assert native["paddle_color_policy"] == "bgr-to-rgb-v1"
        assert native["paddle_max_new_tokens"] == 4096
        assert native["paddle_generation_observation"] is True
        assert native["paddle_use_queues"] is False
        assert native["paddle_execution_mode"] == "persistent-owner-v1"
