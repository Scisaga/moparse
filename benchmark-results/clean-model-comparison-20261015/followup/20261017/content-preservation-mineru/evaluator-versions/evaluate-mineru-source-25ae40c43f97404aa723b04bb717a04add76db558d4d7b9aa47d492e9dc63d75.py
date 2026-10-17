"""Evaluate official raw MinerU blocks against independent original-PDF cells.

This is an offline model-output reader, not a MosaicParse adapter. No public
page/table-source comments are added. Model content/table correctness and the
unimplemented public-interface provenance are deliberately separate results.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import string
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE_REFERENCE = (
    HERE.parent / "selected-pipeline-deployment/source-independent-recheck-20261017.json"
)
spec = importlib.util.spec_from_file_location("source_verifier", HERE / "verify-content-source.py")
source_verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source_verifier)
compact = source_verifier.compact
TYPOGRAPHY_EQUIVALENCE = str.maketrans(
    {
        chr(codepoint): unicodedata.normalize("NFKC", chr(codepoint))
        for codepoint in range(0xFF01, 0xFF5F)
        if unicodedata.category(chr(codepoint))[0] in {"P", "S"}
        and unicodedata.normalize("NFKC", chr(codepoint)) in string.punctuation
    }
)


def prose(text):
    """Fullwidth ASCII punctuation only; never delete signs or alter digits."""
    return compact(text).translate(TYPOGRAPHY_EQUIVALENCE)


class VisibleReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def visible(text):
    reader = VisibleReader()
    reader.feed(text or "")
    reader.close()
    return "".join(reader.parts)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class TableReader(HTMLParser):
    """Read HTML anchors and explicit spans; never infer absent cells/text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.cell = None
        self.row = -1
        self.column = 0
        self.occupied = set()
        self.errors = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            if self.table is not None:
                self.errors.append("Nested table not supported by the acceptance reader")
                return
            self.table = {"cells": [], "closed": False}
            self.row = -1
            self.occupied = set()
        elif tag == "tr" and self.table is not None:
            self.row += 1
            self.column = 0
        elif tag in ("td", "th") and self.table is not None:
            while (self.row, self.column) in self.occupied:
                self.column += 1
            try:
                rowspan, colspan = int(attrs.get("rowspan", "1")), int(attrs.get("colspan", "1"))
            except ValueError:
                self.errors.append("Invalid explicit rowspan/colspan")
                rowspan, colspan = 1, 1
            self.cell = {
                "row": self.row,
                "column": self.column,
                "rowspan": rowspan,
                "colspan": colspan,
                "text": "",
                "semantic_markup": "",
                "tag": tag,
                "HTML_line_column": list(self.getpos()),
            }
        elif self.cell is not None:
            if tag == "br":
                self.cell["text"] += "\n"
                self.cell["semantic_markup"] += "\n"
            elif tag == "sup":
                self.cell["semantic_markup"] += "<sup>"

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data
            self.cell["semantic_markup"] += data

    def handle_endtag(self, tag):
        if tag == "sup" and self.cell is not None:
            self.cell["semantic_markup"] += "</sup>"
        elif tag in ("td", "th") and self.cell is not None:
            cell = self.cell
            for row in range(cell["row"], cell["row"] + cell["rowspan"]):
                for column in range(cell["column"], cell["column"] + cell["colspan"]):
                    if (row, column) in self.occupied:
                        self.errors.append(
                            f"Overlapping physical cells at row {row}, column {column}"
                        )
                    self.occupied.add((row, column))
            self.table["cells"].append(cell)
            self.column += cell["colspan"]
            self.cell = None
        elif tag == "table" and self.table is not None:
            self.table["closed"] = True
            rows = max((cell["row"] + cell["rowspan"] for cell in self.table["cells"]), default=0)
            columns = max(
                (cell["column"] + cell["colspan"] for cell in self.table["cells"]), default=0
            )
            grid = [[""] * columns for _ in range(rows)]
            for cell in self.table["cells"]:
                grid[cell["row"]][cell["column"]] = cell["text"]
            self.table.update(
                rows=grid,
                num_rows=rows,
                num_cols=columns,
                spans=[
                    [cell["row"], cell["column"], cell["rowspan"], cell["colspan"]]
                    for cell in self.table["cells"]
                    if cell["rowspan"] > 1 or cell["colspan"] > 1
                ],
                complete_physical_coverage=all(
                    (row, column) in self.occupied
                    for row in range(rows)
                    for column in range(columns)
                ),
                uncovered_grid_positions=[
                    [row, column]
                    for row in range(rows)
                    for column in range(columns)
                    if (row, column) not in self.occupied
                ],
            )
            self.tables.append(self.table)
            self.table = None

    def close(self):
        super().close()
        if self.table is not None or self.cell is not None:
            self.errors.append("Unclosed table/cell in official block HTML")


