"""Independent development-binding counterexamples using invented JSON/text only.

No conftest, media, SDK, subprocess, service or repository data fixture is used.
"""

from copy import deepcopy

import pytest

from moparse_eval.diagnostic_artifacts import load_artifacts, read_candidates, sha256
from moparse_eval.packaging import read_json, write_json


def authored(tmp_path):
    records = []
    for number in range(1, 9):
        pipeline = f"P{number:02}"
        directory = tmp_path / pipeline
        directory.mkdir()
        selection = {"id": "one", "document_id": "document", "source_pages": [4]}
        source = {
            "selection": selection,
            "software_id": "execution",
            "native": f"{pipeline}/native.json",
            "observation": f"{pipeline}/observation.json",
        }
        for filename, value in [
            ("native.json", {"producer": pipeline}),
            ("observation.json", {"pipeline": pipeline}),
            ("evidence.json", {"stages": []}),
            ("delivery-state.json", {"status": "partial"}),
        ]:
            write_json(directory / filename, value)
        (directory / "final.md").write_text("Amount: 17\n")
        source["native_sha256"] = sha256(directory / "native.json")
        source["observation_sha256"] = sha256(directory / "observation.json")
        write_json(directory / "input-binding.json", source)
        binding = {
            "sample_id": "one",
            "document_id": "document",
            "pipeline": pipeline,
            "software_id": "execution",
            "source_pages": [4],
            "native_sha256": source["native_sha256"],
            "observation_sha256": source["observation_sha256"],
            "artifact_sha256": {
                name: sha256(directory / name)
                for name in (
                    "final.md",
                    "evidence.json",
                    "delivery-state.json",
                    "input-binding.json",
                )
            },
        }
        write_json(directory / "final-binding.json", binding)
        records.append(
            {
                **{
                    key: binding[key]
                    for key in (
                        "sample_id",
                        "document_id",
                        "pipeline",
                        "software_id",
                        "source_pages",
                    )
                },
                "selection_id": "one",
                **{
                    key: {"path": f"{pipeline}/{name}", "sha256": sha256(directory / name)}
                    for key, name in [
                        ("native", "native.json"),
                        ("observation", "observation.json"),
                        ("final", "final.md"),
                        ("evidence", "evidence.json"),
                        ("delivery_state", "delivery-state.json"),
                        ("binding", "final-binding.json"),
                        ("input_binding", "input-binding.json"),
                    ]
                },
            }
        )
    manifest = {
        "diagnostic_only": True,
        "publishable": False,
        "quality_scores_withheld": True,
        "software_id": "execution",
        "sample_ids": ["one"],
        "record_count": 8,
        "document_pipeline_count": 8,
        "document_count": 1,
        "records": records,
    }
    path = tmp_path / "manifest.json"
    write_json(path, manifest)
    return path, manifest


def test_explicit_bindings_keep_selection_and_execution_identity(tmp_path):
    path, manifest = authored(tmp_path)
    before = deepcopy(manifest)
    result = load_artifacts(path, root=tmp_path, sample_ids=["one"])
    assert result["records"] == before["records"]
    assert result["selections"] == {
        "one": {"id": "one", "document_id": "document", "source_pages": [4]}
    }
    assert read_json(path) == before


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "software", "selection", "borrow", "checksum", "escape"]
)
def test_binding_rejects_mixed_or_borrowed_or_missing_artifacts(tmp_path, mutation):
    path, manifest = authored(tmp_path)
    first, second = manifest["records"][:2]
    if mutation == "duplicate":
        manifest["records"][-1] = deepcopy(first)
    if mutation == "missing":
        manifest["records"].pop()
    if mutation == "software":
        first["software_id"] = "other-execution"
    if mutation == "selection":
        first["source_pages"] = [5]
    if mutation == "borrow":
        second["final"] = deepcopy(first["final"])
    if mutation == "checksum":
        (tmp_path / first["final"]["path"]).write_text("stale body")
    if mutation == "escape":
        first["final"]["path"] = "../outside.md"
    write_json(path, manifest)
    with pytest.raises(ValueError):
        load_artifacts(path, root=tmp_path, sample_ids=["one"])


@pytest.mark.parametrize("selection", [[], ["one", "one"], ["absent"]])
def test_selection_is_explicit_and_never_guessed(tmp_path, selection):
    path, _ = authored(tmp_path)
    with pytest.raises(ValueError):
        load_artifacts(path, root=tmp_path, sample_ids=selection)


@pytest.mark.parametrize(
    "field,value",
    [("diagnostic_only", False), ("publishable", True), ("quality_scores_withheld", False)],
)
def test_development_binding_cannot_claim_formal_publication(tmp_path, field, value):
    path, manifest = authored(tmp_path)
    manifest[field] = value
    write_json(path, manifest)
    with pytest.raises(ValueError, match="diagnostic-only"):
        load_artifacts(path, root=tmp_path, sample_ids=["one"])


