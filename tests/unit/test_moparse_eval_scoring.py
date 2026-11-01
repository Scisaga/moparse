"""Synthetic tests only: these tests must never open repository corpus files."""

from __future__ import annotations

import copy

import pytest

from moparse_eval.matching import match_units
from moparse_eval.metrics import edit_counts, normalize_text, precision_recall_f1, text_metrics


def unit(identifier: str, text: str, *, kind: str = "text", **extra):
    return {"id": identifier, "kind": kind, "literal": text, "pages": [1], "status": "confirmed", **extra}


def observation(*blocks, **extra):
    return {
        "sample_id": "synthetic", "pipeline": "P-test", "status": "success",
        "pages": [{"page": 1, "blocks": list(blocks)}], "relations": [], "assets": [],
        "errors": [], "timing": {}, **extra,
    }


def block(identifier: str, text: str = "", **extra):
    return {"id": identifier, "kind": "text", "text": text, "native_path": f"$.{identifier}", **extra}


def rendered_repetition(identifier: str, text: str):
    return block(
        identifier, f"- 范围：{text}；项目：样例；2025：17。", kind="table_body",
        service_evidence_state="converted",
        cells=[{"id": identifier + ":scope", "record_id": identifier, "text": text}],
    )


def published_header(identifier, text, *, table="table-a", token="table-a.r1c0", row=1):
    return block(
        identifier, kind="table_body", service_evidence_state="converted",
        native_table_container="service:table:" + table,
        cells=[{
            "id": identifier + ":header", "record_id": identifier, "text": text,
            "is_row_header": True, "final_markdown_span": [100, 100 + len(text)],
            "source_cell_ref": {"table_id": table, "token": token, "row": row, "column": 0},
        }],
    )


@pytest.mark.parametrize("kind", ["text", "table_record"])
@pytest.mark.parametrize("suffix", ["", ":"])
def test_printed_shared_row_header_is_one_origin_across_records(kind, suffix):
    text = "Operating results attributable to"
    obs = observation(published_header("one", text + suffix), published_header("two", text + suffix))
    result = match_units([dict(unit("group", text, kind=kind), reference_text=text)], obs)
    assert result["diagnostics"]["group"]["status"] == "localized"
    assert result["matches"]["group"]["candidate_id"] == "one:header"


@pytest.mark.parametrize("difference", ["table", "token", "row", "record", "span", "role", "text"])
def test_independent_or_unproven_row_header_repetitions_stay_ambiguous(difference):
    text = "Operating results attributable to"
    first, second = published_header("one", text), published_header("two", text)
    cell = second["cells"][0]
    if difference == "table":
        second["native_table_container"] = "service:table:other"
    elif difference in {"token", "row"}:
        cell["source_cell_ref"][difference] = "other" if difference == "token" else 7
    elif difference == "record":
        cell["record_id"] = "unrelated"
    elif difference == "span":
        cell.pop("final_markdown_span")
    elif difference == "role":
        cell.pop("is_row_header")
    else:
        cell["text"] += " (continued)"
        cell["final_markdown_span"][1] += len(" (continued)")
    result = match_units([dict(unit("group", text), reference_text=text)], observation(first, second))
    assert result["diagnostics"]["group"]["status"] == "ambiguous"


def test_repeating_a_shared_header_twice_inside_one_record_remains_ambiguous():
    text = "Operating results attributable to"
    one = published_header("one", text)
    repeated = copy.deepcopy(one["cells"][0])
    repeated["id"] = "second-header"
    repeated["final_markdown_span"] = [200, 200 + len(text)]
    one["cells"].append(repeated)
    result = match_units([dict(unit("group", text), reference_text=text)], observation(one))
    assert result["diagnostics"]["group"]["status"] == "ambiguous"


@pytest.mark.parametrize("difference", [None, "other-table", "outside-scope", "no-scope", "whole-cell"])
def test_record_locator_distinguishes_its_row_header_from_a_scoped_prose_mention(difference):
    text = "Nuclear power equipment production line"
    header = published_header("one", text)
    context = rendered_repetition("two", "Proceeds will fund " + text + " and other equipment.")
    context["native_table_container"] = header["native_table_container"]
    cell = context["cells"][0]
    cell["source_cell_ref"] = {
        "table_id": "table-a", "block_id": "intro", "text_span": [0, len(cell["text"])],
        "scope_rows": [1, 2], "scope_columns": [0, 1],
    }
    if difference == "other-table":
        context["native_table_container"] = "service:table:other"
    elif difference == "outside-scope":
        cell["source_cell_ref"]["scope_rows"] = [7]
    elif difference == "no-scope":
        cell["source_cell_ref"].pop("scope_rows")
    elif difference == "whole-cell":
        cell["text"] = text
    result = match_units([dict(unit("record", text, kind="table_record"), reference_text=text)],
                         observation(header, context))
    if difference is None:
        assert result["matches"]["record"]["candidate_id"] == "one:header"
    else:
        assert result["diagnostics"]["record"]["status"] == "ambiguous"


def test_width_policy_keeps_strict_diagnostics_and_does_not_use_nfkc():
    assert normalize_text("Ａ１，\u3000−①ﬁ") == "A1, −①ﬁ"
    metrics = text_metrics("Ａ１", "A1")
    assert metrics["strict"]["distance"] == 2
    assert metrics["width_equivalent"]["distance"] == 0
    assert text_metrics("-100", "100")["width_equivalent"]["distance"] == 1


def test_cer_can_exceed_one_and_zero_denominators_stay_na():
    metrics = text_metrics("a", "abcdef")["strict"]
    assert metrics["cer"] == 5
    assert metrics["normalized_edit_distance"] == pytest.approx(5 / 6)
    assert metrics["similarity"] == pytest.approx(1 / 6)
    assert text_metrics("", "")["strict"]["cer"] is None
    assert precision_recall_f1(0, None, 0)["recall"] is None


def test_edit_counts_preserve_substitution_deletion_and_insertion():
    assert edit_counts("abc", "axc")["substitutions"] == 1
    assert edit_counts("abc", "ac")["deletions"] == 1
    assert edit_counts("ac", "abc")["insertions"] == 1


def test_two_references_cannot_consume_one_native_character_span():
    prepared = [{"id": name, "kind": "text", "pages": [1], "reference_text": "shared"} for name in ("a", "b")]
    result = match_units(prepared, observation(block("one", "shared")))
    assert result["matches"] == {}
    assert all(row["status"] == "ambiguous" for row in result["diagnostics"].values())
