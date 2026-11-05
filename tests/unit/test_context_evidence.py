"""Independent candidate context sources and stopping-boundary oracles."""

from __future__ import annotations

from copy import deepcopy

import pytest

from moparse_eval.context_evidence import read_contexts
from moparse_eval.saved_native import read_saved_native


def block(ident, kind="text", text="", **metadata):
    return {"id": ident, "native_path": "#/" + ident, "kind": kind, "text": text,
            "text_format": "plain", **metadata}


def table(ident="table", *, label="Logistics", property="Amount", value="17", **metadata):
    cells = [{"id": ident + ":item", "row": 0, "col": 0, "text": "Item", "is_column_header": True},
             {"id": ident + ":property", "row": 0, "col": 1, "text": property, "is_column_header": True},
             {"id": ident + ":record", "row": 1, "col": 0, "text": label},
             {"id": ident + ":value", "row": 1, "col": 1, "text": value}]
    return block(ident, "table", cells=cells, **metadata)


def observation(*blocks, relations=(), containers=()):
    return {"sample_id": "context-only", "pages": [{"page": 1, "blocks": list(blocks)}],
            "relations": list(relations), "native_containers": list(containers)}


def test_real_heading_roles_keep_revenue_and_costs_separate_across_body_paragraphs():
    data = observation(block("revenue", "section_header", "營業收入", level=1),
                       block("revenue-prose", text="The following disclosures explain this business."),
                       table("revenue-table"), block("notes", "heading", "Notes", level=1),
                       block("costs", "section_header", "營業成本", level=1),
                       block("costs-prose", text="The operating review continues."), table("costs-table"))
    before = deepcopy(data)
    result = read_contexts(data)
    assert data == before
    assert result["by_block"]["revenue-table"]["scope"] == ["營業收入"]
    assert result["by_block"]["costs-table"]["scope"] == ["營業成本"]
    assert result["by_block"]["revenue-table"]["boundary"]["stop"]["source"]["block"] == "notes"
    assert result["by_block"]["costs-table"]["context_evidence"][0]["source"]["block"] == "costs"


def test_flat_display_headers_keep_the_complete_actual_event_history_without_invented_parents():
    result = read_contexts(observation(block("review", "heading", "財務回顧", level=1),
                                      block("revenue", "heading", "營業收入", level=1), table()))
    current = result["by_block"]["table"]
    assert current["scope"] == ["營業收入"]
    assert current["heading_path"] == ["營業收入"]
    first, end = current["heading_history_range"]
    events = result["heading_events"][first:end]
    assert [(event["text"], event["level"], event["source"]["position"]) for event in events] == [
        ("財務回顧", 1, 0), ("營業收入", 1, 1)]
    assert events[0]["display_end"]["source"]["block"] == "revenue"


def test_flat_heading_path_is_the_whole_contiguous_run_with_original_levels_and_sources():
    result = read_contexts(observation(block("root", "section_header", "Review", level=1),
                                      block("north", "section_header", "North", level=1),
                                      block("south", "section_header", "South", level=1),
                                      block("leaf", "section_header", "Revenue", level=1),
                                      block("body", text="This paragraph belongs to the printed Revenue section."), table()))
    current = result["by_block"]["table"]
    assert current["flat_heading_path"] == ["Review", "North", "South", "Revenue"]
    evidence = current["flat_heading_evidence"]
    assert [event["source"]["block"] for event in evidence["events"]] == ["root", "north", "south", "leaf"]
    assert [event["level"] for event in evidence["events"]] == [1, 1, 1, 1]
    assert evidence["start"]["block"] == "root" and evidence["end"]["block"] == "leaf"
    assert evidence["boundary"]["run_stop"]["source"]["block"] == "body"
    assert evidence["boundary"]["scope_stop"]["reason"] == "end_of_saved_input"
    # A matcher can check a full contiguous suffix; North->Revenue is absent.
    assert current["flat_heading_path"][-2:] != ["North", "Revenue"]


