"""Independent invented business cases, through the actual syntax readers."""

from copy import deepcopy

import pytest

from moparse_eval.adapters import read_docling, read_glm, read_mineru, read_paddle, read_visual
from moparse_eval.expected_readback import markdown_observation, read_expected
from moparse_eval.expected_scoring import grade_expected
from moparse_eval.packaging import write_json


def expected(tmp_path, text):
    root = tmp_path / "expected"
    folder = root / "neutral"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "answer.md").write_text(text)
    write_json(folder / "manifest.json", {
        "markdown": {"path": "answer.md"}, "source_map": {"entries": [
            {"source_pages": [1], "markdown_lines": [1, len(text.splitlines())]}]},
    })
    return read_expected({"id": "case", "document_id": "neutral", "source_pages": [1]}, root)


def md(text):
    return markdown_observation(text, sample_id="case", pipeline="P01", pages=[1])


def business(score):
    return [row for row in score["outcomes"] if row["kind"] == "business_field"]


@pytest.mark.parametrize("text", [
    "The policy is: do not distribute; approval remains pending.",
    "The board records the following conditions:",
    "事项说明：暂不支付；仍需独立批准。",
])
@pytest.mark.parametrize("prefix", ["", "- "])
def test_narrative_punctuation_never_creates_empty_or_partial_fields(tmp_path, text, prefix):
    reference = expected(tmp_path, prefix + text + "\n")
    assert not any(row.get("record") for row in reference["targets"])
    score = grade_expected(reference, md(prefix + text))
    assert not business(score)
    assert score["text_metrics"]["reference_characters"] == len(text)


def test_near_complete_paragraph_is_measured_by_characters(tmp_path):
    text = "The board approved seventeen units, subject to independent review."
    score = grade_expected(expected(tmp_path, text), md(text.replace("seventeen", "eighteen")))
    metric = score["text_metrics"]
    assert metric["located_targets"] == 1
    assert 0 < metric["aligned_strict_cer"] < .2
    assert metric["preserved_characters"] > len(text) * .8
    assert any(row["outcome"] == "incorrect" for row in score["outcomes"])


@pytest.mark.parametrize("shape", ["gfm", "list", "visual", "docvortex", "paddle", "glm", "docling"])
def test_multi_fact_cell_and_native_syntax_are_equivalent(tmp_path, shape):
    reference = expected(tmp_path, "- Net sales: Amount: 17; Change: -2%\n")
    html = "<table><tr><th>Item</th><th>Result</th></tr><tr><td>Net sales</td><td>Amount: 17; Change: -2%</td></tr></table>"
    if shape == "list":
        candidate = md("- Net sales\n  - Amount: 17\n  - Change: -2%\n")
    elif shape == "gfm":
        candidate = md("|Item|Result|\n|---|---|\n|Net sales|Amount: 17; Change: -2%|\n")
    else:
        if shape == "visual":
            blocks = read_visual([{"type": "table", "content": html}], 1)
        elif shape == "docvortex":
            blocks = read_mineru({"blocks": [{"type": "table", "index": 0, "content": [
                {"type": "table_body", "index": 0, "content": html}]}]}, 1)
        elif shape == "paddle":
            blocks = read_paddle({"res": {"parsing_res_list": [{"block_label": "table", "block_content": html}]}}, 1)
        elif shape == "docling":
            cells = [{"start_row_offset_idx": row, "start_col_offset_idx": col,
                      "row_span": 1, "col_span": 1, "column_header": row == 0, "text": text}
                     for row, col, text in [(0, 0, "Item"), (0, 1, "Result"),
                                             (1, 0, "Net sales"), (1, 1, "Amount: 17; Change: -2%")]]
            blocks = read_docling({"body": {"children": [{"$ref": "#/tables/0"}]},
                "tables": [{"self_ref": "#/tables/0", "label": "table", "prov": [{"page_no": 1}],
                            "data": {"num_rows": 2, "num_cols": 2, "table_cells": cells}}]}, 1)
        else:
            blocks = read_glm({"json_result": [[{"label": "table", "content": html}]]}, 1)
        candidate = {"sample_id": "case", "pipeline": "P01", "status": "success", "pages": [{"page": 1, "blocks": blocks}]}
    rows = business(grade_expected(reference, candidate))
    assert len(rows) == 2
    assert all(row["outcome"] == "correct" for row in rows)
    wrong = deepcopy(candidate)
    for page in wrong["pages"]:
        for block in page["blocks"]:
            block["text"] = block.get("text", "").replace("-2%", "2%")
            for cell in block.get("cells", []):
                cell["text"] = cell["text"].replace("-2%", "2%")
    assert any(row["outcome"] == "incorrect" for row in business(grade_expected(reference, wrong)))


