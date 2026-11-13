"""Fixed P02 assertions authored from its own native JSON, not another answer.

No app/evaluator imports or I/O. This is normalization and bounded conversion
acceptance, never parser quality. V2's incomplete literals remain its literals.
"""

VALUES = {
    2: ["15,386,99", "0.14%", "", "15,848,774", "0.14%"],
    4: ["9,718,459,333", "87.96%", "12,480,299", "9,708,327,759", "87.94%"],
    5: ["1,314,955,468", "11.90%", "", "1,314,955,468", "11.91%"],
    6: ["11,033,414,801", "99.86%", "12,480,299", "11,023,283,227", "99.86%"],
    7: ["11,048,801,800", "100.00%", "12,480,299", "11,039,132,001", "100.00%"],
}
HEADERS = {1: [(0, 1), (1, 1)], 2: [(0, 1), (1, 2)], 3: [(0, 3)],
           4: [(0, 4), (1, 4)], 5: [(0, 4), (1, 5)]}


def accept_fixed_docling_v2(native, evidence, final):
    assert native["pipeline"] == evidence["pipeline"] == "P02"
    assert native["config"]["revisions"]["tableformer_v2"] == "e41ba5da7ef69004f4b329168791c2987abf917c"
    assert evidence["sample_id"] == "vanke-repurchase-share-changes-p001-003"
    assert [(p["page"], p["branch"]) for p in native["pages"]] == [(1, "docling"), (2, "docling"), (3, "glm")]
    doc = native["documents"][0]["document"]
    assert doc["schema_name"] == "DoclingDocument" and doc["version"] == "1.10.0"
    assert (len(doc["texts"]), len(doc["groups"]), len(doc["tables"]), len(doc["pictures"])) == (23, 2, 1, 2)
    assert [c["$ref"] for c in doc["groups"][1]["children"]] == [f"#/texts/{i}" for i in (17, 18, 19, 20)]
    data = doc["tables"][0]["data"]
    assert (data["num_rows"], data["num_cols"], len(data["table_cells"])) == (8, 6, 46)
    assert sum(bool(c["text"].strip()) for c in data["table_cells"]) == 37
    assert sum(c["column_header"] for c in data["table_cells"]) == 10
    assert all(c["row_section"] is False and c["fillable"] is False for c in data["table_cells"])
    raw = {(c["start_row_offset_idx"], c["start_col_offset_idx"]): c for c in data["table_cells"]}
    assert raw[0, 3]["row_span"] == 1 and raw[1, 3]["text"] == "" and raw[1, 3]["column_header"] is True
    assert raw[0, 1]["text"] == "本次回购前 " + chr(13) + chr(10) + "（2015 年 8 月 31 日"
    assert raw[2, 1]["text"] == "15,386,99"
    assert doc["tables"][0]["captions"] == doc["tables"][0]["footnotes"] == []
    assert len(evidence["semantic_tables"]) == len(evidence["table_fragments"]) == 1
    fragment = evidence["table_fragments"][0]
    assert len(fragment["cells"]) == len(fragment["native_evidence"]["source_cells"]) == 46
    block_pages = evidence["native_blocks"]
    blocks = [b for values in block_pages.values() for b in values]
    table = next(b for b in blocks if b["type"] == "table")
    assert table["source_locator"]["path"] == "#/documents/0/document/tables/0"
    assert table["source_locator"]["view"] == "document"
    fields = ("text", "row_span", "col_span", "start_row_offset_idx", "end_row_offset_idx",
              "start_col_offset_idx", "end_col_offset_idx", "column_header", "row_header", "row_section", "fillable", "bbox")
    for index, (source, cell) in enumerate(zip(data["table_cells"], table["cells"], strict=True)):
        assert cell["native_path"] == f"#/documents/0/document/tables/0/data/table_cells/{index}"
        assert all(cell.get(k) == source.get(k) for k in fields)
        assert cell["coordinate_origin"] == "TOPLEFT" and cell["coordinate_system"] == "pdf_points"
    for b in blocks:
        assert b["source_locator"]["artifact_sha256"] == evidence["contract"]["artifact"]["sha256"]
        if b["native_branch"] == "docling":
            family, number = b["native_path"].split("/document/", 1)[1].split("/")
            node = doc[family][int(number)]
            if family == 'pictures':
                payload = b['native_payload']
                assert {k: v for k, v in payload.items() if k != 'image'} == {k: v for k, v in node.items() if k != 'image'}
                assert {k: v for k, v in payload['image'].items() if k != 'uri'} == {k: v for k, v in node['image'].items() if k != 'uri'}
                assert node['image']['uri'].startswith('data:image/')
                assert payload['image']['uri'] == {'inline_media_declared': True, 'access': 'not_decoded_or_validated'}
            else:
                assert b["native_payload"] == node
            assert b["parent_id"] == "#/documents/0/document" + node["parent"]["$ref"][1:]
        else:
            assert b["page"] == 3 and b["branch_page"] == 0 and b["source_view"] == "json_result"
    view = evidence["semantic_tables"][0]
    assert view["status"] == "converted" and [r["source_row"] for r in view["records"]] == list(VALUES)
    for record in view["records"]:
        row = record["source_row"]
        assert [(v["value"]["row"], v["value"]["column"]) for v in record["values"]] == [(row, c) for c in range(1, 6)]
        for col, relation in enumerate(record["values"], 1):
            assert raw[row, col]["text"].strip() == VALUES[row][col-1]
            assert [(r["row"], r["column"]) for r in relation["column_headers"]] == HEADERS[col]
            assert [(r["row"], r["column"]) for r in relation["row_headers"]] == (
                [(3, 0), (row, 0)] if row in {4, 5, 6} else [(row, 0)])
            assert [(r["row"], r["column"]) for r in relation["period_refs"]] == (
                [(0, 1)] if col in {1, 2} else [(0, 4)] if col in {4, 5} else [])
            assert not relation["unit_refs"] and not relation["note_refs"]
    assert len(evidence["relation_checks"]) == 25
    dispositions = evidence["content_dispositions"]
    cells = next(d["cells"] for d in dispositions if d["classification"] == "data_table")
    assert len(cells) == 46
    assert sum(c["disposition"] == "located_in_final" for c in cells) == 37
    assert sum(c["disposition"] == "empty_literal_not_filled" for c in cells) == 9
    for cell in cells:
        index = int(cell["native_path"].rsplit("/", 1)[1])
        assert cell["raw_text"] == data["table_cells"][index]["text"]
        if cell["raw_text"].strip():
            assert cell["disposition"] == "located_in_final" and cell["final_spans"]
        else:
            assert cell["disposition"] == "empty_literal_not_filled"
        for (a, b), printed in zip(cell["final_spans"], cell["actual_renderings"], strict=True):
            assert final[a:b] == printed
    value = next(c for c in cells if c["native_path"].endswith("/11"))
    assert all(final[a:b] == "15,386,99" for a, b in value["final_spans"])
    assert "本次回购前 （2015 年 8 月 31 日 / 股份数量：15,386,99" in final
    assert final.count("图片未交付。") == 2 and "董事会" in final and "二O一六年一月十五日" in final
    assert "2,810,500" not in final and "<!--" not in final
    assert all(d["disposition"] in {"retained", "converted", "unresolved_media_delivery"} for d in dispositions)
    s = evidence["states"]
    assert [s[k]["status"] for k in ("original_execution", "readback", "conversion", "delivery")] == [
        "completed", "read", "completed", "partial"]
    assert len(s["delivery"]["partial_reasons"]) == 2
    assert all(i["category"] == "asset_delivery_incomplete" for i in s["delivery"]["partial_reasons"])
    assert evidence["stages"][-1]["markdown"] == final and all(c["equal"] for c in evidence["format_readback_checks"])
    return {"pipeline": "P02", "status": "accepted_native_handoff_and_bounded_conversion", "quality_grade": None,
            "native_source_cells": 46, "located_nonempty_cells": 37, "empty_literals": 9,
            "value_relations": 25, "undelivered_media": 2, "delivery": "partial"}
