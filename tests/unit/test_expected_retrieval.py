"""Predetermined identity and context cases, from native/public syntax to grades.

The invented answers and their locations are authored here, not obtained from
the locator. No corpus, PDF, old score or reference-writing tool is used.
"""

from copy import deepcopy

import pytest

from moparse_eval.adapters import read_docling, read_glm, read_mineru, read_paddle, read_visual
from moparse_eval.expected_readback import markdown_observation, read_expected
from moparse_eval.expected_scoring import grade_expected
from moparse_eval.packaging import write_json
from moparse_eval.score_contract import require_retrieval_evidence

OFFLINE = "2027年主要产品线下市场份额及排名"
ONLINE = "2027年主要产品线上市场份额及排名"
HEADER = "<tr><th>品类</th><th>份额</th><th>排名</th></tr>"


@pytest.mark.parametrize("operator", ["/", "+", "-"])
def test_heading_label_operator_spacing_keeps_the_symbol_and_does_not_cut_its_parent(
    tmp_path, operator
):
    sentence = "The complete declared statement remains visible."
    target = (
        f"# Report\n\n## Technology\n\n- 波分/频分+直检\n- {sentence}\n\n## Other\n\n{sentence}\n"
    )
    actual = f"# Report\n\n## Technology\n\n## · 波分 {operator} 频分 + 直检\n\n{sentence}\n\n## Other\n\n{sentence}\n"
    score = grade_expected(
        reference(tmp_path, target), output("markdown", [[{"type": "text", "content": actual}]])
    )
    rows = [row for row in score["outcomes"] if row.get("expected") == sentence]
    assert rows[0]["outcome"] == ("correct" if operator == "/" else "incorrect")
    assert rows[1]["outcome"] == "correct"


@pytest.mark.parametrize(
    "actual,correct",
    [
        ("□适用√不适用", True),
        ("□适用 √不适用", True),
        ("√适用□不适用", False),
        ("□适用√适用", False),
        ("□1 2√3", True),
        ("□12√3", False),
    ],
)
def test_checkbox_spacing_preserves_markers_negation_and_label_characters(
    tmp_path, actual, correct
):
    text = "□1 2 √3" if "1" in actual else "□适用 √不适用"
    score = grade_expected(
        reference(tmp_path, f"# Report\n\n{text}\n"),
        output("markdown", [[{"type": "text", "content": f"# Report\n\n{actual}"}]]),
    )
    row = next(row for row in score["outcomes"] if row.get("expected") == text)
    assert row["outcome"] == ("correct" if correct else "incorrect")
    if actual != text and correct:
        assert row["text"]["strict"]["distance"] > 0


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("wrong", [False, True])
@pytest.mark.parametrize("name_key", ["名称", "Vendor"])
def test_explicit_type_is_a_record_identity_and_not_the_requested_amount(
    tmp_path, shape, wrong, name_key
):
    target = f"## Operations\n\n- {name_key}：North；交易类型：Purchase；Amount：4\n- {name_key}：North；交易类型：Sale；Amount：7\n"
    body = (
        f"<table><tr><th>{name_key}</th><th>交易类型</th><th>Amount</th></tr>"
        f"<tr><td>South</td><td>Purchase</td><td>4</td></tr><tr><td>North</td><td>Sale</td><td>7</td></tr><tr><td>North</td><td>Purchase</td><td>{9 if wrong else 4}</td></tr></table>"
    )
    score = grade_expected(
        reference(tmp_path, target),
        output(
            shape,
            [[{"type": "title", "content": "Operations"}, {"type": "table", "content": body}]],
        ),
    )
    rows = [r for r in fields(score) if r["expected"]["column_header_path"] == ["Amount"]]
    assert len(rows) == 2
    assert all(r["row_header_path"][0] == "North" for r in rows)
    assert rows[0]["actual"] == ("9" if wrong else "4")
    assert rows[0]["outcome"] == ("incorrect" if wrong else "correct")
    assert rows[1]["outcome"] == "correct"


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("wrong", [False, True])
def test_record_type_identity_must_come_from_its_own_field_not_a_description(
    tmp_path, shape, wrong
):
    target = "## Operations\n\n- 名称：North；交易类型：Purchase；Amount：4\n"
    body = (
        "<table><tr><th>名称</th><th>交易类型</th><th>Description</th><th>Amount</th></tr>"
        f"<tr><td>North</td><td>{'Return' if wrong else 'Purchase'}</td><td>Purchase</td><td>4</td></tr></table>"
    )
    score = grade_expected(
        reference(tmp_path, target),
        output(
            shape,
            [[{"type": "title", "content": "Operations"}, {"type": "table", "content": body}]],
        ),
    )
    row = next(r for r in fields(score) if r["expected"]["column_header_path"] == ["Amount"])
    assert row["outcome"] == ("incorrect" if wrong else "correct")


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize(
    "change", [None, "reordered", "swapped_shares", "one_wrong_value", "missing", "extra"]
)
def test_repeated_identity_is_compared_as_complete_records_after_collection_localization(
    tmp_path, shape, change
):
    target = "## Operations\n\n- 名称：North；交易类型：Rent；Amount：4；Share：20%\n- 名称：North；交易类型：Rent；Amount：7；Share：30%\n"
    rows = [["North", "Rent", "4", "20%"], ["North", "Rent", "7", "30%"]]
    if change == "reordered":
        rows.reverse()
    if change == "swapped_shares":
        rows[0][3], rows[1][3] = rows[1][3], rows[0][3]
    if change == "one_wrong_value":
        rows[0][2] = "9"
    if change == "missing":
        rows.pop()
    if change == "extra":
        rows.append(["North", "Rent", "999", "90%"])
    body = (
        "<table><tr><th>名称</th><th>交易类型</th><th>Amount</th><th>Share</th></tr>"
        + "".join("<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>" for row in rows)
        + "</table>"
    )
    score = grade_expected(
        reference(tmp_path, target),
        output(
            shape,
            [[{"type": "title", "content": "Operations"}, {"type": "table", "content": body}]],
        ),
    )
    result = fields(score)
    if change in {None, "reordered"}:
        assert all(row["outcome"] == "correct" for row in result)
        assert all(
            row["candidate"]["localization"]["collection_comparison"]["method"]
            == "complete_record_multiset_equality_after_identity"
            for row in result
        )
    else:
        assert any(
            row["outcome"] == "incorrect"
            for row in result
            if row["expected"]["column_header_path"] in [["Amount"], ["Share"]]
        )
        assert not any(
            row["candidate"]["localization"].get("collection_comparison") for row in result
        )
    assert all("value" not in row["candidate"]["localization"]["query"] for row in result)


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("new_document", [False, True])
def test_a_complete_repeated_report_header_does_not_end_an_ancestor_scope(
    tmp_path, shape, new_document
):
    sentence = "The required complete statement remains here."
    target = f"# Main division\n\n## Detail\n\n- Account：Amount：4\n\n{sentence}\n"
    raw = [
        {"type": "title", "content": "Main division"},
        {"type": "text", "content": "2027年年度报告"},
        {"type": "title", "content": "Detail"},
        {"type": "text", "content": "2028年年度报告" if new_document else "2027年年度报告"},
        {"type": "text", "content": "- Account：Amount：4"},
        {"type": "text", "content": sentence},
    ]
    score = grade_expected(reference(tmp_path, target), output(shape, [raw]))
    row = next(r for r in fields(score) if r["expected"]["value"] == "4")
    prose = next(r for r in score["outcomes"] if r.get("expected") == sentence)
    assert row["outcome"] == ("incorrect" if new_document else "correct")
    assert prose["outcome"] == ("incorrect" if new_document else "correct")


def reference(tmp_path, text=None, selected_lines=None):
    text = text or f"## {OFFLINE}\n\n- 器具甲：份额17.3%；排名4\n"
    folder = tmp_path / "expected" / "invented"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "answer.md").write_text(text)
    write_json(
        folder / "manifest.json",
        {
            "markdown": {"path": "answer.md"},
            "source_map": {
                "entries": [
                    {
                        "source_pages": [1, 2],
                        "markdown_lines": selected_lines or [1, len(text.splitlines())],
                    }
                ]
            },
        },
    )
    return read_expected(
        {"id": "case", "document_id": "invented", "source_pages": [1, 2]}, folder.parent
    )


def table(rank, *, header=True, name="器具甲", share="17.3%"):
    return f"<table>{HEADER if header else ''}<tr><td>{name}</td><td>{share}</td><td>{rank}</td></tr></table>"


