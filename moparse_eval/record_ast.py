"""Read a record's printed row path, fields and period groups from its own syntax."""

from __future__ import annotations

import re
from collections import defaultdict

from .measurement_evidence import read_measurement_label, read_measurement_literal, read_unit_token
from .period_evidence import DATE_PATTERN, calendar_date

_PERIOD = re.compile(rf"(?:{DATE_PATTERN}|(?:19|20)\d{{2}}(?:年(?:度|末|初)?)?)(?!\d)", re.I)
_PAIR = re.compile(r"\s*([^;；:：\n]+?)\s*[:：]\s*(.+)", re.S)
_BASIS = re.compile(r"年末|月均|年初|期末|期初|日均|季末|季均|期均")
_OPERATOR = re.compile(r"(?:>=|<=|≥|≤|>|<|=)")
_STATUS = re.compile(r"不[适適]用|N/?A|—|–|-", re.I)
_UNIT_AXIS = re.compile(
    r"(?:(?:财务|財務|主要|金融|业务|業務)*)?(?:指标|指標|项目|項目)|(?:financial\s+)?(?:metrics?|items?|indicators?)",
    re.I,
)


def _token(text, origin, start, stop):
    while start < stop and text[start].isspace():
        start += 1
    while stop > start and text[stop - 1].isspace():
        stop -= 1
    base = origin.get("text_span", [0])[0]
    return {
        "text": text[start:stop],
        "source": {**origin, "text_span": [base + start, base + stop]},
    }


def _period(text):
    match = _PERIOD.match(text)
    if not match:
        return None
    name = match[0]
    if re.fullmatch(DATE_PATTERN, name, re.I) and not calendar_date(name):
        return None
    return match


def _field(label, value, *, explicit_cell=False):
    """A status is a printed value. An empty/unsupported operand has no numeric reading."""
    raw = value["text"]
    op = _OPERATOR.match(raw)
    offset = op.end() if op else 0
    value_start, value_end = value["source"]["text_span"]
    operand_source = {**value["source"], "text_span": [value_start + offset, value_end]}
    measured = read_measurement_literal(raw[offset:], operand_source)
    field = {"kind": "field", "label": label, "value": value}
    header = read_measurement_label(label["text"], label["source"])
    if header["matched"]:
        field["printed_label"] = label
        field["label"] = {"text": header["label"], "source": header["sources"]["label"]}
    if measured["matched"]:
        field["number"] = {"text": measured["value"], "source": measured["sources"]["value"]}
        if op:
            field["operator"] = _token(raw, value["source"], 0, op.end())
        qualifier = (
            measured
            if measured["unit"] or measured["currency"] or measured["currency_symbol"]
            else header
        )
        for key in ("unit", "currency", "currency_symbol"):
            if qualifier[key]:
                field[key] = {"text": qualifier[key], "source": qualifier["sources"][key]}
    elif _STATUS.fullmatch(raw):
        field["status"] = value
    elif explicit_cell:
        field["reading"] = "opaque" if raw else "empty"
    else:
        return None
    return field


def _named_field(part):
    text, source = part["text"], part["source"]
    pair = _PAIR.fullmatch(text)
    if pair:
        return _field(_token(text, source, *pair.span(1)), _token(text, source, *pair.span(2)))
    # A printed bound separates a column name from its inequality operand.
    op = _OPERATOR.search(text)
    basis = _BASIS.match(text)
    cut = op.start() if op and op.start() else basis.end() if basis else None
    if cut is None and (status := re.fullmatch(r"(.+?)(不[适適]用|N/?A)", text, re.I)):
        cut = status.end(1)
    if not cut or cut >= len(text):
        return None
    return _field(_token(text, source, 0, cut), _token(text, source, cut, len(text)))


