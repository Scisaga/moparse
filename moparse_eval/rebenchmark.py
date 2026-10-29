"""Build declared execution prechecks and direct single-page calibration jobs.

This module never starts inference, scores quality, reads reference material or
reviews corpus content. PDF page copying only materializes the already authored
preflight selection; declarations and successful packaging are not acceptance.
"""

from __future__ import annotations

import copy
import math
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import cli
from .packaging import extract_declared_pages


def assess_measurement_conditions(maintenance: Mapping[str, Any] | None) -> dict[str, Any]:
    """Assess runtime evidence only, independently of service recovery success.

    This function performs no I/O, changes no evidence and accepts no references
    or parser answers. Legacy records require positive TTS stability evidence;
    an explicit observe-only policy retains TTS observations as qualifications.
    """
    evidence = maintenance if isinstance(maintenance, Mapping) else {}
    identity = evidence.get("tts_identity_condition")
    activity = evidence.get("tts_no_calls_condition")
    observed = {
        "maintenance.phase": evidence.get("phase", "unknown"),
        "tts_policy": evidence.get("tts_policy", "unknown"),
        "tts_observation_policy": evidence.get("tts_observation_policy", "strict"),
        "user_instruction_date": evidence.get("user_instruction_date", "unknown"),
        "tts_identity_condition.status": identity.get("status", "unknown")
            if isinstance(identity, Mapping) else "unknown",
        "tts_no_calls_condition.status": activity.get("status", "unknown")
            if isinstance(activity, Mapping) else "unknown",
    }
    required = {"maintenance.phase": "restored", "tts_policy": "keep_running"}
    observe_only = observed["tts_observation_policy"] == "observe_only"
    if not observe_only:
        required.update({"tts_identity_condition.status": "unchanged",
                         "tts_no_calls_condition.status": "no_observed_activity"})
    problems = [{"condition": key, "expected": expected, "observed": observed[key]}
                for key, expected in required.items() if observed[key] != expected]
    warnings = [{"condition": key, "observed": observed[key], "effect": "observation_only"}
                for key, expected in (("tts_identity_condition.status", "unchanged"),
                                      ("tts_no_calls_condition.status", "no_observed_activity"))
                if observe_only and observed[key] != expected]
    qualifications = (["TTS is co-resident and uncontrolled; its activity, identity and query availability do not determine measurement admission. Performance reflects these actual shared-GPU conditions."]
                      if observe_only else [])
    return {"valid": not problems, "status": "invalidated" if problems else "valid",
            "observed": observed, "problems": problems, "warnings": warnings,
            "qualifications": qualifications,
            "evidence": {"tts_identity_condition": copy.deepcopy(identity),
                         "tts_no_calls_condition": copy.deepcopy(activity),
                         "tts_readiness_observation": copy.deepcopy(evidence.get("tts_readiness_observation"))},
            "scope": "runtime measurement conditions only; not parser quality or corpus acceptance"}


