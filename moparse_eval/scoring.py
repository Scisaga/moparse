"""Shared business-field comparison for the canonical expected scorer."""

from __future__ import annotations

import re
from collections import Counter
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
    candidate_note_texts,
    metric_units,
    read_information_observation,
    scalar_notes,
)
from .matching import in_page_scope, observation_candidates
from .metrics import (
    aggregate_text_metrics,
    fraction,
    text_metrics,
)


def _native_value_and_notes(cell: dict[str, Any], field: dict[str, Any]) -> tuple[str, Any]:
    """Project only explicitly represented native formatting, never a Gold suffix."""
    if re.fullmatch(r"[（(]?原表留空[）)]?", str(cell.get("text", "")).strip()):
        return "", cell.get("note_markers")
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
        if any(_declared_path_locates(row_path, path, collapse_whitespace, require_leaf=require_leaf)
               for path in cell.get("printed_subject_paths", [])):
            return True
        if require_leaf:
            return False
        return all(any(_label_in_native_cell(label, actual, collapse_whitespace)
                       for actual in cell.get("information_record_labels", [])) for label in row_path)
    paths = [cell.get("row_header_path"), *cell.get("printed_subject_paths", [])]
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
    if unit.get("source_element_id"):
        # Canonical expected IDs and list spans are navigation only. A row
        # text match cannot choose a table before its full business scope.
        # The field resolver below uses labels and scoped qualifiers across
        # all actual bodies, without looking at the expected value.
        return pool, None
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
    collapse_whitespace: bool, *, identity_field: bool = False, endpoint_cache: dict | None = None,
) -> dict[str, Any]:
    """Select a unique complete label solution before looking at a value."""
    bodies: dict[str, list[dict[str, Any]]] = {}
    for item in pool:
        bodies.setdefault(item["parent_id"], []).append(item)
    solutions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    def endpoints(labels, cells, axis):
        key = tuple(labels), tuple(id(item) for item in cells), axis, collapse_whitespace
        if endpoint_cache is not None and key in endpoint_cache:
            return endpoint_cache[key]
        result = endpoint_paths(labels, cells, axis, collapse_whitespace)
        if endpoint_cache is not None:
            endpoint_cache[key] = result
        return result
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
                             if not leaf_tables[tuple(physical_rows)]
                             or _record_path_locates(physical_rows, item, collapse_whitespace, require_leaf=True)]
            if explicit_rows:
                found = [item for item in explicit_rows if (not physical_columns and item["cell"].get("named_value") is not False) or physical_columns and column_path_locates(
                    physical_columns, item["cell"].get("column_header_path"), collapse_whitespace,
                    [*item["cell"].get("units", []), *([item["cell"]["unit"]] if isinstance(item["cell"].get("unit"), str) else [])],
                    [*item["cell"].get("periods", []), *([item["cell"]["period"]] if isinstance(item["cell"].get("period"), str) else [])],
                    allow_prefix=True)]
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
            row_paths, reason = endpoints(physical_rows, grid, "row")
            if reason:
                failures.append({"body": body, "axis": "row", "reason": reason,
                                 "label_presence": [any(_label_in_native_cell(label, item["text"], collapse_whitespace)
                                                        for item in group) for label in physical_rows]})
                continue
            for row_endpoints in row_paths:
                if any((physical_columns and item["cell"].get("information_header_body_rows") is not None
                        or item["cell"].get("is_column_header") is True)
                       and item["cell"].get("is_row_header") is not True for item in row_endpoints):
                    continue
                if not physical_columns:
                    row_ranges = [_native_range(item["cell"], "row") for item in row_endpoints]
                    endpoint_ids = {item["id"] for item in row_endpoints}
                    selected = [item for item in grid if item["id"] not in endpoint_ids
                                and item["cell"].get("is_column_header") is not True
                                and all(set(_native_range(item["cell"], "row") or []) & set(r or []) for r in row_ranges)]
                    if len(selected) == 1:
                        solutions.append({"selected": selected, "rows": row_endpoints, "columns": [],
                                          "group": group, "method": "explicit_single_value_row", "orientation": orientation})
                    continue
                column_pool = _grid_column_header_pool(grid, row_endpoints)
                column_paths, reason = endpoints(physical_columns, column_pool, "column")
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
                        is_identity_value = identity_field and item["id"] == row_endpoints[-1]["id"]
                        if (item["id"] not in endpoint_ids or is_identity_value) and native_rows and native_cols and (
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
    result = {key: field.get(key, table.get(key)) for key in ("unit", "currency", "period", "business_scope", "note_markers", "note_texts")}
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
        rows = set.intersection(*(_native_range(item["cell"], "row") or set() for item in row_endpoints)) if row_endpoints else set()
        columns = set.intersection(*(_native_range(item["cell"], "col") or set() for item in column_endpoints)) if column_endpoints else set()
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
        qualifiers.pop("note_texts", None)
    native_cell = candidate["cell"]
    notes = candidate_note_texts(native_cell)
    if notes:
        native_cell = {**native_cell, "note_texts": notes}
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
    endpoint_cache: dict = {}

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
            if (not isinstance(value, str) or not isinstance(column_path, list)
                    or not column_path and field.get("named_value") is not True
                    or any(not isinstance(label, str) or not label for label in column_path)):
                raise ValueError("frozen field lacks an evaluable literal or business label")
            resolution = _locate_record_field(row_path, column_path, pool, collapse_whitespace,
                                              identity_field=field.get("identity_field") is True,
                                              endpoint_cache=endpoint_cache)
            alternatives = [projected for alternative in resolution.get("alternatives", [])
                            for projected in ([{**alternative, "selected": [candidate]}
                                for candidate in alternative["selected"] if not candidate.get("duplicate_native_id")]
                                if alternative["selected"] else [alternative])]
            # Authored business headings locate homonymous records, even
            # when the selected expected range contains only one of them.
            # This uses labels and actual scope, never a field's answer.
            for heading in reversed(unit.get("expected_context", [])):
                scoped = [alternative for alternative in alternatives if all(
                    item["status"] == "correct" for item in _field_qualifiers(
                        {**table, "business_scope": heading}, field, alternative, identity_only=True)[2].values())]
                if scoped:
                    alternatives = scoped
                    break
            if alternatives:
                # Period and unit identify the requested measure. Each comes
                # from this candidate's own field; its value is not a locator.
                identities = [(alternative, _field_qualifiers(table, field, alternative, identity_only=True)[2])
                              for alternative in alternatives]
                qualified = [alternative for alternative, evidence in identities
                             if all(item["status"] == "correct" for item in evidence.values())]
                incompatible = [alternative for alternative, evidence in identities
                    if evidence.get("unit_applicability", {}).get("status") == "incorrect"
                    and all(item["status"] == "correct" for key, item in evidence.items()
                            if key not in {"unit", "unit_applicability"})]
                conflict = bool(qualified and incompatible)
                if conflict:
                    resolution["reason"] = "conflicting_incompatible_field_units"
                    resolution["diagnostic"]["conflicting_claim_ids"] = [
                        candidate["id"] for alternative in [*qualified, *incompatible]
                        for candidate in alternative["selected"]]
                considered = qualified or alternatives
                present = [alternative for alternative in considered if alternative["selected"]]
                agree = not conflict and (len(considered) == 1 or not present)
                if len(present) == len(considered):
                    literal, notes = _native_value_and_notes(present[0]["selected"][0]["cell"], field)
                    agree = not conflict
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