@pytest.mark.parametrize("interruption", [block("body", text="Business explanation."),
                                           table("earlier"), block("picture", "image"),
                                           block("break", "document_boundary")])
def test_flat_heading_run_never_stitches_an_earlier_parent_across_content(interruption):
    result = read_contexts(observation(block("parent", "heading", "North", level=1), interruption,
                                      block("leaf", "heading", "Revenue", level=1), table()))
    assert result["by_block"]["table"]["flat_heading_path"] == ["Revenue"]
    assert [event["source"]["block"] for event in result["by_block"]["table"]["flat_heading_evidence"]["events"]] == ["leaf"]


def test_explicit_furniture_preserves_a_heading_run_without_becoming_part_of_it():
    result = read_contexts(observation(block("parent", "heading", "Review", level=1),
                                      block("furniture", "page_header", "Annual report"),
                                      block("leaf", "heading", "Revenue", level=1), table()))
    record = result["by_block"]["table"]
    assert record["flat_heading_path"] == ["Review", "Revenue"]
    assert record["flat_heading_evidence"]["boundary"]["run_stop"]["source"]["block"] == "table"


def test_repeated_leaf_uses_only_the_most_recent_run_with_its_own_parent():
    result = read_contexts(observation(block("north", "heading", "North", level=1),
                                      block("north-leaf", "heading", "Revenue", level=1), table("north-table"),
                                      block("south", "heading", "South", level=1),
                                      block("south-leaf", "heading", "Revenue", level=1), table("south-table")))
    north, south = (result["by_block"][ident] for ident in ["north-table", "south-table"])
    assert north["flat_heading_path"] == ["North", "Revenue"]
    assert south["flat_heading_path"] == ["South", "Revenue"]
    assert north["flat_heading_evidence"]["boundary"]["scope_stop"]["source"]["block"] == "south"
    assert south["flat_heading_evidence"]["start"]["block"] == "south"


def test_document_boundary_clears_a_prior_flat_run_even_without_a_new_heading():
    result = read_contexts(observation(block("old", "heading", "North", level=1), table("old-table"),
                                      block("break", "document_boundary"), table()))
    assert result["by_block"]["table"]["flat_heading_path"] == []
    assert result["by_block"]["table"]["flat_heading_evidence"]["events"] == []
    assert result["by_block"]["old-table"]["flat_heading_evidence"]["boundary"]["scope_stop"]["source"]["block"] == "break"


def test_north_south_siblings_and_repeated_child_titles_keep_distinct_positions_and_stops():
    result = read_contexts(observation(block("north", "heading", "North", level=1),
                                      block("north-results", "heading", "Results", level=2), table("north-table"),
                                      block("south", "heading", "South", level=1),
                                      block("south-results", "heading", "Results", level=2), table("south-table")))
    assert result["by_block"]["north-table"]["heading_path"] == ["North", "Results"]
    assert result["by_block"]["south-table"]["heading_path"] == ["South", "Results"]
    assert result["by_block"]["north-table"]["boundary"]["stop"]["source"]["block"] == "south"
    events = result["heading_events"]
    assert [event["source"]["block"] for event in events if event["text"] == "Results"] == ["north-results", "south-results"]
    assert events[1]["source"]["position"] < events[2]["source"]["position"] < events[3]["source"]["position"]


def test_type_only_titles_retain_local_scope_but_do_not_acquire_a_tree_level():
    result = read_contexts(observation(block("root", "title", "Review"),
                                      block("local", "title", "Revenue"), table()))
    assert result["by_block"]["table"]["scope"] == ["Revenue"]
    assert result["by_block"]["table"]["heading_path"] == []
    assert [event["level"] for event in result["heading_events"]] == [None, None]
    assert [event["text"] for event in result["heading_events"]] == ["Review", "Revenue"]


def test_a_single_markdown_heading_is_read_from_its_own_markup():
    result = read_contexts(observation(block("title", text="## Revenue", text_format="markdown"), table()))
    assert result["by_block"]["table"]["scope"] == ["Revenue"]
    assert result["heading_events"][0]["level"] == 2


