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
