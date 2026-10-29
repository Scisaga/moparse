"""Synthetic-only figure checks; no corpus or recorded pipeline output is read."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from moparse_eval.report_figures import (
    _coverage,
    _perf,
    _quality,
    _relations,
    _resources,
    _rounds,
    render_figures,
)


def test_missing_resource_records_remain_na(synthetic_figures: tuple[Path, list[dict[str, Any]]]) -> None:
    import matplotlib.pyplot as plt

    report = {"runtime_evidence": {"P01": {
        "worker_lifecycle_resources": None,
        "inference_lifecycle_resources": {"record": None},
    }}}
    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"]}):
        figure, data = _resources(report, plt, ["P01"])
    try:
        assert all(rows[0]["gib"] is None for rows in data.values())
    finally:
        plt.close(figure)


def _synthetic_report() -> dict[str, Any]:
    groups = []
    for pipeline in ("P01", "P02"):
        quality = {
            "micro": {
                "unit_presence": {"recall": 0.8, "target_units": 10},
                "text": {"strict": {"cer": 1.6, "reference_chars": 120}},
                "text_aligned": {"strict": {"cer": 1.4, "reference_chars": 100}},
                "table_records": {
                    "target_fields": 10, "compared_fields": 2, "target_missing_fields": 1,
                    "unresolved_fields": 7, "correct_fields": 2, "strict_correct_fields": 1,
                    "field_target_correctness": {"value": 0.2, "numerator": 2, "denominator": 10},
                    "field_compared_accuracy": {"value": 1.0, "numerator": 2, "denominator": 2},
                    "field_strict_accuracy": {"value": 0.5, "numerator": 1, "denominator": 2},
                    "field_coverage": {"value": 0.2, "numerator": 2, "denominator": 10},
                },
                "relations": {"recall": None, "target_units": 10, "by_type": {
                    "before": {"denominator": 10, "value": 0.4, "confirmed_correct": 4,
                               "confirmed_incorrect": 1, "native_not_provided": 2,
                               "endpoint_unresolved": 2, "unassessable": 1},
                    "heading_of": {"denominator": 10, "value": 0, "confirmed_correct": 0,
                                   "confirmed_incorrect": 0, "native_not_provided": 8,
                                   "endpoint_unresolved": 1, "unassessable": 1},
                }},
            },
            "macro_by_document": {"text.strict.cer": {"value": 1.1, "available_groups": 2, "total_groups": 2}},
            "macro_by_family": {"text.strict.cer": {"value": 0.9, "available_groups": 1, "total_groups": 1}},
            "coverage": {"scored_units": 10, "localization_only_units": 2,
                         "localized_units": 8, "localized_anchors": 1,
                         "ambiguous_units": 1, "unresolved_units": 1, "not_localized_units": 1},
        }
        if pipeline == "P02":
            quality["micro"]["table_records"] = {}
            quality["micro"]["relations"] = {"recall": 0, "target_units": 10}
        groups.append({"pipeline": pipeline, "suite": "quality800", "quality": quality,
                       "performance": {"rounds": [{"repetition": "1", "attempted_input_pages": 800,
                                                   "processing_seconds_including_failures": 120}]}})
        groups.append({"pipeline": pipeline, "suite": "perf80", "performance": {"rounds": [
            {"repetition": str(index + 1), "attempted_input_pages": 80,
             "processing_seconds_including_failures": value}
            for index, value in enumerate((20, 35, 23))]}})
    return {"groups": groups, "score_index": "artifacts/scores/synthetic/index.json",
            "quality_slices": [{"pipeline": pipeline, "suite": "quality800", "scope": "tag",
                                "scope_key": "data-table", "samples": 2, "documents": 1,
                                "strict_cer": 1.4, "text_reference_chars": 100,
                                "table_field_target_correctness": None, "table_field_targets": 0}
                               for pipeline in ("P01", "P02")],
            "runtime_evidence": {"P01": {
                "worker_lifecycle_resources": {"path": "artifacts/P01/worker-resources.json", "record": {
                    "observed_shared_host_memory_peak_bytes": 2 * 1024 ** 3,
                    "sampling_completeness": {"status": "partial"}}},
                "inference_lifecycle_resources": {"path": "artifacts/P01/inference/resources.json", "record": {
                    "observed_shared_host_memory_peak_bytes": 3 * 1024 ** 3,
                    "observed_owned_gpu_peak_memory_mib": 1024,
                    "observed_gpu1_peak_memory_mib": 6144}}}}}


@pytest.fixture(scope="module")
def synthetic_figures(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[dict[str, Any]]]:
    report = _synthetic_report()
    original = copy.deepcopy(report)
    directory = tmp_path_factory.mktemp("synthetic-report") / "figures"
    entries = render_figures(report, directory)
    assert report == original
    return directory, entries


def test_export_formats_index_and_traceability(synthetic_figures: tuple[Path, list[dict[str, Any]]]) -> None:
    directory, entries = synthetic_figures
    assert len(entries) == 10
    for entry in entries:
        assert entry["caption"]
        assert entry["source_paths"][0] == "summary.json"
        assert entry["data"]
        for extension in ("png", "svg", "pdf"):
            assert entry[extension] == f"figures/{entry['id']}.{extension}"
            assert (directory / Path(entry[extension]).name).is_file()
    index = json.loads((directory / "index.json").read_text())
    assert index["figures"] == entries
    assert index["source"] == "existing_aggregate_report_only"


def test_missing_values_are_na_and_cer_can_exceed_one(synthetic_figures: tuple[Path, list[dict[str, Any]]]) -> None:
    _, entries = synthetic_figures
    quality = next(entry for entry in entries if entry["id"] == "quality")
    assert quality["data"]["aligned_cer"]["rows"][0]["value"] == 1.4
    assert "relation_recall" not in quality["data"]
    assert quality["data"]["table_target_correctness"]["rows"][1]["value"] is None
    resources = next(entry for entry in entries if entry["id"] == "resources")
    assert resources["data"]["worker_host"][0]["gib"] == 2
    assert resources["data"]["inference_host"][0]["gib"] == 3
    assert resources["data"]["owned_gpu_memory"][0]["gib"] == 1
    assert resources["data"]["owned_gpu_memory"][0]["field"] == "observed_owned_gpu_peak_memory_mib"
    assert resources["data"]["owned_gpu_memory"][1]["gib"] is None
    assert len(resources["source_paths"]) == 4


def test_relations_preserve_unknown_types_and_target_denominators(
    synthetic_figures: tuple[Path, list[dict[str, Any]]],
) -> None:
    _, entries = synthetic_figures
    relations = next(entry for entry in entries if entry["id"] == "relations")
    assert set(relations["data"]) == {"before"}
    before = relations["data"]["before"]["rows"][0]
    assert before["available"] is True
    assert before["denominator"] == 10
    assert before["states"] == {"confirmed_correct": 4, "confirmed_incorrect": 1,
                                "native_not_provided": 2, "endpoint_unresolved": 2,
                                "unassessable": 1}
    legacy = relations["data"]["before"]["rows"][1]
    assert legacy["available"] is False
    assert legacy["value"] is None
    assert all(value is None for value in legacy["states"].values())


def test_table_panels_use_new_content_equivalence_and_closed_field_states(
    synthetic_figures: tuple[Path, list[dict[str, Any]]],
) -> None:
    directory, entries = synthetic_figures
    table = next(entry for entry in entries if entry["id"] == "table-coverage")
    assert set(table["data"]) == {"field_target_correctness", "field_compared_accuracy", "field_states"}
    assert table["data"]["field_target_correctness"][0] == {
        "pipeline": "P01", "value": 0.2, "numerator": 2, "denominator": 10,
    }
    assert table["data"]["field_compared_accuracy"][0] == {
        "pipeline": "P01", "value": 1.0, "numerator": 2, "denominator": 2,
    }
    states = table["data"]["field_states"][0]
    assert states["available"] and states["denominator"] == 10 and states["compared_fields"] == 2
    assert states["states"] == {"correct_fields": 2, "compared_incorrect": 0,
                                "target_missing_fields": 1, "unresolved_fields": 7}
    assert table["data"]["field_compared_accuracy"][1]["value"] is None
    assert table["data"]["field_states"][1]["available"] is False
    assert "field_strict_accuracy" not in table["data"]
    assert "目标格未取到值" in table["caption"]
    relations_svg = (directory / "relations.svg").read_text()
    assert "heading_of" not in relations_svg
    assert "阅读顺序" in relations_svg



def test_quality_has_four_dimensions_and_unclosed_relation_rows_are_pending():
    import matplotlib.pyplot as plt

    report = _synthetic_report()
    report["groups"][0]["quality"]["micro"]["relations"]["by_type"]["before"]["unassessable"] = 9
    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"]}):
        quality, data = _quality(report, plt, ["P01", "P02"])
        relations, relation_data = _relations(report, plt, ["P01", "P02"])
    try:
        assert len(quality.axes) == 4
        assert set(data) == {"content_recall", "aligned_cer", "table_target_correctness", "information_target_correctness"}
        assert relation_data["before"]["rows"][0]["available"] is False
        assert len(relations.axes[0].patches) == 0
        assert all("NA（复核中）" in text.get_text() for text in relations.axes[0].texts)
    finally:
        plt.close(quality)
        plt.close(relations)


def test_time_suites_and_actual_three_points_are_distinct(synthetic_figures: tuple[Path, list[dict[str, Any]]]) -> None:
    _, entries = synthetic_figures
    time = next(entry for entry in entries if entry["id"] == "quality-time")
    assert time["data"]["rows"][0]["rounds"][0]["processing_seconds"] == 120
    perf = next(entry for entry in entries if entry["id"] == "perf-repeat")
    assert perf["data"]["rows"][0]["median_seconds"] == 23
    assert [row["processing_seconds"] for row in perf["data"]["rows"][0]["rounds"]] == [20, 35, 23]
    tradeoff = next(entry for entry in entries if entry["id"] == "tradeoff")
    assert tradeoff["data"]["rows"][0]["processing_seconds"] == 120
    assert tradeoff["data"]["time_suite"] == tradeoff["data"]["quality_suite"] == "quality800"


def test_perf_labels_clear_all_rounds_and_stay_inside_the_axis(
    synthetic_figures: tuple[Path, list[dict[str, Any]]],
) -> None:
    import matplotlib.pyplot as plt

    report = _synthetic_report()
    rounds = report["groups"][1]["performance"]["rounds"]
    for row, seconds in zip(rounds, (120, 900, 180), strict=True):
        row["processing_seconds_including_failures"] = seconds
    original = copy.deepcopy(report)
    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"]}):
        figure, data = _perf(report, plt, ["P01", "P02"])
    try:
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        axis = figure.axes[0]
        for index, (row, label) in enumerate(zip(data["rows"], axis.texts, strict=True)):
            largest = max(item["processing_seconds"] for item in row["rounds"]) / 60
            last_point_x = axis.transData.transform((largest, index))[0]
            bounds = label.get_window_extent(renderer)
            assert bounds.x0 > last_point_x
            assert bounds.x1 <= axis.get_window_extent(renderer).x1
        assert axis.get_xlim() == pytest.approx((0, 15 * 1.28))
        assert data["rows"][0]["median_seconds"] == 180
        assert report == original
    finally:
        plt.close(figure)


def test_coverage_counts_include_anchor_in_both_parts(synthetic_figures: tuple[Path, list[dict[str, Any]]]) -> None:
    _, entries = synthetic_figures
    coverage = next(entry for entry in entries if entry["id"] == "coverage")
    row = coverage["data"]["rows"][0]
    assert row["denominator"] == 12
    assert row["closed"] is True
    assert sum(row["states"].values()) == 12
    assert row["states"]["唯一定位（含锚点）"] == 9


def test_unclosed_coverage_stays_na() -> None:
    import matplotlib.pyplot as plt

    report = _synthetic_report()
    report["groups"][0]["quality"]["coverage"]["ambiguous_units"] = 30
    with plt.rc_context({"font.family": ["DejaVu Sans", "Noto Sans CJK SC", "sans-serif"]}):
        figure, data = _coverage(report, plt, ["P01"])
    try:
        assert data["rows"][0]["closed"] is False
        assert any("NA" in text.get_text() for text in figure.axes[0].texts)
    finally:
        plt.close(figure)


def test_duplicate_groups_not_arbitrarily_selected() -> None:
    report = _synthetic_report()
    report["groups"].append(copy.deepcopy(report["groups"][0]))
    assert _rounds(report, "P01", "quality800") == []


def test_svg_uses_explicit_sans_serif_and_pdf_fonts_are_embedded(synthetic_figures: tuple[Path, list[dict[str, Any]]]) -> None:
    directory, _ = synthetic_figures
    svg = (directory / "quality.svg").read_text()
    assert "sans-serif" in svg
    assert "Noto Sans CJK SC" in svg
    assert "DejaVu Sans" in svg
    assert "NA" in svg
    import fitz

    with fitz.open(directory / "quality.pdf") as document:
        fonts = document.get_page_fonts(0, full=True)
        assert fonts
        names = []
        for font in fonts:
            name, extension, _, data = document.extract_font(font[0])
            names.append(name)
            assert extension in {"ttf", "otf", "cff"}
            assert data
        assert any("NotoSansCJK" in name for name in names)
        assert any("DejaVuSans" in name for name in names)
