#!/usr/bin/env python3
"""Import the fixed, previously inspected corpus without changing historical evidence.

This one-time importer is deliberately explicit about source files and scopes.
It does not infer gold from parser outputs. Historical reports supply check IDs
and observed scores only; expected content comes from source-only references.
"""

from __future__ import annotations

import json
import shutil
import statistics
from pathlib import Path

from benchmark.moparse_benchmark import (
    BENCH,
    CONTENT,
    HISTORY,
    ROOT,
    artifact,
    digest,
    fingerprint,
    read,
    save,
)

DATA = BENCH / "datasets/moparse-v1"


def write(path: Path, value):
    save(path, value, overwrite=True)


def registry():
    native = {
        "package": "docling",
        "version": "2.139.0",
        "table_model": "TableFormer V1 Accurate",
        "matching": False,
        "pdf_backend": "PyPdfium",
        "OCR": False,
        "device": "CPU",
    }
    glm = {
        "model": "GLM-OCR",
        "model_revision": "recorded per deployed image; not inferred from model name",
        "SDK_version": "0.1.5",
        "orientation_preprocess": True,
        "DPI": 200,
        "precision": "FP16",
        "device": "GPU1",
    }
    mineru = {
        "package": "mineru",
        "version": "4.0.12",
        "text_mode": "TXT",
        "model": "opendatalab/MinerU2.5-Pro-2605-1.2B",
        "revision": "08aaea840498d49ce16247b6263196cf02814885",
        "engine": "vllm",
        "vllm_version": "0.19.1",
        "precision": "FP16",
        "max_model_len": 8192,
        "KV_bytes": 134217728,
        "max_num_batched_tokens": 2048,
        "enforce_eager": True,
        "logits_processor": "mineru_vl_utils:MinerULogitsProcessor",
        "client_max_concurrency": 2,
        "max_num_seqs": 2,
        "sampling": "pinned official SDK defaults; temperature0/top_p0.01/top_k1; task-specific penalties",
    }
    recipes = [
        ("production-docling-glm", "Current deployed Docling + GLM", "baseline", native),
        (
            "mineru-advanced-txt-vllm-c2-glm",
            "Advanced + TXT + vLLM, concurrency 2 + GLM",
            "candidate",
            {**mineru, "tier": "advanced"},
        ),
        (
            "mineru-standard-txt-vllm-glm",
            "Standard + TXT + vLLM + GLM",
            "diagnostic",
            {**mineru, "tier": "standard", "client_max_concurrency": 1, "max_num_seqs": 1},
        ),
        (
            "mineru-visual-vllm-glm",
            "MinerU pure visual vLLM + GLM",
            "candidate",
            {
                **mineru,
                "text_mode": "visual",
                "tier": "official two_step_extract",
                "client_max_concurrency": 1,
                "max_num_seqs": 1,
            },
        ),
        (
            "mineru-visual-transformers-glm",
            "MinerU pure visual Transformers + GLM",
            "diagnostic",
            {
                **mineru,
                "engine": "transformers",
                "text_mode": "visual",
                "client_max_concurrency": 1,
                "max_num_seqs": 1,
            },
        ),
        ("glm-only", "Whole-page GLM + official orientation", "comparison", glm),
        (
            "archive-paddle15-glm",
            "Archived PaddleOCR-VL 1.5 + GLM",
            "archived",
            {"model": "PaddleOCR-VL", "version": "1.5", "orientation_preprocess": True, "DPI": 200},
        ),
        (
            "archive-paddle16-glm",
            "Archived PaddleOCR-VL 1.6 + GLM",
            "archived",
            {
                "model": "PaddleOCR-VL",
                "version": "1.6",
                "orientation_preprocess": False,
                "DPI": 200,
            },
        ),
        (
            "archive-docling2139-v1-true-default-glm",
            "Archived Docling2.139/V1/matching=True/default backend + GLM",
            "archived",
            {**native, "matching": True, "pdf_backend": "Docling default backend"},
        ),
    ]
    for concurrency in (1, 3, 4):
        recipes.append(
            (
                f"mineru-advanced-txt-vllm-c{concurrency}-glm",
                f"Advanced TXT concurrency {concurrency}",
                "diagnostic",
                {
                    **mineru,
                    "tier": "advanced",
                    "client_max_concurrency": concurrency,
                    "max_num_seqs": concurrency,
                },
            )
        )
    for version in ("2.119.0", "2.139.0"):
        for model in ("V1 Accurate", "V2"):
            for matching in (False, True):
                identifier = f"archive-docling-{version.replace('.', '')}-{model.split()[0].lower()}-matching-{str(matching).lower()}-glm"
                recipes.append(
                    (
                        identifier,
                        f"Archived Docling {version}/{model}/matching={matching}",
                        "archived",
                        {**native, "version": version, "table_model": model, "matching": matching},
                    )
                )
    for identifier, label, status, backend in recipes:
        recipe = {
            "routing": {
                "policy": "native text and embedded-image coverage, independent of model answers",
                "native": backend,
                "scan_mixed": glm,
            },
            "public_output": {
                "format": "faithful logical-table GFM",
                "table_source": True,
                "coordinates": False,
                "semantic_XML": False,
                "header_merge": "only complete source-backed header and column-meaning equivalence",
            },
            "adapter_version": "record actual Git SHA per run; component FULL output is a different stage",
        }
        destination = BENCH / "methods" / f"{identifier}.json"
        if destination.exists():
            # Runtime recipes evolve independently of importing old evidence.
            continue
        write(
            destination,
            {
                "schema": "moparse-method/1",
                "id": identifier,
                "label": label,
                "status": status,
                "recipe": recipe,
                "fingerprint": fingerprint(recipe),
                "deployment_gate": "Full HTTP/public GFM and source annotations must pass; component runs alone do not qualify",
                "reuse": {
                    "functional": "exact source/input/weights/settings and output-stage hashes required",
                    "timing": "same cohort/hardware/power/time scope/warmup; never sum component work as end-to-end latency",
                },
            },
        )


