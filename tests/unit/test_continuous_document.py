"""Independent invented answers through native-format readers to final credits.

Only literal text, invented JSON and tmp_path reference text are used. Expected
edit counts below are hand authored, never computed by the implementation.
"""

from copy import deepcopy

import pytest

from moparse_eval.ast_alignment import METHOD
from moparse_eval.layer_aggregation import summarize_layers
from moparse_eval.native_candidate import bind_native_syntax_scopes, expose_native_heading_fields
from moparse_eval.native_evaluation import requirement_inventory, retain_limits
from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection
from moparse_eval.saved_native import read_saved_native
from moparse_eval.three_layer import grade_layers, read_candidate, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored
from tests.unit.test_three_layer_native_formats import (
    _docling,
    _glm,
    _mineru,
    _observation,
    _paddle,
    _visual,
)


def compare(tmp_path, expected, candidate, *, pipeline='invented'):
    graph = compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast')
    required = evaluation_projection(graph)
    actual = read_candidate_markdown(candidate, sample_id=required['sample_id'], pipeline=pipeline)
    return grade_layers(required, actual, scoring_method=METHOD)


def t_edits(score):
    return {key: sum(row['edits'][key] for row in score['outcomes'] if row['layer'] == 'T')
            for key in ('S', 'D', 'I')}


def test_exact_document_and_partial_wording_without_grammar_gate(tmp_path):
    text = '# 治理\n\n委員積極參與調研。\n\n董事接受專業培訓。'
    good = compare(tmp_path, text, text)
    assert [good['layers'][k]['score'] for k in ('T', 'L', 'B')] == [100, 100, 100]
    bad = compare(tmp_path, text, text.replace('專業', '職業'))
    assert t_edits(bad) == {'S': 1, 'D': 0, 'I': 0}
    assert bad['layers']['L']['score'] == 100
    assert 0 < bad['layers']['B']['score'] < 100
    assert bad['comparison_complete']


@pytest.mark.parametrize('candidate,edits,score', [
    ('甲乙丙。', {'S': 0, 'D': 0, 'I': 0}, 100),
    ('甲丁丙。', {'S': 1, 'D': 0, 'I': 0}, 75),
    ('甲丙。', {'S': 0, 'D': 1, 'I': 0}, 75),
    ('甲乙丁丙。', {'S': 0, 'D': 0, 'I': 1}, 75),
])
def test_hand_authored_character_counts(tmp_path, candidate, edits, score):
    result = compare(tmp_path, '甲乙丙。', candidate)
    assert t_edits(result) == edits
    assert result['layers']['T']['denominator'] == 4
    assert result['layers']['T']['score'] == score


def test_missing_node_is_local_and_new_text_is_debited(tmp_path):
    text = '甲方開展調研。\n\n乙方完成培訓。'
    dropped = compare(tmp_path, text, '甲方開展調研。')
    assert t_edits(dropped) == {'S': 0, 'D': 7, 'I': 0}
    assert any(r['credit'] == 1 for r in dropped['outcomes'] if r['layer'] == 'B')
    extra = compare(tmp_path, text, text + '\n\n無關文字。')
    assert t_edits(extra) == {'S': 0, 'D': 0, 'I': 5}
    duplicate = compare(tmp_path, text, text + '\n\n甲方開展調研。')
    assert duplicate['layers']['T']['score'] < 100


@pytest.mark.parametrize('expected,candidate', [
    ('甲方積極參與調研並接受培訓。', '甲方積極參與調研\n\n並接受培訓。'),
    ('甲方積極參與調研\n\n並接受培訓。', '甲方積極參與調研並接受培訓。'),
    ('Alpha conducts research and training.', 'Alpha conducts research\n\nand training.'),
])
def test_legal_splits_and_merges_keep_text(tmp_path, expected, candidate):
    score = compare(tmp_path, expected, candidate)
    assert score['layers']['T']['score'] == 100
    assert score['layers']['B']['score'] == 100


def test_reversal_and_wrong_heading_are_relation_errors(tmp_path):
    original = '# 調研\n\n甲方積極參與調研。\n\n# 培訓\n\n乙方完成專業培訓。'
    swapped = '# 調研\n\n乙方完成專業培訓。\n\n# 培訓\n\n甲方積極參與調研。'
    result = compare(tmp_path, original, swapped)
    assert result['layers']['T']['score'] == 100
    assert 0 < result['layers']['L']['score'] < 100
    assert any(p['relation'] == 'heading_ownership' and p['credit'] == 0
               for r in result['outcomes'] if r['layer'] == 'L' for p in r['components'])


