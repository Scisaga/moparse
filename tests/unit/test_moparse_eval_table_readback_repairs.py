"""Native table readback contracts; all content is invented software input.

The SDK fixture uses the fixed Docling data types and actual JSON exporter,
not a hand-authored approximation of a parser's schema. No parser is loaded.
"""

from __future__ import annotations

import copy
import importlib.metadata

import pytest

from moparse_eval.adapters import _docling_cell_fields, read_docling
from moparse_eval.native_readback import READBACK_VERSION, read_native_relations


@pytest.fixture
def sdk_document():
    sdk = pytest.importorskip("docling_core.types.doc")
    assert importlib.metadata.version("docling-core") == "2.101.1"
    doc = sdk.DoclingDocument(name="invented-table-contract")
    doc.add_page(page_no=1, size=sdk.Size(width=100, height=100))
    prov = sdk.ProvenanceItem(page_no=1, charspan=(0, 0),
                              bbox=sdk.BoundingBox(l=0, t=100, r=100, b=0,
                                                   coord_origin="BOTTOMLEFT"))
    common = {"row_span": 1, "col_span": 1, "start_row_offset_idx": 1,
              "end_row_offset_idx": 2, "start_col_offset_idx": 1, "end_col_offset_idx": 2}
    table = doc.add_table(data=sdk.TableData(num_rows=2, num_cols=2, table_cells=[
        sdk.TableCell(text="  Group  ", row_span=1, col_span=2, start_row_offset_idx=0,
                      end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=2,
                      column_header=True, row_section=True, fillable=True),
        sdk.TableCell(text="13.25", **common),
    ]), prov=prov)
    group = doc.add_group(label=sdk.GroupLabel.UNSPECIFIED, name="rich-cell", parent=table)
    doc.add_text(label=sdk.DocItemLabel.TEXT, text="Alpha", prov=prov, parent=group)
    doc.add_table_cell(table_item=table, cell=sdk.RichTableCell(
        text="", row_span=1, col_span=1, start_row_offset_idx=1, end_row_offset_idx=2,
        start_col_offset_idx=0, end_col_offset_idx=1, row_header=True, ref=group.get_ref()))
    return sdk, doc, table, group, prov


def _inputs(sdk_document):
    _sdk, doc, _table, _group, _prov = sdk_document
    exported = doc.export_to_dict()
    wrapper = {"document": exported}
    blocks = read_docling(wrapper, 1, pointer="#/documents/0")
    observation = {
        "pipeline": "P01", "sample_id": "synthetic-only", "status": "completed",
        "pages": [{"page": 1, "blocks": blocks}], "native_containers": [], "relations": [],
        "timing": {"processing_seconds": 3.25}, "resources": {"synthetic_budget": 1},
        "faithful_markdown": "Opaque saved execution export remains unchanged.",
    }
    native = {"documents": [wrapper], "pages": [{"page": 1, "branch": "docling",
                                               "raw": {"native_document": "#/documents/0"}}]}
    return observation, native


def _table(observation):
    return next(block for block in observation["pages"][0]["blocks"] if block["kind"] == "table")


def _legacy(observation):
    """Emulate only the explicitly known old adapter omissions."""
    legacy = copy.deepcopy(observation)
    table = _table(legacy)
    table.pop("native_table_data", None)
    for cell in table["cells"]:
        for key in (
            "start_row_offset_idx", "end_row_offset_idx", "start_col_offset_idx", "end_col_offset_idx",
            "column_header", "row_header", "row_section", "fillable", "native_cell_ref",
            "native_rich_content", "native_rich_text", "native_rich_text_path",
        ):
            cell.pop(key, None)
    return legacy


