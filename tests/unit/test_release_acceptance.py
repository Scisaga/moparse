"""Ensure release assertions reject invisible text and broken source mappings."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from benchmark.tools.check_release import (
    GOLD_PATHS,
    check_continuation,
    check_tables,
    compact,
    fold_ascii_width,
    load_reader,
    spans,
)


def public_table(source):
    return {
        "id": "adapter_specific_id",
        "rows": deepcopy(source["rows"]),
        "rendered_page": source["source_page"],
        "sources": [],
        "meta": {
            "source_pages": [source["source_page"]],
            "num_rows": len(source["rows"]),
            "num_cols": len(source["rows"][0]),
            "structure_valid": True,
            "encoding": "anchor_and_blanks",
            "header_scope_complete": True,
            "header_scope_rows": [0],
            "spans": spans(source),
        },
    }


def funding_source():
    return next(source for source in json.loads(GOLD_PATHS["tables"].read_text())["tables"]
                if source["document"].endswith("1225473526.pdf")
                and (source["source_page"], source["source_ordinal"]) == (7, 2))


def test_release_cannot_accept_missing_cell_text_hidden_in_comment():
    reader, source = load_reader(), funding_source()
    table = public_table(source)
    assert check_tables([table], source, reader)["pass"]
    table["rows"][1][0] = "<!-- " + table["rows"][1][0] + " -->"
    result = check_tables([table], source, reader)
    assert not result["pass"] and result["mismatches"]
    note = "完整附注正文。"
    assert compact(f"<!-- {note} -->", reader) == ""
    assert compact(f"&lt;!-- {note} --&gt;", reader) != ""


def test_release_checks_original_page_and_merge_spans():
    reader, source = load_reader(), funding_source()
    table = public_table(source)
    table["meta"]["spans"] = []
    assert not check_tables([table], source, reader)["pass"]
    table = public_table(source)
    table["meta"]["source_pages"] = [6]
    assert check_tables([table], source, reader)["matching_tables"] == 0


def test_release_rejects_wrong_repeated_header_source_row_map():
    reader = load_reader()
    sources = json.loads(GOLD_PATHS["continuation"].read_text())["tables"]
    first, second = sorted(sources, key=lambda source: source["source_page"])
    table = public_table(first)
    table["rows"] += deepcopy(second["rows"][1:])
    table["meta"].update(source_pages=[6, 7], num_rows=len(table["rows"]),
                         spans=spans(first) + spans(second, len(first["rows"]) - 1))
    table["sources"] = [
        {"fragment": "custom_6", "page": 6, "source_rows": "1-7", "logical_rows": "1-7",
         "repeated_header_rows": 0},
        {"fragment": "custom_7", "page": 7, "source_rows": "2-6", "logical_rows": "8-12",
         "repeated_header_rows": 1},
    ]
    assert check_continuation([table], sources, reader)["pass"]
    table["sources"][1]["repeated_header_rows"] = 0
    result = check_continuation([table], sources, reader)
    assert not result["pass"] and not result["source_rows_match"]


def test_width_equivalence_retains_raw_surface_differences_without_losing_units():
    source = {"source_page": 3, "source_ordinal": 1, "cells": [],
              "rows": [["项目", "本报告期"], ["每股收益（元／股）", "０.２９０７"]]}
    table = public_table(source)
    table["rows"][1] = ["每股收益(元/股)", "0.2907"]
    result = check_tables([table], source, load_reader())
    assert result["pass"] and result["width_equivalent"]
    assert not result["raw_surface_exact"]
    assert len(result["mismatches"]) == len(result["width_differences"]) == 2
    assert not result["content_mismatches"]
    assert result["mismatches"][0]["expected"] == "每股收益（元／股）"
    assert result["mismatches"][0]["actual"] == "每股收益(元/股)"
    assert fold_ascii_width("！Ａ～　") == "!A~ "


@pytest.mark.parametrize(("expected", "actual"), [
    ("每股收益（元／股）", "每股收益(元/股"),
    ("-0.2907", "0.2907"),
    ("-0.2907", "+0.2907"),
    ("0.2907", "0.2908"),
    ("10²", "102"),
    ("10²", "10^2"),
    ("Ⅳ", "IV"),
    ("−3", "-3"),
    ("每股收益（元／股）", "每股收益(元/份)"),
])
def test_width_equivalence_never_repairs_missing_symbols_or_different_content(expected, actual):
    source = {"source_page": 3, "source_ordinal": 1, "cells": [],
              "rows": [["项目", "本报告期"], ["源格", expected]]}
    table = public_table(source)
    table["rows"][1][1] = actual
    result = check_tables([table], source, load_reader())
    assert not result["pass"] and not result["width_equivalent"]
    assert result["content_mismatches"]
