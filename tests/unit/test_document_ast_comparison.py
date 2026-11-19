"""Independent invented documents for structure/content comparison, not NLP."""

from copy import deepcopy

import pytest

from moparse_eval.document_ast_comparison import _candidate_ast
from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored

DOCUMENT = ('# 治理\n\n## 委員會\n\n本年度，遠海公司的審計委員會由5名成員組成，每年至少召開3次會議。\n\n'
            '## 培訓\n\n董事會秘書接受專業培訓的時間為18小時以上。')


def required_document(tmp_path, text=DOCUMENT):
    original = authored(tmp_path, text)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    assert graph['unresolved']  # Kept limitations of sentence interpretation.
    assert graph['content_comparison_ready']
    assert len(graph['source_form_units']) == 2
    return graph, evaluation_projection(graph)


def compare(required, text):
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    score = grade_layers(required, actual)
    if score['publishable']:
        validate_evidence(score)
    else:
        with pytest.raises(ValueError):
            validate_evidence(score)
    return score


def test_typed_only_document_still_authenticates_both_trees(tmp_path):
    from moparse_eval.ast_alignment import METHOD

    text = '# Figures\n\n- Balance: 12'
    graph = compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast')
    required = evaluation_projection(graph)
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    assert not required['source_form_requirements'] and len(required['business']) == 1
    score = grade_layers(required, actual)
    validate_evidence(score)
    assert score['layers']['B']['score'] == 100
    assert score['document_comparison']['base_score']['layers']['B']['denominator'] == 1
    altered = deepcopy(required)
    altered['document_ast']['children'][-1]['parents'] = ['unprinted owner']
    for method in (None, METHOD):
        with pytest.raises(ValueError, match='source selection'):
            grade_layers(altered, actual, scoring_method=method)
    actual['document_ast'] = _candidate_ast(actual)
    actual['document_ast']['children'][-1]['parents'] = ['unprinted owner']
    with pytest.raises(ValueError, match='actual native syntax'):
        grade_layers(required, actual)


def test_both_document_trees_keep_own_cell_spans_and_native_header_declarations(tmp_path):
    from moparse_eval.ast_alignment import METHOD

    table = ('<table><tr><th colspan="2" scope="colgroup">Periods</th></tr>'
             '<tr><td rowspan="2">North</td><td>12</td></tr><tr><td>15</td></tr></table>')
    graph = compile_requirement_graph(authored(tmp_path, table), comparison_contract='document_ast')
    required = evaluation_projection(graph)
    actual = read_candidate_markdown(table, sample_id=required['sample_id'])
    actual['document_ast'] = _candidate_ast(actual)
    for tree in (required['document_ast'], actual['document_ast']):
        cells = {''.join(n['text'] for n in b['content']['children']): b
                 for b in tree['children'] if b['role'] == 'table_cell'}
        assert cells['Periods']['cell_structure']['col_span'] == 2
        assert cells['Periods']['cell_structure']['native_declarations']['native_attributes']['scope'] == 'colgroup'
        assert cells['North']['cell_structure']['row_span'] == 2
        assert cells['North']['parents'] == []
        assert not cells['North']['cell_structure']['native_declarations'].get('native_header_tag')
    cell = next(b for b in actual['document_ast']['children'] if b['role'] == 'table_cell')
    cell['cell_structure']['col_span'] = 9
    for method in (None, METHOD):
        with pytest.raises(ValueError, match='actual native syntax'):
            grade_layers(required, actual, scoring_method=method)


NESTED_LIST = ('# 周转指标\n\n- 口径甲\n'
               '  - 周转率：下限≥8；2025年12月31日期末10.5%、月均不适用；2024年12月31日期末9.1%、月均8%。')
NESTED_GRID = ('# 周转指标\n\n<table><tr><th rowspan="2" colspan="2">指标</th><th rowspan="2">下限</th>'
               '<th colspan="2">2025-12-31</th><th colspan="2">2024-12-31</th></tr>'
               '<tr><th>期末（%）</th><th>月均（%）</th><th>期末（%）</th><th>月均（%）</th></tr>'
               '<tr><td>口径甲</td><td>周转率</td><td>≥8</td><td>10.5</td><td>不适用</td>'
               '<td>9.1</td><td>8</td></tr></table>')


def compare_nested(tmp_path, markdown, expected=NESTED_LIST):
    from moparse_eval.ast_alignment import METHOD
    from moparse_eval.continuous_projection import extend_projection

    graph = compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast')
    required = evaluation_projection(graph)
    actual = read_candidate_markdown(markdown, sample_id=required['sample_id'])
    actual['document_ast'] = _candidate_ast(actual)
    strict = grade_layers(required, actual)
    continuous = grade_layers(extend_projection(graph, required), actual, scoring_method=METHOD)
    proof, = [r['decision']['proof'] for r in strict['document_comparison']['decision']['proof']['rows']
              if r['required'].get('record')]
    return strict, continuous, proof


@pytest.mark.parametrize('extra', [False, True])
def test_expected_leaf_is_entailed_by_its_own_row_date_and_shared_header_unit(tmp_path, extra):
    grid = NESTED_GRID
    if extra:
        grid = grid.replace('<th colspan="2">2025', '<th rowspan="2">峰值</th><th colspan="2">2025')
        grid = grid.replace('<td>≥8</td>', '<td>≥8</td><td>99</td>')
    strict, continuous, proof = compare_nested(tmp_path, grid)
    for score in (strict, continuous):
        assert score['layers']['B']['score'] == score['layers']['L']['score'] == 100
        assert score['layers']['T']['score'] < 100
    assert proof['extra_paths'] == ([['', '峰值']] if extra else [])
    assert len(proof['components']) == 5
    field, = [p for p in proof['components'] if p['path'] == ['2025-12-31', '期末']]
    value = field['actual']
    assert field['status'] == 'entailed' and not field['value_used_for_location']
    assert value['unit']['text'] == '%' and value['unit']['source']['row'] == 1
    assert value['number']['text'] == '10.5' and value['number']['source']['row'] == 2
    assert value['unit']['source']['col'] == value['number']['source']['col']
    date = next(c for c in proof['actual']['children'] if c['kind'] == 'period')
    assert date['label']['source']['row'] == 0
    assert proof['actual']['row_path'][0]['text'] == '口径甲'
    validate_evidence(strict)