def read_list_record(text, source):
    if not re.search(r"[;；]", text):
        return None
    row = re.match(r"\s*([^:：;；\n]+?)\s*[:：]\s*", text)
    if not row:
        return None
    label = _token(text, source, *row.span(1))
    cursor, end = row.end(), len(text.rstrip())
    if text[end - 1 : end] in {".", "。"}:
        end -= 1
    children, dates, paths = [], set(), set()
    for part in re.finditer(r"[^;；]+", text[cursor:end]):
        piece = _token(text, source, cursor + part.start(), cursor + part.end())
        content, origin = piece["text"], piece["source"]
        period = _period(content)
        if not period:
            child = _named_field(piece)
            if not child or child["label"]["text"] in paths:
                return None
            paths.add(child["label"]["text"])
            children.append(child)
            continue
        marker = _token(content, origin, *period.span())
        if marker["text"] in dates:
            return None
        dates.add(marker["text"])
        begin = period.end()
        if sep := re.match(r"\s*[:：]\s*", content[begin:]):
            begin += sep.end()
        # An enumeration delimiter splits sibling fields only within this period.
        members = []
        for segment in re.finditer(r"[^、|]+", content[begin:]):
            field = _named_field(
                _token(content, origin, begin + segment.start(), begin + segment.end())
            )
            if not field or any(m["label"]["text"] == field["label"]["text"] for m in members):
                return None
            members.append(field)
        if not members:
            return None
        children.append({"kind": "period", "label": marker, "children": members})
    if not dates or not any(c["kind"] == "period" and len(c["children"]) >= 2 for c in children):
        return None
    from .three_layer import canonical

    # Partition the original item's single content weight across its fields,
    # including the printed label, date and delimiters once in source order.
    fields = [f for c in children for f in (c["children"] if c["kind"] == "period" else [c])]
    start = 0
    for index, field in enumerate(fields):
        stop = (
            len(text)
            if index == len(fields) - 1
            else field["value"]["source"]["text_span"][1] - source.get("text_span", [0])[0]
        )
        field["source_weight"] = len(canonical(text[start:stop]))
        start = stop
    return {"kind": "record", "row_path": [label], "children": children, "source": source}


def _grid_records(table, cells):
    """Accept two explicit header levels and a named row axis in one physical table."""
    by_row = defaultdict(list)
    for c in cells:
        if not all(type(c.get(k)) is int for k in ("row", "col")):
            return
        by_row[c["row"]].append(c)
    if len(by_row) < 3:
        return
    top = min(by_row)
    heads = sorted(by_row[top], key=lambda c: c["col"])
    if not heads or heads[0]["col"] != 0:
        return
    axis = heads[0]
    corner = None
    if axis["row_span"] == 1 and not axis["text"].strip():
        below = [
            c
            for c in by_row[top + 1]
            if c["col"] == 0
            and c["row_span"] == 1
            and c["col_span"] == axis["col_span"]
            and c["text"].strip()
        ]
        if len(below) != 1:
            return
        corner, axis = axis, below[0]
    elif axis["row_span"] != 2 or not axis["text"].strip():
        return
    decl = axis.get("native_declarations", {})
    if not (
        decl.get("native_header_tag")
        or decl.get("is_column_header")
        or _UNIT_AXIS.fullmatch(axis["text"].strip())
    ):
        return
    width, columns, groups, dated = axis["col_span"], {}, [], set()
    plain_headers, subcolumns = set(), set()
    if width < 1:
        return
    end = width
    for head in heads[1:]:
        col, span = head["col"], head["col_span"]
        if col != end or span < 1:
            return
        end += span
        name = head["text"].strip()
        if not name:
            return
        period = _period(name)
        if period and period.end() == len(name) and span >= 2 and head["row_span"] == 1:
            identity = calendar_date(name) or name
            if identity in dated:
                return
            dated.add(identity)
            leaves = sorted(
                (c for c in by_row[top + 1] if col <= c["col"] < end),
                key=lambda c: c["col"],
            )
            if (
                [c["col"] for c in leaves] != list(range(col, end))
                or any(
                    c["row_span"] != 1 or c["col_span"] != 1 or not c["text"].strip()
                    for c in leaves
                )
                or len({c["text"].strip() for c in leaves}) != span
            ):
                return
            groups.append((head, leaves))
            columns.update((c["col"], c) for c in leaves)
            subcolumns.update(range(col, end))
        elif head["row_span"] == 2 and span == 1 and not period:
            if name in plain_headers:
                return
            plain_headers.add(name)
            groups.append((None, [head]))
            columns[col] = head
        else:
            return
    if (
        len(dated) < 2
        or set(columns) != set(range(width, end))
        or sorted(c["col"] for c in by_row[top + 1] if c is not axis) != sorted(subcolumns)
    ):
        return
    label_cells = [c for c in cells if c["row"] >= top + 2 and c["col"] < width]
    for row in sorted(r for r in by_row if r >= top + 2):
        local = by_row[row]
        if any(
            c["native_declarations"].get("native_attributes", {}).get("scope")
            in {"col", "colgroup"}
            or c["col_span"] > 1
            and _period(c["text"].strip())
            for c in local
        ):
            break
        if any(_UNIT_AXIS.fullmatch(c["text"].strip()) for c in local if c["col"] == 0):
            break
        if any(c["col"] >= end for c in local):
            break
        labels = sorted(
            (c for c in label_cells if c["row"] <= row < c["row"] + c["row_span"]),
            key=lambda c: c["col"],
        )
        coverage = [i for c in labels for i in range(c["col"], c["col"] + c["col_span"])]
        if coverage != list(range(width)) or any(not c["text"].strip() for c in labels):
            continue
        data = {c["col"]: c for c in local if c["col"] >= width}
        if len(data) != len([c for c in local if c["col"] >= width]):
            continue
        if set(data) != set(columns) or any(
            c["row_span"] != 1
            or c["col_span"] != 1
            or c["native_declarations"].get("native_attributes", {}).get("headers")
            for c in data.values()
        ):
            continue
        children = []
        for parent, headers in groups:
            fields = [
                _field(_cell_label(h), _cell_label(data[h["col"]]), explicit_cell=True)
                for h in headers
            ]
            children.extend(
                [{"kind": "period", "label": _cell_label(parent), "children": fields}]
                if parent
                else fields
            )
        anchor = labels[-1]
        if anchor["row"] == row and anchor["row_span"] == 1:
            yield (
                anchor["index"],
                {
                    "kind": "record",
                    "row_path": [_cell_label(c) for c in labels],
                    "children": children,
                    "source": anchor["source"],
                    "table_source": table,
                    "row_axis": _cell_label(axis),
                    **({"blank_corner": _cell_label(corner)} if corner else {}),
                },
            )