def native_page(shape, blocks, page):
    if shape == "visual":
        return read_visual(blocks, page, f"#/pages/{page - 1}/raw")
    if shape == "paddle":
        return read_paddle(
            {
                "res": {
                    "parsing_res_list": [
                        {"block_label": b["type"], "block_content": b["content"]} for b in blocks
                    ]
                }
            },
            page,
        )
    if shape == "glm":
        return read_glm(
            {"json_result": [[{"label": b["type"], "content": b["content"]} for b in blocks]]}, page
        )
    if shape == "docvortex":
        return read_mineru(
            {
                "blocks": [
                    {
                        "type": b["type"],
                        "index": i,
                        "content": [{"type": "table_body", "index": 0, "content": b["content"]}]
                        if b["type"] == "table"
                        else b["content"],
                    }
                    for i, b in enumerate(blocks)
                ]
            },
            page,
        )
    if shape == "docling":
        from moparse_eval.adapters import html_cells

        document = {"body": {"children": []}, "texts": [], "tables": []}
        for b in blocks:
            category = "tables" if b["type"] == "table" else "texts"
            ref = f"#/{category}/{len(document[category])}"
            item = {"self_ref": ref, "label": b["type"], "prov": [{"page_no": page}]}
            if category == "tables":
                cells = html_cells(b["content"], ref)
                item["data"] = {
                    "table_cells": [
                        {
                            "text": c["text"],
                            "start_row_offset_idx": c["row"],
                            "start_col_offset_idx": c["col"],
                            "row_span": c.get("row_span", 1),
                            "col_span": c.get("col_span", 1),
                            "column_header": c.get(
                                "is_column_header",
                                c.get("native_header_tag", False)
                                and not c.get("is_row_header", False),
                            ),
                            "row_header": c.get("is_row_header", False),
                        }
                        for c in cells
                    ]
                }
            else:
                item["text"] = b["content"]
                if b.get("caption_of_previous_table"):
                    document["tables"][-1]["captions"] = [{"$ref": ref}]
            document[category].append(item)
            document["body"]["children"].append({"$ref": ref})
        return read_docling(document, page, f"#/documents/{page - 1}")
    raise AssertionError(shape)


def output(shape, pages):
    if shape == "markdown":
        text = "\n\n".join(
            (b["content"] if b["type"] == "table" else b["content"]) for page in pages for b in page
        )
        return markdown_observation(text, sample_id="case", pipeline="P08", pages=[1, 2])
    return {
        "sample_id": "case",
        "pipeline": "P08",
        "pages": [
            {"page": i + 1, "blocks": native_page(shape, blocks, i + 1)}
            for i, blocks in enumerate(pages)
        ],
    }


def fields(score):
    return [row for row in score["outcomes"] if row["kind"] == "business_field"]


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("change", [None, "digit", "split_word", "joined_numbers", "business_word"])
def test_cjk_latin_term_edge_spacing_does_not_change_business_content(
    tmp_path, shape, change
):
    target = "## Operations\n\n- 业务AI：Description：随着3D应用，AI技术提升绿电消费，编号1 2\n"
    value = "随着 3D 应用，AI 技术提升绿电消费，编号1 2"
    if change == "digit":
        value = value.replace("3D", "4D")
    if change == "split_word":
        value = value.replace("AI", "A I")
    if change == "joined_numbers":
        value = value.replace("1 2", "12")
    if change == "business_word":
        value = value.replace("消费", "消纳")
    body = (
        "<table><tr><th>业务</th><th>Description</th></tr>"
        f"<tr><td>业务 AI</td><td>{value}</td></tr></table>"
    )
    score = grade_expected(
        reference(tmp_path, target),
        output(shape, [[{"type": "title", "content": "Operations"}, {"type": "table", "content": body}]]),
    )
    row = fields(score)[0]
    assert row["actual"] == value
    assert row["outcome"] == ("correct" if change is None else "incorrect")
    assert row["raw_value_text"]["strict"]["distance"] > 0


@pytest.mark.parametrize(
    "literal",
    ["1 2", "A I", "New York", "1 + 2", "人民币 100", "编号 1 2", "3D + 4D"],
)
def test_term_spacing_preserves_numeric_and_word_internal_separators(literal):
    from moparse_eval.information_reading import cjk_term_spacing

    assert cjk_term_spacing(literal) == literal


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("repeated_title", [False, True])
@pytest.mark.parametrize(
    "root_value,child_value,root_correct,child_correct",
    [("BB 级", "BB", True, True), ("BC 级", "BB", False, True),
     (None, "BB级", False, False), (None, "BB", False, True)],
)
def test_same_named_facts_in_declared_parent_and_child_scopes_are_separate(
    tmp_path, shape, root_value, child_value, root_correct, child_correct, repeated_title
):
    child_title = "Report Overview" if repeated_title else "Overview"
    target = f"# Report\n\n- Credit grade：BB级\n\n## {child_title}\n\n- Credit grade：BB\n"
    blocks = [{"type": "title", "content": "Report"}]
    if root_value is not None:
        blocks.append({"type": "text", "content": f"Credit grade: {root_value}"})
    if repeated_title:
        blocks.append({"type": "title", "content": "Report"})
    blocks += [{"type": "title", "content": "Overview"},
               {"type": "text", "content": f"Credit grade: {child_value}"}]
    if repeated_title:
        target += "\n## Report\n\n### Details\n\nOther visible text.\n"
        blocks += [{"type": "title", "content": "Report"},
                   {"type": "title", "content": "Details"},
                   {"type": "text", "content": "Other visible text."}]
    score = grade_expected(reference(tmp_path, target), output(shape, [blocks]))
    rows = fields(score)
    assert [row["outcome"] == "correct" for row in rows] == [root_correct, child_correct]
    assert rows[0]["actual"] == root_value
    assert rows[1]["actual"] == child_value
    rejected = [hit for hit in rows[0]["candidate"]["localization"]["candidates"]
                if hit["decision"] == "rejected"]
    assert rejected and all("business_scope" in hit["reasons"] for hit in rejected)


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("between", [None, "Document ID: REF-27", "Amount: 4", "Business content interrupts here."])
def test_split_business_title_can_preserve_explicit_identifier_metadata_between_its_parts(
    tmp_path, shape, between
):
    target = "# Report\n\n- Credit grade：4\n\n## Report Overview\n\n- Credit grade：7\n"
    blocks = [{"type": "title", "content": "Report"},
              {"type": "text", "content": "Credit grade: 4"},
              {"type": "title", "content": "Report"}]
    if between:
        blocks.append({"type": "text", "content": between})
    blocks += [{"type": "title", "content": "Overview"},
               {"type": "text", "content": "Credit grade: 7"}]
    if shape == "markdown":
        blocks = [{**block, "content": "# " + block["content"]}
                  if block["type"] == "title" else block for block in blocks]
    score = grade_expected(reference(tmp_path, target), output(shape, [blocks]))
    rows = fields(score)
    if between is None or between.startswith("Document ID:"):
        assert all(row["outcome"] == "correct" for row in rows)
    else:
        assert rows[1]["outcome"] == "incorrect"
        # Extra explicit heading levels may still resolve the first fact;
        # interruption never makes the child's 7 a valid parent value.
        assert rows[0]["actual"] in {"4", None}
    if between == "Document ID: REF-27":
        selected = [hit for hit in rows[1]["candidate"]["localization"]["candidates"]
                    if hit["decision"] == "accepted"]
        anchors = [search["selected"]["anchor"] for hit in selected
                   for search in hit["scope_search"] if search.get("selected")]
        assert any(anchor.get("intervening_metadata", [])[0]["text"] == between
                   for anchor in anchors if anchor.get("intervening_metadata"))


