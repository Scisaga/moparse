"""Mutation checks for independently authored source assertions, invented only."""

from copy import deepcopy

import pytest

from moparse_eval.document_ast_comparison import _original_content_sources
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from tests.unit.test_cjk_circumstance_contract import authored
from tests.validation.lite_source_oracle import check_fixed_source_graph


def independent_sample(tmp_path):
    text = '# 外层\n\n## 内层\n\n董事會秘書接受專業培訓。\n\n事务所：远海'
    assertions = {'ranges': [(1, 7)], 'sources': [
        {'line': 1, 'role': 'H1', 'anchors': ['外层'], 'scope': [], 'parents': [], 'record': None},
        {'line': 3, 'role': 'H2', 'anchors': ['内层'], 'scope': ['外层'], 'parents': [], 'record': None},
        {'line': 5, 'role': 'P', 'anchors': ['董事會秘書', '專業培訓'],
         'scope': ['外层', '内层'], 'parents': [], 'record': None},
        {'line': 7, 'role': 'F', 'anchors': ['事务所：远海'],
         'scope': ['外层', '内层'], 'parents': [], 'record': None},
    ]}
    original = authored(tmp_path, text)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    return graph, original, assertions


def test_substantive_source_assertions_execute_before_derived_ids_are_bound(tmp_path):
    graph, original, assertions = independent_sample(tmp_path)
    cases = check_fixed_source_graph(graph, original, assertions)
    assert len(cases) == 5  # Four substantive source assertions plus blank gaps.
    assert all(c['status'] == 'passed' and c['expected']['source_assertions'] for c in cases)
    case = next(c for c in cases if c['case_id'].endswith('L7'))
    assert case['actual']['typed_facts'] == [('', '事务所', '远海', {})]
    assert case['requirement_ids'] and case['obligation_ids']


@pytest.mark.parametrize('mutation', ['leaf', 'scope', 'typed_value', 'typed_scope', 'typed_delete',
                                     'heading_parent', 'omit_source', 'content_delete', 'content_overlap'])
def test_source_oracle_rejects_real_content_and_relation_corruption(tmp_path, mutation):
    graph, original, assertions = independent_sample(tmp_path)
    changed = deepcopy(graph)
    facts = [n for n in changed['nodes'] if n['id'] in changed['comparison_coverage']['retained_semantic_requirements']['B']]
    fact, = facts
    if mutation == 'leaf':
        changed['document_ast']['children'][2]['content']['children'].pop()
    elif mutation == 'scope':
        changed['document_ast']['children'][2]['scope'] = ['别处']
    elif mutation == 'typed_value':
        fact['value'] = '近山'
    elif mutation == 'typed_scope':
        fact['scope'] = ['别处']
    elif mutation == 'typed_delete':
        changed['nodes'].remove(fact)
    elif mutation == 'heading_parent':
        changed['relations'] = [r for r in changed['relations'] if r['type'] != 'heading_parent']
    elif mutation == 'omit_source':
        changed['document_ast']['children'].pop()
    elif mutation == 'content_delete':
        changed['source_form_requirements'] = []
    else:
        extra = deepcopy(changed['document_ast']['children'][-1])
        extra['requirement_id'] = 'forged:overlap'
        extra['source'] = deepcopy(extra['content']['source'])
        changed['source_form_requirements'].append(extra)
    with pytest.raises((AssertionError, ValueError)):
        check_fixed_source_graph(changed, original, assertions)


def test_source_case_cannot_claim_unreviewed_nonblank_content_is_whitespace(tmp_path):
    graph, original, assertions = independent_sample(tmp_path)
    changed = deepcopy(original)
    changed['authorized_raw_segments'][0]['raw'] = changed['authorized_raw_segments'][0]['raw'].replace(
        '# 外层\n\n', '# 外层\n遗漏的独立正文。\n', 1)
    with pytest.raises(AssertionError, match='unreviewed substantive source'):
        check_fixed_source_graph(graph, changed, assertions)


def test_joined_analysis_ownership_projects_absolute_offsets_to_all_original_fragments():
    source = {'path': 'invented', 'lines': [1, 1], 'text_span': [9, 15], 'joined_fragments': [
        {'source': {'path': 'invented', 'lines': [1, 1], 'text_span': [7, 11]},
         'text': '甲乙丙丁', 'joined_span': [0, 4]},
        {'source': {'path': 'invented', 'lines': [3, 3], 'text_span': [2, 6]},
         'text': '戊己庚辛', 'joined_span': [4, 8]},
    ]}
    assert _original_content_sources(source) == [
        {'path': 'invented', 'lines': [1, 1], 'text_span': [9, 11]},
        {'path': 'invented', 'lines': [3, 3], 'text_span': [2, 6]},
    ]


