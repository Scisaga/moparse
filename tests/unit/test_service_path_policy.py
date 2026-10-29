"""Explicit paths and grid endpoints share label localization, never values."""

from copy import deepcopy

import pytest

from moparse_eval.scoring import score_case


def _score(*, explicit: bool, value="100", row_path=None, column_path=None, reference_row_path=None):
    reference = {"sample_id": "synthetic", "review_status": "confirmed", "relations": [],
                 "units": [{"id": "record", "kind": "table_record", "status": "confirmed",
                            "pages": [1], "literal": "Profit Current 100", "table": {
                                "row_header_path": reference_row_path or ["Profit"],
                                "fields": [{"column_header_path": ["Current"], "value": "100"}],
                            }}]}
    if explicit:
        cells = [{"id": "value", "text": value,
                  "row_header_path": row_path or ["Profit (USD)"],
                  "column_header_path": column_path or ["Current (%)"]}]
    else:
        cells = [{"id": "row", "row": 1, "col": 0, "text": "Profit (USD)"},
                 {"id": "column", "row": 0, "col": 1, "text": "Current (%)"},
                 {"id": "value", "row": 1, "col": 1, "text": value}]
    observation = {"sample_id": "synthetic", "pipeline": "controlled", "status": "completed",
                   "pages": [{"page": 1, "blocks": [{"id": "table", "kind": "table", "cells": cells}]}]}
    before = deepcopy((reference, observation))
    result = score_case(reference, observation)
    assert (reference, observation) == before
    return result["metrics"]["table_records"]


def test_header_with_unit_uses_identical_localization_in_explicit_and_grid_views():
    for explicit in (True, False):
        result = _score(explicit=explicit)
        assert result["compared_fields"] == result["correct_fields"] == 1


@pytest.mark.parametrize("value", ["-100", "1000", "100%"])
def test_path_localization_does_not_normalize_or_repair_the_value(value):
    result = _score(explicit=True, value=value)
    assert result["compared_fields"] == 1 and result["correct_fields"] == 0


@pytest.mark.parametrize("path", [["Profits"], ["Unrelated Profitability"]])
def test_explicit_path_keeps_complete_levels_and_word_boundaries(path):
    result = _score(explicit=True, row_path=path)
    assert result["correct_fields"] == 0


def test_unannotated_leading_context_is_not_an_extra_required_answer_dimension():
    assert _score(explicit=True, row_path=["Group", "Profit"])["correct_fields"] == 1


@pytest.mark.parametrize("path", [["Other", "Profit"], ["Group", "Intermediate", "Profit"]])
def test_annotated_parent_cannot_be_replaced_or_skipped(path):
    assert _score(explicit=True, row_path=path, reference_row_path=["Group", "Profit"])["correct_fields"] == 0
