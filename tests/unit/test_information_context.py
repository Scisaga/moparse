"""Candidate-only literal unit lexing, without semantic grading."""

from moparse_eval.information_reading import unit_scope_literal, units


def test_literal_unit_lexer_retains_scale_currency_and_compound_denominators():
    cases = {
        "单位：1000元": ["1000元"],
        "单位(1000元)": ["1000元"],
        "单位：百万股": ["百万股"],
        "单位：元/股": ["元/股"],
        "(人民币亿元)": ["人民币亿元"],
        "(毫克/立方米)": ["毫克/立方米"],
        "单位：元 币种：人民币": ["元"],
        "单位：元币种：人民币": ["元"],
    }
    for text, expected in cases.items():
        assert units(text) == expected
        assert unit_scope_literal(text)
