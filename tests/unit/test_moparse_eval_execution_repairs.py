"""Execution repairs use authored PDFs and fake SDKs, never repository corpus."""

from __future__ import annotations

import copy
import io
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pymupdf
import pytest
from PIL import Image

from moparse_eval import executors
from moparse_eval.request_control import RequestControl, RequestStopped

POLICY = {"minimum_native_characters": 10, "scan_image_coverage": 0.8,
          "mixed_image_coverage": 0.2}


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (12, 12), "red").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
@pytest.mark.parametrize("offset", [(0, 0), (50, 60)])
def test_rotated_cropbox_routing_uses_one_coordinate_frame(angle, offset):
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=600)
        x, y = offset
        page.insert_text((x + 10, y + 30), "Synthetic native text is present.")
        page.insert_image(pymupdf.Rect(x, y + 375, x + 300, y + 500), stream=image_bytes())
        page.set_cropbox(pymupdf.Rect(x, y, x + 300, y + 500))
        page.set_rotation(angle)
        assert executors._route(page, POLICY) == "mixed"
        assert page.rotation == angle
        assert list(page.cropbox) == [x, y, x + 300, y + 500]


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_scan_image_is_clipped_to_visible_crop_and_duplicate_placements_do_not_add_area(angle):
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=600)
        image = page.insert_image(pymupdf.Rect(0, 0, 400, 600), stream=image_bytes())
        page.insert_image(pymupdf.Rect(0, 0, 400, 600), xref=image)
        page.set_cropbox(pymupdf.Rect(50, 60, 350, 560))
        page.set_rotation(angle)
        assert executors._route(page, POLICY) == "scan"


async def test_preprocess_retains_pdf_rotation_separately_from_orientation_correction(tmp_path):
    source = tmp_path / "synthetic.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=600)
        page.set_cropbox(pymupdf.Rect(50, 60, 350, 560))
        page.set_rotation(90)
        document.save(source)

    def orient(uri):
        image = Image.open(io.BytesIO(__import__("base64").b64decode(uri.partition(",")[2])))
        corrected = image.transpose(Image.Transpose.ROTATE_180)
        return executors._uri(corrected), 180, 0.95

    sdk = SimpleNamespace(spec={"hybrid": False}, control=RequestControl({}),
                          orientation=SimpleNamespace(orient=orient))
    result, pages = await executors._preprocess(source, {}, sdk, tmp_path)
    assert pages[0]["pdf_original_rotation_clockwise"] == 90
    assert pages[0]["rotation_clockwise"] == 180
    assert pages[0]["pdf_effective_rotation_clockwise"] == 270
    assert pages[0]["pdf_original_cropbox"] == [50, 60, 350, 560]
    with pymupdf.open(result) as document:
        assert document[0].rotation == 270
        assert list(document[0].cropbox) == [50, 60, 350, 560]
    with pymupdf.open(source) as document:
        assert document[0].rotation == 90


class FakeDoclingDocument:
    def __init__(self, *, bad_media=False, bad_export=False):
        self.source = {"texts": ["before", "bad", "after"],
                       "pictures": [{"self_ref": "#/pictures/0", "image": {"uri": "original.png"}}]}
        self.bad_export = bad_export

        def get_image(_document):
            if bad_media:
                raise ValueError("synthetic invalid image")
            return Image.new("RGB", (3, 3), "blue")

        self.pictures = [SimpleNamespace(self_ref="#/pictures/0", get_image=get_image,
                                        image=SimpleNamespace(uri="original.png"))]

    def export_to_dict(self):
        return copy.deepcopy(self.source)

    def iterate_items(self, **_options):
        return [(SimpleNamespace(self_ref=f"#/texts/{index}"), 0) for index in range(3)]

    def export_to_markdown(self, *, from_element=0, to_element=3, **_options):
        if self.bad_export and from_element <= 1 < to_element:
            raise ValueError("synthetic bad renderer region")
        return "\n\n".join(self.source["texts"][from_element:to_element])


