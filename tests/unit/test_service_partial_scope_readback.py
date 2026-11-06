"""Final partial grids retain local header scopes; all examples are authored."""

from __future__ import annotations

import pytest

from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from app.services.table_semantics_service import bind_table_view, render_semantic_view
from app.services.table_service import TableCellFragment, TableFragment, render_gfm_rows
from moparse_eval.service_observation import (
    _inline_text,
    build_service_observation,
    read_final_observation,
)
from moparse_eval.three_layer import read_candidate


def partial_result():
    rows = [
        ["Item", "2024"], ["Good", "111"], ["Revenue", "900"], ["X", ""],
        ["Item", "2023"], ["Cost", "200"], ["Y", ""],
    ]
    cells = [TableCellFragment(r, c, 1, 1, text) for r, values in enumerate(rows)
             for c, text in enumerate(values) if (r, c) not in {(3, 1), (6, 1)}]
    for cell in cells:
        if (cell.row, cell.column) in {(2, 1), (5, 1)}:
            cell.row_span = 2
    markdown = render_gfm_rows(rows)
    fragment = TableFragment("t1", 1, 1, (0.1, 0.1, 0.9, 0.9), len(rows), 2,
                             rows, [], markdown, markdown, cells=cells)
    fragment.pdf_evidence = {"bound": True, "source_cells": [
        {"row": c.row, "column": c.column, "row_span": c.row_span,
         "column_span": c.column_span, "text": c.text, "shaded": False} for c in cells
    ]}
    fragment.source_header_scopes = [
        {"header_rows": [0], "body_rows": [1, 2, 3], "complete": True},
        {"header_rows": [4], "body_rows": [5, 6], "complete": True},
    ]
    view = bind_table_view("view", [fragment], [fragment])
    assert view.status == "partial"
    final = render_semantic_view(view, [fragment])
    result = DocumentParseResult(
        document_id="synthetic", filename="synthetic.pdf", mime_type="application/pdf",
        page_count=1, processed_pages=1, pages=[PageParseResult(page_number=1, content="PRIVATE PAGE")],
        markdown=final, plain_text="PRIVATE PLAIN",
        pipeline=ParsePipeline(profile="balanced", primary="synthetic"),
    )
    result._table_fragments = [fragment]
    result._semantic_tables = [view]
    return result, fragment




def cells(observation):
    return [cell for page in observation["pages"] for block in page["blocks"]
            for cell in block.get("cells", [])]


def test_internal_header_scopes_do_not_lend_columns_to_other_period_records():
    result, _fragment = partial_result()
    observation = build_service_observation(result, sample_id="synthetic")
    assert observation["errors"] == []
    assert read_candidate(observation)["blockers"]
    actual = cells(observation)
    assert len([c for c in actual if c["text"] == "900"]) == 1
    assert len([c for c in actual if c["text"] == "200"]) == 1
    for cell in actual:
        start, end = cell["final_markdown_span"]
        assert _inline_text(result.markdown[start:end]) == cell["text"]
    ranges = [block["final_markdown_span"] for page in observation["pages"] for block in page["blocks"]]
    assert all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:], strict=False))


def test_unshown_private_header_is_not_restored_or_used_as_a_column():
    result, fragment = partial_result()
    next(c for c in fragment.cells if (c.row, c.column) == (4, 1)).text = "PRIVATE HEADER"
    observation = build_service_observation(result, sample_id="synthetic")
    assert all("PRIVATE" not in c["text"] for c in cells(observation))
    assert read_candidate(observation)["blockers"]
    # A conflicting private header also cannot provide trusted scope geometry.
    assert any(c["text"] == "200" for c in cells(observation))


def test_conflicting_scope_membership_keeps_text_but_withholds_relations():
    result, fragment = partial_result()
    fragment.source_header_scopes[0]["body_rows"].extend([4, 5, 6])
    observation = build_service_observation(result, sample_id="synthetic")
    assert read_candidate(observation)["blockers"]
    cost = next(c for c in cells(observation) if c["text"] == "200")
    assert cost["service_grid_scope_state"] == "unknown" and "row" not in cost
    assert result.markdown == observation["service_output"]["final_markdown"]


