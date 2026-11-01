"""Common binary output grading against a transient read-only expected view."""

from __future__ import annotations

import copy
import re
from collections import Counter
from typing import Any

from .expected_readback import ExpectedReadError, _field, qualify_reference_record
from .matching import (
    _normalized_positions,
    _whole_numeric_span,
    in_page_scope,
    match_units,
    observation_candidates,
)
from .metrics import normalize_text, text_metrics
from .scoring import _required_qualifiers, _score_records

PROTOCOL = {
    "id": "mo-parse-expected-only-v1", "reference": "canonical_expected_read_only",
    "scope": "existing_authored_source_map_selected_content",
    "grades": ["correct", "incorrect"], "legacy_adjudications": "not_consumed",
    "field_locator": "complete_business_labels_before_value_comparison",
    "text_policy": "mo-parse-eval-text-v1", "reader_failure": "repair_before_publication",
    "field_content_equivalence": "declared_width_spacing_scoped_scalar_units_year_range_dash_terminal_prose_punctuation",
    "qualifier_reading": "candidate_only_explicit_table_record_caption_and_note_scopes",
    "output_reading": "native_fields_or_actual_public_markdown_without_private_ir_credit",
    "reader_revision": "canonical_expected_6",
}


def _table_records(target: dict[str, Any]) -> list[dict[str, Any]]:
    """Read explicit authored table headers, never manufacturing a first row."""
    cells = target["cells"]
    headers = [c for c in cells if c.get("is_column_header") is True and c["text"].strip()]
    if not headers:
        return []
    header_rows = {c["row"] for c in headers}
    rows = sorted({c["row"] for c in cells} - header_rows)
    result = []
    for row in rows:
        band = [c for c in cells if c["row"] == row]
        subject = next((c for c in band if c["col"] == 0 and c["text"].strip()), None)
        if subject is None:
            continue
        fields = []
        for cell in band:
            if cell is subject:
                continue
            labels = [c["text"] for c in headers if c["col"] <= cell["col"] < c["col"] + c.get("col_span", 1)]
            if not labels:
                raise ExpectedReadError("expected table field has no explicitly expressed column label")
            fields.append(_field(" / ".join(labels), cell["text"]))
        if fields:
            parsed = {"id": target["id"], "row_header_path": [subject["text"]], "fields": fields}
            context = target.get("reference_context", {})
            qualify_reference_record(parsed, context.get("units", []), context.get("periods", []), context.get("currencies", []))
            result.append({**target, "id": f"{target['id']}:row:{row}",
                           "record": parsed})
    return result


