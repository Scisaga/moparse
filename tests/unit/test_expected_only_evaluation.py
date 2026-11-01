"""Programmatic expected-only evaluation of invented references and outputs."""

from copy import deepcopy
from pathlib import Path

import pytest

from moparse_eval import cli
from moparse_eval.expected_readback import elements, markdown_observation, read_expected
from moparse_eval.expected_scoring import grade_expected, require_paired_targets
from moparse_eval.packaging import write_json

REFERENCE = "## Results\n\n单位：人民币百万元。\n\n- Revenue\n  - 2024：17\n  - 2023：11\n\nNo dividend was approved.\n"


def reference(tmp_path, markdown=REFERENCE, *, selected=(1,)):
    root = tmp_path / "reference"
    doc = root / "invented-document"
    doc.mkdir(parents=True)
    (doc / "expected.md").write_text(markdown)
    write_json(doc / "manifest.json", {
        "markdown": {"path": "expected.md"},
        "source_map": {"entries": [{"source_pages": [1], "markdown_lines": [1, len(markdown.splitlines())]}]},
    })
    sample = {"id": "invented", "document_id": "invented-document", "source_pages": list(selected),
              "evaluation": "/must-not-read-old-answers.json"}
    return read_expected(sample, root), root


def candidate(text, pipeline="P01"):
    return markdown_observation(text, sample_id="invented", pipeline=pipeline, pages=[1])


def fields(score):
    return [row for row in score["outcomes"] if row["kind"] == "business_field"]


def test_scope_caption_ending_colon_is_not_an_outer_field(tmp_path):
    markdown = "- Name: Mira; Age: 47; Other boards: 。\n"
    expected, _ = reference(tmp_path, markdown)
    actual = "- Scope: The following table lists the nominees:; Name: Mira; Age: 47; Other boards: 。\n"
    result = fields(grade_expected(expected, candidate(actual)))
    assert len(result) == 3 and all(row["outcome"] == "correct" for row in result)
    assert fields(grade_expected(expected, candidate(actual.replace("Mira", "Nora"))))[1]["outcome"] == "incorrect"


def test_named_parent_and_its_value_survive_explicit_record_conversion(tmp_path):
    markdown = "- Fixed instruments: Long-term loan\n  - 2024: 17\n"
    expected, _ = reference(tmp_path, markdown)
    actual = "- Scope: Principal instruments:; Fixed instruments: Long-term loan; 2024: 17。\n"
    result = fields(grade_expected(expected, candidate(actual)))
    assert len(result) == 2 and all(row["outcome"] == "correct" for row in result)
    wrong = fields(grade_expected(expected, candidate(actual.replace("Long-term loan", "Other loan"))))
    assert all(row["outcome"] == "incorrect" for row in wrong)


@pytest.mark.parametrize("representation", ["scope_path", "split_caption"])
def test_explicit_scope_paths_preserve_the_same_complete_caption(tmp_path, representation):
    markdown = ("## 附表7 2023年银行概览（季末余额）\n\n- Other: Q1: 17\n\n"
                "## 附表9 2023年企业概览（季末余额）\n\n- Other: Q1: 11\n")
    expected, _ = reference(tmp_path, markdown)
    actual = ("- 范围：附表 7 / 2023年银行概览 / （季末余额）；Name：Other；Q1：17。\n"
              "- 范围：附表 9 / 2023年企业概览 / （季末余额）；Name：Other；Q1：11。\n")
    if representation == "split_caption":
        actual = ("附表 7\n\n2023年银行概览\n\n（季末余额）\n\n| Item | Q1 |\n|---|---|\n|Other|17|\n\n"
                  "附表 9\n\n2023年企业概览\n\n（季末余额）\n\n| Item | Q1 |\n|---|---|\n|Other|11|\n")
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(actual))))
    wrong = actual.replace("附表 7", "附表 9", 1).replace("2023年银行概览", "2023年企业概览", 1)
    assert fields(grade_expected(expected, candidate(wrong)))[0]["outcome"] == "incorrect"
    assert all(row["outcome"] == "incorrect" for row in fields(grade_expected(
        expected, candidate(actual.replace("2023年", "2024年")))))
    assert fields(grade_expected(expected, candidate(actual.replace("附表 7", "附表 17"))))[0]["outcome"] == "incorrect"


