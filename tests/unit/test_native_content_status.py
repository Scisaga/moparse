"""Independent JSON state cases; source identities are strings, never media I/O."""

from copy import deepcopy
from pathlib import Path

import pytest

from app.models.source import StoredSource
from moparse_eval.saved_content_closure import close_saved_document


def content_input(pipeline="P03", count=1):
    literals = ["Printed standalone 17.", "Printed second 23."][:count]
    if pipeline in {"P01", "P02"}:
        texts = [{"self_ref": f"#/texts/{i}", "parent": {"$ref": "#/body"},
                  "label": "text", "text": text, "children": [],
                  "prov": [{"page_no": 1, "charspan": [0, len(text)],
                            "bbox": {"l": 10, "t": 10+i*30, "r": 100, "b": 25+i*30,
                                     "coord_origin": "TOPLEFT"}}]} for i, text in enumerate(literals)]
        return {"pipeline": pipeline, "config": {"pipeline": pipeline},
                "pages": [{"page": 1, "branch": "docling", "raw": {
                    "native_document": "#/documents/0", "source_page": 1}}],
                "documents": [{"status": "ConversionStatus.SUCCESS", "errors": [],
                    "research_group_pages": [1], "document": {
                        "body": {"self_ref": "#/body", "children": [{"$ref": t["self_ref"]} for t in texts]},
                        "groups": [], "texts": texts, "pictures": [], "tables": [],
                        "pages": {"1": {"size": {"width": 120, "height": 200}}}}}]}
    if pipeline in {"P03", "P04"}:
        regions = [{"block_id": i, "block_label": "text", "block_content": text,
                    "block_bbox": [10, 10+i*30, 100, 25+i*30],
                    "block_order": None, "group_id": 7} for i, text in enumerate(literals)]
        raw = {"res": {"page_index": None, "width": 120, "height": 200,
                       "model_settings": {"use_doc_preprocessor": False}, "parsing_res_list": regions}}
        branch = "paddle"
    else:
        raw = {"json_result": [[{"label": "text", "content": text} for text in literals]]}
        branch = "glm"
    return {"pipeline": pipeline, "config": {"pipeline": pipeline},
            "pages": [{"page": 1, "branch": branch, "raw": raw}]}


def observed(native, **extra):
    return {"pipeline": native["pipeline"], "status": "completed",
            "pages": [{"page": p["page"], "branch": p["branch"], "status": "completed"}
                      for p in native["pages"]], **extra}


async def finish(native, execution=None):
    pages = len(native["pages"])
    source = StoredSource(path=Path("/not-mounted/unused.pdf"), filename="unused.pdf",
                          mime_type="application/pdf", size_bytes=12, page_count=pages)
    original = deepcopy(native)
    result, evidence = await close_saved_document(native, source, sample_id="invented",
        declared_source_sha256="a" * 64, source_pages=list(range(81, 81+pages)),
        original_observation=observed(native) if execution is None else execution)
    assert native == original
    assert result.markdown == evidence["stages"][-1]["markdown"]
    return result, evidence


@pytest.mark.asyncio
async def test_single_region_unknown_group_and_rank_do_not_create_output_obligations():
    result, evidence = await finish(content_input())
    assert evidence["states"]["original_execution"]["status"] == "completed"
    assert evidence["states"]["readback"]["status"] == "read"
    assert evidence["states"]["conversion"]["status"] == "completed"
    assert evidence["states"]["delivery"]["status"] == "completed"
    assert "Printed standalone 17." in result.markdown


@pytest.mark.asyncio
async def test_unknown_order_with_two_glm_regions_blocks_the_actual_order_obligation():
    result, evidence = await finish(content_input("P05", 2))
    assert evidence["states"]["conversion"]["status"] == "partial"
    assert evidence["states"]["delivery"]["status"] == "partial"
    assert "Printed standalone 17." in result.markdown and "Printed second 23." in result.markdown


