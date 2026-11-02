"""Trace transient targets to every visible expected text range.

This is compilation accounting, not reference validation or a second answer
file. Unconsumed wording becomes a literal content target rather than vanishing
when a field reader recognizes part of a paragraph or list item.
"""

from __future__ import annotations

import re
from typing import Any


def partition_record(target: dict[str, Any], records: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    text = target["text"]
    owners: list[set[str]] = [set() for _ in text]
    for record in records:
        for index, field in enumerate(record["table"]["fields"]):
            identifier = f"{record['id']}:field:{index}"
            literals = [*record["table"]["row_header_path"], *field["column_header_path"],
                        field.get("authored_value", field["value"])]
            for obj in (record["table"], field):
                for key in ("unit", "currency", "period", "business_scope", "note_texts", "notes"):
                    value = obj.get(key)
                    literals.extend(value if isinstance(value, list) else [value] if isinstance(value, str) else [])
            for literal in sorted(set(literals), key=len, reverse=True):
                if not literal:
                    continue
                for found in re.finditer(re.escape(literal), text):
                    for position in range(found.start(), found.end()):
                        owners[position].add(identifier)
            # These words declare the relation's type in one syntax. The
            # relation remains mandatory; its spelling need not be copied by
            # another faithful representation (for example a unit in a header).
            syntax = {"unit": "unit", "单位": "unit", "單位": "unit", "period": "period",
                      "期间": "period", "期間": "period", "currency": "currency", "币种": "currency",
                      "幣種": "currency", "note": "note_texts", "附注": "note_texts", "附註": "note_texts",
                      "scope": "printed_scopes", "范围": "printed_scopes", "範圍": "printed_scopes"}
            for match in re.finditer(r"(?<!\w)(Unit|单位|單位|Period|期间|期間|Currency|币种|幣種|Note|附注|附註|Scope|范围|範圍)\s*[:：]", text, re.I):
                key = syntax[match[1].lower()]
                if field.get(key) is not None or record["table"].get(key):
                    for position in range(match.start(), match.end()):
                        owners[position].add(identifier)
    pieces, residual = [], []
    start = 0
    while start < len(text):
        end = start + 1
        while end < len(text) and owners[end] == owners[start]:
            end += 1
        literal = text[start:end]
        requirement = bool(re.search(r"\w|[%‰−]", literal))
        role = "business_requirement" if owners[start] else "residual_text" if requirement else "format_separator"
        entry = {"span": [start, end], "literal": literal, "role": role, "target_ids": sorted(owners[start])}
        if role == "residual_text":
            identifier = f"{target['id']}:residual:{start}-{end}"
            entry["target_ids"] = [identifier]
            residual.append({"id": identifier, "reference_text": literal, "expected_kind": "record_residual_text"})
        pieces.append(entry)
        start = end
    return pieces, residual


def require_complete_ranges(coverage: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> None:
    identifiers = {row["id"] for row in outcomes}
    for element in coverage:
        cursor = 0
        for piece in element["ranges"]:
            start, end = piece["span"]
            if start != cursor or end <= start or piece["literal"] != element["text"][start:end]:
                raise ValueError("expected content compiler omitted or altered a literal range")
            if piece["role"] != "format_separator" and (not piece["target_ids"] or not set(piece["target_ids"]) <= identifiers):
                raise ValueError("expected wording or business requirement has no completed target")
            cursor = end
        if cursor != len(element["text"]):
            raise ValueError("expected content compiler left an unaccounted suffix")