@pytest.mark.parametrize("unrelated", ["Amount: Mira", "Note: Mira", "Count: Mira"])
def test_native_prose_values_cannot_replace_business_identity(tmp_path, unrelated):
    expected, _ = reference(tmp_path, "- Name: Mira; Age: 47\n")
    output = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [{
        "id": "paragraph", "kind": "paragraph", "text": f"Name: Nora; {unrelated}; Age: 47"}]}]}
    assert all(row["outcome"] == "incorrect" for row in fields(grade_expected(expected, output)))


def test_same_leaf_in_a_different_parent_still_needs_its_table_scope(tmp_path):
    markdown = "## Table 7\n\n- Other: Q1: 17\n\n## Table 9\n\n- Liabilities\n  - Other: Q1: 11\n"
    expected, _ = reference(tmp_path, markdown)
    actual = "- Scope: Table 7; Name: Other; Q1: 17\n- Scope: Table 9; Name: Liabilities / Other; Q1: 11\n"
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(actual))))
    # Explicitly swap both values, retaining their actual scopes.
    wrong = "- Scope: Table 7; Name: Other; Q1: 11\n- Scope: Table 9; Name: Liabilities / Other; Q1: 17\n"
    assert all(row["outcome"] == "incorrect" for row in fields(grade_expected(expected, candidate(wrong))))


def test_numbered_table_owns_even_a_unique_business_label(tmp_path):
    expected, _ = reference(tmp_path, "## Table 7\n\n- Revenue: Q1: 17\n\n## Table 9\n\n- Expense: Q1: 11\n")
    actual = "- Scope: Table 7; Name: Revenue; Q1: 17\n- Scope: Table 9; Name: Expense; Q1: 11\n"
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(actual))))
    swapped = actual.replace("Table 7", "Table 0").replace("Table 9", "Table 7").replace("Table 0", "Table 9")
    assert all(row["outcome"] == "incorrect" for row in fields(grade_expected(expected, candidate(swapped))))


def test_reads_full_expected_instead_of_an_annotation_subset(tmp_path):
    expected, root = reference(tmp_path)
    original = (root / "invented-document/expected.md").read_bytes()
    score = grade_expected(expected, candidate(REFERENCE))
    assert score["targets"] == score["correct"] and score["incorrect"] == 0
    assert len(fields(score)) == 2
    assert any(row["expected"] == "No dividend was approved." for row in score["outcomes"])
    assert (root / "invented-document/expected.md").read_bytes() == original


@pytest.mark.parametrize("old,new", [("2024：17", "2024：-17"), ("2024：17", "2024：11"),
                                    ("人民币百万元", "人民币千元"), ("Revenue", "Expense")])
def test_wrong_values_units_and_business_identity_are_incorrect(tmp_path, old, new):
    expected, _ = reference(tmp_path)
    score = grade_expected(expected, candidate(REFERENCE.replace(old, new)))
    assert any(row["outcome"] == "incorrect" for row in fields(score))
    assert score["targets"] == score["correct"] + score["incorrect"]


def test_negation_is_not_replaced_by_keyword_presence(tmp_path):
    expected, _ = reference(tmp_path)
    score = grade_expected(expected, candidate(REFERENCE.replace("No dividend was approved.", "A dividend was approved.")))
    row = next(x for x in score["outcomes"] if x["expected"] == "No dividend was approved.")
    assert row["outcome"] == "incorrect"


def test_all_eight_pipeline_ids_get_identical_results_and_evidence(tmp_path):
    expected, _ = reference(tmp_path)
    before = deepcopy(expected)
    scores = [grade_expected(expected, candidate(REFERENCE, f"P{i:02}")) for i in range(1, 9)]
    require_paired_targets(scores)
    first = {key: value for key, value in scores[0].items() if key != "pipeline"}
    assert all({key: value for key, value in score.items() if key != "pipeline"} == first for score in scores)
    assert expected == before