def _prepared(expected: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    texts, records = [], []
    for target in expected["targets"]:
        source = {"id": target["id"], "kind": "text", "pages": target["pages"],
                  "source_element_id": target["id"],
                  "reference_text": target["text"], "reference": target["reference"],
                  "expected_context": target["context"], "expected_kind": target["kind"]}
        if target.get("record"):
            table = copy.deepcopy(target["record"])
            if not table["fields"]:
                raise ExpectedReadError("an expected record was read without its required fields")
            table.setdefault("id", f"expected:list:{target['list_span']}" if target.get("list_span")
                             else " / ".join(target["context"]) or "expected-records")
            records.append({**source, "kind": "table_record", "table": table,
                            "reference_text": table["row_header_path"][-1]})
        elif target.get("cells"):
            table_rows = _table_records(target)
            for row in table_rows:
                records.append({**source, "id": row["id"], "kind": "table_record", "table": row["record"],
                                "reference_text": row["record"]["row_header_path"][-1]})
            covered_rows = {int(row["id"].rsplit(":", 1)[1]) for row in table_rows}
            # Values already have business-field targets. Keep table labels
            # and unbound prose as visible-content targets without inventing
            # header semantics for a first row with no declared header role.
            for i, cell in enumerate(target["cells"]):
                if cell["row"] in covered_rows and cell["col"] > 0:
                    continue
                if cell["text"].strip():
                    texts.append({**source, "id": f"{source['id']}:cell:{i}", "reference_text": cell["text"],
                                  "expected_kind": "table_cell_text"})
        elif source["reference_text"]:
            texts.append(source)
    # Distinct authored headings can distinguish otherwise identical business
    # labels. Read that requirement before any candidate or value is examined.
    scopes: dict[tuple, set[str]] = {}
    for record in records:
        heading = record["expected_context"][-1] if record["expected_context"] else ""
        for field in record["table"]["fields"]:
            key = tuple(record["table"]["row_header_path"][-1:]), tuple(field["column_header_path"])
            scopes.setdefault(key, set()).add(heading)
    for record in records:
        heading = record["expected_context"][-1] if record["expected_context"] else ""
        for field in record["table"]["fields"]:
            # A shorter target path can also match a same-named child in
            # another table. Different parent paths do not remove the need
            # for the explicitly authored table scope in that case.
            key = tuple(record["table"]["row_header_path"][-1:]), tuple(field["column_header_path"])
            if heading and (len(scopes[key]) > 1 or re.match(r"^(?:附表|图表|圖表|表|Table)\s*\d", heading, re.I)):
                field["business_scope"] = heading
    return texts, records


def grade_expected(expected: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """Grade every target using one shared policy, with no pipeline branches."""
    if expected["sample_id"] != observation.get("sample_id"):
        raise ValueError("expected and candidate sample identities differ")
    if observation.get("scoring_readback", {}).get("native_status") == "readback_error":
        raise ValueError("candidate reader failed; repair it before grading")
    texts, records = _prepared(expected)
    matching = match_units(records, observation, threshold=0.8, collapse_whitespace=True)
    text_matching = match_units(texts, observation, threshold=0.8, collapse_whitespace=True)
    visible = [(item, *_normalized_positions(item["text"], True)) for item in observation_candidates(observation)]
    record_rows, record_metrics = _score_records(records, observation, True, matching)
    outcomes = []
    for target in texts:
        match = text_matching["matches"].get(target["id"])
        wanted = normalize_text(target["reference_text"], collapse_whitespace=True)
        # Repeated headings/labels still preserve their literal content. Their
        # business ownership is graded independently by complete record paths.
        if not match and wanted:
            exact = [(item, text.index(wanted), positions) for item, text, positions in visible if wanted in text
                     and in_page_scope(item, set(target["pages"]))
                     and (not wanted.replace(",", "").replace(".", "").isdigit()
                          or _whole_numeric_span(text, text.index(wanted), text.index(wanted) + len(wanted)))]
            if exact:
                item, start, positions = exact[0]
                raw_start, raw_end = positions[start][0], positions[start + len(wanted) - 1][1]
                match = {"candidate_id": item["id"], "native_path": item.get("native_path"),
                         "hypothesis": item["text"][raw_start:raw_end], "span": [raw_start, raw_end],
                         "normalized_span": [start, start + len(wanted)],
                         "method": "complete_visible_literal_presence", "matching_occurrences": len(exact)}
        actual = match["hypothesis"] if match else ""
        correct = bool(match and normalize_text(target["reference_text"], collapse_whitespace=True)
                       == normalize_text(actual, collapse_whitespace=True))
        outcomes.append({"id": target["id"], "kind": target["expected_kind"],
                         "source_element_id": target["source_element_id"],
                         "reference": target["reference"], "expected": target["reference_text"],
                         "context": target["expected_context"], "outcome": "correct" if correct else "incorrect",
                         "reason": "complete_visible_text" if correct else "text_missing_or_different",
                         "candidate": match, "actual": actual,
                         "text": text_metrics(target["reference_text"], actual, collapse_whitespace=True)})
    by_id = {record["id"]: record for record in records}
    for row in record_rows:
        target = by_id[row["id"]]
        for field in row["fields"]:
            if field.get("outcome") not in {"correct", "incorrect"}:
                raise ValueError("shared business reader has not produced a binary decision")
            index = field["index"]
            expected_field = target["table"]["fields"][index]
            outcomes.append({"id": f"{row['id']}:field:{index}", "kind": "business_field",
                             "source_element_id": target["source_element_id"],
                             "reference": target["reference"],
                             "expected": {**expected_field, "required": _required_qualifiers(target["table"], expected_field)},
                             "row_header_path": target["table"]["row_header_path"],
                             "context": target["expected_context"], "outcome": field["outcome"],
                             "reason": field.get("information", {}).get("reason") or field.get("reason"),
                             "actual": field.get("native_text"),
                             "raw_value_text": None if expected_field.get("reference_blank") else text_metrics(
                                 expected_field["value"], field.get("native_text") or "", collapse_whitespace=True),
                             "candidate": field})
    counts = Counter(item["outcome"] for item in outcomes)
    content_elements = {t["id"] for t in expected["targets"] if t["text"].strip()
                        or any(cell["text"].strip() for cell in t.get("cells", []))}
    represented = {row["source_element_id"] for row in outcomes}
    if content_elements - represented:
        raise ExpectedReadError("expected content was omitted by the scoring compiler; repair before publication")
    by_kind = {}
    for kind in sorted({item["kind"] for item in outcomes}):
        members = [item for item in outcomes if item["kind"] == kind]
        by_kind[kind] = {"targets": len(members), "correct": sum(x["outcome"] == "correct" for x in members),
                         "incorrect": sum(x["outcome"] == "incorrect" for x in members)}
    if len({item["id"] for item in outcomes}) != len(outcomes):
        raise ValueError("duplicate expected target identities")
    return {"sample_id": expected["sample_id"], "document_id": expected["document_id"],
            "family_id": expected.get("family_id"), "pipeline": observation.get("pipeline"),
            "tags": expected.get("tags", []), "development_exposure": expected.get("development_exposure"),
            "source_category": expected.get("source_category"), "status": observation.get("status"),
            "timing": copy.deepcopy(observation.get("timing", {})),
            "runtime": copy.deepcopy(observation.get("runtime", {})),
            "resources": copy.deepcopy(observation.get("resources", {})),
            "asset_delivery": copy.deepcopy(observation.get("asset_delivery", {})),
            "input_page_count": observation.get("input_page_count", len(expected["source_pages"])),
            "protocol": PROTOCOL, "scope": expected["scope"], "source_pages": expected["source_pages"],
            "expected_elements": len(expected["targets"]), "targets": len(outcomes),
            "content_coverage": {"expected_elements": len(content_elements),
                                 "compared_elements": len(content_elements & represented), "omitted_elements": 0},
            "correct": counts["correct"], "incorrect": counts["incorrect"], "by_kind": by_kind,
            "business_metrics": record_metrics, "outcomes": outcomes}


def require_paired_targets(scores: list[dict[str, Any]]) -> None:
    """Compare evaluation outputs only; never inspect corpus truth here."""
    signatures = [{(row["id"], row["kind"], repr(row["expected"])) for row in score["outcomes"]}
                  for score in scores]
    if not signatures or any(items != signatures[0] for items in signatures[1:]):
        raise ValueError("compared candidates did not receive identical expected targets")
    for score in scores:
        if score["targets"] != score["correct"] + score["incorrect"]:
            raise ValueError("every expected target must have a binary decision")
        if any(row["outcome"] not in {"correct", "incorrect"} for row in score["outcomes"]):
            raise ValueError("score contains an unfinished target")
