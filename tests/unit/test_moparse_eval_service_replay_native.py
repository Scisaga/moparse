"""Offline replay of invented candidate structures, without files or models."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import PageSourceKind, PageStatus
from app.models.source import StoredSource
from moparse_eval.service_replay_native import (
    ReplayDependencyError,
    project_mineru_blocks,
    replay_native,
)


def _source(pages=1):
    return StoredSource(path=Path("/unopened-synthetic-source.pdf"), filename="synthetic.pdf",
                        mime_type="application/pdf", size_bytes=17, page_count=pages)


def _text(text):
    return {"type": "text", "bbox": [.1, .1, .9, .2], "content": [{"type": "text", "content": text}]}


def _native(blocks=None):
    blocks = blocks if blocks is not None else [_text("Existing typed content")]
    return {"pipeline": "P07", "documents": [{"schema": "docvortex.middle", "pages": [
        {"page_idx": 0, "blocks": blocks},
    ]}], "pages": [{"page": 1, "branch": "mineru", "raw": {
        "page_idx": 0, "native_document": "#/documents/0", "blocks": [
            {"type": "text", "markdown": "Derived research view is not the worker projection"},
        ],
    }}], "page_processing": [{"page": 1, "source_prediction": "native", "rotation_clockwise": 0}]}


def _controlled_projection(blocks):
    result = deepcopy(blocks)
    for block in result:
        if block["type"] == "text":
            block["markdown"] = "".join(part["content"] for part in block["content"])
        elif block["type"] == "table":
            html = block["content"][0]["content"]
            block["markdown"] = html
            block["content"][0]["markdown"] = html
        elif block["type"] == "image":
            block["markdown"] = "<!-- image -->"
            block["source_images"] = [{"bbox": block["bbox"]}]
    return result, []


def test_declared_typed_document_is_projected_without_reading_pdf_or_rewriting_native():
    native = _native()
    before = deepcopy(native)
    result, diagnostic = replay_native(native, _source(), ContentParseOptions(), document_id="synthetic",
                                      mineru_projector=_controlled_projection)
    assert native == before
    assert result.pages[0].content == "Existing typed content"
    assert result.pages[0].status == PageStatus.COMPLETED
    assert diagnostic["pages"][0]["native_page_pointer"] == "#/documents/0/pages/0"
    assert diagnostic["model_calls"] == diagnostic["http_calls"] == 0


def test_missing_child_markdown_is_a_projection_difference_not_a_failed_parser():
    html = "<table><tr><th>Field</th><th>Value</th></tr><tr><td>Metric</td><td>100</td></tr></table>"
    native = _native([{"type": "table", "bbox": [.1, .2, .9, .8], "content": [
        {"type": "table_body", "bbox": [.1, .2, .9, .8], "content": html},
    ]}])
    result, diagnostic = replay_native(native, _source(), ContentParseOptions(), document_id="synthetic",
                                      mineru_projector=_controlled_projection)
    assert result.pages[0].status == PageStatus.COMPLETED and not diagnostic["errors"]
    assert result._table_fragments[0].cells[-1].text == "100"
    assert "markdown" not in native["documents"][0]["pages"][0]["blocks"][0]["content"][0]


@pytest.mark.parametrize("mutation,reason", [
    (lambda n: n["pages"][0]["raw"].update(native_document="#/documents/9"), "mineru_declared_middle_document_unavailable"),
    (lambda n: n["pages"][0]["raw"].update(page_idx=5), "mineru_raw_page_identity_conflict"),
    (lambda n: n["documents"][0]["pages"].append(deepcopy(n["documents"][0]["pages"][0])), "mineru_middle_page_not_unique"),
])
def test_missing_or_conflicting_declared_identity_does_not_select_a_favorable_view(mutation, reason):
    native = _native()
    mutation(native)
    def forbidden(_blocks):
        raise AssertionError("ambiguous identity cannot reach the official renderer")
    result, diagnostic = replay_native(native, _source(), ContentParseOptions(), document_id="synthetic",
                                      mineru_projector=forbidden)
    assert result.pages[0].status == PageStatus.FAILED
    assert diagnostic["errors"][0]["error"] == reason
    assert "source-page-image" in result.pages[0].content


def test_native_documents_pointer_is_resolved_as_declared_without_a_key_alias_guess():
    native = _native()
    native["native_documents"] = native.pop("documents")
    native["pages"][0]["raw"]["native_document"] = "#/native_documents/0"
    result, diagnostic = replay_native(native, _source(), ContentParseOptions(), document_id="synthetic",
                                      mineru_projector=_controlled_projection)
    assert result.pages[0].status == PageStatus.COMPLETED
    assert diagnostic["pages"][0]["native_page_pointer"] == "#/native_documents/0/pages/0"


def test_primary_glm_view_is_used_without_completing_it_from_the_raw_stage():
    native = {"pipeline": "P07", "pages": [{"page": 1, "branch": "glm", "raw": {
        "json_result": [[{"label": "text", "content": "Primary content", "bbox_2d": [0, 0, 1000, 1000]}]],
        "raw_json_result": [[{"label": "text", "content": "Raw stage must stay separate"}]],
        "image_files": {"native.png": "assets/existing.png"},
    }}], "page_processing": [{"page": 1, "rotation_clockwise": 90, "source_prediction": "mixed"}]}
    before = deepcopy(native)
    result, diagnostic = replay_native(native, _source(), ContentParseOptions(), document_id="synthetic")
    assert native == before and result.pages[0].content == "Primary content"
    assert result.pages[0].diagnostics.source_kind == PageSourceKind.MIXED
    assert diagnostic["geometry_frame"] == "frozen_oriented_input"
    assert diagnostic["pages"][0]["frozen_page_processing"]["rotation_clockwise"] == 90
    assert diagnostic["asset_references"][0]["reference"] == "assets/existing.png"
    assert result._picture_candidates[0].allow_description is False


def test_unreadable_glm_region_keeps_its_neighbors_and_is_not_silently_completed():
    native = {"pipeline": "P07", "pages": [{"page": 1, "branch": "glm", "raw": {
        "json_result": [[{"label": "text", "content": "Before"}, None,
                         {"label": "text", "content": "After"}]],
    }}]}
    result, diagnostic = replay_native(native, _source(), ContentParseOptions(), document_id="synthetic")
    page = result.pages[0]
    assert "Before" in page.content and "After" in page.content and page.status == PageStatus.FAILED
    assert diagnostic["errors"][0]["warnings"] == ["glm_sdk_local_region_unreadable"]
    assert result._picture_candidates[-1].source_page_ref in page.content


def test_missing_and_duplicate_pages_have_explicit_engineering_records():
    native = _native()
    native["pages"].append(deepcopy(native["pages"][0]))
    result, diagnostic = replay_native(native, _source(2), ContentParseOptions(), document_id="synthetic",
                                      mineru_projector=_controlled_projection)
    assert [page.status for page in result.pages] == [PageStatus.FAILED, PageStatus.FAILED]
    assert [record["error"] for record in diagnostic["pages"]] == ["native_page_duplicated", "native_page_missing"]
    assert len(result._picture_candidates) == 2


def test_existing_image_candidates_and_asset_paths_are_preserved_without_opening_them():
    native = _native([{"type": "image", "bbox": [.1, .2, .8, .9]}])
    native["pages"][0]["raw"]["blocks"][0]["research_assets"] = ["assets/already-produced.png"]
    result, diagnostic = replay_native(native, _source(), ContentParseOptions(), document_id="synthetic",
                                      mineru_projector=_controlled_projection)
    assert result._picture_candidates[0].normalized_bbox == (.1, .2, .8, .9)
    assert diagnostic["asset_references"][0]["reference"] == "assets/already-produced.png"


@pytest.mark.parametrize("error", [MemoryError, TimeoutError, ReplayDependencyError])
def test_resources_deadlines_and_missing_preparation_are_not_candidate_parse_failures(error):
    def fail(_blocks):
        raise error("controlled preparation or runtime failure")
    with pytest.raises(error):
        replay_native(_native(), _source(), ContentParseOptions(), document_id="synthetic", mineru_projector=fail)


def test_missing_fixed_sdk_fails_before_attempting_any_fallback(monkeypatch):
    from importlib import metadata

    import moparse_eval.service_replay_native as bridge
    def missing(_name):
        raise metadata.PackageNotFoundError("controlled")
    monkeypatch.setattr(bridge.metadata, "version", missing)
    with pytest.raises(ReplayDependencyError, match="docvortex==0.5.16"):
        project_mineru_blocks([_text("Existing content")])
