"""Bounded reference exposure and responsibility tests with invented text/JSON."""

from copy import deepcopy

import pytest

from moparse_eval.diagnostic_comparison import diagnostic_outcomes, withhold
from moparse_eval.expected_readback import read_expected
from moparse_eval.packaging import write_json


def selected_reference(tmp_path):
    directory = tmp_path / "reference" / "invented"
    directory.mkdir(parents=True)
    (directory / "expected.md").write_text(
        "# Outside secret\n\n# Selected\n\nAmount: 17\n\nForbidden tail: 900\n"
    )
    write_json(
        directory / "manifest.json",
        {
            "markdown": {"path": "expected.md"},
            "source_map": {
                "entries": [
                    {"source_pages": [2], "markdown_lines": [3, 5]},
                    {"source_pages": [1], "markdown_lines": [1, 1]},
                    {"source_pages": [3], "markdown_lines": [7, 7]},
                ]
            },
        },
    )
    return {"id": "one", "document_id": "invented", "source_pages": [2]}, directory.parent


def test_selection_only_reader_never_exposes_other_selection_or_context(tmp_path):
    sample, root = selected_reference(tmp_path)
    result = read_expected(sample, root, selection_only=True)
    assert [target["text"] for target in result["targets"]] == ["Selected", "Amount: 17"]
    assert [target["reference"]["lines"] for target in result["targets"]] == [[3, 3], [5, 5]]
    assert result["authorized_raw_segments"][0]["raw"] == "# Selected\n\nAmount: 17\n"
    assert all(not target["outside_selection_context"] for target in result["targets"])
    assert "secret" not in str(result) and "900" not in str(result)


def test_selection_only_cannot_reuse_whole_document_cache(tmp_path):
    sample, root = selected_reference(tmp_path)
    with pytest.raises(ValueError, match="cannot use a document cache"):
        read_expected(sample, root, selection_only=True, cache={})


def test_selected_source_binding_does_not_compile_new_requirements(tmp_path, monkeypatch):
    from moparse_eval import requirement_graph
    from moparse_eval.diagnostic_artifacts import sha256
    from moparse_eval.diagnostic_comparison import load_requirements

    sample, root = selected_reference(tmp_path)
    expected = read_expected(sample, root, selection_only=True)
    graph = requirement_graph.compile_requirement_graph(
        expected, comparison_contract="document_ast"
    )
    index = tmp_path / "views/index.json"
    path = index.parent / "one.json"
    write_json(path, graph)
    write_json(
        index,
        {
            "records": [
                {"sample_id": "one", "json": "one.json", "generated_view_sha256": sha256(path)}
            ]
        },
    )
    monkeypatch.setattr(
        requirement_graph,
        "compile_requirement_graph",
        lambda *args, **kwargs: pytest.fail("diagnosis must not compile Expected"),
    )
    loaded, projection, _, current = load_requirements(index, sample, root)
    assert (
        loaded == graph
        and current["authorized_raw_segments"] == expected["authorized_raw_segments"]
    )
    assert projection["comparison_contract"] == "document_ast"
    (root / "invented/expected.md").write_text("# Outside secret\n\n# Selected\n\nAmount: 18\n")
    with pytest.raises(ValueError, match="source binding differs"):
        load_requirements(index, sample, root)


def test_withholding_also_removes_nested_document_base_scores():
    def score():
        return {
            "score": 92,
            "publishable": True,
            "layers": {
                layer: {
                    "score": 93,
                    "numerator": 9,
                    "denominator": 10,
                    "diagnostic_score": 94,
                    "full_scope_edit_rate": 0.1,
                }
                for layer in ("T", "L", "B")
            },
        }

    value = score()
    value["document_comparison"] = {"base_score": score(), "decision": {"proof": {"literal": "17"}}}
    withhold(value)
    for part in (value, value["document_comparison"]["base_score"]):
        assert part["publishable"] is False and part["score"] is None
        assert all(
            row["numerator"] is None
            and row["score"] is None
            and row["denominator"] == 10
            and "diagnostic_score" not in row
            for row in part["layers"].values()
        )
    assert value["document_comparison"]["decision"] == {"proof": {"literal": "17"}}


def test_incomplete_business_responsibility_does_not_block_independent_literal_or_neighbor():
    source = {"path": "invented.md", "lines": [3, 3], "text_span": [0, 5]}
    graph = {
        "source_obligation_inventory": {"obligations": [{"id": "o", "layers": ["L", "B"]}]},
        "unresolved": [],
        "comparison_coverage": {
            "obligations": [
                {
                    "obligation_id": "o",
                    "status": "blocking",
                    "source": source,
                    "requirement_ids": [],
                }
            ],
            "analysis_limitations": [],
        },
    }
    score = {
        "outcomes": [
            {
                "id": "text",
                "layer": "T",
                "role": "literal",
                "expected": {"source": source},
                "outcome": "correct",
            },
            {
                "id": "business",
                "layer": "B",
                "role": "fact",
                "expected": {"source": source},
                "outcome": "correct",
            },
            {
                "id": "neighbor",
                "layer": "B",
                "role": "fact",
                "expected": {"source": {**source, "text_span": [5, 9]}},
                "outcome": "incorrect",
            },
        ]
    }
    original = deepcopy(score)
    rows = diagnostic_outcomes(
        score, graph=graph, trace="trace.json", artifact={"path": "native.json"}
    )
    assert [row["status"] for row in rows] == ["correct", "blocked", "incorrect"]
    assert rows[1]["comparator_status"] == "correct" and rows[1]["requirement_status"] == "blocked"
    assert score == original


