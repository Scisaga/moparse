"""Independent literal and public-output contracts, using invented data only."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from moparse_eval.expected_readback import markdown_observation, read_expected
from moparse_eval.expected_scoring import grade_expected
from moparse_eval.packaging import write_json

ROOT = Path(__file__).resolve().parents[2]
CASES = runpy.run_path(str(ROOT / "benchmark/diagnostics/expected-preservation-probes.py"))["cases"]()


def expected(tmp_path, markdown):
    root = tmp_path / "references"
    directory = root / "invented"
    directory.mkdir(parents=True)
    (directory / "expected.md").write_text(markdown)
    write_json(directory / "manifest.json", {"markdown": {"path": "expected.md"}, "source_map": {"entries": [
        {"source_pages": [1], "markdown_lines": [1, len(markdown.splitlines())]}]}})
    return read_expected({"id": "invented", "document_id": "invented", "source_pages": [1]}, root)


def fields(reference, markdown, pipeline="P01"):
    observation = markdown_observation(markdown, sample_id="invented", pipeline=pipeline, pages=[1])
    return [r for r in grade_expected(reference, observation)["outcomes"] if r["kind"] == "business_field"]


@pytest.mark.parametrize("name,reference,markdown,intended", CASES, ids=[c[0] for c in CASES])
def test_independent_preservation_contract(tmp_path, name, reference, markdown, intended):
    source = expected(tmp_path, reference)
    baseline = fields(source, markdown)
    assert bool(baseline) and all(r["outcome"] == "correct" for r in baseline) is intended
    for i in range(2, 9):
        assert fields(source, markdown, f"P{i:02}") == baseline


@pytest.mark.parametrize("wrong", ["- Age: 52（单位：股）", "- Age: 52（单位：元）", "- Age: 52（单位：千克）"])
def test_extra_incompatible_age_unit_is_an_error_even_without_a_required_unit(tmp_path, wrong):
    ref = expected(tmp_path, "- Age: 52\n")
    assert fields(ref, "- Age: 52")[0]["outcome"] == "correct"
    assert fields(ref, wrong)[0]["outcome"] == "incorrect"


def test_column_periods_cannot_be_exchanged_or_borrowed(tmp_path):
    ref = expected(tmp_path, "## 2024年\n\n- Revenue: Q1: 17\n")
    good = "- Revenue; 2024年人民币百万元 / Q1:17\n"
    assert fields(ref, good)[0]["outcome"] == "correct"
    assert fields(ref, good.replace("2024年", "2023年"))[0]["outcome"] == "incorrect"
    assert fields(ref, good.replace("Q1", "Q2"))[0]["outcome"] == "incorrect"


def test_currency_cannot_cross_a_new_list_or_an_intervening_paragraph(tmp_path):
    ref = expected(tmp_path, "单位：元 币种：人民币\n\n- 名称：Beta；金额：原表留空\n")
    actual = "单位：元 币种：人民币\n\n- 名称：Alpha；金额：17\n\nAnother section.\n\n- 名称：Beta；金额：\n"
    assert fields(ref, actual)[-1]["outcome"] == "incorrect"


def test_actual_native_rendering_preserves_mixed_measurement_units(tmp_path):
    from test_native_table_context import table

    from app.models.table_semantics import TextRef
    from app.services.table_semantics_service import bind_table_view, render_semantic_view

    ref = expected(tmp_path, "单位：股\n\n- 姓名：甲；年龄：52；年末持股数：17\n")
    source = table([["姓名", "年龄", "年末持股数"], ["甲", "52", "17"]])
    source.context_refs = (TextRef("native", 1, "caption", "股", "unit", 0, 1, (1,), (0, 1, 2)),)
    view = bind_table_view("v", [source], [source])
    markdown = render_semantic_view(view, [source])
    assert "年龄：52（单位：股）" not in markdown
    assert all(r["outcome"] == "correct" for r in fields(ref, markdown))


def test_native_textual_field_table_keeps_its_caption_in_public_text(tmp_path):
    from test_native_table_context import table

    from app.services.table_context_service import native_scopes
    from app.services.table_semantics_service import bind_table_view, render_semantic_view
    from app.services.table_service import TableCellFragment

    source = table([["Security details", "", ""], ["股票种类", "股票简称", "股票代码"], ["A股", "Example", "000017"]])
    source.cells = [c for c in source.cells if c.row != 0] + [TableCellFragment(0, 0, 1, 3, "Security details")]
    source.native_evidence = native_scopes(source)
    source.source_header_scopes = source.native_evidence["header_scopes"]
    view = bind_table_view("v", [source], [source])
    markdown = render_semantic_view(view, [source])
    assert view.status == "converted"
    assert "Security details" in markdown and "<table" not in markdown and "| ---" not in markdown
    ref = expected(tmp_path, "- 股票种类：A股；股票简称：Example；股票代码：000017\n")
    assert all(r["outcome"] == "correct" for r in fields(ref, markdown))


def test_property_fields_do_not_convert_layout_prose():
    from test_native_table_context import table

    from app.services.table_semantics_service import bind_table_view

    fields_table = table([["公司名称", "Example"], ["公司网址", "https://example.invalid"]])
    assert bind_table_view("v", [fields_table], [fields_table]).status == "converted"
    grid = table([["公司名称", "Example"], ["公司网址", "https://example.invalid"]])
    grid.pdf_evidence = {"content_kind": "layout_grid"}
    view = bind_table_view("v", [grid], [grid])
    assert view.status == "retained" and not view.records
    assert view.retained_rows == (("native", 0), ("native", 1))
    assert "Example" in grid.rendered


@pytest.mark.parametrize("label", ["科目", "主要财务指标", "子公司全称", "关联方", "Account category"])
def test_named_text_subject_is_read_without_an_identity_vocabulary(tmp_path, label):
    reference = expected(tmp_path, f"- {label}：Alpha；金额：17\n")
    equivalent = f"<table><tr><th>{label}</th><th>金额</th></tr><tr><td>Alpha</td><td>17</td></tr></table>"
    assert all(r["outcome"] == "correct" for r in fields(reference, equivalent))
    assert all(r["outcome"] == "correct" for r in fields(reference, f"- {label}：Alpha；金额：17"))
    assert any(r["outcome"] == "incorrect" for r in fields(reference, equivalent.replace("Alpha", "Beta")))


def test_named_parent_and_its_child_remain_distinct_assertions(tmp_path):
    reference = expected(tmp_path, "- Instrument: Loan\n  - Amount: 17\n")
    assert all(r["outcome"] == "correct" for r in fields(reference, "- Instrument: Loan; Amount: 17\n"))
    assert any(r["outcome"] == "incorrect" for r in fields(reference, "- Instrument: Deposit; Amount: 17\n"))


def test_explicit_year_in_annual_caption_is_equivalent_but_wrong_year_is_not(tmp_path):
    reference = expected(tmp_path, "## 2024年度\n\n- Revenue: Amount: 17\n")
    actual = "- Revenue; Amount: 17（期间：（3）2024 年度测量数据:）\n"
    assert all(r["outcome"] == "correct" for r in fields(reference, actual))
    assert any(r["outcome"] == "incorrect" for r in fields(reference, actual.replace("2024", "2023")))


def test_undated_annual_header_does_not_replace_the_required_numeric_year(tmp_path):
    reference = expected(tmp_path, "- Revenue: 2024年: 17\n")
    actual = "- Revenue; 截至12月31日止年度(收入)/支出 / 2024年: 17\n"
    assert all(r["outcome"] == "correct" for r in fields(reference, actual))
    assert any(r["outcome"] == "incorrect" for r in fields(reference, actual.replace("2024年", "2023年")))


def test_compound_identity_keeps_each_named_entity_and_prevents_cross_record_borrowing(tmp_path):
    reference = expected(tmp_path, "- 项目：Loan；关联方：Alpha；本期：17\n- 项目：Loan；关联方：Beta；本期：19\n")
    actual = "- 项目 / 关联方：Loan / Alpha；本期：17\n- 项目 / 关联方：Loan / Beta；本期：19\n"
    assert all(r["outcome"] == "correct" for r in fields(reference, actual))
    assert any(r["outcome"] == "incorrect" for r in fields(reference, actual.replace("本期：17", "本期：19")))


def test_surplus_column_ancestor_does_not_erase_a_required_group(tmp_path):
    reference = expected(tmp_path, "- 姓名：Alpha；亲自出席次数：8\n")
    actual = "- 姓名：Alpha；参加会议情况 / 亲自出席次数：8\n"
    assert all(r["outcome"] == "correct" for r in fields(reference, actual))
    grouped = expected(tmp_path / "grouped", "- 姓名：Alpha；董事会 / 亲自出席次数：8\n")
    assert any(r["outcome"] == "incorrect" for r in fields(grouped, actual))


def test_parent_record_does_not_borrow_values_from_a_child_scope_in_another_list(tmp_path):
    reference = expected(tmp_path, "- Expenses: 2024: -17\n")
    actual = "- Scope: Summary; Expenses; 2024: -17\n\n\n- Scope: Expenses; Research; 2024: 11\n"
    assert all(r["outcome"] == "correct" for r in fields(reference, actual))
    assert any(r["outcome"] == "incorrect" for r in fields(reference, actual.replace("2024: -17", "2024: -11")))


def test_explicit_heading_locates_homonyms_before_their_values(tmp_path):
    reference = expected(tmp_path, "## Team A\n\n- 姓名：Alpha；任期起始日期：2024年01月01日\n")
    actual = "## Team A\n\n- 姓名：Alpha；任期起始日期：2024年01月01日\n\n## Team B\n\n- 姓名：Alpha；任期起始日期：2023年01月01日\n"
    assert all(r["outcome"] == "correct" for r in fields(reference, actual))
    swapped = actual.replace("2024年01月01日", "TEMP").replace("2023年01月01日", "2024年01月01日").replace("TEMP", "2023年01月01日")
    assert any(r["outcome"] == "incorrect" for r in fields(reference, swapped))


def test_plain_numbered_caption_and_amount_unit_are_context_not_empty_records(tmp_path):
    reference = expected(tmp_path, "## 附表1：资金使用情况\n\n金额单位：人民币百万元\n\n- 项目：Alpha；金额：17\n")
    actual = "附表 1:资金使用情况:\n\n金额单位:人民币百万元\n\n<table><tr><th>项目</th><th>金额</th></tr><tr><td>Alpha</td><td>17</td></tr></table>"
    assert all(r["outcome"] == "correct" for r in fields(reference, actual))


def test_parallel_measurements_are_named_facts_instead_of_numeric_identities(tmp_path):
    reference = expected(tmp_path, "- Operating Income: $17 billion; year on year: up 12%\n")
    actual = "- Scope: Results; Revenue: $19 billion; Operating Income: $17 billion\n"
    rows = fields(reference, actual)
    amount = next(r for r in rows if r["expected"].get("named_value"))
    assert amount["row_header_path"] == ["Operating Income"] and amount["outcome"] == "correct"
    assert any(r["outcome"] == "incorrect" for r in rows)  # Growth is still absent.
    bad = fields(reference, actual.replace("$17", "$18"))
    assert next(r for r in bad if r["expected"].get("named_value"))["outcome"] == "incorrect"


def test_named_record_header_is_not_consumed_as_a_property_value(tmp_path):
    from test_native_table_context import table

    from app.services.table_semantics_service import bind_table_view, render_semantic_view

    source = table([["姓名", "主要工作经历"], ["甲", "曾任Example研究员。现任技术负责人。"],
                    ["乙", "曾任Example工程师。现任产品负责人。"]])
    assert not source.native_evidence["field_scopes"]
    view = bind_table_view("v", [source], [source])
    markdown = render_semantic_view(view, [source])
    reference = expected(tmp_path, "- 姓名：甲；主要工作经历：曾任Example研究员。现任技术负责人。\n"
                                  "- 姓名：乙；主要工作经历：曾任Example工程师。现任产品负责人。\n")
    assert view.status == "converted"
    assert "姓名：主要工作经历" not in markdown
    assert all(r["outcome"] == "correct" for r in fields(reference, markdown))


@pytest.mark.parametrize("order", [False, True])
def test_a_correct_claim_does_not_hide_an_incompatible_duplicate_unit(tmp_path, order):
    reference = expected(tmp_path, "- 姓名：Alpha；年龄：52\n")
    claims = ["- 姓名：Alpha；年龄：52", "- 姓名：Alpha；年龄：52（单位：股）"]
    if order:
        claims.reverse()
    result = fields(reference, "\n".join(claims))
    age = next(r for r in result if r["expected"]["column_header_path"] == ["年龄"])
    assert age["outcome"] == "incorrect"


def test_an_incompatible_unit_in_a_different_explicit_period_is_not_the_same_fact(tmp_path):
    reference = expected(tmp_path, "## 2024年度\n\n- 姓名：Alpha；年龄：52\n")
    actual = "- 姓名：Alpha；年龄：52（期间：2024年度）\n- 姓名：Alpha；年龄：51（单位：股；期间：2023年度）\n"
    age = next(r for r in fields(reference, actual) if r["expected"]["column_header_path"] == ["年龄"])
    assert age["outcome"] == "correct"


@pytest.mark.parametrize("reference,actual", [
    ("## The Factory Is Ready\n\n![The Factory Is Ready](image.png)\n", "## The Factory\nIs Ready\n"),
    ("## 公司评级报告　概述\n", "## 公司评级报告\n\n## 概述\n"),
])
def test_complete_visible_text_can_cross_adjacent_markdown_blocks(tmp_path, reference, actual):
    ref = expected(tmp_path, reference)
    observation = markdown_observation(actual, sample_id="invented", pipeline="P01", pages=[1])
    rows = grade_expected(ref, observation)["outcomes"]
    assert rows and all(r["outcome"] == "correct" for r in rows)
    assert any(len(r["candidate"].get("claims", [])) >= 2 for r in rows)


@pytest.mark.parametrize("actual", [
    "## The Factory\nIs not Ready\n",
    "## The Factory\n\n| Metric | Amount |\n| --- | --- |\n| Extra | 17 |\n\nIs Ready\n",
    "## The Factory\n\n![](image.png)\n\nIs Ready\n",
    "## Is Ready\n\nThe Factory\n",
])
def test_continuous_text_never_skips_negation_a_table_or_reading_order(tmp_path, actual):
    ref = expected(tmp_path, "## The Factory Is Ready\n")
    observation = markdown_observation(actual, sample_id="invented", pipeline="P01", pages=[1])
    assert all(r["outcome"] == "incorrect" for r in grade_expected(ref, observation)["outcomes"])


def test_continuous_text_respects_known_physical_page_scope(tmp_path):
    ref = expected(tmp_path, "## The Factory Is Ready\n")
    observation = {"sample_id": "invented", "pages": [
        {"page": 1, "blocks": [{"id": "first", "kind": "text", "text": "The Factory"}]},
        {"page": 2, "blocks": [{"id": "second", "kind": "text", "text": "Is Ready"}]},
    ]}
    assert all(r["outcome"] == "incorrect" for r in grade_expected(ref, observation)["outcomes"])


def test_continuous_text_does_not_invent_a_business_record_binding(tmp_path):
    ref = expected(tmp_path, "- 名称：Alpha；金额：17\n")
    assert all(r["outcome"] == "incorrect" for r in fields(ref, "Alpha\n\n金额：17\n"))


@pytest.mark.parametrize("actual", [
    "- 库存股；2024年金额：17（单位：人民币千元）\n",
    "单位：人民币千元\n\n<table><tr><th>项目</th><th>2024年金额</th></tr><tr><td>库存股</td><td>17</td></tr></table>",
])
def test_business_name_ending_in_shares_cannot_rescue_a_different_metric(tmp_path, actual):
    reference = expected(tmp_path, "单位：人民币千元\n\n- 库存：2024年金额：17\n")
    assert all(r["outcome"] == "incorrect" for r in fields(reference, actual))
    assert all(r["outcome"] == "correct" for r in fields(reference, actual.replace("库存股", "库存")))


@pytest.mark.parametrize("year", ["2024", "2024年末"])
def test_explicit_year_and_share_unit_are_not_mistaken_for_a_business_name(tmp_path, year):
    reference = expected(tmp_path, f"- 项目：Alpha；{year}：17（单位：千股）\n")
    actual = f"- 项目：Alpha；{year}千股：17\n"
    assert all(r["outcome"] == "correct" for r in fields(reference, actual))
    assert any(r["outcome"] == "incorrect" for r in fields(reference, actual.replace("2024", "2023")))