def test_changed_final_value_does_not_recover_the_private_original():
    result, _fragment = partial_result()
    result.markdown = result.markdown.replace("200", "999")
    observation = build_service_observation(result, sample_id="synthetic")
    assert read_candidate(observation)["blockers"]
    assert not any(c["text"] == "200" for c in cells(observation))


def test_saved_residual_without_an_empty_optional_context_list_is_read_from_its_actual_body():
    result, _fragment = partial_result()
    result.markdown = result.markdown.replace(',"context_rows":[]', '')
    observation = build_service_observation(result, sample_id="authored")
    assert observation["errors"] == []
    assert read_candidate(observation)["blockers"]


def test_empty_context_omission_does_not_permit_changed_residual_coordinates():
    from moparse_eval.service_observation import _printed_marker_forms

    marker = '<!-- semantic-retained: {"source_rows":[1,2],"context_rows":[],"header_rows":[0]} -->'
    forms = _printed_marker_forms(marker)
    assert '<!-- semantic-retained: {"source_rows":[1,2],"header_rows":[0]} -->' in forms
    assert '<!-- semantic-retained: {"source_rows":[2,3],"header_rows":[0]} -->' not in forms
    nonempty = marker.replace('"context_rows":[]', '"context_rows":[1]')
    assert _printed_marker_forms(nonempty) == {nonempty}


@pytest.mark.parametrize("version", [
    "mo-parse-final-output-observation-v4", "mo-parse-final-output-observation-v5",
])
def test_superseded_observation_versions_are_rejected_even_for_stage_names(version):
    result, _fragment = partial_result()
    observed = build_service_observation(result, sample_id="authored")
    observed["pipeline"] = "P07+MO-Parse:assets"
    observed["service_output"]["reader_version"] = version
    with pytest.raises(ValueError, match="current repaired"):
        read_final_observation(observed)


def isolated_leading_result(*, shared_value=False):
    rows = [
        ["Metric", "Current", "Prior"], ["Sales", "700", "600"], ["Profit", "70", "60"],
        ["", "Current end", "Prior end"], ["Assets", "900", "800"],
    ]
    if shared_value:
        rows[2][1] = ""
    cells = [TableCellFragment(r, c, 2 if shared_value and (r, c) == (1, 1) else 1, 1, text)
             for r, values in enumerate(rows) for c, text in enumerate(values)
             if not (shared_value and (r, c) == (2, 1))]
    markdown = render_gfm_rows(rows)
    fragment = TableFragment("isolated", 1, 1, (0.1, 0.1, 0.9, 0.9), len(rows), 3,
                             rows, [], markdown, markdown, cells=cells)
    fragment.pdf_evidence = {"bound": True, "source_cells": [
        {"row": cell.row, "column": cell.column, "row_span": cell.row_span,
         "column_span": cell.column_span, "text": cell.text, "shaded": False} for cell in cells
    ]}
    fragment.source_header_scopes = [{"header_rows": [3], "body_rows": [4], "complete": True}]
    view = bind_table_view("isolated-view", [fragment], [fragment])
    assert view.status == "partial"
    result = DocumentParseResult(
        document_id="authored", filename="authored.pdf", mime_type="application/pdf",
        page_count=1, processed_pages=1, pages=[PageParseResult(page_number=1)],
        markdown=render_semantic_view(view, [fragment]),
        pipeline=ParsePipeline(profile="balanced", primary="authored"),
    )
    result._table_fragments = [fragment]
    result._semantic_tables = [view]
    return result, fragment


def test_isolated_unclassified_residual_retains_visible_grid_without_semantic_roles():
    result, _fragment = isolated_leading_result()
    original = result.markdown
    observation = build_service_observation(result, sample_id="authored")
    assert observation["errors"] == []
    assert read_candidate(observation)["blockers"]
    retained = [cell for cell in cells(observation) if cell.get("service_evidence_state") == "retained"]
    assert retained and all(cell["service_grid_scope_state"] == "geometry_only_unclassified" for cell in retained)
    assert all("row" in cell and "col" in cell for cell in retained)
    assert all(not any(key in cell for key in ("is_column_header", "is_row_header", "row_header_path", "column_header_path"))
               for cell in retained)
    for cell in retained:
        start, end = cell["final_markdown_span"]
        assert _inline_text(original[start:end]) == cell["text"]
    assert original == result.markdown == observation["service_output"]["final_markdown"]