def test_fixed_sdk_export_retains_plain_cells_and_declared_metadata(sdk_document):
    observation, native = _inputs(sdk_document)
    table = _table(observation)
    assert table["native_table_data"] == {"num_rows": 2, "num_cols": 2, "orientation": "rot_0"}
    header, value, rich = table["cells"]
    assert (header["row"], header["col"], header["row_span"], header["col_span"], header["text"]) == (
        0, 0, 1, 2, "  Group  ")
    assert header["end_col_offset_idx"] == 2
    assert header["is_column_header"] is True and header["column_header"] is True
    assert header["row_section"] is True and header["fillable"] is True
    assert value["text"] == "13.25"
    assert rich["text"] == "" and rich["is_row_header"] is True
    assert native["documents"][0]["document"]["tables"][0]["data"]["table_cells"][2]["text"] == ""


def test_fixed_sdk_rich_reference_has_exact_text_evidence_without_rewriting_cell(sdk_document):
    observation, _native = _inputs(sdk_document)
    rich = _table(observation)["cells"][2]
    assert rich["native_cell_ref"] == {"$ref": "#/groups/0"}
    assert rich["native_rich_content"]["status"] == "text_resolved"
    assert rich["native_rich_text"] == "Alpha"
    assert rich["native_rich_text_path"] == "#/documents/0/document/texts/0/text"
    assert rich["native_rich_content"]["edges"] == [{
        "native_path": "#/documents/0/document/groups/0/children/0",
        "reference": {"$ref": "#/texts/0"},
        "target_native_path": "#/documents/0/document/texts/0",
    }]
    assert rich["text"] == ""


def test_saved_observation_receives_missing_fields_and_keeps_frozen_inputs_unchanged(sdk_document):
    observation, native = _inputs(sdk_document)
    legacy = _legacy(observation)
    before = copy.deepcopy((legacy, native))
    derived, diagnostics = read_native_relations(legacy, native)
    assert (legacy, native) == before
    assert _table(derived)["cells"] == _table(observation)["cells"]
    assert _table(derived)["native_table_data"] == _table(observation)["native_table_data"]
    assert diagnostics["reader_version"] == READBACK_VERSION
    assert "table-fields" in READBACK_VERSION
    assert diagnostics["status"] == "read"
    records = diagnostics["table_field_readback"]["records"]
    assert any(record.get("rich_content_status") == "text_resolved" for record in records)
    for key in ("timing", "resources", "status", "faithful_markdown"):
        assert derived[key] == legacy[key]
    for old_block, new_block in zip(legacy["pages"][0]["blocks"], derived["pages"][0]["blocks"], strict=True):
        assert old_block["text"] == new_block["text"]
        assert old_block["native_sequence"] == new_block["native_sequence"]
    again, _ = read_native_relations(derived, native)
    assert again["pages"] == derived["pages"]


@pytest.mark.parametrize("kind", ["picture", "multiple_text"])
def test_mixed_or_multiple_rich_content_never_becomes_a_joined_cell_answer(sdk_document, kind):
    sdk, doc, _table_item, group, prov = sdk_document
    if kind == "picture":
        doc.add_picture(parent=group, prov=prov)
    else:
        doc.add_text(label=sdk.DocItemLabel.TEXT, text="Beta", prov=prov, parent=group)
    observation, native = _inputs(sdk_document)
    rich = _table(observation)["cells"][2]
    assert rich["text"] == "" and "native_rich_text" not in rich
    assert rich["native_rich_content"]["status"] == (
        "mixed_or_nontext" if kind == "picture" else "multiple_text_items")
    text_items = rich["native_rich_content"]["text_items"]
    assert [item["text"] for item in text_items] == (["Alpha"] if kind == "picture" else ["Alpha", "Beta"])
    derived, _ = read_native_relations(_legacy(observation), native)
    assert _table(derived)["cells"][2] == rich