@pytest.mark.parametrize(('old', 'new', 'wrong'), [
    ('<td>≥8</td>', '<td>≤8</td>', ['', '下限']),
    ('<td>不适用</td>', '<td>0</td>', ['2025-12-31', '月均']),
    ('<th>期末（%）</th>', '<th>期末（万元）</th>', ['2025-12-31', '期末']),
    ('<td>10.5</td>', '<td></td>', ['2025-12-31', '期末']),
])
def test_one_conflicting_leaf_cannot_use_a_sibling_as_its_witness(tmp_path, old, new, wrong):
    strict, continuous, proof = compare_nested(tmp_path, NESTED_GRID.replace(old, new, 1))
    assert [p['path'] for p in proof['components'] if p['status'] != 'entailed'] == [wrong]
    assert proof['layout_correct']
    assert 0 < continuous['layers']['B']['score'] < 100
    assert strict['layers']['B']['score'] < 100


def test_opaque_cell_with_a_printed_header_keeps_its_neighbors_and_location(tmp_path):
    strict, continuous, proof = compare_nested(tmp_path, NESTED_GRID.replace('<td>10.5</td>', '<td>待复核</td>'))
    assert [p['status'] for p in proof['components']] == ['entailed', 'unresolved', 'entailed', 'entailed', 'entailed']
    for score in (strict, continuous):
        assert score['layers']['B']['score'] is None
        assert score['layers']['L']['score'] == 100


def test_scope_and_original_occurrence_are_required_before_choosing_a_matching_number(tmp_path):
    row = NESTED_GRID[NESTED_GRID.index('<tr><td>'):-len('</table>')]
    duplicated = NESTED_GRID.replace('</table>', row.replace('10.5', '91') + '</table>')
    _, _, proof = compare_nested(tmp_path, duplicated)
    assert len(proof['candidate_sources']) == 2 and proof['status'] == 'unresolved'
    # A correct alternative in another titled table cannot rescue the first cell.
    changed = NESTED_GRID.replace('10.5', '91') + '\n\n' + NESTED_GRID.replace('# 周转指标', '# 另一组')
    _, _, proof = compare_nested(tmp_path, changed)
    assert [p['path'] for p in proof['components'] if not p['credit']] == [['2025-12-31', '期末']]


def test_replaced_matrix_issue_has_the_specific_row_header_and_cell_witnesses(tmp_path):
    from moparse_eval.record_ast import resolved_matrix_issues

    row = NESTED_GRID[NESTED_GRID.index('<tr><td>'):-len('</table>')]
    grid = NESTED_GRID.replace('</table>', row.replace('口径甲', '口径乙') + '</table>')
    strict, _, _ = compare_nested(tmp_path, grid)
    actual = strict['document_comparison']['inputs']['actual']
    proofs = strict['document_comparison']['candidate_record_bindings']
    assert len(proofs) == 14
    wrong_header = deepcopy(proofs[-1]['issue'])
    wrong_header['header_ids'] = proofs[0]['issue']['header_ids']
    assert not resolved_matrix_issues(_candidate_ast(actual)['children'], [wrong_header])


def test_split_corner_and_wrapped_parent_are_local_proofs(tmp_path):
    grid = NESTED_GRID.replace('<th rowspan="2" colspan="2">指标</th>', '<th colspan="2"></th>')
    grid = grid.replace('<tr><th>期末', '<tr><th colspan="2">指标</th><th>期末')
    grid = grid.replace('口径甲', '依据《管理\n（甲）》')
    expected = NESTED_LIST.replace('口径甲', '依据《管理（甲）》')
    strict, continuous, proof = compare_nested(tmp_path, grid, expected)
    assert all(s['layers']['B']['score'] == 100 for s in (strict, continuous))
    record = proof['actual']
    assert record['blank_corner']['text'] == '' and record['row_axis']['text'] == '指标'
    assert record['blank_corner']['source']['row'] == 0 and record['row_axis']['source']['row'] == 1
    # The rest of a truncated title in a neighboring data row cannot supply this parent.
    truncated = grid.replace('依据《管理\n（甲）》', '依据《管理')
    _, _, proof = compare_nested(tmp_path, truncated, expected)
    assert proof['status'] == 'unresolved' and not proof['spans']


def test_record_unit_declaration_applies_only_to_covered_numeric_leaves(tmp_path):
    expected = NESTED_LIST.replace('10.5%', '10.5').replace('9.1%', '9.1').replace('8%', '8')
    expected = expected.replace('- 口径甲', '单位：%。各年分别列期末、月均。\n\n- 口径甲')
    grid = NESTED_GRID.replace('（%）', '').replace('<table>', '（单位：%）\n\n<table>')
    _, _, proof = compare_nested(tmp_path, grid, expected)
    assert proof['status'] == 'equivalent'
    assert all(p['status'] == 'entailed' for p in proof['components'])
    for part in proof['components']:
        for side in ('expected', 'actual'):
            field = part[side]
            if field.get('number'):
                assert field['unit']['text'] == '%' and field['unit']['source']['lines'] == [3, 3]
                assert field['unit_declaration_source']['lines'] == [3, 3]
            else:
                assert 'unit' not in field
    wrong = grid.replace('单位：%', '单位：万元')
    _, _, proof = compare_nested(tmp_path, wrong, expected)
    assert [p['status'] for p in proof['components']] == ['conflict','conflict','entailed','conflict','conflict']
    interrupted = grid.replace('（单位：%）\n\n', '') + '\n\n注：另表说明。\n\n（单位：%）'
    _, _, proof = compare_nested(tmp_path, interrupted, expected)
    assert [p['status'] for p in proof['components']] == ['unresolved','unresolved','entailed','unresolved','unresolved']


