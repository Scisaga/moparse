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
    assert b.values[1].value_state == "literal"
    md = render_semantic_view(view, [f])
    assert "本报告期末：0" in md and "上年末：—" in md
    assert "B；本报告期：-1.20%" in md and "上年同期：。" in md
    assert "原表留空" not in md
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
    f.pdf_evidence["field_scopes"] = [{
        "body_rows": [0], "pairs": [{"label": [0, 0], "value": [0, 1]},
                                    {"label": [0, 2], "value": [0, 3]}],
        "complete": True, "evidence_source": "authored_field_scope",
        "evidence": {"source_style_contrast": True, "numeric_value_evidence": True},
    }]
    view = bind_table_view("t1", [f], [f])
    assert view.status == "converted" and view.kind == "mixed"
    assert view.covered_source_cells == len(f.cells)
    md = render_semantic_view(view, [f])
    assert "名称：甲；代码：001" in md
    assert "字段：联系人；角色甲：张三；角色乙：；角色丙：李四" in md
    assert "原表留空" not in md


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
    view = bind_table_view("t1", [f], [f])
    assert view.status == "partial" and ("t1", 1) in view.retained_rows
    rendered = render_semantic_view(view, [f])
    assert "semantic-retained:" in rendered and rendered.count("10") == 1
    assert "原表留空" not in rendered


def test_partial_table_prints_shared_header_spans_and_retains_only_unconverted_values():
    from app.parsers.glm_sdk_remote import _html_table_layout

    f = table([["Item", "Year ended", ""], ["", "2034", "2033"],
               ["Alpha", "11", "7"], ["", "13", "5"]])
    f.cells = [c for c in f.cells if (c.row, c.column) not in {(1, 0), (0, 2)}]
    for cell in f.cells:
        if (cell.row, cell.column) == (0, 0):
            cell.row_span = 2
        elif (cell.row, cell.column) == (0, 1):
            cell.column_span = 2
    f.pdf_evidence["source_cells"] = [
        {"row": c.row, "column": c.column, "row_span": c.row_span,
         "column_span": c.column_span, "text": c.text} for c in f.cells
    ]
    f.source_header_scopes = [{"header_rows": [0, 1], "body_rows": [2, 3], "complete": True}]
    before = deepcopy(f)
    view = bind_table_view("partial", [f], [f])
    assert view.status == "partial" and len(view.records) == 1
    rendered = render_semantic_view(view, [f])
    assert '<td colspan="2">Year ended</td>' in rendered
    assert '<td rowspan="2">Item</td>' in rendered
    raw = "<table>" + rendered.partition("<table>")[2]
    rows, _, cells = _html_table_layout(raw)
    assert rows == [["", "", ""], ["Item", "Year ended", ""],
                    ["", "2034", "2033"], ["", "13", "5"]]
    assert any(c.column_span == 2 and c.text == "Year ended" for c in cells)
    assert rendered.count("11") == 1 and rendered.count("13") == 1
    assert f == before


def test_unreferenced_nonempty_header_cannot_disappear_behind_coverage_metadata():
    f = table([["项目", "值"], ["A", "10"], ["另一个期间", "另一个单位"]], [(0, 2)])
    f.source_header_scopes.append({"header_rows": [2], "body_rows": [], "complete": True})
    view = bind_table_view("t1", [f], [f])
    assert view.status == "partial" and view.reason_codes == ("incomplete_source_cell_coverage",)
    rendered = render_semantic_view(view, [f])
    assert "另一个期间" in rendered and "另一个单位" in rendered
    assert rendered.count("10") == 1


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


def _explicit_view(*values: ValueRelation, subject=None, subject_headers=()) -> SemanticTableView:
    return SemanticTableView(
        "t1", ("t1",), "converted", "fields",
        (SemanticRecord("t1", values[0].value.row, tuple(values), subject, tuple(subject_headers)),),
    )


