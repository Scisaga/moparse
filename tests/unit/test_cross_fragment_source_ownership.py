"""Invented end-to-end source joins, boundaries and responsibility partitions."""

from copy import deepcopy

import pytest

from moparse_eval.document_ast_comparison import _original_content_sources, _same_record
from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    _semantic_literal,
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored


def production(tmp_path, text):
    expected = authored(tmp_path, text)
    graph = compile_requirement_graph(expected, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=expected)
    return expected, graph, evaluation_projection(graph)


def final_compare(required, candidate):
    actual = read_candidate_markdown(candidate, sample_id=required['sample_id'])
    result = grade_layers(required, actual)
    if result['publishable']:
        validate_evidence(result)
    else:
        with pytest.raises(ValueError):
            validate_evidence(result)
    return result


@pytest.mark.parametrize('parts', [
    ['The board', 'shall pay 17 credits only if approved by 4 directors.'],
    ['The board', 'shall pay 17 credits', 'only if approved by 4 directors.'],
    ['背景。The board', 'shall pay 17 credits', 'only if approved by 4 directors. Other items remain under discussion.'],
])
def test_joined_partial_reading_has_all_original_owners_without_a_duplicate_typed_vote(tmp_path, parts):
    text = '# Governance\n\n' + '\n\n'.join(parts)
    _, graph, required = production(tmp_path, text)
    assert graph['comparison_coverage']['responsibility_complete']
    assert not required['comparison_coverage']['retained_semantic_requirements']['B']
    for index, literal in enumerate(parts):
        owners = [b for b in graph['source_form_requirements'] if b['source']['lines'] == [3 + 2 * index] * 2]
        assert len(owners) == 1
        assert owners[0]['source']['text_span'] == [0, len(literal)]
        assert ''.join(n['text'] for n in owners[0]['content']['children']) == ''.join(literal.split())
    result = final_compare(required, text)
    assert result['publishable']
    assert result['layers']['B']['denominator'] == len(parts)
    # Different independent synthetic candidate inputs retain the fixed graph
    # denominator even when their segmentation, values or order differ.
    for candidate in [text.replace('17', '18'), '# Governance\n\n' + '\n\n'.join(reversed(parts)),
                      '# Governance\n\n' + '\n\n'.join(parts[:-1]),
                      '# Governance\n\n' + ' '.join(parts)]:
        changed = final_compare(required, candidate)
        assert changed['layers']['B']['denominator'] == len(parts)
        if candidate != '# Governance\n\n' + ' '.join(parts):
            assert not all(o['outcome'] == 'correct' for o in changed['outcomes'] if o['layer'] in {'B', 'L'})


def test_local_join_cut_keeps_nonzero_offsets_partial_ends_and_real_whitespace():
    first = {'path': 'invented', 'lines': [3, 3], 'text_span': [7, 15], 'block': 'a'}
    middle = {'path': 'invented', 'lines': [5, 5], 'text_span': [2, 8], 'block': 'b'}
    last = {'path': 'invented', 'lines': [7, 7], 'text_span': [9, 16], 'block': 'c'}
    source = {**first, 'text_span': [10, 25], 'joined_fragments': [
        {'source': first, 'text': 'AB  CD E', 'projected_text': 'AB CD E', 'joined_span': [0, 7]},
        {'source': middle, 'text': ' middle', 'projected_text': 'middle', 'joined_span': [8, 14]},
        {'source': last, 'text': 'last ZZ', 'joined_span': [15, 22]},
    ]}
    # The middle raw source really has seven characters, including its space.
    source['joined_fragments'][1]['source'] = {**middle, 'text_span': [2, 9]}
    assert _original_content_sources(source) == [
        {**first, 'text_span': [11, 15]},
        {**middle, 'text_span': [2, 9]},
        {**last, 'text_span': [9, 12]},
    ]
    inserted = {**source, 'text_span': [14, 15]}
    assert _original_content_sources(inserted) == []  # inserted join space


@pytest.mark.parametrize('mutation', ['offset', 'source', 'order', 'delete', 'gap', 'literal'])
def test_full_graph_source_guard_rejects_changed_join_provenance(tmp_path, mutation):
    parts = ['背景。The board', 'shall pay 17 credits', 'only if approved by 4 directors.']
    expected, graph, _ = production(tmp_path, '# Governance\n\n' + '\n\n'.join(parts))
    source = deepcopy(next(n['source'] for n in graph['nodes'] if n['source'].get('joined_fragments')))
    fragments = source['joined_fragments']
    if mutation == 'offset':
        fragments[0]['source']['text_span'][0] += 1
    elif mutation == 'source':
        fragments[1]['source']['lines'] = [7, 7]
    elif mutation == 'order':
        fragments[1], fragments[2] = fragments[2], fragments[1]
    elif mutation == 'delete':
        fragments.pop(1)
    elif mutation == 'gap':
        fragments[1]['joined_span'][0] += 1
    else:
        fragments[1]['text'] = fragments[1]['text'].replace('17', '18')
    assert _semantic_literal(graph['sources'], source) is None
    changed = deepcopy(graph)
    fact = next(n for n in changed['nodes'] if n['source'].get('joined_fragments'))
    fact['source'] = source
    with pytest.raises(ValueError):
        validate_requirement_graph(changed, expected=expected)


