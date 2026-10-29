"""Source/semantic CPU mutations remain owned through repeated cancellation."""

import asyncio
import threading
from pathlib import Path

import pytest

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult, ParsePipeline
from app.models.source import StoredSource
from app.services.pdf_table_evidence_service import PDFTableEvidenceService
from app.services.table_semantics_service import TableSemanticsService
from app.services.table_service import TableCellFragment, TableFragment


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["source", "semantics"])
async def test_repeated_cancel_does_not_release_a_mutating_cpu_worker(kind, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        started.set()
        release.wait(3)
        return []

    result = DocumentParseResult(
        document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
        page_count=1, processed_pages=0, pipeline=ParsePipeline(profile="balanced", primary="synthetic"),
    )
    options = ContentParseOptions()
    if kind == "source":
        monkeypatch.setattr("app.services.pdf_table_evidence_service.inspect_pdf_tables", blocked)
        result._table_fragments = [TableFragment(
            "synthetic-table", 1, 1, (0, 0, 1, 1), 1, 1, [["synthetic"]], [], "", "",
            cells=[TableCellFragment(0, 0, 1, 1, "synthetic")],
        )]
        source = StoredSource(path=Path("/not-opened/synthetic.pdf"), filename="synthetic.pdf",
                              mime_type="application/pdf", size_bytes=0, page_count=1)
        pending = PDFTableEvidenceService(None).apply(result, source, options)
    else:
        monkeypatch.setattr(TableSemanticsService, "_apply_owned", staticmethod(blocked))
        pending = TableSemanticsService().apply(result, options)
    task = asyncio.create_task(pending)
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
