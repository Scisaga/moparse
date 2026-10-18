#!/usr/bin/env python3
"""Validate a corpus, capture HTTP results, score public Markdown and compare evidence.

The CLI never starts models, changes GPU settings or deploys a service. Source
documents are private local references. Historical files are opened read-only.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import types
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmark"
DEFAULT_DATASET = BENCH / "datasets/moparse-v1/dataset.json"
HISTORY = ROOT / "benchmark-results/clean-model-comparison-20261015"
CONTENT = HISTORY / "followup/20261017/content-preservation-mineru"
FROZEN = BENCH / "scorers/frozen"
SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")


def utc() -> str:
    return datetime.now(UTC).isoformat()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value: Any, *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if overwrite else "x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def artifact(path: Path) -> dict[str, Any]:
    return {"path": relative(path), "sha256": digest(path), "bytes": path.stat().st_size}


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot import evaluator: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_relocated_module(name: str, path: Path, overrides: dict[str, Any]) -> Any:
    """Relocate file globals only; execute unchanged scoring predicates."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            key = node.targets[0].id
            if key in overrides:
                node.value = ast.Subscript(
                    value=ast.Name(id="_MOPARSE_RELOCATED_PATHS", ctx=ast.Load()),
                    slice=ast.Constant(value=key),
                    ctx=ast.Load(),
                )
    ast.fix_missing_locations(tree)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module._MOPARSE_RELOCATED_PATHS = overrides
    sys.modules[name] = module
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


def frozen_contract() -> list[dict]:
    lock = read(FROZEN / "lock.json")
    result = []
    for item in lock["files"]:
        path = FROZEN / item["path"]
        if not path.is_file() or digest(path) != item["sha256"]:
            raise ValueError("Frozen scorer bundle changed: " + item["path"])
        result.append(artifact(path))
    result.append(artifact(DEFAULT_DATASET.parent / "annotations/core209-source-gold.json"))
    return result


def verified_source_resolver(frozen_sources: list[dict], dataset_documents: list[dict], root: Path):
    """Relocate only unambiguous original identities after actual-byte validation."""
    frozen_by_name: dict[str, list[dict]] = {}
    dataset_by_name: dict[str, list[dict]] = {}
    for item in frozen_sources:
        frozen_by_name.setdefault(Path(item["path"]).name, []).append(item)
    for item in dataset_documents:
        dataset_by_name.setdefault(Path(item["source_path"]).name, []).append(item)
    verified: dict[str, tuple[Path, tuple[int, int, int]]] = {}
    audit: list[dict] = []

    def resolve(source_path: Path) -> Path:
        name = Path(source_path).name
        if name not in frozen_by_name:
            return source_path
        candidates, originals = dataset_by_name.get(name, []), frozen_by_name[name]
        if len(candidates) != 1 or len(originals) != 1:
            raise ValueError("Source path relocation requires one registered original: " + name)
        expected, registered = originals[0]["sha256"], candidates[0]
        if registered["sha256"] != expected:
            raise ValueError("Frozen and registered source identity disagree: " + name)
        canonical = root / registered["source_path"]
        if not canonical.is_file():
            raise ValueError("Registered original PDF is required for source judging: " + name)
        stat = canonical.stat()
        identity = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if name not in verified or verified[name] != (canonical, identity):
            actual = digest(canonical)
            if actual != expected:
                raise ValueError("Actual source bytes disagree with frozen SHA256: " + name)
            verified[name] = canonical, identity
            audit.append(
                {
                    "document_id": registered["id"],
                    "requested_path": str(source_path),
                    "registered_path": str(canonical),
                    "frozen_sha256": expected,
                    "registered_sha256": registered["sha256"],
                    "actual_sha256": actual,
                    "source_bytes_verified": True,
                    "source_text_or_gold_changed": False,
                }
            )
        return canonical

    return resolve, audit


def public_scoring_runtime():
    frozen_contract()
    baseline = FROZEN / "followup/20261017/production-baseline/score-baseline.py"
    full = FROZEN / "followup/20261017/selected-pipeline-deployment/score-full-cohort.py"
    adapter = load_relocated_module(
        "moparse_portable_public", full, {"OLD": FROZEN, "REPO": ROOT, "FROZEN_ADAPTER": baseline}
    )
    frozen = load_relocated_module("moparse_portable_baseline", baseline, {"OLD": FROZEN})
    _, dataset_documents = load_dataset(DEFAULT_DATASET)
    resolve_source, source_audit = verified_source_resolver(
        frozen.MANIFEST["documents"], dataset_documents, ROOT
    )
    visited: set[int] = set()

    def relocate(module):
        if id(module) in visited:
            return
        visited.add(id(module))
        path = getattr(module, "__file__", None)
        if not path or not Path(path).resolve().is_relative_to(FROZEN):
            return
        if hasattr(module, "REPO"):
            module.REPO = ROOT
        if hasattr(module, "GOLD"):
            module.GOLD = DEFAULT_DATASET.parent / "annotations/core209-source-gold.json"
        if hasattr(module, "select_source_table"):
            original_selector = module.select_source_table

            def relocated_selector(expected, page, source_path, original=original_selector):
                return original(expected, page, resolve_source(source_path))

            module.select_source_table = relocated_selector
        for value in list(vars(module).values()):
            if isinstance(value, types.ModuleType):
                relocate(value)

    relocate(frozen)
    frozen.moparse_source_relocations = source_audit
    return adapter, frozen


def load_dataset(path: Path) -> tuple[dict, list[dict]]:
    data = read(path)
    documents = [
        json.loads(line)
        for line in (path.parent / data["documents"]).read_text().splitlines()
        if line.strip()
    ]
    return data, documents


def validate_dataset(path: Path, *, require_sources: bool = False) -> dict:
    data, documents = load_dataset(path)
    errors, unavailable, groups = [], [], {}
    if data.get("schema") != "moparse-dataset/1":
        errors.append("Unsupported dataset schema")
    ids = [item["id"] for item in documents]
    if len(set(ids)) != len(ids):
        errors.append("Duplicate document IDs")
    hashes: dict[str, str] = {}
    for document in documents:
        identifier, source_hash = document["id"], document["sha256"]
        if not SAFE_ID.fullmatch(identifier):
            errors.append(f"Unsafe document ID: {identifier}")
        if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            errors.append(f"Invalid source SHA: {identifier}")
        if document["page_count"] <= 0:
            errors.append(f"Invalid page count: {identifier}")
        if source_hash in hashes and document.get("derived_from") != hashes[source_hash]:
            errors.append(f"Duplicate original bytes without derivative link: {identifier}")
        hashes[source_hash] = identifier
        group = document["leakage_group"]
        groups.setdefault(group, set()).add(document["split"])
        if document.get("exposure") == "previously_used" and document["split"] == "holdout":
            errors.append(f"Exposed document cannot be holdout: {identifier}")
        source = repo_path(document["source_path"])
        if source.is_file():
            if digest(source) != source_hash:
                errors.append(f"Source hash mismatch: {identifier}")
        else:
            unavailable.append(identifier)
    for group, splits in groups.items():
        if "holdout" in splits and len(splits) > 1:
            errors.append(f"Leakage group crosses holdout boundary: {group}")
    for item in data["artifacts"]:
        source = path.parent / item["path"]
        if not source.is_file() or digest(source) != item["sha256"]:
            errors.append(f"Annotation/manifest hash mismatch: {item['path']}")
    for parent in (path.parent / "annotations").glob("*.assertions.json"):
        errors.extend(validate_annotations(read(parent), documents))
    for cohort in data["cohorts"]:
        selected = cohort.get("document_ids", [])
        if set(selected) - set(ids):
            errors.append(f"Unknown document in cohort: {cohort['id']}")
        if "source_pages" in cohort:
            by_id = {item["id"]: item for item in documents}
            for key, pages in cohort["source_pages"].items():
                if key not in by_id or any(
                    type(p) is not int or p < 1 or p > by_id[key]["page_count"] for p in pages
                ):
                    errors.append(f"Invalid selected pages: {cohort['id']} / {key}")
    if require_sources and unavailable:
        errors.append("Local sources required but missing: " + ", ".join(unavailable))
    return {
        "schema": "moparse-dataset-validation/1",
        "dataset": data["id"],
        "dataset_sha256": digest(path),
        "valid": not errors,
        "errors": errors,
        "documents": len(documents),
        "pages": sum(d["page_count"] for d in documents),
        "splits": dict(Counter(d["split"] for d in documents)),
        "unavailable_local_sources": unavailable,
        "independent_holdout_documents": sum(d["split"] == "holdout" for d in documents),
    }


