"""Original scalar-cell offsets are fixed by hand, never by a compiler."""

from copy import deepcopy

import pytest

from moparse_eval.matrix_evidence import read_matrix
from moparse_eval.scalar_evidence import validate_scalar_sources
from moparse_eval.three_layer import canonical, read_candidate

SOURCE = {"path": "#/synthetic/table", "block": "table", "lines": [4, 4]}
CASES = [
    (" (597) ", "(597)", None, [1, 6], None),
    (" 72.7 % ", "72.7", "%", [1, 5], [6, 7]),
    (" 100.0 % ", "100.0", "%", [1, 6], [7, 8]),
    (" (0.2) ", "(0.2)", None, [1, 6], None),
    ("\t 17万元 \n", "17", "万元", [2, 4], [4, 6]),
    ("72.7%", "72.7", "%", [0, 4], [4, 5]),
]


def cells(raw):
    return [{"id": "item", "native_path": "#/synthetic/table/item", "row": 0, "col": 0,
             "text": "Item", "column_header": True},
            {"id": "amount", "native_path": "#/synthetic/table/amount", "row": 0, "col": 1,
             "text": "Amount", "column_header": True},
            {"id": "delta", "native_path": "#/synthetic/table/delta", "row": 1, "col": 0,
             "text": "Delta", "row_header": True},
            {"id": "value", "native_path": "#/synthetic/table/value", "row": 1, "col": 1, "text": raw}]


def original_projection(raw):
    # This raw cell and its location are authored independently of the reader.
    return {"source_cells": [{"text": raw, "source": {**SOURCE, "cell": "value",
            "native_path": "#/synthetic/table/value", "row": 1, "col": 1}}], "source_fragments": []}


@pytest.mark.parametrize("raw,value,unit,value_span,unit_span", CASES)
def test_matrix_public_reader_preserves_original_raw_value_and_both_exact_token_spans(
        raw, value, unit, value_span, unit_span):
    material = cells(raw)
    before = deepcopy(material)
    result = read_matrix(material, source=SOURCE)
    assert material == before and result["blockers"] == []
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"], fact["role"]) == (
        "Delta", "Amount", value, "metric")
    assert fact["raw_value"] == raw and fact["data_evidence"]["text"] == raw
    assert fact["qualifiers"] == ({"unit": unit} if unit else {})
    assert fact["value_source"]["cell_text_span"] == value_span
    assert fact["value_source"]["text_span"] == value_span
    assert raw[slice(*value_span)] == value
    if unit:
        assert fact["qualifier_sources"]["unit"]["cell_text_span"] == unit_span
        assert fact["qualifier_sources"]["unit"]["text_span"] == unit_span
        assert raw[slice(*unit_span)] == unit
    validate_scalar_sources([fact], original_projection(raw), canonicalize=canonical)


def test_nonzero_source_offset_preserves_absolute_and_cell_local_coordinates_separately():
    raw = " 72.7 % "
    source = {**SOURCE, "text_span": [40, 48]}
    [fact] = read_matrix(cells(raw), source=source)["facts"]
    assert fact["value"] == "72.7" and fact["raw_value"] == raw and fact["qualifiers"] == {"unit": "%"}
    assert fact["value_source"]["text_span"] == [41, 45]
    assert fact["value_source"]["cell_text_span"] == [1, 5]
    assert fact["qualifier_sources"]["unit"]["text_span"] == [46, 47]
    assert fact["qualifier_sources"]["unit"]["cell_text_span"] == [6, 7]
    # The table source's absolute origin is not a native-cell snapshot origin.
    # The independent scalar guard's local-origin proof is exercised above.


def test_typed_candidate_public_entry_keeps_padding_and_its_guarded_original_cell():
    raw = " 72.7 % "
    observation = {"sample_id": "synthetic-padding", "pipeline": "P03", "status": "completed",
                   "pages": [{"page": 1, "blocks": [{"id": "table", "native_path": SOURCE["path"],
                   "kind": "table", "cells": cells(raw)}]}], "relations": []}
    before = deepcopy(observation)
    graph = read_candidate(observation)
    assert observation == before
    [fact] = graph["business"]
    assert fact["value"] == "72.7" and fact["raw_value"] == raw and fact["qualifiers"] == {"unit": "%"}
    assert fact["value_source"]["cell_text_span"] == [1, 5]
    assert fact["qualifier_sources"]["unit"]["cell_text_span"] == [6, 7]
    [original] = [item for item in graph["text_projection"]["source_cells"] if item["source"].get("cell") == "value"]
    assert original["text"] == raw
    validate_scalar_sources([fact], graph["text_projection"], canonicalize=canonical)


def test_scalar_guard_still_rejects_trimmed_offsets_against_the_unchanged_raw_cell():
    raw = " 72.7 % "
    [fact] = read_matrix(cells(raw), source=SOURCE)["facts"]
    fact["value_source"].update(text_span=[0, 4], cell_text_span=[0, 4])
    with pytest.raises(ValueError, match="source-bound scalar"):
        validate_scalar_sources([fact], original_projection(raw), canonicalize=canonical)