def test_docling_native_and_neighbor_exports_survive_bad_media_and_bad_renderer():
    document = FakeDoclingDocument(bad_media=True, bad_export=True)
    sdk = SimpleNamespace(control=RequestControl({}), docling=SimpleNamespace(convert=lambda *_a, **_k:
        SimpleNamespace(document=document, status="success", errors=[])))
    assets = executors._Assets()
    result = executors._docling_run(sdk, Path("not-read.pdf"),
                                   [{"page": 1, "source_prediction": "native"}], assets)
    raw, markdown = result[1]
    assert raw["document"] == document.source
    assert raw["document"]["pictures"][0]["image"]["uri"] == "original.png"
    assert markdown == "before\n\nafter"
    assert {error["stage"] for error in assets.errors} == {"media_export", "faithful_export"}
    assert all(error["category"] == "engineering_failure" for error in assets.errors)


def test_docling_later_parse_failure_does_not_erase_earlier_group():
    calls = []

    def convert(_path, *, page_range, **_options):
        calls.append(page_range)
        if len(calls) == 2:
            raise RuntimeError("synthetic later parser failure")
        return SimpleNamespace(document=FakeDoclingDocument(), status="success", errors=[])

    sdk = SimpleNamespace(control=RequestControl({}), docling=SimpleNamespace(convert=convert))
    output = {}
    with pytest.raises(RuntimeError, match="later parser failure"):
        executors._docling_run(sdk, Path("not-read.pdf"), [
            {"page": 1, "source_prediction": "native"}, {"page": 2, "source_prediction": "scan"},
            {"page": 3, "source_prediction": "native"}], executors._Assets(), output)
    assert output[1][1] == "before\n\nbad\n\nafter"
    assert 3 not in output


def stub_module(monkeypatch, name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)


async def test_visual_malformed_region_and_image_do_not_drop_valid_neighbors(monkeypatch):
    def json2md(blocks):
        if any(block.get("type") == "broken" for block in blocks):
            raise ValueError("synthetic renderer failure")
        return "\n\n".join(block.get("content", "") for block in blocks)

    stub_module(monkeypatch, "mineru_vl_utils.post_process.json2markdown", json2md=json2md)
    original = [{"type": "text", "content": "first"}, None,
                {"type": "image", "bbox": [0.7, 0.5, 0.2, 0.8], "content": "original location"},
                {"type": "broken", "content": "unrenderable original"},
                {"type": "text", "content": "last"}]

    async def extract(_image, **_options):
        return original

    assets = executors._Assets()
    raw, markdown = await executors._visual_page(
        SimpleNamespace(visual=SimpleNamespace(aio_two_step_extract=extract)),
        {"page": 1, "image": Image.new("RGB", (10, 20))}, assets)
    assert markdown == "first\n\nlast"
    assert raw[1] is None
    assert raw[2]["bbox"] == original[2]["bbox"]
    assert raw[2]["content"] == "original location"
    assert original[0] == {"type": "text", "content": "first"}
    assert len(assets.errors) == 3
    assert [block["text"] for block in executors.READERS["visual"](raw, 1)
            if block["kind"] == "text"] == ["first", "last"]


async def test_visual_aggregate_export_failure_keeps_successful_sdk_region_exports(monkeypatch):
    def json2md(blocks):
        if len(blocks) > 1:
            raise ValueError("synthetic aggregate failure")
        return blocks[0]["content"] if blocks else ""

    stub_module(monkeypatch, "mineru_vl_utils.post_process.json2markdown", json2md=json2md)

    async def extract(_image, **_options):
        return [{"type": "text", "content": "first"}, {"type": "text", "content": "last"}]

    assets = executors._Assets()
    raw, markdown = await executors._visual_page(
        SimpleNamespace(visual=SimpleNamespace(aio_two_step_extract=extract)),
        {"page": 2, "image": Image.new("RGB", (10, 20))}, assets)
    assert markdown == "first\n\nlast"
    assert [block["research_export_markdown"] for block in raw] == ["first", "last"]
    assert assets.errors[0]["stage"] == "faithful_export"


class NativeBlock:
    def __init__(self, kind, content, bbox=None):
        self.type, self.content, self.bbox = kind, content, bbox

    def model_dump(self, **_options):
        return {"type": self.type, "content": [item.model_dump() if isinstance(item, NativeBlock) else item
                for item in self.content] if isinstance(self.content, list) else self.content,
                "bbox": self.bbox}


