"""Impact of verified source observations on actual source-free obligations.

An unknown field is retained even when no current output consumes it. Status
depends on the source-bound responsibility, never on pipeline or warning name.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any


def execution_incomplete(metadata):
    status = str(metadata.get("status", "")).casefold()
    return bool(metadata.get("error") or metadata.get("errors") or metadata.get("timed_out")
                or metadata.get("truncated") or metadata.get("unprocessed_pages")
                or metadata.get("length_limit_reached") or metadata.get("reached_max_new_tokens")
                or metadata.get("possible_length_truncation")
                or any(word in status for word in ("fail", "error", "partial", "timeout", "truncat")))


def native_status_impacts(result):
    """Read validated facts and consumer dependencies; never infer missing text."""
    contract = result._native_content
    if contract is None:
        raise ValueError("native status requires a bound evidence contract")
    state = result._source_verification["native_content"]
    bridge = result._source_verification["saved_native_bridge"]
    blocks = {(page, b.get("occurrence_id", b.get("id"))): b
              for page, values in result._native_page_blocks.items() for b in values}
    items = [i for i in contract.items if i.kind in {"content", "table", "picture"}]
    impacts = []
    covered = set()

    def add(code, category, sources, fields, *, effects=(), dependencies=(), blocking=False,
            conversion=False, observation=None):
        impacts.append({"code": code, "category": category, "sources": sources,
            "objects": [s["occurrence_id"] for s in sources if s.get("occurrence_id")],
            "affected_output_fields": fields,
            "effects": {k: k in effects for k in ("body_content", "reading_order", "table_relations", "asset_delivery")},
            "dependencies": list(dependencies), "blocks_conversion": blocking and conversion,
            "requires_partial": blocking, "warning_only": not blocking,
            "observation": observation})

    def source(item):
        return {**asdict(item.locator), "input_page": item.input_page, "occurrence_id": item.identity}

    def native_page(page):
        binding: dict[str, Any] = next((p for p in contract.page_bindings if p["input_page"] == page), {})
        return {"artifact_sha256": contract.artifact.sha256, "view": "saved_native",
                "path": binding.get("entry", "#/pages"), "input_page": page}

    pending = result._final_text_evidence.get("unresolved_continuations", [])
    for page in contract.selected_pages:
        own = [i for i in items if i.input_page == page]
        # Both textual regions and table/image occurrences have a position in
        # the delivered sequence. A singleton has no pairwise order obligation.
        sequence = [i for i in own if i.raw_text or i.kind in {"table", "picture"}]
        for item in own:
            b = blocks.get((page, item.identity), {})
            if item.order_basis not in {"native_index", "native_reading_tree"}:
                dependent = len(sequence) > 1 and item in sequence
                add("native_reading_order_unverified", "native_metadata_unknown", [source(item)],
                    ["body.reading_order"] if dependent else ["native_metadata.reading_order"],
                    effects=("body_content", "reading_order") if dependent else (),
                    dependencies=[{"obligation": "order_multiple_output_occurrences", "objects": [i.identity for i in sequence]}]
                        if dependent else [], blocking=dependent, conversion=True,
                    observation={"order_basis": item.order_basis, "native_order": list(item.order)})
                covered.add(("native_reading_order_unverified", item.locator.path))
            group = b.get("group_identity")
            if isinstance(group, dict) and group.get("parent_relationship") == "unknown":
                dependent = bool(b.get("merge_prev") or b.get("continues_prev")) and any(
                    p.get("native_path") == item.locator.path for p in pending)
                add("native_group_semantics_unknown", "native_metadata_unknown", [source(item)],
                    ["body.continuation_scope"] if dependent else ["native_metadata.group_relationship"],
                    effects=("body_content",) if dependent else (),
                    dependencies=[{"obligation": "resolve_declared_continuation", "object": item.identity}]
                        if dependent else [], blocking=dependent, conversion=True, observation=group)
                covered.add(("native_group_semantics_unknown", item.locator.path))
            # Source-free text/relations do not consume a crop transform. Keep
            # geometry limits explicit; actual media delivery has its own duty.
            if b.get("geometry_status") == "unknown":
                add("native_geometry_transform_unknown", "native_metadata_unknown", [source(item)],
                    ["native_metadata.geometry", "ir.bbox"], observation=b.get("geometry_basis"))
                covered.add(("native_geometry_transform_unknown", item.locator.path))
            if b.get("polygon_status") == "unknown":
                add("native_polygon_unresolved", "native_metadata_unknown", [source(item)],
                    ["native_metadata.polygon"], observation=b.get("native_polygon_fields"))
                covered.add(("native_polygon_unresolved", item.locator.path))
            if b.get('service_bbox') is None:
                add('native_geometry_unknown_or_conflicting', 'native_metadata_unknown', [source(item)],
                    ['native_metadata.geometry', 'ir.bbox'],
                    observation={'native_bbox': b.get('bbox'), 'coordinate_system': b.get('coordinate_system'),
                                 'coordinate_origin': b.get('coordinate_origin'),
                                 'current_crop_consumer': 'disabled_source_free_mode'})
                covered.add(('native_geometry_unknown_or_conflicting', item.locator.path))
            if b.get('read_error') or b.get('type') == 'unknown' or b.get('read_status') == 'unresolved':
                add('native_content_projection_incomplete',
                    'format_readback_failure' if b.get('read_error') else 'conversion_not_supported',
                    [source(item)], ['body.content_or_structure'], effects=('body_content',),
                    blocking=True, conversion=True,
                    observation={'native_label': item.details.get('label'), 'consumer_role': b.get('type'),
                                 'read_status': b.get('read_status'), 'read_error': b.get('read_error')})
            declaration = b.get('native_table_declaration', {})
            if declaration.get('continues_prev') is True:
                add('native_table_continuation_unresolved', 'output_responsibility_unresolved',
                    [source(item)], ['body.table_relations'], effects=('table_relations',),
                    dependencies=[{'obligation': 'complete_cross_page_header_and_cell_partition'}],
                    blocking=True, conversion=True, observation=declaration)

    media_paths = {(i.input_page, i.locator.path) for i in contract.items if i.kind == "media"}
    for item in contract.items:
        if item.kind == 'container':
            declaration = item.details.get('continuation', {})
            if item.details.get('label') != 'table' and any(v is True for v in declaration.values()):
                add('native_container_continuation_unresolved', 'output_responsibility_unresolved',
                    [source(item)], ['body.continuation_scope'], effects=('body_content', 'reading_order'),
                    blocking=True, conversion=True, observation=declaration)
            if item.details.get('label') in {'table', 'image', 'chart', 'code'} and item.details.get('native_children') == []:
                add('native_container_content_unavailable', 'format_readback_failure', [source(item)],
                    ['body.content_or_structure'], effects=('body_content',), blocking=True, conversion=True)
        if item.kind == "media":
            add("native_media_not_delivered", "asset_delivery_incomplete", [source(item)],
                ["assets", "body.media_occurrence"], effects=("asset_delivery",), blocking=True,
                observation={"bytes_read": False, "verified": False, "delivered": False})

    execution = contract.execution.metadata
    execution_source = {"artifact_sha256": contract.execution.artifact_sha256,
                        "artifact_identity": contract.execution.artifact_identity,
                        "view": "original_execution", "path": "#"}
    page_states = execution.get("pages", [])
    observed_pages = {p.get("page", p.get("page_number")) for p in page_states}
    for warning in execution.get('warnings', []):
        add('original_execution_warning', 'execution_information', [execution_source],
            ['execution.warnings'], observation=warning)
    if execution.get("status") not in {"completed", "warning"} or execution_incomplete(execution):
        unknown = execution.get('status') in {None, 'unknown'}
        add("original_execution_completeness_unknown" if unknown else "original_execution_incomplete",
            "original_execution_unknown" if unknown else "original_execution", [execution_source],
            ["execution.coverage"], effects=("body_content",), blocking=True, observation=execution)
    if set(contract.selected_pages) - observed_pages:
        add("original_execution_page_coverage_unknown", "original_execution_unknown", [execution_source],
            ["execution.processed_pages"], effects=("body_content",), blocking=True,
            observation={"unverified_pages": sorted(set(contract.selected_pages) - observed_pages)})
    incomplete_pages = set()
    for index, p in enumerate(page_states):
        page = p.get("page", p.get("page_number"))
        if page not in contract.selected_pages:
            continue
        if p.get("status") not in {"completed", "warning"} or execution_incomplete(p):
            incomplete_pages.add(page)
            add("original_page_incomplete", "original_execution", [{**execution_source, "path": f"#/pages/{index}", "input_page": page}],
                ["execution.page_coverage"], effects=("body_content",), blocking=True, observation=p)
    for record in execution.get("native_status_evidence", []):
        if execution_incomplete(record["metadata"]):
            pages = record.get("input_pages", [])
            incomplete_pages.update(pages)
            add("native_execution_incomplete", "original_execution", [{"artifact_sha256": contract.artifact.sha256,
                "view": "native_execution_metadata", "path": record["native_path"]}],
                ["execution.native_coverage"], effects=("body_content",), blocking=True, observation=record)

    for page in bridge["pages"]:
        number = page["raw_page"]
        for issue in page.get("local_read_errors", []):
            paths = issue.get("native_paths", [issue.get("native_path")])
            if paths and all((issue["code"], p) in covered for p in paths):
                continue  # The observation above records its real dependencies.
            if any((number, p) in media_paths for p in paths) and issue["code"] == "saved_native_media_unverified":
                continue
            if number in incomplete_pages and issue["code"] == "saved_native_producer_incomplete":
                continue
            related = [b for (p, _), b in blocks.items() if p == number and b.get('native_path') in paths]
            sources = [source(i) for i in items if i.input_page == number and i.locator.path in paths] or [native_page(number)]
            # Categorize the observed failure stage, independently of severity:
            # decoder errors, absent native positions and unsupported consumer
            # roles are different causes even though each blocks conversion.
            if any(b.get('read_error') for b in related) or page.get('error'):
                category = 'format_readback_failure'
            elif any(b.get('kind') == 'table' and (not b.get('cells') or any(
                type(c.get(k)) is not int for c in b.get('cells', []) for k in ('row', 'col', 'row_span', 'col_span')))
                for b in related):
                category = 'native_information_missing'
            elif any(b.get('kind') == 'table' and not b.get('service_fragment_id') for b in related):
                category = 'native_structure_incomplete'
            elif any(b.get('read_status') == 'unresolved' for b in related):
                category = 'conversion_not_supported'
            else:
                category = 'output_responsibility_unresolved'
            add(issue["code"], category, sources, ["body.content_or_structure"],
                effects=("body_content", "table_relations") if any(i.kind == "table" and i.locator.path in paths for i in items)
                        else ("body_content",), blocking=True, conversion=True, observation=issue)
    for issue in bridge.get("errors", []):
        if "code" in issue:  # Document identity/structure errors, not page warning copies.
            add(issue["code"], "native_structure_error", [native_page(None)], ["body.page_coverage"],
                effects=("body_content",), blocking=True, conversion=True, observation=issue)
    for view in result._semantic_tables:
        if view.status != "converted":
            table_items = [i for i in items if any(b.get("service_fragment_id") in view.source_tables
                for key, b in blocks.items() if key == (i.input_page, i.identity))]
            add("table_semantics_incomplete", "conversion_unsupported_or_incomplete", [source(i) for i in table_items],
                ["body.table_relations"], effects=("body_content", "table_relations"),
                blocking=True, conversion=True, observation={"view_id": view.view_id, "status": view.status,
                                                            "reasons": list(view.reason_codes)})
    if result._final_text_evidence:
        accounted = {t for v in result._semantic_tables for t in v.source_tables}
        for (page, ident), b in blocks.items():
            if b.get('service_fragment_id') and b['service_fragment_id'] not in accounted:
                item = next(i for i in items if (i.input_page, i.identity) == (page, ident))
                add('table_conversion_not_accounted', 'output_responsibility_unresolved', [source(item)],
                    ['body.table_relations'], effects=('body_content', 'table_relations'),
                    blocking=True, conversion=True)
    for p in pending:
        add("final_continuation_incomplete", "output_responsibility_unresolved", [native_page(p["page"])],
            ["body.continuation_scope"], effects=("body_content", "reading_order"),
            blocking=True, conversion=True, observation=p)
    if state["readback"]["status"] == "partial" and not any(i["blocks_conversion"] for i in impacts):
        add("native_readback_incomplete", "native_read_error", [native_page(None)], ["body.content"],
            effects=("body_content",), blocking=True, conversion=True)
    return impacts
