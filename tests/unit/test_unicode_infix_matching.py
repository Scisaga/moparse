"""Exact acceleration checks using only controlled strings."""

import itertools
import random

import pytest

from moparse_eval import matching


def test_vectorized_infix_costs_and_tie_locations_equal_scalar_oracle():
    pytest.importorskip("numpy")
    strings = ["".join(parts) for size in range(5) for parts in itertools.product("甲乙", repeat=size)]
    for query in strings:
        for output in strings:
            assert matching._unicode_infix_distances(query, output) == matching._unicode_infix_distances(
                query, output, vectorized=False)


def test_unicode_and_astral_alphabets_keep_exact_costs_and_locations():
    pytest.importorskip("numpy")
    rng = random.Random(7103)
    for _ in range(30):
        query = "".join(rng.choices("甲乙丙🙂𠀀", k=rng.randrange(1, 40)))
        output = "".join(rng.choices("甲乙丙🙂𠀀", k=rng.randrange(1, 80)))
        assert matching._unicode_infix_distances(query, output) == matching._unicode_infix_distances(
            query, output, vectorized=False)
    query = "".join(chr(0x4e00 + i) for i in range(300))
    output = "开头" + query[:150] + "修改" + query[151:] + "结尾"
    assert matching._unicode_infix_distances(query, output) == matching._unicode_infix_distances(
        query, output, vectorized=False)


@pytest.mark.parametrize("threshold", [0.5, 0.8, 0.99, 1.0])
def test_accelerated_spans_equal_fallback_at_frozen_thresholds(monkeypatch, threshold):
    pytest.importorskip("numpy")
    monkeypatch.setattr(matching, "_edlib", None)
    query = "".join(chr(0x4e00 + i) for i in range(260))
    output = "甲" + query[:-1] + "乙" + "丙" + query + "丁"
    accelerated = matching._approximate_spans(query, output, threshold)
    monkeypatch.setattr(matching, "_np", None)
    assert matching._approximate_spans(query, output, threshold) == accelerated
