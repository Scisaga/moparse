"""Synthetic score outcomes cannot publish a partially adjudicated comparison."""

from copy import deepcopy

import pytest

from moparse_eval.scoring import require_complete_target_grading


def _score():
    return {"sample_id": "invented", "units": [{"id": "record", "kind": "table_record", "fields": [
        {"index": 0, "status": "compared", "content_exact": True, "outcome": "correct", "information": {"status": "correct"}},
        {"index": 1, "status": "compared", "content_exact": False, "outcome": "incorrect", "information": {"status": "incorrect"}},
    ]}], "metrics": {"table_records": {"target_fields": 2, "unresolved_fields": 0,
                                      "information_unresolved_fields": 0}}}


def test_correct_and_incorrect_outcomes_cover_all_admitted_targets():
    score = _score()
    before = deepcopy(score)
    require_complete_target_grading(score)
    assert score == before


@pytest.mark.parametrize("problem", ["value_not_read", "qualifier_not_read", "missing_outcome", "duplicate_target", "stale_aggregate"])
def test_readback_failure_cannot_be_published_as_a_third_quality_outcome(problem):
    score = _score()
    field = score["units"][0]["fields"][0]
    if problem == "value_not_read":
        field.update(status="unresolved", content_exact=None)
    elif problem == "qualifier_not_read":
        field["information"]["status"] = "unresolved"
    elif problem == "missing_outcome":
        score["units"][0]["fields"].pop()
    elif problem == "duplicate_target":
        score["units"][0]["fields"][1]["index"] = 0
    else:
        score["metrics"]["table_records"]["information_unresolved_fields"] = 1
    before = deepcopy(score)
    with pytest.raises(ValueError, match="target grading incomplete"):
        require_complete_target_grading(score)
    assert score == before