@pytest.mark.asyncio
async def test_docling_v2_reaches_the_existing_evidence_and_finalization():
    result, evidence = await finish(content_input("P02"))
    assert result._native_content is not None and result._native_content.pipeline == "P02"
    assert evidence["states"]["conversion"]["status"] == "completed"
    assert evidence["states"]["delivery"]["status"] == "completed"
    assert "Printed standalone 17." in result.markdown


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["P01", "P02", "P03", "P04", "P05"])
async def test_equivalent_singleton_responsibilities_have_the_same_four_states(pipeline):
    result, evidence = await finish(content_input(pipeline))
    s = evidence["states"]
    assert [s[k]["status"] for k in ("original_execution", "readback", "conversion", "delivery")] == [
        "completed", "read", "completed", "completed"]
    assert s["delivery"]["partial_reasons"] == []
    assert all(i["warning_only"] and not i["requires_partial"] for i in s["impacts"])
    assert "Printed standalone 17." in result.markdown
    if pipeline in {"P03", "P04"}:
        assert {w["code"] for w in evidence["warnings"]} >= {
            "native_reading_order_unverified", "native_group_semantics_unknown"}
        assert {i["code"] for i in s["impacts"]} >= {
            "native_reading_order_unverified", "native_group_semantics_unknown"}
        assert all(i["sources"][0]["artifact_sha256"] == result._native_content.artifact.sha256
                   and i["objects"] for i in s["impacts"])


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["P01", "P02", "P03", "P04", "P05"])
async def test_pairwise_order_requires_actual_order_evidence(pipeline):
    result, evidence = await finish(content_input(pipeline, 2))
    s = evidence["states"]
    expected = "completed" if pipeline in {"P01", "P02"} else "partial"
    assert [s[k]["status"] for k in ("original_execution", "readback", "conversion", "delivery")] == [
        "completed", "read", expected, expected]
    assert all(t in result.markdown for t in ("Printed standalone 17.", "Printed second 23."))
    if expected == "partial":
        order = [i for i in s["delivery"]["partial_reasons"] if i["effects"]["reading_order"]]
        assert len(order) == 2 and all(i["dependencies"][0]["obligation"] == "order_multiple_output_occurrences" for i in order)
        assert len({i["objects"][0] for i in order}) == 2
        groups = [i for i in s["impacts"] if i["code"] == "native_group_semantics_unknown"]
        assert all(i["warning_only"] for i in groups)


@pytest.mark.asyncio
async def test_page_local_repeated_group_values_do_not_create_cross_page_parentage():
    n = content_input()
    n["pages"].append(deepcopy(n["pages"][0]))
    n["pages"][1]["page"] = 2
    result, evidence = await finish(n)
    s = evidence["states"]
    assert [s[k]["status"] for k in ("original_execution", "readback", "conversion", "delivery")] == [
        "completed", "read", "completed", "completed"]
    assert result.markdown.count("Printed standalone 17.") == 2
    assert all(b["parent_id"] is None and b["group_identity"]["cross_page_relationship"] == "unknown"
               for values in result._native_page_blocks.values() for b in values)
    groups = [i for i in s["impacts"] if i["code"] == "native_group_semantics_unknown"]
    assert len(groups) == 2 and groups[0]["sources"] != groups[1]["sources"]
    assert all(i["warning_only"] for i in groups) and not s["delivery"]["partial_reasons"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["purpose", "cell", "media", "failed", "timeout", "truncated", "information", "continuation"])