@pytest.mark.parametrize('before,after', [('1000', '9000'), ('萬元', '元'), ('不得', '必須'), ('以上', '以下')])
def test_critical_source_content_cannot_pass_by_high_similarity(tmp_path, before, after):
    text = '甲公司不得發行1000萬元以上的債券。'
    result = compare(tmp_path, text, text.replace(before, after))
    assert result['layers']['T']['score'] > 70
    assert result['layers']['B']['score'] == 0
    assert result['layers']['L']['score'] == 100


def test_typed_amount_is_zero_with_correct_structure(tmp_path):
    result = compare(tmp_path, 'Revenue: 1000; Profit: 50', 'Revenue: 9000; Profit: 50')
    values = {r['expected']['attribute']: r['credit'] for r in result['outcomes'] if r['layer'] == 'B'}
    assert values == {'Revenue': 0, 'Profit': 1}
    assert result['layers']['B']['score'] == 50
    assert result['layers']['L']['score'] == 100


def test_field_binding_checks_column_identity_after_fuzzy_correspondence(tmp_path):
    text = '| Name | Revenue |\n| --- | --- |\n| Delta | 17 |'
    good = compare(tmp_path, text, text)
    wrong = compare(tmp_path, text, text.replace('Revenue', 'Profit'))
    assert good['layers']['L']['score'] == 100
    # Name is intact. Revenue's membership is intact, but its column axis is
    # wrong: (1 + (1+0)/2) / 2 = 3/4, independent of the unchanged value 17.
    assert wrong['layers']['L']['score'] == 75
    assert wrong['layers']['B']['score'] == 50
    assert any(p['relation'] == 'row_column_period_axes' and p['credit'] == 0
               for r in wrong['outcomes'] if r['layer'] == 'L' for p in r['components'])


def test_same_named_fields_do_not_borrow_other_parent_values(tmp_path):
    expected = '# Alpha\n\nRevenue: 1000\n\n# Beta\n\nRevenue: 9000'
    candidate = '# Alpha\n\nRevenue: 9000\n\n# Beta\n\nRevenue: 1000'
    score = compare(tmp_path, expected, candidate)
    assert score['layers']['B']['score'] == 0
    assert score['layers']['L']['score'] == 100


def test_one_occurrence_cannot_satisfy_two_expected_nodes(tmp_path):
    result = compare(tmp_path, '委員參與調研。\n\n委員參與調研。', '委員參與調研。')
    assert t_edits(result) == {'S': 0, 'D': 7, 'I': 0}
    assert result['layers']['B']['score'] == 50


def test_inserted_condition_is_not_skipped(tmp_path):
    result = compare(tmp_path, 'Alpha shall pay the fee.', 'Alpha shall pay if approved the fee.')
    assert t_edits(result)['I'] > 0
    assert result['layers']['B']['score'] == 0


@pytest.mark.parametrize('body', ['Revenue: 1000', 'Alpha shall pay the fee.'])
@pytest.mark.parametrize('heading', ['If approved', 'Unless rejected', '仅在批准后', '若经批准', 'Not approved'])
def test_new_conditional_heading_changes_its_business_scope(tmp_path, body, heading):
    result = compare(tmp_path, body, f'# {heading}\n\n{body}')
    assert result['layers']['B']['score'] == 0
    assert result['layers']['L']['score'] < 100
    assert t_edits(result)['I'] > 0
    same = compare(tmp_path, f'# {heading}\n\n{body}', f'# {heading}\n\n{body}')
    assert same['layers']['B']['score'] == 100
    wrapper = compare(tmp_path, body, '# Report\n\n' + body)
    assert wrapper['layers']['B']['score'] == 100


@pytest.mark.parametrize('body', ['Revenue: 1000', '甲公司積極參與調研。'])
def test_combined_document_title_and_separate_own_title_fragments(tmp_path, body):
    expected = '# 甲企業年度公告\n\n## 收入\n\n' + body
    actual = '# 甲企業\n\n# 年度公告\n\n## 收入\n\n' + body
    result = compare(tmp_path, expected, actual)
    assert result['layers']['B']['score'] == 100
    wrong = compare(tmp_path, expected, actual.replace('甲企業', '乙企業'))
    assert wrong['layers']['B']['score'] == 0