@pytest.mark.parametrize("problem", ["cycle", "missing", "conflicting_alias", "wrong_self_ref"])
def test_unresolved_rich_references_remain_unknown_and_keep_native_paths(sdk_document, problem):
    observation, native = _inputs(sdk_document)
    document = native["documents"][0]["document"]
    raw_cell = document["tables"][0]["data"]["table_cells"][2]
    if problem == "cycle":
        document["groups"][0]["children"].append({"$ref": "#/groups/0"})
    elif problem == "missing":
        raw_cell["ref"] = {"$ref": "#/groups/999"}
    elif problem == "wrong_self_ref":
        document["groups"][0]["self_ref"] = "#/groups/999"
    else:
        raw_cell["ref"]["cref"] = "#/groups/999"
    derived, diagnostics = read_native_relations(_legacy(observation), native)
    rich = _table(derived)["cells"][2]
    assert rich["native_rich_content"]["status"] == "unknown"
    assert rich["native_rich_content"]["errors"]
    assert "native_rich_text" not in rich and rich["text"] == ""
    assert any(record.get("rich_content_status") == "unknown"
               for record in diagnostics["table_field_readback"]["records"])


@pytest.mark.parametrize("problem", ["duplicate_cell_path", "duplicate_cell_id", "duplicate_table_path",
                                     "wrong_parent", "foreign_cell_path", "wrong_table_self_ref"])
def test_metadata_requires_unique_exact_native_cell_and_table_identity(sdk_document, problem):
    observation, native = _inputs(sdk_document)
    legacy = _legacy(observation)
    table = _table(legacy)
    header = table["cells"][0]
    if problem == "duplicate_cell_path":
        duplicate = copy.deepcopy(header)
        duplicate["id"] = "different-id-same-path"
        table["cells"].append(duplicate)
    elif problem == "duplicate_cell_id":
        table["cells"][1]["id"] = header["id"]
    elif problem == "duplicate_table_path":
        duplicate = copy.deepcopy(table)
        duplicate["id"] = "different-table-id-same-path"
        legacy["pages"][0]["blocks"].append(duplicate)
    elif problem == "wrong_parent":
        header["parent_id"] = "a-different-table"
    elif problem == "foreign_cell_path":
        header["native_path"] = "#/documents/0/document/texts/0"
    else:
        native["documents"][0]["document"]["tables"][0]["self_ref"] = "#/tables/999"
    derived, diagnostics = read_native_relations(legacy, native)
    assert "row_section" not in _table(derived)["cells"][0]
    records = diagnostics["table_field_readback"]["records"]
    assert any(record["status"] == "unknown" and "identity" in record.get("reason", "") for record in records)


def test_existing_observed_values_are_not_silently_corrected(sdk_document):
    observation, native = _inputs(sdk_document)
    legacy = _legacy(observation)
    cell = _table(legacy)["cells"][0]
    cell.update(text="An already recorded answer", row_section=False, is_column_header=False)
    derived, diagnostics = read_native_relations(legacy, native)
    cell = _table(derived)["cells"][0]
    assert cell["text"] == "An already recorded answer"
    assert cell["row_section"] is False and cell["is_column_header"] is False
    records = diagnostics["table_field_readback"]["records"]
    assert any({"row_section", "is_column_header"} <= set(record.get("field_conflicts", [])) for record in records)


def test_rich_reference_graph_work_is_bounded_without_flattening(sdk_document):
    _observation, native = _inputs(sdk_document)
    document = native["documents"][0]["document"]
    document["groups"][0]["children"] = [{"$ref": "#/texts/0"}] * 1000
    cell = document["tables"][0]["data"]["table_cells"][2]
    fields = _docling_cell_fields(cell, document, "#/document")
    evidence = fields["native_rich_content"]
    assert len(evidence["nodes"]) <= 256 and len(evidence["edges"]) <= 512
    assert evidence["status"] == "unknown" and "native_rich_text" not in fields
    assert any(error["reason"] == "reference_budget_exceeded" for error in evidence["errors"])


def test_missing_native_does_not_generate_new_table_metadata(sdk_document):
    observation, _native = _inputs(sdk_document)
    legacy = _legacy(observation)
    derived, diagnostics = read_native_relations(legacy, None)
    assert derived["pages"] == legacy["pages"]
    assert diagnostics["table_field_readback"]["status"] == "native_missing"
