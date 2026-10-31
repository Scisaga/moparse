"""Synthetic tests only: these tests must never open repository corpus files."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from moparse_eval.adapters import html_cells, markdown_cells
from moparse_eval.matching import match_units
from moparse_eval.metrics import edit_counts, normalize_text, precision_recall_f1, text_metrics
from moparse_eval.reporting import aggregate_reports, render_markdown
from moparse_eval.scoring import read_reference_text, score_case


def unit(identifier: str, text: str, *, kind: str = "text", **extra):
    return {"id": identifier, "kind": kind, "literal": text, "pages": [1], "status": "confirmed", **extra}


def case(*units, **extra):
    return {
        "sample_id": "synthetic", "document_id": "doc-a", "family_id": "family-a",
        "tags": ["synthetic"], "review_status": "confirmed", "units": list(units),
        "relations": [], "visual_review": {"pages": [1], "reviewer": "synthetic-fixture"},
        **extra,
    }


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


@pytest.mark.parametrize("original_kind", ["paragraph", "retained_grid"])
def test_prose_locator_uses_independent_literal_instead_of_rendered_repetitions(original_kind):
    text = "Quarterly operating results"
    original = (block("original", text) if original_kind == "paragraph" else
                block("grid", kind="table_body", service_evidence_state="retained",
                      cells=[{"id": "original", "text": text}]))
    result = score_case(case(unit("title", text)), observation(
        original, rendered_repetition("one", text), rendered_repetition("two", text)))
    row = result["units"][0]
    assert row["status"] == "localized"
    assert row["match"]["candidate_id"] == "original"
    assert row["strict_exact"] is True


def test_rendered_repetitions_alone_do_not_invent_an_independent_original():
    text = "Quarterly operating results"
    result = score_case(case(unit("title", text)), observation(
        rendered_repetition("one", text), rendered_repetition("two", text)))
    assert result["units"][0]["status"] == "ambiguous"


@pytest.mark.parametrize("second_kind", ["paragraph", "retained_grid"])
def test_true_independent_duplicates_remain_ambiguous_with_rendered_repetitions(second_kind):
    text = "Quarterly operating results"
    second = (block("second", text) if second_kind == "paragraph" else
              block("grid", kind="table_body", service_evidence_state="retained",
                    cells=[{"id": "second", "text": text}]))
    result = score_case(case(unit("title", text)), observation(
        block("first", text), second, rendered_repetition("copy", text)))
    assert result["units"][0]["status"] == "ambiguous"


@pytest.mark.parametrize("kind", ["field", "table_cell"])
def test_prose_repetition_rule_does_not_relax_business_field_localization(kind):
    text = "Long term facilities outstanding"
    original = block("grid", kind="table_body", cells=[{"id": "original", "text": text}])
    result = score_case(case(unit("field", text, kind=kind)), observation(
        original, rendered_repetition("one", text), rendered_repetition("two", text)))
    assert result["units"][0]["status"] == "ambiguous"


def test_prose_repetition_rule_does_not_prefer_a_weaker_original_transcription():
    text = "Quarterly operating results"
    result = score_case(case(unit("title", text)), observation(
        block("original", "Quarterly operating resultx"),
        rendered_repetition("one", text), rendered_repetition("two", text)))
    assert result["units"][0]["status"] == "ambiguous"


def test_prose_repetition_rule_does_not_borrow_an_original_from_another_page():
    text = "Quarterly operating results"
    obs = observation(rendered_repetition("one", text), rendered_repetition("two", text))
    obs["pages"].append({"page": 2, "blocks": [block("elsewhere", text)]})
    result = score_case(case(unit("title", text)), obs)
    assert result["units"][0]["status"] == "ambiguous"


def test_a_rendered_state_label_without_record_identity_does_not_resolve_a_tie():
    text = "Quarterly operating results"
    suspect = rendered_repetition("one", text)
    suspect["cells"][0]["record_id"] = "different-record"
    result = score_case(case(unit("title", text)), observation(block("original", text), suspect))
    assert result["units"][0]["status"] == "ambiguous"


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


def test_scoring_record_order_uses_the_printed_row_label_beside_its_copied_scope():
    text = "Nuclear power equipment production line"
    intro = "Proceeds will fund " + text + " and other equipment."
    header = published_header("record", text)
    context = {"id": "scope", "record_id": "record", "text": intro,
               "source_cell_ref": {"table_id": "table-a", "block_id": "intro", "text_span": [0, len(intro)],
                                   "scope_rows": [1], "scope_columns": [0]}}
    header["cells"].insert(0, context)
    result = score_case(case(
        unit("intro", intro), unit("project", text, kind="table_record",
                                  table={"row_header_path": [text], "fields": []}),
        relations=[{"type": "before", "source": "intro", "target": "project", "status": "confirmed"}],
    ), observation(block("intro", intro), header))
    assert result["units"][1]["label_match"]["candidate_id"] == "record:header"
    assert result["relations"][0]["correct"] is True


def record_case(value: str = "100", **table_extra):
    return case(unit(
        "record", "营业收入：2024年100；2023年200。", kind="table_record",
        table={"id": "authored-table", "row": 1, "row_header_path": ["营业收入"],
               "fields": [{"column_header_path": ["2024"], "value": value}], **table_extra},
    ))


def grid_observation(value: str = "100", **extra):
    cells = [
        {"id": "h24", "row": 0, "col": 1, "row_span": 1, "col_span": 1, "text": "2024"},
        {"id": "h23", "row": 0, "col": 2, "row_span": 1, "col_span": 1, "text": "2023"},
        {"id": "row-label", "row": 1, "col": 0, "row_span": 1, "col_span": 1, "text": "营业收入"},
        {"id": "v24", "row": 1, "col": 1, "row_span": 1, "col_span": 1, "text": value},
        {"id": "v23", "row": 1, "col": 2, "row_span": 1, "col_span": 1, "text": "200"},
    ]
    return observation(block("native-table", kind="table", cells=cells), **extra)


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


@pytest.mark.parametrize("representation,text", [
    ("plain", "Revenue was 100 million."),
    ("markdown", "**Revenue** was 100 million."),
    ("html", "<p><b>Revenue</b> was 100 million.</p>"),
])
def test_declared_formats_have_equal_visible_character_scores(representation, text):
    result = score_case(case(unit("a", "Revenue was 100 million.")),
                        observation(block("native", text, text_format=representation)))
    assert result["metrics"]["text"]["strict"]["distance"] == 0
    assert result["units"][0]["match"]["span_representation"] == representation + "_visible_text"


def test_plain_asterisks_are_content_rather_than_guessed_markdown():
    result = score_case(case(unit("a", "Literal ** notation.")),
                        observation(block("native", "Literal ** notation.", text_format="plain")))
    assert result["metrics"]["text"]["strict"]["distance"] == 0


def test_multpage_native_cell_scope_does_not_invent_an_exact_page():
    target = case(unit("a", "Revenue total", kind="table_cell", pages=[2]))
    actual = observation(block("table", kind="table", provenance_pages=[1, 2], cells=[
        {"id": "pointer-cell", "native_id": "sdk-cell", "text": "Revenue total", "page": None},
    ]))
    result = score_case(target, actual)
    match = result["units"][0]["match"]
    assert match["page"] is None
    assert match["physical_page_known"] is False
    assert match["provenance_pages"] == [1, 2]


def test_native_tree_sequence_controls_stream_and_order_across_physical_pages():
    target = case(unit("a", "first paragraph", pages=[1]), unit("b", "second paragraph", pages=[2]), relations=[
        {"type": "before", "source": "a", "target": "b", "status": "confirmed"},
    ])
    actual = observation()
    actual["pages"] = [
        {"page": 1, "blocks": [block("first", "first paragraph", native_sequence=[0, 1])]},
        {"page": 2, "blocks": [block("second", "second paragraph", native_sequence=[0, 0])]},
    ]
    result = score_case(target, actual)
    assert result["metrics"]["unit_exact"]["recall"] == 1
    assert result["relations"][0]["correct"] is False
    stream = score_case(case(unit("whole", "second paragraph first paragraph", pages=[1, 2])), actual)
    assert stream["metrics"]["unit_exact"]["recall"] == 1


def test_label_only_anchor_is_not_whole_card_content_or_a_value_binding():
    target = case(
        unit("label", "Annual revenue", localization_scope="label_only"),
        unit("value", "100", kind="field", field_scope={
            "status": "confirmed", "scope_kind": "visual_label_value_pair", "label_unit": "label",
        }),
    )
    actual = observation(block("label", "Annual revenue", parent_id="native-card"),
                         block("value", "100", parent_id="native-card"))
    actual["native_containers"] = [{"id": "native-card", "label": "card", "native_children": ["label", "value"]}]
    result = score_case(target, actual)
    assert result["coverage"]["scored_units"] == 1
    assert result["coverage"]["localization_only_units"] == 1
    assert result["metrics"]["field_exact"]["value"] == 1
    assert result["metrics"]["field_pair_binding"]["value"] == 0
    assert result["metrics"]["field_pair_binding"]["observable"] == 0
    actual["relations"] = [{"type": "label_value", "source": "label", "target": "value"}]
    assert score_case(target, actual)["metrics"]["field_pair_binding"]["value"] == 1


def test_field_pair_text_colon_is_evidence_without_gold_reordering():
    target = case(unit("label", "Annual revenue", localization_scope="label_only"),
                  unit("value", "100", kind="field", field_scope={
                      "status": "confirmed", "scope_kind": "visual_label_value_pair", "label_unit": "label",
                  }))
    result = score_case(target, observation(block("both", "Annual revenue: 100")))
    assert result["metrics"]["field_pair_binding"]["value"] == 1


def test_closed_business_without_closed_furniture_has_no_precision():
    target = case(unit("a", "Business text"), scoring={"exhaustive_units": True})
    result = score_case(target, observation(block("body", "Business text"), block("footer", "1")))
    assert result["metrics"]["unit_presence"]["precision"] is None


def test_superscript_note_projection_needs_actual_native_format_evidence():
    target = record_case("150.1", fields=[{
        "column_header_path": ["2024"], "value": "150.1", "note_markers": ["4"],
        "value_representation": "number_and_note",
    }])
    actual = grid_observation("150.14")
    plain = score_case(target, actual)
    assert plain["metrics"]["table_records"]["field_strict_accuracy"]["value"] == 0
    actual["pages"][0]["blocks"][0]["cells"][3]["inline_annotations"] = [
        {"type": "superscript", "span": [5, 6], "text": "4"},
    ]
    # Typography alone is also compatible with a mathematical exponent.
    assert score_case(target, actual)["metrics"]["table_records"]["field_strict_accuracy"]["value"] == 0
    actual["pages"][0]["blocks"].append({"id": "n", "kind": "table_footnote", "text": "4 Record high."})
    formatted = score_case(target, actual)
    assert formatted["metrics"]["table_records"]["field_strict_accuracy"]["value"] == 1
    assert formatted["units"][0]["fields"][0]["native_text"] == "150.14"
    assert formatted["units"][0]["fields"][0]["native_note_markers"] == ["4"]
    assert formatted["metrics"]["table_records"]["binding"]["value"] == 1


def test_unlabelled_source_row_is_reference_coverage_rather_than_model_miss():
    target = record_case(row_header_path=[], row_binding={"status": "unresolved", "reason": "unlabelled_subtotal"})
    result = score_case(target, grid_observation())
    metric = result["metrics"]["table_records"]
    assert metric["declared_fields"] == 1
    assert metric["source_unscoped_fields"] == 1
    assert metric["target_fields"] == 0


def test_blank_field_needs_an_explicit_native_empty_cell():
    target = record_case("")
    correct = score_case(target, grid_observation(""))["metrics"]["table_records"]
    assert correct["blank_fields"]["value"] == 1
    assert correct["field_text"]["strict"]["reference_chars"] == 0
    actual = grid_observation("")
    del actual["pages"][0]["blocks"][0]["cells"][3]
    missing = score_case(target, actual)["metrics"]["table_records"]
    assert missing["blank_fields"]["value"] == 0
    assert missing["blank_observed_accuracy"]["value"] is None


def test_table_record_fragment_references_do_not_invent_a_second_body(tmp_path):
    reference = tmp_path / "expected.md"
    body = "Revenue 2024: 100\nOther row\nRevenue 2023: 200\n"
    reference.write_text(body)
    authored = {"kind": "table_record", "reference": {"fragments": [
        {"path": "expected.md", "lines": [1, 1]},
        {"path": "expected.md", "lines": [3, 3]},
    ]}}
    assert read_reference_text(authored, tmp_path) == "Revenue 2024: 100\nRevenue 2023: 200"
    assert reference.read_text() == body
    with pytest.raises(ValueError, match="table records only"):
        read_reference_text({**authored, "kind": "text"}, tmp_path)


def test_native_grid_prose_keeps_text_credit_and_its_actual_reading_order():
    target = case(unit("p", "First layout paragraph second layout paragraph"))
    native = observation(block("layout-grid", kind="table", cells=[
        {"id": "cell-a", "text": "First layout paragraph", "row": 0, "col": 0},
        {"id": "cell-b", "text": "second layout paragraph", "row": 0, "col": 1},
    ]))
    result = score_case(target, native)
    assert result["metrics"]["unit_exact"]["recall"] == 1
    assert result["metrics"]["table_grid"]["denominator"] == 0


@pytest.mark.parametrize("representation", ["json", "html", "markdown"])
def test_same_table_information_has_equal_field_scores_across_formats(representation):
    if representation == "json":
        cells = grid_observation()["pages"][0]["blocks"][0]["cells"]
    elif representation == "html":
        cells = html_cells("<table><tr><th></th><th>2024</th><th>2023</th></tr>"
                           "<tr><td>营业收入</td><td>100</td><td>200</td></tr></table>")
    else:
        cells = markdown_cells("| |2024|2023|\n|---|---|---|\n|营业收入|100|200|")
    result = score_case(record_case(), observation(block("table", kind="table", cells=cells)))
    assert result["metrics"]["table_records"]["field_target_correctness"]["value"] == 1
    assert result["metrics"]["table_records"]["field_coverage"]["value"] == 1


def test_actual_table_container_can_locate_card_values_without_granting_binding():
    target = case(unit("label", "Annual revenue", localization_scope="label_only"),
                  unit("value", "100", kind="field", field_scope={"status": "confirmed",
                      "scope_kind": "visual_label_value_pair", "label_unit": "label"}))
    native = observation(block("grid", kind="table", cells=[
        {"id": "label", "text": "Annual revenue", "row": 0, "col": 0},
        {"id": "value", "text": "100", "row": 0, "col": 1},
    ]))
    result = score_case(target, native)
    assert result["metrics"]["field_exact"]["value"] == 1
    assert result["metrics"]["field_pair_binding"]["value"] == 0


def test_ambiguous_text_keeps_conservative_and_aligned_cer_separate():
    result = score_case(case(unit("a", "Repeated paragraph")),
                        observation(block("one", "Repeated paragraph"), block("two", "Repeated paragraph")))
    assert result["coverage"]["ambiguous_units"] == 1
    assert result["metrics"]["text"]["strict"]["cer"] == 1
    assert result["metrics"]["text_aligned"]["strict"]["cer"] is None
    assert result["evaluation_policy"]["unlocalized_reference_deletions_do_not_prove_native_text_absence"] is True


def test_edit_counts_preserve_substitution_deletion_and_insertion():
    assert edit_counts("abc", "axc")["substitutions"] == 1
    assert edit_counts("abc", "ac")["deletions"] == 1
    assert edit_counts("ac", "abc")["insertions"] == 1


def test_reference_reader_uses_declared_slice_without_rewriting(tmp_path: Path):
    source = tmp_path / "references" / "expected.md"
    source.parent.mkdir()
    content = "first\nsecond\nthird\n"
    source.write_text(content, encoding="utf-8")
    target = {"reference": {"path": "references/expected.md", "lines": [2, 3]}}
    assert read_reference_text(target, tmp_path) == "second\nthird"
    assert source.read_text(encoding="utf-8") == content
    with pytest.raises(ValueError, match="escapes"):
        read_reference_text({"reference": {"path": "../outside.md", "lines": [1, 1]}}, tmp_path)
    with pytest.raises(ValueError, match="unavailable"):
        read_reference_text({"reference": {"path": "references/expected.md", "lines": [3, 4]}}, tmp_path)


def test_reading_order_is_not_used_to_reward_content_matching():
    target = case(unit("a", "first paragraph"), unit("b", "second paragraph"), relations=[
        {"type": "before", "source": "a", "target": "b", "status": "confirmed"},
    ])
    result = score_case(target, observation(block("second", "second paragraph"), block("first", "first paragraph")))
    assert result["metrics"]["unit_exact"]["recall"] == 1
    assert result["metrics"]["relations"]["recall"] == 0
    assert result["relations"][0]["observable"] is True


def test_fused_native_block_can_supply_disjoint_spans():
    result = score_case(case(unit("a", "alpha"), unit("b", "beta")), observation(block("both", "alpha beta")))
    assert result["coverage"]["localized_units"] == 2
    first, second = [row["match"]["span"] for row in result["units"]]
    assert first[1] <= second[0]


def test_one_paragraph_can_span_native_blocks_without_creating_duplicate_output():
    target = case(unit("a", "first part second part"), scoring={"exhaustive_units": True, "exhaustive_output_scope": True})
    result = score_case(target, observation(block("a", "first part"), block("b", "second part")))
    assert result["metrics"]["unit_presence"]["recall"] == 1
    assert result["metrics"]["unit_presence"]["fp"] == 0
    assert result["metrics"]["unit_exact"]["recall"] == 1
    assert len(result["units"][0]["match"]["claims"]) == 2


def test_missing_heading_relation_does_not_hide_paragraph_text():
    target = case(unit("h", "Business heading"), unit("p", "The complete business paragraph.", parent="h"), relations=[
        {"type": "heading_of", "source": "h", "target": "p", "status": "confirmed"},
    ])
    result = score_case(target, observation(block("h", "Business heading"), block("p", "The complete business paragraph.")))
    assert result["metrics"]["unit_presence"]["recall"] == 1
    assert result["metrics"]["relations"]["recall"] == 0


def test_stream_and_original_block_cannot_reuse_a_character_range():
    target = case(unit("a", "first part second part"), unit("b", "second part"))
    result = score_case(target, observation(block("a", "first part"), block("b", "second part")))
    assert result["coverage"]["localized_units"] == 0
    assert result["coverage"]["ambiguous_units"] == 2


def test_nonliteral_reference_needs_source_literal_for_presence_and_relation(tmp_path):
    reference = tmp_path / "expected.md"
    reference.write_text("Label: a reorganized sentence.\n")
    target = case({
        "id": "a", "kind": "text", "status": "confirmed", "pages": [1],
        "reference": {"path": "expected.md", "lines": [1, 1]},
        "text_comparison": "not_applicable",
    }, unit("b", "Complete second sentence."), relations=[
        {"type": "before", "source": "a", "target": "b", "status": "confirmed"},
    ])
    result = score_case(target, observation(block("a", "Label a reorganized sentence."), block("b", "Complete second sentence.")), tmp_path)
    assert result["coverage"]["excluded_units"] == {"nonliteral_reference_without_source_locator": 1}
    assert result["coverage"]["reference_unavailable_relations"] == 1
    assert result["metrics"]["unit_presence"]["target_units"] == 1
    assert result["metrics"]["relations"]["recall"] is None
    target["units"][0]["localization_literal"] = "Label a reorganized sentence."
    result = score_case(target, observation(block("a", "Label a reorganized sentence."), block("b", "Complete second sentence.")), tmp_path)
    assert result["metrics"]["unit_presence"]["recall"] == 1
    assert result["metrics"]["relations"]["recall"] == 1
    assert result["metrics"]["text"]["units"] == 1
    assert result["units"][0]["text"] is None


def test_markdown_syntax_is_projected_but_authored_punctuation_is_preserved(tmp_path):
    (tmp_path / "expected.md").write_text("## Heading\n\n- **Label**: value.\n")
    assert read_reference_text({"reference": {"path": "expected.md", "lines": [1, 3]}}, tmp_path) == "Heading\nLabel: value."


def test_furniture_exclusion_matches_whole_native_item_only():
    target = case(unit("a", "Complete business paragraph."), scoring={
        "exhaustive_units": True,
        "exhaustive_output_scope": True,
        "ignored_units": [{"literal": "Company 2024", "pages": [1], "reason": "page_furniture"}],
    })
    result = score_case(target, observation(block("a", "Complete business paragraph."), block("footer", "Company 2024")))
    assert result["metrics"]["unit_presence"]["fp"] == 0
    result = score_case(target, observation(block("a", "Complete business paragraph."), block("p", "Company 2024 owes money.")))
    assert result["metrics"]["unit_presence"]["fp"] == 1


def test_duplicates_remain_ambiguous_instead_of_using_expected_order():
    result = score_case(case(unit("a", "same paragraph")), observation(
        block("one", "same paragraph"), block("two", "same paragraph"),
    ))
    assert result["coverage"]["ambiguous_units"] == 1
    assert result["metrics"]["unit_presence"]["recall"] == 0
    assert result["units"][0]["status"] == "ambiguous"


def test_two_references_cannot_consume_one_native_character_span():
    prepared = [{"id": name, "kind": "text", "pages": [1], "reference_text": "shared"} for name in ("a", "b")]
    result = match_units(prepared, observation(block("one", "shared")))
    assert result["matches"] == {}
    assert all(row["status"] == "ambiguous" for row in result["diagnostics"].values())


def test_short_numbers_need_parent_scope_even_when_globally_unique():
    result = score_case(case(unit("number", "42", kind="field")), observation(block("value", "42")))
    assert result["units"][0]["reason"] == "short_number_without_parent_scope"
    assert result["metrics"]["field_exact"]["denominator"] == 1
    assert result["metrics"]["field_exact"]["value"] == 0


def test_explicit_native_parent_scope_disambiguates_repeated_numbers():
    target = case(unit("p", "Alpha table"), unit("number", "42", kind="field", parent="p"))
    actual = observation(block("heading", "Alpha table"), block("value", "42"), block("other", "42"), relations=[
        {"type": "contains", "source": "heading", "target": "value"},
    ])
    result = score_case(target, actual)
    assert result["metrics"]["field_exact"]["value"] == 1
    assert result["units"][1]["match"]["native_id"] == "value"


def test_fuzzy_threshold_only_localizes_and_does_not_repair_output():
    target = case(unit("a", "Revenue was 100 million."))
    result = score_case(target, observation(block("a", "Revenue was 101 million.")))
    assert result["coverage"]["localized_units"] == 1
    assert result["units"][0]["match"]["hypothesis"] == "Revenue was 101 million."
    assert result["metrics"]["unit_exact"]["recall"] == 0
    assert result["metrics"]["text"]["strict"]["distance"] == 1


def test_precision_requires_explicit_exhaustive_reference_scope():
    actual = observation(block("a", "business paragraph"), block("extra", "another valid paragraph"))
    default = score_case(case(unit("a", "business paragraph")), actual)
    assert default["metrics"]["unit_presence"]["precision"] is None
    exhaustive = score_case(case(unit("a", "business paragraph"), scoring={"exhaustive_units": True, "exhaustive_output_scope": True}), actual)
    assert exhaustive["metrics"]["unit_presence"]["precision"] == 0.5
    assert exhaustive["metrics"]["unit_presence"]["fp"] == 1


def test_pending_reference_and_missing_reference_are_not_declared_correct(tmp_path: Path):
    target = case(unit("pending", "unused", status="pending"), {
        "id": "missing", "kind": "text", "status": "confirmed", "pages": [1],
        "reference": {"path": "missing.md", "lines": [1, 1]},
    })
    result = score_case(target, observation(), tmp_path)
    assert result["coverage"]["scored_units"] == 0
    assert result["coverage"]["excluded_units"] == {"pending": 1, "reference_unavailable": 1}
    assert result["metrics"]["unit_exact"]["recall"] is None


def test_failed_run_retains_target_and_character_denominators():
    result = score_case(case(unit("a", "business text")), observation(status="failed", errors=[{"code": "timeout"}]))
    assert result["metrics"]["unit_presence"]["target_units"] == 1
    assert result["metrics"]["unit_presence"]["recall"] == 0
    assert result["metrics"]["text"]["strict"]["cer"] == 1
    assert result["errors"] == [{"code": "timeout"}]


def test_table_record_grid_probe_finds_position_before_comparing_value():
    result = score_case(record_case(), grid_observation("101"))
    record = result["units"][0]
    metrics = result["metrics"]["table_records"]
    assert record["method"] == "native_grid_relation_probes"
    assert record["fields"][0]["native_id"] == "v24"
    assert metrics["field_strict_accuracy"]["value"] == 0
    assert metrics["field_coverage"]["value"] == 1
    assert metrics["field_text"]["strict"]["substitutions"] == 1
    assert metrics["whole_record_edit_distance"] is None
    assert result["metrics"]["text"]["strict"]["reference_chars"] == 0


def test_numeric_data_below_a_record_is_not_a_competing_column_header():
    actual = grid_observation()
    actual["pages"][0]["blocks"][0]["cells"].append({"id": "duplicate", "row": 2, "col": 1, "text": "2024"})
    result = score_case(record_case(), actual)
    metrics = result["metrics"]["table_records"]
    assert result["units"][0]["fields"][0]["outcome"] == "correct"
    assert metrics["target_fields"] == 1
    assert metrics["field_strict_accuracy"]["value"] == 1
    assert metrics["field_coverage"]["value"] == 1


def test_complete_label_combination_can_identify_one_of_two_native_tables():
    actual = grid_observation()
    other = copy.deepcopy(actual["pages"][0]["blocks"][0])
    other["id"] = "second-table"
    for cell in other["cells"]:
        cell["id"] = "other-" + cell["id"]
    other["cells"][0]["text"] = "2025"
    actual["pages"][0]["blocks"].append(other)
    result = score_case(record_case(), actual)
    assert result["units"][0]["fields"][0]["status"] == "compared"
    assert result["units"][0]["fields"][0]["native_id"] == "v24"
    assert result["metrics"]["table_records"]["field_strict_accuracy"]["value"] == 1


def test_record_reading_relation_uses_independently_localized_label():
    target = case(
        unit("record", "Revenue: 100", kind="table_record", table={"row_header_path": ["Revenue"]}),
        unit("note", "A complete source note."),
        relations=[{"type": "before", "source": "record", "target": "note", "status": "confirmed"}],
    )
    actual = observation(block("table", kind="table", cells=[
        {"id": "label", "text": "Revenue", "row": 1, "col": 0},
        {"id": "value", "text": "100", "row": 1, "col": 1},
    ]), block("note", "A complete source note."))
    result = score_case(target, actual)
    assert result["metrics"]["table_records"]["located_records"] == 1
    assert result["metrics"]["relations"]["recall"] == 1


def test_table_header_can_have_separate_complete_labels_in_one_native_cell():
    actual = grid_observation()
    actual["pages"][0]["blocks"][0]["cells"][0]["text"] = "2024\n$m"
    target = record_case()
    target["units"][0]["table"]["fields"][0].update(
        column_header_path=["2024", "$m"], unit="$m", period="2024"
    )
    result = score_case(target, actual)
    assert result["metrics"]["table_records"]["field_strict_accuracy"]["value"] == 1
    assert result["units"][0]["fields"][0]["binding"]["correct"] is True


def test_table_unit_label_is_not_found_inside_a_different_unit():
    actual = grid_observation()
    actual["pages"][0]["blocks"][0]["cells"][0]["text"] = "2024\n万元"
    target = record_case()
    target["units"][0]["table"]["fields"][0]["column_header_path"] = ["2024", "元"]
    result = score_case(target, actual)
    assert result["metrics"]["table_records"]["field_coverage"]["value"] == 0


def test_table_record_merged_native_headers_use_existing_span_ranges():
    actual = observation(block("table", kind="table", cells=[
        {"id": "top", "row": 0, "col": 1, "col_span": 2, "text": "Amount"},
        {"id": "year", "row": 1, "col": 1, "text": "2024"},
        {"id": "label", "row": 2, "col": 0, "text": "Revenue"},
        {"id": "value", "row": 2, "col": 1, "text": "100"},
    ]))
    target = case(unit("r", "Revenue Amount 2024 100", kind="table_record", table={
        "id": "t", "row_header_path": ["Revenue"], "fields": [
            {"column_header_path": ["Amount", "2024"], "value": "100"},
        ],
    }))
    result = score_case(target, actual)
    assert result["metrics"]["table_records"]["field_strict_accuracy"]["value"] == 1
    assert result["metrics"]["table_records"]["grid_relation"]["value"] == 1


def test_table_record_explicit_paths_are_read_without_constructing_paths():
    actual = observation(block("table", kind="table", cells=[{
        "id": "value", "row": 1, "col": 1, "text": "100",
        "row_header_path": ["营业收入"], "column_header_path": ["2024"], "unit": "万元",
    }]))
    result = score_case(record_case(unit="万元"), actual)
    assert result["units"][0]["method"] == "explicit_native_paths"
    assert result["metrics"]["table_records"]["binding"]["value"] == 1


def test_flat_table_output_does_not_manufacture_structure_or_record_ed():
    result = score_case(record_case(), observation(block("flat", "营业收入 2024 100 2023 200")))
    metrics = result["metrics"]["table_records"]
    assert metrics["field_strict_accuracy"]["value"] is None
    assert metrics["target_fields"] == 1
    assert metrics["field_coverage"]["value"] == 0
    assert metrics["whole_record_edit_distance"] is None


def test_table_record_missing_unit_is_not_filled_from_expected():
    result = score_case(record_case(unit="万元"), grid_observation())
    metrics = result["metrics"]["table_records"]
    assert metrics["field_strict_accuracy"]["value"] == 1
    assert metrics["binding"]["value"] is None
    assert metrics["binding_target_coverage"]["value"] == 0


def test_whole_record_without_manual_fields_stays_visually_reviewable():
    target = case(unit("r", "同意：原表留空", kind="table_record", table={"id": "t", "row_header_path": ["议案"]}))
    result = score_case(target, observation())
    assert result["units"][0]["reason"] == "no_declared_field_targets"
    assert result["metrics"]["table_records"]["whole_record_edit_distance"] is None


def test_image_reference_presence_does_not_claim_image_fidelity():
    result = score_case(case(unit("image", "Figure caption", kind="image")), observation(
        block("image", kind="image", caption="Figure caption", asset="native/image.png"),
    ))
    assert result["metrics"]["image_reference_presence"]["value"] == 1
    assert result["metrics"]["image_fidelity"]["value"] is None
    assert result["metrics"]["image_reference_presence"]["verifies_asset_bytes"] is False


def test_reports_separate_micro_and_document_macro():
    first = score_case(case(unit("a", "a")), observation(block("a", "a")))
    second = score_case(
        case(unit("b", "bbbbbbbbb"), sample_id="synthetic-b", document_id="doc-b", family_id="family-b"),
        observation(sample_id="synthetic-b"),
    )
    group = aggregate_reports([first, second])["groups"][0]["quality"]
    assert group["micro"]["text"]["strict"]["cer"] == 0.9
    assert group["macro_by_document"]["text.strict.cer"]["value"] == 0.5
    assert group["documents"] == 2


def test_reports_keep_perf_repetitions_and_warmup_out_of_quality800():
    quality = score_case(case(unit("a", "hello"), suite="quality800"), observation(
        block("a", "hello"), timing={"processing_seconds": 2}, input_page_count=1, repetition=1,
    ))
    performance = []
    for repetition in (1, 2, 3):
        result = copy.deepcopy(quality)
        result.update(suite="perf80", repetition=repetition, run_id=f"run-{repetition}")
        performance.append(result)
    warmup = copy.deepcopy(performance[0])
    warmup.update(phase="warmup", repetition=0)
    warmup["timing"] = {"processing_seconds": 100}
    report = aggregate_reports([quality, *performance, warmup])
    perf = next(group for group in report["groups"] if group["suite"] == "perf80")
    assert perf["quality"]["metrics"] is None
    assert perf["performance"]["measured_runs"] == 3
    assert perf["performance"]["samples"]["synthetic"]["mean_processing_seconds"] == 2
    assert perf["performance"]["samples"]["synthetic"]["at_least_three_measured_repetitions"] is True
    assert len(perf["performance"]["warmup"]) == 1
    assert report["weighted_total_score"] is None
    assert "不计算加权总分" in render_markdown(report)
    json.dumps(report, allow_nan=False)


def test_failure_cost_stays_in_round_throughput_and_missing_time_is_not_zero():
    success = score_case(case(unit("a", "hello"), suite="perf80"), observation(
        block("a", "hello"), timing={"processing_seconds": 2}, input_page_count=1, repetition=1,
    ))
    failed = copy.deepcopy(success)
    failed.update(sample_id="failed", status="timed_out", input_page_count=2)
    failed["timing"]["processing_seconds"] = 8
    group = aggregate_reports([success, failed])["groups"][0]["performance"]
    assert group["rounds"][0]["attempted_input_pages"] == 3
    assert group["rounds"][0]["completed_pages_per_second_including_failure_cost"] == 0.1
    assert group["failed_runs"] == 1
    failed["timing"]["processing_seconds"] = None
    group = aggregate_reports([success, failed])["groups"][0]["performance"]
    assert group["rounds"][0]["completed_pages_per_second_including_failure_cost"] is None
    assert group["round_duration_summary"]["n"] == 0
    assert group["failed_runs"] == 1


def test_duplicate_quality_runs_are_not_independent_documents():
    result = score_case(case(unit("a", "hello")), observation(block("a", "hello")))
    quality = aggregate_reports([result, copy.deepcopy(result)])["groups"][0]["quality"]
    assert quality["status"] == "duplicate_quality_runs_require_explicit_run_selection"
    assert quality["metrics"] is None


def test_missing_timing_is_not_zero_cost_and_failed_timing_stays_visible():
    result = score_case(case(unit("a", "hello")), observation(status="failed"))
    report = aggregate_reports([result])["groups"][0]
    assert report["quality"]["failed_samples"] == 1
    assert report["performance"]["measured_runs"] == 0
    assert report["performance"]["successful_run_throughput"]["pages_per_second"] is None
    assert len(report["performance"]["timing_unavailable"]) == 1


def test_scoring_refuses_unconfirmed_reference_or_wrong_sample():
    with pytest.raises(ValueError, match="visually confirmed"):
        score_case(case(review_status="pending"), observation())
    with pytest.raises(ValueError, match="sample_id"):
        score_case(case(), observation(sample_id="other"))
