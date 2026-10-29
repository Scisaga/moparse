"""Pareto calculations use invented costs and scores, never benchmark inputs."""

from __future__ import annotations

from copy import deepcopy

import pytest

from moparse_eval.pareto import pareto_partition


@pytest.fixture(scope="module", autouse=True)
def _chart_fonts(tmp_path_factory):
    import matplotlib.pyplot as plt

    from moparse_eval.report_figures import _register_cjk_fonts

    _register_cjk_fonts(tmp_path_factory.mktemp("pareto-chart-fonts"))
    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"]}):
        yield


def _row(name, cost, cer, coverage=0.5, **extra):
    return {"pipeline": name, "processing_seconds": cost, "cer": cer,
            "table_target_correctness": coverage, **extra}


def test_objectives_are_separate_and_do_not_mutate_or_weight_input():
    rows = [_row("fast", 1, 0.5, 0.8), _row("accurate", 2, 0.1, 0.7),
            _row("dominated", 3, 0.7, 0.6)]
    before = deepcopy(rows)
    text = pareto_partition(rows, "cer")
    table = pareto_partition(rows, "table_target_correctness", maximize_quality=True)
    assert text["frontier"] == ["fast", "accurate"]
    assert text["dominated_by"]["dominated"] == ["accurate", "fast"]
    assert table["frontier"] == ["fast"]
    assert rows == before


def test_equal_coordinates_retain_both_identities_but_one_strict_axis_dominates():
    rows = [_row("A", 1, 0.2), _row("B", 1, 0.2), _row("slower", 2, 0.2),
            _row("worse", 1, 0.3)]
    result = pareto_partition(rows, "cer")
    assert result["frontier"] == ["A", "B"]
    assert result["dominated_by"]["slower"] == ["A", "B"]
    assert result["dominated_by"]["worse"] == ["A", "B"]


@pytest.mark.parametrize("cost", [None, 0, -1, True, float("nan"), float("inf")])
def test_invalid_cost_never_becomes_a_free_frontier_point(cost):
    result = pareto_partition([_row("bad", cost, 0)], "cer")
    assert result["frontier"] == []
    assert result["excluded"][0]["reason"] == "missing_or_invalid_processing_cost"


@pytest.mark.parametrize("quality", [None, True, -0.1, float("nan"), float("inf")])
def test_invalid_quality_is_excluded_per_objective(quality):
    row = _row("one", 10, quality, 0.8)
    assert not pareto_partition([row], "cer")["frontier"]
    assert pareto_partition([row], "table_target_correctness", maximize_quality=True)["frontier"] == ["one"]


def test_perfect_error_and_cer_above_one_are_valid_without_clipping():
    rows = [_row("fast", 1, 1.4), _row("perfect", 2, 0)]
    assert pareto_partition(rows, "cer")["frontier"] == ["fast", "perfect"]
    result = pareto_partition([_row("bad", 1, 0.1, 1.1)], "table_target_correctness", maximize_quality=True)
    assert not result["frontier"]


def test_unrounded_near_ties_and_input_order_are_respected():
    rows = [_row("A", 1.00001, 0.2), _row("B", 1, 0.199999)]
    assert pareto_partition(rows, "cer")["frontier"] == ["B"]
    assert pareto_partition(list(reversed(rows)), "cer") == pareto_partition(rows, "cer")


def test_incomplete_measurements_are_excluded_but_failure_itself_is_not_hidden():
    rows = [_row("partial-input", 1, 0.1, comparison_eligible=False,
                 comparison_exclusion="incomplete_input_timing"),
            _row("full-attempt-with-failure", 2, 0.2, comparison_eligible=True,
                 has_failed_or_partial_samples=True)]
    result = pareto_partition(rows, "cer")
    assert result["frontier"] == ["full-attempt-with-failure"]
    assert result["excluded"] == [{"pipeline": "partial-input", "reason": "incomplete_input_timing"}]


def test_empty_and_duplicate_identity_inputs_have_explicit_behavior():
    assert pareto_partition([], "cer")["frontier"] == []
    with pytest.raises(ValueError, match="duplicate configuration"):
        pareto_partition([_row("same", 1, 0.2), _row("same", 2, 0.1)], "cer")


def _plot_group(name, cost, cer, *, pages=10, attempted=10, timing=True, completed=True):
    return {"pipeline": name, "suite": "quality800",
            "quality": {"input_pages": pages, "micro": {"unit_presence": {"recall": 1 - cer}}},
            "performance": {"rounds": [{"processing_seconds_including_failures": cost,
                "attempted_input_pages": attempted, "timing_complete": timing,
                "all_samples_completed": completed}]}}


def test_plot_uses_the_same_complete_attempted_input_without_hiding_failure():
    import matplotlib.pyplot as plt

    from moparse_eval.report_figures import _tradeoff

    report = {"groups": [_plot_group("fast", 10, 0.2),
                         _plot_group("slow", 20, 0.1, completed=False),
                         _plot_group("partial", 1, 0.01, attempted=5)]}
    before = deepcopy(report)
    figure, data = _tradeoff(report, plt, ["fast", "slow", "partial"])
    try:
        assert data["pareto"]["content_recall"]["frontier"] == ["fast", "slow"]
        assert data["pareto"]["content_recall"]["excluded"] == [{
            "pipeline": "partial", "reason": "incomplete_or_different_input_timing"}]
        assert data["rows"][1]["has_failed_or_partial_samples"] is True
        assert len(figure.axes) == 2
        assert all(axis.get_xscale() == "log" for axis in figure.axes)
        assert data["interpolated_configurations"] is False
        assert report == before
    finally:
        plt.close(figure)


def test_plot_does_not_put_different_page_budgets_on_one_frontier():
    import matplotlib.pyplot as plt

    from moparse_eval.report_figures import _tradeoff

    report = {"groups": [_plot_group("small", 1, 0.1, pages=5, attempted=5),
                         _plot_group("large", 2, 0.1)]}
    figure, data = _tradeoff(report, plt, ["small", "large"])
    try:
        assert not data["pareto"]["content_recall"]["frontier"]
        assert len(data["pareto"]["content_recall"]["excluded"]) == 2
    finally:
        plt.close(figure)
