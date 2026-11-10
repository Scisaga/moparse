"""Mutation checks for independently authored source assertions, invented only."""

from copy import deepcopy

import pytest

from moparse_eval.document_ast_comparison import _original_content_sources
from moparse_eval.requirement_graph import compile_requirement_graph, validate_requirement_graph
from tests.unit.test_cjk_circumstance_contract import authored
from tests.validation.lite_source_oracle import (
    _check_directory_source,
    check_fixed_source_graph,
    fixed_assertion_catalogue,
    handwritten_assertion_identity,
    source_in_target,
)


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


def test_collected_source_failures_preserve_both_defects_and_execute_later_sources(tmp_path):
    graph, original, expected = independent_sample(tmp_path)
    changed = deepcopy(graph)
    changed['document_ast']['children'][2]['content']['children'].pop()
    fact = next(n for n in changed['nodes']
                if n['id'] in changed['comparison_coverage']['retained_semantic_requirements']['B'])
    fact['value'] = '近山'
    cases = check_fixed_source_graph(changed, original, expected, collect_failures=True)
    sources = [case for case in cases if case.get('source_assertion_case')]
    assert len(sources) == len(expected['sources'])
    assert [(case['input']['source']['lines'][0], case['status']) for case in sources] == [
        (1, 'passed'), (3, 'passed'), (5, 'failed'), (7, 'failed')]
    assert sources[-1]['expected']['source_assertions']['anchors'] == ['事务所：远海']
    assert sources[-1]['actual']['typed_facts'][0]['value'] == '近山'
    assert sources[-1]['traceback'] and sources[-1]['observed_requirement_ids']
    assert sources[-1]['requirement_ids'] == []
    assert any(case['failure_stage'] == 'coverage_and_order' for case in cases if case['status'] == 'failed')
    with pytest.raises((AssertionError, ValueError)):
        check_fixed_source_graph(changed, original, expected)


def test_collecting_a_missing_document_block_does_not_skip_later_assertions(tmp_path):
    graph, original, expected = independent_sample(tmp_path)
    changed = deepcopy(graph)
    changed['document_ast']['children'].pop(1)
    cases = check_fixed_source_graph(changed, original, expected, collect_failures=True)
    assert any(case['failure_stage'] == 'document_structure' for case in cases if case['status'] == 'failed')
    sources = [case for case in cases if case.get('source_assertion_case')]
    assert [case['status'] for case in sources] == ['passed', 'failed', 'passed', 'passed']
    assert sources[1]['input']['source']['lines'] == [3, 3]
    assert 'document source block missing' in sources[1]['detail']


def test_multiline_source_owns_actual_raw_interior_rows_without_borrowing_a_neighbor(tmp_path):
    text = '# Closing\n\nNora Vale\nChair\nHarbor City, 12 May 2030\n\nThe board retained the stated limits.'
    original = authored(tmp_path, text)
    expected = {'ranges': [(1, 7)], 'sources': [
        {'line': 1, 'role': 'H1', 'anchors': ['Closing'], 'scope': [], 'parents': []},
        {'line': 3, 'role': 'P', 'anchors': ['Nora Vale', 'Chair', 'Harbor City, 12 May 2030'],
         'scope': ['Closing'], 'parents': []},
        {'line': 7, 'role': 'P', 'anchors': ['The board retained the stated limits.'],
         'scope': ['Closing'], 'parents': []},
    ]}
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    cases = check_fixed_source_graph(graph, original, expected)
    case = next(case for case in cases if case['input'].get('source', {}).get('lines') == [3, 5])
    raw = [row for row in graph['comparison_coverage']['obligations']
           if row['obligation_id'].startswith('authorized-raw-obligation:') and row['source']['lines'][0] in (3, 4, 5)]
    assert len(raw) == 3 and {row['obligation_id'] for row in raw} <= set(case['obligation_ids'])
    target = next(target for target in original['targets'] if target['reference']['lines'] == [3, 5])
    path = target['reference']['path']
    assert source_in_target({'path': path, 'lines': [4, 4]}, target, original)
    assert not source_in_target({'path': path, 'lines': [7, 7]}, target, original)
    assert not source_in_target({'path': path + '.neighbor', 'lines': [4, 4]}, target, original)
    assert not source_in_target({'path': path, 'lines': [4, 4], 'text_span': [0, 5]}, target, original)
    changed = deepcopy(original)
    changed['authorized_raw_segments'][0]['raw'] = text.replace('Nora Vale\nChair', 'Nora Vale\nAnother Chair')
    assert not source_in_target({'path': path, 'lines': [4, 4]}, target, changed)


