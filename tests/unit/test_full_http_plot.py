"""Chart guards use synthetic observations, never model calls or scored PDFs."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

import pytest

from benchmark.tools import plot_full_http as chart


def write(root: Path, name: str, value: dict) -> dict:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return {"path": name, "sha256": chart.digest(path), "bytes": path.stat().st_size}


def count(total: int, *, unknown: int = 0) -> dict:
    return {
        "pass": total - unknown,
        "total": total,
        "unknown": unknown,
        "gold_fingerprint": "a" * 64,
        "reader_fingerprint": "b" * 64,
    }


def fixture(root: Path) -> dict:
    pages = [4, 27, 6, 3, 15, 36, 134, 28, 119, 130]
    pdf_ids, office = [f"pdf-{n}" for n in range(10)], "office"
    (root / "documents.jsonl").write_text(
        "\n".join(
            json.dumps({"id": name, "page_count": n})
            for name, n in zip(pdf_ids + [office], pages + [2], strict=True)
        )
    )
    write(
        root,
        "dataset.json",
        {
            "documents": "documents.jsonl",
            "cohorts": [
                {"id": "regression-502", "document_ids": pdf_ids},
                {"id": "regression-office2", "document_ids": [office]},
            ],
        },
    )
    rows = []
    for role in ("docling", "primary", "header"):
        historical = role == "docling"
        record = {
            "schema": "moparse-evidence/1",
            "id": role,
            "method_id": role,
            "cohort_id": "regression-502" if historical else "regression-504",
            "origin": "historical_reuse" if historical else "fresh_HTTP",
            "output_stage": "public-HTTP-GFM",
            "qualification": {"full_HTTP": True},
            "quality": {key: count(total) for key, total in chart.METRICS.items()},
            "performance": {
                "seconds": 600 if historical else 999999,
                "power_limit_W": 180 if historical else 220,
                "own_GPU_peak_MiB": None,
                "shared_GPU_energy_Wh": None,
            },
            "provenance": [],
        }
        plan = {"id": role, "label": role, "evidence": role + ".json"}
        if historical:
            proof = {
                "schema": "selected-pipeline-performance-summary/1",
                "status": "complete",
                "expected_pages": 502,
                "finished_capture_pages": 502,
                "expected_documents": 10,
                "timing": {
                    "submit_to_saved_MD_s": {
                        "total_s": 600,
                        "known_case_count": 10,
                        "unknown_case_count": 0,
                    }
                },
            }
            record["provenance"].append(write(root, "historical-timing.json", proof))
            for name, key, total, cohort in [
                ("body", "content14_pdf40", 40, "regression-502"),
                ("office", "office_source6", 6, "regression-office2"),
            ]:
                supplement = {**record, "quality": {key: count(total)}, "cohort_id": cohort}
                plan["content_evidence" if name == "body" else "office_evidence"] = name + ".json"
                write(root, name + ".json", supplement)
        else:
            checks = [
                {
                    "document_id": pdf_ids[n % 10] if n < 40 else office,
                    "page": 1,
                    "check": str(n),
                    "status": "pass",
                }
                for n in range(46)
            ]
            record["quality"]["fixed46"] = count(46)
            record["provenance"].append(
                write(
                    root,
                    role + "-content.json",
                    {"schema": "moparse-content14-evaluation/1", "fixed_checks": checks},
                )
            )
            cases = [
                {
                    "id": name,
                    "page_count": n,
                    "status": "completed",
                    "submit_to_saved_MD_seconds": 10,
                    "full_capture_seconds": 99999,
                }
                for name, n in zip(pdf_ids, pages, strict=True)
            ]
            cases.append(
                {
                    "id": office,
                    "page_count": 2,
                    "status": "completed",
                    "submit_to_saved_MD_seconds": 900,
                }
            )
            record["provenance"].append(
                write(
                    root,
                    role + "-run.json",
                    {
                        "schema": "moparse-http-run/1",
                        "method_id": role,
                        "cohort_id": "regression-504",
                        "request_policy": {
                            "scan_policy": "auto",
                            "unit_range": "omitted",
                            "full_document": True,
                        },
                        "status": "completed",
                        "cases": cases,
                    },
                )
            )
        write(root, role + ".json", record)
        rows.append(plan)
    return {"schema": "moparse-full-http-chart-plan/1", "dataset": "dataset.json", "rows": rows}


def revise(root: Path, role: str, path: str, change) -> None:
    record = chart.read(root / (role + ".json"))
    source = chart.read(root / path)
    change(source)
    ref = write(root, path, source)
    record["provenance"] = [ref if x["path"] == path else x for x in record["provenance"]]
    write(root, role + ".json", record)


def test_502_timing_excludes_office_and_asset_totals(tmp_path):
    data = chart.collect(fixture(tmp_path), tmp_path)
    primary = data["rows"][1]
    assert primary["timing"]["seconds"] == 100  # not 1000, 999999 or asset capture
    assert primary["timing"]["excluded_case_ids"] == ["office"]
    assert primary["quality"]["content40"]["total"] == 40
    assert primary["quality"]["office6"]["total"] == 6
    assert data["overlapping_denominators_never_summed"] is True


@pytest.mark.parametrize("key,total", [("core209", 210), ("content14_pdf40", 46)])
def test_wrong_or_office_inclusive_denominators_are_rejected(tmp_path, key, total):
    config = fixture(tmp_path)
    name = "docling.json" if key == "core209" else "body.json"
    record = chart.read(tmp_path / name)
    record["quality"][key]["total"] = total
    write(tmp_path, name, record)
    with pytest.raises(ValueError, match="Fixed denominator"):
        chart.collect(config, tmp_path)


@pytest.mark.parametrize("key", ["reader_fingerprint", "gold_fingerprint"])
def test_incompatible_judgments_cannot_be_grouped(tmp_path, key):
    config = fixture(tmp_path)
    record = chart.read(tmp_path / "header.json")
    record["quality"]["column_meaning402"][key] = "f" * 64
    write(tmp_path, "header.json", record)
    with pytest.raises(ValueError, match="plotted separately"):
        chart.collect(config, tmp_path)


@pytest.mark.parametrize("fault", ["missing_time", "partial_pages", "partial_request"])
def test_incomplete_timing_never_falls_back_to_asset_inclusive_performance(tmp_path, fault):
    config = fixture(tmp_path)

    def change(run):
        if fault == "missing_time":
            del run["cases"][0]["submit_to_saved_MD_seconds"]
        elif fault == "partial_pages":
            run["cases"][0]["page_count"] = 1
        else:
            run["request_policy"]["unit_range"] = "1-2"

    revise(tmp_path, "primary", "primary-run.json", change)
    with pytest.raises(ValueError):
        chart.collect(config, tmp_path)


def test_unknown_content_and_missing_resources_remain_explicit(tmp_path):
    config = fixture(tmp_path)
    revise(
        tmp_path,
        "primary",
        "primary-content.json",
        lambda data: data["fixed_checks"][0].update(status="unknown"),
    )
    record = chart.read(tmp_path / "primary.json")
    record["quality"]["fixed46"] = count(46, unknown=1)
    write(tmp_path, "primary.json", record)
    data = chart.collect(config, tmp_path)
    assert data["rows"][1]["quality"]["content40"]["unknown"] == 1
    assert data["rows"][1]["resources"]["own_GPU_peak_MiB"] is None
    svg = chart.render(data)
    ElementTree.fromstring(svg)
    assert "未知 1" in svg and 'fill="url(#unknown)"' in svg
    assert "未测" in svg and "0 MiB" not in svg
    assert "180 W" in svg and "220 W" in svg


def test_modified_hashed_provenance_is_rejected(tmp_path):
    config = fixture(tmp_path)
    path = tmp_path / "primary-run.json"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        chart.collect(config, tmp_path)


def test_missing_final_evidence_writes_no_chart(tmp_path):
    config = fixture(tmp_path)
    (tmp_path / "header.json").unlink()
    with pytest.raises(FileNotFoundError):
        chart.collect(config, tmp_path)
    assert not (tmp_path / "full-http-comparison.svg").exists()


def test_fresh_office_baseline_keeps_its_own_origin_and_power(tmp_path):
    config = fixture(tmp_path)
    office = chart.read(tmp_path / "office.json")
    office["origin"] = "fresh_HTTP"
    office["performance"]["power_limit_W"] = 220
    write(tmp_path, "office.json", office)
    data = chart.collect(config, tmp_path)
    old = data["rows"][0]
    assert old["origin"] == "historical_reuse" and old["power_limit_W"] == 180
    assert old["quality"]["office6"]["source_origin"] == "fresh_HTTP"
    assert old["quality"]["office6"]["source_power_limit_W"] == 220