def read_tables(blocks):
    tables, errors = [], []
    for index, block in enumerate(blocks):
        content = block.get("content") or ""
        if "<table" not in content.lower():
            continue
        reader = TableReader()
        reader.feed(content)
        reader.close()
        errors.extend({"block_index": index, "error": err} for err in reader.errors)
        for table_index, table in enumerate(reader.tables):
            table.update(
                block_index=index,
                table_index=table_index,
                block_bbox=block.get("bbox"),
                block_angle=block.get("angle"),
                raw_pointer=f"/blocks/{index}/content/table[{table_index}]",
            )
            tables.append(table)
    return tables, errors


def locations(table, row=None, column=None):
    result = {
        "JSON_pointer": table["raw_pointer"],
        "block_index": table["block_index"],
        "bbox_normalized": table["block_bbox"],
        "angle": table["block_angle"],
    }
    if row is not None:
        result["row_zero_based"] = row
    if column is not None:
        result["column_zero_based"] = column
        cell = next(
            (cell for cell in table["cells"] if cell["row"] == row and cell["column"] == column),
            None,
        )
        if cell:
            result["HTML_line_column"] = cell["HTML_line_column"]
    return result


def matching_rows(tables, label):
    return [
        (table, row, values)
        for table in tables
        for row, values in enumerate(table["rows"])
        if values and prose(values[0]) == prose(label)
    ]


def grid_comparison(tables, expected, expected_spans=None):
    normalized = [[compact(value) for value in row] for row in expected]
    candidates = [
        table
        for table in tables
        if table["num_rows"] == len(expected) and table["num_cols"] == len(expected[0])
    ]
    compared = []
    for table in candidates:
        literal_mismatches = [
            {"row": row, "column": col, "source": value, "actual": compact(table["rows"][row][col])}
            for row, values in enumerate(normalized)
            for col, value in enumerate(values)
            if compact(table["rows"][row][col]) != value
        ]
        mismatches = [m for m in literal_mismatches if prose(m["source"]) != prose(m["actual"])]
        span_match = expected_spans is None or sorted(table["spans"]) == sorted(expected_spans)
        compared.append(
            {
                "location": locations(table),
                "mismatches": mismatches,
                "literal_character_mismatches_including_typography": literal_mismatches,
                "spans_match": span_match,
                "actual_spans": table["spans"],
                "complete_explicit_cell_or_span_coverage": table["complete_physical_coverage"],
                "uncovered_grid_positions": table["uncovered_grid_positions"],
                "literal_exact_positions": sum(map(len, expected)) - len(literal_mismatches),
                "positions_equal_under_explicit_typography": sum(map(len, expected))
                - len(mismatches),
            }
        )
    return {
        "pass": any(
            not candidate["mismatches"]
            and candidate["spans_match"]
            and candidate["complete_explicit_cell_or_span_coverage"]
            for candidate in compared
        ),
        "source_shape": [len(expected), len(expected[0])],
        "expected_spans": expected_spans,
        "actual_shapes": [[table["num_rows"], table["num_cols"]] for table in tables],
        "candidates": compared,
    }


