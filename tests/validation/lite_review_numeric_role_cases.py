"""Invented role counterexamples executed by the one Lite source Oracle.

These diagnose a capability gap; failed assertions are deliberately reported as
failed evidence, never converted into passing sample acceptance or quality.
No real expected document or saved candidate is used as comparison input.
"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from moparse_eval.expected_report import validate_evidence
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    validate_requirement_graph,
)
from moparse_eval.three_layer import grade_layers, read_candidate_markdown
from tests.unit.test_cjk_circumstance_contract import authored


# B/L responsibilities are fixed by the invented authored declarations, before
# candidate reading. A numeric rewrite of a calendar/reference identifier has no
# authorized quantity equivalence proof. In the absence of a supported role
# interpretation the required boundary is unresolved, not a fabricated conflict.
ROLE_CASES = [
    {'case_id': 'numeric-role/calendar-label',
     'expected_text': '# Events\n\n- 3 May: New chair appointed',
     'candidate_exact': '# Events\n\n- 3 May: New chair appointed',
     'candidate_layout': '# Events\n\n\n- 3 May: New chair appointed',
     'candidate_numeric_rewrite': '# Events\n\n- 3.0 May: New chair appointed',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'calendar_event_label'},
    {'case_id': 'numeric-role/calendar-body',
     'expected_text': '# Notice\n\nThe board signed this statement on 19 March 2029.',
     'candidate_exact': '# Notice\n\nThe board signed this statement on 19 March 2029.',
     'candidate_layout': '# Notice\n\n\nThe board signed this statement on 19 March 2029.',
     'candidate_numeric_rewrite': '# Notice\n\nThe board signed this statement on 19.0 March 2029.',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'calendar_date_in_content'},
    {'case_id': 'numeric-role/typed-calendar-label',
     'expected_text': '# Events\n\n- 1 Mar: New Chief Executive Officer, Ms Jane Rivers, appointed',
     'candidate_exact': '# Events\n\n- 1 Mar: New Chief Executive Officer, Ms Jane Rivers, appointed',
     'candidate_layout': '# Events\n\n\n- 1 Mar: New Chief Executive Officer, Ms Jane Rivers, appointed',
     'candidate_numeric_rewrite': '# Events\n\n- 1.0 Mar: New Chief Executive Officer, Ms Jane Rivers, appointed',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     # Here the rewritten date is the fixed field identity, so both its
     # required business attribute and the field-binding position conflict.
     # This existing scalar contract differs from a body date's document scope.
     'negative_business_outcome': 'incorrect', 'negative_layout_outcomes': ['incorrect'],
     'negative_publishable': True,
     'required_role': 'calendar_event_label_in_existing_scalar_reader'},
    {'case_id': 'numeric-role/calendar-attribution',
     'expected_text': '# Notice\n\nChairman\n\nHong Kong, 27 February 2029',
     'candidate_exact': '# Notice\n\nChairman\n\nHong Kong, 27 February 2029',
     'candidate_layout': '# Notice\n\n\nChairman\n\n\nHong Kong, 27 February 2029',
     'candidate_numeric_rewrite': '# Notice\n\nChairman\n\nHong Kong, 27.0 February 2029',
     'fixed_denominators': {'B': 2, 'L': 3}, 'changed_business_index': 1,
     'required_role': 'signed_calendar_date'},
    {'case_id': 'numeric-role/page-reference',
     'expected_text': '# Index\n\nThe auditor report begins on page 135.',
     'candidate_exact': '# Index\n\nThe auditor report begins on page 135.',
     'candidate_layout': '# Index\n\n\nThe auditor report begins on page 135.',
     'candidate_numeric_rewrite': '# Index\n\nThe auditor report begins on page 135.0.',
     # One body statement has one parent scope. The previous L=2 mistook its
     # retired prose-heading membership for a separate page-navigation edge;
     # there is no directory or independent navigation endpoint in this source.
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'printed_page_reference'},
    {'case_id': 'numeric-role/reporting-year',
     'expected_text': '# Outlook\n\nIn 2029, the board expects stable growth.',
     'candidate_exact': '# Outlook\n\nIn 2029, the board expects stable growth.',
     'candidate_layout': '# Outlook\n\n\nIn 2029, the board expects stable growth.',
     'candidate_numeric_rewrite': '# Outlook\n\nIn 2029.0, the board expects stable growth.',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'reporting_or_forecast_year'},
    {'case_id': 'numeric-role/statute-reference',
     'expected_text': '# Terms\n\nThe rules refer to Section 267(m) of the fictional Act.',
     'candidate_exact': '# Terms\n\nThe rules refer to Section 267(m) of the fictional Act.',
     'candidate_layout': '# Terms\n\n\nThe rules refer to Section 267(m) of the fictional Act.',
     'candidate_numeric_rewrite': '# Terms\n\nThe rules refer to Section 267.0(m) of the fictional Act.',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'statute_section_reference'},
    {'case_id': 'numeric-role/statute-year',
     'expected_text': '# Terms\n\nThe fictional Act of 1935 defines the restricted awards.',
     'candidate_exact': '# Terms\n\nThe fictional Act of 1935 defines the restricted awards.',
     'candidate_layout': '# Terms\n\n\nThe fictional Act of 1935 defines the restricted awards.',
     'candidate_numeric_rewrite': '# Terms\n\nThe fictional Act of 1935.0 defines the restricted awards.',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'statute_identity_year'},
    {'case_id': 'numeric-role/plan-identifier',
     'expected_text': '# Terms\n\nArchived Plan 2011A governs the restricted awards.',
     'candidate_exact': '# Terms\n\nArchived Plan 2011A governs the restricted awards.',
     'candidate_layout': '# Terms\n\n\nArchived Plan 2011A governs the restricted awards.',
     'candidate_numeric_rewrite': '# Terms\n\nArchived Plan 2011.0A governs the restricted awards.',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'plan_text_identifier'},
    {'case_id': 'numeric-role/model-version',
     'expected_text': '# Terms\n\nPrototype Atlas-3.7B supplies the archived benchmark output.',
     'candidate_exact': '# Terms\n\nPrototype Atlas-3.7B supplies the archived benchmark output.',
     'candidate_layout': '# Terms\n\n\nPrototype Atlas-3.7B supplies the archived benchmark output.',
     'candidate_numeric_rewrite': '# Terms\n\nPrototype Atlas-3.70B supplies the archived benchmark output.',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'model_version_identifier'},
    {'case_id': 'numeric-role/security-code',
     'expected_text': '# Terms\n\nThe archive retains security code 004721 for the retired issue.',
     'candidate_exact': '# Terms\n\nThe archive retains security code 004721 for the retired issue.',
     'candidate_layout': '# Terms\n\n\nThe archive retains security code 004721 for the retired issue.',
     'candidate_numeric_rewrite': '# Terms\n\nThe archive retains security code 4721 for the retired issue.',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'security_text_code',
     'evidence_scope': 'fixed_statement_parent_scope_single_vote_regression'},
    {'case_id': 'numeric-role/security-code-isolated',
     'expected_text': '# Archive\n\nArchived issue dossier CODE004721X.',
     'candidate_exact': '# Archive\n\nArchived issue dossier CODE004721X.',
     'candidate_layout': '# Archive\n\n\nArchived issue dossier CODE004721X.',
     'candidate_numeric_rewrite': '# Archive\n\nArchived issue dossier CODE4721X.',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'required_role': 'security_text_code_in_uninterpreted_content'},
    {'case_id': 'numeric-role/typed-text-reference',
     'expected_text': '# Terms\n\nDeferred Units: Awards eligible under Item 403(v) of Regulation R-K, excluding emergency grants.',
     'candidate_exact': '# Terms\n\nDeferred Units: Awards eligible under Item 403(v) of Regulation R-K, excluding emergency grants.',
     'candidate_layout': '# Terms\n\n\nDeferred Units: Awards eligible under Item 403(v) of Regulation R-K, excluding emergency grants.',
     'candidate_numeric_rewrite': '# Terms\n\nDeferred Units: Awards eligible under Item 403.0(v) of Regulation R-K, excluding emergency grants.',
     'fixed_denominators': {'B': 1, 'L': 1}, 'changed_business_index': 0,
     'negative_business_outcome': 'incorrect', 'negative_publishable': True,
     'required_role': 'existing_typed_text_identifier_control'},
]


def run_numeric_role_cases():
    """Return actual executed positive/negative assertions without masking gaps."""
    records = []
    for case in ROLE_CASES:
        with TemporaryDirectory(prefix='moparse-invented-role-') as directory:
            original = authored(Path(directory), case['expected_text'])
            graph = compile_requirement_graph(original, comparison_contract='document_ast')
            validate_requirement_graph(graph, expected=original)
            required = evaluation_projection(graph)
            fixed_required = deepcopy(required)
            variants = []
            for variant in ('exact', 'layout', 'numeric_rewrite'):
                candidate = read_candidate_markdown(case['candidate_' + variant], sample_id=required['sample_id'])
                actual = grade_layers(required, candidate)
                try:
                    validate_evidence(actual)
                    replay = 'passed'
                except ValueError as error:
                    replay = {'status': 'rejected', 'error': str(error)}
                denominators = {layer: actual['layers'][layer]['denominator'] for layer in ('B', 'L')}
                wanted_b = ['correct'] * case['fixed_denominators']['B']
                wanted_l = ['correct'] * case['fixed_denominators']['L']
                wanted_publishable = variant != 'numeric_rewrite' or case.get('negative_publishable', False)
                if variant == 'numeric_rewrite':
                    wanted_b[case['changed_business_index']] = case.get('negative_business_outcome', 'unresolved')
                    wanted_l = case.get('negative_layout_outcomes', wanted_l)
                business = [outcome for outcome in actual['outcomes'] if outcome['layer'] == 'B']
                layout = [outcome for outcome in actual['outcomes'] if outcome['layer'] == 'L']
                text = [outcome for outcome in actual['outcomes'] if outcome['layer'] == 'T']
                checks = {
                    'fixed_denominators': denominators == case['fixed_denominators'],
                    'fixed_requirement_identity': required == fixed_required,
                    'B_outcomes': [outcome['outcome'] for outcome in business] == wanted_b,
                    'L_outcomes': [outcome['outcome'] for outcome in layout] == wanted_l,
                    'T_literal_difference': any(outcome['outcome'] != 'correct' for outcome in text) == (variant == 'numeric_rewrite'),
                    'publishable': actual['publishable'] == wanted_publishable,
                    'evidence_boundary': (replay == 'passed') == wanted_publishable,
                }
                variants.append({'case_id': case['case_id'] + '/' + variant,
                    'status': 'passed' if all(checks.values()) else 'failed',
                    'input': {'expected': case['expected_text'], 'candidate': case['candidate_' + variant]},
                    'expected': {'fixed_denominators': case['fixed_denominators'], 'B_outcomes': wanted_b,
                                 'L_outcomes': wanted_l, 'publishable': wanted_publishable},
                    'actual': {'fixed_denominators': denominators, 'B_outcomes': business, 'L_outcomes': layout,
                               'T_outcomes': text,
                               'publishable': actual['publishable'], 'blockers': actual['blockers'],
                               'evidence_replay': replay},
                    'assertions': checks})
            records.append({'case_id': case['case_id'], 'required_role': case['required_role'],
                'status': 'passed' if all(v['status'] == 'passed' for v in variants) else 'failed',
                'evidence_scope': case.get('evidence_scope', 'independent_numeric_role_capability'),
                'source_only_graph_integrity': 'passed', 'variants': variants,
                'actual_candidate_read': False, 'independent_synthetic_candidate': True})
    return records