async def test_independent_obligations_keep_their_source_and_layer(case):
    n = content_input()
    raw = n["pages"][0]["raw"]
    region = raw["res"]["parsing_res_list"][0]
    obs = observed(n)
    if case in {"purpose", "cell"}:
        region.update(block_label="table", block_content=(
            "<table><tr><td>Printed standalone 17.</td><td>Unclassified prose.</td></tr></table>"
            if case == "purpose" else
            "<table><tr><th>Item</th><th>Revenue</th></tr><tr><td>Printed standalone 17.</td></tr></table>"))
    elif case == "media":
        region["block_content"] += " ![printed declaration](assets/not-read.png)"
    elif case in {"failed", "timeout"}:
        obs.update(status=case)
        obs["pages"][0].update(status=case)
        if case == "timeout":
            obs["timed_out"] = obs["pages"][0]["timed_out"] = True
    elif case == "truncated":
        raw["res"].update(status="completed", truncated=True, stop_reason="length")
    elif case == "information":
        obs["warnings"] = [{"code": "original_information", "message": "Informational only."}]
    else:
        region["merge_prev"] = True
    result, evidence = await finish(n, obs)
    s = evidence["states"]
    assert s["original_execution"]["status"] == (case if case in {"failed", "timeout"} else "completed")
    assert s["readback"]["status"] == "read"
    assert s["conversion"]["status"] == ("partial" if case in {"purpose", "cell", "continuation"} else "completed")
    assert s["delivery"]["status"] == ("completed" if case == "information" else "partial")
    assert "Printed standalone 17." in result.markdown
    assert bool(s["delivery"]["partial_reasons"]) == (case != "information")
    assert all(i["sources"] and i["affected_output_fields"] for i in s["impacts"])
    assert {w["code"] for w in evidence["warnings"]} >= {
        "native_reading_order_unverified", "native_group_semantics_unknown"}
    if case == "information":
        assert s["original_execution"]["warnings"] == obs["warnings"]
        assert not any(i["requires_partial"] for i in s["impacts"])
    elif case in {"failed", "timeout", "truncated"}:
        assert any(i["category"] == "original_execution" for i in s["delivery"]["partial_reasons"])
        assert all(not i["blocks_conversion"] for i in s["delivery"]["partial_reasons"])
    elif case == "media":
        assert s["delivery"]["media"]["declared"] == 1 and s["delivery"]["media"]["delivered"] == 0
        assert [i["code"] for i in s["delivery"]["partial_reasons"]] == ["native_media_not_delivered"]
    elif case == "continuation":
        assert any(i["code"] == "native_group_semantics_unknown" and i["blocks_conversion"]
                   for i in s["impacts"])


@pytest.mark.asyncio
async def test_native_structure_error_is_not_unknown_metadata_or_original_failure():
    n = content_input()
    n["pages"][0]["raw"]["res"]["parsing_res_list"][0]["block_content"] = {"malformed": "not text"}
    result, evidence = await finish(n)
    s = evidence["states"]
    assert [s[k]["status"] for k in ("original_execution", "readback", "conversion", "delivery")] == [
        "completed", "partial", "partial", "partial"]
    assert any(i["blocks_conversion"] and i["sources"] for i in s["impacts"])
    assert result._native_page_blocks[1][0]["native_payload"]["block_content"] == {"malformed": "not text"}


@pytest.mark.asyncio
async def test_adapter_exception_is_an_engineering_exception_without_a_fake_final(monkeypatch):
    import app.adapters.saved_native as adapter
    def broken(*args, **kwargs):
        raise RuntimeError("invented adapter engineering failure")
    monkeypatch.setattr(adapter, "read_paddle_blocks", broken)
    with pytest.raises(RuntimeError, match="engineering failure"):
        await finish(content_input())


@pytest.mark.asyncio
async def test_final_text_loss_cannot_be_relabelled_as_upstream_unknown(monkeypatch):
    from app.services.final_content_service import FinalContentService
    from app.services.native_content_evidence import NativeContentError
    actual = FinalContentService.apply
    def broken(self, result):
        actual(self, result)
        result.markdown = ""
        result.parse_result.renderings.markdown = ""
    monkeypatch.setattr(FinalContentService, "apply", broken)
    with pytest.raises(NativeContentError, match="producer edits"):
        await finish(content_input())


@pytest.mark.asyncio
async def test_unknown_input_transform_is_not_a_crop_obligation_in_text_only_mode():
    n = content_input()
    n["pages"][0]["raw"]["res"]["model_settings"]["use_doc_preprocessor"] = True
    result, evidence = await finish(n)
    b = result._native_page_blocks[1][0]
    assert b["geometry_status"] == "unknown" and b["service_bbox"] is None
    s = evidence["states"]
    assert not [i['code'] for i in s['impacts'] if i['requires_partial']]
    assert [s[k]["status"] for k in ("original_execution", "readback", "conversion", "delivery")] == [
        "completed", "read", "completed", "completed"], s["impacts"]
    geometry = next(i for i in s["impacts"] if i["code"] == "native_geometry_transform_unknown")
    assert geometry["warning_only"] and geometry["affected_output_fields"] == ["native_metadata.geometry", "ir.bbox"]
    assert "Printed standalone 17." in result.markdown