async def test_mineru_broken_media_renderer_and_scalar_keep_raw_and_neighbor_blocks(monkeypatch):
    def render(block, *, image_renderer, **options):
        if block.type == "image":
            return image_renderer(block)
        if block.type == "broken":
            raise ValueError("synthetic broken typed renderer")
        if isinstance(block.content, list):
            return "\n\n".join(render(child, image_renderer=image_renderer, **options)
                                for child in block.content)
        return block.content

    blocks = [NativeBlock("text", "before"),
              NativeBlock("image", "", [0.8, 0.2, 0.1, 0.5]),
              NativeBlock("table", [NativeBlock("text", "inside-before"),
                                     NativeBlock("broken", "unrendered"), NativeBlock("text", "inside-after")]),
              None, NativeBlock("text", "after")]
    full = {"metadata": {"producer": "synthetic"}, "pages": [{"page_idx": 0}]}

    async def parse(*_args, **_options):
        return SimpleNamespace(middle_json=full, pages=[SimpleNamespace(page_idx=0, blocks=blocks)])

    stub_module(monkeypatch, "docvortex.options", LatexDelimitersConfig=lambda: {})
    stub_module(monkeypatch, "docvortex.render.markdown", render_single_block=render)
    stub_module(monkeypatch, "mineru.config", VlmConfig=lambda **options: options)
    stub_module(monkeypatch, "mineru.parser", parse_async=parse)
    sdk = SimpleNamespace(control=RequestControl({}), config={"endpoints": {"mineru": "http://fake.test"}},
                          spec={"tier": "standard"})
    assets = executors._Assets()
    output = await executors._mineru_run(sdk, Path("not-read.pdf"), [
        {"page": 1, "source_prediction": "native", "image": Image.new("RGB", (10, 20))}], assets)
    raw, markdown = output[1]
    assert markdown == "before\n\n\n\ninside-before\n\n\n\ninside-after\n\nafter"
    assert raw["blocks"][3] is None
    assert raw["blocks"][1]["bbox"] == [0.8, 0.2, 0.1, 0.5]
    assert raw["blocks"][2]["content"][1]["content"] == "unrendered"
    assert sdk.last_mineru_document == full
    assert {error["category"] for error in assets.errors} == {
        "engineering_failure", "candidate_native_structure"}
    observed = executors.READERS["mineru"](raw, 1)
    assert {block["text"] for block in observed} >= {"before", "inside-before", "inside-after", "after"}


@pytest.mark.parametrize("failure", [RuntimeError("later parse"), MemoryError("budget"),
                                     RequestStopped("cancelled"), TimeoutError("remote unknown")])
async def test_worker_preserves_successful_produced_page_after_later_failure(tmp_path, monkeypatch, failure):
    config = {"pipeline": "P01", "timeout_seconds": 60}
    control = RequestControl(config)
    control.responses = [{"finish_reason": "stop", "usage": {"completion_tokens": 4}}]
    sdk = SimpleNamespace(spec=executors.PIPELINES["P01"], control=control, initialization_seconds=0)
    pages = [{"page": number, "source_prediction": "native", "width": 10, "height": 20,
              "image": Image.new("RGB", (10, 20))} for number in (1, 2)]

    async def preprocess(*_args):
        return Path("not-read.pdf"), pages

    def native(_sdk, _path, _pages, _assets, produced):
        produced[1] = ({"document": {"original": "first native page"}, "status": "success",
                        "research_group_pages": [1]}, "first SDK export")
        raise failure

    monkeypatch.setattr(executors, "_preprocess", preprocess)
    monkeypatch.setattr(executors, "_docling_run", native)
    monkeypatch.setitem(executors.READERS, "docling", lambda *_a, **_k:
                        [{"id": "first", "kind": "text", "text": "first native page"}])
    observation = await executors.execute_in_worker(Path("never-opened.pdf"), config,
        sample_id="synthetic", output_dir=tmp_path / "output", _sdks=sdk)
    assert observation["pages"][0]["status"] == "completed"
    assert observation["pages"][0]["blocks"][0]["text"] == "first native page"
    assert observation["pages"][1]["status"] in {"failed", "not_processed", "execution_unknown"}
    saved = json.loads((tmp_path / "output/native.json").read_text())
    assert saved["documents"][0]["document"] == {"original": "first native page"}
    assert (tmp_path / "output/faithful.md").read_text() == "first SDK export"
    assert observation["request_observation"] == control.responses