def validate_annotations(data: dict, documents: list[dict] | None = None) -> list[str]:
    errors, seen = [], set()
    if data.get("schema") != "moparse-source-assertions/1" or not isinstance(
        data.get("checks"), list
    ):
        return ["Unsupported assertion schema or missing checks"]
    if not data["checks"]:
        errors.append("Refusing an empty source assertion set")
    by_id = {item["id"]: item for item in documents or []}
    source_ids = {item["id"]: item.get("sha256") for item in data.get("source_documents", [])}
    for check in data["checks"]:
        identifier = check.get("id")
        if not isinstance(identifier, str) or identifier in seen:
            errors.append(f"Missing/duplicate assertion ID: {identifier}")
        seen.add(identifier)
        document_id = check.get("document_id")
        if document_id not in source_ids:
            errors.append(f"Assertion lacks a hashed source document: {identifier}")
        if by_id and (
            document_id not in by_id or source_ids[document_id] != by_id[document_id]["sha256"]
        ):
            errors.append(f"Assertion source differs from registered document: {identifier}")
        page = check.get("page")
        if page is not None and (
            type(page) is not int
            or page < 1
            or (document_id in by_id and page > by_id[document_id]["page_count"])
        ):
            errors.append(f"Invalid assertion page: {identifier}")
        kind = check.get("kind")
        if kind not in {"text", "absent_text", "ordered_text", "regex", "table_grid", "table_span"}:
            errors.append(f"Unsupported assertion kind: {identifier}")
        if kind in {"text", "absent_text", "regex"} and not isinstance(check.get("expected"), str):
            errors.append(f"Expected text is not a string: {identifier}")
        if kind == "ordered_text" and (
            not isinstance(check.get("expected"), list)
            or not all(isinstance(v, str) for v in check["expected"])
        ):
            errors.append(f"Expected order is not a string list: {identifier}")
        if not isinstance(check.get("source_evidence"), dict):
            errors.append(f"Source-review provenance missing: {identifier}")
    return errors


def add_documents(args: argparse.Namespace) -> dict:
    """Append genuinely new sources after validation, preserving the prior manifest as evidence."""
    data, documents = load_dataset(args.dataset)
    incoming = read(args.documents)
    incoming = incoming["documents"] if isinstance(incoming, dict) else incoming
    if not isinstance(incoming, list) or not incoming:
        raise ValueError("--documents must contain a nonempty JSON list")
    old_ids = {item["id"] for item in documents}
    if old_ids.intersection(item["id"] for item in incoming):
        raise ValueError("An imported document ID already exists")
    expected_hashes = {item["sha256"] for item in documents}
    for item in incoming:
        if item["sha256"] in expected_hashes and not item.get("derived_from"):
            raise ValueError("Identical source bytes are not a new independent document")
        if item["split"] == "holdout" and item.get("exposure") != "unseen_at_freeze":
            raise ValueError("Holdout must explicitly record unseen_at_freeze exposure")
        source = repo_path(item["source_path"])
        if not source.is_file() or digest(source) != item["sha256"]:
            raise ValueError(f"New source missing or SHA mismatch: {item['id']}")
    annotation = read(args.annotations) if args.annotations else None
    if annotation:
        errors = validate_annotations(annotation, documents + incoming)
        if errors:
            raise ValueError("; ".join(errors))
    if any(cohort["id"] == args.cohort for cohort in data["cohorts"]):
        raise ValueError("Cohort already exists; use a new versioned cohort ID")
    # The prior locked metadata stays available even as the registry grows.
    history = args.dataset.parent / "versions" / ("dataset-" + digest(args.dataset)[:16] + ".json")
    if not history.exists():
        save(history, data)
    all_documents = documents + incoming
    manifest = args.dataset.parent / data["documents"]
    manifest.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in all_documents)
    )
    data["artifacts"] = [item for item in data["artifacts"] if item["path"] != data["documents"]]
    data["artifacts"].insert(0, {"path": data["documents"], "sha256": digest(manifest)})
    if annotation:
        name = args.cohort + ".assertions.json"
        target = args.dataset.parent / "annotations" / name
        save(target, annotation)
        data["artifacts"].append({"path": "annotations/" + name, "sha256": digest(target)})
    data["cohorts"].append(
        {
            "id": args.cohort,
            "document_ids": [item["id"] for item in incoming],
            "pages": sum(item["page_count"] for item in incoming),
            "whole_documents": True,
            "annotation": "annotations/" + name if annotation else None,
            "split": "holdout" if all(item["split"] == "holdout" for item in incoming) else "mixed",
        }
    )
    data["holdout"] = {
        "status": "source_reviewed" if annotation else "sources_acquired_annotations_pending",
        "document_ids": [item["id"] for item in all_documents if item["split"] == "holdout"],
        "requirement": "Freeze method configuration before seeing held-out model output",
    }
    data["version"] = args.version
    data["parent_manifest_sha256"] = digest(history)
    save(args.dataset, data, overwrite=True)
    return validate_dataset(args.dataset, require_sources=True)


def method(identifier: str) -> dict:
    if not SAFE_ID.fullmatch(identifier):
        raise ValueError("Invalid method ID")
    record = read(BENCH / "methods" / (identifier + ".json"))
    if record["id"] != identifier or record.get("fingerprint") != fingerprint(record["recipe"]):
        raise ValueError(f"Method recipe/fingerprint mismatch: {identifier}")
    return record


def validate_evidence(record: dict, *, check_files: bool = True) -> list[str]:
    errors = []
    if record.get("schema") != "moparse-evidence/1":
        errors.append("Unsupported evidence schema")
    for key in (
        "id",
        "method_id",
        "cohort_id",
        "origin",
        "output_stage",
        "quality",
        "performance",
        "provenance",
        "qualification",
    ):
        if key not in record:
            errors.append(f"Missing evidence field: {key}")
    if (
        record.get("origin") == "historical_reuse"
        and record.get("fresh_model_inference") is not False
    ):
        errors.append("Historical evidence must not claim fresh inference")
    for metric, value in record.get("quality", {}).items():
        passed, total = value.get("pass"), value.get("total")
        if type(passed) is not int or type(total) is not int or not 0 <= passed <= total:
            errors.append(f"Invalid quality denominator: {metric}")
    if check_files:
        for item in record.get("provenance", []):
            source = repo_path(item["path"])
            if not source.is_file() or digest(source) != item["sha256"]:
                errors.append(f"Evidence artifact missing or changed: {item['path']}")
    return errors