def test_all_handwritten_modules_are_bound_without_replacing_historical_batches(tmp_path):
    from tests.validation import lite_fixed_source_assertions as historical
    from tests.validation.lite_source_oracle import (
        CONTROLLED_REVIEW_MODULES,
        REVIEW_MODULES,
        STAGE3_MODULES,
    )

    before = deepcopy((historical.ASSERTIONS, historical.ADDITIONAL_ASSERTIONS))
    catalogue = fixed_assertion_catalogue()
    assert len(catalogue['review_ids']) == 23
    assert len(catalogue['stage3_ids']) == 1
    assert len(catalogue['assertions']) - len(catalogue['stage3_ids']) + 3 == 55
    assert (historical.ASSERTIONS, historical.ADDITIONAL_ASSERTIONS) == before
    paths = ['tests/validation/lite_fixed_source_assertions.py']
    paths += [name.replace('.', '/') + '.py' for name in (*REVIEW_MODULES, *STAGE3_MODULES, *CONTROLLED_REVIEW_MODULES)]
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('independent hand assertions: ' + name)
    first = handwritten_assertion_identity(tmp_path)
    (tmp_path / paths[-2]).write_text('changed independent assertion')
    second = handwritten_assertion_identity(tmp_path)
    assert first['handwritten_assertions_sha256'] == second['handwritten_assertions_sha256']
    assert first['handwritten_assertions_aggregate_sha256'] != second['handwritten_assertions_aggregate_sha256']
    assert first['handwritten_assertion_modules_sha256'].keys() == set(paths)
    assert first['handwritten_assertion_modules_sha256'][paths[-2]] != second['handwritten_assertion_modules_sha256'][paths[-2]]


def test_multiline_markdown_controls_require_an_exact_independent_physical_transcription(tmp_path):
    text = '# Closing\n\nNora Vale\\\n*Chair*\\\nHarbor City, 12 May 2030'
    original = authored(tmp_path, text)
    physical = {3: 'Nora Vale\\', 4: '*Chair*\\', 5: 'Harbor City, 12 May 2030'}
    expected = {'ranges': [(1, 5)], 'sources': [
        {'line': 1, 'role': 'H1', 'anchors': ['Closing'], 'scope': [], 'parents': []},
        {'line': 3, 'role': 'P', 'anchors': ['Nora Vale', 'Chair', 'Harbor City, 12 May 2030'],
         'scope': ['Closing'], 'parents': [], 'physical_lines': physical},
    ]}
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    cases = check_fixed_source_graph(graph, original, expected)
    source = next(case for case in cases if case['input'].get('source', {}).get('lines') == [3, 5])
    assert source['status'] == 'passed'
    assert any(ident.startswith('authorized-raw-obligation:') for ident in source['obligation_ids'])
    target = original['targets'][-1]
    interior = {'path': target['reference']['path'], 'lines': [4, 4]}
    assert not source_in_target(interior, target, original)
    assert source_in_target(interior, target, original, physical_lines=physical)
    assert not source_in_target(interior, target, original, physical_lines={**physical, 4: '*Other*\\'})
    assert not source_in_target(interior, target, original, physical_lines={4: '*Chair*\\'})