@pytest.mark.parametrize('company,expected_credit', [('甲企业', 100), ('甲企业集团', 0)])
def test_saved_native_bilingual_brand_title_keeps_complete_company_fragment(tmp_path, company, expected_credit):
    expected = '# 甲企业\n\n## 年度公告\n\n### 调研\n\n甲方完成專業培訓。'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    native = {'pages': [{'page': 1, 'branch': 'glm', 'raw': {'json_result': [[
        {'index': 0, 'label': 'title', 'content': f'ACME {company} ACME GROUP CO., LTD.'},
        {'index': 1, 'label': 'title', 'content': '年度公告'},
        {'index': 2, 'label': 'title', 'content': '调研'},
        {'index': 3, 'label': 'text', 'content': '甲方完成專業培訓。'},
    ]]}}]}
    observed, _ = expose_native_heading_fields(read_saved_native(native, observation))
    actual = read_candidate(observed)
    bind_native_syntax_scopes(actual)
    result = grade_layers(required, actual, scoring_method=METHOD)
    assert result['layers']['B']['score'] == expected_credit


def test_partial_scope_context_disambiguates_same_label_without_using_values(tmp_path):
    expected = '# Report\n\n## Financials\n\n### Revenue\n\nNote: 1000\n\n### Profit\n\nNote: 50'
    actual = '# Report\n\n## Revenue\n\nNote: 1000\n\n## Profit\n\nNote: 50'
    result = compare(tmp_path, expected, actual)
    assert result['layers']['B']['complete']
    alignment = result['document_comparison']['typed_alignment']
    assert all(r['status'] == 'matched' for r in alignment['rows'])
    changed = compare(tmp_path, expected, actual.replace('1000', '9000'))
    assert all(r['status'] == 'matched' for r in changed['document_comparison']['typed_alignment']['rows'])
    assert [r['actual_pieces'][0]['index'] for r in alignment['rows']] == [r['actual_pieces'][0]['index'] for r in changed['document_comparison']['typed_alignment']['rows']]


def test_reader_failure_is_not_an_edit_deletion(tmp_path):
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, '甲方參與調研。'), comparison_contract='document_ast'))
    failed = read_candidate_markdown('', sample_id=required['sample_id'])
    failed['status'] = 'failed'
    with pytest.raises(ValueError, match='reader_failure'):
        grade_layers(required, failed, scoring_method=METHOD)
    deleted = compare(tmp_path, '甲方參與調研。', '')
    assert t_edits(deleted) == {'S': 0, 'D': 7, 'I': 0}


@pytest.mark.parametrize('factory', [_docling, _paddle, _glm, _mineru, _visual])
def test_saved_table_formats_run_to_final_scores(tmp_path, factory):
    text = '| Name | Revenue | Profit |\n| --- | --- | --- |\n| Delta | 17 | 5 |'
    if factory in (_mineru, _visual):
        text = 'Results\n\n' + text  # Both invented native fixtures print this caption.
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    observed, _ = expose_native_heading_fields(read_saved_native(factory(), observation))
    actual = read_candidate(observed)
    bind_native_syntax_scopes(actual)
    score = grade_layers(required, actual, scoring_method=METHOD)
    assert [score['layers'][k]['score'] for k in ('T', 'L', 'B')] == [100, 100, 100]
    summary = summarize_layers([score])
    assert summary['score'] == 100 and not summary['publication_authorized']


def test_old_readiness_cannot_erase_new_credits(tmp_path):
    text = '委員參與調研。'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast'))
    score = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']), scoring_method=METHOD)
    mask = {'layers': {k: {'state': 'blocked', 'not_comparable_reasons': {r['id']: 'old_limit' for r in score['outcomes'] if r['layer'] == k}}
                       for k in ('T', 'L', 'B')}}
    retained = retain_limits(score, mask, requirement_inventory(required))
    assert retained['score'] == 100
    assert retained['outcomes'] == score['outcomes']


def test_pipeline_labels_are_irrelevant(tmp_path):
    a = compare(tmp_path, 'Revenue: 1000', 'Revenue: 9000', pipeline='P01')
    b = compare(tmp_path, 'Revenue: 1000', 'Revenue: 9000', pipeline='renamed')
    assert a['layers'] == b['layers']
    assert a['outcomes'] == b['outcomes']


def test_component_tampering_is_rejected(tmp_path):
    score = compare(tmp_path, 'Revenue: 1000', 'Revenue: 9000')
    damaged = deepcopy(score)
    next(r for r in damaged['outcomes'] if r['layer'] == 'B')['credit'] = 1
    with pytest.raises(ValueError, match='components'):
        summarize_layers([damaged])