def import_evidence(source: Path, output: Path) -> dict:
    record = read(source)
    errors = validate_evidence(record)
    if errors:
        raise ValueError("; ".join(errors))
    registered = method(record["method_id"])
    record = {
        **record,
        "imported_at": utc(),
        "import_source": artifact(source),
        "registered_method_fingerprint": registered["fingerprint"],
    }
    # Historical configurations remain what actually ran, not the new recipe.
    record["qualification"]["matches_registered_recipe"] = (
        record.get("observed_recipe_fingerprint") == registered["fingerprint"]
    )
    save(output, record)
    return {
        "imported": record["id"],
        "output": str(output),
        "fresh_model_inference": record.get("fresh_model_inference", False),
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lower = math.floor(index)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (
        index - lower
    )


def normalize_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


class ResourceSampler:
    """Read-only whole-device metrics, with explicit sharing/attribution limits."""

    def __init__(self, output: Path, interval: float):
        self.output, self.interval = output, interval
        self.samples: list[dict] = []
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.done.is_set():
            started = time.monotonic()
            sample: dict[str, Any] = {
                "at": utc(),
                "monotonic": started,
                "scope": "whole GPU device; includes unrelated services",
            }
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=index,uuid,utilization.gpu,"
                        "memory.used,memory.free,power.draw,power.limit",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                    capture_output=True,
                    timeout=8,
                    check=True,
                )
                names = (
                    "index",
                    "uuid",
                    "utilization_pct",
                    "used_MiB",
                    "free_MiB",
                    "power_W",
                    "limit_W",
                )
                sample["devices"] = []
                for line in result.stdout.splitlines():
                    parts = [part.strip() for part in line.split(",")]
                    item = dict(zip(names, parts, strict=True))
                    for key in names:
                        if key != "uuid":
                            try:
                                item[key] = float(item[key])
                            except ValueError:
                                item[key] = None
                    sample["devices"].append(item)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                sample["unavailable"] = str(error)
            try:
                import psutil

                sample["client_RSS_bytes"] = psutil.Process().memory_info().rss
                sample["host_CPU_pct"] = psutil.cpu_percent()
            except ImportError:
                sample["CPU_RAM_unavailable"] = "psutil is not installed"
            self.samples.append(sample)
            self.done.wait(max(0.01, self.interval - (time.monotonic() - started)))

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.done.set()
        self.thread.join(timeout=10)
        save(
            self.output,
            {
                "schema": "moparse-resource-samples/1",
                "interval_seconds": self.interval,
                "scope": "client process and shared host devices; no per-model attribution",
                "sample_count": len(self.samples),
                "samples": self.samples,
            },
        )