def build_preflight_jobs(
    manifest: dict[str, Any], dataset: Path, calibration_dir: Path,
) -> tuple[list[dict[str, Any]], Path]:
    """Copy three declared samples and split their eight declared input pages.

    The external ``inputs`` root contains input PDFs only, so one persistent
    worker can mount it read-only for the complete 3+8 schedule. No reference
    paths, source text, PDF page counts or corpus correctness are inspected.
    The output directory is new and cannot overwrite an earlier preparation.
    """
    dataset, calibration_dir = dataset.resolve(), calibration_dir.resolve()
    if calibration_dir.is_relative_to(dataset):
        raise ValueError("calibration inputs must be outside the read-only dataset")
    declared = cli.execution_plan(manifest, dataset, "preflight8")
    # These are constraints on the requested job schedule, not PDF validation.
    if len(declared) != 3 or sum(job["input_page_count"] for job in declared) != 8:
        raise ValueError("preflight preparation requires the authored three samples and eight input pages")
    dataset_inputs = (dataset / "inputs").resolve()
    for job in declared:
        if not Path(job["pdf_path"]).resolve().is_relative_to(dataset_inputs):
            raise ValueError("preflight PDF must be inside the declared dataset inputs directory")
        count = job["input_page_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("preflight input_page_count must declare a positive integer")
    calibration_dir.mkdir(parents=True, exist_ok=False)
    input_root = calibration_dir / "inputs"
    preflight_inputs = input_root / "preflight8"
    single_inputs = input_root / "calibration8"
    preflight_inputs.mkdir(parents=True)
    single_inputs.mkdir()
    jobs, calibration = [], []
    for sample_index, original in enumerate(declared):
        source = Path(original["pdf_path"])
        copied = preflight_inputs / f"sample-{sample_index + 1:02d}.pdf"
        shutil.copyfile(source, copied)
        job = copy.deepcopy(original)
        job.update(pdf_path=str(copied),
                   output_dir=f"preflight-preflight8-r1/sample-{sample_index + 1:02d}")
        jobs.append(job)
        for local_page in range(1, original["input_page_count"] + 1):
            single_id = f"{original['sample_id']}__local_{local_page:04d}"
            destination = single_inputs / f"sample-{sample_index + 1:02d}-page-{local_page:04d}.pdf"
            extract_declared_pages(copied, destination, [local_page])
            calibration.append({
                "sample_id": single_id, "parent_sample_id": original["sample_id"],
                "local_page": local_page, "pdf_path": str(destination),
                "suite": "calibration8", "phase": "calibration", "warmup": False,
                "repetition": 1, "input_page_count": 1,
                "output_dir": f"calibration-calibration8-r1/sample-{sample_index + 1:02d}-page-{local_page:04d}",
            })
    return jobs + calibration, input_root


def calibration_summary(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Retain current direct single-page measurements and all unsuccessful cases.

    Completed jobs, including preserved native-structure limitations, contribute
    to the preparation timeout. Missing timings remain unknown. This is execution
    calibration, not throughput reporting, quality scoring or corpus review.
    """
    successful, incomplete = [], []
    slowest: float | None = None
    for observation in observations:
        if observation.get("suite") != "calibration8":
            continue
        timing = observation.get("timing", {})
        seconds = timing.get("processing_seconds") if isinstance(timing, Mapping) else None
        item = {"sample_id": observation.get("sample_id"),
                "status": observation.get("status"),
                "input_page_count": observation.get("input_page_count"),
                "processing_seconds": seconds}
        errors = observation.get("errors", [])
        native_structure_only = (observation.get("status") == "partial" and bool(errors)
                                 and all(error.get("category") == "candidate_native_structure"
                                         for error in errors))
        if ((observation.get("status") == "completed" or native_structure_only)
                and observation.get("input_page_count") == 1
                and isinstance(seconds, (int, float)) and not isinstance(seconds, bool)
                and math.isfinite(seconds) and seconds > 0):
            if native_structure_only:
                item["native_structure_limitations"] = copy.deepcopy(errors)
            successful.append(item)
            slowest = max(slowest, float(seconds)) if slowest is not None else float(seconds)
        else:
            item["errors"] = copy.deepcopy(observation.get("errors", []))
            item["excluded_reason"] = "calibration_requires_completed_single_page_with_observed_positive_processing_seconds"
            incomplete.append(item)
    return {
        "scope": "direct_single_page_execution_calibration_not_comparison_results",
        "successful_single_pages": successful, "incomplete_single_pages": incomplete,
        "slowest_successful_page_seconds": slowest,
        "timeout_policy": "min(3600, max(300, 3 * slowest_successful_page_seconds * input_page_count))",
        "complete_calibration": len(successful) == 8 and not incomplete,
    }


def calibrated_timeout_seconds(slowest_page_seconds: float, input_page_count: int) -> float:
    """Apply the declared rule to a newly observed direct single-page cost."""
    if (isinstance(slowest_page_seconds, bool)
            or not isinstance(slowest_page_seconds, (int, float))
            or not math.isfinite(slowest_page_seconds) or slowest_page_seconds <= 0):
        raise ValueError("slowest_page_seconds needs an observed positive finite measurement")
    if isinstance(input_page_count, bool) or not isinstance(input_page_count, int) or input_page_count < 1:
        raise ValueError("input_page_count must be a declared positive integer")
    return min(3600.0, max(300.0, 3 * slowest_page_seconds * input_page_count))
