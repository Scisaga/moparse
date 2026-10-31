"""Evaluate pipeline outputs against a user-frozen, visually reviewed index.

This module consumes declared reference slices read-only. It is deliberately
not a corpus checker: it does not discover annotations, infer their truth,
rewrite references, or certify that visual review actually took place.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .information import (
    column_path_locates,
    endpoint_paths,
    information_value_equal,
    qualifier_evidence,
)
from .information import (
    label_in_text as _label_in_native_cell,
)
from .information import (
    native_range as _native_range,
)
from .information import (
    row_path_locates as _declared_path_locates,
)
from .information_reading import (
    _scalar_units,
    ambiguous_note_scalar,
    metric_units,
    read_information_observation,
    scalar_notes,
)
from .matching import in_page_scope, match_units, observation_candidates, reference_parent_scope
from .metrics import (
    aggregate_text_metrics,
    fraction,
    normalize_text,
    precision_recall_f1,
    text_metrics,
)
from .representations import visible_text

_ORDER_RELATIONS = {"before", "precedes", "reading_order"}
_GRID_RELATIONS = {"same_row", "same_column"}
_BINDING_FIELDS = ("row_header_path", "column_header_path", "unit", "period")
_RELATION_STATES = (
    "confirmed_correct", "confirmed_incorrect", "native_not_provided",
    "endpoint_unresolved", "unassessable",
)


def require_complete_target_grading(score: dict[str, Any]) -> None:
    """Prevent final quality publication until every admitted field is graded.

    This checks score outcomes only, without reading or accepting references.
    It never converts a reader failure into an incorrect candidate answer.
    """
    fields = [(unit["id"], field) for unit in score.get("units", [])
              if unit.get("kind") == "table_record" for field in unit.get("fields", [])
              if field.get("status") != "not_scored"]
    metric = score.get("metrics", {}).get("table_records", {})
    expected = metric.get("target_fields")
    if expected is not None and expected != len(fields):
        raise ValueError("target grading incomplete: field outcomes do not cover the fixed target count")
    identities = [(identity, field.get("index")) for identity, field in fields]
    if len(identities) != len(set(identities)):
        raise ValueError("target grading incomplete: duplicated target identities")
    incomplete = [(identity, field.get("index")) for identity, field in fields
                  if type(field.get("content_exact")) is not bool
                  or field.get("information", {}).get("status") not in {"correct", "incorrect"}
                  or field.get("outcome") != field.get("information", {}).get("status")]
    actual = {"graded_fields": len(fields),
              "correct_fields": sum(field.get("content_exact") is True for _, field in fields),
              "incorrect_fields": sum(field.get("content_exact") is False for _, field in fields),
              "information_correct_fields": sum(field.get("outcome") == "correct" for _, field in fields),
              "information_incorrect_fields": sum(field.get("outcome") == "incorrect" for _, field in fields)}
    if any(key in metric and metric[key] != value for key, value in actual.items()):
        raise ValueError("target grading incomplete: aggregate outcomes disagree with field decisions")
    if incomplete or metric.get("unresolved_fields", 0) or metric.get("information_unresolved_fields", 0):
        raise ValueError(
            f"target grading incomplete for {score.get('sample_id')!r}: "
            f"{len(incomplete)} fields have no final correct/incorrect decision; "
            "repair evaluation before publishing quality results"
        )


def _native_value_and_notes(cell: dict[str, Any], field: dict[str, Any]) -> tuple[str, Any]:
    """Project only explicitly represented native formatting, never a Gold suffix."""
    return scalar_notes(cell)


def _information_value_equal(expected: str, actual: str, field: dict[str, Any],
                             evidence: dict[str, dict[str, Any]]) -> bool:
    """Only a percentage token/Latin-label boundary may vary in spacing.

    Values, signs, labels, and all other word boundaries remain literal; raw
    transcription and strict comparison retain the original strings.
    """
    def boundaries(text: str) -> str:
        return re.sub(r"(?<=\d)%\s*(?=[A-Za-z])", "% ", text)
    return information_value_equal(boundaries(expected), boundaries(actual), field, evidence)


def _record_path_locates(row_path: list[str], item: dict[str, Any], collapse_whitespace: bool, *,
                         require_leaf: bool = False) -> bool:
    cell = item["cell"]
    if cell.get("information_prose_record"):
        if require_leaf:
            return False
        return all(any(_label_in_native_cell(label, actual, collapse_whitespace)
                       for actual in cell.get("information_record_labels", [])) for label in row_path)
    paths = [cell.get("row_header_path")]
    if cell.get("service_evidence_state") == "converted":
        paths += cell.get("printed_record_row_paths", [])
    return any(_declared_path_locates(row_path, path, collapse_whitespace, require_leaf=require_leaf)
               for path in paths)


def _candidate_table_identity(candidate: dict[str, Any]) -> str | None:
    block = candidate.get("block", {})
    identity = block.get("native_table_container") or candidate.get("parent_id")
    return identity if "cell" in candidate and isinstance(identity, str) else None


def _record_candidate_pool(
    unit: dict[str, Any], candidates: list[dict[str, Any]], observation: dict[str, Any],
    matching: dict[str, Any], label_match: dict[str, Any] | None, collapse_whitespace: bool,
) -> tuple[list[dict[str, Any]], str | None]:
    """Honor independent parent/table anchors for both path and grid readers.

    A shared outer container does not establish a common coordinate grid.
    An independently localized row therefore restricts both readers to its
    existing body; sibling bodies are not joined or renumbered here.
    """
    pool = [item for item in candidates if in_page_scope(item, set(unit.get("pages", [])))]
    scope_key = (unit.get("table", {}).get("id"), tuple(unit.get("pages", [])))
    anchored = matching.get("information_table_bodies", {}).get(scope_key, set())
    if label_match is None and len(anchored) == 1:
        pool = [item for item in pool if _candidate_table_identity(item) in anchored
                or item["cell"].get("information_prose_record")]
    # Query the actual business labels together. A reference-side parent ID
    # is navigation metadata, not another required prediction.
    if label_match is not None:
        table, _aliases, context = _table_endpoint_scope(label_match, matching, observation)
        if not context or table is None:
            # A printed record can express the same fact without a table.
            # A table-only locator is not an additional evaluation target.
            return pool, None
        claims = label_match.get("claims") or [label_match]
        bodies = {matching["candidate_map"].get(claim["candidate_id"], {}).get("parent_id")
                  for claim in claims}
        if len(bodies) != 1 or None in bodies:
            return [], "record_native_body_scope_unresolved"
        body = next(iter(bodies))
        pool = [item for item in pool if item.get("parent_id") == body
                or item["cell"].get("information_prose_record")]
        if not pool:
            return [], "record_native_parent_scope_conflict"
    return pool, None


def _html_header_references(
    candidate: dict[str, Any], group: list[dict[str, Any]],
) -> tuple[set[str] | None, str | None]:
    """Resolve only actually declared HTML header IDs, including their chains."""
    attributes = candidate["cell"].get("native_attributes")
    if not isinstance(attributes, dict) or "headers" not in attributes:
        return None, None
    identifiers: dict[str, list[dict[str, Any]]] = {}
    for item in group:
        native = item["cell"].get("native_attributes")
        key = native.get("id") if isinstance(native, dict) else None
        if isinstance(key, str) and key:
            identifiers.setdefault(key, []).append(item)
    resolved: set[str] = set()
    active: set[str] = set()

    def visit(raw: Any) -> bool:
        if not isinstance(raw, str) or not raw.split():
            return False
        for key in raw.split():
            matches = identifiers.get(key, [])
            if len(matches) != 1 or key in active or len(active) >= 128 or len(resolved) >= 2000:
                return False
            item = matches[0]
            cell = item["cell"]
            if cell.get("native_tag") != "th" and cell.get("native_header_tag") is not True:
                return False
            if item.get("duplicate_native_id"):
                return False
            if item["id"] in resolved:
                continue
            active.add(key)
            linked = cell.get("native_attributes", {})
            if "headers" in linked and not visit(linked["headers"]):
                return False
            active.remove(key)
            resolved.add(item["id"])
        return True

    if not visit(attributes["headers"]):
        return set(), "native_explicit_header_references_unresolved"
    return resolved, None


def _active_column_header_group(
    group: list[dict[str, Any]], column: int, data_rows: set[int],
) -> set[str] | None:
    """Find a native-declared contiguous header group, without reading labels."""
    headers = []
    for item in group:
        cell = item["cell"]
        rows, columns = _native_range(cell, "row"), _native_range(cell, "col")
        if (cell.get("is_column_header") is True and item["text"].strip() and rows and columns
                and column in columns):
            headers.append((min(rows), max(rows), item["id"]))
    if not headers or not data_rows:
        return None
    scopes: list[tuple[int, int, set[str]]] = []
    for start, end, identity in sorted(headers):
        if scopes and start <= scopes[-1][1] + 1:
            prior_start, prior_end, members = scopes[-1]
            scopes[-1] = prior_start, max(prior_end, end), members | {identity}
        else:
            scopes.append((start, end, {identity}))
    selected = []
    for row in sorted(data_rows):
        if any(start <= row <= end for start, end, _members in scopes):
            return None
        preceding = [scope for scope in scopes if scope[1] < row]
        if not preceding:
            return None
        selected.append(preceding[-1])
    if any(scope[:2] != selected[0][:2] for scope in selected[1:]):
        return None
    return selected[0][2]


def _grid_column_header_pool(
    group: list[dict[str, Any]], row_endpoints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Scope endpoint lookup before matching the requested column labels."""
    row_ranges = [_native_range(item["cell"], "row") for item in row_endpoints]
    if not row_ranges or any(rows is None for rows in row_ranges):
        return group
    data_rows = set.intersection(*(rows for rows in row_ranges if rows is not None))
    if not data_rows:
        return []
    endpoint_ids = {item["id"] for item in row_endpoints}
    probes = []
    for item in group:
        cell = item["cell"]
        rows = _native_range(cell, "row")
        if (item["id"] not in endpoint_ids and rows and rows & data_rows
                and cell.get("is_column_header") is not True
                and cell.get("is_row_header") is not True):
            references, error = _html_header_references(item, group)
            if references is not None:
                probes.append((item, references, error))
    declared = any(item["cell"].get("is_column_header") is True and item["text"].strip() for item in group)
    if not declared and not probes:
        scoped = [item for item in group if "information_header_body_rows" in item["cell"]]
        if scoped:
            return [item for item in scoped if data_rows <= set(item["cell"]["information_header_body_rows"])]
        return group
    output = []
    active_by_column: dict[int, set[str] | None] = {}
    for item in group:
        cell = item["cell"]
        columns = _native_range(cell, "col")
        if not columns:
            continue
        allowed = False
        for column in columns:
            explicit = [(references, error) for probe, references, error in probes
                        if column in (_native_range(probe["cell"], "col") or set())]
            if explicit:
                allowed |= any(not error and item["id"] in references for references, error in explicit)
            elif declared:
                if column not in active_by_column:
                    active_by_column[column] = _active_column_header_group(group, column, data_rows)
                active = active_by_column[column]
                allowed |= active is not None and item["id"] in active
            else:
                # Preserve the original physical-grid policy in unrelated columns
                # that do not declare either header roles or HTML associations.
                allowed = True
        if allowed:
            output.append(item)
    return output