def capture_http(args: argparse.Namespace) -> dict:
    import httpx

    registered = method(args.method)
    data, documents = load_dataset(args.dataset)
    cohort = next((item for item in data["cohorts"] if item["id"] == args.cohort), None)
    if cohort is None or not cohort.get("whole_documents"):
        raise ValueError("run-http requires a registered whole-document cohort")
    selected = set(cohort["document_ids"])
    records = [item for item in documents if item["id"] in selected]
    validation = validate_dataset(args.dataset, require_sources=True)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    if args.output.exists():
        raise ValueError("Choose a new run directory; prior requests are immutable")
    args.output.mkdir(parents=True)
    api_key = args.api_key
    if args.api_key_file:
        api_key = args.api_key_file.read_text().strip()
    elif args.api_key_env:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise ValueError("Requested API key environment variable is unset")
    elif not api_key:
        api_key = os.environ.get("MOPARSE_API_KEY") or os.environ.get("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}
    summary: dict[str, Any] = {
        "schema": "moparse-http-run/1",
        "started_at": utc(),
        "method_id": args.method,
        "method_fingerprint": registered["fingerprint"],
        "dataset": artifact(args.dataset),
        "cohort_id": args.cohort,
        "request_policy": {"scan_policy": "auto", "unit_range": "omitted", "full_document": True},
        "transport": "HTTP /v1/content/parse; 200 Markdown or 202 job polling through persisted result",
        "server_deployment": read(args.deployment) if args.deployment else None,
        "server_deployment_verified": False,
        "method_identity_limit": "Recipe label alone does not establish deployed model identity",
        "cases": [],
    }
    save(args.output / "plan.json", summary)
    with (
        httpx.Client(
            base_url=args.base_url.rstrip("/"),
            headers=headers,
            timeout=args.timeout,
            trust_env=False,
        ) as client,
        ResourceSampler(args.output / "resources.json", args.sample_interval),
    ):
        for document in records:
            source = repo_path(document["source_path"])
            case_dir = args.output / "cases" / document["id"]
            case_dir.mkdir(parents=True)
            request_record = {
                "source": artifact(source),
                "endpoint": "/v1/content/parse",
                "form": {"scan_policy": "auto"},
                "unit_range_omitted": True,
            }
            save(case_dir / "request.json", request_record)
            started = time.perf_counter()
            entry: dict[str, Any] = {
                "id": document["id"],
                "source": document["source_path"],
                "source_sha256": document["sha256"],
                "page_count": document["page_count"],
            }
            try:
                with source.open("rb") as handle:
                    response = client.post(
                        "/v1/content/parse",
                        data={"scan_policy": "auto"},
                        files={"file": (source.name, handle, "application/pdf")},
                    )
                (case_dir / "response-body.bin").write_bytes(response.content)
                save(
                    case_dir / "response.json",
                    {"status": response.status_code, "headers": dict(response.headers)},
                )
                entry.update(
                    submit_http_status=response.status_code,
                    http_status=response.status_code,
                    status="failed",
                )
                if response.status_code not in {200, 202}:
                    raise ValueError(f"Parse submission failed HTTP {response.status_code}")
                markdown, job = capture_final_result(
                    client, response, case_dir, entry, started, args.timeout, args.poll_interval
                )
                entry["assets"] = capture_job_assets_and_events(client, markdown, case_dir, job)
            except (httpx.HTTPError, ValueError) as error:
                entry.update(status="failed", error=str(error))
            entry["full_capture_seconds"] = time.perf_counter() - started
            entry["duration_seconds"] = entry["full_capture_seconds"]
            save(case_dir / "summary.json", entry)
            summary["cases"].append(entry)
    durations = [item["full_capture_seconds"] for item in summary["cases"]]
    summary.update(
        finished_at=utc(),
        status="completed"
        if all(item["status"] == "completed" for item in summary["cases"])
        else "failed",
        performance={
            "scope": "full HTTP upload through saved Markdown and public assets",
            "documents": len(durations),
            "total_seconds": sum(durations),
            "median_document_seconds": statistics.median(durations) if durations else None,
            "p95_document_seconds": percentile(durations, 0.95),
            "per_page_time_limit": "document duration/page count is not measured per-page latency",
        },
    )
    save(args.output / "run.json", summary)
    return {key: summary[key] for key in ("method_id", "cohort_id", "status", "performance")}


def capture_response(directory: Path, name: str, response: Any) -> None:
    (directory / (name + ".bin")).write_bytes(response.content)
    save(
        directory / (name + ".json"),
        {
            "status": response.status_code,
            "headers": dict(response.headers),
            "body_sha256": hashlib.sha256(response.content).hexdigest(),
        },
    )


def capture_final_result(
    client: Any,
    response: Any,
    directory: Path,
    entry: dict,
    started: float,
    timeout: float,
    poll_interval: float,
) -> tuple[str, dict]:
    """Keep the public 200/202 contract intact and verify persisted result bytes."""
    async_submission = response.status_code == 202
    if async_submission:
        job = response.json()
        job_id = job["id"]
    else:
        if "json" in response.headers.get("content-type", ""):
            raise ValueError("Expected public Markdown, received JSON")
        (directory / "result.md").write_bytes(response.content)
        entry["submit_to_saved_MD_seconds"] = time.perf_counter() - started
        job_id = response.headers.get("x-content-id")
        if not job_id:
            location = response.headers.get("location", "")
            match = re.search(r"/v1/content/jobs/([^/]+)/result", location)
            job_id = match[1] if match else None
        job = {"id": job_id, "status": "completed"}
    if not job_id or not SAFE_ID.fullmatch(job_id):
        raise ValueError("Parse response has no safe persisted job ID")
    endpoint = "/v1/content/jobs/" + job_id
    entry["job"] = job_id
    poll_count = 0
    while True:
        if time.perf_counter() - started >= timeout:
            raise ValueError("Full-document job exceeded capture timeout; job remains running")
        state = client.get(
            endpoint, timeout=min(30, max(0.1, timeout - (time.perf_counter() - started)))
        )
        capture_response(directory, f"job-poll-{poll_count:05d}", state)
        if state.status_code != 200:
            raise ValueError(f"Job state failed HTTP {state.status_code}")
        job = state.json()
        poll_count += 1
        if job.get("status") in {"completed", "partial", "failed", "cancelled"}:
            break
        time.sleep(
            min(5, max(0.01, poll_interval), max(0.01, timeout - (time.perf_counter() - started)))
        )
    save(directory / "job.json", job)
    entry.update(
        status=job["status"],
        submit_to_terminal_seconds=time.perf_counter() - started,
        poll_count=poll_count,
    )
    if job["status"] not in {"completed", "partial"}:
        raise ValueError("Job terminated with status " + job["status"])
    persisted = client.get(endpoint + "/result")
    capture_response(directory, "persisted-result-response", persisted)
    if persisted.status_code != 200:
        raise ValueError(f"Persisted final Markdown failed HTTP {persisted.status_code}")
    (directory / "persisted-result.md").write_bytes(persisted.content)
    if async_submission:
        (directory / "result.md").write_bytes(persisted.content)
        entry["submit_to_saved_MD_seconds"] = time.perf_counter() - started
    elif response.content != persisted.content:
        raise ValueError("HTTP200 Markdown differs from persisted /result bytes")
    entry.update(
        final_http_status=200,
        MD_SHA256=digest(directory / "result.md"),
        persisted_MD_SHA256=digest(directory / "persisted-result.md"),
        response_and_persisted_MD_equal=True,
    )
    return persisted.text, job


def capture_job_assets_and_events(
    client: Any, markdown: str, directory: Path, job: dict
) -> list[dict]:
    endpoint = "/v1/content/jobs/" + job["id"]
    events = client.get(endpoint + "/events", timeout=30)
    capture_response(directory, "events", events)
    if events.status_code != 200:
        raise ValueError(f"Job event evidence failed HTTP {events.status_code}")
    listed = client.get(endpoint + "/assets")
    capture_response(directory, "assets-list", listed)
    if listed.status_code != 200:
        raise ValueError(f"Asset listing failed HTTP {listed.status_code}")
    expected = listed.json()
    assets = capture_assets(
        client, markdown, directory, extra_urls=[item["download_url"] for item in expected]
    )
    by_path = {urlsplit(item["public_path"]).path: item for item in assets}
    for item in expected:
        actual = by_path[urlsplit(item["download_url"]).path]
        if actual["sha256"] != item["sha256"]:
            raise ValueError("Public asset bytes disagree with declared SHA256")
    return assets


def capture_assets(
    client: Any, markdown: str, directory: Path, *, extra_urls: list[str] | None = None
) -> list[dict]:
    urls = sorted(
        set(
            re.findall(
                r"(?:https?://[^\s<>()]+)?/v1/content/jobs/[^/\s<>()]+/assets/[^\s<>()]+", markdown
            )
            + (extra_urls or [])
        )
    )
    assets = []
    for index, url in enumerate(urls):
        # Download only the configured service's path, never a document-supplied host.
        path = urlsplit(url).path
        response = client.get(path)
        target = directory / "assets" / f"{index:04d}.bin"
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(response.content)
        assets.append({"public_path": path, "status": response.status_code, **artifact(target)})
        if response.status_code != 200:
            raise ValueError(f"Public asset failed HTTP {response.status_code}: {path}")
    return assets


def score_public(capture: Path, output: Path) -> dict:
    """Call frozen scoring functions without its historical-only output restriction."""
    adapter, frozen = public_scoring_runtime()
    contract_before = frozen_contract()
    by_id = {Path(item["path"]).stem: item for item in frozen.MANIFEST["documents"]}
    rows, unavailable, proofs = {"frozen": [], "public_structure_aware": []}, [], []
    for identifier, source in by_id.items():
        directory = capture / "cases" / identifier
        path = directory / "result.md"
        if not path.is_file():
            unavailable.append(identifier)
            continue
        summary = read(directory / "summary.json") if (directory / "summary.json").is_file() else {}
        if summary.get("status") not in {None, "completed", "partial"}:
            unavailable.append(identifier)
            continue
        before = digest(path)
        if summary.get("MD_SHA256", before) != before:
            raise ValueError(f"Captured result hash mismatch: {identifier}")
        template = {
            "run_id": capture.name,
            "config_id": "formal-registered-method",
            "source": {key: source[key] for key in ("path", "sha256", "page_count")},
            "status": summary.get("status", "completed"),
            "pages": [
                {"page_number": number, "status": "completed", "tables": []}
                for number in range(1, source["page_count"] + 1)
            ],
        }
        final, issues = frozen.reader.parse_final(path.read_text(), template)
        structured = adapter.with_public_metadata(final)
        views = {
            "frozen": frozen.project_public_logical_tables(final),
            "public_structure_aware": adapter.project_metadata_view(structured, frozen),
        }
        for name, view in views.items():
            scores = frozen.score_view(view)
            row = adapter.row_summary(
                identifier,
                {"status": template["status"], **summary},
                source,
                final,
                scores,
                issues,
                before,
            )
            rows[name].append(row)
            save(output / name / identifier / "scores.json", scores)
        if digest(path) != before:
            raise RuntimeError("Scoring changed captured Markdown")
        proofs.append(artifact(path))
    if not rows["frozen"]:
        raise ValueError("No captured regression-502 Markdown found; refusing empty pass")
    if frozen_contract() != contract_before:
        raise RuntimeError("Frozen scorer/gold changed while scoring")
    result = {
        "schema": "moparse-public-evaluation/1",
        "created_at": utc(),
        "suite": "public-209-402",
        "coverage": {
            "expected_documents": 10,
            "scored_documents": len(proofs),
            "missing_document_ids": unavailable,
            "complete": not unavailable,
        },
        "scope": "Selected source assertions; not whole-document semantic accuracy",
        "overlapping_suites_not_summed": True,
        "frozen": adapter.aggregate(rows["frozen"]),
        "public_structure_aware": adapter.aggregate(rows["public_structure_aware"]),
        "source_MD_proofs": proofs,
        "frozen_contract": contract_before,
        "source_path_relocations": frozen.moparse_source_relocations,
        "no_private_sidecars_or_coordinates": True,
        "no_model_or_HTTP_calls": True,
    }
    save(output / "evaluation.json", result)
    return {
        "output": str(output / "evaluation.json"),
        "coverage": result["coverage"],
        "core_numeric": result["public_structure_aware"]["core_numeric"],
        "complete_period": result["public_structure_aware"]["core_period_pass"],
        "supplement402": result["public_structure_aware"]["supplements"]["supplement402"],
    }


def score_content14(capture: Path, output: Path) -> dict:
    """Apply the exact fixed46 and extra4 source predicates to public output."""
    contract_before = frozen_contract()
    folder = FROZEN / "followup/20261017/content-preservation-mineru"
    reader = load_module("moparse_fixed46_reader", folder / "evaluate-docling-component.py")
    # The original extra-state audit derives the repo from HERE.parents[4].
    # Relocate only that path; the frozen source predicate is unchanged.
    reader.HERE = CONTENT
    source_reference = read(folder / "source-reference.json")
    older_reference = read(
        FROZEN
        / "followup/20261017/selected-pipeline-deployment/source-independent-recheck-20261017.json"
    )
    adapter, frozen = public_scoring_runtime()
    _, documents = load_dataset(DEFAULT_DATASET)
    by_id = {item["id"]: item for item in documents}
    suites = read(DEFAULT_DATASET.parent / "annotations/suites.json")["suites"]
    expected = next(item for item in suites if item["id"] == "content14-fixed46")["checks"]
    pages, missing, source_proofs = [], [], []
    for identifier in dict.fromkeys(item["document_id"] for item in expected):
        path = capture / "cases" / identifier / "result.md"
        if not path.is_file():
            missing.append(identifier)
            continue
        source = by_id[identifier]
        template = {
            "run_id": capture.name,
            "config_id": "formal-source-assertions",
            "status": "completed",
            "source": {
                "path": source["source_path"],
                "sha256": source["sha256"],
                "page_count": source["page_count"],
            },
            "pages": [
                {"page_number": number, "status": "completed", "tables": []}
                for number in range(1, source["page_count"] + 1)
            ],
        }
        content = path.read_text()
        final, _ = frozen.reader.parse_final(content, template)
        structured = adapter.with_public_metadata(final)
        view = adapter.project_metadata_view(structured, frozen)
        page_content = reader.evaluator.source_verifier.pages(content)
        for page in view["pages"]:
            number = page["page_number"]
            if not any(
                item["document_id"] == identifier and item["page"] == number for item in expected
            ) and not (identifier == "1225475375" and number == 62):
                continue
            tables = []
            for index, table in enumerate(page["tables"]):
                meta = table.get("public_structure_metadata")
                if not meta:
                    continue
                cells = [
                    {
                        "row": cell["row"],
                        "column": cell["column"],
                        "rowspan": cell.get("row_span", 1),
                        "colspan": cell.get("column_span", 1),
                        "text": cell.get("text", ""),
                        "semantic_markup": cell.get("text", ""),
                        "HTML_line_column": None,
                    }
                    for cell in table.get("cells", [])
                ]
                spans = [
                    [cell["row"], cell["column"], cell["rowspan"], cell["colspan"]]
                    for cell in cells
                    if cell["rowspan"] > 1 or cell["colspan"] > 1
                ]
                tables.append(
                    {
                        "rows": table["rows"],
                        "num_rows": len(table["rows"]),
                        "num_cols": max(map(len, table["rows"]), default=0),
                        "spans": spans,
                        "cells": cells,
                        "block_index": index,
                        "table_index": index,
                        "block_bbox": None,
                        "block_angle": None,
                        "raw_pointer": str(path) + "#" + table["table_id"],
                        "complete_physical_coverage": True,
                        "uncovered_grid_positions": [],
                    }
                )
            actual = page_content.get(number, "")
            blocks = [
                {
                    "type": "evaluation_visible_text_view",
                    "content": reader.evaluator.source_verifier.visible_markdown(actual),
                    "raw_pointer": str(path) + f"#page-{number}",
                }
            ]
            checks = reader.evaluator.model_checks(
                identifier, number, blocks, tables, source_reference, older_reference
            )
            for check in checks:
                check["status"] = "pass" if check["observed_pass"] else "fail"
            pages.append(
                {
                    "source": identifier,
                    "source_page": number,
                    "checks": checks,
                    "_segments": [actual],
                    "_tables": tables,
                }
            )
        source_proofs.append(artifact(path))
    by_key = {
        (page["source"], page["source_page"], check["check"]): check
        for page in pages
        for check in page["checks"]
    }
    checked = [
        {
            "document_id": item["document_id"],
            "page": item["page"],
            **by_key.get(
                (item["document_id"], item["page"], item["id"]),
                {"check": item["id"], "status": "unknown", "reason": "missing source-page output"},
            ),
        }
        for item in expected
    ]
    additional = reader.extra_checks(pages)
    expected_extra = next(item for item in suites if item["id"] == "additional4")["checks"]
    by_check = {item["check"]: item for item in additional}
    additional = [
        by_check.get(
            item["id"],
            {"check": item["id"], "status": "unknown", "reason": "missing source-page output"},
        )
        for item in expected_extra
    ]
    p62_page = next(
        (page for page in pages if page["source"] == "1225475375" and page["source_page"] == 62),
        None,
    )
    extra_p62 = {
        "status": "unknown",
        "reason": "separate p62 page or public table structure unavailable",
    }
    if p62_page and p62_page["_tables"]:
        p62_reference = read(folder / "source-reference-p62.json")
        comparison = reader.evaluator.grid_comparison(
            p62_page["_tables"], p62_reference["rows_raw"], p62_reference["spans"]
        )
        extra_p62 = {
            "status": "pass" if comparison["pass"] else "fail",
            "grid_positions": 99,
            "merged_spans": 9,
            "separate_denominator": True,
            **comparison,
        }
    result = {
        "schema": "moparse-content14-evaluation/1",
        "suite": "content14-fixed46",
        "fixed_checks": checked,
        "fixed46": dict(Counter(item["status"] for item in checked)),
        "additional_checks": additional,
        "additional4": dict(Counter(item["status"] for item in additional)),
        "extra_p62": extra_p62,
        "missing_documents": missing,
        "source_MD_proofs": source_proofs,
        "frozen_contract": contract_before,
        "scope": "Exact fixed source predicates; public table structure and declared source-row maps only",
        "overlapping_denominators_never_summed": True,
        "passed": bool(checked)
        and all(item["status"] == "pass" for item in checked + additional)
        and extra_p62["status"] == "pass",
    }
    if frozen_contract() != contract_before:
        raise RuntimeError("Frozen scoring files changed")
    save(output / "evaluation.json", result)
    return {
        key: result[key]
        for key in ("suite", "fixed46", "additional4", "extra_p62", "missing_documents", "passed")
    }


def score_assertions(capture: Path, annotation: Path, output: Path) -> dict:
    """Portable assertions for newly source-reviewed documents; absent scope is unknown."""
    from benchmark.scorers.html_line_breaks import html_breaks_as_spaces

    source = read(annotation)
    errors = validate_annotations(source)
    if errors:
        raise ValueError("; ".join(errors))
    frozen_contract()
    verifier = load_module(
        "moparse_source_visible",
        FROZEN / "followup/20261017/content-preservation-mineru/verify-content-source.py",
    )
    source_proofs = []
    for document in source.get("source_documents", []):
        if document.get("source_path"):
            original = repo_path(document["source_path"])
            if not original.is_file() or digest(original) != document["sha256"]:
                raise ValueError("Gold source file missing or changed: " + document["id"])
            source_proofs.append(artifact(original))
    checks = []
    for check in source["checks"]:
        path = capture / "cases" / check["document_id"] / "result.md"
        item = {"id": check["id"], "document_id": check["document_id"], "kind": check["kind"]}
        if not path.is_file():
            checks.append({**item, "status": "unknown", "reason": "missing public Markdown"})
            continue
        content = path.read_text()
        if check.get("page"):
            matches = list(re.finditer(r"<!--\s*page:\s*(\d+)\s*-->", content))
            pages = {
                int(match[1]): content[
                    match.end() : matches[i + 1].start() if i + 1 < len(matches) else len(content)
                ]
                for i, match in enumerate(matches)
            }
            if check["page"] not in pages:
                checks.append({**item, "status": "unknown", "reason": "missing source-page scope"})
                continue
            content = pages[check["page"]]
        visible = verifier.visible_markdown(html_breaks_as_spaces(content))
        if check.get("normalize_whitespace"):
            visible = normalize_space(visible)
        if check["kind"] == "text":
            passed = check["expected"] in visible
        elif check["kind"] == "absent_text":
            passed = check["expected"] not in visible
        elif check["kind"] == "ordered_text":
            offset, passed = 0, True
            for text in check["expected"]:
                found = visible.find(text, offset)
                if found < 0:
                    passed = False
                    break
                offset = found + len(text)
        elif check["kind"] == "regex":
            passed = re.search(check["expected"], visible) is not None
        elif check["kind"] in {"table_grid", "table_span"}:
            tables = verifier.public_tables(html_breaks_as_spaces(content), check.get("page"))
            candidates = [
                table
                for table in tables
                if check.get("selector", {}).get("text", "")
                in verifier.visible_markdown("\n".join(" | ".join(row) for row in table["rows"]))
            ]
            if len(candidates) != 1:
                checks.append(
                    {
                        **item,
                        "status": "unknown",
                        "reason": "public table selector absent or ambiguous",
                        "matching_tables": len(candidates),
                    }
                )
                continue
            table = candidates[0]
            if check["kind"] == "table_grid":
                passed = [[normalize_space(cell) for cell in row] for row in table["rows"]] == [
                    [normalize_space(cell) for cell in row] for row in check["expected"]
                ]
            else:
                passed = check["expected"] in table["meta"].get("spans", [])
        else:
            raise ValueError(f"Unsupported assertion kind: {check['kind']}")
        checks.append({**item, "status": "pass" if passed else "fail", "MD_sha256": digest(path)})
    result = {
        "schema": "moparse-assertion-evaluation/1",
        "annotation": artifact(annotation),
        "checks": checks,
        "counts": dict(Counter(check["status"] for check in checks)),
        "passed": bool(checks) and all(check["status"] == "pass" for check in checks),
        "source_proofs": source_proofs,
        "scope": "Only explicitly source-reviewed assertions; table topology uses public-209-402 suite",
    }
    save(output / "evaluation.json", result)
    return result


def register_http(args: argparse.Namespace) -> dict:
    """Turn captured HTTP and independently computed scores into a typed result."""
    registered = method(args.method)
    dataset, documents = load_dataset(args.dataset)
    cohort = next(item for item in dataset["cohorts"] if item["id"] == args.cohort)
    expected = set(cohort["document_ids"])
    by_id = {item["id"]: item for item in documents}
    quality, provenance, received = {}, [artifact(args.dataset), artifact(args.evaluation)], []
    evaluation = read(args.evaluation)
    for identifier in sorted(expected):
        path = args.input / "cases" / identifier / "result.md"
        request = args.input / "cases" / identifier / "request.json"
        summary_path = args.input / "cases" / identifier / "summary.json"
        if not path.is_file():
            raise ValueError("Complete HTTP cohort is missing received Markdown: " + identifier)
        metadata = read(summary_path) if summary_path.exists() else {}
        submit_response = args.input / "cases" / identifier / "response.json"
        if not request.is_file() or not submit_response.is_file():
            raise ValueError(
                "Fresh HTTP registration requires captured request and submit response: "
                + identifier
            )
        if metadata.get("MD_SHA256", digest(path)) != digest(path):
            raise ValueError("Received Markdown differs from capture: " + identifier)
        if metadata.get("status") not in {None, "completed", "partial"}:
            raise ValueError("HTTP case did not complete: " + identifier)
        if (
            metadata.get("source_sha256", by_id[identifier]["sha256"])
            != by_id[identifier]["sha256"]
        ):
            raise ValueError("Received source SHA differs from dataset: " + identifier)
        if request.is_file():
            form = read(request).get("form", {})
            if form.get("scan_policy", "auto") != "auto" or form.get("unit_range"):
                raise ValueError(
                    "Full-document acceptance requires scan_policy=auto and omitted unit_range"
                )
            provenance.append(artifact(request))
        provenance.append(artifact(submit_response))
        received.append(
            {
                "document_id": identifier,
                "source_sha256": by_id[identifier]["sha256"],
                **artifact(path),
            }
        )
    if "public_structure_aware" in evaluation:
        scores = evaluation["public_structure_aware"]
        supplement = scores["supplements"]["supplement402"]["literal"]
        gold = digest(DEFAULT_DATASET.parent / "annotations/core209-source-gold.json")
        supplement_gold = digest(
            DEFAULT_DATASET.parent / "annotations/supplement402-source-gold.json"
        )
        reader = fingerprint(
            {item["path"]: item["sha256"] for item in read(FROZEN / "lock.json")["files"]}
        )
        for name, count in (
            ("core209", scores["core_numeric"].get("pass", 0)),
            ("period209", scores["core_period_pass"]),
        ):
            quality[name] = {
                "pass": count,
                "total": 209,
                "gold_fingerprint": gold,
                "reader_fingerprint": reader,
                "scope_cohort_id": "regression-502",
            }
        for name, field in (
            ("unique_row402", "literal_and_unique_row_pass"),
            ("column_meaning402", "literal_row_and_complete_header_pass"),
        ):
            quality[name] = {
                "pass": supplement[field],
                "total": 402,
                "gold_fingerprint": supplement_gold,
                "reader_fingerprint": reader,
                "scope_cohort_id": "regression-502",
            }
        quality["funding31"] = {
            "pass": scores["funding31"].get("pass", 0),
            "total": 31,
            "gold_fingerprint": digest(
                DEFAULT_DATASET.parent / "annotations/full-selected-source-tables.json"
            ),
            "reader_fingerprint": reader,
            "scope_cohort_id": "regression-502",
        }
    elif evaluation.get("schema") == "moparse-assertion-evaluation/1":
        assertions = evaluation["checks"]
        for kind in dict.fromkeys(item["kind"] for item in assertions):
            items = [item for item in assertions if item["kind"] == kind]
            quality["source_" + kind] = {
                "pass": sum(item["status"] == "pass" for item in items),
                "total": len(items),
                "unknown": sum(item["status"] == "unknown" for item in items),
                "gold_fingerprint": evaluation["annotation"]["sha256"],
                "reader_fingerprint": digest(Path(__file__)),
            }
    else:
        raise ValueError("Unsupported evaluation schema for HTTP registration")
    if args.content_evaluation:
        content = read(args.content_evaluation)
        provenance.append(artifact(args.content_evaluation))
        for metric, total in (("fixed46", 46), ("additional4", 4)):
            quality[metric] = {
                "pass": content[metric].get("pass", 0),
                "total": total,
                "unknown": content[metric].get("unknown", 0),
                "gold_fingerprint": digest(
                    DEFAULT_DATASET.parent / "annotations/content14-source-reference.json"
                ),
                "reader_fingerprint": digest(
                    FROZEN
                    / "followup/20261017/content-preservation-mineru/evaluate-mineru-source.py"
                ),
                "scope_cohort_id": "content14",
            }
    performance = {
        "seconds": None,
        "scope": "full HTTP upload through saved Markdown; measured time unavailable",
        "power_limit_W": args.power_limit,
        "hardware_fingerprint": args.hardware,
        "warmup": args.warmup,
        "own_GPU_peak_MiB": None,
        "shared_GPU_energy_Wh": None,
    }
    run_metadata = args.input / "run.json"
    if run_metadata.is_file():
        run = read(run_metadata)
        provenance.append(artifact(run_metadata))
        performance.update(
            seconds=run["performance"].get("total_seconds"),
            scope=run["performance"].get("scope", performance["scope"]),
        )
    if args.performance:
        timing = read(args.performance)
        provenance.append(artifact(args.performance))
        if "submit_to_saved_MD_s" in timing.get("timing", {}):
            performance.update(
                seconds=timing["timing"]["submit_to_saved_MD_s"].get("total_s"),
                scope="full HTTP upload through saved Markdown; assets timed separately",
            )
        elif "seconds" in timing and "scope" in timing:
            performance.update(timing)
        else:
            raise ValueError("Unrecognized performance schema; provide explicit seconds and scope")
    if args.deployment:
        provenance.append(artifact(args.deployment))
    record = {
        "schema": "moparse-evidence/1",
        "id": args.id,
        "method_id": args.method,
        "cohort_id": args.cohort,
        "origin": "fresh_HTTP",
        "fresh_model_inference": None,
        "new_HTTP_requests": True,
        "output_stage": "public-HTTP-GFM",
        "quality": quality,
        "performance": performance,
        "provenance": provenance,
        "received_MD_proofs": received,
        "registered_method_fingerprint": registered["fingerprint"],
        "observed_recipe_fingerprint": read(args.deployment).get("method_fingerprint")
        if args.deployment
        else None,
        "qualification": {
            "full_HTTP": True,
            "complete_document_capture": True,
            "deployment_identity_observation_supplied": bool(args.deployment),
            "deployment_acceptance": False,
            "note": "Registration records observed evidence; release acceptance additionally requires source, coverage and regression gates",
        },
    }
    errors = validate_evidence(record)
    if errors:
        raise ValueError("; ".join(errors))
    snapshots = []
    for item in record["provenance"]:
        original = repo_path(item["path"])
        target = BENCH / "evidence/artifacts" / (item["sha256"] + original.suffix)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes())
        snapshots.append(
            {**artifact(target), "original_path": item["path"], "snapshot_bytes_unchanged": True}
        )
    record["provenance"] = snapshots
    save(args.output, record)
    return {
        "registered": args.id,
        "quality": quality,
        "performance": performance,
        "output": str(args.output),
    }


