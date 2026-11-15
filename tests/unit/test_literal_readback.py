"""Independent reading/capacity counterexamples; invented text and JSON only."""

from copy import deepcopy

import pytest

from moparse_eval.expected_report import _complete_text_trace
from moparse_eval.literal_readback import overlaps, text_readback
from moparse_eval.three_layer import (
    _text_layer,
    canonical,
    compile_markdown,
    grade_layers,
    read_candidate,
    read_candidate_markdown,
)


def literal(identifier, text, *, line=1, kind="text", **extra):
    return {"id": identifier, "text": text, "role": "literal", "syntax_kind": kind,
            "source": {"path": "invented.md", "lines": [line, line]}, **extra}


def compare(required, atoms):
    return _text_layer(required, atoms, readback=text_readback(atoms))


def test_independent_sentence_in_a_merged_native_unit_keeps_its_own_range():
    first = "The disputed figures follow this method; and"
    second = "The certificate remains binding. A report must accompany it."
    candidate = read_candidate({"sample_id": "synthetic", "pipeline": "invented", "pages": [{"page": 1,
        "blocks": [{"id": "a", "kind": "text", "text": first},
                   {"id": "b", "kind": "text", "text": second}]}]})
    required = [literal("binding", "The certificate remains binding.")]
    assert not any(canonical(unit["text"]) == canonical(required[0]["text"]) for unit in candidate["text"])
    stats, rows = _text_layer(required, candidate["text"])
    assert (stats, rows) == compare(required, candidate["text"])
    assert rows[0]["outcome"] == "correct"
    assert rows[0]["actual"]["source"]["path"] == "b"
    assert rows[0]["actual"]["source"]["text_span"] == [0, 32]
    assert rows[0]["actual"]["id"] in {r["id"] for r in rows[0]["correspondence"]["candidates"]}
    assert any("report must accompany" in v["atom"]["text"] for v in candidate["literal_readback"]["views"])


@pytest.mark.parametrize("joined", [False, True])
def test_legal_sentence_partition_does_not_change_reference_or_character_responsibility(joined):
    required = [literal("one", "The board shall pay 43 credits."),
                literal("two", "The clerk shall send the notice.", line=3)]
    original = deepcopy(required)
    candidate = read_candidate_markdown((" " if joined else "\n\n").join(r["text"] for r in required))
    stats, rows = compare(required, candidate["text"])
    assert required == original
    assert stats["denominator"] == 63
    assert [r["id"] for r in rows] == ["one", "two"]
    assert all(r["outcome"] == "correct" for r in rows)


def test_repeated_title_and_signature_have_separate_occurrences_and_own_context():
    required = [literal("signature", "Orchid Instruments", line=9),
                literal("title", "Orchid Instruments", kind="heading")]
    candidates = [literal("top", "Orchid Instruments", kind="heading"),
                  literal("end", "Orchid Instruments", line=9)]
    for wanted in (required, required[::-1]):
        for actual in (candidates, candidates[::-1]):
            _, rows = compare(wanted, actual)
            assert {r["id"]: r["actual"]["id"] for r in rows} == {"signature": "end", "title": "top"}


def test_parent_child_views_cannot_increase_occurrence_capacity():
    candidate = [literal("native", "The permit remains valid. The board shall notify holders.")]
    required = [literal("whole", candidate[0]["text"]),
                literal("child", "The permit remains valid.", line=3)]
    stats, rows = compare(required, candidate)
    assert sum(r["outcome"] == "correct" for r in rows) == 1
    assert stats["score"] < 100
    consumed = [r["correspondence"]["consumed_capacity"] for r in rows if r["actual"]]
    assert all(not overlaps(a, b) for i, a in enumerate(consumed) for b in consumed[i + 1:])


def test_renaming_the_same_source_occurrence_does_not_duplicate_capacity():
    first = literal("native", "The permit remains valid.")
    clone = {**deepcopy(first), "id": "new-name"}
    stats, rows = compare([literal("r1", first["text"]), literal("r2", first["text"], line=3)], [first, clone])
    assert sum(r["outcome"] == "correct" for r in rows) <= 1
    assert stats["score"] != 100