async def test_worker_reports_export_engineering_error_separately_and_keeps_neighbors(tmp_path, monkeypatch):
    config = {"pipeline": "P08", "timeout_seconds": 60}
    sdk = SimpleNamespace(spec=executors.PIPELINES["P08"], control=RequestControl(config),
                          initialization_seconds=0)

    async def preprocess(*_args):
        return Path("not-read.pdf"), [{"page": 1, "source_prediction": "not_used", "width": 10,
                                     "height": 20, "image": Image.new("RGB", (10, 20))}]

    async def visual(_sdk, _page, assets):
        assets.error(ValueError("bad image export"), stage="media_export", native_path="blocks/1", pages=[1])
        return [{"type": "text", "content": "kept"}, None, {"type": "text", "content": "neighbor"}], "kept\n\nneighbor"

    monkeypatch.setattr(executors, "_preprocess", preprocess)
    monkeypatch.setattr(executors, "_visual_page", visual)
    observed = await executors.execute_in_worker(Path("never-opened.pdf"), config, sample_id="synthetic",
                                                output_dir=tmp_path / "output", _sdks=sdk)
    assert observed["status"] == "export_failed"
    assert observed["pages"][0]["status"] == "export_partial"
    assert observed["pages"][0]["export_status"] == "partial"
    assert {block["text"] for block in observed["pages"][0]["blocks"]} >= {"kept", "neighbor"}
    assert {error["category"] for error in observed["errors"]} == {
        "engineering_failure", "candidate_native_structure"}
    assert all(not error["retry"] for error in observed["errors"])
    assert (tmp_path / "output/native.json").is_file()


def test_glm_bad_media_and_audit_json_do_not_discard_primary_result():
    result = SimpleNamespace(json_result=[[{"label": "text", "content": "primary retained"}]],
        markdown_result="primary retained\n\n![](imgs/good.png)", raw_json_result="not valid JSON",
        original_images=["original SDK image position"], image_files={
            "bad.png": object(), "good.png": Image.new("RGB", (3, 4))})
    sdk = SimpleNamespace(glm=SimpleNamespace(process=lambda _request: [result]))
    assets = executors._Assets()
    raw, markdown = executors._glm_page(sdk, {"page": 1, "image": Image.new("RGB", (10, 20))}, assets)
    assert raw["json_result"] == result.json_result
    assert raw["raw_json_result"] == "not valid JSON"
    assert raw["original_images"] == ["original SDK image position"]
    assert "primary retained" in markdown
    assert raw["image_files"]["good.png"] in markdown
    assert raw["image_files"]["good.png"] in assets.data
    assert "bad.png" not in raw["image_files"]
    assert {error["stage"] for error in assets.errors} == {"media_export", "audit_stage_export"}


def test_paddle_broken_whole_view_and_region_keep_sdk_neighbor_exports():
    regions = [SimpleNamespace(label="text", value="before"), None,
               SimpleNamespace(label="text", value="after")]

    class Result:
        json = {"res": {"parsing_res_list": [
            {"block_label": "text", "block_content": "before"}, None,
            {"block_label": "text", "block_content": "after"}]}}

        @property
        def markdown(self):
            raise ValueError("synthetic whole-page export failure")

        def _build_handle_funcs_dict(self, **_options):
            return {"text": lambda region: region.value}

        def __getitem__(self, name):
            assert name == "parsing_res_list"
            return regions

    sdk = SimpleNamespace(config={"paddle_use_queues": False},
                          paddle=SimpleNamespace(predict=lambda *_a, **_k: [Result()]))
    assets = executors._Assets()
    raw, markdown = executors._paddle_page(sdk, {"page": 1, "image": Image.new("RGB", (5, 8))}, assets)
    assert markdown == "before\n\nafter"
    assert raw["res"]["parsing_res_list"][1] is None
    assert raw["research_region_exports"] == {"0": "before", "2": "after"}
    assert len(assets.errors) == 2
    observed = executors.READERS["paddle"](raw, 1)
    assert [block["text"] for block in observed] == ["before", "", "after"]


def test_native_serialization_failure_is_explicit_without_dropping_siblings():
    assets = executors._Assets()
    snapshot = executors._native_snapshot([
        {"type": "text", "content": "before"}, object(), {"type": "text", "content": "after"}],
        assets, pages=[4], pointer="blocks")
    assert snapshot[0]["content"] == "before"
    assert snapshot[2]["content"] == "after"
    assert snapshot[1]["research_unserializable_object"] == "object"
    assert assets.errors[0]["native_preserved"] is False
    assert assets.errors[0]["native_path"] == "blocks/1"


