"""Synthetic command construction; never starts Docker or accesses documents."""

import json
from pathlib import Path

import pytest

from moparse_eval.maintenance import inference_command


def command(**overrides):
    return inference_command({"family": "glm", "inference_image": "synthetic-image", **overrides},
        model_path=Path("/synthetic-model"), model_name="synthetic", port=12541,
        name="moparse-eval-synthetic")


def test_native_rotary_changes_only_custom_op_preserving_graphs_and_budget():
    baseline, fixed = command(), command(rotary_embedding="native")
    index = baseline.index("--compilation-config") + 1
    before, after = json.loads(baseline[index]), json.loads(fixed[index])
    assert "custom_ops" not in before
    assert after.pop("custom_ops") == ["all", "-rotary_embedding"]
    assert before == after
    assert after["mode"] == 0 and after["cudagraph_mode"] == "FULL_DECODE_ONLY"
    fixed[index] = baseline[index]
    assert fixed == baseline


@pytest.mark.parametrize("overrides", [
    {"rotary_embedding": "cuda"},
    {"family": "mineru", "rotary_embedding": "native"},
])
def test_rotary_experiment_cannot_silently_change_another_family(overrides):
    with pytest.raises(ValueError, match="explicit GLM native"):
        command(**overrides)
