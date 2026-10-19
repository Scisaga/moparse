"""Relation and literal-rendering invariants, independent of parser accuracy."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.models import ContentParseOptions, DocumentParseResult, PageParseResult, ParsePipeline
from app.models.content_result import (
    ContentLinks,
    ContentParseResult,
    ContentRenderings,
    ContentSource,
    ParseRuntime,
    SourceKind,
)
from app.models.table_semantics import CellRef, SemanticRecord, SemanticTableView, ValueRelation
from app.services.export_service import ExportService
from app.services.table_semantics_service import (
    TableSemanticsService,
    bind_table_view,
    render_semantic_view,
)
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    render_gfm_rows,
)


def table(rows: list[list[str]], scopes=(), *, name="t1") -> TableFragment:
    md = render_gfm_rows(rows)
    cells = [
        TableCellFragment(r, c, 1, 1, text)
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    f = TableFragment(
        name,
        1,
        1,
        (0.1, 0.1, 0.9, 0.9),
        len(rows),
        len(rows[0]),
        deepcopy(rows),
        [],
        md,
        f"<!-- table-fragment: {name} -->\n\n{md}",
        cells=cells,
    )
    f.pdf_evidence = {
        "bound": True,
        "source_cells": [
            {
                "row": c.row,
                "column": c.column,
                "row_span": c.row_span,
                "column_span": c.column_span,
                "text": c.text,
                "shaded": c.row in {s[0] for s in scopes},
            }
            for c in cells
        ],
    }
    f.source_header_scopes = [
        {"header_rows": [start], "body_rows": list(range(start + 1, end)), "complete": True}
        for start, end in scopes
    ]
    return f


def test_internal_header_switch_uses_its_own_period_and_preserves_literals():
    f = table(
        [
            ["项目", "本报告期末", "上年末"],
            ["A", "0", "—"],
            ["", "本报告期", "上年同期"],
            ["B", "-1.20%", ""],
        ],
        [(0, 2), (2, 4)],
    )
    before = deepcopy(f.rows)
    view = bind_table_view("t1", [f], [f])
    assert view.status == "converted"
    a, b = view.records
    assert a.values[0].period_refs == (CellRef("t1", 0, 1),)
    assert b.values[0].column_headers == (CellRef("t1", 2, 1),)
    assert b.values[1].value_state == "source_blank"
    md = render_semantic_view(view, [f])
    assert "本报告期末：0" in md and "上年末：—" in md
    assert "B；本报告期：-1.20%" in md and "上年同期：（原表留空）" in md
    assert f.rows == before and "| ---" not in md
    assert "table-structure" not in md and "version=" not in md
    assert view.policy == "source-scoped-relations"


def test_mixed_field_rows_and_record_band_cover_every_source_cell():
    f = table(
        [
            ["名称", "甲", "代码", "001"],
            ["字段", "角色甲", "角色乙", "角色丙"],
            ["联系人", "张三", "", "李四"],
        ],
        [(1, 3)],
    )
    for c in f.pdf_evidence["source_cells"]:
        if c["row"] == 0:
            c["shaded"] = c["column"] in {0, 2}
    view = bind_table_view("t1", [f], [f])
    assert view.status == "converted" and view.kind == "mixed"
    assert view.covered_source_cells == len(f.cells)
    md = render_semantic_view(view, [f])
    assert "名称：甲；代码：001" in md
    assert "字段：联系人；角色甲：张三；角色乙：（原表留空）；角色丙：李四" in md


def test_source_bound_flag_and_numeric_cells_do_not_create_headers():
    f = table([["A", "12"], ["B", "15"]])
    assert bind_table_view("t1", [f], [f]).status == "retained"
    f.pdf_evidence["source_cells"][1]["text"] = "13"
    view = bind_table_view("t1", [f], [f])
    assert view.reason_codes == ("source_grid_not_completely_bound",)


def test_model_header_flags_without_original_source_binding_are_insufficient():
    f = table([["项目", "值"], ["A", "10"]], [(0, 2)])
    f.pdf_evidence = {}
    for c in f.cells:
        c.is_column_header = c.row == 0
    f.header_scope_complete = True
    assert bind_table_view("t1", [f], [f]).status == "retained"


def test_group_header_without_distinct_leaf_roles_cannot_assign_two_values():
    f = table([["名称", "状态及数量", ""], ["甲", "无", "0"]], [(0, 2)])
    f.cells = [c for c in f.cells if (c.row, c.column) != (0, 2)]
    f.cells[1].column_span = 2
    f.pdf_evidence["source_cells"] = [
        c for c in f.pdf_evidence["source_cells"] if (c["row"], c["column"]) != (0, 2)
    ]
    f.pdf_evidence["source_cells"][1]["column_span"] = 2
    view = bind_table_view("t1", [f], [f])
    assert view.status == "retained" and view.reason_codes == ("ambiguous_duplicate_leaf_headers",)


def test_actual_blank_row_is_not_an_invented_header_or_dropped_content():
    f = table([["项目", "值"], ["", ""], ["A", "10"]], [(0, 3)])
    assert bind_table_view("t1", [f], [f]).status == "retained"


def test_unreferenced_nonempty_header_cannot_disappear_behind_coverage_metadata():
    f = table([["项目", "值"], ["A", "10"], ["另一个期间", "另一个单位"]], [(0, 2)])
    f.source_header_scopes.append({"header_rows": [2], "body_rows": [], "complete": True})
    view = bind_table_view("t1", [f], [f])
    assert view.status == "retained" and view.reason_codes == ("incomplete_source_cell_coverage",)


def test_rendering_escapes_source_markup_and_uses_references_only():
    f = table([["字段", "<script>x</script> **42** [甲](url)"]])
    value = ValueRelation(CellRef("t1", 0, 1), (CellRef("t1", 0, 0),))
    view = SemanticTableView(
        "t1", ("t1",), "converted", "fields", (SemanticRecord("t1", 0, (value,)),)
    )
    md = render_semantic_view(view, [f])
    assert "<script>" not in md and "&lt;script&gt;" in md
    assert r"\*\*42\*\*" in md and r"\[甲\]" in md
    f.cells[1].text = "43"
    assert "字段：43" in render_semantic_view(view, [f])


def test_malformed_source_grid_is_retained_and_duplicate_identity_is_rejected():
    f = table([["项目", "值"], ["A", "10"]], [(0, 2)])
    f.rows[1] = ["A"]
    assert bind_table_view("t1", [f], [f]).status == "retained"
    f = table([["项目", "值"], ["A", "10"]], [(0, 2)])
    assert bind_table_view("t1", [f], [f, f]).reason_codes == ("invalid_table_identity",)


def document(f: TableFragment) -> DocumentParseResult:
    result = DocumentParseResult(
        document_id="sem-test",
        filename="source.pdf",
        mime_type="application/pdf",
        page_count=1,
        processed_pages=1,
        pages=[PageParseResult(page_number=1, content=f.rendered)],
        pipeline=ParsePipeline(profile="balanced", primary="test"),
    )
    result._table_fragments = [f]
    views = []
    md, _ = ExportService().join_document(
        result.pages, preserve_page_breaks=True, table_fragments=[f], public_views=views
    )
    result._table_views = views
    result.parse_result = ContentParseResult(
        units=[],
        runtime=ParseRuntime(profile="balanced", primary_backend="test", parser_version="test"),
        links=ContentLinks(
            job="/job", events="/events", result="/result", assets="/assets", bundle="/bundle"
        ),
        source=ContentSource(
            content_id="sem-test",
            source_sha256="0" * 64,
            filename="source.pdf",
            mime_type="application/pdf",
            kind=SourceKind.PDF,
            size_bytes=1,
            unit_count=1,
            page_count=1,
        ),
        renderings=ContentRenderings(markdown=md + "\n\n## 图片资产\n\n[图](/asset/test)"),
    )
    return result


@pytest.mark.asyncio
async def test_final_public_view_keeps_assets_source_ir_and_no_gfm_prose_mapping():
    f = table([["项目", "本报告期"], ["A", "10"]], [(0, 2)])
    before = deepcopy(f.rows)
    r = document(f)
    await TableSemanticsService().apply(r, ContentParseOptions())
    md = r.parse_result.renderings.markdown
    assert "项目：A；本报告期：10" in md and "[图](/asset/test)" in md
    assert "semantic-source:" in md and "table-structure:" not in md
    assert r._semantic_tables[0].status == "converted" and f.rows == before


@pytest.mark.asyncio
async def test_unresolved_owned_view_keeps_exact_source_grid_and_explicit_status():
    f = table([["A", "10"], ["B", "12"]])
    r = document(f)
    old = r.parse_result.renderings.markdown
    await TableSemanticsService().apply(r, ContentParseOptions())
    md = r.parse_result.renderings.markdown
    assert r._table_views[0].rendered in md
    assert r._source_markdown == old
    assert "status=retained" in md and "保留原表" in md and "[图](/asset/test)" in md
    assert "version=" not in md
    assert "table-structure:" in old and "table-structure:" in md


@pytest.mark.asyncio
async def test_duplicate_rendering_positions_are_never_globally_replaced():
    f = table([["项目", "值"], ["A", "10"]], [(0, 2)])
    r = document(f)
    r.parse_result.renderings.markdown += "\n\n" + r._table_views[0].rendered
    old = r.parse_result.renderings.markdown
    await TableSemanticsService().apply(r, ContentParseOptions())
    assert old in r.parse_result.renderings.markdown
    assert r._semantic_tables[0].status == "retained"


@pytest.mark.asyncio
async def test_semantic_finalization_is_idempotent():
    f = table([["项目", "值"], ["A", "10"]], [(0, 2)])
    r = document(f)
    service = TableSemanticsService()
    await service.apply(r, ContentParseOptions())
    first = r.parse_result.renderings.markdown
    await service.apply(r, ContentParseOptions())
    assert r.parse_result.renderings.markdown == first


def test_inherited_scope_references_the_original_header_cells():
    first = table([["项目", "本报告期"], ["A", "10"]], [(0, 2)], name="p1")
    second = table([["B", "12"]], name="p2")
    second.page_number = 2
    second.pdf_evidence["inherited_header_scope"] = {
        "complete": True,
        "source_table_id": "p1",
        "header_rows": [0],
        "source_column_groups": [[0], [1]],
        "body_rows": [0],
    }
    view = bind_table_view("p2", [second], [first, second])
    assert view.status == "converted"
    relation = view.records[0].values[0]
    assert relation.value == CellRef("p2", 0, 1)
    assert relation.column_headers == (CellRef("p1", 0, 1),)
    assert "本报告期：12" in render_semantic_view(view, [first, second])
    first.pdf_evidence = {}
    assert bind_table_view("p2", [second], [first, second]).status == "retained"


@pytest.mark.asyncio
async def test_cancellation_keeps_the_original_public_view():
    import threading

    from app.parsers.base import ParserCancelledError

    f = table([["项目", "值"], ["A", "10"]], [(0, 2)])
    r = document(f)
    before = r.parse_result.renderings.markdown
    event = threading.Event()
    event.set()
    with pytest.raises(ParserCancelledError):
        await TableSemanticsService().apply(r, ContentParseOptions(), cancel_event=event)
    assert r.parse_result.renderings.markdown == before and not r._semantic_tables