def test_cached_record_witness_must_equal_the_two_independently_rebuilt_trees(tmp_path):
    graph = compile_requirement_graph(authored(tmp_path, NESTED_LIST), comparison_contract='document_ast')
    required = evaluation_projection(graph)
    actual = read_candidate_markdown(NESTED_GRID, sample_id=required['sample_id'])
    actual['document_ast'] = _candidate_ast(actual)
    record = next(b['record'] for b in actual['document_ast']['children'] if 'record' in b)
    record['children'][1]['children'][0]['unit']['source']['col'] += 1
    with pytest.raises(ValueError, match='actual native syntax'):
        grade_layers(required, actual)


def test_unprinted_outer_scope_keeps_local_field_proofs_without_accepting_full_record(tmp_path):
    expected = NESTED_LIST.replace('# 周转指标', '# 样本报告\n\n## 综合口径\n\n### 周转指标')
    actual = NESTED_GRID.replace('# 周转指标', '# 样本报告\n\n## 周转指标')
    strict, continuous, proof = compare_nested(tmp_path, actual, expected)
    assert proof['reason'] == 'record_outer_scope_unproven'
    assert proof['expected_scope'] == ['样本报告','综合口径','周转指标']
    assert proof['observed_scope'] == ['样本报告','周转指标']
    assert not proof['spans'] and not proof['layout_correct'] and proof['status'] == 'unresolved'
    assert len(proof['components']) == 5 and all(p['status'] == 'entailed' for p in proof['components'])
    assert strict['layers']['B']['score'] is None and continuous['layers']['B']['score'] is None
    # A different printed local section supplies a contradictory placement.
    _, _, conflict = compare_nested(tmp_path, actual.replace('## 周转指标', '## 采购指标'), expected)
    assert conflict['status'] == 'conflict' and not conflict['components']


def test_complete_content_is_comparable_without_parsing_chinese_grammar(tmp_path):
    graph, required = required_document(tmp_path)
    assert len(graph['document_ast']['children']) == 5
    score = compare(required, DOCUMENT)
    assert score['publishable'], score['blockers']
    assert all(layer['score'] == 100 for layer in score['layers'].values())
    assert score['document_comparison']['semantic_limitations_retained'] == required['blockers']
    assert [r['outcome'] for r in score['outcomes'] if r['id'].startswith('B:content:')] == ['correct', 'correct']


def test_unparsed_nominal_purpose_can_be_preserved_without_inventing_an_attachment(tmp_path):
    text = DOCUMENT.replace('董事會秘書接受專業培訓的時間為18小時以上。',
                            '獨立委員積極參與調研，為公司發展建言獻策。')
    _, required = required_document(tmp_path, text)
    score = compare(required, text)
    assert score['publishable'], score['blockers']
    assert score['layers']['B']['score'] == 100


@pytest.mark.parametrize('before,after,index', [('18', '19', 1), ('小時', '年', 1), ('以上', '以下', 1)])
def test_explicit_typed_changes_are_local_errors_with_intact_denominators(tmp_path, before, after, index):
    _, required = required_document(tmp_path)
    good = compare(required, DOCUMENT)
    score = compare(required, DOCUMENT.replace(before, after))
    assert score['publishable'], score['blockers']
    assert score['layers']['L']['score'] == 100
    assert score['layers']['T']['score'] < 100
    assert {k: v['denominator'] for k, v in score['layers'].items()} == {k: v['denominator'] for k, v in good['layers'].items()}
    assert [r['outcome'] for r in score['outcomes'] if r['id'].startswith('B:content:')] == [
        'incorrect' if i == index else 'correct' for i in range(2)]


@pytest.mark.parametrize('before,after', [('至少', '最少'), ('小時', '小时'), ('18', '18.0')])
def test_declared_token_equivalence_preserves_business_content_but_not_literal_text(tmp_path, before, after):
    _, required = required_document(tmp_path)
    score = compare(required, DOCUMENT.replace(before, after))
    assert score['publishable'], score['blockers']
    assert score['layers']['B']['score'] == score['layers']['L']['score'] == 100
    assert score['layers']['T']['score'] < 100


def test_unbound_scale_and_number_changes_remain_unresolved_instead_of_false_business_errors(tmp_path):
    text = DOCUMENT.replace('18小時', '18萬元')
    _, required = required_document(tmp_path, text)
    score = compare(required, text.replace('18萬元', '0.0018億元'))
    assert not score['publishable']
    assert any(b['reason'] == 'source_form_typed_equivalence_unresolved' for b in score['blockers'])


def test_layout_markers_and_cjk_line_wrapping_do_not_require_new_semantics(tmp_path):
    _, required = required_document(tmp_path)
    changed = DOCUMENT.replace('董事會秘書接受', '- 董事會秘書接受\n  ')
    score = compare(required, changed)
    assert score['publishable'], score['blockers']
    assert score['layers']['B']['score'] == score['layers']['L']['score'] == 100


def test_adjacent_native_fragments_are_aligned_without_skipping_inserted_content(tmp_path):
    _, required = required_document(tmp_path)
    split = DOCUMENT.replace('組成，每年', '組成，\n\n每年')
    score = compare(required, split)
    assert score['publishable'], score['blockers']
    assert score['layers']['B']['score'] == score['layers']['L']['score'] == 100
    assert len(score['document_comparison']['decision']['proof']['rows'][0]['actual_indices']) == 2
    interrupted = split.replace('組成，\n\n每年', '組成，\n\n## 其他業務\n\n每年')
    score = compare(required, interrupted)
    # Partial words on either side of a new scope cannot be joined. A failed
    # retrieval alone does not prove absence or a supported semantic conflict.
    assert next(row for row in score['outcomes'] if row['id'] == 'B:content:0')['outcome'] == 'unresolved'
    assert not score['publishable']