@pytest.mark.parametrize(
    "label,value",
    [
        ("Within:Site count", "Owner:Ready"),
        ("Allocation:17", "4"),
        ("Name:Unit count", "4"),
        ("单位:人数", "4"),
    ],
)
def test_independent_grid_prose_and_literal_assertions_do_not_become_compound_metric_keys(
    label, value
):
    from moparse_eval.adapters import html_cells
    from moparse_eval.candidate_sequences import read_compound_measurement_labels

    cells = html_cells(f"<table><tr><td>{label}</td><td>{value}</td></tr></table>", "source")
    assert read_compound_measurement_labels(cells, set()) == ([], set())


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("actual", ["4", "9", "", "Wrong literal"])
@pytest.mark.parametrize("row_header", [False, True])
def test_a_colon_in_a_compound_metric_key_does_not_turn_its_label_into_the_value(
    tmp_path, shape, actual, row_header
):
    target = "## Metrics\n\n- Within：Site count：4\n- Other：Site count：4\n"
    body = (
        "<table><tr><td>Total count</td><td>13</td></tr>"
        f"<tr><td>Within:Site count</td><td>{actual}</td></tr>"
        "<tr><td>Other:Site count</td><td>4</td></tr></table>"
    )
    if row_header:
        body = body.replace("<td>Within:Site count</td>", '<th scope="row">Within:Site count</th>')
    score = grade_expected(
        reference(tmp_path, target),
        output(
            shape, [[{"type": "title", "content": "Metrics"}, {"type": "table", "content": body}]]
        ),
    )
    rows = fields(score)
    assert rows[0]["actual"] == actual
    assert rows[0]["outcome"] == ("correct" if actual == "4" else "incorrect")
    assert rows[1]["actual"] == "4" and rows[1]["outcome"] == "correct"
    chosen = rows[0]["candidate"].get("native_path", "")
    assert "cell[3]" in chosen or "cells/1" in chosen or "/data/table_cells/3" in chosen


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("full_company", [False, True])
def test_the_first_unqualified_annual_period_is_not_another_document_identity(
    tmp_path, shape, full_company
):
    sentence = "The existing own scope remains applicable."
    target = f"# Report\n\n## Division\n\n- Account：Amount：4\n\n{sentence}\n"
    header = "Another股份公司2027年年度报告" if full_company else "2027年年度报告"
    raw = [
        {"type": "title", "content": "Report"},
        {"type": "title", "content": "Division"},
        {"type": "text", "content": header},
        {"type": "text", "content": "- Account：Amount：4"},
        {"type": "text", "content": sentence},
    ]
    score = grade_expected(reference(tmp_path, target), output(shape, [raw]))
    row = next(row for row in fields(score) if row["expected"]["value"] == "4")
    prose = next(row for row in score["outcomes"] if row.get("expected") == sentence)
    assert row["outcome"] == ("incorrect" if full_company else "correct")
    assert prose["outcome"] == ("incorrect" if full_company else "correct")


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("change", [None, "wrapped", "extra_tail", "wrong_local_text"])
def test_a_complete_long_list_parent_is_read_inside_an_actual_multi_line_block(
    tmp_path, shape, change
):
    parent = (
        "(iii) "
        + ("The complete independently declared qualification remains in force; " * 12)
        + "end of scope."
    )
    sentence = "The required own statement remains subject to approval."
    target = f"# Report\n\n- Outer definition:\n  - {parent}\n    - {sentence}\n- Other definition:\n  - {sentence}\n"
    printed = parent
    if change == "wrapped":
        cut = printed.index(" ", len(printed) // 2)
        printed = printed[:cut] + "\n" + printed[cut + 1 :]
    if change == "extra_tail":
        printed += " A different restriction."
    own = (
        sentence.replace("approval", "external review")
        if change == "wrong_local_text"
        else sentence
    )
    raw = [
        {"type": "title", "content": "Report"},
        {
            "type": "text",
            "content": f"Outer definition:\n\n(ii) Previous rule.\n{printed}\n\n{own}\n\nOther definition:\n\n{sentence}",
        },
    ]
    score = grade_expected(reference(tmp_path, target), output(shape, [raw]))
    rows = [row for row in score["outcomes"] if row.get("expected") == sentence]
    assert len(rows) == 2
    assert rows[0]["outcome"] == ("correct" if change in {None, "wrapped"} else "incorrect")
    assert rows[1]["outcome"] == "correct"


def rank_field(score):
    return next(row for row in fields(score) if row["expected"]["column_header_path"] == ["排名"])


@pytest.mark.parametrize("repeat", ["业务回顾", "Business Review业务回顾"])
@pytest.mark.parametrize("changed", [False, True])
@pytest.mark.parametrize("ancestor_outside_selection", [False, True])
def test_repeated_complete_ancestor_title_keeps_the_open_child_scope_but_not_foreign_values(
    tmp_path, repeat, changed, ancestor_outside_selection
):
    text = "# 业务回顾\n\n## 品牌甲\n\n### 车型乙\n\nFirst local statement.\n\nSecond local statement.\n\n- Amount: 17\n\n## 品牌丙\n\nOther text.\n"
    expected = reference(
        tmp_path, text, [3, len(text.splitlines())] if ancestor_outside_selection else None
    )
    actual = (
        "# 业务回顾\n\n## 品牌甲\n\n### 车型乙\n\nFirst local statement.\n\n# " + repeat + "\n\n"
    )
    actual += (
        "Second local statemXnt.\n\n- Amount: 19"
        if changed
        else "Second local statement.\n\n- Amount: 17"
    )
    actual += "\n\n## 品牌丙\n\nSecond local statement.\n\n- Amount: 17\n\nOther text.\n"
    score = grade_expected(
        expected, markdown_observation(actual, sample_id="case", pipeline="P08", pages=[1, 2])
    )
    row = next(row for row in score["outcomes"] if row["expected"] == "Second local statement.")
    assert (row["outcome"] == "correct") is (not changed)
    assert (fields(score)[0]["outcome"] == "correct") is (not changed)
    if changed:
        assert row["actual"] == "Second local statemXnt."
        assert fields(score)[0]["actual"] == "19"


@pytest.mark.parametrize("new_title", ["业务回顾补充", "New business", "品牌丙"])
def test_partial_or_new_ancestor_names_do_not_continue_a_closed_scope(tmp_path, new_title):
    expected = reference(
        tmp_path,
        "# 业务回顾\n\n## 品牌甲\n\n### 车型乙\n\nFirst local statement.\n\nSecond local statement.\n\n## 品牌丙\n\nOther text.\n",
    )
    actual = (
        "# 业务回顾\n\n## 品牌甲\n\n### 车型乙\n\nFirst local statement.\n\n# "
        + new_title
        + "\n\nSecond local statement.\n"
    )
    score = grade_expected(
        expected, markdown_observation(actual, sample_id="case", pipeline="P08", pages=[1, 2])
    )
    row = next(row for row in score["outcomes"] if row["expected"] == "Second local statement.")
    assert row["outcome"] == "incorrect"


@pytest.mark.parametrize("change", ["no_preceding_ancestor", "new_document"])
def test_repeated_ancestor_requires_a_preceding_actual_title_and_does_not_cross_document_roles(
    tmp_path, change
):
    expected = reference(
        tmp_path,
        "# 业务回顾\n\n## 品牌甲\n\n### 车型乙\n\nFirst local statement.\n\nSecond local statement.\n",
    )
    actual = "# 业务回顾\n\n" if change != "no_preceding_ancestor" else ""
    actual += "## 品牌甲\n\n### 车型乙\n\nFirst local statement.\n\n# Business Review业务回顾\n\nSecond local statement.\n"
    observation = markdown_observation(actual, sample_id="case", pipeline="P08", pages=[1, 2])
    if change == "new_document":
        for block in observation["pages"][0]["blocks"]:
            if block["text"] == "Business Review业务回顾":
                block["kind"] = "doc_title"
    score = grade_expected(expected, observation)
    row = next(row for row in score["outcomes"] if row["expected"] == "Second local statement.")
    assert row["outcome"] == "incorrect"


def test_a_language_component_inside_untyped_business_prose_is_not_a_missing_parent_title(tmp_path):
    expected = reference(tmp_path, "# 业务回顾\n\n## 项目\n\nExact required statement.\n")
    actual = "These business words mention 业务回顾\n\n## 项目\n\nExact required statement.\n"
    score = grade_expected(
        expected, markdown_observation(actual, sample_id="case", pipeline="P08", pages=[1, 2])
    )
    row = next(row for row in score["outcomes"] if row["expected"] == "Exact required statement.")
    assert row["outcome"] == "incorrect"


@pytest.mark.parametrize(
    "change", [None, "changed_value", "new_english_title", "intervening_prose"]
)
def test_a_repeated_bilingual_title_pair_requires_the_same_prior_consecutive_title_pair(
    tmp_path, change
):
    text = "# 业务回顾\n\n## 车型乙\n\nFirst statement.\n\nSecond statement.\n\n- Amount: 17\n\n## 车型丙\n\nSecond statement.\n"
    expected = reference(tmp_path, text, [3, len(text.splitlines())])
    actual = "## Business Review\n\n## 业务回顾\n\n## 车型乙\n\nFirst statement.\n\n"
    actual += "## " + ("New Division" if change == "new_english_title" else "Business Review")
    actual += "\n\n" + (
        "A separate business paragraph.\n\n" if change == "intervening_prose" else ""
    )
    actual += "## 业务回顾\n\nSecond statement.\n\n- Amount: " + (
        "19" if change == "changed_value" else "17"
    )
    actual += "\n\n## 车型丙\n\nSecond statement.\n\n- Amount: 17\n"
    score = grade_expected(
        expected, markdown_observation(actual, sample_id="case", pipeline="P08", pages=[1, 2])
    )
    prose = [row for row in score["outcomes"] if row.get("expected") == "Second statement."][0]
    assert (prose["outcome"] == "correct") is (change in {None, "changed_value"})
    assert (fields(score)[0]["outcome"] == "correct") is (change is None)


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("change", [None, "wrong_year", "shorter_name", "intervening_words"])
def test_one_native_multiline_title_keeps_its_complete_literal_without_dropping_a_line(
    tmp_path, shape, change
):
    expected = reference(
        tmp_path,
        "# 星辰集团股份有限公司2031年年度报告摘要\n\n## 业务概况\n\n- Metric Alpha：Revenue：17\n",
    )
    title = "星辰集团股份有限公司\n2031 年年度报告摘要"
    if change == "wrong_year":
        title = title.replace("2031", "2039")
    elif change == "shorter_name":
        title = title.replace("星辰集团股份有限公司", "星辰集团")
    elif change == "intervening_words":
        title = title.replace("\n", "\nAnother business\n")
    candidate = output(
        shape,
        [
            [
                {"type": "title", "content": title},
                {"type": "title", "content": "业务概况"},
                grid(
                    "<table><tr><th>Name</th><th>Revenue</th></tr><tr><td>Metric Alpha</td><td>17</td></tr></table>"
                ),
            ]
        ],
    )
    row = fields(grade_expected(expected, candidate))[0]
    assert (row["outcome"] == "correct") is (change is None)


@pytest.mark.parametrize("as_item", [False, True])
@pytest.mark.parametrize("decoration", ["", "· "])
def test_a_complete_reference_statement_promoted_to_a_heading_remains_in_its_parent(
    tmp_path, as_item, decoration
):
    text = "Sales and operations remain material, which creates additional exposure."
    expected = reference(
        tmp_path,
        "# Report\n\n## Chapter\n\n"
        + ("- " if as_item else "")
        + text
        + "\n\nA later required statement.\n\n## Other\n\nForeign text.\n",
    )
    actual = (
        "# Report\n\n## Chapter\n\n## "
        + decoration
        + text
        + "\n\nA later required statement.\n\n## Other\n\nForeign text.\n"
    )
    score = grade_expected(
        expected, markdown_observation(actual, sample_id="case", pipeline="P08", pages=[1, 2])
    )
    rows = [
        r for r in score["outcomes"] if r.get("expected") in [text, "A later required statement."]
    ]
    assert rows and all(r["outcome"] == "correct" for r in rows)


def test_repeated_plain_complete_ancestor_is_read_from_the_candidates_own_prior_complete_text(
    tmp_path,
):
    expected = reference(
        tmp_path,
        "# 星辰集团2031年年度报告\n\n## Business\n\nFirst statement.\n\nSecond statement.\n",
    )
    actual = "星辰集团 2031 年年度报告\n\n## Business\n\nFirst statement.\n\n星辰集团 2031 年年度报告\n\nSecond statement.\n"
    score = grade_expected(
        expected, markdown_observation(actual, sample_id="case", pipeline="P08", pages=[1, 2])
    )
    assert (
        next(r for r in score["outcomes"] if r.get("expected") == "Second statement.")["outcome"]
        == "correct"
    )


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("change", [None, "wrong_value", "heading", "body_sentence"])
def test_colon_label_owns_the_immediately_following_short_literal_without_an_empty_competing_record(
    tmp_path, shape, change
):
    expected = reference(tmp_path, "# Calendar\n\n- Rating date：2031年2月3日\n")
    middle = (
        [{"type": "title", "content": "Other section"}]
        if change == "heading"
        else [{"type": "text", "content": "A separate business sentence."}]
        if change == "body_sentence"
        else []
    )
    blocks = [
        {"type": "title", "content": "Calendar"},
        *(
            [{"type": "text", "content": "Rating date：2031年2月3日"}]
            if change not in {"heading", "body_sentence"}
            else []
        ),
        {"type": "text", "content": "Rating date："},
        *middle,
        {"type": "text", "content": "2031年2月4日" if change == "wrong_value" else "2031年2月3日"},
    ]
    score = grade_expected(expected, output(shape, [blocks]))
    row = fields(score)[0]
    assert (row["outcome"] == "correct") is (change is None)


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("barrier", [None, "new_heading", "new_unit"])
def test_printed_unit_legend_bounds_adjacent_complete_tables_without_a_hidden_unit_copy(
    tmp_path, shape, barrier
):
    expected = reference(
        tmp_path, "# Audit\n\n单位：万元 币种：人民币\n\n- Internal audit：报酬：41\n"
    )
    tables = [
        grid(
            "<table><tr><th>Name</th><th>Value</th></tr><tr><td>Other fee</td><td>17</td></tr></table>"
        )
    ]
    if barrier:
        tables.append(
            {
                "type": "title" if barrier == "new_heading" else "text",
                "content": "Another scope" if barrier == "new_heading" else "单位：元 币种：人民币",
            }
        )
    tables.append(
        grid(
            "<table><tr><th>Name</th><th>报酬</th></tr><tr><td>Internal audit</td><td>41</td></tr></table>"
        )
    )
    score = grade_expected(
        expected,
        output(
            shape,
            [
                [
                    {"type": "title", "content": "Audit"},
                    {"type": "text", "content": "单位：万元 币种：人民币"},
                    *tables,
                ]
            ],
        ),
    )
    assert (fields(score)[0]["outcome"] == "correct") is (barrier is None)


@pytest.mark.parametrize("changed", [False, True])
def test_explicit_list_parent_printed_as_a_heading_with_leaders_keeps_its_own_child(
    tmp_path, changed
):
    expected = reference(
        tmp_path,
        "# Programme\n\n- Issue method:\n  - Own issue text.\n- Registration form:\n  - Own registration text.\n",
    )
    actual = "## Programme\n\n## Issue method . . . . .\n\n" + (
        "Own issue ERROR." if changed else "Own issue text."
    )
    actual += "\n\n## Registration form . . . . .\n\nOwn registration text.\n\nOwn issue text.\n"
    score = grade_expected(
        expected, markdown_observation(actual, sample_id="case", pipeline="P08", pages=[1, 2])
    )
    row = next(r for r in score["outcomes"] if r.get("expected") == "Own issue text.")
    assert (row["outcome"] == "correct") is (not changed)


@pytest.mark.parametrize("prelude", ["title", "business_prose", "other_document"])
def test_initial_cover_title_may_precede_its_brand_but_business_prose_and_document_roles_do_not(
    tmp_path, prelude
):
    expected = reference(tmp_path, "# Magazine Brand\n\nCover headline with a literal 5G marker.\n")
    actual = (
        "## " if prelude != "business_prose" else ""
    ) + "Cover headline with a literal 5G marker.\n\nMagazine Brand\n"
    observation = markdown_observation(actual, sample_id="case", pipeline="P08", pages=[1])
    if prelude == "other_document":
        observation["pages"][0]["blocks"][0]["kind"] = "doc_title"
    row = next(
        r
        for r in grade_expected(expected, observation)["outcomes"]
        if r.get("expected") == "Cover headline with a literal 5G marker."
    )
    assert (row["outcome"] == "correct") is (prelude == "title")


def test_an_open_list_label_keeps_all_its_text_without_creating_an_unstated_empty_fact(tmp_path):
    expected = reference(tmp_path, "# Report\n\n- Section label:\n  - Amount: 17\n- Empty leaf:\n")
    parent = next(t for t in expected["targets"] if t["text"] == "Section label:")
    leaf = next(t for t in expected["targets"] if t["text"] == "Empty leaf:")
    assert parent["has_children"] and "record" not in parent
    assert "record" not in leaf
    score = grade_expected(
        expected,
        markdown_observation(
            "# Report\n\n- Section label:\n  - Amount: 17\n- Empty leaf:\n",
            sample_id="case",
            pipeline="P08",
            pages=[1, 2],
        ),
    )
    assert any(
        r.get("expected") == "Section label:" and r["kind"] == "item" for r in score["outcomes"]
    )
    assert any(
        r.get("expected") == "Empty leaf:" and r["kind"] == "item" for r in score["outcomes"]
    )
    assert score["content_coverage"]["omitted_elements"] == 0


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("change", [None, "wrong_year", "new_company", "business_prose"])
def test_complete_header_only_grid_remains_readable_across_an_exact_repeated_report_title(
    tmp_path, shape, change
):
    root = "星辰股份有限公司2031年年度报告"
    expected = reference(
        tmp_path,
        f"# {root}\n\n## Transactions\n\n单位：元\n\n- Company Alpha：关系：Subsidiary；金额：17\n",
    )
    title = "星辰股份有限公司 2031 年年度报告"
    repeated = (
        title.replace("2031", "2039")
        if change == "wrong_year"
        else title.replace("星辰", "大河")
        if change == "new_company"
        else title
    )
    blocks = [
        {"type": "title", "content": title},
        {"type": "title", "content": "Transactions"},
        {"type": "text", "content": "单位：元"},
        grid("<table><tr><td>Name</td><td>关系</td><td>金额</td></tr></table>"),
        {"type": "text", "content": repeated},
    ]
    if change == "business_prose":
        blocks.append({"type": "text", "content": "A different business scope begins."})
    blocks.append(
        grid("<table><tr><td>Company Alpha</td><td>Subsidiary</td><td>17</td></tr></table>")
    )
    rows = fields(grade_expected(expected, output(shape, [blocks])))
    assert all(r["outcome"] == "correct" for r in rows) is (change is None)


def test_a_shared_money_caption_does_not_turn_an_empty_note_into_a_money_field(tmp_path):
    expected = reference(
        tmp_path,
        "# Ledger\n\n单位：元 币种：人民币\n\n- Account：金额：原表留空；附注（如适用）：原表留空\n",
    )
    record = next(target["record"] for target in expected["targets"] if target.get("record"))
    amount, note = record["fields"]
    assert amount.get("currency") == "人民币" and amount.get("unit", record.get("unit")) == "元"
    assert note.get("unit") is None and note.get("currency") is None


@pytest.mark.parametrize(
    "new_title", ["大河股份有限公司 2031 年年度报告", "星辰股份有限公司 2039 年年度报告"]
)
def test_a_different_complete_report_title_stops_a_prior_document_identity_even_with_local_units(
    tmp_path, new_title
):
    expected = reference(
        tmp_path,
        "# 星辰股份有限公司2031年年度报告\n\n## Business\n\n单位：元\n\n- Company Alpha：金额：17\n",
    )
    blocks = [
        {"type": "title", "content": "星辰股份有限公司 2031 年年度报告"},
        {"type": "title", "content": "Business"},
        {"type": "text", "content": new_title},
        {"type": "text", "content": "单位：元"},
        grid(
            "<table><tr><th>Name</th><th>金额</th></tr><tr><td>Company Alpha</td><td>17</td></tr></table>"
        ),
    ]
    row = fields(grade_expected(expected, output("visual", [blocks])))[0]
    assert row["outcome"] == "incorrect" and row.get("actual") is None


def caption(title):
    return {"type": "table_caption", "content": title}


def grid(html):
    return {"type": "table", "content": html}


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("foreign_rank", ["1", "4"])
def test_explicit_scope_is_required_even_with_one_reference_record(tmp_path, shape, foreign_rank):
    candidate = output(
        shape,
        [
            [
                caption(ONLINE),
                grid(table(foreign_rank, share="23.1%")),
                caption(OFFLINE),
                grid(table("4")),
            ]
        ],
    )
    result = rank_field(grade_expected(reference(tmp_path), candidate))
    assert result["outcome"] == "correct"
    assert result["actual"] == "4"
    trace = result["candidate"]["localization"]
    assert trace["query"]["identity"]["business_scope"] == OFFLINE
    assert "value" not in trace["query"]
    rejected = [item for item in trace["candidates"] if item["decision"] == "rejected"]
    assert any(item["identity"]["business_scope"]["status"] == "incorrect" for item in rejected)


@pytest.mark.parametrize("foreign_rank", ["1", "4"])
def test_unique_wrong_market_is_not_compared_as_a_number_error(tmp_path, foreign_rank):
    candidate = output("visual", [[caption(ONLINE), grid(table(foreign_rank))]])
    result = rank_field(grade_expected(reference(tmp_path), candidate))
    assert result["outcome"] == "incorrect"
    assert result["reason"] == "required_business_identity_conflict"
    assert result.get("actual") is None
    assert result["raw_value_text"] is None
    assert result["candidate"]["localization"]["candidates"][0]["decision"] == "rejected"


@pytest.mark.parametrize("shape", ["visual", "markdown"])
@pytest.mark.parametrize("target_rank", ["4", "9"])
def test_caption_bounded_header_reading_retains_a_headerless_fragment(tmp_path, shape, target_rank):
    pages = [
        [caption(OFFLINE), grid(table("2", name="器具乙"))],
        [grid(table(target_rank, header=False)), caption(ONLINE), grid(table("4", share="23.1%"))],
    ]
    result = rank_field(grade_expected(reference(tmp_path), output(shape, pages)))
    assert result["actual"] == target_rank
    assert result["outcome"] == ("correct" if target_rank == "4" else "incorrect")
    assert result["candidate"]["localization"]["query"]["identity"]["business_scope"] == OFFLINE
    # The correct value in the other market cannot rescue the changed target.
    assert "caption" in str(result["candidate"]["header_evidence"]).lower()


@pytest.mark.parametrize(
    "barrier",
    [
        caption(ONLINE),
        {"type": "title", "content": "另一项业务"},
        {"type": "text", "content": "下面开始一张独立的新表。"},
        {"type": "text", "content": "单位：千元"},
    ],
)
def test_header_scope_cannot_cross_a_new_caption_heading_prose_or_unit(tmp_path, barrier):
    pages = [
        [caption(OFFLINE), grid(table("2", name="器具乙"))],
        [barrier, grid(table("4", header=False))],
    ]
    result = rank_field(grade_expected(reference(tmp_path), output("visual", pages)))
    assert result["outcome"] == "incorrect"
    assert result.get("actual") is None


def test_two_unlabelled_tables_do_not_create_a_shared_header_scope(tmp_path):
    candidate = output(
        "visual", [[grid(table("2", name="器具乙"))], [grid(table("4", header=False))]]
    )
    result = rank_field(grade_expected(reference(tmp_path), candidate))
    assert result["outcome"] == "incorrect"
    assert result.get("actual") is None


def test_paddle_page_number_does_not_break_caption_but_remains_visible(tmp_path):
    pages = [
        [caption(OFFLINE), grid(table("2", name="器具乙")), {"type": "number", "content": "31"}],
        [grid(table("4", header=False))],
    ]
    candidate = output("paddle", pages)
    assert any(block.get("text") == "31" for page in candidate["pages"] for block in page["blocks"])
    assert rank_field(grade_expected(reference(tmp_path), candidate))["outcome"] == "correct"


def test_docling_linked_caption_after_table_is_read_by_its_native_reference(tmp_path):
    pages = [
        [grid(table("2", name="器具乙")), {**caption(OFFLINE), "caption_of_previous_table": True}],
        [grid(table("4", header=False))],
    ]
    result = rank_field(grade_expected(reference(tmp_path), output("docling", pages)))
    assert result["outcome"] == "correct"
    assert "native_caption_references" in str(result["candidate"]["header_evidence"])


@pytest.mark.parametrize("rank", ["4", "9"])
def test_declared_header_role_on_a_scalar_continuation_does_not_hide_its_printed_record(
    tmp_path, rank
):
    pages = [
        [caption(OFFLINE), grid(table("2", name="器具乙"))],
        [
            grid(f"<table><tr><th>器具甲</th><th>17.3%</th><th>{rank}</th></tr></table>"),
            caption(ONLINE),
            grid(table("4")),
        ],
    ]
    candidate = output("docling", pages)
    before = deepcopy(candidate)
    result = rank_field(grade_expected(reference(tmp_path), candidate))
    assert result["actual"] == rank
    assert result["outcome"] == ("correct" if rank == "4" else "incorrect")
    assert candidate == before


@pytest.mark.parametrize("reverse", [False, True])
def test_foreign_order_and_value_changes_do_not_reassign_the_target(tmp_path, reverse):
    own = [caption(OFFLINE), grid(table("9"))]
    other = [caption(ONLINE), grid(table("4"))]
    candidate = output("visual", [[*(own if reverse else other), *(other if reverse else own)]])
    result = rank_field(grade_expected(reference(tmp_path), candidate))
    assert result["outcome"] == "incorrect"
    assert result["actual"] == "9"


def test_same_scope_contradictory_claims_are_not_resolved_using_the_answer(tmp_path):
    candidate = output(
        "visual", [[caption(OFFLINE), grid(table("4")), caption(OFFLINE), grid(table("9"))]]
    )
    result = rank_field(grade_expected(reference(tmp_path), candidate))
    assert result["outcome"] == "incorrect"
    assert result.get("actual") is None


def test_expected_and_candidate_remain_read_only_and_pipeline_labels_do_not_select(tmp_path):
    expected = reference(tmp_path)
    candidate = output(
        "visual", [[caption(OFFLINE), grid(table("4")), caption(ONLINE), grid(table("1"))]]
    )
    before = deepcopy((expected, candidate))
    first = grade_expected(expected, candidate)["outcomes"]
    assert (expected, candidate) == before
    for pipeline in ("P01", "P05", "P08"):
        changed = deepcopy(candidate)
        changed["pipeline"] = pipeline
        assert grade_expected(expected, changed)["outcomes"] == first


@pytest.mark.parametrize(
    "corruption", ["wrong_query", "wrong_admission", "foreign_value", "reader_failure"]
)
def test_publication_guard_rejects_a_frozen_looking_but_invalid_selection(tmp_path, corruption):
    candidate = output(
        "visual", [[caption(OFFLINE), grid(table("4")), caption(ONLINE), grid(table("1"))]]
    )
    row = rank_field(grade_expected(reference(tmp_path), candidate))
    bad = deepcopy(row)
    field = bad["candidate"]
    if corruption == "wrong_query":
        field["localization"]["query"]["identity"]["business_scope"] = ONLINE
    elif corruption == "wrong_admission":
        admitted = next(
            hit for hit in field["localization"]["candidates"] if hit["decision"] == "accepted"
        )
        admitted["identity"]["business_scope"]["status"] = "incorrect"
    elif corruption == "foreign_value":
        field["native_id"] = "another-table/value"
    else:
        field["reader_failure"] = "unread_candidate_expression"
    with pytest.raises(ValueError):
        require_retrieval_evidence([bad])


@pytest.mark.parametrize("one_block", [False, True])
def test_near_paragraph_in_its_own_scope_is_not_replaced_by_foreign_exact_text(tmp_path, one_block):
    sentence = "The planned annual allocation is seventeen units, subject to independent approval."
    target = f"## North\n\n{sentence}\n\n## South\n\n{sentence}\n"
    actual = f"## North\n\n{sentence.replace('seventeen', 'eighteen')}\n\n## South\n\n{sentence}\n"
    if one_block:
        # A plain native block may carry multiple headings and paragraphs.
        candidate = output("visual", [[{"type": "text", "content": actual.replace("## ", "")}]])
    else:
        candidate = output("markdown", [[{"type": "text", "content": actual}]])
    score = grade_expected(reference(tmp_path, target), candidate)
    paragraphs = [row for row in score["outcomes"] if row["kind"] == "text"]
    assert paragraphs[0]["outcome"] == "incorrect"
    assert "eighteen" in paragraphs[0]["actual"]
    assert paragraphs[1]["outcome"] == "correct"
    assert paragraphs[0]["context_evidence"]["correct"] is True
    assert any(hit["decision"] == "rejected" for hit in paragraphs[0]["localization"]["candidates"])


def test_unselected_actual_sibling_heading_still_closes_the_text_scope(tmp_path):
    sentence = "The planned annual allocation is seventeen units, subject to independent approval."
    target = f"## North\n\n{sentence}\n"
    actual = f"## North\n\n{sentence.replace('seventeen', 'eighteen')}\n\n## Other division\n\n{sentence}\n"
    candidate = output("markdown", [[{"type": "text", "content": actual}]])
    row = next(
        item
        for item in grade_expected(reference(tmp_path, target), candidate)["outcomes"]
        if item["kind"] == "text"
    )
    assert row["outcome"] == "incorrect"
    assert "eighteen" in row["actual"]


def test_printed_identity_prefix_does_not_become_part_of_a_colon_ended_parent(tmp_path):
    target = "## Results\n\n- Per-unit measures\n  - Product (元)：2027年1.7；2026年1.4。\n"
    actual = "## Results\n\n- Item：Per-unit measures: / Product (元)；2027年：1.7；2026年：1.4。\n"
    candidate = output("markdown", [[{"type": "text", "content": actual}]])
    result = fields(grade_expected(reference(tmp_path, target), candidate))
    assert len(result) == 2 and all(row["outcome"] == "correct" for row in result)
    wrong = output(
        "markdown",
        [[{"type": "text", "content": actual.replace("Per-unit measures:", "Another group:")}]],
    )
    assert all(
        row["outcome"] == "incorrect"
        for row in fields(grade_expected(reference(tmp_path, target), wrong))
    )


@pytest.mark.parametrize("role", ["text", "title"])
def test_printed_parent_scope_survives_a_finer_native_subtitle(tmp_path, role):
    target = "## 1、主要指标\n\n- 器具甲：份额17.3%；排名4\n\n## 2、其他业务\n\n- 器具乙：份额9%；排名2\n"
    raw = [
        {"type": role, "content": "1、主要指标"},
        {"type": "title", "content": "专项项目"},
        grid(table("4")),
        {"type": role, "content": "2、其他业务"},
        grid(table("9", name="器具乙", share="9%")),
    ]
    result = fields(grade_expected(reference(tmp_path, target), output("visual", [raw])))
    own = [row for row in result if row["row_header_path"] == ["器具甲"]]
    assert all(row["outcome"] == "correct" for row in own)
    # A value in the following sibling cannot establish the first scope.
    swapped = deepcopy(raw)
    swapped[2] = grid(table("9"))
    swapped[4] = grid(table("4"))
    own = [
        row
        for row in fields(grade_expected(reference(tmp_path, target), output("visual", [swapped])))
        if row["row_header_path"] == ["器具甲"]
    ]
    assert (
        next(row for row in own if row["expected"]["column_header_path"] == ["排名"])["actual"]
        == "9"
    )


def test_local_printed_year_cannot_be_rescued_by_a_wider_year_caption(tmp_path):
    target = "## 2027年经营指标\n\n- Revenue：Q1：17\n"
    candidate = output(
        "visual",
        [
            [
                caption("2027年经营指标"),
                grid(
                    "<table><tr><td>Item</td><td>2026年 / Q1</td></tr><tr><td>Revenue</td><td>17</td></tr></table>"
                ),
            ]
        ],
    )
    result = fields(grade_expected(reference(tmp_path, target), candidate))
    assert result[0]["outcome"] == "incorrect"


def test_identical_leaf_scope_under_another_parent_cannot_supply_a_field(tmp_path):
    target = (
        "# Company A\n\n## North\n\n- 器具甲：排名4\n\n# Company B\n\n## North\n\n- 器具甲：排名1\n"
    )
    raw = [
        {"type": "title", "content": "Company A"},
        {"type": "title", "content": "North"},
        grid(table("9")),
        {"type": "title", "content": "Company B"},
        {"type": "title", "content": "North"},
        grid(table("4")),
    ]
    result = fields(grade_expected(reference(tmp_path, target), output("visual", [raw])))
    assert all(row["outcome"] == "incorrect" for row in result)
    assert result[0]["actual"] == "9"
    assert result[1]["actual"] == "4"


def test_flattened_markdown_caption_retains_its_explicit_parent_scope(tmp_path):
    target = "## Results\n\nSpecial calculation，单位：元。\n\n- Revenue：Amount：17\n\nA mandatory explanatory note.\n"
    actual = "## Results\n\n## Special calculation\n\n单位：元。\n\n- Revenue：Amount：17\n\nA mandatory explanatory note.\n"
    score = grade_expected(
        reference(tmp_path, target), output("markdown", [[{"type": "text", "content": actual}]])
    )
    assert fields(score)[0]["outcome"] == "correct"
    note = next(
        row for row in score["outcomes"] if row.get("expected") == "A mandatory explanatory note."
    )
    assert note["outcome"] == "correct"
    # An actual different sibling still cuts off the expected parent.
    changed = actual.replace("Special calculation", "Other division")
    score = grade_expected(
        reference(tmp_path, target), output("markdown", [[{"type": "text", "content": changed}]])
    )
    assert fields(score)[0]["outcome"] == "incorrect"


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("year", ["2027", "2026"])
@pytest.mark.parametrize("date_separator", [" ", ""])
def test_year_and_full_date_in_one_native_header_keep_their_path(
    tmp_path, shape, year, date_separator
):
    target = "## Results\n\n- Account：2027 / December 31, 2027：17\n"
    raw = [
        {"type": "title", "content": "Results"},
        grid(
            f"<table><tr><th>Item</th><th>{year}/December31,{date_separator}2027</th></tr><tr><td>Account</td><td>17</td></tr></table>"
        ),
    ]
    result = fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))
    assert result[0]["outcome"] == ("correct" if year == "2027" else "incorrect")


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("marker", ["1", "2"])
@pytest.mark.parametrize("unit", ["in RMB", "%"])
def test_note_and_unit_parenthesis_spacing_is_only_label_typography(tmp_path, shape, marker, unit):
    target = f"## Results\n\n- Operating profit (1) ({unit})：2027：17\n"
    raw = [
        {"type": "title", "content": "Results"},
        grid(
            "<table><tr><th>Item</th><th>2027</th></tr>"
            f"<tr><td>Operating profit({marker})({unit})</td><td>17</td></tr></table>"
        ),
    ]
    result = fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))[0]
    assert result["outcome"] == ("correct" if marker == "1" else "incorrect")


