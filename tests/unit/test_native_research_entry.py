"""Independent admission mutations over invented text/JSON, never real scores.

Only tmp_path/monkeypatch fixtures are used. Namespace launching is intercepted;
the real 24-input reader is verified separately with Expected masked out.
"""

from copy import deepcopy

import pytest

from moparse_eval import cli
from moparse_eval import native_evaluation as entry
from moparse_eval.expected_readback import read_expected
from moparse_eval.packaging import write_json
from moparse_eval.requirement_graph import (
    compile_requirement_graph,
    evaluation_projection,
    write_requirement_graph,
)


def invented(tmp_path, monkeypatch):
    monkeypatch.setattr(entry, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "code_identity", lambda: {"software_id": "invented-current"})
    area = tmp_path / entry.AREA
    area.mkdir(parents=True)
    records, permission_rows, requirements, references = [], [], [], []
    for sid, (_, document, pages) in entry.SELECTIONS.items():
        folder = tmp_path / "pdf_sample/parsing/expected" / document
        folder.mkdir(parents=True)
        text = "Name: Delta; Revenue: 17\n"
        (folder / "expected.md").write_text(text)
        write_json(
            folder / "manifest.json",
            {
                "markdown": {"path": "expected.md"},
                "source_map": {"entries": [{"source_pages": pages, "markdown_lines": [1, 1]}]},
            },
        )
        references.extend(entry.reference(folder / f) for f in ("manifest.json", "expected.md"))
        selection = {"id": sid, "document_id": document, "source_pages": pages}
        graph = compile_requirement_graph(
            read_expected(selection, tmp_path / "pdf_sample/parsing/expected"),
            comparison_contract="document_ast",
        )
        path = tmp_path / "benchmark/runs/lite/requirements/current/samples" / (sid + ".json")
        write_requirement_graph(graph, path, path.with_suffix(".xml"))
        index_row = {
            "sample_id": sid,
            "json": "samples/" + sid + ".json",
            "generated_view_sha256": entry.sha256(path),
        }
        requirements.append(
            {
                "sample_id": sid,
                "json": entry.reference(path),
                "xml": entry.reference(path.with_suffix(".xml")),
                "index_record": index_row,
                "inventory": entry.requirement_inventory(evaluation_projection(graph)),
            }
        )
        for pipeline in entry.PIPELINES:
            directory = (
                tmp_path
                / "benchmark/runs/lite/artifacts"
                / pipeline
                / "measured-quality800-r1"
                / sid
            )
            mapping = [
                {"entry": f"#/pages/{i}", "input_page": i + 1, "original_page": p, "branch": "glm"}
                for i, p in enumerate(pages)
            ]
            configuration = {"pipeline": pipeline, "model": "invented-fixed"}
            write_json(
                directory / "native.json",
                {
                    "pipeline": pipeline,
                    "config": configuration,
                    "pages": [
                        {"page": i + 1, "branch": "glm", "raw": {}} for i in range(len(pages))
                    ],
                },
            )
            write_json(
                directory / "observation.json",
                {"sample_id": sid, "pipeline": pipeline, "run_id": "invented"},
            )
            records.append(
                {
                    "sample_id": sid,
                    "document_id": document,
                    "selection_id": sid,
                    "pipeline": pipeline,
                    "source_pages": pages,
                    "selection": selection,
                    "native": entry.reference(directory / "native.json"),
                    "observation": entry.reference(directory / "observation.json"),
                    "producer": "invented-own",
                    "configuration": configuration,
                    "page_bindings": mapping,
                    "native_run_id": "invented",
                    "native_software_id": "historical-native",
                }
            )
            permission_rows.append(
                {
                    "sample_id": sid,
                    "pipeline": pipeline,
                    "page_branches_views_and_permissions": [
                        {
                            "existing_page_binding": p,
                            "original_source_permission": "own model observations",
                        }
                        for p in mapping
                    ],
                }
            )
    index = tmp_path / "benchmark/runs/lite/requirements/current/index.json"
    write_json(
        index, {"state": "structure_blocked", "records": [r["index_record"] for r in requirements]}
    )
    oracle = area / "historical-oracle.json"
    oracle_case = area / "invented-oracle-case.json"
    write_json(
        oracle_case,
        {"input": "invented source", "expected": "bound source", "observed": "bound source"},
    )
    write_json(
        oracle,
        {
            "source_oracle_passed": 3,
            "source_span_oracle_passed": 1,
            "original_61_ids": list(entry.SELECTIONS),
            "fixed_2_ids": [],
            "evidence_sha256": {oracle_case.name: entry.sha256(oracle_case)},
            "source_index_sha256": entry.sha256(index),
        },
    )
    cost = area / "original-cost.json"
    write_json(cost, {"processing_seconds": 4, "scope": "historical global only"})
    cost_verification = area / "cost-verification.json"
    execution_verification = area / "execution-verification.json"
    write_json(
        cost_verification,
        {
            "records": [{"pipeline": p} for p in entry.PIPELINES],
            "original_cost_bindings": [entry.reference(cost)],
        },
    )
    write_json(execution_verification, {"records": [{"pipeline": p} for p in entry.PIPELINES]})
    history = {
        "records": records,
        "reference_files": references,
        "requirement_files": [entry.reference(index), *[r["json"] for r in requirements]],
    }
    preparation = {
        "records": permission_rows,
        "phase16": {
            "original_cost_verification": entry.reference(cost_verification),
            "original_execution_verification": entry.reference(execution_verification),
        },
    }
    for relative, value, key in [
        (entry.HISTORY, history, "HISTORY_SHA"),
        (entry.PREPARATION, preparation, "PREPARATION_SHA"),
    ]:
        path = tmp_path / relative
        write_json(path, value)
        monkeypatch.setattr(entry, key, entry.sha256(path))
    matrix_rows = []
    for row in records:
        inventory = next(r["inventory"] for r in requirements if r["sample_id"] == row["sample_id"])
        matrix_rows.append(
            {
                "sample_id": row["sample_id"],
                "pipeline": row["pipeline"],
                "layers": {
                    layer: {
                        "state": "partial" if layer == "T" else "blocked",
                        "required_records": len(inventory["requirement_ids"][layer]),
                        "fixed_denominator": inventory["denominators"][layer],
                        "not_comparable_requirement_ids": inventory["requirement_ids"][layer],
                        "not_comparable_reasons": {
                            k: "unresolved independently"
                            for k in inventory["requirement_ids"][layer]
                        },
                    }
                    for layer in entry.LAYERS
                },
            }
        )
    matrix = tmp_path / entry.MATRIX
    write_json(matrix, {"records": matrix_rows})
    monkeypatch.setattr(entry, "MATRIX_SHA", entry.sha256(matrix))
    evidence = {}
    reads = []
    for row in records:
        target = area / "invented-reading" / row["pipeline"] / row["sample_id"] / "native.json"
        write_json(target, {"invented": "candidate-only receipt transport"})
        reads.append(
            {
                **{k: row[k] for k in ("sample_id", "pipeline", "native", "observation")},
                "state": "read",
                "candidate": entry.reference(target),
            }
        )
    for name in ("source_only", "independent_entry", "native_reading"):
        receipt = area / (name + ".json")
        write_json(
            receipt,
            {
                "status": "passed",
                "software_id": "invented-current",
                "exit_code": 0,
                "collection_only": False,
                "software_unchanged": True,
                "tests_unchanged": True,
                "boundary_violations": [],
                "executed_nodeids": ["invented-case"],
                "reviewed_files": {},
                "records": reads,
                "expected_access": False,
                "Final_access": False,
                "source_masked": True,
                "network_namespace_isolated": True,
            },
        )
        evidence[name] = entry.reference(receipt)
    parts = {
        "scope": {
            "benchmark": "native",
            "selection_ids": list(entry.SELECTIONS),
            "pipelines": list(entry.PIPELINES),
            "combinations": 24,
            "independent_holdout": False,
            "represents_full_lite": False,
        },
        "inputs": {"records": entry.input_rows(history, preparation)},
        "evaluation": {
            "software": cli.code_identity(),
            "protocol": cli.SCORING_PROTOCOL,
            "python_executable": entry.sys.executable,
            "environment_files": [],
        },
        "requirements": {
            "index": entry.reference(index),
            "records": requirements,
            "reference_files": references,
            "historical_independent_acceptance": entry.reference(oracle),
            "independent_evidence": [entry.reference(oracle_case)],
        },
        "costs": {
            "verification": entry.reference(cost_verification),
            "execution_verification": entry.reference(execution_verification),
            "original_record_bindings": [entry.reference(cost)],
        },
        "readiness": {"records": matrix_rows},
        "validation": {"software_id": "invented-current", **evidence},
    }
    freeze = area / "freeze.json"
    frozen = {
        **entry.PERMISSIONS,
        "schema": entry.SCHEMA,
        "software_id": "invented-current",
        "components": {},
    }
    for name, value in parts.items():
        target = area / (name + "-binding.json")
        write_json(target, value)
        frozen["components"][name] = entry.reference(target)
    write_json(freeze, frozen)
    return freeze, frozen, parts


