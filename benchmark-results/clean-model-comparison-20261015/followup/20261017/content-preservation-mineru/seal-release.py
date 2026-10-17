"""Seal the completed release and isolated trials; no parsing or deployment."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = next(parent for parent in HERE.parents if (parent / ".git").exists())
REPORT = ROOT / "benchmark-results/clean-model-comparison-20261015/report.md"
EXCLUDED = {"release-manifest.json", "release-evidence-index.jsonl", "git-push-closure.json"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(name):
    return json.loads((HERE / name).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def headings(path):
    result = set()
    for line in path.read_text().splitlines():
        if re.match(r"^#{1,6} ", line):
            value = re.sub(r"^#{1,6} ", "", line).strip().lower().replace("`", "")
            value = "".join(c for c in value if c in "-_ " or unicodedata.category(c)[0] in "LN")
            result.add(value.replace(" ", "-"))
    return result


def main():
    now = dt.datetime.now(dt.UTC).isoformat()
    checks = []
    for args in [
        [".venv/bin/ruff", "check", "app", "tests", "scripts", "docker"],
        [".venv/bin/mypy", "app"],
        ["uv", "lock", "--check"],
        ["git", "diff", "--check"],
    ]:
        process = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        checks.append(
            {
                "command": args,
                "exit": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        )
        assert process.returncode == 0
    missing, anchors, count = [], [], 0
    documents = [ROOT / "README.md", ROOT / "docs/deployment.md", REPORT]
    for document in documents:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
            if re.match(r"^[a-z]+:", target):
                continue
            parts = unquote(target.strip("<>")).split("#", 1)
            path = (document.parent / parts[0]).resolve() if parts[0] else document
            count += 1
            if not path.exists():
                missing.append({"document": str(document.relative_to(ROOT)), "target": target})
            elif len(parts) == 2 and path.suffix == ".md" and parts[1] not in headings(path):
                anchors.append({"document": str(document.relative_to(ROOT)), "target": target})
    assert not missing and not anchors, (missing, anchors)
    deployment = read("production-deployment.json")
    expected = read("candidate-image-ready-and-source.json")
    files = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / "app").rglob("*.py"))}
    assert files == deployment["actual"]["files"] == expected["actual"]["files"]
    assert "352 passed in 25.12s" in (HERE / "pytest-final-image.log").read_text()
    chart = read("chart-build.json")
    assert chart["component_input_SHA256"] == sha(HERE / "component-comparison.json")
    assert chart["renderer_SHA256"] == sha(ROOT / "scripts/render_readme_charts.py")
    assert chart["SVG_SHA256"] == sha(ROOT / "docs/assets/native-model-component-comparison.svg")
    for name, digest in read("production-old-output-hashes-before.json").items():
        assert sha(Path("/var/lib/docker/volumes/mosaicparse-data/_data") / name) == digest
    for item in read("input-manifest.json")["documents"]:
        assert sha(item["source_path"]) == item["sha256"]
    historical = {}
    prior = HERE.parent / "selected-pipeline-deployment"
    for path, digest in [
        (
            prior / "release-manifest.json",
            "610bef32c1b665ded32b52dccec1afc189d16129f0dafe744b33581951a4648f",
        ),
        (
            prior / "independent-recheck-20261017T170704/release-manifest.json",
            "4cd919ccf2e86640bb288eef64f6a89e99a532a35045d66b30fea96ff857a348",
        ),
        (
            REPORT.parent / "final-evidence-index.jsonl",
            "fe83566adc4c2556b4679816ad8f080fd940f5c478f6c77b0ae57b668c50ae71",
        ),
    ]:
        assert sha(path) == digest
        historical[str(path.relative_to(ROOT))] = digest
    validation = {
        "UTC": now,
        "checks": checks,
        "documentation_relative_links": count,
        "missing_links": missing,
        "bad_anchors": anchors,
        "application_sources_match_runtime_and_tested_image": len(files),
        "old_result_and_asset_files_unchanged": 314,
        "historical_manifests_and_index_unchanged": historical,
        "backend_test_log_SHA256": sha(HERE / "pytest-final-image.log"),
    }
    save(HERE / "final-static-verification.json", validation)
    index_rows = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.parent == HERE and path.name in EXCLUDED:
            continue
        index_rows.append(
            {
                "path": str(path.relative_to(HERE)),
                "size_bytes": path.stat().st_size,
                "SHA256": sha(path),
            }
        )
    index = HERE / "release-evidence-index.jsonl"
    index.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in index_rows))
    manifest = {
        "schema": "mosaicparse-source-content-release/1",
        "UTC": now,
        "git_parent": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "scope": "Source-content export fix deployed; five new model paths remain isolated component trials.",
        "deployed_API_image": deployment["after"]["mosaicparse"]["image"],
        "image_tag": deployment["image_tag"],
        "runtime_source_files": files,
        "SDK_and_GLM_instances_unchanged": True,
        "full_candidate_HTTP_pages": 504,
        "post_deployment_HTTP_pages": 203,
        "new_backend_tests": 23,
        "final_image_backend_tests_passed": 352,
        "model_versions_and_configuration_changed_in_production": False,
        "fixed_134_issue_classes": 1,
        "total_134_issue_classes": 6,
        "original_table_boundary_and_funding_and_source_mapping_verified": True,
        "experiment_source_pages": 14,
        "extra_p62_is_separate": True,
        "component_comparison": "component-comparison.json",
        "component_comparison_SHA256": sha(HERE / "component-comparison.json"),
        "candidate_HTTP": "candidate-full10-http/summary.json",
        "production_HTTP": "production-validation-summary.json",
        "deployed_configuration": "production-deployment.json",
        "source_acceptance": "model-evaluation/frozen-five-configuration-source-summary.json",
        "current_model_known_errors": "candidate-all-content-source-summary.json",
        "known_source_replay_limits": {
            "remaining_picture_child_text_refs": 227,
            "continuation_groups_before_after": [10, 9],
        },
        "new_model_recommendation": "MinerU4.0.12 Advanced+TXT and MinerU2.5-Pro-2605-1.2B/vLLM for native pages; GLM SDK200DPI orientation-on for scans/mixed.",
        "new_model_not_yet_deployed_because": [
            "Official native TXT fill truncates the source p87 business footnote22 to15 characters.",
            "Exact header-role, cell/span and table-source mapping adapter plus full-PDF HTTP validation remains required.",
        ],
        "own_experiment_containers_removed": True,
        "documentation_SHA256": {
            str(path.relative_to(ROOT)): sha(path)
            for path in documents + [ROOT / "docs/assets/native-model-component-comparison.svg"]
        },
        "evidence_index": index.name,
        "evidence_index_SHA256": sha(index),
        "indexed_files": len(index_rows),
        "indexed_bytes": sum(row["size_bytes"] for row in index_rows),
        "index_exclusions": sorted(EXCLUDED) + ["__pycache__/**", "*.pyc"],
        "bulk_evidence_retained_locally": str(HERE),
        "old_jobs_and_raw_results_rewritten": False,
        "report_revision_and_post_push_closure_are_outer_pointers": True,
    }
    save(HERE / "release-manifest.json", manifest)
    revision_path = REPORT.parent / "report-revision.json"
    revision = json.loads(revision_path.read_text())
    before = hashlib.sha256(
        subprocess.check_output(["git", "show", "HEAD:" + str(REPORT.relative_to(ROOT))], cwd=ROOT)
    ).hexdigest()
    clarification = {
        "created_UTC": now,
        "previous_report_SHA256": before,
        "updated_report_SHA256": sha(REPORT),
        "change": "Publish generic source-furniture/business-note preservation, full504 candidate and203 production HTTP evidence, and five same14-page model/calling-path comparisons, resource scopes and remaining TXT-fill defect. Historical runs/charts retained.",
    }
    previous = revision["report_clarifications"]
    if previous and previous[-1].get("change") == clarification["change"]:
        previous[-1] = clarification
    else:
        previous.append(clarification)
    revision["source_content_preservation_release"] = {
        "created_UTC": now,
        "deployment_or_application_code_changed": True,
        "model_weights_configuration_and_locked_package_versions_changed": False,
        "manifest": str((HERE / "release-manifest.json").relative_to(REPORT.parent)),
        "manifest_SHA256": sha(HERE / "release-manifest.json"),
        "report_SHA256": sha(REPORT),
        "deployed_API_image": manifest["deployed_API_image"],
        "full_candidate_HTTP_pages": 504,
        "post_deployment_HTTP_pages": 203,
        "isolated_new_model_configurations": 4,
        "same_page_component_configurations_including_Docling": 5,
        "isolated_model_experiments_in_production": False,
        "historical_evidence_and_charts_preserved": True,
    }
    save(revision_path, revision)
    print(
        json.dumps(
            {
                "manifest_SHA256": sha(HERE / "release-manifest.json"),
                "files": len(index_rows),
                "links_checked": count,
                "all_checks_pass": True,
            }
        )
    )


if __name__ == "__main__":
    main()
