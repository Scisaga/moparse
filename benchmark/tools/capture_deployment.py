#!/usr/bin/env python3
"""Read deployed identities and existing GET probes; never infer or record secrets.

This collector does not parse documents, download models, initialize pipelines or
start containers. A successful identity check is not a document-quality verdict.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import textwrap
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_PARTS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
DOCLING_REQUIRED_FILES = (
    "docling-project--docling-models/model_artifacts/tableformer/accurate/tm_config.json",
    "docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors",
    "docling-project--docling-layout-heron/config.json",
    "docling-project--docling-layout-heron/model.safetensors",
    "docling-project--docling-layout-heron/preprocessor_config.json",
)
SAFE_SETTING_NAMES = (
    "version", "native_parser_backend", "mineru_header_verifier", "mineru_source_verifier",
    "docling_artifacts_path",
    "docling_device", "docling_pdf_backend", "docling_do_cell_matching",
    "glm_ocr_enabled", "glm_sdk_enabled", "glm_sdk_orientation_enabled",
)
SAFE_MODEL_FLAGS = {
    "--served-model-name", "--dtype", "--gpu-memory-utilization", "--max-model-len",
    "--kv-cache-memory-bytes", "--max-num-seqs", "--max-num-batched-tokens",
    "--limit-mm-per-prompt", "--logits-processors", "--port", "--host",
}


def command(args: list[str]) -> str:
    result = subprocess.run(args, text=True, capture_output=True, timeout=60, check=False)
    if result.returncode:
        # Docker/validation stderr and process arguments can contain credentials.
        raise RuntimeError(f"Read-only subprocess failed with exit code {result.returncode}")
    return result.stdout.strip()


def endpoint(url: str) -> dict:
    with build_opener(ProxyHandler({})).open(url, timeout=20) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError("Identity GET returned a non-object response")
    return result


def sha(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def local_code(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        raise ValueError("Expected host source/static directory is missing")
    return {
        path.relative_to(directory).as_posix(): sha(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and not (set(path.relative_to(directory).parts) & EXCLUDED_PARTS)
        and path.suffix not in EXCLUDED_SUFFIXES
    }


def code(container: str, directory: str) -> dict[str, str]:
    script = textwrap.dedent(f"""
        import pathlib, hashlib, json
        p = pathlib.Path({directory!r})
        if not p.is_dir():
            raise ValueError('Expected deployed directory is missing')
        excluded = {sorted(EXCLUDED_PARTS)!r}
        suffixes = {sorted(EXCLUDED_SUFFIXES)!r}
        def digest(path):
            with path.open('rb') as source:
                return hashlib.file_digest(source, 'sha256').hexdigest()
        print(json.dumps({{str(f.relative_to(p)): digest(f) for f in sorted(p.rglob('*'))
                          if f.is_file() and not set(f.relative_to(p).parts).intersection(excluded)
                          and f.suffix not in suffixes}}))
    """)
    return json.loads(command(["docker", "exec", container, "python3", "-c", script]))


def compare_files(actual: dict[str, str], expected: dict[str, str]) -> dict:
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(actual) & set(expected) if actual[name] != expected[name])
    return {
        "deployed_files": actual, "expected_host_files": expected,
        "missing_in_container": missing, "unexpected_in_container": unexpected,
        "content_mismatches": changed, "file_sets_match": not missing and not unexpected,
        "host_mismatches": sorted(set(missing + unexpected + changed)),
        "matches_host_files": bool(expected) and not (missing or unexpected or changed),
    }


def identity(container: str) -> dict:
    inspected = json.loads(command(["docker", "inspect", container]))[0]
    # Never serialize Config.Env, arbitrary labels, or raw command arguments.
    # The command hash distinguishes startup invocations without leaking tokens.
    cmd = json.dumps(inspected["Config"].get("Cmd"), sort_keys=True).encode()
    return {
        "container": container, "id": inspected["Id"], "image_id": inspected["Image"],
        "image_tag": inspected["Config"]["Image"],
        "started_at": inspected["State"]["StartedAt"],
        "running": inspected["State"]["Running"],
        "startup_command_SHA256": hashlib.sha256(cmd).hexdigest(),
        "model_startup_options": model_options(inspected["Config"].get("Cmd")),
        "mounts": [{key: item.get(key) for key in ("Type", "Name", "Destination", "RW")}
                   for item in inspected["Mounts"]],
        "source_revision_label": (inspected["Config"].get("Labels") or {}).get(
            "org.opencontainers.image.revision"),
    }


def model_options(arguments: list | None) -> dict:
    """Keep public model configuration, not arbitrary CLI flags/credentials."""
    if not isinstance(arguments, list):
        return {}
    result = {}
    if arguments and isinstance(arguments[0], str) and arguments[0].startswith("/models/"):
        result["model_path"] = arguments[0]
    for index, value in enumerate(arguments):
        if value == "--enforce-eager":
            result[value] = True
        elif value in SAFE_MODEL_FLAGS and index + 1 < len(arguments):
            result[value] = arguments[index + 1]
    return result


def mount_for_path(container_identity: dict, directory: str) -> dict | None:
    path = PurePosixPath(directory)
    candidates = [item for item in container_identity.get("mounts", [])
                  if path.is_relative_to(PurePosixPath(item["Destination"]))]
    if not candidates:
        return None
    selected = max(candidates, key=lambda item: len(PurePosixPath(item["Destination"]).parts))
    return {**selected, "path_in_mount": str(path.relative_to(selected["Destination"]))}


def artifacts(container: str, directory: str, names: list[str]) -> dict:
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Artifact paths must stay inside the selected model directory")
    script = textwrap.dedent(f"""
        import pathlib, hashlib, json
        p = pathlib.Path({directory!r})
        files = {{}}
        for name in {names!r}:
            f = p / name
            if f.is_file():
                with f.open('rb') as source:
                    files[name] = {{'sha256': hashlib.file_digest(source, 'sha256').hexdigest(),
                                   'bytes': f.stat().st_size}}
        print(json.dumps({{'directory': str(p), 'resolved_directory': str(p.resolve()),
                          'directory_exists': p.is_dir(), 'files': files}}))
    """)
    return json.loads(command(["docker", "exec", container, "python3", "-c", script]))


def required_files(inventory: dict, names: list[str]) -> dict:
    actual = inventory.get("files", {})
    missing = sorted(set(names) - set(actual))
    invalid = sorted(name for name, value in actual.items() if name in names
                     and (not isinstance(value.get("bytes"), int) or value["bytes"] <= 0
                          or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("sha256", "")))))
    return {"actual": actual, "required_files": names, "missing_files": missing,
            "invalid_files": invalid,
            "complete": bool(names) and inventory.get("directory_exists") is True
                        and not missing and not invalid}


def package_versions(container: str) -> dict:
    script = textwrap.dedent("""
        import importlib.metadata, json, platform
        packages = {distribution.metadata['Name'].lower().replace('_', '-'): distribution.version
                    for distribution in importlib.metadata.distributions()
                    if distribution.metadata.get('Name')}
        print(json.dumps({'python': platform.python_version(), 'packages': dict(sorted(packages.items()))}))
    """)
    return json.loads(command(["docker", "exec", container, "python3", "-c", script]))


def selected_settings(container: str) -> dict:
    script = textwrap.dedent(f"""
        import json
        from app.config import get_settings
        settings = get_settings()
        result = {{name: getattr(settings, name, None) for name in {SAFE_SETTING_NAMES!r}}}
        print(json.dumps(result, default=str))
    """)
    return json.loads(command(["docker", "exec", container, "python3", "-c", script]))


def patched_dependency(container: str) -> dict:
    script = textwrap.dedent("""
        import hashlib, importlib.metadata, importlib.util, json, pathlib
        spec = importlib.util.find_spec('mineru')
        if spec is None or spec.origin is None:
            raise ValueError('MinerU is not installed')
        path = pathlib.Path(spec.origin).parent / 'backend/analysis/pdf/text/native.py'
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        print(json.dumps({'path': str(path), 'mineru_version': importlib.metadata.version('mineru'),
                          'source_SHA256': digest}))
    """)
    actual = json.loads(command(["docker", "exec", container, "python3", "-c", script]))
    constants = {}
    for node in ast.parse((ROOT / "native_worker/patch_dependency.py").read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PATCHED_SHA256" for target in node.targets
        ):
            constants["PATCHED_SHA256"] = ast.literal_eval(node.value)
    expected = constants.get("PATCHED_SHA256")
    return {**actual, "expected_SHA256": expected,
            "matches_reviewed_patch": bool(expected) and actual.get("source_SHA256") == expected
                                      and actual.get("mineru_version") == "4.0.12"}


def safe_probe(kind: str, payload: dict) -> dict:
    """Record known identity fields, never arbitrary response/env/credential data."""
    allowed = {
        "health": ("status", "service", "version", "uptime_seconds", "queue"),
        "ready": ("ready", "status", "checks"),
        "worker": ("ready", "backend", "versions", "model", "max_concurrency", "text_matching"),
        "models": ("object", "data"),
    }
    result = {name: payload[name] for name in allowed[kind] if name in payload}
    if kind == "health":
        result["config"] = {name: payload.get("config", {}).get(name)
                            for name in SAFE_SETTING_NAMES if name in payload.get("config", {})}
    if kind in {"health", "ready"}:
        result["backends"] = [{name: item[name] for name in
                               ("name", "state", "enabled", "model", "latency_ms", "checked_at")
                               if name in item} for item in payload.get("backends", [])]
    if kind == "models":
        result["data"] = [{name: item[name] for name in
                           ("id", "object", "created", "owned_by", "root", "max_model_len")
                           if name in item} for item in payload.get("data", [])]
    return result


def readiness_checks(report: dict) -> dict[str, bool]:
    settings = report.get("selected_settings", {})
    mineru = settings.get("native_parser_backend") == "mineru"
    docling = (settings.get("native_parser_backend") == "docling"
               or settings.get("mineru_header_verifier") == "docling"
               or settings.get("mineru_source_verifier") == "docling")
    locked = report.get("model_artifacts", {})
    sources = report.get("source", {})
    checks = {
        "http_ready": report.get("ready", {}).get("ready") is True,
        "selected_settings_observed": settings.get("native_parser_backend") in {"mineru", "docling"},
        "live_native_selection_matches_settings": all(
            report.get("health", {}).get("config", {}).get(key) == settings.get(key)
            for key in ("native_parser_backend", "mineru_header_verifier", "mineru_source_verifier")),
        "containers_running": bool(report.get("containers"))
                              and all(item.get("running") is True for item in report.get("containers", [])),
        "source_file_sets_and_content_match": bool(sources)
                                             and all(item.get("matches_host_files") is True for item in sources.values()),
        "static_file_set_and_content_match": report.get("static", {}).get("matches_host_files") is True,
        "package_metadata_observed": bool(report.get("package_versions"))
                                     and all(item.get("packages") for item in report.get("package_versions", {}).values()),
        "required_docling_models_complete": not docling
            or (locked.get("docling_header_verifier", {}).get("complete") is True
                and bool(locked.get("docling_header_verifier", {}).get("selected_mount"))),
        "required_mineru_models_match": not mineru or all(
            locked.get(key, {}).get("matches_locked_files") is True for key in ("vlm", "native")),
        "worker_ready_and_patch_matches": not mineru or (
            report.get("worker", {}).get("ready") is True
            and report.get("worker_patched_dependency", {}).get("matches_reviewed_patch") is True),
        "served_model_matches_worker": not mineru or any(
            item.get("id") == report.get("worker", {}).get("model")
            for item in report.get("models", {}).get("data", [])),
        "capture_has_no_errors": not report.get("errors"),
    }
    return {name: bool(value) for name, value in checks.items()}


def collect(args: argparse.Namespace) -> dict:
    report = {"schema": "moparse-observed-deployment/1", "collector_version": 2,
              "observed_at": datetime.now(UTC).isoformat(), "errors": [], "containers": [],
              "source": {}, "model_artifacts": {}, "package_versions": {},
              "scope": "Read-only identity GETs, Docker metadata and on-disk files; no document inference or quality claim"}

    def observe(phase, operation, default=None):
        try:
            return operation()
        except Exception as error:
            # Error messages/tracebacks may embed upstream payloads or secrets.
            report["errors"].append({"phase": phase, "error_type": type(error).__name__,
                                      "status": "unverified"})
            return default

    report["git_head"] = observe("git_head", lambda: command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]))
    report["git_worktree_dirty"] = observe("git_worktree", lambda: bool(command(
        ["git", "-C", str(ROOT), "status", "--porcelain"])))
    for kind, url in (("health", args.base_url + "/health"), ("ready", args.base_url + "/ready")):
        report[kind] = observe(kind, lambda kind=kind, url=url: safe_probe(kind, endpoint(url)), {})
    report["selected_settings"] = observe("selected_settings", lambda: selected_settings(args.app), {})
    settings = report["selected_settings"]
    mineru = settings.get("native_parser_backend") == "mineru"
    if mineru:
        for kind, url in (("worker", args.worker_url + "/ready"), ("models", args.model_url + "/v1/models")):
            report[kind] = observe(kind, lambda kind=kind, url=url: safe_probe(kind, endpoint(url)), {})
    containers = [args.app]
    if mineru:
        containers += [args.worker, args.model]
    if settings.get("glm_ocr_enabled"):
        containers.append("docling_glm_ocr")
        if settings.get("glm_sdk_enabled"):
            containers.append("docling_glm_ocr_sdk")
    by_name = {}
    for container in containers:
        item = observe("container:" + container, lambda container=container: identity(container))
        if item:
            report["containers"].append(item)
            by_name[container] = item
        report["package_versions"][container] = observe(
            "packages:" + container, lambda container=container: package_versions(container), {})
    targets = [(args.app, "/app/app", ROOT / "app")]
    if mineru:
        targets.append((args.worker, "/worker/native_worker", ROOT / "native_worker"))
    for name, target, host in targets:
        report["source"][name] = observe("source:" + name, lambda name=name, target=target, host=host:
            compare_files(code(name, target), local_code(host)), {"matches_host_files": False})
    report["static"] = observe("app_static", lambda: compare_files(
        code(args.app, "/app/static"), local_code(args.static_dir)), {"matches_host_files": False})
    if mineru:
        report["worker_patched_dependency"] = observe("worker_patched_dependency", lambda: patched_dependency(args.worker), {})
        locked = observe("model_lock", lambda: json.loads((ROOT / "native_worker/models.lock.json").read_text()), {})
        for entry in locked.get("models", []):
            name, mount_root = ((args.model, "/models/mineru") if entry["id"] == "vlm"
                                else (args.worker, "/models/mineru-native"))
            directory = mount_root + "/" + entry["target"]["path"]
            actual = observe("model_artifacts:" + entry["id"], lambda name=name, directory=directory, entry=entry:
                artifacts(name, directory, [item["path"] for item in entry["files"]]), {})
            expected = {item["path"]: {key: item[key] for key in ("sha256", "bytes")} for item in entry["files"]}
            report["model_artifacts"][entry["id"]] = {
                "repo_id": entry["repo_id"], "revision": entry["revision"],
                **actual, "actual": actual.get("files", {}),
                "selected_mount": mount_for_path(by_name.get(name, {}), directory),
                "matches_locked_files": actual.get("directory_exists") is True
                                        and bool(expected) and actual.get("files") == expected}
        report["all_locked_models_match"] = all(
            report["model_artifacts"].get(key, {}).get("matches_locked_files") is True for key in ("vlm", "native"))
    docling = (settings.get("native_parser_backend") == "docling"
               or settings.get("mineru_header_verifier") == "docling"
               or settings.get("mineru_source_verifier") == "docling")
    if docling:
        directory = settings.get("docling_artifacts_path")
        if not isinstance(directory, str) or not directory.startswith("/"):
            report["errors"].append({"phase": "docling_artifacts_path", "status": "unverified"})
            directory = "/__unobserved_docling_artifacts__"
        actual = observe("docling_models", lambda: artifacts(args.app, directory, list(DOCLING_REQUIRED_FILES)), {})
        report["model_artifacts"]["docling_header_verifier"] = {
            **actual, **required_files(actual, list(DOCLING_REQUIRED_FILES)),
            "selected_mount": mount_for_path(by_name.get(args.app, {}), directory),
            "SHA_provenance": "Observed files in selected mounted artifact directory; not a new immutable upstream revision lock"}
    report["observed_live"] = bool(report["containers"]) and bool(report.get("health"))
    report["identity_checks"] = readiness_checks(report)
    report["ready_and_source_matched"] = all(report["identity_checks"].values())
    report["status"] = "verified" if report["ready_and_source_matched"] else "unverified"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", default="moparse-candidate")
    parser.add_argument("--worker", default="moparse-native-worker")
    parser.add_argument("--model", default="moparse-mineru-vllm")
    parser.add_argument("--base-url", default="http://127.0.0.1:12313")
    parser.add_argument("--worker-url", default="http://127.0.0.1:12432")
    parser.add_argument("--model-url", default="http://127.0.0.1:12431")
    parser.add_argument("--static-dir", type=Path, default=ROOT / "frontend/dist")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new path; deployment observations are immutable")
    report = collect(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        target.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "status": report["status"],
                      "ready_and_source_matched": report["ready_and_source_matched"],
                      "failed_checks": [name for name, passed in report["identity_checks"].items() if not passed]}))
    return 0 if report["ready_and_source_matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
