"""Invented Middle JSON, no SDK impostor, files, network, source or media access."""

from copy import deepcopy

import pytest

from app.adapters.native_readers import read_mineru
from app.services.native_content_evidence import NativeContentError, validate_native_content
from tests.unit.test_native_content_status import finish


def text(value, index, kind="text", **extra):
    return {
        "type": kind,
        "index": index,
        "bbox": [0.1, 0.1, 0.8, 0.2],
        "content": [{"type": "text", "content": value, "styles": []}],
        **extra,
    }


def middle(pipeline="P06"):
    blocks = [
        text("Own heading", 0, "doc_title", level=1),
        {
            "type": "list",
            "index": 1,
            "content": [
                text("1、First printed member", 2),
                {"type": "list", "index": 3, "content": [text("a) Nested member", 4)]},
            ],
        },
        {
            "type": "table",
            "index": 5,
            "continues_prev": None,
            "cell_merge": None,
            "content": [
                {"type": "table_caption", "index": 5, "content": "单位：万元"},
                {
                    "type": "table_body",
                    "index": 6,
                    "bbox": [0.1, 0.3, 0.9, 0.6],
                    "content": '<table><tr><th rowspan="2">Item</th><th colspan="2">2027年度</th></tr>'
                    "<tr><th>收入</th><th>成本</th></tr>"
                    "<tr><td>Alpha</td><td>17</td><td>23</td></tr></table>",
                },
                text("注：记录按已印刷期间列示。", 7, "table_footnote"),
            ],
        },
        text("Same literal.", 8),
        text("Same literal.", 9),
        {"type": "equation", "index": 10, "content": r"E=mc^{2}", "bbox": [0.1, 0.7, 0.9, 0.8]},
        {
            "type": "image",
            "index": 11,
            "content": [
                {
                    "type": "image_body",
                    "index": 11,
                    "content": "",
                    "image_path": "declared://figure",
                },
                text("Printed image caption", 12, "image_caption"),
            ],
        },
        text("Failed but available text.", 13, status="failed", error="original local failure"),
    ]
    doc = {
        "schema": "docvortex.middle",
        "schema_version": "2.0",
        "metadata": {"producer": {"name": "mineru", "version": "4.0.12"}},
        "extensions": {
            "mineru": {"tier": "standard" if pipeline == "P06" else "advanced", "parse_mode": "txt"}
        },
        "pages": [{"page_idx": 0, "blocks": blocks}],
        "is_full_document": False,
    }
    return {
        "pipeline": pipeline,
        "config": {"pipeline": pipeline},
        "documents": [doc],
        "pages": [
            {
                "page": 1,
                "branch": "mineru",
                "faithful_markdown": "Forbidden faithful",
                "raw": {
                    "native_document": "#/documents/0",
                    "page_idx": 0,
                    "blocks": [{"type": "text", "content": "Forbidden export projection"}],
                    "content_list": [{"type": "text", "text": "Forbidden content list"}],
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_same_middle_evidence_uses_common_services_preserving_both_identities():
    a, ea = await finish(middle())
    b, eb = await finish(middle("P07"))
    assert a.markdown == b.markdown
    assert a._native_content.artifact.sha256 != b._native_content.artifact.sha256
    assert (
        a.pipeline.primary == "mineru-standard-txt" and b.pipeline.primary == "mineru-advanced-txt"
    )
    assert "Forbidden" not in a.markdown
    assert "1、First printed member" in a.markdown and "a) Nested member" in a.markdown
    assert "E=mc" in a.markdown and "Printed image caption" in a.markdown
    assert ea["semantic_tables"] == eb["semantic_tables"]
    assert "2027年度 / 收入：17" in a.markdown and "2027年度 / 成本：23" in a.markdown
    assert ea["states"]["original_execution"]["status"] == "completed"
    assert ea["states"]["delivery"]["status"] == "partial"
    assert any(i["code"] == "native_execution_incomplete" for i in ea["states"]["impacts"])
    assert any(i["code"] == "native_media_not_delivered" for i in ea["states"]["impacts"])
    items = a._native_content.items
    assert all(i.branch_page == 0 and i.original_page == 81 for i in items)
    assert any(i.details.get("purpose") == "content_list_unbound_derived_view" for i in items)
    table = next(b for b in a._native_page_blocks[1] if b["kind"] == "table_body")
    assert table["type"] == "table" and table["native_block_type"] == "table_body"
    assert all(not i.details["native_independent_ocr_cell"] for i in items if i.kind == "cell")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage",
    [
        "typed_block",
        "content_list",
        "parent",
        "type",
        "locator",
        "page",
        "table",
        "cell",
        "span",
        "media",
        "formula",
        "failure",
        "same_literal",
        "unknown_success",
        "cross_source",
        "duplicate",
        "inline_span",
        "reference",
        "order",
        "container_child",
    ],
)
async def test_independent_input_inventory_rejects_damage_with_original_bytes_unchanged(damage):
    n = middle()
    original = deepcopy(n)
    r, _ = await finish(n)
    blocks = r._native_page_blocks[1]
    table = next(b for b in blocks if b["kind"] == "table_body")
    bridge = r._source_verification["saved_native_bridge"]["pages"][0]
    if damage == "typed_block":
        blocks.pop(0)
    elif damage == "content_list":
        bridge["native_audit_objects"].pop()
    elif damage == "parent":
        bridge["native_containers"].pop(0)
    elif damage == "type":
        blocks[0]["kind"] = "text"
    elif damage == "locator":
        blocks[0]["native_path"] = blocks[1]["native_path"]
    elif damage == "page":
        r.pages.pop()
    elif damage == "table":
        blocks.remove(table)
    elif damage == "cell":
        table["cells"].pop()
    elif damage == "span":
        table["cells"][0]["row_span"] = 1
    elif damage == "media":
        r._source_verification["native_content"]["media"].clear()
        r._source_verification["saved_native_bridge"]["asset_references"].clear()
    elif damage == "formula":
        blocks[:] = [b for b in blocks if b["kind"] != "equation"]
    elif damage == "failure":
        r._source_verification["native_content"]["original_execution"][
            "native_status_evidence"
        ] = []
    elif damage == "same_literal":
        twins = [b for b in blocks if b["text"] == "Same literal."]
        blocks[blocks.index(twins[0])] = deepcopy(twins[1])
    elif damage == "unknown_success":
        r._source_verification["native_content"]["original_execution"]["status"] = "unknown"
    elif damage == "cross_source":
        other, _ = await finish(middle("P07"))
        blocks[0] = deepcopy(other._native_page_blocks[1][0])
    elif damage == "duplicate":
        blocks.append(deepcopy(blocks[0]))
    elif damage == "inline_span":
        blocks[0]["native_content"].clear()
    elif damage == "reference":
        blocks[1]["parent_id"] = None
    elif damage == "order":
        blocks[1]["order_basis"] = "unknown"
    elif damage == "container_child":
        bridge["native_containers"][0]["native_children"].pop()
    with pytest.raises(NativeContentError):
        validate_native_content(r)
    assert n == original


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["page_map", "tier", "mode", "missing_primary", "wrong_schema"])
async def test_invalid_primary_evidence_cannot_be_admitted_by_capability_booleans(damage):
    n = middle()
    if damage == "page_map":
        n["pages"][0]["raw"]["page_idx"] = 8
    elif damage == "tier":
        n["documents"][0]["extensions"]["mineru"]["tier"] = "advanced"
    elif damage == "mode":
        n["documents"][0]["extensions"]["mineru"]["parse_mode"] = "ocr"
    elif damage == "missing_primary":
        n["documents"] = []
    elif damage == "wrong_schema":
        n["documents"][0]["schema"] = "other"
    n["supports_tables"] = n["validated"] = n["saved_native"] = True
    r, e = await finish(n)
    assert "Forbidden" not in r.markdown
    assert e["states"]["readback"]["status"] == "partial"
    assert e["states"]["conversion"]["status"] == e["states"]["delivery"]["status"] == "partial"


@pytest.mark.asyncio
async def test_unknown_order_and_missing_content_do_not_fall_back_to_markdown():
    n = middle()
    b = n["documents"][0]["pages"][0]["blocks"]
    b[0].pop("index")
    b[0].pop("content")
    b[0]["markdown"] = "Forbidden renderer answer"
    r, e = await finish(n)
    assert "Forbidden" not in r.markdown
    assert e["states"]["conversion"]["status"] == "partial"
    assert r._native_page_blocks[1][0]["order_basis"] == "native_array_order_unknown_reading_order"
    assert r._native_page_blocks[1][0]["read_status"] == "unresolved"
    assert r._native_page_blocks[1][0]["native_block_id"] is None


@pytest.mark.asyncio
async def test_verified_indices_sort_display_without_relabeling_array_positions():
    n = middle()
    nodes = n["documents"][0]["pages"][0]["blocks"]
    nodes[0], nodes[1] = nodes[1], nodes[0]
    r, _ = await finish(n)
    assert r._native_page_blocks[1][0]["native_path"].endswith("/blocks/1")
    assert r.markdown.index("Own heading") < r.markdown.index("First printed member")


@pytest.mark.asyncio
async def test_declared_table_continuation_retains_physical_grid_and_unresolved_partition():
    n = middle()
    n["documents"][0]["pages"][0]["blocks"][2]["continues_prev"] = True
    r, e = await finish(n)
    assert len(r._table_fragments) == 1
    assert e["states"]["conversion"]["status"] == "partial"
    assert any(i["code"] == "native_table_continuation_unresolved" for i in e["states"]["impacts"])


def test_research_reading_keeps_its_existing_export_policy():
    raw = {"blocks": [{"type": "text", "content": None, "markdown": "Saved research export"}]}
    assert read_mineru(raw, 1)[0]["text"] == "Saved research export"
    assert read_mineru(raw, 1, primary_only=True)[0]["text"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["header", "unit", "period", "note", "row"])
async def test_mineru_cell_and_qualifier_bindings_cannot_be_replaced_by_printed_values(damage):
    from dataclasses import replace

    from app.services.native_content_evidence import validate_table_relations

    n = middle()
    n["documents"][0]["pages"][0]["blocks"][2]["content"][1]["content"] = (
        "<table><tr><th>Item</th><th>2027年度收入</th><th>2027年度成本</th></tr>"
        "<tr><td>Alpha^1</td><td>17</td><td>23</td></tr></table>"
    )
    n["documents"][0]["pages"][0]["blocks"][2]["content"][2]["content"][0]["content"] = (
        "1 Printed record note."
    )
    r, _ = await finish(n)
    view = r._semantic_tables[0]
    record = view.records[0]
    value = record.values[0]
    if damage == "header":
        value = replace(value, column_headers=record.values[1].column_headers)
    elif damage == "unit":
        assert value.unit_refs
        value = replace(value, unit_refs=())
    elif damage == "period":
        assert value.period_refs
        value = replace(value, period_refs=())
    elif damage == "note":
        assert value.note_refs
        value = replace(value, note_refs=())
    elif damage == "row":
        record = replace(record, source_row=0)
    record = replace(record, values=(value, *record.values[1:]))
    r._semantic_tables[0] = replace(view, records=(record,))
    with pytest.raises(NativeContentError):
        validate_table_relations(r)


@pytest.mark.asyncio
async def test_same_literal_different_native_parent_stays_two_occurrences():
    n = middle()
    nodes = n["documents"][0]["pages"][0]["blocks"]
    nodes[1]["content"][0]["content"][0]["content"] = "Same literal."
    r, e = await finish(n)
    same = [b for b in r._native_page_blocks[1] if b["text"] == "Same literal."]
    assert len(same) == 3 and len({b["id"] for b in same}) == 3
    assert same[0]["parent_id"] and same[1]["parent_id"] is None
    assert len([d for d in e["content_dispositions"] if d["raw_text"] == "Same literal."]) == 3


@pytest.mark.asyncio
async def test_original_failure_unknown_metadata_and_engineering_error_are_distinct(monkeypatch):
    import app.adapters.mineru_native as reader

    n = middle()
    n["documents"][0]["pages"][0]["blocks"] = [text("Readable.", 0)]
    r, e = await finish(
        n,
        {
            "pipeline": "P06",
            "status": "failed",
            "errors": ["real failure"],
            "pages": [{"page": 1, "status": "failed"}],
        },
    )
    assert e["states"]["original_execution"]["status"] == "failed"
    assert (
        e["states"]["conversion"]["status"] == "completed"
        and e["states"]["delivery"]["status"] == "partial"
    )
    r, e = await finish(n, {"pipeline": "P06", "pages": [{"page": 1, "status": "unknown"}]})
    assert e["states"]["original_execution"]["status"] == "unknown"
    r._source_verification["native_content"]["original_execution"]["status"] = "completed"
    with pytest.raises(NativeContentError):
        validate_native_content(r)

    def broken(*args, **kwargs):
        raise RuntimeError("independent injected engineering exception")

    monkeypatch.setattr(reader, "read_middle_page", broken)
    with pytest.raises(RuntimeError, match="engineering"):
        await finish(n)


@pytest.mark.asyncio
async def test_unknown_native_type_retains_literal_and_current_partial():
    n = middle()
    n["documents"][0]["pages"][0]["blocks"] = [
        text("Unsupported but present.", 0, "unfamiliar_type")
    ]
    r, e = await finish(n)
    assert "Unsupported but present." in r.markdown
    assert r._native_page_blocks[1][0]["kind"] == "unfamiliar_type"
    assert e["states"]["conversion"]["status"] == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content", [None, {"opaque": "not text"}, [False], [{"type": "text", "content": False}], ""]
)
async def test_unreadable_primary_regions_cannot_be_forged_as_completed(content):
    n = middle()
    n["documents"][0]["pages"][0]["blocks"] = [{"type": "equation", "index": 0, "content": content}]
    r, e = await finish(n)
    assert e["states"]["readback"]["status"] == "partial"
    assert e["states"]["conversion"]["status"] == "partial"
    b = r._native_page_blocks[1][0]
    assert b["kind"] == "equation" and b["native_content"] == content
    b.pop("read_error", None)
    b["read_status"] = "read"
    with pytest.raises(NativeContentError):
        validate_native_content(r)


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["table_declaration", "container_role"])
async def test_container_and_table_declarations_are_checked_against_immutable_source(damage):
    n = middle()
    n["documents"][0]["pages"][0]["blocks"][2]["continues_prev"] = True
    r, _ = await finish(n)
    if damage == "table_declaration":
        next(b for b in r._native_page_blocks[1] if b["kind"] == "table_body")[
            "native_table_declaration"
        ]["continues_prev"] = False
    else:
        r._source_verification["saved_native_bridge"]["pages"][0]["native_containers"][0][
            "label"
        ] = "other"
    with pytest.raises(NativeContentError):
        validate_native_content(r)


