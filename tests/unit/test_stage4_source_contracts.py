"""Independent invented contracts for the five phase-four source families."""

import json
from copy import deepcopy

import pytest

from moparse_eval.expected_readback import elements
from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored


def test_continuation_paragraph_has_its_own_printed_list_owner():
    text = '# Terms\n\n- The Borrower shall report:\n  - (i) an audited statement; and\n  - (ii) a review.\n\n    Except when law prohibits, apply the following proviso:\n    - (A) notify the Registrar.\n\n  The Borrower must retain records.'
    rows = elements(text)
    assert rows[4].parents == (rows[1].text, rows[3].text)
    assert rows[-1].parents == (rows[1].text,)
    assert rows[5].parents == (rows[1].text, rows[3].text)


def test_declared_section_directory_requires_literal_navigation_not_body_content(tmp_path):
    expected = authored(tmp_path, '# Agenda\n\n- 007 Programme\n  - 009 Review\n- 012 Accounts')
    expected['tags'] = ['section-toc']
    graph = compile_requirement_graph(expected, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=expected)
    validate_requirement_graph(json.loads(json.dumps(graph)))
    retained = graph['comparison_coverage']['retained_semantic_requirements']['B']
    assert [(n['subject'], n['value'], n.get('semantic_type'), n.get('identity_facets'))
            for n in graph['nodes'] if n['id'] in retained] == [
        ('Programme', '007', 'toc_page', {'toc_parent': []}),
        ('Review', '009', 'toc_page', {'toc_parent': ['Programme']}),
        ('Accounts', '012', 'toc_page', {'toc_parent': []})]
    assert not graph['source_form_requirements']
    assert graph['comparison_coverage']['responsibility_complete']

# Invented clauses and identifiers, not copies or transformations of any real
# expected answer. Each family declares its contract before compilation.
FAMILIES = {
 'compliance': '''# Governance

- If the review remains open, the Compliance Officer shall supervise two teams, except when local law prohibits:
  - (A) the regional team shall audit 43 records within 17 days under Rule 8(b); and
  - (B) the central team shall train employees.

  The Compliance Officer shall notify the Registrar of completion.
- The Board shall appoint the Compliance Officer.

# Neighbour

- The Treasurer shall retain a separate report.''',
 'definitions': '''# Definitions

- “Qualified Entity” means an entity whose revenue exceeds 43 units, except when the accounts are unaudited:
  - (A) if the entity is domestic, use the latest annual report under Rule 8(b); or
  - (B) if the entity is foreign, use the latest interim report.

  This definition grants no entitlement to a payment.
- The Registrar shall certify the entity to the Trustee.

# Neighbour

- “Payment Entity” means the Treasurer acting for the Borrower.''',
 'redemption': '''# Redemption

- If the Recall Option is specified, the Borrower shall offer payment to the Bondholder within 43 days, except when the Trustee waives notice:
  - (A) the Paying Agent shall hold 17 units under Rule 8(b); and
  - (B) the Registrar shall record the depositing holder.

  The Borrower shall notify the Trustee before the recall date.
- The Borrower shall pay the Bondholder on the recall date.

# Neighbour

- The Paying Agent shall hold the certificate for the Registrar.''',
 'trustee': '''# Tax and Default

- If a tax deduction is required, the Borrower shall compensate the Holder within 43 days, except when the Holder refuses certification:
  - (A) the Trustee shall receive 17 units under Rule 8(b); and
  - (B) the Registrar shall retain the tax certificate.

  The Borrower shall notify the Trustee before the due date.
- The Trustee shall instruct the Paying Agent after a continuing default.

# Neighbour

- The Paying Agent shall notify the Treasurer about its separate agency duty.''',
 'directory': '''# Contents

- 007 Programme
  - 009 Review
- 012 Accounts
  - 013 Review

# Duties

- If the review remains open, the Registrar shall report within 43 days, except when local law prohibits:
  - (A) the Board shall notify the Trustee under Rule 8(b); and
  - (B) the Trustee shall notify the Board.''',
}


def fixture_contract(tmp_path, family):
    text = FAMILIES[family]
    expected = authored(tmp_path, text)
    graph = compile_requirement_graph(expected, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=expected)
    assert graph['source_obligation_inventory']['source_complete']
    assert graph['comparison_coverage']['responsibility_complete']
    required = evaluation_projection(graph)
    return graph, required