def model_checks(stem, page, blocks, tables, reference, old_reference):
    checks = []
    block_visible = [visible(block.get("content") or "") for block in blocks]
    text = "\n".join(block_visible)
    literal_text = compact(text)
    normalized = prose(text)

    def add(name, passed, **detail):
        checks.append({"check": name, "observed_pass": bool(passed), **detail})

    def exact_text(name, expected):
        literal_expected = compact(expected)
        expected = prose(expected)
        global_start = normalized.find(expected)
        global_end = global_start + len(expected)
        found = [
            {
                "JSON_pointer": f"/blocks/{i}/content",
                "bbox_normalized": b.get("bbox"),
                "angle": b.get("angle"),
            }
            for i, b in enumerate(blocks)
            if expected in prose(block_visible[i])
        ]
        if not found and global_start >= 0:
            offset = 0
            for i, content in enumerate(block_visible):
                end = offset + len(prose(content))
                if end > global_start and offset < global_end:
                    found.append(
                        {
                            "JSON_pointer": f"/blocks/{i}/content",
                            "bbox_normalized": blocks[i].get("bbox"),
                            "angle": blocks[i].get("angle"),
                            "match_spans_adjacent_blocks": True,
                        }
                    )
                offset = end
        add(
            name,
            bool(found),
            expected=expected,
            literal_character_exact=literal_expected in literal_text,
            raw_locations=found,
        )

    def exact_note(name, label, expected, colspan=None):
        matches = matching_rows(tables, label)
        details = []
        passed = False
        for table, row, values in matches:
            payloads = [v for v in values[1:] if compact(v)]
            match = len(payloads) == 1 and prose(payloads[0]) == prose(expected)
            span = [row, 1, 1, colspan] if colspan else None
            span_match = span is None or span in table["spans"]
            passed = passed or match and span_match
            details.append(
                {
                    "location": locations(table, row, 1),
                    "actual_payloads": payloads,
                    "full_text_equal_under_explicit_typography": match,
                    "literal_character_exact": len(payloads) == 1
                    and compact(payloads[0]) == compact(expected),
                    "source_colspan_retained": span_match,
                }
            )
        add(
            name,
            passed,
            expected_label=label,
            expected_text=expected,
            expected_colspan=colspan,
            candidates=details,
        )
        return matches

    if stem == "1225474739":
        s = reference[stem]
        if page == 19:
            s = s["page19"]
            exact_note(
                "p19_entire_long_risk_cell_text_and_span",
                s["risk_label"]["text"],
                s["risk_control_merged_cell"]["text"],
                8,
            )
            tail = prose(s["risk_control_merged_cell"]["text"]).split("所有的", 1)[-1]
            add(
                "p19_previously_missing_risk_tail_present",
                tail in normalized,
                expected=tail,
                literal_character_exact=compact(s["risk_control_merged_cell"]["text"]).split(
                    "所有的", 1
                )[-1]
                in literal_text,
            )
            amount_rows = matching_rows(tables, "远期结售汇")
            amount_candidates = []
            for table, row, values in amount_rows:
                if len(values) != 9:
                    continue
                cell = next(
                    (cell for cell in table["cells"] if cell["row"] == row and cell["column"] == 7),
                    None,
                )
                if cell:
                    markup = cell["semantic_markup"]
                    # Rendering-only interpretation of explicit superscript math.
                    semantic = re.sub(
                        r"\^\{?1\}?", "<sup>1</sup>", markup.replace("¹", "<sup>1</sup>")
                    )
                    semantic = semantic.strip().strip("$").replace(r"\(", "").replace(r"\)", "")
                    amount_candidates.append(
                        {
                            "location": locations(table, row, 7),
                            "raw_cell": markup,
                            "separate_numeric_and_reference": source_verifier.amount_and_footnote(
                                semantic, s["amount"], s["footnote_reference"]
                            ),
                        }
                    )
            add(
                "p19_exact_amount_and_separate_superscript_reference",
                any(c["separate_numeric_and_reference"] for c in amount_candidates),
                expected_amount=s["amount"],
                expected_reference=s["footnote_reference"],
                candidates=amount_candidates,
            )
            rows = matching_rows(tables, "报告期实际损益情况的说明")
            add(
                "p19_exact_negative_decimal_at_actual_profit_explanation",
                any(
                    len(values) > 1 and re.search(r"(?<![\d.,])-0\.61(?![\d.])", values[1])
                    for _, _, values in rows
                ),
                candidates=[
                    {"location": locations(table, row, 1), "actual": values[1:]}
                    for table, row, values in rows
                ],
            )
        elif page == 40:
            s = s["page40"]
            notes = exact_note(
                "p40_entire_seven_item_financing_cell",
                s["financing_explanation_label"]["text"],
                s["financing_explanation_cell"]["text"],
            )
            for account in s["account_bindings"]:
                matching = [
                    {"location": locations(table, row, 1)}
                    for table, row, values in notes
                    if prose(account["raw_source_paragraph"]) in prose("".join(values[1:]))
                ]
                add(
                    f"p40_account_{account['number']}_person_credit_ordinary_total_binding",
                    bool(matching),
                    expected=account,
                    raw_locations=matching,
                )
            exact_note(
                "p40_independent_explanation_row_label_and_text",
                s["independent_explanation_label"]["text"],
                s["independent_explanation_text"]["text"],
            )
            for expected in s["shareholder_rows_4cols"]:
                actual = [
                    {
                        "location": locations(table, row),
                        "anchors": [v for v in values if compact(v)],
                    }
                    for table, row, values in matching_rows(tables, expected[0])
                ]
                add(
                    "p40_four_source_cells_" + compact(expected[0]),
                    any(
                        [compact(v) for v in candidate["anchors"]] == [compact(v) for v in expected]
                        for candidate in actual
                    ),
                    expected=expected,
                    candidates=actual,
                )
            expected = s["top_chenqingliang_9cols"]
            actual = [
                {"location": locations(table, row), "anchors": values}
                for table, row, values in matching_rows(tables, expected[0])
                if len(values) == 9
            ]
            add(
                "p40_top_chenqingliang_all_nine_cells",
                any(
                    [compact(v) for v in candidate["anchors"]] == [compact(v) for v in expected]
                    for candidate in actual
                ),
                expected=expected,
                candidates=actual,
            )
        elif page == 74:
            s = s["page74"]
            exact_text("p74_accounting_policy_heading", s["policy_heading"]["text"])
            exact_text("p74_accounting_policy_sentence", s["policy_sentence"]["text"])
            positions = [
                normalized.find(prose(s[key]["text"]))
                for key in ["policy_heading", "policy_sentence"]
            ]
            positions.append(normalized.find("研发支出的归集范围及相关会计处理方法"))
            add(
                "p74_policy_precedes_next_section_in_correct_order",
                0 <= positions[0] < positions[1] < positions[2],
                positions=positions,
            )
        elif page == 131:
            expected = [compact(v) for v in s["page130_131"]["page131_rows_raw"][1]]
            candidates = [
                {
                    "location": locations(table, row),
                    "row": values,
                    "columns": table["num_cols"],
                    "complete_explicit_cell_coverage": table["complete_physical_coverage"],
                }
                for table, row, values in matching_rows(tables, expected[0])
            ]
            add(
                "p131_six_columns_total_with_two_blanks_and_92_29_percent",
                any(
                    candidate["columns"] == 6
                    and [compact(v) for v in candidate["row"]] == expected
                    and candidate["complete_explicit_cell_coverage"]
                    for candidate in candidates
                ),
                expected=expected,
                candidates=candidates,
            )
    elif stem == "1225475375":
        s = reference[stem]
        if page == 74:
            exact_text(
                "p74_negative_business_conclusion",
                s["page74"]["negative_business_conclusion"]["text"],
            )
            expected = s["page74"]["negative_business_conclusion"]["text"]
            exact_text(
                "p74_negative_business_statement_body_restored",
                expected[1:] if expected.startswith("—") else expected,
            )
        elif page == 87:
            s = s["page87"]
            comparison = grid_comparison(tables, s["rows_raw"], s["spans"])
            add(
                "p87_exact_ninety_grid_positions_and_all_four_header_spans",
                comparison.pop("pass"),
                **comparison,
            )
            add(
                "p87_six_column_current_period_group_opening_and_closing_outside",
                any(
                    [0, 2, 1, 6] in table["spans"]
                    and table["num_cols"] == 9
                    and compact(table["rows"][0][0]) == "项目"
                    and compact(table["rows"][0][1]) == "期初余额"
                    and compact(table["rows"][0][8]) == "期末余额"
                    for table in tables
                ),
                raw_locations=[locations(table) for table in tables],
            )
            exact_text("p87_business_footnote", s["footnote"]["text"])
    elif stem == "1225474139":
        s = reference[stem]
        if page == 28:
            exact_text(
                "p28_exact_business_paragraph_reading_order",
                s["page28"]["ordered_paragraph"]["text"],
            )
        elif page == 30:
            expected = compact(s["page30"]["blank_date"]["text"])
            numeric_dates = re.findall(r"\d{2,4}年|\d{1,2}月|\d{1,2}日", normalized)
            add(
                "p30_date_field_left_blank_without_invented_numbers",
                expected in normalized and not numeric_dates,
                expected=expected,
                numeric_dates=numeric_dates,
            )
    elif stem == "1206337604":
        s = reference[stem]
        spans = s["pages"][str(page)]["nonempty_native_spans"]
        missing = [span for span in spans if prose(span["text"]) not in normalized]
        literal_missing = [span for span in spans if compact(span["text"]) not in literal_text]
        add(
            f"p{page}_independent_native_character_span_coverage",
            not missing,
            native_span_count=len(spans),
            missing_source_spans=missing,
            literal_unmatched_source_spans_including_typography=literal_missing,
            caution="Coverage only; no table/reading-order/provenance claim",
        )
        if page == 1:
            exact_text(
                "p1_visible_complete_security_identification_line", s["identity_line"]["text"]
            )
            exact_text("p1_original_document_title", s["title"]["text"])
            header, title = (
                normalized.find(prose(s["identity_line"]["text"])),
                normalized.find(prose(s["title"]["text"])),
            )
            add(
                "p1_security_identification_precedes_title",
                0 <= header < title,
                positions=[header, title],
            )
        elif page == 2:
            exact_text("p2_original_record_date", s["record_date"]["text"])
    elif stem == "1225474693":
        s = old_reference["financial_period_headers"][f"table_p{page}"]
        spans = [
            [c["row_zero_based"], c["column_zero_based"], c["rowspan"], c["colspan"]]
            for c in s["merged_physical_cells"]
        ]
        comparison = grid_comparison(tables, s["rows_raw"], spans)
        add(
            f"p{page}_original_financial_full_grid_and_header", comparison.pop("pass"), **comparison
        )
    elif stem == "1225473526":
        s = old_reference["matching_header_continuation"][f"table_p{page}"]
        spans = [
            [c["row_zero_based"], c["column_zero_based"], c["rowspan"], c["colspan"]]
            for c in s["merged_physical_cells"]
        ]
        comparison = grid_comparison(tables, s["rows_raw"], spans)
        add(
            f"p{page}_original_shareholder_continuation_source_grid",
            comparison.pop("pass"),
            **comparison,
        )
        if page == 7:
            s = old_reference["funding_merged_cell"]["source_table"]
            spans = [
                [c["row_zero_based"], c["column_zero_based"], c["rowspan"], c["colspan"]]
                for c in s["merged_physical_cells"]
            ]
            comparison = grid_comparison(tables, s["rows_raw"], spans)
            add(
                "p7_fundraising_full_grid_and_all_seven_merged_spans",
                comparison.pop("pass"),
                **comparison,
            )
    return checks