def _grid_value_header_scope(
    candidate: dict[str, Any], group: list[dict[str, Any]],
    row_endpoints: list[dict[str, Any]], column_endpoints: list[dict[str, Any]],
) -> str | None:
    references, error = _html_header_references(candidate, group)
    if error:
        return error
    if references is not None:
        required = {item["id"] for item in [*row_endpoints, *column_endpoints]}
        if not required <= references:
            return "native_explicit_header_scope_conflict"
        declared = [item for item in group if item["id"] in references
                    and item["cell"].get("is_column_header") is True]
        ancestors = {item["id"]: _html_header_references(item, group)[0] or set() for item in declared}
        for index, first in enumerate(declared):
            first_rows, first_cols = _native_range(first["cell"], "row"), _native_range(first["cell"], "col")
            for second in declared[index + 1:]:
                if first["id"] in ancestors[second["id"]] or second["id"] in ancestors[first["id"]]:
                    continue
                second_rows = _native_range(second["cell"], "row")
                second_cols = _native_range(second["cell"], "col")
                if not first_rows or not second_rows or first_cols != second_cols or not first_cols:
                    continue
                before, after = sorted((first_rows, second_rows), key=min)
                between = set(range(max(before) + 1, min(after)))
                if not between:
                    continue
                if any(
                    item["cell"].get("is_column_header") is not True
                    and item["cell"].get("is_row_header") is not True
                    and item["cell"].get("native_header_tag") is not True
                    and item["text"].strip()
                    and between & (_native_range(item["cell"], "row") or set())
                    and first_cols & (_native_range(item["cell"], "col") or set())
                    for item in group
                ):
                    return "native_explicit_header_scope_ambiguous"
        return None
    if not any(item["cell"].get("is_column_header") is True and item["text"].strip() for item in group):
        return None
    rows = _native_range(candidate["cell"], "row")
    columns = _native_range(candidate["cell"], "col")
    if not rows or not columns:
        return "native_grid_header_scope_unresolved"
    for column in columns:
        active = _active_column_header_group(group, column, rows)
        if active is None or any(item["id"] not in active for item in column_endpoints):
            return "native_grid_header_scope_unresolved"
    return None


def _locate_record_field(
    row_path: list[str], column_path: list[str], pool: list[dict[str, Any]],
    collapse_whitespace: bool,
) -> dict[str, Any]:
    """Select a unique complete label solution before looking at a value."""
    bodies: dict[str, list[dict[str, Any]]] = {}
    for item in pool:
        bodies.setdefault(item["parent_id"], []).append(item)
    solutions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    # A value on an explicitly expressed row is distinct from the same label
    # repeated as context on that row's children. Resolve this by labels and
    # declared table identity before columns or expected values are inspected.
    leaf_tables = {tuple(labels): {_candidate_table_identity(item) for item in pool
                   if _candidate_table_identity(item) is not None
                   and _record_path_locates(labels, item, collapse_whitespace, require_leaf=True)}
                   for labels in (row_path, column_path)}
    for body, group in bodies.items():
        before_body = len(solutions)
        for physical_rows, physical_columns, orientation in (
            (row_path, column_path, "as_returned"), (column_path, row_path, "transposed"),
        ):
            if orientation == "transposed" and len(solutions) > before_body:
                break
            explicit_rows = [item for item in group if _record_path_locates(physical_rows, item, collapse_whitespace)]
            explicit_rows = [item for item in explicit_rows
                             if _candidate_table_identity(item) not in leaf_tables[tuple(physical_rows)]
                             or _record_path_locates(physical_rows, item, collapse_whitespace, require_leaf=True)]
            if explicit_rows:
                found = [item for item in explicit_rows if column_path_locates(
                    physical_columns, item["cell"].get("column_header_path"), collapse_whitespace,
                    [*item["cell"].get("units", []), *([item["cell"]["unit"]] if isinstance(item["cell"].get("unit"), str) else [])],
                    [*item["cell"].get("periods", []), *([item["cell"]["period"]] if isinstance(item["cell"].get("period"), str) else [])])]
                for item in found:
                    solutions.append({"selected": [item], "rows": [], "columns": [],
                                      "group": group, "method": "explicit_native_paths", "orientation": orientation})
                if not found:
                    failures.append({"body": body, "axis": "column", "reason": "native_column_path_unavailable",
                                     "label_presence": [any(_label_in_native_cell(label, text, collapse_whitespace)
                                        for item in explicit_rows for text in item["cell"].get("column_header_path", []))
                                        for label in physical_columns]})
                continue
            # Path-only assertions have no physical grid. Failure to match
            # their printed labels does not make their representation unreadable.
            grid = [item for item in group if _native_range(item["cell"], "row")
                    and _native_range(item["cell"], "col")]
            row_paths, reason = endpoint_paths(physical_rows, grid, "row", collapse_whitespace)
            if reason:
                failures.append({"body": body, "axis": "row", "reason": reason,
                                 "label_presence": [any(_label_in_native_cell(label, item["text"], collapse_whitespace)
                                                        for item in group) for label in physical_rows]})
                continue
            for row_endpoints in row_paths:
                if any(item["cell"].get("information_header_body_rows") is not None
                       and item["cell"].get("is_row_header") is not True for item in row_endpoints):
                    continue
                column_pool = _grid_column_header_pool(grid, row_endpoints)
                column_paths, reason = endpoint_paths(physical_columns, column_pool, "column", collapse_whitespace)
                if reason:
                    failures.append({"body": body, "axis": "column", "reason": reason,
                                     "label_presence": [any(_label_in_native_cell(label, item["text"], collapse_whitespace)
                                                            for item in group) for label in physical_columns]})
                    continue
                for column_endpoints in column_paths:
                    row_ranges = [_native_range(item["cell"], "row") for item in row_endpoints]
                    col_ranges = [_native_range(item["cell"], "col") for item in column_endpoints]
                    if any(extent is None for extent in [*row_ranges, *col_ranges]):
                        failures.append({"body": body, "reason": "native_grid_fields_unavailable"})
                        continue
                    endpoint_ids = {item["id"] for item in [*row_endpoints, *column_endpoints]}
                    selected = []
                    for item in group:
                        native_rows, native_cols = _native_range(item["cell"], "row"), _native_range(item["cell"], "col")
                        if item["id"] not in endpoint_ids and native_rows and native_cols and (
                            all(native_rows & extent for extent in row_ranges if extent is not None)
                            and all(native_cols <= extent for extent in col_ranges if extent is not None)
                        ):
                            selected.append(item)
                    solutions.append({"selected": selected, "rows": row_endpoints, "columns": column_endpoints,
                                      "group": group, "method": "native_grid_relation_probes", "orientation": orientation})
                    if len(solutions) > 512:
                        return {"reason": "native_label_path_search_limit", "diagnostic": {"solution_limit": 512}}
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for solution in solutions:
        key = (tuple(item["id"] for item in solution["selected"]),
               () if solution["selected"] else tuple(item["id"] for item in [*solution["rows"], *solution["columns"]]))
        unique.setdefault(key, solution)
    solutions = list(unique.values())
    diagnostic: dict[str, Any] = {"complete_label_solutions": len(solutions), "scope_failures": failures}
    diagnostic["diagnosis"] = (
        "multiple_complete_correspondences" if len(solutions) > 1
        else "unique_complete_correspondence" if solutions
        else "labels_present_but_scope_unresolved" if any(
            failure.get("label_presence") and all(failure["label_presence"]) for failure in failures)
        else "no_complete_label_in_readable_scope"
    )
    if len(solutions) != 1:
        if solutions:
            reason = "ambiguous_complete_label_path"
        else:
            reasons = {failure["reason"] for failure in failures}
            reason = next(iter(reasons)) if len(reasons) == 1 else "native_fields_unresolved"
        return {"reason": reason, "diagnostic": diagnostic, "alternatives": solutions}
    solution = solutions[0]
    selected = solution["selected"]
    if len(selected) > 1 or any(item.get("duplicate_native_id") for item in selected):
        return {"reason": "ambiguous_native_value_position", "diagnostic": diagnostic, "alternatives": [solution]}
    if selected and solution["method"] == "native_grid_relation_probes":
        reason = _grid_value_header_scope(selected[0], solution["group"], solution["rows"], solution["columns"])
        if reason:
            return {"reason": reason, "diagnostic": diagnostic}
    return {**solution, "reason": None, "diagnostic": diagnostic}


