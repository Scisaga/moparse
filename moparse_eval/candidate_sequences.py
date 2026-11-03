"""Faithful readback of repeated identifier/description text pairs.

These are candidate-only printed sequences. No dictionary, expected answer,
PDF, coordinates or other pipeline supplies a description or association.
"""

from __future__ import annotations

import re

from .representations import visible_text

_IDENTIFIER = re.compile(r"(?=.*\d)[A-Za-z0-9][A-Za-z0-9._/\-]{0,79}")
_TEXT = {"text", "paragraph", "list", "list_item"}


def read_compound_measurement_labels(cells, header_rows):
    """Read a compound metric key beside its separate actual value cell.

    A colon inside a row key is not a label/value assertion when its final
    component is a metric and the two-column source pairs it with a value.
    Values, including empty or wrong values, are copied without correction.
    """
    from .expected_readback import _IDENTITY
    from .information_reading import _SCALAR, metric_units
    from .metrics import normalize_text

    grid = [cell for cell in cells if type(cell.get("row")) is int and type(cell.get("col")) is int]
    if not grid or {
        col for cell in grid for col in range(cell["col"], cell["col"] + cell.get("col_span", 1))
    } != {0, 1}:
        return [], set()

    def metric_label(text):
        return bool(
            metric_units(text)
            or re.search(
                r"金额|金額|收入|成本|余额|餘額|数量|數量|计数|計數|\b(?:count|amount|revenue|balance|cost|rate|ratio|total)\b",
                text,
                re.I,
            )
        )

    paired_metric_rows = 0
    for row in {cell["row"] for cell in grid} - header_rows:
        band = sorted([cell for cell in grid if cell["row"] == row], key=lambda cell: cell["col"])
        if (
            len(band) == 2
            and all(cell.get("row_span", 1) == cell.get("col_span", 1) == 1 for cell in band)
            and metric_label(str(band[0].get("text", "")).split(":")[-1].split("：")[-1])
            and _SCALAR.fullmatch(normalize_text(str(band[1].get("text", ""))).strip())
        ):
            paired_metric_rows += 1
    additions, label_ids = [], set()
    for label in grid:
        if (
            label["col"] != 0
            or label["row"] in header_rows
            or label.get("is_column_header")
            or label.get("native_header_tag")
            and label.get("is_row_header") is not True
        ):
            continue
        band = [cell for cell in grid if cell["row"] == label["row"]]
        if len(band) != 2 or any(
            cell.get("row_span", 1) != 1 or cell.get("col_span", 1) != 1 for cell in band
        ):
            continue
        value = next((cell for cell in band if cell["col"] == 1), None)
        labels = [part.strip() for part in re.split(r"[:：]", str(label.get("text", "")))]
        if (
            value is None
            or len(labels) != 2
            or not all(labels)
            or _IDENTITY.fullmatch(labels[0])
            or re.fullmatch(
                r"单位|單位|Units?|币种|幣種|Currency|期间|期間|Period|日期|Date", labels[0], re.I
            )
            or any(len(part) > 80 or re.search(r"[。;；!?！？\n]", part) for part in labels)
            or not metric_label(labels[-1])
        ):
            continue
        literal_value = normalize_text(str(value.get("text", ""))).strip()
        if literal_value and not _SCALAR.fullmatch(literal_value) and paired_metric_rows < 2:
            continue
        proof = {
            "method": "compound_metric_key_with_separate_value_cell",
            "label_cell": label["id"],
            "label_literal": label["text"],
            "value_cell": value["id"],
            "value_literal": value.get("text", ""),
            "paired_metric_rows": paired_metric_rows,
        }
        label_ids.add(label["id"])
        base = {
            **value,
            "id": str(value["id"]) + ":compound_metric_value",
            "row_header_path": labels[:-1],
            "column_header_path": labels[-1:],
            "readback_evidence": proof,
            "native_path": value.get("native_path", value["id"]),
        }
        additions.extend(
            [
                base,
                {
                    **base,
                    "id": str(value["id"]) + ":compound_named_value",
                    "row_header_path": labels,
                    "column_header_path": [],
                    "named_value": True,
                },
            ]
        )
    return additions, label_ids


