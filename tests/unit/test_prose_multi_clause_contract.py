"""Hand-authored logical-clause requirements, never compiler-generated answers."""

from copy import deepcopy

import pytest

from moparse_eval.expected_readback import markdown_observation
from moparse_eval.prose_requirements import read_prose_requirements
from moparse_eval.three_layer import compile_markdown, grade_layers, read_candidate

SOURCE = {"path": "<invented-multiple-clauses>", "lines": [7, 7]}
COMPOUND = [
    ("If A is ready, Board may pay if B is ready.",
     [("condition", "if", "A is ready"), ("condition", "if", "B is ready")]),
    ("Unless A is ready, Board may pay unless B is ready.",
     [("condition", "unless", "A is ready"), ("condition", "unless", "B is ready")]),
    ("Only if A is ready, Board may pay only if B is ready.",
     [("condition", "only if", "A is ready"), ("condition", "only if", "B is ready")]),
    ("Except when A is ready, Board may pay except when B is ready.",
     [("exception", "except when", "A is ready"), ("exception", "except when", "B is ready")]),
    ("If A is ready, Board may pay except when B is ready.",
     [("condition", "if", "A is ready"), ("exception", "except when", "B is ready")]),
    ("Except when A is ready, Board may pay if B is ready.",
     [("exception", "except when", "A is ready"), ("condition", "if", "B is ready")]),
    ("If A is ready, Board may pay unless B is ready.",
     [("condition", "if", "A is ready"), ("condition", "unless", "B is ready")]),
    ("If B is ready, Board may pay if A is ready.",
     [("condition", "if", "B is ready"), ("condition", "if", "A is ready")]),
]


def parsed(text):
    source = {**SOURCE, "text_span": [13, 13 + len(text)]}
    before = deepcopy(source)
    result = read_prose_requirements(text, source)
    assert source == before
    assert result["text_spans"] == [{"text": text, "span": [0, len(text)],
                                     "role": "original_prose", "source": source}]
    return result, source


def expected_fragment(text, source, kind, operator, operand):
    # Roles and operators above are the oracle; these offsets locate their
    # exact declared fixture literals, without consulting a reader/compiler.
    start = text.index(operand)
    operator_start = text.lower().rfind(operator, 0, start)
    assert operator_start >= 0
    offset = source["text_span"][0]
    return {"kind": kind, "operator": operator, "text": operand,
            "source": {**source, "text_span": [offset + start, offset + start + len(operand)]},
            "operator_source": {**source, "text_span": [offset + operator_start,
                                                       offset + operator_start + len(operator)]}}


def assert_modal_role_bindings(result, text, source):
    """The logical qualifier coexists with independently bound modal S/P/O."""
    offset = source["text_span"][0]
    def origin(literal):
        start = text.index(literal)
        return {**source, "text_span": [offset + start, offset + start + len(literal)]}
    [binding] = [edge for edge in result["relations"] if edge["type"] == "field_binding"]
    assert binding["left"] == {"subject": "Board", "attribute": "pay"}
    assert binding["right"] == {"subject": "Board", "attribute": "pay", "scope": [], "identity_facets": {}}
    pay = origin("pay")
    statement_source = {**source, "text_span": [offset, offset + len(text.rstrip("."))]}
    assert binding["source"] == pay
    assert binding["binding_evidence"] == {
        "statement_source": statement_source, "subject_source": origin("Board"), "predicate_source": pay,
        "object_source": {**source, "text_span": [pay["text_span"][1], pay["text_span"][1]]}}
    [modal] = [edge for edge in result["relations"] if edge["type"] == "qualifier_scope"]
    assert modal["left"] == {"type": "modality", "text": "may"}
    assert modal["right"] == binding["right"]
    assert modal["source"] == modal["operator_source"] == origin("may")
    assert modal["binding_evidence"] == {**binding["binding_evidence"], "operator": "may", "operator_source": origin("may")}


@pytest.mark.parametrize("text,clauses", COMPOUND, ids=["if-if", "unless-unless", "only-if-twice",
                                                       "exception-twice", "condition-exception",
                                                       "exception-condition", "if-unless", "reversed-operands"])
def test_two_printed_connectors_remain_ordered_source_bound_pending_without_a_partial_answer(text, clauses):
    result, source = parsed(text)
    assert result["matched"] is True
    assert result["facts"] == [] and result["relations"] == []
    blockers = [item for item in result["blockers"] if set(item.get("layers", [])) >= {"B", "L"}]
    assert blockers
    [pending] = [item for item in result["pending_requirements"] if item.get("kind") == "compound_logical_scope"]
    assert pending["text"] == text and pending["source"] == source
    wanted = [expected_fragment(text, source, *clause) for clause in clauses]
    assert len(pending["fragments"]) == 2
    assert [{key: item[key] for key in wanted[0]} for item in pending["fragments"]] == wanted
    assert pending["fragments"][0]["source"]["text_span"][1] < pending["fragments"][1]["source"]["text_span"][0]