def _required_qualifiers(table: dict[str, Any], field: dict[str, Any]) -> dict[str, Any]:
    result = {key: field.get(key, table.get(key)) for key in ("unit", "period", "note_markers")}
    result = {key: value for key, value in result.items() if value is not None}
    # Read an explicitly printed local ratio before a wider table amount
    # caption. This consumes the frozen target literally, without rewriting
    # it or manufacturing a unit from a metric name or an expected number.
    # An authored field-level override remains authoritative.
    if "unit" not in field:
        local_units = [u for u in _scalar_units(str(field.get("value", "")))
                       if u not in {"$", "€", "£", "¥"}]
        if not local_units:
            local_units = list(dict.fromkeys(u for label in field.get("column_header_path", [])
                                             for u in metric_units(label)))
        if len(local_units) == 1 and re.fullmatch(
                r"[%‰]|[个個]?百分[点點]|percentage points?|basis points?|bps", local_units[0], re.I):
            result["unit"] = local_units[0]
    if "unit" not in result:
        literal_units = [unit for unit in _scalar_units(str(field.get("value", "")))
                         if unit not in {"$", "€", "£", "¥"}]
        if len(literal_units) == 1:
            result["unit"] = literal_units[0]
    return result


def _field_qualifiers(table: dict[str, Any], field: dict[str, Any], resolution: dict[str, Any],
                      *, identity_only: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Read a candidate field's own qualifiers, without inspecting its target value."""
    row_endpoints, column_endpoints = resolution["rows"], resolution["columns"]
    if resolution["selected"]:
        candidate = resolution["selected"][0]
    else:
        # An absent value still has an observed row and column scope. Read
        # those actual headers to distinguish an absent CNY measure from an
        # available USD measure; this does not create a candidate value.
        rows = set.intersection(*(_native_range(item["cell"], "row") or set() for item in row_endpoints))
        columns = set.intersection(*(_native_range(item["cell"], "col") or set() for item in column_endpoints))
        headers = [item["text"] for item in resolution["group"]
                   if rows <= set(item["cell"].get("information_header_body_rows", []))
                   and columns & (_native_range(item["cell"], "col") or set())]
        common = resolution["group"][0]["cell"]
        scope = {"text": "", "information_headers": headers,
                 "information_row_labels": [item["text"] for item in row_endpoints],
                 **{key: common[key] for key in ("information_context", "information_table_units") if key in common}}
        if rows and columns:
            scope.update(row=min(rows), row_span=max(rows) - min(rows) + 1,
                         col=min(columns), col_span=max(columns) - min(columns) + 1)
        candidate = {"cell": scope}
    method = resolution["method"]
    _actual, actual_notes = _native_value_and_notes(candidate["cell"], field)
    qualifiers = _required_qualifiers(table, field)
    if identity_only:
        qualifiers.pop("note_markers", None)
    native_cell = candidate["cell"]
    if not identity_only and "note_markers" in field:
        qualifiers["note_markers"] = field["note_markers"]
        if actual_notes is not None:
            native_cell = {**native_cell, "note_markers": actual_notes}
    endpoint_texts = [item["text"] for item in [*row_endpoints, *column_endpoints]]
    endpoint_texts += [text for key in ("row_header_path", "column_header_path")
                      for text in native_cell.get(key, []) if isinstance(text, str)]
    caption = candidate.get("block", {}).get("caption")
    if isinstance(caption, str):
        endpoint_texts.append(caption)
    if method == "native_grid_relation_probes":
        for column in _native_range(native_cell, "col") or []:
            active = _active_column_header_group(resolution["group"], column, _native_range(native_cell, "row") or set())
            if active:
                endpoint_texts += [item["text"] for item in resolution["group"] if item["id"] in active]
    # Actual explicit HTML links may add scoped units or notes.
    linked, error = _html_header_references(candidate, resolution["group"])
    if linked and not error:
        endpoint_texts += [item["text"] for item in resolution["group"] if item["id"] in linked]
    evidence = qualifier_evidence(qualifiers, native_cell, endpoint_texts)
    return qualifiers, native_cell, evidence


def _score_records(
    units: list[dict[str, Any]], observation: dict[str, Any], collapse_whitespace: bool,
    matching: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read each field independently inside an already declared native scope.

    Header roles and grid positions are candidate evidence. Expected values
    never select a table, header, or cell. Missing values at a resolved native
    position are distinct from unsupported or ambiguous localization.
    """
    readable = read_information_observation(observation)
    candidates = [item for item in observation_candidates(readable) if "cell" in item]
    # Reference table identities scope localization through other uniquely
    # matched labels, never through a target value or a guessed table title.
    matching = {**matching, "information_table_bodies": {}}
    for unit in units:
        match = matching["matches"].get(unit["id"])
        if match and unit.get("table", {}).get("id"):
            label_claims = match.get("claims") or [match]
            bodies = {_candidate_table_identity(matching["candidate_map"].get(claim["candidate_id"], {}))
                      for claim in label_claims}
            if len(bodies) == 1 and None not in bodies:
                key = (unit["table"]["id"], tuple(unit.get("pages", [])))
                matching["information_table_bodies"].setdefault(key, set()).update(bodies)
    rows: list[dict[str, Any]] = []
    declared_fields = target_fields = correct_fields = strict_correct_fields = 0
    compared_fields = target_missing_fields = unresolved_fields = 0
    grid_targets = grid_correct = source_unscoped_fields = field_annotated_records = 0
    blank_targets = blank_observed = blank_correct = 0
    binding_observable = binding_correct = located_records = 0
    field_text: list[dict[str, Any]] = []

    def reject(output: dict[str, Any], reason: str) -> None:
        output["reason"] = reason
        for item in output["fields"]:
            item["reason"] = reason

    for unit in units:
        table = unit.get("table", {})
        row_path = table.get("row_header_path") or []
        fields = table.get("fields") or []
        output: dict[str, Any] = {
            "id": unit["id"], "kind": "table_record", "reference": unit.get("reference"),
            "status": "record_incorrect", "fields": [
                    {"index": index, "status": "incorrect", "reason": "required_business_binding_not_expressed",
                     "required_qualifiers": list(_required_qualifiers(table, field)),
                 "strict_exact": False, "content_exact": False,
                 "information": {"status": "incorrect", "reason": "required_business_binding_not_expressed"}}
                    for index, field in enumerate(fields)
            ], "whole_record_edit_distance": None,
        }
        rows.append(output)
        declared_fields += len(fields)
        field_annotated_records += int(bool(fields))
        if table.get("row_binding", {}).get("status") in {"unresolved", "unknown", "not_annotated"}:
            source_unscoped_fields += len(fields)
            reject(output, "source_row_binding_not_annotated")
            for item in output["fields"]:
                item["status"] = "not_scored"
                item.update(strict_exact=None, content_exact=None)
                item.pop("information", None)
            continue
        target_fields += len(fields)
        blank_targets += sum(field.get("value") == "" for field in fields)
        label_match = matching["matches"].get(unit["id"])
        if label_match:
            output["label_match"] = label_match
            located_records += 1
        if not fields:
            output.update(status="record_without_field_targets", reason="no_declared_field_targets")
            continue
        if not row_path or any(not isinstance(label, str) or not label for label in row_path):
            raise ValueError("frozen target has no evaluable business identity or fields")
        pool, reason = _record_candidate_pool(
            unit, candidates, observation, matching, label_match, collapse_whitespace,
        )
        if reason:
            reject(output, reason)
            continue
        for field, field_row in zip(fields, output["fields"], strict=True):
            value = field.get("value")
            column_path = field.get("column_header_path")
            if (not isinstance(value, str) or len(value) > 512 or not isinstance(column_path, list)
                    or not column_path or any(not isinstance(label, str) or not label for label in column_path)):
                raise ValueError("frozen field lacks an evaluable literal or business label")
            resolution = _locate_record_field(row_path, column_path, pool, collapse_whitespace)
            alternatives = [projected for alternative in resolution.get("alternatives", [])
                            for projected in ([{**alternative, "selected": [candidate]}
                                for candidate in alternative["selected"] if not candidate.get("duplicate_native_id")]
                                if alternative["selected"] else [alternative])]
            if alternatives:
                # Period and unit identify the requested measure. Each comes
                # from this candidate's own field; its value is not a locator.
                qualified = [alternative for alternative in alternatives if all(
                    item["status"] == "correct" for item in
                    _field_qualifiers(table, field, alternative, identity_only=True)[2].values())]
                considered = qualified or alternatives
                present = [alternative for alternative in considered if alternative["selected"]]
                agree = len(considered) == 1 or not present
                if len(present) == len(considered):
                    literal, notes = _native_value_and_notes(present[0]["selected"][0]["cell"], field)
                    agree = True
                for alternative in present if len(present) == len(considered) else []:
                    actual, actual_notes = _native_value_and_notes(alternative["selected"][0]["cell"], field)
                    attributes, _cell, evidence = _field_qualifiers(table, field, alternative)
                    agree &= _information_value_equal(literal, actual, {**field, **attributes}, evidence)
                    agree &= "note_markers" not in field or actual_notes == notes
                if agree:
                    resolution = {**considered[0], "reason": None, "diagnostic": resolution["diagnostic"],
                                  "equivalent_claim_ids": [alternative["selected"][0]["id"] for alternative in present]}
                    for alternative in present:
                        if alternative["method"] == "native_grid_relation_probes":
                            error = _grid_value_header_scope(alternative["selected"][0], alternative["group"],
                                                             alternative["rows"], alternative["columns"])
                            if error:
                                resolution["reason"] = error
                                break
            field_row["localization"] = resolution["diagnostic"]
            if resolution["reason"]:
                if resolution["reason"] in {"native_label_path_search_limit", "native_grid_fields_unavailable"}:
                    raise ValueError("scoring reader cannot evaluate candidate expression: " + resolution["reason"])
                field_row["reason"] = resolution["reason"]
                field_row["information"]["reason"] = resolution["reason"]
                field_row["candidate_evidence"] = {"pages": unit.get("pages", []),
                    "field_ids": [item["id"] for item in pool],
                    "label_witnesses": [{"id": item["id"], "native_path": item.get("native_path"), "text": item["text"]}
                        for item in pool if any(_label_in_native_cell(label, item["text"], collapse_whitespace)
                                                for label in [*row_path, *column_path])]}
                continue
            method = resolution["method"]
            output["method"] = method
            selected = resolution["selected"]
            row_endpoints, column_endpoints = resolution["rows"], resolution["columns"]
            if method == "native_grid_relation_probes":
                grid_targets += 1
                grid_correct += int(len(selected) == 1)
                field_row["grid_relation"] = {"target_candidates": len(selected), "correct": len(selected) == 1}
            field_row["header_evidence"] = [{"native_id": item["native_id"], "text": item["text"],
                                           "native_path": item["native_path"]}
                                          for item in [*row_endpoints, *column_endpoints]]
            if not selected:
                field_row.update(status="incorrect", reason="no_value_at_resolved_native_position",
                                 strict_exact=False, content_exact=False,
                                 information={"status": "incorrect", "reason": "required_value_not_expressed"},
                                 text=text_metrics(value, "", collapse_whitespace=collapse_whitespace))
                continue
            candidate = selected[0]
            if resolution.get("equivalent_claim_ids"):
                field_row["equivalent_claim_ids"] = resolution["equivalent_claim_ids"]
            field_row["candidate_id"] = candidate["id"]
            actual, actual_notes = _native_value_and_notes(candidate["cell"], field)
            strict_correct = value == actual
            content_correct = value == actual  # assigned after reading candidate qualifiers
            if value == "":
                blank_observed += 1
                blank_correct += int(strict_correct)
            correct_fields += int(content_correct)
            strict_correct_fields += int(strict_correct)
            comparison = text_metrics(value, actual, collapse_whitespace=collapse_whitespace)
            field_text.append(comparison)
            field_row.update(
                status="compared", reason="native_value_compared",
                native_id=candidate["native_id"], native_path=candidate["native_path"],
                strict_exact=strict_correct, content_exact=content_correct, text=comparison,
                native_text=candidate["text"], native_note_markers=actual_notes,
                raw_transcription=text_metrics(value, candidate["text"], collapse_whitespace=collapse_whitespace),
            )
            qualifiers, native_cell, evidence = _field_qualifiers(table, field, resolution)
            content_correct = _information_value_equal(value, actual, {**field, **qualifiers}, evidence)
            field_row["content_exact"] = content_correct
            qualifier_observable = all(item.get("source") != "required_candidate_qualifier_not_expressed"
                                       for item in evidence.values())
            qualifier_correct = all(item["status"] == "correct" for item in evidence.values())
            information_status = (
                "incorrect" if not content_correct or any(item["status"] == "incorrect" for item in evidence.values())
                else "correct" if qualifier_correct else "incorrect"
            )
            field_row["information"] = {"status": information_status, "qualifiers": evidence}
            if information_status == "incorrect":
                wrong = [key for key, item in evidence.items() if item["status"] != "correct"]
                field_row["information"]["reason"] = (
                    "value_expression_incorrect" if not content_correct else "required_qualifier_incorrect:" + ",".join(wrong))
            if (not content_correct and ambiguous_note_scalar(native_cell)
                    and not any(item["status"] == "incorrect" for item in evidence.values())):
                field_row["information"].update(status="incorrect", reason="ambiguous_note_or_exponent_format")
            field_row["binding"] = {
                "observable": qualifier_observable,
                "correct": bool(strict_correct and qualifier_correct) if qualifier_observable else None,
                "content_correct": content_correct, "strict_content_correct": strict_correct,
                "qualifier_correct": bool(qualifier_correct) if qualifier_observable else None,
                "qualifiers": list(qualifiers),
            }
        usable = [item for item in output["fields"] if item["status"] == "compared"]
        if usable:
            output["status"] = "record_located"
        else:
            reasons = {item["reason"] for item in output["fields"]}
            output["reason"] = next(iter(reasons)) if len(reasons) == 1 else "required_business_binding_not_expressed"
    all_fields = [item for row in rows for item in row["fields"] if item["status"] != "not_scored"]
    compared = [item for item in all_fields if item["status"] == "compared"]
    correct_fields = sum(bool(item["content_exact"]) for item in compared)
    strict_correct_fields = sum(bool(item["strict_exact"]) for item in compared)
    field_text = [item["text"] for item in compared]
    blank_compared = [item for item in compared if item["text"]["strict"]["reference_chars"] == 0]
    blank_observed = len(blank_compared)
    blank_correct = sum(bool(item["strict_exact"]) for item in blank_compared)
    binding_observable = sum(bool(item.get("binding", {}).get("observable")) for item in compared)
    binding_correct = sum(bool(item.get("binding", {}).get("correct")) for item in compared)
    information = Counter(item["information"]["status"] for item in all_fields)
    if information["correct"] + information["incorrect"] != target_fields:
        raise ValueError("not every admitted business target has a correct/incorrect decision")
    for item in all_fields:
        item["outcome"] = item["information"]["status"]
    for row in rows:
        if row["fields"] and not any(item["status"] == "compared" for item in row["fields"]):
            row["status"] = "record_incorrect"
    located_records = sum(bool(row.get("label_match")) or row["status"] == "record_located" for row in rows)
    statuses = Counter(item["status"] for row in rows for item in row["fields"])
    compared_fields = statuses["compared"]
    target_missing_fields = sum(item["reason"] == "no_value_at_resolved_native_position" for item in all_fields)
    unresolved_fields = 0
    observed_fields = compared_fields + target_missing_fields
    return rows, {
        "target_records": len(units), "located_records": located_records,
        "field_annotation_record_coverage": fraction(field_annotated_records, len(units)),
        "declared_fields": declared_fields, "source_unscoped_fields": source_unscoped_fields,
        "blank_target_fields": blank_targets, "blank_observed_fields": blank_observed,
        "blank_fields": fraction(blank_correct, blank_targets, observable=blank_observed),
        "blank_observed_accuracy": fraction(blank_correct, blank_observed),
        "target_fields": target_fields, "observable_fields": observed_fields,
        "graded_fields": target_fields, "incorrect_fields": target_fields - correct_fields,
        "compared_fields": compared_fields, "target_missing_fields": target_missing_fields,
        "unresolved_fields": unresolved_fields, "correct_fields": correct_fields,
        "strict_correct_fields": strict_correct_fields,
        "information_correct_fields": information["correct"],
        "information_incorrect_fields": information["incorrect"],
        "information_unresolved_fields": 0,
        "information_target_correctness": fraction(information["correct"], target_fields),
        "information_compared_accuracy": fraction(information["correct"], information["correct"] + information["incorrect"]),
        "field_unresolved_reasons": {}, "field_unresolved_diagnoses": {},
        "field_error_reasons": dict(Counter(item.get("information", {}).get("reason", item["reason"])
                                             for item in all_fields if item["outcome"] == "incorrect")),
        "field_coverage": fraction(observed_fields, target_fields),
        "field_comparison_coverage": fraction(compared_fields, target_fields),
        "field_compared_accuracy": fraction(correct_fields, compared_fields),
        "field_strict_accuracy": fraction(strict_correct_fields, compared_fields),
        "field_target_correctness": fraction(correct_fields, target_fields),
        "field_strict_target_correctness": fraction(strict_correct_fields, target_fields),
        "field_text": aggregate_text_metrics(field_text),
        "grid_relation": fraction(grid_correct, grid_targets, meaning="unique_native_grid_probe_resolution_not_source_structure_accuracy"),
        "binding": fraction(binding_correct, binding_observable),
        "binding_target_coverage": fraction(binding_observable, target_fields),
        "whole_record_edit_distance": None,
    }


def read_reference_text(unit: dict[str, Any], reference_root: str | Path) -> str:
    """Read a declared inclusive 1-based line slice; never modify its file."""
    literal = unit.get("literal")
    if literal is not None:
        if not isinstance(literal, str) or len(literal) > 512:
            raise ValueError("inline literals are limited to small manually authored fields")
        return literal
    reference = unit.get("reference") or {}
    if "fragments" in reference:
        if unit.get("kind") != "table_record":
            raise ValueError("fragment references currently support table records only")
        fragments = reference["fragments"]
        if not isinstance(fragments, list) or not fragments:
            raise ValueError("table record fragments must be an authored nonempty list")
        return "\n".join(read_reference_text({"reference": fragment,
            "reference_representation": unit.get("reference_representation", "markdown")}, reference_root)
            for fragment in fragments)
    relative = reference.get("path")
    lines = reference.get("lines")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("reference.path must be relative to the frozen reference root")
    if (
        not isinstance(lines, (list, tuple)) or len(lines) != 2
        or any(type(value) is not int for value in lines)
        or lines[0] < 1 or lines[1] < lines[0]
    ):
        raise ValueError("reference.lines must be an inclusive [start, end] pair")
    root = Path(reference_root).resolve()
    source = (root / relative).resolve()
    if not source.is_relative_to(root):
        raise ValueError("reference.path escapes the frozen reference root")
    # Read only through the declared endpoint, rather than ingesting a whole document.
    selected: list[str] = []
    with source.open("r", encoding="utf-8", newline="") as handle:
        for index, line in enumerate(handle, 1):
            if index >= lines[0]:
                selected.append(line)
            if index == lines[1]:
                break
        else:
            raise ValueError("declared reference slice is unavailable")
    # Physical line separators are not authored paragraph content.
    raw = "".join(selected).removesuffix("\n").removesuffix("\r")
    return visible_text(raw, unit.get("reference_representation", "markdown"))


def _extra_output_units(
    matching: dict[str, Any], case: dict[str, Any], scored_units: list[dict[str, Any]]
) -> int:
    """Count unclaimed native items/fragments only in an exhaustive declared scope."""
    scoring = case.get("scoring", {})
    ignored_ids = set(scoring.get("ignored_native_ids", []))
    ignored_paths = set(scoring.get("ignored_native_paths", []))
    pages = {page for unit in scored_units for page in unit.get("pages", [])}
    extra = 0
    for candidate in matching["candidates"]:
        if not in_page_scope(candidate, pages):
            continue
        if candidate["native_id"] in ignored_ids or candidate["native_path"] in ignored_paths:
            continue
        if any(
            in_page_scope(candidate, set(item.get("pages", [])))
            and isinstance(item.get("literal"), str)
            and normalize_text(candidate["text"], collapse_whitespace=True)
            == normalize_text(item["literal"], collapse_whitespace=True)
            for item in scoring.get("ignored_units", [])
        ):
            # Only a complete native item can be excluded as authored furniture.
            # A matching number within a business paragraph is never removed.
            continue
        spans = sorted(
            claim["span"]
            for match in matching["matches"].values()
            for claim in match.get("claims", [match])
            if claim["candidate_id"] == candidate["id"]
        )
        if candidate["kind"] == "image":
            extra += int(not spans)
            continue
        cursor = 0
        for start, end in [*spans, [len(candidate["text"]), len(candidate["text"])]]:
            if candidate["text"][cursor:start].strip():
                extra += 1
            cursor = max(cursor, end)
    return extra


def _native_table_ids(candidate: dict[str, Any], observation: dict[str, Any]) -> set[str]:
    """Follow only declared native body/container identities, never geometry."""
    block = candidate.get("block", {})
    containers = {str(item["id"]): item for item in observation.get("native_containers", [])
                  if item.get("id") is not None}
    identifiers: set[str] = set()
    if "cell" in candidate or block.get("kind") in {"table", "table_body"}:
        identifiers.update(str(value) for value in (
            candidate.get("id"), candidate.get("native_id"), candidate.get("parent_id"), block.get("id"),
        ) if value is not None)
    explicit = block.get("native_table_container")
    if isinstance(explicit, str):
        identifiers.add(explicit)
    parent = block.get("parent_id")
    seen = set()
    while isinstance(parent, str) and parent not in seen:
        seen.add(parent)
        container = containers.get(parent, {})
        if container.get("label") != "table":
            break
        identifiers.add(parent)
        parent = container.get("parent_id")
    return identifiers


def _table_endpoint_scope(match: dict[str, Any], matching: dict[str, Any],
                          observation: dict[str, Any]) -> tuple[str | None, set[str], bool]:
    """Require every physical claim to own the same unambiguous native table.

    Cell and body IDs are aliases, not competing table containers. An alias
    usable for a multi-claim endpoint must be shared by all of its claims.
    """
    table_counts = Counter(str(item["id"]) for item in observation.get("native_containers", [])
                           if item.get("id") is not None and item.get("label") == "table")
    declared_tables = set(table_counts)
    scopes: list[set[str]] = []
    aliases: list[set[str]] = []
    table_context = False
    ambiguous = False
    for claim in match.get("claims") or [match]:
        candidate = matching["candidate_map"].get(claim.get("candidate_id"), {})
        block = candidate.get("block", {})
        identifiers = _native_table_ids(candidate, observation)
        owned = identifiers & declared_tables
        explicit = block.get("native_table_container")
        if isinstance(explicit, str):
            owned.add(explicit)
        if not owned and block.get("kind") == "table" and block.get("id") is not None:
            owned.add(str(block["id"]))
        context = bool(owned or "cell" in candidate or block.get("kind") in {
            "table", "table_body", "table_caption", "table_footnote",
        })
        # A stand-alone SDK table body can be the only declared table object.
        if not owned and ("cell" in candidate or block.get("kind") == "table_body"):
            body = block.get("id")
            if body is not None:
                owned.add(str(body))
        table_context |= context
        ambiguous |= bool(candidate.get("duplicate_native_id") or any(
            table_counts[identity] > 1 for identity in owned
        ))
        scopes.append(owned)
        aliases.append(identifiers)
    if not table_context:
        return None, set(), False
    if ambiguous or any(len(scope) != 1 for scope in scopes):
        return None, set(), True
    common = set.intersection(*scopes)
    if len(common) != 1:
        return None, set(), True
    return next(iter(common)), set.intersection(*aliases) | common, True


def _explicit_table_relation(kind: str, left: dict[str, Any], right: dict[str, Any],
                             observation: dict[str, Any], *,
                             endpoint_ids: tuple[set[str], set[str]] | None = None) -> dict[str, Any] | None:
    """Test an unordered native table pair; reading direction is scored separately."""
    left_ids, right_ids = endpoint_ids if endpoint_ids is not None else (
        _native_table_ids(left, observation), _native_table_ids(right, observation)
    )
    if not left_ids or not right_ids:
        return None
    declarations = [edge for edge in observation.get("relations", [])
                    if edge.get("type") in {"continues", "separate"} and (
                        edge.get("source") in left_ids and edge.get("target") in right_ids
                        or edge.get("source") in right_ids and edge.get("target") in left_ids
                    )]
    kinds = {edge["type"] for edge in declarations}
    if kinds:
        conflicting = len(kinds) > 1
        return {
            "correct": not conflicting and kind in kinds, "observable": not conflicting,
            "evidence": "explicit_native_table_relation",
            "reason": "conflicting_native_table_relations" if conflicting else None,
            "native_declaration_paths": [edge.get("native_path") for edge in declarations],
            "implicit_pair_test": True,
        }
    if not left_ids & right_ids and any(
        (item.get("table_id") in left_ids | right_ids or item.get("native_path") in left_ids | right_ids
         or bool((left_ids | right_ids) & set(item.get("unresolved_observation_table_ids", []))))
        and item.get("continues_prev") is True
        and item.get("status") == "unknown"
        for item in observation.get("native_table_declarations", [])
    ):
        return {"correct": False, "observable": False, "reason": "native_continuation_unresolved",
                "evidence": "native_table_declaration", "implicit_pair_test": True}
    if not left_ids & right_ids and (observation.get("scoring_readback") or {}).get("native_status") in {
        "native_missing", "readback_error",
    } and (left.get("block", {}).get("native_table_container") is not None
           or right.get("block", {}).get("native_table_container") is not None):
        return {"correct": False, "observable": False, "reason": "native_declaration_readback_unavailable",
                "evidence": "scoring_readback", "implicit_pair_test": True}
    return None


def _relation_endpoint_ids(
    match: dict[str, Any], matching: dict[str, Any], observation: dict[str, Any],
    *, containers: bool,
) -> tuple[list[set[str]], bool]:
    """Resolve native aliases and, where requested, explicit containment only.

    A caption or heading assigned to a native table also applies to a located
    record inside that table. This does not infer ownership from proximity,
    coordinates, equal labels, or a reference table identifier.
    """
    blocks = [item for page in observation.get("pages", []) for item in page.get("blocks", [])]
    nodes = [*observation.get("native_containers", []), *blocks]
    nodes.extend(cell for block in blocks for cell in block.get("cells", []))
    counts = Counter(str(item["id"]) for item in nodes if item.get("id") is not None)
    parents: dict[str, set[str]] = {}
    if containers:
        for item in nodes:
            if item.get("id") is None:
                continue
            identity = str(item["id"])
            parent = item.get("parent_id")
            if parent is not None:
                parents.setdefault(identity, set()).add(str(parent))
            for child in item.get("native_children", []):
                parents.setdefault(str(child), set()).add(identity)
            if item.get("native_table_container") is not None and str(item["native_table_container"]) != identity:
                parents.setdefault(identity, set()).add(str(item["native_table_container"]))
        for edge in observation.get("relations", []):
            if edge.get("type") == "contains" and edge.get("source") is not None and edge.get("target") is not None:
                parents.setdefault(str(edge["target"]), set()).add(str(edge["source"]))
    native_counts = Counter(str(item.get("native_id")) for item in matching["candidate_map"].values()
                            if item.get("native_id") is not None)
    result: list[set[str]] = []
    for claim in match.get("claims") or [match]:
        candidate = matching["candidate_map"].get(claim.get("candidate_id"), {})
        if candidate.get("duplicate_native_id") or not candidate:
            return [], True
        identities = {str(candidate["id"])}
        native_id = candidate.get("native_id")
        if native_id is not None and native_counts[str(native_id)] == 1:
            identities.add(str(native_id))
        if any(counts[identity] > 1 for identity in identities):
            return [], True
        if containers:
            block = candidate.get("block", {})
            if "cell" in candidate and candidate.get("parent_id") is not None:
                identities.add(str(candidate["parent_id"]))
            # Only a declared identity can connect a body to its outer table.
            if block.get("native_table_container") is not None:
                identities.add(str(block["native_table_container"]))
            pending: list[tuple[str, frozenset[str]]] = [(identity, frozenset()) for identity in identities]
            expanded: set[str] = set()
            while pending:
                identity, ancestors = pending.pop()
                if identity in ancestors:
                    return [], True
                if identity in expanded:
                    continue
                expanded.add(identity)
                if counts[identity] > 1:
                    return [], True
                for parent in parents.get(identity, set()):
                    identities.add(parent)
                    pending.append((parent, ancestors | {identity}))
        result.append(identities)
    return result, False


def _relation_evidence(
    relation: dict[str, Any], matching: dict[str, Any], observation: dict[str, Any]
) -> dict[str, Any]:
    row = {key: relation.get(key) for key in ("type", "source", "target")}
    source = matching["matches"].get(relation.get("source"))
    target = matching["matches"].get(relation.get("target"))
    if source is None or target is None:
        return {**row, "correct": False, "observable": False, "reason": "endpoint_unresolved"}
    candidates = matching["candidate_map"]
    left, right = candidates[source["candidate_id"]], candidates[target["candidate_id"]]
    if left.get("duplicate_native_id") or right.get("duplicate_native_id"):
        return {**row, "correct": False, "observable": False, "reason": "native_id_ambiguous"}
    kind = relation.get("type")
    table_scopes: tuple[str, str] | None = None
    if kind in {"continues", "separate"}:
        left_scope, left_ids, left_table = _table_endpoint_scope(source, matching, observation)
        right_scope, right_ids, right_table = _table_endpoint_scope(target, matching, observation)
        if (left_table or right_table) and (left_scope is None or right_scope is None):
            return {**row, "correct": False, "observable": False,
                    "reason": "native_table_endpoint_scope_unresolved",
                    "evidence": "all_native_claim_table_scopes", "implicit_pair_test": True}
        if left_scope is not None and right_scope is not None:
            table_scopes = (left_scope, right_scope)
        explicit = _explicit_table_relation(kind, left, right, observation,
            endpoint_ids=(left_ids, right_ids) if table_scopes is not None else None)
        if explicit is not None:
            return {**row, **explicit}
    if kind in _ORDER_RELATIONS:
        # Content matching has already finished without consulting this order.
        first_claim = source.get("claims", [source])[0]
        second_claim = target.get("claims", [target])[0]
        left_position = (*candidates[first_claim["candidate_id"]]["order"], first_claim["span"][0])
        right_position = (*candidates[second_claim["candidate_id"]]["order"], second_claim["span"][0])
        return {
            **row, "correct": left_position < right_position, "observable": True,
            "evidence": "native_sequence", "implicit_pair_test": True,
        }
    if kind in _GRID_RELATIONS:
        key = "row" if kind == "same_row" else "col"
        left_cell, right_cell = left.get("cell", {}), right.get("cell", {})
        left_range, right_range = _native_range(left_cell, key), _native_range(right_cell, key)
        available = left_range is not None and right_range is not None
        same_table = left.get("parent_id") is not None and left.get("parent_id") == right.get("parent_id")
        return {
            **row,
            "correct": bool(available and same_table and left_range and right_range and left_range & right_range),
            "observable": available,
            "evidence": "native_cell_fields" if available else None,
            "reason": None if available else "native_grid_unavailable",
            "implicit_pair_test": True,
        }
    if kind in {"continues", "separate"} and "cell" in left and "cell" in right:
        available = table_scopes is not None or (left.get("parent_id") is not None and right.get("parent_id") is not None)
        same = table_scopes[0] == table_scopes[1] if table_scopes is not None else available and left["parent_id"] == right["parent_id"]
        return {
            **row, "correct": bool(available and (same if kind == "continues" else not same)),
            "observable": available, "evidence": "native_table_container_identity",
            "implicit_pair_test": True,
        }
    if kind in {"caption_for", "caption_of", "heading_of"}:
        target_scope, _target_aliases, table_context = _table_endpoint_scope(target, matching, observation)
        if table_context and target_scope is None:
            return {**row, "correct": False, "observable": False,
                    "reason": "native_relation_identity_unresolved"}
    native_kind = "caption_of" if kind == "caption_for" else kind
    edges = {
        ("caption_of" if edge.get("type") == "caption_for" else edge.get("type"),
         str(edge.get("source")), str(edge.get("target")))
        for edge in observation.get("relations", [])
        if edge.get("source") is not None and edge.get("target") is not None
    }
    source_ids, source_ambiguous = _relation_endpoint_ids(source, matching, observation, containers=False)
    target_ids, target_ambiguous = _relation_endpoint_ids(
        target, matching, observation, containers=kind in {"caption_for", "caption_of", "heading_of"},
    )
    if source_ambiguous or target_ambiguous:
        return {**row, "correct": False, "observable": False, "reason": "native_relation_identity_unresolved"}
    projected = native_kind != kind or any(len(values) > 1 for values in [*source_ids, *target_ids])
    row["implicit_pair_test"] = projected
    owners = [{origin for edge_kind, origin, endpoint in edges
               if edge_kind == native_kind and endpoint in endpoints}
              for endpoints in target_ids] if kind == "heading_of" else []
    if any(len(values) > 1 for values in owners):
        return {**row, "correct": False, "observable": False,
                "reason": "conflicting_native_heading_owners", "evidence": "explicit_native_relation"}
    correct = all(any((native_kind, origin, endpoint) in edges
                      for origin in origins for endpoint in endpoints)
                  for origins in source_ids for endpoints in target_ids)
    if correct:
        return {**row, "correct": True, "observable": True,
                "evidence": ("explicit_native_relation_and_containment"
                             if kind in {"caption_for", "caption_of", "heading_of"}
                             else "explicit_native_relation")}
    # A declared direct heading owner supplies a counterexample. Merely having
    # some other outgoing edge does not establish that an unreturned edge is
    # false: SDK relation inventories need not be exhaustive.
    if kind == "heading_of":
        if all(owners) and all(len(values) == 1 for values in owners):
            return {**row, "correct": False, "observable": True,
                    "reason": "different_declared_heading_owner", "evidence": "explicit_native_relation"}
    reason = "native_relation_not_provided"
    if kind == "heading_of":
        heading_sources = (observation.get("native_relation_evidence") or {}).get("heading_blocks", [])
        source_aliases = set().union(*source_ids)
        if any(item.get("id") in source_aliases and item.get("status") == "role_only_without_level"
               for item in heading_sources):
            reason = "native_title_role_without_hierarchy"
    return {
        **row, "correct": False, "observable": False, "reason": reason,
        "evidence": "native_relation_inventory",
    }


def _relation_result(
    relation: dict[str, Any], matching: dict[str, Any], observation: dict[str, Any],
) -> dict[str, Any]:
    row = _relation_evidence(relation, matching, observation)
    reason = row.get("reason")
    if row["correct"]:
        state = "confirmed_correct"
    elif reason == "endpoint_unresolved":
        state = "endpoint_unresolved"
    elif row["observable"]:
        state = "confirmed_incorrect"
    elif reason in {"native_id_ambiguous", "native_relation_identity_unresolved",
                    "native_table_endpoint_scope_unresolved", "native_declaration_readback_unavailable",
                    "conflicting_native_table_relations", "conflicting_native_heading_owners"}:
        state = "unassessable"
    else:
        state = "native_not_provided"
    return {**row, "state": state}


def _field_pair_binding(unit: dict[str, Any], matching: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    scope = unit.get("field_scope", {})
    label = matching["matches"].get(scope.get("label_unit"))
    value = matching["matches"].get(unit["id"])
    if not label or not value:
        return {"observable": False, "correct": False, "reason": "field_pair_endpoint_unresolved"}
    label_claims = label.get("claims", [label])
    value_claims = value.get("claims", [value])
    label_ids = {claim["candidate_id"] for claim in label_claims}
    value_ids = {claim["candidate_id"] for claim in value_claims}
    native_pairs = []
    for edge in observation.get("relations", []):
        if edge.get("type") in {"label_value", "key_value", "field_value", "has_value"}:
            native_pairs.append((str(edge.get("source")), str(edge.get("target"))))
        elif edge.get("type") == "value_of":
            native_pairs.append((str(edge.get("target")), str(edge.get("source"))))
    if any(origin in label_ids for origin, _target in native_pairs):
        return {"observable": True, "correct": any(origin in label_ids and target in value_ids for origin, target in native_pairs),
                "evidence": "explicit_native_field_relation"}
    if len(label_claims) == len(value_claims) == 1 and label_ids == value_ids:
        left, right = label_claims[0]["span"], value_claims[0]["span"]
        candidate = matching["candidate_map"][label_claims[0]["candidate_id"]]
        if left[1] <= right[0] and candidate["text"][left[1]:right[0]].strip() in {":", "：", "="}:
            return {"observable": True, "correct": True, "evidence": "explicit_native_text_key_value_separator"}
    return {"observable": False, "correct": False, "reason": "native_field_relation_unavailable"}


def score_case(
    case: dict[str, Any],
    observation: dict[str, Any],
    reference_root: str | Path = ".",
    *,
    text_locator_threshold: float = 0.8,
    reference_exclusions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score one frozen case. Unknown references never become correct answers."""
    if case.get("sample_id") != observation.get("sample_id"):
        raise ValueError("case and observation sample_id differ")
    if observation.get("scoring_readback", {}).get("native_status") == "readback_error":
        raise ValueError("candidate reader failed; repair readback before grading")
    if case.get("review_status") != "confirmed":
        raise ValueError("scoring requires an explicitly frozen, visually confirmed case")
    scoring = case.get("scoring", {})
    collapse_whitespace = bool(scoring.get("collapse_whitespace", True))
    prepared: list[dict[str, Any]] = []
    unit_rows: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    unit_ids: set[str] = set()
    known_image_targets = sum(unit.get("kind") == "image" and unit.get("status") == "confirmed"
                              for unit in case.get("units", []))
    for unit in case.get("units", []):
        unit_id = unit.get("id")
        if not isinstance(unit_id, str) or not unit_id or unit_id in unit_ids:
            raise ValueError("scoring unit IDs must be nonempty and unique")
        unit_ids.add(unit_id)
        status = unit.get("status", "pending")
        row = {"id": unit_id, "kind": unit.get("kind"), "reference": unit.get("reference")}
        adjudication = (reference_exclusions or {}).get(unit_id)
        if adjudication:
            excluded["human_reference_pending"] += 1
            unit_rows[unit_id] = {
                **row, "status": "not_scored", "reason": "human_reference_pending",
                "reference_status_at_freeze": status, "human_adjudication": adjudication,
            }
            continue
        if status != "confirmed":
            excluded[status] += 1
            unit_rows[unit_id] = {**row, "status": "not_scored", "reason": status}
            continue
        if unit.get("field_scope", {}).get("status") in {"unresolved", "unknown", "not_annotated"}:
            excluded["source_field_scope_not_annotated"] += 1
            unit_rows[unit_id] = {**row, "status": "not_scored", "reason": "source_field_scope_not_annotated"}
            continue
        if unit.get("kind") == "image" and unit.get("literal") is None:
            excluded["image_output_identity_requires_visual_adjudication"] += 1
            unit_rows[unit_id] = {
                **row, "status": "not_scored", "reference_status": "confirmed",
                "reason": "image_output_identity_requires_visual_adjudication",
            }
            continue
        try:
            reference_text = read_reference_text(unit, reference_root)
        except (OSError, UnicodeError, ValueError) as exc:
            excluded["reference_unavailable"] += 1
            errors.append({"code": "reference_unavailable", "unit_id": unit_id, "detail": str(exc)})
            unit_rows[unit_id] = {**row, "status": "not_scored", "reason": "reference_unavailable"}
            continue
        if not reference_text:
            excluded["empty_reference"] += 1
            unit_rows[unit_id] = {**row, "status": "not_scored", "reason": "empty_reference"}
            continue
        if unit.get("text_comparison") == "not_applicable" and unit.get("kind") != "table_record":
            literal = unit.get("localization_literal", unit.get("literal"))
            if not isinstance(literal, str) or not literal or len(literal) > 512:
                excluded["nonliteral_reference_without_source_locator"] += 1
                unit_rows[unit_id] = {
                    **row, "status": "not_scored", "text": None,
                    "reason": "nonliteral_reference_without_source_locator",
                }
                continue
            reference_text = literal
        prepared.append({**unit, "reference_text": reference_text})
        unit_rows[unit_id] = row
    if unknown_exclusions := set(reference_exclusions or {}) - unit_ids:
        raise ValueError(f"human reference exclusion has no unit in this scoring case: {sorted(unknown_exclusions)}")
    # An unavailable reference anchor is not a candidate omission. Propagate
    # only actual, declared localization dependencies; long independent prose
    # can still be scored when its heading reference is unavailable.
    unavailable = {identifier for identifier, row in unit_rows.items() if row.get("status") == "not_scored"}
    changed = True
    while changed:
        changed = False
        for unit in prepared:
            if unit["id"] in unavailable:
                continue
            parent, needs_scope, _ = reference_parent_scope(unit, collapse_whitespace=collapse_whitespace)
            if needs_scope and parent in unavailable:
                unavailable.add(unit["id"])
                excluded["reference_localization_dependency_unavailable"] += 1
                unit_rows[unit["id"]].update(
                    status="not_scored", reason="reference_localization_dependency_unavailable",
                    reference_status_at_freeze=unit.get("status"), reference_dependency=parent,
                )
                changed = True
    prepared = [unit for unit in prepared if unit["id"] not in unavailable]
    record_units = [unit for unit in prepared if unit.get("kind") == "table_record"]
    prepared = [unit for unit in prepared if unit.get("kind") != "table_record"]
    record_locators = [
        {**unit, "reference_text": unit["table"]["row_header_path"][-1]}
        for unit in record_units if unit.get("table", {}).get("row_header_path")
        and unit.get("table", {}).get("row_binding", {}).get("status") not in {"unresolved", "unknown", "not_annotated"}
    ]
    matching = match_units(
        [*prepared, *record_locators], observation,
        threshold=text_locator_threshold, collapse_whitespace=collapse_whitespace
    )
    record_rows, record_metrics = _score_records(record_units, observation, collapse_whitespace, matching)
    for row in record_rows:
        unit_rows[row["id"]] = row
    text_results: list[dict[str, Any]] = []
    aligned_text_results: list[dict[str, Any]] = []
    field_results: list[dict[str, Any]] = []
    cell_results: list[dict[str, Any]] = []
    fields_correct = fields_total = fields_observed = exact_units = exact_targets = 0
    pair_correct = pair_observed = pair_total = 0
    grid_correct = grid_total = binding_correct = binding_total = binding_observable = 0
    image_correct = image_total = 0
    for unit in prepared:
        unit_id, kind = unit["id"], unit.get("kind")
        match = matching["matches"].get(unit_id)
        hypothesis = match["hypothesis"] if match else ""
        row = unit_rows[unit_id]
        row.update(matching["diagnostics"][unit_id])
        localization_only = unit.get("localization_scope") == "label_only"
        row["content_presence_scored"] = not localization_only
        if match:
            row["match"] = match
        text_comparable = unit.get("text_comparison") != "not_applicable" and not localization_only
        row["strict_exact"] = bool(match and unit["reference_text"] == hypothesis) if text_comparable else None
        row["policy_exact"] = bool(
            match and normalize_text(unit["reference_text"], collapse_whitespace=collapse_whitespace)
            == normalize_text(hypothesis, collapse_whitespace=collapse_whitespace)
        ) if text_comparable else None
        exact_units += int(bool(row["policy_exact"]))
        exact_targets += int(text_comparable and not localization_only)
        if kind != "image" and text_comparable:
            row["text"] = text_metrics(
                unit["reference_text"], hypothesis, collapse_whitespace=collapse_whitespace
            )
        elif not text_comparable:
            row["text"] = None
            row["text_na_reason"] = (
                "localization_anchor_does_not_annotate_whole_content"
                if localization_only else "authored_reference_reorganizes_source_text"
            )
        if kind == "text" and text_comparable:
            text_results.append(row["text"])
            if match:
                aligned_text_results.append(row["text"])
        elif kind == "field" and text_comparable:
            fields_total += 1
            fields_correct += int(row["strict_exact"])
            fields_observed += int(match is not None)
            field_results.append(row["text"])
            if unit.get("field_scope", {}).get("scope_kind") == "visual_label_value_pair":
                label_id = unit["field_scope"].get("label_unit")
                if label_id in unavailable:
                    row["field_pair_binding"] = {
                        "correct": None, "observable": False,
                        "reason": "reference_binding_dependency_unavailable", "reference_dependency": label_id,
                    }
                else:
                    pair_total += 1
                    binding = _field_pair_binding(unit, matching, observation)
                    pair_correct += int(binding["correct"] and row["strict_exact"])
                    pair_observed += int(binding["observable"])
                    row["field_pair_binding"] = binding
        elif kind == "table_cell":
            if text_comparable:
                cell_results.append(row["text"])
            expected_table = unit.get("table", {})
            candidate = matching["candidate_map"].get(match["candidate_id"], {}) if match else {}
            native_cell = candidate.get("cell", {})
            grid_keys = [key for key in ("row", "col", "row_span", "col_span") if key in expected_table]
            if grid_keys:
                grid_total += 1
                grid_available = all(key in native_cell for key in grid_keys)
                grid_ok = grid_available and all(native_cell[key] == expected_table[key] for key in grid_keys)
                grid_correct += int(grid_ok)
                row["grid"] = {"correct": grid_ok, "observable": grid_available, "fields": grid_keys}
            binding_keys = [key for key in _BINDING_FIELDS if key in expected_table]
            if binding_keys:
                binding_total += 1
                available = all(key in native_cell for key in binding_keys)
                correct = available and row["strict_exact"] and all(
                    native_cell[key] == expected_table[key] for key in binding_keys
                )
                binding_observable += int(available)
                binding_correct += int(correct)
                row["binding"] = {
                    "correct": bool(correct), "observable": available, "fields": binding_keys,
                }
        elif kind == "image":
            image_total += 1
            candidate = matching["candidate_map"].get(match["candidate_id"], {}) if match else {}
            has_asset_reference = bool(candidate.get("asset"))
            image_correct += int(has_asset_reference)
            row["image_reference_present"] = has_asset_reference
            row["image_fidelity"] = None
    content_units = [unit for unit in prepared if unit.get("localization_scope") != "label_only"]
    exhaustive = (
        scoring.get("exhaustive_units") is True and scoring.get("exhaustive_output_scope") is True
        and not excluded and not record_units and len(content_units) == len(prepared)
    )
    extras = _extra_output_units(matching, case, content_units) if exhaustive else None
    localized = sum(unit["id"] in matching["matches"] for unit in content_units)
    presence = precision_recall_f1(localized, extras, len(content_units) - localized)
    presence["meaning"] = "localized_presence_not_character_correctness"
    presence["unresolved_are_not_asserted_model_omissions"] = True
    presence["precision_scope"] = "exhaustively_annotated_business_scope" if exhaustive else None
    if not exhaustive:
        presence["precision_na_reason"] = "closed_business_and_furniture_scope_not_declared_or_reference_unavailable"
    exact = precision_recall_f1(
        exact_units,
        extras + localized - exact_units if extras is not None and exact_targets == len(prepared) else None,
        exact_targets - exact_units,
    )
    declared_confirmed_relations = [
        relation for relation in case.get("relations", []) if relation.get("status") == "confirmed"
    ]
    unavailable_reference_ids = {
        identifier for identifier, row in unit_rows.items() if row.get("status") == "not_scored"
    }
    confirmed_relations = [
        relation for relation in declared_confirmed_relations
        if relation.get("source") not in unavailable_reference_ids
        and relation.get("target") not in unavailable_reference_ids
    ]
    relation_rows = [_relation_result(relation, matching, observation) for relation in confirmed_relations]
    relation_correct = sum(row["correct"] for row in relation_rows)
    relation_exhaustive = (
        scoring.get("exhaustive_relations") is True
        and not any(row.get("implicit_pair_test") for row in relation_rows)
        and not excluded
        and all(relation.get("status") == "confirmed" for relation in case.get("relations", []))
    )
    relation_fp: int | None = None
    if relation_exhaustive:
        confirmed_edges = set()
        for relation, row in zip(confirmed_relations, relation_rows, strict=True):
            if row["correct"]:
                source = matching["matches"][relation["source"]]
                target = matching["matches"][relation["target"]]
                for left in source.get("claims", [source]):
                    for right in target.get("claims", [target]):
                        confirmed_edges.add((relation["type"], left["candidate_id"], right["candidate_id"]))
        # Several disjoint reference spans can share one native block edge.
        # Their target recall remains defined, but edge precision has a
        # different unit unless the support is genuinely one-to-one.
        if len(confirmed_edges) == relation_correct:
            output_counts = Counter(
                (edge.get("type"), str(edge.get("source")), str(edge.get("target")))
                for edge in observation.get("relations", [])
            )
            relation_fp = sum(output_counts.values()) - len(confirmed_edges)
    relations_metric = precision_recall_f1(
        relation_correct, relation_fp, len(confirmed_relations) - relation_correct
    )
    relations_metric["observable"] = sum(row["observable"] for row in relation_rows)
    relations_metric["unresolved"] = sum(not row["observable"] for row in relation_rows)
    relations_metric["evidence_states"] = {
        state: sum(row["state"] == state for row in relation_rows) for state in _RELATION_STATES
    }
    relations_metric["interpretation"] = "target_fulfillment_not_relation_recognition_accuracy"
    relation_types = sorted({str(relation["type"]) for relation in confirmed_relations})
    relations_metric["by_type"] = {
        kind: {**fraction(
            sum(row["correct"] for row in relation_rows if row["type"] == kind),
            sum(row["type"] == kind for row in relation_rows),
            observable=sum(row["observable"] for row in relation_rows if row["type"] == kind),
        ), **{state: sum(row["type"] == kind and row["state"] == state for row in relation_rows)
              for state in _RELATION_STATES},
            "conditional_accuracy": fraction(
                sum(row["type"] == kind and row["state"] == "confirmed_correct" for row in relation_rows),
                sum(row["type"] == kind and row["observable"] for row in relation_rows),
            ), **({"pair_classification": precision_recall_f1(
            sum(row["correct"] for row in relation_rows if row["type"] == kind),
            sum(row["observable"] and not row["correct"] for row in relation_rows if row["type"] == kind),
            sum(not row["correct"] for row in relation_rows if row["type"] == kind),
        )} if kind in _ORDER_RELATIONS else {})}
        for kind in relation_types
    }
    return {
        "sample_id": case.get("sample_id"),
        "document_id": case.get("document_id"),
        "family_id": case.get("family_id"),
        "source_category": case.get("source_category", "source-unknown"),
        "development_exposure": case.get("development_exposure", "unknown"),
        "tags": case.get("tags", []),
        "pipeline": observation.get("pipeline"),
        "status": observation.get("status", "unknown"),
        "dataset": case.get("dataset"),
        "suite": observation.get("suite", case.get("suite")),
        "phase": observation.get("phase", "measured"),
        "input_page_count": observation.get("input_page_count", case.get("input_page_count")),
        "run_id": observation.get("run_id"),
        "repetition": observation.get("repetition"),
        "review_status": "confirmed",
        "human_reference_adjudications": list((reference_exclusions or {}).values()),
        "scorer_status": "evaluated",
        "metrics": {
            "unit_presence": presence,
            "unit_exact": exact,
            "text": aggregate_text_metrics(text_results),
            "text_aligned": aggregate_text_metrics(aligned_text_results),
            "field_text": aggregate_text_metrics(field_results),
            "field_exact": fraction(fields_correct, fields_total, comparison="strict_character_target_correctness", observable=fields_observed),
            "field_observed_accuracy": fraction(fields_correct, fields_observed),
            "field_pair_binding": fraction(pair_correct, pair_total, observable=pair_observed),
            "field_pair_observed_binding": fraction(pair_correct, pair_observed),
            "table_cell_text": aggregate_text_metrics(cell_results),
            "table_records": record_metrics,
            "table_grid": fraction(grid_correct, grid_total),
            "table_binding": fraction(binding_correct, binding_total, observable=binding_observable),
            "image_reference_presence": fraction(image_correct, image_total, verifies_asset_bytes=False,
                scope="automatic_identity_subset_only", known_image_targets=known_image_targets),
            "image_fidelity": {"value": None, "reason": "requires_direct_visual_review",
                               "known_image_targets": known_image_targets, "visually_reviewed_outputs": 0},
            "relations": relations_metric,
        },
        "coverage": {
            "declared_units": len(case.get("units", [])),
            "confirmed_units": sum(unit.get("status") == "confirmed" for unit in case.get("units", [])),
            "scored_units": len(content_units),
            "localization_only_units": len(prepared) - len(content_units),
            "table_record_targets": len(record_units),
            "table_record_located": record_metrics["located_records"],
            "localized_units": localized,
            "text_reference_units": len(text_results),
            "text_aligned_units": len(aligned_text_results),
            "text_reference_chars": sum(item["strict"]["reference_chars"] for item in text_results),
            "text_aligned_reference_chars": sum(item["strict"]["reference_chars"] for item in aligned_text_results),
            "localized_anchors": sum(unit["id"] in matching["matches"] for unit in prepared if unit.get("localization_scope") == "label_only"),
            "ambiguous_units": sum(row.get("status") == "ambiguous" for row in unit_rows.values()),
            "unresolved_units": sum(row.get("status") == "unresolved" for row in unit_rows.values()),
            "not_localized_units": sum(row.get("status") == "not_localized" for row in unit_rows.values()),
            "excluded_units": dict(excluded),
            "declared_relations": len(case.get("relations", [])),
            "scored_relations": len(confirmed_relations),
            "reference_unavailable_relations": len(declared_confirmed_relations) - len(confirmed_relations),
            "input_pages": len({page for unit in case.get("units", []) for page in unit.get("pages", [])}),
            "known_image_targets": known_image_targets,
            "image_automatic_identity_targets": image_total,
            "image_output_visual_review_targets": 0,
            "declared_field_pair_bindings": sum(
                unit.get("field_scope", {}).get("scope_kind") == "visual_label_value_pair"
                for unit in case.get("units", [])
            ),
            "reference_unavailable_field_pair_bindings": sum(
                unit.get("field_scope", {}).get("scope_kind") == "visual_label_value_pair"
                and (unit["id"] in unavailable or unit.get("field_scope", {}).get("label_unit") in unavailable)
                for unit in case.get("units", [])
            ),
        },
        "units": list(unit_rows.values()),
        "relations": relation_rows,
        "timing": observation.get("timing", {}),
        "resources": observation.get("resources", {}),
        "runtime": observation.get("runtime", {}),
        "scoring_readback": observation.get("scoring_readback"),
        "page_inference_runtime": [
            {"page": page.get("page"), "record": page["inference_runtime"]}
            for page in observation.get("pages", []) if page.get("inference_runtime")
        ],
        "errors": [*observation.get("errors", []), *errors],
        "evaluation_policy": {
            "text_locator_threshold": text_locator_threshold,
            "locator_threshold_is_not_correctness": True,
            "collapse_whitespace": collapse_whitespace,
            "table_text_not_flattened_into_prose": True,
            "output_denominator": "aligned_spans_and_unclaimed_native_items_or_fragments",
            "text": "conservative_target_score_unlocalized_reference_as_deletions",
            "text_aligned": "conditional_character_accuracy_on_uniquely_localized_units",
            "unlocalized_reference_deletions_do_not_prove_native_text_absence": True,
            "unclaimed_output_in_character_cer": False,
            "extra_output": "unit_precision_only_with_exhaustive_business_and_furniture_scope",
            "unavailable_reference_dependencies": "exclude_declared_localization_or_binding_dependencies_only",
        },
    }