def dataset():
    DATA.mkdir(parents=True, exist_ok=True)
    source = read(HISTORY / "input-manifest.json")
    rows = []
    for document in source["documents"]:
        identifier = Path(document["path"]).stem
        rows.append(
            {
                "schema": "moparse-document/1",
                "id": identifier,
                "source_path": document["path"],
                "sha256": document["sha256"],
                "bytes": (ROOT / document["path"]).stat().st_size,
                "page_count": document["page_count"],
                "media_type": "application/pdf",
                "split": "regression",
                "exposure": "previously_used",
                "leakage_group": "original-" + identifier,
                "template_family": "Chinese listed-company reports; cross-document family review pending",
                "source_distribution": "local-only; redistribution rights not established",
                "route_counts": dict(
                    __import__("collections").Counter(page["route"] for page in document["pages"])
                ),
                "derivatives": "all crops/rendered pages retain this leakage_group",
            }
        )
    office = CONTENT / "sources/1206337604"
    rows.append(
        {
            "schema": "moparse-document/1",
            "id": "1206337604",
            "source_path": str((office / "source-converted.pdf").relative_to(ROOT)),
            "sha256": digest(office / "source-converted.pdf"),
            "bytes": (office / "source-converted.pdf").stat().st_size,
            "page_count": 2,
            "media_type": "application/pdf",
            "split": "regression",
            "exposure": "previously_used",
            "leakage_group": "office-1206337604",
            "template_family": "investor relation activity record",
            "source_distribution": "local-only; redistribution rights not established",
            "derived_from": "1206337604-docx",
            "parent_source": artifact(office / "source-original.docx"),
            "conversion_provenance": artifact(office / "input-recovery.json"),
            "route_counts": {"native": 2},
            "derivatives": "DOCX and derived PDF/pages are one leakage group",
        }
    )
    (DATA / "documents.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    )
    originals = [
        (ROOT / "pdf_sample/gold/table_fact_gold_v1.json", "core209-source-gold.json"),
        (
            HISTORY / "scoring/supplemental/source-only-tables.json",
            "supplement402-source-gold.json",
        ),
        (HISTORY / "scoring/full-source-tables.json", "full-selected-source-tables.json"),
        (HISTORY / "scoring/same-header-continuation-source.json", "same-header-source-gold.json"),
        (HISTORY / "scoring/critical-shareholder-source.json", "shareholder-source-gold.json"),
        (CONTENT / "source-reference.json", "content14-source-reference.json"),
        (CONTENT / "source-reference-p62.json", "extra-p62-source-reference.json"),
    ]
    annotations = DATA / "annotations"
    annotations.mkdir(exist_ok=True)
    provenance = []
    for original, name in originals:
        target = annotations / name
        shutil.copyfile(original, target)
        provenance.append(
            {
                "copy": name,
                "source": artifact(original),
                "copy_sha256": digest(target),
                "source_only": True,
                "unchanged": True,
            }
        )
    write(
        annotations / "provenance.json",
        {
            "schema": "moparse-annotation-provenance/1",
            "imports": provenance,
            "review": "Existing original-PDF visual/character references; provisional single reviewer, not double-annotated",
            "model_outputs_are_not_gold": True,
        },
    )
    evaluation = read(CONTENT / "model-evaluation/official-native-advanced-source-evaluation.json")
    fixed = [
        {
            "document_id": page["source"],
            "page": page["source_page"],
            "id": check["check"],
            "source_sha256": page["source_SHA256"],
        }
        for page in evaluation["views"]["FULL"]["pages"]
        for check in page["checks"]
    ]
    extra = [
        {"document_id": check["source"], "page": check["source_page"], "id": check["check"]}
        for check in evaluation["views"]["FULL"]["additional_four_source_observations"]
    ]
    write(
        annotations / "suites.json",
        {
            "schema": "moparse-suite-registry/1",
            "suites": [
                {
                    "id": "core209",
                    "total": 209,
                    "reference": "core209-source-gold.json",
                    "unit": "nonempty numeric source-column bindings",
                },
                {
                    "id": "supplement402",
                    "total": 402,
                    "reference": "supplement402-source-gold.json",
                    "unit": "source literal and unique row; complete header tracked separately",
                },
                {
                    "id": "content14-fixed46",
                    "total": len(fixed),
                    "checks": fixed,
                    "reference": "content14-source-reference.json",
                    "checker": artifact(CONTENT / "evaluate-mineru-source.py"),
                    "check_id_origin_only": artifact(
                        CONTENT / "model-evaluation/official-native-advanced-source-evaluation.json"
                    ),
                },
                {
                    "id": "additional4",
                    "total": len(extra),
                    "checks": extra,
                    "reference": "source-confirmed identity/state observations; independent extra denominator",
                    "checker": artifact(CONTENT / "evaluate-docling-component.py"),
                },
                {
                    "id": "extra-p62",
                    "grid_positions": 99,
                    "merged_spans": 9,
                    "reference": "extra-p62-source-reference.json",
                },
            ],
            "denominators": "Never sum 209,402,46,4,99 or their overlapping source pages into a global accuracy",
            "unlabelled_scope": "All other page content remains unscored, not implicitly correct",
        },
    )
    page_map = {
        "1206337604": [1, 2],
        "1225474739": [19, 40, 74, 131],
        "1225475375": [74, 87],
        "1225474139": [28, 30],
        "1225474693": [2, 3],
        "1225473526": [6, 7],
    }
    items = [{"path": "documents.jsonl", "sha256": digest(DATA / "documents.jsonl")}]
    items.extend(
        {"path": "annotations/" + path.name, "sha256": digest(path)}
        for path in sorted(annotations.glob("*.json"))
    )
    write(
        DATA / "dataset.json",
        {
            "schema": "moparse-dataset/1",
            "id": "moparse-v1",
            "version": "1.0.0",
            "documents": "documents.jsonl",
            "artifacts": items,
            "policy": {
                "originals": "Private local source paths; do not commit raw documents",
                "exposure": "All current sources previously used; no independent holdout claim",
                "split_unit": "original document and template family, including all derivatives",
                "gold": "Source-backed provisional single-reviewer annotations; frozen imported bytes",
                "routing": "Independent source properties; no gold/page-ID performance branching",
            },
            "cohorts": [
                {
                    "id": "regression-502",
                    "document_ids": [d["id"] for d in rows[:-1]],
                    "pages": 502,
                    "whole_documents": True,
                    "source_manifest": artifact(HISTORY / "input-manifest.json"),
                },
                {
                    "id": "regression-office2",
                    "document_ids": ["1206337604"],
                    "pages": 2,
                    "whole_documents": True,
                },
                {
                    "id": "content14",
                    "document_ids": list(page_map),
                    "source_pages": page_map,
                    "pages": 14,
                    "whole_documents": False,
                    "contained_in": ["regression-502", "regression-office2"],
                },
                {
                    "id": "extra-p62",
                    "document_ids": ["1225475375"],
                    "source_pages": {"1225475375": [62]},
                    "pages": 1,
                    "whole_documents": False,
                    "contained_in": ["regression-502"],
                },
            ],
            "holdout": {
                "status": "not_yet_acquired",
                "document_ids": [],
                "requirement": "New unseen documents with source review; never relabel exposed files",
            },
        },
    )


def metric(passed, total, gold, reader):
    return {
        "pass": int(passed),
        "total": int(total),
        "gold_fingerprint": gold,
        "reader_fingerprint": reader,
    }


def evidence_record(
    identifier, method_id, cohort, stage, provenance, quality, performance, **qualification
):
    write(
        BENCH / "evidence" / (identifier + ".json"),
        {
            "schema": "moparse-evidence/1",
            "id": identifier,
            "method_id": method_id,
            "cohort_id": cohort,
            "origin": "historical_reuse",
            "fresh_model_inference": False,
            "output_stage": stage,
            "provenance": [artifact(path) for path in provenance],
            "quality": quality,
            "performance": performance,
            "qualification": {
                "source_artifacts_hashed": True,
                "deployment_acceptance": False,
                "source_exposed": True,
                **qualification,
            },
            "observed_recipe_fingerprint": None,
            "recipe_limit": "Historical component settings/export stage are preserved; this is not a run of the newly registered whole pipeline",
        },
    )


def evidence():
    comp_path = CONTENT / "component-comparison.json"
    comp = read(comp_path)
    ids = {
        "docling": "production-docling-glm",
        "transformers": "mineru-visual-transformers-glm",
        "vllm": "mineru-visual-vllm-glm",
        "standard": "mineru-standard-txt-vllm-glm",
        "advanced": "mineru-advanced-txt-vllm-c1-glm",
    }
    labels = {
        "docling": "docling-component-source-evaluation.json",
        "transformers": "transformers-source-evaluation.json",
        "vllm": "vllm-source-evaluation.json",
        "standard": "official-native-standard-source-evaluation.json",
        "advanced": "official-native-advanced-source-evaluation.json",
    }
    gold = digest(CONTENT / "source-reference.json")
    reader = fingerprint(
        {
            "fixed": digest(CONTENT / "evaluate-mineru-source.py"),
            "extra": digest(CONTENT / "evaluate-docling-component.py"),
        }
    )
    for row in comp["configurations"]:
        identifier = row["id"]
        stage = (
            "component-public-GFM"
            if identifier == "docling"
            else "component-official-FULL"
            if identifier in {"standard", "advanced"}
            else "component-official-visual"
        )
        evidence_record(
            "historical-20261017-" + identifier,
            ids[identifier],
            "content14",
            stage,
            [
                comp_path,
                CONTENT / "model-evaluation" / labels[identifier],
                CONTENT / "source-reference.json",
            ],
            {
                "fixed46": metric(row["condition_pass"], 46, gold, reader),
                "additional4": metric(row["additional_pass"], 4, gold, reader),
            },
            {
                "seconds": row["component_seconds"],
                "scope": row["time_scope"],
                "power_limit_W": 180,
                "hardware_fingerprint": "RTX2080Ti22GiB/shared-GPU1/CPU4",
                "warmup": "initialization_excluded",
                "own_GPU_peak_MiB": None,
                "shared_GPU_energy_Wh": None,
            },
            full_HTTP=False,
            routing_GLM_not_measured_in_component=True,
        )
    concurrency = HISTORY / "followup/20261018/advanced-txt-concurrency"
    resource = read(concurrency / "resource-summary.json")
    quality = read(concurrency / "quality-summary-final.json")
    for level in resource["levels"]:
        c = level["concurrency"]
        rounds = [item for item in quality["rounds"] if item["label"].startswith(f"c{c}/")]
        assert len(rounds) == 3 and all(item["fixed"]["pass"] == 45 for item in rounds)
        # Preserve actual individual round samples in addition to the displayed median.
        performance = {
            "seconds": level["original_14_component_seconds_median"],
            "round_seconds": [
                r["cohorts"]["original_14"]["PDF_to_FULL_MD_component_seconds"]
                for r in level["rounds"]
            ],
            "scope": "original PDF selection/render/official parse/FULL Markdown; initialization and evidence export excluded",
            "power_limit_W": 220,
            "hardware_fingerprint": "RTX2080Ti22GiB/shared-GPU1/CPU4",
            "warmup": "first_cold_MM_cache_then_two_warm_MM_cache_rounds;model_initialization_excluded",
            "own_GPU_peak_MiB": max(
                r["cohorts"]["original_14"]["resources"]["owned_GPU_processes"][
                    "FB_MiB_sum_per_sample"
                ]["max"]
                for r in level["rounds"]
            ),
            "own_GPU_SM_mean_pct": statistics.median(
                r["cohorts"]["original_14"]["resources"]["owned_GPU_processes"][
                    "SM_percent_sum_per_sample"
                ]["mean"]
                for r in level["rounds"]
            ),
            "shared_GPU_energy_Wh": statistics.median(
                r["cohorts"]["original_14"]["resources"]["whole_GPU1_energy"]["Wh"]
                for r in level["rounds"]
            ),
            "shared_GPU_energy_scope": "whole GPU1, includes GLM/TTS; not candidate-exclusive",
        }
        evidence_record(
            f"historical-20261018-concurrency-{c}",
            f"mineru-advanced-txt-vllm-c{c}-glm",
            "content14",
            "component-official-FULL",
            [
                concurrency / "resource-summary.json",
                concurrency / "quality-summary-final.json",
                concurrency / "experiment-manifest.json",
            ],
            {"fixed46": metric(45, 46, gold, reader), "additional4": metric(4, 4, gold, reader)},
            performance,
            full_HTTP=False,
            page_output_byte_identical_across_12_rounds=True,
            p62="separate 99 positions/9 spans all pass; not included in fixed46",
        )
    run = CONTENT / "candidate-full10-http"
    source_score = run / "scoring/score-summary.json"
    scores, perf = (
        read(source_score)["public_structure_aware"],
        read(run / "performance-summary.json"),
    )
    supplemental = scores["supplements"]["supplement402"]["literal"]
    evidence_record(
        "historical-20261017-docling-full-http",
        "production-docling-glm",
        "regression-502",
        "public-HTTP-GFM",
        [source_score, run / "performance-summary.json"],
        {
            "core209": metric(
                scores["core_numeric"].get("pass", 0),
                209,
                digest(ROOT / "pdf_sample/gold/table_fact_gold_v1.json"),
                "frozen-public-reader-and-validated-structure-v1",
            ),
            "period209": metric(
                scores["core_period_pass"],
                209,
                digest(ROOT / "pdf_sample/gold/table_fact_gold_v1.json"),
                "frozen-public-reader-and-validated-structure-v1",
            ),
            "unique_row402": metric(
                supplemental["literal_and_unique_row_pass"],
                402,
                digest(HISTORY / "scoring/supplemental/source-only-tables.json"),
                "frozen-public-reader-and-validated-structure-v1",
            ),
            "column_meaning402": metric(
                supplemental["literal_row_and_complete_header_pass"],
                402,
                digest(HISTORY / "scoring/supplemental/source-only-tables.json"),
                "frozen-public-reader-and-validated-structure-v1",
            ),
            "funding31": metric(
                scores["funding31"].get("pass", 0),
                31,
                digest(HISTORY / "scoring/full-source-tables.json"),
                "frozen-public-reader-and-validated-structure-v1",
            ),
        },
        {
            "seconds": perf["timing"]["submit_to_saved_MD_s"]["total_s"],
            "scope": "full HTTP upload through saved Markdown; assets timed separately",
            "power_limit_W": 180,
            "hardware_fingerprint": "historical-shared-host-20261017",
            "warmup": "actual_complete_HTTP_capture",
            "own_GPU_peak_MiB": None,
            "shared_GPU_energy_Wh": None,
        },
        full_HTTP=True,
        deployment_acceptance=True,
        imported_result_preserved=True,
    )
    public = HISTORY / "followup/20261017/production-baseline/public-output-comparison"
    historical_map = {
        "paddle16-off-glm-actualHTTP": "archive-paddle16-glm",
        "paddle15-on-glm": "archive-paddle15-glm",
        "all-glm-oriented": "glm-only",
        "docling139-v1-true-default-glm": "archive-docling2139-v1-true-default-glm",
        "docling139-v1-false-pypdfium-glm": "archive-docling-21390-v1-matching-false-glm",
    }
    for row in read(public / "summary.json"):
        recipe_id = historical_map[row["config"]]
        supplement = row["supplements"]["supplement402"]
        evidence_record(
            "historical-public-" + row["config"],
            recipe_id,
            "regression-502",
            "public-final-GFM",
            [public / "summary.json", public / "plan.json", public / "completed.json"],
            {
                "core209": metric(
                    row["core_numeric"].get("pass", 0),
                    209,
                    digest(ROOT / "pdf_sample/gold/table_fact_gold_v1.json"),
                    "frozen-public-reader-v1",
                ),
                "period209": metric(
                    row["core_period_pass"],
                    209,
                    digest(ROOT / "pdf_sample/gold/table_fact_gold_v1.json"),
                    "frozen-public-reader-v1",
                ),
                "unique_row402": metric(
                    supplement["literal_and_unique_row_pass"],
                    402,
                    digest(HISTORY / "scoring/supplemental/source-only-tables.json"),
                    "frozen-public-reader-v1",
                ),
                "column_meaning402": metric(
                    supplement["literal_row_and_complete_header_pass"],
                    402,
                    digest(HISTORY / "scoring/supplemental/source-only-tables.json"),
                    "frozen-public-reader-v1",
                ),
                "funding31": metric(
                    row["funding31"].get("pass", 0),
                    31,
                    digest(HISTORY / "scoring/full-source-tables.json"),
                    "frozen-public-reader-v1",
                ),
            },
            {
                "seconds": None,
                "scope": "saved public final Markdown rescored; no fresh inference timing",
                "power_limit_W": None,
                "hardware_fingerprint": None,
                "warmup": None,
            },
            full_HTTP=row["config"] == "paddle16-off-glm-actualHTTP",
            original_output_unchanged=True,
            original_result_acquisition="saved actual HTTP"
            if row["config"] == "paddle16-off-glm-actualHTTP"
            else "saved component-composed final Markdown",
        )
    write(
        BENCH / "archive-index.json",
        {
            "schema": "moparse-archived-experiments/1",
            "functional_configurations": 147,
            "source_documents": 10,
            "source_pages": 502,
            "scope": "16 native,7 vision,112 fixed combinations/ablations,12 posthoc registered combinations; not147 full-HTTP requests",
            "frozen_manifests": [
                artifact(HISTORY / "experiment-manifest.json"),
                artifact(HISTORY / "input-manifest.json"),
                artifact(public / "summary.json"),
            ],
            "policy": "Core recipes are in methods/. Old component/composition evidence is immutable; timing reuse requires a matching protocol.",
        },
    )


def freeze_evaluators():
    """Vendor only the read-only evaluator dependency closure, byte for byte."""
    selected = [
        "input-manifest.json",
        "http/common-export-v1.1/faithful-gfm.py",
        "followup/20261017/production-baseline/score-baseline.py",
        "followup/20261017/selected-pipeline-deployment/score-full-cohort.py",
        "followup/20261017/selected-pipeline-deployment/source-independent-recheck-20261017.json",
        "followup/20261017/content-preservation-mineru/evaluate-mineru-source.py",
        "followup/20261017/content-preservation-mineru/verify-content-source.py",
        "followup/20261017/content-preservation-mineru/evaluate-docling-component.py",
        "followup/20261017/content-preservation-mineru/audit-visible-source-spans.py",
        "followup/20261017/content-preservation-mineru/source-reference.json",
        "followup/20261017/content-preservation-mineru/source-reference-p62.json",
    ]
    selected.extend(
        "scoring/" + name
        for name in [
            "score-result.py",
            "declared-scope-view.py",
            "calendar-date-review.py",
            "score-critical-keyvalue.py",
            "source-manifest.json",
            "full-source-tables.json",
            "source28-original-only.json",
            "same-header-continuation-source.json",
            "critical-shareholder-source.json",
            "supplemental/score-supplemental.py",
            "supplemental/score-source130.py",
            "supplemental/score-source28.py",
            "supplemental/score-normal-continuation.py",
            "supplemental/source-only-tables.json",
            "supplemental/130-merged-source-only.json",
        ]
    )
    selected.extend(
        str(path.relative_to(HISTORY))
        for path in (HISTORY / "scoring").glob("*contract-lock*.json")
    )
    bundle = BENCH / "scorers/frozen"
    locks = []
    for name in sorted(set(selected)):
        original, target = HISTORY / name, bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        locks.append(
            {
                "path": name,
                "sha256": digest(target),
                "original": artifact(original),
                "criteria_changed": False,
            }
        )
    write(
        bundle / "lock.json",
        {
            "schema": "moparse-frozen-evaluator-bundle/1",
            "files": locks,
            "relocation": "Only path globals OLD/REPO/GOLD/FROZEN_ADAPTER are relocated at load; predicate source bytes remain exact",
            "originals_unmodified": True,
        },
    )


def seal_evidence():
    """Small JSON snapshots make historical rescoring metadata usable on a fresh clone."""
    for record_path in sorted((BENCH / "evidence").glob("*.json")):
        record = read(record_path)
        snapshots = []
        for item in record["provenance"]:
            original = ROOT / item["path"]
            target = BENCH / "evidence/artifacts" / (item["sha256"] + original.suffix)
            target.parent.mkdir(exist_ok=True)
            if not target.exists():
                shutil.copyfile(original, target)
            if digest(target) != item["sha256"]:
                raise ValueError("Evidence snapshot hash mismatch")
            snapshots.append(
                {
                    **artifact(target),
                    "original_path": item.get("original_path", item["path"]),
                    "snapshot_bytes_unchanged": True,
                }
            )
        record["provenance"] = snapshots
        write(record_path, record)


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace-initial-import", action="store_true")
    parser.add_argument("--evidence-only", action="store_true")
    args = parser.parse_args()
    if (
        (DATA / "dataset.json").exists()
        and not args.replace_initial_import
        and not args.evidence_only
    ):
        parser.error(
            "Dataset already exists. Use add-documents; do not rebuild over holdout metadata."
        )
    registry()
    if not args.evidence_only:
        dataset()
    evidence()
    seal_evidence()
    freeze_evaluators()
    print(
        json.dumps(
            {
                "dataset": str(DATA / "dataset.json"),
                "methods": len(list((BENCH / "methods").glob("*.json"))),
                "historical_evidence": len(list((BENCH / "evidence").glob("*.json"))),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
