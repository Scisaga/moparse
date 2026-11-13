"""Invented visual JSON and text only; no model, SDK, conftest or media I/O."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.native_content_evidence import (
    NativeContentError,
    validate_ir_handoff,
    validate_native_content,
)
from app.services.storage_service import StorageService
from tests.unit.test_native_content_status import finish


def visual(regions=None, *, fixed=True):
    return {
        "pipeline": "P08",
        "config": {
            "pipeline": "P08",
            "versions": {"mineru-vl-utils": "2.0.7" if fixed else "unknown"},
        },
        "documents": [],
        "pages": [
            {
                "page": 1,
                "branch": "visual",
                "raw": regions
                if regions is not None
                else [
                    {
                        "type": "text",
                        "content": "Printed standalone 17.",
                        "bbox": [0.1, 0.1, 0.8, 0.2],
                        "angle": 0,
                    }
                ],
            }
        ],
        "page_processing": [
            {
                "page": 1,
                "width": 100,
                "height": 200,
                "rotation_clockwise": 0,
                "pdf_original_rotation_clockwise": 270,
            }
        ],
    }


def rich_visual():
    return visual(
        [
            {
                "id": "heading",
                "type": "title",
                "content": "Own title",
                "bbox": [0.1, 0.1, 0.8, 0.2],
                "angle": 0,
            },
            {
                "id": "a",
                "type": "text",
                "content": "Repeated literal.",
                "bbox": [0.1, 0.2, 0.8, 0.3],
                "polygon": [[0.1, 0.2], [0.8, 0.2], [0.8, 0.3]],
                "group_id": 8,
                "parent": "visual-group",
                "merge_prev": False,
            },
            {
                "id": "b",
                "type": "text",
                "content": "Repeated literal.",
                "bbox": [0.1, 0.3, 0.8, 0.4],
            },
            {
                "id": "description",
                "type": "description",
                "content": "A model description.",
                "bbox": [0.1, 0.4, 0.8, 0.5],
            },
            {
                "id": "image",
                "type": "image",
                "content": None,
                "bbox": [0.1, 0.5, 0.8, 0.6],
                "caption": "Declared caption.",
                "description": "Separate description.",
                "research_asset": "declared://unread.png",
            },
            {"id": "group", "type": "list", "content": None, "bbox": [0.1, 0.6, 0.8, 0.7]},
            {
                "id": "failed",
                "type": "text",
                "content": "Retained failed output.",
                "bbox": [0.1, 0.7, 0.8, 0.8],
                "status": "failed",
                "errors": ["original local recognition failure"],
            },
        ]
    )


@pytest.mark.asyncio
async def test_visual_singleton_uses_shared_contract_without_fabricated_character_sources():
    result, evidence = await finish(visual())
    assert [
        evidence["states"][k]["status"]
        for k in ("original_execution", "readback", "conversion", "delivery")
    ] == ["completed", "read", "completed", "completed"]
    block = result._native_page_blocks[1][0]
    assert block["source_locator"]["text_spans"] == ()
    assert block["native_text_span"] is None and block["parent_id"] is None
    component = block["source_components"][0]
    assert (
        component["source_type"] == "native_text"
        and component["origin"] == "visual_model_recognition"
    )
    assert component["charspan"] is None and block["ocr_verification"] == "not_available"
    assert component["source_locator"]["artifact_sha256"] == result._native_content.artifact.sha256
    assert block["geometry_basis"]["coordinate_basis"] == "fixed_sdk_2.0.7_contract"
    assert (
        block["geometry_basis"]["saved_page_processing"]["pdf_original_rotation_clockwise"] == 270
    )
    assert block["geometry_basis"]["original_pdf_transform"] == "unknown"
    assert result.parse_result.units[0].blocks[0].provenance.selected_source is None


@pytest.mark.asyncio
async def test_visual_descriptions_regions_and_media_have_distinct_destinations():
    result, evidence = await finish(rich_visual())
    assert "视觉描述：A model description." in result.markdown
    assert "视觉描述：Separate description." in result.markdown
    assert "原生图题：Declared caption." in result.markdown
    assert "Retained failed output." in result.markdown
    assert result.markdown.count("Repeated literal.") == 2
    assert "图片未交付。" in result.markdown and "declared://" not in result.markdown
    assert result._native_page_blocks[1][5]["type"] == "layout_region"
    assert result._native_page_blocks[1][5]["parent_id"] is None
    assert evidence["states"]["readback"]["status"] == "read"
    assert evidence["states"]["conversion"]["status"] == "partial"
    assert evidence["states"]["delivery"]["status"] == "partial"
    assert evidence["states"]["delivery"]["media"] == {
        "declared": 1,
        "delivered": 0,
        "status": "unverified",
        "media_io": False,
    }
    assert len(evidence["native_destinations"]) == len(result._native_content.items)
    assert any(
        i["code"] == "native_execution_incomplete" and i["category"] == "original_execution"
        for i in evidence["states"]["impacts"]
    )
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage",
    [
        "region",
        "text",
        "description",
        "picture",
        "region_id",
        "native_id",
        "page",
        "original_page",
        "bbox",
        "polygon",
        "origin",
        "group",
        "parent",
        "sequence",
        "array_order",
        "description_as_text",
        "model_as_ocr",
        "same_literal_neighbor",
        "native_failure",
        "charspan",
        "source_component",
        "media_reference",
    ],
)
async def test_immutable_input_catches_independent_visual_handoff_damage(damage):
    native = rich_visual()
    original = deepcopy(native)
    result, _ = await finish(native)
    blocks = result._native_page_blocks[1]
    if damage in {"region", "text", "description", "picture"}:
        del blocks[{"region": 5, "text": 1, "description": 3, "picture": 4}[damage]]
    elif damage == "region_id":
        blocks[1]["id"] = "#/pages/0/raw/2"
    elif damage == "native_id":
        blocks[1]["native_id"] = "b"
    elif damage == "page":
        blocks[1]["page"] = 2
    elif damage == "original_page":
        blocks[1]["original_pdf_page"] = 9
    elif damage == "bbox":
        blocks[1]["bbox"][0] = 0.09
    elif damage == "polygon":
        blocks[1]["polygon"][0][0] = 0.09
    elif damage == "origin":
        blocks[1]["coordinate_origin"] = "BOTTOMLEFT"
    elif damage in {"group", "parent"}:
        blocks[1]["native_relations"].pop("group_id" if damage == "group" else "parent")
    elif damage == "sequence":
        blocks[1]["native_sequence"] = [1, 99]
    elif damage == "array_order":
        blocks[1], blocks[2] = blocks[2], blocks[1]
    elif damage == "description_as_text":
        blocks[3]["source_components"][0]["source_type"] = "native_text"
    elif damage == "model_as_ocr":
        blocks[1]["source_components"][0]["origin"] = "ocr"
        blocks[1]["ocr_verification"] = "verified"
    elif damage == "same_literal_neighbor":
        blocks[1]["source_locator"] = deepcopy(blocks[2]["source_locator"])
    elif damage == "native_failure":
        blocks[6]["status"] = "completed"
        blocks[6]["native_execution_state"] = {"status": "completed", "errors": []}
    elif damage == "charspan":
        blocks[1]["charspan"] = [0, 17]
    elif damage == "source_component":
        blocks[4]["source_components"].pop()
    else:
        blocks[4]["asset"] = "declared://another.png"
    with pytest.raises(NativeContentError):
        validate_native_content(result)
    assert native == original


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["clear", "reference", "delivery"])
async def test_visual_media_declarations_are_not_asset_delivery(damage):
    result, _ = await finish(rich_visual())
    state = result._source_verification["native_content"]
    if damage == "clear":
        state["media"].clear()
    elif damage == "reference":
        result._native_page_blocks[1][4]["native_media_declaration"]["research_asset"] = "other"
    else:
        state["media"][0]["status"] = "ready"
    with pytest.raises(NativeContentError):
        validate_native_content(result)


@pytest.mark.asyncio
async def test_unknown_coordinate_units_are_not_deduced_from_number_ranges():
    native = visual(fixed=False)
    result, evidence = await finish(native)
    block = result._native_page_blocks[1][0]
    assert block["bbox"] == [0.1, 0.1, 0.8, 0.2] and block["coordinate_system"] == "unknown"
    assert block["coordinate_origin"] == "UNKNOWN" and block["service_bbox"] is None
    assert evidence["states"]["delivery"]["status"] == "completed"
    assert all(i["warning_only"] for i in evidence["states"]["impacts"])


@pytest.mark.asyncio
async def test_visual_array_or_bbox_does_not_create_reading_order_parent_or_continuation():
    native = visual(
        [
            {"type": "text", "content": "First.", "bbox": [0.5, 0.6, 0.9, 0.7]},
            {
                "type": "text",
                "content": "Second.",
                "bbox": [0.1, 0.1, 0.3, 0.2],
                "merge_prev": True,
            },
        ]
    )
    result, evidence = await finish(native)
    assert "First.\n\nSecond." in result.markdown
    assert not result._final_text_evidence["joined_paragraphs"]
    assert result._final_text_evidence["unresolved_continuations"]
    assert all(b["parent_id"] is None for b in result._native_page_blocks[1])
    assert evidence["states"]["conversion"]["status"] == "partial"


@pytest.mark.asyncio
async def test_layout_only_visual_region_is_preserved_without_invented_body():
    native = visual([{"type": "list", "content": None, "bbox": [0.1, 0.1, 0.8, 0.8]}])
    result, evidence = await finish(native)
    assert result.markdown == ""
    assert result.parse_result.units[0].blocks[0].block_type == "unknown"
    assert evidence["states"]["delivery"]["status"] == "completed"
    assert evidence["content_dispositions"][0]["disposition"] == "preserved_in_audit"


@pytest.mark.asyncio
async def test_visual_table_uses_own_html_cells_in_shared_semantics():
    native = visual(
        [
            {
                "type": "table",
                "bbox": [0.1, 0.1, 0.8, 0.8],
                "content": "<table><tr><th>Item</th><th>Revenue</th></tr><tr><td>Alpha</td><td>17</td></tr></table>",
            }
        ]
    )
    result, evidence = await finish(native)
    assert evidence["states"]["delivery"]["status"] == "completed"
    assert evidence["semantic_tables"][0]["status"] == "converted"
    assert len(evidence["table_fragments"][0]["cells"]) == 4
    assert "Revenue：17" in result.markdown
    assert (
        evidence["table_fragments"][0]["native_evidence"]["source_binding"]["view"]
        == "ContentBlock[]"
    )
    assert all("charspan" not in c for c in result._native_page_blocks[1][0]["cells"])


@pytest.mark.asyncio
async def test_visual_storage_and_real_final_stage_agree_as_utf8(tmp_path):
    result, evidence = await finish(rich_visual())
    stored = await StorageService(SimpleNamespace(data_dir=tmp_path)).write_result(
        "invented", result
    )
    assert stored.result.read_bytes() == result.markdown.encode("utf-8")
    assert (
        result.parse_result.renderings.markdown
        == result.markdown
        == evidence["stages"][-1]["markdown"]
    )
    assert not list(tmp_path.rglob("*.png"))


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [None, 17, {"content": "wrong shape"}])
async def test_local_malformed_visual_regions_keep_valid_neighbors(malformed):
    native = visual(
        [{"type": "text", "content": "Left."}, malformed, {"type": "text", "content": "Right."}]
    )
    result, evidence = await finish(native)
    assert "Left." in result.markdown and "Right." in result.markdown
    assert evidence["states"]["readback"]["status"] == "partial"
    assert evidence["states"]["delivery"]["status"] == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "native_state",
    [
        {"status": "failed", "errors": ["native failure"]},
        {"timed_out": True},
        {"truncated": True},
        {"processed": False},
        {"research_export_errors": [{"stage": "faithful_export", "message": "failure"}]},
        {"warnings": [{"message": "native informational warning"}]},
    ],
)
async def test_visual_native_execution_failure_and_warning_keep_their_own_responsibility(
    native_state,
):
    native = visual()
    native["pages"][0]["raw"][0].update(native_state)
    result, evidence = await finish(native)
    assert evidence["states"]["readback"]["status"] == "read"
    assert evidence["states"]["conversion"]["status"] == "completed"
    info = "warnings" in native_state
    assert evidence["states"]["delivery"]["status"] == ("completed" if info else "partial")
    assert result._native_page_blocks[1][0]["native_execution_state"] == native_state
    if info:
        assert any(w["code"] == "native_execution_warning" for w in evidence["warnings"])
        assert all(i["warning_only"] for i in evidence["states"]["impacts"])
    else:
        assert any(
            i["category"] == "original_execution"
            for i in evidence["states"]["delivery"]["partial_reasons"]
        )


@pytest.mark.asyncio
async def test_region_label_and_description_are_never_promoted_to_printed_text():
    native = visual(
        [
            {"type": "label", "content": "Detected region label."},
            {"type": "image", "content": "Generated visual description."},
        ]
    )
    result, _ = await finish(native)
    assert "区域标签：Detected region label." in result.markdown
    assert "视觉描述：Generated visual description." in result.markdown
    assert [b["source_components"][0]["source_type"] for b in result._native_page_blocks[1]] == [
        "native_region_label",
        "model_description",
    ]
    assert 'native_region_label' in result.parse_result.units[0].blocks[0].provenance.reason_codes
    assert 'model_description' in result.parse_result.units[0].blocks[1].provenance.reason_codes


@pytest.mark.asyncio
async def test_description_syntax_does_not_become_recognized_table_or_asset():
    native = visual(
        [
            {
                "type": "description",
                "content": "<table><tr><td>Described</td></tr> ![imagined](unread.png)",
            }
        ]
    )
    result, evidence = await finish(native)
    block = result._native_page_blocks[1][0]
    assert block["text_format"] == "plain" and not block.get("cells")
    assert block["read_status"] == "read"
    assert "视觉描述：" in result.markdown
    assert not evidence["table_fragments"] and not evidence["states"]["media"]
    assert evidence["states"]["delivery"]["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['origin', 'geometry', 'region', 'description', 'page'])
async def test_visual_source_category_and_geometry_survive_the_actual_ir_handoff(damage):
    result, _ = await finish(rich_visual())
    block = result.parse_result.units[0].blocks[3]
    if damage == 'origin':
        block.provenance.reason_codes = []
    elif damage == 'geometry':
        block.bbox = None
    elif damage == 'region':
        block.region_id = 'another_region'
    elif damage == 'description':
        block.block_type = 'text'
    else:
        block.unit_id = 'p2'
    with pytest.raises(NativeContentError):
        validate_ir_handoff(result)
