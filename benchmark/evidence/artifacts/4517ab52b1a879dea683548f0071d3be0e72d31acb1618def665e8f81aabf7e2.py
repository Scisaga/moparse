"""Replay existing fourteen source predictions; no new inference or HTTP."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from app.parsers.mineru_native_remote import render_mineru_page_evidence
from app.services.export_service import ExportService
from app.services.header_verification_service import verify_cached_header_evidence
from app.services.table_service import PageFurnitureFragment, TableCellFragment, TableFragment

ROOT = Path(__file__).resolve().parents[3]
BASE = (
    ROOT
    / "benchmark-results/clean-model-comparison-20261015/followup/20261017/content-preservation-mineru"
)
ADAPTER = ROOT / "benchmark/runs/native-axis-adapter-20261018/adapter-render"
OUTPUT = Path(__file__).parent


def result(doc_id):
    return DocumentParseResult(
        document_id=doc_id,
        filename=f"{doc_id}.pdf",
        mime_type="application/pdf",
        page_count=1,
        processed_pages=0,
        pipeline=ParsePipeline(profile="balanced", primary="cached-only"),
    )


def visible_values(parsed):
    return [
        (
            fragment.fragment_id,
            fragment.rows,
            [
                (cell.row, cell.column, cell.row_span, cell.column_span, cell.text)
                for cell in fragment.cells
            ],
        )
        for fragment in parsed._table_fragments
    ]


def main():
    plans = json.loads((BASE / "mineru-trial/first-pages.json").read_text()) + json.loads(
        (BASE / "mineru-trial/remaining-pages.json").read_text()
    )
    groups = defaultdict(list)
    for plan in plans:
        groups[plan["id"]].append(plan["page"])
    allowed = {field.name for field in dataclasses.fields(TableFragment) if field.init}
    inputs, cases = {}, []
    for doc_id, pages in groups.items():
        native, independent = result(doc_id), result(doc_id)
        for page in sorted(pages):
            key = f"{doc_id}-p{page}"
            native_path = ADAPTER / key / "worker-page.json"
            doc_path = BASE / "docling-target14-component" / key / "table-fragments.json"
            md_path = doc_path.parent / "page.md"
            for path in (native_path, doc_path, md_path):
                inputs[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
            markdown, fragments, _, furniture = render_mineru_page_evidence(
                json.loads(native_path.read_text())
            )
            native.pages.append(PageParseResult(page_number=page, content=markdown))
            native._table_fragments.extend(fragments)
            native._page_furniture.extend(furniture)
            for raw in json.loads(doc_path.read_text()):
                values = {key: value for key, value in raw.items() if key in allowed}
                values["cells"] = [TableCellFragment(**cell) for cell in raw["cells"]]
                values["page_furniture"] = [
                    PageFurnitureFragment(**source) for source in raw["page_furniture"]
                ]
                values["rendered"] = (
                    f"<!-- table-fragment: {raw['fragment_id']} -->\n\n{raw['markdown']}"
                )
                independent._table_fragments.append(TableFragment(**values))
            independent.pages.append(PageParseResult(page_number=page, content=md_path.read_text()))
        before = json.dumps(visible_values(native), ensure_ascii=False)
        page_md_before = [page.content for page in native.pages]
        decisions = verify_cached_header_evidence(native, independent)
        after = json.dumps(visible_values(native), ensure_ascii=False)
        assert before == after, f"native values changed: {doc_id}"
        markdown, _ = ExportService().join_document(
            native.pages,
            preserve_page_breaks=True,
            table_fragments=native._table_fragments,
            merge_cross_page_tables=True,
            page_furniture=native._page_furniture,
        )
        output_path = OUTPUT / "cached-replay" / f"{doc_id}.md"
        output_path.parent.mkdir(exist_ok=True)
        output_path.write_text(markdown + "\n")
        cases.append(
            {
                "id": doc_id,
                "source_pages": pages,
                "tables": len(native._table_fragments),
                "native_value_sha256_before": hashlib.sha256(before.encode()).hexdigest(),
                "native_value_sha256_after": hashlib.sha256(after.encode()).hexdigest(),
                "all_native_values_unchanged": before == after,
                "visible_page_markdown_unchanged": page_md_before
                == [page.content for page in native.pages],
                "table_source_markers": markdown.count("<!-- table-source:"),
                "decisions": [dataclasses.asdict(decision) for decision in decisions],
                "markdown": str(output_path.relative_to(ROOT)),
                "markdown_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            }
        )
    report = {
        "schema": "cached-header-verifier-replay/1",
        "scope": "Existing original14 predictions only; no new CPU/GPU inference, no HTTP, no full-document quality score. Hierarchical pagination needs a third consecutive source page unavailable in the fourteen-page subset, so the normal continuation waits for full-document HTTP verification.",
        "documents": len(cases),
        "source_pages": sum(len(pages) for pages in groups.values()),
        "tables": sum(case["tables"] for case in cases),
        "all_native_values_unchanged": all(case["all_native_values_unchanged"] for case in cases),
        "all_visible_page_markdown_unchanged": all(
            case["visible_page_markdown_unchanged"] for case in cases
        ),
        "inputs_sha256": inputs,
        "cases": cases,
    }
    target = OUTPUT / "cached-replay.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in report.items() if key not in {"inputs_sha256", "cases"}},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