def checked_score(required, text):
    result = grade_layers(required, read_candidate_markdown(text, sample_id=required['sample_id']))
    if result['publishable']:
        validate_evidence(result)
    else:
        with pytest.raises(ValueError):
            validate_evidence(result)
    # Blocked results still need exact evidence replay, while the publication
    # validator must continue rejecting them. Re-read the serialized inputs.
    saved = json.loads(json.dumps(result))
    proof = saved.get('document_comparison')
    if proof:
        replay = grade_layers(proof['inputs']['required'], proof['inputs']['actual'])
        assert json.loads(json.dumps(replay)) == saved
    return result


def variants(family):
    text = FAMILIES[family]
    lines = text.splitlines()
    first_child = next(line for line in lines if line.startswith('  - '))
    last_child = [line for line in lines if line.startswith('  - ')][-1]
    last_clause = [line for line in lines if line.startswith('- ')][-1]
    condition = 'If the review remains open, ' if family in {'compliance','directory'} else (
        'If the Recall Option is specified, ' if family == 'redemption' else
        'If a tax deduction is required, ' if family == 'trustee' else 'if the entity is domestic, ')
    exception = {'compliance':'except when local law prohibits', 'directory':'except when local law prohibits',
        'definitions':'except when the accounts are unaudited', 'redemption':'except when the Trustee waives notice',
        'trustee':'except when the Holder refuses certification'}[family]
    before, after = {'compliance':('The Board shall appoint the Compliance Officer','The Compliance Officer shall appoint the Board'),
        'definitions':('The Registrar shall certify the entity to the Trustee','The Trustee shall certify the entity to the Registrar'),
        'redemption':('The Borrower shall pay the Bondholder','The Bondholder shall pay the Borrower'),
        'trustee':('The Trustee shall instruct the Paying Agent','The Paying Agent shall instruct the Trustee'),
        'directory':('the Board shall notify the Trustee','the Trustee shall notify the Board')}[family]
    # Identical text on a second occurrence must not silently supply a
    # replacement identity or a second evidence-capacity slot.
    return {
      'correct': text,
      'legal_chunking': text.replace(' shall ', '\n    shall ', 1) if family == 'directory'
          else text.replace(' shall ', '\n  shall ', 1),
      'content_deletion': text.split('\n\n',1)[0],
      'wrong_parent': text.replace(first_child,first_child.lstrip(),1),
      'member_omission': text.replace(last_child,''),
      'duplicate_entry': text.replace(first_child,first_child+'\n'+first_child),
      'wrong_value': text.replace('43','44'),
      'wrong_identifier': text.replace('8(b)','8(c)'),
      'wrong_subject': text.replace('Registrar','Depositary',1),
      'condition_deleted': text.replace(condition,'',1),
      'exception_deleted': text.replace(exception,'',1),
      'neighbour_borrowing': text.replace(first_child,'  '+last_clause),
      'reversed_relation': text.replace(before,after,1),
      'unsupported_paraphrase': text.replace('shall','is obliged to',1),
    }


# All body fixtures contain six independently owned complete clauses. Their
# six parent scopes plus five content-order edges give eleven fixed L votes.
# Directory has four navigation pages, two navigation parents, three clauses
# (three scope and two order votes), with no numeric business metric.
FIXED_DENOMINATORS = {name: {'B':6,'L':11} for name in FAMILIES if name != 'directory'}
# The compound heading itself adds one structural preservation and its order
# edge, with no business vote.
FIXED_DENOMINATORS['trustee'] = {'B':6,'L':13}
FIXED_DENOMINATORS['directory'] = {'B':7,'L':14}


@pytest.mark.parametrize('family', list(FAMILIES))
@pytest.mark.parametrize('change', list(variants('compliance')))
def test_each_source_family_final_outcomes_and_replay(tmp_path, family, change):
    graph, required = fixture_contract(tmp_path, family)
    text = variants(family)[change]
    assert text != FAMILIES[family] or change == 'correct', (family,change,'mutation did not execute')
    result = checked_score(required, text)
    assert {k:result['layers'][k]['denominator'] for k in ('B','L')} == FIXED_DENOMINATORS[family]
    if change in {'correct','legal_chunking'}:
        assert result['publishable'], result['blockers']
        assert all(result['layers'][k]['numerator']==FIXED_DENOMINATORS[family][k] for k in ('B','L'))
    else:
        assert any(row['outcome']!='correct' for row in result['outcomes'] if row['layer'] in {'B','L'})
        rows = result['document_comparison']['decision']['proof']['rows']
        if change == 'content_deletion':
            assert any(row['decision']['status']=='missing' for row in rows)
            if family == 'directory':
                assert all(o['outcome']=='incorrect' for o in result['outcomes'] if o['role']=='navigation_order')
        elif change == 'wrong_value':
            assert any(row['decision']['status']=='conflict' for row in rows)
        elif change == 'unsupported_paraphrase':
            assert any(row['decision']['status']=='unresolved' for row in rows)