def test_expected_narrative_and_full_parent_qualifiers_do_not_disappear(tmp_path):
    reference = expected(tmp_path, "## Restricted operations\n\nThe following limits apply; no guarantee is provided:\n\n- Region East\n  - Sales: Amount: 17; Change: -2%\n")
    score = grade_expected(reference, md("## Restricted operations\n\n- Region East\n  - Sales: Amount: 17; Change: -2%\n"))
    assert any(row["outcome"] == "incorrect" and "no guarantee" in str(row["expected"]) for row in score["outcomes"])


def test_same_value_in_other_table_cannot_rescue_wrong_year_unit_or_scope(tmp_path):
    text = "## Table 3\n\n单位：万元\n\n- Sales: 2024: 17; 2023: 11\n\n## Table 4\n\n- Sales: 2024: 9\n"
    reference = expected(tmp_path, text)
    for wrong in [text.replace("2024: 17; 2023: 11", "2024: 11; 2023: 17"),
                  text.replace("万元", "千元"), text.replace("2024: 17", "2024: -17")]:
        assert any(row["outcome"] == "incorrect" for row in business(grade_expected(reference, md(wrong))))


def test_conflicting_statement_is_not_selected_by_expected_value(tmp_path):
    reference = expected(tmp_path, "- Sales: Amount: 17\n")
    assert business(grade_expected(reference, md("- Sales: Amount: 17\n- Sales: Amount: 19\n")))[0]["outcome"] == "incorrect"


def test_identity_and_private_metadata_cannot_change_final_grade(tmp_path):
    reference = expected(tmp_path, "- Sales: Amount: 17\n")
    output = md("- Sales: Amount: 11\n")
    first = grade_expected(reference, output)["outcomes"]
    for number in range(1, 9):
        candidate = deepcopy(output)
        candidate.update(pipeline=f"P{number:02}", hidden_ir={"Amount": "17"})
        assert grade_expected(reference, candidate)["outcomes"] == first


def test_digit_spaces_and_negation_remain_meaningful(tmp_path):
    text = "No distribution is approved. The identifier is 12."
    reference = expected(tmp_path, text)
    for wrong in [text.replace("12", "1 2"), text.replace("No ", "")]:
        score = grade_expected(reference, md(wrong))
        assert score["incorrect"] > 0


def test_native_single_named_value_is_read_without_a_private_field(tmp_path):
    reference = expected(tmp_path, "Security codes: 000017、000011\n")
    blocks = read_visual([{"type": "text", "content": "Security codes: 000017、000011"}], 1)
    output = {"sample_id": "case", "pages": [{"page": 1, "blocks": blocks}]}
    assert all(row["outcome"] == "correct" for row in business(grade_expected(reference, output)))


def test_explicit_local_note_is_a_required_business_condition(tmp_path):
    text = "- Sales: Amount: 17 (Note: subject to approval)\n"
    reference = expected(tmp_path, text)
    assert business(grade_expected(reference, md(text)))[0]["outcome"] == "correct"
    wrong = text.replace("subject to approval", "approval is unnecessary")
    assert business(grade_expected(reference, md(wrong)))[0]["outcome"] == "incorrect"


