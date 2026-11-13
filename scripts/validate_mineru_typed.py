"""Run fixed DocVortex checks in a disposable offline, CPU-only container.

Reuses an immutable local image. No image pull, dependency install, worker
entrypoint, source/Expected/media mount or production output write is provided.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = (
    "moparse_eval/__init__.py",
    "moparse_eval/mineru_typed_validation.py",
    "app/__init__.py",
    "app/adapters/__init__.py",
    "app/adapters/native_config.py",
    "app/adapters/native_readers.py",
    "app/adapters/mineru_native.py",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(image, output, name, arguments, mounts=(), *, test=False):
    cpus = sorted(os.sched_getaffinity(0))[:8]
    cid = output / (name + ".cid")
    code = [*CODE]
    if test:
        code.extend(
            [
                "tests/__init__.py",
                "tests/validation/__init__.py",
                "tests/validation/test_mineru_typed_validation.py",
            ]
        )
    code = [p for p in code if (ROOT / p).is_file()]
    command = [
        "docker",
        "run",
        "--pull",
        "never",
        "--cidfile",
        str(cid),
        "--network",
        "none",
        "--runtime",
        "runc",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "8g",
        "--memory-swap",
        "8g",
        "--cpus",
        "8",
        "--cpuset-cpus",
        ",".join(map(str, cpus)),
        "--pids-limit",
        "128",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=128m",
        "--env",
        "CUDA_VISIBLE_DEVICES=",
        "--env",
        "NVIDIA_VISIBLE_DEVICES=void",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "OPENBLAS_NUM_THREADS=1",
        "--env",
        "OMP_NUM_THREADS=1",
        "--env",
        "HF_HUB_OFFLINE=1",
        "--workdir",
        "/validation",
    ]
    for source in code:
        command.extend(
            ["--mount", f"type=bind,src={ROOT / source},dst=/validation/{source},readonly"]
        )
    for source, target in mounts:
        command.extend(["--mount", f"type=bind,src={source},dst={target},readonly"])
    command.extend(
        [
            "--mount",
            f"type=bind,src={output},dst=/output",
            "--entrypoint",
            "/usr/local/bin/python",
            image,
            "-I",
            "-c",
        ]
    )
    module = (
        "tests.validation.test_mineru_typed_validation"
        if test
        else "moparse_eval.mineru_typed_validation"
    )
    command.append(
        f"import sys; sys.path.insert(0, '/validation'); from {module} import main; raise SystemExit(main())"
    )
    command.extend(arguments)
    record = {
        "command": command,
        "reproduce": shlex.join(command),
        "code_sha256": {p: sha(ROOT / p) for p in code},
        "input_sha256": {str(p): sha(p) for p, _ in mounts},
    }
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        record.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        if cid.exists():
            container = cid.read_text().strip()
            inspected = json.loads(
                subprocess.check_output(["docker", "inspect", container], text=True)
            )[0]
            cfg = inspected["HostConfig"]
            record["actual_container"] = {
                "id": container,
                "image": inspected["Image"],
                "state": inspected["State"],
                "limits": {
                    k: cfg.get(k)
                    for k in [
                        "NetworkMode",
                        "Runtime",
                        "ReadonlyRootfs",
                        "Memory",
                        "MemorySwap",
                        "NanoCpus",
                        "CpusetCpus",
                        "PidsLimit",
                        "CapDrop",
                        "SecurityOpt",
                        "DeviceRequests",
                        "Devices",
                    ]
                },
                "mounts": [
                    {k: m[k] for k in ("Source", "Destination", "RW")} for m in inspected["Mounts"]
                ],
            }
    finally:
        if cid.exists():
            container = cid.read_text().strip()
            cleanup = subprocess.run(
                ["docker", "rm", "-f", container], capture_output=True, text=True, check=False
            )
            record["own_container_cleanup_exit_code"] = cleanup.returncode
        record["code_unchanged"] = all(sha(ROOT / p) == h for p, h in record["code_sha256"].items())
        record["inputs_unchanged"] = all(
            sha(Path(p)) == h for p, h in record["input_sha256"].items()
        )
        (output / (name + "-execution.json")).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        )
    print(
        json.dumps(
            {
                "stage": name,
                "exit_code": record.get("exit_code"),
                "stdout": record.get("stdout"),
                "stderr": record.get("stderr"),
            }
        )
    )
    return record.get("exit_code", 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Existing immutable sha256 image ID")
    parser.add_argument("--output", type=Path, required=True, help="New run directory")
    parser.add_argument("--binding", type=Path, help="Prior fixed-input final-binding.json")
    parser.add_argument("--environment-only", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if not args.image.startswith("sha256:") or len(args.image) != 71:
        parser.error("a complete local immutable image ID is required")
    image = json.loads(
        subprocess.check_output(["docker", "image", "inspect", args.image], text=True)
    )[0]
    if image["Id"] != args.image:
        parser.error("image identity mismatch")
    preparation = {
        "sys_executable": sys.executable,
        "image_id": image["Id"],
        "image_repo_digests": image.get("RepoDigests"),
        "package_source": "existing_local_immutable_native_worker_image; no download or installation",
        "historical_download_url": "not recorded by installed distribution; not claimed",
        "main_environment_modified": False,
        "historical_lock_modified": False,
        "network_used": False,
        "launcher_sha256": sha(Path(__file__)),
        "command": [sys.executable, *sys.argv],
    }
    (output / "preparation.json").write_text(
        json.dumps(preparation, ensure_ascii=False, indent=2) + "\n"
    )
    if args.test:
        return execute(
            args.image, output, "official-tests", ["--output", "/output/tests.json"], test=True
        )
    result = execute(
        args.image,
        output,
        "environment",
        ["--environment-only", "--output", "/output/environment.json"],
    )
    if result or args.environment_only:
        return result
    if args.binding is None:
        parser.error("prior binding is required for the two fixed inputs")
    binding = json.loads(args.binding.read_text())
    selected = [o for o in binding["outputs"] if o["pipeline"] in {"P06", "P07"}]
    if len(selected) != 2 or {o["pipeline"] for o in selected} != {"P06", "P07"}:
        parser.error("binding must identify each pipeline exactly once")
    for item in selected:
        path = (ROOT / item["native_input"]).resolve()
        if sha(path) != item["native_sha256"]:
            parser.error("native differs from immutable prior binding")
        pipeline = item["pipeline"]
        result = execute(
            args.image,
            output,
            pipeline,
            [
                "--native",
                "/inputs/native.json",
                "--sha256",
                item["native_sha256"],
                "--pipeline",
                pipeline,
                "--output",
                f"/output/{pipeline}.json",
            ],
            [(path, "/inputs/native.json")],
        )
        if result:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