@pytest.mark.parametrize('change', ['correct', 'colon_form', 'reorder', 'page_rewrite', 'wrong_parent', 'body_confusion'])
def test_declared_directory_final_identity_parent_page_and_order(tmp_path, change):
    source = '# Agenda\n\n- 007 Programme\n  - 009 Review\n- 012 Accounts'
    expected = authored(tmp_path, source)
    expected['tags'] = ['section-toc']
    graph = compile_requirement_graph(expected, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=expected)
    required = evaluation_projection(graph)
    candidate = source.replace('# Agenda', '# Contents')
    candidate = {
        'correct': candidate,
        'colon_form': '# Contents\n\n- Programme: Page 007\n  - Review: Page 009\n- Accounts: Page 012',
        'reorder': '# Contents\n\n- 012 Accounts\n- 007 Programme\n  - 009 Review',
        'page_rewrite': candidate.replace('007', '7'),
        'wrong_parent': candidate.replace('  - 009 Review', '- 009 Review'),
        'body_confusion': source,
    }[change]
    result = checked_score(required, candidate)
    assert {k:result['layers'][k]['denominator'] for k in ('B','L')} == {'B':3,'L':6}
    if change in {'correct','colon_form'}:
        assert result['publishable'] and all(result['layers'][k]['score']==100 for k in ('B','L'))
    elif change == 'reorder':
        assert result['layers']['B']['numerator']==3
        assert any(o['role']=='navigation_order' and o['outcome']=='incorrect' for o in result['outcomes'])
    else:
        assert any(o['outcome']!='correct' for o in result['outcomes'] if o['layer'] in {'B','L'})


def test_order_transfer_needs_both_independent_complete_source_endpoints(tmp_path):
    from moparse_eval.document_ast_comparison import _without_grammar_analysis

    graph, required = fixture_contract(tmp_path, 'compliance')
    owners = graph['comparison_coverage']['content_relation_ownership']
    assert len([o for o in owners if o['relation']=='printed_statement_order'])==3
    # A forged endpoint identity must remain an independent unresolved duty,
    # not disappear merely because its right-hand source lies in body content.
    forged = deepcopy(required)
    order = next(e for e in forged['relations'] if e['type']=='prose_reading_order')
    order['left']['identity']['subject'] = 'The unrelated Depositary'
    kept = _without_grammar_analysis(forged, graph['source_form_requirements'])
    assert order['id'] in {e['id'] for e in kept['relations']}


def test_section_directory_tag_cannot_reclassify_mixed_front_matter(tmp_path):
    from moparse_eval.expected_readback import declared_navigation_heading

    expected = authored(tmp_path, '# Cover\n\nAn ordinary introduction.\n\n## Agenda\n\n- 007 Programme\n- 009 Accounts')
    expected['tags'] = ['section-toc']
    assert declared_navigation_heading(expected) is None
    graph = compile_requirement_graph(expected, comparison_contract='document_ast')
    assert 'navigation_declaration' not in graph['source_obligation_inventory']['selection']
    assert not any(n.get('semantic_type')=='toc_page' for n in graph['nodes'])


@pytest.mark.parametrize('depth', [1,2,3])
def test_proviso_continuation_keeps_its_interpolation_condition(tmp_path, depth):
    # A proviso after alternatives stays under their interpolation condition.
    labels = [f'Parent {i}:' for i in range(depth)] + ['If interpolation is selected:']
    lines = ['# Rates', ''] + ['  '*i+'- '+label for i,label in enumerate(labels)]
    lines += ['  '*(depth+1)+'- (A) the shorter term; and',
              '  '*(depth+1)+'- (B) the longer term.', '',
              '  '*(depth+1)+'Provided that neither term is available, appoint an Adviser.']
    rows = elements('\n'.join(lines))
    assert rows[-1].parents == tuple(labels)