def test_explicit_heading_ownership_is_not_global_literal_presence(tmp_path):
    text = "## North\n\nApproval is required before distribution.\n\n## South\n\nNo approval is required.\n"
    reference = expected(tmp_path, text)
    wrong = "## North\n\nNo approval is required.\n\n## South\n\nApproval is required before distribution.\n"
    score = grade_expected(reference, md(wrong))
    paragraphs = [row for row in score["outcomes"] if row["kind"] == "text"]
    assert len(paragraphs) == 2 and all(row["outcome"] == "incorrect" for row in paragraphs)
    # A similar paragraph inside the correct section may now be located, but
    # its wording remains wrong. Exact foreign text must stay rejected.
    assert all(any("heading_scope_conflict" in hit["reasons"]
                   for hit in row["localization"]["candidates"]) for row in paragraphs)


def test_expected_table_multi_fact_cell_is_not_one_opaque_value(tmp_path):
    html = "<table><tr><th>Item</th><th>Result</th></tr><tr><td>Sales</td><td>Amount: 17; Change: -2%</td></tr></table>"
    reference = expected(tmp_path, html)
    rows = business(grade_expected(reference, md(html)))
    assert len(rows) == 2 and all(row["outcome"] == "correct" for row in rows)


def test_duplicate_prose_is_recorded_as_extra_content(tmp_path):
    text = "The company has no outstanding guarantee."
    score = grade_expected(expected(tmp_path, text), md(text + "\n\n" + text))
    assert score["text_metrics"]["duplicate_occurrences_diagnostic"] == 1


@pytest.mark.parametrize("native", [False, True])
def test_space_separated_explicit_identity_assertions_do_not_swallow_neighbors(tmp_path, native):
    reference = expected(tmp_path, "Security codes: 000017、000011\n\nTicker: Alpha、Beta\n")
    text = "Security codes: 000017、000011 Ticker: Alpha、Beta Announcement: 2024-3"
    output = md(text)
    if native:
        output = {"sample_id": "case", "pages": [{"page": 1, "blocks": read_visual([
            {"type": "text", "content": text}], 1)}]}
    rows = business(grade_expected(reference, output))
    assert len(rows) == 2 and all(row["outcome"] == "correct" for row in rows)


def test_expected_spans_compile_every_row_and_complete_header_path(tmp_path):
    html = ("<table><tr><th rowspan='2'>Group</th><th rowspan='2'>Metric</th><th colspan='2'>2024</th><th>2023</th></tr>"
            "<tr><th>Amount</th><th>Change</th><th>Amount</th></tr>"
            "<tr><th scope='rowgroup' rowspan='2'>East</th><th scope='row'>Sales</th><td>17</td><td>-2%</td><td>11</td></tr>"
            "<tr><th scope='row'>Cost</th><td>9</td><td>3%</td><td>7</td></tr></table>")
    reference = expected(tmp_path, html)
    rows = business(grade_expected(reference, md(html)))
    assert len(rows) == 6 and all(row["outcome"] == "correct" for row in rows)
    assert {tuple(row["row_header_path"]) for row in rows} == {("East", "Sales"), ("East", "Cost")}
    assert all(row["outcome"] == "incorrect" for row in business(grade_expected(reference, md(html.replace('East', 'West')))))


def test_introductory_mentions_do_not_replace_actual_heading_anchors(tmp_path):
    text = "## North\n\nApproval is required.\n\n## South\n\nNo distribution is approved.\n"
    reference = expected(tmp_path, text)
    candidate = md("North and South are operating regions.\n\n" + text)
    result = grade_expected(reference, candidate)
    assert all(row["outcome"] == "correct" for row in result["outcomes"])


def test_repeated_signature_text_is_located_inside_its_own_section(tmp_path):
    text = "## Board\n\nExample Ltd\n\nSeven December 2024\n"
    reference = expected(tmp_path, text)
    output = md("Example Ltd\n\nSeven December 2024\n\n" + text)
    assert all(row["outcome"] == "correct" for row in grade_expected(reference, output)["outcomes"])