def test_display_wrapper_and_actual_reversal(tmp_path):
    text = '甲方參與調研。\n\n乙方完成培訓。'
    wrapped = compare(tmp_path, text, '# 文件\n\n' + text)
    assert wrapped['layers']['L']['score'] == 100
    assert wrapped['layers']['B']['score'] == 100
    reversed_doc = compare(tmp_path, text, '乙方完成培訓。\n\n甲方參與調研。')
    assert reversed_doc['layers']['T']['score'] == 100
    assert reversed_doc['layers']['L']['score'] < 100


def test_page_value_does_not_select_another_entry(tmp_path):
    text = '# Contents\n\nOverview: 12\n\nStrategy: 20'
    score = compare(tmp_path, text, text.replace('12', '13'))
    assert t_edits(score) == {'S': 1, 'D': 0, 'I': 0}
    assert score['layers']['B']['score'] == 50
    assert score['layers']['L']['score'] == 100


def test_period_identity_cannot_borrow_the_correct_value(tmp_path):
    text = '# 2023\n\nRevenue: 1000\n\n# 2024\n\nRevenue: 9000'
    score = compare(tmp_path, text, text.replace('1000', '8000'))
    assert score['layers']['B']['score'] == 50


def test_unrelated_numbers_do_not_change_field_correspondence(tmp_path):
    a = compare(tmp_path, 'Revenue: 1000; Profit: 7', 'Revenue: 9000; Profit: 7')
    b = compare(tmp_path, 'Revenue: 1000; Profit: 8', 'Revenue: 9000; Profit: 8')
    assert a['document_comparison']['typed_alignment']['rows'] == b['document_comparison']['typed_alignment']['rows']


def test_two_conflicting_duplicate_fields_preserve_ambiguity(tmp_path):
    score = compare(tmp_path, 'Revenue: 1000', 'Revenue: 1000\n\nRevenue: 9000')
    assert score['layers']['T']['score'] is not None
    assert score['layers']['B']['score'] is None
    assert score['layers']['B']['unresolved_requirement_ids'] == ['B:0']


def test_list_parent_error_is_local(tmp_path):
    text = '- Alpha\n  - Delta performs research.\n- Beta\n  - Echo attends training.'
    candidate = '- Alpha\n  - Echo attends training.\n- Beta\n  - Delta performs research.'
    score = compare(tmp_path, text, candidate)
    assert score['layers']['T']['score'] == 100
    assert score['layers']['L']['score'] < 100


def test_many_to_many_uses_all_contiguous_content(tmp_path):
    score = compare(tmp_path, '甲方進行\n\n完整調研及\n\n專業培訓。', '甲方進行完整\n\n調研及專業培訓。')
    assert score['layers']['T']['score'] == 100
    assert score['layers']['B']['score'] == 100


