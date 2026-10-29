"""Saved candidate reconstruction uses invented in-memory artifacts only."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict

import pytest

from app.models.content_result import ContentParseResult
from app.models.parse_result import (
    DocumentParseResult,
    PageParseResult,
    ParsePipeline,
    PipelineWarning,
)
from app.models.source_evidence import SourceGlyph, SourceRegionEvidence
from app.models.table_semantics import CellRef, SemanticRecord, SemanticTableView, ValueRelation
from app.services.table_semantics_service import render_semantic_view
from app.services.table_service import (
    PageFurnitureFragment,
    TableCellFragment,
    TableFragment,
    TableSourceView,
    render_gfm_rows,
)
from moparse_eval.service_artifacts import ServiceArtifactError, rebuild_final_result
from moparse_eval.service_observation import build_service_observation


def _json(value):
    return json.loads(json.dumps(value))


def _fragment(name, page):
    rows = [["Item", "Amount"], ["Sales", "100"]]
    markdown = render_gfm_rows(rows)
    fragment = TableFragment(
        name, page, 1, (0.1, 0.1, 0.9, 0.9), 2, 2, rows, [], markdown,
        f"<!-- table-fragment: {name} -->\n\n{markdown}", has_column_header=True,
        cells=[TableCellFragment(row, col, 1, 1, text, is_column_header=row == 0,
                                 is_row_header=row == 1 and col == 0)
               for row, values in enumerate(rows) for col, text in enumerate(values)],
    )
    fragment.page_furniture = [PageFurnitureFragment(
        "furniture", page, "page_number", "2", "2", (0.8, 0.9, 0.9, 1.0),
    )]
    fragment.pdf_evidence = {"opaque_candidate_metadata": {"state": "unknown"}}
    return fragment


def _artifacts():
    converted, retained = _fragment("t1", 1), _fragment("t2", 2)
    row, column, value = CellRef("t1", 1, 0), CellRef("t1", 0, 1), CellRef("t1", 1, 1)
    record = SemanticRecord("t1", 1, (ValueRelation(value, (row,), (column,)),), row)
    semantic = SemanticTableView("s1", ("t1",), "converted", "records", (record,),
                                 source_cell_count=4, covered_source_cells=4)
    source_view = TableSourceView("retained", (retained,), retained.rendered)
    markdown = "# Final title\n\n" + render_semantic_view(semantic, [converted])
    markdown += "\n\n" + source_view.rendered
    warning = PipelineWarning(code="synthetic_warning", message="Saved candidate warning", page_number=2)
    ir = ContentParseResult.model_validate({
        "source": {"content_id": "synthetic", "source_sha256": "0" * 64,
                   "filename": "invented.pdf", "mime_type": "application/pdf", "kind": "pdf",
                   "size_bytes": 123, "unit_count": 2, "page_count": 2},
        "units": [{"unit_id": f"p{i}", "unit_type": "page", "index": i,
                   "status": "warning" if i == 2 else "completed",
                   "renderings": {"markdown": "HIDDEN PRECONVERSION PAGE"},
                   "diagnostics": {"source_kind": "native", "quality_verdict": "trusted",
                                   "selected_strategy": "mineru"}} for i in (1, 2)],
        "renderings": {"markdown": markdown, "plain_text": "Saved final plain text"},
        "runtime": {"profile": "balanced", "primary_backend": "mineru-advanced-txt",
                    "ocr_backend": "glm-sdk-remote", "parser_version": "test",
                    "input_bytes": 123, "duration_ms": 45},
        "links": {key: "unused" for key in ("job", "events", "result", "assets", "bundle")},
    })
    result = DocumentParseResult(
        document_id="synthetic", filename="invented.pdf", mime_type="application/pdf",
        page_count=2, processed_pages=2, markdown=markdown, plain_text=ir.renderings.plain_text,
        pages=[PageParseResult(page_number=i, status="warning" if i == 2 else "completed",
                               warnings=[warning] if i == 2 else []) for i in (1, 2)],
        pipeline=ParsePipeline(profile="balanced", primary="mineru-advanced-txt", ocr="glm-sdk-remote"),
        warnings=[warning], parse_result=ir,
    )
    result._table_fragments = [converted, retained]
    result._semantic_tables = [semantic]
    result._table_views = [source_view]
    result._source_regions = [SourceRegionEvidence(
        "r1", 2, (0.1, 0.2, 0.3, 0.4), "Unknown region", "1" * 64,
        (SourceGlyph(0, "U", (1.0, 2.0, 3.0, 4.0)),), 100.0, 200.0, 90,
        {"candidate": "uninterpreted"}, reason_codes=("synthetic_unknown",),
    )]
    result._source_verification = {"pdf_table_evidence": {"state": "saved_unknown"}}
    evidence = _json({
        "bridge": {"model_calls": 0},
        "source_verification": result._source_verification,
        "table_fragments": [asdict(item) for item in result._table_fragments],
        "table_views": [asdict(item) for item in result._table_views],
        "semantic_tables": [asdict(item) for item in result._semantic_tables],
        "source_regions": [asdict(item) for item in result._source_regions],
        "warnings": [warning.model_dump(mode="json")],
    })
    observation = build_service_observation(result, sample_id="synthetic")
    return markdown, ir.model_dump(mode="json"), evidence, observation


def test_roundtrip_preserves_final_rendering_private_shapes_statuses_and_warnings():
    artifacts = _artifacts()
    before = deepcopy(artifacts)
    restored = rebuild_final_result(*artifacts)
    assert artifacts == before
    assert restored.markdown == artifacts[0]
    assert restored.parse_result.model_dump(mode="json") == artifacts[1]
    for key in ("table_fragments", "table_views", "semantic_tables", "source_regions"):
        assert _json([asdict(item) for item in getattr(restored, "_" + key)]) == artifacts[2][key]
    assert isinstance(restored._table_fragments[0].cells[0], TableCellFragment)
    assert isinstance(restored._semantic_tables[0].records[0].values[0].value, CellRef)
    assert isinstance(restored._source_regions[0].glyphs[0], SourceGlyph)
    assert [str(page.status) for page in restored.pages] == ["completed", "warning"]
    assert restored.pages[1].warnings == restored.warnings
    assert restored.pages[0].content is None and restored.pages[1].content is None
    assert build_service_observation(restored, sample_id="synthetic") == artifacts[3]


def test_restoration_does_not_invoke_table_constructor_or_rerender(monkeypatch):
    artifacts = _artifacts()

    def forbidden(_self):
        raise AssertionError("candidate evidence must not be rendered again")

    monkeypatch.setattr(TableFragment, "__post_init__", forbidden)
    result = rebuild_final_result(*artifacts)
    assert result._table_fragments[0].rendered == artifacts[2]["table_fragments"][0]["rendered"]


@pytest.mark.parametrize("kind", ["ir", "observation"])
def test_inconsistent_final_rendering_is_an_engineering_failure(kind):
    artifacts = list(_artifacts())
    if kind == "ir":
        artifacts[1]["renderings"]["markdown"] += " Extra"
    else:
        artifacts[3]["service_output"]["final_markdown"] += " Extra"
    with pytest.raises(ServiceArtifactError, match="rendering differs"):
        rebuild_final_result(*artifacts)


@pytest.mark.parametrize("kind", ["extra", "missing", "type", "bbox", "semantic_literal"])
def test_unknown_private_shapes_are_rejected_without_default_roles_or_repairs(kind):
    artifacts = _artifacts()
    evidence = artifacts[2]
    if kind == "extra":
        evidence["table_fragments"][0]["cells"][0]["invented_role"] = True
    elif kind == "missing":
        del evidence["table_fragments"][0]["cells"][0]["is_row_header"]
    elif kind == "type":
        evidence["table_fragments"][0]["cells"][0]["is_row_header"] = "false"
    elif kind == "bbox":
        evidence["table_fragments"][0]["normalized_bbox"] = [0.0, 1.0]
    else:
        evidence["semantic_tables"][0]["records"][0]["values"][0]["value_state"] = "guessed"
    with pytest.raises(ServiceArtifactError):
        rebuild_final_result(*artifacts)


@pytest.mark.parametrize("kind", ["duplicate", "missing", "inconsistent", "warning"])
def test_inconsistent_page_and_warning_metadata_cannot_masquerade_as_success(kind):
    artifacts = _artifacts()
    if kind == "duplicate":
        artifacts[3]["service_output"]["page_statuses"][1]["page"] = 1
    elif kind == "missing":
        artifacts[3]["service_output"]["page_statuses"].pop()
    elif kind == "inconsistent":
        artifacts[3]["service_output"]["page_statuses"][1]["status"] = "failed"
    else:
        artifacts[3]["service_output"]["warnings"] = []
    with pytest.raises(ServiceArtifactError):
        rebuild_final_result(*artifacts)


def test_failed_page_and_partial_ir_remain_partial_without_hidden_content_fallback():
    artifacts = _artifacts()
    artifacts[1]["status"] = "partial"
    artifacts[1]["units"][1]["status"] = "failed"
    artifacts[3]["service_output"]["page_statuses"][1]["status"] = "failed"
    result = rebuild_final_result(*artifacts)
    observation = build_service_observation(result, sample_id="synthetic")
    assert result.processed_pages == 1 and observation["status"] == "partial"
    assert observation["service_output"]["page_statuses"][1]["status"] == "failed"
    assert "HIDDEN PRECONVERSION" not in json.dumps(observation)