def test_unknown_paraphrase_stays_unresolved_instead_of_becoming_a_false_business_error(tmp_path):
    _, required = required_document(tmp_path)
    score = compare(required, DOCUMENT.replace('專業培訓', '職業教育'))
    assert not score['publishable']
    assert any(b['reason'] == 'wording_change_requires_semantic_comparison' for b in score['blockers'])
    assert next(row for row in score['outcomes'] if row['id'] == 'B:content:1')['software_failure']


def test_scope_conflicts_cannot_borrow_the_identical_neighbor_text(tmp_path):
    _, required = required_document(tmp_path)
    parts = DOCUMENT.split('\n\n')
    parts[2], parts[4] = parts[4], parts[2]
    score = compare(required, '\n\n'.join(parts))
    assert score['layers']['L']['score'] < 100
    assert [r['outcome'] for r in score['outcomes'] if r['id'].startswith('B:content:')] == ['incorrect', 'incorrect']


def test_repeated_shapes_are_not_selected_by_the_correct_number(tmp_path):
    text = ('# 治理\n\n委員會由5名成員組成，每年至少召開3次會議。\n\n'
            '委員會由8名成員組成，每年至少召開6次會議。')
    _, required = required_document(tmp_path, text)
    score = compare(required, text)
    assert not score['publishable']
    rows = score['document_comparison']['decision']['proof']['rows']
    assert all(r['decision']['rule_id'] == 'document_block_identity_ambiguous' for r in rows)
    assert all(not r['retrieval']['value_used'] for r in rows)


@pytest.mark.parametrize('mutation', ['leaf', 'node', 'scope', 'borrow', 'role'])
def test_internal_ast_corruption_is_rejected_even_when_all_original_words_remain(tmp_path, mutation):
    _, required = required_document(tmp_path)
    actual = read_candidate_markdown(DOCUMENT, sample_id=required['sample_id'])
    actual['document_ast'] = _candidate_ast(actual)
    blocks = actual['document_ast']['children']
    if mutation == 'leaf':
        blocks[2]['content']['children'].pop()
    elif mutation == 'node':
        blocks.pop()
    elif mutation == 'scope':
        blocks[2]['scope'] = ['錯誤父項']
    elif mutation == 'borrow':
        blocks[2]['content']['children'][0]['source'] = deepcopy(blocks[4]['content']['children'][0]['source'])
    else:
        blocks[2]['content']['children'][0]['role'] = 'number'
    with pytest.raises(ValueError):
        grade_layers(required, actual)


def test_expected_coverage_and_final_outcomes_are_independently_rechecked(tmp_path):
    graph, required = required_document(tmp_path)
    mutated = deepcopy(graph)
    mutated['document_ast']['children'].pop()
    with pytest.raises(ValueError):
        validate_requirement_graph(mutated)
    score = compare(required, DOCUMENT)
    next(row for row in score['outcomes'] if row['id'] == 'B:content:0')['outcome'] = 'incorrect'
    with pytest.raises(ValueError):
        validate_evidence(score)


def test_synchronized_scope_payload_cannot_override_the_printed_heading_tree(tmp_path):
    _, required = required_document(tmp_path)
    actual = read_candidate_markdown(DOCUMENT, sample_id=required['sample_id'])
    actual['syntax'][2]['scope'] = ['治理', '培訓']
    with pytest.raises(ValueError, match='heading'):
        grade_layers(required, actual)


def test_typed_financial_ast_and_source_form_proof_share_one_layer_aggregation(tmp_path):
    text = ('# 財務\n\n流動資產為人民幣80億元，比上年末增加人民幣9億元。\n\n' + DOCUMENT)
    _, required = required_document(tmp_path, text)
    good = compare(required, text)
    assert good['publishable'], good['blockers']
    assert good['layers']['B']['denominator'] == 4  # Two quantities and two content assertions.
    bad = compare(required, text.replace('18小時', '19小時'))
    assert bad['publishable'] and bad['layers']['B']['numerator'] == 3
    assert all(row['outcome'] == 'correct' for row in bad['outcomes'] if row['layer'] == 'B' and ':content:' not in row['id'])


@pytest.mark.parametrize('pipeline', [f'P{i:02}' for i in range(1, 9)])
def test_normalized_native_document_uses_the_same_comparator_for_every_pipeline(tmp_path, pipeline):
    from moparse_eval.three_layer import read_candidate

    _, required = required_document(tmp_path)
    texts = [('heading', '治理', 1), ('heading', '委員會', 2),
             ('text', '本年度，遠海公司的審計委員會由5名成員組成，每年至少召開3次會議。', 0),
             ('heading', '培訓', 2), ('text', '董事會秘書接受專業培訓的時間為18小時以上。', 0)]
    observation = {'sample_id': required['sample_id'], 'pipeline': pipeline, 'status': 'completed',
        'relations': [], 'pages': [{'page': 1, 'blocks': [
            {'id': f'node-{i}', 'native_path': f'#/blocks/{i}', 'kind': kind, 'text': text,
             'heading_level': level, 'order': i} for i, (kind, text, level) in enumerate(texts)]}]}
    score = grade_layers(required, read_candidate(observation))
    assert score['publishable'], score['blockers']
    assert score['layers']['B']['score'] == score['layers']['L']['score'] == 100
    validate_evidence(score)


def test_units_inside_ordinary_words_and_empty_cells_keep_their_actual_roles():
    from moparse_eval.requirement_ast import (
        build_document_ast,
        read_content_ast,
        validate_content_ast,
    )

    text = '每年參閱年報，培訓18小時。'
    source = {'path': 'invented', 'lines': [1, 1]}
    ast = read_content_ast(text, source)
    assert [(n['text'], n['role']) for n in ast['children'] if n['text'] in {'年', '小時'}] == [
        ('年', 'literal'), ('年', 'literal'), ('小時', 'unit')]
    cell = build_document_ast([{'kind': 'table_cell', 'text': '', 'source': {**source, 'cell': 'c1'}}])
    assert len(cell['children']) == 1
    validate_content_ast(cell['children'][0]['content'], lambda source: '')


TRAINING = '董事會秘書接受專業培訓的時間為18小時以上。'
MEETINGS = '委員會每年至少召開3次會議。'