@pytest.mark.parametrize("year", ["2027", "2026"])
@pytest.mark.parametrize("trailer", ["Decem", ""])
def test_printed_year_prefix_and_its_separate_complete_date_are_both_read(tmp_path, year, trailer):
    target = "## Results\n\n- Account：2027 / December 31, 2027：17\n"
    raw = [
        {"type": "title", "content": "Results"},
        grid(
            f"<table><tr><th></th><th>{year}/{trailer}</th></tr>"
            "<tr><th>Item</th><th>December31,2027</th></tr><tr><td>Account</td><td>17</td></tr></table>"
        ),
    ]
    candidate = output("docling", [raw])
    before = deepcopy(candidate)
    row = fields(grade_expected(reference(tmp_path, target), candidate))[0]
    assert row["outcome"] == ("correct" if year == "2027" else "incorrect")
    assert candidate == before


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize(
    "label",
    [
        ("Measure (“A”)", 'Measure("A")', True),
        ("Holding ≥4 contracts", "Holding≥4 contracts", True),
        ("Holding ≥4 contracts", "Holding>4 contracts", False),
        ("Measure (“A”)", 'Measure("B")', False),
    ],
)
def test_label_quote_and_operator_layout_keeps_the_actual_symbols(tmp_path, shape, label):
    wanted, actual, correct = label
    target = f"## Results\n\n- {wanted}：2027：17\n"
    raw = [
        {"type": "title", "content": "Results"},
        grid(
            f"<table><tr><th>Item</th><th>2027</th></tr><tr><td>{actual}</td><td>17</td></tr></table>"
        ),
    ]
    row = fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))[0]
    assert row["outcome"] == ("correct" if correct else "incorrect")


