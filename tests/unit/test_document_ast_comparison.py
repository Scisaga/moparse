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