@pytest.mark.parametrize("mutation", ["same", "changed", "duplicate", "scope"])
def test_candidate_slice_cache_preserves_entire_existing_comparison_trace(tmp_path, mutation):
    from moparse_eval import requirement_ast
    from moparse_eval.diagnostic_comparison import candidate_slice_cache
    from moparse_eval.requirement_graph import compile_requirement_graph, evaluation_projection
    from moparse_eval.three_layer import grade_layers, read_candidate_markdown

    text = (
        "# Authority\n\nThe annual report preserves the committee responsibilities.\n\n"
        "The operating permit remains in effect under the following conditions.\n\n"
        "No holder may transfer rights except under this agreement.\n"
    )
    directory = tmp_path / "invented"
    directory.mkdir()
    (directory / "expected.md").write_text(text)
    write_json(
        directory / "manifest.json",
        {
            "markdown": {"path": "expected.md"},
            "source_map": {
                "entries": [{"source_pages": [1], "markdown_lines": [1, len(text.splitlines())]}]
            },
        },
    )
    expected = read_expected(
        {"id": "one", "document_id": "invented", "source_pages": [1]}, tmp_path
    )
    required = evaluation_projection(
        compile_requirement_graph(expected, comparison_contract="document_ast")
    )
    actual = text
    if mutation == "changed":
        actual = actual.replace("No holder", "Every holder")
    if mutation == "duplicate":
        actual += "\nNo holder may transfer rights except under this agreement.\n"
    if mutation == "scope":
        actual = actual.replace("# Authority", "# Another authority")
    evidence = read_candidate_markdown(actual, sample_id="one")
    before = deepcopy((required, evidence))
    original = requirement_ast._document_slice
    vanilla = grade_layers(required, evidence)
    with candidate_slice_cache() as info:
        cached = grade_layers(required, evidence)
        assert info().misses > 0
    assert cached == vanilla
    assert requirement_ast._document_slice is original
    assert (required, evidence) == before


def test_candidate_slice_cache_is_restored_after_failure():
    from moparse_eval import requirement_ast
    from moparse_eval.diagnostic_comparison import candidate_slice_cache

    original = requirement_ast._document_slice
    with pytest.raises(RuntimeError):
        with candidate_slice_cache():
            raise RuntimeError("controlled failure")
    assert requirement_ast._document_slice is original


def test_candidate_slice_cache_reuses_only_the_same_actual_source_cut(monkeypatch):
    from moparse_eval import requirement_ast
    from moparse_eval.diagnostic_comparison import candidate_slice_cache

    calls = []

    def independent_slice(parts, leaves, start, end, resolver):
        calls.append((parts, start, end))
        return {"actual_source": parts[0][1]["source"]}, [{"text_span": [start, end]}]

    monkeypatch.setattr(requirement_ast, "_document_slice", independent_slice)
    one, other = {"source": "own"}, {"source": "other"}
    with candidate_slice_cache() as info:
        first = requirement_ast._document_slice([(0, one)], [], 0, 2, None)
        assert requirement_ast._document_slice([(0, one)], [], 0, 2, None) == first
        requirement_ast._document_slice([(0, one)], [], 1, 2, None)
        requirement_ast._document_slice([(0, other)], [], 0, 2, None)
        assert info().hits == 1 and len(calls) == 3
    assert requirement_ast._document_slice is independent_slice


def test_native_markdown_paragraphs_resolve_their_own_local_source_frames():
    from moparse_eval.document_ast_comparison import _candidate_ast, _resolve
    from moparse_eval.requirement_ast import validate_content_ast
    from moparse_eval.three_layer import read_candidate

    observation = {
        "sample_id": "one",
        "pipeline": "synthetic",
        "status": "completed",
        "relations": [],
        "pages": [
            {
                "page": 1,
                "blocks": [
                    {
                        "id": "region",
                        "native_path": "#/region",
                        "kind": "text",
                        "text": "Alpha Company\n\n10028161",
                        "text_format": "markdown",
                    }
                ],
            }
        ],
    }
    evidence = read_candidate(observation)
    ast = _candidate_ast(evidence)
    sequences = [block["content"] for block in ast["children"] if block.get("content")]
    assert [_resolve(evidence, node["source"]) for node in sequences] == [
        "Alpha Company",
        "10028161",
    ]
    assert [node["source"]["block_lines"] for node in sequences] == [[1, 1], [3, 3]]
    for node in sequences:
        validate_content_ast(node, lambda source: _resolve(evidence, source))


def test_equal_literals_in_different_native_paragraphs_cannot_share_a_source_frame():
    from moparse_eval.document_ast_comparison import _same_record

    first = {"path": "#/region", "lines": [], "block": "region", "block_lines": [1, 1]}
    second = {**first, "block_lines": [3, 3]}
    assert not _same_record(first, second)
    assert not _same_record({"path": "#/region", "lines": [], "block": "region"}, second)
    assert _same_record(second, dict(second))