def compare(paths: list[Path], *, verify: bool = True) -> dict:
    records, rejected = [], []
    for path in paths:
        record = read(path)
        errors = validate_evidence(record, check_files=verify)
        if errors:
            rejected.append({"path": str(path), "errors": errors})
        else:
            records.append(record)
    quality_groups: dict[str, list] = {}
    timing_groups: dict[str, list] = {}
    for record in records:
        for name, value in record["quality"].items():
            key = fingerprint(
                {
                    "cohort": value.get("scope_cohort_id", record["cohort_id"]),
                    "metric": name,
                    "gold": value["gold_fingerprint"],
                    "reader": value["reader_fingerprint"],
                    "stage": record["output_stage"],
                }
            )[:16]
            quality_groups.setdefault(key, []).append(
                {
                    "evidence_id": record["id"],
                    "method_id": record["method_id"],
                    "metric": name,
                    **value,
                }
            )
        performance = record.get("performance", {})
        if performance.get("seconds") is not None:
            key = fingerprint(
                {
                    "cohort": record["cohort_id"],
                    "scope": performance["scope"],
                    "hardware": performance.get("hardware_fingerprint"),
                    "power_W": performance.get("power_limit_W"),
                    "warmup": performance.get("warmup"),
                    "stage": record["output_stage"],
                }
            )[:16]
            timing_groups.setdefault(key, []).append(
                {"evidence_id": record["id"], "method_id": record["method_id"], **performance}
            )
    return {
        "schema": "moparse-comparison/1",
        "created_at": utc(),
        "quality_groups": quality_groups,
        "timing_groups": timing_groups,
        "rejected": rejected,
        "records": records,
        "selection_rule": "Pass required source-backed quality gates, then choose resource/latency Pareto frontier; no pooled score across overlapping suites",
        "unmeasured_values_remain_null": True,
    }