def test_published_markdown_has_no_private_metadata_input(tmp_path):
    expected, _ = reference(tmp_path)
    output = candidate(REFERENCE)
    score = grade_expected(expected, output)
    output["private_ir"] = {"unit": "wrong", "period": "1999"}
    assert grade_expected(expected, output) == score


def test_targets_cannot_silently_disappear_from_one_pipeline(tmp_path):
    expected, _ = reference(tmp_path)
    score = grade_expected(expected, candidate(REFERENCE))
    damaged = deepcopy(score)
    damaged["outcomes"].pop()
    with pytest.raises(ValueError, match="identical expected targets"):
        require_paired_targets([score, damaged])


def test_explicit_inline_multi_year_fields_are_read_with_their_subject(tmp_path):
    markdown = "## Results\n\n- Revenue ($m): 2024: 17; 2023: 11; Change: 5%.\n"
    expected, _ = reference(tmp_path, markdown)
    score = grade_expected(expected, candidate(markdown))
    assert len(fields(score)) == 3
    assert all(row["outcome"] == "correct" for row in fields(score))


def test_markdown_heading_and_nested_groups_retain_syntax_locations():
    parsed = elements("## Results\n\n- North\n  - Other\n    - 2024: 17\n")
    assert parsed[-1].parents == ("North", "Other")
    assert parsed[-1].lines == (5, 5)


def test_expected_reader_never_opens_a_pdf(tmp_path, monkeypatch):
    original_open = Path.open

    def only_authored_text(path, *args, **kwargs):
        assert path.suffix != ".pdf"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", only_authored_text)
    expected, _ = reference(tmp_path)
    assert grade_expected(expected, candidate(REFERENCE))["incorrect"] == 0


def test_legacy_adjudication_argument_fails_before_reading_any_input(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("explicit legacy adjudication must fail before reading or writing files")

    monkeypatch.setattr(cli, "read_json", forbidden)
    monkeypatch.setattr(cli, "write_json", forbidden)
    with pytest.raises(ValueError, match="does not accept adjudications"):
        cli.score_run(tmp_path / "missing-run", adjudications=tmp_path / "must-not-open.json")


@pytest.mark.parametrize("format_name", ["html", "gfm", "sdk", "prose"])
def test_same_business_fields_across_public_and_native_formats(tmp_path, format_name):
    from moparse_eval.adapters import html_cells, markdown_cells

    expected, _ = reference(tmp_path)
    if format_name == "prose":
        output = candidate(REFERENCE)
    else:
        if format_name == "html":
            cells = html_cells('<table><tr><td>(人民币百万元)</td><td>2024</td><td>2023</td></tr>'
                               '<tr><td>Revenue</td><td>17</td><td>11</td></tr></table>')
        elif format_name == "gfm":
            cells = markdown_cells('|(人民币百万元)|2024|2023|\n|---|---|---|\n|Revenue|17|11|')
        else:
            cells = [{"id": "v1", "text": "17", "row_header_path": ["Revenue"],
                      "column_header_path": ["2024"], "unit": "人民币百万元"},
                     {"id": "v2", "text": "11", "row_header_path": ["Revenue"],
                      "column_header_path": ["2023"], "unit": "人民币百万元"}]
        output = {"sample_id": "invented", "pipeline": "arbitrary-name", "pages": [{"page": 1, "blocks": [
            {"id": "table", "kind": "table", "cells": cells}]}]}
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, output)))


def test_single_named_value_is_not_looked_up_in_another_column(tmp_path):
    markdown = "- Revenue: 17\n"
    expected, _ = reference(tmp_path, markdown)
    assert fields(grade_expected(expected, candidate(markdown)))[0]["outcome"] == "correct"
    output = candidate("| Metric | Value |\n|---|---|\n|Revenue|17|")
    assert fields(grade_expected(expected, output))[0]["outcome"] == "correct"
    ambiguous = candidate("| Metric | North | South |\n|---|---|---|\n|Revenue|11|17|")
    assert fields(grade_expected(expected, ambiguous))[0]["outcome"] == "incorrect"