@pytest.mark.parametrize("kind", ["page_header", "footer", "image"])
def test_declared_furniture_or_media_cannot_become_business_scope_from_heading_export(kind):
    result = read_contexts(observation(block("furniture", kind, "# Revenue", text_format="markdown"), table()))
    assert result["by_block"]["table"]["scope"] == []
    assert result["heading_events"] == []


def test_an_explicit_heading_reference_with_no_saved_source_stays_a_reader_gap():
    result = read_contexts(observation(table(), relations=[{"type": "heading_of", "source": "absent", "target": "table"}]))
    assert result["by_block"]["table"]["scope"] == []
    assert result["issues"][0]["reason"] == "declared_heading_source_unavailable"


def test_explicit_caption_reference_can_point_after_a_table_and_preserves_the_actual_source():
    result = read_contexts(observation(table(), block("caption", "table_caption", "Revenue by region"),
                                      relations=[{"type": "caption_of", "source": "caption", "target": "table"}]))
    record = result["by_block"]["table"]
    assert record["scope"] == ["Revenue by region"]
    caption = next(item for item in record["context_evidence"] if item["role"] == "table_caption")
    assert caption["method"] == "explicit_native_caption_relation"
    assert caption["source"]["block"] == "caption" and caption["source"]["position"] == 1


def test_typed_container_caption_binds_only_its_own_body_not_a_neighbor_table():
    owner = {"id": "container", "label": "table", "native_children": ["body", "caption"]}
    result = read_contexts(observation(table("body", native_table_container="container"),
                                      block("caption", "table_caption", "Revenue", parent_id="container"),
                                      table("neighbor"), containers=[owner]))
    assert result["by_block"]["body"]["scope"] == ["Revenue"]
    # The explicitly owned caption is not a free title for another table.
    assert result["by_block"]["neighbor"]["scope"] == []
    rejected = result["by_block"]["neighbor"]["rejected_candidates"][0]
    assert rejected["reason"] == "caption_already_belongs_to_another_native_table"
    assert rejected["source"]["block"] == "caption" and rejected["owners"] == ["body"]


def test_generic_image_caption_cannot_be_borrowed_as_an_adjacent_table_title():
    result = read_contexts(observation(block("image", "image"), block("caption", "caption", "Revenue"), table(),
                                      relations=[{"type": "caption_of", "source": "caption", "target": "image"}]))
    assert result["by_block"]["table"]["scope"] == []
    assert not any(item["source"]["block"] == "caption" for item in result["by_block"]["table"]["context_evidence"])


def test_explicit_parent_heading_relation_preserves_its_own_text_and_position():
    title = block("title", "heading", "Revenue", level=2)
    body = table(parent_id="title")
    result = read_contexts(observation(title, body))
    record = result["by_block"]["table"]
    assert record["scope"] == ["Revenue"]
    assert any(item["source"]["block"] == "title" for item in record["context_evidence"])


def test_a_numbered_adjacent_caption_has_independent_title_grammar():
    result = read_contexts(observation(block("caption", text="Table 7: Revenue by region"), table()))
    record = result["by_block"]["table"]
    assert record["scope"] == ["Table 7: Revenue by region"]
    assert record["boundary"]["method"] == "adjacent_declared_or_numbered_caption"


@pytest.mark.parametrize("interruption", [block("paragraph", text="A business paragraph intervenes."),
                                           block("picture", "image"),
                                           block("other-title", "heading", "Other scope", level=1)])
def test_adjacent_caption_extension_cannot_skip_prose_media_or_another_title(interruption):
    result = read_contexts(observation(block("caption", text="Table 7: Revenue by region"), interruption, table()))
    record = result["by_block"]["table"]
    assert "Table 7: Revenue by region" not in record["scope"]
    assert not any(item["source"]["block"] == "caption" for item in record["context_evidence"])
    assert any(event["source"]["block"] == interruption["id"] for event in result["events"])


