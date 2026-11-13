"""Fixed own-native engineering assertions, independent of app/readers/scorers.

Only caller-supplied JSON/text is read. No SDK, I/O, media or answer input.
The saved sample has no content_list, stable block_id or formula; no claim is
made about official Typed validation or missing real-format categories.
"""

from html.parser import HTMLParser

CONTAINERS = {"image", "table", "chart", "code", "list", "index"}
HEADERS = {
    1: [(0, 1), (1, 1)],
    2: [(0, 1), (1, 2)],
    3: [(0, 3)],
    4: [(0, 4), (1, 4)],
    5: [(0, 4), (1, 5)],
}


class SourceHTML(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.row = -1
        self.cells = []
        self.occupied = set()
        self.active = None
        self.feed(body)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row += 1
        elif tag in {"td", "th"}:
            a = dict(attrs)
            col = 0
            while (self.row, col) in self.occupied:
                col += 1
            self.active = {
                "row": self.row,
                "column": col,
                "text": "",
                "row_span": int(a.get("rowspan", "1")),
                "column_span": int(a.get("colspan", "1")),
            }
            self.occupied.update(
                (r, c)
                for r in range(self.row, self.row + self.active["row_span"])
                for c in range(col, col + self.active["column_span"])
            )
        elif tag == "br" and self.active is not None:
            self.active["text"] += "\n"

    def handle_data(self, value):
        if self.active is not None:
            self.active["text"] += value

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.active is not None:
            self.cells.append(self.active)
            self.active = None


def _text(value):
    return value if isinstance(value, str) else "".join(_text(s["content"]) for s in value)


def accept_fixed_mineru(native, evidence, final):
    pipe = native["pipeline"]
    assert pipe in {"P06", "P07"}
    assert (
        evidence["pipeline"] == pipe
        and evidence["sample_id"] == "vanke-repurchase-share-changes-p001-003"
    )
    doc = native["documents"][0]
    assert (doc["schema"], doc["schema_version"]) == ("docvortex.middle", "2.0")
    assert doc["metadata"]["producer"] == {"name": "mineru", "version": "4.0.12"}
    assert doc["extensions"]["mineru"]["tier"] == ("standard" if pipe == "P06" else "advanced")
    assert doc["extensions"]["mineru"]["parse_mode"] == "txt"
    assert [p["page_idx"] for p in doc["pages"]] == [0, 1]
    assert [(p["page"], p["branch"]) for p in native["pages"]] == [
        (1, "mineru"),
        (2, "mineru"),
        (3, "glm"),
    ]
    expected = {}
    containers = {}
    source_types = {}

    def walk(nodes, path, parent=None):
        for i, node in enumerate(nodes):
            own = path + "/" + str(i)
            kind = node["type"]
            source_types[own] = kind
            assert "block_id" not in node and "parent" not in node and "children" not in node
            if kind in CONTAINERS and isinstance(node.get("content"), list):
                containers[own] = node
                walk(node["content"], own + "/content", own)
            else:
                expected[own] = (node, parent, _text(node["content"]))

    for i, p in enumerate(doc["pages"]):
        walk(p["blocks"], f"#/documents/0/pages/{i}/blocks")
    actual = {
        b["native_path"]: b
        for values in evidence["native_blocks"].values()
        for b in values
        if b["native_branch"] == "mineru"
    }
    assert set(actual) == set(expected)
    for path, (node, parent, literal) in expected.items():
        b = actual[path]
        assert b["kind"] == b["native_block_type"] == node["type"]
        assert b["text"] == literal and b["parent_id"] == parent
        assert b["native_block_id"] is None and b["order_basis"] == "native_index"
        assert b["branch_page"] == int(path.split("/pages/")[1].split("/")[0])
        assert b["page"] == b["branch_page"] + 1 and b["original_pdf_page"] == b["page"]
        assert b["bbox"] == node.get("bbox") and b["coordinate_system"] == "normalized"
        assert b["source_locator"] == {
            "artifact_sha256": evidence["native_sha256"],
            "view": "docvortex.middle",
            "path": path,
            "text_spans": [],
        }
    audit = evidence["bridge"]["pages"]
    real_containers = {c["native_path"]: c for p in audit for c in p.get("native_containers", [])}
    assert set(real_containers) == set(containers)
    for path, node in containers.items():
        assert real_containers[path]["native_children"] == [
            path + "/content/" + str(i) for i in range(len(node["content"]))
        ]
    raw_objects = [r for p in audit for r in p.get("native_audit_objects", [])]
    assert len(raw_objects) == sum(len(p["blocks"]) for p in doc["pages"])
    assert all(
        r["used_as_answer"] is False and r["purpose"] == "saved_page_projection"
        for r in raw_objects
    )
    assert len(containers) == (1 if pipe == "P06" else 2)
    assert [len(p["blocks"]) for p in doc["pages"]] == ([14, 13] if pipe == "P06" else [13, 10])
    lists = [p for p, n in containers.items() if n["type"] == "list"]
    assert len(lists) == (0 if pipe == "P06" else 1)
    if lists:
        members = [b for b in actual.values() if b["parent_id"] == lists[0]]
        assert len(members) == 4 and all(
            b["type"] == "list_item" and b["kind"] == "text" for b in members
        )
        assert [b["text"][:2] for b in members] == ["1、", "2、", "3、", "4、"]
    table = next(b for b in actual.values() if b["kind"] == "table_body")
    html = expected[table["native_path"]][0]["content"]
    parsed = SourceHTML(html)
    assert len(parsed.cells) == 44 and sum(bool(c["text"]) for c in parsed.cells) == 37
    assert "（2015年8月31日）" in html if pipe == "P06" else "(2015年8月31日)" in html
    f = evidence["table_fragments"][0]
    assert (f["num_rows"], f["num_cols"]) == (8, 6) and len(f["cells"]) == 44
    source = {(c["row"], c["column"]): c for c in parsed.cells}
    assert source[0, 0]["row_span"] == source[0, 3]["row_span"] == 2
    for c in f["cells"]:
        assert all(
            c[k] == source[c["row"], c["column"]][k] for k in ("text", "row_span", "column_span")
        )
    assert f["native_evidence"]["source_binding"] == table["source_locator"]
    assert all(
        c["source_locator"]["kind"] == "primary_html_projection"
        and c["source_locator"]["independent_ocr_cell"] is False
        for c in table["cells"]
    )
    view = evidence["semantic_tables"][0]
    assert view["status"] == "converted"
    assert [r["source_row"] for r in view["records"]] == [2, 4, 5, 6, 7]
    assert len(evidence["relation_checks"]) == 25
    for record in view["records"]:
        row = record["source_row"]
        assert len(record["values"]) == 5
        for col, v in enumerate(record["values"], 1):
            assert (v["value"]["row"], v["value"]["column"]) == (row, col)
            assert [(h["row"], h["column"]) for h in v["column_headers"]] == HEADERS[col]
            assert [(h["row"], h["column"]) for h in v["row_headers"]] == (
                [(3, 0), (row, 0)] if row in {4, 5, 6} else [(row, 0)]
            )
            assert [(h["row"], h["column"]) for h in v["period_refs"]] == (
                [(0, 1)] if col in {1, 2} else [(0, 4)] if col in {4, 5} else []
            )
            assert all(
                h["table_id"] == f["fragment_id"]
                for h in (v["value"], *v["column_headers"], *v["row_headers"])
            )
            assert v["note_refs"] == []
    note = next(b for b in actual.values() if b["kind"] == "table_footnote")
    assert "2,810,500股" in note["text"]
    assert any(r["kind"] == "note" and r["text"] == note["text"] for r in f["context_refs"])
    note_d = next(
        d for d in evidence["content_dispositions"] if d["native_path"] == note["native_path"]
    )
    assert note_d["disposition"] == "retained" and all(
        "2,810,500股" in final[a:b] for a, b in note_d["final_spans"]
    )
    assert evidence["stages"][-1]["markdown"] == final and "<!--" not in final
    s = evidence["states"]
    assert [
        s[k]["status"] for k in ("original_execution", "readback", "conversion", "delivery")
    ] == ["completed", "read", "completed", "partial"]
    assert s["delivery"]["media"]["declared"] == 1 and s["delivery"]["media"]["delivered"] == 0
    assert (
        len(s["delivery"]["partial_reasons"]) == 1
        and s["delivery"]["partial_reasons"][0]["category"] == "asset_delivery_incomplete"
    )
    assert (
        evidence["native_unchanged"]
        and evidence["persisted_equals_final"]
        and evidence["boundary_violations"] == []
    )
    inventory = evidence["contract"]["inventory"]
    dest = evidence["native_destinations"]
    assert len(inventory) == len(dest) and {i["identity"] for i in inventory} == {
        d["identity"] for d in dest
    }
    assert not any(
        d["destination"] in {"unresolved_final_location", "unresolved_native_readback"}
        for d in dest
    )
    assert not any("content_list" in i["locator"]["path"] for i in inventory)
    stages = {s["stage"]: s["markdown"] for s in evidence["stages"]}
    for ledger in evidence["stage_edit_ledger"]:
        before, after = stages[ledger["from_stage"]], stages[ledger["to_stage"]]
        replay = before
        for edit in reversed(ledger["edits"]):
            a, b = edit["before_span"]
            assert before[a:b] == edit["before"]
            c, d = edit["after_span"]
            assert after[c:d] == edit["after"]
            replay = replay[:a] + edit["after"] + replay[b:]
        assert replay == after
    return {
        "pipeline": pipe,
        "acceptance": "saved_json_normalization_and_bounded_conversion",
        "official_typed_acceptance": "incomplete_dependency_not_installed",
        "primary_leaf_blocks": len(expected),
        "primary_containers": len(containers),
        "independent_inventory_objects": len(inventory),
        "html_cells": 44,
        "nonempty_cells": 37,
        "records": 5,
        "value_relations": 25,
        "media_not_delivered": 1,
        "content_list": "not_saved",
        "formula": "not_covered_in_real_sample",
    }
