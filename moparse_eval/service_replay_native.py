"""Offline bridge from frozen candidate native objects to service readback.

All eight saved configurations delegate to the same source-free contract.
The separate fixed Typed verification helper remains available; it is never
invoked by saved JSON admission. No parser, model, transport or asset extraction runs.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from importlib import metadata
from types import SimpleNamespace
from typing import Any

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import DocumentParseResult
from app.models.source import StoredSource

MinerUProjector = Callable[[list[Any]], tuple[list[Any], list[dict[str, Any]]]]


class ReplayDependencyError(RuntimeError):
    """The offline environment lacks its declared fixed software dependency."""


def project_mineru_blocks(blocks: list[Any]) -> tuple[list[Any], list[dict[str, Any]]]:
    """Recreate the production worker projection with DocVortex 0.5.16 only.

    Validation is per block so a malformed sibling cannot erase valid typed
    content. Received bytes stay in the caller's frozen native object.
    """
    try:
        version = metadata.version("docvortex")
    except metadata.PackageNotFoundError as exc:
        raise ReplayDependencyError("offline native replay requires docvortex==0.5.16") from exc
    if version != "0.5.16":
        raise ReplayDependencyError(f"offline native replay requires docvortex==0.5.16; found {version}")
    from docvortex.schema import PageBlock
    from pydantic import TypeAdapter

    from native_worker.server import export_source_blocks

    adapter = TypeAdapter(PageBlock)
    projected: list[Any] = []
    errors = []
    for index, raw in enumerate(blocks):
        try:
            typed = adapter.validate_python(raw)
            exported = export_source_blocks(SimpleNamespace(blocks=[typed]))
            if len(exported) != 1:
                raise ValueError("official projection did not return one block")
            block = exported[0]
        except (ValueError, TypeError, KeyError) as exc:
            block = copy.deepcopy(raw)
            if isinstance(block, dict):
                block["export_error"] = {"code": "offline_typed_projection_failed",
                                         "exception_type": type(exc).__name__}
            errors.append({"block_index": index, "stage": "typed_native_projection",
                           "code": "offline_typed_projection_failed", "exception_type": type(exc).__name__})
        else:
            if block.get("export_error") is not None:
                errors.append({"block_index": index, "stage": "official_native_rendering",
                               "code": "offline_official_rendering_failed", "detail": block["export_error"]})
        projected.append(block)
    return projected, errors


def _pointer(root: Mapping[str, Any], pointer: Any) -> Any:
    if isinstance(pointer, str) and "::decoded" in pointer:
        outer, inner = pointer.split("::decoded", 1)
        serialized = _pointer(root, outer)
        if not isinstance(serialized, str):
            return None
        try:
            decoded = json.loads(serialized)
        except json.JSONDecodeError:
            return None
        return _pointer(decoded, "#" + inner) if inner else decoded
    if not isinstance(pointer, str) or not pointer.startswith("#/"):
        return None
    value: Any = root
    for encoded in pointer[2:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(value, Mapping) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdecimal() and int(key) < len(value):
            value = value[int(key)]
        else:
            return None
    return value



def replay_native(
    native: Mapping[str, Any], source: StoredSource, options: ContentParseOptions, *, document_id: str,
    mineru_projector: MinerUProjector | None = None,
    include_source_markers: bool = False,
    artifact=None, original_observation=None, observation_identity=None,
    observation_bytes=None, source_pages=None,
) -> tuple[DocumentParseResult, dict[str, Any]]:
    """Admit every saved configuration through the common source-free contract."""
    from app.adapters.native_config import CONFIGURATIONS
    from app.adapters.saved_native import adapt_saved_document

    if native.get("pipeline") not in CONFIGURATIONS:
        raise ValueError("service replay requires a declared P01-P08 candidate")
    if mineru_projector is not None:
        raise ValueError("shared saved JSON admission does not accept injected Typed projectors")
    return adapt_saved_document(native, source, options, document_id=document_id,
        include_source_markers=include_source_markers, artifact=artifact,
        original_observation=original_observation, observation_identity=observation_identity,
        observation_bytes=observation_bytes, source_pages=source_pages)