def test_a_deficit_of_identical_printed_marks_still_has_finite_literal_capacity():
    required = [literal("r" + str(i), "√", line=i + 1) for i in range(4)]
    candidates = [literal("a" + str(i), "√", line=i + 1) for i in range(3)]
    stats, rows = compare(required, candidates)
    assert sum(r["outcome"] == "correct" for r in rows) == 3
    assert rows[-1]["outcome"] == "incorrect"
    assert stats["denominator"] == 4 and stats["D"] == 1


@pytest.mark.parametrize("text", ["Coverage ratio ", " Coverage ratio", "\nCoverage ratio\n", "A complete sentence.  "])
def test_outer_whitespace_does_not_create_another_view_of_the_same_occurrence(text):
    candidate = [literal("native", text)]
    reading = text_readback(candidate)
    assert len(reading["views"]) == 1
    stats, rows = compare([literal("required", text.strip())], candidate)
    assert stats["complete"] is True and rows[0]["outcome"] == "correct"
    assert rows[0]["actual"]["text"] == text
    assert sum(rows[0]["strict_edits"].values()) > 0


@pytest.mark.parametrize("before,after", [
    ("The owner shall not pay 43 credits if approval is absent.", "The owner shall pay 43 credits if approval is absent."),
    ("The owner shall pay 43 credits only if approved.", "The owner shall pay 43 credits."),
    ("The owner shall pay 43 credits except when waived.", "The owner shall pay 43 credits."),
    ("Cash flow: 84,731,205", "Cash flow: 84,731,20"),
    ("Contact: office@orchid.test", "Contact: ffice@orchid.test"),
    ("Dated 2028-03-07.", "Dated 2028-03-08."),
    ("Code: AX-047", "Code: AX-074"),
    ("Reference: [47]", "Reference: [74]"),
])
def test_true_negation_condition_exception_number_email_date_code_and_reference_errors_survive(before, after):
    required = compile_markdown(before)
    candidate = read_candidate_markdown(after)
    _, rows = compare(required["text"], candidate["text"])
    assert not all(r["outcome"] == "correct" for r in rows)


@pytest.mark.parametrize("barrier", ["Inserted body text.", "# New heading", "- Another member", "![Caption](unread.png)",
                                     "| A | B |\n|---|---|\n| x | y |"])
def test_fragments_cannot_skip_intervening_body_heading_list_media_or_table(barrier):
    required = [literal("signature", "Orchid Instruments Board 2028-03-07")]
    graph = read_candidate_markdown("Orchid Instruments\n\n" + barrier + "\n\nBoard 2028-03-07")
    _, rows = compare(required, graph["text"])
    assert rows[0]["outcome"] != "correct"
    assert not any(canonical(v["atom"]["text"]) == canonical(required[0]["text"]) for v in graph["literal_readback"]["views"])


def test_parenthetical_labels_are_read_without_new_business_facts_or_discarded_brackets():
    graph = read_candidate_markdown("（Correspondence address: Willow Avenue 47）\n\nA separate publisher")
    before = deepcopy(graph["business"])
    stats, rows = compare([literal("label", "Correspondence address")], graph["text"])
    assert rows[0]["outcome"] == "correct"
    assert graph["business"] == before
    assert rows[0]["actual"]["source"]["text_span"] == [1, 23]
    assert any("（" in r["text"] for r in stats["unadjudicated_extra_units"])
    assert any("47）" in r["text"] for r in stats["unadjudicated_extra_units"])


def test_list_row_path_exposes_its_labels_but_never_borrows_another_occurrence():
    text = "- Financial measure: Solvency framework / Coverage ratio\n  - Detail: unverified\n"
    graph = read_candidate_markdown(text)
    _, rows = compare([literal("ratio", "Coverage ratio")], graph["text"])
    assert rows[0]["outcome"] == "correct"
    assert rows[0]["actual"]["source"]["lines"] == [1, 1]
    assert not any(f["attribute"] == "Coverage ratio" for f in graph["business"])


