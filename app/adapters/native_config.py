"""Declared saved configurations: identity and source permissions, never semantics."""

from typing import Any

CONFIGURATIONS: dict[str, dict[str, Any]] = {
    "P01": {"backend": "docling-tableformer-v1", "branches": {"docling", "glm"}},
    "P02": {"backend": "docling-tableformer-v2", "branches": {"docling", "glm"}},
    "P05": {"backend": "glm-sdk-remote", "branches": {"glm"}},
    "P03": {"backend": "paddleocr-vl-1.5", "branches": {"paddle"}},
    "P04": {"backend": "paddleocr-vl-1.6", "branches": {"paddle"}},
}