@pytest.mark.parametrize('barrier', ['## Other', '![preserved](invented.png)',
                                    '| Field | Value |\n| --- | --- |\n| Name | Delta |',
                                    'Independent inserted content.'])
def test_join_does_not_skip_intervening_authorized_objects(tmp_path, barrier):
    text = '# Governance\n\nThe board\n\n' + barrier + '\n\nshall pay 17 credits only if approved.'
    _, graph, required = production(tmp_path, text)
    assert not any(n.get('subject') == 'The board' and n.get('attribute') == 'pay' for n in graph['nodes'])
    result = final_compare(required, text)
    assert not any(o.get('actual', {}).get('source') == 'forged' for o in result['outcomes'] if isinstance(o.get('actual'), dict))


@pytest.mark.parametrize('first,second', [
    ('AI is supported by a global industrial network', 'These devices are manufactured using advanced machines.'),
    ('Training currently requires around 127 MW', '⁴ In practice, servers never attain maximum power.'),
])
def test_independent_finite_paragraphs_and_footnotes_remain_separate(tmp_path, first, second):
    text = '# Infrastructure\n\n' + first + '\n\n' + second
    _, graph, required = production(tmp_path, text)
    assert not any(n['source'].get('joined_fragments') for n in [*graph['nodes'], *graph['unresolved']])
    assert graph['comparison_coverage']['responsibility_complete']
    assert final_compare(required, text)['publishable']


def test_equal_literal_does_not_substitute_a_different_original_native_object():
    a = {'path': 'invented', 'lines': [], 'block': 'a', 'native_path': '/a', 'text_span': [0, 4]}
    assert not _same_record(a, {**a, 'block': 'b'})
    assert not _same_record(a, {**a, 'native_path': '/b'})
    assert not _same_record(a, {**a, 'cell': 'other'})


@pytest.mark.parametrize('first,second', [('甲方承諾履行約定。', '——周甲，甲方代表'),
                                         ('乙方承諾履行約定。', '——周乙，乙方代表')])
def test_all_words_with_attribution_in_the_wrong_order_cannot_pass_L(tmp_path, first, second):
    text = '# Statements\n\n' + first + '\n\n' + second
    _, _, required = production(tmp_path, text)
    assert final_compare(required, text)['publishable']
    changed = final_compare(required, '# Statements\n\n' + second + '\n\n' + first)
    assert any(o['outcome'] != 'correct' for o in changed['outcomes'] if o['layer'] == 'L')


@pytest.mark.parametrize('line,facts', [
    ('证券代码：000927\u3000证券简称：远海 A\u3000公告编号：2029-014',
     [('', '证券代码', '000927'), ('', '证券简称', '远海 A'), ('', '公告编号', '2029-014')]),
    ('（股份代號：927）', []),
    ('https://example.invalid/research?q=1', []),
])
def test_new_batch_readback_defects_have_independent_production_counterexamples(tmp_path, line, facts):
    _, graph, required = production(tmp_path, '# Announcements\n\n' + line)
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == facts
    assert graph['comparison_coverage']['responsibility_complete']
    assert final_compare(required, '# Announcements\n\n' + line)['publishable']


def test_colon_heading_and_parenthetical_exception_are_not_scalar_business_answers(tmp_path):
    text = '# Subject\n\n## 家庭（toH）：服务体验再升级\n\n截至2029年12月31日，发行人不存在对外担保（不包括对子公司的担保）事项。'
    _, graph, required = production(tmp_path, text)
    assert not graph['comparison_coverage']['retained_semantic_requirements']['B']
    assert any(r['type'] == 'heading_parent' for r in graph['relations'])
    assert graph['comparison_coverage']['responsibility_complete']
    result = final_compare(required, text)
    assert result['publishable']
    changed = final_compare(required, text.replace('不包括', '包括'))
    assert not all(r['outcome'] == 'correct' for r in changed['outcomes'] if r['layer'] in {'B', 'L'})


@pytest.mark.parametrize('separator', ['；', ';', '，插入的独立内容，'])
def test_analysis_join_cannot_erase_original_punctuation_or_inserted_words(tmp_path, separator):
    text = '# Governance\n\n董事會秘書接受專業培訓' + separator + '另行安排專門課程。'
    _, graph, required = production(tmp_path, text)
    for node in [*graph['nodes'], *graph['unresolved']]:
        origin = node['source']
        if origin.get('joined_fragments'):
            assert _semantic_literal(graph['sources'], origin) is not None
    assert ''.join(n['text'] for n in graph['document_ast']['children'][1]['content']['children']) == text.split('\n\n')[-1]
    assert final_compare(required, text)['publishable']
