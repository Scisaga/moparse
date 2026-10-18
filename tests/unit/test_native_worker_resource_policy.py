"""Exercise the exact pinned MFR code with a fake session, never model inference."""

from __future__ import annotations

import ast
import hashlib
import math
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from native_worker import patch_dependency as dependency

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/mineru-4.0.12-pp-formulanet-plus-m-onnx.py.txt"


@pytest.fixture(scope="module")
def patched_source(tmp_path_factory):
    """Apply the production patch to an exact original upstream source copy."""
    original = FIXTURE.read_bytes()
    assert hashlib.sha256(original).hexdigest() == dependency.MFR_ORIGINAL_SHA256
    root = tmp_path_factory.mktemp("mfr-patch")
    target = root / "mineru/model/mfr/pp_formulanet_plus_m_onnx.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(original)
    subprocess.run(
        [
            "patch",
            "--batch",
            "--fuzz=0",
            "-p1",
            "-d",
            str(root),
            "-i",
            str(ROOT / "native_worker/patches/mineru-4.0.12-mfr-cpu-batch.patch"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert hashlib.sha256(target.read_bytes()).hexdigest() == dependency.MFR_PATCHED_SHA256
    return target


class Progress:
    def __init__(self, **_kwargs):
        self.count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def update(self, count):
        self.count += count


def load_patched_code(path):
    """Keep actual functions/loop; omit optional SDK imports and model loading."""
    tree = ast.parse(path.read_text())
    tree.body = [
        node
        for node in tree.body
        if not isinstance(node, (ast.Import, ast.ImportFrom))
        or isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
    ]
    namespace = {"os": os, "math": math, "np": np, "tqdm": Progress}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("value", [None, *map(str, range(1, 9))])
def test_pinned_dependency_and_startup_validator_read_the_same_batch_cap(
    patched_source, monkeypatch, value
):
    if value is None:
        monkeypatch.delenv(dependency.MFR_BATCH_ENV, raising=False)
    else:
        monkeypatch.setenv(dependency.MFR_BATCH_ENV, value)
    code = load_patched_code(patched_source)
    expected = 8 if value is None else int(value)
    assert code["_cpu_batch_limit"]() == dependency.cpu_mfr_batch_size() == expected


@pytest.mark.parametrize("value", ["", "0", "-1", "9", "1.5", "unknown"])
def test_invalid_caps_fail_explicitly_instead_of_silently_changing_resources(
    patched_source, monkeypatch, value
):
    monkeypatch.setenv(dependency.MFR_BATCH_ENV, value)
    code = load_patched_code(patched_source)
    with pytest.raises(ValueError, match="integer from 1 to 8"):
        code["_cpu_batch_limit"]()
    with pytest.raises(ValueError, match="integer from 1 to 8"):
        dependency.cpu_mfr_batch_size()


def formula_inputs():
    images, formulas = [], []
    for page in range(2):
        image = np.zeros((60, 120, 3), dtype=np.uint8)
        items = []
        for index in range(13):
            value = page * 13 + index + 1
            x, y = (index % 6) * 20, (index // 6) * 20
            width, height = 2 + value % 11, 2 + value % 13
            image[y : y + height, x : x + width] = value
            items.append(
                {
                    "label": "inline_formula",
                    "bbox": [x, y, x + width, y + height],
                    "original_id": value,
                }
            )
        images.append(image)
        formulas.append(items)
    return formulas, images


@pytest.mark.parametrize(
    "cap,requested,expected_batches",
    [
        (None, 32, [8, 8, 8, 2]),
        ("1", 32, [1] * 26),
        ("2", 32, [2] * 13),
        ("3", 32, [3] * 8 + [2]),
        ("8", 2, [2] * 13),
    ],
)
def test_all_26_formulas_cross_microbatches_once_and_return_in_original_page_order(
    patched_source, monkeypatch, cap, requested, expected_batches
):
    if cap is None:
        monkeypatch.delenv(dependency.MFR_BATCH_ENV, raising=False)
    else:
        monkeypatch.setenv(dependency.MFR_BATCH_ENV, cap)
    code = load_patched_code(patched_source)
    model = object.__new__(code["PPFormulaNetPlusMONNX"])
    batches, observed_ids = [], []

    def run(_outputs, feed):
        inputs = feed["images"]
        batches.append(len(inputs))
        observed_ids.extend(int(value[0]) for value in inputs)
        return [inputs.astype(np.int64)]

    model.session = SimpleNamespace(run=run)
    model.input_name = "images"
    # Real sorting, target mapping, microbatch loop and return path are used.
    # Only image preprocessing and model inference are replaced with identities.
    model._preprocess = lambda crop: np.asarray([[crop[0, 0, 0]]], dtype=np.float32)
    model._decode_tokens = lambda tokens: str(int(tokens[0]))
    original, images = formula_inputs()
    result = model.batch_predict(original, images, batch_size=requested)

    assert batches == expected_batches
    assert sorted(observed_ids) == list(range(1, 27))
    assert observed_ids != list(range(1, 27))  # area ordering was actually exercised
    assert [[item["original_id"] for item in page] for page in result] == [
        list(range(1, 14)),
        list(range(14, 27)),
    ]
    assert [item["latex"] for page in result for item in page] == [str(i) for i in range(1, 27)]
    assert all("latex" not in item for page in original for item in page)
    assert model.batch_predict([], [], batch_size=requested) == []


def test_startup_rejects_drift_and_reports_all_three_effective_resource_settings(
    patched_source, monkeypatch, tmp_path
):
    monkeypatch.setattr(dependency.importlib.metadata, "version", lambda _name: "4.0.12")
    monkeypatch.setattr(dependency, "mfr_source_path", lambda: patched_source)
    monkeypatch.setenv(dependency.MFR_BATCH_ENV, "1")
    monkeypatch.setenv("MINERU_PROCESSING_WINDOW_SIZE", "8")
    monkeypatch.setenv("MINERU_MALLOC_TRIM", "1")
    assert dependency.verify_resource_patch() == {
        "name": "cpu-mfr-microbatch-limit-v1",
        "source_sha256": dependency.MFR_PATCHED_SHA256,
        "cpu_mfr_batch_size": 1,
        "processing_window_size": 8,
        "malloc_trim": True,
    }
    changed = tmp_path / "changed.py"
    changed.write_bytes(patched_source.read_bytes() + b"\n")
    monkeypatch.setattr(dependency, "mfr_source_path", lambda: changed)
    with pytest.raises(RuntimeError, match="unpatched or changed"):
        dependency.verify_resource_patch()


def test_docker_defaults_are_explicit_and_the_reviewed_source_axis_hash_is_unchanged():
    dockerfile = (ROOT / "Dockerfile.native-worker").read_text()
    assert "MOPARSE_CPU_MFR_BATCH_SIZE=1" in dockerfile
    assert "MINERU_PROCESSING_WINDOW_SIZE=8" in dockerfile
    assert "MINERU_MALLOC_TRIM=1" in dockerfile
    assert dependency.PATCHED_SHA256 == (
        "616f44e2a1749f4b82074df36c3da852694a9401828c6c36aad62553b2a182cf"
    )


def patcher_tree(tmp_path, monkeypatch):
    axis = tmp_path / "mineru/backend/analysis/pdf/text/native.py"
    axis.parent.mkdir(parents=True)
    axis.write_bytes(b"already patched axis test sentinel")
    mfr = tmp_path / "mineru/model/mfr/pp_formulanet_plus_m_onnx.py"
    mfr.parent.mkdir(parents=True)
    mfr.write_bytes(FIXTURE.read_bytes())
    monkeypatch.setattr(dependency, "source_path", lambda: axis)
    monkeypatch.setattr(dependency, "mfr_source_path", lambda: mfr)
    monkeypatch.setattr(dependency, "PATCHED_SHA256", hashlib.sha256(axis.read_bytes()).hexdigest())
    monkeypatch.setattr(dependency.importlib.metadata, "version", lambda _name: "4.0.12")
    monkeypatch.setenv(dependency.MFR_BATCH_ENV, "1")
    return axis, mfr


def test_image_patcher_accepts_existing_axis_fix_and_is_idempotent(tmp_path, monkeypatch):
    axis, mfr = patcher_tree(tmp_path, monkeypatch)
    original_axis = axis.read_bytes()
    dependency.main()
    assert hashlib.sha256(mfr.read_bytes()).hexdigest() == dependency.MFR_PATCHED_SHA256
    first = mfr.read_bytes()
    dependency.main()
    assert axis.read_bytes() == original_axis
    assert mfr.read_bytes() == first


@pytest.mark.parametrize("problem", ["source_drift", "invalid_batch"])
def test_image_patcher_preflights_every_source_and_config_before_writing(
    tmp_path, monkeypatch, problem
):
    axis, mfr = patcher_tree(tmp_path, monkeypatch)
    if problem == "source_drift":
        mfr.write_bytes(mfr.read_bytes() + b"\n")
    else:
        monkeypatch.setenv(dependency.MFR_BATCH_ENV, "0")
    original = axis.read_bytes(), mfr.read_bytes()
    with pytest.raises((ValueError, RuntimeError)):
        dependency.main()
    assert (axis.read_bytes(), mfr.read_bytes()) == original


@pytest.mark.parametrize("window,expected", [(None, 64), ("invalid", 64), ("-1", 1)])
def test_resource_status_retains_official_unset_and_window_fallback_semantics(
    patched_source, monkeypatch, window, expected
):
    monkeypatch.setattr(dependency.importlib.metadata, "version", lambda _name: "4.0.12")
    monkeypatch.setattr(dependency, "mfr_source_path", lambda: patched_source)
    for key in (dependency.MFR_BATCH_ENV, "MINERU_PROCESSING_WINDOW_SIZE", "MINERU_MALLOC_TRIM"):
        monkeypatch.delenv(key, raising=False)
    if window is not None:
        monkeypatch.setenv("MINERU_PROCESSING_WINDOW_SIZE", window)
    status = dependency.verify_resource_patch()
    assert status["cpu_mfr_batch_size"] == 8
    assert status["processing_window_size"] == expected
    assert status["malloc_trim"] is False
