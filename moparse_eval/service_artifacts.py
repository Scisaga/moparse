"""Rebuild saved final-output evidence without repeating service processing.

Inputs are candidate artifacts already supplied by the caller. This module
opens no files, reads no PDF/reference, and never renders, infers or repairs an
answer. Private dataclasses are restored as saved, including their rendering
caches; their constructors must not recompute the candidate's table display.
"""

from __future__ import annotations

import copy
import types
from collections.abc import Mapping
from dataclasses import MISSING, fields, is_dataclass
from functools import cache
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from app.models.content_result import ContentParseResult, UnitType
from app.models.parse_result import (
    DocumentParseResult,
    PageParseResult,
    PageStatus,
    ParsePipeline,
    ParseUsage,
    PipelineWarning,
)
from app.models.source_evidence import SourceRegionEvidence
from app.models.table_semantics import SemanticTableView
from app.services.table_service import TableFragment, TableSourceView


class ServiceArtifactError(ValueError):
    """Saved candidate evidence cannot be restored without guessing."""


@cache
def _hints(cls: type[Any]) -> dict[str, Any]:
    return get_type_hints(cls)


def _restore(value: Any, annotation: Any, path: str) -> Any:
    """Decode only the declared dataclass shape, preserving opaque evidence."""
    if annotation is Any:
        return copy.deepcopy(value)
    if annotation is type(None):
        if value is None:
            return None
        raise ServiceArtifactError(f"{path}: expected null")
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                return _restore(value, option, path)
            except ServiceArtifactError:
                pass
        raise ServiceArtifactError(f"{path}: incompatible saved value type")
    if origin is Literal:
        if any(type(value) is type(option) and value == option for option in args):
            return value
        raise ServiceArtifactError(f"{path}: unknown declared literal")
    if origin in (list, tuple):
        if not isinstance(value, (list, tuple)):
            raise ServiceArtifactError(f"{path}: expected array")
        if origin is list or len(args) == 2 and args[1] is Ellipsis:
            restored = [_restore(item, args[0], f"{path}[{i}]") for i, item in enumerate(value)]
        else:
            if len(value) != len(args):
                raise ServiceArtifactError(f"{path}: unexpected tuple length")
            restored = [_restore(item, kind, f"{path}[{i}]")
                        for i, (item, kind) in enumerate(zip(value, args, strict=True))]
        return tuple(restored) if origin is tuple else restored
    if origin is dict:
        if not isinstance(value, Mapping):
            raise ServiceArtifactError(f"{path}: expected object")
        return {_restore(key, args[0], f"{path}.key"): _restore(item, args[1], f"{path}.{key}")
                for key, item in value.items()}
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, Mapping):
            raise ServiceArtifactError(f"{path}: expected dataclass object")
        declarations = fields(annotation)
        expected = {field.name for field in declarations}
        # Absent optional context means no external source assertion. Other
        # private fields, including all role flags, remain mandatory.
        optional_evidence = {"native_evidence", "context_refs", "scope_refs"}
        required = expected - optional_evidence
        if not required <= set(value) or set(value) - expected:
            missing, extra = sorted(expected - set(value)), sorted(set(value) - expected)
            raise ServiceArtifactError(f"{path}: unknown private shape; missing={missing}, extra={extra}")
        instance = object.__new__(annotation)
        hints = _hints(annotation)
        for field in declarations:
            if field.name not in value:
                default = field.default_factory() if field.default_factory is not MISSING else copy.deepcopy(field.default)
                object.__setattr__(instance, field.name, default)
                continue
            decoded = _restore(value[field.name], hints[field.name], f"{path}.{field.name}")
            object.__setattr__(instance, field.name, decoded)
        return instance
    if annotation is float and type(value) in (int, float):
        return value
    if annotation in (str, int, bool) and type(value) is annotation:
        return value
    raise ServiceArtifactError(f"{path}: unsupported or incompatible saved value type")