@pytest.mark.parametrize("shape", ["visual", "markdown"])
def test_initial_delimited_metadata_can_precede_its_root_title(tmp_path, shape):
    target = "# 2027年年度报告\n\n- Code：ZX17\n"
    title = "# 2027年年度报告" if shape == "markdown" else "2027年年度报告"
    raw = [{"type": "header", "content": "Code：ZX17"}, {"type": "doc_title", "content": title}]
    result = fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))
    assert result[0]["outcome"] == "correct"
    # Metadata in another document or behind business prose is not preamble.
    for barrier in (
        "# Other report" if shape == "markdown" else "Other report",
        "A business statement.",
    ):
        changed = [{"type": "title", "content": barrier}, *raw]
        assert (
            fields(grade_expected(reference(tmp_path, target), output(shape, [changed])))[0][
                "outcome"
            ]
            == "incorrect"
        )


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
def test_a_new_declared_document_title_closes_the_previous_annual_scope(tmp_path, shape):
    target = "# Annual Report 2027\n\n- Revenue：Amount：17\n"
    raw = [
        {
            "type": "doc_title",
            "content": "# Annual Report 2027" if shape == "markdown" else "Annual Report 2027",
        },
        {
            "type": "doc_title",
            "content": "# Annual Report 2026" if shape == "markdown" else "Annual Report 2026",
        },
        grid(
            "<table><tr><th>Item</th><th>Amount</th></tr><tr><td>Revenue</td><td>17</td></tr></table>"
        ),
    ]
    result = fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))[0]
    assert result["outcome"] == "incorrect"
    assert result.get("actual") is None