@pytest.mark.parametrize("text,kind,operator", [
    ("If A is ready, Board may pay.", "condition", "if"),
    ("Board may pay if A is ready.", "condition", "if"),
    ("Only if A is ready, Board may pay.", "condition", "only_if"),
    ("Board may pay only if A is ready.", "condition", "only_if"),
    ("Unless A is ready, Board may pay.", "condition", "unless"),
    ("Board may pay unless A is ready.", "condition", "unless"),
    ("Board may pay except when A is ready.", "exception", "except_when"),
])
def test_one_printed_condition_or_exception_keeps_its_complete_supported_role(text, kind, operator):
    result, source = parsed(text)
    assert result["blockers"] == [] and result["pending_requirements"] == []
    [fact] = result["facts"]
    assert (fact["subject"], fact["attribute"], fact["value"], fact["role"]) == (
        "Board", "pay", "pay", "description")
    assert fact["qualifiers"] == {"modality": "may", "polarity": "positive",
                                  kind: "A is ready", kind + "_operator": operator}
    [relation] = [edge for edge in result["relations"] if edge["type"] == kind + "_scope"]
    assert relation["type"] == kind + "_scope"
    assert relation["left"] == {"role": kind, "lexical_anchor": ["A", "is", "ready"]}
    assert relation["right"] == {"subject": "Board", "action": "pay", "scope": []}
    start = text.index("A is ready")
    assert fact["qualifier_sources"][kind] == {**source, "text_span": [13 + start, 13 + start + 10]}
    assert_modal_role_bindings(result, text, source)
    assert len(result["relations"]) == 3


def test_single_leading_exception_is_an_exception_or_explicitly_unsupported_never_a_condition():
    text = "Except when A is ready, Board may pay."
    result, source = parsed(text)
    if result["blockers"]:
        assert result["facts"] == []
        assert set().union(*(set(item.get("layers", [])) for item in result["blockers"])) >= {"B", "L"}
    else:
        [fact] = result["facts"]
        assert fact["qualifiers"] == {"modality": "may", "polarity": "positive",
                                      "exception": "A is ready", "exception_operator": "except_when"}
        [relation] = [edge for edge in result["relations"] if edge["type"] == "exception_scope"]
        assert relation["type"] == "exception_scope"
        assert relation["left"] == {"role": "exception", "lexical_anchor": ["A", "is", "ready"]}
        assert_modal_role_bindings(result, text, source)


def test_condition_words_keep_their_printed_order_in_both_assertion_and_relation():
    original_text, reversed_text = "If A is ready, Board may pay.", "If ready is A, Board may pay."
    original, original_source = parsed(original_text)
    reversed_words, reversed_source = parsed(reversed_text)
    assert original["blockers"] == reversed_words["blockers"] == []
    assert len(original["facts"]) == len(reversed_words["facts"]) == 1
    assert original["facts"][0]["qualifiers"]["condition"] == "A is ready"
    assert reversed_words["facts"][0]["qualifiers"]["condition"] == "ready is A"
    [first] = [edge for edge in original["relations"] if edge["type"] == "condition_scope"]
    [second] = [edge for edge in reversed_words["relations"] if edge["type"] == "condition_scope"]
    assert first["left"]["lexical_anchor"] == ["A", "is", "ready"]
    assert second["left"]["lexical_anchor"] == ["ready", "is", "A"]
    assert_modal_role_bindings(original, original_text, original_source)
    assert_modal_role_bindings(reversed_words, reversed_text, reversed_source)


def test_purpose_plus_one_tail_condition_is_the_existing_distinct_supported_path():
    text = "To participate, Board may pay if A is ready."
    result, source = parsed(text)
    assert result["blockers"] == [] and result["pending_requirements"] == []
    [fact] = result["facts"]
    assert fact["qualifiers"] == {"purpose": "participate", "modality": "may", "polarity": "positive",
                                  "condition": "A is ready", "condition_operator": "if"}
    assert [(edge["type"], edge["left"]) for edge in result["relations"] if edge["type"] in {"condition_scope", "purpose_scope"}] == [
        ("condition_scope", {"role": "condition", "lexical_anchor": ["A", "is", "ready"]}),
        ("purpose_scope", {"role": "purpose", "lexical_anchor": ["participate"]}),
    ]
    assert_modal_role_bindings(result, text, source)
    assert len(result["relations"]) == 4


@pytest.mark.parametrize("text", [COMPOUND[index][0] for index in (0, 3, 5)])
def test_final_markdown_public_entry_keeps_full_t_and_blocks_b_l_despite_another_answered_identity(text):
    markdown = "# Policy\n\nName: Anchor\n\n" + text
    requirements = compile_markdown(markdown, sample_id="invented-multiple-clauses")
    observation = markdown_observation(markdown, sample_id="invented-multiple-clauses", pipeline="P07", pages=[1])
    candidate = read_candidate(observation)
    for graph in (requirements, candidate):
        assert [(fact["attribute"], fact["value"], fact["role"]) for fact in graph["business"]] == [
            ("Name", "Anchor", "identity")]
        assert text in [atom["text"] for atom in graph["text"]]
        [pending] = [item for item in graph["pending_requirements"] if item.get("text") == text
                     and set(item.get("layers", [])) >= {"B", "L"}]
        assert pending["source"]["text_span"] == [0, len(text)]
        clauses = next(clauses for printed, clauses in COMPOUND if printed == text)
        wanted = [expected_fragment(text, pending["source"], *clause) for clause in clauses]
        assert [{key: item[key].replace("_", " ") if key == "operator" else item[key]
                 for key in ("operator", "text", "source", "operator_source")}
                for item in pending["fragments"]] == [
            {key: item[key] for key in ("operator", "text", "source", "operator_source")} for item in wanted]
    score = grade_layers(requirements, candidate)
    assert score["publishable"] is False and score["score"] is None
    assert score["layers"]["T"]["score"] == 100
    assert score["layers"]["B"]["complete"] is score["layers"]["L"]["complete"] is False
    assert score["layers"]["B"]["score"] is score["layers"]["L"]["score"] is None
