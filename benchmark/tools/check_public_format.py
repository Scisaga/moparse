"""Inspect captured Markdown for visible HTML table leakage, without inference.

This supplementary contract check leaves the frozen source scorer and original
production checker unchanged. Literal code fences and comments do not render as
HTML tables; the original strict substring observation is retained separately.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from benchmark import moparse_benchmark as bench
from markdown_it import MarkdownIt

TAG = re.compile(r"<\s*(table|thead|tbody|tfoot|tr|td|th)(?=[\s/>])", re.IGNORECASE)
COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)


def html_table_leaks(markdown: str) -> list[dict]:
    """Return rendered HTML table tags; preserve exact input and byte identity."""
    result = []
    for token in MarkdownIt("commonmark", {"html": True}).parse(markdown):
        candidates = [token] if token.type == "html_block" else token.children or []
        for child in candidates:
            if child.type not in {"html_block", "html_inline"}:
                continue
            content = COMMENTS.sub("", child.content)
            matches = list(TAG.finditer(content))
            if matches:
                result.append(
                    {
                        "line": token.map[0] + 1 if token.map else None,
                        "tag_count": len(matches),
                        "tags": sorted({match[1].lower() for match in matches}),
                        "HTML_SHA256": hashlib.sha256(child.content.encode("utf-8")).hexdigest(),
                    }
                )
    return result


def check(capture: Path) -> dict:
    run = bench.read(capture / "run.json")
    documents = []
    for case in run["cases"]:
        path = capture / "cases" / case["id"] / "result.md"
        if not path.is_file():
            documents.append(
                {"id": case["id"], "pass": False, "status": "unknown_missing_MD"}
            )
            continue
        if bench.digest(path) != case.get("MD_SHA256"):
            raise ValueError("Captured Markdown SHA differs from immutable receipt")
        content = path.read_bytes().decode("utf-8")
        leaks = html_table_leaks(content)
        transport = case.get("capture_status", case["status"]) == "completed"
        documents.append(
            {
                "id": case["id"],
                "actual_API_status": case["status"],
                "capture_status": case.get("capture_status"),
                "Markdown": bench.artifact(path),
                "pass": transport and not leaks,
                "visible_HTML_leaks": leaks,
                "original_strict_table_substring_absent": re.search(
                    r"<table\b", content, re.IGNORECASE
                )
                is None,
            }
        )
    return {
        "schema": "moparse-captured-public-format-observation/1",
        "created_at": bench.utc(),
        "run": bench.artifact(capture / "run.json"),
        "documents": documents,
        "pass": bool(documents) and all(item["pass"] for item in documents),
        "scope": "Rendered HTML table leakage only, not source cell accuracy or semantic completeness",
        "frozen_gold_reader_or_production_checker_changed": False,
        "new_inference_API_or_service_operations": False,
        "source_literal_code_fences_and_comments_not_rendered_as_HTML": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.input.resolve())
    bench.save(args.output, result)
    print(bench.json.dumps({"pass": result["pass"], "documents": len(result["documents"])}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