@pytest.mark.parametrize('text', [
 '# Contents\n\n- Alpha: 1\n- Beta: 2\n  - Child: 3\n- Appendix: A-1',
 '# Contents\n\n- Parent: Page 17\n  - Child: Page 18',
])
def test_navigation_order_uses_fixed_retained_facts_on_first_and_saved_validation(tmp_path, text):
    from moparse_eval.document_ast_comparison import (
        comparison_requirement_coverage,
        navigation_order_requirements,
    )

    expected = authored(tmp_path, text)
    graph = compile_requirement_graph(expected, comparison_contract='document_ast')
    validate_requirement_graph(graph, expected=expected)
    validate_requirement_graph(json.loads(json.dumps(graph)))
    assert graph['comparison_coverage']==comparison_requirement_coverage(graph)
    assert graph['comparison_coverage']['navigation_order_requirement_ids']==[
        e['id'] for e in navigation_order_requirements(graph)]
    # A retired local analysis fact must not create a new typed order vote.
    retained=set(graph['comparison_coverage']['retained_semantic_requirements']['B'])
    retired=[n for n in graph['nodes'] if n.get('semantic_type')=='toc_page' and n['id'] not in retained]
    assert retired and graph['source_form_requirements']


def test_incomplete_candidate_cannot_prove_empty_navigation(tmp_path):
    _,required=fixture_contract(tmp_path,'directory')
    candidate=read_candidate_markdown('# Contents',sample_id=required['sample_id'])
    candidate['status']='failed'
    result=grade_layers(required,candidate)
    assert all(o['outcome']=='unresolved' for o in result['outcomes'] if o['role']=='navigation_order')


LABELLED_DUTY = '# Duties\n\n- (a) Recall: If the Recall Option is specified, the Borrower shall pay the Holder within 47 days, except when the Trustee waives notice. The Paying Agent shall deliver a receipt to the depositing Holder. For as long as a certificate is absent, the Option will be available only after certification.'


LABELLED_VARIANTS = {
 'correct': LABELLED_DUTY,
 'legal_chunking': LABELLED_DUTY.replace('Paying Agent shall', 'Paying Agent\n  shall'),
 'wrong_value': LABELLED_DUTY.replace('47','48'),
 'wrong_actor': LABELLED_DUTY.replace('the Borrower shall pay','the Registrar shall pay'),
 'condition_deleted': LABELLED_DUTY.replace('If the Recall Option is specified, ',''),
 'exception_deleted': LABELLED_DUTY.replace('except when the Trustee waives notice',''),
 'reversed_direction': LABELLED_DUTY.replace('The Paying Agent shall deliver a receipt to the depositing Holder',
     'The depositing Holder shall deliver a receipt to the Paying Agent'),
}


@pytest.mark.parametrize('change', list(LABELLED_VARIANTS))
def test_complete_labelled_content_owns_inner_scope_and_order_once(tmp_path, change):
    expected=authored(tmp_path,LABELLED_DUTY)
    graph=compile_requirement_graph(expected,comparison_contract='document_ast')
    validate_requirement_graph(graph,expected=expected)
    retained=graph['comparison_coverage']['retained_semantic_requirements']
    assert not retained['B']
    assert not retained['L'], 'Partial labelled endpoints must not add votes to the complete ordered statement.'
    required=evaluation_projection(graph)
    score=checked_score(required,LABELLED_VARIANTS[change])
    assert score['layers']['B']['denominator']==score['layers']['L']['denominator']==1
    if change in {'correct','legal_chunking'}:
        assert score['layers']['B']['numerator']==score['layers']['L']['numerator']==1
    else:
        assert any(o['outcome']!='correct' for o in score['outcomes'] if o['layer'] in {'B','L'})


@pytest.mark.parametrize('damage', ['label_source','outer_parent','body_source'])
def test_label_scope_transfer_never_consumes_an_unrelated_relation(tmp_path, damage):
    from moparse_eval.document_ast_comparison import _without_grammar_analysis
    expected=authored(tmp_path,LABELLED_DUTY+'\n\n- A separate unrelated statement.')
    graph=compile_requirement_graph(expected,comparison_contract='document_ast')
    required=evaluation_projection(graph)
    # Keep the analysis relation for an independent proof-boundary mutation.
    relation=deepcopy(next(e for e in required['relations'] if e['type']=='heading_parent' and e.get('field_label_evidence')))
    relation['id']='independent:forged-label-scope'
    other=graph['document_ast']['children'][-1]['content']['source']
    if damage=='label_source':
        relation['field_label_evidence']['source']=deepcopy(other)
    elif damage=='body_source':
        relation['source']=deepcopy(other)
    else:
        relation['left']='Other jurisdiction'
    required['relations'].append(relation)
    filtered=_without_grammar_analysis(required,graph['source_form_requirements'])
    assert relation['id'] in {e['id'] for e in filtered['relations']}
