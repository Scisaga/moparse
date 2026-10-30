"""Comparison reporting keeps newly wrong fields distinct from net gains."""

from moparse_eval.table_context_report import _transitions


def test_information_gains_losses_and_new_errors_are_separate():
    pairs = [{"field_index": n, "baseline": {"information": {"status": a}},
              "final": {"information": {"status": b}}} for n, (a, b) in enumerate([
                  ("incorrect", "correct"), ("correct", "incorrect"),
                  ("correct", "incorrect"), ("incorrect", "incorrect"), ("incorrect", "correct")])]
    result = _transitions(pairs)
    assert result["new_correct"] == 2
    assert result["lost_correct"] == 2
    assert result["new_incorrect"] == 2
    assert len(result["introduced_errors"]) == 2


def test_unreadable_output_cannot_publish_a_paired_quality_gain():
    import pytest
    with pytest.raises(ValueError, match="target grading incomplete"):
        _transitions([{"field_index": 0, "baseline": {"status": "not_scored"},
                       "final": {"status": "unresolved"}}])


def test_a_new_unit_error_is_reported_even_when_both_full_information_answers_are_wrong():
    from moparse_eval.service_report import _paired_units
    def score(unit_status):
        return {"units": [{"id": "record", "kind": "table_record", "fields": [
            {"index": 0, "status": "compared", "content_exact": False,
             "required_qualifiers": ["unit"], "information": {"status": "incorrect", "qualifiers": {
                 "unit": {"status": unit_status}}}}
        ]}]}
    pairs = _paired_units({"sample_id": "invented"}, score("correct"), score("incorrect"))
    result = _transitions(pairs)
    assert result["lost_correct"] == result["new_correct"] == 0
    assert len(result["attribute_losses"]["unit"]) == 1
    assert result["attribute_losses"]["period"] == []


def test_common_reader_changes_require_rescoring_and_cannot_admit_runtime_changes():
    from copy import deepcopy

    import pytest

    from moparse_eval.service_evaluation import require_shared_scoring
    software = {"module_sha256": {"information.py": "old", "service_replay_native.py": "same"},
                "support_module_sha256": {"app/service.py": "same"}, "python": "same", "dependencies": {}}
    identity = deepcopy(software)
    identity["module_sha256"]["information.py"] = "new"
    with pytest.raises(ValueError, match="shared scoring"):
        require_shared_scoring({"software": software}, identity)
    require_shared_scoring({"software": software}, identity, paired_native_rescore=True)
    identity["module_sha256"]["service_replay_native.py"] = "new"
    with pytest.raises(ValueError, match="shared scoring"):
        require_shared_scoring({"software": software}, identity, paired_native_rescore=True)
    identity = deepcopy(software)
    identity["support_module_sha256"]["app/service.py"] = "new"
    with pytest.raises(ValueError, match="service implementation"):
        require_shared_scoring({"software": software}, identity, paired_native_rescore=True)


def test_candidate_preparation_can_require_new_native_grades_but_not_change_native_readers():
    from copy import deepcopy

    import pytest

    from moparse_eval.service_evaluation import SCORING_MODULES, require_preparation_scorer
    previous = {'module_sha256': {name: 'same' for name in SCORING_MODULES}}
    current = deepcopy(previous)
    current['module_sha256']['information_reading.py'] = 'changed'
    with pytest.raises(ValueError, match='shared scorer'):
        require_preparation_scorer(previous, current)
    require_preparation_scorer(previous, current, rescore_native=True)
    current['module_sha256']['adapters.py'] = 'changed'
    with pytest.raises(ValueError, match='shared scorer'):
        require_preparation_scorer(previous, current, rescore_native=True)
