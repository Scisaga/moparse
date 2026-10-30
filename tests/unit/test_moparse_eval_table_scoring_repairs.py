"""Invented tables only; these tests never read repository reference materials."""

from __future__ import annotations

from copy import deepcopy

import pytest

from moparse_eval.scoring import score_case


def _inputs(*, value="100", extra_fields=(), cells=None, **unit_extra):
    reference = {
        "sample_id": "synthetic", "review_status": "confirmed", "relations": [],
        "units": [{"id": "record", "kind": "table_record", "status": "confirmed", "pages": [1],
                   "literal": "Revenue 2024 100", "table": {
                       "row_header_path": ["Revenue"],
                       "fields": [{"column_header_path": ["2024"], "value": value}, *extra_fields],
                   }, **unit_extra}],
    }
    native_cells = cells if cells is not None else [
        {"id": "year", "row": 0, "col": 1, "text": "2024"},
        {"id": "row", "row": 1, "col": 0, "text": "Revenue"},
        {"id": "value", "row": 1, "col": 1, "text": value},
    ]
    observation = {
        "sample_id": "synthetic", "pipeline": "P-test", "status": "completed", "relations": [],
        "pages": [{"page": 1, "blocks": [{"id": "table", "kind": "table", "cells": native_cells}]}],
    }
    return reference, observation


def _score(reference, observation):
    original = deepcopy((reference, observation))
    result = score_case(reference, observation)
    assert (reference, observation) == original
    metrics = result["metrics"]["table_records"]
    assert metrics["target_fields"] == metrics["graded_fields"]
    assert metrics["target_fields"] == metrics["information_correct_fields"] + metrics["information_incorrect_fields"]
    assert metrics["unresolved_fields"] == 0
    assert metrics["observable_fields"] == metrics["compared_fields"] + metrics["target_missing_fields"]
    for row in result["units"]:
        if row["kind"] == "table_record":
            assert all(item["status"] and item["reason"] for item in row["fields"])
    return result["units"][-1], metrics


@pytest.mark.parametrize("other_header", ["202X", "2024"])
def test_unavailable_or_ambiguous_other_column_does_not_suppress_a_known_field(other_header):
    reference, observation = _inputs(extra_fields=[{"column_header_path": ["2023"], "value": "90"}])
    cells = observation["pages"][0]["blocks"][0]["cells"]
    cells += [{"id": "other-year", "row": 0, "col": 2, "text": other_header},
              {"id": "other-value", "row": 1, "col": 2, "text": "90"}]
    if other_header == "2024":
        cells[0]["text"] = "2023"
        cells[-2]["text"] = "2024"
        cells.append({"id": "duplicate-2023", "row": 2, "col": 2, "text": "2023"})
        # Keep the known 2024 field's expected value at its native position.
        cells[-2]["text"] = "100"
    row, metrics = _score(reference, observation)
    assert row["fields"][0]["status"] == "compared"
    assert row["fields"][0]["content_exact"] is True
    assert row["fields"][1]["outcome"] == "incorrect"
    assert metrics["correct_fields"] == 1
    assert metrics["compared_fields"] == (2 if other_header == "2024" else 1)
    assert metrics["information_incorrect_fields"] == 1


def test_missing_position_is_distinct_from_unresolved_and_not_in_compared_accuracy():
    reference, observation = _inputs(extra_fields=[
        {"column_header_path": ["2023"], "value": "90"},
        {"column_header_path": ["2022"], "value": "80"},
    ])
    observation["pages"][0]["blocks"][0]["cells"].append(
        {"id": "missing-column", "row": 0, "col": 2, "text": "2023"},
    )
    row, metrics = _score(reference, observation)
    assert [item["status"] for item in row["fields"]] == ["compared", "incorrect", "incorrect"]
    assert row["fields"][1]["reason"] == "no_value_at_resolved_native_position"
    assert metrics["field_compared_accuracy"]["value"] == 1
    assert metrics["field_strict_accuracy"]["denominator"] == 1
    assert metrics["field_comparison_coverage"]["value"] == pytest.approx(1 / 3)
    assert metrics["field_coverage"]["value"] == pytest.approx(2 / 3)
    assert metrics["field_text"]["units"] == 1


@pytest.mark.parametrize("axis", ["row", "column"])
def test_declared_header_role_disambiguates_data_with_the_same_text(axis):
    reference, observation = _inputs()
    cells = observation["pages"][0]["blocks"][0]["cells"]
    chosen = cells[1 if axis == "row" else 0]
    if axis == "row":
        chosen["text"] = "Net"
        reference["units"][0]["table"]["row_header_path"] = ["Net"]
    chosen["is_" + axis + "_header"] = True
    cells.append({"id": "data-duplicate", "row": 3, "col": 3,
                  "text": chosen["text"], "is_" + axis + "_header": False})
    row, metrics = _score(reference, observation)
    assert row["fields"][0]["content_exact"] is True
    assert metrics["correct_fields"] == 1


@pytest.mark.parametrize("axis", ["row", "column"])
def test_duplicate_headers_with_the_same_declared_role_remain_unresolved(axis):
    reference, observation = _inputs()
    cells = observation["pages"][0]["blocks"][0]["cells"]
    chosen = cells[1 if axis == "row" else 0]
    chosen["is_" + axis + "_header"] = True
    # Both column endpoints belong to the same active native header group.
    # A later internal header belongs to a separate scope, not this ambiguity.
    cells.append({"id": "duplicate-header", "row": 0 if axis == "column" else 2, "col": 2,
                  "text": chosen["text"], "is_" + axis + "_header": True})
    row, metrics = _score(reference, observation)
    assert row["fields"][0]["status"] == "incorrect"
    if axis == "column":
        assert row["fields"][0]["reason"] == "ambiguous_complete_label_path"
    assert metrics["information_incorrect_fields"] == 1