def test_invalid_declared_scope_cannot_be_treated_as_an_absent_scope():
    result, fragment = isolated_leading_result()
    # This declaration intersects the residual but cannot be a valid scope:
    # its body precedes its header. It must not enable the plain-grid fallback.
    fragment.source_header_scopes[0]["body_rows"].append(1)
    result.markdown = render_semantic_view(result._semantic_tables[0], [fragment])
    observation = build_service_observation(result, sample_id="authored")
    assert read_candidate(observation)["blockers"]
    actual = next(cell for cell in cells(observation) if cell["text"] == "700")
    assert actual["service_grid_scope_state"] == "unknown" and "row" not in actual


def test_isolated_unclassified_grid_preserves_exact_span_and_single_value():
    result, _fragment = isolated_leading_result(shared_value=True)
    observation = build_service_observation(result, sample_id="authored")
    actual = [cell for cell in cells(observation) if cell["text"] == "700"]
    assert len(actual) == 1
    assert actual[0]["row_span"] == 2 and actual[0]["col_span"] == 1
    assert actual[0]["service_grid_scope_state"] == "geometry_only_unclassified"
    start, end = actual[0]["final_markdown_span"]
    assert result.markdown[start:end] == "700"


def test_plain_grid_fallback_requires_unique_complete_display_mapping():
    from moparse_eval.service_observation import _isolated_unclassified_grid

    _result, fragment = isolated_leading_result()
    part = {"source_rows": [0, 1, 2], "header_rows": [],
            "source_to_display_rows": {0: 1, 1: 2, 2: 3}}
    assert _isolated_unclassified_grid(part, fragment)
    part["source_to_display_rows"][2] = 2
    assert not _isolated_unclassified_grid(part, fragment)
    part["source_to_display_rows"] = {0: 1, 1: 2}
    assert not _isolated_unclassified_grid(part, fragment)


def test_public_partial_grid_readback_keeps_unlocated_visible_words_and_valid_neighbor_metrics():
    result, _fragment = partial_result()
    observation = build_service_observation(result, sample_id="synthetic")
    graph = read_candidate(observation)
    literals = [entry["text"] for entry in graph["text"]]
    assert all(literal in literals for literal in ("Item", "Good", "2024", "111", "900", "200"))
    assert literals.count("900") == literals.count("200") == 1
    assert not any(edge["type"].startswith("toc_") for edge in graph["relations"])
    assert {(fact["attribute"], fact["value"]) for fact in graph["business"]} == {("Revenue", "900"), ("Cost", "200")}
    [unlocated] = [entry for entry in graph["text"] if entry["text"] == "111"]
    assert unlocated["source"].get("row") is None and unlocated["source"].get("col") is None
    assert any(issue["reason"] == "matrix_cell_position_unavailable" for issue in graph["blockers"])


@pytest.mark.parametrize("geometry", [{}, {"row": False, "col": 0}, {"row": 1, "col": "0"}])
def test_toc_probe_retains_unlocated_cell_text_without_inventing_a_directory_or_positions(geometry):
    from copy import deepcopy

    from moparse_eval.toc_evidence import read_toc

    raw = [{"id": "literal", "native_path": "#/actual/cell", "text": "Revenue", **geometry}]
    before = deepcopy(raw)
    result = read_toc(cells=raw, source={"path": "#/actual/table"})
    assert raw == before
    assert result["matched"] is False and not result["facts"] and not result["relations"]
    assert [item["text"] for item in result["text_atoms"]] == ["Revenue"]
    [pending] = result["unresolved"]
    assert pending["raw_cell"] == raw[0]
    assert not any(item["source"].get("row") == 0 for item in result["text_atoms"])
    assert pending["source"]["cell_position"] == 0


