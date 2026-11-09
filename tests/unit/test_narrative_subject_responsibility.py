"""A reporting clause or note marker is not an atomic proposition subject."""

import pytest

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection, validate_requirement_graph
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored


@pytest.mark.parametrize('body', [
    'Fiscal year 2031 marked a year of progress as Meridian Group advanced our “customer first, automation-driven” strategy.',
    'Calendar year 2032 represented strong progress as Harbor Group advanced our “service first, technology-driven” strategy.',
    '(7) Totals may not match the estimate due to rounding.',
])
def test_unresolved_context_has_complete_content_not_a_fabricated_actor(tmp_path, body):
    text = '# Terms\n\n' + body
    original = authored(tmp_path, text)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    assert graph['comparison_coverage']['responsibility_complete']
    assert graph['unresolved']
    assert not graph['comparison_coverage']['retained_semantic_requirements']['B']
    [content] = graph['source_form_requirements']
    assert content['source']['text_span'] == [0, len(body)]
    required = evaluation_projection(graph)
    for candidate in [text, text.replace(' Group ', '  Group ')]:
        result = grade_layers(required, read_candidate_markdown(candidate, sample_id=required['sample_id']))
        assert result['layers']['B']['numerator'] == result['layers']['B']['denominator'] == 1
        assert result['layers']['L']['numerator'] == result['layers']['L']['denominator'] == 1
        validate_evidence(result)


def test_unsupported_note_rewrite_remains_unresolved_with_fixed_requirements(tmp_path):
    body = '(7) Totals may not match the estimate due to rounding.'
    original = authored(tmp_path, '# Terms\n\n' + body)
    graph = compile_requirement_graph(original, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=original)
    required = evaluation_projection(graph)
    candidate = '# Terms\n\n' + body.replace('may not match', 'always equals')
    result = grade_layers(required, read_candidate_markdown(candidate, sample_id=required['sample_id']))
    assert result['layers']['B']['denominator'] == result['layers']['L']['denominator'] == 1
    assert [r['outcome'] for r in result['outcomes'] if r['layer'] == 'B'] == ['unresolved']
    assert not result['publishable']
    with pytest.raises(ValueError):
        validate_evidence(result)
