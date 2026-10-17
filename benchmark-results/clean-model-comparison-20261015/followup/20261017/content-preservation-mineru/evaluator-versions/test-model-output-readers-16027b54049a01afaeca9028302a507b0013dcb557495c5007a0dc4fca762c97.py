"""Pure in-memory adversarial tests of independent model-output readers."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def main():
    output = HERE / "model-evaluation/reader-self-tests.json"
    if output.exists():
        raise ValueError("Refusing to overwrite reader test evidence")
    evaluator = module("model_evaluator_test", "evaluate-mineru-source.py")
    audit = module("coverage_auditor_test", "audit-visible-source-spans.py")
    checks = []

    def require(name, condition):
        assert condition, name
        checks.append({"test": name, "pass": True})

    html = '<table><tr><td rowspan="2">项目</td><td colspan="2">本期</td></tr><tr><td>1.00</td><td></td></tr></table>'
    tables, errors = evaluator.read_tables(
        [{"type": "table", "bbox": [0, 0, 1, 1], "angle": 0, "content": html}]
    )
    require(
        "HTML_explicit_anchors_and_spans",
        not errors
        and tables[0]["rows"] == [["项目", "本期", ""], ["", "1.00", ""]]
        and tables[0]["spans"] == [[0, 0, 2, 1], [0, 1, 1, 2]],
    )
    require("HTML_complete_explicit_physical_coverage", tables[0]["complete_physical_coverage"])
    expected = [["项目", "本期", ""], ["", "1.00", ""]]
    require(
        "complete_source_grid_passes",
        evaluator.grid_comparison(tables, expected, [[0, 0, 2, 1], [0, 1, 1, 2]])["pass"],
    )
    incomplete = html.replace("<td>1.00</td><td></td>", "<td>1.00</td>")
    bad_tables, _ = evaluator.read_tables([{"content": incomplete}])
    require(
        "omitted_blank_cell_not_filled_as_evidence",
        not bad_tables[0]["complete_physical_coverage"]
        and not evaluator.grid_comparison(bad_tables, expected)["pass"],
    )
    wrong_spans = html.replace('colspan="2"', 'colspan="1"')
    span_tables, _ = evaluator.read_tables([{"content": wrong_spans}])
    require(
        "wrong_group_span_rejected",
        not evaluator.grid_comparison(span_tables, expected, [[0, 0, 2, 1], [0, 1, 1, 2]])["pass"],
    )
    _, unclosed = evaluator.read_tables([{"content": "<table><tr><td>unfinished"}])
    require("unclosed_HTML_reported", bool(unclosed))
    sup, _ = evaluator.read_tables(
        [{"content": "<table><tr><td>6,606.57<sup>1</sup></td></tr></table>"}]
    )
    require(
        "superscript_semantics_preserved",
        sup[0]["cells"][0]["semantic_markup"] == "6,606.57<sup>1</sup>",
    )
    require(
        "punctuation_width_equivalence_only",
        evaluator.prose("（元／股）公司－基金") == evaluator.prose("(元/股)公司-基金"),
    )
    require(
        "Chinese_identity_one_not_hyphen",
        evaluator.prose("基金一零零一") != evaluator.prose("基金-零零一"),
    )
    require("em_dash_not_Chinese_one", evaluator.prose("—公司") != evaluator.prose("一公司"))
    require("digits_never_normalized", evaluator.prose("１２") != evaluator.prose("12"))
    require(
        "negative_decimal_keeps_sign_and_point", evaluator.prose("-0.61") != evaluator.prose("061")
    )
    require(
        "pure_numeric_span_cannot_match_contamination",
        not audit.covered("6,606.57", audit.canonical("6,606.571")),
    )
    require(
        "positive_span_cannot_match_negative", not audit.covered("0.61", audit.canonical("-0.61"))
    )
    require("negative_span_exact_token", audit.covered("-0.61", audit.canonical("金额-0.61万元")))
    require(
        "negative_span_cannot_match_longer_decimal",
        not audit.covered("-0.61", audit.canonical("-0.611")),
    )
    require(
        "adjacent_HTML_numeric_cells_do_not_concatenate",
        audit.covered(
            "1.00", audit.canonical("<table><tr><td>1.00</td><td>2.00</td></tr></table>")
        ),
    )
    require(
        "cross_cell_native_text_span_can_be_covered",
        audit.covered(
            "1.00 不适用", audit.canonical("<table><tr><td>1.00</td><td>不适用</td></tr></table>")
        ),
    )
    require(
        "choice_state_kept_distinct",
        audit.choice_states(audit.canonical("□适用 ☑不适用"))
        != audit.choice_states(audit.canonical("□适用 □不适用")),
    )
    output.parent.mkdir(exist_ok=True)
    result = {
        "schema": "mosaicparse-model-reader-self-tests/1",
        "created_UTC": dt.datetime.now(dt.UTC).isoformat(),
        "scope": "Pure in-memory verifier tests; no synthetic parser results are saved or counted as model quality.",
        "scripts": {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in [
                "evaluate-mineru-source.py",
                "audit-visible-source-spans.py",
                "test-model-output-readers.py",
            ]
        },
        "pass": True,
        "test_count": len(checks),
        "tests": checks,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"pass": True, "tests": len(checks), "output": str(output)}))


if __name__ == "__main__":
    main()