def assess_generation(page_dir):
    path = page_dir / "generation-calls.json"
    if not path.exists():
        return {
            "status": "unknown",
            "reason": "Generation termination evidence absent",
            "calls": [],
        }
    calls = json.loads(path.read_text())
    evidence = []
    for index, call in enumerate(calls):
        eos = call.get("eos_token_id")
        eos_ids = eos if isinstance(eos, list) else [eos]
        kwargs = call.get("kwargs", {})
        reached_limit = (
            isinstance(kwargs.get("max_length"), int)
            and call.get("output_tokens", 0) >= kwargs["max_length"]
            or isinstance(kwargs.get("max_new_tokens"), int)
            and call.get("generated_tokens", 0) >= kwargs["max_new_tokens"]
        )
        ended_eos = call.get("last_token_id") in eos_ids and call.get("last_token_id") is not None
        evidence.append(
            {
                "call": index,
                "input_tokens": call.get("input_tokens"),
                "generated_tokens": call.get("generated_tokens"),
                "output_tokens": call.get("output_tokens"),
                "max_length": kwargs.get("max_length"),
                "max_new_tokens": kwargs.get("max_new_tokens"),
                "last_token_id": call.get("last_token_id"),
                "eos_token_id": eos,
                "ended_with_EOS": ended_eos,
                "reached_generation_limit": bool(reached_limit),
            }
        )
    truncated = [
        call for call in evidence if call["reached_generation_limit"] and not call["ended_with_EOS"]
    ]
    unknown = [
        call
        for call in evidence
        if not call["ended_with_EOS"] and not call["reached_generation_limit"]
    ]
    return {
        "status": "generation_limit_hit"
        if truncated
        else "termination_unknown"
        if unknown
        else "all_calls_EOS",
        "limit_hit_calls": truncated,
        "unknown_termination_calls": unknown,
        "calls": evidence,
    }


