"""Invented Paddle JSON/HTML only; no source, media, model or network fixture."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.parse_options import ContentParseOptions
from app.models.source import StoredSource
from app.services.native_content_evidence import (
    NativeContentError,
    validate_native_content,
    validate_table_relations,
)
from app.services.storage_service import StorageService
from moparse_eval.saved_content_closure import close_saved_document
from moparse_eval.service_replay_native import replay_native


def source(pages=1):
    return StoredSource(
        path=Path("/not-mounted/unused.pdf"),
        filename="unused.pdf",
        mime_type="application/pdf",
        size_bytes=12,
        page_count=pages,
    )


def native(pipeline="P03"):
    def region(label, text, ident, group, order):
        return {
            "block_label": label,
            "block_content": text,
            "block_id": ident,
            "group_id": group,
            "block_order": order,
            "block_bbox": [12, 20, 108, 40],
            "block_polygon_points": [[12, 20], [108, 20], [107, 39], [12, 40]],
        }

    blocks = [
        region("doc_title", "Printed title", 0, 1, 1),
        region("text", "- Printed list member", 1, 2, 2),
        region("text", "Same literal.", 2, 7, 3),
        region("text", "Same literal.", 3, 7, 4),
        region(
            "table",
            '<table><tr><th rowspan="2">Item</th><th colspan="2">2025年度</th></tr>'
            "<tr><th>Revenue</th><th>Cost</th></tr><tr><td>Alpha</td><td>17</td><td>17</td></tr></table>",
            4,
            9,
            None,
        ),
        region("vision_footnote", "Printed qualification.", 5, 9, None),
        region("footer_image", "", 6, 10, None),
        region("number", "Printed Company Limited", 7, None, None),
    ]
    return {
        "pipeline": pipeline,
        "config": {"pipeline": pipeline},
        "pages": [
            {
                "page": 1,
                "branch": "paddle",
                "raw": {
                    "res": {
                        "page_index": None,
                        "page_count": None,
                        "width": 120,
                        "height": 200,
                        "model_settings": {"use_doc_preprocessor": False},
                        "parsing_res_list": blocks,
                        "layout_det_res": {
                            "boxes": [
                                {"cls_id": 0, "label": "text", "coordinate": [12, 20, 108, 40]}
                            ]
                        },
                    },
                    "research_region_media": {"6": "assets/declaration-only.png"},
                    "research_region_exports": {"0": "Forbidden alternate export"},
                    "research_media": ["assets/declaration-only.png"],
                },
            }
        ],
    }


def execution(pipeline="P03", status="completed"):
    return {
        "pipeline": pipeline,
        "status": status,
        "pages": [{"page": 1, "branch": "paddle", "status": status}],
    }


async def finish(n=None, observation=None):
    n = n or native()
    return await close_saved_document(
        n,
        source(),
        sample_id="invented",
        declared_source_sha256="a" * 64,
        source_pages=[81],
        original_observation=observation or execution(n["pipeline"]),
    )


@pytest.mark.parametrize("pipeline", ["P03", "P04"])
def test_real_bridge_wiring_enters_the_existing_bound_contract(pipeline):
    result, _ = replay_native(
        native(pipeline), source(), ContentParseOptions(), document_id="invented"
    )
    assert result._native_content is not None
    assert result._native_content.pipeline == pipeline


@pytest.mark.parametrize("pipeline", ["P03", "P04"])
def test_paddle_polygon_group_and_native_order_survive_readback(pipeline):
    n = native(pipeline)
    result, _ = replay_native(n, source(), ContentParseOptions(), document_id="invented")
    block = result._native_page_blocks[1][1]
    raw = n["pages"][0]["raw"]["res"]["parsing_res_list"][1]
    assert block.get("polygon") == raw["block_polygon_points"]
    assert block.get("native_block_order") == 2
    assert block.get("native_group_id") == 2 and block.get("parent_id") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["P03", "P04"])
async def test_paddle_uses_actual_public_finalization_and_preserves_missing_delivery(pipeline):
    result, evidence = await finish(native(pipeline))
    assert result.parse_result.status == "partial"
    assert "# Printed title" in result.markdown
    assert "2025年度 / Revenue：17" in result.markdown
    assert "Printed Company Limited" in result.markdown
    assert result.markdown.count("Same literal.") == 2
    assert result.markdown.count("图片未交付。") == 1
    assert "Forbidden alternate" not in result.markdown
    assert evidence["stages"][-1]["markdown"] == result.markdown


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["P03", "P04"])
@pytest.mark.parametrize(
    "damage",
    [
        "body",
        "title",
        "list",
        "group_member",
        "group_id",
        "block_order",
        "polygon",
        "origin",
        "table",
        "cell",
        "page",
        "media",
        "same_literal",
        "failure",
        "promote_order",
        "bbox",
        "native_id",
        "locator",
        "global_group",
        "display",
    ],
)
async def test_input_unchanged_independent_damage_is_rejected(pipeline, damage):
    n = native(pipeline)
    original = deepcopy(n)
    result, _ = await finish(
        n, execution(pipeline, "failed" if damage == "failure" else "completed")
    )
    blocks = result._native_page_blocks[1]
    if damage in {"body", "title", "group_member", "table"}:
        blocks.pop({"body": 2, "title": 0, "group_member": 3, "table": 4}[damage])
    elif damage == "list":
        blocks[1]["text"] = "- Missing member"
    elif damage == "group_id":
        blocks[2]["native_group_id"] = 99
    elif damage == "block_order":
        blocks[2]["native_block_order"] = 33
    elif damage == "polygon":
        del blocks[2]["polygon"]
    elif damage == "origin":
        blocks[2]["coordinate_origin"] = "BOTTOMLEFT"
    elif damage == "cell":
        blocks[4]["cells"].pop()
    elif damage == "page":
        blocks[2]["branch_page"] = 81
    elif damage == "media":
        result._source_verification["native_content"]["media"].clear()
    elif damage == "same_literal":
        blocks[3] = deepcopy(blocks[2])
    elif damage == "failure":
        result._source_verification["native_content"]["original_execution"]["status"] = "completed"
    elif damage == "promote_order":
        blocks[2]["order_basis"] = "native_reading_tree"
    elif damage == "bbox":
        blocks[2]["bbox"][0] += 1
    elif damage == "native_id":
        blocks[2]["native_block_id"] = 3
    elif damage == "locator":
        blocks[2]["source_locator"]["path"] = blocks[3]["native_path"]
    elif damage == "global_group":
        blocks[2]["group_identity"]["parent_relationship"] = "confirmed"
    else:
        blocks[2]["markdown"] = ""
    with pytest.raises(NativeContentError):
        validate_native_content(result)
    assert n == original


@pytest.mark.asyncio
async def test_configuration_identity_and_semantics_are_separate():
    first, a = await finish(native("P03"))
    second, b = await finish(native("P04"))
    assert first.markdown == second.markdown and a["semantic_tables"] == b["semantic_tables"]
    assert (
        first.pipeline.primary == "paddleocr-vl-1.5"
        and second.pipeline.primary == "paddleocr-vl-1.6"
    )
    assert first._native_content.artifact.sha256 != second._native_content.artifact.sha256
    n = native("P04")
    n["config"]["pipeline"] = "P03"
    with pytest.raises(NativeContentError, match="configuration"):
        await finish(n)


@pytest.mark.asyncio
async def test_pixel_polygon_group_and_html_cell_evidence_are_not_inferred_relations():
    result, _ = await finish()
    b = result._native_page_blocks[1][2]
    assert b["service_bbox"] == (0.1, 0.1, 0.9, 0.2)
    assert b["polygon"][2] == [107, 39] and b["bbox"][2] == 108
    assert b["page"] == 1 and b["branch_page"] is None and b["original_pdf_page"] == 81
    assert b["parent_id"] is None and b["order_basis"] == "native_array_order_unknown_reading_order"
    assert b["group_identity"]["cross_page_relationship"] == "unknown"
    assert all(c.normalized_bbox is None for c in result._table_fragments[0].cells)
    assert all(
        c["source_locator"]["kind"] == "primary_html_projection"
        and c["evidence_locator"]["view"] == "res.parsing_res_list"
        for c in result._table_fragments[0].native_evidence["source_cells"]
    )
    assert (
        result._table_fragments[0].native_evidence["saved_structure"]["format_family"] == "paddle"
    )
    assert all(b.provenance.selected_source is None for b in result.parse_result.units[0].blocks)


@pytest.mark.asyncio
async def test_native_failure_and_generation_truncation_keep_their_original_scope():
    n = native()
    raw = n["pages"][0]["raw"]
    raw["res"]["status"] = "failed"
    raw["research_inference_runtime"] = {
        "generation_observations": {
            "batches": [
                {
                    "generations": [
                        {"status": "completed", "truncated": True, "stop_reason": "limit"}
                    ]
                }
            ]
        }
    }
    result, evidence = await finish(n)
    original = evidence["states"]["original_execution"]
    assert original["status"] == "completed"
    states = original["native_status_evidence"]
    assert any(
        s["metadata"].get("status") == "failed" and s["native_path"].endswith("/res")
        for s in states
    )
    assert any(
        s["metadata"].get("truncated") is True and s["native_path"].endswith("/generations/0")
        for s in states
    )
    assert all("no inferred SDK-region binding" in s["scope"] for s in states)
    states = result._source_verification["native_content"]["original_execution"][
        "native_status_evidence"
    ]
    states[0]["metadata"]["status"] = "completed"
    with pytest.raises(NativeContentError, match="execution"):
        validate_native_content(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["size", "box", "polygon", "preprocessed"])
async def test_missing_or_conflicting_geometry_is_retained_as_unknown(defect):
    n = native()
    r = n["pages"][0]["raw"]["res"]
    b = r["parsing_res_list"][2]
    if defect == "size":
        del r["width"]
    elif defect == "box":
        b["block_bbox"] = [12, 20, 12, 40]
    elif defect == "polygon":
        b["block_polygon_points"] = [[1, 1], [1, 1], [1, 1]]
    else:
        r["model_settings"]["use_doc_preprocessor"] = True
    result, evidence = await finish(n)
    actual = result._native_page_blocks[1][2]
    assert actual["native_payload"] == b and "Same literal." in result.markdown
    if defect == "polygon":
        assert actual["polygon_status"] == "unknown"
    else:
        assert actual["geometry_status"] == "unknown" and actual["service_bbox"] is None
    assert evidence["status"] == "partial"


@pytest.mark.asyncio
async def test_plain_grid_unknown_region_and_incomplete_cells_do_not_get_answers():
    n = native()
    r = n["pages"][0]["raw"]["res"]["parsing_res_list"]
    r[4]["block_content"] = "<table><tr><td>Left prose.</td><td>Right prose.</td></tr></table>"
    r[2]["block_label"] = "new_native_label"
    result, evidence = await finish(n)
    assert result._semantic_tables[0].status == "retained"
    assert "Left prose." in result.markdown and "Right prose." in result.markdown
    assert "Same literal." in result.markdown and evidence["status"] == "partial"


@pytest.mark.asyncio
async def test_wrong_header_from_neighbor_same_value_is_not_accepted():
    result, _ = await finish()
    view = result._semantic_tables[0]
    record = view.records[0]
    value = replace(record.values[0], column_headers=record.values[1].column_headers)
    result._semantic_tables[0] = replace(
        view, records=(replace(record, values=(value, *record.values[1:])),)
    )
    with pytest.raises(NativeContentError, match="header"):
        validate_table_relations(result)


@pytest.mark.asyncio
async def test_actual_stages_and_storage_keep_final_bytes_and_distinct_occurrences(tmp_path):
    result, evidence = await finish()
    assert [s["stage"] for s in evidence["stages"]] == [
        "adapted",
        "source_pages",
        "native_pages",
        "exported",
        "ir",
        "assets",
        "semantic",
        "final",
    ]
    assert all(
        t["producer_edits"]["status"] in {"verified", "verified_no_text_change", "not_applicable"}
        for t in evidence["stage_edit_ledger"]
    )
    states = evidence["states"]
    assert (
        states["original_execution"]["status"] == "completed"
        and states["readback"]["status"] == "read"
    )
    assert states["conversion"]["status"] == "partial" and states["delivery"]["status"] == "partial"
    paths = await StorageService(SimpleNamespace(data_dir=tmp_path)).write_result(
        "invented", result
    )
    assert (
        paths.result.read_bytes()
        == result.markdown.encode()
        == evidence["stages"][-1]["markdown"].encode()
    )
    duplicate = [d for d in evidence["content_dispositions"] if d["raw_text"] == "Same literal."]
    assert len(duplicate) == 2 and duplicate[0]["final_spans"] != duplicate[1]["final_spans"]


@pytest.mark.asyncio
async def test_optional_fields_and_primary_missing_keep_unknown_and_do_not_use_exports():
    n = native()
    r = n["pages"][0]["raw"]["res"]["parsing_res_list"]
    del r[2]["group_id"]
    del r[2]["block_order"]
    del r[2]["block_polygon_points"]
    result, _ = await finish(n)
    b = result._native_page_blocks[1][2]
    assert b["group_identity"] is None and b["polygon_status"] == "not_available"
    del n["pages"][0]["raw"]["res"]["parsing_res_list"]
    result, evidence = await finish(n)
    assert "Forbidden alternate export" not in result.markdown
    assert evidence["status"] == "partial" and result.pages[0].status == "failed"


@pytest.mark.asyncio
async def test_reused_group_ids_across_pages_do_not_create_cross_page_parents_or_merge_text():
    n = native()
    n["pages"].append(deepcopy(n["pages"][0]))
    n["pages"][1]["page"] = 2
    result, _ = await close_saved_document(
        n,
        source(2),
        sample_id="invented",
        declared_source_sha256="a" * 64,
        source_pages=[81, 82],
        original_observation={
            "pipeline": "P03",
            "status": "completed",
            "pages": [{"page": p, "status": "completed"} for p in (1, 2)],
        },
    )
    a, b = result._native_page_blocks[1][2], result._native_page_blocks[2][2]
    assert a["native_group_id"] == b["native_group_id"] == 7
    assert a["group_identity"] != b["group_identity"] and a["parent_id"] is b["parent_id"] is None
    assert a["source_locator"] != b["source_locator"]
    assert result.markdown.count("Same literal.") == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant", ["unwrapped", "gfm", "prose_html", "non_object", "conflicting_order"]
)
async def test_supported_primary_syntax_and_local_unknowns_keep_valid_neighbors(variant):
    n = native()
    raw = n["pages"][0]["raw"]
    r = raw["res"]["parsing_res_list"]
    if variant == "unwrapped":
        n["pages"][0]["raw"] = raw["res"]
    elif variant == "gfm":
        r[4]["block_content"] = "| Item | Revenue |\n| --- | --- |\n| Alpha | 17 |"
    elif variant == "prose_html":
        r[4].update(
            block_label="text",
            block_content="<table><tr><td>First prose.</td><td>Second prose.</td></tr></table>",
        )
    elif variant == "non_object":
        r[3] = "unreadable native region"
    else:
        r[3]["block_order"] = 3
    result, evidence = await finish(n)
    assert "Printed title" in result.markdown and "Printed qualification." in result.markdown
    if variant == "gfm":
        assert "Revenue：17" in result.markdown
        assert (
            result._table_fragments[0].native_evidence["saved_structure"]["cell_identity"]
            == "primary_gfm_cells"
        )
    if variant == "prose_html":
        assert "First prose.\n\nSecond prose." in result.markdown and not result._semantic_tables
    assert evidence["status"] == "partial"