def test_docling_recovery_slices_match_real_sdk_tree_indices(monkeypatch):
    from docling_core.types.doc import DocItemLabel, DoclingDocument

    document = DoclingDocument(name="controlled synthetic document")
    for text in ("before", "broken renderer item", "after"):
        document.add_text(label=DocItemLabel.TEXT, text=text)
    # The root itself participates in SDK export indices. Use the installed
    # SDK traversal and serializer, rather than assuming text-array offsets.
    tree = list(document.iterate_items(with_groups=True, traverse_pictures=True))
    bad_index = next(index for index, (item, _) in enumerate(tree)
                     if getattr(item, "text", None) == "broken renderer item")
    original = DoclingDocument.export_to_markdown

    def controlled_export(self, *, from_element=0, to_element=sys.maxsize, **options):
        if from_element <= bad_index < to_element:
            raise ValueError("controlled SDK rendering defect")
        return original(self, from_element=from_element, to_element=to_element, **options)

    monkeypatch.setattr(DoclingDocument, "export_to_markdown", controlled_export)
    assets = executors._Assets()
    markdown = executors._docling_markdown(document, {"research_group_pages": [1]}, assets)
    assert markdown == "before\n\nafter"
    assert assets.errors[-1]["native_path"] == "document/texts/1"


@pytest.mark.parametrize("shape", ["flat", "nested", "bad_page_before_nested", "declared_pages", "serialized"])
def test_glm_audit_wrappers_keep_valid_neighbors_after_malformed_first_item(shape):
    content = "Literal -12.30% and original unit."
    region = {"label": "text", "content": content}
    stages = {
        "flat": [None, region], "nested": [[None, region]],
        "bad_page_before_nested": [None, [region]], "declared_pages": {"pages": [None, [region]]},
        "serialized": json.dumps([None, region]),
    }
    stage = copy.deepcopy(stages[shape])
    result = SimpleNamespace(json_result=[[{"label": "text", "content": "primary"}]],
        markdown_result="primary", raw_json_result=stage, original_images=[], image_files={})
    sdk = SimpleNamespace(glm=SimpleNamespace(process=lambda _request: [result]))
    assets = executors._Assets()
    raw, _markdown = executors._glm_page(sdk, {"page": 1, "image": Image.new("RGB", (3, 4))}, assets)
    assert raw["raw_json_result"] == stages[shape]
    assert raw["research_raw_stage_markdown"] == content
    blocks = executors.READERS["glm"](raw, 1, source_view="raw_json_result")
    assert [block["text"] for block in blocks] == ["", content]
    assert blocks[0]["read_error_category"] == "candidate_native_structure"
    assert blocks[1]["native_path"].endswith("/1/0") if shape in {
        "bad_page_before_nested", "declared_pages"} else blocks[1]["native_path"].endswith("/1")
    assert all(error["category"] == "candidate_native_structure" for error in assets.errors)
    assert stage == stages[shape]


async def single_page_worker(tmp_path, monkeypatch, pipeline, *, config_extra=None, sdk_extra=None):
    config = {"pipeline": pipeline, "timeout_seconds": 60, **(config_extra or {})}
    sdk = SimpleNamespace(spec=executors.PIPELINES[pipeline], control=RequestControl(config),
                          initialization_seconds=0, config=config, **(sdk_extra or {}))

    async def preprocess(*_args):
        return Path("not-read.pdf"), [{"page": 1, "source_prediction": "not_used", "width": 10,
                                     "height": 20, "image": Image.new("RGB", (10, 20))}]

    monkeypatch.setattr(executors, "_preprocess", preprocess)
    return await executors.execute_in_worker(Path("never-opened.pdf"), config, sample_id="synthetic",
                                             output_dir=tmp_path / "output", _sdks=sdk)


async def test_preserved_unsupported_native_html_is_candidate_partial_not_engineering(tmp_path, monkeypatch):
    html = "<table><tr><td>original -12.30%<table><tr><td>nested</td></tr></table></td></tr></table>"
    original = {"json_result": [{"label": "table", "content": html},
                                {"label": "text", "content": "neighbor"}]}

    def glm(*_args):
        return copy.deepcopy(original), html + "\n\nneighbor"

    monkeypatch.setattr(executors, "_glm_page", glm)
    observed = await single_page_worker(tmp_path, monkeypatch, "P05")
    assert observed["status"] == "partial"
    assert observed["pages"][0]["status"] == "candidate_partial"
    blocks = observed["pages"][0]["blocks"]
    assert [block["text"] for block in blocks] == [html, "neighbor"]
    assert blocks[0]["structure_status"] == "unknown"
    assert "read_error" in blocks[0] and "cells" not in blocks[0]
    assert all(error["category"] == "candidate_native_structure" for error in observed["errors"])
    saved = json.loads((tmp_path / "output/native.json").read_text())
    assert saved["pages"][0]["raw"] == original
    assert observed["timing"]["processing_seconds"] > 0


