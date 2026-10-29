"""Small-panel averaging plots use invented aggregates only."""

from __future__ import annotations

import copy
import math

import pytest

from moparse_eval.report_figures import PIPELINE_COLORS, _averaging, _register_cjk_fonts


@pytest.fixture(scope="module", autouse=True)
def averaging_fonts(tmp_path_factory):
    _register_cjk_fonts(tmp_path_factory.mktemp("synthetic-averaging-fonts"))


def _report():
    micro = (0.10, 0.11, 0.05, 0.046, 0.07, 0.06, 0.049, 0.045)
    document = (0.18, 0.20, 0.08, 0.055, 0.10, 0.095, 0.12, 0.062)
    family = (0.17, 0.19, 0.085, 0.059, 0.11, 0.10, 0.125, 0.066)
    pipelines = [f"P{number:02}" for number in range(1, 9)]
    return {"groups": [
        {"pipeline": pipeline, "suite": "quality800", "quality": {
            "micro": {"text": {"strict": {"cer": micro[index]}}},
            "macro_by_document": {"text.strict.cer": {
                "value": document[index], "available_groups": 5, "total_groups": 5}},
            "macro_by_family": {"text.strict.cer": {
                "value": family[index], "available_groups": 3, "total_groups": 4}},
        }} for index, pipeline in enumerate(pipelines)
    ]}, pipelines


def _draw(report, pipelines):
    import matplotlib.pyplot as plt

    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"],
                         "mathtext.fontset": "dejavusans", "text.usetex": False}):
        return _averaging(report, plt, pipelines)


def test_three_shared_log_panels_preserve_values_coverage_and_categorical_identity():
    import matplotlib.colors as colors
    import matplotlib.pyplot as plt

    report, pipelines = _report()
    before = copy.deepcopy(report)
    figure, data = _draw(report, pipelines)
    try:
        assert len(figure.axes) == 3
        assert data["macro_metric"] == "text.strict.cer"
        assert data["layout"] == "three_shared_y_panels_pipeline_categories"
        assert data["y_scale"] == "log" and data["guide_not_fit"] is True
        assert all(axis.get_yscale() == "log" for axis in figure.axes)
        assert all(axis.get_ylim() == pytest.approx(data["y_limits"]) for axis in figure.axes)
        assert data["rows"][0]["macro_by_document"] == {
            "value": 0.18, "available_groups": 5, "total_groups": 5,
        }
        assert data["rows"][0]["macro_by_family"]["available_groups"] == 3
        assert data["rows"][0]["micro"]["value"] == 0.10
        for axis, scope in zip(figure.axes, ("micro", "macro_by_document", "macro_by_family"), strict=True):
            assert len(axis.lines) == 1
            assert list(axis.lines[0].get_xdata()) == list(range(8))
            assert list(axis.lines[0].get_ydata()) == [row[scope]["value"] for row in data["rows"]]
            assert [label.get_text() for label in axis.get_xticklabels()] == pipelines
            assert len(axis.collections) == 8
            for index, collection in enumerate(axis.collections):
                assert collection.get_offsets()[0].tolist() == [index, data["rows"][index][scope]["value"]]
                assert collection.get_facecolors()[0] == pytest.approx(colors.to_rgba(PIPELINE_COLORS[pipelines[index]]))
        assert any("按参考字符数加权" in text.get_text() for text in figure.axes[0].texts)
        assert any("各文档等权 · 可用 5/5" in text.get_text() for text in figure.axes[1].texts)
        assert any("各家族等权 · 可用 3/4" in text.get_text() for text in figure.axes[2].texts)
        assert "细线仅引导视线" in figure.texts[-1].get_text()
        assert report == before
    finally:
        plt.close(figure)


def test_actual_zero_switches_all_panels_to_linear_without_epsilon_or_na():
    import matplotlib.pyplot as plt

    report, pipelines = _report()
    report["groups"][0]["quality"]["micro"]["text"]["strict"]["cer"] = 0
    figure, data = _draw(report, pipelines)
    try:
        assert data["y_scale"] == "linear"
        assert all(axis.get_yscale() == "linear" for axis in figure.axes)
        assert data["rows"][0]["micro"]["value"] == 0
        assert figure.axes[0].collections[0].get_offsets()[0].tolist() == [0, 0]
        assert any(text.get_text() == "0.00%" for text in figure.axes[0].texts)
        assert all(axis.get_ylim() == pytest.approx(data["y_limits"]) for axis in figure.axes)
    finally:
        plt.close(figure)


@pytest.mark.parametrize("missing", [None, float("nan"), float("inf")])
def test_missing_measurement_breaks_guide_and_does_not_acquire_zero(missing):
    import matplotlib.pyplot as plt

    report, pipelines = _report()
    report["groups"][3]["quality"]["macro_by_document"]["text.strict.cer"]["value"] = missing
    report["groups"][3]["quality"]["macro_by_document"]["text.strict.cer"].pop("available_groups")
    figure, data = _draw(report, pipelines)
    try:
        assert data["y_scale"] == "log"
        assert data["rows"][3]["macro_by_document"]["value"] is None
        assert data["rows"][3]["macro_by_document"]["available_groups"] is None
        axis = figure.axes[1]
        assert math.isnan(axis.lines[0].get_ydata()[3])
        assert len(axis.collections) == 7
        assert any(text.get_text() == "NA" for text in axis.texts)
        assert any("可用数各配置不同或未记录" in text.get_text() for text in axis.texts)
    finally:
        plt.close(figure)


def test_direct_labels_remain_inside_panels_and_do_not_overlap_for_close_values():
    import matplotlib.pyplot as plt
    from matplotlib.text import Annotation

    report, pipelines = _report()
    figure, _ = _draw(report, pipelines)
    try:
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        for axis in figure.axes:
            labels = [text for text in axis.texts if isinstance(text, Annotation)]
            assert len(labels) == 8
            bounds = [text.get_window_extent(renderer) for text in labels]
            panel = axis.get_window_extent(renderer)
            for bound in bounds:
                assert panel.x0 <= bound.x0 <= bound.x1 <= panel.x1
                assert panel.y0 <= bound.y0 <= bound.y1 <= panel.y1
            assert all(not left.overlaps(right) for index, left in enumerate(bounds)
                       for right in bounds[index + 1:])
    finally:
        plt.close(figure)


def test_absent_groups_stay_na_without_fake_points():
    import matplotlib.pyplot as plt

    figure, data = _draw({"groups": []}, ["P01", "P08"])
    try:
        assert data["y_scale"] == "linear"
        assert all(not axis.collections for axis in figure.axes)
        assert all(sum(text.get_text() == "NA" for text in axis.texts) == 2 for axis in figure.axes)
        assert all(row[scope]["value"] is None for row in data["rows"]
                   for scope in ("micro", "macro_by_document", "macro_by_family"))
    finally:
        plt.close(figure)