def test_native_entry_canonicalizes_paths_before_isolated_writes(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from moparse_eval import native_evaluation as entry

    monkeypatch.setattr(entry, 'ROOT', tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(entry, 'limit_resources', lambda: None)
    seen = []
    monkeypatch.setattr(entry, '_output', lambda p, **kw: seen.append(p))
    monkeypatch.setattr(entry, 'preflight', lambda p: {'preflight_status': 'ready_for_authorization'})
    target = tmp_path / 'benchmark/runs/lite/native-only/invented/check.json'
    args = SimpleNamespace(phase='preflight', freeze=tmp_path / 'freeze.json',
                           output=target.relative_to(tmp_path), authorization=None)
    assert entry.native_command(args) == 0
    assert seen == [target]


@pytest.mark.parametrize('candidate', ['"Alpha" shall pay 1000 dollars.', '“ Alpha ” shall pay 1000 dollars.'])
def test_quote_wrappers_do_not_create_false_business_conflicts(tmp_path, candidate):
    result = compare(tmp_path, '“Alpha” shall pay 1000 dollars.', candidate)
    assert result['layers']['B']['score'] > 90
    assert result['layers']['T']['score'] < 100


def test_heading_display_spaces_and_split_titles_do_not_change_owner(tmp_path):
    text = '# 甲公司2024年度公告\n\n甲方積極參與調研。'
    candidate = '# 甲公司\n\n# 2024 年度公告\n\n甲方積極參與調研。'
    result = compare(tmp_path, text, candidate)
    assert result['layers']['B']['score'] == 100
    assert result['layers']['L']['score'] == 100


def test_page_first_native_block_is_not_a_single_unmatchable_atom(tmp_path):
    expected = '# Contents\n\nOverview: 12\n\nStrategy: 20\n\nGovernance: 31'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    native = {'pages': [{'page': 1, 'branch': 'glm', 'raw': {'json_result': [[
        {'index': 0, 'label': 'title', 'content': 'Operating Review'},
        {'index': 1, 'label': 'text', 'content': '12 Overview\n20 Strategy 31 Governance'},
    ]]}}]}
    observed, _ = expose_native_heading_fields(read_saved_native(native, observation))
    candidate = read_candidate(observed)
    bind_native_syntax_scopes(candidate)
    score = grade_layers(required, candidate, scoring_method=METHOD)
    assert score['layers']['B']['score'] == 100
    titles = [r for r in score['outcomes'] if r['layer'] == 'T' and r['role'] in {'toc_title', 'page_reference'}]
    assert len(titles) == 6
    assert all(r['edits']['D'] == r['edits']['S'] == 0 for r in titles)


def test_two_quantities_are_not_a_navigation_schema(tmp_path):
    from moparse_eval.continuous_document import _navigation

    observation = read_candidate_markdown('12 employees\n\n20 people', sample_id='neutral')
    assert _navigation(observation) == []


def test_deleted_node_inside_a_fuzzy_group_has_no_membership_credit(tmp_path):
    result = compare(tmp_path, '甲方進行專業調研。\n\n乙方完成正式培訓。', '甲方進行科學調研。')
    assert result['layers']['L']['score'] < 100
    assert any(r['credit'] == 0 for r in result['outcomes'] if r['layer'] == 'B')


def test_explicit_wrong_native_table_header_binding_loses_relations(tmp_path):
    text = '| Name | Revenue | Profit |\n| --- | --- | --- |\n| Delta | 17 | 5 |'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast'))
    native = _paddle()
    region = native['pages'][0]['raw']['res']['parsing_res_list'][0]
    region['block_content'] = region['block_content'].replace('<td headers="r">17', '<td headers="p">17')
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    score = grade_layers(required, read_candidate(read_saved_native(native, observation)), scoring_method=METHOD)
    assert score['layers']['L']['score'] < 100
    assert any(p['credit'] == 0 for r in score['outcomes'] if r['layer'] == 'L' for p in r['components'])


def test_sample_names_do_not_change_matching(tmp_path):
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, 'Revenue: 1000; Profit: 50'), comparison_contract='document_ast'))
    candidate = read_candidate_markdown('Revenue: 9000; Profit: 50', sample_id=required['sample_id'])
    first = grade_layers(required, candidate, scoring_method=METHOD)
    required['sample_id'] = candidate['sample_id'] = 'unrelated-name'
    second = grade_layers(required, candidate, scoring_method=METHOD)
    assert first['layers'] == second['layers']
    assert first['outcomes'] == second['outcomes']


@pytest.mark.parametrize('before,after', [('2024', '2025'), ('>=', '<='), ('万元', '元')])
def test_protected_period_operator_and_unit_changes_are_business_losses(tmp_path, before, after):
    text = '甲公司2024年度不得发行1000万元，金额必须>=100万元。'
    result = compare(tmp_path, text, text.replace(before, after))
    assert result['layers']['B']['score'] < 100
    assert result['layers']['T']['score'] > 70


def test_one_field_value_cannot_also_supply_a_separate_prose_occurrence(tmp_path):
    text = '备注: 委員積極參與調研。\n\n委員積極參與調研。'
    result = compare(tmp_path, text, '备注: 委員積極參與調研。')
    assert result['layers']['B']['score'] <= 50
    assert result['layers']['T']['score'] < 100


def test_row_column_period_axes_compare_across_native_table_and_source_series(tmp_path):
    from moparse_eval.continuous_projection import extend_projection

    text = '营业收入：2014年100；2013年80；本年同比增减25%。'
    graph = compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast')
    original = evaluation_projection(graph)
    required = extend_projection(graph, original)
    assert {f['id'] for f in original['business']} <= {f['id'] for f in required['business']}
    native = _paddle()
    native['pages'][0]['raw']['res']['parsing_res_list'][0]['block_content'] = (
        '<table><tr><th>项目</th><th>2014年</th><th>2013年</th><th>本年同比增减(%)</th></tr>'
        '<tr><th scope="row">营业收入</th><td>100</td><td>80</td><td>25</td></tr></table>')
    observed = _observation('neutral')
    observed['sample_id'] = required['sample_id']
    candidate = read_candidate(read_saved_native(native, observed))
    score = grade_layers(required, candidate, scoring_method=METHOD)
    assert score['layers']['B']['score'] == 100
    growth = next(r for r in score['outcomes'] if r['layer'] == 'B' and r['expected'].get('attribute') == '本年同比增减')
    assert growth['expected']['value'] == '25' and growth['credit'] == 1
    native['pages'][0]['raw']['res']['parsing_res_list'][0]['block_content'] = native['pages'][0]['raw']['res']['parsing_res_list'][0]['block_content'].replace('<td>25</td>', '<td>35</td>')
    bad = grade_layers(required, read_candidate(read_saved_native(native, observed)), scoring_method=METHOD)
    assert next(r for r in bad['outcomes'] if r['id'] == growth['id'])['credit'] == 0
    assert bad['layers']['B']['score'] == pytest.approx(200 / 3)