def _cell_label(cell):
    return _token(cell["text"], cell["source"], 0, len(cell["text"]))


def _dated_fields(block, text, facts, literals):
    """Expose already bound values as children, retaining each independent owner."""
    if len(facts) < 2:
        return None
    source = block["content"]["source"]
    label_source = facts[0].get("attribute_source")
    if not label_source or not label_source.get("text_span"):
        return None
    from .literal_readback import _identity

    def printed(token):
        origin = token["source"]
        if not origin.get("text_span"):
            return False
        a, b = origin["text_span"]
        return any(
            offset <= a <= b <= offset + len(raw) and raw[a - offset : b - offset] == token["text"]
            for offset, raw in literals.get(_identity(origin), ())
        )

    if _identity(source) != _identity(label_source) or any(
        f.get("attribute_source") != label_source for f in facts
    ):
        return None
    offset = source["text_span"][0]
    a, b = label_source["text_span"]
    if not source["text_span"][0] <= a < b <= source["text_span"][1]:
        return None
    label = _token(text, source, a - offset, b - offset)
    if label["text"] != facts[0]["attribute"]:
        return None
    children = []
    for fact in facts:
        period = fact["role_basis"]["period_selector"]
        cut = fact.get("value_source", {})
        if not cut.get("text_span") or _identity(cut) != _identity(source):
            return None
        lo, hi = cut["text_span"]
        if (
            not b <= lo < hi <= source["text_span"][1]
            or text[lo - offset : hi - offset] != fact["value"]
        ):
            return None
        child = {"kind": "field", "label": label, "value": {"text": fact["value"], "source": cut}}
        for key in ("unit", "currency", "note"):
            if key in fact.get("qualifier_sources", {}) and key in fact.get("qualifiers", {}):
                token = {
                    "text": fact["qualifiers"][key],
                    "source": fact["qualifier_sources"][key],
                }
                if printed(token):
                    child[key] = token
        if "unit" in child and "currency" not in child:
            unit = child["unit"]
            currency = read_unit_token(unit["text"])
            if currency["matched"] and currency["currency"]:
                child["currency"] = _token(unit["text"], unit["source"], *currency["currency_span"])
        if "source" not in period or "text" not in period or not printed(period):
            return None
        children.append(
            {
                "kind": "period",
                "label": {"text": period["text"], "source": period["source"]},
                "children": [child],
            }
        )
    if len({c["label"]["text"] for c in children}) != len(children):
        return None
    record = {
        "kind": "record",
        "row_path": [label],
        "source": source,
        "children": children,
        "comparison": "existing_typed_owners",
    }
    note = re.search(r"[（(](?:附[注註]|Notes?)\s*([0-9]+)[)）]$", label["text"], re.I)
    if note:
        record["note"] = _token(label["text"], label["source"], *note.span(1))
    return record


