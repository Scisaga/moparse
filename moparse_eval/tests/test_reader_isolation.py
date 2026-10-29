"""Controlled malformed regions and explicit SDK export metadata only."""

from types import SimpleNamespace

from PIL import Image

from moparse_eval.adapters import read_docling, read_mineru, read_paddle, read_visual
from moparse_eval.executors import _Assets, _paddle_page
from moparse_eval.native_relations import native_relations


def test_malformed_mineru_region_does_not_discard_valid_neighbors():
    raw = {"blocks": [{"type": "text", "content": "Before"},
                      {"type": "text", "content": [None]},
                      {"type": "text", "content": "After"}]}
    blocks = read_mineru(raw, 1)
    assert [block["text"] for block in blocks] == ["Before", "", "After"]
    assert blocks[1]["read_error"]
    assert blocks[2]["native_path"].endswith("/blocks/2")


def test_malformed_visual_region_does_not_discard_valid_neighbors():
    blocks = read_visual([{"type": "text", "content": "Before"}, None,
                          {"type": "text", "content": "After"}], 1)
    assert [block["text"] for block in blocks] == ["Before", "", "After"]
    assert blocks[1]["structure_status"] == "unknown"


def test_docling_bad_references_and_cells_preserve_independent_neighbors():
    raw = {"body": {"children": [{"$ref": "#/texts/0"}, None, {"$ref": "#/texts/99"},
                                  {"$ref": "#/tables/0"}, {"$ref": "#/texts/1"}]},
           "texts": [{"label": "text", "text": "Before", "prov": [{"page_no": 1}]},
                     {"label": "text", "text": "After", "prov": [{"page_no": 1}]}],
           "tables": [{"label": "table", "prov": [{"page_no": 1}], "data": {"table_cells": [
               {"text": "A", "start_row_offset_idx": 0, "start_col_offset_idx": 0}, None,
               {"text": "B", "start_row_offset_idx": 0, "start_col_offset_idx": 1}]}}]}
    blocks = read_docling(raw, 1)
    assert [block["text"] for block in blocks if block.get("kind") == "text"] == ["Before", "After"]
    table = next(block for block in blocks if block.get("kind") == "table")
    assert [cell["text"] for cell in table["cells"]] == ["A", "B"]
    assert table["read_errors"] and any(block.get("read_error") for block in blocks)


def test_sdk_heading_export_adds_relationship_evidence_without_rewriting_text():
    raw = {"res": {"parsing_res_list": [
        {"block_label": "doc_title", "block_content": "Literal title."},
        {"block_label": "text", "block_content": "Body."}]},
        "research_region_exports": {"0": "# Literal title.", "1": "Body."}}
    blocks = read_paddle(raw, 1)
    assert blocks[0]["text"] == "Literal title."
    assert blocks[0]["native_export_markdown_path"] == "#/paddle/research_region_exports/0"
    assert any(edge["type"] == "heading_of" and edge["target"] == blocks[1]["id"]
               for edge in native_relations({"pages": [{"blocks": blocks}]}))
    raw.pop("research_region_exports")
    assert not native_relations({"pages": [{"blocks": read_paddle(raw, 1)}]})


def test_paddle_export_comes_from_the_sdk_handler_and_preserves_original_field():
    region = SimpleNamespace(label="doc_title", content="Literal title.", image=None)

    class Result(dict):
        json = {"res": {"parsing_res_list": [{"block_label": "doc_title", "block_content": "Literal title."}]}}
        markdown = {"markdown_texts": "# Literal title.", "markdown_images": {}}

        def _build_handle_funcs_dict(self, *, pretty):
            assert pretty is True
            return {"doc_title": lambda block: "# " + block.content}

    result = Result(parsing_res_list=[region])
    sdk = SimpleNamespace(config={}, paddle=SimpleNamespace(predict=lambda *args, **kwargs: [result]))
    raw, markdown = _paddle_page(sdk, {"page": 1, "image": Image.new("RGB", (2, 2))}, _Assets())
    assert raw["res"]["parsing_res_list"][0]["block_content"] == "Literal title."
    assert raw["research_region_exports"]["0"] == markdown == "# Literal title."