@pytest.mark.asyncio
async def test_one_complete_table_does_not_require_unknown_outer_region_order_or_group():
    n = content_input()
    n["pages"][0]["raw"]["res"]["parsing_res_list"][0].update(
        block_label="table", block_content="<table><tr><th>Item</th><th>Revenue</th></tr>"
        "<tr><td>Alpha</td><td>17</td></tr></table>")
    result, evidence = await finish(n)
    s = evidence["states"]
    assert [s[k]["status"] for k in ("original_execution", "readback", "conversion", "delivery")] == [
        "completed", "read", "completed", "completed"]
    assert evidence["semantic_tables"][0]["status"] == "converted"
    assert "Revenue：17" in result.markdown
    assert all(not i["requires_partial"] for i in s["impacts"])


@pytest.mark.asyncio
async def test_unknown_region_order_does_not_authorize_an_adjacent_continuation_join():
    n = content_input(count=2)
    n["pages"][0]["raw"]["res"]["parsing_res_list"][1]["merge_prev"] = True
    result, evidence = await finish(n)
    assert "Printed standalone 17.\n\nPrinted second 23." in result.markdown
    assert not result._final_text_evidence["joined_paragraphs"]
    assert evidence["states"]["conversion"]["status"] == "partial"
    assert result._final_text_evidence["unresolved_continuations"][0]["native_path"].endswith("/1")


@pytest.mark.asyncio
async def test_a_body_omitted_before_finalization_is_an_engineering_handoff_error(monkeypatch):
    from app.services.export_service import ExportService
    from app.services.native_content_evidence import NativeContentError
    actual = ExportService.apply_document
    def broken(self, result):
        actual(self, result)
        result.markdown = result.markdown.replace("Printed standalone 17.", "")
    monkeypatch.setattr(ExportService, "apply_document", broken)
    with pytest.raises(NativeContentError, match="final content occurrence"):
        await finish(content_input())


@pytest.mark.asyncio
async def test_unhandled_content_cannot_be_waived_by_clearing_reader_issue_lists():
    from app.services.native_content_evidence import native_partial
    n = content_input()
    n["pages"][0]["raw"]["res"]["parsing_res_list"][0]["block_label"] = "unhandled-semantic-element"
    result, _ = await finish(n)
    bridge = result._source_verification["saved_native_bridge"]
    bridge["errors"].clear()
    for page in bridge["pages"]:
        page["local_read_errors"].clear()
    assert native_partial(result)


@pytest.mark.asyncio
async def test_malformed_native_text_cannot_be_promoted_by_clearing_read_flags():
    from app.services.native_content_evidence import NativeContentError, validate_native_content
    n = content_input()
    n["pages"][0]["raw"]["res"]["parsing_res_list"][0]["block_content"] = {"bad": "shape"}
    result, _ = await finish(n)
    block = result._native_page_blocks[1][0]
    block.pop('read_error')
    block['read_status'] = 'read'
    with pytest.raises(NativeContentError, match="malformed native text"):
        validate_native_content(result)


@pytest.mark.asyncio
async def test_a_table_without_a_conversion_account_cannot_be_completed(monkeypatch):
    from app.models.parse_options import ContentParseOptions
    from app.services.saved_content_service import SavedContentService
    from app.services.table_semantics_service import TableSemanticsService
    from moparse_eval.service_replay_native import replay_native
    n = content_input()
    n["pages"][0]["raw"]["res"]["parsing_res_list"][0].update(
        block_label="table", block_content="<table><tr><th>Item</th><th>Revenue</th></tr>"
        "<tr><td>Alpha</td><td>17</td></tr></table>")
    async def missing_conversion(*args, **kwargs):
        return None
    monkeypatch.setattr(TableSemanticsService, 'apply', missing_conversion)
    source = StoredSource(path=Path('/not-mounted/unused.pdf'), filename='unused.pdf',
                          mime_type='application/pdf', size_bytes=12, page_count=1)
    options = ContentParseOptions()
    result, _ = replay_native(n, source, options, document_id='invented', include_source_markers=True,
                              original_observation=observed(n))
    await SavedContentService().finalize(result, source, options, declared_source_sha256='a'*64)
    s = result._source_verification['native_content']
    assert [s[k]['status'] for k in ('original_execution', 'readback', 'conversion', 'delivery')] == [
        'completed', 'read', 'partial', 'partial']
    assert any(i['code'] == 'table_conversion_not_accounted' and i['sources'] for i in s['delivery']['partial_reasons'])
    assert 'Alpha' in result.markdown and '17' in result.markdown
