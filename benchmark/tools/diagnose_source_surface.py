"""Inspect original table surfaces and logical provenance without rescoring.

Only fullwidth ASCII U+FF01..U+FF5E and U+3000 are folded, exactly as in
check_release's existing financial/funding comparison. Original strict results
remain separate. This tool neither repairs output nor issues a release verdict.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from benchmark.tools import check_release as frozen_release


def compare_grid(actual: list[list[str]], expected: list[list[str]]) -> dict:
    same_shape = len(actual) == len(expected) and all(
        len(left) == len(right) for left, right in zip(actual, expected, strict=False)
    )
    differences = []
    if same_shape:
        for row, source_row in enumerate(expected):
            for column, source in enumerate(source_row):
                observed = actual[row][column]
                if source != observed:
                    differences.append(
                        {
                            "row": row,
                            "column": column,
                            "source": source,
                            "actual": observed,
                            "ASCII_width_only": frozen_release.fold_ascii_width(source)
                            == frozen_release.fold_ascii_width(observed),
                        }
                    )
    return {
        "same_shape": same_shape,
        "raw_exact": same_shape and not differences,
        "ASCII_width_equivalent": same_shape
        and all(item["ASCII_width_only"] for item in differences),
        "raw_differences": differences,
        "non_width_differences": [item for item in differences if not item["ASCII_width_only"]],
    }


def continuation_diagnostic(tables: list[dict], sources: list[dict], reader) -> dict:
    first, second = sorted(sources, key=lambda item: item["source_page"])
    first_rows = frozen_release.matrix(first["rows"], reader)
    second_rows = frozen_release.matrix(second["rows"], reader)
    if first_rows[0] != second_rows[0]:
        raise ValueError("Source reference does not prove equal complete repeated headers")
    expected = first_rows + second_rows[1:]
    pages = [first["source_page"], second["source_page"]]
    combined = [
        table
        for table in tables
        if table["meta"].get("source_pages") == pages
        and len(table["rows"]) == len(expected)
        and all(len(row) == len(expected[0]) for row in table["rows"])
    ]
    fragments = []
    for source, original_rows in ((first, first_rows), (second, second_rows)):
        matches = [
            table
            for table in tables
            if table["meta"].get("source_pages") == [source["source_page"]]
            and len(table["rows"]) == len(original_rows)
            and all(len(row) == len(original_rows[0]) for row in table["rows"])
        ]
        detail = {"source_page": source["source_page"], "matching_fragments": len(matches)}
        if len(matches) == 1:
            table = matches[0]
            detail.update(
                table_id=table["id"],
                surface=compare_grid(frozen_release.matrix(table["rows"], reader), original_rows),
                spans_match=sorted(table["meta"].get("spans", [])) == frozen_release.spans(source),
            )
        fragments.append(detail)
    result = {
        "source_pages": pages,
        "source_complete_headers_exactly_equal": True,
        "separate_fragments": fragments,
        "matching_logical_tables": len(combined),
        "logical_merge_observed": len(combined) == 1,
        "functional_merge_and_source_maps": False,
        "ASCII_width_equivalent_complete_continuation": False,
        "strict_original_checker": frozen_release.check_continuation(tables, sources, reader),
        "units": {
            "in_grid_units_and_all_other_text": "Included in every full-grid cell comparison",
            "external_unit_caption": "unknown_no_separate_source_annotation",
            "period_or_unit_inferred_from_row_names": False,
        },
    }
    if len(combined) != 1:
        return result
    table = combined[0]
    meta = table["meta"]
    expected_maps = [
        (pages[0], f"1-{len(first_rows)}", f"1-{len(first_rows)}", 0),
        (pages[1], f"2-{len(second_rows)}", f"{len(first_rows) + 1}-{len(expected)}", 1),
    ]
    actual_maps = [
        (item["page"], item["source_rows"], item["logical_rows"], item["repeated_header_rows"])
        for item in table["sources"]
    ]
    surface = compare_grid(frozen_release.matrix(table["rows"], reader), expected)
    expected_spans = sorted(
        frozen_release.spans(first) + frozen_release.spans(second, len(first_rows) - 1)
    )
    checks = {
        "structure_valid": meta.get("structure_valid") is True,
        "complete_header_scope": meta.get("header_scope_complete") is True
        and meta.get("header_scope_rows") == [0],
        "source_and_logical_rows_match": actual_maps == expected_maps,
        "repeated_header_skip_matches": [item[3] for item in actual_maps] == [0, 1],
        "merged_spans_match": sorted(meta.get("spans", [])) == expected_spans,
        "rendered_on_first_source_page": table["rendered_page"] == pages[0],
        "no_separate_duplicate_fragment": not any(
            other["id"] == item["fragment"] for item in table["sources"][1:] for other in tables
        ),
    }
    header = compare_grid([frozen_release.matrix(table["rows"], reader)[0]], [first_rows[0]])
    result.update(
        table_id=table["id"],
        complete_grid_surface=surface,
        complete_header_surface=header,
        source_and_logical_row_maps=table["sources"],
        expected_source_and_logical_row_maps=expected_maps,
        structural_checks=checks,
        functional_merge_and_source_maps=all(checks.values()),
        ASCII_width_equivalent_complete_continuation=all(checks.values())
        and surface["ASCII_width_equivalent"]
        and header["ASCII_width_equivalent"],
    )
    return result


def diagnose(directory: Path) -> dict:
    reader = frozen_release.load_reader()
    gold = {name: frozen_release.read(path) for name, path in frozen_release.GOLD_PATHS.items()}
    fingerprints = {
        name: {
            "path": str(path.relative_to(frozen_release.ROOT)),
            "sha256": frozen_release.digest(path),
        }
        for name, path in frozen_release.GOLD_PATHS.items()
    }
    references = gold["tables"]["tables"]
    result = {
        "schema": "moparse-source-surface-diagnostic/1",
        "created_at": datetime.now(UTC).isoformat(),
        "input": str(directory),
        "tool_SHA256": frozen_release.digest(Path(__file__)),
        "original_checker_SHA256": frozen_release.digest(Path(frozen_release.__file__)),
        "gold": fingerprints,
        "policy": {
            "ASCII_width_mapping": "U+FF01..U+FF5E to ASCII; U+3000 to space only",
            "NFKC": False,
            "digits_signs_separators_or_symbols_deleted": False,
            "strict_scores_or_release_conclusion_changed": False,
            "output_or_gold_changed": False,
            "release_verdict": False,
        },
        "captures": [],
        "financial": [],
        "funding": None,
        "continuation": None,
    }
    captured = {}
    for identifier, count in (("1225474693", 4), ("1225473526", 27)):
        source = next(item for item in references if Path(item["document"]).stem == identifier)
        proof, _, tables = frozen_release.capture_case(
            directory, identifier, source["source_sha256"], count, reader
        )
        result["captures"].append(proof)
        captured[identifier] = tables
    for page, ordinal in ((2, 3), (3, 1)):
        source = next(
            item
            for item in references
            if Path(item["document"]).stem == "1225474693"
            and (item["source_page"], item["source_ordinal"]) == (page, ordinal)
        )
        result["financial"].append(
            frozen_release.check_tables(captured["1225474693"], source, reader)
        )
    source = next(
        item
        for item in references
        if Path(item["document"]).stem == "1225473526"
        and (item["source_page"], item["source_ordinal"]) == (7, 2)
    )
    result["funding"] = frozen_release.check_tables(captured["1225473526"], source, reader)
    result["continuation"] = continuation_diagnostic(
        captured["1225473526"], gold["continuation"]["tables"], reader
    )
    for name, path in frozen_release.GOLD_PATHS.items():
        if frozen_release.digest(path) != fingerprints[name]["sha256"]:
            raise ValueError("Source gold changed while diagnosing")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new diagnostic file; prior evidence is immutable")
    result = diagnose(args.input.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "logical_merge_observed": result["continuation"]["logical_merge_observed"],
                "functional_merge_and_source_maps": result["continuation"][
                    "functional_merge_and_source_maps"
                ],
                "strict_continuation_pass": result["continuation"]["strict_original_checker"][
                    "pass"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