def test_one_prose_occurrence_cannot_satisfy_two_required_occurrences(tmp_path):
    sentence = "Approval is required before distribution."
    reference = expected(tmp_path, sentence + "\n\n" + sentence)
    score = grade_expected(reference, md(sentence))
    assert score["text_metrics"]["missing_targets"] == 1
    assert score["text_metrics"]["character_preservation"] == .5


@pytest.mark.parametrize("reference,actual", [("Total amount equals 12", "Total amount equals 123"),
                                               ("批准", "未批准"), ("12", "-12")])
def test_literal_infix_does_not_hide_adjacent_number_or_negation(tmp_path, reference, actual):
    score = grade_expected(expected(tmp_path, reference), md(actual))
    assert score["incorrect"] > 0
    assert any(row.get("differences") for row in score["outcomes"])


def test_sample_names_do_not_select_answers_or_evidence(tmp_path):
    reference = expected(tmp_path, "- Sales: Amount: 17\n")
    output = md("- Sales: Amount: 17\n")
    first = grade_expected(reference, output)["outcomes"]
    for name in ["unknown-file", "sample-928", "renamed-document"]:
        renamed_reference, renamed_output = deepcopy(reference), deepcopy(output)
        renamed_reference["sample_id"] = renamed_output["sample_id"] = name
        renamed_output["filename"] = name + ".pdf"
        assert grade_expected(renamed_reference, renamed_output)["outcomes"] == first


def test_grading_has_no_pdf_or_reference_write_path(tmp_path, monkeypatch):
    from pathlib import Path

    import pymupdf
    reference = expected(tmp_path, "No distribution is approved.\n")
    original = Path.write_text

    def no_reference_write(path, *args, **kwargs):
        if path.is_relative_to(tmp_path / "expected"):
            raise AssertionError("reference write attempted")
        return original(path, *args, **kwargs)

    def no_pdf(*args, **kwargs):
        raise AssertionError("PDF access attempted by grader")

    monkeypatch.setattr(Path, "write_text", no_reference_write)
    monkeypatch.setattr(pymupdf, "open", no_pdf)
    assert grade_expected(reference, md("No distribution is approved."))["incorrect"] == 0


def test_sentence_end_punctuation_is_equivalent_with_strict_difference_retained(tmp_path):
    reference = expected(tmp_path, "Total amount equals 12")
    score = grade_expected(reference, md("Total amount equals 12."))
    assert score["incorrect"] == 0
    assert score["text_metrics"]["aligned"]["strict"]["insertions"] == 1


def test_qualifier_grammar_labels_are_not_extra_business_words(tmp_path):
    reference = expected(tmp_path, "- Sales: Amount: 17 (Unit: USD million; Period: 2024)\n")
    output = md("- Sales: Amount: 17（单位：USD million；期间：2024）\n")
    assert grade_expected(reference, output)["incorrect"] == 0


def test_explicit_expected_unit_is_authoritative_even_when_unusual(tmp_path):
    text = "- Age: 52（单位：股）\n"
    reference = expected(tmp_path, text)
    rows = business(grade_expected(reference, md(text)))
    assert len(rows) == 1 and rows[0]["expected"]["value"] == "52"
    assert rows[0]["expected"]["required"]["unit"] == "股"
    assert rows[0]["outcome"] == "correct"


def test_single_named_property_can_be_expressed_as_a_vertical_column(tmp_path):
    reference = expected(tmp_path, "Legal name: Example Ltd\n")
    output = md("<table><tr><th>Legal name</th></tr><tr><td>Example Ltd</td></tr></table>")
    rows = business(grade_expected(reference, output))
    assert len(rows) == 1 and rows[0]["outcome"] == "correct"


