"""Invented text/JSON only; every test forbids source, media and model work.

The independent assertions cover the actual adapter -> export -> semantic ->
final -> text persistence chain, including unresolved native structures.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.parse_options import ContentParseOptions
from app.models.source import StoredSource
from app.services.storage_service import StorageService
from moparse_eval.p01_native_closure import close_p01_document
from moparse_eval.service_replay_native import _pointer, replay_native


def source(pages=3):
    return StoredSource(
        path=Path("/must-never-open/source.pdf"),
        filename="invented.pdf",
        mime_type="application/pdf",
        size_bytes=1234,
        page_count=pages,
    )


def prov(page, span=(0, 0)):
    return [
        {
            "page_no": page,
            "charspan": list(span),
            "bbox": {"l": 10, "t": 90, "r": 90, "b": 60, "coord_origin": "BOTTOMLEFT"},
        }
    ]


def cell(text, row, col, *, rs=1, cs=1, header=False):
    return {
        "text": text,
        "start_row_offset_idx": row,
        "end_row_offset_idx": row + rs,
        "start_col_offset_idx": col,
        "end_col_offset_idx": col + cs,
        "row_span": rs,
        "col_span": cs,
        "column_header": header,
        "row_header": False,
        "bbox": {"l": 10, "t": 10, "r": 30, "b": 30, "coord_origin": "TOPLEFT"},
    }


def native(*, media=False):
    texts = [
        {"label": "section_header", "level": 1, "text": "Independent heading", "prov": prov(1)},
        {"label": "text", "text": "Ordinary prose 17.25 and a legal statement.", "prov": prov(1)},
        {
            "label": "list_item",
            "text": "Parent item",
            "prov": prov(1),
            "parent": {"$ref": "#/groups/0"},
        },
        {
            "label": "list_item",
            "text": "Nested item",
            "prov": prov(1),
            "parent": {"$ref": "#/groups/1"},
        },
        {"label": "caption", "text": "单位：万元", "prov": prov(2)},
        {"label": "text", "text": "After the table.", "prov": prov(2)},
        {
            "label": "page_footer",
            "text": "Signed 2025-01-17",
            "prov": prov(2),
            "content_layer": "furniture",
        },
    ]
    refs = [0, 1, "group", 4, "table", 5, 6]
    children = [
        {"$ref": "#/groups/0" if i == "group" else "#/tables/0" if i == "table" else f"#/texts/{i}"}
        for i in refs
    ]
    table = {
        "label": "table",
        "prov": prov(2),
        "data": {
            "num_rows": 3,
            "num_cols": 3,
            "table_cells": [
                cell("Item", 0, 0, rs=2, header=True),
                cell("2025年度", 0, 1, cs=2, header=True),
                cell("收入", 1, 1, header=True),
                cell("成本", 1, 2, header=True),
                cell("Alpha", 2, 0),
                cell("1234.50", 2, 1),
                cell("1100.00", 2, 2),
            ],
        },
    }
    document = {
        "body": {"children": children},
        "texts": texts,
        "tables": [table],
        "pictures": [],
        "groups": [
            {"label": "list", "children": [{"$ref": "#/texts/2"}, {"$ref": "#/groups/1"}]},
            {
                "label": "list",
                "parent": {"$ref": "#/groups/0"},
                "children": [{"$ref": "#/texts/3"}],
            },
        ],
        "pages": {str(i): {"size": {"width": 100, "height": 100}} for i in (1, 2)},
    }
    if media:
        document["pictures"].append(
            {
                "label": "picture",
                "prov": prov(2),
                "children": [],
                "image": {"uri": "assets/existing.png"},
            }
        )
        children.insert(-1, {"$ref": "#/pictures/0"})
    return {
        "pipeline": "P01",
        "documents": [
            {
                "document": document,
                "research_group_pages": [1, 2],
                "status": "success",
                "errors": [],
            }
        ],
        "pages": [
            {
                "page": 1,
                "branch": "docling",
                "raw": {"native_document": "#/documents/0", "source_page": 1},
            },
            {
                "page": 2,
                "branch": "docling",
                "raw": {"native_document": "#/documents/0", "source_page": 2},
            },
            {
                "page": 3,
                "branch": "glm",
                "raw": {
                    "json_result": [
                        [
                            {
                                "index": 2,
                                "label": "text",
                                "native_label": "text",
                                "content": "GLM second",
                                "bbox_2d": [10, 10, 900, 200],
                            },
                            {
                                "index": 1,
                                "label": "text",
                                "native_label": "doc_title",
                                "content": "GLM heading",
                                "bbox_2d": [10, 210, 900, 400],
                            },
                        ]
                    ],
                    "raw_json_result": [[{"label": "text", "content": "Forbidden audit answer"}]],
                    "markdown_result": "Forbidden alternate Markdown answer",
                },
            },
        ],
        "page_processing": [
            {
                "page": i,
                "rotation_clockwise": 90 if i == 3 else 0,
                "pdf_original_rotation_clockwise": 0,
                "pdf_effective_rotation_clockwise": 90 if i == 3 else 0,
            }
            for i in (1, 2, 3)
        ],
    }


async def close(n):
    return await close_p01_document(
        n,
        source(),
        sample_id="invented",
        declared_source_sha256="a" * 64,
        source_pages=[101, 102, 103],
    )


@pytest.mark.asyncio
async def test_complete_mixed_document_uses_real_services_and_keeps_exact_values():
    n = native()
    before = copy.deepcopy(n)
    result, evidence = await close(n)
    assert n == before
    assert result.markdown == result.parse_result.renderings.markdown
    assert "# Independent heading" in result.markdown
    assert "- Parent item\n\n    - Nested item" in result.markdown
    assert (
        result.markdown.index("After the table.")
        < result.markdown.index("# GLM heading")
        < result.markdown.index("GLM second")
    )
    assert "2025年度 / 收入：1234.50" in result.markdown
    assert "2025年度 / 成本：1100.00" in result.markdown
    assert "万元" in result.markdown and "Signed 2025-01-17" in result.markdown
    assert (
        "<table" not in result.markdown
        and "| ---" not in result.markdown
        and "<!--" not in result.markdown
    )
    assert "Forbidden" not in result.markdown
    assert evidence["status"] == "completed"
    view = evidence["semantic_tables"][0]
    assert view["status"] == "converted" and view["covered_source_cells"] == 7
    regions = result.parse_result.units[1].regions
    assert [r.reading_order for r in regions] == sorted(r.reading_order for r in regions)
    assert regions[1].region_type == "table"
    assert len(view["records"][0]["values"][0]["column_headers"]) == 2
    assert len(view["records"][0]["values"][0]["unit_refs"]) == 1
    blocks = result._native_page_blocks
    assert blocks[3][0]["native_path"] == "#/pages/2/raw/json_result/0/1"
    assert (
        blocks[3][0]["original_pdf_page"] == 103
        and blocks[3][0]["page_processing"]["rotation_clockwise"] == 90
    )
    assert all(b["native_branch"] == "docling" for b in blocks[1] + blocks[2])
    assert [s["stage"] for s in evidence["stages"]] == [
        "adapted",
        "source_pages",
        "native_pages",
        "exported",
        "assets",
        "semantic",
        "final",
    ]
    for stage in evidence["stages"][1:3]:
        assert stage["applicability"]["applicable"] is False
        assert (
            stage["applicability"]["reason"] == "source_access_disabled_for_saved_json_validation"
        )
    assert evidence["stages"][-1]["markdown"] == result.markdown
    final = evidence["final_text_evidence"]
    from app.services.final_content_service import apply_text_edits

    assert apply_text_edits(final["assembly_markdown"], final["edits"]) == result.markdown
    for edit in final["edits"]:
        a, b = edit["final_span"]
        assert result.markdown[a:b] == edit["replacement"]
    assert evidence["stage_edit_ledger"][-1]["producer_edits"]


@pytest.mark.asyncio
async def test_media_declarations_stay_missing_and_partial_without_asset_files(tmp_path):
    result, evidence = await close(native(media=True))
    assert result.parse_result.status == "partial"
    assert "图片未交付。" in result.markdown
    assert "![" not in result.markdown and result.parse_result.assets == []
    assert evidence["bridge"]["asset_references"][0]["reference"] == "assets/existing.png"
    assert evidence["bridge"]["asset_references"][0]["bytes_accessed"] is False
    assert any(w.code == "saved_native_media_unverified" for w in result.parse_result.warnings)
    storage = StorageService(SimpleNamespace(data_dir=tmp_path))
    paths = await storage.write_result("invented", result)
    assert paths.result.read_bytes() == result.markdown.encode("utf-8")
    assert await storage.read_result("invented") == result.markdown
    assert list(storage.assets_dir("invented").rglob("*.*")) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem",
    [
        "duplicate_page",
        "missing_page",
        "wrong_branch",
        "cross_branch_pointer",
        "local_page_conflict",
        "group_conflict",
        "processing_conflict",
    ],
)
async def test_page_identity_conflicts_stay_failed_and_do_not_borrow_another_branch(problem):
    n = native()
    if problem == "duplicate_page":
        n["pages"].append(copy.deepcopy(n["pages"][0]))
    elif problem == "missing_page":
        n["pages"].pop(0)
    elif problem == "wrong_branch":
        n["pages"][0]["branch"] = "mineru"
    elif problem == "cross_branch_pointer":
        n["pages"][0]["raw"]["native_document"] = "#/pages/2/raw"
    elif problem == "local_page_conflict":
        n["pages"][0]["raw"]["source_page"] = 2
    elif problem == "group_conflict":
        n["documents"][0]["research_group_pages"] = [1, 3]
    else:
        n["page_processing"].append(copy.deepcopy(n["page_processing"][0]))
    result, evidence = await close(n)
    assert result.pages[0].status == "failed"
    assert result.parse_result.status == "partial"
    assert "GLM second" not in (result.pages[0].content or "")
    assert evidence["bridge"]["errors"]


@pytest.mark.asyncio
async def test_explicit_local_docling_page_is_distinct_from_physical_and_original_page():
    n = native()
    d = n["documents"][0]["document"]
    d["pages"]["11"] = d["pages"].pop("1")
    for item in d["texts"]:
        for p in item["prov"]:
            if p["page_no"] == 1:
                p["page_no"] = 11
    n["pages"][0]["raw"]["source_page"] = 11
    result, evidence = await close(n)
    b = result._native_page_blocks[1][0]
    assert b["branch_page"] == 11 and b["page"] == 1 and b["original_pdf_page"] == 101
    assert b["provenance"][0]["native_page_no"] == 11 and b["provenance"][0]["page_no"] == 1
    assert evidence["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect",
    [
        "missing_position",
        "overlapping_cell",
        "unsupported_role",
        "orphan",
        "broken_ref",
        "unknown_origin",
    ],
)
async def test_local_adapter_gaps_preserve_neighbors_and_are_partial(defect):
    n = native()
    d = n["documents"][0]["document"]
    if defect == "missing_position":
        del d["tables"][0]["data"]["table_cells"][5]["start_col_offset_idx"]
    elif defect == "overlapping_cell":
        d["tables"][0]["data"]["table_cells"][5]["start_col_offset_idx"] = 0
    elif defect == "unsupported_role":
        d["texts"][1]["label"] = "new_native_shape"
    elif defect == "orphan":
        d["body"]["children"].pop(1)
    elif defect == "broken_ref":
        d["body"]["children"].append({"$ref": "#/texts/999"})
    else:
        d["texts"][1]["prov"][0]["bbox"]["coord_origin"] = "UNKNOWN"
    result, evidence = await close(n)
    assert "Ordinary prose 17.25" in result.markdown
    assert "After the table." in result.markdown and "Signed 2025-01-17" in result.markdown
    assert evidence["status"] == "partial" and evidence["warnings"]
    if defect in {"missing_position", "overlapping_cell"}:
        assert "1234.50" in result.markdown and "1100.00" in result.markdown


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variant",
    [
        "string",
        "page_wrapper",
        "unknown_region",
        "missing_primary",
        "multiple_pages",
        "index_conflict",
    ],
)
async def test_glm_primary_wrappers_and_failures_do_not_consume_audit_answers(variant):
    n = native()
    raw = n["pages"][2]["raw"]
    if variant == "string":
        raw["json_result"] = json.dumps(raw["json_result"])
    elif variant == "page_wrapper":
        raw["json_result"] = {"pages": [{"page_index": 0, "regions": raw["json_result"][0]}]}
    elif variant == "unknown_region":
        raw["json_result"][0].insert(0, "bad region")
    elif variant == "missing_primary":
        del raw["json_result"]
    elif variant == "multiple_pages":
        raw["json_result"].append([{"content": "Unbound page"}])
    else:
        raw["json_result"][0][0]["index"] = 1
    result, evidence = await close(n)
    assert "Forbidden" not in result.markdown
    if variant in {"string", "page_wrapper"}:
        assert "# GLM heading" in result.markdown and evidence["status"] == "completed"
        b = result._native_page_blocks[3][0]
        assert _pointer(n, b["native_path"])["content"] == "GLM heading"
    else:
        assert evidence["status"] == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,role",
    [
        ("<table><tr><td>First paragraph.</td><td>Second paragraph.</td></tr></table>", "text"),
        ("<table><tr><td>First paragraph.</td><td>Second paragraph.</td></tr></table>", "table"),
        (
            '<table><tr><th scope="col">Item</th><th scope="col">2025年度</th></tr><tr><td>Alpha</td><td>17.50</td></tr></table>',
            "table",
        ),
    ],
)
async def test_primary_html_prose_unknown_grids_and_confirmed_data_are_distinct(content, role):
    n = native()
    n["pages"][2]["raw"]["json_result"] = [
        [{"index": 0, "label": role, "native_label": role, "content": content}]
    ]
    result, evidence = await close(n)
    if role == "text":
        assert "First paragraph.\n\nSecond paragraph." in result.markdown
        assert result._native_page_blocks[3][0]["type"] == "grid_layout"
        assert len(result._semantic_tables) == 1
    elif "First paragraph" in content:
        assert "First paragraph." in result.markdown and "Second paragraph." in result.markdown
        assert result._semantic_tables[-1].status == "retained" and evidence["status"] == "partial"
    else:
        assert "2025年度：17.50" in result.markdown
        assert result._semantic_tables[-1].status == "converted"
        cells = result._table_fragments[-1].native_evidence["source_cells"]
        assert cells[0]["source_locator"]["kind"] == "primary_html_projection"
        assert result._table_fragments[-1].source_kind == "glm"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,errors", [("failed", []), ("partial", []), ("success", ["native conversion issue"])]
)
async def test_native_conversion_errors_are_retained_with_partial_status(status, errors):
    n = native()
    n["documents"][0].update(status=status, errors=errors)
    result, evidence = await close(n)
    assert "Ordinary prose" in result.markdown and evidence["status"] == "partial"
    assert evidence["bridge"]["pages"][0]["source_envelope"]["status"] == status


@pytest.mark.asyncio
async def test_software_exception_is_not_disguised_as_a_native_failure(monkeypatch):
    from moparse_eval import service_p01_adapter

    def bug(*args, **kwargs):
        raise RuntimeError("intentional engineering fault")

    monkeypatch.setattr(service_p01_adapter, "_table", bug)
    with pytest.raises(RuntimeError, match="intentional engineering fault"):
        await close(native())


def test_docling_bottom_origin_and_cell_top_origin_are_normalized_independently():
    result, _ = replay_native(native(), source(), ContentParseOptions(), document_id="invented")
    b = result._native_page_blocks[2][1]
    assert b["kind"] == "table"
    f = result._table_fragments[0]
    assert f.normalized_bbox == (0.1, 0.1, 0.9, 0.4)
    assert f.cells[0].normalized_bbox == (0.1, 0.1, 0.3, 0.3)
    assert f.native_evidence["source_cells"][0]["coordinate_origin"] == "TOPLEFT"


@pytest.mark.asyncio
async def test_explicit_multipage_text_charspans_retain_both_physical_occurrences_once():
    n = native()
    t = n["documents"][0]["document"]["texts"][1]
    t.update(text="First.Second.", prov=[*prov(1, (0, 6)), *prov(2, (6, 13))])
    result, _ = await close(n)
    assert result.markdown.count("First.") == 1 and result.markdown.count("Second.") == 1
    assert any(b.get("text_selection") == [[6, 13]] for b in result._native_page_blocks[2])


def test_half_open_cell_endpoint_does_not_include_the_next_edit_replacement():
    from app.services.final_content_service import map_text_offset

    edits = [{"start": 10, "end": 20, "replacement": "\n\n"}]
    assert map_text_offset(10, edits, end=True) == 10
    assert map_text_offset(10, edits) == 10
    assert map_text_offset(20, edits, end=True) == 12


@pytest.mark.asyncio
async def test_every_nonempty_cell_and_ordinary_block_has_an_actual_final_destination():
    result, evidence = await close(native())
    assert evidence["format_readback_checks"] and all(
        c["equal"] for c in evidence["format_readback_checks"]
    )
    for item in evidence["content_dispositions"]:
        assert item["disposition"] in {"retained", "converted"}
        for cell in item["cells"]:
            assert cell["disposition"] in {"located_in_final", "empty_literal_not_filled"}
            for (a, b), literal in zip(cell["final_spans"], cell["actual_renderings"], strict=True):
                assert result.markdown[a:b] == literal
    transitions = evidence["stage_edit_ledger"]
    assert [e["producer_edits"]["status"] for e in transitions] == [
        "not_applicable",
        "not_applicable",
        "verified",
        "verified_no_text_change",
        "verified",
        "verified",
    ]
    assert "\n  - 2025年度 / 收入：1234.50" in result.markdown
    assert "\n    - 单位：万元" in result.markdown


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["row_count", "column_count", "missing_count", "cell_page"])
async def test_declared_source_grid_or_page_conflicts_never_certify_a_complete_table(defect):
    n = native()
    data = n["documents"][0]["document"]["tables"][0]["data"]
    if defect == "row_count":
        data["num_rows"] = 4
    elif defect == "column_count":
        data["num_cols"] = 4
    elif defect == "missing_count":
        del data["num_rows"]
    else:
        data["table_cells"][5]["page_no"] = 999
    result, evidence = await close(n)
    assert evidence["status"] == "partial"
    assert "1234.50" in result.markdown and "1100.00" in result.markdown
    assert result._semantic_tables == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spans", [[(0, 8), (6, 13)], [(0, 5), (6, 13)], [(0, 6), (6, 12)]])
async def test_incomplete_or_overlapping_multpage_charspans_keep_one_unknown_full_literal(spans):
    n = native()
    t = n["documents"][0]["document"]["texts"][1]
    t.update(text="First.Second.", prov=[*prov(1, spans[0]), *prov(2, spans[1])])
    result, evidence = await close(n)
    assert evidence["status"] == "partial"
    assert result.markdown.count("First.Second.") == 1
    assert any(w.code == "multipage_node_without_complete_text_partition" for w in result.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_provenance", [None, "invalid", [None], [{"page_no": "1"}]])
async def test_malformed_native_provenance_is_a_local_read_gap_and_keeps_literal_neighbors(
    bad_provenance,
):
    n = native()
    n["documents"][0]["document"]["texts"][1]["prov"] = bad_provenance
    result, evidence = await close(n)
    assert "Ordinary prose 17.25" in result.markdown and "After the table." in result.markdown
    assert evidence["status"] == "partial"
    assert "engineering_failure" not in str(evidence["bridge"]["pages"][0]["local_read_errors"])


@pytest.mark.asyncio
async def test_missing_native_page_does_not_discard_a_valid_page_in_its_docling_group():
    n = native()
    n["pages"].pop(0)
    result, evidence = await close(n)
    assert result.pages[0].status == "failed"
    assert "After the table." in result.pages[1].content
    assert "1234.50" in result.markdown and evidence["status"] == "partial"


@pytest.mark.asyncio
async def test_native_caption_and_note_refs_reach_units_and_footnotes_in_nested_output():
    n = native()
    d = n["documents"][0]["document"]
    d["tables"][0]["captions"] = [{"$ref": "#/texts/4"}]
    d["tables"][0]["footnotes"] = [{"$ref": "#/texts/7"}]
    d["tables"][0]["data"]["table_cells"][4]["text"] = "Alpha^1"
    d["texts"].append({"label": "footnote", "text": "1 Printed qualification.", "prov": prov(2)})
    result, evidence = await close(n)
    values = result._semantic_tables[0].records[0].values
    assert all(v.note_refs for v in values)
    assert "\n    - 附注：1 Printed qualification." in result.markdown
    assert result.markdown.count("Printed qualification.") == 3
    context = result._table_fragments[0].native_evidence["context_native_paths"]
    assert any(
        v["native_path"] == "#/documents/0/document/texts/4" and v["text"] == "万元"
        for v in context.values()
    )
    assert evidence["status"] == "completed"


@pytest.mark.asyncio
async def test_mixed_measurement_grid_keeps_unconfirmed_prose_outside_data_records():
    n = native()
    n["pages"][2]["raw"]["json_result"] = [
        [
            {
                "label": "table",
                "content": '<table><tr><th scope="col">Item</th><th scope="col">Revenue</th></tr>'
                "<tr><td>Alpha</td><td>17.50</td></tr>"
                "<tr><td>Independent left prose.</td><td>Independent right prose.</td></tr></table>",
            }
        ]
    ]
    result, evidence = await close(n)
    view = result._semantic_tables[-1]
    assert view.status == "partial" and len(view.records) == 1
    assert "Revenue：17.50" in result.markdown
    assert (
        "Independent left prose." in result.markdown
        and "Independent right prose." in result.markdown
    )
    assert "Independent left prose.：" not in result.markdown
    assert evidence["status"] == "partial"


@pytest.mark.asyncio
async def test_repeated_native_literals_keep_distinct_final_spans():
    n = native()
    d = n["documents"][0]["document"]
    d["texts"][1]["text"] = d["texts"][5]["text"] = "The same literal."
    result, evidence = await close(n)
    occurrences = [
        x for x in evidence["content_dispositions"] if x["raw_text"] == "The same literal."
    ]
    assert len(occurrences) == 2
    assert all(x["disposition"] == "retained" for x in occurrences)
    assert occurrences[0]["final_spans"] != occurrences[1]["final_spans"]
    assert result.markdown.count("The same literal.") == 2


@pytest.mark.asyncio
async def test_source_stage_denial_prevents_every_injected_source_reader():
    from moparse_eval.service_source_policy import apply_source_stages

    r, bridge = replay_native(native(), source(), ContentParseOptions(), document_id="invented")

    def forbidden(*args, **kwargs):
        raise AssertionError("source reader must never be entered")

    observed, _, _ = await apply_source_stages(
        r,
        bridge,
        source(),
        ContentParseOptions(),
        None,
        allow_source_reads=False,
        inspect_pages=forbidden,
        apply_tables=forbidden,
        apply_text=forbidden,
    )
    assert observed == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,markup",
    [
        ("text", "Before ![Printed caption](assets/existing.png) after."),
        ("image", "![Printed caption](assets/existing.png)"),
        ("text", 'Before <img src="assets/existing.png" alt="Printed caption"> after.'),
    ],
)
async def test_inline_media_is_a_missing_delivery_declaration_and_never_an_unverified_embed(
    role, markup
):
    n = native()
    n["pages"][2]["raw"]["json_result"] = [[{"label": role, "content": markup}]]
    result, evidence = await close(n)
    assert evidence["status"] == "partial"
    assert "![" not in result.markdown and "<img" not in result.markdown
    assert "Printed caption" in result.markdown
    assert result.markdown.count("图片未交付。") == 1
    media = evidence["bridge"]["asset_references"]
    assert (
        len(media) == 1
        and media[0]["reference"] == "assets/existing.png"
        and media[0]["bytes_accessed"] is False
    )


@pytest.mark.asyncio
async def test_literal_code_example_is_not_treated_as_a_media_delivery():
    n = native()
    n["pages"][2]["raw"]["json_result"] = [
        [{"label": "text", "content": "`![example](unopened.png)`"}]
    ]
    result, evidence = await close(n)
    assert "`![example](unopened.png)`" in result.markdown
    assert evidence["bridge"]["asset_references"] == [] and evidence["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect", ["extra_page", "invalid_branch", "invalid_local_page", "span_end"]
)
async def test_unknown_source_identities_and_inconsistent_native_spans_are_explicit(defect):
    n = native()
    if defect == "extra_page":
        n["pages"].append({"page": 999, "branch": "glm", "raw": {"json_result": [[]]}})
    elif defect == "invalid_branch":
        n["pages"][0]["branch"] = ["docling"]
    elif defect == "invalid_local_page":
        n["pages"][0]["raw"]["source_page"] = [1]
    else:
        n["documents"][0]["document"]["tables"][0]["data"]["table_cells"][5][
            "end_col_offset_idx"
        ] = 99
    result, evidence = await close(n)
    assert evidence["status"] == "partial" and result.warnings
    assert "After the table." in result.markdown


@pytest.mark.asyncio
async def test_a_glm_image_call_cannot_continue_the_previous_docling_page():
    n = native()
    d = n["documents"][0]["document"]
    d["texts"][6]["label"] = "text"
    d["texts"][6]["text"] = "甲公司的合同"
    n["pages"][2]["raw"]["json_result"] = [
        [{"index": 0, "label": "text", "content": "尚未生效。", "merge_prev": True}]
    ]
    result, evidence = await close(n)
    assert "甲公司的合同尚未生效。" not in result.markdown
    assert "甲公司的合同" in result.markdown and "尚未生效。" in result.markdown
    assert evidence["status"] == "partial"
    assert any(w.code == "final_continuation_incomplete" for w in result.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["row_span", "col_span", "text"])
async def test_missing_native_cell_fields_never_default_to_a_complete_data_relation(field):
    n = native()
    del n["documents"][0]["document"]["tables"][0]["data"]["table_cells"][5][field]
    result, evidence = await close(n)
    assert evidence["status"] == "partial" and result._semantic_tables == []
    assert "1100.00" in result.markdown and "After the table." in result.markdown


@pytest.mark.asyncio
async def test_unknown_source_category_and_unknown_method_are_not_invented_native_or_sparse():
    n = native()
    result, _ = await close(n)
    assert result.parse_result.units[2].diagnostics.source_kind == "unknown"
    assert result.parse_result.units[2].diagnostics.selected_strategy == "glm_table"
    assert result.parse_result.units[2].rotation_degrees == 90
    n["pages"][0]["branch"] = None
    result, _ = await close(n)
    assert result.parse_result.units[0].diagnostics.source_kind == "unknown"
    assert result.parse_result.units[0].diagnostics.selected_strategy == "unknown"
    assert result.parse_result.units[0].diagnostics.quality_verdict == "untrusted"


@pytest.mark.asyncio
async def test_ir_keeps_native_tree_order_when_coordinates_disagree_with_the_tree():
    n = native()
    d = n["documents"][0]["document"]
    d["texts"][0]["prov"][0]["bbox"].update(t=30, b=10)
    d["texts"][1]["prov"][0]["bbox"].update(t=90, b=80)
    result, _ = await close(n)
    assert result.parse_result.units[0].blocks[0].text == "Independent heading"
    assert result.parse_result.units[0].regions[0].block_ids == [
        result.parse_result.units[0].blocks[0].block_id
    ]


@pytest.mark.asyncio
async def test_native_numbered_marker_is_retained_without_inventing_intermediate_numbers():
    n = native()
    d = n["documents"][0]["document"]
    d["texts"][2].update(marker="3.", enumerated=True)
    result, _ = await close(n)
    assert "- &#51;&#46; Parent item" in result.markdown
    assert "3. Parent item" in result.plain_text
    assert "2. Parent item" not in result.plain_text
