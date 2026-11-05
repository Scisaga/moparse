"""User-selected scope deferrals never authorize arbitrary unknown targets."""

from copy import deepcopy

import pytest

from moparse_eval.requirement_graph import is_deferred_input_scope

SAMPLE = "alibaba-strategies-p009-010"
ISSUE = {"reason": "input_scope_context", "source": {
    "path": "/readonly/complex-alibaba-2025-annual/expected.md", "lines": [230, 230]},
    "outside_selection": [{"kind": "mixed_page_selection_declaration", "declared_source_pages": [10, 11],
                           "outside_source_pages": [11]}]}


def test_only_the_exact_authorized_pending_declaration_can_defer_the_structure_context():
    assert is_deferred_input_scope(SAMPLE, ISSUE) is True


@pytest.mark.parametrize("mutation", ["sample", "line", "document", "reason", "operator", "pages", "missing_side", "extra_dependency"])
def test_known_sample_or_reason_cannot_waive_a_different_uninterpreted_obligation(mutation):
    issue, sample = deepcopy(ISSUE), SAMPLE
    if mutation == "sample":
        sample = "unapproved-sample"
    elif mutation == "line":
        issue["source"]["lines"] = [231, 231]
    elif mutation == "document":
        issue["source"]["path"] = "/readonly/unapproved/expected.md"
    elif mutation == "reason":
        issue["reason"] = "narrative_unresolved"
    elif mutation == "operator":
        issue["outside_selection"][0]["kind"] = "explicit_unit_or_period"
    elif mutation == "pages":
        issue["outside_selection"][0]["declared_source_pages"] = [10, 12]
    elif mutation == "missing_side":
        issue["outside_selection"][0]["outside_source_pages"] = [10]
    else:
        issue["outside_selection"].append({"kind": "explicit_unit_or_period"})
    assert is_deferred_input_scope(sample, issue) is False
