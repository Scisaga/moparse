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
    assert next(row for row in score['outcomes'] if row['id'] == 'B:content:0')['outcome'] == 'incorrect'


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