def test_legacy_unparsed_statement_gets_one_complete_content_owner(tmp_path):
    from moparse_eval.continuous_projection import extend_projection
    from moparse_eval.document_ast_comparison import document_order_requirements

    text = '机构于2020年6月13日发行可转换债券，截至2021年6月12日发行满一年。根据募集说明书规定，现将付息有关事项公告如下：'
    graph = compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast')
    base = evaluation_projection(graph)
    before = deepcopy(base)
    old_orders = document_order_requirements(base)
    required = extend_projection(graph, base)
    assert base == before
    assert required['continuous_coverage']['bounded_responsibility_complete']
    assert required['continuous_coverage']['added_owners']
    assert all(e in document_order_requirements(required) for e in old_orders)
    actual = read_candidate_markdown(text, sample_id=required['sample_id'])
    result = grade_layers(required, actual, scoring_method=METHOD)
    assert result['layers']['B']['score'] == 100


def test_checkbox_selection_cannot_pass_by_character_similarity(tmp_path):
    text = '本机构是否重述以前年度数据：√是 □否。'
    result = compare(tmp_path, text, text.replace('√是 □否', '□是 √否'))
    assert result['layers']['T']['score'] > 70
    assert result['layers']['B']['score'] == 0


def test_nine_selection_scope_rejects_missing_and_extra_members():
    from moparse_eval.native_evaluation import ALL_SCOPE, ALL_SELECTIONS, PIPELINES, _keys

    rows = [{'sample_id': s, 'pipeline': p} for s in ALL_SELECTIONS for p in PIPELINES]
    assert len(_keys(rows, ALL_SCOPE)) == 72
    for changed in (rows[:-1], rows + [rows[0]], [{**rows[0], 'sample_id': 'outside'}] + rows[1:]):
        with pytest.raises(ValueError):
            _keys(changed, ALL_SCOPE)


def test_compact_pooling_keeps_the_full_weighted_result(tmp_path):
    from moparse_eval.layer_aggregation import continuous_aggregation_record

    score = compare(tmp_path, 'Revenue: 1000; Profit: 50', 'Revenue: 9000; Profit: 50')
    assert summarize_layers([score]) == summarize_layers([continuous_aggregation_record(score)])


def test_native_completion_pools_compact_records_without_legacy_publication_key(tmp_path):
    from moparse_eval.layer_aggregation import continuous_aggregation_record
    from moparse_eval.native_evaluation import aggregate_native_scores

    score = compare(tmp_path, 'Revenue: 1000', 'Revenue: 1000\n\nRevenue: 9000')
    record = continuous_aggregation_record(score)
    assert 'publishable' not in record
    result = aggregate_native_scores({'invented': [record]}, METHOD)['invented']
    assert result == summarize_layers([score])
    assert result['layers']['T']['score'] is not None
    assert result['layers']['B']['score'] is None
    assert result['layers']['L']['score'] == 100


def test_complete_nine_selection_research_pooling_preserves_all_fractional_evidence(tmp_path):
    from moparse_eval.native_evaluation import ALL_SELECTIONS, PIPELINES
    from scripts.native_limited_research import aggregate, build_common

    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, 'Revenue: 1000; Profit: 50'), comparison_contract='document_ast'))
    score = compare(tmp_path, 'Revenue: 1000; Profit: 50', 'Revenue: 9000; Profit: 50')
    inventory = requirement_inventory(required)
    common = build_common(dict.fromkeys(ALL_SELECTIONS, required), dict.fromkeys(ALL_SELECTIONS, inventory), scoring_method=METHOD)
    scores = {(sid, p): {**deepcopy(score), 'sample_id': sid, 'pipeline': p, 'benchmark': 'native'}
              for sid in ALL_SELECTIONS for p in PIPELINES}
    result = aggregate(common, scores, dict.fromkeys(ALL_SELECTIONS, inventory))
    assert result['combinations'] == len(result['by_selection']) == 72
    assert result['excluded_denominators'] == dict.fromkeys(('T', 'L', 'B'), 0)
    for pipeline in result['rows']:
        assert pipeline['layers']['B']['score'] == 50
        assert pipeline['layers']['B']['denominator'] == 18
    assert len(result['requirement_records']) == 72 * len(score['outcomes'])