def compile_content_document(tmp_path, text):
    """The production reader/compiler owns requirements; candidates are independent."""
    from moparse_eval.source_obligations import audit_source_obligations

    original = authored(tmp_path, text)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    assert audit_source_obligations(graph['source_obligation_inventory'], graph)['source_complete']
    validate_requirement_graph(graph, expected=original)
    return graph, evaluation_projection(graph)


def test_low_recall_paraphrase_is_unresolved_through_the_complete_chain(tmp_path):
    from moparse_eval.requirement_ast import compare_content_ast

    _, required = compile_content_document(tmp_path, '# 培訓\n\n' + TRAINING)
    actual = read_candidate_markdown('# 培訓\n\n董事會秘書的專業培訓時長不少於18小時。',
                                     sample_id=required['sample_id'])
    direct = compare_content_ast(required['document_ast']['children'][1]['content'],
                                 _candidate_ast(actual)['children'][1]['content'])
    assert direct['status'] == 'unresolved'
    score = grade_layers(required, actual)
    row = score['document_comparison']['decision']['proof']['rows'][0]
    assert row['decision']['status'] == 'unresolved'
    outcome = next(r for r in score['outcomes'] if r['id'] == 'B:content:0')
    assert outcome['outcome'] == 'unresolved' and outcome['software_failure']
    assert score['layers']['B']['denominator'] == 1
    assert score['layers']['B']['score'] is None and not score['publishable']
    with pytest.raises(ValueError):
        validate_evidence(score)


def test_two_requirements_consume_distinct_spans_in_one_candidate_block(tmp_path):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + MEETINGS + '\n\n' + TRAINING)
    score = compare(required, '# 治理\n\n' + MEETINGS + TRAINING)
    assert score['publishable'], score['blockers']
    assert score['layers']['B']['denominator'] == score['layers']['B']['numerator'] == 2
    assert score['layers']['L']['score'] == 100
    rows = score['document_comparison']['decision']['proof']['rows']
    assert [r['actual_index'] for r in rows] == [1, 1]
    assert [r['actual_spans'][0]['text_span'] for r in rows] == [
        [0, len(MEETINGS)], [len(MEETINGS), len(MEETINGS + TRAINING)]]


@pytest.mark.parametrize('candidate', [
    MEETINGS + '\n\n' + TRAINING,
    MEETINGS[:7] + '\n\n' + MEETINGS[7:] + '\n\n' + TRAINING,
    MEETINGS + TRAINING,
    MEETINGS[:7] + '\n\n' + MEETINGS[7:] + TRAINING[:8] + '\n\n' + TRAINING[8:],
])
def test_bidirectional_and_many_to_many_partition_has_fixed_votes(tmp_path, candidate):
    graph, required = compile_content_document(tmp_path, '# 治理\n\n' + MEETINGS + '\n\n' + TRAINING)
    before = deepcopy(required)
    score = compare(required, '# 治理\n\n' + candidate)
    assert score['publishable'], score['blockers']
    assert required == before
    assert score['layers']['B']['denominator'] == score['layers']['B']['numerator'] == 2
    assert score['layers']['L']['score'] == 100
    rows = score['document_comparison']['decision']['proof']['rows']
    assert [r['required_id'] for r in rows] == [r['requirement_id'] for r in graph['source_form_requirements']]
    assert [r['decision']['status'] for r in rows] == ['equivalent', 'equivalent']
    assert [''.join(s['text'] for s in r['actual_spans']) for r in rows] == [MEETINGS, TRAINING]
    spans = score['document_comparison']['decision']['proof']['consumed_spans']
    for i, a in enumerate(spans):
        assert all(a['actual_index'] != b['actual_index'] or a['text_span'][1] <= b['text_span'][0]
                   or b['text_span'][1] <= a['text_span'][0] for b in spans[i+1:])


def test_same_block_reversal_keeps_business_but_exposes_real_reading_order(tmp_path):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + MEETINGS + '\n\n' + TRAINING)
    score = compare(required, '# 治理\n\n' + TRAINING + MEETINGS)
    assert score['publishable'], score['blockers']
    assert score['layers']['B']['numerator'] == score['layers']['B']['denominator'] == 2
    [order] = [r for r in score['outcomes'] if r['id'].startswith('L:content-order:')]
    assert order['outcome'] == 'incorrect'
    assert all(r['outcome'] == 'correct' for r in score['outcomes'] if r['id'].startswith('L:content:'))


@pytest.mark.parametrize('candidate,status', [
    ('', 'missing'), (MEETINGS, 'missing'), (TRAINING, 'equivalent'),
    (TRAINING.replace('18', '19'), 'conflict'),
    (TRAINING.replace('18', '18.0'), 'equivalent'),
    (TRAINING.replace('小時', '年'), 'conflict'),
    (TRAINING.replace('以上', '以下'), 'conflict'),
    ('董事會秘書的專業培訓時長不少於18小時。', 'unresolved'),
])
def test_explicit_absence_supported_conflicts_and_open_wording_have_distinct_evidence(tmp_path, candidate, status):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + MEETINGS + '\n\n' + TRAINING)
    text = '# 治理\n\n' + (MEETINGS + '\n\n' + candidate if candidate and candidate != MEETINGS else candidate)
    score = compare(required, text)
    rows = score['document_comparison']['decision']['proof']['rows']
    assert rows[1]['decision']['status'] == status
    assert score['layers']['B']['denominator'] == 2
    assert score['publishable'] == (status != 'unresolved')


@pytest.mark.parametrize('separator', ['插入的獨立敘述。', '## 其他', '![圖](invented.png)', '| 名稱 | 值 |\n| --- | --- |\n| A | 7 |'])
def test_intervening_text_and_protected_nodes_are_never_skipped(tmp_path, separator):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + TRAINING)
    split = TRAINING[:8] + '\n\n' + separator + '\n\n' + TRAINING[8:]
    score = compare(required, '# 治理\n\n' + split)
    [row] = score['document_comparison']['decision']['proof']['rows']
    assert row['decision']['status'] != 'equivalent'
    assert not row['actual_spans'] or ''.join(s['text'] for s in row['actual_spans']) != TRAINING


