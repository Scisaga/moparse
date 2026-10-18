"""Read-only original-source acceptance for captured full/PDF-page Markdown.

Examples:
  .venv/bin/python PATH/verify-content-source.py --case 1225474739=CAPTURE/result.md --output CHECK.json
  .venv/bin/python PATH/verify-content-source.py --case 1225475375@87=PAGE87.md --output CHECK.json

Only supplied cases/pages are checked; missing documents are never called a pass.
Use the existing verify-http-source.py independently for the earlier 4/27-page
header, merged-cell and exact table-source regression cases. This tool does not
change teacher prompts/gold, historical outputs, or parser runtime.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
REFERENCE = HERE / "source-reference.json"
PAGE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")
MARKER = re.compile(
    r"<!-- (?:table-fragment: ([^;\s]+)|logical-table: ([^;\s]+); source-pages: ([0-9,]+)) -->"
)
STRUCTURE = re.compile(r"<!-- table-structure: (.*?) -->")
SOURCE = re.compile(
    r"<!-- table-source: ([^;]+); source-page: (\d+); source-rows: ([^;]+); logical-rows: ([^;]+); repeated-header-rows: (\d+) -->"
)
FURNITURE = re.compile(r"<!-- source-furniture: ([^;]+); source-page: (\d+); role: ([^ >]+) -->")
MARKDOWN = MarkdownIt("commonmark", {"html": True})


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def visible_markdown(content):
    """Read rendered text; actual comments are invisible, escaped literals stay.

    Raw source/page/table comments are checked separately, never converted into
    visible text or used to cover a missing original statement.
    """
    pieces = []

    def visit(tokens):
        for token in tokens:
            if token.type in {"text", "code_inline", "code_block", "fence"}:
                pieces.append(token.content)
            elif token.type in {"html_inline", "html_block"}:
                reader = VisibleHTML()
                reader.feed(token.content)
                reader.close()
                pieces.extend(reader.parts)
            elif token.type in {"softbreak", "hardbreak"}:
                pieces.append("\n")
            elif token.type != "image" and token.children:
                visit(token.children)
            elif token.type.endswith("_close"):
                pieces.append("\n")

    visit(MARKDOWN.parse(content))
    return "".join(pieces)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compact(text):
    return re.sub(r"\s+", "", html.unescape(text or ""))


def split_cells(line):
    return [
        html.unescape(value.strip().replace(r"\|", "|"))
        for value in re.split(r"(?<!\\)\|", line.strip()[1:-1])
    ]


def public_tables(content, declared_page=None):
    tables = []
    markers = list(MARKER.finditer(content))
    for i, marker in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(content)
        segment = content[marker.end() : end]
        metadata = STRUCTURE.search(segment)
        grid = re.search(r"(?m)^\|[^\n]*(?:\n\|[^\n]*)*", segment)
        if not metadata or not grid:
            continue
        lines = grid[0].splitlines()
        separator = len(lines) > 1 and all(
            re.fullmatch(r":?-{3,}:?", v) for v in split_cells(lines[1])
        )
        if not separator:
            continue
        rows = [split_cells(line) for row, line in enumerate(lines) if row != 1]
        meta = json.loads(metadata[1])
        preceding = list(PAGE.finditer(content, 0, marker.start()))
        rendered_page = int(preceding[-1][1]) if preceding else declared_page
        tables.append(
            {
                "id": marker[1] or marker[2],
                "meta": meta,
                "rows": rows,
                "rendered_page": rendered_page,
                "start": marker.start(),
                "sources": [
                    {
                        "fragment": m[1],
                        "page": int(m[2]),
                        "source_rows": m[3],
                        "logical_rows": m[4],
                        "repeated_header_rows": int(m[5]),
                    }
                    for m in SOURCE.finditer(segment)
                ],
            }
        )
    return tables


def pages(content, declared_page=None):
    if declared_page:
        return {declared_page: content}
    matches = list(PAGE.finditer(content))
    return {
        int(m[1]): content[
            m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(content)
        ]
        for i, m in enumerate(matches)
    }


def row_matches(tables, page, label):
    expected = compact(label)
    return [
        (table, row, values)
        for table in tables
        if page in table["meta"].get("source_pages", [table["rendered_page"]])
        for row, values in enumerate(table["rows"])
        if values and compact(values[0]) == expected
    ]


def check_source_row(checks, key, tables, page, label, expected_text, *, colspan=None):
    rows = row_matches(tables, page, label)
    ok = len(rows) == 1
    detail = {"matching_rows": len(rows), "source_page": page}
    if ok:
        table, row, values = rows[0]
        payloads = [value for value in values[1:] if compact(value)]
        ok = len(payloads) == 1 and compact(payloads[0]) == compact(expected_text)
        detail.update(
            table_id=table["id"],
            row_zero_based=row,
            expected_text=expected_text,
            actual_payloads=payloads,
        )
        if colspan:
            detail["expected_payload_span"] = [row, 1, 1, colspan]
            detail["actual_spans"] = table["meta"].get("spans")
            ok = ok and detail["expected_payload_span"] in table["meta"].get("spans", [])
    checks.append({"check": key, "pass": bool(ok), **detail})
    return rows


def amount_and_footnote(value, amount, reference):
    # A separate semantic marker is mandatory. Plain concatenation or numeric
    # substring matching can never pass this check.
    escaped_amount, escaped_reference = re.escape(amount), re.escape(reference)
    pattern = (
        rf"\s*{escaped_amount}\s*(?:<sup(?:\s[^>]*)?>\s*{escaped_reference}\s*</sup>"
        rf"|\[\^{escaped_reference}\]|\[{escaped_reference}\]|\s+{escaped_reference})\s*"
    )
    return re.fullmatch(pattern, value, flags=re.I) is not None


def check_document(stem, content, declared_page, reference):
    pmap, tables = pages(content, declared_page), public_tables(content, declared_page)
    rendered = {number: visible_markdown(page_content) for number, page_content in pmap.items()}
    checks = []
    for furniture in FURNITURE.finditer(content):
        preceding = list(PAGE.finditer(content, 0, furniture.start()))
        rendered_page = int(preceding[-1][1]) if preceding else declared_page
        checks.append(
            {
                "check": "source_furniture_original_page_binding",
                "pass": int(furniture[2]) == rendered_page,
                "source_ref": furniture[1],
                "role": furniture[3],
                "source_page": int(furniture[2]),
                "rendered_page": rendered_page,
            }
        )
    wanted_pages = reference["source_documents"][stem]["inspected_pages"]
    page_selection = [declared_page] if declared_page else wanted_pages
    for page in page_selection:
        if page == 130 and stem == "1225474739":
            continue  # Source page 130 supplies printed continuation columns.
        checks.append(
            {
                "check": f"p{page}_source_page_present",
                "pass": page in pmap,
                "provenance": "explicit_single_source_page_capture"
                if declared_page
                else "public_page_marker",
            }
        )
    if stem == "1225474739":
        source = reference[stem]
        if 19 in pmap:
            s = source["page19"]
            check_source_row(
                checks,
                "p19_complete_risk_cell_and_binding",
                tables,
                19,
                s["risk_label"]["text"],
                s["risk_control_merged_cell"]["text"],
                colspan=8,
            )
            amount_rows = row_matches(tables, 19, "远期结售汇")
            exact = len(amount_rows) == 1 and len(amount_rows[0][2]) == 9
            actual = amount_rows[0][2][7] if exact else None
            exact = exact and amount_and_footnote(actual, s["amount"], s["footnote_reference"])
            checks.append(
                {
                    "check": "p19_exact_amount_separate_footnote",
                    "pass": exact,
                    "expected_amount": s["amount"],
                    "expected_footnote": s["footnote_reference"],
                    "actual_cell": actual,
                }
            )
            rows = row_matches(tables, 19, "报告期实际损益情况的说明")
            actual = rows[0][2][1] if len(rows) == 1 and len(rows[0][2]) > 1 else ""
            checks.append(
                {
                    "check": "p19_negative_decimal_in_own_explanation_cell",
                    "pass": bool(re.search(r"(?<![\d.,])-0\.61(?![\d.])", actual)),
                    "actual_cell": actual,
                }
            )
        if 40 in pmap:
            s = source["page40"]
            note_rows = check_source_row(
                checks,
                "p40_complete_financing_explanation_same_cell",
                tables,
                40,
                s["financing_explanation_label"]["text"],
                s["financing_explanation_cell"]["text"],
            )
            actual_note = compact(note_rows[0][2][1]) if len(note_rows) == 1 else ""
            for binding in s["account_bindings"]:
                checks.append(
                    {
                        "check": f"p40_financing_person_{binding['number']}_account_association",
                        "pass": compact(binding["raw_source_paragraph"]) in actual_note,
                        "expected": binding,
                        "scope": "Same original financing explanation row/cell, not a value anywhere in the document",
                    }
                )
            explanation = check_source_row(
                checks,
                "p40_independent_explanation_row",
                tables,
                40,
                s["independent_explanation_label"]["text"],
                s["independent_explanation_text"]["text"],
            )
            last = row_matches(tables, 40, "尹缘平")
            checks.append(
                {
                    "check": "p40_explanation_distinct_from_last_shareholder_row",
                    "pass": len(explanation) == 1
                    and len(last) == 1
                    and (explanation[0][0]["id"], explanation[0][1])
                    != (last[0][0]["id"], last[0][1]),
                }
            )
            for expected in s["shareholder_rows_4cols"]:
                matches = row_matches(tables, 40, expected[0])
                # A complex table can retain a wider base grid with spans. Its
                # nonempty physical anchors must still match four source cells.
                actual_rows = [
                    [compact(v) for v in values if compact(v)] for _, _, values in matches
                ]
                exact = [compact(v) for v in expected] in actual_rows
                checks.append(
                    {
                        "check": f"p40_shareholder_four_physical_cells_{compact(expected[0])}",
                        "pass": exact,
                        "expected": expected,
                        "actual_rows": actual_rows,
                    }
                )
            expected = s["top_chenqingliang_9cols"]
            candidates = [
                values for _, _, values in row_matches(tables, 40, expected[0]) if len(values) == 9
            ]
            checks.append(
                {
                    "check": "p40_chenqingliang_exact_nine_top_cells",
                    "pass": any(
                        [compact(v) for v in values] == [compact(v) for v in expected]
                        for values in candidates
                    ),
                    "expected": expected,
                    "actual_rows": candidates,
                }
            )
        if 74 in pmap:
            s = source["page74"]
            actual = compact(rendered[74])
            heading, sentence = (
                compact(s["policy_heading"]["text"]),
                compact(s["policy_sentence"]["text"]),
            )
            h, n, nxt = (
                actual.find(heading),
                actual.find(sentence),
                actual.find("研发支出的归集范围及相关会计处理方法"),
            )
            checks.append(
                {
                    "check": "p74_complete_policy_heading_sentence_and_order",
                    "pass": 0 <= h < n < nxt,
                    "expected_heading": heading,
                    "expected_sentence": sentence,
                    "actual_positions": [h, n, nxt],
                }
            )
        if 131 in pmap or any(131 in t["meta"].get("source_pages", []) for t in tables):
            s = source["page130_131"]
            expected = [compact(v) for v in s["page131_rows_raw"][1]]
            candidates = row_matches(tables, 131, expected[0])
            exact = [
                (t, r, v)
                for t, r, v in candidates
                if t["meta"].get("num_cols") == 6 and [compact(x) for x in v] == expected
            ]
            checks.append(
                {
                    "check": "p131_exact_six_columns_total_with_blank_cells_and_percentage",
                    "pass": len(exact) == 1,
                    "expected": expected,
                    "actual_candidates": [
                        {"table_id": t["id"], "declared_cols": t["meta"].get("num_cols"), "row": v}
                        for t, _, v in candidates
                    ],
                }
            )
            provenance = False
            if len(exact) == 1:
                table, row, _ = exact[0]
                if table["meta"].get("source_pages") == [131]:
                    provenance = table["rendered_page"] == 131
                else:
                    for src in table["sources"]:
                        logical = [int(x) for x in src["logical_rows"].split("-")]
                        if src["page"] == 131 and logical[0] <= row + 1 <= logical[-1]:
                            provenance = True
            checks.append(
                {"check": "p131_total_row_has_actual_page131_provenance", "pass": provenance}
            )
    elif stem == "1225475375":
        source = reference[stem]
        if 74 in pmap:
            expected = compact(source["page74"]["negative_business_conclusion"]["text"])
            checks.append(
                {
                    "check": "p74_negative_business_conclusion_after_table",
                    "pass": expected in compact(rendered[74]),
                    "expected": expected,
                }
            )
        if 87 in pmap:
            s = source["page87"]
            expected = [[compact(v) for v in row] for row in s["rows_raw"]]
            candidates = [t for t in tables if 87 in t["meta"].get("source_pages", [])]
            exact_tables = [
                t
                for t in candidates
                if [[compact(v) for v in row] for row in t["rows"]] == expected
            ]
            checks.append(
                {
                    "check": "p87_upright_nine_columns_all_ninety_positions",
                    "pass": len(exact_tables) == 1,
                    "source_rows": 10,
                    "source_columns": 9,
                    "candidate_shapes": [
                        [len(t["rows"]), t["meta"].get("num_cols")] for t in candidates
                    ],
                    "exact_positions": 90 if len(exact_tables) == 1 else 0,
                }
            )
            spans_ok = len(exact_tables) == 1 and sorted(
                exact_tables[0]["meta"].get("spans", [])
            ) == sorted(s["spans"])
            header_ok = len(exact_tables) == 1 and exact_tables[0]["meta"].get("header_rows") == [
                0,
                1,
            ]
            checks.append(
                {
                    "check": "p87_six_column_group_full_spans_and_two_header_rows",
                    "pass": spans_ok and header_ok,
                    "expected_spans": s["spans"],
                }
            )
            checks.append(
                {
                    "check": "p87_business_footnote_retained",
                    "pass": compact(s["footnote"]["text"]) in compact(rendered[87]),
                }
            )
    elif stem == "1225474139":
        source = reference[stem]
        if 28 in pmap:
            expected = compact(source["page28"]["ordered_paragraph"]["text"])
            checks.append(
                {
                    "check": "p28_complete_paragraph_exact_order",
                    "pass": expected in compact(rendered[28]),
                    "expected": expected,
                }
            )
        if 30 in pmap:
            actual = compact(rendered[30])
            expected = compact(source["page30"]["blank_date"]["text"])
            fabricated_date = re.findall(r"\d{2,4}年|\d{1,2}月|\d{1,2}日", actual)
            checks.append(
                {
                    "check": "p30_blank_date_not_fabricated",
                    "pass": expected in actual and not fabricated_date,
                    "expected": expected,
                    "observed_numeric_dates": fabricated_date,
                }
            )
    elif stem == "1206337604":
        source = reference[stem]
        for page in page_selection:
            if str(page) not in source["pages"] or page not in pmap:
                continue
            actual = compact(rendered[page])
            spans = source["pages"][str(page)]["nonempty_native_spans"]
            missing = [s for s in spans if compact(s["text"]) not in actual]
            checks.append(
                {
                    "check": f"p{page}_all_independent_native_spans_coverage",
                    "pass": not missing,
                    "span_count": len(spans),
                    "missing_source_spans": missing,
                    "scope": "Character coverage only; table, order and provenance are separate checks.",
                }
            )
        if 1 in pmap:
            actual = compact(rendered[1])
            header = compact(source["identity_line"]["text"])
            title = compact(source["title"]["text"])
            checks.append(
                {
                    "check": "p1_complete_security_identity_before_exact_title",
                    "pass": 0 <= actual.find(header) < actual.find(title),
                    "expected_identity": header,
                    "expected_title": title,
                }
            )
        if 2 in pmap:
            expected = compact(source["record_date"]["text"])
            checks.append(
                {
                    "check": "p2_actual_record_date_retained",
                    "pass": expected in compact(rendered[2]),
                    "expected": expected,
                }
            )
    return {
        "checks": checks,
        "passed_checks": sum(c["pass"] for c in checks),
        "total_checks": len(checks),
        "pass": bool(checks) and all(c["pass"] for c in checks),
        "inspected_output_pages": sorted(pmap),
        "selected_source_pages": page_selection,
        "parsed_public_tables": len(tables),
    }


def self_test():
    assert amount_and_footnote("6,606.57<sup>1</sup>", "6,606.57", "1")
    assert amount_and_footnote("6,606.57[^1]", "6,606.57", "1")
    assert amount_and_footnote("6,606.57 1", "6,606.57", "1")
    assert not amount_and_footnote("6,606.571", "6,606.57", "1")
    assert not amount_and_footnote("16,606.57<sup>1</sup>", "6,606.57", "1")
    assert not amount_and_footnote("6,606.57", "6,606.57", "1")
    assert compact("无经营相关财务资料。日，截至本报告书签署日，暂") != compact(
        "日，截至本报告书签署日，暂无经营相关财务资料。"
    )
    assert re.search(r"(?<![\d.,])-0\.61(?![\d.])", "-0.61万元")
    assert not re.search(r"(?<![\d.,])-0\.61(?![\d.])", "061万元")
    assert not re.search(r"(?<![\d.,])-0\.61(?![\d.])", "-0.611万元")
    print(json.dumps({"self_test": "pass", "positive_and_negative_checks": 10}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    parser.add_argument(
        "--case", action="append", default=[], help="STEM=MARKDOWN or STEM@PDF_PAGE=MARKDOWN"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        if not args.case:
            return 0
    if not args.case or not args.output:
        parser.error("--case and --output are required")
    if args.output.exists():
        parser.error("Refusing to overwrite captured acceptance evidence")
    raw = args.reference.read_bytes()
    reference = json.loads(raw)
    result = {
        "schema": "mosaicparse-original-content-acceptance/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "reference": str(args.reference),
        "reference_SHA256": sha(raw),
        "verifier_SHA256": sha(Path(__file__).read_bytes()),
        "source": "Independent matching source PDF, character geometry and reviewed visible grids",
        "scope": "Targeted content/structure only; no whole-document semantic accuracy claim",
        "cases": [],
    }
    for assignment in args.case:
        key, path = assignment.split("=", 1)
        stem, page = key.split("@", 1) if "@" in key else (key, None)
        if stem not in reference["source_documents"]:
            parser.error(f"Unknown source: {stem}")
        source = reference["source_documents"][stem]
        if sha((REPO / source["path"]).read_bytes()) != source["sha256"]:
            parser.error(f"Original source SHA mismatch: {stem}")
        payload = Path(path).read_bytes()
        checked = check_document(stem, payload.decode(), int(page) if page else None, reference)
        result["cases"].append(
            {
                "source": stem,
                "source_SHA256": source["sha256"],
                "markdown": path,
                "markdown_SHA256": sha(payload),
                "markdown_bytes": len(payload),
                **checked,
            }
        )
    result["pass"] = all(case["pass"] for case in result["cases"])
    result["passed_checks"] = sum(case["passed_checks"] for case in result["cases"])
    result["total_checks"] = sum(case["total_checks"] for case in result["cases"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pass": result["pass"],
                "passed_checks": result["passed_checks"],
                "total_checks": result["total_checks"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
