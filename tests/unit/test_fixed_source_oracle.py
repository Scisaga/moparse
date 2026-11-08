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