def test_repeated_printed_headings_use_the_local_occurrence(tmp_path):
    text = "# Review\n\n## Scope\n\nEarlier description.\n\n## Response\n\nFirst response.\n\n## Scope\n\nLater description.\n\n## Response\n\nLast response.\n"
    reference = expected(tmp_path, text)
    assert all(row["outcome"] == "correct" for row in grade_expected(reference, md(text))["outcomes"])
    moved = text.replace("Later description.\n\n", "").replace("First response.", "First response.\n\nLater description.")
    row = next(row for row in grade_expected(reference, md(moved))["outcomes"] if row["expected"] == "Later description.")
    assert row["outcome"] == "incorrect"


def test_repeated_prose_with_terminal_punctuation_variants_is_not_reused(tmp_path):
    reference = expected(tmp_path, "# Review\n\nSource: Independent survey.\n\nSource: Independent survey.\n")
    for literal, count in [("Source: Independent survey", 2), ("Source: Independent survey.", 2), ("Source: Independent survey", 1)]:
        rows = [row for row in grade_expected(reference, md("# Review\n\n" + "\n\n".join([literal] * count)))["outcomes"] if row["kind"] == "text"]
        assert sum(row["outcome"] == "correct" for row in rows) == count


def test_row_label_unit_is_explicit_in_html_and_printed_records(tmp_path):
    reference = expected(tmp_path, "- Coverage ratio (times): 2027: 0.8\n")
    for output in ["- Coverage ratio (times)；2027：0.8。", "<table><tr><th>Metric</th><th>2027</th></tr><tr><td>Coverage ratio (times)</td><td>0.8</td></tr></table>"]:
        row = business(grade_expected(reference, md(output)))[0]
        assert row["outcome"] == "correct"
        wrong = business(grade_expected(reference, md(output.replace("times", "%"))))[0]
        assert wrong["outcome"] == "incorrect"


def test_unrelated_rating_row_does_not_create_a_vertical_property_claim(tmp_path):
    reference = expected(tmp_path, "- Efficient workflow: reduces the required work\n")
    output = "- Efficient workflow: reduces the required work\n\n<table><tr><th>Approach</th><th>Impact</th><th>Cost</th></tr><tr><td>Efficient workflow</td><td>high</td><td>low</td></tr></table>"
    assert business(grade_expected(reference, md(output)))[0]["outcome"] == "correct"


def test_one_printed_heading_cannot_supply_two_expected_occurrences(tmp_path):
    reference = expected(tmp_path, "## Review\n\nFirst discussion.\n\n## Review\n\nSecond discussion.\n")
    rows = [row for row in grade_expected(reference, md("## Review\n\nFirst discussion.\n\nSecond discussion."))["outcomes"] if row["kind"] == "heading"]
    assert [row["outcome"] for row in rows] == ["correct", "incorrect"]


def test_split_or_typographic_heading_locates_scope_without_erasing_character_errors(tmp_path):
    for title, output in [("机构年度事项的专项报告", "## 机构年度事项\n\n## 的专项报告"),
                          ("Director’s Review", "## Director's Review"),
                          ("第二节 重要提示", "## 第二节重要提示")]:
        reference = expected(tmp_path, "## " + title + "\n\nA complete statement follows.\n")
        rows = grade_expected(reference, md(output + "\n\nA complete statement follows."))["outcomes"]
        assert next(row for row in rows if row["kind"] == "text")["outcome"] == "correct"


def test_caption_inserted_in_prose_keeps_its_own_correct_target(tmp_path):
    reference = expected(tmp_path, "## Scope\n\nThe opening sentence continues with the closing sentence.\n\nSource: Independent agency.\n")
    output = "## Scope\n\nThe opening sentence continues\n\nSource: Independent agency.\n\nwith the closing sentence."
    rows = [row for row in grade_expected(reference, md(output))["outcomes"] if row["kind"] == "text"]
    assert [row["outcome"] for row in rows] == ["incorrect", "correct"]