def test_multi_value_year_fields_use_the_printed_column_definitions(tmp_path):
    markdown = "2024年金額及佔營業收入比、2023年金額及佔營業收入比、金額同比變動。\n\n- Revenue：2024年17、5%；2023年11、4%。\n"
    expected, _ = reference(tmp_path, markdown)
    score = grade_expected(expected, candidate(markdown))
    assert len(fields(score)) == 4
    assert all(row["outcome"] == "correct" for row in fields(score))


def test_comma_separated_shared_year_columns_keep_both_relations(tmp_path):
    markdown = ("各项分别列示2024年金额、占资产比，2023年金额、占资产比，金额同比变动。\n\n"
                "- Assets\n  - Cash：2024年17、5%；2023年11、4%。\n")
    expected, _ = reference(tmp_path, markdown)
    assert len(fields(grade_expected(expected, candidate(markdown)))) == 4
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(markdown))))
    swapped = markdown.replace("2024年17、5%", "2024年5%、17")
    assert sum(row["outcome"] == "incorrect" for row in fields(grade_expected(expected, candidate(swapped)))) == 2


def test_labelled_numeric_list_does_not_invent_year_column_labels(tmp_path):
    markdown = "- Security codes: 000017、000011\n"
    expected, _ = reference(tmp_path, markdown)
    score = grade_expected(expected, candidate(markdown))
    assert fields(score)[0]["expected"]["value"] == "000017、000011"
    assert fields(score)[0]["outcome"] == "correct"
    assert fields(grade_expected(expected, candidate(markdown.replace("000011", "000019"))))[0]["outcome"] == "incorrect"


def test_unit_in_expected_row_label_can_be_printed_in_candidate_header(tmp_path):
    from moparse_eval.adapters import html_cells
    expected, _ = reference(tmp_path, "- Revenue ($m): 2024: 17; 2023: 11.\n")
    output = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [{
        "id": "table", "kind": "table", "cells": html_cells(
            '<table><tr><td>Metric</td><td>2024$m</td><td>2023$m</td></tr>'
            '<tr><td>Revenue</td><td>17</td><td>11</td></tr></table>')}]}]}
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, output)))


def test_scoped_unicode_superscript_note_keeps_both_value_and_note(tmp_path):
    markdown = "## Results\n\n- Revenue: 2024: 17⁴; 2023: 11.\n\n4. New record.\n"
    expected, _ = reference(tmp_path, markdown)
    score = grade_expected(expected, candidate(markdown))
    assert fields(score)[0]["expected"]["reference_note_markers"] == ["4"]
    assert fields(score)[0]["outcome"] == "correct"
    missing = grade_expected(expected, candidate(markdown.replace("17⁴", "17")))
    assert fields(missing)[0]["outcome"] == "incorrect"


def test_unicode_exponent_without_note_definition_is_not_stripped(tmp_path):
    markdown = "- Power: 2024: 2⁴; 2023: 3.\n"
    expected, _ = reference(tmp_path, markdown)
    assert fields(grade_expected(expected, candidate(markdown)))[0]["outcome"] == "correct"
    assert fields(grade_expected(expected, candidate(markdown.replace("2⁴", "2"))))[0]["outcome"] == "incorrect"


def test_selected_scope_is_used_without_scoring_unselected_paragraph(tmp_path):
    expected, root = reference(tmp_path, "First page.\n\nSecond page.\n")
    write_json(root / "invented-document/manifest.json", {
        "markdown": {"path": "expected.md"}, "source_map": {"entries": [
            {"source_pages": [1], "markdown_lines": [1, 1]},
            {"source_pages": [2], "markdown_lines": [3, 3]},
        ]}})
    sample = {"id": "invented", "document_id": "invented-document", "source_pages": [2]}
    selected = read_expected(sample, root)
    score = grade_expected(selected, candidate("Second page.\n"))
    assert score["targets"] == score["correct"] == 1