def test_read_phase_keeps_software_failure_separate_and_final_reads_only_body(
    tmp_path, monkeypatch
):
    from moparse_eval import cli, three_layer
    from moparse_eval import expected_evaluation as evaluation

    path, _ = authored(tmp_path)
    bound = load_artifacts(path, root=tmp_path, sample_ids=["one"])
    bound["records"] = bound["records"][:1]
    seen = []
    monkeypatch.setattr(cli, "code_identity", lambda: {"software_id": "diagnostic"})

    def broken_native(*args, **kwargs):
        raise ValueError("independent native readback failure")

    def final_only(source, **kwargs):
        seen.append(source)
        return {"sample_id": kwargs["sample_id"], "text": source.read_text()}

    monkeypatch.setattr(evaluation, "native_observation", broken_native)
    monkeypatch.setattr(evaluation, "final_observation", final_only)
    monkeypatch.setattr(three_layer, "read_candidate", lambda observation: dict(observation))
    result = read_json(read_candidates(bound, tmp_path / "out", root=tmp_path))
    assert result["expected_access"] is False
    assert result["publishable"] is False
    assert result["records"][0]["sides"]["native"]["state"] == "software_blocked"
    assert "score" not in result["records"][0]["sides"]["native"]
    assert result["records"][0]["sides"]["final"]["state"] == "read"
    assert seen == [tmp_path / "P01/final.md"]


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--diagnostic", "--sample", "one"],
        ["--diagnostic", "--sample", "one", "--workers", "1", "--current-root", "/invented"],
    ],
)
def test_cli_cannot_use_development_manifest_in_formal_or_parallel_or_current_mode(
    monkeypatch, extra
):
    from moparse_eval.expected_evaluation import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "diagnostic",
            "--baseline",
            "/invented",
            "--output",
            "/invented-out",
            "--diagnostic-artifact-manifest",
            "/invented-manifest",
            *extra,
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_own_sdk_heading_metadata_is_exposed_without_changing_primary_text():
    from moparse_eval.diagnostic_artifacts import expose_native_heading_fields
    from moparse_eval.document_ast_comparison import _candidate_ast
    from moparse_eval.three_layer import read_candidate

    observation = {
        "sample_id": "invented",
        "pipeline": "synthetic",
        "status": "completed",
        "relations": [],
        "pages": [
            {
                "page": 1,
                "blocks": [
                    {
                        "id": "root",
                        "native_path": "#/root",
                        "kind": "doc_title",
                        "text": "Title",
                        "text_format": "markdown",
                        "native_export_markdown": "# Title",
                    },
                    {
                        "id": "section",
                        "native_path": "#/section",
                        "kind": "paragraph_title",
                        "text": "Section",
                        "text_format": "markdown",
                        "native_export_markdown": "## Section",
                        "native_export_markdown_path": "#/sdk_export/section",
                    },
                    {
                        "id": "body",
                        "native_path": "#/body",
                        "kind": "text",
                        "text": "Amount: 17",
                        "text_format": "plain",
                    },
                ],
            }
        ],
    }
    original = deepcopy(observation)
    derived, evidence = expose_native_heading_fields(observation)
    assert observation == original
    assert len(evidence) == 1 and evidence[0]["source"] == "#/sdk_export/section"
    assert evidence[0]["expected_access"] is False
    assert [b["text"] for b in derived["pages"][0]["blocks"]] == ["Title", "Section", "Amount: 17"]
    candidate = read_candidate(derived)
    section = next(u for u in candidate["syntax"] if u["text"] == "Section")
    body = next(u for u in candidate["syntax"] if u["text"] == "Amount: 17")
    assert section["kind"] == "heading" and section["heading_level"] == 2
    assert body["scope"] == ["Title", "Section"]
    _candidate_ast(candidate)  # the independent native scope must agree


@pytest.mark.parametrize("exported", ["## Another title", "## Section\n\nExtra text", "", None])
def test_conflicting_or_mixed_or_missing_sdk_views_cannot_supply_heading_fields(exported):
    from moparse_eval.diagnostic_artifacts import expose_native_heading_fields

    observation = {
        "pages": [
            {
                "page": 1,
                "blocks": [
                    {
                        "id": "own",
                        "native_path": "#/own",
                        "kind": "paragraph_title",
                        "text": "Section",
                        "text_format": "markdown",
                        "native_export_markdown": exported,
                    }
                ],
            }
        ]
    }
    derived, evidence = expose_native_heading_fields(observation)
    assert derived == observation and evidence == []
    assert "level" not in derived["pages"][0]["blocks"][0]


