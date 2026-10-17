"""Positive and adversarial checks of the source verifier, without model calls.

Synthetic strings exist only in memory, explicitly as verifier test fixtures.
They are never saved as parser results or included in model-quality counts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("source_verifier", HERE / "verify-content-source.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
reference = json.loads((HERE / "source-reference.json").read_text())


def table(name, page, rows, spans=None, headers=None):
    rows = [[str(v or "").replace("\n", " ").strip() for v in row] for row in rows]
    meta = {
        "table_id": name,
        "source_pages": [page],
        "num_rows": len(rows),
        "num_cols": len(rows[0]),
        "spans": spans or [],
        "header_rows": headers,
    }
    grid = ["| " + " | ".join(values) + " |" for values in rows]
    grid.insert(1, "| " + " | ".join(["---"] * len(rows[0])) + " |")
    return (
        f"<!-- table-fragment: {name} -->\n<!-- table-structure: {json.dumps(meta, ensure_ascii=False)} -->\n"
        + "\n".join(grid)
        + "\n"
    )


def page(number, *content):
    return f"<!-- page: {number} -->\n" + "\n".join(content) + "\n"


def fixtures():
    a = reference["1225474739"]
    p19 = a["page19"]
    p40 = a["page40"]
    p74 = a["page74"]

    def nine(label, text):
        return [label, text] + [""] * 7

    rows19 = [
        nine("衍生品投资类型", "初始投资金额"),
        [
            "远期结售汇",
            "0",
            "0",
            "2.06",
            "0",
            "9,671.48",
            "3,064.91",
            "6,606.57<sup>1</sup>",
            "4.35%",
        ],
        nine(p19["risk_label"]["text"], p19["risk_control_merged_cell"]["text"]),
        nine("报告期实际损益情况的说明", p19["actual_profit_loss_cell"]["text"]),
    ]
    rows40 = [
        [p40["independent_explanation_label"]["text"], p40["independent_explanation_text"]["text"]],
        [p40["financing_explanation_label"]["text"], p40["financing_explanation_cell"]["text"]],
    ]
    md134 = page(19, table("p19_t2", 19, rows19, [[2, 1, 1, 8], [3, 1, 1, 8]], [0]))
    md134 += page(
        40,
        table("p40_body", 40, p40["shareholder_rows_4cols"]),
        table("p40_top", 40, [p40["top_chenqingliang_9cols"]]),
        table("p40_notes", 40, rows40),
    )
    md134 += page(
        74,
        p74["policy_heading"]["text"],
        p74["policy_sentence"]["text"],
        "研发支出的归集范围及相关会计处理方法",
    )
    md134 += page(130, "Original preceding continuation page retained in fixture.")
    md134 += page(131, table("p131_t1", 131, a["page130_131"]["page131_rows_raw"]))
    b = reference["1225475375"]
    p87 = b["page87"]
    md119 = page(74, b["page74"]["negative_business_conclusion"]["text"])
    md119 += page(
        87, table("p87_t1", 87, p87["rows_raw"], p87["spans"], [0, 1]), p87["footnote"]["text"]
    )
    c = reference["1225474139"]
    md36 = page(28, c["page28"]["ordered_paragraph"]["text"]) + page(
        30, c["page30"]["blank_date"]["text"]
    )
    office = reference["1206337604"]
    md2 = "".join(
        page(int(n), *[line["text"] for line in p["native_lines"]])
        for n, p in office["pages"].items()
    )
    return {"1225474739": md134, "1225475375": md119, "1225474139": md36, "1206337604": md2}


def run(output):
    if output.exists():
        raise ValueError("Refusing to overwrite verifier self-test evidence")
    fixtures_by_stem = fixtures()
    checks = []
    for stem, content in fixtures_by_stem.items():
        result = verifier.check_document(stem, content, None, reference)
        failed = [c["check"] for c in result["checks"] if not c["pass"]]
        assert result["pass"], (stem, failed)
        checks.append(
            {
                "test": f"positive_all_targeted_checks_{stem}",
                "pass": True,
                "checked_conditions": result["total_checks"],
            }
        )
    header = reference["1206337604"]["identity_line"]["text"]
    parts = re.split(r"\s{2,}", header.strip())
    assert len(parts) == 2
    separated = fixtures_by_stem["1206337604"].replace(
        header,
        parts[0]
        + "\n<!-- source-furniture: #/fixture/second-header; source-page: 1; role: page_header -->\n"
        + parts[1],
    )
    separated_result = verifier.check_document("1206337604", separated, None, reference)
    assert separated_result["pass"], [c for c in separated_result["checks"] if not c["pass"]]
    checks.append({"test": "visible_original_header_separated_by_source_comment", "pass": True})
    code = re.search(r"\d+", parts[0]).group()
    comment_mutations = [
        (
            "security_fields_reversed_with_values_present",
            separated.replace(parts[0], "TEMP_FIRST")
            .replace(parts[1], parts[0])
            .replace("TEMP_FIRST", parts[1]),
            "p1_complete_security_identity_before_exact_title",
        ),
        (
            "missing_security_value_shadowed_by_comment",
            separated.replace(code, "<!-- hidden original value " + code + " -->"),
            "p1_complete_security_identity_before_exact_title",
        ),
        (
            "whole_identity_only_inside_comment",
            fixtures_by_stem["1206337604"].replace(header, "<!-- " + header + " -->"),
            "p1_complete_security_identity_before_exact_title",
        ),
        (
            "correct_visible_header_wrong_furniture_source_page",
            separated.replace(
                "source-page: 1; role: page_header", "source-page: 2; role: page_header"
            ),
            "source_furniture_original_page_binding",
        ),
    ]
    for name, modified, expected_failure in comment_mutations:
        result = verifier.check_document("1206337604", modified, None, reference)
        assert any(c["check"] == expected_failure and not c["pass"] for c in result["checks"]), name
        checks.append({"test": name, "pass": True, "expected_failure_detected": expected_failure})
    assert (
        verifier.compact(verifier.visible_markdown("left <!-- invisible --> right")) == "leftright"
    )
    assert "<!-- visible literal -->" in verifier.visible_markdown("&lt;!-- visible literal --&gt;")
    assert "<!-- code literal -->" in verifier.visible_markdown(
        "```text\n<!-- code literal -->\n```"
    )
    checks.append(
        {
            "test": "actual_comment_invisible_escaped_and_code_literals_visible",
            "pass": True,
            "conditions": 3,
        }
    )
    mutations = [
        (
            "1225474739",
            "polluted_decimal",
            lambda s: s.replace("6,606.57<sup>1</sup>", "6,606.571"),
            "p19_exact_amount_separate_footnote",
        ),
        (
            "1225474739",
            "missing_reference",
            lambda s: s.replace("6,606.57<sup>1</sup>", "6,606.57"),
            "p19_exact_amount_separate_footnote",
        ),
        (
            "1225474739",
            "lost_minus_decimal",
            lambda s: s.replace("-0.61", "061"),
            "p19_negative_decimal_in_own_explanation_cell",
        ),
        (
            "1225474739",
            "truncated_risk",
            lambda s: s.replace("外汇交易行为均以正常生产经营为基础", "TRUNCATED"),
            "p19_complete_risk_cell_and_binding",
        ),
        (
            "1225474739",
            "wrong_person_credit_binding",
            lambda s: s.replace("3,093,000", "3,093,001"),
            "p40_financing_person_6_account_association",
        ),
        (
            "1225474739",
            "wrong_person_ordinary_binding",
            lambda s: s.replace("75,900", "75,901"),
            "p40_financing_person_7_account_association",
        ),
        (
            "1225474739",
            "wrong_explanation_label",
            lambda s: s.replace(
                reference["1225474739"]["page40"]["independent_explanation_label"]["text"]
                .replace("\n", " ")
                .strip(),
                "MISSING LABEL",
            ),
            "p40_independent_explanation_row",
        ),
        (
            "1225474739",
            "combined_shareholder_names",
            lambda s: s.replace("| 彭朝晖 |", "| 彭朝晖 罗洪波 |"),
            "p40_shareholder_four_physical_cells_彭朝晖",
        ),
        (
            "1225474739",
            "wrong_chenqingliang_amount",
            lambda s: s.replace("1,314,000", ",314,000"),
            "p40_chenqingliang_exact_nine_top_cells",
        ),
        (
            "1225474739",
            "missing_policy",
            lambda s: s.replace(reference["1225474739"]["page74"]["policy_sentence"]["text"], ""),
            "p74_complete_policy_heading_sentence_and_order",
        ),
        (
            "1225474739",
            "missing_percentage",
            lambda s: s.replace("92.29%", ""),
            "p131_exact_six_columns_total_with_blank_cells_and_percentage",
        ),
        (
            "1225474739",
            "wrong_source_page",
            lambda s: s.replace('"source_pages": [131]', '"source_pages": [130]'),
            "p131_total_row_has_actual_page131_provenance",
        ),
        (
            "1225475375",
            "missing_negative_conclusion",
            lambda s: s.replace(
                reference["1225475375"]["page74"]["negative_business_conclusion"]["text"], ""
            ),
            "p74_negative_business_conclusion_after_table",
        ),
        (
            "1225475375",
            "missing_group_span",
            lambda s: s.replace("[0, 2, 1, 6]", "[0, 2, 1, 5]"),
            "p87_six_column_group_full_spans_and_two_header_rows",
        ),
        (
            "1225475375",
            "wrong_header_depth",
            lambda s: s.replace('"header_rows": [0, 1]', '"header_rows": [0]'),
            "p87_six_column_group_full_spans_and_two_header_rows",
        ),
        (
            "1225475375",
            "wrong_bound_numeric_cell",
            lambda s: s.replace("-337,962.19", "-337,962.18"),
            "p87_upright_nine_columns_all_ninety_positions",
        ),
        (
            "1225474139",
            "reordered_text_same_characters",
            lambda s: s.replace("暂\n无经营相关财务资料。", "无经营相关财务资料。\n暂"),
            "p28_complete_paragraph_exact_order",
        ),
        (
            "1225474139",
            "fabricated_blank_date",
            lambda s: s.replace("年\n月\n日", "2026年10月17日"),
            "p30_blank_date_not_fabricated",
        ),
        (
            "1206337604",
            "lost_security_code",
            lambda s: s.replace("300635", ""),
            "p1_complete_security_identity_before_exact_title",
        ),
        (
            "1206337604",
            "wrong_record_date",
            lambda s: s.replace("2019 年6 月4 日 星期二", "2019 年6 月5 日 星期三"),
            "p2_actual_record_date_retained",
        ),
    ]
    for stem, name, mutation, expected_failure in mutations:
        original = fixtures_by_stem[stem]
        modified = mutation(original)
        assert modified != original, f"Bad mutation did not modify fixture: {name}"
        result = verifier.check_document(stem, modified, None, reference)
        failures = [c["check"] for c in result["checks"] if not c["pass"]]
        assert expected_failure in failures, (name, expected_failure, failures)
        checks.append({"test": name, "pass": True, "expected_failure_detected": expected_failure})
    verifier.self_test()
    result = {
        "schema": "mosaicparse-source-verifier-self-test/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "scope": "In-memory synthetic verification fixtures only, zero inference or HTTP calls; not parser/model-quality results.",
        "verifier_SHA256": hashlib.sha256(
            (HERE / "verify-content-source.py").read_bytes()
        ).hexdigest(),
        "reference_SHA256": hashlib.sha256(
            (HERE / "source-reference.json").read_bytes()
        ).hexdigest(),
        "checks": checks,
        "pass": all(c["pass"] for c in checks),
        "tests": len(checks),
        "additional_helper_positive_negative_tests": 10,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "self_tests": len(checks),
                "additional_helpers": 10,
                "pass": True,
                "output": str(output),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "verifier-self-test.json")
    run(parser.parse_args().output)
