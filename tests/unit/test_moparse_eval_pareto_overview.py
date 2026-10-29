"""Pareto prose is derived from synthetic plotted analyses."""

from moparse_eval.report_overview import _pareto_lines


def test_frontier_prose_preserves_metric_direction_and_measured_order():
    figure = {"data": {"pareto": {
        "content_recall": {"frontier": ["fast", "accurate"], "dominated": ["worse"]},
        "information_target_correctness": {"frontier": ["fast"], "dominated": ["accurate", "worse"]},
    }}}
    text = "\n".join(_pareto_lines(figure))
    assert "耗时与内容定位覆盖的前沿（按耗时递增）：**fast → accurate**" in text
    assert "耗时与完整信息覆盖的前沿（按耗时递增）：**fast**" in text
    assert "至少一项更优" in text
    assert "不合成加权总分" in text