def attach_records(blocks, units, facts):
    from .literal_readback import _identity
    from .native_grid_fields import table_source_owns

    tables = [b for b in blocks if b["role"] == "table"]
    explicit_tables = {}
    by_table = defaultdict(list)
    ancestors = []
    dated = defaultdict(list)
    literals = defaultdict(list)
    for block, unit in zip(blocks, units, strict=True):
        if block.get("content"):
            source = block["content"]["source"]
            literals[_identity(source)].append((source["text_span"][0], unit["text"]))
    for fact in facts:
        basis = fact.get("role_basis")
        if isinstance(basis, dict) and isinstance(basis.get("period_selector"), dict):
            dated[_identity(fact.get("value_source", fact["source"]))].append(fact)
    for i, (block, unit) in enumerate(zip(blocks, units, strict=True)):
        if block["role"] == "table_cell":
            if unit.get("table_source"):
                table = unit["table_source"]
                identity = _identity(table)
                if identity not in explicit_tables:
                    explicit_tables[identity] = len(tables)
                    tables.append({"source": table, "scope": block["scope"]})
                owners = [explicit_tables[identity]]
            else:
                owners = [
                    n
                    for n, t in enumerate(tables)
                    if table_source_owns(t["source"], block["source"])
                ]
            if len(owners) == 1:
                by_table[owners[0]].append(
                    {
                        "index": i,
                        "text": unit["text"],
                        "source": block["source"],
                        "row": unit.get("row", block["source"].get("row")),
                        "col": unit.get(
                            "col", block["source"].get("col", block["source"].get("column"))
                        ),
                        **block["cell_structure"],
                    }
                )
        if block["role"] not in {"item", "list_item", "parent_label"}:
            ancestors.clear()
            continue
        parents = block.get("parents", [])
        ancestors = ancestors[: len(parents)]
        path = [p["token"] for p in ancestors]
        scope = block["scope"]
        local = all(p["scope"] == scope for p in ancestors) and [p["text"] for p in path] == parents
        row = read_list_record(unit["text"], block["content"]["source"]) if local else None
        if local and not row:
            row = _dated_fields(
                block, unit["text"], dated.get(_identity(block["source"]), ()), literals
            )
        if row:
            row["row_path"] = path + row["row_path"]
            row["scope"] = scope
            block["record"] = row
        if local:
            ancestors.append(
                {
                    "scope": scope,
                    "token": _token(unit["text"], block["source"], 0, len(unit["text"])),
                }
            )
    for n, cells in by_table.items():
        for i, record in _grid_records(tables[n]["source"], cells):
            fields = [
                f
                for c in record["children"]
                for f in (c["children"] if c["kind"] == "period" else [c])
            ]
            if len(_paths(record)) != len(fields) or not any(
                "number" in f or "status" in f for f in fields
            ):
                continue
            record["scope"] = tables[n]["scope"]
            blocks[i]["record"] = record
    _attach_unit_declarations(blocks, units)


def _unit_declaration(text, source):
    """Read a complete printed declaration, optionally followed by its explicit column list."""
    match = re.fullmatch(
        r"\s*([（(])?\s*(?:金额单位|金額單位|单位|單位|Units?)\s*[:：]\s*"
        r"([^()（）.。;；:\n：]+?)\s*([）)])?\s*(?:[.。]\s*"
        r"(?:(?:各|每)(?:年|期)(?:分别|分別)?列(?:示|出)?([^。.;；]+)[。.]?)?)?\s*",
        text,
        re.I,
    )
    if not match or {"（": "）", "(": ")", None: None}[match[1]] != match[3]:
        return None
    token = _token(text, source, *match.span(2))
    reading = read_unit_token(token["text"], token["source"])
    if not reading["matched"]:
        return None
    labels = [v.strip() for v in re.split(r"[、,，]", match[4])] if match[4] else []
    if labels and (len(set(labels)) < 2 or len(set(labels)) != len(labels)):
        return None
    return {
        "roles": {
            k: {"text": reading[k], "source": reading["sources"][k]}
            for k in ("unit", "currency", "currency_symbol")
            if reading[k]
        },
        "source": source,
        "labels": labels,
    }


