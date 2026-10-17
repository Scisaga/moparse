"""Small decoding tests for the independent official-output acceptance reader."""

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite verifier evidence")
    spec = importlib.util.spec_from_file_location(
        "test_native_reader", HERE / "evaluate-native-mineru-source.py"
    )
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    checks = []

    def require(name, condition):
        assert condition, name
        checks.append({"test": name, "pass": True})

    tables, errors = reader.markdown_tables(
        "| 项目 | 金额 | 空 |\n| --- | --- | --- |\n| A | -0.61 | |\n", "test-only"
    )
    require(
        "GFM_explicit_empty_cell_and_sign",
        not errors and tables[0]["rows"] == [["项目", "金额", "空"], ["A", "-0.61", ""]],
    )
    require("GFM_no_inferred_spans", tables[0]["spans"] == [])
    tables, errors = reader.markdown_tables(
        '<table><tr><td rowspan="2">A</td><td>6,606.57<sup>1</sup></td></tr><tr><td></td></tr></table>\n',
        "test-only",
    )
    require("HTML_span_retained", not errors and tables[0]["spans"] == [[0, 0, 2, 1]])
    require(
        "HTML_superscript_not_decimal",
        tables[0]["cells"][1]["semantic_markup"] == "6,606.57<sup>1</sup>",
    )
    require(
        "HTML_explicit_blank_grid_position",
        tables[0]["rows"] == [["A", "6,606.571"], ["", ""]]
        and tables[0]["complete_physical_coverage"],
    )
    _, errors = reader.markdown_tables(
        '<table><tr><td colspan=\\"2\\">A</td></tr></table>\n', "test-only"
    )
    require("literal_backslash_quote_attributes_rejected", bool(errors))
    raw = {
        "pages": [
            [
                {
                    "type": "header",
                    "content": [
                        {"type": "text", "content": "证券代码"},
                        {"type": "text", "content": ":300635"},
                    ],
                },
                {
                    "type": "table",
                    "content": "<table><tr><td>A</td></tr></table>",
                    "image_base64": "MUST_NEVER_BECOME_BODY",
                },
            ]
        ]
    }
    blocks, tables, errors = reader.raw_blocks(raw, "test-only.json")
    require("raw_inline_text_order", blocks[0]["content"] == "证券代码:300635")
    require(
        "raw_image_base64_excluded_from_body", all("MUST_NEVER" not in b["content"] for b in blocks)
    )
    require(
        "raw_table_actual_pointer", tables[0]["raw_pointer"] == "test-only.json#/pages/0/1/content"
    )
    result = {
        "schema": "mosaicparse-native-reader-self-tests/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "scope": "Pure in-memory decoding tests; no synthetic parser results saved or counted as quality.",
        "scripts": {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in [
                "evaluate-native-mineru-source.py",
                "evaluate-mineru-source.py",
                "test-native-output-reader.py",
            ]
        },
        "pass": True,
        "test_count": len(checks),
        "tests": checks,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"pass": True, "tests": len(checks), "output": str(args.output)}))


if __name__ == "__main__":
    main()
