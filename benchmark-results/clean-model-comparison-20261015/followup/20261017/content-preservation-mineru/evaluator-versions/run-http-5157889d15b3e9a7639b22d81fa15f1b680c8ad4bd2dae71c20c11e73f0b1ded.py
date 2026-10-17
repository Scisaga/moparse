"""Reuse the sealed HTTP capture/scoring tools without changing old evidence.

Only input identity and the new evidence destination are supplied here. Parsing
requests, resource sampling, final Markdown capture and frozen scoring use the
existing helpers. Office is captured separately from the frozen ten-PDF scores.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "selected-pipeline-deployment"
MANIFEST = HERE / "input-manifest.json"
MODES = {
    "capture": "capture-full-cohort.py",
    "score": "score-full-cohort.py",
    "assets": "audit-source-assets.py",
    "performance": "summarize-performance.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cohort(args):
    manifest = json.loads(MANIFEST.read_text())
    by_id = {item["source"]: item for item in manifest["documents"]}
    if args.cohort == "full10":
        order = manifest["frozen_ten_source_order"]
    elif args.cohort == "all11":
        order = manifest["frozen_ten_source_order"] + ["1206337604"]
    else:
        order = args.cohort.split(",")
    if not order or len(order) != len(set(order)) or any(s not in by_id for s in order):
        raise ValueError("Select full10, all11, or unique registered source IDs")
    result = []
    for source in order:
        item = by_id[source]
        path = Path(item["source_path"])
        if sha(path) != item["sha256"]:
            raise ValueError(f"Input SHA256 changed: {source}")
        result.append({
            "source": source, "source_path": str(path),
            "manifest_path": item["path"], "sha256": item["sha256"],
            "page_count": item["page_count"], "size_bytes": path.stat().st_size,
        })
    return result


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        raise SystemExit("Usage: run-http.py capture|score|assets|performance [helper options]")
    mode = sys.argv.pop(1)
    path = PREVIOUS / MODES[mode]
    spec = importlib.util.spec_from_file_location("content_preservation_http_helper", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.HERE = HERE
    if mode == "capture":
        module.MANIFEST = MANIFEST
        module.cohort = cohort
    elif mode == "assets":
        module.source_file = lambda args, planned: Path(planned["source_path"])
    return module.main()


if __name__ == "__main__":
    sys.exit(main())
