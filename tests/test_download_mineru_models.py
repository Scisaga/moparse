"""The model preparer is verified without Hub access, weights, or inference."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download_mineru_models.py"
SPEC = importlib.util.spec_from_file_location("download_mineru_models", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
preparer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparer)
REVISION = "a" * 40
PAYLOAD = b"locked fixture bytes\n"


def fixture_lock(tmp_path: Path) -> tuple[Path, dict, Path, Path]:
    lock = {
        "schema": preparer.SCHEMA,
        "models": [
            {
                "id": "vlm",
                "repo_id": "example/fixture",
                "revision": REVISION,
                "target": {"root": "vlm_dir", "path": f"snapshots/{REVISION}"},
                "files": [
                    {
                        "path": "model.bin",
                        "bytes": len(PAYLOAD),
                        "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
                    }
                ],
            }
        ],
    }
    lock_path = tmp_path / "models.lock.json"
    lock_path.write_text(json.dumps(lock))
    vlm = tmp_path / "vlm"
    destination = vlm / "snapshots" / REVISION / "model.bin"
    return lock_path, lock, vlm, destination


def test_verify_only_and_help_work_without_site_packages(tmp_path: Path) -> None:
    lock_path, _, vlm, destination = fixture_lock(tmp_path)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(PAYLOAD)
    command = [sys.executable, "-S", str(SCRIPT)]
    help_result = subprocess.run([*command, "--help"], capture_output=True, text=True)
    assert help_result.returncode == 0
    result = subprocess.run(
        [*command, "--verify-only", "--lock-file", str(lock_path), "--vlm-dir", str(vlm)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["offline_verification"] is True
    assert not (tmp_path / "mineru-native").exists()


@pytest.mark.parametrize(
    "state", ["missing", "truncated", "wrong_hash", "symlink", "dangling_symlink"]
)
def test_verification_rejects_missing_corrupt_and_linked_artifacts(
    tmp_path: Path, state: str
) -> None:
    _, lock, vlm, destination = fixture_lock(tmp_path)
    destination.parent.mkdir(parents=True)
    if state == "truncated":
        destination.write_bytes(b"short")
    elif state == "wrong_hash":
        destination.write_bytes(b"x" * len(PAYLOAD))
    elif state in {"symlink", "dangling_symlink"}:
        cache_file = tmp_path / "cache.bin"
        if state == "symlink":
            cache_file.write_bytes(PAYLOAD)
        destination.symlink_to(cache_file)
    with pytest.raises(preparer.ModelPreparationError, match="Model verification failed"):
        preparer.prepare_models(lock, vlm, tmp_path / "native", verify_only=True)


def test_download_uses_exact_revision_and_materializes_cache_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, lock, vlm, destination = fixture_lock(tmp_path)
    source = tmp_path / "read-only-cache.bin"
    source.write_bytes(PAYLOAD)
    source.chmod(0o444)
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        staged = Path(kwargs["local_dir"]) / kwargs["filename"]
        staged.symlink_to(source)
        return str(staged)

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", types.SimpleNamespace(hf_hub_download=fake_download)
    )
    result = preparer.prepare_models(lock, vlm, tmp_path / "native", verify_only=False)
    assert calls[0]["repo_id"] == "example/fixture"
    assert calls[0]["revision"] == REVISION
    assert destination.read_bytes() == PAYLOAD
    assert not destination.is_symlink()
    assert source.read_bytes() == PAYLOAD
    assert source.stat().st_mode & 0o777 == 0o444
    assert result["models"][0]["downloaded_files"] == 1
    assert not list(destination.parent.parent.glob(".mineru-download-*"))
    # A verified local installation skips Hub calls on subsequent preparation.
    assert (
        preparer.prepare_models(lock, vlm, tmp_path / "native", verify_only=False)["status"]
        == "verified"
    )
    assert len(calls) == 1


def test_corrupt_download_does_not_replace_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, lock, vlm, destination = fixture_lock(tmp_path)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"previous contents")

    def fake_download(**kwargs):
        staged = Path(kwargs["local_dir"]) / kwargs["filename"]
        staged.write_bytes(b"corrupt download")
        return str(staged)

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", types.SimpleNamespace(hf_hub_download=fake_download)
    )
    with pytest.raises(preparer.ModelPreparationError, match="do not match lock"):
        preparer.prepare_models(lock, vlm, tmp_path / "native", verify_only=False)
    assert destination.read_bytes() == b"previous contents"


@pytest.mark.parametrize(
    "invalid", ["../escape.bin", "/absolute.bin", "a/../../escape.bin", "a\\escape.bin"]
)
def test_lock_rejects_paths_outside_installation(tmp_path: Path, invalid: str) -> None:
    lock_path, lock, _, _ = fixture_lock(tmp_path)
    lock["models"][0]["files"][0]["path"] = invalid
    lock_path.write_text(json.dumps(lock))
    with pytest.raises(preparer.ModelPreparationError):
        preparer.load_lock(lock_path)


def test_lock_requires_immutable_revision(tmp_path: Path) -> None:
    lock_path, lock, _, _ = fixture_lock(tmp_path)
    lock["models"][0]["revision"] = "main"
    lock_path.write_text(json.dumps(lock))
    with pytest.raises(preparer.ModelPreparationError, match="immutable commit"):
        preparer.load_lock(lock_path)


def test_committed_model_lock_is_valid() -> None:
    lock = preparer.load_lock(preparer.DEFAULT_LOCK)
    assert lock["schema"] == "moparse-mineru-model-lock/1"
    assert len(lock["models"]) == 2
    assert sum(len(model["files"]) for model in lock["models"]) == 25