@pytest.mark.parametrize("text", ["Revenue", "Domestic", "Table 7 shows the revenue amounts."])
def test_short_prose_and_table_mentions_are_not_promoted_to_printed_titles(text):
    result = read_contexts(observation(block("prose", text=text), table(property="Share of operating costs", value="17%")))
    record = result["by_block"]["table"]
    assert record["scope"] == [] and record["status"] == "unknown"
    assert record["topic_indicators"] == []
    assert record["rejected_candidates"][0]["source"]["block"] == "prose"


def test_ratio_denominator_alone_does_not_establish_or_replace_an_amounts_business_scope():
    result = read_contexts(observation(block("revenue", "heading", "Operating revenue", level=1),
                                      table(property="Share of operating costs", value="17%")))
    record = result["by_block"]["table"]
    assert record["scope"] == ["Operating revenue"]
    assert record["topic_indicators"] == [] and record["conflicts"] == []


def test_opposing_explicit_measurement_and_title_are_retained_as_a_scope_conflict():
    result = read_contexts(observation(block("revenue", "heading", "營業收入", level=1),
                                      table(label="營業成本合計", property="金額")))
    record = result["by_block"]["table"]
    assert record["scope"] == ["營業收入"]
    assert record["status"] == "conflict"
    assert record["conflicts"][0]["reason"] == "opposing_explicit_scope_and_measurement_roles"
    assert record["conflicts"][0]["measurement_sources"][0]["source"]["cell"] == "table:value"


def test_explicit_document_boundary_stops_earlier_headings_even_without_a_new_title():
    result = read_contexts(observation(block("north", "heading", "North", level=1), table("first"),
                                      block("break", "document_boundary"), table("second")))
    assert result["by_block"]["first"]["scope"] == ["North"]
    assert result["by_block"]["second"]["scope"] == []
    assert result["by_block"]["first"]["boundary"]["stop"]["source"]["block"] == "break"
    assert result["by_block"]["first"]["segment"] != result["by_block"]["second"]["segment"]
    assert result["by_block"]["second"]["heading_history_range"] == [1, 1]
    assert result["heading_events"][0]["display_end"]["reason"] == "explicit_document_boundary"


@pytest.mark.parametrize("kind", ["heading", "table_caption"])
def test_explicit_reference_cannot_reuse_a_title_across_a_document_boundary(kind):
    relation = "heading_of" if kind == "heading" else "caption_of"
    result = read_contexts(observation(block("old", kind, "Revenue", level=1),
                                      block("break", "document_boundary"), table(),
                                      relations=[{"type": relation, "source": "old", "target": "table"}]))
    record = result["by_block"]["table"]
    assert record["scope"] == [] and record["status"] == "unknown"
    assert record["conflicts"][0]["reason"] == f"declared_{'heading' if kind == 'heading' else 'caption'}_crosses_explicit_document_boundary"
    assert result["issues"][0]["category"] == "candidate_ambiguity"


def test_different_document_titles_open_new_segments_without_using_filenames():
    result = read_contexts(observation(block("a", "doc_title", "Entity A annual report"), table("a-table"),
                                      block("b", "doc_title", "Entity B annual report"), table("b-table")))
    assert result["by_block"]["a-table"]["scope"] == ["Entity A annual report"]
    assert result["by_block"]["b-table"]["scope"] == ["Entity B annual report"]
    assert result["by_block"]["b-table"]["heading_history_range"] == [1, 2]


def test_duplicate_block_identity_never_picks_one_context_source():
    result = read_contexts(observation(block("same", "heading", "North"), block("same", "heading", "South"), table()))
    assert result["by_block"] == {}
    assert result["issues"][0]["reason"] == "context_block_identity_not_unique"