def _attach_unit_declarations(blocks, units):
    from .literal_readback import _identity

    table_records = defaultdict(list)
    ancestors = set()
    for block in blocks:
        record = block.get("record")
        if record and not record.get("comparison"):
            ancestors.update(_identity(t["source"]) for t in record["row_path"][:-1])
            if record.get("table_source"):
                table_records[_identity(record["table_source"])].append(record)

    def apply(record, declaration):
        for field in _paths(record).values():
            if "number" in field and not any(
                k in field for k in ("unit", "currency", "currency_symbol")
            ):
                field.update(declaration["roles"])
                field["unit_declaration_source"] = declaration["source"]

    active, scope, schema, page = None, None, None, None
    for block, unit in zip(blocks, units, strict=True):
        role, source = block["role"], block["source"]
        declaration = (
            _unit_declaration(unit["text"], block["content"]["source"])
            if role in {"text", "item", "table_caption"} and block.get("content")
            else None
        )
        if declaration:
            active, scope, schema, page = declaration, block["scope"], None, source.get("page")
            continue
        if not active:
            continue
        if block["scope"] != scope or page is not None and source.get("page", page) != page:
            active = None
            continue
        table = source if role == "table" else unit.get("table_source")
        if table is not None:
            # A declaration belongs to just the immediately following physical table.
            if schema is None:
                for record in table_records.get(_identity(table), []):
                    if not active["labels"] or all(
                        [f["label"]["text"] for f in period["children"]] == active["labels"]
                        for period in record["children"]
                        if period["kind"] == "period"
                    ):
                        apply(record, active)
            active = None
            continue
        record = block.get("record")
        if (
            role in {"item", "list_item", "parent_label"}
            and _identity(source) in ancestors
            and not record
        ):
            continue
        if not record or record.get("comparison"):
            active = None
            continue
        periods = [
            (p["label"]["text"], tuple(f["label"]["text"] for f in p["children"]))
            for p in record["children"]
            if p["kind"] == "period"
        ]
        if (
            not periods
            or schema is not None
            and periods != schema
            or active["labels"]
            and any(list(labels) != active["labels"] for _, labels in periods)
        ):
            active = None
            continue
        schema = periods
        apply(record, active)


def _paths(record):
    from .ast_alignment import identity_text

    fields = {}
    for child in record["children"]:
        if child["kind"] == "field":
            fields[("", identity_text(child["label"]["text"]))] = child
        else:
            period = child["label"]["text"]
            for field in child["children"]:
                fields[
                    (
                        calendar_date(period) or identity_text(period),
                        identity_text(field["label"]["text"]),
                    )
                ] = field
    return fields


def resolved_matrix_issues(blocks, issues):
    """A named row and its exact candidate header cells can resolve a legacy matrix issue."""
    from .literal_readback import _identity

    witnesses = defaultdict(list)
    for block in blocks:
        record = block.get("record", {})
        if not record.get("table_source") or not record.get("row_axis"):
            continue
        bindings = [(t, [record["row_axis"]]) for t in record["row_path"]]
        for child in record["children"]:
            if child["kind"] == "field":
                bindings.append((child["value"], [child["label"]]))
            else:
                bindings.extend(
                    (f["value"], [child["label"], f["label"]]) for f in child["children"]
                )
        for token, headers in bindings:
            cell = token["source"]
            key = (_identity(cell), tuple(h["source"].get("cell") for h in headers))
            witnesses[key].append(
                {
                    "table": record["table_source"],
                    "row_path": record["row_path"],
                    "headers": headers,
                    "cell": cell,
                }
            )
    result = []
    for issue in issues:
        sources = issue.get("affected_data_sources", [])
        if (
            issue.get("reason") != "matrix_record_identity_unavailable"
            or issue.get("category") != "software_unsupported"
            or issue.get("binding_scope", {}).get("observation")
            != "record_identity_not_established"
            or len(sources) != 1
            or not issue.get("cell")
            or sources[0].get("cell") != issue["cell"]
            or not issue.get("header_ids")
        ):
            continue
        proved = [
            w
            for w in witnesses.get((_identity(sources[0]), tuple(issue["header_ids"])), [])
            if _identity(w["table"]) == _identity(issue["source"])
        ]
        if proved:
            result.append({"issue": issue, "witnesses": proved})
    return result