@pytest.mark.parametrize("shape", ["visual", "markdown"])
def test_complete_bilingual_root_title_part_is_not_a_shorter_name_alias(tmp_path, shape):
    target = "# 甲企业股份有限公司\n\n## Announcement\n\n- Code：ZX17\n"
    title = "BRAND 甲企业股份有限公司 EXAMPLE CO."
    if shape == "markdown":
        title = "# " + title
    raw = [
        {"type": "doc_title", "content": title},
        {"type": "title", "content": "## Announcement" if shape == "markdown" else "Announcement"},
        {"type": "text", "content": "Code：ZX17"},
    ]
    assert (
        fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))[0]["outcome"]
        == "correct"
    )
    changed = deepcopy(raw)
    changed[0]["content"] = title.replace("甲企业股份有限公司", "甲企业股份有限公司分公司")
    assert (
        fields(grade_expected(reference(tmp_path, target), output(shape, [changed])))[0]["outcome"]
        == "incorrect"
    )


@pytest.mark.parametrize("rank", ["4", "9"])
def test_empty_native_group_rows_bound_fields_without_copying_heading_layout(tmp_path, rank):
    target = "# Summary\n\n## North\n\n- Account：Amount：4\n"
    raw = [
        caption("Summary"),
        grid(
            "<table><tr><th>Item</th><th>Amount</th></tr>"
            '<tr><td colspan="2">North</td></tr><tr><td>Account</td><td>' + rank + "</td></tr>"
            '<tr><td colspan="2">South</td></tr><tr><td>Account</td><td>4</td></tr></table>'
        ),
    ]
    result = fields(grade_expected(reference(tmp_path, target), output("visual", [raw])))[0]
    assert result["actual"] == rank
    assert result["outcome"] == ("correct" if rank == "4" else "incorrect")


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize(
    "label,value,wrong",
    [("Status", "active", "inactive"), ("Notice number", "2028-009", "2028-008")],
)
def test_initial_metadata_split_into_native_blocks_retains_its_record(
    tmp_path, shape, label, value, wrong
):
    target = f"# Annual Report 2027\n\n- Name：Alpha；{label}：{value}\n"
    raw = [
        {"type": "header", "content": "Name：Alpha"},
        {"type": "header", "content": f"{label}：{value}"},
        {
            "type": "doc_title",
            "content": "# Annual Report 2027" if shape == "markdown" else "Annual Report 2027",
        },
    ]
    result = fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))
    assert result and all(row["outcome"] == "correct" for row in result)
    missing = deepcopy(raw)
    missing[1]["content"] = f"{label}：{wrong}"
    bad = fields(grade_expected(reference(tmp_path, target), output(shape, [missing])))
    assert any(row["outcome"] == "incorrect" for row in bad)


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
def test_named_property_grid_reads_values_instead_of_an_axis_intersection_label(tmp_path, shape):
    target = "## Results\n\n- Name：Alpha；Code：ZX17；Venue：Exchange X\n"
    raw = [
        {"type": "title", "content": "Results"},
        grid(
            "<table>"
            "<tr><td>Name</td><td>Alpha</td><td>Code</td><td>ZX17</td></tr>"
            '<tr><td>Venue</td><td colspan="3">Exchange X</td></tr>'
            "<tr><td>Name</td><td>Beta</td><td>Code</td><td>ZX99</td></tr>"
            '<tr><td>Venue</td><td colspan="3">Exchange Y</td></tr></table>'
        ),
    ]
    rows = fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))
    assert rows and all(row["outcome"] == "correct" for row in rows)
    assert rows[-1]["actual"] == "Exchange X"
    changed = deepcopy(raw)
    changed[1]["content"] = changed[1]["content"].replace(
        '<tr><td>Venue</td><td colspan="3">Exchange X</td></tr>', ""
    )
    bad = fields(grade_expected(reference(tmp_path, target), output(shape, [changed])))
    assert bad[-1]["outcome"] == "incorrect"
    assert bad[-1].get("actual") is None


