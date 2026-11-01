"""Synthetic scope and business-value counterexamples; no corpus access."""


TABLE = '<table><tr><td>(人民币百万元)</td><td>2024</td><td>2023</td><td>同比</td></tr><tr><td>Revenue</td><td>17</td><td>11</td><td>5%</td></tr></table>'


def test_literal_cutoff_date_can_be_read_inside_an_actual_record_title():
    from moparse_eval.information import qualifier_evidence
    cell = {"text": "17", "periods": ["截至2024年9月末股东持股情况"]}
    assert qualifier_evidence({"period": "截至2024年9月末"}, cell, [])["period"]["status"] == "correct"
    assert qualifier_evidence({"period": "截至2023年9月末"}, cell, [])["period"]["status"] != "correct"


def test_explicit_count_measure_and_composed_period_parts():
    from moparse_eval.information import qualifier_evidence
    cell = {"text": "17", "column_header_path": ["2024年", "二季度", "参加会议次数"]}
    assert qualifier_evidence({"unit": "次", "period": "2024年二季度"}, cell, [])["period"]["status"] == "correct"
    assert qualifier_evidence({"unit": "次"}, cell, [])["unit"]["status"] == "correct"
    assert qualifier_evidence({"period": "2024年三季度"}, cell, [])["period"]["status"] == "incorrect"
    cell = {"text": "17", "column_header_path": ["截至12月31日止年度", "2024年"]}
    assert qualifier_evidence({"period": "截至2024年12月31日止年度"}, cell, [])["period"]["status"] == "correct"
    assert qualifier_evidence({"period": "截至2023年12月31日止年度"}, cell, [])["period"]["status"] == "incorrect"


def test_column_qualifier_layout_can_vary_without_skipping_business_groups_or_years():
    from moparse_eval.information import column_path_locates, path_locates
    assert column_path_locates(["2024年", "金額"], ["截至12月31日止年度", "2024年", "金額人民幣千元"], True)
    assert column_path_locates(["Change"], ["Year Ended", "Change"], True)
    assert column_path_locates(["Year Ended", "2024"], ["Year Ended", "2024", "$m"], True)
    assert not column_path_locates(["2024", "Amount"], ["2023", "Amount"], True)
    assert not column_path_locates(["Amount"], ["Group", "Amount"], True)
    assert not path_locates(["Other"], ["North", "Other"], True)
    assert path_locates(["North", "Other"], ["North:", "Other"], True)


def test_unit_lexer_keeps_scale_and_compound_denominator_instead_of_short_suffixes():
    from moparse_eval.information_reading import units
    assert units("单位：1000元") == ["1000元"]
    assert units("单位(1000元)") == ["1000元"]
    assert units("单位：百万股") == ["百万股"]
    assert units("单位：元/股") == ["元/股"]
    assert units("(人民币亿元)") == ["人民币亿元"]
    assert units("(毫克/立方米)") == ["毫克/立方米"]
    assert units("单位：元 币种：人民币") == ["元"]
    assert units("单位：元币种：人民币") == ["元"]
    from moparse_eval.information import qualifier_evidence
    assert qualifier_evidence({"unit": "万元"}, {"unit": "(万元)"}, [])["unit"]["status"] == "correct"
    assert qualifier_evidence({"unit": "元"}, {"unit": "1000元"}, [])["unit"]["status"] == "incorrect"
    assert qualifier_evidence({"unit": "股"}, {"unit": "(元/股)"}, [])["unit"]["status"] == "incorrect"
    assert qualifier_evidence({"unit": "元/股"}, {"unit": "(元 / 股)"}, [])["unit"]["status"] == "correct"
    assert qualifier_evidence({"unit": "元"}, {"units": ["元/股"]}, [])["unit"]["status"] == "incorrect"
    assert qualifier_evidence({"unit": "$m"}, {"units": ["$bn"]}, [])["unit"]["status"] == "incorrect"


def test_explicit_record_path_units_are_read_without_lending_currency_to_change():
    from moparse_eval.information import qualifier_evidence
    cell = {"text": "17", "row_header_path": ["Trading ($bn)"], "column_header_path": ["2024"]}
    assert qualifier_evidence({"unit": "$bn"}, cell, [])["unit"]["status"] == "correct"
    cell["column_header_path"] = ["Change"]
    assert qualifier_evidence({"unit": "$bn"}, cell, [])["unit"]["status"] != "correct"
    cell["column_header_path"] = ["2024"]
    cell["row_header_path"] = ["Other trading"]
    assert qualifier_evidence({"unit": "$bn"}, cell, [])["unit"]["status"] != "correct"


def test_math_wrapper_is_a_footnote_only_with_an_actually_emitted_definition():
    from moparse_eval.information_reading import scalar_notes
    marked = {"text": r"\( 17^4 \)", "notes": ["4 Declared source note"]}
    assert scalar_notes(marked) == ("17", ["4"])
    assert scalar_notes({"text": marked["text"]}) == (marked["text"], None)
    assert scalar_notes({"text": "17^4", "notes": marked["notes"]}) == ("17^4", None)
    assert scalar_notes({"text": r"\( 17^3 \)", "notes": marked["notes"]}) == (r"\( 17^3 \)", None)


def test_single_annual_section_period_survives_attached_business_words():
    from moparse_eval.information import qualifier_evidence
    cell = {"text": "17", "periods": ["（3）2024年度排放情况："]}
    assert qualifier_evidence({"period": "2024年度"}, cell, [])["period"]["status"] == "correct"
    assert qualifier_evidence({"period": "2023年度"}, cell, [])["period"]["status"] != "correct"
    for text in ("2024年度至2025年度排放情况：", "2024年度与2023年度排放情况："):
        assert qualifier_evidence({"period": "2024年度"}, {"text": "17", "periods": [text]}, [])["period"]["status"] != "correct"
    for value in ("2024", "2024年", "2024年度"):
        assert qualifier_evidence({"period": value}, {"text": "17", "periods": ["2024年–2025年"]}, [])["period"]["status"] != "correct"
    unrelated = {"text": "17", "information_context": [{"kind": "paragraph", "text": "Unrelated 2024年度 paragraph"}]}
    assert qualifier_evidence({"period": "2024年度"}, unrelated, [])["period"]["status"] != "correct"


def test_visible_column_units_can_be_printed_as_separate_qualifiers():
    from moparse_eval.information import column_path_locates
    assert column_path_locates(["2024", "(人民币百万元)"], ["2024"], True, ["(人民币百万元)"])
    assert not column_path_locates(["2024", "(人民币百万元)"], ["2024"], True, ["(美元百万元)"])
    assert column_path_locates(["2024年", "金額"], ["於12月31日", "2024年", "金額 人民幣千元"], True)
    assert not column_path_locates(["2024年", "金額"], ["於2023年12月31日", "2024年", "金額"], True)


def test_row_path_keeps_all_annotated_business_levels_and_only_adds_leading_context():
    from moparse_eval.information import row_path_locates
    assert row_path_locates(["North", "Other"], ["Company", "North", "Other"], True)
    assert not row_path_locates(["North", "Other"], ["South", "Other"], True)
    assert not row_path_locates(["North", "Other"], ["North", "South", "Other"], True)
    assert not row_path_locates(["Other"], [None, "Other"], True)
    assert not row_path_locates(["Other"], ["", "Other"], True)
    assert row_path_locates(["Revenue"], ["Revenue (USD)"], True)
    assert not row_path_locates(["Revenue"], ["Revenue and other income"], True)
    assert not row_path_locates(["Revenue and other income"], ["Revenue and other income less expenses"], True)