def representation_sample(tmp_path, text, *, policy, typed_facts=()):
    original = authored(tmp_path, '# 范围\n\n' + text)
    expected = {'ranges': [(1, 3)], 'sources': [
        {'line': 1, 'role': 'H1', 'anchors': ['范围'], 'scope': [], 'parents': [], 'record': None},
        {'line': 3, 'role': 'P', 'anchors': [text], 'scope': ['范围'], 'parents': [], 'record': None,
         'representation': policy, 'typed_facts': list(typed_facts)},
    ]}
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    return graph, original, expected


def test_required_complete_measurement_cannot_fall_back_to_intact_whole_content(tmp_path):
    graph, original, expected = representation_sample(tmp_path, 'Revenue: 17万元', policy='typed',
        typed_facts=[('', 'Revenue', '17', {'unit': '万元'})])
    check_fixed_source_graph(graph, original, expected)
    changed = deepcopy(graph)
    # Simulate a reader returning full, source-valid lexical content instead
    # of the independently required typed quantity. The Oracle is called
    # directly; rejection must come from its representation declaration.
    whole = deepcopy(changed['document_ast']['children'][-1])
    whole['source'] = deepcopy(whole['content']['source'])
    whole['requirement_id'] = 'content:reader-fallback'
    changed['source_form_requirements'] = [whole]
    changed['comparison_coverage']['retained_semantic_requirements']['B'] = []
    with pytest.raises(AssertionError, match='required typed representation'):
        check_fixed_source_graph(changed, original, expected)


def test_authorized_body_content_does_not_require_a_universal_SVO_analysis(tmp_path):
    text = '董事會秘書接受專業培訓的時間為18小時以上。'
    graph, original, expected = representation_sample(tmp_path, text, policy='content')
    cases = check_fixed_source_graph(graph, original, expected)
    assert cases[1]['expected']['representation_policy'] == 'content'
    assert cases[1]['actual']['typed_facts'] == []


@pytest.mark.parametrize('mutation', ['partial', 'duplicate', 'hole', 'overlap'])
def test_independent_representation_policy_requires_an_exact_mixed_partition(tmp_path, mutation):
    text = '流動資產為人民幣80億元。董事會秘書接受專業培訓的時間為18小時以上。'
    graph, original, expected = representation_sample(tmp_path, text, policy='mixed',
        typed_facts=[('流動資產', '為', '80', {'unit': '億元', 'currency': '人民幣'})])
    check_fixed_source_graph(graph, original, expected)
    changed = deepcopy(graph)
    content = changed['source_form_requirements'][0]
    if mutation == 'duplicate':
        changed['source_form_requirements'].append(deepcopy(content))
    elif mutation == 'partial':
        content['source']['text_span'][1] -= 1
        content['content']['source']['text_span'][1] -= 1
        content['content']['children'].pop()
    elif mutation == 'hole':
        content['source']['text_span'][0] += 1
        content['content']['source']['text_span'][0] += 1
        content['content']['children'].pop(0)
    else:
        extra = deepcopy(changed['document_ast']['children'][-1])
        extra['source'] = deepcopy(extra['content']['source'])
        extra['requirement_id'] = 'content:overlap'
        changed['source_form_requirements'].append(extra)
    with pytest.raises((AssertionError, ValueError)):
        check_fixed_source_graph(changed, original, expected)


def test_preauthorized_either_representation_still_rejects_a_proper_content_substring(tmp_path):
    text = '董事會秘書接受專業培訓的時間為18小時以上。'
    graph, original, expected = representation_sample(tmp_path, text, policy='either',
        typed_facts=[('董事會秘書', '接受', '專業培訓的時間為18小時以上', {'polarity': 'positive'})])
    check_fixed_source_graph(graph, original, expected)
    content = graph['source_form_requirements'][0]
    # Even a fully valid local lexical AST cannot replace the whole statement.
    content['content']['children'].pop()
    content['content']['source']['text_span'][1] -= 1
    content['source']['text_span'][1] -= 1
    with pytest.raises((AssertionError, ValueError)):
        check_fixed_source_graph(graph, original, expected)