def test_actual_rendered_scope_subject_and_parenthesized_qualifiers(tmp_path):
    markdown = "单位：人民币百万元。\n\n- Revenue\n  - 2024: 17\n  - 2023: 11\n"
    expected, _ = reference(tmp_path, markdown)
    actual = "- 范围：Results；Revenue；2024：17（单位：(人民币百万元)）；2023：11（单位：(人民币百万元)）。\n"
    score = grade_expected(expected, candidate(actual))
    assert all(row["outcome"] == "correct" for row in fields(score))


def test_semicolon_inside_qualifier_does_not_break_the_next_value(tmp_path):
    expected, _ = reference(tmp_path, "- Revenue ($m): 2024: 17; 2023: 11.\n")
    actual = "- Revenue；2024：17（单位：$m；期间：2024）；2023：11（单位：$m；期间：2023）。\n"
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(actual))))


def test_printed_header_paths_and_section_colons_are_read_as_paths(tmp_path):
    markdown = ("2024年金額及佔比、2023年金額及佔比。\n\n单位：人民币千元。\n\n- North\n"
                "  - Other：2024年17、5%；2023年11、4%。\n")
    expected, _ = reference(tmp_path, markdown)
    actual = ("- North: / Other；截至12月31日止年度 / 2024年 / 金額人民币千元：17；"
              "截至12月31日止年度 / 2024年 / 佔比：5%；截至12月31日止年度 / 2023年 / 金額人民币千元：11；"
              "截至12月31日止年度 / 2023年 / 佔比：4%。\n")
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(actual))))


def test_unsupported_expected_multi_values_are_a_reader_error(tmp_path):
    from moparse_eval.expected_readback import ExpectedReadError

    with pytest.raises(ExpectedReadError, match="explicitly printed column labels"):
        reference(tmp_path, "- Revenue: 2024年17、5%；2023年11、4%。\n")


def test_unlabelled_candidate_multi_values_are_preserved_without_inventing_labels(tmp_path):
    markdown = "2024年金額及佔營業收入比、2023年金額及佔營業收入比。\n\n- Revenue：2024年17、5%；2023年11、4%。\n"
    expected, _ = reference(tmp_path, markdown)
    score = grade_expected(expected, candidate("- Revenue：2024年17、5%；2023年11、4%。\n"))
    assert all(row["outcome"] == "incorrect" for row in fields(score))


def test_inline_fields_inherit_their_explicit_list_subject(tmp_path):
    markdown = "- Revenue\n  - 2024: 17; 2023: 11.\n"
    expected, _ = reference(tmp_path, markdown)
    assert len(fields(grade_expected(expected, candidate(markdown)))) == 2
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(markdown))))


def test_explicit_name_field_can_use_the_named_row_cell(tmp_path):
    from moparse_eval.adapters import markdown_cells

    expected, _ = reference(tmp_path, "- Name: Example Person; Votes: 17.\n")
    output = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [{"id": "table", "kind": "table",
        "cells": markdown_cells('| Name | Votes |\n|---|---|\n|Example Person|17|')}]}]}
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, output)))


@pytest.mark.parametrize("tables", [1, 2])
def test_named_value_with_only_column_labels_is_incorrect_without_reader_crash(tmp_path, tables):
    from moparse_eval.adapters import html_cells

    expected, _ = reference(tmp_path, "- Revenue: 17\n")
    output = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [
        {"id": f"table-{i}", "kind": "table", "cells": html_cells('<table><tr><th>Revenue</th></tr></table>', f"#/table/{i}")}
        for i in range(tables)]}]}
    score = grade_expected(expected, output)
    assert score["targets"] == score["incorrect"] == 1


def test_numeric_condition_in_subject_is_not_reinterpreted_as_a_value(tmp_path):
    expected, _ = reference(tmp_path, "- USD declines 5%: 2024: 17; 2023: 11.\n")
    actual = "- 范围：FX sensitivity；USD declines 5%；2024：17；2023：11。\n"
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(actual))))