@pytest.mark.parametrize("scope", ["unknown", "geometry_only_unclassified"])
def test_printed_title_page_words_in_an_unclassified_service_grid_do_not_become_navigation(scope):
    from moparse_eval.toc_evidence import read_toc

    raw = [{"id": f"c{row}{col}", "row": row, "col": col, "text": text,
            "service_evidence_state": "retained", "service_grid_scope_state": scope}
           for row, values in enumerate((("Title", "Page"), ("Results", "17"))) for col, text in enumerate(values)]
    result = read_toc(cells=raw, source={"path": "#/unknown-service-grid"})
    assert result["matched"] is False and result["entries"] == result["facts"] == result["relations"] == []
    assert [item["text"] for item in result["text_atoms"]] == ["Title", "Page", "Results", "17"]
    assert len(result["unresolved"]) == 4


@pytest.mark.parametrize("bad", [{"id": "unknown", "text": "Unknown"},
                                 {"id": "unknown", "row": False, "col": 0, "text": "Unknown"}])
def test_explicit_navigation_keeps_its_valid_neighbor_but_withholds_unlocated_cell_relations(bad):
    from moparse_eval.toc_evidence import read_toc

    raw = [{"id": f"c{row}{col}", "row": row, "col": col, "text": text}
           for row, values in enumerate((("Title", "Page"), ("Results", "17"))) for col, text in enumerate(values)]
    result = read_toc(cells=[*raw, bad], source={"path": "#/declared-title-page"})
    assert [(fact["subject"], fact["value"]) for fact in result["facts"]] == [("Results", "17")]
    assert result["matched"] and not result["complete"]
    assert any(atom["text"] == "Unknown" for atom in result["text_atoms"])
    assert any(issue["reason"] == "toc_cell_position_or_scope_unavailable" for issue in result["blockers"])
    assert not any("Unknown" in repr(edge) for edge in result["relations"])


def test_duplicate_toc_positions_do_not_borrow_a_title_and_do_not_erase_other_rows():
    from moparse_eval.toc_evidence import read_toc

    raw = [{"id": f"c{row}{col}", "row": row, "col": col, "text": text}
           for row, values in enumerate((("Title", "Page"), ("Results", "17"), ("Appendix", "23")))
           for col, text in enumerate(values)]
    raw.append({"id": "conflict", "row": 1, "col": 0, "text": "Conflicting title"})
    result = read_toc(cells=raw, source={"path": "#/duplicate-grid"})
    assert [(fact["subject"], fact["value"]) for fact in result["facts"]] == [("Appendix", "23")]
    assert {atom["text"] for atom in result["text_atoms"]} >= {"Results", "Conflicting title", "17", "Appendix", "23"}
    assert result["blockers"] and not result["complete"]


def test_unclosed_service_html_is_not_repaired_and_does_not_hide_a_valid_navigation_neighbor():
    from copy import deepcopy

    from moparse_eval.toc_evidence import read_toc

    broken = '<table><tr><td>Unknown visible value</td></tr>'
    blocks = [{"id": "contents", "kind": "heading", "text": "Contents"},
        {"id": "broken", "kind": "table", "text": broken, "text_format": "html",
         "cells": [{"id": "unknown", "text": "Unknown visible value"}]},
        {"id": "known", "kind": "table", "cells": [
            {"id": f"c{row}{col}", "row": row, "col": col, "text": text}
            for row, values in enumerate((("Title", "Page"), ("Results", "17"))) for col, text in enumerate(values)]}]
    original = deepcopy(blocks)
    result = read_toc(blocks=blocks, source={"path": "#/declared-source"})
    assert blocks == original
    assert [(fact["subject"], fact["value"]) for fact in result["facts"]] == [("Results", "17")]
    assert any(issue["text"] == broken for issue in result["unresolved"])
    assert any(atom["text"] == "Unknown visible value" for atom in result["text_atoms"])
    assert any(issue["reason"] == "toc_embedded_table_boundary_unavailable" for issue in result["blockers"])
    assert not result["text_projection_complete"]