def test_unique_explicit_paths_do_not_require_a_repeated_row_label_string():
    reference, observation = _inputs(cells=[{
        "id": "value", "text": "100", "row_header_path": ["Revenue"], "column_header_path": ["2024"],
    }])
    row, metrics = _score(reference, observation)
    assert row["method"] == "explicit_native_paths"
    assert metrics["correct_fields"] == 1


@pytest.mark.parametrize("other_native_paths", [False, True])
def test_explicit_paths_cannot_borrow_a_value_outside_an_independently_located_parent(other_native_paths):
    reference, observation = _inputs(parent="section", requires_parent_scope=True)
    reference["units"].insert(0, {"id": "section", "kind": "text", "literal": "Segment A",
                                 "status": "confirmed", "pages": [1]})
    blocks = observation["pages"][0]["blocks"]
    blocks[0]["cells"][-1]["text"] = "999"
    if not other_native_paths:
        blocks[0]["cells"][-1].update(row_header_path=["Revenue"], column_header_path=["2024"])
    blocks.insert(0, {"id": "section", "kind": "text", "text": "Segment A"})
    blocks.append({"id": "unrelated-table", "kind": "table", "cells": [
        {"id": "other-value", "text": "100", "row_header_path": ["Revenue"], "column_header_path": ["2024"]},
    ]})
    observation["relations"] = [{"type": "contains", "source": "section", "target": "table"}]
    row, metrics = _score(reference, observation)
    assert row["fields"][0]["native_id"] == "value"
    assert row["fields"][0]["content_exact"] is False
    assert metrics["compared_fields"] == 1 and metrics["correct_fields"] == 0


def test_reference_navigation_parent_is_not_an_extra_prediction_target():
    reference, observation = _inputs(parent="missing-parent", requires_parent_scope=True, cells=[{
        "id": "value", "text": "100", "row_header_path": ["Revenue"], "column_header_path": ["2024"],
    }])
    row, metrics = _score(reference, observation)
    assert row["fields"][0]["outcome"] == "correct"
    assert metrics["information_correct_fields"] == 1


def test_content_parent_without_a_localization_dependency_does_not_require_native_heading_edges():
    reference, observation = _inputs(parent="heading")
    reference["units"].insert(0, {"id": "heading", "kind": "text", "literal": "Business overview",
                                 "status": "confirmed", "pages": [1]})
    observation["pages"][0]["blocks"].insert(0, {
        "id": "heading", "kind": "title", "text": "Business overview",
    })
    row, metrics = _score(reference, observation)
    assert row["fields"][0]["status"] == "compared"
    assert metrics["correct_fields"] == 1


def test_explicit_year_row_and_amount_column_express_the_business_fact():
    reference, observation = _inputs(cells=[{
        "id": "value", "text": "100", "row_header_path": ["2024"], "column_header_path": ["Amount"],
    }])
    reference["units"][0]["table"].update(
        row_header_path=["2024"], fields=[{"column_header_path": ["Amount"], "value": "100"}],
    )
    row, metrics = _score(reference, observation)
    assert row["fields"][0]["outcome"] == "correct"
    assert metrics["information_correct_fields"] == 1


def test_an_outer_table_does_not_join_separate_body_coordinate_systems():
    reference, observation = _inputs()
    cells = observation["pages"][0]["blocks"][0]["cells"]
    observation["pages"][0]["blocks"] = [
        {"id": "header-body", "kind": "table_body", "parent_id": "outer", "native_table_container": "outer",
         "cells": cells[:1]},
        {"id": "value-body", "kind": "table_body", "parent_id": "outer", "native_table_container": "outer",
         "cells": cells[1:]},
    ]
    observation["native_containers"] = [{"id": "outer", "label": "table", "native_children": ["header-body", "value-body"]}]
    row, metrics = _score(reference, observation)
    assert row["fields"][0]["status"] == "incorrect"
    assert metrics["compared_fields"] == 0


@pytest.mark.parametrize("native,content_correct", [("  １００  ", True), ("-100", False), ("10.0", False)])
def test_content_equivalence_uses_existing_width_and_whitespace_policy(native, content_correct):
    reference, observation = _inputs()
    observation["pages"][0]["blocks"][0]["cells"][-1]["text"] = native
    row, metrics = _score(reference, observation)
    field = row["fields"][0]
    assert field["native_text"] == native and field["strict_exact"] is False
    assert field["content_exact"] is content_correct
    assert metrics["strict_correct_fields"] == 0
    assert metrics["correct_fields"] == int(content_correct)
    assert field["binding"]["strict_content_correct"] is False
    assert field["binding"]["content_correct"] is content_correct


def test_unannotated_row_scope_keeps_field_placeholders_outside_the_target_denominator():
    reference, observation = _inputs()
    reference["units"][0]["table"]["row_binding"] = {"status": "unknown"}
    row, metrics = _score(reference, observation)
    assert row["fields"][0]["status"] == "not_scored"
    assert metrics["target_fields"] == 0 and metrics["source_unscoped_fields"] == 1
