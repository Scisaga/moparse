"""Report mutation checks on invented complete three-layer score material."""

from __future__ import annotations

from copy import deepcopy

import pytest

from moparse_eval.expected_report import load_complete, text_layer_diagnostics, validate_evidence
from moparse_eval.layer_aggregation import VALIDATION_STAGES, paired_layers, summarize_layers
from moparse_eval.packaging import read_json, write_json
from moparse_eval.three_layer import (
    PROTOCOL,
    compile_markdown,
    grade_layers,
    read_candidate_markdown,
)
from scripts.render_lite_report import render


def _score(pipeline="P01", actual="Name: Delta; Revenue: 17; Profit: 5"):
    expected = compile_markdown("Name: Delta; Revenue: 17; Profit: 5", sample_id="toy")
    candidate = read_candidate_markdown(actual, sample_id="toy", pipeline=pipeline)
    result = grade_layers(expected, candidate)
    result["scoring_software_id"] = "invented-frozen-software"
    return result


def _index(tmp_path):
    groups = {f"P{i:02}": [_score(f"P{i:02}")] for i in range(1, 9)}
    for pipeline in ("P07", "P08"):
        for label in ("baseline", "current"):
            groups[pipeline + "-" + label] = [_score(pipeline)]
    validation = {"status": "passed", "known_reader_defects": [],
                  **{stage: {"status": "passed", "evidence": ["invented test evidence"]} for stage in VALIDATION_STAGES}}
    records = []
    for group, scores in groups.items():
        path = group + ".json"
        write_json(tmp_path / path, scores[0])
        records.append({"group": group, "sample_id": "toy", "path": path})
    index = {"state": "completed", "protocol": PROTOCOL, "expected_comparison_complete": True,
             "software": {"software_id": "invented-frozen-software"}, "validation": validation,
             "groups": list(groups), "records": records,
             "coverage": [{"sample_id": "toy", "layers": {layer: {"denominator": groups["P01"][0]["layers"][layer]["denominator"]}
                                                                    for layer in ("T", "L", "B")}}],
             "summary": {group: summarize_layers(scores) for group, scores in groups.items()}}
    index["paired"] = {}
    for pipeline in ("P07", "P08"):
        index["paired"][pipeline] = {}
        for name, before, after in (("native_to_baseline", pipeline, pipeline + "-baseline"),
                                    ("native_to_current", pipeline, pipeline + "-current"),
                                    ("baseline_to_current", pipeline + "-baseline", pipeline + "-current")):
            pair = paired_layers(groups[before], groups[after])
            index["paired"][pipeline][name] = {
                layer: {"new_correct": row["new_correct"], "lost_correct": row["lost_correct"],
                        "remaining_incorrect": row["remaining_defects"], "required_units": row["after"]["denominator"]}
                for layer, row in pair["layers"].items()
            }
    path = tmp_path / "index.json"
    write_json(path, index)
    return path


def test_three_layers_render_from_decisions_with_separate_pairs_and_full_text_diagnostics(tmp_path):
    path = _index(tmp_path)
    output = tmp_path / "report"
    result = render(path, output)
    assert result == [str(output / "report.md")]
    report = (output / "report.md").read_text()
    assert "(T+L+B)/3" in report
    assert report.index("T比较全部授权文字") < report.index("## P01–P08 原生输出")
    assert "全范围S/D/I" in report and "P07/P08 保存正文配对" in report
    assert "value_and_labels_correct" not in report
    assert len(read_json(output / "data/results.json")) == 12
    pairs = read_json(output / "data/paired.json")
    assert set(pairs) == {"P07", "P08"}
    assert set(pairs["P07"]) == {"native_to_baseline", "native_to_current", "baseline_to_current"}
    assert pairs["P07"]["baseline_to_current"]["layers"]["B"]["lost_correct"] == 0
    assert "gains" not in pairs["P07"]["baseline_to_current"]["layers"]["B"]


def test_blocked_result_cannot_overwrite_the_maintained_report(tmp_path):
    path = _index(tmp_path)
    output = tmp_path / "report"
    output.mkdir()
    (output / "report.md").write_text("keep the paused report\n")
    index = read_json(path)
    index["state"] = "blocked"
    write_json(path, index)
    with pytest.raises(ValueError, match="complete validated"):
        render(path, output)
    assert (output / "report.md").read_text() == "keep the paused report\n"
    assert not (output / "data").exists()


@pytest.mark.parametrize("field", ["edits", "strict_edits"])
def test_report_rejects_tampered_text_edit_counts(field):
    score = _score()
    row = next(row for row in score["outcomes"] if row["layer"] == "T")
    row[field]["S"] = 1
    with pytest.raises(ValueError, match="S/D/I"):
        validate_evidence(score)


def test_text_aggregate_cannot_hide_an_omitted_requirement_even_if_formula_matches():
    score = _score()
    score["layers"]["T"]["denominator"] += 1
    score["layers"]["T"]["numerator"] += 1
    with pytest.raises(ValueError, match="full-range aggregate"):
        validate_evidence(score)


def test_accepted_unique_business_hit_must_keep_its_identity_check():
    score = _score()
    row = next(row for row in score["outcomes"] if row["layer"] == "B" and row["expected"]["attribute"] == "Profit")
    hit = row["retrieval"]["candidates"][0]
    hit["identity"]["subject"]["actual"] = "Other entity"
    with pytest.raises(ValueError, match="inconsistent identity"):
        validate_evidence(score)


def test_relation_pass_must_match_the_actual_endpoint():
    score = _score()
    row = next(row for row in score["outcomes"] if row["layer"] == "L")
    row["actual"] = deepcopy(row["actual"])
    row["actual"]["left"]["attribute"] = "Other metric"
    with pytest.raises(ValueError, match="different endpoints"):
        validate_evidence(score)


def test_one_text_occurrence_cannot_be_reused_for_repeated_requirements():
    score = _score()
    rows = [row for row in score["outcomes"] if row["layer"] == "T"]
    rows[1]["actual"] = deepcopy(rows[1]["actual"])
    rows[1]["actual"]["id"] = rows[0]["actual"]["id"]
    with pytest.raises(ValueError, match="one candidate text occurrence"):
        validate_evidence(score)


@pytest.mark.parametrize("mutation", ["software", "protocol", "denominator", "validation", "missing_group", "paired"])
def test_frozen_complete_report_contract_is_checked(tmp_path, mutation):
    path = _index(tmp_path)
    index = read_json(path)
    if mutation in {"software", "protocol"}:
        score = read_json(tmp_path / "P01.json")
        score["scoring_software_id" if mutation == "software" else "protocol"] = "different"
        write_json(tmp_path / "P01.json", score)
    elif mutation == "denominator":
        index["coverage"][0]["layers"]["B"]["denominator"] += 1
    elif mutation == "validation":
        index["validation"]["saved_output_diagnosis"]["status"] = "blocked"
    elif mutation == "paired":
        index["paired"]["P07"]["baseline_to_current"]["B"]["lost_correct"] = 1
    else:
        index["records"] = index["records"][:-1]
    write_json(path, index)
    with pytest.raises(ValueError):
        load_complete(path)


def test_full_text_diagnostics_keep_missing_characters_and_strict_edits():
    score = _score(actual="Name: Delta; Revenue: 18")
    result = text_layer_diagnostics([score])
    assert result["required_units"] == 6
    assert result["located_units"] < result["required_units"]
    assert result["required_characters"] == score["layers"]["T"]["denominator"]
    assert result["edits"]["D"] > 0
    assert result["strict_edits"]["D"] > 0