async def test_scalar_visual_region_is_partial_with_unknown_structure_and_raw_preserved(tmp_path, monkeypatch):
    stub_module(monkeypatch, "mineru_vl_utils.post_process.json2markdown", json2md=lambda blocks:
                "\n\n".join(block["content"] for block in blocks))
    original = [{"type": "text", "content": "before"}, None, {"type": "text", "content": "after"}]

    async def extract(*_args, **_kwargs):
        return original

    observed = await single_page_worker(tmp_path, monkeypatch, "P08", sdk_extra={
        "visual": SimpleNamespace(aio_two_step_extract=extract)})
    assert observed["status"] == "partial"
    assert observed["pages"][0]["status"] == "candidate_partial"
    assert observed["pages"][0]["structure_status"] == "unknown"
    assert [block["text"] for block in observed["pages"][0]["blocks"]] == ["before", "", "after"]
    assert all(error["category"] == "candidate_native_structure" for error in observed["errors"])
    saved = json.loads((tmp_path / "output/native.json").read_text())
    assert saved["pages"][0]["raw"][1] is None
    assert original == [{"type": "text", "content": "before"}, None, {"type": "text", "content": "after"}]
    assert (tmp_path / "output/faithful.md").read_text() == "before\n\nafter"


@pytest.mark.parametrize("error,category,status", [
    (executors.NativeReadError("declared native contract unavailable"), "candidate_native_structure", "partial"),
    (RuntimeError("unexpected implementation failure"), "engineering_failure", "readback_failed"),
])
async def test_reader_contract_and_unexpected_errors_have_different_categories(
    tmp_path, monkeypatch, error, category, status,
):
    raw = {"json_result": [{"label": "text", "content": "unaltered native"}]}
    monkeypatch.setattr(executors, "_glm_page", lambda *_args: (copy.deepcopy(raw), "unaltered native"))

    def reader(*_args, **_kwargs):
        raise error

    monkeypatch.setitem(executors.READERS, "glm", reader)
    observed = await single_page_worker(tmp_path, monkeypatch, "P05")
    assert observed["status"] == status
    assert observed["errors"][0]["category"] == category
    saved = json.loads((tmp_path / "output/native.json").read_text())
    assert saved["pages"][0]["raw"] == raw


@pytest.mark.parametrize("category,expected", [("engineering_failure", "export_failed"),
                                                ("candidate_native_structure", "partial")])
async def test_paddle_rpc_carries_received_export_errors_once_without_retry_or_raw_rewrite(
    tmp_path, monkeypatch, category, expected,
):
    diagnostic = {"stage": "media_export", "category": category, "scope_pages": [1],
                  "native_path": "markdown_images/bad.png", "retry": False, "native_preserved": True}
    original_raw = {"res": {"parsing_res_list": [{"block_label": "text", "block_content": "literal 12.30"}]},
                    "research_export_errors": [diagnostic, copy.deepcopy(diagnostic)]}
    calls = []

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def post(self, endpoint, *, json):
            calls.append(endpoint)
            payload = {"request_id": json["request_id"], "raw": copy.deepcopy(original_raw),
                       "faithful_markdown": "literal 12.30", "media": {}, "inference_runtime": {}}
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr("httpx.Client", Client)
    observed = await single_page_worker(tmp_path, monkeypatch, "P03", config_extra={"paddle_backend": "native-rpc"},
                                        sdk_extra={"paddle": "http://synthetic.invalid"})
    assert observed["status"] == expected
    assert len(observed["errors"]) == 1
    assert observed["errors"][0] == diagnostic
    assert len(calls) == 1
    assert observed["pages"][0]["blocks"][0]["text"] == "literal 12.30"
    saved = json.loads((tmp_path / "output/native.json").read_text())
    assert saved["pages"][0]["raw"]["research_export_errors"] == original_raw["research_export_errors"]
    assert saved["pages"][0]["raw"]["res"] == original_raw["res"]