def rebuild_final_result(
    final_markdown: str,
    final_ir: Mapping[str, Any],
    evidence: Mapping[str, Any],
    raw_observation: Mapping[str, Any],
) -> DocumentParseResult:
    """Restore a PDF final result from its own stored artifact representations.

    Page content is deliberately absent: it was not persisted as a separate
    final page answer. Page statuses and scoped warnings are retained; only
    the supplied document rendering supplies candidate text. An inconsistency
    is an engineering error, never permission to fill an answer from evidence.
    """
    if not isinstance(final_markdown, str):
        raise ServiceArtifactError("final_markdown: expected string")
    ir = ContentParseResult.model_validate(copy.deepcopy(dict(final_ir)))
    if ir.renderings.markdown != final_markdown:
        raise ServiceArtifactError("final IR rendering differs from saved final Markdown")
    output = raw_observation.get("service_output")
    if not isinstance(output, Mapping):
        raise ServiceArtifactError("raw observation has no service_output metadata")
    if output.get("final_markdown") != final_markdown:
        raise ServiceArtifactError("raw observation rendering differs from saved final Markdown")
    count = raw_observation.get("input_page_count")
    if type(count) is not int or count < 1 or ir.source.page_count != count:
        raise ServiceArtifactError("saved PDF page counts are inconsistent")
    units = {unit.index: unit for unit in ir.units}
    if (len(units) != len(ir.units) or set(units) != set(range(1, count + 1))
            or any(unit.unit_type != UnitType.PAGE for unit in ir.units)):
        raise ServiceArtifactError("final IR does not declare each PDF page exactly once")
    statuses = output.get("page_statuses")
    if not isinstance(statuses, list) or len(statuses) != count:
        raise ServiceArtifactError("saved page statuses are unavailable")
    status_map = {}
    for item in statuses:
        if (not isinstance(item, Mapping) or set(item) != {"page", "status"}
                or type(item["page"]) is not int or item["page"] in status_map):
            raise ServiceArtifactError("unknown or duplicate saved page status shape")
        status_map[item["page"]] = item["status"]
    if set(status_map) != set(units) or any(
        status_map[index] != unit.status for index, unit in units.items()
    ):
        raise ServiceArtifactError("saved page statuses differ from final IR")
    warnings = evidence.get("warnings")
    if not isinstance(warnings, list):
        raise ServiceArtifactError("saved candidate warnings are unavailable")
    parsed_warnings = [PipelineWarning.model_validate(copy.deepcopy(item)) for item in warnings]
    if output.get("warnings") != warnings:
        raise ServiceArtifactError("saved candidate warning representations differ")
    result = DocumentParseResult(
        document_id=ir.source.content_id,
        filename=ir.source.filename,
        mime_type=ir.source.mime_type,
        page_count=count,
        processed_pages=sum(status != "failed" for status in status_map.values()),
        markdown=final_markdown,
        plain_text=ir.renderings.plain_text,
        pages=[PageParseResult(
            page_number=unit.index,
            status=PageStatus(unit.status),
            duration_ms=unit.duration_ms,
            warnings=[warning.model_copy(deep=True) for warning in parsed_warnings
                      if warning.page_number == unit.index],
        ) for unit in ir.units],
        pipeline=ParsePipeline(profile=ir.runtime.profile, primary=ir.runtime.primary_backend,
                               ocr=ir.runtime.ocr_backend),
        warnings=parsed_warnings,
        usage=ParseUsage(input_bytes=ir.runtime.input_bytes, duration_ms=ir.runtime.duration_ms),
        created_at=ir.created_at,
        parse_result=ir,
    )
    for key, cls, attribute in (
        ("table_fragments", TableFragment, "_table_fragments"),
        ("table_views", TableSourceView, "_table_views"),
        ("semantic_tables", SemanticTableView, "_semantic_tables"),
        ("source_regions", SourceRegionEvidence, "_source_regions"),
    ):
        saved = evidence.get(key)
        if not isinstance(saved, list):
            raise ServiceArtifactError(f"{key}: saved private array is unavailable")
        setattr(result, attribute, [_restore(item, cls, f"{key}[{i}]")
                                    for i, item in enumerate(saved)])
    verification = evidence.get("source_verification")
    if not isinstance(verification, Mapping):
        raise ServiceArtifactError("source_verification: saved object is unavailable")
    result._source_verification = copy.deepcopy(dict(verification))
    final_text = evidence.get("final_text_evidence", {})
    if not isinstance(final_text, Mapping):
        raise ServiceArtifactError("final_text_evidence: saved object is unavailable")
    result._final_text_evidence = copy.deepcopy(dict(final_text))
    return result