def test_textless_native_image_is_a_real_correspondence_barrier(tmp_path):
    from moparse_eval.three_layer import read_candidate

    _, required = compile_content_document(tmp_path, '# 治理\n\n' + TRAINING)
    blocks = [('heading', '治理'), ('text', TRAINING[:8]), ('image', ''), ('text', TRAINING[8:])]
    actual = read_candidate({'sample_id': required['sample_id'], 'pages': [{'page': 1, 'blocks': [
        {'id': f'block-{i}', 'native_path': f'#/blocks/{i}', 'kind': kind, 'text': text, 'order': i,
         'heading_level': 1} for i, (kind, text) in enumerate(blocks)]}], 'relations': []})
    score = grade_layers(required, actual)
    assert any(b['role'] == 'image' and b['content'] is None for b in _candidate_ast(actual)['children'])
    assert score['document_comparison']['decision']['status'] != 'equivalent'


@pytest.mark.parametrize('number', ['18', '19'])
def test_duplicate_shapes_stay_ambiguous_when_only_one_value_is_correct(tmp_path, number):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + TRAINING)
    score = compare(required, '# 治理\n\n' + TRAINING + TRAINING.replace('18', number))
    [row] = score['document_comparison']['decision']['proof']['rows']
    assert row['decision']['status'] == 'unresolved'
    assert row['actual_spans'] == [] and not row['retrieval']['value_used']
    assert sum(hit['exact_shape'] and not hit['conflicts'] for hit in row['retrieval']['candidates']) == 2


def test_two_independent_requirements_cannot_consume_the_same_raw_span(tmp_path):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + TRAINING + '\n\n' + TRAINING)
    score = compare(required, '# 治理\n\n' + TRAINING)
    rows = score['document_comparison']['decision']['proof']['rows']
    assert [r['decision']['status'] for r in rows] == ['unresolved', 'unresolved']
    assert not score['document_comparison']['decision']['proof']['consumed_spans']
    assert score['layers']['B']['denominator'] == 2


@pytest.mark.parametrize('financial_first', [True, False])
@pytest.mark.parametrize('before,after,expected', [('80', '81', ['incorrect', 'correct']),
                                                ('18', '19', ['correct', 'incorrect']),
                                                ('18', '18', ['correct', 'correct'])])
def test_mixed_typed_and_content_requirements_keep_their_exact_ownership(tmp_path, financial_first, before, after, expected):
    finance = '流動資產為人民幣80億元。'
    text = finance + TRAINING if financial_first else TRAINING + finance
    graph, required = compile_content_document(tmp_path, '# 治理\n\n' + text)
    assert len(graph['source_form_requirements']) == 1
    assert ''.join(n['text'] for n in graph['source_form_requirements'][0]['content']['children']) == TRAINING
    score = compare(required, '# 治理\n\n' + text.replace(before, after))
    assert score['publishable'], score['blockers']
    assert [r['outcome'] for r in score['outcomes'] if r['layer'] == 'B'] == expected
    assert score['layers']['B']['denominator'] == 2
    assert score['layers']['L']['score'] == 100


def test_unconsumed_insert_and_local_unknown_are_preserved(tmp_path):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + TRAINING)
    score = compare(required, '# 治理\n\n' + TRAINING + '只有特定未明條件下另行處置。')
    assert any(s['text_span'][0] == len(TRAINING) for s in score['document_comparison']['decision']['proof']['unconsumed_spans'])
    assert score['blockers'] and not score['publishable']
    assert next(r for r in score['outcomes'] if r['id'] == 'B:content:0')['outcome'] == 'correct'


def test_correspondence_bound_is_recorded_without_claiming_absence(tmp_path):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + TRAINING)
    score = compare(required, '# 治理\n\n' + '\n\n'.join(TRAINING))
    [row] = score['document_comparison']['decision']['proof']['rows']
    assert row['retrieval']['limit_triggered']
    assert row['decision']['status'] == 'unresolved' and not score['publishable']


@pytest.mark.parametrize('mutation', ['parent', 'span', 'required_id', 'role'])
def test_fixed_requirement_ownership_cannot_be_changed_before_grading(tmp_path, mutation):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + TRAINING)
    block = required['source_form_requirements'][0]
    if mutation == 'parent':
        block['parents'] = ['偽造父項']
    elif mutation == 'span':
        block['source']['text_span'][0] += 1
    elif mutation == 'required_id':
        block['requirement_id'] = 'new-vote'
    else:
        block['role'] = 'heading'
    with pytest.raises(ValueError, match='authorized source selection'):
        grade_layers(required, read_candidate_markdown('# 治理\n\n' + TRAINING, sample_id=required['sample_id']))


def test_unknown_reader_coverage_cannot_prove_an_empty_scope(tmp_path):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + TRAINING)
    actual = read_candidate_markdown('# 治理', sample_id=required['sample_id'])
    actual['blockers'].append({'reason': 'candidate_reader_failure', 'layers': ['L', 'B'],
                               'source': {'path': '<candidate-markdown>', 'lines': [1, 1]}})
    score = grade_layers(required, actual)
    [row] = score['document_comparison']['decision']['proof']['rows']
    assert row['decision']['status'] == 'unresolved'
    assert score['layers']['B']['score'] is score['layers']['L']['score'] is None
    assert all(r['outcome'] == 'unresolved' for r in score['outcomes'] if ':content:' in r['id'])


def test_source_span_consumption_is_checked_again_by_final_evidence_replay(tmp_path):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + MEETINGS + '\n\n' + TRAINING)
    score = compare(required, '# 治理\n\n' + MEETINGS + TRAINING)
    score['document_comparison']['decision']['proof']['rows'][1]['actual_spans'][0]['text_span'][0] = 0
    with pytest.raises(ValueError, match='complete replay'):
        validate_evidence(score)


