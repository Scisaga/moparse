"""Independent assertions for supplied saved visual JSON and delivered text.

No app, reader, scorer, reference answer, SDK, I/O or visual/media dependency.
The fixed input has no descriptions, polygon, parent tree or known read order.
"""

from collections import Counter


def accept_fixed_visual(native, evidence, final):
    assert native["pipeline"] == evidence["pipeline"] == "P08"
    assert evidence["sample_id"] == "zhenye-coupon-seals-p001-003"
    assert native["documents"] == []
    assert native["config"]["versions"]["mineru-vl-utils"] == "2.0.7"
    roles = Counter(n["type"] for p in native["pages"] for n in p["raw"])
    assert roles == {"text": 14, "header": 3, "title": 2, "image": 2, "page_number": 1}
    blocks = {
        b["native_path"]: (int(number), b)
        for number, values in evidence["native_blocks"].items()
        for b in values
    }
    dispositions = {d["native_path"]: d for d in evidence["content_dispositions"]}
    objects = []
    for pi, page in enumerate(native["pages"]):
        assert page["page"] == pi + 1 and page["branch"] == "visual"
        for index, node in enumerate(page["raw"]):
            own = f"#/pages/{pi}/raw/{index}"
            number, adapted = blocks[own]
            assert number == page["page"] == adapted["page"]
            assert adapted["id"] == own and adapted["native_array_position"] == index
            assert adapted["native_sequence"] == [number, index]
            assert adapted["native_payload"] == node and adapted["bbox"] == node["bbox"]
            assert adapted["kind"] == node["type"] and adapted["text"] == (node["content"] or "")
            assert (
                adapted["source_view"] == "ContentBlock[]"
                and adapted["source_kind"] == "native_visual_region"
            )
            assert adapted["parent_id"] is None and adapted["branch_page"] is None
            assert adapted["order_basis"] == "native_array_order_unknown_reading_order"
            assert (
                adapted["native_text_span"] is None
                and adapted["source_locator"]["text_spans"] == []
            )
            assert adapted["ocr_verification"] == adapted["character_provenance"] == "not_available"
            assert (
                adapted["native_polygon_fields"] == {}
                and adapted["polygon_status"] == "not_available"
            )
            assert (
                adapted["coordinate_system"] == "normalized"
                and adapted["coordinate_origin"] == "TOPLEFT"
            )
            assert adapted["geometry_basis"]["coordinate_basis"] == "fixed_sdk_2.0.7_contract"
            assert adapted["geometry_basis"]["original_pdf_transform"] == "unknown"
            assert (
                adapted["geometry_basis"]["saved_page_processing"] == native["page_processing"][pi]
            )
            assert adapted["derived_display"]["source_type"] == "derived_display_text"
            assert adapted["derived_display"]["inferred_relations"] == []
            disposition = dispositions[own]
            assert len(disposition["final_spans"]) == 1
            a, b = disposition["final_spans"][0]
            actual = final[a:b]
            assert actual == disposition["actual_rendering"]
            if node["type"] == "page_number":
                assert (
                    actual == "" and disposition["disposition"] == "explicitly_excluded_furniture"
                )
            elif node["type"] == "image":
                assert actual == "图片未交付。"
            else:
                assert actual == ("## " if node["type"] == "title" else "") + node["content"]
            if node["content"] is not None:
                assert len(adapted["source_components"]) == 1
                component = adapted["source_components"][0]
                assert (
                    component["text"] == node["content"]
                    and component["source_type"] == "native_text"
                )
                assert (
                    component["origin"] == "visual_model_recognition"
                    and component["charspan"] is None
                )
                assert component["source_locator"]["path"] == own + "/content"
                assert component["source_locator"]["artifact_sha256"] == evidence["native_sha256"]
            else:
                assert adapted["source_components"] == [] and node["type"] == "image"
                assert adapted["asset"] == node["research_asset"]
                assert adapted["media"]["status"] == "unverified_not_delivered"
                assert adapted["media"]["bytes_accessed"] is False
            objects.append(own)
    assert set(objects) == set(blocks) and len(objects) == 22
    assert len(evidence["contract"]["inventory"]) == len(evidence["native_destinations"]) == 50
    assert len({(i["page"], i["identity"]) for i in evidence["native_destinations"]}) == 50
    assert not any(
        i["destination"] in {"unresolved_native_readback", "unresolved_final_location"}
        for i in evidence["native_destinations"]
    )
    assert [
        evidence["states"][k]["status"]
        for k in ("original_execution", "readback", "conversion", "delivery")
    ] == ["completed", "read", "partial", "partial"]
    assert {i["category"] for i in evidence["states"]["delivery"]["partial_reasons"]} == {
        "native_metadata_unknown",
        "asset_delivery_incomplete",
    }
    assert evidence["states"]["delivery"]["media"]["declared"] == 2
    assert evidence["states"]["delivery"]["media"]["delivered"] == 0
    assert final.count("图片未交付。") == 2
    assert "5.20%" in final and "15亿元" in final and "二〇一五年三月十三日" in final
    assert final.count("2015年3月13日") == 4
    assert "视觉描述：" not in final
    assert "assets/" not in final and "<!--" not in final and "\f" not in final
    assert not evidence["semantic_tables"] and not evidence["table_fragments"]
    assert (
        evidence["stages"][-1]["markdown"] == final and evidence["persisted_equals_final"] is True
    )
    assert evidence["boundary_violations"] == [] and evidence["native_unchanged"] is True
    return {
        "status": "accepted_fixed_visual_engineering_scope",
        "native_regions": 22,
        "native_text_components": 20,
        "media_declarations": 2,
        "inventory_destinations": 50,
        "description_polygon_group_read_order_real_coverage": "not_available",
        "media_bytes_verified": False,
        "parser_quality_grade": None,
    }
