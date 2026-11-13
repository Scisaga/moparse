"""Independent saved Middle JSON inventory; never reads adapter output."""

from collections.abc import Mapping

from app.adapters.mineru_native import CONTAINERS, MEDIA_FIELDS, indexed, source_page
from app.adapters.native_readers import NativeReadError, html_cells


def inventory_mineru(root, entry, position, add):
    number = entry["page"]
    try:
        page, pointer, document = source_page(root, entry)
    except NativeReadError:
        return None
    local = page["page_idx"]

    def literal(value):
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            if any(
                not isinstance(s, Mapping) or not isinstance(s.get("content", ""), (str, list))
                for s in value
            ):
                raise NativeReadError("unreadable inline content")
            return "".join(literal(s.get("content", "")) for s in value)
        return ""

    def metadata(path, value, purpose, *, receipt=False):
        add(
            "metadata",
            path,
            number,
            "mineru",
            local,
            view="mineru_audit",
            details={
                "purpose": purpose,
                "requires_audit_receipt": receipt,
                "native_fields": sorted(value) if isinstance(value, Mapping) else None,
            },
        )

    def spans(values, path, parent):
        if not isinstance(values, list):
            return
        for i, span in enumerate(values):
            own = path + "/" + str(i)
            add(
                "metadata",
                own,
                number,
                "mineru",
                local,
                parent=parent,
                view="docvortex.middle",
                details={"purpose": "inline_span_in_native_content", "owner": parent},
            )
            if isinstance(span, Mapping):
                spans(span.get("content"), own + "/content", parent)

    def walk(nodes, path, parent=None, prefix=(), known=True):
        good = known and indexed(nodes)
        for i, obj in enumerate(nodes):
            own = f"{path}/{i}"
            node = obj if isinstance(obj, Mapping) else {}
            role, content = str(node.get("type", "unknown")), node.get("content")
            seq = (*prefix, node["index"] if good else i)
            basis = "native_index" if good else "native_array_order_unknown_reading_order"
            container = role in CONTAINERS and isinstance(content, list)
            malformed = (
                not isinstance(obj, Mapping) or not isinstance(content, (str, list))
            ) and role not in {"image_body", "chart_body"}
            try:
                text = "" if container else literal(content)
            except NativeReadError:
                text = ""
                malformed = True
            if role in {"equation", "formula"} and not text:
                malformed = True
            kind = (
                "container"
                if container
                else "table"
                if role == "table_body"
                else "picture"
                if role in {"image_body", "chart_body", "image", "chart"}
                else "content"
            )
            fmt = (
                None
                if not isinstance(obj, Mapping)
                else "html"
                if role == "table_body"
                else "plain"
            )
            add(
                kind,
                own,
                number,
                "mineru",
                local,
                parent=parent,
                text=text,
                order=(number, *seq),
                basis=basis,
                view="docvortex.middle",
                details={
                    "label": role,
                    "requires_read_failure": malformed,
                    "text_format": fmt,
                    "native_index": node.get("index"),
                    "native_block_id": node.get("block_id"),
                    "field_presence": sorted(node),
                    "native_children": [own + "/content/" + str(j) for j in range(len(content))]
                    if container and isinstance(content, list)
                    else [],
                    "in_reading_tree": container,
                    "continuation": {
                        k: node[k] for k in ("continues_prev", "merge_prev") if k in node
                    },
                    "source_kind": "middle_json_not_official_typed",
                },
            )
            if container:
                walk(content, own + "/content", own, seq, good)
            else:
                spans(content, own + "/content", own)
                if role == "table_body" and isinstance(content, str):
                    try:
                        cells = html_cells(content, own + "/content")
                    except (NativeReadError, ValueError):
                        cells = []
                    for cell in cells:
                        add(
                            "cell",
                            cell["id"],
                            number,
                            "mineru",
                            local,
                            parent=own,
                            text=cell["text"],
                            view="docvortex.middle",
                            details={
                                "source_cell": cell,
                                "source_table": own,
                                "origin": "primary_html_projection",
                                "native_independent_ocr_cell": False,
                            },
                        )
            if kind == "picture" or any(node.get(k) is not None for k in MEDIA_FIELDS):
                add(
                    "media",
                    own,
                    number,
                    "mineru",
                    local,
                    identity=own + ":media",
                    parent=own,
                    view="docvortex.middle",
                    details={
                        "appearance": "native_region_media",
                        "fields": [k for k in MEDIA_FIELDS if node.get(k) is not None],
                        "delivery": "not_read_not_verified_not_delivered",
                    },
                )

    walk(page["blocks"], pointer + "/blocks")
    metadata(pointer, page, "primary_native_page")
    for i, node in enumerate(
        entry["raw"].get("blocks", []) if isinstance(entry["raw"].get("blocks"), list) else []
    ):
        metadata(f"#/pages/{position}/raw/blocks/{i}", node, "saved_page_projection", receipt=True)

    def lists(node, path):
        if isinstance(node, Mapping):
            for k, v in node.items():
                own = path + "/" + str(k).replace("~", "~0").replace("/", "~1")
                if k == "content_list":
                    if isinstance(v, list):
                        for i, value in enumerate(v):
                            metadata(
                                own + "/" + str(i),
                                value,
                                "content_list_unbound_derived_view",
                                receipt=True,
                            )
                    else:
                        metadata(own, v, "malformed_content_list_audit", receipt=True)
                elif isinstance(v, (dict, list)):
                    lists(v, own)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                lists(v, path + "/" + str(i))

    lists(entry["raw"], f"#/pages/{position}/raw")
    ref = pointer.split("/pages/", 1)[0]
    first = next(
        p
        for p in root["pages"]
        if isinstance(p, Mapping)
        and p.get("branch") == "mineru"
        and isinstance(p.get("raw"), Mapping)
        and p["raw"].get("native_document") == ref
    )
    if first is entry:
        lists(document, ref)
        for key in document:
            if key != "pages":
                metadata(ref + "/" + key, document[key], "document_metadata_or_audit")
    return {
        "branch_page": local,
        "source_view": "docvortex.middle",
        "native_page_pointer": pointer,
        "mapping_basis": "saved_executor_physical_page_idx",
        "content_list_present": any(k == "content_list" for k in document),
    }