def test_complete_directory_text_cannot_disguise_a_page_reference_as_a_metric(tmp_path):
    original = authored(tmp_path, '# Contents\n\n## North\n\n- Summary: 017')
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    assert graph['comparison_coverage']['responsibility_complete']
    _check_directory_source(graph, original, (5, 'North', 'Summary', '017'))
    changed = deepcopy(graph)
    [fact] = [f for f in changed['nodes'] if f['id'] in changed['comparison_coverage']['retained_semantic_requirements']['B']]
    fact['semantic_type'] = 'metric'
    # Independent corruption remains rejected after normal production works.
    with pytest.raises(AssertionError, match='navigation page role'):
        _check_directory_source(changed, original, (5, 'North', 'Summary', '017'))


def test_independent_binding_override_preserves_the_required_subject_attachment(tmp_path):
    text = 'Members of all oversight committees are directors.'
    graph, original, expected = representation_sample(tmp_path, text, policy='typed',
        typed_facts=[('Members of all oversight committees', 'be', 'directors',
                      {'polarity': 'positive', 'tense': 'present'})])
    expected['sources'][-1]['binding_qualifiers'] = {'tense': 'present'}
    expected['required_relations'] = {3: [{
        'type': 'narrative_prepositional_attachment',
        'left': {'preposition': 'of', 'semantic_role': 'complement',
                 'attachment': {'kind': 'nominal', 'head': 'Members'}, 'complement': 'all oversight committees'},
        'right': {'subject': 'Members of all oversight committees', 'attribute': 'be',
                  'scope': ['范围'], 'qualifiers': {'tense': 'present'}},
    }]}
    check_fixed_source_graph(graph, original, expected)
    changed = deepcopy(graph)
    changed['relations'] = [edge for edge in changed['relations'] if edge['type'] != 'narrative_prepositional_attachment']
    with pytest.raises(AssertionError, match='independently required relation'):
        check_fixed_source_graph(changed, original, expected)


def test_whole_content_owns_the_only_vote_for_its_statement_parent_scope(tmp_path):
    from moparse_eval.expected_report import validate_evidence
    from moparse_eval.requirement_graph import evaluation_projection
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown

    text = 'The archive retains security code 004721 for the retired issue.'
    graph, original, expected = representation_sample(tmp_path, text, policy='content')
    assert not graph['comparison_coverage']['retained_semantic_requirements']['B']
    assert graph['source_form_requirements'][0]['source']['text_span'] == [0, len(text)]
    assert all(case['status'] == 'passed' for case in check_fixed_source_graph(graph, original, expected))
    assert not graph['comparison_coverage']['retained_semantic_requirements']['L']
    [owner] = graph['comparison_coverage']['content_relation_ownership']
    assert owner['relation'] == 'statement_parent_scope'
    assert owner['owners'][0]['counted_relation_id'] == 'L:content:0'
    assert any(e['id'] == owner['analysis_relation_id'] for e in graph['relations'])
    required = evaluation_projection(graph)
    score = grade_layers(required, read_candidate_markdown('# 范围\n\n' + text, sample_id=required['sample_id']))
    assert score['layers']['B']['denominator'] == score['layers']['L']['denominator'] == 1
    assert [r['id'] for r in score['outcomes'] if r['layer'] == 'L'] == ['L:content:0']
    assert score['layers']['L']['numerator'] == 1
    validate_evidence(score)


def test_injected_duplicate_parent_scope_is_still_rejected(tmp_path):
    from moparse_eval.requirement_graph import evaluation_projection
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown

    text = 'The archive retains security code 004721 for the retired issue.'
    graph, original, expected = representation_sample(tmp_path, text, policy='content')
    duplicate = graph['comparison_coverage']['content_relation_ownership'][0]['analysis_relation_id']
    graph['comparison_coverage']['retained_semantic_requirements']['L'].append(duplicate)
    with pytest.raises(AssertionError, match='duplicate statement parent-scope responsibility'):
        check_fixed_source_graph(graph, original, expected)
    with pytest.raises(ValueError, match='comparison responsibility coverage'):
        validate_requirement_graph(graph, expected=original)
    required = evaluation_projection(graph)
    with pytest.raises(ValueError, match='fixed comparison responsibility'):
        grade_layers(required, read_candidate_markdown('# 范围\n\n' + text, sample_id=required['sample_id']))