def test_printed_note_number_and_linked_body_are_compared_as_one_note(tmp_path):
    markdown = "## Results\n\n- Revenue: 2024: 17⁴; 2023: 11.\n\n4. A new high.\n"
    expected, _ = reference(tmp_path, markdown)
    math_literal = r"\\( 17^4 \\)"
    actual = f"- Revenue；2024：{math_literal}（附注：4 A new high.）；2023：11。\n\n4. A new high.\n"
    assert fields(grade_expected(expected, candidate(actual)))[0]["outcome"] == "correct"
    assert fields(grade_expected(expected, candidate(actual.replace("4 A new high.", "4 A different condition."))))[0]["outcome"] == "incorrect"


def test_unit_caption_condition_is_not_reduced_to_its_currency_keyword(tmp_path):
    markdown = "单位：人民币百万元，除每股金额外。\n\n- Revenue: 2024: 17.\n"
    expected, _ = reference(tmp_path, markdown)
    assert expected["targets"][0]["text"] == "单位：人民币百万元，除每股金额外。"
    score = grade_expected(expected, candidate(markdown.replace("，除每股金额外", "")))
    caption = next(row for row in score["outcomes"] if row["kind"] == "unit_caption")
    assert caption["outcome"] == "incorrect"


def test_selected_continuation_reads_explicit_enclosing_scope_without_adding_unselected_targets(tmp_path):
    _, root = reference(tmp_path, "## Results\n\n单位：人民币百万元。\n\n- Revenue: 2024: 17.\n")
    write_json(root / "invented-document/manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {"entries": [
        {"source_pages": [1], "markdown_lines": [1, 3]}, {"source_pages": [2], "markdown_lines": [5, 5]}]}})
    sample = {"id": "invented", "document_id": "invented-document", "source_pages": [2]}
    expected = read_expected(sample, root)
    assert len(expected["targets"]) == 1 and expected["targets"][0]["context"] == ["Results"]
    assert expected["targets"][0]["record"]["unit"] == "人民币百万元"


def test_candidate_unit_caption_does_not_cross_an_unrelated_paragraph(tmp_path):
    expected, _ = reference(tmp_path, "- Revenue ($m): 2024: 17.\n")
    actual = "Units: $m\n\nA separate unrelated discussion.\n\n- Revenue: 2024: 17.\n"
    assert fields(grade_expected(expected, candidate(actual)))[0]["outcome"] == "incorrect"


def test_explicit_fullwidth_separated_fields_are_independent_business_targets(tmp_path):
    expected, _ = reference(tmp_path, "Ticker: Alpha、Beta\u3000Security codes: 000017、000011\n")
    assert len(expected["targets"]) == 2
    assert expected["targets"][1]["reference"]["part_index"] == 1
    score = grade_expected(expected, candidate("Ticker: Alpha、Beta\n\nSecurity codes: 000017、000011\n"))
    assert len(fields(score)) == 2 and all(row["outcome"] == "correct" for row in fields(score))
    wrong = grade_expected(expected, candidate("Ticker: Alpha、Beta\n\nSecurity codes: 000017、000019\n"))
    assert sum(row["outcome"] == "incorrect" for row in fields(wrong)) == 1


def test_sample_name_changes_no_business_decision_or_evidence(tmp_path):
    expected, _ = reference(tmp_path)
    output = candidate(REFERENCE)
    before = grade_expected(expected, output)
    expected["sample_id"] = output["sample_id"] = "unrelated-name"
    after = grade_expected(expected, output)
    assert before["outcomes"] == after["outcomes"]


def test_label_path_cache_uses_actual_immutable_labels_not_object_identity():
    from moparse_eval.information import _row_path_locates_cached, row_path_locates

    native = ["North", "Cash"]
    assert row_path_locates(["North", "Cash"], native, True)
    native[0] = "South"
    assert not row_path_locates(["North", "Cash"], native, True)
    for wanted in (("Cash",), ("South", "Cash"), ("North", "Cash")):
        assert _row_path_locates_cached(wanted, tuple(native), True) == _row_path_locates_cached.__wrapped__(wanted, tuple(native), True)


