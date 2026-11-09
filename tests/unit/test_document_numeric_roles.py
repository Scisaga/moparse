"""Numbers in text do not acquire a quantity contract from their glyphs."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection, validate_requirement_graph
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored


def production(tmp_path, body):
    original = authored(tmp_path, '# Records\n\n' + body)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    return original, graph, evaluation_projection(graph)


def compare(required, body):
    result = grade_layers(required, read_candidate_markdown('# Records\n\n' + body,
                                                           sample_id=required['sample_id']))
    if result['publishable']:
        validate_evidence(result)
    else:
        with pytest.raises(ValueError):
            validate_evidence(result)
    return result


@pytest.mark.parametrize('body,before,after', [
    ('The rules refer to Section 267(m) of the fictional Act.', '267', '267.0'),
    ('The fictional Act of 1935 defines restricted awards.', '1935', '1935.0'),
    ('Archived Plan 2011A defines restricted awards.', '2011', '2011.0'),
    ('Hong Kong, 27 February 2029', '27', '27.0'),
    ('The Board met on 19 March 2029.', '2029', '2029.0'),
    ('Please consult Note 034(b) for the exclusion.', '034', '34'),
    ('The issuer code is 000019.', '000019', '19'),
    ('董事會於2029年3月4日審議本計劃。', '2029', '2029.0'),
    ('董事會於2029年3月4日審議本計劃。', '3月', '3.0月'),
    ('董事會於2029年3月4日審議本計劃。', '4日', '4.0日'),
])
def test_unbound_numeric_text_never_borrows_quantity_equivalence(tmp_path, body, before, after):
    _, graph, required = production(tmp_path, body)
    assert graph['comparison_coverage']['responsibility_complete']
    good = compare(required, body)
    result = compare(required, body.replace(before, after))
    assert good['publishable']
    assert result['layers']['B']['denominator'] == good['layers']['B']['denominator'] == 1
    assert result['layers']['L']['denominator'] == good['layers']['L']['denominator']
    assert result['layers']['L']['numerator'] == good['layers']['L']['numerator']
    assert [r['outcome'] for r in result['outcomes'] if r['id'].startswith('B:content:')] == ['unresolved']
    assert not result['publishable']


@pytest.mark.parametrize('body,before,after', [
    ('董事會秘書接受專業培訓的時間為18小時以上。', '18', '18.0'),
    ('董事會秘書接受專業培訓的時間為18小時以上。', '小時', '小时'),
    ('董事會秘書接受專業培訓的時間至少為18小時。', '至少', '最少'),
])
def test_supported_content_measurements_retain_declared_equivalence(tmp_path, body, before, after):
    _, _, required = production(tmp_path, body)
    result = compare(required, body.replace(before, after))
    assert result['publishable'], result['blockers']
    assert result['layers']['B']['numerator'] == result['layers']['B']['denominator'] == 1


@pytest.mark.parametrize('mutation', ['basis', 'source', 'role', 'delete'])
def test_forged_numeric_role_or_neighbor_unit_is_rejected(tmp_path, mutation):
    original, graph, _ = production(tmp_path, '董事會秘書接受專業培訓的時間為18小時以上。')
    changed = deepcopy(graph)
    leaf = next(n for n in changed['document_ast']['children'][1]['content']['children'] if n['text'] == '18')
    if mutation == 'basis':
        leaf['numeric_context']['unit']['text'] = '年'
    elif mutation == 'source':
        leaf['numeric_context']['unit']['source']['lines'] = [1, 1]
    elif mutation == 'role':
        leaf['numeric_context']['dimension'] = 'literal'
    else:
        leaf.pop('numeric_context')
    with pytest.raises(ValueError):
        validate_requirement_graph(changed, expected=original)


def test_unit_in_neighbor_record_does_not_turn_a_reference_into_a_quantity(tmp_path):
    body = '董事會秘書接受專業培訓的時間為18小時以上。\n\nThe rules refer to Section 267(m) of the fictional Act.'
    _, _, required = production(tmp_path, body)
    result = compare(required, body.replace('267', '267.0'))
    assert [r['outcome'] for r in result['outcomes'] if r['id'].startswith('B:content:')] == ['correct', 'unresolved']
    assert result['layers']['B']['denominator'] == 2


def test_quantity_role_cannot_choose_a_correct_identifier_in_another_scope(tmp_path):
    original = authored(tmp_path, '# Policy\n\nThe rules refer to Section 267(m) of the fictional Act.\n\n'
                        '# Archive\n\nDifferent obligations apply here.')
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    required = evaluation_projection(graph)
    candidate = ('# Policy\n\nThe rules refer to Section 267.0(m) of the fictional Act.\n\n'
                 '# Archive\n\nThe rules refer to Section 267(m) of the fictional Act.')
    result = grade_layers(required, read_candidate_markdown(candidate, sample_id=required['sample_id']))
    assert next(r for r in result['outcomes'] if r['id'] == 'B:content:0')['outcome'] == 'unresolved'
    assert result['layers']['B']['denominator'] == 2
