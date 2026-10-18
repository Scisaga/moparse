from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from benchmark import moparse_benchmark as bench
from benchmark.scorers.html_line_breaks import html_breaks_as_spaces


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_fixed_dataset_source_and_annotation_locks():
    result = bench.validate_dataset(bench.DEFAULT_DATASET)
    assert result["valid"], result["errors"]
    assert result["documents"] >= 11
    data, documents = bench.load_dataset(bench.DEFAULT_DATASET)
    old = next(cohort for cohort in data["cohorts"] if cohort["id"] == "regression-502")
    assert old["pages"] == 502
    assert len(old["document_ids"]) == 10
    assert all(
        item["split"] != "holdout" for item in documents if item["exposure"] == "previously_used"
    )


def test_method_fingerprint_is_deterministic():
    record = bench.method("mineru-advanced-txt-vllm-c2-glm")
    assert record["recipe"]["routing"]["native"]["client_max_concurrency"] == 2
    assert record["fingerprint"] == bench.fingerprint(record["recipe"])
    assert bench.fingerprint({"a": 1, "b": 2}) == bench.fingerprint({"b": 2, "a": 1})


def test_historical_import_refuses_changed_artifact(tmp_path):
    source = tmp_path / "source.json"
    write_json(source, {"old": True})
    record = {
        "schema": "moparse-evidence/1",
        "id": "old-run",
        "method_id": "production-docling-glm",
        "cohort_id": "test",
        "origin": "historical_reuse",
        "fresh_model_inference": False,
        "output_stage": "public-GFM",
        "quality": {},
        "performance": {},
        "qualification": {},
        "provenance": [bench.artifact(source)],
    }
    old_hash = bench.digest(source)
    source.write_text("{}")
    assert bench.digest(source) != old_hash
    assert "changed" in bench.validate_evidence(record)[0]


def test_comparison_never_pools_different_power_or_denominators(tmp_path):
    base = {
        "schema": "moparse-evidence/1",
        "id": "run",
        "method_id": "production-docling-glm",
        "cohort_id": "fixed",
        "origin": "historical_reuse",
        "fresh_model_inference": False,
        "output_stage": "component-FULL",
        "qualification": {},
        "provenance": [],
        "quality": {
            "fixed46": {
                "pass": 45,
                "total": 46,
                "gold_fingerprint": "gold46",
                "reader_fingerprint": "reader",
            }
        },
        "performance": {
            "seconds": 10,
            "scope": "parse",
            "hardware_fingerprint": "GPU1",
            "power_limit_W": 180,
            "warmup": "warm",
        },
    }
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    write_json(first, base)
    other = json.loads(json.dumps(base))
    other["id"] = "run220"
    other["performance"]["power_limit_W"] = 220
    other["quality"] = {
        "extra4": {
            "pass": 4,
            "total": 4,
            "gold_fingerprint": "gold4",
            "reader_fingerprint": "reader",
        }
    }
    write_json(second, other)
    result = bench.compare([first, second])
    assert len(result["timing_groups"]) == 2
    assert len(result["quality_groups"]) == 2
    assert not result["rejected"]


def annotation(expected, *, kind="text"):
    return {
        "schema": "moparse-source-assertions/1",
        "id": "source-gold",
        "source_documents": [{"id": "doc", "sha256": "a" * 64}],
        "review": {"method": "source only", "model_outputs_seen": False},
        "checks": [
            {
                "id": "literal",
                "document_id": "doc",
                "page": 1,
                "kind": kind,
                "expected": expected,
                "source_evidence": {"physical_page": 1},
            }
        ],
    }


def test_missing_document_is_unknown_not_empty_pass(tmp_path):
    gold = tmp_path / "gold.json"
    write_json(gold, annotation("original content"))
    result = bench.score_assertions(tmp_path / "capture", gold, tmp_path / "scores")
    assert not result["passed"]
    assert result["counts"] == {"unknown": 1}


def test_annotation_comments_cannot_cover_missing_visible_text(tmp_path):
    capture = tmp_path / "capture"
    path = capture / "cases/doc/result.md"
    path.parent.mkdir(parents=True)
    path.write_text("<!-- page: 1 -->\n<!-- original content -->\nVisible words")
    gold = tmp_path / "gold.json"
    write_json(gold, annotation("original content"))
    result = bench.score_assertions(capture, gold, tmp_path / "scores")
    assert not result["passed"]
    assert result["counts"] == {"fail": 1}


