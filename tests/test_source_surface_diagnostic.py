from __future__ import annotations

import copy

import pytest

from benchmark.tools import diagnose_source_surface as diagnostic


class Reader:
    @staticmethod
    def visible_markdown(value):
        return value


def original_sources():
    return [
        {"source_page": 6, "rows": [["Holder", "Value (shares)"], ["基金－甲", "10"]], "cells": []},
        {
            "source_page": 7,
            "rows": [["Holder", "Value (shares)"], ["机构（甲）", "20"]],
            "cells": [],
        },
    ]


def logical_table():
    return {
        "id": "logical",
        "rendered_page": 6,
        "rows": [["Holder", "Value (shares)"], ["基金-甲", "10"], ["机构(甲)", "20"]],
        "meta": {
            "source_pages": [6, 7],
            "structure_valid": True,
            "spans": [],
            "header_scope_complete": True,
            "header_scope_rows": [0],
        },
        "sources": [
            {
                "page": 6,
                "source_rows": "1-2",
                "logical_rows": "1-2",
                "repeated_header_rows": 0,
                "fragment": "fragment6",
            },
            {
                "page": 7,
                "source_rows": "2-2",
                "logical_rows": "3-3",
                "repeated_header_rows": 1,
                "fragment": "fragment7",
            },
        ],
    }


def test_width_diagnostic_keeps_original_strict_failure():
    table = logical_table()
    sources = original_sources()
    before = copy.deepcopy((table, sources))
    result = diagnostic.continuation_diagnostic([table], sources, Reader)
    assert result["functional_merge_and_source_maps"] is True
    assert result["ASCII_width_equivalent_complete_continuation"] is True
    assert result["strict_original_checker"]["pass"] is False
    assert result["complete_grid_surface"]["raw_exact"] is False
    assert len(result["complete_grid_surface"]["raw_differences"]) == 2
    assert (table, sources) == before


def test_preserved_split_fragments_do_not_count_as_functional_merge():
    tables = []
    for index, source in enumerate(original_sources()):
        table = logical_table()
        table.update(
            id=f"fragment{6 + index}", rendered_page=6 + index, rows=copy.deepcopy(source["rows"])
        )
        table["meta"]["source_pages"] = [6 + index]
        tables.append(table)
    result = diagnostic.continuation_diagnostic(tables, original_sources(), Reader)
    assert result["logical_merge_observed"] is False
    assert result["functional_merge_and_source_maps"] is False
    assert result["ASCII_width_equivalent_complete_continuation"] is False
    assert all(item["surface"]["raw_exact"] for item in result["separate_fragments"])


@pytest.mark.parametrize(
    ("actual", "source"),
    [
        ("1,465.510,368.44", "1,465,510,368.44"),
        ("1.342,788,515.86", "1,342,788,515.86"),
        ("-", "一"),
        ("1", "¹"),
    ],
)
def test_width_diagnostic_never_repairs_numbers_or_compatibility_glyphs(actual, source):
    result = diagnostic.compare_grid([[actual]], [[source]])
    assert result["ASCII_width_equivalent"] is False
    assert len(result["non_width_differences"]) == 1


def test_incorrect_units_cannot_pass_complete_source_grid():
    table = logical_table()
    table["rows"][0][1] = "Value (yuan)"
    result = diagnostic.continuation_diagnostic([table], original_sources(), Reader)
    assert result["functional_merge_and_source_maps"] is True
    assert result["complete_header_surface"]["ASCII_width_equivalent"] is False
    assert result["ASCII_width_equivalent_complete_continuation"] is False


def test_incorrect_skip_and_source_mapping_remain_failed():
    table = logical_table()
    table["sources"][1]["repeated_header_rows"] = 0
    result = diagnostic.continuation_diagnostic([table], original_sources(), Reader)
    assert result["complete_grid_surface"]["ASCII_width_equivalent"] is True
    assert result["structural_checks"]["repeated_header_skip_matches"] is False
    assert result["functional_merge_and_source_maps"] is False


def test_different_source_headers_cannot_be_diagnosed_as_repeated():
    sources = original_sources()
    sources[1]["rows"][0][1] = "Value (yuan)"
    with pytest.raises(ValueError, match="equal complete repeated headers"):
        diagnostic.continuation_diagnostic([logical_table()], sources, Reader)
