"""Read saved Middle JSON only; this is not an official DocVortex Typed projection."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping

from app.adapters.native_config import CONFIGURATIONS
from app.adapters.native_readers import (
    NativeReadError,
    _position,
    audit_copy,
    read_mineru,
    resolve_pointer,
)

CONTAINERS = {"image", "table", "chart", "code", "list", "index"}
MEDIA_FIELDS = ("image_base64", "image_path", "image_url", "image_uri")
STATE_FIELDS = (
    "status",
    "error",
    "errors",
    "warnings",
    "timed_out",
    "truncated",
    "stop_reason",
    "processed",
    "unprocessed_pages",
    "length_limit_reached",
)


def source_page(native, entry):
    """Validate this saved executor's explicit physical-page/Middle binding."""
    raw = entry.get("raw")
    if not isinstance(raw, Mapping):
        raise NativeReadError("mineru_raw_not_an_object")
    local = raw.get("page_idx")
    if type(local) is not int or local < 0 or local != entry["page"] - 1:
        raise NativeReadError("mineru_saved_physical_page_mapping_conflict")
    ref = raw.get("native_document")
    if not isinstance(ref, str) or not re.fullmatch(r"#/documents/\d+", ref):
        raise NativeReadError("mineru_document_pointer_outside_branch")
    document = resolve_pointer(native, ref)
    if not isinstance(document, Mapping) or document.get("schema") != "docvortex.middle":
        raise NativeReadError("mineru_primary_middle_document_unavailable")
    if document.get("schema_version") != "2.0":
        raise NativeReadError("mineru_middle_schema_not_supported")
    extensions = document.get("extensions")
    extension = extensions.get("mineru") if isinstance(extensions, Mapping) else None
    if not isinstance(extension, Mapping):
        raise NativeReadError("mineru_saved_mode_metadata_unavailable")
    expected = CONFIGURATIONS[native["pipeline"]]["mineru_tier"]
    if extension.get("tier") != expected or extension.get("parse_mode") != "txt":
        raise NativeReadError("mineru_saved_tier_or_mode_conflict")
    pages = document.get("pages")
    if not isinstance(pages, list):
        raise NativeReadError("mineru_middle_pages_unavailable")
    matches = [
        (i, p)
        for i, p in enumerate(pages)
        if isinstance(p, Mapping) and type(p.get("page_idx")) is int and p["page_idx"] == local
    ]
    if len(matches) != 1 or not isinstance(matches[0][1].get("blocks"), list):
        raise NativeReadError("mineru_middle_page_or_blocks_not_unique")
    owners = [
        p
        for p in native.get("pages", [])
        if isinstance(p, Mapping)
        and p.get("branch") == "mineru"
        and isinstance(p.get("raw"), Mapping)
        and p["raw"].get("native_document") == ref
        and p["raw"].get("page_idx") == local
    ]
    if len(owners) != 1:
        raise NativeReadError("mineru_middle_page_ownership_conflict")
    pos, page = matches[0]
    return page, f"{ref}/pages/{pos}", document


def indexed(items):
    return (
        bool(items)
        and all(
            isinstance(x, Mapping) and type(x.get("index")) is int and x["index"] >= 0
            for x in items
        )
        and len({x["index"] for x in items}) == len(items)
    )


def media_declaration(node):
    return {k: audit_copy(node[k]) for k in MEDIA_FIELDS if node.get(k) is not None}