def change_part(freeze, frozen, parts, name):
    path = entry.ROOT / frozen["components"][name]["path"]
    write_json(path, parts[name])
    frozen["components"][name] = entry.reference(path)
    write_json(freeze, frozen)


def test_complete_fixed_preflight_is_unapproved_and_never_calls_grader(tmp_path, monkeypatch):
    freeze, _, _ = invented(tmp_path, monkeypatch)
    from moparse_eval import three_layer

    monkeypatch.setattr(three_layer, "grade_layers", lambda *_: pytest.fail("preflight scored"))
    before = freeze.read_bytes()
    result = entry.preflight(freeze)
    assert result["preflight_status"] == "ready_for_authorization"
    assert result["layer_readiness"] == {
        "T": {"partial": 24},
        "L": {"blocked": 24},
        "B": {"blocked": 24},
    }
    assert result["quality_scoring_executed"] is False
    assert {k: result[k] for k in entry.PERMISSIONS} == entry.PERMISSIONS
    assert freeze.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_native",
        "native_sha",
        "observation_sha",
        "pipeline",
        "selection",
        "page_mapping",
        "producer",
        "source_permission",
        "final_input",
        "expand_selection",
        "drop_pipeline",
        "missing_requirement",
        "missing_acceptance",
        "missing_cost",
        "software_identity",
        "software_exception",
        "expected_blocked",
        "promote_partial",
        "promote_approval",
        "incomplete_evidence",
    ],
)
def test_fixed_preflight_rejects_independently_authored_mutations(tmp_path, monkeypatch, mutation):
    freeze, frozen, parts = invented(tmp_path, monkeypatch)
    row = parts["inputs"]["records"][0]
    changed = "inputs"
    if mutation == "missing_native":
        (tmp_path / row["native"]["path"]).unlink()
    elif mutation in {"native_sha", "observation_sha"}:
        row[mutation.removesuffix("_sha")]["sha256"] = "0" * 64
    elif mutation == "pipeline":
        row["pipeline"] = "P02"
    elif mutation == "selection":
        row["selection_id"] = "another-selection"
    elif mutation == "page_mapping":
        row["page_bindings"][0]["original_page"] = 99
    elif mutation == "producer":
        row["producer"] = "borrowed-producer"
    elif mutation == "source_permission":
        row["page_branches_views_and_permissions"][0]["original_source_permission"] = (
            "Expected supplement"
        )
    elif mutation == "final_input":
        row["native"]["path"] = "service/development/final.json"
    elif mutation == "expand_selection":
        changed = "scope"
        parts[changed]["selection_ids"].append("S9")
    elif mutation == "drop_pipeline":
        parts[changed]["records"].pop()
    elif mutation == "missing_requirement":
        changed = "requirements"
        parts[changed]["records"][0]["inventory"]["requirement_ids"]["B"].pop()
    elif mutation == "missing_acceptance":
        changed = "requirements"
        (tmp_path / parts[changed]["historical_independent_acceptance"]["path"]).unlink()
    elif mutation == "missing_cost":
        changed = "costs"
        parts[changed]["original_record_bindings"].clear()
    elif mutation == "software_identity":
        changed = "evaluation"
        parts[changed]["software"]["software_id"] = "other-version"
    elif mutation == "software_exception":
        monkeypatch.setattr(
            cli, "code_identity", lambda: (_ for _ in ()).throw(RuntimeError("invented failure"))
        )
    elif mutation == "expected_blocked":
        from moparse_eval import requirement_gate

        original = requirement_gate.load_bound_requirement

        def blocked(*args):
            graph, *rest = original(*args)
            graph["comparison_coverage"]["responsibility_complete"] = False
            return graph, *rest

        monkeypatch.setattr(requirement_gate, "load_bound_requirement", blocked)
    elif mutation == "promote_partial":
        changed = "readiness"
        parts[changed]["records"][0]["layers"]["T"]["state"] = "ready"
    elif mutation == "promote_approval":
        frozen.update(approval_status="approved", execution_authorized=True)
    elif mutation == "incomplete_evidence":
        changed = "validation"
        parts[changed].pop("independent_entry")
    change_part(freeze, frozen, parts, changed)
    result = entry.preflight(freeze)
    assert result["preflight_status"] == "blocked"
    assert result["quality_scoring_executed"] is False
    assert "score" not in result


