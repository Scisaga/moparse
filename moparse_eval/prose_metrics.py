"""Character accounting for compared output, with explicit alignment limits."""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz.distance import Levenshtein

from .metrics import aggregate_text_metrics


def changed_spans(expected: str, actual: str) -> list[dict[str, Any]]:
    result = []
    for op in Levenshtein.opcodes(expected, actual):
        if op.tag == "equal":
            continue
        left, right = expected[op.src_start:op.src_end], actual[op.dest_start:op.dest_end]
        context = expected[max(0, op.src_start - 18):op.src_end + 18]
        result.append({"operation": op.tag, "expected_span": [op.src_start, op.src_end],
                       "candidate_span": [op.dest_start, op.dest_end], "expected": left, "actual": right,
                       "context": context, "sensitive": "number_or_sign" if re.search(r"\d|[+−%‰]", left + right)
                       else "negation_or_condition" if re.search(r"\bno\b|\bnot\b|unless|subject to|不|未|无|無|仅|僅|除非", context, re.I)
                       else "literal_text_or_name"})
    return result


def summarize_text(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in rows if row.get("text") and row.get("kind") != "image_alt_text"]
    located = [row for row in rows if row.get("candidate")]
    all_metrics = aggregate_text_metrics(row["text"] for row in rows)
    aligned = aggregate_text_metrics(row["text"] for row in located)
    total = all_metrics["strict"]["reference_chars"]
    aligned_chars = aligned["strict"]["reference_chars"]
    preserved = sum(row["text"]["strict"]["reference_chars"] - row["text"]["strict"]["deletions"]
                    - row["text"]["strict"]["substitutions"] for row in rows)
    return {"targets": len(rows), "located_targets": len(located), "missing_targets": len(rows) - len(located),
            "location_coverage": len(located) / len(rows) if rows else None,
            "reference_characters": total, "aligned_reference_characters": aligned_chars,
            "character_location_coverage": aligned_chars / total if total else None,
            "preserved_characters": preserved, "character_preservation": preserved / total if total else None,
            "aligned_strict_cer": aligned["strict"]["cer"], "aligned": aligned,
            "target_cer_missing_as_deletion_diagnostic": all_metrics,
            "width_equivalent_exact_paragraphs_diagnostic": sum(row["text"]["width_equivalent"]["distance"] == 0 for row in rows),
            "duplicate_occurrences_diagnostic": sum(max(0, row.get("distinct_occurrences", 1) - 1) for row in rows),
            "meaning": "located range CER; missing references counted as deletions only in explicitly named diagnostic"}