def test_longer_complete_name_keeps_its_own_occurrence_before_prefix_claims(tmp_path):
    reference = expected(tmp_path, "## Audit\n\nIndependent Partners\n\nIndependent Partners (registered partnership)\n")
    rows = [row for row in grade_expected(reference, md("## Audit\n\nIndependent Partners (registered partnership)"))["outcomes"] if row["kind"] == "text"]
    assert [row["outcome"] for row in rows] == ["incorrect", "correct"]


def test_heading_scope_can_be_printed_without_markup_and_figure_label_can_follow(tmp_path):
    for title, candidate in [("2027 年度报告", "2027年度报告"),
                             ("Figure 3. System capacity¹", "## System capacity \\( ^{1} \\)\n\nFigure 3")]:
        reference = expected(tmp_path, "## " + title + "\n\nA complete statement follows.\n")
        row = next(row for row in grade_expected(reference, md(candidate + "\n\nA complete statement follows."))["outcomes"] if row["kind"] == "text")
        assert row["outcome"] == "correct"


def test_incomplete_heading_does_not_certify_the_complete_expected_scope(tmp_path):
    reference = expected(tmp_path, "## Report: Supplemental review\n\nA complete statement follows.\n")
    row = next(row for row in grade_expected(reference, md("## Report\n\nA complete statement follows."))["outcomes"] if row["kind"] == "text")
    assert row["outcome"] == "incorrect"


def test_identical_leaf_headings_still_require_their_printed_parent_scope(tmp_path):
    text = "# Review\n\n## Group A\n\n### Status\n\nNot applicable.\n\n## Group B\n\n### Status\n\nNot applicable.\n"
    reference = expected(tmp_path, text)
    assert all(row["outcome"] == "correct" for row in grade_expected(reference, md(text))["outcomes"])
    output = "# Review\n\n## Group A\n\n### Status\n\nNot applicable.\n\nNot applicable.\n\n## Group B\n\n### Status\n"
    rows = [row for row in grade_expected(reference, md(output))["outcomes"] if row["kind"] == "text"]
    assert [row["outcome"] for row in rows] == ["correct", "incorrect"]


@pytest.mark.parametrize("marked", [True, False])
def test_attachment_reference_is_not_the_start_of_the_later_table(tmp_path, marked):
    text = "# Report\n\n## Conclusion\n\nTable 2: Supplementary details\n\nThe board signed.\n\n## Table 2: Supplementary details\n\nSeparate content.\n"
    output = text if marked else text.replace("## Table 2: Supplementary details", "Table 2: Supplementary details")
    rows = grade_expected(expected(tmp_path, text), md(output))["outcomes"]
    assert next(row for row in rows if row["expected"] == "The board signed.")["outcome"] == "correct"


def test_plain_and_marked_parent_titles_have_the_same_scope(tmp_path):
    reference = expected(tmp_path, "# Business\n\n## Details\n\nA complete statement.\n")
    output = "Business\n\n## Details\n\nA complete statement.\n\n# Business\n"
    assert next(row for row in grade_expected(reference, md(output))["outcomes"] if row["kind"] == "text")["outcome"] == "correct"


@pytest.mark.parametrize("shape", ["list", "gfm", "visual"])
def test_shared_column_label_keeps_each_named_parent_and_its_text(tmp_path, shape):
    text = "# Risks\n\n- Risk: Delivery\n  - Controls\n    - Weekly review.\n- Risk: Capacity\n  - Controls\n    - Independent testing.\n"
    reference = expected(tmp_path, text)
    html = "<table><tr><th>Risk</th><th>Controls</th></tr><tr><td>Delivery</td><td>Weekly review.</td></tr><tr><td>Capacity</td><td>Independent testing.</td></tr></table>"
    if shape == "list":
        output = md(text)
    elif shape == "gfm":
        output = md("# Risks\n\n|Risk|Controls|\n|---|---|\n|Delivery|Weekly review.|\n|Capacity|Independent testing.|\n")
    else:
        output = {"sample_id": "case", "pipeline": "P08", "status": "success", "pages": [{"page": 1,
            "blocks": read_visual([{"type": "title", "content": "Risks"}, {"type": "table", "content": html}], 1)}]}
    score = grade_expected(reference, output)
    assert all(row["outcome"] == "correct" for row in score["outcomes"])
    wrong = deepcopy(output)
    for page in wrong["pages"]:
        for block in page["blocks"]:
            block["text"] = block.get("text", "").replace("Capacity", "Other")
            for cell in block.get("cells", []):
                cell["text"] = cell.get("text", "").replace("Capacity", "Other")
    if shape != "list":
        rows = grade_expected(reference, wrong)["outcomes"]
        assert next(row for row in rows if row["expected"] == "Independent testing.")["outcome"] == "incorrect"


