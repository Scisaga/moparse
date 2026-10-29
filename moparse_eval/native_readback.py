"""Scoring-only readback of saved native declarations, without reference inputs.

This reader neither merges tables nor interprets their headers, units or values.
It re-reads explicit metadata and markup in derived views, leaving frozen
execution pages, text and timing unchanged. Derived cells receive metadata,
never rewritten text. DocVortex continuation edges retain
predecessor direction; heading roles without levels remain unavailable.
"""

from __future__ import annotations

import copy
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from typing import Any

from .adapters import _docling_cell_fields, _docling_reference
from .native_relations import HEADING_SCOPE_EVIDENCE, heading_evidence, native_relations

READBACK_VERSION = "native-explicit-relations-and-table-fields-3"
SOURCE_EVIDENCE = {
    "package": "docvortex", "version": "0.5.16",
    "schema_sha256": "f1cb73d0f29104df10a59e0663b2884059354ce59c531402a362a4415854b4f4",
    "planner_sha256": "95c3dbd59600ea66ab96e2e1009b283b4b5636071d62e85ec659502a850f8ecc",
    "rule": "schema.TableBlock; render._internal.common.planner._merge_continued_table_blocks",
}


def _native_object(native: Mapping[str, Any], pointer: Any) -> Mapping[str, Any] | None:
    """Resolve an exact saved JSON pointer; no search by text, index or location."""
    if not isinstance(pointer, str) or not pointer.startswith("#/"):
        return None
    value: Any = native
    for encoded in pointer[2:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(value, Mapping) and token in value:
            value = value[token]
        elif isinstance(value, list) and token.isdecimal() and int(token) < len(value):
            value = value[int(token)]
        else:
            return None
    return value if isinstance(value, Mapping) else None


def _read_docling_table_fields(derived: dict[str, Any], native: Mapping[str, Any] | None
                              ) -> dict[str, Any]:
    """Add missing metadata to uniquely identified saved cells, never text or order."""
    result: dict[str, Any] = {
        "reader_version": READBACK_VERSION, "status": "native_missing" if native is None else "not_applicable",
        "scope": "explicit_docling_cell_fields_and_rich_references_no_text_rewrite",
        "records": [],
        "limitations": [
            "Rich-cell text is supplemental native evidence; existing cell.text is unchanged.",
            "Multiple text leaves, pictures and unsupported objects are not flattened into cell text.",
            "No missing cells, header semantics or grid structure are generated.",
        ],
    }
    if native is None:
        return result
    blocks = [block for page in derived.get("pages", []) for block in page.get("blocks", [])]
    items = [*derived.get("native_containers", []), *blocks,
             *(cell for block in blocks for cell in block.get("cells", []) if isinstance(cell, Mapping))]
    path_counts = Counter(item.get("native_path") for item in items if isinstance(item.get("native_path"), str))
    id_counts = Counter(item.get("id") for item in items if isinstance(item.get("id"), str))

    def unique(item: Mapping[str, Any]) -> bool:
        return (isinstance(item.get("native_path"), str) and path_counts[item["native_path"]] == 1
                and isinstance(item.get("id"), str) and id_counts[item["id"]] == 1)

    def supplement(item: dict[str, Any], fields: Mapping[str, Any]) -> tuple[list[str], list[str]]:
        added, conflicts = [], []
        for key, value in fields.items():
            if key not in item:
                item[key] = copy.deepcopy(value)
                added.append(key)
            elif item[key] != value:
                conflicts.append(key)
        return sorted(added), sorted(conflicts)

    for block in blocks:
        pointer = block.get("native_path")
        raw = _native_object(native, pointer)
        if raw is None or not isinstance(raw.get("data"), Mapping):
            continue
        self_ref = raw.get("self_ref")
        if not isinstance(self_ref, str) or not self_ref.startswith("#/tables/"):
            continue
        record: dict[str, Any] = {"native_path": pointer, "status": "unknown", "fields_added": []}
        result["records"].append(record)
        if not unique(block) or not pointer.endswith(self_ref[1:]):
            record["reason"] = "table_native_identity_not_unique"
            continue
        document_pointer = pointer[:-len(self_ref) + 1]
        document = _native_object(native, document_pointer)
        if document is None:
            record["reason"] = "native_document_unresolved"
            continue
        data = raw["data"]
        table_fields = {key: copy.deepcopy(data[key]) for key in ("num_rows", "num_cols", "orientation")
                        if key in data}
        if table_fields:
            if isinstance(block.get("native_table_data"), dict):
                added, conflicts = supplement(block["native_table_data"], table_fields)
                added = ["native_table_data." + key for key in added]
                conflicts = ["native_table_data." + key for key in conflicts]
            else:
                added, conflicts = supplement(block, {"native_table_data": table_fields})
            record.update(fields_added=added, field_conflicts=conflicts)
        record["status"] = "read"
        raw_cells = data.get("table_cells")
        if not isinstance(raw_cells, list):
            record.update(status="unknown", reason="native_table_cells_not_a_list")
            continue
        for cell in block.get("cells", []):
            if not isinstance(cell, dict):
                continue
            cell_pointer = cell.get("native_path")
            cell_record: dict[str, Any] = {"native_path": cell_pointer, "status": "unknown", "fields_added": []}
            result["records"].append(cell_record)
            prefix = pointer + "/data/table_cells/"
            index = cell_pointer[len(prefix):] if isinstance(cell_pointer, str) and cell_pointer.startswith(prefix) else ""
            if (not unique(cell) or not index.isdecimal() or str(int(index)) != index
                    or int(index) >= len(raw_cells) or cell.get("parent_id", block["id"]) != block["id"]):
                cell_record["reason"] = "cell_native_identity_not_unique"
                continue
            raw_cell = raw_cells[int(index)]
            if not isinstance(raw_cell, Mapping):
                cell_record["reason"] = "native_cell_not_an_object"
                continue
            if "native_id" in cell and "id" in raw_cell and cell["native_id"] != raw_cell["id"]:
                cell_record["reason"] = "conflicting_native_cell_identity"
                continue
            fields = _docling_cell_fields(raw_cell, document, document_pointer)
            added, conflicts = supplement(cell, fields)
            cell_record.update(status="read", fields_added=added, field_conflicts=conflicts)
            if "native_rich_content" in fields:
                cell_record["rich_content_status"] = fields["native_rich_content"]["status"]
    if result["records"]:
        result["status"] = "read"
        derived["native_table_field_evidence"] = copy.deepcopy(result)
    return result


def _relation_view(observation: dict[str, Any], native: Mapping[str, Any] | None
                   ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Supplement metadata only in a temporary view, through unique native paths."""
    view = {**observation, "pages": [
        {**page, "blocks": [dict(block) for block in page.get("blocks", [])]}
        for page in observation.get("pages", [])
    ], "native_containers": [dict(item) for item in observation.get("native_containers", [])]}
    items = [*view["native_containers"],
             *(block for page in view["pages"] for block in page["blocks"])]
    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if isinstance(item.get("native_path"), str):
            by_path[item["native_path"]].append(item)
    records = []
    for item in items:
        pointer = item.get("native_path")
        raw = _native_object(native, pointer) if native is not None else None
        if raw is None:
            continue
        if len(by_path[pointer]) != 1:
            records.append({"native_path": pointer, "status": "unknown",
                            "reason": "observation_native_path_not_unique", "fields_added": []})
            continue
        fields: dict[str, Any] = {}
        if "level" in raw:
            fields["level"] = raw["level"]
        for source in ("research_export_markdown", "markdown"):
            if isinstance(raw.get(source), str):
                fields["native_export_markdown"] = raw[source]
                fields["native_export_markdown_path"] = pointer + "/" + source
                break
        self_ref = raw.get("self_ref")
        prefix = (pointer[:-len(self_ref) + 1] if isinstance(self_ref, str)
                  and self_ref.startswith("#/") and pointer.endswith(self_ref[1:]) else None)

        def referenced_id(value: Any, document_prefix: str | None = prefix) -> str | None:
            reference = _docling_reference(value) if isinstance(value, Mapping) else value
            if not isinstance(reference, str):
                return None
            path = (document_prefix + reference[1:] if document_prefix is not None and reference.startswith("#/")
                    else reference)
            targets = by_path.get(path, [])
            return targets[0].get("id") if len(targets) == 1 else None

        # Docling's self_ref fixes the document prefix. Only existing, unique
        # observed objects may satisfy its explicit references.
        if prefix is not None:
            refs = {}
            for name in ("captions", "footnotes", "references"):
                if isinstance(raw.get(name), list):
                    refs[name] = [ident for value in raw[name]
                                  if (ident := referenced_id(value)) is not None]
            if refs:
                fields["native_references"] = refs
            if isinstance(raw.get("children"), list):
                fields["native_children"] = [ident for value in raw["children"]
                                             if (ident := referenced_id(value)) is not None]
            if (parent := referenced_id(raw.get("parent"))) is not None:
                fields["parent_id"] = parent
        added = sorted(key for key in fields if key not in item)
        for key in added:
            item[key] = copy.deepcopy(fields[key])
        if isinstance(fields.get("native_references"), Mapping) and isinstance(item.get("native_references"), Mapping):
            missing = {key: values for key, values in fields["native_references"].items()
                       if key not in item["native_references"]}
            if missing:
                item["native_references"] = {**item["native_references"], **copy.deepcopy(missing)}
                added.extend(f"native_references.{key}" for key in sorted(missing))
        if added:
            records.append({"native_path": pointer, "status": "read", "fields_added": added})
    return view, records


def _refresh_explicit_relations(derived: dict[str, Any], native: Mapping[str, Any] | None
                                ) -> dict[str, Any]:
    view, metadata = _relation_view(derived, native)
    original = list(derived.get("relations", []))
    generated = [edge for edge in original if edge.get("type") == "heading_of"
                 and edge.get("evidence") == HEADING_SCOPE_EVIDENCE]
    view["relations"] = [edge for edge in original if edge not in generated]
    refreshed = native_relations(view)
    triples = {(edge.get("type"), edge.get("source"), edge.get("target")) for edge in refreshed}
    blocks = [heading_evidence(block) for page in view.get("pages", []) for block in page.get("blocks", [])]
    by_id = {block["id"]: block for block in blocks}
    withdrawn = [{**edge, "withdrawal_reason": (
        "empty_markdown_heading" if by_id.get(edge.get("source"), {}).get("status") == "empty_markdown_heading"
        else "generated_heading_scope_no_longer_supported")}
        for edge in generated if (edge.get("type"), edge.get("source"), edge.get("target")) not in triples]
    evidence = {
        "reader_version": READBACK_VERSION,
        "scope": "explicit_native_metadata_references_and_single_heading_markup_only_no_content_repair",
        "heading_blocks": blocks, "metadata_readback": metadata,
        "limitations": [
            "Type-only titles have no inferred level; header/footer roles remain page furniture.",
            "Mixed-block Markdown scope is not converted to an invented block-level heading.",
            "Caption edges retain their native caption-to-container direction; no reference-driven binding.",
            "No paired_with or row_header edges are inferred from adjacency, text or grid positions.",
        ],
    }
    derived["relations"] = refreshed
    derived["native_relation_evidence"] = evidence
    old_triples = {(edge.get("type"), edge.get("source"), edge.get("target")) for edge in original}
    return {
        "metadata_readback": metadata, "heading_blocks": blocks,
        "added_relations": [edge for edge in refreshed
                            if (edge.get("type"), edge.get("source"), edge.get("target")) not in old_triples],
        "withdrawn_relations": withdrawn,
    }


def _ordered_indices(items: list[Any], key: str) -> bool:
    values = [item.get(key) if isinstance(item, Mapping) else None for item in items]
    if any(type(value) is not int for value in values):
        return False
    indices = [value for value in values if isinstance(value, int)]
    return all(value >= 0 for value in indices) and all(
        left < right for left, right in zip(indices, indices[1:], strict=False)
    )


def _nested_continuation(value: Any) -> bool:
    if isinstance(value, Mapping):
        return "continues_prev" in value or _nested_continuation(value.get("content"))
    if isinstance(value, list):
        return any(_nested_continuation(child) for child in value)
    return False


def _nested_tables(block: Mapping[str, Any], pointer: str) -> Iterator[tuple[str, Mapping[str, Any]]]:
    children = block.get("content")
    if not isinstance(children, list):
        return
    for position, child in enumerate(children):
        if not isinstance(child, Mapping):
            continue
        child_pointer = f"{pointer}/content/{position}"
        if child.get("type") == "table":
            yield child_pointer, child
        yield from _nested_tables(child, child_pointer)


def _malformed_block_tables(value: Any, pointer: str) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """Retain explicit table flags in a malformed view without interpreting order."""
    if isinstance(value, Mapping):
        if value.get("type") == "table":
            yield pointer, value
        for key, child in value.items():
            token = str(key).replace("~", "~0").replace("/", "~1")
            yield from _malformed_block_tables(child, pointer + "/" + token)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _malformed_block_tables(child, f"{pointer}/{index}")


def _page_table_ids(observation: Mapping[str, Any], prefix: str) -> list[str]:
    """Scope uncertainty to explicitly observed tables in this saved raw page."""
    identities: set[str] = set()
    for item in observation.get("native_containers") or []:
        path = item.get("native_path")
        if item.get("label") == "table" and isinstance(path, str) and path.startswith(prefix + "/"):
            identities.update(value for value in (item.get("id"), path) if isinstance(value, str))
    for page in observation.get("pages") or []:
        for block in page.get("blocks") or []:
            parent = block.get("native_table_container")
            if isinstance(parent, str) and parent.startswith(prefix + "/"):
                identities.add(parent)
    return sorted(identities)


def _valid_table(block: Mapping[str, Any]) -> bool:
    children = block.get("content")
    flag = block.get("continues_prev")
    merge = block.get("cell_merge")
    return bool(
        block.get("type") == "table" and isinstance(children, list)
        and sum(isinstance(child, Mapping) and child.get("type") == "table_body"
                for child in children) == 1
        and all(isinstance(child, Mapping) and child.get("type") in {
            "table_body", "table_caption", "table_footnote",
        } for child in children)
        and not _nested_continuation(children)
        and (flag is None or type(flag) is bool)
        and (merge is None or isinstance(merge, list)
             and all(type(value) is int and value in {0, 1} for value in merge))
    )


def _document_tables(document: Mapping[str, Any], pointer: str) -> dict[tuple[int, int], dict[str, Any]]:
    pages = document.get("pages")
    if document.get("schema") != "docvortex.middle" or not isinstance(pages, list):
        return {}
    ordered_pages = _ordered_indices(pages, "page_idx")
    inventory: dict[tuple[int, int], dict[str, Any]] = {}
    previous: dict[str, Any] | None = None
    for page_position, page in enumerate(pages):
        if not isinstance(page, Mapping) or type(page.get("page_idx")) is not int:
            previous = None
            continue
        page_idx = page["page_idx"]
        blocks = page.get("blocks")
        if not isinstance(blocks, list):
            previous = None
            continue
        ordered_blocks = _ordered_indices(blocks, "index")
        for block_position, block in enumerate(blocks):
            if not isinstance(block, Mapping) or block.get("type") != "table":
                continue
            index = block.get("index")
            if type(index) is not int:
                previous = {"valid": False}
                continue
            valid = ordered_pages and ordered_blocks and _valid_table(block)
            record = {
                "document_table_path": f"{pointer}/pages/{page_position}/blocks/{block_position}",
                "page_idx": page_idx, "block_index": index, "valid": valid,
                "continues_prev": block.get("continues_prev"),
                "cell_merge": copy.deepcopy(block.get("cell_merge")),
                "previous_document_table_path": None, "status": "not_declared",
                "reason": "continues_prev_false" if block.get("continues_prev") is False else "continues_prev_null",
            }
            if not valid:
                record.update(status="unknown", reason="invalid_native_table_or_order")
            elif block.get("continues_prev") is True:
                reason = ("no_previous_table" if previous is None else
                          "previous_table_invalid" if not previous["valid"] else
                          "previous_table_same_page" if previous["page_idx"] == page_idx else None)
                record.update(status="unknown" if reason else "declared", reason=reason)
                if reason is None and previous is not None:
                    record["previous_document_table_path"] = previous["document_table_path"]
            inventory[(page_idx, index)] = record
            # An invalid apparent table is a barrier, not permission to choose
            # an older table by its content or visual similarity.
            previous = record
    return inventory


def _observation_table_id(observation: Mapping[str, Any], pointer: str) -> str | None:
    containers = observation.get("native_containers") or []
    counts = Counter(str(item.get("id")) for item in containers if isinstance(item, Mapping))
    found = [item for item in containers if isinstance(item, Mapping)
             and item.get("native_path") == pointer and item.get("label") == "table"]
    if found:
        if len(found) == 1 and isinstance(found[0].get("id"), str) and counts[found[0]["id"]] == 1:
            return str(found[0]["id"])
        return None
    # Existing readers also explicitly preserve a body block's native parent.
    identifiers = {block.get("native_table_container")
                   for page in observation.get("pages", []) for block in page.get("blocks", [])
                   if block.get("native_table_container") == pointer
                   and isinstance(block.get("native_path"), str)
                   and block["native_path"].startswith(pointer + "/content/")}
    return pointer if identifiers == {pointer} else None


def read_native_relations(observation: Mapping[str, Any], native: Mapping[str, Any] | None
                          ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a new observation and auditable native-only readback diagnostics."""
    derived = copy.deepcopy(dict(observation))
    table_fields = _read_docling_table_fields(derived, native)
    relation_readback = _refresh_explicit_relations(derived, native)
    diagnostic: dict[str, Any] = {
        "reader_version": READBACK_VERSION, "source_evidence": copy.deepcopy(SOURCE_EVIDENCE),
        "status": "native_missing" if native is None else "not_applicable", "records": [],
        "scope": "explicit_heading_markup_and_metadata_native_references_docling_table_fields_and_docvortex_table_continuation_no_semantic_binding",
        "relation_readback": relation_readback,
        "table_field_readback": table_fields,
    }
    if native is None:
        return derived, diagnostic
    documents = native.get("documents") or []
    inventories = {f"#/documents/{index}": _document_tables(document, f"#/documents/{index}")
                   for index, document in enumerate(documents) if isinstance(document, Mapping)
                   and document.get("schema") == "docvortex.middle"}
    records: list[dict[str, Any]] = []
    by_document_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page_position, page in enumerate(native.get("pages") or []):
        if not isinstance(page, Mapping) or not isinstance(page.get("raw"), Mapping):
            continue
        raw = page["raw"]
        document_path = raw.get("native_document")
        inventory = inventories.get(document_path) if isinstance(document_path, str) else None
        if inventory is None and page.get("branch") != "mineru":
            continue
        raw_blocks = raw.get("blocks")
        raw_pointer = f"#/pages/{page_position}/raw/blocks"
        if not isinstance(raw_blocks, list):
            for pointer, block in _malformed_block_tables(raw_blocks, raw_pointer):
                if block.get("continues_prev") is not True:
                    continue
                records.append({
                    "native_path": pointer, "table_id": _observation_table_id(observation, pointer),
                    "document_path": document_path, "document_table_path": None,
                    "continues_prev": True, "cell_merge": copy.deepcopy(block.get("cell_merge")),
                    "previous_table_id": None, "status": "unknown", "reason": "native_blocks_not_a_list",
                    "unresolved_observation_table_ids": _page_table_ids(observation, raw_pointer),
                })
            continue
        ordered_raw_blocks = _ordered_indices(raw_blocks, "index")
        for position, block in enumerate(raw_blocks):
            if not isinstance(block, Mapping):
                continue
            pointer = f"#/pages/{page_position}/raw/blocks/{position}"
            for nested_pointer, nested in _nested_tables(block, pointer):
                records.append({
                    "native_path": nested_pointer,
                    "table_id": _observation_table_id(observation, nested_pointer),
                    "document_path": document_path, "document_table_path": None,
                    "continues_prev": nested.get("continues_prev"),
                    "cell_merge": copy.deepcopy(nested.get("cell_merge")), "previous_table_id": None,
                    "status": "unknown", "reason": "nested_table_continuation_forbidden",
                })
            if block.get("type") != "table":
                continue
            table_id = _observation_table_id(observation, pointer)
            record = {
                "native_path": pointer, "table_id": table_id, "document_path": document_path,
                "document_table_path": None, "continues_prev": block.get("continues_prev"),
                "cell_merge": copy.deepcopy(block.get("cell_merge")),
                "previous_table_id": None, "status": "unknown",
                "reason": "native_document_unresolved" if inventory is None else "native_identity_unresolved",
            }
            page_index, block_index = raw.get("page_idx"), block.get("index")
            canonical = None
            if inventory is not None and type(page_index) is int and type(block_index) is int:
                canonical = inventory.get((page_index, block_index))
            if canonical:
                record.update(copy.deepcopy(canonical))
                if not _valid_table(block) or any(block.get(field) != canonical[field]
                                                for field in ("continues_prev", "cell_merge")):
                    record.update(status="unknown", valid=False, reason="conflicting_or_invalid_native_view")
                by_document_table[canonical["document_table_path"]].append(record)
            if not ordered_raw_blocks:
                record.update(status="unknown", valid=False, reason="invalid_native_raw_block_order")
            records.append(record)
    relations = derived.setdefault("relations", [])
    for record in records:
        canonical_path = record.get("document_table_path")
        if not record["table_id"] or canonical_path and len(by_document_table[canonical_path]) != 1:
            record.update(status="unknown", reason="native_table_view_not_unique")
        if record["status"] != "declared":
            continue
        antecedents = by_document_table.get(record["previous_document_table_path"], [])
        if len(antecedents) != 1 or not antecedents[0]["table_id"] or not antecedents[0].get("valid"):
            record.update(status="unknown", reason="previous_native_view_not_unique")
            continue
        previous = antecedents[0]
        record.update(status="linked", previous_table_id=previous["table_id"])
        edge = {
            "type": "continues", "source": previous["table_id"], "target": record["table_id"],
            "evidence": "docvortex.continues_prev", "reader_version": READBACK_VERSION,
            "native_path": record["native_path"] + "/continues_prev",
            "source_native_path": previous["document_table_path"],
            "target_native_path": record["document_table_path"],
        }
        if edge not in relations:
            relations.append(edge)
    derived["native_table_declarations"] = records
    diagnostic.update(status="read" if records or table_fields["status"] == "read" else "not_applicable",
                      records=copy.deepcopy(records))
    return derived, diagnostic
