"""Keep the maintained MinerU deployment on its verified CUDA Graph policy."""

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def services() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]


def argument(command: list[str], flag: str) -> str:
    values = []
    for index, item in enumerate(command):
        if item == flag:
            assert index + 1 < len(command), f"{flag} must have an explicit value"
            values.append(command[index + 1])
        elif item.startswith(f"{flag}="):
            values.append(item.partition("=")[2])
    assert len(values) == 1, f"{flag} must be explicit and unambiguous"
    return values[0]


def test_mineru_decode_graphs_are_explicit_without_enabling_inductor(services: dict) -> None:
    command = services["mineru-vllm"]["command"]
    assert not any(item.partition("=")[0] == "--enforce-eager" for item in command)
    config = json.loads(argument(command, "--compilation-config"))
    assert config["mode"] == 0
    assert config["cudagraph_mode"] == "FULL_DECODE_ONLY"
    concurrency = int(argument(command, "--max-num-seqs"))
    assert set(config["cudagraph_capture_sizes"]) == set(range(1, concurrency + 1))
    assert config["max_cudagraph_capture_size"] == concurrency


def test_graph_capture_covers_admitted_vlm_requests_with_the_reviewed_budget(
    services: dict,
) -> None:
    command = services["mineru-vllm"]["command"]
    native = services["mineru-native"]
    concurrency = int(native["environment"]["MINERU_VLM_CONCURRENCY"])
    assert 1 <= concurrency <= 4
    assert int(argument(command, "--max-num-seqs")) == concurrency
    assert int(argument(command, "--kv-cache-memory-bytes")) == 134_217_728
    assert int(argument(command, "--max-num-batched-tokens")) == 2048
    assert int(argument(command, "--max-model-len")) == 8192


def test_native_worker_retains_the_accepted_cpu_budget(services: dict) -> None:
    assert float(services["mineru-native"]["cpus"]) == 8
