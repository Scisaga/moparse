"""Stage capture observes visible candidate strings, using synthetic results only."""

from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from moparse_eval.service_stages import capture_stage, materialize_stage


def test_page_snapshot_is_frozen_without_mutating_the_live_candidate():
    result = DocumentParseResult(
        document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
        page_count=1, processed_pages=1,
        pages=[PageParseResult(page_number=1, content="Before source handling.")],
        markdown="Unassembled document.", pipeline=ParsePipeline(profile="balanced", primary="synthetic"),
    )
    snapshot = capture_stage(result, stage="bridge", sample_id="synthetic", pages_only=True)
    assert result.markdown == "Unassembled document."
    assert snapshot["markdown"] == "<!-- page: 1 -->\n\nBefore source handling."
    result.pages[0].content = "After source handling."
    assert "After source" not in snapshot["markdown"]
    snapshot = materialize_stage(snapshot)
    assert snapshot["observation"]["service_output"]["final_markdown"] == snapshot["markdown"]


def test_document_snapshot_uses_the_actual_rendering_instead_of_page_text():
    result = DocumentParseResult(
        document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
        page_count=1, processed_pages=1,
        pages=[PageParseResult(page_number=1, content="Hidden old page text.")],
        markdown="Actually rendered document.",
        pipeline=ParsePipeline(profile="balanced", primary="synthetic"),
    )
    snapshot = materialize_stage(capture_stage(result, stage="exported", sample_id="synthetic"))
    assert snapshot["markdown"] == "Actually rendered document."
    assert "Hidden old" not in str(snapshot["observation"])
