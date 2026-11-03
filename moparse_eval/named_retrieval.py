"""Locate named records in actual column grids and printed list collections.

The queries contain identity labels/names and the requested property label.
No answer value is supplied. Every returned value retains its original item.
"""

from __future__ import annotations

from .information import column_path_locates, native_range, row_path_locates


def _key(wanted, actual, collapse):
    return column_path_locates(wanted, actual, collapse, allow_prefix=True)


def _bound_identity(row_path, keys, pairs, collapse):
    bound = []
    for required in keys:
        values = [(key, value) for key, value in pairs if _key(required, key, collapse)]
        if not values or len({value["text"] for _key_path, value in values}) != 1:
            return None
        bound.append(values[0][1])
    return bound if row_path_locates(row_path, [item["text"] for item in bound], collapse) else None


def column_named_fields(row_path, column_path, keys, group, collapse):
    from .expected_readback import _IDENTITY

    if not keys or not column_path:
        return False, []
    bands = {}
    for item in group:
        cell = item["cell"]
        if type(cell.get("row")) is int and type(cell.get("col")) is int:
            bands.setdefault(cell["row"], []).append(item)
    found, results = False, []
    for row, band in sorted(bands.items()):
        stub = next((item for item in band if item["cell"]["col"] == 0), None)
        if stub is None:
            continue
        direct = _key(keys[0], [stub["text"]], collapse)
        identity_row = bool(_IDENTITY.fullmatch(stub["text"].strip()))
        if not direct and not identity_row:
            continue
        for name in band:
            if name is stub or not any(
                row_path_locates(row_path[:n], [name["text"]], collapse)
                for n in range(1, len(row_path) + 1)
            ):
                continue
            role_headers = [
                item
                for item in group
                if row in item["cell"].get("information_header_body_rows", [])
                and (extent := native_range(item["cell"], "col"))
                and (native_range(name["cell"], "col") or set()) <= extent
            ]
            if not direct and not any(
                _key(keys[0], [header["text"]], collapse) for header in role_headers
            ):
                continue
            found = True
            slots = native_range(name["cell"], "col")
            if not slots:
                continue
            start = row
            header_bands = [
                item["cell"]["row"]
                for item in group
                if row in item["cell"].get("information_header_body_rows", [])
            ]
            if header_bands:
                start = min(header_bands)
            stop = max(bands) + 1
            for following, cells in sorted(bands.items()):
                if following <= row:
                    continue
                left = next((item for item in cells if item["cell"]["col"] == 0), None)
                nonempty = [item for item in cells if item["text"].strip()]
                if (
                    left
                    and (
                        _key(keys[0], [left["text"]], collapse)
                        or left["cell"].get("information_header_body_rows") is not None
                    )
                    or len(nonempty) == 1
                    and nonempty[0]["cell"].get("col_span", 1) > 1
                ):
                    stop = following
                    break
            pairs, labels = [], []
            for actual_row, cells in sorted(bands.items()):
                if not start <= actual_row < stop:
                    continue
                left = next((item for item in cells if item["cell"]["col"] == 0), None)
                if left is None:
                    continue
                values = [
                    item
                    for item in cells
                    if item is not left
                    and (extent := native_range(item["cell"], "col"))
                    and extent <= slots
                ]
                pairs.extend(([left["text"]], value) for value in values)
                labels.extend((left, value) for value in values)
            identity = _bound_identity(row_path, keys, pairs, collapse)
            if identity is None and identity_row:
                role_pairs = [([header["text"]], name) for header in role_headers]
                identity = _bound_identity(row_path, keys, [*pairs, *role_pairs], collapse)
            if identity is None:
                continue
            for header in role_headers if identity_row else []:
                if _key(column_path, [header["text"]], collapse):
                    results.append(
                        {
                            "selected": [name],
                            "rows": identity,
                            "columns": [header],
                            "group": group,
                            "method": "native_named_column_identity",
                            "orientation": "printed_column_record",
                            "record_identity_evidence": {
                                "name_ids": [item["id"] for item in identity],
                                "name_row_key": stub["text"],
                                "header_id": header["id"],
                            },
                        }
                    )
            for label, value in labels:
                if _key(column_path, [label["text"]], collapse):
                    results.append(
                        {
                            "selected": [value],
                            "rows": identity,
                            "columns": [label],
                            "group": group,
                            "method": "native_named_column_field",
                            "orientation": "printed_column_record",
                            "record_identity_evidence": {
                                "name_ids": [item["id"] for item in identity],
                                "rows": [start, stop],
                                "columns": sorted(slots),
                            },
                        }
                    )
    return found, results


def list_named_fields(row_path, column_path, keys, pool, collapse):
    """Read sibling properties in one actual Markdown list, ending at a new name."""
    if not keys or not column_path:
        return set(), []
    collections = {}
    for item in pool:
        block = item["block"]
        span = block.get("public_list_span")
        if span and item["cell"].get("column_header_path"):
            collection = tuple(span), tuple(block.get("public_list_parents", []))
            collections.setdefault(collection, {}).setdefault(item["parent_id"], []).append(item)
    masked, results = set(), []
    for blocks in collections.values():
        ordered = sorted(blocks.values(), key=lambda items: min(item["order"] for item in items))
        for index, items in enumerate(ordered):
            primary = [
                item
                for item in items
                if _key(keys[0], item["cell"]["column_header_path"], collapse)
                and any(
                    row_path_locates(row_path[:n], [item["text"]], collapse)
                    for n in range(1, len(row_path) + 1)
                )
            ]
            if not primary:
                continue
            region = []
            for offset, following in enumerate(ordered[index:]):
                unique = {
                    (tuple(item["cell"]["column_header_path"]), item["text"]) for item in following
                }
                if offset and (
                    any(
                        _key(keys[0], item["cell"]["column_header_path"], collapse)
                        for item in following
                    )
                    or len(unique) > 1
                ):
                    break
                region.extend(following)
            masked.update(item["parent_id"] for item in region)
            pairs = [(item["cell"]["column_header_path"], item) for item in region]
            identity = _bound_identity(row_path, keys, pairs, collapse)
            if identity is None:
                continue
            for item in region:
                if _key(column_path, item["cell"]["column_header_path"], collapse):
                    label = {**item, "text": " / ".join(item["cell"]["column_header_path"])}
                    results.append(
                        {
                            "selected": [item],
                            "rows": identity,
                            "columns": [label],
                            "group": region,
                            "method": "printed_list_named_property",
                            "orientation": "printed_property_list",
                            "record_identity_evidence": {
                                "name_ids": [part["id"] for part in identity],
                                "list_span": list(item["block"]["public_list_span"]),
                            },
                        }
                    )
    return masked, results
