"""Re-read saved SDK objects from their declared branches without answer input."""

from __future__ import annotations

import copy
from typing import Any

from .adapters import READERS, NativeReadError
from .native_readback import _native_object


def read_saved_native(native: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(observation)
    result["pages"], result["native_containers"] = [], []
    original_pages = {page.get("page"): page for page in observation.get("pages", [])}
    emitted: set[str] = set()
    for index, page in enumerate(native.get("pages", [])):
        number, branch, raw = page["page"], page["branch"], page["raw"]
        if branch not in READERS:
            raise ValueError(f"saved branch has no faithful reader: {branch}")
        pointer = f"#/pages/{index}/raw"
        if branch == "docling":
            pointer = raw["native_document"]
            raw = _native_object(native, pointer)
            if raw is None:
                raise ValueError("declared Docling document is missing from saved native object")
        prior = original_pages.get(number, {})
        dimensions = {"width": prior.get("width"), "height": prior.get("height"), "unit": "pixel"}
        try:
            blocks = READERS[branch](raw, number, pointer, emitted=emitted,
                containers=result["native_containers"], page_dimensions=dimensions)
        except NativeReadError as error:
            # Producer-malformed objects retain their original failure and
            # denominator; software exceptions must stop publication.
            blocks = [{"id": pointer, "native_path": pointer, "kind": "unknown", "text": "",
                       "read_error": str(error), "read_error_category": "candidate_native_structure"}]
        if any(block.get("read_error_category") == "engineering_failure" for block in blocks):
            raise ValueError("native SDK reader failed; repair before scoring")
        result["pages"].append({**{k: v for k, v in prior.items() if k != "blocks"},
                                "page": number, "branch": branch, "blocks": blocks})
    returned = {page["page"] for page in result["pages"]}
    result["pages"].extend({**page, "blocks": []} for number, page in original_pages.items() if number not in returned)
    result["pages"].sort(key=lambda page: page.get("page") or 0)
    result["native_reading"] = {"source": "saved_native_json", "audit_views_used_as_answers": False,
                                "declared_branches": sorted({p["branch"] for p in native.get("pages", [])})}
    return result