def render_report(comparison: dict, dataset: Path, output: Path) -> dict:
    data, documents = load_dataset(dataset)
    lines = [
        "# moparse 方法评测",
        "",
        "<!-- Generated by python -m benchmark report. Edit report-notes.md for maintained prose. -->",
        "",
        f"数据版本：`{data['id']}`；{len(documents)} 个输入、{sum(d['page_count'] for d in documents)} 页。",
        "10 份 PDF／502 页及 Office 衍生两页均已用于调试，属于已暴露回归集；不能据此宣称独立泛化精度。",
        f"独立封存测试文件：{sum(d['split'] == 'holdout' for d in documents)}。未标注页不计为正确，重叠验收集分开报告。",
        "",
    ]
    notes = BENCH / "report-notes.md"
    if notes.is_file():
        lines.extend([notes.read_text().strip(), ""])
    chart = BENCH / "assets/concurrency.svg"
    if render_concurrency_chart(comparison["records"], chart):
        lines.extend(
            [
                "## 双并发运行预算",
                "",
                "![相同 220W、同一批 14 难页的耗时及共享 GPU 能耗](assets/concurrency.svg)",
                "双并发为共享资源下选定的默认预算。图中三轮中位数均来自实际同条件试验；权重、FP16、输入、采样及输出预算不变。",
                "",
            ]
        )
    lines.extend(
        [
            "## 质量",
            "",
            "相同分组的原件范围、金标、读取器及输出阶段一致。组件 FULL 视图与公共 HTTP GFM 分开。",
            "",
        ]
    )
    for group, rows in comparison["quality_groups"].items():
        lines.extend(
            [
                f"### {rows[0]['metric']} · {group}",
                "",
                "| 方法 | 通过／固定分母 | 证据 |",
                "| --- | ---: | --- |",
            ]
        )
        for row in rows:
            lines.append(
                f"| `{row['method_id']}` | {row['pass']}／{row['total']} | `{row['evidence_id']}` |"
            )
        lines.append("")
    lines.extend(
        [
            "## 时间与资源",
            "",
            "仅同计时边界、功率、硬件及预热策略分组；缺测项保持为空。整卡能耗包含共享服务，不能视为单模型能耗。",
            "",
        ]
    )
    for group, rows in comparison["timing_groups"].items():
        lines.extend(
            [
                f"### {rows[0]['scope']} · {group}",
                "",
                "| 方法 | 秒 | 功率上限 W | 自身显存峰值 MiB | 整卡能耗 Wh | 证据 |",
                "| --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row in rows:

            def display(key, row=row):
                value = row.get(key)
                return (
                    f"{value:.3f}"
                    if isinstance(value, float)
                    else str(value)
                    if value is not None
                    else ""
                )

            lines.append(
                f"| `{row['method_id']}` | {display('seconds')} | {display('power_limit_W')} | "
                f"{display('own_GPU_peak_MiB')} | {display('shared_GPU_energy_Wh')} | `{row['evidence_id']}` |"
            )
        lines.append("")
    lines.extend(
        ["## 可追溯证据", "", "| 编号 | 来源 | 范围 | 原始记录 |", "| --- | --- | --- | --- |"]
    )
    for record in comparison["records"]:
        first = record["provenance"][0]
        target = Path(first["path"])
        link = str(Path("..") / target) if not target.is_absolute() else str(target)
        label = Path(first.get("original_path", first["path"])).name
        lines.append(
            f"| `{record['id']}` | {record['origin']} | {record['cohort_id']} / {record['output_stage']} | [{label}]({link}) |"
        )
    lines.extend(
        [
            "",
            "历史记录原字节与分数保持不变；新结果另建 run-id。方法名称相同不代表历史输出已使用当前生产出口。",
            "",
        ]
    )
    rendered = "\n".join(lines)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    return {
        "report": str(output),
        "evidence_records": len(comparison["records"]),
        "rejected": comparison["rejected"],
    }


def render_concurrency_chart(records: list[dict], output: Path) -> bool:
    """Simple exportable SVG; every plotted number comes from a locked record."""
    import html

    values = [
        record for record in records if record["id"].startswith("historical-20261018-concurrency-")
    ]
    if len(values) != 4:
        return False
    values.sort(key=lambda item: item["method_id"])
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 550" role="img" aria-labelledby="title desc">',
        '<title id="title">Advanced TXT concurrency: time and shared GPU energy</title>',
        '<desc id="desc">Same fourteen difficult pages, 220 watt limit, three rounds. Concurrency2 is the chosen shared-resource default.</desc>',
        '<rect width="1200" height="550" fill="#fff"/>',
        '<g font-family="sans-serif" fill="#172033">',
        '<text x="35" y="45" font-size="28" font-weight="700">Advanced＋TXT：并发、时间与整卡能耗</text>',
        '<text x="35" y="78" font-size="17" fill="#556177">14 个既有难页 · 220W · 每档三轮中位数 · 蓝色为选定的双并发预算</text>',
    ]
    panels = [
        ("seconds", "原 PDF → FULL Markdown · 秒", 245.0, 45),
        ("shared_GPU_energy_Wh", "同时间窗 GPU 1 整卡能耗 · Wh", 7.0, 650),
    ]
    for field, title, maximum, offset in panels:
        svg.append(
            f'<text x="{offset}" y="125" font-size="20" font-weight="700">{html.escape(title)}</text>'
        )
        for tick in (0, 0.5, 1):
            x = offset + 90 + tick * 395
            svg.append(f'<path d="M{x} 155V425" stroke="#e5eaf1"/>')
            svg.append(
                f'<text x="{x}" y="452" text-anchor="middle" font-size="15" fill="#64748b">{maximum * tick:g}</text>'
            )
        for index, record in enumerate(values):
            concurrency = index + 1
            value = record["performance"].get(field)
            if value is None:
                continue
            y, color = 170 + index * 66, "#2563eb" if concurrency == 2 else "#718096"
            width = value / maximum * 395
            svg.append(
                f'<text x="{offset + 75}" y="{y + 24}" text-anchor="end" font-size="18">{concurrency} 并发</text>'
            )
            svg.append(
                f'<rect x="{offset + 90}" y="{y}" width="{width:.2f}" height="35" rx="3" fill="{color}"/>'
            )
            svg.append(
                f'<text x="{offset + 100 + width:.2f}" y="{y + 24}" font-size="18" fill="{color}">{value:.2f}</text>'
            )
    svg.extend(
        [
            '<text x="35" y="495" font-size="16" fill="#556177">各档自身显存峰值均 3426 MiB；固定验收均 45/46，额外四项均通过。既有 TXT 脚注遗漏尚在。</text>',
            '<text x="35" y="524" font-size="15" fill="#64748b">能耗包含 GLM／TTS 等共享服务及设备基线；这不是模型独占能耗。组件计时不等于完整 HTTP 延迟。</text>',
            "</g></svg>",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(svg) + "\n")
    save(
        output.with_suffix(".sources.json"),
        {
            "schema": "moparse-chart-source/1",
            "records": [
                {"id": record["id"], "fingerprint": fingerprint(record)} for record in values
            ],
            "SVG_sha256": digest(output),
            "no_model_inference": True,
        },
        overwrite=True,
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser(
        "validate", help="Validate dataset, source hashes, annotation locks and split leakage"
    )
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    validate.add_argument("--require-sources", action="store_true")
    add = sub.add_parser(
        "add-documents",
        help="Import new source records and source-only assertions into a new dataset version",
    )
    add.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    add.add_argument("--documents", type=Path, required=True)
    add.add_argument("--annotations", type=Path)
    add.add_argument("--cohort", required=True)
    add.add_argument("--version", required=True)
    reuse = sub.add_parser(
        "import-evidence",
        aliases=["reuse-evidence"],
        help="Verify immutable historical evidence and import a reference",
    )
    reuse.add_argument("source", type=Path)
    reuse.add_argument("--output", required=True, type=Path)
    evaluate = sub.add_parser(
        "evaluate", help="Score captured public Markdown without running a model"
    )
    evaluate.add_argument("--input", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument(
        "--suite", choices=("public-209-402", "content14", "assertions"), default="public-209-402"
    )
    evaluate.add_argument("--annotations", type=Path)
    for name in ("compare", "report"):
        item = sub.add_parser(name)
        item.add_argument("evidence", type=Path, nargs="*")
        item.add_argument(
            "--output", type=Path, default=BENCH / "report.md" if name == "report" else None
        )
        item.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run = sub.add_parser(
        "run-http",
        help="Parse complete registered PDFs and save exact requests/Markdown/assets/metrics",
    )
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--cohort", default="regression-502")
    run.add_argument("--method", required=True)
    run.add_argument("--base-url", default="http://127.0.0.1:12303")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument(
        "--deployment",
        type=Path,
        help="Observed image/model revision identity, without credentials",
    )
    run.add_argument("--api-key", help=argparse.SUPPRESS)
    auth = run.add_mutually_exclusive_group()
    auth.add_argument(
        "--api-key-env",
        help="Read a named environment variable; never save credentials in evidence",
    )
    auth.add_argument(
        "--api-key-file",
        type=Path,
        help="Read a local secret file; never save credentials in evidence",
    )
    run.add_argument("--timeout", type=float, default=3600)
    run.add_argument("--sample-interval", type=float, default=2)
    run.add_argument("--poll-interval", type=float, default=2)
    register = sub.add_parser(
        "register-http", help="Register an actual captured HTTP result and independent score report"
    )
    register.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    register.add_argument("--input", type=Path, required=True)
    register.add_argument("--evaluation", type=Path, required=True)
    register.add_argument("--content-evaluation", type=Path)
    register.add_argument("--performance", type=Path)
    register.add_argument("--deployment", type=Path)
    register.add_argument("--cohort", required=True)
    register.add_argument("--method", required=True)
    register.add_argument("--id", required=True)
    register.add_argument("--power-limit", type=float)
    register.add_argument("--hardware", default="not observed")
    register.add_argument("--warmup", default="not observed")
    register.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_dataset(args.dataset, require_sources=args.require_sources)
            status = 0 if result["valid"] else 1
        elif args.command == "add-documents":
            result = add_documents(args)
            status = 0 if result["valid"] else 1
        elif args.command in {"import-evidence", "reuse-evidence"}:
            result, status = import_evidence(args.source, args.output), 0
        elif args.command == "evaluate":
            if args.output.exists():
                raise ValueError("Choose a new evaluation directory; prior scores are immutable")
            if args.suite == "assertions":
                if args.annotations is None:
                    raise ValueError("--annotations is required for assertions")
                result = score_assertions(args.input, args.annotations, args.output)
                status = 0 if result["passed"] else 1
            elif args.suite == "content14":
                result = score_content14(args.input, args.output)
                status = 0 if result["passed"] else 1
            else:
                result, status = score_public(args.input, args.output), 0
        elif args.command == "register-http":
            result, status = register_http(args), 0
        elif args.command in {"compare", "report"}:
            paths = args.evidence or sorted((BENCH / "evidence").glob("*.json"))
            result = compare(paths)
            if args.command == "report":
                result = render_report(result, args.dataset, args.output)
            elif args.output:
                save(args.output, result)
            status = 1 if result.get("rejected") else 0
        else:
            if args.sample_interval <= 0:
                raise ValueError("Sampling interval must be positive")
            result = capture_http(args)
            status = 0 if result["status"] == "completed" else 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return status
    except (ValueError, FileExistsError, FileNotFoundError, KeyError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