def test_explicit_units_periods_and_notes_are_rendered_and_traced_without_rebinding():
    f = table([
        ["字段", "收入"], ["值", "100"], ["单位一", "万元"], ["单位二", "人民币"],
        ["期间", "2025年度"], ["附注一", "含税"], ["附注二", "已审计"],
    ])
    relation = ValueRelation(
        CellRef("t1", 1, 1), (CellRef("t1", 0, 1),),
        unit_refs=(CellRef("t1", 2, 1), CellRef("t1", 3, 1), CellRef("t1", 2, 1)),
        period_refs=(CellRef("t1", 4, 1),),
        note_refs=(CellRef("t1", 5, 1), CellRef("t1", 6, 1), CellRef("t1", 5, 1)),
    )
    before = deepcopy(f)
    md = render_semantic_view(_explicit_view(relation), [f])
    assert "收入：100（单位：万元 / 人民币；期间：2025年度；附注：含税 / 已审计）" in md
    assert md.count("万元") == 1 and md.count("含税") == 1
    source = next(line for line in md.splitlines() if "semantic-source:" in line)
    assert all(CellRef("t1", row, 1).token in source for row in range(7))
    assert f == before


@pytest.mark.parametrize("role", ["unit_refs", "period_refs", "note_refs"])
def test_every_explicit_qualifier_reference_must_exist(role):
    f = table([["字段", "收入"], ["值", "100"]])
    relation = ValueRelation(
        CellRef("t1", 1, 1), (CellRef("t1", 0, 1),),
        **{role: (CellRef("absent", 0, 0),)},
    )
    with pytest.raises(ValueError, match="source reference is absent"):
        render_semantic_view(_explicit_view(relation), [f])


def test_referenced_ambiguous_cell_is_rejected_but_unrelated_duplicate_does_not_hide_neighbors():
    f = table([["字段", "收入"], ["值", "100"], ["单位", "万元"]])
    relation = ValueRelation(CellRef("t1", 1, 1), (CellRef("t1", 0, 1),),
                             unit_refs=(CellRef("t1", 2, 1),))
    duplicate = deepcopy(f.cells[-1])
    duplicate.text = "元"
    f.cells.append(duplicate)
    with pytest.raises(ValueError, match="source reference is ambiguous"):
        render_semantic_view(_explicit_view(relation), [f])
    f.cells.pop()
    unrelated = table([["其他", "文字"]], name="unrelated")
    unrelated.cells.append(deepcopy(unrelated.cells[0]))
    assert "单位：万元" in render_semantic_view(_explicit_view(relation), [f, unrelated])


def test_qualifier_cell_already_emitted_in_heading_is_not_repeated_or_guessed():
    f = table([["项目", "2025年度金额（万元）"], ["收入", "100"]])
    heading = CellRef("t1", 0, 1)
    relation = ValueRelation(
        CellRef("t1", 1, 1), (CellRef("t1", 1, 0),), (heading, heading),
        unit_refs=(heading,), period_refs=(heading,), note_refs=(heading,),
    )
    view = _explicit_view(relation, subject=CellRef("t1", 1, 0))
    md = render_semantic_view(view, [f])
    assert md.count("2025年度金额（万元）") == 1
    assert "单位：" not in md and "期间：" not in md and "附注：" not in md


def test_qualifiers_are_scoped_per_value_and_deduplicated_by_cell_not_by_text():
    f = table([["项目", "金额甲", "金额乙"], ["收入", "100", "200"],
               ["单位", "元", "元"], ["期间", "2025年度", "2024年度"]])
    first = ValueRelation(CellRef("t1", 1, 1), (), (CellRef("t1", 0, 1),),
                          unit_refs=(CellRef("t1", 2, 1), CellRef("t1", 2, 2)),
                          period_refs=(CellRef("t1", 3, 1),))
    second = ValueRelation(CellRef("t1", 1, 2), (), (CellRef("t1", 0, 2),),
                           period_refs=(CellRef("t1", 3, 2),))
    md = render_semantic_view(_explicit_view(first, second, subject=CellRef("t1", 1, 0)), [f])
    assert "金额甲：100（单位：元 / 元；期间：2025年度）" in md
    assert "金额乙：200（期间：2024年度）" in md
    assert md.count("单位：") == 1


def test_qualifier_markup_is_escaped_and_unbound_qualifiers_are_not_discovered():
    f = table([["字段", "收入"], ["值", "100"], ["附注", "<b>**含税**</b>"],
               ["未绑定单位", "亿元"]])
    relation = ValueRelation(CellRef("t1", 1, 1), (CellRef("t1", 0, 1),),
                             note_refs=(CellRef("t1", 2, 1),))
    md = render_semantic_view(_explicit_view(relation), [f])
    assert r"附注：&lt;b&gt;\*\*含税\*\*&lt;/b&gt;" in md
    assert "亿元" not in md and "单位：" not in md


