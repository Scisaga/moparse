"""Independently authored information-level examples; no real corpus is read."""


import pytest

from moparse_eval.information import field_value_text, row_path_locates
from moparse_eval.scoring import _declared_path_locates, _label_in_native_cell


@pytest.mark.parametrize("label,text,found", [
    ("$m", "2025$m", True), ("(%)", "占比(%)", True), ("%", "增长率%", True),
    ("元", "万元", False), ("2025", "12025", False), ("Amount", "Amounts", False),
    ("2025", "2025/26", False), ("2025", "2025-2026", False),
    ("2025", "2025.0", False), ("2025", "2025$m", True),
    ("2025", "2025, audited", True), ("2025", "2024/2025", False),
    ("Q1 2025", "Q1 2025/26", False),
])
def test_label_boundary_depends_on_the_actual_label_ends(label, text, found):
    assert _label_in_native_cell(label, text, True) is found


@pytest.mark.parametrize("expected,actual,correct", [
    ("$100.00", "$ 100.00", True), ("75.0%", "75.0 %", True),
    ("100", "1 00", False), ("100", "100%", False), ("100", "-100", False),
    ("1,000.0", "1000.0", False), ("75.0%", "75%", False), ("$100", "€100", False),
])
def test_scalar_display_spacing_does_not_normalize_numbers_or_change_units(expected, actual, correct):
    assert (field_value_text(expected) == field_value_text(actual)) is correct


@pytest.mark.parametrize("reference,native,found", [
    (["2025", "$m"], ["2025$m"], True),
    (["Q1 2025"], ["Q1", "2025"], True),
    (["Group", "Revenue"], ["Group Revenue"], True),
    (["Group Revenue"], ["Group", "Revenue"], True),
    (["Revenue"], ["Group", "Revenue"], True),
    (["North", "Revenue"], ["South", "Revenue"], False),
    (["North", "Revenue"], ["North", "Intermediate", "Revenue"], False),
    (["2025", "Amount"], ["Amount", "2025"], False),
    (["Amount", "Amount"], ["Amount"], False),
])
def test_path_segmentation_can_change_without_dropping_business_context(reference, native, found):
    assert _declared_path_locates(reference, native, True) is found


@pytest.mark.parametrize("reference,native,found", [
    (["Assets"], ["Assets", "Receivables"], False),
    (["Assets"], ["Statement", "Assets"], True),
    (["Assets"], ["Statement", "Assets", "(USD million)"], True),
    (["North", "Other"], ["North", "Other", "Subsidiary"], False),
    (["North", "Other"], ["Statement", "North", "Other"], True),
    (["Revenue"], ["Revenue", "2025"], False),
])
def test_field_row_path_ends_at_the_actual_business_leaf(reference, native, found):
    assert row_path_locates(reference, native, True, require_leaf=True) is found


def test_requested_row_identity_does_not_require_unannotated_outer_or_inner_context():
    assert _declared_path_locates(['Revenue'], ['Revenue', '營業額'], True)
    assert _declared_path_locates(['Lease', 'Adjustment'], ['IFRS', 'Lease-Adjustment'], True)
    assert not _declared_path_locates(['North', 'Revenue'], ['South', 'Revenue'], True)
    assert not _declared_path_locates(['North', 'Revenue'], ['North', 'Another measure', 'Revenue'], True)
