"""Invented event-bearing text; no corpus, OCR, parser or reference access."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.parse_options import ContentParseOptions
from app.models.source import StoredSource
from app.services.export_service import ExportService
from app.services.final_content_service import FinalContentService, apply_text_edits
from app.services.multimodal_service import MultimodalService
from moparse_eval.service_observation import build_service_observation, read_final_observation
from moparse_eval.service_replay_native import replay_native


def _block(role, text, **extra):
    return {"type": role, "content": text, "bbox": [.1, .1, .9, .8], "angle": 0, **extra}


def _result(pages):
    native = {"pipeline": "P08", "pages": [
        {"page": i, "branch": "visual", "raw": blocks} for i, blocks in enumerate(pages, 1)
    ]}
    before = deepcopy(native)
    source = StoredSource(path=Path('/unopened.pdf'), filename='synthetic.pdf', mime_type='application/pdf',
                          size_bytes=1, page_count=len(pages))
    result, diagnostics = replay_native(native, source, ContentParseOptions(), document_id='synthetic')
    assert native == before
    assert not diagnostics['errors']
    result.markdown, result.plain_text = ExportService().join_pages(result.pages, preserve_page_breaks=True)
    return result


def test_visual_roles_and_continuation_preserve_entity_action_negation_period_and_value():
    result = _result([
        [_block('doc_title', '甲辰科技股份有限公司'), _block('title', '资产收购'),
         _block('text', '公司于2025年6月3日签订协议，拟以人民币'), _block('page_number', '1')],
        [_block('text', '1,200万元收购乙辰公司60%股权，尚未完成交割。', merge_prev=True),
         _block('footer', '甲辰科技董事会\n2025年6月4日')],
    ])
    FinalContentService().apply(result)
    assert '# 甲辰科技股份有限公司' in result.markdown
    assert '## 资产收购' in result.markdown
    assert '拟以人民币1,200万元收购乙辰公司60%股权，尚未完成交割。' in result.markdown
    assert '甲辰科技董事会\n2025年6月4日' in result.markdown
    assert '<!--' not in result.markdown and '\f' not in result.markdown
    assert len(result._final_text_evidence['joined_paragraphs']) == 1
    assert apply_text_edits(result._final_text_evidence['assembly_markdown'],
                            result._final_text_evidence['edits']) == result.markdown
    observed, _ = read_final_observation(build_service_observation(result, sample_id='invented', pipeline='P08+MO-Parse'))
    assert observed['service_output']['final_markdown'] == result.markdown
    blocks = observed['pages'][0]['blocks']
    assert all(block['text'] == result.markdown[slice(*block['final_markdown_span'])] for block in blocks)
    assert any(block['provenance_pages'] == [2] and '尚未完成' in block['text'] for block in blocks)
    assert not any(block['text'].strip() == '1' for block in blocks)


@pytest.mark.parametrize('middle', ['title', 'table', 'image'])
def test_continuation_never_jumps_a_heading_table_or_image(middle):
    material = '<table><tr><td>保留材料</td></tr></table>' if middle == 'table' else '保留材料'
    result = _result([[_block('text', '第一主体。'), _block(middle, material),
                       _block('text', '另一主体。', merge_prev=True)]])
    FinalContentService().apply(result)
    assert not result._final_text_evidence['joined_paragraphs']
    assert '第一主体。另一主体。' not in result.markdown
    assert '第一主体。' in result.markdown and '另一主体。' in result.markdown


def test_only_repeated_header_copy_is_removed_and_dates_are_not_furniture():
    result = _result([
        [_block('header', '甲辰科技股份有限公司'), _block('text', '甲辰公司于今日签约。'),
         _block('footer', '签署日期：2025年1月2日')],
        [_block('header', '甲辰科技股份有限公司'), _block('header', '2025年度经营情况'),
         _block('text', '乙辰公司未签约。'), _block('footer', '签署日期：2025年1月2日')],
    ])
    FinalContentService().apply(result)
    assert result.markdown.count('甲辰科技股份有限公司') == 1
    assert result.markdown.count('签署日期：2025年1月2日') == 2
    assert '2025年度经营情况' in result.markdown
    assert '乙辰公司未签约。' in result.markdown


def test_source_code_examples_of_internal_comments_survive_cleanup():
    result = _result([[_block('text', '正文示例 `<!-- page: 27 -->`。\n\n```html\n<!-- page: 29 -->\n```')]])
    FinalContentService().apply(result)
    assert '`<!-- page: 27 -->`' in result.markdown
    assert '<!-- page: 29 -->' in result.markdown
    assert '<!-- page: 1 -->' not in result.markdown


@pytest.mark.parametrize('malformed', [None, 'unreadable block', 17, ['invalid']])
def test_unreadable_native_block_keeps_valid_neighbors_and_blocks_continuation(malformed):
    result = _result([[_block('text', '甲公司尚未完成交割。'),
                       _block('text', '乙公司仍需股东大会批准。', merge_prev=True)]])
    result._native_page_blocks[1].insert(1, malformed)
    before = deepcopy(result._native_page_blocks)
    FinalContentService().apply(result)
    assert '甲公司尚未完成交割。' in result.markdown
    assert '乙公司仍需股东大会批准。' in result.markdown
    assert not result._final_text_evidence['joined_paragraphs']
    assert result._native_page_blocks == before


def test_native_bold_punctuation_does_not_publish_literal_stars_or_change_business_text():
    first, rest = '甲辰公司尚未完成交割。', '拟以1,200万元收购乙辰公司60%股权。'
    raw = '**' + first + '**' + rest
    result = _result([[_block('text', raw)]])
    result._native_page_blocks[1][0]['content'] = [
        {'type': 'text', 'content': first, 'styles': ['bold']},
        {'type': 'text', 'content': rest, 'styles': []},
    ]
    FinalContentService().apply(result)
    assert '<strong>' + first + '</strong>' + rest in result.markdown
    assert result.plain_text.strip() == first + rest
    assert result._final_text_evidence['operation_counts']['explicit_native_inline_style'] == 1
    observed, _ = read_final_observation(build_service_observation(result, sample_id='invented'))
    assert observed['service_output']['final_markdown'] == result.markdown


@pytest.mark.parametrize('children', [
    [{'type': 'text', 'content': 'literal ** stars', 'styles': ['bold']}],
    [{'type': 'text', 'content': '甲公司。', 'styles': ['italic']}],
    [{'type': 'inline_equation', 'content': 'x+y', 'styles': []}],
])
def test_inline_style_fix_never_guesses_literal_markup_or_unknown_native_styles(children):
    result = _result([[_block('text', '**甲公司。**保留原文。')]])
    result._native_page_blocks[1][0]['content'] = children
    FinalContentService().apply(result)
    assert '**甲公司。**保留原文。' in result.markdown
    assert 'explicit_native_inline_style' not in result._final_text_evidence['operation_counts']


def test_without_native_declaration_no_sentence_is_invented():
    result = _result([[_block('text', '甲公司拟收购')], [_block('text', '乙公司未出售。')]])
    FinalContentService().apply(result)
    assert not result._final_text_evidence['joined_paragraphs']
    assert '甲公司拟收购乙公司未出售。' not in result.markdown


def test_published_reader_refuses_a_hidden_answer_not_in_final_text():
    result = _result([[_block('text', '已披露金额100万元。')]])
    FinalContentService().apply(result)
    result.markdown = result.markdown.replace('100', '999')
    with pytest.raises(ValueError, match='edit ledger'):
        build_service_observation(result, sample_id='invented')


def test_visual_layout_only_containers_and_images_accept_sdk_optional_content():
    result = _result([[_block('list', None), _block('image', None),
                       _block('text', '甲公司未完成收购。')]])
    assert len(result._picture_candidates) == 1
    assert result._native_page_blocks[1][0]['content'] is None
    assert result._native_page_blocks[1][1]['content'] is None
    assert not result.warnings
    FinalContentService().apply(result)
    assert '甲公司未完成收购。' in result.markdown
    assert '<!-- image -->' not in result.markdown


def test_declared_continuation_uses_published_native_text_after_source_selection():
    result = _result([[_block('text', '甲公司于6月1日计划以人民币')],
                      [_block('text', '200万元收购乙公司。', merge_prev=True)]])
    result.markdown = result.markdown.replace('6月1日', '6月2日')
    result._source_verification['native_text_reconstruction'] = {'pages': [
        {'page': 1, 'actions': [{'action': 'selected_native_region', 'region': 0,
                               'rendered_replacement': '甲公司于6月2日计划以人民币'}]},
    ]}
    FinalContentService().apply(result)
    assert '甲公司于6月2日计划以人民币200万元收购乙公司。' in result.markdown


def test_pdf_asset_metadata_stays_outside_business_text_and_image_references_remain():
    from app.models.content_result import AssetRole
    result = SimpleNamespace(
        renderings=SimpleNamespace(markdown='甲公司尚未签约。\n\n![源图](/assets/a)', plain_text='甲公司尚未签约。'),
        assets=[SimpleNamespace(role=AssetRole.PAGE_CROP, download_url=url, visual_analysis=None)
                for url in ['/assets/a', '/assets/b']],
    )
    MultimodalService._project_pdf_images(result)
    assert result.renderings.markdown.count('/assets/a') == 1
    assert result.renderings.markdown.count('/assets/b') == 1
    assert '甲公司尚未签约。' in result.renderings.markdown
    assert '图片资产' not in result.renderings.markdown
    assert '下载' not in result.renderings.markdown
    assert '/assets/' not in result.renderings.plain_text