@pytest.mark.parametrize("state,expected", [("literal", "字段：。"),
                                            ("source_blank", "字段：（原表留空）。")])
def test_only_explicit_source_blank_may_describe_an_empty_literal_as_source_blank(state, expected):
    f = table([["字段", " \n "]])
    relation = ValueRelation(CellRef("t1", 0, 1), (CellRef("t1", 0, 0),), value_state=state)
    md = render_semantic_view(_explicit_view(relation), [f])
    assert md.splitlines()[-1] == "- " + expected
    if state == "literal":
        assert "原表留空" not in md


def test_contradictory_blank_state_cannot_delete_existing_literal():
    f = table([["字段", "0"]])
    relation = ValueRelation(CellRef("t1", 0, 1), (CellRef("t1", 0, 0),), value_state="source_blank")
    with pytest.raises(ValueError, match="conflicts with a nonempty literal"):
        render_semantic_view(_explicit_view(relation), [f])


@pytest.mark.asyncio
async def test_bound_empty_value_keeps_literal_state_and_valid_neighbors_in_public_output():
    f = table([["项目", "值"], ["A", ""], ["B", "0"], ["C", "—"]], [(0, 4)])
    result = document(f)
    before = deepcopy(f)
    await TableSemanticsService().apply(result, ContentParseOptions())
    view = result._semantic_tables[0]
    assert view.status == "converted"
    assert all(value.value_state == "literal" for record in view.records for value in record.values)
    md = result.parse_result.renderings.markdown
    assert "项目：A；值：。" in md
    assert "项目：B；值：0。" in md and "项目：C；值：—。" in md
    assert "原表留空" not in md
    assert f == before


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
    assert "status=retained" in md and "[图](/asset/test)" in md
    assert "表格语义转换：" not in md and "表格语义关系尚未确定" not in md
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


@pytest.mark.asyncio
@pytest.mark.parametrize("extra,duplicate", [("", False), ("\n\n<div>Keep this note</div>", False), ("", True)])
async def test_owned_html_span_table_reaches_semantic_conversion_without_accepting_neighbors(extra, duplicate):
    from dataclasses import replace

    f = table([["项目", "2024", ""], ["", "收入", "成本"], ["Alpha", "11", "7"]])
    f.cells = [c for c in f.cells if (c.row, c.column) not in {(1, 0), (0, 2)}]
    for cell in f.cells:
        if (cell.row, cell.column) == (0, 0):
            cell.row_span = 2
        if (cell.row, cell.column) == (0, 1):
            cell.column_span = 2
    f.pdf_evidence = {"bound": True, "source_cells": [
        {"row": c.row, "column": c.column, "row_span": c.row_span,
         "column_span": c.column_span, "text": c.text, "shaded": False}
        for c in f.cells
    ]}
    f.source_header_scopes = [{"header_rows": [0, 1], "body_rows": [2], "complete": True}]
    f = replace(f, rendered=f"<!-- table-fragment: t1 -->\n\n{f.markdown}")
    result = document(f)
    view = result._table_views[0]
    assert '<td colspan="2">2024</td>' in view.rendered
    if extra:
        result._table_views[0] = replace(view, rendered=view.rendered + extra)
        result.parse_result.renderings.markdown = result.parse_result.renderings.markdown.replace(
            view.rendered, view.rendered + extra, 1)
    if duplicate:
        result.parse_result.renderings.markdown += "\n\n" + view.rendered
    before = deepcopy(f)
    await TableSemanticsService().apply(result, ContentParseOptions())
    output = result.parse_result.renderings.markdown
    if extra or duplicate:
        assert result._semantic_tables[0].status == "retained"
        assert view.rendered in output
        assert extra in output
        assert "public_view_not_uniquely_owned" in result._semantic_tables[0].reason_codes
    else:
        assert result._semantic_tables[0].status == "converted"
        assert "Alpha" in output and "收入" in output and "11" in output and "成本" in output and "7" in output
        assert '<td colspan="2">2024</td>' not in output
    assert "[图](/asset/test)" in output and f == before