def test_code_digits_are_literal_business_identifiers(tmp_path):
    result = compare(tmp_path, 'Code: 00123', 'Code: 123')
    assert result['layers']['B']['score'] == 0


@pytest.mark.parametrize('label', ['电话', 'Phone', 'Fax', '邮编'])
def test_contact_identifiers_do_not_use_quantity_equivalence(tmp_path, label):
    exact = compare(tmp_path, f'{label}: 00123', f'{label}: 00123')
    wrong = compare(tmp_path, f'{label}: 00123', f'{label}: 123')
    assert exact['layers']['B']['score'] == 100
    assert wrong['layers']['B']['score'] == 0


@pytest.mark.parametrize('actual_email,credit', [('one@delta.example', 100), ('ne@delta.example', 0)])
def test_saved_email_grid_is_read_without_a_business_entity_class(tmp_path, actual_email, credit):
    expected = 'Email / Left: one@delta.example。'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    native = {'pages': [{'page': 1, 'branch': 'glm', 'raw': {'json_result': [[
        {'index': 0, 'label': 'table', 'content': f'| Slot | Left | Right |\n| --- | --- | --- |\n| Email | {actual_email} | other@delta.example |'},
    ]]}}]}
    actual = read_candidate(read_saved_native(native, observation))
    result = grade_layers(required, actual, scoring_method=METHOD)
    assert result['layers']['B']['score'] == credit
    field = next(r for r in result['outcomes'] if r['layer'] == 'B')['actual']
    assert field['value'] == actual_email
    assert field['semantic_entity_class_inferred'] is False


def test_native_cells_keep_table_positions_and_do_not_cross_table_boundaries(tmp_path):
    from moparse_eval.continuous_document import _nodes, _source_order_ast
    from moparse_eval.document_ast_comparison import _candidate_ast

    text = '| Field | Value |\n| --- | --- |\n| Alpha | 17 |\n\nBetween tables.\n\n| Field | Value |\n| --- | --- |\n| Beta | 19 |\n\nAfter tables.'
    actual = read_candidate_markdown(text, sample_id='invented')
    ast = _source_order_ast(_candidate_ast(actual))
    nodes = _nodes(actual, ast, clauses=True)
    assert not ast['unplaced_cell_sources']
    indices = {n['text']: i for i, n in enumerate(nodes) if n.get('text')}
    assert indices['17'] < indices['Between tables.'] < indices['19'] < indices['After tables.']
    assert any(n.get('barrier') for n in nodes[indices['17']+1:indices['19']])


def test_short_own_table_label_supports_local_scope_and_keeps_condition(tmp_path):
    expected = '# Results\n\n| Name | Revenue |\n| --- | --- |\n| Delta | 17 |'
    actual = 'Results\n\n| Name | Revenue |\n| --- | --- |\n| Delta | 17 |'
    result = compare(tmp_path, expected, actual)
    assert result['layers']['B']['score'] == 100
    assert result['layers']['L']['score'] == 100
    conditioned = compare(tmp_path, expected, actual.replace('Results\n', 'Results\n\nIf approved\n'))
    assert conditioned['layers']['B']['score'] == 0


def test_unique_table_hit_cannot_borrow_an_earlier_heading_across_a_new_label(tmp_path):
    text = '# Alpha\n\n| Name | Revenue |\n| --- | --- |\n| Delta | 17 |'
    actual = text.replace('| Name', 'Beta\n\n| Name')
    result = compare(tmp_path, text, actual)
    assert result['layers']['B']['score'] == 0
    assert result['layers']['L']['score'] < 100


@pytest.mark.parametrize('cny,usd,credit', [('1', '9', 1), ('9', '1', 0)])
def test_currency_column_is_located_before_comparing_amount(tmp_path, cny, usd, credit):
    text = 'Revenue / 2024年（人民币百万元）: 1'
    actual = f'| Slot | 2024年（人民币百万元） | 2024年（美元百万元） |\n| --- | --- | --- |\n| Revenue | {cny} | {usd} |'
    result = compare(tmp_path, text, actual)
    fields = [r for r in result['outcomes'] if r['layer'] == 'B']
    assert len(fields) == 1
    assert fields[0]['credit'] == credit
    assert fields[0]['actual']['value'] == cny


