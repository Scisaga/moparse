#!/usr/bin/env python3
"""Check received full-document HTTP Markdown against frozen original-PDF gold.

This tool is read-only apart from a new JSON report. It never imports the parser,
contacts services, starts models, or repairs text. Usage:
  uv run python benchmark/tools/check_release.py --input RUN --output NEW_REPORT.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS = ROOT / "benchmark/datasets/moparse-v1/annotations"
READER_PATH = (ROOT / "benchmark/scorers/frozen/followup/20261017/"
               "content-preservation-mineru/verify-content-source.py")
GOLD_PATHS = {
    "tables": ANNOTATIONS / "full-selected-source-tables.json",
    "continuation": ANNOTATIONS / "same-header-source-gold.json",
    "content": ANNOTATIONS / "content14-source-reference.json",
}
PAGE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_reader() -> Any:
    spec = importlib.util.spec_from_file_location("moparse_release_visible_reader", READER_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load frozen public Markdown reader")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    return reader


def compact(value: object, reader: Any) -> str:
    """Compare visible characters; metadata/comments cannot supply body text."""
    return re.sub(r"\s+", "", reader.visible_markdown(str(value or "")))


def matrix(rows: list[list[Any]], reader: Any) -> list[list[str]]:
    return [[compact(cell, reader) for cell in row] for row in rows]


def fold_ascii_width(value: str) -> str:
    """Fold only fullwidth ASCII and ideographic space, never compatibility glyphs.

    NFKC would also change superscripts, Roman numerals and mathematical
    symbols, so it cannot establish that numeric content was preserved.
    """
    return "".join(chr(ord(char) - 0xFEE0) if 0xFF01 <= ord(char) <= 0xFF5E
                   else " " if char == "\u3000" else char for char in value)


def spans(source: dict[str, Any], offset: int = 0) -> list[list[int]]:
    return sorted([[cell["row"] + offset, cell["column"], cell.get("row_span", 1),
                    cell.get("column_span", 1)] for cell in source["cells"]
                   if cell.get("row_span", 1) > 1 or cell.get("column_span", 1) > 1])


def check_tables(
    tables: list[dict[str, Any]], source: dict[str, Any], reader: Any,
) -> dict[str, Any]:
    expected = matrix(source["rows"], reader)
    page = source["source_page"]
    shape = (len(expected), len(expected[0]))
    # Source page and printed shape select candidates, never financial answers.
    candidates = [table for table in tables if table["meta"].get("source_pages") == [page]
                  and len(table["rows"]) == shape[0]
                  and all(len(row) == shape[1] for row in table["rows"])]
    result: dict[str, Any] = {"source_page": page, "source_ordinal": source["source_ordinal"],
                              "matching_tables": len(candidates), "raw_surface_exact": None,
                              "width_equivalent": None, "pass": False}
    if len(candidates) != 1:
        return result
    table = candidates[0]
    actual = matrix(table["rows"], reader)
    mismatches = [{"row": r, "column": c, "expected": cell, "actual": actual[r][c]}
                  for r, row in enumerate(expected) for c, cell in enumerate(row)
                  if actual[r][c] != cell]
    width_differences = [item for item in mismatches
                         if fold_ascii_width(item["expected"]) == fold_ascii_width(item["actual"])]
    content_mismatches = [item for item in mismatches if item not in width_differences]
    meta = table["meta"]
    scope = (meta.get("structure_valid") is True
             and meta.get("encoding") == "anchor_and_blanks"
             and meta.get("num_rows") == shape[0] and meta.get("num_cols") == shape[1]
             and table["rendered_page"] == page)
    source_maps_valid = all(
        item["page"] == page and item["source_rows"] == f"1-{shape[0]}"
        and item["logical_rows"] == f"1-{shape[0]}" and item["repeated_header_rows"] == 0
        for item in table["sources"])
    expected_spans = spans(source)
    result.update(table_id=table["id"], positions=sum(map(len, expected)),
                  nonempty_source_cells=sum(bool(value) for row in expected for value in row),
                  mismatches=mismatches, raw_surface_exact=not mismatches,
                  width_equivalent=not content_mismatches,
                  width_differences=width_differences, content_mismatches=content_mismatches,
                  source_page_binding=scope,
                  actual_spans=meta.get("spans"), expected_spans=expected_spans,
                  spans_match=sorted(meta.get("spans", [])) == expected_spans,
                  source_rows_valid=source_maps_valid,
                  source_rows=table["sources"], source_binding_kind="table-structure.source_pages",
                  complete_first_header=actual[0] == expected[0],
                  width_equivalent_first_header=([fold_ascii_width(value) for value in actual[0]]
                                                 == [fold_ascii_width(value) for value in expected[0]]),
                  declared_complete_first_header=(meta.get("header_scope_complete") is True
                                                  and meta.get("header_scope_rows") == [0]))
    result["pass"] = (result["width_equivalent"] and scope and source_maps_valid
                      and result["spans_match"])
    return result


def check_continuation(
    tables: list[dict[str, Any]], sources: list[dict[str, Any]], reader: Any,
) -> dict[str, Any]:
    first, second = sorted(sources, key=lambda value: value["source_page"])
    first_rows, second_rows = matrix(first["rows"], reader), matrix(second["rows"], reader)
    if first_rows[0] != second_rows[0]:
        raise ValueError("Frozen same-header original-PDF reference has differing headers")
    expected = first_rows + second_rows[1:]
    pages = [first["source_page"], second["source_page"]]
    candidates = [table for table in tables if table["meta"].get("source_pages") == pages
                  and len(table["rows"]) == len(expected)
                  and all(len(row) == len(expected[0]) for row in table["rows"])]
    result: dict[str, Any] = {"source_pages": pages, "matching_tables": len(candidates), "pass": False}
    if len(candidates) != 1:
        return result
    table = candidates[0]
    expected_maps = [
        (pages[0], f"1-{len(first_rows)}", f"1-{len(first_rows)}", 0),
        (pages[1], f"2-{len(second_rows)}", f"{len(first_rows) + 1}-{len(expected)}", 1),
    ]
    actual_maps = [(item["page"], item["source_rows"], item["logical_rows"],
                    item["repeated_header_rows"]) for item in table["sources"]]
    expected_spans = sorted(spans(first) + spans(second, len(first_rows) - 1))
    meta = table["meta"]
    same_grid = matrix(table["rows"], reader) == expected
    # No hardcoded fragment names: adapters may use distinct table-ID prefixes.
    result.update(table_id=table["id"], exact_grid=same_grid,
                  body_positions=sum(map(len, expected[1:])),
                  source_rows=table["sources"], source_rows_match=actual_maps == expected_maps,
                  complete_header_scope=(meta.get("header_scope_complete") is True
                                         and meta.get("header_scope_rows") == [0]),
                  spans_match=sorted(meta.get("spans", [])) == expected_spans,
                  expected_spans=expected_spans,
                  source_page_binding=table["rendered_page"] == pages[0],
                  structure_valid=meta.get("structure_valid") is True,
                  no_separate_duplicate_fragment=not any(
                      other["id"] == item["fragment"] for item in table["sources"][1:]
                      for other in tables))
    result["pass"] = all(result[key] for key in (
        "exact_grid", "source_rows_match", "complete_header_scope", "spans_match",
        "source_page_binding", "structure_valid", "no_separate_duplicate_fragment"))
    return result


def capture_case(directory: Path, identifier: str, source_sha: str, page_count: int,
                 reader: Any) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    case = directory / "cases" / identifier
    path = case / "result.md"
    payload = path.read_bytes()
    summary, request = read(case / "summary.json"), read(case / "request.json")
    form = request.get("form", {})
    request_source = request.get("source")
    requested_sha = (request_source.get("sha256") if isinstance(request_source, dict)
                     else request.get("source_SHA256"))
    markers = [int(match[1]) for match in PAGE.finditer(payload.decode("utf-8"))]
    checks = {
        "completed": summary.get("status") == "completed",
        "captured_sha_matches": summary.get("MD_SHA256") == digest(path),
        "complete_page_markers": markers == list(range(1, page_count + 1)),
        "source_sha_matches": requested_sha == source_sha,
        "scan_policy_auto": form.get("scan_policy") == "auto",
        "unit_range_omitted": "unit_range" not in form
                              and request.get("unit_range_in_request") is not True,
    }
    source_path = ROOT / "pdf_sample" / f"{identifier}.pdf"
    checks["original_source_sha_matches"] = source_path.is_file() and digest(source_path) == source_sha
    proof = {"document_id": identifier, "markdown": str(path), "MD_SHA256": digest(path),
             "MD_bytes": len(payload), "source_SHA256": source_sha,
             "request_SHA256": digest(case / "request.json"),
             "capture_summary_SHA256": digest(case / "summary.json"),
             "output_stage": "received-public-HTTP-GFM", "checks": checks,
             "pass": all(checks.values())}
    content = payload.decode("utf-8")
    return proof, content, reader.public_tables(content)


def verify(directory: Path) -> dict[str, Any]:
    reader = load_reader()
    references = {name: read(path) for name, path in GOLD_PATHS.items()}
    fingerprints = {name: {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
                    for name, path in GOLD_PATHS.items()}
    table_gold = references["tables"]["tables"]
    source_specs = {
        "1225474693": (next(item["source_sha256"] for item in table_gold
                             if Path(item["document"]).stem == "1225474693"), 4),
        "1225473526": (next(item["source_sha256"] for item in table_gold
                             if Path(item["document"]).stem == "1225473526"), 27),
        "1225475375": (references["content"]["source_documents"]["1225475375"]["sha256"], 119),
    }
    result: dict[str, Any] = {"schema": "moparse-source-release-acceptance/1",
        "created_UTC": datetime.now(UTC).isoformat(), "input": str(directory),
        "gold": fingerprints, "reader_SHA256": digest(READER_PATH),
        "checker_SHA256": digest(Path(__file__)), "documents": [], "checks": {}, "errors": [],
        "unavailable_documents": [],
        "comparison_policy": {
            "raw_surface_exact": "Visible cell text with whitespace removed; original expected/actual mismatches retained",
            "width_equivalent": "Only U+FF01-U+FF5E to ASCII and U+3000 to space; no NFKC or symbol/number deletion",
            "continuation_gate": "Unchanged complete-header, grid, span and table-source assertions",
        },
        "scope": "Three complete HTTP inputs; source-confirmed financial headers, funding and continuation grids, and p87 note/table; not whole-document semantic accuracy"}
    for name in ("different_financial_headers_and_values", "funding_31_source_cells_and_spans",
                 "same_header_continuation_and_table_sources", "p87_visible_full_note_and_source_table"):
        result["checks"][name] = {"status": "unknown", "pass": None,
                                  "reason": "Required complete HTTP case is not available yet"}
    captures = {}
    for identifier, (source_sha, count) in source_specs.items():
        try:
            proof, content, tables = capture_case(directory, identifier, source_sha, count, reader)
            result["documents"].append(proof)
            if not proof["pass"]:
                result["errors"].append({"document_id": identifier, "capture_checks": proof["checks"]})
            captures[identifier] = (content, tables)
        except FileNotFoundError as error:
            result["unavailable_documents"].append({"document_id": identifier,
                                                     "status": "unknown", "reason": str(error)})
        except (OSError, ValueError, TypeError, KeyError) as error:
            result["errors"].append({"document_id": identifier, "error": str(error)})
    if "1225474693" in captures:
        _, tables = captures["1225474693"]
        financial = []
        for page, ordinal in ((2, 3), (3, 1)):
            source = next(item for item in table_gold if Path(item["document"]).stem == "1225474693"
                          and (item["source_page"], item["source_ordinal"]) == (page, ordinal))
            check = check_tables(tables, source, reader)
            # A declared complete header or complete physical printed header is
            # required; values never infer a period from their metric label.
            check["pass"] = check["pass"] and check.get("width_equivalent_first_header", False)
            financial.append(check)
        result["checks"]["different_financial_headers_and_values"] = {
            "tables": financial, "pass": all(item["pass"] for item in financial)
            and len({item.get("table_id") for item in financial}) == 2,
            "raw_surface_exact": all(item.get("raw_surface_exact") is True for item in financial),
            "width_equivalent": all(item.get("width_equivalent") is True for item in financial),
            "period_source": "complete original-PDF header rows; no metric-name inference",
            "EPS_unit": "compared as part of original row label, including 元／股"}
    if "1225473526" in captures:
        _, tables = captures["1225473526"]
        source = next(item for item in table_gold if Path(item["document"]).stem == "1225473526"
                      and (item["source_page"], item["source_ordinal"]) == (7, 2))
        funding = check_tables(tables, source, reader)
        funding["pass"] = funding["pass"] and funding.get("nonempty_source_cells") == 31
        result["checks"]["funding_31_source_cells_and_spans"] = funding
        result["checks"]["same_header_continuation_and_table_sources"] = check_continuation(
            tables, references["continuation"]["tables"], reader)
    if "1225475375" in captures:
        content, tables = captures["1225475375"]
        page = reader.pages(content).get(87, "")
        source = references["content"]["1225475375"]["page87"]
        note = compact(source["footnote"]["text"], reader)
        note_visible = note in compact(page, reader)
        candidates = [table for table in tables if table["meta"].get("source_pages") == [87]
                      and len(table["rows"]) == source["grid_rows"]
                      and all(len(row) == source["grid_columns"] for row in table["rows"])]
        expected = matrix(source["rows_raw"], reader)
        actual = matrix(candidates[0]["rows"], reader) if len(candidates) == 1 else []
        grid = len(candidates) == 1 and actual == expected
        width_grid = len(candidates) == 1 and [
            [fold_ascii_width(value) for value in row] for row in actual] == [
                [fold_ascii_width(value) for value in row] for row in expected]
        source_bound = len(candidates) == 1 and candidates[0]["rendered_page"] == 87
        spans_equal = len(candidates) == 1 and sorted(candidates[0]["meta"].get("spans", [])) == sorted(source["spans"])
        row_maps_valid = len(candidates) == 1 and all(
            item["page"] == 87 and item["source_rows"] == f"1-{source['grid_rows']}"
            and item["logical_rows"] == f"1-{source['grid_rows']}"
            and item["repeated_header_rows"] == 0 for item in candidates[0]["sources"])
        # It is a paragraph after the table in the original, so neither a
        # metadata comment nor a copied phrase inside a cell can satisfy it.
        paragraph_text = re.sub(r"(?m)^\|[^\n]*(?:\n\|[^\n]*)*", "", page)
        note_in_paragraph = note in compact(paragraph_text, reader)
        result["checks"]["p87_visible_full_note_and_source_table"] = {
            "source_page": 87, "note_visible": note_visible, "expected_note": source["footnote"]["text"],
            "matching_tables": len(candidates), "grid_exact": grid, "spans_match": spans_equal,
            "raw_surface_exact": grid, "width_equivalent": width_grid,
            "source_page_binding": source_bound, "source_rows_valid": row_maps_valid,
            "note_in_paragraph": note_in_paragraph,
            "source_rows": candidates[0]["sources"] if len(candidates) == 1 else [],
            "pass": note_visible and note_in_paragraph and width_grid and source_bound
                    and row_maps_valid and spans_equal}
    for name, check in result["checks"].items():
        if check["pass"] is None:
            continue
        check["status"] = "pass" if check["pass"] else "fail"
        if check["pass"] is False:
            result["errors"].append({"check": name, "error": "Original-source assertion failed; see check detail"})
    if any(digest(GOLD_PATHS[name]) != proof["sha256"] for name, proof in fingerprints.items()):
        raise ValueError("Frozen source gold changed during verification")
    result["pass"] = not result["errors"] and all(
        item["pass"] is True for item in result["checks"].values())
    result["status"] = "fail" if result["errors"] else "pass" if result["pass"] else "unknown"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.input / "release-acceptance.json"
    if output.exists():
        parser.error(f"Refusing to overwrite existing evidence: {output}")
    result = verify(args.input.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"pass": result["pass"], "output": str(output),
                      "checks": {name: check["pass"] for name, check in result["checks"].items()},
                      "errors": result["errors"]}, ensure_ascii=False))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