def read_middle_page(native, entry):
    page, pointer, document = source_page(native, entry)
    number, local = entry["page"], page["page_idx"]
    containers: list[dict] = []
    blocks = read_mineru(page, number, pointer, containers=containers, primary_only=True)
    paths = {}

    def order(items, path, prefix, known):
        good = known and indexed(items)
        for index, node in enumerate(items):
            own = f"{path}/{index}"
            node = node if isinstance(node, Mapping) else {}
            sequence = (*prefix, node["index"] if good else index)
            paths[own] = (
                sequence,
                "native_index" if good else "native_array_order_unknown_reading_order",
            )
            if isinstance(node.get("content"), list) and node.get("type") in CONTAINERS:
                order(node["content"], own + "/content", sequence, good)

    order(page["blocks"], pointer + "/blocks", (number,), True)
    for block in [*containers, *blocks]:
        source_node = resolve_pointer(native, block["native_path"])
        node = source_node if isinstance(source_node, Mapping) else {}
        seq, basis = paths[block["native_path"]]
        block.update(
            native_payload=audit_copy(resolve_pointer(native, block["native_path"])),
            branch_page=local,
            page=number,
            source_view="docvortex.middle",
            native_sequence=list(seq),
            order_basis=basis,
            native_block_type=node.get("type"),
            native_block_id=copy.deepcopy(node.get("block_id")),
            native_fields={
                k: audit_copy(node[k]) for k in node if k not in ("content", *MEDIA_FIELDS)
            },
            native_content=audit_copy(node.get("content")),
            native_media_declaration=media_declaration(node),
        )
        for key in ("continues_prev", "merge_prev"):
            if key in node:
                block[key] = audit_copy(node[key])
        if block in blocks and block.get("read_error"):
            # A malformed inline region is still this native type/location;
            # its raw payload and valid neighboring regions remain available.
            block.update(
                kind=str(node.get("type", "unknown")),
                bbox=node.get("bbox"),
                text_format=None
                if not isinstance(source_node, Mapping)
                else "html"
                if node.get("type") == "table_body"
                else "plain",
            )
            if isinstance(node.get('content'), str):
                block['text'] = node['content']
            _position(block, system="normalized", page=number)
        if block.get("read_error_category") == "engineering_failure":
            raise RuntimeError(
                "MinerU JSON projection engineering failure: " + str(block["read_error"])
            )
        for cell in block.get("cells", []):
            cell["source_locator"] = {
                "json_pointer": block["native_path"] + "/content",
                "syntax_path": cell["native_path"].split("::html", 1)[-1],
                "kind": "primary_html_projection",
                "independent_ocr_cell": False,
            }
    # Table continuation is a declaration on the container, not a cell/header
    # partition. Retain it; this source-free projection cannot certify a join.
    for block in blocks:
        parent = resolve_pointer(native, block.get("parent_id"))
        if block.get("kind") == "table_body" and isinstance(parent, Mapping):
            block["native_table_declaration"] = {
                k: audit_copy(parent[k]) for k in ("continues_prev", "cell_merge") if k in parent
            }
    return (
        blocks,
        containers,
        {
            "native_page_pointer": pointer,
            "branch_page": local,
            "primary_view": "docvortex.middle",
            "projection": "saved_json_only_not_official_typed",
            "official_typed_validation": "not_executed",
            "producer": audit_copy(document["metadata"].get("producer"))
            if isinstance(document.get("metadata"), Mapping)
            else None,
            "mode": audit_copy(document.get("extensions", {}).get("mineru")),
            "source_envelope": {k: audit_copy(document[k]) for k in STATE_FIELDS if k in document},
        },
    )


def audit_objects(native, entry, position):
    """Retain derived blocks/content_list separately, without answer merging."""
    records = []
    _, pointer, document = source_page(native, entry)
    ref = pointer.split("/pages/", 1)[0]
    raw = entry["raw"]

    def add(path, value, purpose):
        records.append(
            {
                "native_path": path,
                "view": "mineru_audit",
                "purpose": purpose,
                "payload": audit_copy(value),
                "used_as_answer": False,
            }
        )

    for i, node in enumerate(raw.get("blocks", []) if isinstance(raw.get("blocks"), list) else []):
        add(f"#/pages/{position}/raw/blocks/{i}", node, "saved_page_projection")

    # Native schema does not promise cross-view IDs. Keep each occurrence,
    # including identical literals, even when no primary counterpart is known.
    def lists(node, path):
        if isinstance(node, Mapping):
            for k, v in node.items():
                own = path + "/" + str(k).replace("~", "~0").replace("/", "~1")
                if k == "content_list":
                    if isinstance(v, list):
                        for i, item in enumerate(v):
                            add(own + "/" + str(i), item, "content_list_unbound_derived_view")
                    else:
                        add(own, v, "malformed_content_list_audit")
                elif isinstance(v, (dict, list)):
                    lists(v, own)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                lists(v, path + "/" + str(i))

    lists(raw, f"#/pages/{position}/raw")
    # Document-level auxiliary views are owned by its first selected entry.
    first = next(
        p
        for p in native["pages"]
        if isinstance(p, Mapping)
        and p.get("branch") == "mineru"
        and isinstance(p.get("raw"), Mapping)
        and p["raw"].get("native_document") == ref
    )
    if first is entry:
        lists(document, ref)
    return records


def execution_states(native):
    """Original state fields only, including nested Typed block failures."""
    records, seen = [], set()

    def walk(node, path, pages):
        if isinstance(node, Mapping):
            metadata = {k: audit_copy(node[k]) for k in STATE_FIELDS if k in node}
            if metadata and path not in seen:
                seen.add(path)
                records.append(
                    {
                        "native_path": path,
                        "input_pages": pages,
                        "scope": "saved_mineru_native_object",
                        "metadata": metadata,
                    }
                )
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    walk(v, path + "/" + str(k).replace("~", "~0").replace("/", "~1"), pages)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + "/" + str(i), pages)

    for i, entry in enumerate(native.get("pages", [])):
        if not isinstance(entry, Mapping) or entry.get("branch") != "mineru":
            continue
        walk(entry.get("raw"), f"#/pages/{i}/raw", [entry.get("page")])
        raw = entry.get("raw", {})
        ref = raw.get("native_document") if isinstance(raw, Mapping) else None
        document = resolve_pointer(native, ref)
        if isinstance(document, Mapping):
            walk(
                {k: document[k] for k in STATE_FIELDS if k in document},
                ref,
                [
                    e.get("page")
                    for e in native["pages"]
                    if isinstance(e, Mapping)
                    and isinstance(e.get("raw"), Mapping)
                    and e["raw"].get("native_document") == ref
                ],
            )
            for j, page in enumerate(document.get("pages", [])):
                if isinstance(page, Mapping) and page.get("page_idx") == raw.get("page_idx"):
                    walk(page, f"{ref}/pages/{j}", [entry.get("page")])
    return records