def test_year_in_meeting_name_is_not_a_nested_value_or_field_header(tmp_path):
    markdown = "- 会议届次：2023年度股东大会；召开日期：2024-05-29；查询索引：https://example.org/report。\n"
    expected, _ = reference(tmp_path, markdown)
    row = expected["targets"][0]["record"]
    assert row["row_header_path"] == ["2023年度股东大会"]
    assert [f["column_header_path"] for f in row["fields"]] == [["会议届次"], ["召开日期"], ["查询索引"]]
    assert all(x["outcome"] == "correct" for x in fields(grade_expected(expected, candidate(markdown))))


def test_a_year_mentioned_in_prose_does_not_declare_all_following_field_periods(tmp_path):
    markdown = "A separate event was announced in 2024年.\n\n- Revenue: Amount: 17.\n"
    expected, _ = reference(tmp_path, markdown)
    row = expected["targets"][1]["record"]
    assert all("period" not in f for f in row["fields"])


def test_explicit_named_parent_keeps_its_value_as_the_child_business_group(tmp_path):
    markdown = "- Scope: North\n  - Cash: 2024: 17\n- Scope: South\n  - Cash: 2024: 11\n"
    expected, _ = reference(tmp_path, markdown)
    paths = [t["record"]["row_header_path"] for t in expected["targets"] if t.get("record")]
    assert ["North", "Cash"] in paths and ["South", "Cash"] in paths
    score = grade_expected(expected, candidate(markdown))
    child = [r for r in fields(score) if r["row_header_path"][-1] == "Cash"]
    assert all(r["outcome"] == "correct" for r in child)
    swapped = grade_expected(expected, candidate(markdown.replace("North", "Temporary").replace("South", "North").replace("Temporary", "South")))
    assert all(r["outcome"] == "incorrect" for r in fields(swapped) if r["row_header_path"][-1] == "Cash")


@pytest.mark.parametrize("format_name", ["html", "prose"])
def test_explicit_reference_blank_requires_an_observed_blank_field_not_a_missing_output(tmp_path, format_name):
    from moparse_eval.adapters import html_cells

    expected, _ = reference(tmp_path, "- Revenue: 2024: 原表留空; 2023: 11.\n")
    if format_name == "html":
        output = {"sample_id": "invented", "pages": [{"page": 1, "blocks": [{"id": "table", "kind": "table",
            "cells": html_cells('<table><tr><th>Item</th><th>2024</th><th>2023</th></tr>'
                                '<tr><td>Revenue</td><td></td><td>11</td></tr></table>')}]}]}
    else:
        output = candidate("- Revenue；2024：（原表留空）；2023：11。\n")
    assert fields(grade_expected(expected, output))[0]["outcome"] == "correct"
    assert fields(grade_expected(expected, candidate("")))[0]["outcome"] == "incorrect"
    assert fields(grade_expected(expected, candidate("- Revenue；2024：0；2023：11。\n")))[0]["outcome"] == "incorrect"


def test_non_numeric_named_value_accepts_the_renderer_statement_punctuation(tmp_path):
    expected, _ = reference(tmp_path, "- Legal name: Example Company\n")
    assert fields(grade_expected(expected, candidate("- Legal name：Example Company。\n")))[0]["outcome"] == "correct"


def test_explicit_category_subject_and_printed_empty_field_are_read_as_a_record(tmp_path):
    expected, _ = reference(tmp_path, "- Current assets: 2034: 17; 2033: 原表留空.\n")
    actual = "- Asset category：Current assets；2034：17；2033：。\n"
    assert all(x["outcome"] == "correct" for x in fields(grade_expected(expected, candidate(actual))))


@pytest.mark.parametrize("format_name", ["gfm", "html"])
def test_multiple_public_tables_have_distinct_source_positions_without_fabricating_headers(tmp_path, format_name):
    expected, _ = reference(tmp_path, "- Alpha: 2034: 17\n- Beta: 2034: 11\n")
    def table(name, value):
        if format_name == "html":
            return f'<table><tr><td>Item</td><td>2034</td></tr><tr><td>{name}</td><td>{value}</td></tr></table>\n'
        return f'| | |\n|---|---|\n|Item|2034|\n|{name}|{value}|\n'
    actual = table("Alpha", "17") + "\nSeparate region.\n\n" + table("Beta", "11")
    assert all(x["outcome"] == "correct" for x in fields(grade_expected(expected, candidate(actual))))
    contradictory = table("Alpha", "17") + "\nSeparate region.\n\n" + table("Alpha", "19")
    assert fields(grade_expected(expected, candidate(contradictory)))[0]["outcome"] == "incorrect"


