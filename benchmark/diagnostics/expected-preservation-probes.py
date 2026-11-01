"""Controlled scoring-contract counterexamples; no real corpus or PDF input.

Run from the repository root. Exit 1 means a contract counterexample remains.
The program accepts no input paths and never reads or writes corpus references.
All references below are invented software fixtures in a temporary directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from moparse_eval.cli import code_identity  # noqa: E402
from moparse_eval.expected_readback import markdown_observation, read_expected  # noqa: E402
from moparse_eval.expected_scoring import grade_expected  # noqa: E402
from moparse_eval.packaging import write_json  # noqa: E402


def cases():
    name = "- Legal name: Example Corp\n"
    money = "单位：人民币千元。\n\n- 庫存股：2024年金額：17。\n"
    age = "单位：股。\n\n- 姓名：甲；年龄：52；年末持股数：17。\n"
    currency = "单位：元 币种：人民币。\n\n- 名称：Alpha；金额：17。\n- 名称：Beta；金额：原表留空。\n"
    quarter = "单位：人民币百万元。\n\n- 项目：Alpha；一季度：17。\n"
    path = "- 总资产(亿元)：2011年：17。\n"
    return [
        ("named_html_span", name,
         '<table><tr><td></td><td></td><td></td><td></td></tr>'
         '<tr><td>Legal name</td><td colspan="3">Example Corp</td></tr></table>', True),
        ("named_prose_control", name, name, True),
        ("monetary_stock_account", money, "- 庫存股：2024年金額：17（单位：人民币千元）。\n", True),
        ("stock_account_wrong_count_unit", money, "- 庫存股：2024年金額：17（单位：股）。\n", False),
        ("age_without_shares", age, "- 姓名：甲；年龄：52；年末持股数：17（单位：股）。\n", True),
        ("age_with_wrong_shares", age,
         "- 姓名：甲；年龄：52（单位：股）；年末持股数：17（单位：股）。\n", False),
        ("currency_one_list_caption", currency,
         "单位：元 币种：人民币\n\n- 名称：Alpha；金额：17。\n- 名称：Beta；金额：。\n", True),
        ("currency_repeated_caption_control", currency,
         "单位：元 币种：人民币\n\n- 名称：Alpha；金额：17。\n\n"
         "单位：元 币种：人民币\n\n- 名称：Beta；金额：。\n", True),
        ("year_unit_column_path", quarter,
         "单位：人民币百万元\n\n- 项目：Alpha；2024年人民币百万元 / 一季度：17。\n", True),
        ("separate_column_qualifier_control", quarter,
         "单位：人民币百万元\n\n- 项目：Alpha；一季度：17（单位：人民币百万元）。\n", True),
        ("printed_subject_path", path,
         "- 范围：主要财务数据；项目：财务数据与指标 / 总资产(亿元)；2011年：17。\n", True),
        ("nested_subject_path_control", path,
         "- 财务数据与指标\n  - 总资产(亿元)：2011年：17。\n", True),
    ]


def main() -> int:
    results = []
    for identifier, reference, actual, intended in cases():
        with TemporaryDirectory(prefix="moparse-synthetic-contract-") as temporary:
            root = Path(temporary)
            directory = root / "invented"
            directory.mkdir()
            (directory / "expected.md").write_text(reference, encoding="utf-8")
            write_json(directory / "manifest.json", {
                "markdown": {"path": "expected.md"}, "source_map": {"entries": [
                    {"source_pages": [1], "markdown_lines": [1, len(reference.splitlines())]},
                ]},
            })
            expected = read_expected({"id": "synthetic", "document_id": "invented", "source_pages": [1]}, root)
            candidate = markdown_observation(actual, sample_id="synthetic", pipeline="generic", pages=[1])
            score = grade_expected(expected, candidate)
            fields = [row for row in score["outcomes"] if row["kind"] == "business_field"]
            if not fields:
                raise AssertionError("an invented business fixture was not read")
            observed = all(row["outcome"] == "correct" for row in fields)
            results.append({
                "id": identifier, "reference_fixture": reference, "candidate_fixture": actual,
                "intended_all_business_fields_correct": intended,
                "observed_all_business_fields_correct": observed, "violates_contract": observed != intended,
                "fields": [{key: row.get(key) for key in (
                    "row_header_path", "expected", "actual", "outcome", "reason",
                )} for row in fields],
            })
    failures = sum(result["violates_contract"] for result in results)
    print(json.dumps({"scope": "invented_software_contracts_only_not_quality_results",
                      "software_id": code_identity()["software_id"], "cases": len(results),
                      "contract_failures": failures, "results": results}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