def test_transposed_grid_is_not_suppressed_by_a_wrong_axis_intersection(tmp_path):
    target = "## Results\n\n- Alpha：Revenue：17\n"
    raw = [
        {"type": "title", "content": "Results"},
        grid(
            "<table><tr><td>17</td><td>Alpha</td><td>Beta</td></tr>"
            "<tr><td>Revenue</td><td>9</td><td>17</td></tr></table>"
        ),
    ]
    row = fields(grade_expected(reference(tmp_path, target), output("visual", [raw])))[0]
    assert row["outcome"] == "incorrect" and row["actual"] == "9"


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("own", ["alpha@example.com", "wrong@example.com"])
@pytest.mark.parametrize("key", ["Name", "Director"])
def test_named_column_records_read_properties_below_the_name_row(tmp_path, shape, own, key):
    target = f"## Results\n\n- {key}：Alpha；Email：alpha@example.com\n"
    raw = [
        {"type": "title", "content": "Results"},
        grid(
            "<table>"
            '<tr><th>Contact role</th><th colspan="2">Director</th><th colspan="2">Representative</th></tr>'
            '<tr><td>Name</td><td colspan="2">Alpha</td><td colspan="2">Beta</td></tr>'
            f'<tr><td>Email</td><td colspan="2">{own}</td><td colspan="2">alpha@example.com</td></tr></table>'
        ),
    ]
    rows = fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))
    assert rows[-1]["actual"] == own
    assert rows[-1]["outcome"] == ("correct" if own == "alpha@example.com" else "incorrect")


