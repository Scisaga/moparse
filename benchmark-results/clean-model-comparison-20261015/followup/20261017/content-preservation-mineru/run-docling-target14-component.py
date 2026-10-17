"""Run the candidate-image CPU Docling component on the same fourteen pages.

Each convert receives the unchanged original full-PDF path plus an explicit
one-page page_range. This is a component timing comparison, not another full
HTTP corpus run. The baked application adapter and exporter are used unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import hashlib
import importlib.metadata
import json
import resource
import threading
import time
import traceback
from pathlib import Path
from types import SimpleNamespace


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def snapshot():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "at_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "user_CPU_seconds": usage.ru_utime,
        "system_CPU_seconds": usage.ru_stime,
        "peak_RSS_bytes": usage.ru_maxrss * 1024,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    if (out / "run-manifest.json").exists():
        parser.error("Refusing to overwrite a component run")
    specs = json.loads(args.spec.read_text())
    if len(specs) != 14:
        parser.error("The fixed component comparison must have exactly fourteen input pages")
    manifest = {
        "schema": "mosaicparse-docling-target14-component/1",
        "started_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "status": "initializing",
        "image_id": args.image_id,
        "runner_SHA256": sha(Path(__file__)),
        "input_spec_SHA256": sha(args.spec),
        "component_scope": "same original full PDF bytes plus explicit one-page page_range; no HTTP parsing, routing, GLM/OCR or whole-document throughput claim",
        "CPU_threads": 4,
        "document_concurrency": 1,
        "page_concurrency": 1,
        "device": "cpu",
        "GPU_device_requested": False,
        "GLM_or_SDK_requests": 0,
        "network": "isolated docker --network none",
        "source_PDFs_rewritten": False,
        "pages": [],
        "resources": [],
    }
    stop = threading.Event()
    samples = []

    def monitor():
        while not stop.wait(1):
            samples.append(snapshot())
            save(out / "resource-samples.json", samples)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        import torch

        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        if torch.cuda.is_available():
            raise RuntimeError("This component experiment must expose no CUDA device")
        import pymupdf
        from docling.datamodel.base_models import InputFormat

        from app.models.parse_options import ParseProfile
        from app.models.source import StoredSource
        from app.parsers.docling_standard import DoclingStandardParser
        from app.services.table_service import assemble_logical_tables

        manifest["versions"] = {
            name: importlib.metadata.version(name)
            for name in ["docling", "docling-core", "torch", "pypdfium2", "pymupdf"]
        }
        if manifest["versions"]["docling"] != "2.139.0":
            raise RuntimeError(f"Unexpected Docling package: {manifest['versions']['docling']}")
        manifest["application_sources"] = [
            {"path": str(p.relative_to("/app")), "SHA256": sha(p)}
            for p in sorted(Path("/app/app").rglob("*.py"))
        ]
        manifest["CUDA_available"] = torch.cuda.is_available()
        manifest["torch_num_threads"] = torch.get_num_threads()
        manifest["torch_interop_threads"] = torch.get_num_interop_threads()
        settings = SimpleNamespace(
            parser_workers=1,
            docling_page_workers=1,
            docling_num_threads=4,
            docling_artifacts_path="/models/docling",
            docling_model_download=False,
            docling_device="cpu",
            docling_compile_models=False,
            docling_force_backend_text=False,
            content_timeout_seconds=900,
            max_upload_bytes=200 * 1024 * 1024,
        )
        adapter = DoclingStandardParser(settings, None)
        start = time.perf_counter()
        converter = adapter._build_converter(ParseProfile.BALANCED, False, ["zh", "en"], False)
        option = converter.format_to_options[InputFormat.PDF]
        manifest["actual_pipeline_options"] = option.pipeline_options.model_dump(mode="json")
        manifest["actual_PDF_backend"] = str(option.backend)
        converter.initialize_pipeline(InputFormat.PDF)
        manifest["model_pipeline_initialize_seconds"] = time.perf_counter() - start
        manifest["status"] = "running"
        manifest["CPU_at_start"] = snapshot()
        save(out / "run-manifest.json", manifest)
        grouped_pages, grouped_fragments = {}, {}
        for index, item in enumerate(specs):
            source_path, page_no = Path(item["pdf"]), int(item["page"])
            source_sha = sha(source_path)
            with pymupdf.open(source_path) as source_pdf:
                count = len(source_pdf)
            target = out / f"{item['id']}-p{page_no}"
            target.mkdir(exist_ok=True)
            row = {
                "id": item["id"],
                "page": page_no,
                "run_order_zero_based": index,
                "source_pdf": str(source_path),
                "source_pdf_SHA256": source_sha,
                "source_total_pages": count,
                "convert_page_range_one_based": [page_no, page_no],
                "status": "running",
                "device": "cpu",
                "CPU_threads": 4,
            }
            save(target / "request.json", row)
            source = StoredSource(
                path=source_path,
                filename=source_path.name,
                mime_type="application/pdf",
                size_bytes=source_path.stat().st_size,
                page_count=count,
            )
            before = snapshot()
            started = time.perf_counter()
            conversion = adapter._convert(converter, source, (page_no, page_no))
            row["convert_seconds"] = time.perf_counter() - started
            row["conversion_status"] = str(conversion.status)
            started = time.perf_counter()
            pages, pictures, fragments, _ = asyncio.run(
                adapter._export_conversion(
                    (page_no, page_no),
                    conversion,
                    page_backend=adapter.name,
                    cancel_event=None,
                    progress_callback=None,
                    completed_count=0,
                    total_pages=1,
                    source_path=source_path,
                )
            )
            row["export_seconds"] = time.perf_counter() - started
            if len(pages) != 1 or pages[0].page_number != page_no or pages[0].content is None:
                raise RuntimeError(f"Unexpected source page export: {item}")
            row["convert_plus_export_seconds"] = row["convert_seconds"] + row["export_seconds"]
            after = snapshot()
            row["user_CPU_seconds"] = after["user_CPU_seconds"] - before["user_CPU_seconds"]
            row["system_CPU_seconds"] = after["system_CPU_seconds"] - before["system_CPU_seconds"]
            row["CPU_core_percent"] = (
                100
                * (row["user_CPU_seconds"] + row["system_CPU_seconds"])
                / row["convert_plus_export_seconds"]
            )
            row["peak_process_RSS_bytes"] = after["peak_RSS_bytes"]
            row["table_fragments"] = len(fragments)
            row["picture_candidates"] = len(pictures)
            (target / "page.md").write_text(pages[0].content)
            save(target / "page-result.json", pages[0].model_dump(mode="json"))
            save(target / "raw-docling.json", conversion.document.export_to_dict())
            save(
                target / "table-fragments.json",
                [dataclasses.asdict(fragment) for fragment in fragments],
            )
            row["MD_SHA256"] = sha(target / "page.md")
            row["raw_docling_SHA256"] = sha(target / "raw-docling.json")
            row["status"] = "complete"
            save(target / "request.json", row)
            manifest["pages"].append(row)
            grouped_pages.setdefault(item["id"], []).extend(pages)
            grouped_fragments.setdefault(item["id"], []).extend(fragments)
            save(out / "run-manifest.json", manifest)
            print("PAGE_COMPLETE", json.dumps(row, ensure_ascii=False), flush=True)
        started = time.perf_counter()
        for stem, pages in grouped_pages.items():
            assembled = assemble_logical_tables(pages, grouped_fragments[stem], enabled=True)
            save(out / "selected-page-assembly" / f"{stem}.json", assembled)
        manifest["selected_page_assembly_seconds"] = time.perf_counter() - started
        manifest["convert_seconds_total"] = sum(row["convert_seconds"] for row in manifest["pages"])
        manifest["export_seconds_total"] = sum(row["export_seconds"] for row in manifest["pages"])
        manifest["convert_plus_export_seconds_total"] = sum(
            row["convert_plus_export_seconds"] for row in manifest["pages"]
        )
        manifest["status"] = "complete"
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = repr(exc)
        manifest["traceback"] = traceback.format_exc()
        print(manifest["traceback"], flush=True)
    finally:
        stop.set()
        thread.join(timeout=3)
        samples.append(snapshot())
        save(out / "resource-samples.json", samples)
        manifest["finished_UTC"] = dt.datetime.now(dt.UTC).isoformat()
        manifest["CPU_at_end"] = snapshot()
        save(out / "run-manifest.json", manifest)
    return 0 if manifest["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
