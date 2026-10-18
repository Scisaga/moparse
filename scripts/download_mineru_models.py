#!/usr/bin/env python3
"""Prepare the locked MinerU model files for an offline native worker.

The VLM is installed as ordinary files below ``--vlm-dir/snapshots/<revision>``.
The ONNX models are installed below ``--native-home/models/MinerU-4_models_onnx``.
``--verify-only`` uses only the Python standard library and never contacts the Hub.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "moparse-mineru-model-lock/1"
DEFAULT_LOCK = Path(__file__).resolve().parent.parent / "native_worker" / "models.lock.json"


class ModelPreparationError(Exception):
    """A locked artifact cannot be prepared or verified."""


def relative_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ModelPreparationError(f"{label} must be a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {".", ".."} for part in value.split("/")):
        raise ModelPreparationError(f"{label} must stay inside its model directory")
    return Path(*path.parts)


def load_lock(path: Path) -> dict[str, Any]:
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelPreparationError(f"Cannot read model lock {path}: {exc}") from exc
    if not isinstance(lock, dict) or lock.get("schema") != SCHEMA:
        raise ModelPreparationError(f"Model lock must use schema {SCHEMA}")
    models = lock.get("models")
    if not isinstance(models, list) or not models:
        raise ModelPreparationError("Model lock has no models")
    ids: set[str] = set()
    destinations: set[tuple[str, str]] = set()
    for model in models:
        if not isinstance(model, dict):
            raise ModelPreparationError("Each locked model must be an object")
        model_id = model.get("id")
        if not isinstance(model_id, str) or not model_id or model_id in ids:
            raise ModelPreparationError("Locked model identifiers must be unique strings")
        ids.add(model_id)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(model.get("repo_id", ""))):
            raise ModelPreparationError(f"Invalid repository identifier for {model_id}")
        if not re.fullmatch(r"[a-f0-9]{40}", str(model.get("revision", ""))):
            raise ModelPreparationError(f"{model_id} requires a full immutable commit revision")
        target = model.get("target")
        if not isinstance(target, dict) or target.get("root") not in {"vlm_dir", "native_home"}:
            raise ModelPreparationError(f"Invalid installation root for {model_id}")
        target_path = relative_path(target.get("path"), f"{model_id} target")
        files = model.get("files")
        if not isinstance(files, list) or not files:
            raise ModelPreparationError(f"{model_id} has no locked files")
        for artifact in files:
            if not isinstance(artifact, dict):
                raise ModelPreparationError(f"Invalid file entry for {model_id}")
            artifact_path = relative_path(artifact.get("path"), f"{model_id} file")
            if not re.fullmatch(r"[a-f0-9]{64}", str(artifact.get("sha256", ""))):
                raise ModelPreparationError(f"Invalid SHA-256 for {model_id}/{artifact_path}")
            size = artifact.get("bytes")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ModelPreparationError(f"Invalid byte count for {model_id}/{artifact_path}")
            destination = (target["root"], (target_path / artifact_path).as_posix())
            if destination in destinations:
                raise ModelPreparationError(f"Duplicate locked destination: {destination[1]}")
            destinations.add(destination)
    return lock


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_error(path: Path, artifact: dict[str, Any]) -> str | None:
    if path.is_symlink():
        return "symlink (offline deployment requires an ordinary file)"
    if not path.is_file():
        return "missing or not an ordinary file"
    try:
        if path.stat().st_size != artifact["bytes"]:
            return "byte count differs from model lock"
        if sha256(path) != artifact["sha256"]:
            return "SHA-256 differs from model lock"
    except OSError as exc:
        return str(exc)
    return None


def install_regular_file(
    source: Path, destination: Path, *, owned_source_root: Path | None = None
) -> None:
    """Copy bytes atomically; never leave a link to a Hub cache in the volume."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".mineru-", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        if (
            owned_source_root is not None
            and not source.is_symlink()
            and source.resolve().is_relative_to(owned_source_root.resolve())
        ):
            source.replace(temporary)
        else:
            shutil.copyfile(source, temporary)
        temporary.chmod(0o644)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def download_artifact(
    model: dict[str, Any], artifact: dict[str, Any], destination: Path, staging: Path
) -> None:
    # Import only on the download path: --help and --verify-only need no Hub package.
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise ModelPreparationError(
            "huggingface_hub is required to download models; install the worker dependencies first"
        ) from exc
    try:
        downloaded = Path(
            hf_hub_download(
                repo_id=model["repo_id"],
                filename=artifact["path"],
                revision=model["revision"],
                local_dir=staging,
                force_download=True,
            )
        )
        # Verify staged bytes before replacing any existing deployment artifact.
        if not downloaded.is_file():
            raise ModelPreparationError(f"Hub did not return a file for {artifact['path']}")
        if (
            downloaded.stat().st_size != artifact["bytes"]
            or sha256(downloaded) != artifact["sha256"]
        ):
            raise ModelPreparationError(f"Downloaded bytes do not match lock: {artifact['path']}")
        install_regular_file(downloaded, destination, owned_source_root=staging)
    except ModelPreparationError:
        raise
    except Exception as exc:
        raise ModelPreparationError(
            f"Download failed for {model['id']}/{artifact['path']}: {exc}"
        ) from exc
    error = artifact_error(destination, artifact)
    if error:
        raise ModelPreparationError(
            f"Installed artifact failed verification: {destination}: {error}"
        )


def prepare_models(
    lock: dict[str, Any], vlm_dir: Path, native_home: Path, *, verify_only: bool
) -> dict[str, Any]:
    roots = {
        "vlm_dir": vlm_dir.expanduser().absolute(),
        "native_home": native_home.expanduser().absolute(),
    }
    problems: list[str] = []
    summaries: list[dict[str, Any]] = []
    for model in lock["models"]:
        directory = roots[model["target"]["root"]] / relative_path(
            model["target"]["path"], "target"
        )
        missing = []
        for artifact in model["files"]:
            destination = directory / relative_path(artifact["path"], "file")
            error = artifact_error(destination, artifact)
            if error:
                if verify_only:
                    problems.append(f"{model['id']}/{artifact['path']}: {error}")
                else:
                    missing.append((artifact, destination))
        if missing:
            directory.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=".mineru-download-", dir=directory.parent
            ) as temporary:
                for artifact, destination in missing:
                    download_artifact(model, artifact, destination, Path(temporary))
        summaries.append(
            {
                "id": model["id"],
                "repo_id": model["repo_id"],
                "revision": model["revision"],
                "directory": str(directory),
                "files": len(model["files"]),
                "bytes": sum(artifact["bytes"] for artifact in model["files"]),
                "downloaded_files": len(missing),
            }
        )
    if problems:
        raise ModelPreparationError("Model verification failed:\n" + "\n".join(problems))
    return {"status": "verified", "offline_verification": verify_only, "models": summaries}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vlm-dir", type=Path, default=Path("/models/mineru"), help="VLM volume root"
    )
    parser.add_argument(
        "--native-home",
        type=Path,
        default=Path("/models/mineru-native"),
        help="Native worker HOME volume root",
    )
    parser.add_argument(
        "--lock-file", type=Path, default=DEFAULT_LOCK, help="Committed immutable model lock"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify local files without imports or network calls",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        lock = load_lock(args.lock_file)
        result = prepare_models(lock, args.vlm_dir, args.native_home, verify_only=args.verify_only)
    except (ModelPreparationError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