def test_sibling_properties_in_one_printed_list_keep_their_named_owner(tmp_path):
    target = "## Results\n\n- Name：Alpha；Code：ZX17；Venue：Exchange X\n"
    actual = "## Results\n\n- Name：Alpha；Code：ZX17\n\n- Venue：Exchange X\n\n- Name：Beta；Code：ZX99\n\n- Venue：Exchange Y\n"
    rows = fields(
        grade_expected(
            reference(tmp_path, target), output("markdown", [[{"type": "text", "content": actual}]])
        )
    )
    assert rows and all(row["outcome"] == "correct" for row in rows)
    for changed in (
        actual.replace("- Venue：Exchange X\n\n", "").replace("Exchange Y", "Exchange X"),
        actual.replace(
            "- Venue：Exchange X", "A different business paragraph.\n\n- Venue：Exchange X"
        ),
    ):
        bad = fields(
            grade_expected(
                reference(tmp_path, target),
                output("markdown", [[{"type": "text", "content": changed}]]),
            )
        )
        assert bad[-1]["outcome"] == "incorrect" and bad[-1].get("actual") is None


@pytest.mark.parametrize("caption", ["Graph 4", "Box B", "Graph B1"])
def test_split_figure_title_at_a_default_level_does_not_close_its_printed_parent(tmp_path, caption):
    sentence = "Sources: Independent records; Exchange index."
    target = f"# Report\n\n## Chapter\n\n### {caption}. Review the scenario\n\n{sentence}\n\n## Other division\n\n{sentence}\n"
    actual = f"# Report\n\n## Chapter\n\n## Review the scenario\n\n{caption}\n\n{sentence}\n\n## Other division\n\n{sentence}\n"
    candidate = output("markdown", [[{"type": "text", "content": actual}]])
    rows = [
        row
        for row in grade_expected(reference(tmp_path, target), candidate)["outcomes"]
        if row.get("expected") == sentence
    ]
    assert len(rows) == 2 and all(row["outcome"] == "correct" for row in rows)
    changed = actual.replace(sentence, sentence.replace("Independent", "Changed"), 1)
    rows = [
        row
        for row in grade_expected(
            reference(tmp_path, target),
            output("markdown", [[{"type": "text", "content": changed}]]),
        )["outcomes"]
        if row.get("expected") == sentence
    ]
    assert rows[0]["outcome"] == "incorrect" and "Changed" in rows[0]["actual"]
    assert rows[1]["outcome"] == "correct"
    wrong_id = actual.replace(caption, caption + "9")
    rows = [
        row
        for row in grade_expected(
            reference(tmp_path, target),
            output("markdown", [[{"type": "text", "content": wrong_id}]]),
        )["outcomes"]
        if row.get("expected") == sentence
    ]
    assert rows[0]["outcome"] == "incorrect"


@pytest.mark.parametrize("business", [False, True])
def test_demonstrated_flat_display_levels_do_not_cut_a_known_parent_on_an_extra_title(
    tmp_path, business
):
    text = "The allocation remains subject to independent approval."
    body = "- Account：Amount：4" if business else text
    other = "- Account：Amount：1" if business else text
    target = f"# Report\n\n## North\n\n### Declared detail\n\n{body}\n\n## South\n\n{other}\n"
    actual = f"## Report\n\n## North\n\n## Declared detail\n\n## Additional printed caption\n\n{body}\n\n## South\n\n{other}\n"

    def rows(markdown):
        score = grade_expected(
            reference(tmp_path, target),
            output("markdown", [[{"type": "text", "content": markdown}]]),
        )
        return (
            fields(score)
            if business
            else [row for row in score["outcomes"] if row.get("expected") == text]
        )

    result = rows(actual)
    assert len(result) == 2 and all(row["outcome"] == "correct" for row in result)
    wrong = (
        actual.replace("Amount：4", "Amount：9", 1)
        if business
        else actual.replace("independent", "external", 1)
    )
    result = rows(wrong)
    assert result[0]["outcome"] == "incorrect"
    assert ("9" if business else "external") in result[0]["actual"]
    assert result[1]["outcome"] == "correct"


@pytest.mark.parametrize("business", [False, True])
def test_flat_display_evidence_does_not_disable_levels_in_an_unrelated_parent(tmp_path, business):
    sentence = "A separate required statement."
    body = "- Account：Amount：4" if business else sentence
    target = f"# Report\n\n## North\n\n### Detail\n\n{body}\n\n## South\n\n{body}\n"
    actual = f"# Report\n\n## North\n\n## Detail\n\n{body}\n\n## South\n\n## Unselected sibling\n\n{body}\n"
    score = grade_expected(
        reference(tmp_path, target), output("markdown", [[{"type": "text", "content": actual}]])
    )
    rows = (
        fields(score)
        if business
        else [r for r in score["outcomes"] if r.get("expected") == sentence]
    )
    assert rows[0]["outcome"] == "correct"
    assert rows[1]["outcome"] == "incorrect" and not rows[1].get("actual")


@pytest.mark.parametrize("shape", ["visual", "paddle", "glm", "docvortex", "docling", "markdown"])
@pytest.mark.parametrize("own", ["Independent Exchange A", "Wrong descriptive text"])
@pytest.mark.parametrize("one_block", [False, True])
def test_repeated_identifier_description_pairs_are_read_without_reference_values(
    tmp_path, shape, own, one_block
):
    target = "## Profile\n\n- ZX-17：Independent Exchange A\n"
    raw = [
        {"type": "title", "content": "Profile"},
        *(
            {"type": "text", "content": t}
            for t in ("ZX-17", own, "ZX-99", "Independent Exchange A")
        ),
    ]
    if one_block:
        raw = [raw[0], {"type": "text", "content": "\n".join(item["content"] for item in raw[1:])}]
    row = fields(grade_expected(reference(tmp_path, target), output(shape, [raw])))[0]
    assert row.get("actual") == own
    assert row["outcome"] == ("correct" if own == "Independent Exchange A" else "incorrect")
    changed = deepcopy(raw)
    if one_block:
        changed[1]["content"] = changed[1]["content"].replace(
            "ZX-17", "ZX-17\n# A new business scope", 1
        )
    else:
        changed.insert(2, {"type": "title", "content": "A new business scope"})
    bad = fields(grade_expected(reference(tmp_path, target), output(shape, [changed])))[0]
    assert bad["outcome"] == "incorrect" and bad.get("actual") is None
