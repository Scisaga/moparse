"""Read-only DocVortex 0.5.16 format checks; never a production converter.

The container launcher mounts code, the fixed native JSON, and new output only.
Each source occurrence keeps its original JSON pointer, including rejected ones.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.abc
import importlib.metadata as metadata
import inspect
import json
import os
import resource
import sys
from collections import Counter
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Any

PINNED_VERSION = "0.5.16"
MEDIA_FIELDS = {"image_base64", "image_path", "image_url", "image_uri"}
CONTAINERS = {"table", "list", "index", "image", "chart", "code"}


class DependencyUnavailable(RuntimeError):
    """No official work has executed in this interpreter."""


class BoundaryViolation(RuntimeError):
    """An operation outside text/schema validation was refused."""


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_digest(value: Any) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def observe(value: Any) -> Any:
    """Keep media declarations as strings/hashes, never decode or dereference."""
    if isinstance(value, dict):
        return {
            k: {"declared": True, "characters": len(v), "utf8_sha256": digest(v.encode())}
            if k == "image_base64" and isinstance(v, str)
            else observe(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [observe(v) for v in value]
    return value


def require_pinned_version(found: str) -> None:
    if found != PINNED_VERSION:
        raise DependencyUnavailable(f"requires docvortex=={PINNED_VERSION}; found {found}")


class TextOnlyBoundary(importlib.abc.MetaPathFinder):
    """Audit plus import/call guards, installed before importing official code.

    This does not replace any official class, module, metadata or function.
    The profiler refuses in-memory image decoding, which has no audit event.
    """

    forbidden_modules = (
        "mineru",
        "mineru_vl_utils",
        "native_worker",
        "torch",
        "onnxruntime",
        "magika",
        "transformers",
        "docvortex.analyzers",
        "docvortex.document.pdf",
    )
    media_suffixes = {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
        ".svg",
        ".onnx",
        ".safetensors",
        ".pt",
        ".pth",
        ".bin",
    }

    def __init__(self):
        self.violations: list[dict] = []
        self.imported: set[str] = set()

    def refuse(self, event, detail):
        self.violations.append({"event": event, "detail": str(detail)})
        raise BoundaryViolation(f"{event}: {detail}")

    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == p or fullname.startswith(p + ".") for p in self.forbidden_modules):
            self.refuse("forbidden_import", fullname)
        self.imported.add(fullname)
        return None

    def audit(self, event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0]))
            if path.suffix.lower() in self.media_suffixes or any(
                p in path.parts for p in ("pdf_sample", "datasets", "expected", "models")
            ):
                self.refuse("source_media_or_model_open", path)
        if event in {
            "socket.connect",
            "socket.bind",
            "socket.sendto",
            "socket.getaddrinfo",
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.posix_spawn",
        }:
            self.refuse(event, "not permitted during validation")

    def profile(self, frame, event, arg):
        if event == "call":
            module = frame.f_globals.get("__name__", "")
            name = frame.f_code.co_name
            if (
                module == "base64"
                and name in {"b64decode", "standard_b64decode", "decodebytes"}
                or module == "PIL.Image"
                and name in {"open", "new", "frombytes", "frombuffer"}
                or module == "docvortex.foundation._image_payload"
                and name in {"resolve_image_payload", "decode_image_payload", "read_image_payload"}
            ):
                self.refuse("media_decode_or_creation", f"{module}.{name}")
        elif (
            event == "c_call"
            and getattr(arg, "__module__", "") == "binascii"
            and getattr(arg, "__name__", "") == "a2b_base64"
        ):
            self.refuse("media_decode", "binascii.a2b_base64")

    def install(self):
        sys.meta_path.insert(0, self)
        sys.addaudithook(self.audit)
        sys.setprofile(self.profile)


class OfficialAPI:
    def __init__(self):
        try:
            self.distribution = metadata.distribution("docvortex")
        except metadata.PackageNotFoundError as exc:
            raise DependencyUnavailable(
                "docvortex==0.5.16 not installed; official checks not executed"
            ) from exc
        require_pinned_version(self.distribution.version)
        # These are real imports from the selected interpreter, with no fallback.
        from docvortex import __version__, schema
        from docvortex.options import LatexDelimitersConfig
        from docvortex.render._internal.markdown.blocks import render_visual_annotation
        from docvortex.render._internal.markdown.inline import render_inline_spans
        from docvortex.render.markdown import render_single_block
        from pydantic import BaseModel, TypeAdapter, ValidationError

        self.schema = schema
        require_pinned_version(__version__)
        self.base_model = BaseModel
        self.validation_error = ValidationError
        self.page_block = TypeAdapter(schema.PageBlock)
        self.block = TypeAdapter(schema.Block)
        self.inline = TypeAdapter(schema.InlineSpan)
        self.delimiters = LatexDelimitersConfig()
        self.renderer = render_single_block
        self.annotation_renderer = render_visual_annotation
        self.inline_renderer = render_inline_spans

    def identity(self):
        d = self.distribution
        package = Path(d.locate_file("docvortex"))
        sources = {}
        for path in sorted(package.rglob("*.py")):
            sources[str(path.relative_to(package))] = digest(path.read_bytes())
        return {
            "sys_executable": sys.executable,
            "python": sys.version,
            "docvortex": d.version,
            "package_path": str(package),
            "metadata_sha256": digest(d.read_text("METADATA").encode()),
            "record_sha256": digest(d.read_text("RECORD").encode()),
            "package_python_sources": sources,
            "source_tree_sha256": json_digest(sources),
            "project_urls": d.metadata.get_all("Project-URL"),
            "download_origin": d.read_text("direct_url.json"),
            "requires_dist": d.requires,
            "installed_distributions": sorted(
                (x.metadata["Name"], x.version) for x in metadata.distributions()
            ),
            "api": {
                "PageBlock": str(self.schema.PageBlock),
                "Block": str(self.schema.Block),
                "InlineSpan": str(self.schema.InlineSpan),
                "MiddleJson.from_dict": str(inspect.signature(self.schema.MiddleJson.from_dict)),
                "MiddleJson_path": inspect.getfile(self.schema.MiddleJson),
                "LatexDelimitersConfig_path": inspect.getfile(type(self.delimiters)),
                "TypeAdapter_path": inspect.getfile(type(self.page_block)),
                "pydantic_version": metadata.version("pydantic"),
                "render_single_block": {
                    "path": inspect.getfile(self.renderer),
                    "signature": str(inspect.signature(self.renderer)),
                },
                "render_visual_annotation": inspect.getfile(self.annotation_renderer),
                "render_inline_spans": inspect.getfile(self.inline_renderer),
                "model_config": {
                    k: self.schema.MiddleJson.model_config.get(k)
                    for k in ("extra", "strict", "validate_assignment", "serialize_by_alias")
                },
            },
        }


def differences(before, after, path=""):
    """Missing is distinct from every value. Changed lists are not ordinal-paired.

    Official normalization may merge inline spans. Replacing the complete list
    records that change without inventing cross-view occurrence identities.
    """
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for key in sorted(before.keys() | after.keys()):
            own = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in before:
                out.append({"path": own, "operation": "added", "after": observe(after[key])})
            elif key not in after:
                out.append({"path": own, "operation": "omitted", "before": observe(before[key])})
            else:
                out.extend(differences(before[key], after[key], own))
        return out
    if type(before) is type(after) and before == after:
        return []
    return [
        {
            "path": path,
            "operation": "list_replaced_without_occurrence_pairing"
            if isinstance(before, list) and isinstance(after, list)
            else "changed",
            "before_type": type(before).__name__,
            "after_type": type(after).__name__,
            "before": observe(before),
            "after": observe(after),
        }
    ]


def construction_changes(raw, typed, api, path=""):
    out = []
    if isinstance(typed, api.base_model) and isinstance(raw, dict):
        for key in raw:
            if hasattr(typed, key):
                out.extend(
                    construction_changes(raw[key], getattr(typed, key), api, path + "/" + key)
                )
    elif isinstance(typed, Enum):
        out.append(
            {
                "path": path,
                "raw_type": type(raw).__name__,
                "official_type": type(typed).__name__,
                "serialized": typed.value,
            }
        )
    elif isinstance(raw, list) and isinstance(typed, tuple):
        out.append(
            {
                "path": path,
                "raw_type": "list",
                "official_type": "tuple",
                "values_unchanged": list(typed) == raw,
            }
        )
    elif isinstance(raw, list) and isinstance(typed, list):
        # Inline normalization can alter cardinality; no positional assignment.
        if len(raw) == len(typed):
            for i, (a, b) in enumerate(zip(raw, typed, strict=True)):
                out.extend(construction_changes(a, b, api, path + "/" + str(i)))
        else:
            out.append(
                {
                    "path": path,
                    "operation": "official_list_normalization",
                    "before_count": len(raw),
                    "after_count": len(typed),
                    "occurrence_mapping": "not_established",
                }
            )
    elif type(raw) is not type(typed):
        out.append(
            {"path": path, "raw_type": type(raw).__name__, "official_type": type(typed).__name__}
        )
    return out


def error_detail(exc):
    return {"exception_type": type(exc).__name__, "message": str(exc)}


def attempt_schema(call, api):
    try:
        typed = call()
    except api.validation_error as exc:
        return None, {
            "status": "rejected",
            "category": 3,
            "reason": "official_schema_rejected_saved_payload",
            "errors": json.loads(exc.json(include_url=False, include_input=False)),
        }
    except BoundaryViolation as exc:
        return None, {
            "status": "not_executed",
            "category": 5,
            "reason": "official_call_blocked_by_boundary",
            **error_detail(exc),
        }
    except Exception as exc:
        return None, {
            "status": "error",
            "category": 5,
            "reason": "official_schema_call_exception",
            **error_detail(exc),
        }
    return typed, {"status": "accepted", "official_class": type(typed).__name__}


def attempt_projection(call):
    try:
        text = call()
        if not isinstance(text, str):
            raise RuntimeError("official renderer returned non-text")
    except BoundaryViolation as exc:
        return {
            "status": "blocked",
            "category": 5,
            "reason": "media_or_other_boundary",
            **error_detail(exc),
        }
    except (ValueError, TypeError, KeyError) as exc:
        return {
            "status": "failed",
            "category": 5,
            "reason": "official_text_projection_failed",
            **error_detail(exc),
        }
    except Exception as exc:
        return {
            "status": "error",
            "category": 5,
            "reason": "engineering_exception",
            **error_detail(exc),
        }
    return {"status": "rendered", "text": text, "utf8_sha256": digest(text.encode())}


def literal(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(literal(s.get("content")) for s in content if isinstance(s, dict))
    return ""


def compare_common(raw, common, parent, path):
    """Bind by immutable pointer, never by text, sorted ordinal or another view."""
    from app.adapters.native_readers import audit_copy

    if common is None:
        return {
            "status": "different",
            "category": 4,
            "reason": "common_occurrence_missing",
            "path": path,
        }
    checks = {
        "native_path": common.get("native_path") == path,
        "parent": common.get("parent_id") == parent,
        "native_payload": common.get("native_payload") == audit_copy(raw),
        "type": common.get("native_block_type") == raw.get("type"),
        "index": common.get("native_index", common.get("native_fields", {}).get("index"))
        == raw.get("index"),
    }
    if raw.get("type") in CONTAINERS and isinstance(raw.get("content"), list):
        checks["children"] = common.get("native_children") == [
            path + "/content/" + str(i) for i in range(len(raw["content"]))
        ]
    else:
        checks["literal"] = common.get("text") == literal(raw.get("content"))
        checks["native_content"] = common.get("native_content") == raw.get("content")
    return {
        "status": "retained" if all(checks.values()) else "different",
        "category": None if all(checks.values()) else 4,
        "checks": checks,
        "projection": observe(common),
    }


def compare_projection(record):
    """Compare source-bound text and order, without requiring Markdown bytes.

    Rendered positions below are content checks within this already bound
    occurrence. They never supply an identity for another saved view.
    """
    from app.adapters.native_readers import visible_text

    projected = record["projection"]
    if projected["status"] != "rendered":
        return {"status": "not_executed", "reason": projected["reason"]}
    raw, text = record["raw_payload"], projected["text"]
    role, content = raw.get("type"), raw.get("content")
    if role in CONTAINERS and isinstance(content, list):
        units = []

        def leaves(nodes, pointer):
            for i, child in enumerate(nodes):
                own = pointer + "/" + str(i)
                if not isinstance(child, dict):
                    continue
                if child.get("type") in CONTAINERS and isinstance(child.get("content"), list):
                    leaves(child["content"], own + "/content")
                else:
                    units.append((own, literal(child.get("content"))))

        leaves(content, record["path"] + "/content")
        cursor, locations = 0, []
        for pointer, unit in units:
            location = text.find(unit, cursor) if unit else cursor
            locations.append(
                {
                    "original_path": pointer,
                    "literal_sha256": digest(unit.encode()),
                    "rendered_span": [location, location + len(unit)] if location >= 0 else None,
                }
            )
            if location >= 0:
                cursor = location + len(unit)
        matched = all(r["rendered_span"] is not None for r in locations)
        return {
            "status": "retained" if matched else "needs_review",
            "category": 1 if matched else 6,
            "kind": "source_bound_container_and_ordered_literals",
            "member_locations": locations,
            "cross_view_identity_inferred_from_text": False,
            "common_parent_and_children_retained": record["common"]["status"] == "retained",
        }
    source = literal(content)
    common = record.get("common", {}).get("projection", {}).get("text")
    source_visible = visible_text(source, "html") if role == "table_body" else source
    official_visible = visible_text(text, "markdown")
    matched = official_visible == source_visible and common == source
    return {
        "status": "retained" if matched else "needs_review",
        "category": 1 if matched else 6,
        "kind": "HTML_table_display" if role == "table_body" else "inline_text_display",
        "source_visible": source_visible,
        "official_visible": official_visible,
        "literal_in_official": source in text,
        "official_bytes_equal_source": source == text,
        "common_literal_equal_source": common == source,
        "table_HTML_equal_source": text == source if role == "table_body" else None,
    }


def media_placeholder(path, callbacks, obj):
    callbacks.append(
        {
            "render_owner_path": path,
            "official_type": str(obj.type),
            "index": obj.index,
            "bbox": list(obj.bbox) if obj.bbox is not None else None,
            "media_declarations": observe(
                {k: getattr(obj, k) for k in MEDIA_FIELDS if hasattr(obj, k)}
            ),
            "delivery": "declaration_only_not_delivered",
        }
    )
    return "<!-- validation media declaration; no asset delivered -->"


def validate_objects(nodes, pointer, api, common_by_path, *, parent=None, context=None):
    records = []
    for i, raw in enumerate(nodes):
        path = pointer + "/" + str(i)
        role = raw.get("type") if isinstance(raw, dict) else None
        record = {
            "path": path,
            "parent_path": parent,
            "native_type": role,
            "raw_payload": observe(raw),
            "raw_payload_sha256": json_digest(raw),
        }
        adapter = api.page_block if parent is None else api.block
        record["official_schema_type"] = "PageBlock" if parent is None else "Block"
        typed, record["schema"] = attempt_schema(
            partial(adapter.validate_python, copy.deepcopy(raw)), api
        )
        if typed is not None:
            full = typed.model_dump(mode="json")
            compact = typed.to_dict()
            record["serialization"] = {
                "full": observe(full),
                "to_dict": observe(compact),
                "full_diff": differences(raw, full),
                "to_dict_diff": differences(raw, compact),
                "construction_changes": construction_changes(raw, typed, api),
                "derived_fields_are_native_observations": False,
                "worker_media_exclusion_diff": differences(
                    compact, typed.to_dict(exclude_block_fields={"image_base64"})
                ),
            }
            callbacks = []
            placeholder = partial(media_placeholder, path, callbacks)

            if parent is None or role in {str(t) for t in api.schema.PAGE_BLOCK_TYPES}:
                call = partial(
                    api.renderer,
                    typed,
                    delimiters=api.delimiters,
                    asset_base_url="",
                    image_renderer=placeholder,
                )
                record["projection_call"] = "render_single_block(original_typed_object)"
            elif role in {
                "table_caption",
                "table_footnote",
                "image_caption",
                "image_footnote",
                "chart_caption",
                "chart_footnote",
                "code_caption",
                "code_footnote",
            }:
                call = partial(api.annotation_renderer, typed, api.delimiters)
                record["projection_call"] = "render_visual_annotation(original_typed_object)"
            elif role == "table_body" and context is not None and str(context.type) == "table":
                # The worker already uses this official body-only context. The
                # schema input above is untouched, including its media field.
                body_context = context.model_copy(update={"content": [typed]}, deep=True)
                call = partial(
                    api.renderer,
                    body_context,
                    delimiters=api.delimiters,
                    asset_base_url="",
                    image_renderer=placeholder,
                )
                record["projection_call"] = (
                    "render_single_block(original_parent.model_copy(content=[original_typed_body]))"
                )
                record["projection_context"] = {
                    "parent_path": parent,
                    "changed_fields": ["content"],
                    "purpose": "body_only_display_not_schema_input",
                }
            else:
                call = None
                record["projection"] = {
                    "status": "not_executed",
                    "reason": "no_standalone_safe_PageBlock_projection",
                    "category": 6,
                }
            if call is not None:
                record["projection"] = attempt_projection(call)
            record["media_callback_calls"] = callbacks
        else:
            record["projection"] = {
                "status": "not_executed",
                "reason": "official_schema_not_accepted",
            }
        if isinstance(raw, dict):
            record["upstream_state"] = {
                k: observe(raw[k])
                for k in (
                    "status",
                    "error",
                    "errors",
                    "warnings",
                    "timed_out",
                    "truncated",
                    "processed",
                )
                if k in raw
            }
            record["common"] = compare_common(raw, common_by_path.get(path), parent, path)
            record["text_comparison"] = compare_projection(record)
            record["difference_classifications"] = []
            if record.get("serialization", {}).get("full_diff") or record.get(
                "serialization", {}
            ).get("to_dict_diff"):
                record["difference_classifications"].append(
                    {
                        "category": 2,
                        "reason": "observed_official_defaults_or_serialization; original_not_modified",
                    }
                )
            if record["schema"]["status"] != "accepted":
                record["difference_classifications"].append(
                    {"category": record["schema"]["category"], "reason": record["schema"]["reason"]}
                )
            if record["common"]["status"] != "retained":
                record["difference_classifications"].append(
                    {"category": 4, "reason": "common_read_does_not_retain_source"}
                )
            if record["text_comparison"]["status"] in {"retained", "needs_review"}:
                record["difference_classifications"].append(
                    {
                        "category": record["text_comparison"]["category"],
                        "reason": "official_display_checked_against_own_literal_and_structure",
                    }
                )
            content = raw.get("content")
            if role in CONTAINERS and isinstance(content, list):
                record["original_children"] = [
                    path + "/content/" + str(j) for j in range(len(content))
                ]
                children = validate_objects(
                    content, path + "/content", api, common_by_path, parent=path, context=typed
                )
                records.append(record)
                records.extend(children)
                continue
            if isinstance(content, list):
                record["inline_occurrences"] = validate_inline(
                    content, path + "/content", api, path
                )
        records.append(record)
    return records


def validate_inline(spans, pointer, api, owner):
    records = []
    for i, span in enumerate(spans):
        path = pointer + "/" + str(i)
        typed, state = attempt_schema(partial(api.inline.validate_python, copy.deepcopy(span)), api)
        row = {
            "path": path,
            "owner_path": owner,
            "parent_path": pointer.rsplit("/content", 1)[0],
            "native_type": span.get("type") if isinstance(span, dict) else None,
            "raw_payload": observe(span),
            "schema": state,
            "mapping_to_normalized_parent_spans": "not_assumed; independent original span validation",
        }
        if typed is not None:
            full = typed.model_dump(mode="json")
            row.update(
                serialization={"full": observe(full), "diff": differences(span, full)},
                projection=attempt_projection(
                    partial(api.inline_renderer, [typed], api.delimiters)
                ),
            )
        else:
            row["projection"] = {"status": "not_executed", "reason": "official_schema_not_accepted"}
        if isinstance(span, dict) and isinstance(span.get("content"), list):
            row["children"] = validate_inline(span["content"], path + "/content", api, owner)
        records.append(row)
    return records


def bind_inline_rows(items, binding):
    for span in items:
        span["binding"] = binding
        bind_inline_rows(span.get("children", []), binding)


def validate_native(native, native_sha256, pipeline, api):
    from app.adapters.mineru_native import read_middle_page, source_page

    if pipeline not in {"P06", "P07"} or native.get("pipeline") != pipeline:
        raise ValueError("only own P06/P07 saved inputs are admitted")
    original = json_digest(native)
    pages, documents, objects = [], {}, []
    for position, entry in enumerate(native["pages"]):
        if entry.get("branch") != "mineru":
            pages.append(
                {
                    "entry_path": f"#/pages/{position}",
                    "branch": entry.get("branch"),
                    "input_page": entry.get("page"),
                    "schema": {
                        "status": "not_applicable",
                        "reason": "GLM_primary_view_not_DocVortex",
                    },
                }
            )
            continue
        page, pointer, document = source_page(native, entry)
        blocks, containers, detail = read_middle_page(native, entry)
        common_by_path = {}
        for item in [*blocks, *containers]:
            if item["native_path"] in common_by_path:
                raise ValueError("duplicate common source occurrence")
            common_by_path[item["native_path"]] = item
        doc_path = pointer.split("/pages/", 1)[0]
        if doc_path not in documents:
            typed_doc, state = attempt_schema(
                partial(api.schema.MiddleJson.from_dict, copy.deepcopy(document)), api
            )
            doc_record = {
                "path": doc_path,
                "schema": state,
                "call": "docvortex.schema.MiddleJson.from_dict(original_document)",
            }
            if typed_doc is not None:
                doc_record["serialization"] = {
                    "full": observe(typed_doc.model_dump(mode="json")),
                    "to_dict": observe(typed_doc.to_dict()),
                    "full_diff": differences(document, typed_doc.model_dump(mode="json")),
                    "to_dict_diff": differences(document, typed_doc.to_dict()),
                }
            documents[doc_path] = doc_record
        _, page_state = attempt_schema(
            partial(api.schema.PageInfo.model_validate, copy.deepcopy(page)), api
        )
        rows = validate_objects(page["blocks"], pointer + "/blocks", api, common_by_path)
        binding = {
            "native_sha256": native_sha256,
            "pipeline": pipeline,
            "tier": document["extensions"]["mineru"]["tier"],
            "document_path": doc_path,
            "page_path": pointer,
            "input_page": entry["page"],
            "page_idx": page["page_idx"],
        }
        for row in rows:
            row["binding"] = binding
            bind_inline_rows(row.get("inline_occurrences", []), binding)
        objects.extend(rows)
        pages.append(
            {
                **binding,
                "entry_path": f"#/pages/{position}",
                "schema": page_state,
                "common_read": detail,
                "top_level_paths": [
                    pointer + "/blocks/" + str(i) for i in range(len(page["blocks"]))
                ],
                "common_unmatched_paths": sorted(set(common_by_path) - {r["path"] for r in rows}),
            }
        )
    inline = []

    def collect(rows):
        for row in rows:
            inline.append(row)
            collect(row.get("children", []))

    for row in objects:
        collect(row.get("inline_occurrences", []))
    schema_rows = [
        *documents.values(),
        *[p for p in pages if p["schema"]["status"] != "not_applicable"],
        *objects,
        *inline,
    ]
    problems = [
        {"path": r.get("path", r.get("page_path")), "reason": r["schema"].get("reason")}
        for r in schema_rows
        if r["schema"]["status"] in {"error", "not_executed"}
    ]
    problems.extend(
        {"path": r["path"], "reason": "common_source_or_text_difference"}
        for r in objects
        if r.get("common", {}).get("status") == "different"
        or r.get("text_comparison", {}).get("status") == "needs_review"
    )
    problems.extend(
        {"path": r["path"], "reason": r["projection"].get("reason")}
        for r in [*objects, *inline]
        if r["schema"]["status"] == "accepted" and r["projection"]["status"] != "rendered"
    )
    return {
        "purpose": "fixed_saved_Middle_official_schema_and_text_validation_only",
        "execution_status": "incomplete"
        if problems
        else "completed_with_saved_schema_rejection"
        if any(r["schema"]["status"] == "rejected" for r in schema_rows)
        else "completed",
        "execution_problems": problems,
        "pipeline": pipeline,
        "native_sha256": native_sha256,
        "documents": list(documents.values()),
        "pages": pages,
        "objects": objects,
        "summary": {
            "document_schema": dict(Counter(r["schema"]["status"] for r in documents.values())),
            "page_schema": dict(Counter(r["schema"]["status"] for r in pages)),
            "object_schema": dict(Counter(r["schema"]["status"] for r in objects)),
            "object_projection": dict(Counter(r["projection"]["status"] for r in objects)),
            "inline_schema": dict(Counter(r["schema"]["status"] for r in inline)),
            "inline_projection": dict(Counter(r["projection"]["status"] for r in inline)),
            "common_comparison": dict(
                Counter(r["common"]["status"] for r in objects if "common" in r)
            ),
            "text_comparison": dict(
                Counter(r["text_comparison"]["status"] for r in objects if "text_comparison" in r)
            ),
            "schema_defaults_and_serialization_differences": sum(
                bool(
                    r.get("serialization", {}).get("full_diff")
                    or r.get("serialization", {}).get("to_dict_diff")
                )
                for r in objects
            ),
            "media_callbacks": sum(len(r.get("media_callback_calls", [])) for r in objects),
        },
        "input_unchanged": json_digest(native) == original,
        "quality_acceptance": False,
        "production_path_changed": False,
        "uncovered": [
            "content_list absent",
            "formula absent",
            "cross-page continuation absent",
            "other samples and formats",
            "media delivery",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-only", action="store_true")
    parser.add_argument("--native", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--pipeline", choices=["P06", "P07"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("use a new output; historical evidence is immutable")
    boundary = TextOnlyBoundary()
    boundary.install()
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    try:
        api = OfficialAPI()
    except (DependencyUnavailable, ImportError, BoundaryViolation) as exc:
        record = {
            "status": "not_executed",
            "reason": error_detail(exc),
            "sys_executable": sys.executable,
            "official_calls": 0,
            "command": [sys.executable, *sys.argv],
            "boundary_violations": boundary.violations,
        }
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        return 2
    if args.environment_only:
        record = api.identity()
    else:
        if args.native is None or not args.sha256 or not args.pipeline:
            parser.error("native, SHA256 and pipeline are required for validation")
        data = args.native.read_bytes()
        if digest(data) != args.sha256:
            parser.error("immutable native SHA256 mismatch")
        record = validate_native(json.loads(data), digest(data), args.pipeline, api)
        record["input_bytes_unchanged"] = digest(args.native.read_bytes()) == args.sha256
    record["boundary"] = {
        "violations": boundary.violations,
        "imported_modules": sorted(boundary.imported),
        "network": "container_none",
        "gpu": "runtime_runc_no_devices",
        "media_decode_guard": True,
        "worker_imported": "native_worker.server" in sys.modules,
        "address_space_limit_bytes": resource.getrlimit(resource.RLIMIT_AS)[0],
    }
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "summary": record.get("summary"),
                "docvortex": PINNED_VERSION,
                "boundary_violations": len(boundary.violations),
            }
        )
    )
    return int(
        bool(boundary.violations)
        or record.get("execution_status") == "incomplete"
        or record.get("input_unchanged") is False
        or record.get("input_bytes_unchanged") is False
    )


if __name__ == "__main__":
    raise SystemExit(main())