def evaluate(page_dir, reference, old_reference):
    request = json.loads((page_dir / "request.json").read_text())
    blocks_path, md_path = page_dir / "official-blocks.json", page_dir / "official.md"
    blocks_data, md_data = blocks_path.read_bytes(), md_path.read_bytes()
    blocks = json.loads(blocks_data)
    stem, page = request["id"], request["page"]
    expected_sha = reference["source_documents"].get(stem, {}).get("sha256")
    if expected_sha is None:
        expected_sha = next(
            (
                s["SHA256"]
                for s in old_reference["source_documents"]
                if Path(s["path"]).stem == stem
            ),
            None,
        )
    if request["source_pdf_SHA256"] != expected_sha:
        raise ValueError(f"Source byte identity mismatch: {page_dir}")
    tables, errors = read_tables(blocks)
    termination = assess_generation(page_dir)
    checks = model_checks(stem, page, blocks, tables, reference, old_reference)
    for check in checks:
        check["status"] = (
            "pass"
            if check["observed_pass"]
            else "unknown"
            if termination["status"] != "all_calls_EOS" or errors
            else "fail"
        )
        if not check["observed_pass"] and check["status"] == "unknown":
            check["qualification"] = (
                "Observed output differs; generation termination/HTML integrity must be resolved before attributing to model capability."
            )
    return {
        "source": stem,
        "source_page": page,
        "source_SHA256": expected_sha,
        "page_dir": str(page_dir),
        "official_blocks_SHA256": sha(blocks_data),
        "official_MD_SHA256": sha(md_data),
        "official_request": request,
        "generation_integrity": termination,
        "HTML_reader_errors": errors,
        "table_shapes": [[t["num_rows"], t["num_cols"]] for t in tables],
        "checks": checks,
        "counts": {
            status: sum(check["status"] == status for check in checks)
            for status in ["pass", "fail", "unknown"]
        },
        "public_interface_source_mapping": {
            "status": "unknown",
            "reason": "Official per-page model trial, not MosaicParse HTTP; table-source and cross-page assembly not implemented or claimed.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        type=Path,
        action="append",
        required=True,
        help="Official runner output directory; repeat for separate bounded runs",
    )
    parser.add_argument("--reference", type=Path, default=HERE / "source-reference.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite evaluation evidence")
    reference = json.loads(args.reference.read_text())
    old_reference = json.loads(BASELINE_REFERENCE.read_text())
    out = {
        "schema": "mosaicparse-official-mineru-source-evaluation/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "evaluator_SHA256": sha(Path(__file__).read_bytes()),
        "reference_SHA256": sha(args.reference.read_bytes()),
        "prior_independent_reference_SHA256": sha(BASELINE_REFERENCE.read_bytes()),
        "scope": "Official per-page raw model content and explicit HTML cells/spans only; no whole-PDF HTTP/provenance or throughput equivalence claim.",
        "comparison_policy": {
            "prose_only_punctuation_width_equivalence": {
                chr(key): value for key, value in TYPOGRAPHY_EQUIVALENCE.items()
            },
            "literal_character_mismatches": "Reported separately; typography equality is never called original-character exactness.",
            "numbers_and_relations": "No digit, sign, decimal point, percentage, person/account binding, source row or span is deleted or inferred.",
            "superscript": "Explicit HTML sup, Unicode superscript 1, or latex ^1 is read as a separate reference; 6,606.571 cannot pass.",
            "source_mapping": "Only evaluation input page identity is known; no MosaicParse page/table-source output is fabricated.",
        },
        "run_manifests": [],
        "pages": [],
        "missing_or_unfinished_pages": [],
    }
    for run in args.run:
        manifest_path = run / "run-manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        out["run_manifests"].append(
            {
                "path": str(manifest_path),
                "SHA256": sha(manifest_path.read_bytes()) if manifest_path.exists() else None,
                "status": manifest.get("status"),
                "configuration": manifest,
            }
        )
        for page_dir in sorted(run.glob("*-p*")):
            if all(
                (page_dir / f).exists()
                for f in ["request.json", "official-blocks.json", "official.md"]
            ):
                out["pages"].append(evaluate(page_dir, reference, old_reference))
            else:
                out["missing_or_unfinished_pages"].append(str(page_dir))
    out["counts"] = {
        status: sum(page["counts"][status] for page in out["pages"])
        for status in ["pass", "fail", "unknown"]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "pages": len(out["pages"]),
                "counts": out["counts"],
                "missing_or_unfinished_pages": out["missing_or_unfinished_pages"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