def test_formal_execution_stops_before_any_read_or_write_without_explicit_approval(
    tmp_path, monkeypatch
):
    freeze, _, _ = invented(tmp_path, monkeypatch)
    output = tmp_path / "benchmark/runs/lite/native-only/unapproved"
    monkeypatch.setattr(
        entry, "preflight", lambda *_: pytest.fail("unapproved execution preflight")
    )
    monkeypatch.setattr(
        entry, "launch_reading", lambda *_: pytest.fail("unapproved candidate read")
    )
    with pytest.raises(ValueError, match="execution_authorized=false"):
        entry.execute_native(freeze, output, None)
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    ["no_instruction", "wrong_freeze", "scope", "entry", "freeze", "execute", "bare_flag"],
)
def test_approval_must_bind_each_explicit_decision_and_exact_freeze(
    tmp_path, monkeypatch, mutation
):
    freeze, _, _ = invented(tmp_path, monkeypatch)
    approval = {
        "origin": "explicit_user_instruction",
        "instruction_reference": "invented transport case only",
        "freeze": entry.reference(freeze),
        "software_id": "invented-current",
        "approval_status": "approved",
        "execution_authorized": True,
        "decisions": dict.fromkeys(entry.DECISIONS, True),
    }
    if mutation == "no_instruction":
        approval.pop("instruction_reference")
    elif mutation == "wrong_freeze":
        approval["freeze"]["sha256"] = "0" * 64
    elif mutation == "bare_flag":
        approval = {"execution_authorized": True}
    else:
        key = dict(zip(("scope", "entry", "freeze", "execute"), entry.DECISIONS, strict=True))[
            mutation
        ]
        approval["decisions"][key] = False
    path = tmp_path / "invented-approval.json"
    write_json(path, approval)
    with pytest.raises(ValueError, match="explicit approvals"):
        entry.require_authorization(path, freeze)


