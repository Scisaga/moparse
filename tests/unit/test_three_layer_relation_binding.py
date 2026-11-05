"""Logical relations have the same weight across actual serializations."""

from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate_markdown

LIST = "Name: Delta; Revenue: 17; Profit: 5"
TABLE = ('<table><tr><th id="n">Name</th><th id="r">Revenue</th><th id="p">Profit</th></tr>'
         '<tr><td id="entity" headers="n">Delta</td><td id="a" headers="r">17</td>'
         '<td id="b" headers="p">5</td></tr></table>')


def grade(reference, candidate):
    return grade_layers(compile_markdown(reference), read_candidate_markdown(candidate))


def test_header_references_are_evidence_of_the_same_three_bindings_not_extra_votes():
    for reference in (LIST, TABLE):
        for candidate in (LIST, TABLE):
            result = grade(reference, candidate)
            assert result["layers"]["L"]["denominator"] == 3
            assert result["layers"]["L"]["numerator"] == 3


def test_same_independent_links_preserve_binding_when_header_spelling_is_wrong():
    result = grade(TABLE, TABLE.replace(">Revenue<", ">Revene<"))
    assert result["layers"]["L"]["numerator"] == 3
    assert result["layers"]["T"]["score"] < 100
    assert result["layers"]["B"]["numerator"] == 2
    assert any(row["retrieval"]["method"] == "independent_object_anchor"
               for row in result["outcomes"] if row["layer"] == "L")


def test_complete_record_reordering_preserves_logical_binding_without_using_values():
    reference = "Name: Delta; Revenue: 17\n\nName: Echo; Revenue: 29"
    candidate = "Name: Echo; Revenue: 18\n\nName: Delta; Revenue: 17"
    result = grade(reference, candidate)
    assert result["layers"]["L"]["denominator"] == 4
    assert result["layers"]["L"]["numerator"] == 4
    assert result["layers"]["B"]["numerator"] == 3