def _docling_prose_parent(parent):
    texts = [{"self_ref": "#/texts/0", "label": "section_header", "text": "North", "level": 1,
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/1", "label": "section_header", "text": "South", "level": 1,
              "parent": {"$ref": "#/body"}, "prov": [{"page_no": 1}]},
             {"self_ref": "#/texts/2", "label": "text", "text": "The amount is 17.",
              "parent": {"$ref": parent}, "prov": [{"page_no": 1}]}]
    document = {"body": {"self_ref": "#/body", "children": [{"$ref": item["self_ref"]} for item in texts]},
                "texts": texts, "tables": [], "pages": {"1": {"size": {"width": 100, "height": 100}}}}
    native = {"documents": [{"document": document}],
              "pages": [{"page": 1, "branch": "docling", "raw": {"native_document": "#/documents/0"}}]}
    return read_saved_native(native, {"sample_id": "native-parent-only", "pipeline": "invented", "status": "completed",
                                      "pages": [{"page": 1, "blocks": []}], "relations": []})


def test_docling_native_prose_parent_changes_ownership_without_changing_any_text():
    north, south = (_docling_prose_parent(parent) for parent in ["#/texts/0", "#/texts/1"])
    assert [item["text"] for item in north["pages"][0]["blocks"]] == [item["text"] for item in south["pages"][0]["blocks"]]
    first, changed = (read_contexts(candidate)["by_block"]["#/documents/0/document/texts/2"] for candidate in [north, south])
    assert first["heading_path"] == changed["heading_path"] == ["South"]
    assert first["explicit_heading_paths"][0]["path"] == ["North"]
    assert changed["explicit_heading_paths"][0]["path"] == ["South"]
    assert first["explicit_heading_paths"][0]["headings"][0]["source"]["block"] == "#/documents/0/document/texts/0"
    assert first["scope_disagreements"] and not changed["scope_disagreements"]


@pytest.mark.parametrize("parent", ["north", "south"])
def test_typed_prose_explicit_heading_reference_uses_its_own_target(parent):
    data = observation(block("north", "heading", "North", level=1), block("south", "heading", "South", level=1),
                       block("prose", text="The amount is 17."),
                       relations=[{"type": "heading_of", "source": parent, "target": "prose", "evidence": "typed_native_reference"}])
    result = read_contexts(data)["by_block"]["prose"]
    assert result["explicit_heading_paths"][0]["path"] == [parent.title()]
    assert result["explicit_heading_paths"][0]["edges"][0]["source"] == parent


def test_nested_native_parent_chain_keeps_actual_heading_order_without_numeric_levels():
    result = read_contexts(observation(block("root", "title", "North"),
                                      block("leaf", "title", "Revenue", parent_id="root"),
                                      block("prose", text="The amount is 17.", parent_id="leaf")))
    path = result["by_block"]["prose"]["explicit_heading_paths"][0]
    assert path["path"] == ["North", "Revenue"]
    assert [entry["source"]["block"] for entry in path["headings"]] == ["root", "leaf"]
    assert [entry["level"] for entry in path["headings"]] == [None, None]


def test_two_conflicting_native_heading_parents_are_candidate_ambiguity():
    result = read_contexts(observation(block("north", "heading", "North", level=1),
                                      block("south", "heading", "South", level=1), block("prose", text="The amount is 17.", parent_id="north"),
                                      relations=[{"type": "heading_of", "source": "south", "target": "prose"}]))
    record = result["by_block"]["prose"]
    assert {tuple(path["path"]) for path in record["explicit_heading_paths"]} == {("North",), ("South",)}
    assert record["status"] == "ambiguous"
    assert any(issue["category"] == "candidate_ambiguity" and issue["source"]["block"] == "prose" for issue in result["issues"])


def test_level_sequence_derived_heading_edges_are_kept_as_display_not_explicit_references():
    result = read_contexts(observation(block("north", "heading", "North", level=1), block("prose", text="The amount is 17."),
                                      relations=[{"type": "heading_of", "source": "north", "target": "prose",
                                                  "evidence": "declared_native_heading_level_and_sequence"}]))
    assert result["by_block"]["prose"]["heading_path"] == ["North"]
    assert result["by_block"]["prose"]["explicit_heading_paths"] == []