@pytest.mark.parametrize("literal,correct", [("00481,92714", True), ("00481,92715", False),
                                           ("0048192714", False), ("00481 92714", False)])
def test_value_list_comma_spacing_does_not_join_or_repair_numbers(tmp_path, literal, correct):
    reference = expected(tmp_path, "- Reference codes: 00481, 92714\n")
    row = business(grade_expected(reference, md("- Reference codes: " + literal)))[0]
    assert (row["outcome"] == "correct") is correct
    if correct:
        assert row["raw_value_text"]["strict"]["distance"] > 0


@pytest.mark.parametrize("conflicting", [False, True])
def test_many_unqualified_claims_agree_or_conflict_without_answer_selection(tmp_path, conflicting):
    reference = expected(tmp_path, "- Sales: Amount: 17\n")
    cells = "".join(f"<tr><td>Sales</td><td>{19 if conflicting and index == 1 else 17}</td></tr>" for index in range(100))
    output = md("<table><tr><th>Item</th><th>Amount</th></tr>" + cells + "</table>")
    assert business(grade_expected(reference, output))[0]["outcome"] == ("incorrect" if conflicting else "correct")


@pytest.mark.parametrize("shape", ["html", "gfm"])
@pytest.mark.parametrize("declared", [False, True])
def test_explicit_label_units_have_the_same_policy_in_tables_and_records(tmp_path, shape, declared):
    reference = expected(tmp_path, "- Name: Mira; Age: 52" + ("（单位：股）" if declared else "") + "\n")
    output = md("<table><tr><th>Name</th><th>Age(股)</th></tr><tr><td>Mira</td><td>52</td></tr></table>"
                if shape == "html" else "|Name|Age(股)|\n|---|---|\n|Mira|52|\n")
    age = next(row for row in business(grade_expected(reference, output)) if row["expected"]["column_header_path"] == ["Age"])
    assert age["outcome"] == ("correct" if declared else "incorrect")


@pytest.mark.parametrize("role", ["text", "heading", "header", "list_item"])
def test_native_text_roles_preserve_explicit_assertions(tmp_path, role):
    reference = expected(tmp_path, "- Entity: Example; Amount: 17\n")
    output = {"sample_id": "case", "pages": [{"page": 1, "blocks": read_visual([
        {"type": role, "content": "Entity: Example; Amount: 17"}], 1)}]}
    assert all(row["outcome"] == "correct" for row in business(grade_expected(reference, output)))


@pytest.mark.parametrize("reference", ["- Standard: Topic 718: Compensation\n",
                                         "- Standard: Definition: Topic 718: Compensation\n"])
def test_single_cell_statement_does_not_hide_original_grid_value(tmp_path, reference):
    expected_view = expected(tmp_path, reference)
    output = md("|Item|Definition|\n|---|---|\n|Standard|Topic 718: Compensation|\n")
    rows = business(grade_expected(expected_view, output))
    assert rows and all(row["outcome"] == "correct" for row in rows)


def test_conflicting_inline_and_grid_statements_cannot_be_selected_by_value(tmp_path):
    reference = expected(tmp_path, "- Sales: Amount: 17\n")
    output = md("|Item|Result|Amount|\n|---|---|---|\n|Sales|Amount: 17|19|\n")
    assert business(grade_expected(reference, output))[0]["outcome"] == "incorrect"
