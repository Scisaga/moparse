"""Production GLM configuration guards, without starting a model or service."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_glm_uses_native_rotary_without_disabling_graphs_or_other_custom_ops() -> None:
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
    command = services["glm-ocr"]["command"]
    compilation = json.loads(command[command.index("--compilation-config") + 1])

    assert compilation == {"custom_ops": ["all", "-rotary_embedding"]}
    assert "--enforce-eager" not in command
    assert "--disable-custom-all-reduce" not in command
    assert command[command.index("--dtype") + 1] == "${GLM_DTYPE:-half}"
    assert "-rotary_embedding" not in " ".join(services["mineru-vllm"]["command"])
