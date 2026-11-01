"""Read saved candidate asset delivery; never inspect image or reference content."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .packaging import inside, read_json


def native_delivery(source: Path, observation: dict[str, Any]) -> dict[str, Any]:
    records = []
    for asset in observation.get("assets", []):
        if not isinstance(asset, dict):
            continue
        relative = asset.get("path")
        if not isinstance(relative, str):
            continue
        try:
            path = inside(source.parent, relative)
            present = path.is_file() and path.stat().st_size > 0
        except (ValueError, OSError):
            present = False
        records.append({"path": relative, "present": present})
    references = [block.get("asset") for page in observation.get("pages", []) for block in page.get("blocks", [])
                  if block.get("kind") in {"image", "picture", "figure", "image_body", "chart", "chart_body"}]
    delivered = {record["path"] for record in records if record["present"]}
    linked = sum(isinstance(ref, str) and ref in delivered for ref in references)
    return {"scope": "saved_candidate_files_only_no_image_semantics", "declared_files": len(records),
            "files_present": sum(r["present"] for r in records), "records": records,
            "image_references": len(references), "references_with_file": linked,
            "references_without_file": len(references) - linked}


def final_delivery(source: Path, markdown: str, metadata: dict[str, Any]) -> dict[str, Any]:
    from app.services.storage_service import StorageService

    from .expected_readback import MARKDOWN

    references = [child.attrGet("src") for token in MARKDOWN.parse(markdown)
                  for child in token.children or [] if child.type == "image"]
    saved = source.with_name("final.json")
    result: dict[str, Any] = {"scope": "saved_candidate_assets_only_not_business_text_or_image_semantics",
                              "declared_files": 0, "files_present": 0, "image_references": len(references),
                              "references_with_file": 0, "references_without_file": len(references), "records": []}
    if not saved.is_file():
        result["metadata_status"] = "not_produced"
        return result
    try:
        # Deliberately read only delivery metadata, never private text/IR as an answer.
        assets = read_json(saved).get("assets", [])
        if not isinstance(assets, list):
            raise ValueError("candidate assets must be an array")
    except (ValueError, TypeError, OSError):
        result["metadata_status"] = "invalid_candidate_metadata"
        return result
    storage = StorageService(SimpleNamespace(data_dir=source.parent.parent.parent / "data"))
    ready_references: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            result["records"].append({"present": False, "reason": "invalid_candidate_asset"})
            continue
        identifier, filename = asset.get("asset_id"), asset.get("filename")
        try:
            path = storage.asset_path(metadata.get("job_id", ""), identifier)
            present = bool(path and path.stat().st_size > 0)
        except (ValueError, TypeError, OSError):
            present = False
        result["records"].append({"asset_id": identifier, "filename": filename, "present": present})
        if present:
            ready_references.update(ref for ref in (asset.get("download_url"), f"assets/{identifier}/{filename}")
                                    if isinstance(ref, str) and ref)
    result.update(metadata_status="read", declared_files=len(assets),
                  files_present=sum(r["present"] for r in result["records"]),
                  references_with_file=sum(ref in ready_references for ref in references),
                  references_without_file=sum(ref not in ready_references for ref in references))
    return result
