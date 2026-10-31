"""Common scoring invariants over invented outputs only; no corpus access."""

from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells, markdown_cells
from moparse_eval.scoring import require_complete_target_grading, score_case

PIPELINES = tuple(f"P{number:02d}" for number in range(1, 9))


def reference():
    return {
        "sample_id": "invented-fairness", "review_status": "confirmed",
        "units": [{
            "id": "revenue", "kind": "table_record", "literal": "Revenue",
            "status": "confirmed", "pages": [1],
            "table": {"row_header_path": ["Revenue"], "fields": [{
                "column_header_path": ["2024"], "value": "17", "unit": "人民币百万元",
            }]},
        }],
    }


def table_cells(format_name, unit, years, values):
    rows = [[unit, *years], ["Revenue", *values]]
    if format_name == "html":
        html = "<table>" + "".join(
            "<tr>" + "".join(f"<td>{text}</td>" for text in row) + "</tr>" for row in rows
        ) + "</table>"
        return html_cells(html)
    markdown = "\n".join([
        "| " + " | ".join(rows[0]) + " |",
        "| --- | --- | --- |",
        "| " + " | ".join(rows[1]) + " |",
    ])
    return markdown_cells(markdown)


@pytest.mark.parametrize("format_name", ["html", "gfm"])
@pytest.mark.parametrize("unit,years,values,outcome", [
    ("(人民币百万元)", ("2024", "2023"), ("17", "11"), "correct"),
    ("(人民币百万元)", ("2023", "2024"), ("17", "11"), "incorrect"),
    ("(人民币千元)", ("2024", "2023"), ("17", "11"), "incorrect"),
    ("(人民币百万元)", ("2024", "2023"), ("-17", "11"), "incorrect"),
    ("(人民币百万元)", ("2024", "2023"), ("", "17"), "incorrect"),
])
def test_all_pipeline_ids_receive_identical_grades_and_evidence(format_name, unit, years, values, outcome):
    expected = reference()
    output = {
        "sample_id": expected["sample_id"], "status": "success",
        "pages": [{"page": 1, "blocks": [{
            "id": "table", "kind": "table", "cells": table_cells(format_name, unit, years, values),
        }]}],
    }
    before = deepcopy((expected, output))
    common_score = None
    for pipeline in PIPELINES:
        candidate = {**deepcopy(output), "pipeline": pipeline}
        candidate_before = deepcopy(candidate)
        score = score_case(expected, candidate)
        require_complete_target_grading(score)
        assert score["units"][0]["fields"][0]["outcome"] == outcome
        assert score.pop("pipeline") == pipeline
        if common_score is None:
            common_score = score
        else:
            assert score == common_score, f"{pipeline} changed the grade or evidence for identical output"
        assert candidate == candidate_before
    assert (expected, output) == before
