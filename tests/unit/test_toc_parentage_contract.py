"""Root identity requires own root evidence; a lost parent is not root."""

from copy import deepcopy

import pytest

from moparse_eval.adapters import html_cells
from moparse_eval.three_layer import (
    compile_markdown,
    grade_layers,
    read_candidate,
    read_candidate_markdown,
)
from moparse_eval.toc_evidence import read_toc

REFERENCE = '# Contents\n\n- Results: Page 17'
SOURCE = {'path': '#/parentage-oracle'}


def blocks(parent):
    return [{'id': 'contents', 'native_path': '#/contents', 'kind': 'title', 'text': 'Contents'},
            {'id': 'north', 'native_path': '#/north', 'kind': 'toc_group', 'text': 'North'},
            {'id': 'entry', 'native_path': '#/entry', 'kind': 'toc_entry', 'text': 'Results: Page 17', 'parent_id': parent}]


def public_score(items):
    return grade_layers(compile_markdown(REFERENCE), read_candidate({'sample_id': 'synthetic', 'pipeline': 'controlled',
        'pages': [{'page': 1, 'blocks': items}], 'relations': []}))


def test_broken_explicit_parent_cannot_fall_back_to_a_root_with_the_same_title_and_page():
    items = blocks('missing-parent')
    before = deepcopy(items)
    result = read_toc(blocks=items, source=SOURCE)
    [entry] = result['entries']
    assert entry['parentage'] == 'unknown'
    assert result['facts'][0]['identity_facets']['toc_parent'] is None
    assert any(issue['reason'] == 'toc_parent_reference_target_unavailable' for issue in result['issues'])
    assert result['source_fragments'][-1]['text'] == 'Results: Page 17'
    score = public_score(items)
    assert all(row['outcome'] == 'incorrect' for row in score['outcomes'] if row['layer'] in {'B', 'L'})
    assert items == before


@pytest.mark.parametrize('parent,wanted_path', [('contents', []), ('north', ['North'])])
def test_an_actual_directory_parent_and_a_named_entry_parent_have_distinct_proven_identities(parent, wanted_path):
    result = read_toc(blocks=blocks(parent), source=SOURCE)
    [entry] = result['entries']
    assert entry['parent_path'] == wanted_path and entry['parentage'] == 'explicit'
    assert result['facts'][0]['identity_facets']['toc_parent'] == wanted_path
    if parent == 'contents':
        assert entry['root_evidence'] and entry['root_evidence'][0]['source']['block'] == 'contents'
    score = public_score(blocks(parent))
    assert [row['outcome'] for row in score['outcomes'] if row['layer'] == 'B'] == ['correct' if parent == 'contents' else 'incorrect']


@pytest.mark.parametrize('text', [
    '# Contents\n\nResults: Page 17',
    '# Contents\n\n| Title | Page |\n|---|---|\n| Results | 17 |',
    '# Contents\n\n<table><tr><th>Title</th><th>Page</th></tr><tr><td>Results</td><td>17</td></tr></table>',
])
def test_complete_flat_text_and_named_title_page_schemas_prove_root_across_representations(text):
    result = read_toc(text=text, source=SOURCE)
    [entry] = result['entries']
    assert entry['parentage'] == 'explicit' and entry['root_evidence']
    assert result['facts'][0]['identity_facets']['toc_parent'] == []
    score = grade_layers(compile_markdown(REFERENCE), read_candidate_markdown(text))
    assert score['publishable'] is True
    assert all(row['outcome'] == 'correct' for row in score['outcomes'] if row['layer'] in {'B', 'L'})


def test_unread_explicit_nested_header_references_keep_their_source_and_block_flat_fallback():
    cells = html_cells('<table><tr><th id="t">Title</th><th id="p">Page</th></tr>'
        '<tr><th id="n" scope="rowgroup" colspan="2">North</th></tr>'
        '<tr><td headers="n t">Results</td><td headers="n p">17</td></tr></table>', '#/nested')
    result = read_toc(cells=cells, source=SOURCE)
    assert result['entries'] == [] and result['facts'] == []
    assert result['blockers'][0]['reason'] == 'toc_explicit_header_reference_interpretation_unsupported'
    assert 'n' in result['blockers'][0]['header_ids']
    assert any(atom['text'] == 'North' for atom in result['text_atoms'])
    assert len(result['source_cells']) == 5


def test_adapter_declared_nonsemantic_container_is_not_a_broken_navigation_parent():
    items = [{'id': 'contents', 'kind': 'title', 'text': 'Contents'},
             {'id': 'entry', 'kind': 'text', 'text': 'Results: Page 17',
              'parent_id': '#/body', 'native_parent': '#/body'}]
    result = read_toc(blocks=items, source=SOURCE)
    assert result['facts'][0]['identity_facets']['toc_parent'] == []
    assert result['entries'][0]['root_evidence']
    assert result['issues'] == []
    score = public_score(items)
    assert all(row['outcome'] == 'correct' for row in score['outcomes'] if row['layer'] in {'B', 'L'})


def test_a_declared_but_empty_parent_field_is_not_a_complete_flat_root_schema():
    result = read_toc(text='# Contents\n\n| Parent | Title | Page |\n|---|---|---|\n| | Results | 17 |', source=SOURCE)
    assert result['entries'][0]['parentage'] == 'unknown'
    assert result['facts'][0]['identity_facets']['toc_parent'] is None
    assert result['entries'][0]['root_evidence'] == []
    assert result['issues'][0]['reason'] == 'toc_parentage_unproven'


def test_native_parent_equality_does_not_excuse_a_missing_named_parent_for_plain_navigation_text():
    items = [{'id': 'contents', 'kind': 'title', 'text': 'Contents'},
             {'id': 'entry', 'kind': 'text', 'text': 'Results: Page 17',
              'parent_id': '#/missing-named-parent', 'native_parent': '#/missing-named-parent'}]
    result = read_toc(blocks=items, source=SOURCE)
    assert result['entries'][0]['parentage'] == 'unknown'
    assert result['facts'][0]['identity_facets']['toc_parent'] is None
    assert result['issues'][0]['reason'] == 'toc_parent_reference_target_unavailable'
    score = public_score(items)
    assert all(row['outcome'] == 'incorrect' for row in score['outcomes'] if row['layer'] in {'B', 'L'})