@pytest.mark.parametrize("mode", ["native_level", "primary_markup"])
def test_heading_readback_uses_existing_levels_or_primary_markup_without_guessing(mode):
    from moparse_eval.diagnostic_artifacts import expose_native_heading_fields
    from moparse_eval.document_ast_comparison import _candidate_ast
    from moparse_eval.three_layer import read_candidate

    block = {
        "id": "s",
        "native_path": "#/s",
        "kind": "paragraph_title",
        "text": "Section",
        "text_format": "plain",
    }
    if mode == "native_level":
        block["level"] = 2
    else:
        block.update(kind="text", text="## Section", text_format="markdown")
    original = {
        "sample_id": "one",
        "pipeline": "synthetic",
        "status": "completed",
        "relations": [],
        "pages": [
            {
                "page": 1,
                "blocks": [
                    block,
                    {
                        "id": "b",
                        "native_path": "#/b",
                        "kind": "text",
                        "text": "Revenue: 17",
                        "text_format": "plain",
                    },
                ],
            }
        ],
    }
    before = deepcopy(original)
    derived, proof = expose_native_heading_fields(original)
    assert original == before and proof[0]["exposed_level"] == 2
    candidate = read_candidate(derived)
    assert next(u for u in candidate["syntax"] if u["text"] == "Section")["heading_level"] == 2
    _candidate_ast(candidate)


def test_unknown_native_levels_withdraw_guessed_syntax_hierarchy_and_preserve_facts():
    from moparse_eval.diagnostic_artifacts import bind_native_syntax_scopes
    from moparse_eval.document_ast_comparison import _candidate_ast
    from moparse_eval.three_layer import read_candidate

    original = {
        "sample_id": "one",
        "pipeline": "synthetic",
        "status": "completed",
        "relations": [],
        "pages": [
            {
                "page": 1,
                "blocks": [
                    {
                        "id": "s",
                        "native_path": "#/s",
                        "kind": "title",
                        "text": "Section",
                        "text_format": "plain",
                    },
                    {
                        "id": "b",
                        "native_path": "#/b",
                        "kind": "text",
                        "text": "Revenue: 17",
                        "text_format": "plain",
                    },
                ],
            }
        ],
    }
    candidate = read_candidate(original)
    business = deepcopy(candidate["business"])
    text = deepcopy(candidate["text"])
    with pytest.raises(ValueError, match="native heading evidence"):
        _candidate_ast(candidate)
    proof = bind_native_syntax_scopes(candidate)
    assert any(row["action"] == "withdraw_inferred_heading_level" for row in proof)
    assert candidate["business"] == business and candidate["text"] == text
    assert all("heading_level" not in u for u in candidate["syntax"] if u["kind"] == "heading")
    _candidate_ast(candidate)


def test_explicit_native_scope_conflict_is_not_rebound():
    from moparse_eval.diagnostic_artifacts import bind_native_syntax_scopes

    evidence = {
        "syntax": [
            {"kind": "text", "text": "Amount: 17", "source": {"block": "b"}, "scope": ["Other"]}
        ],
        "native_context": {
            "heading_events": [],
            "by_block": {
                "b": {
                    "heading_path": ["Source"],
                    "context_evidence": [],
                    "conflicts": ["explicit_conflict"],
                }
            },
        },
    }
    original = deepcopy(evidence)
    assert bind_native_syntax_scopes(evidence) == [] and evidence == original


@pytest.mark.parametrize(
    "primary,exported",
    [("一、重要提示", "## 一、 重要提示"), (r"管理层讨论\n与分析", "## 管理层讨论 与分析")],
)
def test_sdk_heading_layout_binding_never_rewrites_primary_or_literal_escape(primary, exported):
    from moparse_eval.diagnostic_artifacts import expose_native_heading_fields
    from moparse_eval.document_ast_comparison import _candidate_ast
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
                        "id": "s",
                        "native_path": "#/s",
                        "kind": "paragraph_title",
                        "text": primary,
                        "text_format": "markdown",
                        "native_export_markdown": exported,
                    },
                    {
                        "id": "b",
                        "native_path": "#/b",
                        "kind": "text",
                        "text": "Amount: 17",
                        "text_format": "plain",
                    },
                ],
            }
        ],
    }
    before = deepcopy(observation)
    exposed, proof = expose_native_heading_fields(observation)
    assert proof and observation == before and exposed["pages"][0]["blocks"][0]["text"] == primary
    candidate = read_candidate(exposed)
    assert next(u for u in candidate["syntax"] if u["source"]["block"] == "s")["text"] == primary
    _candidate_ast(candidate)