def read_colon_value_pairs(observation):
    """Read a short printed label and its immediately following literal."""
    for page in observation.get("pages", []):
        blocks = [
            block
            for block in page.get("blocks", [])
            if block.get("kind") != "text_record"
            and (
                block.get("kind") not in _TEXT
                or block.get("cells")
                or str(block.get("text", "")).strip()
            )
        ]
        additions = []
        for label, value in zip(blocks, blocks[1:], strict=False):
            if any(
                block.get("kind") not in _TEXT or block.get("cells") for block in (label, value)
            ):
                continue
            left = visible_text(
                str(label.get("text", "")), label.get("text_format", "plain")
            ).strip()
            visible_value = visible_text(
                str(value.get("text", "")), value.get("text_format", "plain")
            )
            right = visible_value.strip()
            match = re.fullmatch(r"([^:：\n]{1,80})[:：]", left)
            if (
                not match
                or not re.search(r"[A-Za-z\u3400-\u9fff]", match[1])
                or not right
                or len(right) > 160
                or "\n" in right
                or re.search(r"[。!?！？;；]|(?<!\d)\.$", right)
                or re.search(r"[:：]", right)
                or label.get("information_following_literal")
            ):
                continue
            start = len(visible_value) - len(visible_value.lstrip())
            span = [start, start + len(right)]
            proof = {
                "method": "printed_colon_and_immediate_literal",
                "label_id": label["id"],
                "label_text": match[1],
                "value_id": value["id"],
                "value_span": span,
            }
            label["information_following_literal"] = proof
            identifier = str(value["id"]) + ":colon_owned_value"
            additions.append(
                {
                    "id": identifier + ":record",
                    "kind": "text_record",
                    "text": "",
                    "cells": [
                        {
                            "id": identifier,
                            "text": right,
                            "row_header_path": [match[1]],
                            "column_header_path": [],
                            "named_value": True,
                            "native_path": value.get("native_path", value["id"]),
                            "provenance_pages": value.get("provenance_pages") or [page.get("page")],
                            "information_source_block": value["id"],
                            "information_source_span": span,
                            "information_sequence_readback": proof,
                        }
                    ],
                }
            )
        page["blocks"].extend(additions)


def read_identifier_descriptions(observation):
    for page in observation.get("pages", []):
        stream = [block for block in page.get("blocks", []) if block.get("kind") != "text_record"]
        stream = [
            block
            for block in stream
            if block.get("kind") not in _TEXT
            or str(block.get("text", "")).strip()
            or block.get("cells")
        ]
        expanded = []
        for block in stream:
            if block.get("kind") not in _TEXT or block.get("cells"):
                expanded.append(block)
                continue
            raw = str(block.get("text", ""))
            visible = visible_text(raw, block.get("text_format", "plain"))
            lines = visible.splitlines(keepends=True)
            nonempty = [line.strip() for line in lines if line.strip()]
            if (
                block.get("kind") in _TEXT
                and not block.get("cells")
                and len(nonempty) >= 4
                and len(nonempty) % 2 == 0
                and all(_IDENTIFIER.fullmatch(line) for line in nonempty[::2])
                and not re.search(r"(?m)^\s*#{1,6}\s+", raw)
            ):
                offset = 0
                for line in lines:
                    literal = line.strip()
                    if literal:
                        start = offset + len(line) - len(line.lstrip())
                        expanded.append(
                            {
                                **block,
                                "id": str(block.get("id")) + f":line:{start}",
                                "text": literal,
                                "text_format": "plain",
                                "sequence_source_block": block.get("id"),
                                "sequence_source_span": [start, start + len(literal)],
                            }
                        )
                    offset += len(line)
            else:
                expanded.append(block)
        stream = expanded

        def text(block):
            if block.get("kind") not in _TEXT or block.get("cells"):
                return None
            return visible_text(
                str(block.get("text", "")), block.get("text_format", "plain")
            ).strip()

        additions = []
        index = 0
        while index + 3 < len(stream):
            pairs = []
            cursor = index
            while cursor + 1 < len(stream):
                label, value = stream[cursor : cursor + 2]
                name, description = text(label), text(value)
                if (
                    not name
                    or not _IDENTIFIER.fullmatch(name)
                    or not description
                    or len(description) > 512
                    or _IDENTIFIER.fullmatch(description)
                    or not re.search(r"[A-Za-z\u3400-\u9fff]", description)
                ):
                    break
                pairs.append((label, name, value, description))
                cursor += 2
            if len(pairs) < 2:
                index += 1
                continue
            source_pairs = [
                [label.get("id"), value.get("id")] for label, _name, value, _description in pairs
            ]
            for label, name, value, description in pairs:
                identity = str(value.get("id")) + ":identifier_description"
                cell = {
                    "id": identity,
                    "text": description,
                    "row_header_path": [name],
                    "column_header_path": [],
                    "named_value": True,
                    "native_path": value.get("native_path", value.get("id")),
                    "provenance_pages": value.get("provenance_pages") or [page.get("page")],
                    "information_source_block": value.get("sequence_source_block", value.get("id")),
                    "information_source_span": value.get(
                        "sequence_source_span", [0, len(description)]
                    ),
                    "information_sequence_readback": {
                        "method": "repeated_identifier_description_pairs",
                        "label_id": label.get("id"),
                        "label_text": name,
                        "value_id": value.get("id"),
                        "source_pairs": source_pairs,
                        "label_source_block": label.get("sequence_source_block", label.get("id")),
                        "label_span": label.get("sequence_source_span", [0, len(name)]),
                        "value_source_block": value.get("sequence_source_block", value.get("id")),
                        "value_span": value.get("sequence_source_span", [0, len(description)]),
                    },
                }
                additions.append(
                    {"id": identity + ":record", "kind": "text_record", "text": "", "cells": [cell]}
                )
            index = cursor
        page["blocks"].extend(additions)
