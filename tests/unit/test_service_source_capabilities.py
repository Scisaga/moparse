"""Source readers receive only their permitted pages, including mixed runs."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.parse_result import DocumentParseResult, PageParseResult, ParsePipeline
from moparse_eval.service_evaluation import NoInference
from moparse_eval.service_native_adapters import branch_capabilities
from moparse_eval.service_source_policy import apply_source_stages
from moparse_eval.service_stages import capture_stage, stage_edit_ledger


@pytest.fixture(autouse=True)
def controlled_thread_boundary(monkeypatch):
    # Page permission is the oracle here. Do not depend on the host event
    # loop's executor shutdown to test which objects a source service sees.
    async def immediate(function, *args, **kwargs):
        return function(*args, **kwargs)
    monkeypatch.setattr('moparse_eval.service_source_policy.asyncio.to_thread', immediate)


def result():
    value = DocumentParseResult(document_id='fixture', filename='unopened.pdf', mime_type='application/pdf',
        page_count=2, processed_pages=2, pipeline=ParsePipeline(profile='balanced', primary='fixture'),
        pages=[PageParseResult(page_number=1, content='Native initial'), PageParseResult(page_number=2, content='Visual literal')])
    value._native_page_blocks = {1: [{'type': 'text', 'content': 'Native initial'}], 2: [{'type': 'text', 'content': 'Visual literal'}]}
    value._source_regions = [SimpleNamespace(page_number=1, ordinal=0), SimpleNamespace(page_number=2, ordinal=0)]
    return value


@pytest.mark.parametrize('pipeline,branches', [('P01', ['docling', 'glm']), ('P02', ['docling', 'glm']),
                                             ('P06', ['mineru', 'glm']), ('P07', ['mineru', 'glm'])])
def test_mixed_visual_page_never_enters_text_or_vector_service(pipeline, branches):
    value = result()
    bridge = {'pages': [{'raw_page': number, 'capabilities': branch_capabilities(pipeline, branch)}
                        for number, branch in enumerate(branches, 1)]}
    calls, snapshots = [], []
    def inspect(_source, pages):
        calls.append(('inspect', pages))
        assert pages == {1}
        return {1: 'controlled native evidence'}
    async def tables(scoped, _source, _options):
        calls.append(('tables', {page.page_number for page in scoped.pages}))
        assert set(scoped._native_page_blocks) == {1}
        scoped.pages[0].content = 'Native table stage'
    async def text(scoped, evidence, _options):
        calls.append(('text', {page.page_number for page in scoped.pages}))
        assert set(evidence) == set(scoped._native_page_blocks) == {1}
        scoped.pages[0].content = 'Native prose stage'
    def observe(stage, applicability):
        snapshots.append(capture_stage(value, stage=stage, sample_id='fixture', pages_only=True, applicability=applicability))
    evidence, timings, applicability = asyncio.run(apply_source_stages(
        value, bridge, Path('/unopened.pdf'), None, SimpleNamespace(), inspect_pages=inspect,
        apply_tables=tables, apply_text=text, on_stage=observe))
    assert calls == [('inspect', {1}), ('tables', {1}), ('text', {1})]
    assert set(evidence) == {1} and value.pages[1].content == 'Visual literal'
    assert [region.page_number for region in value._source_regions] == [1, 2]
    assert 'Native table stage' in snapshots[0]['markdown'] and 'Native prose stage' not in snapshots[0]['markdown']
    assert 'Native prose stage' in snapshots[1]['markdown']
    assert applicability['table_source']['not_applicable_pages'] == [2]
    assert set(timings) == {'page_evidence_seconds', 'table_source_seconds', 'native_text_seconds'}
    ledger = stage_edit_ledger(snapshots)
    assert ledger[0]['edits'][0]['before'] == 'Native table stage\n'
    assert ledger[0]['edits'][0]['after'] == 'Native prose stage\n'


@pytest.mark.parametrize('pipeline,branch', [('P03', 'paddle'), ('P04', 'paddle'), ('P05', 'glm'), ('P08', 'visual')])
def test_pure_visual_source_stages_are_explicitly_not_applicable(pipeline, branch):
    value = result()
    bridge = {'pages': [{'raw_page': page, 'capabilities': branch_capabilities(pipeline, branch)} for page in (1, 2)]}
    def forbidden(*_args):
        raise AssertionError('a visual branch reached a PDF text/vector service')
    evidence, _timings, applicability = asyncio.run(apply_source_stages(value, bridge, None, None, SimpleNamespace(),
        inspect_pages=forbidden, apply_tables=forbidden, apply_text=forbidden))
    assert evidence == {}
    assert all(item['applicable'] is False and item['reason'] == 'no_permitted_native_branch'
               for item in applicability.values())
    assert value.pages[1].content == 'Visual literal'


def test_unexpected_evidence_page_is_an_engineering_error():
    bridge = {'pages': [{'raw_page': 1, 'capabilities': branch_capabilities('P01', 'docling')}]}
    with pytest.raises(ValueError, match='escaped'):
        asyncio.run(apply_source_stages(result(), bridge, None, None, SimpleNamespace(),
                                       inspect_pages=lambda *_args: {2: 'unpermitted'}))


def test_no_inference_stub_rejects_recognition_and_parser_execution():
    stub = NoInference()
    with pytest.raises(RuntimeError, match='inference is forbidden'):
        asyncio.run(stub.recognize_image(None))
    with pytest.raises(RuntimeError, match='parser execution is forbidden'):
        asyncio.run(stub.parse(None))
    assert stub.calls == 2