def test_equally_eligible_distinct_occurrences_remain_ambiguous_under_all_traversals():
    required = [literal("wanted", "Distinct literal.")]
    candidates = [literal("first", "Distinct literal."), literal("second", "Distinct literal.", line=7)]
    for atoms in (candidates, candidates[::-1]):
        stats, rows = compare(required, atoms)
        assert rows[0]["outcome"] == "unresolved" and rows[0]["actual"] is None
        assert stats["complete"] is False and stats["score"] is None
        assert {r["id"] for r in rows[0]["correspondence"]["ambiguous_candidates"]} == {"first", "second"}


def test_partial_signature_views_cannot_choose_a_title_or_skip_an_inserted_paragraph():
    graph = read_candidate_markdown("# Orchid Instruments\n\nOrchid Instruments\n\nDelivery unavailable.\n\nBoard\n\n2028-03-07")
    _, rows = compare([literal("signature", "Orchid Instruments Board 2028-03-07")], graph["text"])
    assert rows[0]["outcome"] != "correct"
    assert rows[0]["actual"] is None or rows[0]["actual"].get("syntax_kind") != "heading"


def test_literal_match_alone_cannot_supply_an_absent_required_parent_chain():
    required = compile_markdown("## Approval\n\nThe holder may transfer rights only if approved.")
    candidate = read_candidate_markdown("The holder may transfer rights only if approved.")
    score = grade_layers(required, candidate)
    assert any(r["layer"] == "T" and r["outcome"] == "correct" for r in score["outcomes"])
    assert any(r["layer"] in {"L", "B"} and r["outcome"] != "correct" for r in score["outcomes"])


def test_spaced_slash_in_an_explicit_code_is_not_a_row_label_boundary():
    graph = read_candidate_markdown("- Code: XY / 047\n  - Detail: retained\n")
    assert not any(v["atom"]["text"] == "XY" for v in graph["literal_readback"]["views"])


def test_candidate_reading_does_not_depend_on_expected_and_final_cannot_borrow_internal_ir():
    text = "The committee shall publish the notice."
    observed = read_candidate_markdown(text)
    frozen = deepcopy(observed)
    for wanted in (text, text.replace("publish", "withdraw"), "A wholly different request."):
        compare(compile_markdown(wanted)["text"], observed["text"])
        assert observed == frozen
    observation = {"sample_id": "synthetic", "pipeline": "invented", "pages": [],
                   "internal_ir": {"text": text}}
    missing = read_candidate(observation)
    _, rows = compare(compile_markdown(text)["text"], missing["text"])
    assert all(r["outcome"] != "correct" for r in rows)


def test_literal_reading_does_not_change_unknown_parentage_or_add_business_relations():
    graph = read_candidate({"sample_id": "synthetic", "pipeline": "invented", "pages": [{"page": 1, "blocks": [
        {"id": "a", "kind": "text", "text": "A complete ordinary statement. Another ordinary statement."}]}]})
    before = deepcopy((graph["business"], graph["relations"], graph["native_context"]))
    _, rows = compare([literal("literal", "A complete ordinary statement.")], graph["text"])
    assert rows[0]["outcome"] == "correct"
    assert (graph["business"], graph["relations"], graph["native_context"]) == before


def test_existing_canonical_policy_and_real_internal_spaces_remain_unchanged():
    assert canonical("推进 7G-X业务") == canonical("推进7G-X业务")
    assert canonical("回购后 拟注销数量") != canonical("回购后拟注销数量")
    assert canonical("Code 4 7") != canonical("Code 47")


def test_complete_trace_rejects_forged_fragment_or_reused_parent_capacity():
    required = compile_markdown("The permit remains valid.\n\nThe clerk shall send the notice.")
    observed = read_candidate_markdown("The permit remains valid. The clerk shall send the notice.")
    score = grade_layers(required, observed)
    _complete_text_trace(score)
    damaged = deepcopy(score)
    row = next(r for r in damaged["outcomes"] if r["layer"] == "T")
    row["actual"]["source"]["text_span"] = [900, 999]
    with pytest.raises(ValueError):
        _complete_text_trace(damaged)
