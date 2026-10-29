"""Synthetic native-reference/markup examples, without corpus inputs."""

import copy

import pytest

from moparse_eval.adapters import read_visual
from moparse_eval.native_relations import heading_evidence, native_relations


def test_caption_references_are_not_invented_containment_edges():
    observation = {"pages": [{"blocks": [
        {"id": "picture", "kind": "picture", "native_references": {"captions": ["caption"], "footnotes": ["note"]}},
        {"id": "caption", "kind": "caption"}, {"id": "note", "kind": "footnote"},
    ]}]}
    edges = {(edge["type"], edge["source"], edge["target"]) for edge in native_relations(observation)}
    assert ("caption_of", "caption", "picture") in edges
    assert ("footnote_of", "note", "picture") in edges
    assert ("contains", "picture", "caption") not in edges


def test_declared_markdown_scope_follows_native_sequence_without_page_repair():
    blocks = [
        {"id": "end", "text_format": "markdown", "text": "## End", "native_sequence": [0, 3]},
        {"id": "body", "text_format": "plain", "text": "Body", "native_sequence": [0, 2]},
        {"id": "title", "text_format": "markdown", "text": "# Title", "native_sequence": [0, 0]},
        {"id": "section", "text_format": "markdown", "text": "## Section", "native_sequence": [0, 1]},
    ]
    edges = {(edge["type"], edge["source"], edge["target"]) for edge in native_relations({"pages": [{"blocks": blocks}]})}
    assert ("heading_of", "section", "body") in edges
    assert ("heading_of", "end", "body") not in edges
    assert ("heading_of", "title", "section") in edges
    assert ("heading_of", "title", "body") not in edges  # Only direct hierarchy edges.


def test_plain_hashes_and_mixed_markdown_blocks_do_not_manufacture_a_heading():
    blocks = [{"id": "a", "kind": "title", "text_format": "plain", "text": "# literal"},
              {"id": "b", "text_format": "markdown", "text": "# Header\n\nMixed paragraph."},
              {"id": "c", "text_format": "plain", "text": "Following."}]
    assert native_relations({"pages": [{"blocks": blocks}]}) == []


@pytest.mark.parametrize("kind", ["title", "doc_title", "paragraph_title"])
def test_visual_type_only_title_is_a_role_without_a_declared_hierarchy(kind):
    raw = [
        {"type": kind, "content": "A native title", "bbox": [0, 0, 1, 0.2],
         "research_export_markdown": "A native title\n\n"},
        {"type": "text", "content": "Following content", "bbox": [0, 0.3, 1, 1]},
    ]
    blocks = read_visual(raw, 1)
    before = copy.deepcopy(blocks)
    evidence = heading_evidence(blocks[0])
    assert evidence["role"] == "heading"
    assert evidence["status"] == "role_only_without_level"
    assert evidence["declared_level"] is None
    assert evidence["markdown_heading_level"] is None
    assert evidence["resolved_level"] is None
    assert not any(edge["type"] == "heading_of"
                   for edge in native_relations({"pages": [{"blocks": blocks}]}))
    assert blocks == before


@pytest.mark.parametrize("markup", ["#", "#   ", "# <span></span>", "# \u00a0"])
def test_empty_markdown_page_header_never_creates_a_heading_scope(markup):
    blocks = [
        {"id": "empty", "kind": "header", "text": markup, "text_format": "markdown",
         "native_sequence": [0, 0]},
        {"id": "body", "kind": "text", "text": "Body", "native_sequence": [0, 1]},
    ]
    evidence = heading_evidence(blocks[0])
    assert evidence["role"] == "page_furniture"
    assert evidence["markdown_heading_level"] == 1
    assert evidence["resolved_level"] is None
    assert evidence["status"] == "empty_markdown_heading"
    assert evidence["markdown_status"] == "empty_heading"
    assert native_relations({"pages": [{"blocks": blocks}]}) == []


def test_real_markdown_and_explicit_levels_remain_supported_without_stripping_punctuation():
    blocks = [
        {"id": "title", "kind": "title", "text": "%", "text_format": "plain",
         "native_export_markdown": "# %\n\n", "native_sequence": [0, 0]},
        {"id": "section", "kind": "section_header", "text": "Explicit section", "level": 2,
         "native_sequence": [0, 1]},
        {"id": "body", "kind": "text", "text": "Body", "native_sequence": [0, 2]},
    ]
    assert heading_evidence(blocks[0])["status"] == "markdown_heading"
    assert heading_evidence(blocks[0])["resolved_level"] == 1
    assert heading_evidence(blocks[1])["status"] == "declared_level"
    edges = {(edge["type"], edge["source"], edge["target"])
             for edge in native_relations({"pages": [{"blocks": blocks}]})}
    assert ("heading_of", "title", "section") in edges
    assert ("heading_of", "section", "body") in edges
    assert ("heading_of", "title", "body") not in edges


def test_typed_mineru_caption_keeps_native_body_direction_and_container_edges():
    observation = {
        "native_containers": [{"id": "table", "label": "table", "native_children": ["body", "caption"]}],
        "pages": [{"blocks": [
            {"id": "body", "kind": "table_body", "parent_id": "table", "cells": [{"id": "value"}]},
            {"id": "caption", "kind": "table_caption", "parent_id": "table"},
        ]}],
    }
    before = copy.deepcopy(observation)
    edges = {(edge["type"], edge["source"], edge["target"]) for edge in native_relations(observation)}
    assert ("caption_of", "caption", "body") in edges
    assert ("contains", "table", "body") in edges
    assert ("contains", "body", "value") in edges
    assert ("caption_of", "caption", "value") not in edges
    assert not any(kind in {"caption_for", "paired_with", "row_header"} for kind, _, _ in edges)
    assert observation == before
