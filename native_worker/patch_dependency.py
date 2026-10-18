"""Apply and verify the reviewed patch to exactly the supported dependency.

Run during image construction, before starting the worker. A different upstream
source fails the build so a package upgrade cannot silently skip this fix.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import os
import subprocess
from pathlib import Path

ORIGINAL_SHA256 = "02a4e5bd0564acce4e18ce9b8a9e459c43bc3342ab93bd952db16dabee726fec"
PATCHED_SHA256 = "616f44e2a1749f4b82074df36c3da852694a9401828c6c36aad62553b2a182cf"
PATCH_NAME = "native-text-matching-axis-v1"
MFR_ORIGINAL_SHA256 = "06f787c9414b99388a89b75a9c8a6c752058146d4538725e4afb2451829f1c1f"
MFR_PATCHED_SHA256 = "e2b45491bea11a6af82fef90ec1d4d6beb72373b2aaaa611b7228c309947c5e2"
MFR_PATCH_NAME = "cpu-mfr-microbatch-limit-v1"
MFR_BATCH_ENV = "MOPARSE_CPU_MFR_BATCH_SIZE"


def source_path() -> Path:
    spec = importlib.util.find_spec("mineru")
    if spec is None or spec.origin is None:
        raise RuntimeError("MinerU is not installed")
    return Path(spec.origin).parent / "backend/analysis/pdf/text/native.py"


def mfr_source_path() -> Path:
    return source_path().parents[4] / "model/mfr/pp_formulanet_plus_m_onnx.py"


def cpu_mfr_batch_size() -> int:
    """Validate the same explicit cap enforced by the reviewed dependency."""
    raw = os.getenv(MFR_BATCH_ENV)
    if raw is None:
        return 8
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{MFR_BATCH_ENV} must be an integer from 1 to 8") from exc
    if not 1 <= value <= 8:
        raise ValueError(f"{MFR_BATCH_ENV} must be an integer from 1 to 8")
    return value


def verify_patch() -> dict[str, str]:
    if importlib.metadata.version("mineru") != "4.0.12":
        raise RuntimeError("the reviewed text-axis patch requires MinerU 4.0.12")
    digest = hashlib.sha256(source_path().read_bytes()).hexdigest()
    if digest != PATCHED_SHA256:
        raise RuntimeError("MinerU native text matching source is unpatched or changed")
    return {"name": PATCH_NAME, "source_sha256": digest}


def verify_resource_patch() -> dict[str, str | int | bool]:
    if importlib.metadata.version("mineru") != "4.0.12":
        raise RuntimeError("the reviewed CPU microbatch patch requires MinerU 4.0.12")
    digest = hashlib.sha256(mfr_source_path().read_bytes()).hexdigest()
    if digest != MFR_PATCHED_SHA256:
        raise RuntimeError("MinerU CPU formula microbatch source is unpatched or changed")
    # These two settings retain the official SDK's environment semantics.
    try:
        window = max(1, int(os.getenv("MINERU_PROCESSING_WINDOW_SIZE", "64")))
    except ValueError:
        window = 64
    trim = os.getenv("MINERU_MALLOC_TRIM", "").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "name": MFR_PATCH_NAME,
        "source_sha256": digest,
        "cpu_mfr_batch_size": cpu_mfr_batch_size(),
        "processing_window_size": window,
        "malloc_trim": trim,
    }


def main() -> None:
    if importlib.metadata.version("mineru") != "4.0.12":
        raise RuntimeError("refusing to patch an unreviewed MinerU version/source")
    path = source_path()
    plans = [
        (path, ORIGINAL_SHA256, PATCHED_SHA256, "mineru-4.0.12-text-axis.patch"),
        (
            mfr_source_path(),
            MFR_ORIGINAL_SHA256,
            MFR_PATCHED_SHA256,
            "mineru-4.0.12-mfr-cpu-batch.patch",
        ),
    ]
    # Check every input before writing either source. Both already-patched and
    # original sources are accepted, permitting an interrupted build to resume.
    for target, original, patched, _name in plans:
        if hashlib.sha256(target.read_bytes()).hexdigest() not in {original, patched}:
            raise RuntimeError("refusing to patch an unreviewed MinerU version/source")
    cpu_mfr_batch_size()
    for target, _original, patched, name in plans:
        if hashlib.sha256(target.read_bytes()).hexdigest() == patched:
            continue
        patch = Path(__file__).parent / "patches" / name
        subprocess.run(
            [
                "patch",
                "--batch",
                "--fuzz=0",
                "-p1",
                "-d",
                str(path.parents[5]),
                "-i",
                str(patch.resolve()),
            ],
            check=True,
        )
    print({"text_matching": verify_patch(), "resource_policy": verify_resource_patch()})


if __name__ == "__main__":
    main()
