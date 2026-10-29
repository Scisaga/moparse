"""Offline bridge from frozen candidate native objects to service readback.

This module reads neither source PDF bytes nor references. The only newly
generated Markdown is the fixed official renderer's view of already returned
typed blocks. No parser, model, transport, service, or asset extraction runs.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict
from collections.abc import Callable, Mapping
from importlib import metadata
from types import SimpleNamespace
from typing import Any

from app.models.parse_options import ContentParseOptions
from app.models.parse_result import (
    DocumentParseResult,
    PageDiagnostics,
    PageParseResult,
    PageSourceKind,
    PageStatus,
    ParsePipeline,
    ParseUsage,
    PipelineWarning,
    RouteSummary,
    SelectionStrategy,
    WarningSeverity,
)
from app.models.source import StoredSource
from app.parsers.glm_sdk_remote import GlmSdkRemoteParser
from app.parsers.mineru_native_remote import (
    MinerUPictureCandidate,
    _NativeContentError,
    render_mineru_page_evidence,
)
from app.utils.page_range import parse_page_range

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


def _mineru_source_page(native: Mapping[str, Any], entry: Mapping[str, Any], page: int
                        ) -> tuple[list[Any] | None, dict[str, Any]]:
    raw = entry.get("raw")
    detail: dict[str, Any] = {"raw_page": page, "branch": "mineru"}
    if not isinstance(raw, Mapping):
        return None, {**detail, "error": "mineru_raw_not_an_object"}
    index = raw.get("page_idx")
    detail["raw_page_idx"] = index
    if type(index) is not int or index != page - 1:
        return None, {**detail, "error": "mineru_raw_page_identity_conflict"}
    ref = raw.get("native_document")
    detail["native_document"] = ref
    document = _pointer(native, ref)
    if not isinstance(document, Mapping) or document.get("schema") != "docvortex.middle":
        return None, {**detail, "error": "mineru_declared_middle_document_unavailable"}
    pages = document.get("pages")
    if not isinstance(pages, list):
        return None, {**detail, "error": "mineru_middle_pages_unavailable"}
    matches = [(position, item) for position, item in enumerate(pages)
               if isinstance(item, Mapping) and type(item.get("page_idx")) is int and item["page_idx"] == index]
    if len(matches) != 1:
        return None, {**detail, "error": "mineru_middle_page_not_unique"}
    position, source_page = matches[0]
    detail["native_page_pointer"] = f"{ref}/pages/{position}"
    blocks = source_page.get("blocks")
    if not isinstance(blocks, list):
        return None, {**detail, "error": "mineru_middle_blocks_unavailable"}
    return blocks, detail


def _asset_references(value: Any, pointer: str) -> list[dict[str, Any]]:
    """Index existing candidate asset declarations without opening their files."""
    refs = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = pointer + "/" + str(key).replace("~", "~0").replace("/", "~1")
            if key in {"research_asset", "research_assets", "image_files"}:
                values = child.values() if isinstance(child, Mapping) else child if isinstance(child, list) else [child]
                for ref in values:
                    if isinstance(ref, str):
                        refs.append({"native_path": path, "reference": None if ref.startswith("data:") else ref,
                                     "inline_data": ref.startswith("data:")})
            else:
                refs.extend(_asset_references(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            refs.extend(_asset_references(child, f"{pointer}/{index}"))
    return refs


def _warning(code: str, page: int, branch: str, *, detail: dict[str, Any] | None = None) -> PipelineWarning:
    return PipelineWarning(code=code, message="offline native replay could not read the declared candidate view",
                           severity=WarningSeverity.ERROR, page_number=page, backend=branch, details=detail)


def _unreadable_page(page: int, branch: str, warnings: list[PipelineWarning]
                     ) -> tuple[PageParseResult, MinerUPictureCandidate]:
    ref = f"replay_p{page}_unreadable"
    return (PageParseResult(page_number=page, backend=branch, status=PageStatus.FAILED,
                           content=f"<!-- source-page-image: {ref} -->", warnings=warnings),
            MinerUPictureCandidate(page, 0, "原页（读回未知）", (0, 0, 1, 1),
                                   source_page_ref=ref, allow_description=False))


def replay_native(
    native: Mapping[str, Any], source: StoredSource, options: ContentParseOptions, *, document_id: str,
    mineru_projector: MinerUProjector | None = None,
) -> tuple[DocumentParseResult, dict[str, Any]]:
    """Build service input from a frozen P07/P08 candidate, without source reads.

    ``source`` supplies identity/page-count metadata only. PDF inspection,
    asset extraction and service postprocessing remain the runner's work.
    """
    pipeline = native.get("pipeline")
    if pipeline not in {"P07", "P08"}:
        raise ValueError("service replay accepts frozen P07/P08 candidate artifacts only")
    selected = parse_page_range(options.page_range, source.page_count)
    result = DocumentParseResult(document_id=document_id, filename=source.filename, mime_type=source.mime_type,
                                 page_count=source.page_count, processed_pages=0,
                                 pipeline=ParsePipeline(profile=options.profile.value,
                                                        primary="mineru-visual" if pipeline == "P08" else "mineru-advanced-txt"),
                                 usage=ParseUsage(input_bytes=source.size_bytes))
    diagnostic: dict[str, Any] = {
        "schema": "offline-service-native-replay/1", "pipeline": pipeline, "pages": [], "errors": [],
        "asset_references": [], "model_calls": 0, "http_calls": 0,
        "timing_scope": "offline_native_readback_only_not_original_parser_processing",
        "geometry_frame": "frozen_oriented_input",
        "page_processing": copy.deepcopy(native.get("page_processing", [])),
        "mineru_projection": "production_official_docvortex_0.5.16" if mineru_projector is None else "injected_projector",
    }
    entries: dict[int, list[tuple[int, Mapping[str, Any]]]] = defaultdict(list)
    raw_pages = native.get("pages")
    if not isinstance(raw_pages, list):
        diagnostic["errors"].append({"code": "native_pages_not_a_list"})
        raw_pages = []
    for index, entry in enumerate(raw_pages):
        if not isinstance(entry, Mapping) or type(entry.get("page")) is not int:
            diagnostic["errors"].append({"native_page_position": index, "code": "native_page_identity_unavailable"})
            continue
        number = entry["page"]
        if number not in selected:
            diagnostic["errors"].append({"native_page_position": index, "raw_page": number,
                                         "code": "native_page_outside_replay_selection"})
        entries[number].append((index, entry))
    projector = mineru_projector or project_mineru_blocks
    processing: dict[int, Mapping[str, Any]] = {}
    processing_items = native.get("page_processing") or []
    if not isinstance(processing_items, list):
        diagnostic["errors"].append({"code": "native_page_processing_not_a_list"})
        processing_items = []
    for item in processing_items:
        if isinstance(item, Mapping) and type(item.get("page")) is int:
            processing[item["page"]] = item
    branches = []
    for number in selected:
        records = entries.get(number, [])
        warnings: list[PipelineWarning] = []
        branch = "unknown"
        detail: dict[str, Any] = {"raw_page": number}
        if number in processing:
            detail["frozen_page_processing"] = copy.deepcopy(dict(processing[number]))
        page: PageParseResult | None = None
        if len(records) != 1:
            detail["error"] = "native_page_missing" if not records else "native_page_duplicated"
        else:
            position, entry = records[0]
            branch = str(entry.get("branch", "unknown"))
            branches.append(branch)
            detail.update(branch=branch, native_page_position=position)
            raw = entry.get("raw")
            diagnostic["asset_references"].extend(_asset_references(raw, f"#/pages/{position}/raw"))
            if branch == "visual" and pipeline == "P08" and isinstance(raw, list):
                from app.parsers.mineru_visual_result import render_visual_page
                markdown, fragments, pictures, furniture, projected = render_visual_page(raw, number, warnings=warnings)
                result._native_page_blocks[number] = projected
                result._table_fragments.extend(fragments)
                result._picture_candidates.extend(pictures)
                result._page_furniture.extend(furniture)
                page = PageParseResult(page_number=number, backend="mineru-visual", content=markdown,
                                       status=PageStatus.FAILED if warnings else PageStatus.COMPLETED,
                                       warnings=warnings, diagnostics=PageDiagnostics(
                                           source_kind=PageSourceKind.VISUAL,
                                           selected_strategy=SelectionStrategy.MINERU))
            elif branch == "mineru" and pipeline == "P07":
                blocks, identity = _mineru_source_page(native, entry, number)
                detail.update(identity)
                if blocks is not None:
                    projected, errors = projector(copy.deepcopy(blocks))
                    detail["projection_errors"] = errors
                    projected_page = {"page_number": number, "blocks": projected}
                    try:
                        markdown, fragments, pictures, furniture = render_mineru_page_evidence(
                            projected_page, warnings=warnings,
                        )
                    except _NativeContentError as exc:
                        detail["error"] = "production_mineru_page_unreadable"
                        detail["exception_type"] = type(exc).__name__
                    else:
                        result._native_page_blocks[number] = projected
                        result._table_fragments.extend(fragments)
                        result._picture_candidates.extend(pictures)
                        result._page_furniture.extend(furniture)
                        page = PageParseResult(page_number=number, backend="mineru-advanced-txt", content=markdown,
                                               status=PageStatus.FAILED if warnings else PageStatus.COMPLETED,
                                               warnings=warnings, diagnostics=PageDiagnostics(
                                                   source_kind=PageSourceKind.NATIVE,
                                                   selected_strategy=SelectionStrategy.MINERU))
            elif branch == "glm" and pipeline == "P07" and isinstance(raw, Mapping):
                result.pipeline.ocr = "glm-sdk-remote"
                if "json_result" not in raw:
                    detail["error"] = "glm_primary_json_result_missing"
                else:
                    try:
                        regions = GlmSdkRemoteParser._page_regions(raw["json_result"], warnings=warnings,
                                                                   page_number=number)
                        markdown, fragments = GlmSdkRemoteParser._render_regions(regions, number, warnings=warnings)
                    except (ValueError, TypeError) as exc:
                        detail["error"] = "glm_primary_view_unreadable"
                        detail["exception_type"] = type(exc).__name__
                    else:
                        if not markdown and isinstance(raw.get("markdown_result"), str):
                            markdown = re.sub(r"!\[[^\]]*\]\([^)]*\)", "<!-- image -->", raw["markdown_result"]).strip()
                        if not markdown:
                            warnings.append(_warning("offline_glm_empty_page", number, branch))
                        status = PageStatus.FAILED if warnings else PageStatus.COMPLETED
                        ref = f"sdk_p{number}_failed" if status == PageStatus.FAILED else None
                        if ref:
                            markdown += f"\n\n<!-- source-page-image: {ref} -->"
                        result._picture_candidates.append(MinerUPictureCandidate(
                            number, 0, "扫描页原图", (0, 0, 1, 1), source_page_ref=ref, allow_description=False,
                        ))
                        result._table_fragments.extend(fragments)
                        page = PageParseResult(page_number=number, backend="glm-sdk-remote", content=markdown or None,
                                               status=status, warnings=warnings, diagnostics=PageDiagnostics(
                                                   source_kind={"scan": PageSourceKind.SCANNED,
                                                                "mixed": PageSourceKind.MIXED}.get(
                                                                    str(processing.get(number, {}).get("source_prediction")),
                                                                    PageSourceKind.SPARSE),
                                                   selected_strategy=SelectionStrategy.GLM_TABLE))
            else:
                detail["error"] = "unsupported_or_unreadable_native_branch"
        if page is None:
            warning = _warning(str(detail.get("error", "offline_native_readback_failed")), number, branch, detail=detail)
            page, picture = _unreadable_page(number, branch, [*warnings, warning])
            result._picture_candidates.append(picture)
        detail.update(status=page.status.value, warnings=[item.code for item in page.warnings])
        if detail.get("error") or detail.get("projection_errors") or page.warnings:
            diagnostic["errors"].append(copy.deepcopy(detail))
        diagnostic["pages"].append(detail)
        result.pages.append(page)
        result.warnings.extend(page.warnings)
    result.processed_pages = sum(page.status == PageStatus.COMPLETED for page in result.pages)
    result.route_summary = RouteSummary(native_text_pages=branches.count("mineru"),
                                        pages_with_ocr=sum(page.backend in {"glm-sdk-remote", "mineru-visual"} and page.status == PageStatus.COMPLETED
                                                           for page in result.pages),
                                        failed_pages=sum(page.status == PageStatus.FAILED for page in result.pages))
    return result, diagnostic