@pytest.mark.parametrize('merged', [True, False])
def test_replaced_quoted_governance_analysis_does_not_block_an_independent_typed_neighbor(tmp_path, merged):
    governance = TRAINING.replace('專業培訓', '「專業培訓」')
    text = '# 治理\n\n' + governance + '\n\n流動資產為人民幣80億元。'
    graph, required = compile_content_document(tmp_path, text)
    assert 'quoted_nominal_scope' in graph['required_matcher_features']
    assert 'quoted_nominal_scope' not in graph['comparison_coverage']['required_capabilities']
    assert 'quantity_assertion' in graph['comparison_coverage']['required_capabilities']
    actual = text.replace(governance + '\n\n', governance) if merged else text
    score = compare(required, actual.replace('80', '81'))
    assert score['publishable'], score['blockers']
    assert score['layers']['B']['denominator'] == 2
    assert [r['outcome'] for r in score['outcomes'] if r['layer'] == 'B'] == ['incorrect', 'correct']
    assert score['layers']['L']['score'] == 100


WEAK_A = '董事會秘書接受專業培訓。'
WEAK_B = '董事會秘書參加專業教育。'
WEAK_CANDIDATE = '董事會秘書進行職業訓練。'


def _reverse_internal_document_traversal(monkeypatch):
    """Keep authored reading order; permute only the solver's input traversal."""
    import moparse_eval.document_ast_comparison as module

    original = module.compare_document_ast

    def reversed_solver(required, actual, **kwargs):
        count = len(required['children'])
        result = original({**required, 'children': list(reversed(required['children']))}, actual, **kwargs)
        for row in result['proof']['rows']:
            row['required_index'] = count - 1 - row['required_index']
        result['proof']['rows'].sort(key=lambda row: row['required_index'])
        for span in result['proof']['consumed_spans']:
            span['required_index'] = count - 1 - span['required_index']
        return result

    monkeypatch.setattr(module, 'compare_document_ast', reversed_solver)


@pytest.mark.parametrize('reverse', [False, True])
def test_tentative_weak_correspondence_cannot_prove_another_requirement_missing(tmp_path, monkeypatch, reverse):
    graph, required = compile_content_document(tmp_path, '# 培訓\n\n' + WEAK_A + '\n\n' + WEAK_B)
    if reverse:
        _reverse_internal_document_traversal(monkeypatch)
    score = compare(required, '# 培訓\n\n' + WEAK_CANDIDATE)
    proof = score['document_comparison']['decision']['proof']
    rows = {row['required_id']: row for row in proof['rows']}
    assert set(rows) == {row['requirement_id'] for row in graph['source_form_requirements']}
    assert all(row['decision']['status'] == 'unresolved' for row in rows.values())
    assert all(row['correspondence_status'] == 'unresolved' for row in rows.values())
    assert all(row['retrieval']['competing_requirement_ids'] for row in rows.values())
    assert not proof['consumed_spans']
    assert score['layers']['B']['denominator'] == 2
    assert score['layers']['B']['score'] is score['layers']['L']['score'] is None
    assert all(row['outcome'] == 'unresolved' for row in score['outcomes'] if ':content:' in row['id'])
    assert len([b for b in score['blockers'] if b.get('side') == 'comparison']) == 2
    with pytest.raises(ValueError):
        validate_evidence(score)


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('candidate,status', [
    (TRAINING.replace('18', '19'), 'conflict'),
    (TRAINING.replace('18小時', '0.0018萬元'), 'unresolved'),
])
def test_confirmed_identity_reserves_capacity_even_when_content_conflicts_or_is_unresolved(
        tmp_path, monkeypatch, reverse, candidate, status):
    weak = '董事會秘書進行職業教育。'
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + weak + '\n\n' + TRAINING)
    if reverse:
        _reverse_internal_document_traversal(monkeypatch)
    score = compare(required, '# 治理\n\n' + candidate)
    rows = score['document_comparison']['decision']['proof']['rows']
    assert rows[0]['decision']['status'] == 'missing'
    assert rows[0]['decision']['proof']['complete_scope_exclusively_covered']
    assert rows[1]['decision']['status'] == status
    assert rows[1]['correspondence_status'] == 'confirmed'
    assert score['layers']['B']['denominator'] == 2
    assert [r['outcome'] for r in score['outcomes'] if r['layer'] == 'B'] == [
        'incorrect', 'unresolved' if status == 'unresolved' else 'incorrect']
    assert bool(score['blockers']) == (status == 'unresolved')
    assert score['publishable'] == (status != 'unresolved')


def test_one_unique_weak_expression_remains_tentative_and_does_not_claim_layout_identity(tmp_path):
    _, required = compile_content_document(tmp_path, '# 培訓\n\n' + WEAK_A)
    score = compare(required, '# 培訓\n\n' + WEAK_CANDIDATE)
    proof = score['document_comparison']['decision']['proof']
    row, = proof['rows']
    assert row['decision']['status'] == 'unresolved'
    assert row['correspondence_status'] == 'tentative'
    assert row['actual_spans'] and not proof['consumed_spans']
    assert score['layers']['B']['denominator'] == 1
    assert score['layers']['L']['score'] is None
    assert next(r for r in score['outcomes'] if r['id'] == 'L:content:0')['outcome'] == 'unresolved'


def test_partial_overlap_with_a_confirmed_span_is_not_exhaustive_absence_proof(tmp_path):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + TRAINING + '\n\n' + WEAK_B)
    score = compare(required, '# 治理\n\n' + TRAINING + WEAK_CANDIDATE)
    rows = score['document_comparison']['decision']['proof']['rows']
    assert rows[0]['decision']['status'] == 'equivalent'
    assert rows[1]['decision']['status'] == 'unresolved'
    assert score['layers']['B']['denominator'] == 2
    assert not score['publishable']