@pytest.mark.asyncio
@pytest.mark.parametrize("node", [{}, {"type": ["opaque"], "content": "Still native text"}, False])
async def test_malformed_native_type_is_not_an_adapter_engineering_exception(node):
    n = middle()
    n["documents"][0]["pages"][0]["blocks"] = [node]
    r, e = await finish(n)
    assert len(r._native_page_blocks[1]) == 1
    assert e["states"]["readback"]["status"] == "partial"
    assert e["states"]["conversion"]["status"] == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["P06", "P07"])
async def test_native_level_is_a_preserved_observation_not_a_document_heading_tree(pipeline):
    n = middle(pipeline)
    n["documents"][0]["pages"][0]["blocks"] = [
        text("Document title", 0, "doc_title", level=5),
        text("Section title", 1, "paragraph_title", level=6),
    ]
    r, e = await finish(n)
    assert "# Document title\n\n## Section title" in r.markdown
    a, b = r._native_page_blocks[1]
    assert a["native_fields"]["level"] == 5 and b["native_fields"]["level"] == 6
    assert a["heading_projection"]["document_hierarchy"] == "not_inferred"
    assert b["heading_projection"]["basis"] == "native_title_role_display_only"
    assert e["states"]["conversion"]["status"] == "completed"
    a["heading_projection"]["level"] = 5
    with pytest.raises(NativeContentError):
        validate_native_content(r)
