"""Final service observations from controlled result objects, without a corpus."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from app.models.table_semantics import (
    CellRef,
    SemanticRecord,
    SemanticTableView,
    TextRef,
    ValueRelation,
)
from app.services.export_service import ExportService
from app.services.table_semantics_service import bind_table_view, render_semantic_view
from app.services.table_service import (
    TableCellFragment,
    TableFragment,
    TableSourceView,
    render_gfm_rows,
)
from moparse_eval.matching import match_units, observation_candidates
from moparse_eval.scoring import _score_records
from moparse_eval.service_observation import (
    SERVICE_OBSERVATION_VERSION,
    _inline_text,
    build_service_observation,
    read_final_observation,
    read_final_page_provenance,
)


def _published_list_with_unqualified_value(caption="（单位:%）", *, separator="", value="N/A", unit=None,
                                         column="2025"):
    body = caption + "\n\n" + separator + f"- 项目：Coverage；{column}：17。\n\n\n\n- 项目：Liquidity；{column}：{value}。\n"
    start = body.index(f"{column}：{value}。", body.index("Liquidity")) + len(column + "：")
    cell = {"id": "actual-value", "text": value, "text_format": "plain",
            "final_markdown_span": [start, start + len(value)],
            "row_header_path": ["Liquidity"], "column_header_path": [column]}
    if unit is not None:
        cell["unit"] = unit
    return {"input_page_count": 1, "pages": [{"page": 1, "blocks": [{
        "id": "actual-record", "kind": "table_body", "cells": [cell],
    }]}], "service_output": {"reader_version": SERVICE_OBSERVATION_VERSION,
        "final_markdown": body, "published_provenance": {"status": "bound"}, "semantic_views": []}}


@pytest.mark.parametrize("value", ["N/A", "不适用", "17"])
def test_published_shared_list_unit_covers_values_without_repeating_a_suffix(value):
    from moparse_eval.information import qualifier_evidence
    observation = _published_list_with_unqualified_value(value=value)
    before = deepcopy(observation)
    derived, _diagnostic = read_final_observation(observation)
    assert observation == before
    cell = derived["pages"][0]["blocks"][0]["cells"][0]
    assert qualifier_evidence({"unit": "%"}, cell, [])["unit"]["status"] == "correct"


@pytest.mark.parametrize("caption,separator", [
    ("A separate operation earned 17%.", ""),
    ("（单位:%）", "Ordinary explanation.\n\n"),
    ("（单位:%）", "## Another section\n\n"),
    ("（单位:%）", "- A different list.\n\nAn independent paragraph.\n\n"),
])
def test_unrelated_or_ended_unit_scope_does_not_qualify_another_list(caption, separator):
    from moparse_eval.information import qualifier_evidence
    derived, _diagnostic = read_final_observation(
        _published_list_with_unqualified_value(caption, separator=separator))
    cell = derived["pages"][0]["blocks"][0]["cells"][0]
    assert qualifier_evidence({"unit": "%"}, cell, [])["unit"]["status"] == "incorrect"


def test_shared_list_unit_does_not_rescue_an_explicit_wrong_field_unit():
    from moparse_eval.information import qualifier_evidence
    derived, _diagnostic = read_final_observation(_published_list_with_unqualified_value(unit="USD"))
    cell = derived["pages"][0]["blocks"][0]["cells"][0]
    assert qualifier_evidence({"unit": "%"}, cell, [])["unit"]["status"] == "incorrect"


@pytest.mark.parametrize("column,correct", [("附注", False), ("Notes", False), ("Code", False),
                                           ("Notes receivable", True)])
def test_shared_list_units_distinguish_reference_properties_from_whole_business_labels(column, correct):
    from moparse_eval.information import qualifier_evidence
    derived, _diagnostic = read_final_observation(
        _published_list_with_unqualified_value("（单位:万元）", value="17", column=column))
    cell = derived["pages"][0]["blocks"][0]["cells"][0]
    assert (qualifier_evidence({"unit": "万元"}, cell, [])["unit"]["status"] == "correct") is correct


def _fragment(rows=None, *, name="t1", page=1, headers=True):
    rows = rows or [
        ["项目", "金额", "单位", "期间", "附注"],
        ["收入", "100", "万元", "2025年度", "含税"],
    ]
    markdown = render_gfm_rows(rows)
    return TableFragment(
        fragment_id=name,
        page_number=page,
        ordinal=1,
        normalized_bbox=(0.1, 0.1, 0.9, 0.9),
        num_rows=len(rows),
        num_cols=len(rows[0]),
        rows=deepcopy(rows),
        column_boundaries=[],
        markdown=markdown,
        rendered=f"<!-- table-fragment: {name} -->\n\n{markdown}",
        has_column_header=headers,
        cells=[
            TableCellFragment(
                row,
                col,
                1,
                1,
                text,
                is_column_header=headers and row == 0,
                is_row_header=row > 0 and col == 0,
            )
            for row, values in enumerate(rows)
            for col, text in enumerate(values)
        ],
    )


def _result(markdown="", *, pages=1):
    return DocumentParseResult(
        document_id="synthetic",
        filename="synthetic.pdf",
        mime_type="application/pdf",
        page_count=pages,
        processed_pages=pages,
        markdown=markdown,
        plain_text="HIDDEN PRECONVERSION PLAIN TEXT",
        pages=[
            PageParseResult(page_number=index, content="HIDDEN NATIVE PAGE")
            for index in range(1, pages + 1)
        ],
        pipeline=ParsePipeline(profile="accurate", primary="mineru-native-advanced", ocr="glm-sdk"),
    )


def _converted(*, text="100", state="literal"):
    fragment = _fragment()
    fragment.cells[6].text = text

    def ref(row, col):
        return CellRef("t1", row, col)

    value = ValueRelation(
        ref(1, 1), (ref(1, 0),), (ref(0, 1),), (ref(1, 2),), (ref(1, 3),), (ref(1, 4),), state
    )
    record = SemanticRecord("t1", 1, (value,), ref(1, 0), (ref(0, 0),))
    view = SemanticTableView("view-t1", ("t1",), "converted", "records", (record,))
    result = _result(
        "# Final title\n\n" + render_semantic_view(view, [fragment]) + "\n\nFinal tail."
    )
    result._table_fragments = [fragment]
    result._semantic_tables = [view]
    return result, fragment, view


def _cells(observation):
    return [
        candidate["cell"]
        for candidate in observation_candidates(observation)
        if "cell" in candidate
    ]


def test_clean_public_body_keeps_real_table_values_and_qualifier_evidence():
    from app.services.final_content_service import FinalContentService
    result, _, _ = _converted()
    FinalContentService().apply(result)
    assert '<!--' not in result.markdown
    assert '100' in result.markdown and '万元' in result.markdown and '含税' in result.markdown
    observation = build_service_observation(result, sample_id='invented')
    values = [cell for cell in _cells(observation) if cell['text'] == '100']
    assert len(values) == 1
    assert values[0]['unit'] == '万元'
    assert values[0]['period'] == '2025年度'
    assert values[0]['notes'] == ['含税']
    a, b = values[0]['final_markdown_span']
    assert result.markdown[a:b] == '100'


def _unit_corner_result():
    from app.services.table_context_service import native_scopes

    fragment = _fragment([["(in RMB million)", "2034"], ["Revenue", "17"],
                          ["Number of customers (in million)", "2.47"]])
    fragment.source_kind = "mineru"
    fragment.native_evidence = native_scopes(fragment)
    fragment.source_header_scopes = fragment.native_evidence["header_scopes"]
    view = bind_table_view("view-t1", [fragment], [fragment])
    result = _result(render_semantic_view(view, [fragment]) + "\n\nSeparate business paragraph.")
    result._table_fragments, result._semantic_tables = [fragment], [view]
    return result, fragment, view


def test_a_visible_owned_unit_paragraph_does_not_hide_following_semantic_records():
    from app.services.final_content_service import FinalContentService

    result, _, _ = _unit_corner_result()
    FinalContentService().apply(result)
    observation = build_service_observation(result, sample_id="invented")
    cells = _cells(observation)
    revenue = next(c for c in cells if c["text"] == "17")
    count = next(c for c in cells if c["text"] == "2.47")
    assert revenue["units"] == ["(in RMB million)"]
    assert count["units"] == ["Number of customers (in million)"]
    assert observation["service_output"]["semantic_views"][0]["final_evidence"] == "converted"
    for cell in [revenue, count]:
        a, b = cell["final_markdown_span"]
        assert result.markdown[a:b] == cell["text"]


@pytest.mark.parametrize("old_subject_header", [False, True])
def test_old_records_remain_readable_without_a_new_unit_paragraph(old_subject_header):
    result, fragment, view = _unit_corner_result()
    if old_subject_header:
        view = replace(view, records=tuple(replace(r, subject_headers=(CellRef("t1", 0, 0),)) for r in view.records))
        result._semantic_tables = [view]
    text = render_semantic_view(view, [fragment])
    result.markdown = text.replace(
        "<!-- semantic-source: cells=t1.r0c0; headers=t1.r0c0 -->\n\n(in RMB million)\n\n", "", 1)
    assert not result.markdown.startswith("(in RMB million)")
    observed = build_service_observation(result, sample_id="invented")
    assert {"17", "2.47"}.issubset({c["text"] for c in _cells(observed)})


@pytest.mark.parametrize("replacement", ["An ordinary business paragraph.", "999"])
def test_a_unit_marker_cannot_authorize_nonunit_paragraphs_or_hidden_records(replacement):
    result, _, _ = _unit_corner_result()
    result.markdown = result.markdown.replace("(in RMB million)\n\n", replacement + "\n\n", 1)
    observed = build_service_observation(result, sample_id="invented")
    assert not {"17", "2.47"}.intersection({c["text"] for c in _cells(observed)})
    assert replacement in observed["service_output"]["final_markdown"]


def test_an_unmarked_unit_paragraph_cannot_bridge_to_an_unowned_record_copy():
    result, _, _ = _unit_corner_result()
    result.markdown = result.markdown.replace("<!-- semantic-source: cells=t1.r0c0; headers=t1.r0c0 -->\n\n", "", 1)
    observed = build_service_observation(result, sample_id="invented")
    assert not {"17", "2.47"}.intersection({c["text"] for c in _cells(observed)})


def test_external_native_qualifier_requires_its_literal_in_the_real_final_body():
    result, fragment, view = _converted()
    period = TextRef("t1", 1, "native.p0", "2025年度排放情况：", "period", 0, 12, (1,), (1,))
    fragment.context_refs = (period,)
    relation = replace(view.records[0].values[0], period_refs=(period,))
    record = replace(view.records[0], values=(relation,))
    view = replace(view, records=(record,))
    result._semantic_tables = [view]
    result.markdown = render_semantic_view(view, [fragment])
    observation = build_service_observation(result, sample_id="invented")
    values = [c for c in _cells(observation) if c["text"] == "100"]
    assert len(values) == 1 and values[0]["periods"] == [period.text]
    assert values[0]["period_refs"][0]["block_id"] == "native.p0"
    result.markdown = result.markdown.replace(period.text, "")
    hidden = build_service_observation(result, sample_id="invented")
    assert all(period.text not in str(c.get("periods", [])) for c in _cells(hidden))


def test_parenthesized_unit_is_read_as_visible_scoped_text_not_an_invented_atomic_unit():
    result, fragment, view = _converted()
    fragment.cells[7].text = "(万元)"
    result.markdown = render_semantic_view(view, [fragment])
    observed = build_service_observation(result, sample_id="invented")
    cell = next(c for c in _cells(observed) if c["text"] == "100")
    assert cell["units"] == ["(万元)"] and "unit" not in cell
    units = [{"id": "r", "kind": "table_record", "reference_text": "收入", "pages": [1],
              "table": {"row_header_path": ["收入"], "fields": [{"column_header_path": ["金额"],
              "value": "100", "unit": "万元"}]}}]
    rows, _metrics = _score_records(units, observed, True, match_units(units, observed))
    assert rows[0]["fields"][0]["information"]["status"] == "correct"


def test_an_actual_record_title_unit_is_read_but_a_hidden_title_is_not():
    result, fragment, view = _converted()
    title = "（单位:%）"
    scope = TextRef("t1", 1, "title", title, "title", 0, len(title), (1,), (1,))
    fragment.context_refs = (scope,)
    relation = replace(view.records[0].values[0], unit_refs=())
    view = replace(view, records=(replace(view.records[0], values=(relation,), scope_refs=(scope,)),))
    result._semantic_tables = [view]
    result.markdown = render_semantic_view(view, [fragment])
    observed = build_service_observation(result, sample_id="invented")
    value = next(c for c in _cells(observed) if c["text"] == "100")
    assert value["units"] == [title]
    from moparse_eval.information import qualifier_evidence
    assert qualifier_evidence({"unit": "%"}, value, value["column_header_path"])["unit"]["status"] == "correct"
    result.markdown = result.markdown.replace(title, "")
    assert all(title not in c.get("units", []) for c in _cells(build_service_observation(result, sample_id="invented")))


@pytest.mark.parametrize("caption,found", [
    ("(货币单位：人民币百万元)", True), ("（貨幣單位：港幣百萬元）", True),
    ("人民币百万元项目业务", False), ("货币政策：人民币百万元", False),
])
def test_currency_unit_scope_requires_an_actual_printed_unit_caption(caption, found):
    result, fragment, view = _converted()
    scope = TextRef("t1", 1, "title", caption, "title", 0, len(caption), (1,), (1,))
    fragment.context_refs = (scope,)
    relation = replace(view.records[0].values[0], unit_refs=())
    view = replace(view, records=(replace(view.records[0], values=(relation,), scope_refs=(scope,)),))
    result._semantic_tables = [view]
    result.markdown = render_semantic_view(view, [fragment])
    observed = build_service_observation(result, sample_id="invented")
    value = next(c for c in _cells(observed) if c["text"] == "100")
    assert (caption in value.get("units", [])) is found
    result.markdown = result.markdown.replace(caption, "")
    assert not _cells(build_service_observation(result, sample_id="invented"))


def _named_record(*, identity_header="Name", group=None, duplicate=False, ordinal_header="No."):
    fragment = _fragment([[ordinal_header, identity_header, "Amount"], ["1", "Acme", "17"]])
    def ref(row, col):
        return CellRef("t1", row, col)

    relations = tuple(ValueRelation(ref(1, col), (ref(1, 0),), (ref(0, col),)) for col in (1, 2))
    groups = ()
    if group:
        fragment.cells.append(TableCellFragment(2, 0, 1, 1, group))
        groups = (ref(2, 0),)
    record = SemanticRecord("t1", 1, relations, ref(1, 0), (ref(0, 0),), groups)
    records = (record, record) if duplicate else (record,)
    view = SemanticTableView("named-record", ("t1",), "converted", "records", records)
    result = _result(render_semantic_view(view, [fragment]))
    result._table_fragments, result._semantic_tables = [fragment], [view]
    return result


@pytest.mark.parametrize("header", ["Name", "认购方", "項目", "股东名称", "Shareholder Name"])
@pytest.mark.parametrize("column,value", [("Amount", "17"), ("No.", "1")])
def test_printed_named_identity_locates_the_same_record_including_its_ordinal(header, column, value):
    result = _named_record(identity_header=header)
    observed = build_service_observation(result, sample_id="invented")
    unit = {"id": "r", "kind": "table_record", "reference_text": "Acme", "pages": [1],
            "table": {"row_header_path": ["Acme"], "fields": [{"column_header_path": [column], "value": value}]}}
    rows, metrics = _score_records([unit], observed, True, match_units([unit], observed))
    assert metrics["information_correct_fields"] == 1
    cell = next(c for c in _cells(observed) if c["id"] == rows[0]["fields"][0]["native_id"])
    start, end = cell["final_markdown_span"]
    assert result.markdown[start:end] == value
    result.markdown = result.markdown.replace("Acme", "Hidden")
    assert not _cells(build_service_observation(result, sample_id="invented"))


@pytest.mark.parametrize("options,row", [
    ({"identity_header": "Note"}, ["Acme"]),
    ({"group": "South"}, ["North", "Acme"]),
    ({"duplicate": True}, ["Acme"]),
])
def test_record_identity_requires_business_labels_but_repeated_identical_assertions_agree(options, row):
    observed = build_service_observation(_named_record(**options), sample_id="invented")
    unit = {"id": "r", "kind": "table_record", "reference_text": "Acme", "pages": [1],
            "table": {"row_header_path": row, "fields": [{"column_header_path": ["Amount"], "value": "17"}]}}
    _rows, metrics = _score_records([unit], observed, True, match_units([unit], observed))
    assert metrics["information_correct_fields"] == int(options.get("duplicate", False))


@pytest.mark.parametrize("header,row,correct", [
    ("股东名称", ["1", "Acme"], True), ("Shareholder Name", ["1", "Acme"], True),
    ("股东名称", ["2", "Acme"], False), ("Note Name", ["Acme"], False),
    ("备注名称", ["Acme"], False), ("说明姓名", ["Acme"], False),
])
def test_named_property_and_ordinal_are_read_as_printed_identifiers_not_inferred_parents(header, row, correct):
    observed = build_service_observation(_named_record(identity_header=header), sample_id="invented")
    unit = {"id": "r", "kind": "table_record", "reference_text": "Acme", "pages": [1],
            "table": {"row_header_path": row, "fields": [{"column_header_path": ["Amount"], "value": "17"}]}}
    _rows, metrics = _score_records([unit], observed, True, match_units([unit], observed))
    assert (metrics["information_correct_fields"] == 1) is correct


@pytest.mark.parametrize('ordinal_header,group,row,correct', [
    ('No.', None, ['Acme'], True), ('No.', None, ['1', 'Acme'], True),
    ('No.', None, ['1'], True), ('No.', None, ['2', 'Acme'], False),
    ('Index', None, ['1', 'Acme'], True), ('Cost', None, ['1', 'Acme'], False),
    ('No.', 'South', ['South', '1', 'Acme'], True),
    ('No.', 'South', ['North', '1', 'Acme'], False),
    ('No.', 'South', ['1', 'Acme'], True),
])
def test_identity_subject_and_printed_ordinal_property_keep_the_same_record_scope(ordinal_header, group, row, correct):
    result = _named_record(identity_header='股东名称', group=group, ordinal_header=ordinal_header)
    fragment, view = result._table_fragments[0], result._semantic_tables[0]
    old = view.records[0]
    def ref(r, c):
        return CellRef('t1', r, c)
    record = SemanticRecord('t1', 1, tuple(ValueRelation(ref(1, col), (ref(1, 1),), (ref(0, col),))
                                         for col in (0, 2)), ref(1, 1), (ref(0, 1),), old.row_groups)
    view = replace(view, records=(record,))
    result._semantic_tables = [view]
    result.markdown = render_semantic_view(view, [fragment])
    observed = build_service_observation(result, sample_id='invented')
    unit = {'id': 'r', 'kind': 'table_record', 'reference_text': 'Acme', 'pages': [1],
            'table': {'row_header_path': row, 'fields': [{'column_header_path': ['Amount'], 'value': '17'}]}}
    _rows, metrics = _score_records([unit], observed, True, match_units([unit], observed))
    assert (metrics['information_correct_fields'] == 1) is correct


def _partial_result():
    fragment = _fragment([["项目", "金额"], ["收入", "100"], ["", "20"]])
    fragment.pdf_evidence = {"bound": True, "source_cells": [
        {"row": c.row, "column": c.column, "row_span": 1, "column_span": 1,
         "text": c.text, "shaded": False} for c in fragment.cells
    ]}
    fragment.source_header_scopes = [{"header_rows": [0], "body_rows": [1, 2], "complete": True}]
    view = bind_table_view("partial-t1", [fragment], [fragment])
    assert view.status == "partial"
    result = _result(render_semantic_view(view, [fragment]))
    result._table_fragments = [fragment]
    result._semantic_tables = [view]
    return result


def test_partial_view_reads_confirmed_records_and_exact_residual_grid_without_repeating_values():
    result = _partial_result()
    observation = build_service_observation(result, sample_id="sample")
    assert observation["errors"] == []
    cells = _cells(observation)
    assert len([c for c in cells if c["text"] == "100"]) == 1
    assert len([c for c in cells if c["text"] == "20"]) == 1
    retained = next(c for c in cells if c["text"] == "20")
    assert retained["source_cell_ref"]["token"] == "t1.r2c1"
    assert retained["service_evidence_state"] == "retained"
    assert observation["service_output"]["semantic_views"][0]["final_evidence"] == "partial"
    assert observation["service_output"]["conversion_summary"]["declared_partial_views"] == 1


def _spanned_partial_result():
    fragment = _fragment([["Item", "Year ended", ""], ["", "2034", "2033"],
                          ["Alpha", "11", "7"], ["Beta", "13", "5"]], headers=False)
    fragment.cells = [c for c in fragment.cells if (c.row, c.column) not in {(1, 0), (0, 2)}]
    for cell in fragment.cells:
        if (cell.row, cell.column) == (0, 0):
            cell.row_span = 2
        elif (cell.row, cell.column) == (0, 1):
            cell.column_span = 2
    fragment.pdf_evidence = {"bound": True, "source_cells": [
        {"row": c.row, "column": c.column, "row_span": c.row_span,
         "column_span": c.column_span, "text": c.text} for c in fragment.cells
    ]}
    fragment.source_header_scopes = [{"header_rows": [0, 1], "body_rows": [2, 3], "complete": True}]
    fragment.native_evidence = {"operation_rows": [3]}
    view = bind_table_view("partial-t1", [fragment], [fragment])
    assert view.status == "partial" and len(view.records) == 1
    result = _result(render_semantic_view(view, [fragment]))
    result._table_fragments, result._semantic_tables = [fragment], [view]
    return result


def test_partial_html_period_paths_are_supported_by_printed_spans_after_publication():
    from app.services.final_content_service import FinalContentService

    result = _spanned_partial_result()
    FinalContentService().apply(result)
    observation, diagnostic = read_final_observation(build_service_observation(result, sample_id="sample"))
    assert observation["errors"] == []
    assert diagnostic["reader_version"] == "mo-parse-final-output-readback-v15"
    unit = {"id": "beta", "kind": "table_record", "reference_text": "Beta", "pages": [1],
            "table": {"row_header_path": ["Beta"], "fields": [
                {"column_header_path": ["Year ended", "2034"], "value": "13", "period": "2034"},
                {"column_header_path": ["Year ended", "2033"], "value": "5", "period": "2033"},
            ]}}
    _rows, metrics = _score_records([unit], observation, True, match_units([unit], observation))
    assert metrics["information_correct_fields"] == metrics["target_fields"] == 2
    assert result.markdown.count("13") == 1
    value = next(c for c in _cells(observation) if c["text"] == "13")
    a, b = value["final_markdown_span"]
    assert result.markdown[a:b] == "13"


def test_partial_html_changed_after_publication_is_rejected_instead_of_using_hidden_source():
    from app.services.final_content_service import FinalContentService

    result = _spanned_partial_result()
    FinalContentService().apply(result)
    result.markdown = result.markdown.replace("<td colspan=\"2\">Year ended</td>",
                                              "<td colspan=\"2\"></td>")
    with pytest.raises(ValueError, match="published output differs"):
        build_service_observation(result, sample_id="sample")


def test_partial_gfm_remains_readable_without_acquiring_unprinted_header_spans():
    from app.services.final_content_service import FinalContentService
    from app.services.table_semantics_service import retained_table_parts

    result = _spanned_partial_result()
    view, fragment = result._semantic_tables[0], result._table_fragments[0]
    part = retained_table_parts(view, [fragment])[0]
    marker = part["rendered"].partition("\n\n")[0]
    gfm = marker + "\n\n" + render_gfm_rows([
        [""] * fragment.num_cols, *[fragment.rows[row] for row in part["source_rows"]],
    ])
    result.markdown = result.markdown.replace(part["rendered"], gfm)
    FinalContentService().apply(result)
    observation, _ = read_final_observation(build_service_observation(result, sample_id="sample"))
    assert observation["errors"] == []
    assert any(c["text"] == "11" and c.get("column_header_path") == ["Year ended", "2034"]
               for c in _cells(observation))
    assert len([c for c in _cells(observation) if c["text"] == "13"]) == 1
    unit = {"id": "beta", "kind": "table_record", "reference_text": "Beta", "pages": [1],
            "table": {"row_header_path": ["Beta"], "fields": [
                {"column_header_path": ["Year ended", "2034"], "value": "13"},
                {"column_header_path": ["Year ended", "2033"], "value": "5"},
            ]}}
    _rows, metrics = _score_records([unit], observation, True, match_units([unit], observation))
    assert metrics["correct_fields"] == 1


def test_textual_math_label_note_is_read_from_actual_prose_with_unchanged_scoring():
    from app.services.final_content_service import FinalContentService
    from app.services.table_context_service import native_scopes

    fragment = _fragment([["Item", "2034"], [r"Other \( Cash^1 \)", "17"]], headers=False)
    fragment.source_kind = "mineru"
    fragment.native_evidence = native_scopes(fragment)
    fragment.source_header_scopes = fragment.native_evidence["header_scopes"]
    note = "1 Includes collateral held by this fund."
    fragment.context_refs = (TextRef("t1", 1, "n1", note, "note", 0, len(note), (1,), (0, 1)),)
    view = bind_table_view("view", [fragment], [fragment])
    result = _result(render_semantic_view(view, [fragment]))
    result._table_fragments, result._semantic_tables = [fragment], [view]
    FinalContentService().apply(result)
    observation, _ = read_final_observation(build_service_observation(result, sample_id="sample"))
    assert "Other Cash（附注标记：1）" in result.markdown
    assert observation["errors"] == []
    unit = {"id": "other", "kind": "table_record", "reference_text": "Other Cash", "pages": [1],
            "table": {"row_header_path": ["Other Cash"], "fields": [
                {"column_header_path": ["2034"], "value": "17", "period": "2034", "notes": ["1"]},
            ]}}
    _rows, metrics = _score_records([unit], observation, True, match_units([unit], observation))
    assert metrics["information_correct_fields"] == 1


def test_partial_view_cannot_recover_a_value_hidden_by_a_changed_final_rendering():
    result = _partial_result()
    result.markdown = result.markdown.replace("20", "99")
    observation = build_service_observation(result, sample_id="sample")
    assert not any(c["text"] == "20" for c in _cells(observation))
    # A changed residual value must not hide its unchanged converted neighbor.
    # Read the actual new literal, without giving it the old source-cell ref.
    assert observation["service_output"]["semantic_views"][0]["final_evidence"] == "partial"
    changed = next(c for c in _cells(observation) if c["text"] == "99")
    assert "source_cell_ref" not in changed


def test_explicit_row_group_path_is_emitted_and_read_from_the_actual_semantic_text():
    fragment = _fragment([["Group", "Item", "Value"], ["Segment A", "Revenue", "100"]])
    group, subject, value = (CellRef("t1", 1, col) for col in range(3))
    relation = ValueRelation(value, (group, subject), (CellRef("t1", 0, 2),))
    record = SemanticRecord("t1", 1, (relation,), subject, (CellRef("t1", 0, 1),), (group,))
    view = SemanticTableView("group-t1", ("t1",), "converted", "records", (record,))
    result = _result(render_semantic_view(view, [fragment]))
    result._table_fragments, result._semantic_tables = [fragment], [view]
    observation = build_service_observation(result, sample_id="sample")
    observed_value = next(c for c in _cells(observation) if c.get("column_header_path") == ["Value"])
    assert observed_value["row_header_path"] == ["Segment A", "Revenue"]
    assert observed_value["text"] == "100"


def test_explicit_field_label_separator_is_not_duplicated_by_readback():
    fragment = _fragment([["Amount:", "100"]], headers=False)
    relation = ValueRelation(CellRef("t1", 0, 1), (CellRef("t1", 0, 0),))
    record = SemanticRecord("t1", 0, (relation,))
    view = SemanticTableView("colon-t1", ("t1",), "converted", "fields", (record,))
    result = _result(render_semantic_view(view, [fragment]))
    result._table_fragments, result._semantic_tables = [fragment], [view]
    observation = build_service_observation(result, sample_id="sample")
    assert any(c["text"] == "100" for c in _cells(observation))
    assert observation["service_output"]["semantic_views"][0]["records"][0]["status"] == "converted"


def test_only_real_final_markdown_is_text_never_page_native_or_plain_fallback():
    result = _result("# Actual final\n\nActual final body.")
    observation = build_service_observation(result, sample_id="sample")
    text = "\n".join(candidate["text"] for candidate in observation_candidates(observation))
    assert text == "Actual final\nActual final body."
    assert "HIDDEN" not in text
    result.markdown = ""
    assert observation_candidates(build_service_observation(result, sample_id="sample")) == []


def test_converted_cells_are_actual_final_spans_with_explicit_refs_and_qualifiers():
    result, _, _ = _converted()
    before = deepcopy(result)
    observation = build_service_observation(result, sample_id="sample")
    cells = _cells(observation)
    value = next(cell for cell in cells if cell.get("column_header_path") == ["金额"])
    assert value["text"] == "100"
    assert value["row_header_path"] == ["收入"]
    assert value["unit"] == "万元" and value["period"] == "2025年度"
    assert value["notes"] == ["含税"] and "note_markers" not in value
    assert value["source_cell_ref"]["token"] == "t1.r1c1"
    for cell in cells:
        start, end = cell["final_markdown_span"]
        assert result.markdown[start:end] == cell["text"]
    assert any(edge["type"] == "label_value" for edge in observation["relations"])
    assert observation["service_output"]["semantic_views"][0]["final_evidence"] == "converted"
    assert len(observation["service_output"]["semantic_views"]) == 1
    assert result == before and result._semantic_tables == before._semantic_tables


def test_unrendered_or_changed_semantic_values_are_not_recovered_from_private_cells():
    result, _, _ = _converted()
    result.markdown = result.markdown.replace("100", "900")
    observation = build_service_observation(result, sample_id="sample")
    assert not _cells(observation)
    assert "100" not in [candidate["text"] for candidate in observation_candidates(observation)]
    assert "900" in "\n".join(
        candidate["text"] for candidate in observation_candidates(observation)
    )
    assert observation["service_output"]["semantic_views"][0]["final_evidence"] == "unknown"


def test_ambiguous_final_rendering_never_creates_semantic_field_evidence():
    result, _, view = _converted()
    result.markdown += "\n\n" + render_semantic_view(view, result._table_fragments)
    observation = build_service_observation(result, sample_id="sample")
    assert _cells(observation) == []
    assert (
        observation["service_output"]["semantic_views"][0]["reason"]
        == "semantic_rendering_not_uniquely_present"
    )


@pytest.mark.parametrize("state", ["literal", "source_blank"])
def test_empty_literal_and_explicit_blank_keep_distinct_final_evidence(state):
    result, _, _ = _converted(text="", state=state)
    observation = build_service_observation(result, sample_id="sample")
    value = next(cell for cell in _cells(observation) if cell.get("column_header_path") == ["金额"])
    assert value["text"] == "" and value["value_state"] == state
    start, end = value["final_markdown_span"]
    assert result.markdown[start:end] == ("（原表留空）" if state == "source_blank" else "")


def test_actual_retained_owned_grid_is_available_without_claiming_conversion():
    fragment = _fragment([["项目", "金额"], ["收入", "100"]])
    result = _result("Before.\n\n" + fragment.rendered + "\n\nAfter.")
    result._table_fragments = [fragment]
    result._semantic_tables = [
        SemanticTableView("t1", ("t1",), "retained", "unknown", reason_codes=("unbound",))
    ]
    observation = build_service_observation(result, sample_id="sample")
    cells = _cells(observation)
    assert {cell["text"] for cell in cells} == {"项目", "金额", "收入", "100"}
    assert all(cell["service_evidence_state"] == "retained" for cell in cells)
    assert next(cell for cell in cells if cell["text"] == "金额")["is_column_header"] is True
    assert (
        next(cell for cell in cells if cell["text"] == "100")["source_cell_ref"]["token"]
        == "t1.r1c1"
    )
    state = observation["service_output"]["semantic_views"][0]
    assert state["status"] == "retained" and state["retained_grid_present"] is True
    assert state["final_evidence"] == "retained"
    text = "\n".join(candidate["text"] for candidate in observation_candidates(observation))
    assert text.count("100") == 1 and "Before." in text and "After." in text


def test_source_owned_view_prevents_duplicate_fragment_readback():
    fragment = _fragment([["项目", "金额"], ["收入", "100"]])
    result = _result(fragment.rendered)
    result._table_fragments = [fragment]
    result._table_views = [TableSourceView("view", (fragment,), fragment.rendered)]
    observation = build_service_observation(result, sample_id="sample")
    assert len(_cells(observation)) == 4 and not observation["errors"]


def test_synthetic_display_header_is_not_a_real_source_row_or_header_role():
    fragment = _fragment([["甲", "乙"], ["丙", "丁"]], headers=False)
    result = _result(fragment.rendered)
    result._table_fragments = [fragment]
    cells = _cells(build_service_observation(result, sample_id="sample"))
    assert [(cell["row"], cell["col"], cell["text"]) for cell in cells] == [
        (0, 0, "甲"),
        (0, 1, "乙"),
        (1, 0, "丙"),
        (1, 1, "丁"),
    ]
    assert all(not cell.get("is_column_header") for cell in cells)


def test_hidden_grid_or_ambiguous_ownership_never_exposes_ir_cells():
    fragment = _fragment()
    for markdown in ("Actual final text.", fragment.rendered + "\n\n" + fragment.rendered):
        result = _result(markdown)
        result._table_fragments = [fragment]
        assert _cells(build_service_observation(result, sample_id="sample")) == []


def test_declared_page_mapping_does_not_assign_unknown_prose_a_fake_single_page():
    result, _, _ = _converted()
    result.page_count = result.processed_pages = 2
    observation = build_service_observation(result, sample_id="sample", provenance_pages=[41, 42])
    assert observation["pages"][0]["page"] is None
    prose = next(block for block in observation["pages"][0]["blocks"] if block["kind"] == "heading")
    assert prose["provenance_pages"] == [41, 42]
    assert all(cell["page"] == 41 for cell in _cells(observation))


def test_partial_state_and_metadata_are_preserved_without_overriding_output():
    result = _result("Final.", pages=2)
    result.processed_pages = 1
    result.pages[1].status = "failed"
    metadata = {"suite": "quality800", "timing": {"service_seconds": 1.5}}
    observation = build_service_observation(result, sample_id="sample", metadata=metadata)
    assert observation["status"] == "partial"
    observation["timing"]["service_seconds"] = 3
    assert metadata["timing"]["service_seconds"] == 1.5
    with pytest.raises(ValueError, match="metadata"):
        build_service_observation(result, sample_id="sample", metadata={"pages": []})
    with pytest.raises(ValueError, match="provenance pages"):
        build_service_observation(result, sample_id="sample", provenance_pages=[99])


def test_multiple_qualifier_refs_are_not_invented_as_one_unit_or_note_marker():
    result, _, view = _converted()
    record = view.records[0]
    value = replace(record.values[0], unit_refs=(CellRef("t1", 1, 2), CellRef("t1", 1, 3)))
    view = replace(view, records=(replace(record, values=(value,)),))
    result._semantic_tables = [view]
    result.markdown = render_semantic_view(view, result._table_fragments)
    observation = build_service_observation(result, sample_id="sample")
    cell = next(cell for cell in _cells(observation) if cell.get("column_header_path"))
    assert cell["units"] == ["万元", "2025年度"] and "unit" not in cell


def test_existing_field_scorer_accepts_only_explicit_final_paths_synthetic():
    result, _, _ = _converted()
    observation = build_service_observation(result, sample_id="sample")
    unit = {
        "id": "record",
        "kind": "table_record",
        "reference_text": "收入",
        "pages": [1],
        "table": {
            "row_header_path": ["收入"],
            "fields": [
                {
                    "column_header_path": ["金额"],
                    "value": "100",
                    "unit": "万元",
                    "period": "2025年度",
                }
            ],
        },
    }
    matching = match_units([unit], observation)
    rows, metrics = _score_records([unit], observation, True, matching)
    assert metrics["target_fields"] == 1 and metrics["correct_fields"] == 1
    assert rows[0]["fields"][0]["binding"]["correct"] is True


@pytest.mark.parametrize(('label', 'qualifier'), [('收入(万元)', '万元'), ('收益率(%)', '%')])
def test_qualifier_inside_a_header_is_not_misreported_as_an_explicit_unit_value(label, qualifier):
    result, fragment, view = _converted()
    fragment.cells[5].text = label
    relation = replace(view.records[0].values[0], unit_refs=(CellRef('t1', 1, 0),))
    record = replace(view.records[0], values=(relation,))
    view = replace(view, records=(record,))
    result._semantic_tables = [view]
    result.markdown = render_semantic_view(view, [fragment])
    observation = build_service_observation(result, sample_id='invented')
    value = next(cell for cell in _cells(observation) if cell['text'] == '100')
    assert 'unit' not in value and value['units'] == [label]
    unit = {'id': 'r', 'kind': 'table_record', 'pages': [1], 'reference_text': label,
            'table': {'row_header_path': [label], 'fields': [
                {'column_header_path': ['金额'], 'value': '100', 'unit': qualifier}]}}
    rows, _metrics = _score_records([unit], observation, True, match_units([unit], observation))
    assert rows[0]['fields'][0]['information']['status'] == 'correct'


def test_explicit_wrong_unit_cannot_be_rescued_by_a_correct_unit_in_another_label():
    result, fragment, view = _converted()
    fragment.cells[5].text = '收入(万元)'
    fragment.cells[7].text = '美元'
    result.markdown = render_semantic_view(view, [fragment])
    observation = build_service_observation(result, sample_id='invented')
    unit = {'id': 'r', 'kind': 'table_record', 'pages': [1], 'reference_text': '收入(万元)',
            'table': {'row_header_path': ['收入(万元)'], 'fields': [
                {'column_header_path': ['金额'], 'value': '100', 'unit': '万元'}]}}
    rows, _metrics = _score_records([unit], observation, True, match_units([unit], observation))
    assert rows[0]['fields'][0]['information']['status'] == 'incorrect'


def test_unrelated_ambiguous_cells_do_not_erase_valid_final_semantic_neighbors():
    result, _, _ = _converted()
    unrelated = _fragment([["Other", "Hidden"]], name="unrelated")
    result._table_fragments.extend([unrelated, deepcopy(unrelated)])
    observation = build_service_observation(result, sample_id="sample")
    assert (
        next(cell for cell in _cells(observation) if cell.get("column_header_path"))["text"]
        == "100"
    )
    assert observation["errors"][0]["table_id"] == "unrelated"


def test_literal_escaping_and_repeated_reference_qualifiers_come_from_final_chars():
    result, _, view = _converted(text="**100** & 9")
    record = view.records[0]
    value = replace(record.values[0], unit_refs=(CellRef("t1", 0, 1), CellRef("t1", 0, 1)))
    view = replace(view, records=(replace(record, values=(value,)),))
    result._semantic_tables = [view]
    result.markdown = render_semantic_view(view, result._table_fragments)
    observation = build_service_observation(result, sample_id="sample")
    value_cell = next(cell for cell in _cells(observation) if cell.get("column_header_path"))
    assert value_cell["text"] == "**100** & 9" and value_cell["units"] == ["金额"]
    start, end = value_cell["final_markdown_span"]
    assert result.markdown[start:end] == r"\*\*100\*\* &amp; 9"
    assert sum(cell["text"] == "金额" for cell in _cells(observation)) == 1


def test_retained_grid_is_scored_by_existing_reader_without_semantic_conversion():
    fragment = _fragment([["项目", "金额"], ["收入", "100"]])
    result = _result(fragment.rendered)
    result._table_fragments = [fragment]
    observation = build_service_observation(result, sample_id="sample")
    unit = {
        "id": "record",
        "kind": "table_record",
        "reference_text": "收入",
        "pages": [1],
        "table": {
            "row_header_path": ["收入"],
            "fields": [{"column_header_path": ["金额"], "value": "100"}],
        },
    }
    _rows, metrics = _score_records([unit], observation, True, match_units([unit], observation))
    assert metrics["target_fields"] == metrics["correct_fields"] == 1
    summary = observation["service_output"]["conversion_summary"]
    assert summary["final_converted_views"] == 0 and summary["final_retained_views"] == 1


def test_unknown_internal_classification_does_not_hide_an_actually_printed_gfm_grid():
    fragment = _fragment([["项目", "金额"], ["收入", "100"]])
    result = _result(fragment.rendered)
    result._table_fragments = [fragment]
    observation = build_service_observation(result, sample_id="sample")
    for cell in _cells(observation):
        for key in ("row", "col", "row_span", "col_span", "is_column_header", "is_row_header"):
            cell.pop(key, None)
        cell["service_grid_scope_state"] = "unknown"
    before = deepcopy(observation)
    derived, diagnostic = read_final_observation(observation)
    assert observation == before
    assert diagnostic["retained_gfm_geometry_blocks"] == 1
    value = next(c for c in _cells(derived) if c["text"] == "100")
    assert (value["row"], value["col"]) == (1, 1)
    assert "row_header_path" not in value and not value.get("is_row_header")
    unit = {"id": "record", "kind": "table_record", "reference_text": "收入", "pages": [1],
            "table": {"row_header_path": ["收入"], "fields": [{"column_header_path": ["金额"], "value": "100"}]}}
    _rows, metrics = _score_records([unit], derived, True, match_units([unit], derived))
    assert metrics["correct_fields"] == 1


def test_plain_text_or_headerless_fragment_cannot_acquire_geometry_from_hidden_metadata():
    from moparse_eval.service_observation import _read_retained_gfm_geometry
    for raw in ("Item 2024\nRevenue 17", "| Revenue | 17 |"):
        observed = {"service_output": {"final_markdown": raw}, "pages": [{"blocks": [{"text": raw, "final_markdown_span": [0, len(raw)],
                     "service_evidence_state": "retained", "cells": [{"text": "17", "final_markdown_span": [0, 2],
                     "source_cell_ref": {"row": 1, "column": 1}}]}]}]}
        assert _read_retained_gfm_geometry(observed) == 0
        assert "row" not in observed["pages"][0]["blocks"][0]["cells"][0]


def test_unprinted_source_header_span_cannot_credit_flat_gfm_but_explicit_prose_can():
    from app.services.table_context_service import native_scopes
    from moparse_eval.scoring import score_case
    fragment = _fragment([["Item", "2024", ""], ["", "Amount", "Ratio"], ["Revenue", "17", "5%"]])
    fragment.source_kind = "mineru"
    next(c for c in fragment.cells if (c.row, c.column) == (0, 0)).row_span = 2
    next(c for c in fragment.cells if (c.row, c.column) == (0, 1)).column_span = 2
    fragment.cells = [c for c in fragment.cells if (c.row, c.column) not in {(0, 2), (1, 0)}]
    for cell in fragment.cells:
        cell.is_column_header = cell.row < 2
    fragment.native_evidence = native_scopes(fragment)
    fragment.source_header_scopes = fragment.native_evidence["header_scopes"]
    reference = {"sample_id": "sample", "review_status": "confirmed", "units": [{
        "id": "record", "kind": "table_record", "literal": "Revenue", "status": "confirmed", "pages": [1],
        "table": {"row_header_path": ["Revenue"], "fields": [{"column_header_path": ["2024", "Ratio"],
                    "value": "5%", "unit": "%"}]}}]}
    result = _result(fragment.rendered)
    result._table_fragments = [fragment]
    observed = build_service_observation(result, sample_id="sample")
    derived, _diagnostic = read_final_observation(observed)
    year = next(c for c in _cells(derived) if c["text"] == "2024")
    assert year["col_span"] == 1
    assert score_case(reference, derived)["units"][0]["fields"][0]["outcome"] == "incorrect"
    view = bind_table_view("view", [fragment], [fragment])
    result.markdown = render_semantic_view(view, [fragment])
    result._semantic_tables = [view]
    final, _diagnostic = read_final_observation(build_service_observation(result, sample_id="sample"))
    assert score_case(reference, final)["units"][0]["fields"][0]["information"]["status"] == "correct"


@pytest.mark.parametrize("first,second,status", [("17", "99", "correct"), ("99", "17", "incorrect")])
def test_actual_gfm_tables_do_not_share_totals_through_a_private_parent(first, second, status):
    from moparse_eval.scoring import score_case
    a = _fragment([["Item", "2024"], ["Alpha", "11"], ["Total", first]], name="a")
    b = _fragment([["Item", "2024"], ["Beta", "22"], ["Total", second]], name="b")
    result = _result(a.rendered + "\n\n" + b.rendered)
    result._table_fragments = [a, b]
    observation = build_service_observation(result, sample_id="sample")
    for block in observation["pages"][0]["blocks"]:
        if block.get("cells"):
            block.update(native_table_container="hidden-shared-parent", parent_id="hidden-shared-parent")
    observation.setdefault("native_containers", []).append({"id": "hidden-shared-parent", "label": "table"})
    derived, _diagnostic = read_final_observation(observation)
    reference = {"sample_id": "sample", "review_status": "confirmed", "units": [
        {"id": label, "kind": "table_record", "literal": label, "status": "confirmed", "pages": [1],
         "table": {"id": "authored-a", "row_header_path": [label],
                   "fields": [{"column_header_path": ["2024"], "value": value}]}}
        for label, value in (("Alpha", "11"), ("Total", "17"))]}
    scored = score_case(reference, derived)
    total = next(u for u in scored["units"] if u["id"] == "Total")["fields"][0]
    assert total["native_text"] == first and total["information"]["status"] == status
    repeated, _diagnostic = read_final_observation(derived)
    assert score_case(reference, repeated)["metrics"] == scored["metrics"]


def test_final_page_comments_resolve_repeated_text_without_mutating_raw_or_timing():
    final = "<!-- page: 1 -->\n\nRepeated sentence.\n\n<!-- page: 2 -->\n\nRepeated sentence."
    observation = build_service_observation(
        _result(final, pages=2),
        sample_id="sample",
        metadata={"timing": {"processing_seconds": 12.3}},
    )
    before = deepcopy(observation)
    units = [
        {"id": f"u{page}", "kind": "text", "reference_text": "Repeated sentence.", "pages": [page]}
        for page in (1, 2)
    ]
    assert not match_units(units, observation)["matches"]
    derived, diagnostic = read_final_page_provenance(observation)
    assert set(match_units(units, derived)["matches"]) == {"u1", "u2"}
    assert diagnostic["status"] == "completed" and diagnostic["updated_blocks"] == 2
    assert observation == before and derived["timing"] == before["timing"]
    for raw_page, final_page in zip(observation["pages"], derived["pages"], strict=True):
        for raw_block, final_block in zip(raw_page["blocks"], final_page["blocks"], strict=True):
            assert {
                key: value for key, value in raw_block.items() if key != "provenance_pages"
            } == {key: value for key, value in final_block.items() if key != "provenance_pages"}
    assert read_final_page_provenance(derived)[0] == derived


def test_block_crossing_real_page_comments_retains_unknown_range():
    final = "<!-- page: 1 -->\n\nFirst.\n\n<!-- page: 2 -->\n\nSecond."
    observation = build_service_observation(_result(final, pages=2), sample_id="sample")
    block = observation["pages"][0]["blocks"][0]
    start = final.index("First.")
    block.update(
        native_path=f"#/markdown/{start}:{len(final)}",
        final_markdown_span=[start, len(final)],
        text=final[start:],
    )
    observation["pages"][0]["blocks"] = [block]
    derived, diagnostic = read_final_page_provenance(observation)
    assert derived["pages"][0]["blocks"][0]["provenance_pages"] == [1, 2]
    assert diagnostic["status"] == "partial"
    assert diagnostic["blocks"][0]["reason"] == "block_crosses_page_declarations"


@pytest.mark.parametrize(
    "fake", ["```html\n<!-- page: 2 -->\n```", "`<!-- page: 2 -->`", "    <!-- page: 2 -->"]
)
def test_commonmark_code_comments_never_supply_a_missing_page_marker(fake):
    final = "<!-- page: 1 -->\n\nFirst.\n\n" + fake
    observation = build_service_observation(_result(final, pages=2), sample_id="sample")
    derived, diagnostic = read_final_page_provenance(observation)
    assert derived == observation and diagnostic["status"] == "unknown"
    assert [marker["page"] for marker in diagnostic["markers"]] == [1]


@pytest.mark.parametrize(
    "markers",
    ["<!-- page: 1 -->\n\nOnly.", "<!-- page: 1 -->\n\nFirst.\n\n<!-- page: 1 -->\n\nSecond."],
)
def test_incomplete_or_duplicate_marker_declarations_never_narrow_pages(markers):
    observation = build_service_observation(_result(markers, pages=2), sample_id="sample")
    derived, diagnostic = read_final_page_provenance(observation)
    assert derived == observation and diagnostic["status"] == "unknown"


def test_display_page_never_overwrites_explicit_table_cell_source_pages():
    result, fragment, _ = _converted()
    fragment.page_number = 2
    result.page_count = result.processed_pages = 2
    result.markdown = "<!-- page: 1 -->\n\n" + result.markdown + "\n\n<!-- page: 2 -->\n\nPage two."
    observation = build_service_observation(result, sample_id="sample")
    raw_table = next(block for block in observation["pages"][0]["blocks"] if block.get("cells"))
    assert raw_table["provenance_pages"] == [2]
    derived, diagnostic = read_final_page_provenance(observation)
    table = next(block for block in derived["pages"][0]["blocks"] if block.get("cells"))
    assert table == raw_table
    assert any(
        row["reason"] == "explicit_table_cell_source_provenance" for row in diagnostic["blocks"]
    )


def test_explicit_marker_sequence_is_read_without_repairing_actual_order():
    final = "<!-- page: 2 -->\n\nRepeated sentence.\n\n<!-- page: 1 -->\n\nRepeated sentence."
    observation = build_service_observation(_result(final, pages=2), sample_id="sample")
    derived, diagnostic = read_final_page_provenance(observation)
    assert [marker["page"] for marker in diagnostic["markers"]] == [2, 1]
    assert [block["provenance_pages"] for block in derived["pages"][0]["blocks"]] == [[2], [1]]
    assert [block["native_sequence"] for block in derived["pages"][0]["blocks"]] == [[0], [1]]


def test_conflicting_character_ranges_and_other_coordinate_frames_remain_unknown():
    observation = build_service_observation(
        _result("<!-- page: 1 -->\n\nFinal."), sample_id="sample"
    )
    block = observation["pages"][0]["blocks"][0]
    block["final_markdown_span"][1] -= 1
    derived, diagnostic = read_final_page_provenance(observation)
    assert derived == observation and diagnostic["status"] == "partial"
    assert diagnostic["blocks"][0]["reason"] == "final_character_range_conflict"
    block["final_markdown_span"][1] += 1
    block["provenance_pages"] = [41]
    derived, diagnostic = read_final_page_provenance(observation)
    assert derived == observation and diagnostic["status"] == "partial"
    assert diagnostic["blocks"][0]["reason"] == "existing_page_coordinate_frame_unavailable"


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_real_join_pages_formfeed_preserves_all_text_and_explicit_page_identity(newline):
    final, _ = ExportService().join_pages(
        [
            PageParseResult(page_number=1, content="Repeated sentence."),
            PageParseResult(page_number=2, content="Repeated sentence."),
        ],
        preserve_page_breaks=True,
    )
    assert "\f" in final
    final = final.replace("\n", newline)
    observation = build_service_observation(_result(final, pages=2), sample_id="sample")
    assert [candidate["text"] for candidate in observation_candidates(observation)] == [
        "Repeated sentence.",
        "Repeated sentence.",
    ]
    derived, diagnostic = read_final_observation(observation)
    units = [
        {"id": f"u{page}", "kind": "text", "reference_text": "Repeated sentence.", "pages": [page]}
        for page in (1, 2)
    ]
    assert set(match_units(units, derived)["matches"]) == {"u1", "u2"}
    assert (
        diagnostic["status"] == "completed"
        and diagnostic["source_scope"] == "current_repaired_build_only"
    )


@pytest.mark.parametrize("code", ["```html\n<!-- page: 3 -->\n```", "    <!-- page: 3 -->"])
def test_real_formfeed_pages_keep_code_and_reject_code_fake_page_comments(code):
    final, _ = ExportService().join_pages(
        [
            PageParseResult(page_number=1, content="First.\n\n" + code),
            PageParseResult(page_number=2, content="Second."),
        ],
        preserve_page_breaks=True,
    )
    observation = build_service_observation(_result(final, pages=2), sample_id="sample")
    assert [candidate["text"] for candidate in observation_candidates(observation)] == [
        "First.",
        "<!-- page: 3 -->",
        "Second.",
    ]
    derived, diagnostic = read_final_observation(observation)
    assert diagnostic["status"] == "completed"
    assert [marker["page"] for marker in diagnostic["markers"]] == [1, 2]
    assert [block["provenance_pages"] for block in derived["pages"][0]["blocks"]] == [[1], [1], [2]]


@pytest.mark.parametrize("converted", [False, True])
def test_real_formfeed_pages_preserve_owned_retained_and_converted_cell_blocks(converted):
    if converted:
        result, fragment, view = _converted()
        body = render_semantic_view(view, [fragment])
    else:
        fragment = _fragment([["项目", "金额"], ["收入", "100"]], page=2)
        result = _result()
        result._table_fragments = [fragment]
        body = fragment.rendered
    fragment.page_number = 2
    result.page_count = result.processed_pages = 2
    result.markdown, _ = ExportService().join_pages(
        [
            PageParseResult(page_number=1, content="First."),
            PageParseResult(page_number=2, content=body),
        ],
        preserve_page_breaks=True,
    )
    observation = build_service_observation(result, sample_id="sample")
    raw_table = next(block for block in observation["pages"][0]["blocks"] if block.get("cells"))
    derived, diagnostic = read_final_observation(observation)
    table = next(block for block in derived["pages"][0]["blocks"] if block.get("cells"))
    assert table["text"] == raw_table["text"] and table["final_markdown_span"] == raw_table["final_markdown_span"]
    if converted:
        assert table == raw_table
    else:
        assert table["provenance_pages"] == [2]
        assert next(cell for cell in table["cells"] if cell["text"] == "100")["page"] == 2
    assert "100" in [candidate["text"] for candidate in observation_candidates(derived)]
    assert "First." in [candidate["text"] for candidate in observation_candidates(derived)]
    assert diagnostic["status"] == "completed"


@pytest.mark.parametrize("separator", ["\f", "\u2028", "\u2029", "\v"])
def test_unicode_whitespace_inside_final_grid_never_moves_cell_character_spans(separator):
    fragment = _fragment([["项目", "金额"], ["收入", "100" + separator + "万元"]])
    result = _result(fragment.rendered)
    result._table_fragments = [fragment]
    observation = build_service_observation(result, sample_id="sample")
    value = next(cell for cell in _cells(observation) if cell["text"].startswith("100"))
    start, end = value["final_markdown_span"]
    assert result.markdown[start:end] == "100" + separator + "万元"
    assert not observation["errors"]


def test_readback_does_not_accept_superseded_execution_observation_builds():
    observation = build_service_observation(_result("Final."), sample_id="sample")
    observation["service_output"]["reader_version"] = "superseded-synthetic-build"
    with pytest.raises(ValueError, match="current repaired"):
        read_final_observation(observation)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("-", "-"),
        ("*", "*"),
        ("1.", "1."),
        ("---", "---"),
        ("&lt;sup&gt;4&lt;/sup&gt;", "<sup>4</sup>"),
        ("&amp;lt;", "&lt;"),
        ("<b>label</b>", "label"),
        ("`**literal** &amp; <b>`", "**literal** &amp; <b>"),
        ("  a  b  ", "  a  b  "),
        ("a\\\nb", "a\nb"),
        ("", ""),
        ("   ", "   "),
    ],
)
def test_single_field_uses_inline_syntax_without_block_reinterpretation(source, expected):
    assert _inline_text(source) == expected


@pytest.mark.parametrize("value", ["-", "*", "1.", "---", "<sup>4</sup>"])
def test_retained_grid_markers_and_escaped_html_are_real_final_cell_text(value):
    fragment = _fragment([["项目", "金额"], ["收入", value]])
    result = _result(fragment.rendered)
    result._table_fragments = [fragment]
    observation = build_service_observation(result, sample_id="sample")
    actual = next(
        cell
        for cell in _cells(observation)
        if cell.get("source_cell_ref", {}).get("token") == "t1.r1c1"
    )
    assert actual["text"] == value
    start, end = actual["final_markdown_span"]
    assert _inline_text(result.markdown[start:end]) == value
    assert actual["service_evidence_state"] == "retained"


@pytest.mark.parametrize("value", ["-", "*", "1.", "---", "<sup>4</sup>"])
def test_converted_values_keep_inline_markers_and_same_scorer_field_correctness(value):
    result, _, _ = _converted(text=value)
    observation = build_service_observation(result, sample_id="sample")
    actual = next(
        cell for cell in _cells(observation) if cell.get("column_header_path") == ["金额"]
    )
    assert actual["text"] == value and actual["value_state"] == "literal"
    unit = {
        "id": "record",
        "kind": "table_record",
        "reference_text": "收入",
        "pages": [1],
        "table": {
            "row_header_path": ["收入"],
            "fields": [{"column_header_path": ["金额"], "value": value}],
        },
    }
    _rows, metrics = _score_records([unit], observation, True, match_units([unit], observation))
    assert metrics["correct_fields"] == metrics["compared_fields"] == 1


def test_inline_code_in_final_gfm_is_read_as_code_not_as_emphasis():
    fragment = _fragment([["项目", "金额"], ["收入", "`**literal**`"]])
    result = _result(fragment.rendered)
    result._table_fragments = [fragment]
    actual = next(
        cell
        for cell in _cells(build_service_observation(result, sample_id="sample"))
        if cell.get("source_cell_ref", {}).get("token") == "t1.r1c1"
    )
    assert actual["text"] == "**literal**"


def test_actual_html_spans_survive_delivery_and_private_spans_cannot_repair_missing_markup():
    from app.services.table_service import table_view
    from moparse_eval.scoring import score_case
    fragment = _fragment([['Metric', '2024', ''], ['', 'North', 'South'], ['Revenue', '17', '11']])
    fragment.cells = [cell for cell in fragment.cells if (cell.row, cell.column) not in {(0, 2), (1, 0)}]
    fragment.cells[0].row_span = 2
    fragment.cells[1].column_span = 2
    marker, rendered = table_view(fragment)
    assert '<td colspan="2">2024</td>' in rendered
    fragment.rendered = marker + '\n\n' + rendered
    result = _result(fragment.rendered)
    result._table_fragments = [fragment]
    reference = {'sample_id': 'invented', 'review_status': 'confirmed', 'units': [
        {'id': 'r', 'kind': 'table_record', 'status': 'confirmed', 'literal': 'Revenue', 'pages': [1],
         'table': {'row_header_path': ['Revenue'], 'fields': [
             {'column_header_path': ['2024', 'South'], 'value': '11'}]}}]}
    observation, _ = read_final_observation(build_service_observation(result, sample_id='invented'))
    assert score_case(reference, observation)['units'][0]['fields'][0]['outcome'] == 'correct'
    value = next(cell for cell in _cells(observation) if cell['text'] == '11')
    a, b = value['final_markdown_span']
    assert result.markdown[a:b] == '11'
    # The private source still has its span; only the real HTML has changed.
    fragment.rendered = rendered.replace(' colspan="2"', '')
    result.markdown = fragment.rendered
    observation, _ = read_final_observation(build_service_observation(result, sample_id='invented'))
    assert score_case(reference, observation)['units'][0]['fields'][0]['outcome'] == 'incorrect'


def test_span_display_keeps_source_literal_signs_and_embedded_images_on_the_existing_path():
    from app.services.table_service import render_source_rows
    rows = [['Group', ''], ['(17)', '< 11 & 5%']]
    original = deepcopy(rows)
    rendered = render_source_rows(rows, [[0, 0, 1, 2]])
    assert '(17)' in rendered and '&lt; 11 &amp; 5%' in rendered and rows == original
    image = [['![source](assets/source.png)', ''], ['Label', '17']]
    assert render_source_rows(image, [[0, 0, 1, 2]]).startswith('| ')


@pytest.mark.parametrize('legacy', [False, True])
def test_embedded_column_unit_readback_uses_the_printed_current_or_saved_format(legacy):
    fragment = _fragment([["Item", "2024$m"], ["Average pool ($bn)", "17.0"]])
    value = ValueRelation(CellRef('t1', 1, 1), (CellRef('t1', 1, 0),),
                          (CellRef('t1', 0, 1),), (CellRef('t1', 1, 0),))
    record = SemanticRecord('t1', 1, (value,), CellRef('t1', 1, 0), (CellRef('t1', 0, 0),))
    view = SemanticTableView('view-t1', ('t1',), 'converted', 'records', (record,))
    markdown = render_semantic_view(view, [fragment])
    if legacy:
        markdown = markdown.replace('2024：', '2024$m：')
    result = _result(markdown)
    result._table_fragments, result._semantic_tables = [fragment], [view]
    observation = build_service_observation(result, sample_id='invented')
    cell = next(cell for cell in _cells(observation) if cell['text'] == '17.0')
    assert cell['column_header_path'] == ['2024$m' if legacy else '2024']
    assert cell['row_header_path'] == ['Average pool ($bn)']
    for cell in _cells(observation):
        a, b = cell['final_markdown_span']
        assert cell['text'] == _inline_text(markdown[a:b])


def test_an_unprinted_row_unit_cannot_be_restored_from_the_private_record():
    fragment = _fragment([["Item", "2024$m"], ["Average pool ($bn)", "17.0"]])
    value = ValueRelation(CellRef('t1', 1, 1), (CellRef('t1', 1, 0),),
                          (CellRef('t1', 0, 1),), (CellRef('t1', 1, 0),))
    record = SemanticRecord('t1', 1, (value,), CellRef('t1', 1, 0))
    view = SemanticTableView('view-t1', ('t1',), 'converted', 'records', (record,))
    result = _result(render_semantic_view(view, [fragment]).replace('($bn)', '($m)'))
    result._table_fragments, result._semantic_tables = [fragment], [view]
    observation = build_service_observation(result, sample_id='invented')
    assert not any('$bn' in str(cell) for cell in _cells(observation))