@pytest.mark.parametrize('reverse', [False, True])
def test_two_independently_identified_expressions_keep_fixed_outcomes_under_solver_permutation(tmp_path, monkeypatch, reverse):
    _, required = compile_content_document(tmp_path, '# 治理\n\n' + MEETINGS + '\n\n' + TRAINING)
    if reverse:
        _reverse_internal_document_traversal(monkeypatch)
    score = compare(required, '# 治理\n\n委員會每年至少召開3次會議。董事會秘書接受專業培訓的時間為19小時以上。')
    rows = score['document_comparison']['decision']['proof']['rows']
    assert [r['decision']['status'] for r in rows] == ['equivalent', 'conflict']
    assert all(r['correspondence_status'] == 'confirmed' for r in rows)
    assert [r['outcome'] for r in score['outcomes'] if r['layer'] == 'B'] == ['correct', 'incorrect']
    assert score['layers']['B']['denominator'] == 2
    assert score['layers']['L']['score'] == 100


def test_separate_cover_nominals_cannot_invent_a_reporting_proposition(tmp_path):
    text = '# 城市韧性报告2029\n\nUrban Resilience Report\n\n城市韧性分析小组\n\n远岸出版社'
    graph, required = compile_content_document(tmp_path, text)
    assert len(graph['document_ast']['children']) == 4
    # None of these three printed names asserts a subject reporting an object.
    assert required['comparison_coverage']['retained_semantic_requirements']['B'] == []
    assert len(graph['source_form_requirements']) == 3
    assert not any(n.get('attribute', '').lower() == 'report' for n in graph['nodes'])


@pytest.mark.parametrize('label,body', [
    ('拓展合作，支持产业转型', '携手科研伙伴，在多个领域推进联合研究。'),
    ('积极在研究组织分享思想', '在专业会议中，交流新技术的研究成果。'),
    ('参与竞赛，共同培养人才', '参与公开竞赛，贡献题目，鼓励学生探索。'),
])
def test_unparsed_labelled_sentence_is_complete_content_instead_of_an_opaque_scalar(tmp_path, label, body):
    text = '# 研究进展\n\n- ' + label + '：' + body
    graph, required = compile_content_document(tmp_path, text)
    assert len(graph['source_form_requirements']) == 1
    assert required['comparison_coverage']['retained_semantic_requirements']['B'] == []
    assert graph['source_form_requirements'][0]['content']['source']['text_span'] == [0, len(label + '：' + body)]
    assert not graph['semantic_complete']


@pytest.mark.parametrize('nominal', ['储能', '儲能', '智能', '性能', '功能'])
def test_nominal_final_neng_is_not_a_printed_ability_operator(tmp_path, nominal):
    text = '# 研究\n\n' + nominal + '主要包括甲类、乙类。'
    graph, required = compile_content_document(tmp_path, text)
    facts = [n for n in graph['nodes'] if n['id'] in graph['projections']['B']]
    assert [(f['subject'], f['attribute'], f['value']) for f in facts] == [
        (nominal, '包括', '甲类'), (nominal, '包括', '乙类')]
    assert all('modality' not in f['qualifiers'] for f in facts)
    assert 'ability_operator' not in graph['required_matcher_features']
    # An independently printed ability after the complete nominal stays real.
    _, modal = compile_content_document(tmp_path, '# 研究\n\n' + nominal + '能够支持甲类。')
    assert modal['business'][0]['qualifiers']['modality'] == 'ability'


def test_printed_clause_routing_preserves_closed_financial_records(tmp_path):
    text = '# 财务\n\n基金：期初金額13；期末金額24；本期公允價值變動損益11。'
    graph, required = compile_content_document(tmp_path, text)
    assert not graph['source_form_requirements']
    assert [(f['subject'], f['attribute'], f['value']) for f in required['business']] == [
        ('基金', '期初金額', '13'), ('基金', '期末金額', '24'), ('基金', '本期公允價值變動損益', '11')]
    assert graph['comparison_coverage']['responsibility_complete']


def test_printed_clause_routing_preserves_an_explicit_compact_column_inventory(tmp_path):
    text = ('# 财务\n\n於12月31日，金額單位：人民幣千元。各項分別列示2031年金額、佔總資產比，'
            '2030年金額、佔總資產比，金額同比變動、佔總資產比重同比增減。\n\n'
            '- 存貨：2031年18、9%；2030年12、6%；金額同比變動50%；佔總資產比重同比增減3%。')
    graph, required = compile_content_document(tmp_path, text)
    assert graph['semantic_complete'], graph['unresolved']
    assert len(required['business']) == 6
    assert [f['value'] for f in required['business']] == ['18', '9', '12', '6', '50', '3']
    assert not graph['source_form_requirements']


def test_printed_clause_routing_preserves_existing_financial_reason_fields(tmp_path):
    text = ('# 财务\n\n其他收益：2031年末1,357；2030年末-268；增减606.34%；'
            '报告期内变动的主要原因：市场需求变化，相关业务收入上升。')
    graph, required = compile_content_document(tmp_path, text)
    facts = required['business']
    # The established series reader keeps terminal punctuation in T, outside
    # the typed cause value. Both annual positions and the reason must survive.
    assert [(f['attribute'], f['value']) for f in facts] == [
        ('其他收益', '1,357'), ('其他收益', '-268'), ('增减', '606.34'),
        ('报告期内变动的主要原因', '市场需求变化，相关业务收入上升')]
    assert ''.join(n['text'] for n in graph['document_ast']['children'][1]['content']['children']).endswith('上升。')
    assert not any(i['reason'] == 'series_attribute_unavailable' for i in graph['unresolved'])


@pytest.mark.parametrize('marker', ['²', '²⁰'])
def test_terminal_footnote_markers_do_not_join_independent_paragraphs(tmp_path, marker):
    text = '# 风险\n\nThe board approved the proposal.' + marker + '\n\nThe committee considered another matter.'
    graph, required = compile_content_document(tmp_path, text)
    assert not any(n['source'].get('joined_fragments') for n in graph['nodes'])
    assert not any(n.get('source_fragments') for n in required['text'])
    assert ''.join(n['text'] for n in graph['document_ast']['children'][1]['content']['children']).endswith(marker)