@pytest.mark.parametrize('actual_value,credit', [('10000', 1), ('9999', 0)])
def test_explicit_row_unit_is_not_part_of_the_metric_name(tmp_path, actual_value, credit):
    text = 'Revenue / 2024（万元）: 1'
    actual = f'| Slot | 2024 |\n| --- | --- |\n| Revenue（元） | {actual_value} |'
    result = compare(tmp_path, text, actual)
    fields = [r for r in result['outcomes'] if r['layer'] == 'B']
    assert len(fields) == 1
    assert fields[0]['credit'] == credit


def test_whitespace_inside_a_numeric_period_is_not_display_equivalence(tmp_path):
    result = compare(tmp_path, '# 2024年\n\nRevenue: 1000', '# 2 024年\n\nRevenue: 1000')
    assert result['layers']['B']['score'] == 0
    assert result['layers']['L']['score'] < 100
    assert t_edits(result)['I'] > 0


def test_original_page_routes_compare_the_same_saved_locator():
    from moparse_eval.native_scope import same_page_routes

    plan = [{'input_page': 1, 'branch': 'docling', 'raw_locator': '#/pages/0/raw'}]
    original = [{'input_page': 1, 'branch': 'docling', 'entry': '#/pages/0', 'original_page': 77}]
    assert same_page_routes(plan, original)
    assert not same_page_routes(plan, [{**original[0], 'branch': 'glm'}])
    assert not same_page_routes(plan, [{**original[0], 'entry': '#/pages/1'}])


def test_unknown_matrix_record_class_does_not_block_literal_scoring(tmp_path):
    text = '| Left | Middle | Right |\n| --- | --- | --- |\n| Delta | 17 | 5 |\n| Epsilon | 19 | 6 |'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, text), comparison_contract='document_ast'))
    native = _docling()
    for cell, name in zip(native['documents'][0]['document']['tables'][0]['data']['table_cells'][:3], ['Left', 'Middle', 'Right'], strict=True):
        cell['text'] = name
    data = native['documents'][0]['document']['tables'][0]['data']
    data['num_rows'] = 3
    data['table_cells'].extend({**cell, 'text': text, 'start_row_offset_idx': 2, 'end_row_offset_idx': 3}
                              for cell, text in zip(deepcopy(data['table_cells'][3:6]), ['Epsilon', '19', '6'], strict=True))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    candidate = read_candidate(read_saved_native(native, observation))
    assert candidate['text_projection']['complete'] is False
    result = grade_layers(required, candidate, scoring_method=METHOD)
    assert result['layers']['T']['score'] == 100
    assert result['candidate_literal_projection_audit']['legacy_projection_complete'] is False


def test_unknown_native_heading_depth_keeps_ordered_context(tmp_path):
    expected = '# Report\n\n## Finance\n\n### Metrics\n\nRevenue: 1000'
    required = evaluation_projection(compile_requirement_graph(authored(tmp_path, expected), comparison_contract='document_ast'))
    observation = _observation('neutral')
    observation['sample_id'] = required['sample_id']
    native = {'pages': [{'page': 1, 'branch': 'visual', 'raw': [
        {'type': 'title', 'content': t, 'bbox': [0, i / 5, 1, (i + 1) / 5], 'angle': 0}
        for i, t in enumerate(['Report', 'Finance', 'Metrics'])] + [
        {'type': 'text', 'content': 'Revenue: 1000', 'bbox': [0, .6, 1, 1], 'angle': 0}]}]}
    observed, _ = expose_native_heading_fields(read_saved_native(native, observation))
    candidate = read_candidate(observed)
    bind_native_syntax_scopes(candidate)
    result = grade_layers(required, candidate, scoring_method=METHOD)
    assert result['layers']['B']['score'] == 100


def test_lexical_grid_reader_keeps_prose_and_mixed_rows_separate():
    from moparse_eval.native_grid_fields import syntax_grid_fields

    native = _paddle()
    table = native['pages'][0]['raw']['res']['parsing_res_list'][0]
    table['block_content'] = '<table><tr><th>Item</th><th>Value</th></tr><tr><td>Our mission</td><td>Support all customers.</td></tr></table>'
    candidate = read_candidate(read_saved_native(native, _observation('neutral')))
    candidate['business'] = []  # Independently examine the lexical syntax reader.
    assert syntax_grid_fields(candidate) == []
    table['block_content'] = table['block_content'].replace('</table>', '<tr><td>Revenue</td><td>17</td></tr></table>')
    candidate = read_candidate(read_saved_native(native, _observation('neutral')))
    candidate['business'] = []
    fields = syntax_grid_fields(candidate)
    assert [(f['subject'], f['attribute'], f['value']) for f in fields] == [('Revenue', 'Value', '17')]