def _field_equal(left, right):
    from .ast_alignment import identity_text
    from .quantity import normalize_quantity, unit_key

    if not right:
        return False
    if "number" in right and any(left.get(k) and not right.get(k) for k in ("unit", "currency")):
        return None
    if right.get("reading") == "opaque":
        return (
            True
            if identity_text(left["value"]["text"]) == identity_text(right["value"]["text"])
            else None
        )

    def operand(field):
        if "number" not in field:
            return ("literal", identity_text(field["value"]["text"]))
        operator = field.get("operator", {}).get("text")
        operator = {"≤": "<=", "≥": ">="}.get(operator, operator)
        symbol = field.get("currency_symbol", {}).get("text")
        val = normalize_quantity(
            {
                "value": field["number"]["text"],
                "unit": field.get("unit", {}).get("text"),
                "currency": field.get("currency", {}).get("text"),
            }
        )
        return (
            ("quantity", operator, symbol, unit_key(val["unit"]), val["value"])
            if val["matched"]
            else ("literal", identity_text(field["value"]["text"]))
        )

    return operand(left) == operand(right)


def record_matches(required_blocks, actual_blocks):
    """Align complete records by printed path and scope, then inspect their field children."""
    from .ast_alignment import identity_text
    from .literal_readback import _identity

    def path(record):
        # A line wrap next to CJK book-title punctuation can be removed while
        # preserving every printed character of the name.
        return tuple(
            identity_text(
                re.sub(
                    r"(?<=[\u3400-\u9fff《（(])\s*[\r\n]+\s*(?=[\u3400-\u9fff（()）》])",
                    "",
                    t["text"],
                )
            )
            for t in record["row_path"]
        )

    def unfinished_parent(record):
        return any(
            token["text"].count(left) > token["text"].count(right)
            for token in record["row_path"][:-1]
            for left, right in (("《", "》"), ("（", "）"), ("(", ")"))
        )

    actual_by_label = defaultdict(list)
    locations = defaultdict(list)
    for i, block in enumerate(actual_blocks):
        if (record := block.get("record")) and not record.get("comparison"):
            actual_by_label[path(record)[-1]].append((i, record))
        locations[_identity(block["source"])].append(i)
    result = {}
    for i, block in enumerate(required_blocks):
        wanted = block.get("record")
        if (
            not wanted
            or wanted.get("comparison")
            or block.get("comparison_role") == "typed_order_anchor"
            or block["content"]["source"] != wanted["source"]
        ):
            continue
        candidates = actual_by_label.get(path(wanted)[-1], [])
        if not candidates:
            continue
        expected_scope = [identity_text(s) for s in wanted["scope"]]
        own_rows = [(a, r) for a, r in candidates if path(wanted) == path(r)]
        same = [
            (a, r) for a, r in own_rows if expected_scope == [identity_text(s) for s in r["scope"]]
        ]
        hit = {
            "required": wanted,
            "candidate_sources": [rec["source"] for _, rec in candidates],
            "actual": None,
            "spans": [],
            "components": [],
            "layout_correct": False,
            "value_used_for_location": False,
        }
        result[i] = hit
        local_only = False
        compatible = []
        if not same:
            # Missing intermediate headings do not contradict a locally named
            # record. They also cannot prove the full required scope.
            for a, r in own_rows:
                observed = [identity_text(s) for s in r["scope"]]
                short, long = sorted((observed, expected_scope), key=len)
                remaining = iter(long)
                if (
                    len(short) < len(long)
                    and (not short or short[-1] == long[-1])
                    and all(label in remaining for label in short)
                ):
                    compatible.append((a, r))
            if len(compatible) == 1:
                same = compatible
                local_only = True
        if len(same) != 1:
            missing_context = any(
                (wanted["scope"] and not r["scope"])
                or len(path(r)) < len(path(wanted))
                or unfinished_parent(r)
                for _, r in candidates
            )
            hit["status"] = "unresolved" if same or missing_context or compatible else "conflict"
            hit["reason"] = (
                "record_path_ambiguous_or_unknown"
                if hit["status"] == "unresolved"
                else "record_parent_or_scope_conflict"
            )
            continue
        anchor, found = same[0]
        expected_fields, actual_fields = _paths(wanted), _paths(found)
        # Each expected leaf needs its own witness. A separate printed column
        # can still be studied as additional output; it does not refute this claim.
        for key, expected in expected_fields.items():
            actual = actual_fields.get(key)
            equal = _field_equal(expected, actual)
            hit["components"].append(
                {
                    "path": list(key),
                    "expected": expected,
                    "actual": actual,
                    "credit": None if equal is None else int(equal),
                    "status": "unresolved"
                    if equal is None
                    else "entailed"
                    if equal
                    else "conflict",
                    "weight": expected.get("source_weight", 1),
                    "value_used_for_location": False,
                }
            )
        hit["extra_paths"] = [list(k) for k in actual_fields if k not in expected_fields]
        if local_only:
            hit.update(
                status="unresolved",
                reason="record_outer_scope_unproven",
                observed_record=found,
                expected_scope=wanted["scope"],
                observed_scope=found["scope"],
            )
            # Preserve local child decisions for inspection without claiming
            # the data occurrence in the unproved outer scope.
            continue
        hit["layout_correct"] = expected_fields.keys() <= actual_fields.keys()
        credits = [c["credit"] for c in hit["components"]]
        passed = hit["layout_correct"] and all(credits)
        hit.update(
            status="equivalent"
            if passed
            else "unresolved"
            if None in credits and 0 not in credits
            else "conflict",
            reason="source_bound_record_fields",
            actual=found,
        )
        for key in expected_fields:
            if key not in actual_fields:
                continue
            origin = actual_fields[key]["value"]["source"]
            ids = locations[_identity(origin)] if found.get("table_source") else [anchor]
            if len(ids) != 1:
                raise ValueError("record field has no unique original AST location")
            hit["spans"].append(
                {"actual_index": ids[0], "source": origin, "text_span": origin["text_span"]}
            )
        hit["spans"].sort(key=lambda s: (s["actual_index"], s["text_span"][0]))
    # A list group can itself have a fixed text/layout owner. Its name may be
    # printed once in a spanning source cell serving several proven rows.
    parents = defaultdict(dict)

    def location(token):
        s = token["source"]
        return (_identity(s), tuple(s["text_span"]))

    for hit in result.values():
        if hit["actual"]:
            for own, found in zip(
                hit["required"]["row_path"][:-1], hit["actual"]["row_path"][:-1], strict=True
            ):
                parents[location(own)][location(found)] = found
    for i, block in enumerate(required_blocks):
        if i in result or not block.get("content") or block["role"] not in {"item", "parent_label"}:
            continue
        source = block["content"]["source"]
        options = parents.get((_identity(source), tuple(source["text_span"])), {})
        if len(options) != 1:
            continue
        found = next(iter(options.values()))
        ids = locations[_identity(found["source"])]
        if len(ids) != 1:
            continue
        token = {"text": "".join(n["text"] for n in block["content"]["children"]), "source": source}
        result[i] = {
            "required": token,
            "actual": found,
            "candidate_sources": [found["source"]],
            "spans": [
                {
                    "actual_index": ids[0],
                    "source": found["source"],
                    "text_span": found["source"]["text_span"],
                }
            ],
            "components": [{"expected": token, "actual": found, "credit": 1}],
            "layout_correct": True,
            "reason": "source_bound_record_parent",
            "status": "equivalent",
            "value_used_for_location": False,
        }
    # Two original requirements cannot claim the same candidate data occurrence.
    capacity = defaultdict(set)
    for i, hit in result.items():
        for s in hit["spans"]:
            capacity[(_identity(s["source"]), tuple(s["text_span"]))].add(i)
    for owners in capacity.values():
        if len(owners) > 1:
            for i in owners:
                result[i].update(
                    status="unresolved",
                    reason="record_occurrence_capacity",
                    actual=None,
                    spans=[],
                    components=[],
                    layout_correct=False,
                )
    return result