def test_order_assertion_handles_repeated_text_positions(tmp_path):
    capture = tmp_path / "capture"
    path = capture / "cases/doc/result.md"
    path.parent.mkdir(parents=True)
    path.write_text("<!-- page: 1 -->\nTotal\nOther\nTotal")
    gold = tmp_path / "gold.json"
    write_json(gold, annotation(["Total", "Other", "Total"], kind="ordered_text"))
    assert bench.score_assertions(capture, gold, tmp_path / "scores")["passed"]


def test_missing_table_structure_is_unknown(tmp_path):
    capture = tmp_path / "capture"
    path = capture / "cases/doc/result.md"
    path.parent.mkdir(parents=True)
    path.write_text("<!-- page: 1 -->\n| Label | Value |\n| --- | --- |\n| Original | 10 |")
    gold = tmp_path / "gold.json"
    check = annotation([["Label", "Value"], ["Original", "10"]], kind="table_grid")
    check["checks"][0]["selector"] = {"text": "Original"}
    write_json(gold, check)
    result = bench.score_assertions(capture, gold, tmp_path / "scores")
    assert not result["passed"]
    assert result["counts"] == {"unknown": 1}


def test_historical_records_do_not_claim_fresh_inference():
    for source in (bench.BENCH / "evidence").glob("historical-*.json"):
        record = bench.read(source)
        assert not bench.validate_evidence(record), source
        assert record["origin"] == "historical_reuse"
        assert record["fresh_model_inference"] is False


def test_all_registered_evidence_has_valid_schema_and_artifact_identity():
    for source in (bench.BENCH / "evidence").glob("*.json"):
        assert not bench.validate_evidence(bench.read(source)), source


def test_metadata_observations_do_not_add_quality_or_timing():
    sources = sorted((bench.BENCH / "evidence").glob("*.json"))
    identity_ids = set()
    for source in sources:
        record = bench.read(source)
        if record["qualification"].get("source_identity_only") or record["qualification"].get(
            "observation_only"
        ):
            identity_ids.add(record["id"])
            assert record["quality"] == {}, source
            assert record["performance"] == {}, source
            assert record["fresh_model_inference"] is False, source
    assert identity_ids
    result = bench.compare(sources)
    for group in ("quality_groups", "timing_groups"):
        assert all(
            row["evidence_id"] not in identity_ids
            for rows in result[group].values()
            for row in rows
        )


def test_reuse_does_not_overwrite_prior_evidence(tmp_path):
    source = bench.BENCH / "evidence/historical-20261018-concurrency-2.json"
    target = tmp_path / "imported.json"
    bench.import_evidence(source, target)
    with pytest.raises(FileExistsError):
        bench.import_evidence(source, target)


def test_async_http202_polls_and_downloads_real_markdown(tmp_path):
    requested = []

    def handler(request):
        requested.append(str(request.url.path))
        if request.url.path.endswith("/result"):
            return httpx.Response(
                200,
                text="<!-- page: 1 -->\nOriginal text",
                headers={"content-type": "text/markdown"},
            )
        return httpx.Response(200, json={"id": "job_test", "status": "completed"})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        initial = httpx.Response(202, json={"id": "job_test", "status": "queued"})
        entry = {}
        text, job = bench.capture_final_result(
            client, initial, tmp_path, entry, time.perf_counter(), 30, 0.01
        )
    assert requested == ["/v1/content/jobs/job_test", "/v1/content/jobs/job_test/result"]
    assert text.endswith("Original text")
    assert job["status"] == "completed"
    assert (tmp_path / "result.md").read_bytes() == (tmp_path / "persisted-result.md").read_bytes()
    assert entry["response_and_persisted_MD_equal"] is True


def test_sync_http200_requires_persisted_result_byte_equality(tmp_path):
    def handler(request):
        if request.url.path.endswith("/result"):
            return httpx.Response(200, text="different persisted content")
        return httpx.Response(200, json={"id": "job_test", "status": "completed"})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        initial = httpx.Response(
            200, text="received Markdown", headers={"x-content-id": "job_test"}
        )
        with pytest.raises(ValueError, match="differs from persisted"):
            bench.capture_final_result(client, initial, tmp_path, {}, time.perf_counter(), 30, 0.01)
    assert (tmp_path / "result.md").read_text() == "received Markdown"
    assert (tmp_path / "persisted-result.md").read_text() == "different persisted content"