@pytest.mark.parametrize(
    "destination",
    [
        "benchmark/runs/lite/scores/current/index.json",
        "benchmark/runs/lite/service/current/index.json",
        "benchmark/runs/lite/native-only/current/index.json",
        "benchmark/runs/lite/artifacts/scores/index.json",
        "benchmark/runs/lite/native-only",
    ],
)
def test_native_output_cannot_activate_or_overwrite_a_formal_current(
    tmp_path, monkeypatch, destination
):
    monkeypatch.setattr(entry, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="current activation"):
        entry._output(tmp_path / destination, execute=True)


@pytest.mark.parametrize(
    "option", ["--sample", "--pipeline", "--current-root", "--diagnostic", "--workers"]
)
def test_native_cli_has_no_runtime_scope_or_stage_override(option, tmp_path):
    with pytest.raises(SystemExit):
        cli.parser().parse_args(
            [
                "native-evaluate",
                "--freeze",
                str(tmp_path / "freeze.json"),
                "--output",
                str(tmp_path / "result.json"),
                option,
                "anything",
            ]
        )


def test_partial_and_blocked_keep_all_denominators_and_no_candidate_zero():
    from test_three_layer_orchestration import sample

    score = sample()
    inventory = {
        "requirement_ids": {
            layer: [r["id"] for r in score["outcomes"] if r["layer"] == layer]
            for layer in entry.LAYERS
        },
        "denominators": {layer: score["layers"][layer]["denominator"] for layer in entry.LAYERS},
    }
    mask = {
        "layers": {
            layer: {
                "state": "partial" if layer == "T" else "blocked",
                "not_comparable_reasons": dict.fromkeys(
                    inventory["requirement_ids"][layer], "unknown native relation"
                ),
            }
            for layer in entry.LAYERS
        }
    }
    before = deepcopy(score)
    result = entry.retain_limits(score, mask, inventory)
    assert score == before
    assert all(
        result["layers"][layer]["denominator"] == inventory["denominators"][layer]
        for layer in entry.LAYERS
    )
    assert all(result["layers"][layer]["numerator"] is None for layer in entry.LAYERS)
    assert all(r["outcome"] == "unresolved" for r in result["outcomes"])
    assert result["score"] is None and result["publishable"] is False
    del score["outcomes"][-1]
    with pytest.raises(ValueError, match="fixed requirement"):
        entry.retain_limits(score, mask, inventory)


def test_native_candidate_receives_only_own_artifacts_and_no_expected_argument(monkeypatch):
    from moparse_eval import expected_evaluation, native_candidate

    original = {"sample_id": "invented", "pipeline": "P01", "pages": []}
    monkeypatch.setattr(
        expected_evaluation, "native_observation", lambda *_a, **_k: deepcopy(original)
    )
    evidence, _ = native_candidate.read_native_candidate(
        {
            "sample_id": "invented",
            "pipeline": "P01",
            "observation": {"path": "own/observation.json"},
        },
        root=entry.ROOT,
    )
    assert evidence["sample_id"] == "invented"
    assert original == {"sample_id": "invented", "pipeline": "P01", "pages": []}