def test_explicit_metric_unit_can_move_between_row_and_column_in_a_transposed_record(tmp_path):
    expected, _ = reference(tmp_path, "- 2034\n  - North\n    - Cash: Amount ($m): 17\n")
    actual = "- Amount ($m)；2034 / North / Cash：17。\n"
    assert fields(grade_expected(expected, candidate(actual)))[0]["outcome"] == "correct"


def test_unit_and_currency_are_separate_explicit_requirements(tmp_path):
    expected, _ = reference(tmp_path, "单位：元 币种：人民币\n\n- Revenue: 2034: 17\n")
    actual = "- Revenue；2034：17（单位：元 币种：人民币）。\n"
    row = fields(grade_expected(expected, candidate(actual)))[0]
    assert row["expected"]["required"]["unit"] == "元"
    assert row["expected"]["required"]["currency"] == "人民币"
    assert row["outcome"] == "correct"
    wrong = grade_expected(expected, candidate(actual.replace("人民币", "美元")))
    assert fields(wrong)[0]["outcome"] == "incorrect"


def test_explicit_share_unit_overrides_the_table_currency_amount_unit(tmp_path):
    markdown = "单位：人民币百万元\n\n- 总股本（千股）: 2034: 17; 2033: 11\n"
    expected, _ = reference(tmp_path, markdown)
    score = grade_expected(expected, candidate("- 总股本（千股）；2034：17；2033：11。\n"))
    assert all(r["expected"]["required"]["unit"] == "千股" for r in fields(score))
    assert all(r["outcome"] == "correct" for r in fields(score))


def test_repeated_business_labels_keep_their_authored_channel_scope_before_comparing_rank(tmp_path):
    markdown = "## 2034年线下市场排名\n\n- Filter: Rank: 2\n\n## 2034年线上市场排名\n\n- Filter: Rank: 1\n"
    expected, _ = reference(tmp_path, markdown)
    actual = ("- 范围：2034 年线下市场排名；Name：Filter；Rank：2。\n\n"
              "- 范围：2034 年线上市场排名；Name：Filter；Rank：1。\n")
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(actual))))
    wrong = actual.replace("Rank：2", "Rank：1").replace("线上市场", "线下市场")
    assert all(row["outcome"] == "incorrect" for row in fields(grade_expected(expected, candidate(wrong))))


def test_authored_expected_table_uses_the_same_unit_rules_as_explicit_lists(tmp_path):
    markdown = "单位：人民币百万元\n\n|Item|2034|2033|\n|---|---|---|\n|Revenue|17|11|\n"
    expected, _ = reference(tmp_path, markdown)
    actual = "- Revenue；2034：17（单位：人民币百万元）；2033：11（单位：人民币百万元）。\n"
    assert all(row["outcome"] == "correct" for row in fields(grade_expected(expected, candidate(actual))))
    wrong = grade_expected(expected, candidate(actual.replace("百万元", "千元")))
    assert all(row["outcome"] == "incorrect" for row in fields(wrong))


def test_compiler_omission_is_a_software_error_even_if_every_pipeline_would_drop_it(tmp_path, monkeypatch):
    from moparse_eval import expected_scoring
    from moparse_eval.expected_readback import ExpectedReadError

    expected, _ = reference(tmp_path)
    original = expected_scoring._prepared
    def broken(value):
        texts, records = original(value)
        return texts[:-1], records
    monkeypatch.setattr(expected_scoring, "_prepared", broken)
    with pytest.raises(ExpectedReadError, match="omitted by the scoring compiler"):
        grade_expected(expected, candidate(REFERENCE))