def test_capture_stops_polling_failed_job_without_treating_json_as_markdown(tmp_path):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": "job_test", "status": "failed"})
        ),
        base_url="http://test",
    ) as client:
        with pytest.raises(ValueError, match="terminated with status failed"):
            bench.capture_final_result(
                client,
                httpx.Response(202, json={"id": "job_test"}),
                tmp_path,
                {},
                time.perf_counter(),
                30,
                0.01,
            )
    assert not (tmp_path / "result.md").exists()


@pytest.mark.parametrize("tag", ["<br>", "<br/>", "<br />", "<BR/>"])
def test_html_break_decoding_preserves_word_and_numeric_separation(tag):
    assert html_breaks_as_spaces("Peak" + tag + "HRR") == "Peak HRR"
    assert html_breaks_as_spaces("123" + tag + "456") == "123 456"
    assert html_breaks_as_spaces("-0.61" + tag + "万元") == "-0.61 万元"


@pytest.mark.parametrize("literal", ["`A<br>B`", "``A<br/>B``", r"A\<br>B", "A&lt;br&gt;B"])
def test_html_break_decoding_preserves_literal_markup_and_code(literal):
    assert html_breaks_as_spaces(literal) == literal


@pytest.mark.parametrize(
    "expected,passed", [("Peak HRR", True), ("PeakHRR", False), ("Peak HRC", False)]
)
def test_public_text_assertion_reads_actual_html_line_break(tmp_path, expected, passed):
    capture = tmp_path / "capture"
    path = capture / "cases/doc/result.md"
    path.parent.mkdir(parents=True)
    path.write_text("<!-- page: 1 -->\nPeak<br/>HRR")
    gold = tmp_path / "gold.json"
    write_json(gold, annotation(expected))
    assert bench.score_assertions(capture, gold, tmp_path / "scores")["passed"] is passed


@pytest.mark.parametrize(
    "last_cell,passed", [("123 456", True), ("123456", False), ("123 457", False)]
)
def test_public_cell_line_break_never_joins_digits_or_changes_grid(tmp_path, last_cell, passed):
    capture = tmp_path / "capture"
    path = capture / "cases/doc/result.md"
    path.parent.mkdir(parents=True)
    metadata = {
        "version": 1,
        "table_id": "source-table",
        "source_pages": [1],
        "num_rows": 2,
        "num_cols": 2,
        "encoding": "anchor_and_blanks",
        "structure_valid": True,
        "header_rows": None,
        "spans": [],
    }
    path.write_text(
        "<!-- page: 1 -->\n<!-- table-fragment: source-table -->\n"
        + "<!-- table-structure: "
        + json.dumps(metadata)
        + " -->\n"
        + "| Label | Value |\n| --- | --- |\n| Original | 123<br>456 |"
    )
    gold = tmp_path / "gold.json"
    check = annotation([["Label", "Value"], ["Original", last_cell]], kind="table_grid")
    check["checks"][0]["selector"] = {"text": "Original"}
    write_json(gold, check)
    result = bench.score_assertions(capture, gold, tmp_path / "scores")
    assert result["passed"] is passed


def test_source_relocation_requires_frozen_registered_and_actual_hash_agreement(tmp_path):
    source = tmp_path / "private/doc.pdf"
    source.parent.mkdir()
    source.write_bytes(b"source bytes")
    sha = bench.digest(source)
    resolve, audit = bench.verified_source_resolver(
        [{"path": "/old/repo/private/doc.pdf", "sha256": sha}],
        [{"id": "doc", "source_path": "private/doc.pdf", "sha256": sha}],
        tmp_path,
    )
    assert resolve(Path("/old/repo/private/doc.pdf")) == source
    assert audit[0]["actual_sha256"] == sha
    source.write_bytes(b"changed source bytes")
    with pytest.raises(ValueError, match="Actual source bytes"):
        resolve(Path("/old/repo/private/doc.pdf"))


def test_source_relocation_rejects_same_filename_with_different_registered_identity(tmp_path):
    resolve, _ = bench.verified_source_resolver(
        [{"path": "/old/repo/doc.pdf", "sha256": "a" * 64}],
        [{"id": "doc", "source_path": "doc.pdf", "sha256": "b" * 64}],
        tmp_path,
    )
    with pytest.raises(ValueError, match="identit|identity"):
        resolve(Path("/old/repo/doc.pdf"))
